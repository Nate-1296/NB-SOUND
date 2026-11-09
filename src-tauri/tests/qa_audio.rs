//! Medidas de las pruebas finales de audio.
//!
//! El guion de `scripts/qa/audio-qa.sh` graba el monitor de un sumidero nulo y
//! llama a estas pruebas ignoradas. Se leen las muestras reales de la salida del
//! motor, no una renderización paralela, para que la medida incluya el limitador,
//! el ecualizador y la normalización.

use std::env;
use std::fs::File;
use std::path::{Path, PathBuf};

use ebur128::{EbuR128, Mode};
use rusqlite::{params, Connection};
use serde_json::{json, Value};
use symphonia::core::codecs::audio::AudioDecoderOptions;
use symphonia::core::codecs::CodecParameters;
use symphonia::core::errors::Error;
use symphonia::core::formats::probe::Hint;
use symphonia::core::formats::{FormatOptions, TrackType};
use symphonia::core::io::MediaSourceStream;
use symphonia::core::meta::MetadataOptions;

const SILENCIO_DIGITAL: f32 = 1e-7;
const HUECO_MINIMO_SEG: f64 = 0.005;

struct Grabacion {
    tasa: u32,
    canales: usize,
    muestras: Vec<f32>,
}

#[derive(Debug, Clone)]
struct Silencio {
    inicio_seg: f64,
    duracion_seg: f64,
}

#[derive(Debug)]
struct Discontinuidad {
    posicion_seg: f64,
    salto: f32,
    umbral: f32,
}

fn variable(nombre: &str) -> String {
    env::var(nombre).unwrap_or_else(|_| panic!("falta {nombre}"))
}

fn ruta_de(nombre: &str) -> PathBuf {
    PathBuf::from(variable(nombre))
}

fn cargar(ruta: &Path) -> Grabacion {
    let archivo =
        File::open(ruta).unwrap_or_else(|e| panic!("no se puede abrir {}: {e}", ruta.display()));
    let fuente = MediaSourceStream::new(Box::new(archivo), Default::default());
    let mut pista = Hint::new();
    if let Some(extension) = ruta.extension().and_then(|e| e.to_str()) {
        pista.with_extension(extension);
    }
    let lector = symphonia::default::get_probe()
        .probe(
            &pista,
            fuente,
            FormatOptions::default(),
            MetadataOptions::default(),
        )
        .unwrap_or_else(|e| panic!("formato no reconocido en {}: {e}", ruta.display()));
    let pista = lector
        .first_track_known_codec(TrackType::Audio)
        .unwrap_or_else(|| panic!("{} no tiene audio", ruta.display()))
        .clone();
    let Some(CodecParameters::Audio(parametros)) = pista.codec_params.clone() else {
        panic!("{} no tiene parámetros de audio", ruta.display());
    };
    let tasa = parametros.sample_rate.unwrap_or(44_100);
    let mut lector = lector;
    let mut decodificador = symphonia::default::get_codecs()
        .make_audio_decoder(&parametros, &AudioDecoderOptions::default().gapless(true))
        .unwrap_or_else(|e| panic!("códec no disponible para {}: {e}", ruta.display()));
    let mut muestras = Vec::new();
    loop {
        let paquete = match lector.next_packet() {
            Ok(Some(paquete)) => paquete,
            Ok(None) | Err(Error::ResetRequired) => break,
            Err(Error::IoError(e)) if e.kind() == std::io::ErrorKind::UnexpectedEof => break,
            Err(e) => panic!("no se puede leer {}: {e}", ruta.display()),
        };
        if paquete.track_id != pista.id {
            continue;
        }
        match decodificador.decode(&paquete) {
            Ok(audio) => {
                // El búfer de Symphonia describe un solo paquete. Acumularlo en
                // `muestras` sin uno intermedio dejaría únicamente el último.
                let mut decodificado = Vec::new();
                audio.copy_to_vec_interleaved(&mut decodificado);
                muestras.extend_from_slice(&decodificado);
            }
            Err(Error::DecodeError(_)) => continue,
            Err(e) => panic!("no se puede decodificar {}: {e}", ruta.display()),
        }
    }
    assert!(!muestras.is_empty(), "{} no tiene muestras", ruta.display());
    let canales = decodificador
        .codec_params()
        .channels
        .as_ref()
        .map_or(2, |canales| canales.count())
        .max(1);
    Grabacion {
        tasa,
        canales,
        muestras,
    }
}

fn frames(g: &Grabacion) -> usize {
    g.muestras.len() / g.canales
}

fn duracion(g: &Grabacion) -> f64 {
    frames(g) as f64 / f64::from(g.tasa)
}

