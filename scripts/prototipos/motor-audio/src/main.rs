//! Prototipo F0.4.1: ¿Symphonia + Kira cumplen los criterios de ADR-003?
//!
//! Código desechable. Lo que sobrevive es el informe en
//! `docs/audit/2026-10-29-prototipo-motor-audio.md`.
//!
//! Uso:
//!   cargo run --release -- todo <album-dir> <archivo-largo>
//!
//! Lee archivos del corpus en solo lectura; no escribe nada fuera de la salida
//! estándar.

mod decodificar;
mod fuente;
mod offline;

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use kira::clock::ClockSpeed;
use kira::effect::eq_filter::{EqFilterBuilder, EqFilterKind};
use kira::sound::static_sound::{StaticSoundData, StaticSoundSettings};
use kira::track::TrackBuilder;
use kira::{AudioManager, AudioManagerSettings, Decibels, Frame, StartTime, Tween};

use decodificar::{decodificar, Pcm};
use offline::{AjustesOffline, Offline};

const TASA: u32 = 44_100;
const BLOQUE: usize = 512;

fn gestor() -> AudioManager<Offline> {
    AudioManager::<Offline>::new(AudioManagerSettings {
        internal_buffer_size: BLOQUE,
        backend_settings: AjustesOffline { tasa: TASA },
        ..Default::default()
    })
    .expect("gestor")
}

fn a_sonido(pcm: &[f32], tasa: u32) -> StaticSoundData {
    let frames: Arc<[Frame]> = pcm
        .chunks_exact(2)
        .map(|f| Frame { left: f[0], right: f[1] })
        .collect();
    StaticSoundData {
        sample_rate: tasa,
        frames,
        settings: StaticSoundSettings::default(),
        slice: None,
    }
}

fn pistas_de(dir: &Path) -> Vec<PathBuf> {
    let mut v: Vec<PathBuf> = std::fs::read_dir(dir)
        .expect("carpeta del álbum")
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().is_some_and(|e| e == "mp3" || e == "flac"))
        .filter(|p| !p.to_string_lossy().ends_with("_2.mp3"))
        .collect();
    v.sort();
    v
}

/// 1. Sin cortes: A seguida de B en el mismo reloj debe ser exactamente A ++ B.
fn sin_cortes(album: &Path) {
    let pistas = pistas_de(album);
    assert!(pistas.len() >= 2, "hace falta un álbum con dos pistas");
    let a = decodificar(&pistas[0], None).expect("A");
    let b = decodificar(&pistas[1], None).expect("B");
    for (nombre, p) in [("A", &a), ("B", &b)] {
        println!(
            "  {nombre}: {} frames decodificados, {:?} declarados por el contenedor, {} Hz",
            p.frames(),
            p.frames_declarados,
            p.tasa
        );
    }

    let mut m = gestor();
    let mut reloj = m.add_clock(ClockSpeed::TicksPerSecond(TASA as f64)).expect("reloj");
    let inicio = reloj.time() + 1;
    let fin_a = inicio + a.frames() as u64;
    m.play(a_sonido(&a.muestras, a.tasa).start_time(StartTime::ClockTime(inicio)))
        .expect("A");
    m.play(a_sonido(&b.muestras, b.tasa).start_time(StartTime::ClockTime(fin_a)))
        .expect("B");
    reloj.start();
    let total = a.frames() + b.frames() + TASA as usize;
    let salida = m.backend_mut().renderizar(total);

    // Dónde empieza A en la salida: primer frame no nulo, contrastado con A.
    let primero_a = a.muestras.chunks_exact(2).position(|f| f[0] != 0.0 || f[1] != 0.0).unwrap_or(0);
    let primero_salida =
        salida.chunks_exact(2).position(|f| f[0] != 0.0 || f[1] != 0.0).unwrap_or(0);
    let desfase = primero_salida as i64 - primero_a as i64;

    let mut esperado = a.muestras.clone();
    esperado.extend_from_slice(&b.muestras);
    let mut max_err = 0f32;
    let mut primer_err = None;
    for (i, e) in esperado.iter().enumerate() {
        let j = i as i64 + desfase * 2;
        let s = if j >= 0 { salida.get(j as usize).copied().unwrap_or(0.0) } else { 0.0 };
        let err = (s - e).abs();
        if err > 1e-5 && primer_err.is_none() {
            primer_err = Some(i / 2);
        }
        max_err = max_err.max(err);
    }
    // Diagnóstico: primer frame donde la salida deja de ser A (con B aún sin empezar).
    let res: Vec<f32> = (0..a.frames())
        .map(|i| {
            let j = (i as i64 + desfase) as usize * 2;
            salida.get(j).copied().unwrap_or(0.0) - a.muestras[i * 2]
        })
        .collect();
    let primero_res = res.iter().position(|r| r.abs() > 1e-5);
    println!("  primer frame donde la salida difiere de A sola: {primero_res:?}");
    if let Some(p) = primero_res {
        // ¿Es B empezando antes? Compara el residuo con el comienzo de B.
        let inicio_b = b.muestras.chunks_exact(2).position(|f| f[0] != 0.0).unwrap_or(0);
        println!("  B empieza a sonar en su frame {inicio_b}; el residuo empieza {} frames antes de fin de A", a.frames() as i64 - p as i64);
        let corr = (0..64).map(|k| (res[p + k] - b.muestras[(inicio_b + k) * 2]).abs()).fold(0f32, f32::max);
        println!("  residuo frente a B desde su primer frame sonoro: {corr:.2e}");
    }
    let costura = a.frames();
    println!("  desfase de arranque: {desfase} frames; costura A→B en el frame {costura}");
    println!("  error máximo frente a A++B: {max_err:.2e}; primer frame distinto: {primer_err:?}");
    let silencio_en_costura = (costura.saturating_sub(64)..costura + 64)
        .filter(|&f| {
            let j = (f as i64 + desfase) as usize * 2;
            salida.get(j).is_some_and(|s| *s == 0.0) && salida.get(j + 1).is_some_and(|s| *s == 0.0)
        })
        .count();
    println!("  frames de silencio exacto en ±64 frames de la costura: {silencio_en_costura}");
}

