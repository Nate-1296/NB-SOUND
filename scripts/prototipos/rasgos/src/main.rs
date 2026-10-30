//! Prototipo F0.4.4: rasgos básicos de la V1 (librosa) en Rust.
//!
//! Código desechable. Replica lo que hacía `legado/core/audio_features.py` en modo
//! `light`: 90 s desde el principio, mono a 22.050 Hz, y de ahí tempo (el estimador
//! de `librosa.feature.tempo` que usa `beat_track`), RMS, centroide, ancho de banda,
//! rolloff y ZCR. Compara contra lo que la V1 guardó en `track_audio_features`.
//!
//! Uso: cargo run --release -- <base-v1.sqlite3> [máximo]

mod decodificar;

use std::f64::consts::PI;
use std::path::Path;
use std::sync::Arc;

use rubato::{FftFixedIn, Resampler};
use rustfft::num_complex::Complex;
use rustfft::{Fft, FftPlanner};

const SR: f64 = 22_050.0;
const N_FFT: usize = 2048;
const HOP: usize = 512;
const N_MELS: usize = 128;

/// Mono a 22.050 Hz de los primeros `segundos`.
fn cargar(ruta: &Path, segundos: f64) -> Option<Vec<f32>> {
    let pcm = decodificar::decodificar(ruta, None).ok()?;
    let n = ((segundos * pcm.tasa as f64) as usize).min(pcm.frames());
    let mono: Vec<f32> = pcm.muestras[..n * 2].chunks_exact(2).map(|f| (f[0] + f[1]) * 0.5).collect();
    if pcm.tasa as f64 == SR {
        return Some(mono);
    }
    let trozo = 4096;
    let mut rs = FftFixedIn::<f32>::new(pcm.tasa as usize, SR as usize, trozo, 2, 1).ok()?;
    let mut salida = Vec::with_capacity((n as f64 * SR / pcm.tasa as f64) as usize + trozo);
    let mut i = 0;
    while i + trozo <= mono.len() {
        let out = rs.process(&[&mono[i..i + trozo]], None).ok()?;
        salida.extend_from_slice(&out[0]);
        i += trozo;
    }
    if i < mono.len() {
        let out = rs.process_partial(Some(&[&mono[i..]]), None).ok()?;
        salida.extend_from_slice(&out[0]);
    }
    // El retardo del remuestreador se descarta para alinear con el original.
    let retardo = rs.output_delay();
    let esperado = (mono.len() as f64 * SR / pcm.tasa as f64).round() as usize;
    Some(salida.into_iter().skip(retardo).take(esperado).collect())
}

fn hann_periodica(n: usize) -> Vec<f64> {
    (0..n).map(|i| 0.5 - 0.5 * (2.0 * PI * i as f64 / n as f64).cos()).collect()
}

/// Espectrograma de potencia centrado (relleno de ceros), como `librosa.stft`.
fn espectrograma(y: &[f32], fft: &Arc<dyn Fft<f64>>) -> Vec<Vec<f64>> {
    let ventana = hann_periodica(N_FFT);
    let mut rel = vec![0f64; N_FFT / 2];
    rel.extend(y.iter().map(|&v| v as f64));
    rel.extend(std::iter::repeat_n(0.0, N_FFT / 2));
    let marcos = 1 + y.len() / HOP;
    let mut buf = vec![Complex::new(0.0, 0.0); N_FFT];
    (0..marcos)
        .map(|t| {
            let ini = t * HOP;
            for k in 0..N_FFT {
                buf[k] = Complex::new(rel.get(ini + k).copied().unwrap_or(0.0) * ventana[k], 0.0);
            }
            fft.process(&mut buf);
            buf[..=N_FFT / 2].iter().map(|c| c.norm_sqr()).collect()
        })
        .collect()
}

fn hz_a_mel(f: f64) -> f64 {
    let f_sp = 200.0 / 3.0;
    let min_log_hz = 1000.0;
    let min_log_mel = min_log_hz / f_sp;
    let logstep = (6.4f64).ln() / 27.0;
    if f >= min_log_hz { min_log_mel + (f / min_log_hz).ln() / logstep } else { f / f_sp }
}

fn mel_a_hz(m: f64) -> f64 {
    let f_sp = 200.0 / 3.0;
    let min_log_hz = 1000.0;
    let min_log_mel = min_log_hz / f_sp;
    let logstep = (6.4f64).ln() / 27.0;
    if m >= min_log_mel { min_log_hz * (logstep * (m - min_log_mel)).exp() } else { f_sp * m }
}