fn frame_es_silencio(g: &Grabacion, frame: usize) -> bool {
    let desde = frame * g.canales;
    g.muestras[desde..desde + g.canales]
        .iter()
        .all(|m| m.abs() <= SILENCIO_DIGITAL)
}

fn silencios(g: &Grabacion) -> Vec<Silencio> {
    let mut encontrados = Vec::new();
    let mut inicio = None;
    for frame in 0..frames(g) {
        match (inicio, frame_es_silencio(g, frame)) {
            (None, true) => inicio = Some(frame),
            (Some(desde), false) => {
                encontrados.push(Silencio {
                    inicio_seg: desde as f64 / f64::from(g.tasa),
                    duracion_seg: (frame - desde) as f64 / f64::from(g.tasa),
                });
                inicio = None;
            }
            _ => {}
        }
    }
    if let Some(desde) = inicio {
        encontrados.push(Silencio {
            inicio_seg: desde as f64 / f64::from(g.tasa),
            duracion_seg: (frames(g) - desde) as f64 / f64::from(g.tasa),
        });
    }
    encontrados
}

fn silencios_interiores(g: &Grabacion) -> Vec<Silencio> {
    let total = duracion(g);
    silencios(g)
        .into_iter()
        .filter(|s| s.inicio_seg > 1e-6 && s.inicio_seg + s.duracion_seg < total - 1e-6)
        .filter(|s| s.duracion_seg > HUECO_MINIMO_SEG)
        .collect()
}

/// Saltos que no explica ni la frecuencia local ni una rampa. El umbral se
/// calcula sobre la media móvil de la derivada: un clic aislado de 0,1 supera
/// con holgura a un tono o a ruido, mientras que una rampa de 30 ms no.
fn discontinuidades(g: &Grabacion) -> Vec<Discontinuidad> {
    let n = frames(g);
    if n < 3 {
        return Vec::new();
    }
    let mut deltas = vec![0.0f32; n];
    for (frame, delta) in deltas.iter_mut().enumerate().skip(1) {
        let a = frame * g.canales;
        let b = (frame - 1) * g.canales;
        *delta = (0..g.canales)
            .map(|c| (g.muestras[a + c] - g.muestras[b + c]).abs())
            .fold(0.0, f32::max);
    }
    let mut prefijo = vec![0.0f64; n + 1];
    for i in 0..n {
        prefijo[i + 1] = prefijo[i] + f64::from(deltas[i]);
    }
    let mut encontradas = Vec::new();
    let mut ultima_frame = None;
    for (frame, delta) in deltas.iter().enumerate().skip(1) {
        let desde = frame.saturating_sub(64);
        let hasta = (frame + 65).min(n);
        let media = ((prefijo[hasta] - prefijo[desde]) / (hasta - desde) as f64) as f32;
        let umbral = (media * 12.0).max(0.08);
        if *delta > umbral
            && ultima_frame.is_none_or(|anterior| frame.saturating_sub(anterior) > 96)
        {
            encontradas.push(Discontinuidad {
                posicion_seg: frame as f64 / f64::from(g.tasa),
                salto: *delta,
                umbral,
            });
            ultima_frame = Some(frame);
        }
    }
    encontradas
}

fn pico(g: &Grabacion) -> f32 {
    g.muestras
        .iter()
        .filter(|m| m.is_finite())
        .map(|m| m.abs())
        .fold(0.0, f32::max)
}

fn muestras_recortadas(g: &Grabacion) -> usize {
    g.muestras
        .iter()
        .filter(|m| !m.is_finite() || m.abs() >= 0.999_99)
        .count()
}

fn sonoridad(g: &Grabacion) -> (Option<f64>, Option<f64>) {
    let Ok(mut medidor) = EbuR128::new(
        u32::try_from(g.canales).expect("canales válidos"),
        g.tasa,
        Mode::I | Mode::TRUE_PEAK,
    ) else {
        return (None, None);
    };
    if medidor.add_frames_f32(&g.muestras).is_err() {
        return (None, None);
    }
    let lufs = medidor.loudness_global().ok().filter(|l| l.is_finite());
    let pico_verdadero = (0..g.canales)
        .filter_map(|c| medidor.true_peak(u32::try_from(c).ok()?).ok())
        .fold(0.0f64, f64::max);
    (
        lufs,
        (pico_verdadero > 0.0).then(|| 20.0 * pico_verdadero.log10()),
    )
}

fn informar(caso: &str, datos: Value) {
    println!("INFORME_QA {}", json!({ "caso": caso, "datos": datos }));
}

fn lista_silencios(silencios: &[Silencio]) -> Vec<Value> {
    silencios
        .iter()
        .map(|s| {
            json!({
                "inicioSeg": s.inicio_seg,
                "duracionMs": s.duracion_seg * 1000.0,
            })
        })
        .collect()
}