fn frames(pcm: &[f32]) -> Arc<[Frame]> {
    pcm.chunks_exact(2).map(|f| Frame { left: f[0], right: f[1] }).collect()
}

/// 1b. Sin cortes con la fuente propia, y con el ecualizador en la pista.
fn sin_cortes_cola(album: &Path) {
    let pistas = pistas_de(album);
    let a = decodificar(&pistas[0], None).expect("A");
    let b = decodificar(&pistas[1], None).expect("B");
    let mut m = gestor();
    m.play(fuente::Cola {
        pistas: vec![
            fuente::Pista { original: frames(&a.muestras), instrumental: None },
            fuente::Pista { original: frames(&b.muestras), instrumental: None },
        ],
        rampa: 882,
    })
    .expect("cola");
    let salida = m.backend_mut().renderizar(a.frames() + b.frames() + BLOQUE);
    let mut esperado = a.muestras.clone();
    esperado.extend_from_slice(&b.muestras);
    let distintos = esperado.iter().zip(&salida).filter(|(e, s)| e != s).count();
    let por_encima = esperado.iter().zip(&salida).filter(|(e, s)| e != s && e.abs() > 1.0).count();
    let max_bajo_1 = esperado
        .iter()
        .zip(&salida)
        .filter(|(e, _)| e.abs() <= 1.0)
        .map(|(e, s)| (e - s).abs())
        .fold(0f32, f32::max);
    println!("  de las distintas, {por_encima} son muestras por encima de 0 dBFS; error máximo en el resto {max_bajo_1:.2e}");
    println!(
        "  A ({} frames) ++ B ({} frames): {distintos} muestras distintas de {} (comparación exacta, bit a bit)",
        a.frames(),
        b.frames(),
        esperado.len()
    );
}

/// 3b. Karaoke con la fuente propia: original e instrumental idénticos; conmutar
/// cinco veces no puede cambiar ni una muestra si están alineados.
fn karaoke_cola(archivo: &Path) {
    let pcm = decodificar(archivo, None).expect("pcm");
    let n = (TASA as usize * 300).min(pcm.frames());
    let f = frames(&pcm.muestras[..n * 2]);
    let mut m = gestor();
    let control = m
        .play(fuente::Cola {
            pistas: vec![fuente::Pista { original: f.clone(), instrumental: Some(f.clone()) }],
            rampa: 882,
        })
        .expect("cola");
    let mut salida = Vec::new();
    for k in 0..10 {
        control.karaoke(k % 2 == 0);
        salida.extend(m.backend_mut().renderizar(n / 10));
    }
    let max = salida
        .chunks_exact(2)
        .zip(f.iter())
        .map(|(s, o)| (s[0] - o.left).abs().max((s[1] - o.right).abs()))
        .fold(0f32, f32::max);
    println!("  {:.0} s con 10 conmutaciones: desviación máxima frente al original {max:.2e}", n as f64 / TASA as f64);
}

