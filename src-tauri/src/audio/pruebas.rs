//! El motor sin tarjeta de sonido: una salida de Kira que renderiza fuera de línea
//! y entrega lo que produce, y archivos WAV generados con muestras conocidas.
//! Es lo que permite comprobar el motor muestra a muestra (como en F0.4.1).

use std::path::{Path, PathBuf};
use std::sync::atomic::Ordering;
use std::time::{Duration, Instant};

use kira::backend::{Backend, Renderer};
use kira::AudioManagerSettings;

use super::{ecualizador, EventoMotor, Motor, PistaEnCola};

pub(crate) struct Offline {
    renderer: Option<Renderer>,
    bloque: usize,
}

#[derive(Clone, Copy)]
pub(crate) struct Tasa(pub u32);

impl Default for Tasa {
    fn default() -> Self {
        Self(44_100)
    }
}

impl Backend for Offline {
    type Settings = Tasa;
    type Error = ();

    fn setup(tasa: Tasa, internal_buffer_size: usize) -> Result<(Self, u32), ()> {
        Ok((
            Self {
                renderer: None,
                bloque: internal_buffer_size,
            },
            tasa.0,
        ))
    }

    fn start(&mut self, renderer: Renderer) -> Result<(), ()> {
        self.renderer = Some(renderer);
        Ok(())
    }
}

pub(crate) fn motor(tasa: u32) -> Motor<Offline> {
    Motor::con(AudioManagerSettings {
        backend_settings: Tasa(tasa),
        ..Default::default()
    })
    .expect("motor")
}

/// Renderiza al menos `frames` frames, esperando antes de cada bloque a que el
/// alimentador tenga datos: en la máquina real la cola va siempre por delante,
/// y aquí el renderizado es más rápido que el tiempo real.
pub(crate) fn renderizar(m: &mut Motor<Offline>, frames: usize) -> Vec<f32> {
    let mut salida = Vec::with_capacity(frames * 2 + 512);
    while salida.len() / 2 < frames {
        let limite = Instant::now() + Duration::from_secs(2);
        // Los dos platos: en una mezcla suenan a la vez.
        let pendiente = |c: &super::fuente::Compartido| {
            let vigente = c.generacion.load(Ordering::Acquire);
            (c.en_cola.load(Ordering::Acquire) == 0
                || c.entregada.load(Ordering::Acquire) != vigente)
                && !c.terminado.load(Ordering::Acquire)
        };
        while m.compartidos().into_iter().any(pendiente) && Instant::now() < limite {
            std::thread::sleep(Duration::from_millis(1));
        }
        let backend = m.backend();
        let n = backend.bloque;
        let renderer = backend.renderer.as_mut().expect("arrancado");
        renderer.on_start_processing();
        let mut buffer = vec![0.0f32; n * 2];
        renderer.process(&mut buffer, 2);
        salida.extend_from_slice(&buffer);
    }
    salida
}

/// Hasta que se acaba la cola.
fn renderizar_todo(m: &mut Motor<Offline>) -> Vec<f32> {
    let mut salida = Vec::new();
    let limite = Instant::now() + Duration::from_secs(30);
    while !m.compartido().terminado.load(Ordering::Acquire) && Instant::now() < limite {
        salida.extend(renderizar(m, 4096));
    }
    salida
}

/// Recoge eventos hasta que se cumple `listo` o pasan 5 s: el vigía los cuenta
/// desde otro hilo, y en una máquina cargada puede ir por detrás.
fn esperar_eventos(m: &Motor<Offline>, listo: impl Fn(&[EventoMotor]) -> bool) -> Vec<EventoMotor> {
    let mut eventos = Vec::new();
    let limite = Instant::now() + Duration::from_secs(5);
    while !listo(&eventos) && Instant::now() < limite {
        eventos.extend(m.eventos());
        std::thread::sleep(Duration::from_millis(5));
    }
    eventos
}