fn lista_discontinuidades(discontinuidades: &[Discontinuidad]) -> Vec<Value> {
    discontinuidades
        .iter()
        .map(|d| {
            json!({
                "posicionSeg": d.posicion_seg,
                "salto": d.salto,
                "umbral": d.umbral,
            })
        })
        .collect()
}

#[test]
fn los_ceros_del_tono_no_parten_los_segmentos_activos() {
    let tasa = 48_000u32;
    let mut muestras = Vec::new();
    for frame in 0..tasa * 2 + tasa / 10 {
        let activo = !(tasa..tasa + tasa / 10).contains(&frame);
        let valor = if activo {
            0.35 * (2.0 * std::f32::consts::PI * 440.0 * frame as f32 / tasa as f32).sin()
        } else {
            0.0
        };
        muestras.extend_from_slice(&[valor, valor]);
    }
    let grabacion = Grabacion {
        tasa,
        canales: 2,
        muestras,
    };
    let segmentos = segmentos_activos(&grabacion);
    assert_eq!(segmentos.len(), 2, "{segmentos:?}");
}

#[test]
fn la_ventana_de_la_fuente_incluye_silencios_internos() {
    let tasa = 1_000u32;
    let mut muestras = vec![0.5; 2_000];
    muestras[200..300].fill(0.0);
    muestras[1_800..1_900].fill(0.0);
    let grabacion = Grabacion {
        tasa,
        canales: 1,
        muestras,
    };
    assert!((silencio_en_ventana(&grabacion, 0.0, 0.5) - 0.1).abs() < 1e-9);
    assert!((silencio_en_ventana(&grabacion, 1.5, 2.0) - 0.1).abs() < 1e-9);
}

fn fuentes_del_manifiesto() -> Vec<PathBuf> {
    let Ok(ruta) = env::var("NB_QA_FUENTES") else {
        return Vec::new();
    };
    std::fs::read_to_string(&ruta)
        .unwrap_or_else(|e| panic!("no se puede leer el manifiesto {ruta}: {e}"))
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(PathBuf::from)
        .collect()
}

fn silencio_de_borde(g: &Grabacion, principio: bool) -> f64 {
    let n = frames(g);
    if principio {
        (0..n)
            .take_while(|frame| frame_es_silencio(g, *frame))
            .count() as f64
            / f64::from(g.tasa)
    } else {
        (0..n)
            .rev()
            .take_while(|frame| frame_es_silencio(g, *frame))
            .count() as f64
            / f64::from(g.tasa)
    }
}

fn silencio_en_ventana(g: &Grabacion, desde_seg: f64, hasta_seg: f64) -> f64 {
    silencios(g)
        .iter()
        .map(|silencio| {
            let desde = silencio.inicio_seg.max(desde_seg);
            let hasta = (silencio.inicio_seg + silencio.duracion_seg).min(hasta_seg);
            (hasta - desde).max(0.0)
        })
        .sum()
}

fn grabaciones_de_album() -> Vec<PathBuf> {
    if let Ok(carpeta) = env::var("NB_QA_WAV_DIR") {
        let mut archivos: Vec<PathBuf> = std::fs::read_dir(&carpeta)
            .unwrap_or_else(|e| panic!("no se puede abrir {carpeta}: {e}"))
            .filter_map(Result::ok)
            .map(|entrada| entrada.path())
            .filter(|ruta| ruta.extension().is_some_and(|extension| extension == "wav"))
            .collect();
        archivos.sort();
        archivos
    } else {
        vec![ruta_de("NB_QA_WAV")]
    }
}

