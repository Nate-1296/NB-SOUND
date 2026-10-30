//! Prototipo F0.4.3: el preprocesado de Essentia y los modelos en ONNX, en Rust.
//!
//! Código desechable. Para cada clave que dejó `referencia.py`:
//!
//! 1. lee la señal a 16 kHz que vio Essentia (así el decodificador no cuenta);
//! 2. calcula las bandas de MusiCNN y de VGGish como `TensorflowInputMusiCNN` y
//!    `TensorflowInputVGGish`, con los marcos del `FrameCutter` de streaming, y las
//!    compara marco a marco con las de Essentia;
//! 3. corta los parches como `TensorflowPredict*` (187/93 y 96/93, descartando el
//!    último incompleto), ejecuta los modelos convertidos con ONNX Runtime 1.31.1
//!    y compara las medias con las que guardó la V1.
//!
//! Uso: cargo run --release -- <libonnxruntime.so> <modelos-onnx> <referencia> <clave>...

mod decodificar;

use std::f64::consts::PI;
use std::path::Path;

use ndarray::Array3;
use ort::session::Session;
use ort::value::Tensor;
use rustfft::num_complex::Complex;
use rustfft::FftPlanner;

const SR: f64 = 16_000.0;

fn leer_f32(ruta: &Path) -> Vec<f32> {
    std::fs::read(ruta)
        .expect("archivo de referencia")
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes([b[0], b[1], b[2], b[3]]))
        .collect()
}

/// Los marcos del `FrameCutter` de streaming con `startFromZero = false`.
fn marcos(senal: &[f32], tam: usize, salto: usize) -> Vec<Vec<f32>> {
    let mut salida = Vec::new();
    let n = senal.len() as i64;
    let mut inicio = -(tam as i64 / 2);
    loop {
        if inicio >= n {
            break;
        }
        let mut marco = vec![0f32; tam];
        let mut copiados = 0;
        for (k, v) in marco.iter_mut().enumerate() {
            let i = inicio + k as i64;
            if i >= 0 && i < n {
                *v = senal[i as usize];
                copiados += 1;
            }
        }
        let relleno_al_final = inicio + tam as i64 > n;
        salida.push(marco);
        let _ = copiados;
        if relleno_al_final && inicio + (tam as i64 / 2) >= n {
            break;
        }
        inicio += salto as i64;
    }
    salida
}

fn hann_simetrica(n: usize) -> Vec<f64> {
    (0..n).map(|i| 0.5 - 0.5 * (2.0 * PI * i as f64 / (n as f64 - 1.0)).cos()).collect()
}

fn hz_a_mel_slaney(hz: f64) -> f64 {
    let lin = 3.0 / 200.0;
    if hz < 1000.0 { hz * lin } else { 1000.0 * lin + (hz / 1000.0).ln() / ((6.4f64).ln() / 27.0) }
}
fn mel_slaney_a_hz(mel: f64) -> f64 {
    let lin = 3.0 / 200.0;
    let min = 1000.0 * lin;
    if mel < min { mel / lin } else { 1000.0 * ((mel - min) * ((6.4f64).ln() / 27.0)).exp() }
}
fn hz_a_mel10(hz: f64) -> f64 {
    2595.0 * (hz / 700.0 + 1.0).log10()
}
fn mel10_a_hz(mel: f64) -> f64 {
    700.0 * (10f64.powf(mel / 2595.0) - 1.0)
}

/// `MelBands` de Essentia: triángulos entre frecuencias equiespaciadas en mel.
struct Banco {
    filtros: Vec<(usize, Vec<f64>)>,
    potencia: bool,
}

