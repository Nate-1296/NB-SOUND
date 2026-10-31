//! Los rasgos básicos de una pista (F4.1.12): `core/audio_features.py` de la V1
//! en modo `light`, sin librosa (ADR-002).
//!
//! Los primeros 90 s en mono a 22.050 Hz, y de ahí lo que guarda la tabla
//! `rasgos`: tempo y pulsos (el seguidor de `librosa.beat.beat_track` 0.11, que
//! usaba la V1), RMS, centroide, ancho de banda y caída espectral, cruces por
//! cero, ritmo de ataques, tonalidad y las aproximaciones por regla (energía,
//! valencia…) con las fórmulas de la V1. El tempo, el RMS, el centroide y los
//! cruces por cero son los del prototipo F0.4.4, comparados con la V1 en las
//! 2.397 pistas reales (informe `docs/audit/2026-10-29-prototipo-rasgos.md`).
//!
//! **La tonalidad es nueva a propósito.** La V1 tomaba el máximo del croma y
//! decidía el modo por si la nota llevaba sostenido; aquí se correlaciona el
//! croma medio con los perfiles de Krumhansl y Kessler de las 24 tonalidades.
//! El croma sale de la STFT y no de la CQT de la V1: con el perfil entero, la
//! resolución de la CQT en graves no cambia la decisión y costaría otro
//! análisis de la señal.

use std::f64::consts::PI;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use rubato::{FftFixedIn, Resampler};
use rusqlite::params;
use rustfft::num_complex::Complex;
use rustfft::{Fft, FftPlanner};

use crate::audio::decodificador::Decodificador;
use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};
use crate::reproductor::persistencia;

/// La versión del analizador, que va en cada fila: si cambia, la fila caduca
/// (V4). Las filas que trajo la V1 llevan la suya (`audio_basic_v3`).
pub const VERSION: &str = "v2-basico-1";

const SR: f64 = 22_050.0;
const N_FFT: usize = 2048;
const HOP: usize = 512;
const N_MELS: usize = 128;
/// `AUDIO_FEATURES_SEGMENT_SECONDS` de la V1.
const SEGUNDOS: f64 = 90.0;
/// `tightness` de `beat_track`.
const RIGIDEZ: f64 = 100.0;
const NOTAS: [&str; 12] = [
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
];
/// Perfiles de Krumhansl y Kessler (1982), de do a si.
const MAYOR: [f64; 12] = [
    6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88,
];
const MENOR: [f64; 12] = [
    6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17,
];

/// Lo que se guarda en `rasgos`, con los nombres de sus columnas.
#[derive(Debug, Clone, PartialEq)]
pub struct Rasgos {
    pub bpm: Option<f64>,
    pub pulsos: u32,
    pub ataques_por_seg: f64,
    pub tonalidad: &'static str,
    pub modo: &'static str,
    pub rms_media: f64,
    pub rms_desviacion: f64,
    pub centroide: f64,
    pub ancho_banda: f64,
    pub caida_espectral: f64,
    pub cruces_por_cero: f64,
    pub brillo: f64,
    pub bailabilidad: f64,
    pub energia: f64,
    pub valencia: f64,
    pub activacion: f64,
    pub agresividad: f64,
    pub calma: f64,
    pub melancolia: f64,
    pub para_concentrarse: f64,
    pub para_entrenar: f64,
    pub para_fiesta: f64,
    pub para_la_noche: f64,
}

// --- Señal ---------------------------------------------------------------------------

/// Mono a 22.050 Hz de los primeros 90 s.
fn cargar(ruta: &Path) -> NsResult<Vec<f32>> {
    let mut d = Decodificador::abrir(ruta, 0.0)?;
    let tasa = d.tasa;
    let limite = (SEGUNDOS * f64::from(tasa)) as usize;
    let mut mono = Vec::with_capacity(limite);
    let mut bloque = Vec::with_capacity(16_384);
    while mono.len() < limite {
        bloque.clear();
        if d.leer(&mut bloque, 16_384)? == 0 {
            break;
        }
        mono.extend(bloque.iter().map(|f| (f.left + f.right) * 0.5));
    }
    mono.truncate(limite);
    if f64::from(tasa) == SR {
        return Ok(mono);
    }
    let trozo = 4096;
    let mut rs = FftFixedIn::<f32>::new(tasa as usize, SR as usize, trozo, 2, 1)
        .map_err(|_| NsError::Internal)?;
    let esperado = (mono.len() as f64 * SR / f64::from(tasa)).round() as usize;
    let mut salida = Vec::with_capacity(esperado + trozo);
    let mut i = 0;
    while i + trozo <= mono.len() {
        let out = rs
            .process(&[&mono[i..i + trozo]], None)
            .map_err(|_| NsError::Internal)?;
        salida.extend_from_slice(&out[0]);
        i += trozo;
    }
    if i < mono.len() {
        let out = rs
            .process_partial(Some(&[&mono[i..]]), None)
            .map_err(|_| NsError::Internal)?;
        salida.extend_from_slice(&out[0]);
    }
    // El retardo del remuestreador se descarta para alinear con el original.
    let retardo = rs.output_delay();
    Ok(salida.into_iter().skip(retardo).take(esperado).collect())
}