#[test]
#[ignore = "lo ejecuta scripts/qa/audio-qa.sh sobre una grabación del sumidero"]
fn un_album_no_anade_silencio_entre_pistas() {
    let archivos = grabaciones_de_album();
    let fuentes = fuentes_del_manifiesto();
    let decodificadas: Vec<Grabacion> = fuentes.iter().map(|ruta| cargar(ruta)).collect();
    let por_transicion = env::var("NB_QA_WAV_DIR").is_ok();
    let esperados: Vec<f64> = decodificadas
        .windows(2)
        .map(|par| {
            if por_transicion {
                let anterior = &par[0];
                let siguiente = &par[1];
                silencio_en_ventana(
                    anterior,
                    (duracion(anterior) - 2.5).max(0.0),
                    duracion(anterior),
                ) + silencio_en_ventana(siguiente, 0.0, 3.0)
            } else {
                silencio_de_borde(&par[0], false) + silencio_de_borde(&par[1], true)
            }
        })
        .collect();
    assert_eq!(
        archivos.len(),
        esperados.len(),
        "hay una grabación por cada transición"
    );
    let mut total_grabado = 0.0f64;
    let total_fuente: f64 = esperados.iter().sum();
    let mut exceso_maximo_ms = 0.0f64;
    let mut detalle = Vec::new();
    for (indice, (archivo, esperado)) in archivos.iter().zip(&esperados).enumerate() {
        let grabacion = cargar(archivo);
        assert!(
            duracion(&grabacion) > 1.0,
            "la transición {indice} dura solo {:.3} s",
            duracion(&grabacion)
        );
        assert!(
            pico(&grabacion) > 1e-4,
            "la transición {indice} no contiene señal audible"
        );
        let huecos = silencios_interiores(&grabacion);
        let grabado: f64 = huecos.iter().map(|h| h.duracion_seg).sum();
        let maximo_grabado = huecos.iter().map(|h| h.duracion_seg).fold(0.0f64, f64::max);
        let exceso_transicion_ms = ((grabado - esperado).max(0.0)) * 1000.0;
        let exceso_hueco_ms = ((maximo_grabado - esperado).max(0.0)) * 1000.0;
        total_grabado += grabado;
        exceso_maximo_ms = exceso_maximo_ms.max(exceso_transicion_ms.max(exceso_hueco_ms));
        detalle.push(json!({
            "indice": indice,
            "archivo": archivo,
            "duracionSeg": duracion(&grabacion),
            "huecosMs": lista_silencios(&huecos),
            "huecoFuenteMs": esperado * 1000.0,
            "excesoMs": exceso_transicion_ms,
            "picoDbfs": 20.0 * pico(&grabacion).max(f32::MIN_POSITIVE).log10(),
        }));
    }
    let exceso_total_ms = ((total_grabado - total_fuente).max(0.0)) * 1000.0;
    informar(
        "album",
        json!({
            "transiciones": detalle,
            "transicionesMedidas": archivos.len(),
            "huecosGrabadosMs": total_grabado * 1000.0,
            "huecosFuenteMs": total_fuente * 1000.0,
            "excesoTotalMs": exceso_total_ms,
            "excesoMaximoPorTransicionMs": exceso_maximo_ms,
        }),
    );
    assert!(
        exceso_maximo_ms <= 5.0,
        "una transición añadió {exceso_maximo_ms:.3} ms de silencio"
    );
}

fn segmentos_activos(g: &Grabacion) -> Vec<(usize, usize)> {
    let n = frames(g);
    let minimo = (f64::from(g.tasa) * 0.05) as usize;
    let maximo_hueco = (f64::from(g.tasa) * 0.02) as usize;
    let mut segmentos = Vec::new();
    let mut inicio = None;
    let mut anterior = 0;
    for frame in 0..n {
        if frame_es_silencio(g, frame) {
            continue;
        }
        match inicio {
            None => inicio = Some(frame),
            Some(desde) if frame.saturating_sub(anterior) > maximo_hueco => {
                if anterior + 1 - desde >= minimo {
                    segmentos.push((desde, anterior + 1));
                }
                inicio = Some(frame);
            }
            Some(_) => {}
        }
        anterior = frame;
    }
    if let Some(desde) = inicio.filter(|desde| anterior + 1 - desde >= minimo) {
        segmentos.push((desde, anterior + 1));
    }
    segmentos
}

fn frecuencia_del_segmento(g: &Grabacion, desde: usize, hasta: usize) -> Option<f64> {
    let largo = hasta.saturating_sub(desde);
    let margen = ((f64::from(g.tasa) * 0.25) as usize).min(largo / 4);
    let desde = (desde + margen).min(hasta);
    let hasta = hasta.saturating_sub(margen).max(desde + 1);
    let muestra = |frame: usize| g.muestras[frame * g.canales];
    let mut cruces = 0usize;
    for frame in desde + 1..hasta {
        if muestra(frame - 1) <= 0.0 && muestra(frame) > 0.0 {
            cruces += 1;
        }
    }
    let segundos = (hasta - desde) as f64 / f64::from(g.tasa);
    (cruces > 0).then(|| cruces as f64 / segundos)
}