/// Banco de filtros mel de Slaney normalizado, como `librosa.filters.mel`.
fn banco_mel() -> Vec<Vec<f64>> {
    let nbins = N_FFT / 2 + 1;
    let fftf: Vec<f64> = (0..nbins).map(|k| k as f64 * SR / N_FFT as f64).collect();
    let (mmin, mmax) = (hz_a_mel(0.0), hz_a_mel(SR / 2.0));
    let melf: Vec<f64> = (0..N_MELS + 2)
        .map(|i| mel_a_hz(mmin + (mmax - mmin) * i as f64 / (N_MELS + 1) as f64))
        .collect();
    (0..N_MELS)
        .map(|i| {
            let enorm = 2.0 / (melf[i + 2] - melf[i]);
            fftf.iter()
                .map(|&f| {
                    let bajo = (f - melf[i]) / (melf[i + 1] - melf[i]);
                    let alto = (melf[i + 2] - f) / (melf[i + 2] - melf[i + 1]);
                    bajo.min(alto).max(0.0) * enorm
                })
                .collect()
        })
        .collect()
}

/// Envolvente de onsets como la calcula `librosa.beat.beat_track`.
fn onsets(potencia: &[Vec<f64>], mel: &[Vec<f64>]) -> Vec<f64> {
    let mut db: Vec<Vec<f64>> = potencia
        .iter()
        .map(|p| {
            mel.iter()
                .map(|filtro| {
                    let e: f64 = filtro.iter().zip(p).map(|(w, x)| w * x).sum();
                    10.0 * e.max(1e-10).log10()
                })
                .collect()
        })
        .collect();
    let maximo = db.iter().flatten().fold(f64::MIN, |m, &v| m.max(v));
    for fila in &mut db {
        for v in fila.iter_mut() {
            *v = v.max(maximo - 80.0);
        }
    }
    let n = db.len();
    let mut env = vec![0.0; n];
    // diferencia con retardo 1, media por bandas, desplazada lag + n_fft/(2*hop) = 3
    for t in 1..n {
        // `beat_track` agrega con la mediana, no con la media de `onset_strength`.
        let mut d: Vec<f64> = db[t].iter().zip(&db[t - 1]).map(|(a, b)| (a - b).max(0.0)).collect();
        d.sort_by(f64::total_cmp);
        let d = (d[N_MELS / 2 - 1] + d[N_MELS / 2]) / 2.0;
        if t + 2 < n {
            env[t + 2] = d;
        }
    }
    env
}

/// `librosa.feature.tempo` (start_bpm 120, std_bpm 1, ac_size 8 s, max 320).
fn tempo(env: &[f64]) -> f64 {
    let win = (8.0 * SR / HOP as f64).floor() as usize;
    let mitad = win / 2;
    let n = env.len();
    let (izq, der) = (env.first().copied().unwrap_or(0.0), env.last().copied().unwrap_or(0.0));
    let mut rel = Vec::with_capacity(n + 2 * mitad);
    for i in 0..mitad {
        rel.push(izq * i as f64 / mitad as f64);
    }
    rel.extend_from_slice(env);
    for i in 0..mitad {
        rel.push(der * (mitad - i) as f64 / mitad as f64);
    }
    let ventana = hann_periodica(win);
    let npad = 2 * win - 1;
    let mut plan = FftPlanner::<f64>::new();
    let (ida, vuelta) = (plan.plan_fft_forward(npad), plan.plan_fft_inverse(npad));
    let mut acum = vec![0.0; win];
    let mut buf = vec![Complex::new(0.0, 0.0); npad];
    for t in 0..n {
        buf.iter_mut().for_each(|c| *c = Complex::new(0.0, 0.0));
        for k in 0..win {
            buf[k] = Complex::new(rel.get(t + k).copied().unwrap_or(0.0) * ventana[k], 0.0);
        }
        ida.process(&mut buf);
        buf.iter_mut().for_each(|c| *c = Complex::new(c.norm_sqr(), 0.0));
        vuelta.process(&mut buf);
        let ac: Vec<f64> = buf[..win].iter().map(|c| c.re / npad as f64).collect();
        let m = ac.iter().fold(0f64, |m, v| m.max(v.abs()));
        if m > f64::MIN_POSITIVE {
            for (a, v) in acum.iter_mut().zip(&ac) {
                *a += v / m;
            }
        }
    }
    let mut mejor = (f64::MIN, 0.0);
    for lag in 1..win {
        let bpm = 60.0 * SR / (HOP as f64 * lag as f64);
        if bpm > 320.0 {
            continue;
        }
        let prior = -0.5 * ((bpm.log2() - 120f64.log2()) / 1.0).powi(2);
        let tg = acum[lag] / n as f64;
        let v = (1e6 * tg).ln_1p() + prior;
        if v > mejor.0 {
            mejor = (v, bpm);
        }
    }
    mejor.1
}

struct Rasgos {
    bpm: f64,
    rms: f64,
    centroide: f64,
    zcr: f64,
}