fn banco(
    bins: usize,
    bandas: usize,
    baja: f64,
    alta: f64,
    a_mel: fn(f64) -> f64,
    de_mel: fn(f64) -> f64,
    pesar_en_mel: bool,
    unit_tri: bool,
    potencia: bool,
) -> Banco {
    let (mb, ma) = (a_mel(baja), a_mel(alta));
    let paso = (ma - mb) / (bandas + 1) as f64;
    let f: Vec<f64> = (0..bandas + 2).map(|i| de_mel(mb + paso * i as f64)).collect();
    let escala = (SR / 2.0) / (bins - 1) as f64;
    let peso = |x: f64| if pesar_en_mel { a_mel(x) } else { x };
    let filtros = (0..bandas)
        .map(|i| {
            let (s1, s2) = (peso(f[i + 1]) - peso(f[i]), peso(f[i + 2]) - peso(f[i + 1]));
            let ini = (f[i] / escala).ceil() as usize;
            let fin = ((f[i + 2] / escala).floor() as usize).min(bins - 1);
            let mut w: Vec<f64> = (ini..=fin)
                .map(|j| {
                    let bf = j as f64 * escala;
                    if bf < f[i + 1] { (peso(bf) - peso(f[i])) / s1 } else { (peso(f[i + 2]) - peso(bf)) / s2 }
                })
                .collect();
            if unit_tri {
                let area = (s1 + s2) / 2.0;
                w.iter_mut().for_each(|x| *x /= area);
            }
            (ini, w)
        })
        .collect();
    Banco { filtros, potencia }
}

fn espectro(marco: &[f32], ventana: &[f64], fft_tam: usize, plan: &mut FftPlanner<f64>) -> Vec<f64> {
    let fft = plan.plan_fft_forward(fft_tam);
    let mut buf: Vec<Complex<f64>> = (0..fft_tam)
        .map(|k| Complex::new(if k < marco.len() { marco[k] as f64 * ventana[k] } else { 0.0 }, 0.0))
        .collect();
    fft.process(&mut buf);
    buf[..=fft_tam / 2].iter().map(|c| c.norm()).collect()
}

fn aplicar(b: &Banco, esp: &[f64]) -> Vec<f64> {
    b.filtros
        .iter()
        .map(|(ini, w)| {
            w.iter()
                .enumerate()
                .map(|(k, p)| {
                    let s = esp[ini + k];
                    p * if b.potencia { s * s } else { s }
                })
                .sum()
        })
        .collect()
}

fn bandas_musicnn(senal: &[f32]) -> Vec<Vec<f32>> {
    let mut plan = FftPlanner::new();
    let v = hann_simetrica(512);
    let b = banco(257, 96, 0.0, 8000.0, hz_a_mel_slaney, mel_slaney_a_hz, false, true, true);
    marcos(senal, 512, 256)
        .iter()
        .map(|m| {
            aplicar(&b, &espectro(m, &v, 512, &mut plan))
                .iter()
                .map(|x| (10_000.0 * x + 1.0).log10() as f32)
                .collect()
        })
        .collect()
}

fn bandas_vggish(senal: &[f32]) -> Vec<Vec<f32>> {
    let mut plan = FftPlanner::new();
    let v = hann_simetrica(400);
    let b = banco(257, 64, 125.0, 7500.0, hz_a_mel10, mel10_a_hz, true, false, false);
    marcos(senal, 400, 160)
        .iter()
        .map(|m| aplicar(&b, &espectro(m, &v, 512, &mut plan)).iter().map(|x| (x + 0.01).ln() as f32).collect())
        .collect()
}

fn comparar(nombre: &str, propio: &[Vec<f32>], referencia: &[f32], ancho: usize) {
    let n_ref = referencia.len() / ancho;
    let mut max = 0f32;
    for (t, fila) in propio.iter().take(n_ref).enumerate() {
        for (k, v) in fila.iter().enumerate() {
            max = max.max((v - referencia[t * ancho + k]).abs());
        }
    }
    println!("  {nombre}: {} marcos propios, {n_ref} de Essentia; diferencia máxima {max:.2e}", propio.len());
}

/// Parches como `VectorRealToTensor` con `lastPatchMode = discard`.
fn parches(bandas: &[Vec<f32>], tam: usize, salto: usize) -> Array3<f32> {
    let ancho = bandas[0].len();
    let inicios: Vec<usize> = (0..).map(|k| k * salto).take_while(|i| i + tam <= bandas.len()).collect();
    let mut a = Array3::<f32>::zeros((inicios.len(), tam, ancho));
    for (p, &ini) in inicios.iter().enumerate() {
        for t in 0..tam {
            for k in 0..ancho {
                a[[p, t, k]] = bandas[ini + t][k];
            }
        }
    }
    a
}