#[test]
#[ignore = "lo ejecuta scripts/qa/audio-qa.sh sobre una grabación del sumidero"]
fn buscar_y_pausar_no_dejan_discontinuidades() {
    let wav = ruta_de("NB_QA_WAV");
    let grabacion = cargar(&wav);
    assert!(
        duracion(&grabacion) > 1.0,
        "la grabación dura solo {:.3} s",
        duracion(&grabacion)
    );
    let segmentos = segmentos_activos(&grabacion);
    let frecuencias: Vec<Option<f64>> = segmentos
        .iter()
        .map(|(desde, hasta)| frecuencia_del_segmento(&grabacion, *desde, *hasta))
        .collect();
    let discontinuidades = discontinuidades(&grabacion);
    informar(
        "busqueda_pausa",
        json!({
            "archivo": wav,
            "duracionSeg": duracion(&grabacion),
            "frames": frames(&grabacion),
            "canales": grabacion.canales,
            "picoDbfs": 20.0 * pico(&grabacion).max(f32::MIN_POSITIVE).log10(),
            "segmentosActivos": segmentos
                .iter()
                .zip(&frecuencias)
                .map(|((desde, hasta), frecuencia)| json!({
                    "inicioSeg": *desde as f64 / f64::from(grabacion.tasa),
                    "finSeg": *hasta as f64 / f64::from(grabacion.tasa),
                    "frecuenciaHz": frecuencia,
                }))
                .collect::<Vec<_>>(),
            "discontinuidades": lista_discontinuidades(&discontinuidades),
            "sonoridadLufs": sonoridad(&grabacion).0,
        }),
    );
    assert_eq!(
        segmentos.len(),
        2,
        "se esperaban dos segmentos activos, separados por la pausa"
    );
    for frecuencia in &frecuencias {
        let frecuencia = frecuencia.expect("el segmento debe tener cruces por cero");
        assert!(
            (1_724.0..=1_796.0).contains(&frecuencia),
            "la búsqueda cayó en {frecuencia:.1} Hz en vez de 1760 Hz"
        );
    }
    assert!(
        discontinuidades.is_empty(),
        "discontinuidades: {discontinuidades:?}"
    );
}

#[test]
#[ignore = "lo ejecuta scripts/qa/audio-qa.sh sobre las grabaciones del sumidero"]
fn las_dieciocho_preselecciones_no_recortan() {
    let carpeta = ruta_de("NB_QA_EQ_DIR");
    let mut archivos: Vec<PathBuf> = std::fs::read_dir(&carpeta)
        .unwrap_or_else(|e| panic!("no se puede abrir {}: {e}", carpeta.display()))
        .filter_map(Result::ok)
        .map(|e| e.path())
        .filter(|p| p.extension().is_some_and(|e| e == "wav"))
        .collect();
    archivos.sort();
    assert_eq!(archivos.len(), 18, "faltan grabaciones de preselecciones");
    let mut resultados = Vec::new();
    let mut maximo_pico = 0.0f32;
    let mut total_recortadas = 0usize;
    for (indice, archivo) in archivos.iter().enumerate() {
        let grabacion = cargar(archivo);
        assert!(
            duracion(&grabacion) > 1.0,
            "la preselección {indice} grabó solo {:.3} s",
            duracion(&grabacion)
        );
        let pico = pico(&grabacion);
        let recortadas = muestras_recortadas(&grabacion);
        let (lufs, pico_verdadero) = sonoridad(&grabacion);
        assert_eq!(
            recortadas, 0,
            "la preselección {} tiene {recortadas} muestras recortadas",
            indice
        );
        assert!(pico < 1.0, "la preselección {indice} llegó al techo");
        maximo_pico = maximo_pico.max(pico);
        total_recortadas += recortadas;
        resultados.push(json!({
            "indice": indice,
            "archivo": archivo,
            "picoDbfs": 20.0 * pico.max(f32::MIN_POSITIVE).log10(),
            "picoVerdaderoDbtp": pico_verdadero,
            "sonoridadLufs": lufs,
            "muestrasRecortadas": recortadas,
        }));
    }
    informar(
        "ecualizador",
        json!({
            "preselecciones": resultados,
            "picoMaximoDbfs": 20.0 * maximo_pico.max(f32::MIN_POSITIVE).log10(),
            "muestrasRecortadas": total_recortadas,
        }),
    );
}