fn temporal(nombre: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("ns-motor-{nombre}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// Un WAV estéreo de 16 bits. Devuelve las muestras tal como las leerá el
/// decodificador, entrelazadas.
pub(crate) fn wav(
    ruta: &Path,
    tasa: u32,
    frames: usize,
    muestra: impl Fn(usize, usize) -> f32,
) -> Vec<f32> {
    let mut datos = Vec::with_capacity(frames * 4);
    let mut leidas = Vec::with_capacity(frames * 2);
    for i in 0..frames {
        for canal in 0..2 {
            let v = (muestra(i, canal).clamp(-1.0, 1.0) * 32767.0).round() as i16;
            datos.extend(v.to_le_bytes());
            leidas.push(f32::from(v) / 32768.0);
        }
    }
    let mut b = Vec::new();
    b.extend(b"RIFF");
    b.extend((36 + datos.len() as u32).to_le_bytes());
    b.extend(b"WAVEfmt ");
    b.extend(16u32.to_le_bytes());
    b.extend(1u16.to_le_bytes());
    b.extend(2u16.to_le_bytes());
    b.extend(tasa.to_le_bytes());
    b.extend((tasa * 4).to_le_bytes());
    b.extend(4u16.to_le_bytes());
    b.extend(16u16.to_le_bytes());
    b.extend(b"data");
    b.extend((datos.len() as u32).to_le_bytes());
    b.extend(datos);
    std::fs::write(ruta, b).unwrap();
    leidas
}

/// Ruido determinista por debajo del umbral del limitador.
pub(crate) fn ruido(semilla: u32) -> impl Fn(usize, usize) -> f32 {
    move |i, c| {
        let mut x = (i as u32).wrapping_mul(2_654_435_761) ^ semilla.wrapping_add(c as u32 * 97);
        x ^= x >> 13;
        x = x.wrapping_mul(0x5bd1_e995);
        x ^= x >> 15;
        (x as f32 / u32::MAX as f32 - 0.5) * 1.2
    }
}

fn pista(ficha: u64, ruta: &Path) -> PistaEnCola {
    PistaEnCola {
        ficha,
        ruta: ruta.to_path_buf(),
        instrumental: None,
        ganancia_db: 0.0,
    }
}

fn inicio_de_audio(salida: &[f32]) -> usize {
    salida.iter().position(|s| *s != 0.0).unwrap_or(0) / 2 * 2
}

#[test]
fn dos_pistas_suenan_una_tras_otra_sin_un_solo_frame_de_hueco() {
    let dir = temporal("sin-cortes");
    let a = wav(&dir.join("a.wav"), 44_100, 44_100, ruido(1));
    let b = wav(&dir.join("b.wav"), 44_100, 30_000, ruido(2));
    let mut m = motor(44_100);
    m.reproducir(pista(1, &dir.join("a.wav")), 0.0);
    m.siguiente(Some(pista(2, &dir.join("b.wav"))));
    let salida = renderizar_todo(&mut m);
    let inicio = inicio_de_audio(&salida);
    let esperado: Vec<f32> = a.iter().chain(&b).copied().collect();
    let obtenido = &salida[inicio..inicio + esperado.len()];
    let distintas = obtenido
        .iter()
        .zip(&esperado)
        .filter(|(x, y)| x.to_bits() != y.to_bits())
        .count();
    assert_eq!(distintas, 0, "la salida es A y luego B, bit a bit");
    let eventos = esperar_eventos(&m, |e| e.contains(&EventoMotor::ColaTerminada));
    assert!(eventos.contains(&EventoMotor::PistaEmpieza { ficha: 1 }));
    assert!(eventos.contains(&EventoMotor::PistaEmpieza { ficha: 2 }));
    let _ = std::fs::remove_dir_all(dir);
}

#[test]
fn buscar_cae_en_la_muestra_exacta() {
    let dir = temporal("buscar");
    let a = wav(&dir.join("a.wav"), 44_100, 44_100 * 3, ruido(3));
    let mut m = motor(44_100);
    m.reproducir(pista(1, &dir.join("a.wav")), 0.0);
    let _ = renderizar(&mut m, 8_192);
    m.buscar(1.5);
    let salida = renderizar(&mut m, 8_192);
    let inicio = inicio_de_audio(&salida);
    let frame = 66_150;
    assert_eq!(
        &salida[inicio..inicio + 200],
        &a[frame * 2..frame * 2 + 200]
    );
    let pos = m.posicion();
    assert!((pos.segundos - 1.5).abs() < 0.3, "{pos:?}");
    let _ = std::fs::remove_dir_all(dir);
}

#[test]
fn una_pista_a_otra_tasa_se_remuestrea_sin_cambiar_el_tono() {
    let dir = temporal("remuestreo");
    let _ = wav(&dir.join("a.wav"), 22_050, 22_050, |i, _| {
        (2.0 * std::f32::consts::PI * 441.0 * i as f32 / 22_050.0).sin() * 0.5
    });
    let mut m = motor(44_100);
    m.reproducir(pista(1, &dir.join("a.wav")), 0.0);
    let salida = renderizar_todo(&mut m);
    let izq: Vec<f32> = salida.iter().step_by(2).copied().collect();
    let inicio = izq.iter().position(|s| *s != 0.0).unwrap_or(0) + 100;
    let tramo = &izq[inicio..inicio + 44_100 / 2];
    let cruces = tramo
        .windows(2)
        .filter(|w| w[0] <= 0.0 && w[1] > 0.0)
        .count();
    assert!(
        (219..=222).contains(&cruces),
        "441 Hz son 220,5 ciclos en medio segundo: {cruces}"
    );
    let rms = (tramo.iter().map(|s| s * s).sum::<f32>() / tramo.len() as f32).sqrt();
    assert!((rms - 0.5 / 2f32.sqrt()).abs() < 0.01, "{rms}");
    let _ = std::fs::remove_dir_all(dir);
}

/// La respuesta medida de verdad en la salida de Kira, no la calculada.
#[test]
fn el_ecualizador_da_en_cada_centro_el_valor_de_la_tabla() {
    let dir = temporal("ecualizador");
    for indice in [13, 6] {
        let p = &ecualizador::PRESELECCIONES[indice];
        let preamp = ecualizador::preamp_con_margen(p.preamp_db, &p.bandas_db);
        for (k, f) in ecualizador::BANDAS_HZ.iter().enumerate() {
            let ruta = dir.join(format!("seno-{k}.wav"));
            // Amplitud baja: a amplitud alta el limitador falsearía la medida.
            let entrada = wav(&ruta, 44_100, 44_100, |i, _| {
                (2.0 * std::f64::consts::PI * f * i as f64 / 44_100.0).sin() as f32 * 0.01
            });
            let mut m = motor(44_100);
            m.ecualizador(p.bandas_db, p.preamp_db);
            m.reproducir(pista(1, &ruta), 0.0);
            let salida = renderizar_todo(&mut m);
            let rms = |v: &[f32]| {
                (v.iter().map(|s| f64::from(*s).powi(2)).sum::<f64>() / v.len() as f64).sqrt()
            };
            let inicio = inicio_de_audio(&salida);
            let medida = 20.0
                * (rms(&salida[inicio + 44_100..inicio + 80_000]) / rms(&entrada[44_100..80_000]))
                    .log10();
            let esperada = f64::from(preamp + p.bandas_db[k]);
            assert!(
                (medida - esperada).abs() < 0.5,
                "{} banda {k}: {medida:.2} dB frente a {esperada:.2}",
                p.nombre
            );
        }
    }
    let _ = std::fs::remove_dir_all(dir);
}

#[test]
fn los_picos_por_encima_de_0_dbfs_no_se_recortan_en_seco() {
    let dir = temporal("limitador");
    let _ = wav(&dir.join("a.wav"), 44_100, 22_050, |i, _| {
        (2.0 * std::f32::consts::PI * 100.0 * i as f32 / 44_100.0).sin() * 0.95
    });
    let mut m = motor(44_100);
    let mut p = pista(1, &dir.join("a.wav"));
    p.ganancia_db = 6.0;
    m.reproducir(p, 0.0);
    let salida = renderizar_todo(&mut m);
    let pico = salida.iter().fold(0.0f32, |a, s| a.max(s.abs()));
    assert!(pico < 1.0 && pico > 0.95, "{pico}");
    let _ = std::fs::remove_dir_all(dir);
}

#[test]
fn en_pausa_la_posicion_no_avanza() {
    let dir = temporal("pausa");
    let _ = wav(&dir.join("a.wav"), 44_100, 44_100 * 2, ruido(4));
    let mut m = motor(44_100);
    m.reproducir(pista(1, &dir.join("a.wav")), 0.0);
    let _ = renderizar(&mut m, 8_192);
    m.pausar();
    let _ = renderizar(&mut m, 4_096);
    let antes = m.posicion();
    let silencio = renderizar(&mut m, 8_192);
    assert_eq!(m.posicion().segundos, antes.segundos);
    assert!(!m.posicion().reproduciendo);
    assert!(silencio.iter().all(|s| *s == 0.0));
    m.reanudar();
    let _ = renderizar(&mut m, 8_192);
    assert!(m.posicion().segundos > antes.segundos);
    let _ = std::fs::remove_dir_all(dir);
}

#[test]
fn el_karaoke_pasa_al_instrumental_sin_desfase() {
    let dir = temporal("karaoke");
    let _ = wav(&dir.join("o.wav"), 44_100, 44_100 * 2, ruido(5));
    let inst = wav(&dir.join("i.wav"), 44_100, 44_100 * 2, ruido(6));
    let mut m = motor(44_100);
    let mut p = pista(1, &dir.join("o.wav"));
    p.instrumental = Some(dir.join("i.wav"));
    m.reproducir(p, 0.0);
    let _ = renderizar(&mut m, 4_096);
    m.karaoke(true);
    // La transición dura 30 ms; después, solo el instrumental, en su sitio.
    let _ = renderizar(&mut m, 4_096);
    let frame = m.compartido().frame.load(Ordering::Relaxed) as usize;
    let salida = renderizar(&mut m, 4_096);
    assert_eq!(&salida[..400], &inst[frame * 2..frame * 2 + 400]);
    let _ = std::fs::remove_dir_all(dir);
}

/// F5.2.2: el instrumental que se prepara mientras suena el original se añade a
/// la pista en curso y cae en su sitio, sin desfase y sin cortar.
#[test]
fn el_instrumental_preparado_a_mitad_de_pista_entra_sin_desfase() {
    let dir = temporal("karaoke-en-caliente");
    let _ = wav(&dir.join("o.wav"), 44_100, 44_100 * 6, ruido(15));
    let inst = wav(&dir.join("i.wav"), 44_100, 44_100 * 6, ruido(16));
    let mut m = motor(44_100);
    m.reproducir(pista(1, &dir.join("o.wav")), 0.0);
    let _ = renderizar(&mut m, 44_100);
    m.instrumental_listo(1, dir.join("i.wav"));
    m.karaoke(true);
    // Lo decodificado por delante (hasta un segundo y medio) sigue sin
    // instrumental; pasado eso, suena solo el instrumental, en su sitio.
    let _ = renderizar(&mut m, 44_100 * 2);
    let frame = m.compartido().frame.load(Ordering::Relaxed) as usize;
    let salida = renderizar(&mut m, 4_096);
    assert_eq!(&salida[..400], &inst[frame * 2..frame * 2 + 400]);
    let _ = std::fs::remove_dir_all(dir);
}

#[test]
fn una_pista_que_no_existe_se_salta_y_lo_dice() {
    let dir = temporal("ilegible");
    let b = wav(&dir.join("b.wav"), 44_100, 10_000, ruido(7));
    let mut m = motor(44_100);
    m.reproducir(pista(1, &dir.join("no-existe.wav")), 0.0);
    m.siguiente(Some(pista(2, &dir.join("b.wav"))));
    let salida = renderizar_todo(&mut m);
    let inicio = inicio_de_audio(&salida);
    assert_eq!(
        &salida[inicio..inicio + 100],
        &b[..100],
        "suena la siguiente"
    );
    let eventos = esperar_eventos(&m, |e| e.contains(&EventoMotor::ColaTerminada));
    assert!(eventos.contains(&EventoMotor::PistaIlegible {
        ficha: 1,
        error: crate::error::NsError::FileNotFound
    }));
    assert!(eventos.contains(&EventoMotor::ColaTerminada));
    let _ = std::fs::remove_dir_all(dir);
}

/// Regresión del CI de macOS (2026-10-30): con una sola marca, dos pistas que
/// empezaban dentro del mismo intervalo del vigía se contaban como una, y el
/// servicio creía que sonaba otra.
#[test]
fn dos_pistas_que_empiezan_en_el_mismo_bloque_se_cuentan_las_dos() {
    let dir = temporal("sucesos");
    let _ = wav(&dir.join("a.wav"), 44_100, 300, ruido(8));
    let _ = wav(&dir.join("b.wav"), 44_100, 300, ruido(9));
    let mut m = motor(44_100);
    m.reproducir(pista(1, &dir.join("a.wav")), 0.0);
    m.siguiente(Some(pista(2, &dir.join("b.wav"))));
    let _ = renderizar_todo(&mut m);
    let eventos = esperar_eventos(&m, |e| e.contains(&EventoMotor::ColaTerminada));
    let inicios: Vec<_> = eventos
        .iter()
        .filter_map(|e| match e {
            EventoMotor::PistaEmpieza { ficha } => Some(*ficha),
            _ => None,
        })
        .collect();
    assert_eq!(inicios, [1, 2]);
    let _ = std::fs::remove_dir_all(dir);
}