fn hann_periodica(n: usize) -> Vec<f64> {
    (0..n)
        .map(|i| 0.5 - 0.5 * (2.0 * PI * i as f64 / n as f64).cos())
        .collect()
}

/// Espectrograma de potencia centrado con relleno de ceros, como `librosa.stft`.
fn espectrograma(y: &[f32], fft: &Arc<dyn Fft<f64>>) -> Vec<Vec<f64>> {
    let ventana = hann_periodica(N_FFT);
    let mut rel = vec![0f64; N_FFT / 2];
    rel.extend(y.iter().map(|&v| f64::from(v)));
    rel.extend(std::iter::repeat_n(0.0, N_FFT / 2));
    let marcos = 1 + y.len() / HOP;
    let mut buf = vec![Complex::new(0.0, 0.0); N_FFT];
    (0..marcos)
        .map(|t| {
            let ini = t * HOP;
            for (k, b) in buf.iter_mut().enumerate() {
                *b = Complex::new(rel.get(ini + k).copied().unwrap_or(0.0) * ventana[k], 0.0);
            }
            fft.process(&mut buf);
            buf[..=N_FFT / 2].iter().map(|c| c.norm_sqr()).collect()
        })
        .collect()
}

const F_SP: f64 = 200.0 / 3.0;
const MIN_LOG_HZ: f64 = 1000.0;

fn paso_log() -> f64 {
    6.4f64.ln() / 27.0
}

fn hz_a_mel(f: f64) -> f64 {
    if f >= MIN_LOG_HZ {
        MIN_LOG_HZ / F_SP + (f / MIN_LOG_HZ).ln() / paso_log()
    } else {
        f / F_SP
    }
}