#[test]
#[ignore = "lo ejecuta scripts/qa/audio-qa.sh sobre las grabaciones del sumidero"]
fn la_normalizacion_iguala_las_pistas() {
    let alta = cargar(&ruta_de("NB_QA_ALTA_WAV"));
    let baja = cargar(&ruta_de("NB_QA_BAJA_WAV"));
    assert!(duracion(&alta) > 1.0, "la pista alta grabó muy poco");
    assert!(duracion(&baja) > 1.0, "la pista baja grabó muy poco");
    let (lufs_alta, pico_alta) = sonoridad(&alta);
    let (lufs_baja, pico_baja) = sonoridad(&baja);
    let lufs_alta = lufs_alta.expect("sonoridad de la pista alta");
    let lufs_baja = lufs_baja.expect("sonoridad de la pista baja");
    let diferencia = (lufs_alta - lufs_baja).abs();
    assert!(
        diferencia < 2.0,
        "las pistas normalizadas difieren {diferencia:.3} LU"
    );
    informar(
        "normalizacion",
        json!({
            "alta": {
                "archivo": ruta_de("NB_QA_ALTA_WAV"),
                "lufs": lufs_alta,
                "picoVerdaderoDbtp": pico_alta,
                "picoDbfs": 20.0 * pico(&alta).max(f32::MIN_POSITIVE).log10(),
            },
            "baja": {
                "archivo": ruta_de("NB_QA_BAJA_WAV"),
                "lufs": lufs_baja,
                "picoVerdaderoDbtp": pico_baja,
                "picoDbfs": 20.0 * pico(&baja).max(f32::MIN_POSITIVE).log10(),
            },
            "diferenciaLu": diferencia,
        }),
    );
}

#[test]
#[ignore = "lo ejecuta scripts/qa/audio-qa.sh sobre las grabaciones del sumidero"]
fn una_reproduccion_continua_no_tiene_huecos() {
    let wav = ruta_de("NB_QA_WAV");
    let grabacion = cargar(&wav);
    assert!(
        duracion(&grabacion) > 1.0,
        "la grabación es demasiado corta"
    );
    assert!(pico(&grabacion) > 1e-4, "la grabación no contiene señal");
    let huecos = silencios_interiores(&grabacion);
    assert!(huecos.is_empty(), "la reproducción tuvo huecos: {huecos:?}");
    informar(
        "reproduccion_continua",
        json!({
            "archivo": wav,
            "duracionSeg": duracion(&grabacion),
            "huecosMs": lista_silencios(&huecos),
            "discontinuidades": lista_discontinuidades(&discontinuidades(&grabacion)),
            "picoDbfs": 20.0 * pico(&grabacion).max(f32::MIN_POSITIVE).log10(),
            "sonoridadLufs": sonoridad(&grabacion).0,
        }),
    );
}

#[test]
#[ignore = "lo ejecuta scripts/qa/audio-qa.sh sobre las grabaciones del sumidero"]
fn la_normalizacion_entra_desde_la_siguiente_pista() {
    let antes = cargar(&ruta_de("NB_QA_ANTES_WAV"));
    let despues = cargar(&ruta_de("NB_QA_DESPUES_WAV"));
    let siguiente = cargar(&ruta_de("NB_QA_SIGUIENTE_WAV"));
    let (lufs_antes, _) = sonoridad(&antes);
    let (lufs_despues, _) = sonoridad(&despues);
    let (lufs_siguiente, _) = sonoridad(&siguiente);
    let antes = lufs_antes.expect("sonoridad antes del cambio");
    let despues = lufs_despues.expect("sonoridad después del cambio");
    let siguiente = lufs_siguiente.expect("sonoridad de la pista siguiente");
    assert!(
        (antes - despues).abs() < 1.0,
        "la pista actual cambió {:.3} LU al activar la normalización",
        (antes - despues).abs()
    );
    assert!(
        (siguiente - despues).abs() < 2.0,
        "la pista siguiente quedó a {:.3} LU de la anterior",
        (siguiente - despues).abs()
    );
    informar(
        "normalizacion_siguiente",
        json!({
            "actualAntesLufs": antes,
            "actualDespuesLufs": despues,
            "siguienteLufs": siguiente,
            "cambioActualLu": (antes - despues).abs(),
            "diferenciaSiguienteLu": (siguiente - despues).abs(),
        }),
    );
}

#[test]
#[ignore = "lo ejecuta scripts/qa/audio-qa.sh después de insertar las pistas sintéticas"]
fn prepara_la_sonoridad_de_las_pistas_sinteticas() {
    let db = PathBuf::from(variable("NB_QA_DB"));
    let alta = ruta_de("NB_QA_ALTA_FLAC");
    let baja = ruta_de("NB_QA_BAJA_FLAC");
    let id_alta: i64 = variable("NB_QA_ID_ALTA").parse().expect("id alta");
    let id_baja: i64 = variable("NB_QA_ID_BAJA").parse().expect("id baja");
    let conexion = Connection::open(&db).expect("abre la copia de la base");
    let mut resultado = Vec::new();
    for (id, ruta) in [(id_alta, &alta), (id_baja, &baja)] {
        let medida = nb_sound_lib::audio::sonoridad::medir(ruta).expect("mide la pista sintética");
        let sonoridad = medida
            .sonoridad
            .expect("la pista sintética tiene sonoridad");
        conexion
            .execute(
                "INSERT INTO sonoridad (pista_id, lufs, pico_verdadero, rango)
                 VALUES (?1, ?2, ?3, ?4)
                 ON CONFLICT (pista_id) DO UPDATE SET
                     lufs = excluded.lufs,
                     pico_verdadero = excluded.pico_verdadero,
                     rango = excluded.rango,
                     medida_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
                params![
                    id,
                    sonoridad.lufs,
                    sonoridad.pico_verdadero,
                    sonoridad.rango
                ],
            )
            .expect("guarda la sonoridad en la copia");
        resultado.push(json!({
            "id": id,
            "archivo": ruta,
            "lufs": sonoridad.lufs,
            "picoVerdaderoDbtp": sonoridad.pico_verdadero,
        }));
    }
    informar("preparacion_sonoridad", json!({ "pistas": resultado }));
}