/// 2. Seek preciso: lo que sale tras buscar a T es lo que hay en T decodificando desde 0.
fn seek(archivo: &Path) {
    let completo = decodificar(archivo, None).expect("completo");
    let dur = completo.frames() as f64 / completo.tasa as f64;
    let mut peor = 0i64;
    for k in 1..=12 {
        let t = dur * k as f64 / 13.0;
        let parcial = decodificar(archivo, Some(t)).expect("parcial");
        let ventana = &parcial.muestras[..(4096 * 2).min(parcial.muestras.len())];
        let centro = (t * completo.tasa as f64).round() as i64;
        // Busca el mejor alineamiento en ±3000 frames.
        let mut mejor = (f32::MAX, 0i64);
        for d in -3000i64..=3000 {
            let base = centro + d;
            if base < 0 || (base as usize + 4096) * 2 > completo.muestras.len() {
                continue;
            }
            let ref_ = &completo.muestras[base as usize * 2..base as usize * 2 + ventana.len()];
            let err: f32 = ref_.iter().zip(ventana).map(|(a, b)| (a - b).abs()).sum();
            if err < mejor.0 {
                mejor = (err, d);
            }
        }
        peor = peor.max(mejor.1.abs());
        println!(
            "  t={t:7.2}s  desvío {:+5} frames ({:+.2} ms)  error residual {:.2e}",
            mejor.1,
            mejor.1 as f64 * 1000.0 / completo.tasa as f64,
            mejor.0
        );
    }
    println!(
        "  peor desvío: {peor} frames = {:.2} ms",
        peor as f64 * 1000.0 / completo.tasa as f64
    );
}

/// 3. Karaoke: A y −A arrancados en el mismo instante deben anularse durante 5 min.
fn karaoke(archivo: &Path) {
    let pcm = decodificar(archivo, None).expect("pcm");
    let cinco_min = (TASA as usize * 300).min(pcm.frames());
    let original = &pcm.muestras[..cinco_min * 2];
    let invertido: Vec<f32> = original.iter().map(|s| -s).collect();

    let mut m = gestor();
    let mut reloj = m.add_clock(ClockSpeed::TicksPerSecond(TASA as f64)).expect("reloj");
    let t = reloj.time() + 1;
    m.play(a_sonido(original, pcm.tasa).start_time(StartTime::ClockTime(t))).expect("A");
    m.play(a_sonido(&invertido, pcm.tasa).start_time(StartTime::ClockTime(t))).expect("-A");
    reloj.start();
    let salida = m.backend_mut().renderizar(cinco_min + TASA as usize);
    let max = salida.iter().fold(0f32, |m, s| m.max(s.abs()));
    let pico_original = original.iter().fold(0f32, |m, s| m.max(s.abs()));
    println!(
        "  {:.0} s renderizados: residuo máximo {max:.2e} con un pico original de {pico_original:.3}",
        cinco_min as f64 / TASA as f64
    );

    // Conmutar original → instrumental con una transición de 20 ms: el salto
    // entre muestras consecutivas no debe superar al de la propia música.
    let mut m = gestor();
    let mut reloj = m.add_clock(ClockSpeed::TicksPerSecond(TASA as f64)).expect("reloj");
    let t = reloj.time() + 1;
    let mut voz = m
        .play(a_sonido(original, pcm.tasa).start_time(StartTime::ClockTime(t)))
        .expect("original");
    let mut inst = m
        .play(
            a_sonido(original, pcm.tasa)
                .volume(Decibels::SILENCE)
                .start_time(StartTime::ClockTime(t)),
        )
        .expect("instrumental");
    reloj.start();
    let mut salida = m.backend_mut().renderizar(TASA as usize * 10);
    let tween = Tween { duration: Duration::from_millis(20), ..Default::default() };
    voz.set_volume(Decibels::SILENCE, tween);
    inst.set_volume(Decibels::IDENTITY, tween);
    let antes = salida.len();
    salida.extend(m.backend_mut().renderizar(TASA as usize));
    let salto = |v: &[f32]| v.windows(3).step_by(2).fold(0f32, |m, w| m.max((w[2] - w[0]).abs()));
    println!(
        "  salto máximo entre muestras: {:.4} en la música, {:.4} en la conmutación",
        salto(&salida[..antes]),
        salto(&salida[antes - 4096..antes + 4096])
    );
}