fn mel_a_hz(m: f64) -> f64 {
    let min_log_mel = MIN_LOG_HZ / F_SP;
    if m >= min_log_mel {
        MIN_LOG_HZ * (paso_log() * (m - min_log_mel)).exp()
    } else {
        F_SP * m
    }
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

/// Las dos envolventes de ataques de `onset_strength`: con la mediana entre
/// bandas, la que usa `beat_track`, y con la media, la de `onset_rate` de la V1.
fn envolventes(potencia: &[Vec<f64>], mel: &[Vec<f64>]) -> (Vec<f64>, Vec<f64>) {
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
    let (mut mediana, mut media) = (vec![0.0; n], vec![0.0; n]);
    let mut d = Vec::with_capacity(N_MELS);
    for t in 1..n {
        d.clear();
        d.extend(db[t].iter().zip(&db[t - 1]).map(|(a, b)| (a - b).max(0.0)));
        // Desplazada `lag + n_fft / (2 · hop)` = 3 marcos, como `onset_strength`.
        if t + 2 < n {
            media[t + 2] = d.iter().sum::<f64>() / N_MELS as f64;
            d.sort_by(f64::total_cmp);
            mediana[t + 2] = (d[N_MELS / 2 - 1] + d[N_MELS / 2]) / 2.0;
        }
    }
    (mediana, media)
}

// --- Tempo y pulsos ------------------------------------------------------------------

/// `librosa.feature.tempo` (start_bpm 120, std_bpm 1, ac_size 8 s, max 320).
fn tempo(env: &[f64]) -> f64 {
    let win = (8.0 * SR / HOP as f64).floor() as usize;
    let mitad = win / 2;
    let n = env.len();
    let (izq, der) = (
        env.first().copied().unwrap_or(0.0),
        env.last().copied().unwrap_or(0.0),
    );
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
    let mut ac = vec![0.0; win];
    for t in 0..n {
        buf.iter_mut().for_each(|c| *c = Complex::new(0.0, 0.0));
        for k in 0..win {
            buf[k] = Complex::new(rel.get(t + k).copied().unwrap_or(0.0) * ventana[k], 0.0);
        }
        ida.process(&mut buf);
        buf.iter_mut()
            .for_each(|c| *c = Complex::new(c.norm_sqr(), 0.0));
        vuelta.process(&mut buf);
        for (a, c) in ac.iter_mut().zip(&buf[..win]) {
            *a = c.re / npad as f64;
        }
        let m = ac.iter().fold(0f64, |m, v| m.max(v.abs()));
        if m > f64::MIN_POSITIVE {
            for (a, v) in acum.iter_mut().zip(&ac) {
                *a += v / m;
            }
        }
    }
    let mut mejor = (f64::MIN, 0.0);
    for (lag, valor) in acum.iter().enumerate().skip(1) {
        let bpm = 60.0 * SR / (HOP as f64 * lag as f64);
        if bpm > 320.0 {
            continue;
        }
        let prior = -0.5 * (bpm.log2() - 120f64.log2()).powi(2);
        let v = (1e6 * valor / n as f64).ln_1p() + prior;
        if v > mejor.0 {
            mejor = (v, bpm);
        }
    }
    mejor.1
}

/// `np.round`: a la par en los empates, no hacia arriba.
fn redondear_par(x: f64) -> f64 {
    let r = x.round();
    if (x - x.trunc()).abs() == 0.5 && r % 2.0 != 0.0 {
        r - x.signum()
    } else {
        r
    }
}

/// `util.localmax`: mayor que el anterior y no menor que el siguiente, con los
/// bordes repetidos.
fn maximos_locales(x: &[f64]) -> Vec<bool> {
    let n = x.len();
    (0..n)
        .map(|i| {
            let antes = x[i.saturating_sub(1)];
            let despues = x[(i + 1).min(n - 1)];
            x[i] > antes && x[i] >= despues
        })
        .collect()
}

fn mediana(mut v: Vec<f64>) -> f64 {
    if v.is_empty() {
        return 0.0;
    }
    v.sort_by(f64::total_cmp);
    let m = v.len() / 2;
    if v.len().is_multiple_of(2) {
        (v[m - 1] + v[m]) / 2.0
    } else {
        v[m]
    }
}

/// `__beat_tracker` de librosa 0.11 con tempo fijo y `trim`. Devuelve los marcos
/// de los pulsos.
///
/// El recorte de 0.11 compara la envolvente cruda con un umbral sacado de la
/// suavizada, cuya ventana suma 2: con golpes casi iguales, recorta de más por los
/// extremos. Se replica tal cual porque es lo que contaba la V1.
fn pulsos(env: &[f64], bpm: f64) -> Vec<usize> {
    let n = env.len();
    if n < 2 || bpm <= 0.0 || !env.iter().any(|v| *v != 0.0) {
        return Vec::new();
    }
    let fpb = redondear_par(SR / HOP as f64 * 60.0 / bpm);
    // `__normalize_onsets`: entre la desviación típica muestral.
    let media = env.iter().sum::<f64>() / n as f64;
    let desv = (env.iter().map(|v| (v - media).powi(2)).sum::<f64>() / (n as f64 - 1.0)).sqrt();
    let norm: Vec<f64> = env.iter().map(|v| v / (desv + f64::MIN_POSITIVE)).collect();
    // `__beat_local_score`: la convolución "same" con una gaussiana de un periodo.
    let periodo = fpb as i64;
    let ventana: Vec<f64> = (-periodo..=periodo)
        .map(|k| (-0.5 * (k as f64 * 32.0 / fpb).powi(2)).exp())
        .collect();
    let k_len = ventana.len();
    let local: Vec<f64> = (0..n)
        .map(|i| {
            let desde = (i + k_len / 2 + 1).saturating_sub(n);
            let hasta = (i + k_len / 2).min(k_len);
            (desde..hasta)
                .map(|k| ventana[k] * norm[i + k_len / 2 - k])
                .sum()
        })
        .collect();
    // `__beat_track_dp`.
    let umbral = 0.01 * local.iter().fold(f64::MIN, |m, &v| m.max(v));
    let mut atras = vec![-1i64; n];
    let mut acumulado = vec![0.0; n];
    let mut primero = true;
    let medio = redondear_par(fpb / 2.0) as i64;
    let (log_fpb, max_atras) = (fpb.ln(), 2 * periodo + 1);
    for i in 0..n {
        let (mut mejor, mut donde) = (f64::NEG_INFINITY, -1i64);
        let mut loc = i as i64 - medio;
        while loc > i as i64 - max_atras {
            if loc < 0 {
                break;
            }
            let s = acumulado[loc as usize]
                - RIGIDEZ * (((i as i64 - loc) as f64).ln() - log_fpb).powi(2);
            if s > mejor {
                (mejor, donde) = (s, loc);
            }
            loc -= 1;
        }
        acumulado[i] = if donde >= 0 {
            local[i] + mejor
        } else {
            local[i]
        };
        if primero && local[i] < umbral {
            atras[i] = -1;
        } else {
            atras[i] = donde;
            primero = false;
        }
    }
    // `__last_beat`: el último máximo local que llega a la mitad de su mediana.
    let maximos = maximos_locales(&acumulado);
    let umbral_final = 0.5
        * mediana(
            acumulado
                .iter()
                .zip(&maximos)
                .filter(|(_, m)| **m)
                .map(|(v, _)| *v)
                .collect(),
        );
    let mut cola = n as i64 - 1;
    for j in (0..n).rev() {
        if maximos[j] && acumulado[j] >= umbral_final {
            cola = j as i64;
            break;
        }
    }
    let mut es_pulso = vec![false; n];
    let mut j = cola;
    while j >= 0 {
        es_pulso[j as usize] = true;
        j = atras[j as usize];
    }
    // `__trim_beats`: fuera los extremos con la envolvente por debajo de la mitad
    // del RMS de la suavizada, con su corte de la convolución completa.
    let en_pulsos: Vec<f64> = local
        .iter()
        .zip(&es_pulso)
        .filter(|(_, p)| **p)
        .map(|(v, _)| *v)
        .collect();
    let w = [0.0, 0.5, 1.0, 0.5, 0.0];
    let completa: Vec<f64> = (0..en_pulsos.len() + w.len() - 1)
        .map(|i| {
            (0..w.len())
                .filter(|&k| i >= k && i - k < en_pulsos.len())
                .map(|k| w[k] * en_pulsos[i - k])
                .sum()
        })
        .collect();
    let suave = &completa[(w.len() / 2).min(completa.len())..(n + w.len() / 2).min(completa.len())];
    let umbral_recorte = if suave.is_empty() {
        0.0
    } else {
        0.5 * (suave.iter().map(|v| v * v).sum::<f64>() / suave.len() as f64).sqrt()
    };
    let mut i = 0;
    while i < n && local[i] <= umbral_recorte {
        es_pulso[i] = false;
        i += 1;
    }
    let mut i = n;
    while i > 0 && local[i - 1] <= umbral_recorte {
        es_pulso[i - 1] = false;
        i -= 1;
    }
    (0..n).filter(|i| es_pulso[*i]).collect()
}

// --- Tonalidad -----------------------------------------------------------------------

fn pearson(a: &[f64], b: &[f64]) -> f64 {
    let n = a.len() as f64;
    let (ma, mb) = (a.iter().sum::<f64>() / n, b.iter().sum::<f64>() / n);
    let cov: f64 = a.iter().zip(b).map(|(x, y)| (x - ma) * (y - mb)).sum();
    let va: f64 = a.iter().map(|x| (x - ma).powi(2)).sum();
    let vb: f64 = b.iter().map(|y| (y - mb).powi(2)).sum();
    if va <= 0.0 || vb <= 0.0 {
        0.0
    } else {
        cov / (va * vb).sqrt()
    }
}

/// El croma medio (cada marco normalizado por su máximo, como `chroma_stft`) y la
/// tonalidad que mejor lo explica.
fn tonalidad(potencia: &[Vec<f64>]) -> (&'static str, &'static str) {
    // De la0 (27,5 Hz) a 5 kHz: por debajo no hay resolución y por encima casi
    // todo son armónicos que difuminan la clase de nota.
    let clases: Vec<Option<usize>> = (0..=N_FFT / 2)
        .map(|k| {
            let f = k as f64 * SR / N_FFT as f64;
            (27.5..=5000.0).contains(&f).then(|| {
                let midi = (12.0 * (f / 440.0).log2() + 69.0).round() as i64;
                midi.rem_euclid(12) as usize
            })
        })
        .collect();
    let mut croma = [0.0f64; 12];
    for p in potencia {
        let mut marco = [0.0f64; 12];
        for (v, c) in p.iter().zip(&clases) {
            if let Some(c) = c {
                marco[*c] += v;
            }
        }
        let m = marco.iter().fold(0.0f64, |a, &b| a.max(b));
        if m > 0.0 {
            for (a, b) in croma.iter_mut().zip(&marco) {
                *a += b / m;
            }
        }
    }
    let mut mejor = (f64::MIN, 0usize, "major");
    for tonica in 0..12 {
        for (perfil, modo) in [(&MAYOR, "major"), (&MENOR, "minor")] {
            let rotado: Vec<f64> = (0..12).map(|i| perfil[(i + 12 - tonica) % 12]).collect();
            let r = pearson(&croma, &rotado);
            if r > mejor.0 {
                mejor = (r, tonica, modo);
            }
        }
    }
    (NOTAS[mejor.1], mejor.2)
}

// --- Todo junto ----------------------------------------------------------------------

fn recortar(x: f64) -> f64 {
    x.clamp(0.0, 1.0)
}

/// Analiza una señal mono a 22.050 Hz.
///
/// # Errors
///
/// [`NsError::AudioCorrupted`] si es silencio o demasiado corta.
pub fn de_senal(y: &[f32]) -> NsResult<Rasgos> {
    if y.len() < N_FFT || !y.iter().any(|v| v.abs() > 1e-6) {
        return Err(NsError::AudioCorrupted);
    }
    let mut plan = FftPlanner::<f64>::new();
    let fft = plan.plan_fft_forward(N_FFT);
    let pot = espectrograma(y, &fft);
    let mel = banco_mel();
    let (env_mediana, env_media) = envolventes(&pot, &mel);
    let bpm = if env_mediana.iter().any(|v| *v != 0.0) {
        Some(tempo(&env_mediana)).filter(|b| *b > 0.0)
    } else {
        None
    };
    let pulsos = bpm.map_or(0, |b| {
        u32::try_from(pulsos(&env_mediana, b).len()).unwrap_or(u32::MAX)
    });
    let ataques = env_media.iter().sum::<f64>() / env_media.len() as f64;

    // RMS con relleno de ceros y cruces por cero con el borde repetido, por
    // marcos de 2048 cada 512, como `librosa.feature.rms` y `zero_crossing_rate`.
    let marcos = 1 + y.len() / HOP;
    let mut ceros = vec![0f32; N_FFT / 2];
    ceros.extend_from_slice(y);
    ceros.extend(std::iter::repeat_n(0.0, N_FFT / 2));
    let mut borde = vec![y[0]; N_FFT / 2];
    borde.extend_from_slice(y);
    borde.extend(std::iter::repeat_n(y[y.len() - 1], N_FFT / 2));
    let signo = |v: f32| v.abs() > 1e-10 && v < 0.0;
    let mut rms = Vec::with_capacity(marcos);
    let mut zcr = 0.0;
    for t in 0..marcos {
        let m = &ceros[t * HOP..t * HOP + N_FFT];
        rms.push((m.iter().map(|v| f64::from(*v).powi(2)).sum::<f64>() / N_FFT as f64).sqrt());
        let z = &borde[t * HOP..t * HOP + N_FFT];
        zcr += z.windows(2).filter(|w| signo(w[0]) != signo(w[1])).count() as f64 / N_FFT as f64;
    }
    let rms_media = rms.iter().sum::<f64>() / marcos as f64;
    let rms_desviacion =
        (rms.iter().map(|r| (r - rms_media).powi(2)).sum::<f64>() / marcos as f64).sqrt();
    let cruces = zcr / marcos as f64;

    // Centroide, ancho de banda y caída espectral, sobre la magnitud.
    let freqs: Vec<f64> = (0..=N_FFT / 2)
        .map(|k| k as f64 * SR / N_FFT as f64)
        .collect();
    let (mut cent, mut ancho, mut caida) = (0.0, 0.0, 0.0);
    for p in &pot {
        let mag: Vec<f64> = p.iter().map(|v| v.sqrt()).collect();
        let total: f64 = mag.iter().sum();
        if total > 0.0 {
            let c: f64 = mag.iter().zip(&freqs).map(|(m, f)| m * f).sum::<f64>() / total;
            cent += c;
            ancho += (mag
                .iter()
                .zip(&freqs)
                .map(|(m, f)| m / total * (f - c).powi(2))
                .sum::<f64>())
            .sqrt();
        }
        // La primera frecuencia en la que la energía acumulada llega al 85 %.
        let umbral = 0.85 * total;
        let mut suma = 0.0;
        for (m, f) in mag.iter().zip(&freqs) {
            suma += m;
            if suma >= umbral {
                caida += f;
                break;
            }
        }
    }
    let nm = pot.len() as f64;
    let (centroide, ancho_banda, caida_espectral) = (cent / nm, ancho / nm, caida / nm);
    let (tonalidad, modo) = tonalidad(&pot);

    // Las aproximaciones de la V1, con sus mismas fórmulas.
    let t = bpm.unwrap_or(0.0);
    let brillo = recortar(centroide / 4000.0);
    let energia = recortar(rms_media * 3.0);
    let activacion = recortar(0.6 * energia + 0.4 * recortar(t / 180.0));
    let calma = recortar(1.0 - activacion);
    let valencia = recortar(0.5 * brillo + 0.5 * (1.0 - calma));
    let melancolia = recortar((1.0 - valencia) * 0.7 + calma * 0.3);
    let bailabilidad = recortar(0.5 * recortar(t / 140.0) + 0.5 * recortar(ataques / 5.0));
    let para_fiesta = recortar(0.4 * bailabilidad + 0.4 * energia + 0.2 * valencia);
    let para_entrenar =
        recortar(0.5 * energia + 0.3 * recortar(t / 160.0) + 0.2 * recortar(ataques / 6.0));
    let para_concentrarse =
        recortar(0.5 * calma + 0.3 * (1.0 - rms_desviacion) + 0.2 * (1.0 - cruces * 5.0));
    let para_la_noche = recortar(0.6 * (1.0 - brillo) + 0.4 * melancolia);
    let agresividad = recortar(0.5 * energia + 0.5 * cruces * 5.0);
    Ok(Rasgos {
        bpm,
        pulsos,
        ataques_por_seg: ataques,
        tonalidad,
        modo,
        rms_media,
        rms_desviacion,
        centroide,
        ancho_banda,
        caida_espectral,
        cruces_por_cero: cruces,
        brillo,
        bailabilidad,
        energia,
        valencia,
        activacion,
        agresividad,
        calma,
        melancolia,
        para_concentrarse,
        para_entrenar,
        para_fiesta,
        para_la_noche,
    })
}

/// Analiza un archivo.
///
/// # Errors
///
/// Los de [`Decodificador::abrir`] y [`de_senal`].
pub fn analizar(ruta: &Path) -> NsResult<Rasgos> {
    if !ruta.is_file() {
        return Err(NsError::FileNotFound);
    }
    de_senal(&cargar(ruta)?)
}

// --- En segundo plano ----------------------------------------------------------------

/// Las preferencias de la V1 que lo gobiernan: el análisis encendido y "analizar
/// al importar", las dos de fábrica en sí.
fn activado(db: &BaseDeDatos) -> bool {
    let Ok(conn) = db.conexion() else {
        return false;
    };
    let si = |clave: &str| -> bool {
        conn.query_row(
            "SELECT valor FROM preferencias WHERE clave = ?1",
            [clave],
            |f| f.get::<_, String>(0),
        )
        .ok()
        .and_then(|v| serde_json::from_str::<bool>(&v).ok())
        .unwrap_or(true)
    };
    si("analisis_activado") && si("analizar_al_importar")
}

struct Pendiente {
    id: i64,
    ruta: PathBuf,
    sha256: Option<String>,
}

/// Las pistas sin rasgos: lo que llega en las importaciones. Las filas de la V1
/// se respetan, aunque su versión sea otra: las midió con paridad comprobada.
fn pendientes(db: &BaseDeDatos, saltar: &[i64]) -> NsResult<Vec<Pendiente>> {
    let conn = db.conexion()?;
    let musica = persistencia::carpeta_musica(&conn)?;
    let mut s = conn
        .prepare(
            "SELECT p.id, p.ruta, p.sha256 FROM pistas p
             LEFT JOIN rasgos r ON r.pista_id = p.id
             WHERE p.estado = 'biblioteca' AND r.pista_id IS NULL
             ORDER BY p.id DESC LIMIT ?1",
        )
        .map_err(|_| NsError::StorageFailure)?;
    let filas = s
        .query_map(params![32 + saltar.len() as i64], |f| {
            Ok((
                f.get::<_, i64>(0)?,
                f.get::<_, String>(1)?,
                f.get::<_, Option<String>>(2)?,
            ))
        })
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(filas
        .into_iter()
        .filter(|(id, _, _)| !saltar.contains(id))
        .map(|(id, ruta, sha256)| {
            let ruta = PathBuf::from(ruta);
            let ruta = match &musica {
                Some(m) if ruta.is_relative() => m.join(ruta),
                _ => ruta,
            };
            Pendiente { id, ruta, sha256 }
        })
        .collect())
}

fn guardar(db: &BaseDeDatos, p: &Pendiente, r: Option<&Rasgos>) -> NsResult<()> {
    let finito = |v: f64| v.is_finite().then_some(v);
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    // Sin rasgos posibles (silencio, ilegible) se apunta la fila vacía para no
    // reintentarlo en cada arranque.
    tx.execute(
        "INSERT INTO rasgos (pista_id, version, sha256, bpm, pulsos, ataques_por_seg, tonalidad, modo,
             rms_media, rms_desviacion, sonoridad_aprox, centroide, ancho_banda, caida_espectral,
             cruces_por_cero, brillo, oscuridad, bailabilidad, energia, valencia, activacion,
             agresividad, calma, melancolia, para_concentrarse, para_entrenar, para_fiesta,
             para_la_noche)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18,
                 ?19, ?20, ?21, ?22, ?23, ?24, ?25, ?26, ?27, ?28)
         ON CONFLICT (pista_id) DO NOTHING",
        rusqlite::params_from_iter([
            rusqlite::types::Value::from(p.id),
            VERSION.to_owned().into(),
            p.sha256.clone().into(),
            r.and_then(|r| r.bpm).and_then(finito).into(),
            r.map(|r| i64::from(r.pulsos)).into(),
            r.and_then(|r| finito(r.ataques_por_seg)).into(),
            r.map(|r| r.tonalidad.to_owned()).into(),
            r.map(|r| r.modo.to_owned()).into(),
            r.and_then(|r| finito(r.rms_media)).into(),
            r.and_then(|r| finito(r.rms_desviacion)).into(),
            // `loudness_proxy` de la V1 era la media del RMS.
            r.and_then(|r| finito(r.rms_media)).into(),
            r.and_then(|r| finito(r.centroide)).into(),
            r.and_then(|r| finito(r.ancho_banda)).into(),
            r.and_then(|r| finito(r.caida_espectral)).into(),
            r.and_then(|r| finito(r.cruces_por_cero)).into(),
            r.and_then(|r| finito(r.brillo)).into(),
            r.and_then(|r| finito(1.0 - r.brillo)).into(),
            r.and_then(|r| finito(r.bailabilidad)).into(),
            r.and_then(|r| finito(r.energia)).into(),
            r.and_then(|r| finito(r.valencia)).into(),
            r.and_then(|r| finito(r.activacion)).into(),
            r.and_then(|r| finito(r.agresividad)).into(),
            r.and_then(|r| finito(r.calma)).into(),
            r.and_then(|r| finito(r.melancolia)).into(),
            r.and_then(|r| finito(r.para_concentrarse)).into(),
            r.and_then(|r| finito(r.para_entrenar)).into(),
            r.and_then(|r| finito(r.para_fiesta)).into(),
            r.and_then(|r| finito(r.para_la_noche)).into(),
        ]),
    )
    .map_err(|error| {
        tracing::error!(error = %error, "no se pudieron guardar los rasgos");
        NsError::StorageFailure
    })?;
    if let Some(r) = r {
        guardar_ambiente(
            &tx,
            p.id,
            "basic_rules",
            VERSION,
            &[
                ("energetica", r.energia),
                ("tranquila", r.calma),
                ("bailable", r.bailabilidad),
                ("triste", r.melancolia),
                ("nocturna", r.para_la_noche),
                ("entrenamiento", r.para_entrenar),
                ("concentracion", r.para_concentrarse),
                ("fiesta", r.para_fiesta),
            ],
        )?;
    }
    tx.commit().map_err(|_| NsError::StorageFailure)
}