fn ejecutar(entorno: &ort::environment::Environment, modelos: &Path, nombre: &str, entrada: ndarray::ArrayD<f32>, salida: usize) -> ndarray::Array2<f32> {
    let mut s = Session::builder(entorno).unwrap().commit_from_file(modelos.join(format!("{nombre}.onnx"))).unwrap();
    let t = Tensor::from_array(entrada).unwrap();
    let r = s.run(ort::inputs![t]).unwrap();
    let (forma, datos) = r[salida].try_extract_tensor::<f32>().unwrap();
    let cols = *forma.last().unwrap() as usize;
    ndarray::Array2::from_shape_vec((datos.len() / cols, cols), datos.to_vec()).unwrap()
}

fn media(a: &ndarray::Array2<f32>) -> Vec<f64> {
    (0..a.ncols()).map(|c| a.column(c).iter().map(|v| *v as f64).sum::<f64>() / a.nrows() as f64).collect()
}

fn dif(propio: &[f64], json: &serde_json::Value) -> f64 {
    let r: Vec<f64> = json.as_array().unwrap().iter().map(|v| v.as_f64().unwrap()).collect();
    propio.iter().zip(&r).map(|(a, b)| (a - b).abs()).fold(0.0, f64::max)
}

/// La señal a 16 kHz decodificada y remuestreada por la V2 (Symphonia + rubato),
/// en lugar de la que vio Essentia: así se mide la cadena entera.
fn senal_propia(ruta: &str) -> Vec<f32> {
    use rubato::{FftFixedIn, Resampler};
    let pcm = decodificar::decodificar(Path::new(ruta), None).expect("decodificar");
    let mono: Vec<f32> = pcm.muestras.chunks_exact(2).map(|f| (f[0] + f[1]) * 0.5).collect();
    if std::env::var("LINEAL").is_ok() {
        // Lo que hace Essentia con `resampleQuality = 4`: el conversor lineal de
        // libsamplerate, con la razón calculada en f32 (no en f64: con f64 cada
        // muestra se va desplazando y la diferencia acumulada llega a -36 dB).
        let paso = 1.0 / (SR as f32 / pcm.tasa as f32) as f64;
        let n = (mono.len() as f64 / paso).round() as usize;
        let mut out = Vec::with_capacity(n);
        out.push(mono[0]);
        let mut idx = paso;
        let mut usado = idx.floor() as usize;
        idx -= idx.floor();
        while out.len() < n && usado < mono.len() {
            let a = mono[usado - 1] as f64;
            out.push((a + idx * (mono[usado] as f64 - a)) as f32);
            idx += paso;
            let entero = idx.floor();
            usado += entero as usize;
            idx -= entero;
        }
        return out;
    }
    let trozo = 4096;
    let mut rs = FftFixedIn::<f32>::new(pcm.tasa as usize, SR as usize, trozo, 2, 1).unwrap();
    let mut out = Vec::new();
    let mut i = 0;
    while i + trozo <= mono.len() {
        out.extend_from_slice(&rs.process(&[&mono[i..i + trozo]], None).unwrap()[0]);
        i += trozo;
    }
    if i < mono.len() {
        out.extend_from_slice(&rs.process_partial(Some(&[&mono[i..]]), None).unwrap()[0]);
    }
    let esperado = (mono.len() as f64 * SR / pcm.tasa as f64).round() as usize;
    out.into_iter().skip(rs.output_delay()).take(esperado).collect()
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if let Ok(ref44) = std::env::var("DIAG44") {
        let r = leer_f32(Path::new(&ref44));
        let pcm = decodificar::decodificar(Path::new(&args[2]), None).unwrap();
        let m: Vec<f32> = pcm.muestras.chunks_exact(2).map(|f| (f[0] + f[1]) * 0.5).collect();
        let base = 44_100 * 30;
        let mut mejor = (f64::MAX, 0i64);
        for d in -3000i64..=3000 {
            let e: f64 = (0..20000).map(|k| (m[(base as i64 + k + d) as usize] as f64 - r[base + k as usize] as f64).powi(2)).sum();
            if e < mejor.0 { mejor = (e, d); }
        }
        let en: f64 = (0..20000).map(|k| (r[base + k] as f64).powi(2)).sum();
        println!("Symphonia {} / Essentia {} muestras; desfase {}; error {:.1} dB", m.len(), r.len(), mejor.1, 10.0 * (mejor.0 / en).log10());
        return;
    }
    let entorno = ort::init_from(&args[1]).expect("ONNX Runtime").build().expect("entorno");
    if let Ok(base) = std::env::var("BASE_V1") {
        corpus(&entorno, Path::new(&args[2]), &base);
        return;
    }
    let (modelos, refdir) = (Path::new(&args[2]), Path::new(&args[3]));
    for clave in &args[4..] {
        println!("{clave}");
        let json: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(refdir.join(format!("{clave}.salidas.json"))).unwrap()).unwrap();
        let senal = if std::env::var("DECODIFICAR").is_ok() {
            senal_propia(json["archivo"].as_str().unwrap())
        } else {
            leer_f32(&refdir.join(format!("{clave}.audio.f32")))
        };
        if std::env::var("DIAG").is_ok() {
            let r = leer_f32(&refdir.join(format!("{clave}.audio.f32")));
            let base = 16_000 * 30;
            let mut mejor = (f64::MAX, 0i64);
            for d in -3000i64..=3000 {
                let e: f64 = (0..8000)
                    .map(|k| {
                        let j = (base as i64 + k + d) as usize;
                        (senal[j] as f64 - r[base + k as usize] as f64).powi(2)
                    })
                    .sum();
                if e < mejor.0 {
                    mejor = (e, d);
                }
            }
            let energia: f64 = (0..8000).map(|k| (r[base + k] as f64).powi(2)).sum();
            println!(
                "  longitud propia {} / Essentia {}; desfase {} muestras; error relativo {:.1} dB",
                senal.len(),
                r.len(),
                mejor.1,
                10.0 * (mejor.0 / energia).log10()
            );
            continue;
        }
        let bm = bandas_musicnn(&senal);
        comparar("bandas MusiCNN", &bm, &leer_f32(&refdir.join(format!("{clave}.musicnn.f32"))), 96);

        let pm = parches(&bm, 187, 93).into_dyn();
        // msd-musicnn-1 tiene tres salidas: Sigmoid (tags), dense_1 y dense (embeddings).
        let emb = ejecutar(&entorno, modelos, "msd-musicnn-1", pm.clone(), 2);
        let tags = ejecutar(&entorno, modelos, "msd-musicnn-1", pm, 0);
        println!("  embeddings MusiCNN: {} parches, diferencia de la media {:.2e}", emb.nrows(), dif(&media(&emb), &json["msd_musicnn_embeddings"]));
        println!("  etiquetas MSD: diferencia de la media {:.2e}", dif(&media(&tags), &json["tags_msd50"]));
        for cabeza in [
            "danceability-msd-musicnn-1",
            "mood_happy-msd-musicnn-1",
            "mood_sad-msd-musicnn-1",
            "mood_relaxed-msd-musicnn-1",
            "mood_aggressive-msd-musicnn-1",
            "mood_party-msd-musicnn-1",
            "deam-msd-musicnn-2",
        ] {
            let r = ejecutar(&entorno, modelos, cabeza, emb.clone().into_dyn(), 0);
            println!("  {cabeza:30} diferencia de la media {:.2e}", dif(&media(&r), &json[cabeza]));
        }
    }
}