/// Los 18 presets de la V1 (`legado/servicios/reproductor.py`).
const BANDAS: [f64; 10] = [31.0, 62.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0];
const PRESETS: [(&str, [f64; 10]); 18] = [
    ("Flat", [0.0; 10]),
    ("Classical", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -7.2, -7.2, -7.2, -9.6]),
    ("Club", [0.0, 0.0, 8.0, 5.6, 5.6, 5.6, 3.2, 0.0, 0.0, 0.0]),
    ("Dance", [9.6, 7.2, 2.4, 0.0, 0.0, -5.6, -7.2, -7.2, 0.0, 0.0]),
    ("Full bass", [-8.0, 9.6, 9.6, 5.6, 1.6, -4.0, -8.0, -10.4, -11.2, -11.2]),
    ("Full bass and treble", [7.2, 5.6, 0.0, -7.2, -4.8, 1.6, 8.0, 11.2, 12.0, 12.0]),
    ("Full treble", [-9.6, -9.6, -9.6, -4.0, 2.4, 11.2, 16.0, 16.0, 16.0, 16.8]),
    ("Headphones", [4.8, 11.2, 5.6, -3.2, -2.4, 1.6, 4.8, 9.6, 12.8, 14.4]),
    ("Large Hall", [10.4, 10.4, 5.6, 5.6, 0.0, -4.8, -4.8, -4.8, 0.0, 0.0]),
    ("Live", [-4.8, 0.0, 4.0, 5.6, 5.6, 5.6, 4.0, 2.4, 2.4, 2.4]),
    ("Party", [7.2, 7.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 7.2, 7.2]),
    ("Pop", [-1.6, 4.8, 7.2, 8.0, 5.6, 0.0, -2.4, -2.4, -1.6, -1.6]),
    ("Reggae", [0.0, 0.0, 0.0, -5.6, 0.0, 6.4, 6.4, 0.0, 0.0, 0.0]),
    ("Rock", [8.0, 4.8, -5.6, -8.0, -3.2, 4.0, 8.8, 11.2, 11.2, 11.2]),
    ("Ska", [-2.4, -4.8, -4.0, 0.0, 4.0, 5.6, 8.8, 9.6, 11.2, 9.6]),
    ("Soft", [4.8, 1.6, 0.0, -2.4, 0.0, 4.0, 8.0, 9.6, 11.2, 12.0]),
    ("Soft rock", [4.0, 4.0, 2.4, 0.0, -4.0, -5.6, -3.2, 0.0, 2.4, 8.8]),
    ("Techno", [8.0, 5.6, 0.0, -5.6, -4.8, 0.0, 8.0, 9.6, 9.6, 8.8]),
];
/// Una octava de ancho de banda.
const Q: f64 = 1.414;

/// Ganancia medida (dB) en cada frecuencia central con una cadena de 10 campanas.
fn respuesta(ganancias: &[f64; 10]) -> [f64; 10] {
    let mut medida = [0.0; 10];
    for (i, &f) in BANDAS.iter().enumerate() {
        let mut m = gestor();
        let mut pista = TrackBuilder::new();
        for (i, (b, g)) in BANDAS.iter().zip(ganancias).enumerate() {
            // Los extremos como estantes: una campana a 16 kHz con 44,1 kHz de
            // muestreo queda aplastada contra Nyquist y no alcanza los +16 dB de
            // "Full treble" sin arrastrar a la banda de 8 kHz.
            let tipo = match i {
                0 if std::env::var("ESTANTES").is_ok() => EqFilterKind::LowShelf,
                9 if std::env::var("ESTANTES").is_ok() => EqFilterKind::HighShelf,
                _ => EqFilterKind::Bell,
            };
            pista.add_effect(EqFilterBuilder::new(tipo, *b, Decibels(*g as f32), Q));
        }
        let mut pista = m.add_sub_track(pista).expect("pista");
        let n = TASA as usize; // 1 s de seno
        let seno: Vec<f32> = (0..n)
            .flat_map(|k| {
                let s = (2.0 * std::f64::consts::PI * f * k as f64 / TASA as f64).sin() as f32 * 0.01;
                [s, s]
            })
            .collect();
        pista.play(a_sonido(&seno, TASA)).expect("seno");
        let salida = m.backend_mut().renderizar(n);
        // RMS de la segunda mitad (ya estable) frente al de la entrada.
        let rms = |v: &[f32]| (v.iter().map(|s| (*s as f64).powi(2)).sum::<f64>() / v.len() as f64).sqrt();
        let mitad = n; // en muestras entrelazadas, la segunda mitad empieza en n
        medida[i] = 20.0 * (rms(&salida[mitad..n * 2]) / rms(&seno[mitad..n * 2])).log10();
    }
    medida
}