/// Envolvente en tramos de 10 ms (RMS de todos los canales), que no depende de la
/// tasa: la grabación sale a 48 kHz y la fuente puede estar a 44,1.
fn envolvente(g: &Grabacion, desde_seg: f64, segundos: f64) -> Vec<f64> {
    let paso = (f64::from(g.tasa) * 0.01) as usize;
    let inicio = (desde_seg * f64::from(g.tasa)) as usize;
    let n = (segundos / 0.01) as usize;
    (0..n)
        .map(|k| {
            let a = (inicio + k * paso) * g.canales;
            let b = (a + paso * g.canales).min(g.muestras.len());
            if a >= b {
                return 0.0;
            }
            let suma: f64 = g.muestras[a..b].iter().map(|m| f64::from(*m).powi(2)).sum();
            (suma / (b - a) as f64).sqrt()
        })
        .collect()
}

fn correlacion(a: &[f64], b: &[f64]) -> f64 {
    let n = a.len().min(b.len()) as f64;
    let (ma, mb) = (a.iter().sum::<f64>() / n, b.iter().sum::<f64>() / n);
    let (mut c, mut va, mut vb) = (0.0, 0.0, 0.0);
    for (x, y) in a.iter().zip(b) {
        c += (x - ma) * (y - mb);
        va += (x - ma).powi(2);
        vb += (y - mb).powi(2);
    }
    c / (va.sqrt() * vb.sqrt()).max(1e-12)
}

/// Dónde de la fuente encaja mejor lo grabado, en segundos, y con qué correlación.
/// Se recorre la canción entera: una canción repite partes, así que comparar
/// solo con dos o tres sitios no distingue bien.
fn mejor_encaje(grabacion: &Grabacion, fuente: &Grabacion) -> (f64, f64) {
    let tomado = envolvente(grabacion, 0.3, 3.0);
    let toda = envolvente(fuente, 0.0, duracion(fuente));
    let n = tomado.len();
    (0..toda.len().saturating_sub(n))
        .map(|k| (k as f64 * 0.01, correlacion(&tomado, &toda[k..k + n])))
        .fold((0.0, f64::MIN), |m, x| if x.1 > m.1 { x } else { m })
}

#[test]
#[ignore = "lo ejecuta scripts/qa/ui-qa.sh fase6 sobre la grabación de un fragmento"]
fn el_fragmento_de_a_ciegas_empieza_en_el_treinta_por_ciento() {
    let grabacion = cargar(&ruta_de("NB_QA_WAV"));
    let fuente = cargar(&ruta_de("NB_QA_FUENTE"));
    let desde: f64 = variable("NB_QA_DESDE").parse().expect("NB_QA_DESDE");
    let (donde, correlacion) = mejor_encaje(&grabacion, &fuente);
    // Lo que cuenta es dónde encaja mejor en toda la canción; la correlación no
    // llega a 1 porque el fragmento entra con un fundido y pasa por el limitador.
    // Lo grabado empieza 0,3 s dentro de la grabación, que a su vez arranca un
    // poco después que el fragmento.
    let retraso = donde - 0.3 - desde;
    assert!(
        correlacion > 0.5 && (-0.2..1.5).contains(&retraso),
        "encaja en {donde:.2} s con {correlacion:.3}; el fragmento debía empezar en {desde:.2} s"
    );
    informar(
        "fragmento_a_ciegas",
        json!({ "desdeSeg": desde, "encajaEnSeg": donde, "retrasoSeg": retraso, "correlacion": correlacion }),
    );
}

/// Sonoridad a corto plazo (ventanas de 3 s, EBU R128) cada 100 ms.
fn sonoridad_corta(g: &Grabacion) -> Vec<f64> {
    let mut medidor =
        EbuR128::new(u32::try_from(g.canales).expect("canales"), g.tasa, Mode::S).expect("medidor");
    let paso = (g.tasa / 10) as usize * g.canales;
    g.muestras
        .chunks(paso)
        .map(|trozo| {
            medidor.add_frames_f32(trozo).expect("tramo");
            medidor.loudness_shortterm().unwrap_or(f64::NEG_INFINITY)
        })
        .collect()
}