/// `derive_vibe_tags` y `derive_deep_vibe_tags` de la V1: cada aproximación que
/// llega a 0,35 da su etiqueta de ambiente, con la puntuación como confianza.
/// Sustituye las de esa fuente: un nuevo análisis no deja etiquetas viejas. Las
/// usan las listas por ánimo y el DJ, que penaliza la pista cuyo ambiente nombra
/// algo que el pedido niega.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub(crate) fn guardar_ambiente(
    tx: &rusqlite::Transaction<'_>,
    pista: i64,
    fuente: &str,
    version: &str,
    valores: &[(&str, f64)],
) -> NsResult<()> {
    let fallo = |error: rusqlite::Error| {
        tracing::error!(error = %error, "no se pudieron guardar las etiquetas de ambiente");
        NsError::StorageFailure
    };
    tx.execute(
        "DELETE FROM etiquetas_ambiente WHERE pista_id = ?1 AND fuente = ?2",
        params![pista, fuente],
    )
    .map_err(fallo)?;
    for (etiqueta, valor) in valores {
        if !valor.is_finite() || *valor < 0.35 {
            continue;
        }
        let v = crate::catalogo::texto::redondear(valor.min(1.0), 4);
        tx.execute(
            "INSERT INTO etiquetas_ambiente (pista_id, etiqueta, fuente, puntuacion, confianza, version)
             VALUES (?1, ?2, ?3, ?4, ?4, ?5)",
            params![pista, etiqueta, fuente, v, version],
        )
        .map_err(fallo)?;
    }
    Ok(())
}