fn ecualizador() {
    let mut peor_directo = 0f64;
    let mut peor_corregido = 0f64;
    for (nombre, objetivo) in PRESETS {
        let directa = respuesta(&objetivo);
        let err_d = directa.iter().zip(&objetivo).map(|(a, b)| (a - b).abs()).fold(0.0, f64::max);
        // Corrección iterativa: se ajustan las ganancias hasta que la respuesta en
        // cada centro coincide con la tabla.
        let mut g = objetivo;
        let mut med = directa;
        for _ in 0..20 {
            for k in 0..10 {
                g[k] += objetivo[k] - med[k];
            }
            med = respuesta(&g);
        }
        let err_c = med.iter().zip(&objetivo).map(|(a, b)| (a - b).abs()).fold(0.0, f64::max);
        peor_directo = peor_directo.max(err_d);
        peor_corregido = peor_corregido.max(err_c);
        println!("  {nombre:22} directo ±{err_d:5.2} dB   corregido ±{err_c:5.2} dB");
    }
    println!("  peor: directo ±{peor_directo:.2} dB, corregido ±{peor_corregido:.2} dB");
}

/// 5 y 6. Coste del motor: renderizado con EQ, sin y con todos los núcleos ocupados.
fn carga(archivo: &Path) {
    let pcm = decodificar(archivo, None).expect("pcm");
    let medir = |etiqueta: &str| {
        let mut m = gestor();
        let mut pista = TrackBuilder::new();
        for b in BANDAS {
            pista.add_effect(EqFilterBuilder::new(EqFilterKind::Bell, b, Decibels(3.0), Q));
        }
        let mut pista = m.add_sub_track(pista).expect("pista");
        pista.play(a_sonido(&pcm.muestras, pcm.tasa)).expect("pista");
        let bloques = pcm.frames() / BLOQUE;
        let dur_bloque = BLOQUE as f64 / TASA as f64;
        let mut tiempos = Vec::with_capacity(bloques);
        let mut sal = Vec::with_capacity(BLOQUE * 2);
        let total = Instant::now();
        for _ in 0..bloques {
            sal.clear();
            let t = Instant::now();
            m.backend_mut().bloque(&mut sal);
            tiempos.push(t.elapsed().as_secs_f64());
        }
        let total = total.elapsed().as_secs_f64();
        tiempos.sort_by(f64::total_cmp);
        let p99 = tiempos[tiempos.len() * 99 / 100];
        let max = *tiempos.last().unwrap();
        println!(
            "  {etiqueta}: {:.2} % de un núcleo; bloque de {:.1} ms: p99 {:.3} ms, máximo {:.3} ms ({:.1} % del plazo)",
            100.0 * total / (pcm.frames() as f64 / TASA as f64),
            dur_bloque * 1000.0,
            p99 * 1000.0,
            max * 1000.0,
            100.0 * max / dur_bloque
        );
    };
    medir("en reposo");
    let parar = Arc::new(AtomicBool::new(false));
    let nucleos = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4);
    let hilos: Vec<_> = (0..nucleos)
        .map(|_| {
            let parar = parar.clone();
            std::thread::spawn(move || {
                let mut x = 1u64;
                while !parar.load(Ordering::Relaxed) {
                    x = x.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
                }
                x
            })
        })
        .collect();
    medir(&format!("con {nucleos} núcleos al 100 %"));
    parar.store(true, Ordering::Relaxed);
    for h in hilos {
        let _ = h.join();
    }
}