fn mediana(mut v: Vec<f64>) -> f64 {
    v.retain(|x| x.is_finite());
    if v.is_empty() {
        return f64::NEG_INFINITY;
    }
    v.sort_by(f64::total_cmp);
    v[v.len() / 2]
}

#[test]
#[ignore = "lo ejecuta scripts/qa/ui-qa.sh fase6 sobre la grabación de una sesión del DJ"]
fn las_mezclas_del_dj_no_se_hunden_ni_saltan() {
    let grabacion = cargar(&ruta_de("NB_QA_WAV"));
    let mezclas: Vec<(f64, f64, String)> =
        serde_json::from_str(&std::fs::read_to_string(ruta_de("NB_QA_MEZCLAS")).expect("mezclas"))
            .expect("json de mezclas");
    let corta = sonoridad_corta(&grabacion);
    let en = |seg: f64| ((seg * 10.0).max(0.0) as usize).min(corta.len());
    let huecos = silencios_interiores(&grabacion);
    let clics = discontinuidades(&grabacion);
    let mut informe = Vec::new();
    let mut fallos = Vec::new();
    for (inicio, fin, tecnica) in &mezclas {
        // Sin las primeras 3 s de cada lado: la ventana de 3 s arrastra lo anterior.
        let antes = mediana(corta[en(inicio - 13.0)..en(inicio - 3.0)].to_vec());
        let despues = mediana(corta[en(fin + 3.0)..en(fin + 13.0)].to_vec());
        let durante: Vec<f64> = corta[en(*inicio)..en(fin + 3.0)]
            .iter()
            .copied()
            .filter(|x| x.is_finite())
            .collect();
        let minimo = durante.iter().copied().fold(f64::INFINITY, f64::min);
        let maximo = durante.iter().copied().fold(f64::NEG_INFINITY, f64::max);
        let suelo = antes.min(despues);
        let techo = antes.max(despues);
        let hundimiento = suelo - minimo;
        let subida = maximo - techo;
        let huecos_aqui = huecos
            .iter()
            .filter(|h| h.inicio_seg + h.duracion_seg > inicio - 2.0 && h.inicio_seg < fin + 2.0)
            .count();
        let clics_aqui = clics
            .iter()
            .filter(|c| c.posicion_seg > inicio - 2.0 && c.posicion_seg < fin + 2.0)
            .count();
        if hundimiento > 8.0 || subida > 4.0 || huecos_aqui > 0 || clics_aqui > 0 {
            fallos.push(format!(
                "{tecnica} en {inicio:.1} s: hundimiento {hundimiento:.1} LU, subida {subida:.1} LU, \
                 {huecos_aqui} huecos, {clics_aqui} clics"
            ));
        }
        informe.push(json!({ "tecnica": tecnica, "inicioSeg": inicio, "finSeg": fin,
            "antesLufs": antes, "despuesLufs": despues, "hundimientoLu": hundimiento, "subidaLu": subida }));
    }
    assert!(!mezclas.is_empty(), "no hubo mezclas");
    assert!(fallos.is_empty(), "{fallos:#?}");
    informar(
        "mezclas_dj",
        json!({ "duracionSeg": duracion(&grabacion), "mezclas": informe,
                "discontinuidadesTotales": clics.len(), "huecosTotales": huecos.len() }),
    );
}

#[test]
#[ignore = "lo ejecuta scripts/qa/ui-qa.sh fase8 con la forma de onda de una pista"]
fn la_forma_de_onda_sigue_al_audio() {
    let fuente = cargar(&ruta_de("NB_QA_FUENTE"));
    let picos: Vec<f64> = serde_json::from_str(&variable("NB_QA_PICOS")).expect("picos");
    assert_eq!(
        picos.len(),
        1000,
        "la forma de onda tiene {} tramos",
        picos.len()
    );
    // Lo que la vista debería dibujar: el máximo de cada milésima de la canción.
    let n = frames(&fuente);
    let reales: Vec<f64> = (0..1000)
        .map(|k| {
            let (a, b) = (
                k * n / 1000 * fuente.canales,
                (k + 1) * n / 1000 * fuente.canales,
            );
            fuente.muestras[a..b.min(fuente.muestras.len())]
                .iter()
                .map(|m| f64::from(m.abs()))
                .fold(0.0, f64::max)
        })
        .collect();
    let c = correlacion(&picos, &reales);
    assert!(c > 0.9, "la forma de onda se parece {c:.3} a la canción");
    informar("forma_de_onda", json!({ "correlacion": c }));
}