/// Analiza lo pendiente, lo más reciente primero, con una pausa entre pistas.
/// Devuelve cuántas apuntó. Un archivo ausente solo se salta en esta pasada.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn analizar_pendientes(db: &BaseDeDatos, pausa: Duration) -> NsResult<usize> {
    if !activado(db) {
        return Ok(0);
    }
    let mut saltar = Vec::new();
    let mut apuntadas = 0;
    loop {
        let lote = pendientes(db, &saltar)?;
        if lote.is_empty() {
            return Ok(apuntadas);
        }
        for p in lote {
            match analizar(&p.ruta) {
                Ok(r) => guardar(db, &p, Some(&r))?,
                Err(NsError::AudioCorrupted | NsError::FormatUnsupported) => guardar(db, &p, None)?,
                Err(_) => {
                    saltar.push(p.id);
                    continue;
                }
            }
            apuntadas += 1;
            std::thread::sleep(pausa);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Un tempo de la rejilla de librosa (`60 · sr / (hop · lag)`): el estimador
    /// solo puede dar esos valores, igual que en la V1. 120 BPM cae entre 117,45
    /// y 123,05.
    fn en_la_rejilla(lag: usize) -> f64 {
        60.0 * SR / (HOP * lag) as f64
    }

    /// Un golpe de ruido que decae, cada `periodo` segundos, como un bombo.
    fn golpes(bpm: f64, segundos: f64) -> Vec<f32> {
        let n = (segundos * SR) as usize;
        let periodo = (60.0 / bpm * SR) as usize;
        let mut semilla = 1u32;
        (0..n)
            .map(|i| {
                semilla = semilla.wrapping_mul(1_103_515_245).wrapping_add(12_345);
                let ruido = (semilla >> 16) as f32 / 32_768.0 - 1.0;
                let fase = (i % periodo) as f32 / SR as f32;
                ruido * (-fase * 40.0).exp() * 0.8
            })
            .collect()
    }

    fn tono(frecuencias: &[f64], segundos: f64) -> Vec<f32> {
        (0..(segundos * SR) as usize)
            .map(|i| {
                let t = i as f64 / SR;
                (frecuencias
                    .iter()
                    .map(|f| (2.0 * PI * f * t).sin())
                    .sum::<f64>()
                    * 0.3
                    / frecuencias.len() as f64) as f32
            })
            .collect()
    }

    #[test]
    fn un_pulso_regular_da_su_tempo_y_sus_pulsos() {
        let objetivo = en_la_rejilla(22);
        let senal = golpes(objetivo, 30.0);
        let r = de_senal(&senal).unwrap();
        let bpm = r.bpm.unwrap();
        assert!((bpm / objetivo - 1.0).abs() < 1e-9, "{bpm}");
        assert!(r.ataques_por_seg > 0.0);
        // Los pulsos caen cada 22 marcos sin saltarse ninguno; el recorte de 0.11
        // solo quita de los extremos.
        let mut plan = FftPlanner::<f64>::new();
        let pot = espectrograma(&senal, &plan.plan_fft_forward(N_FFT));
        let (env, _) = envolventes(&pot, &banco_mel());
        let marcas = pulsos(&env, bpm);
        assert_eq!(r.pulsos as usize, marcas.len());
        assert!(marcas.len() >= 30, "{marcas:?}");
        assert!(marcas.windows(2).all(|w| w[1] - w[0] == 22), "{marcas:?}");
    }

    #[test]
    fn un_tono_puro_tiene_su_centroide_y_sus_cruces() {
        let r = de_senal(&tono(&[1000.0], 10.0)).unwrap();
        assert!((r.centroide - 1000.0).abs() < 60.0, "{}", r.centroide);
        assert!(
            (r.caida_espectral - 1000.0).abs() < 60.0,
            "{}",
            r.caida_espectral
        );
        assert!(r.ancho_banda < 300.0, "{}", r.ancho_banda);
        // Dos cruces por ciclo: 2000 por segundo entre 22.050 muestras.
        assert!(
            (r.cruces_por_cero - 2000.0 / SR).abs() < 0.005,
            "{}",
            r.cruces_por_cero
        );
        assert!(
            (r.rms_media - 0.3 / 2f64.sqrt()).abs() < 0.02,
            "{}",
            r.rms_media
        );
    }

    #[test]
    fn un_acorde_mayor_y_uno_menor_dan_su_tonalidad() {
        // La mayor: la, do#, mi. La menor: la, do, mi.
        let mayor = de_senal(&tono(&[220.0, 277.18, 329.63, 440.0], 8.0)).unwrap();
        assert_eq!((mayor.tonalidad, mayor.modo), ("A", "major"));
        let menor = de_senal(&tono(&[220.0, 261.63, 329.63, 440.0], 8.0)).unwrap();
        assert_eq!((menor.tonalidad, menor.modo), ("A", "minor"));
    }

    #[test]
    fn las_aproximaciones_siguen_las_formulas_de_la_v1_y_quedan_entre_cero_y_uno() {
        let r = de_senal(&golpes(128.0, 20.0)).unwrap();
        for v in [
            r.brillo,
            r.bailabilidad,
            r.energia,
            r.valencia,
            r.activacion,
            r.agresividad,
            r.calma,
            r.melancolia,
            r.para_concentrarse,
            r.para_entrenar,
            r.para_fiesta,
            r.para_la_noche,
        ] {
            assert!((0.0..=1.0).contains(&v), "{v}");
        }
        assert!((r.calma - (1.0 - r.activacion)).abs() < 1e-12);
        assert!((r.energia - (r.rms_media * 3.0).clamp(0.0, 1.0)).abs() < 1e-12);
    }

    #[test]
    fn el_silencio_no_tiene_rasgos() {
        assert_eq!(
            de_senal(&vec![0.0; 22_050 * 3]),
            Err(NsError::AudioCorrupted)
        );
        assert_eq!(de_senal(&[0.1; 100]), Err(NsError::AudioCorrupted));
    }

    #[test]
    fn el_redondeo_es_el_de_numpy() {
        assert_eq!(redondear_par(2.5), 2.0);
        assert_eq!(redondear_par(3.5), 4.0);
        assert_eq!(redondear_par(21.5), 22.0);
        assert_eq!(redondear_par(21.4), 21.0);
    }

    #[test]
    fn lo_importado_se_analiza_una_vez_y_lo_de_la_v1_se_respeta() {
        use crate::audio::pruebas::wav;
        let d = std::env::temp_dir().join(format!("ns-rasgos-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        let ruta = d.join("golpes.wav");
        let senal = golpes(en_la_rejilla(22), 12.0);
        let _ = wav(&ruta, 22_050, senal.len(), |i, _| senal[i]);
        let db = BaseDeDatos::en_memoria().unwrap();
        let conn = db.conexion().unwrap();
        conn.execute(
            "INSERT INTO pistas (id, titulo, ruta) VALUES (1, 'nueva', ?1), (2, 'de la v1', 'x.mp3')",
            [ruta.to_string_lossy()],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO rasgos (pista_id, version, bpm) VALUES (2, 'audio_basic_v3', 99)",
            [],
        )
        .unwrap();
        drop(conn);
        assert_eq!(analizar_pendientes(&db, Duration::ZERO).unwrap(), 1);
        assert_eq!(analizar_pendientes(&db, Duration::ZERO).unwrap(), 0);
        let (version, bpm): (String, f64) = db
            .conexion()
            .unwrap()
            .query_row(
                "SELECT version, bpm FROM rasgos WHERE pista_id = 1",
                [],
                |f| Ok((f.get(0)?, f.get(1)?)),
            )
            .unwrap();
        assert_eq!(version, VERSION);
        assert!((bpm / en_la_rejilla(22) - 1.0).abs() < 1e-9, "{bpm}");
        let v1: f64 = db
            .conexion()
            .unwrap()
            .query_row("SELECT bpm FROM rasgos WHERE pista_id = 2", [], |f| {
                f.get(0)
            })
            .unwrap();
        assert_eq!(v1, 99.0);
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn el_ambiente_lleva_lo_que_llega_a_035_y_sustituye_lo_anterior() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let mut conn = db.conexion().unwrap();
        conn.execute(
            "INSERT INTO pistas (id, titulo, ruta) VALUES (1, 'a', 'a.mp3')",
            [],
        )
        .unwrap();
        let tx = db::transaccion_de_escritura(&mut conn).unwrap();
        guardar_ambiente(
            &tx,
            1,
            "basic_rules",
            VERSION,
            &[("fiesta", 0.9), ("triste", 0.2)],
        )
        .unwrap();
        guardar_ambiente(
            &tx,
            1,
            "basic_rules",
            VERSION,
            &[
                ("bailable", 0.123_456_789 + 0.3),
                ("tranquila", 0.349_999),
                ("x", f64::NAN),
            ],
        )
        .unwrap();
        guardar_ambiente(&tx, 1, "deep_model", VERSION, &[("fiesta", 0.5)]).unwrap();
        tx.commit().unwrap();
        let filas: Vec<(String, String, f64)> = conn
            .prepare("SELECT etiqueta, fuente, puntuacion FROM etiquetas_ambiente ORDER BY fuente")
            .unwrap()
            .query_map([], |f| Ok((f.get(0)?, f.get(1)?, f.get(2)?)))
            .unwrap()
            .collect::<rusqlite::Result<_>>()
            .unwrap();
        assert_eq!(
            filas,
            vec![
                ("bailable".to_owned(), "basic_rules".to_owned(), 0.4235),
                ("fiesta".to_owned(), "deep_model".to_owned(), 0.5),
            ]
        );
    }

    #[test]
    fn con_el_analisis_apagado_no_se_analiza_nada() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO preferencias (clave, valor) VALUES ('analizar_al_importar', 'false');
                 INSERT INTO pistas (titulo, ruta) VALUES ('x', 'x.wav');",
            )
            .unwrap();
        assert_eq!(analizar_pendientes(&db, Duration::ZERO).unwrap(), 0);
    }
}