/// Reproducción real con cpal durante `segundos` y los núcleos ocupados: cuenta
/// los errores de flujo que reporta el backend.
fn dispositivo(archivo: &Path, segundos: u64) {
    use kira::backend::cpal::CpalBackend;
    let pcm = decodificar(archivo, None).expect("pcm");
    let Ok(mut m) = AudioManager::<CpalBackend>::new(AudioManagerSettings::default()) else {
        println!("  sin dispositivo de audio en esta máquina: no se mide");
        return;
    };
    let parar = Arc::new(AtomicBool::new(false));
    let nucleos = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4);
    let hilos: Vec<_> = (0..nucleos)
        .map(|_| {
            let parar = parar.clone();
            std::thread::spawn(move || {
                let mut x = 1u64;
                while !parar.load(Ordering::Relaxed) {
                    x = x.wrapping_mul(6364136223846793005).wrapping_add(1);
                }
                x
            })
        })
        .collect();
    let mut sonido = m
        .play(a_sonido(&pcm.muestras, pcm.tasa).volume(Decibels(-60.0)))
        .expect("sonido");
    let mut errores = 0;
    let mut uso_max = 0f32;
    let fin = Instant::now() + Duration::from_secs(segundos);
    while Instant::now() < fin {
        std::thread::sleep(Duration::from_millis(100));
        while m.backend_mut().pop_error().is_some() {
            errores += 1;
        }
        while let Some(u) = m.backend_mut().pop_cpu_usage() {
            uso_max = uso_max.max(u);
        }
    }
    sonido.stop(Tween::default());
    parar.store(true, Ordering::Relaxed);
    for h in hilos {
        let _ = h.join();
    }
    println!(
        "  {segundos} s en el dispositivo real con {nucleos} núcleos ocupados: {errores} errores de flujo, {:?} descartados; uso máximo del hilo de audio {:.1} %",
        m.backend_mut().num_stream_errors_discarded(),
        uso_max * 100.0
    );
}

/// Diagnóstico: un solo sonido, sin reloj; ¿la salida es la entrada muestra a muestra?
fn exactitud(archivo: &Path) {
    let pcm = decodificar(archivo, None).expect("pcm");
    let n = pcm.frames().min(TASA as usize * 60);
    let mut m = gestor();
    if std::env::var("CON_RELOJ").is_ok() {
        let mut reloj = m.add_clock(ClockSpeed::TicksPerSecond(TASA as f64)).expect("reloj");
        let t = reloj.time() + 1;
        m.play(a_sonido(&pcm.muestras[..n * 2], pcm.tasa).start_time(StartTime::ClockTime(t)))
            .expect("A");
        reloj.start();
    } else {
        m.play(a_sonido(&pcm.muestras[..n * 2], pcm.tasa)).expect("A");
    }
    let salida = m.backend_mut().renderizar(n + TASA as usize);
    let inicio = salida.chunks_exact(2).position(|f| f[0] != 0.0).unwrap_or(0);
    let ref0 = pcm.muestras.chunks_exact(2).position(|f| f[0] != 0.0).unwrap_or(0);
    let d = inicio as i64 - ref0 as i64;
    println!("  desfase {d}");
    for seg in 0..(n / TASA as usize) {
        let base = seg * TASA as usize;
        let mut mejor = (f32::MAX, 0i64);
        for off in -4i64..=4 {
            let mut err = 0f32;
            for k in 0..2048 {
                let i = base + k;
                let j = i as i64 + d + off;
                if j < 0 { continue; }
                err += (salida[j as usize * 2] - pcm.muestras[i * 2]).abs();
            }
            if err < mejor.0 { mejor = (err, off); }
        }
        if seg % 5 == 0 || mejor.1 != 0 {
            println!("  s={seg:3} mejor desplazamiento {:+} error {:.2e}", mejor.1, mejor.0);
        }
    }
}

fn main() {
    if std::env::args().nth(1).as_deref() == Some("eq") {
        ecualizador();
        return;
    }
    if std::env::args().nth(1).as_deref() == Some("exactitud") {
        exactitud(Path::new(&std::env::args().nth(2).unwrap()));
        return;
    }
    let args: Vec<String> = std::env::args().collect();
    let album = PathBuf::from(args.get(2).expect("carpeta de álbum"));
    let largo = PathBuf::from(args.get(3).expect("archivo largo"));
    let segundos: u64 = args.get(4).and_then(|s| s.parse().ok()).unwrap_or(60);
    println!("1. Sin cortes entre pistas");
    sin_cortes(&album);
    println!("1b. Sin cortes con la fuente propia");
    sin_cortes_cola(&album);
    println!("2. Seek preciso");
    seek(&largo);
    println!("3. Karaoke: sincronía y conmutación");
    karaoke(&largo);
    println!("3b. Karaoke con la fuente propia");
    karaoke_cola(&largo);
    println!("4. Ecualizador de 10 bandas, 18 presets de la V1");
    ecualizador();
    println!("5. Coste del motor");
    carga(&largo);
    println!("6. Dispositivo real bajo carga");
    dispositivo(&largo, segundos);
}