/// Las 407 pistas que la V1 analizó: cadena completa en Rust frente a lo que guardó.
fn corpus(entorno: &ort::environment::Environment, modelos: &Path, base: &str) {
    let abrir = |n: &str| Session::builder(entorno).unwrap().commit_from_file(modelos.join(format!("{n}.onnx"))).unwrap();
    let mut emb_s = abrir("msd-musicnn-1");
    let cabezas = [
        ("danceability", "danceability-msd-musicnn-1", 0usize),
        ("mood_happy", "mood_happy-msd-musicnn-1", 0),
        ("mood_sad", "mood_sad-msd-musicnn-1", 1),
        ("mood_relaxed", "mood_relaxed-msd-musicnn-1", 1),
        ("mood_aggressive", "mood_aggressive-msd-musicnn-1", 0),
        ("mood_party", "mood_party-msd-musicnn-1", 1),
    ];
    let mut sesiones: Vec<Session> = cabezas.iter().map(|(_, n, _)| abrir(n)).collect();
    let mut deam = abrir("deam-msd-musicnn-2");
    let bd = rusqlite::Connection::open_with_flags(base, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY).unwrap();
    let mut q = bd
        .prepare("SELECT p.ruta_archivo, d.model_outputs_json FROM track_deep_audio_features d JOIN pistas p ON p.id = d.track_id WHERE d.analysis_status = 'ready'")
        .unwrap();
    let filas: Vec<(String, String)> = q.query_map([], |r| Ok((r.get(0)?, r.get(1)?))).unwrap().filter_map(Result::ok).collect();
    let (mut n, mut peor, mut fuera) = (0, 0f64, 0);
    let mut peor_por: std::collections::BTreeMap<&str, f64> = Default::default();
    let inicio = std::time::Instant::now();
    let limite: usize = std::env::var("LIMITE").ok().and_then(|v| v.parse().ok()).unwrap_or(usize::MAX);
    for (ruta, salidas) in filas.iter().take(limite) {
        if !Path::new(ruta).exists() {
            continue;
        }
        let o: serde_json::Value = serde_json::from_str(salidas).unwrap();
        let bm = bandas_musicnn(&senal_propia(ruta));
        // En lotes de 8 parches: con 64 (lo de Essentia) el pico llega a 3,6 GB por las
        // activaciones; con 8, 445 MB y la misma velocidad.
        let p = parches(&bm, 187, 93);
        let mut filas_emb: Vec<f32> = Vec::new();
        let mut cols = 0;
        let tam_lote: usize = std::env::var("LOTE").ok().and_then(|v| v.parse().ok()).unwrap_or(8);
        for lote in p.axis_chunks_iter(ndarray::Axis(0), tam_lote) {
            let r = emb_s.run(ort::inputs![Tensor::from_array(lote.to_owned().into_dyn()).unwrap()]).unwrap();
            let (forma, datos) = r[2].try_extract_tensor::<f32>().unwrap();
            cols = *forma.last().unwrap() as usize;
            filas_emb.extend_from_slice(datos);
        }
        let emb = ndarray::Array2::from_shape_vec((filas_emb.len() / cols, cols), filas_emb).unwrap();
        let mut max_pista = 0f64;
        for (k, (clave, _, clase)) in cabezas.iter().enumerate() {
            let r = sesiones[k].run(ort::inputs![Tensor::from_array(emb.clone().into_dyn()).unwrap()]).unwrap();
            let (f, d) = r[0].try_extract_tensor::<f32>().unwrap();
            let c = *f.last().unwrap() as usize;
            let m = media(&ndarray::Array2::from_shape_vec((d.len() / c, c), d.to_vec()).unwrap());
            let referencia = o[*clave]["classes"].as_object().unwrap().values().nth(*clase).unwrap().as_f64().unwrap();
            let e = (m[*clase] - referencia).abs();
            let entrada = peor_por.entry(clave).or_default();
            *entrada = entrada.max(e);
            max_pista = max_pista.max(e);
        }
        let r = deam.run(ort::inputs![Tensor::from_array(emb.into_dyn()).unwrap()]).unwrap();
        let (f, d) = r[0].try_extract_tensor::<f32>().unwrap();
        let c = *f.last().unwrap() as usize;
        let m = media(&ndarray::Array2::from_shape_vec((d.len() / c, c), d.to_vec()).unwrap());
        let av: Vec<f64> = o["arousal_valence"]["vector"].as_array().unwrap().iter().map(|v| v.as_f64().unwrap()).collect();
        // DEAM va de 1 a 9: se compara sobre esa escala dividida por 8, para que la
        // tolerancia de 0,01 signifique lo mismo que en las probabilidades.
        let e_av = m.iter().zip(&av).map(|(a, b)| (a - b).abs() / 8.0).fold(0.0, f64::max);
        let entrada = peor_por.entry("arousal_valence (escala 0-1)").or_default();
        *entrada = entrada.max(e_av);
        max_pista = max_pista.max(e_av);
        n += 1;
        peor = peor.max(max_pista);
        if max_pista >= 0.01 {
            fuera += 1;
            eprintln!("fuera de tolerancia ({max_pista:.3}): {ruta}");
        }
        if n % 50 == 0 {
            eprintln!("{n} pistas…");
        }
    }
    println!("{n} pistas en {:.0} s; peor diferencia {peor:.2e}; fuera de 0,01: {fuera}", inicio.elapsed().as_secs_f64());
    for (k, v) in peor_por {
        println!("  {k:28} peor {v:.2e}");
    }
}