fn rasgos(y: &[f32], fft: &Arc<dyn Fft<f64>>, mel: &[Vec<f64>]) -> Rasgos {
    let pot = espectrograma(y, fft);
    let bpm = tempo(&onsets(&pot, mel));
    // RMS y ZCR por marcos de 2048 / 512 centrados, como librosa.
    let marcos = 1 + y.len() / HOP;
    let mut rel = vec![0f32; N_FFT / 2];
    rel.extend_from_slice(y);
    rel.extend(std::iter::repeat_n(0.0, N_FFT / 2));
    let (mut rms, mut zcr) = (0.0, 0.0);
    for t in 0..marcos {
        let m = &rel[t * HOP..(t * HOP + N_FFT).min(rel.len())];
        rms += (m.iter().map(|v| (*v as f64).powi(2)).sum::<f64>() / N_FFT as f64).sqrt();
        zcr += m.windows(2).filter(|w| (w[0] >= 0.0) != (w[1] >= 0.0)).count() as f64 / N_FFT as f64;
    }
    // Centroide sobre la magnitud.
    let freqs: Vec<f64> = (0..=N_FFT / 2).map(|k| k as f64 * SR / N_FFT as f64).collect();
    let mut cent = 0.0;
    for p in &pot {
        let mag: Vec<f64> = p.iter().map(|v| v.sqrt()).collect();
        let s: f64 = mag.iter().sum();
        if s > 0.0 {
            cent += mag.iter().zip(&freqs).map(|(m, f)| m * f).sum::<f64>() / s;
        }
    }
    Rasgos {
        bpm,
        rms: rms / marcos as f64,
        centroide: cent / pot.len() as f64,
        zcr: zcr / marcos as f64,
    }
}

fn pearson(a: &[f64], b: &[f64]) -> f64 {
    let n = a.len() as f64;
    let (ma, mb) = (a.iter().sum::<f64>() / n, b.iter().sum::<f64>() / n);
    let cov: f64 = a.iter().zip(b).map(|(x, y)| (x - ma) * (y - mb)).sum();
    let va: f64 = a.iter().map(|x| (x - ma).powi(2)).sum();
    let vb: f64 = b.iter().map(|y| (y - mb).powi(2)).sum();
    cov / (va * vb).sqrt()
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let base = rusqlite::Connection::open_with_flags(
        &args[1],
        rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY,
    )
    .expect("base de la V1");
    let maximo: usize = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(usize::MAX);
    let mut consulta = base
        .prepare(
            "SELECT file_path, bpm, rms_mean, spectral_centroid_mean, zero_crossing_rate_mean
             FROM track_audio_features WHERE bpm IS NOT NULL AND analysis_status = 'ready'",
        )
        .expect("consulta");
    let filas: Vec<(String, f64, f64, f64, f64)> = consulta
        .query_map([], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?)))
        .expect("filas")
        .filter_map(Result::ok)
        .take(maximo)
        .collect();
    let mut plan = FftPlanner::<f64>::new();
    let fft = plan.plan_fft_forward(N_FFT);
    let mel = banco_mel();
    let (mut iguales, mut multiplo, mut total) = (0, 0, 0);
    let (mut rms, mut cent, mut zcr) = (vec![], vec![], vec![]);
    let inicio = std::time::Instant::now();
    for (ruta, bpm_v1, rms_v1, cent_v1, zcr_v1) in &filas {
        let Some(y) = cargar(Path::new(ruta), 90.0) else { continue };
        let r = rasgos(&y, &fft, &mel);
        total += 1;
        let rel = r.bpm / bpm_v1;
        if (rel - 1.0).abs() <= 0.02 {
            iguales += 1;
        } else if (rel - 2.0).abs() <= 0.04 || (rel - 0.5).abs() <= 0.01 {
            multiplo += 1;
        } else if std::env::var("VER").is_ok() {
            eprintln!("{:.2}\t{:.2}\t{ruta}", bpm_v1, r.bpm);
        }
        rms.push((r.rms, *rms_v1));
        cent.push((r.centroide, *cent_v1));
        zcr.push((r.zcr, *zcr_v1));
        if total % 200 == 0 {
            eprintln!("{total} pistas…");
        }
    }
    let corr = |v: &Vec<(f64, f64)>| {
        let (a, b): (Vec<f64>, Vec<f64>) = v.iter().copied().unzip();
        pearson(&a, &b)
    };
    println!(
        "{total} pistas en {:.0} s | tempo dentro de ±2 %: {iguales} ({:.1} %); múltiplo 2× o ½×: {multiplo}; dentro del criterio: {:.1} %",
        inicio.elapsed().as_secs_f64(),
        100.0 * iguales as f64 / total as f64,
        100.0 * (iguales + multiplo) as f64 / total as f64
    );
    println!(
        "correlación con la V1: RMS {:.4}, centroide {:.4}, ZCR {:.4}",
        corr(&rms),
        corr(&cent),
        corr(&zcr)
    );
}
