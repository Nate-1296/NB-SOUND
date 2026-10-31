//! El karaoke: separar la voz con `htdemucs` en ONNX (F5.2.1, ADR-002).
//!
//! El algoritmo es el de `_separar_por_segmentos` de la V1
//! (`legado/servicios/karaoke/separador.py`), el mismo que midió F0.4.2 contra
//! PyTorch: la mezcla se normaliza por su media y su desviación, se recorre en
//! segmentos de 7,8 s (la entrada fija del grafo exportado) con un 25 % de
//! solapamiento y ventana triangular, y se deshace la normalización. El
//! instrumental es la mezcla menos la voz, como en la V1. Solo se acumula la voz:
//! los otros tres stems no se usan y ocuparían otro tanto de memoria.
//!
//! **Memoria (P8).** F0.4.2 vio a ONNX Runtime llegar a 9 GB con su configuración
//! por defecto. Aquí la sesión se crea una vez por pista, sin el *arena* del
//! proveedor de CPU ni el patrón de memoria, y con la mitad de los núcleos: el
//! audio corre en su propio hilo de tiempo real (P1) y la ventana no se nota.
//!
//! **Formato (P14).** El instrumental se guarda como WAV de 16 bits: sin `ffmpeg`
//! (enmienda de ADR-006) no hay codificador de MP3, y el teléfono reproduce WAV con
//! seguridad, cosa que con FLAC está sin comprobar (P7). Ocupa unas cuatro veces
//! lo que el MP3 de la V1.

use std::path::{Path, PathBuf};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, Sender};
use std::sync::{Arc, Mutex, PoisonError};
use std::time::Duration;

use rubato::{FftFixedIn, Resampler};
use rusqlite::{params, OptionalExtension};
use serde::Serialize;
use ts_rs::TS;

use crate::agregados::{self, IdAgregado};
use crate::audio::decodificador::Decodificador;
use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};
use crate::paths::Rutas;
use crate::reproductor::persistencia;

/// La tasa del modelo.
pub const TASA: u32 = 44_100;
/// 7,8 s a 44,1 kHz: la entrada fija del grafo exportado.
pub const SEGMENTO: usize = 343_980;
/// El modelo dentro del agregado.
pub const ARCHIVO_MODELO: &str = "htdemucs.onnx";
/// Lo que se apunta en `stems.modelo`.
pub const MODELO: &str = "htdemucs-onnx-fp16";
/// El índice de la voz entre los cuatro stems (batería, bajo, otros, voz).
const VOZ: usize = 3;

// --- El algoritmo ---------------------------------------------------------------------

/// La ventana triangular de demucs, normalizada a 1 en su máximo.
fn ventana() -> Vec<f32> {
    let mitad = SEGMENTO / 2;
    let mut w: Vec<f32> = (1..=mitad)
        .chain((1..=SEGMENTO - mitad).rev())
        .map(|v| v as f32)
        .collect();
    let max = w.iter().fold(0.0f32, |m, &v| m.max(v));
    for v in &mut w {
        *v /= max;
    }
    w
}

/// Separa la voz de una mezcla estéreo planar y devuelve el instrumental.
/// `modelo` recibe un segmento `[1, 2, SEGMENTO]` aplanado (izquierda y luego
/// derecha) y devuelve los cuatro stems `[1, 4, 2, SEGMENTO]` aplanados.
/// `seguir` recibe la fracción hecha y devuelve `false` para cancelar.
///
/// # Errors
///
/// Los de `modelo`; [`NsError::Cancelled`] si `seguir` lo pide;
/// [`NsError::Internal`] si el modelo devuelve otra forma.
pub fn separar(
    izq: &[f32],
    der: &[f32],
    modelo: &mut dyn FnMut(&[f32]) -> NsResult<Vec<f32>>,
    seguir: &mut dyn FnMut(f64) -> bool,
) -> NsResult<(Vec<f32>, Vec<f32>)> {
    let largo = izq.len().min(der.len());
    if largo == 0 {
        return Err(NsError::AudioCorrupted);
    }
    // La referencia es la media de los dos canales, como `mezcla.mean(0)`.
    let n = largo as f64;
    let media = (0..largo)
        .map(|i| f64::from(izq[i] + der[i]) * 0.5)
        .sum::<f64>()
        / n;
    // `torch.std` es la muestral.
    let varianza = (0..largo)
        .map(|i| (f64::from(izq[i] + der[i]) * 0.5 - media).powi(2))
        .sum::<f64>()
        / (n - 1.0).max(1.0);
    let desv = varianza.sqrt() + 1e-8;
    let (media, desv) = (media as f32, desv as f32);
    let peso = ventana();
    let paso = ((0.75 * SEGMENTO as f64) as usize).max(1);
    let mut voz = [vec![0.0f32; largo], vec![0.0f32; largo]];
    let mut total = vec![0.0f32; largo];
    let mut trozo = vec![0.0f32; 2 * SEGMENTO];
    let inicios: Vec<usize> = (0..largo).step_by(paso).collect();
    for (k, &inicio) in inicios.iter().enumerate() {
        if !seguir(k as f64 / inicios.len() as f64) {
            return Err(NsError::Cancelled);
        }
        let m = SEGMENTO.min(largo - inicio);
        trozo.iter_mut().for_each(|v| *v = 0.0);
        for t in 0..m {
            trozo[t] = (izq[inicio + t] - media) / desv;
            trozo[SEGMENTO + t] = (der[inicio + t] - media) / desv;
        }
        let stems = modelo(&trozo)?;
        if stems.len() != 4 * 2 * SEGMENTO {
            tracing::error!(valores = stems.len(), "el modelo devolvió otra forma");
            return Err(NsError::Internal);
        }
        for (c, v) in voz.iter_mut().enumerate() {
            let base = (VOZ * 2 + c) * SEGMENTO;
            for t in 0..m {
                v[inicio + t] += stems[base + t] * peso[t];
            }
        }
        for t in 0..m {
            total[inicio + t] += peso[t];
        }
    }
    seguir(1.0);
    let instrumental = |mezcla: &[f32], v: &[f32]| -> Vec<f32> {
        (0..largo)
            .map(|i| mezcla[i] - ((v[i] / total[i].max(1e-8)) * desv + media))
            .collect()
    };
    Ok((instrumental(izq, &voz[0]), instrumental(der, &voz[1])))
}

// --- Audio de entrada y salida ---------------------------------------------------------

/// La pista entera en estéreo planar a 44,1 kHz.
fn cargar(ruta: &Path) -> NsResult<(Vec<f32>, Vec<f32>)> {
    let mut d = Decodificador::abrir(ruta, 0.0)?;
    let origen = d.tasa;
    let mut frames = Vec::new();
    while d.leer(&mut frames, 65_536)? > 0 {}
    let izq: Vec<f32> = frames.iter().map(|f| f.left).collect();
    let der: Vec<f32> = frames.iter().map(|f| f.right).collect();
    drop(frames);
    if origen == TASA {
        return Ok((izq, der));
    }
    let trozo = 4096;
    let mut rs = FftFixedIn::<f32>::new(origen as usize, TASA as usize, trozo, 2, 2)
        .map_err(|_| NsError::Internal)?;
    let esperado = (izq.len() as f64 * f64::from(TASA) / f64::from(origen)).round() as usize;
    let (mut a, mut b) = (Vec::with_capacity(esperado), Vec::with_capacity(esperado));
    let mut i = 0;
    while i + trozo <= izq.len() {
        let out = rs
            .process(&[&izq[i..i + trozo], &der[i..i + trozo]], None)
            .map_err(|_| NsError::Internal)?;
        a.extend_from_slice(&out[0]);
        b.extend_from_slice(&out[1]);
        i += trozo;
    }
    let resto = rs
        .process_partial(Some(&[&izq[i..], &der[i..]]), None)
        .map_err(|_| NsError::Internal)?;
    a.extend_from_slice(&resto[0]);
    b.extend_from_slice(&resto[1]);
    let cola = rs
        .process_partial::<&[f32]>(None, None)
        .map_err(|_| NsError::Internal)?;
    a.extend_from_slice(&cola[0]);
    b.extend_from_slice(&cola[1]);
    let retardo = rs.output_delay();
    Ok((
        a.into_iter().skip(retardo).take(esperado).collect(),
        b.into_iter().skip(retardo).take(esperado).collect(),
    ))
}

/// WAV PCM de 16 bits, estéreo, a 44,1 kHz. Se escribe en un temporal y se
/// coloca al terminar.
fn escribir_wav(destino: &Path, izq: &[f32], der: &[f32]) -> NsResult<u64> {
    use std::io::Write as _;
    let n = izq.len().min(der.len());
    let datos = u32::try_from(n * 4).map_err(|_| NsError::Internal)?;
    let mut b = Vec::with_capacity(44 + n * 4);
    b.extend_from_slice(b"RIFF");
    b.extend_from_slice(&(36 + datos).to_le_bytes());
    b.extend_from_slice(b"WAVEfmt ");
    b.extend_from_slice(&16u32.to_le_bytes());
    b.extend_from_slice(&1u16.to_le_bytes());
    b.extend_from_slice(&2u16.to_le_bytes());
    b.extend_from_slice(&TASA.to_le_bytes());
    b.extend_from_slice(&(TASA * 4).to_le_bytes());
    b.extend_from_slice(&4u16.to_le_bytes());
    b.extend_from_slice(&16u16.to_le_bytes());
    b.extend_from_slice(b"data");
    b.extend_from_slice(&datos.to_le_bytes());
    let muestra = |v: f32| ((v.clamp(-1.0, 1.0) * 32_767.0).round() as i16).to_le_bytes();
    for i in 0..n {
        b.extend_from_slice(&muestra(izq[i]));
        b.extend_from_slice(&muestra(der[i]));
    }
    if let Some(dir) = destino.parent() {
        std::fs::create_dir_all(dir).map_err(|_| NsError::StorageFailure)?;
    }
    let temporal = destino.with_extension("wav.parcial");
    let mut f = std::fs::File::create(&temporal).map_err(|_| NsError::StorageFailure)?;
    f.write_all(&b).map_err(|_| NsError::StorageFailure)?;
    f.sync_all().map_err(|_| NsError::StorageFailure)?;
    std::fs::rename(&temporal, destino).map_err(|_| NsError::StorageFailure)?;
    Ok(b.len() as u64)
}

// --- El modelo -------------------------------------------------------------------------

/// El modelo del agregado, si está instalado.
#[must_use]
pub fn modelo_instalado(rutas: &Rutas) -> Option<PathBuf> {
    agregados::instalado(rutas, IdAgregado::Karaoke)?;
    let m = agregados::carpeta(rutas, IdAgregado::Karaoke).join(ARCHIVO_MODELO);
    m.is_file().then_some(m)
}

fn sesion(modelo: &Path) -> NsResult<ort::session::Session> {
    let entorno = crate::onnx::entorno()?;
    let hilos = std::thread::available_parallelism()
        .map(|n| (n.get() / 2).max(1))
        .unwrap_or(1);
    let fallo = |_| {
        tracing::error!("no se pudo preparar el modelo de karaoke");
        NsError::ComponentUnavailable
    };
    ort::session::Session::builder(entorno)
        .map_err(|_| NsError::ComponentUnavailable)?
        .with_execution_providers([ort::ep::CPU::default().with_arena_allocator(false).build()])
        .map_err(fallo)?
        .with_memory_pattern(false)
        .map_err(fallo)?
        .with_intra_threads(hilos)
        .map_err(fallo)?
        .with_optimization_level(ort::session::builder::GraphOptimizationLevel::All)
        .map_err(fallo)?
        .commit_from_file(modelo)
        .map_err(|_| NsError::ComponentUnavailable)
}

/// Separa una pista y escribe su instrumental.
///
/// # Errors
///
/// Los de la decodificación, del modelo y de la escritura; [`NsError::Cancelled`].
pub fn separar_archivo(
    modelo: &Path,
    audio: &Path,
    destino: &Path,
    seguir: &mut dyn FnMut(f64) -> bool,
) -> NsResult<u64> {
    let (izq, der) = cargar(audio)?;
    let mut s = sesion(modelo)?;
    let mut llamar = |trozo: &[f32]| -> NsResult<Vec<f32>> {
        let entrada = ort::value::Tensor::from_array(([1usize, 2, SEGMENTO], trozo.to_vec()))
            .map_err(|_| NsError::Internal)?;
        let salidas = s
            .run(ort::inputs![entrada])
            .map_err(|_| NsError::Internal)?;
        let (_, datos) = salidas[0]
            .try_extract_tensor::<f32>()
            .map_err(|_| NsError::Internal)?;
        Ok(datos.to_vec())
    };
    let (a, b) = separar(&izq, &der, &mut llamar, seguir)?;
    escribir_wav(destino, &a, &b)
}

// --- La cola en segundo plano ----------------------------------------------------------

/// Lo que ve la interfaz: qué pista se está preparando y cuánto lleva.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct Preparando {
    pub pista: i64,
    pub fraccion: f64,
}

/// Pide preparar una pista: la pone en la cola si no tiene ya fila. Si estaba
/// fallida, vuelve a intentarlo.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la escritura falla.
pub fn pedir(db: &BaseDeDatos, pistas: &[i64]) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    for p in pistas {
        tx.execute(
            "INSERT INTO stems (pista_id, estado) VALUES (?1, 'pendiente')
             ON CONFLICT (pista_id) DO UPDATE SET estado = 'pendiente', error = NULL,
                 solicitada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
             WHERE stems.estado = 'fallida'",
            [p],
        )
        .map_err(|_| NsError::StorageFailure)?;
    }
    tx.commit().map_err(|_| NsError::StorageFailure)
}

/// La próxima pendiente, por orden de petición, con su archivo y su huella.
fn siguiente(db: &BaseDeDatos) -> NsResult<Option<(i64, PathBuf, Option<String>)>> {
    let conn = db.conexion()?;
    let musica = persistencia::carpeta_musica(&conn)?;
    let fila: Option<(i64, String, Option<String>)> = conn
        .query_row(
            "SELECT s.pista_id, p.ruta, p.sha256 FROM stems s JOIN pistas p ON p.id = s.pista_id
             WHERE s.estado = 'pendiente' ORDER BY s.solicitada_en, s.pista_id LIMIT 1",
            [],
            |f| Ok((f.get(0)?, f.get(1)?, f.get(2)?)),
        )
        .optional()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(fila.map(|(id, ruta, sha)| {
        let r = PathBuf::from(ruta);
        let r = match &musica {
            Some(m) if r.is_relative() => m.join(r),
            _ => r,
        };
        (id, r, sha)
    }))
}

fn marcar(db: &BaseDeDatos, sql: &str, p: impl rusqlite::Params) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    tx.execute(sql, p).map_err(|_| NsError::StorageFailure)?;
    tx.commit().map_err(|_| NsError::StorageFailure)
}

/// Lo que se cortó con la aplicación cerrada vuelve a la cola.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la escritura falla.
pub fn retomar(db: &BaseDeDatos) -> NsResult<()> {
    marcar(
        db,
        "UPDATE stems SET estado = 'pendiente' WHERE estado = 'separando'",
        [],
    )
}

/// Separa una pendiente. Devuelve `false` si no había ninguna.
fn una(
    db: &BaseDeDatos,
    rutas: &Rutas,
    modelo: &Path,
    estado: &Mutex<Option<Preparando>>,
    avisar: &dyn Fn(),
) -> NsResult<bool> {
    let Some((pista, audio, sha)) = siguiente(db)? else {
        return Ok(false);
    };
    marcar(
        db,
        "UPDATE stems SET estado = 'separando', intentos = intentos + 1 WHERE pista_id = ?1",
        [pista],
    )?;
    let relativa = format!("v2-{pista}.wav");
    let destino = rutas.stems().join(&relativa);
    let mut ultimo = -1.0;
    let resultado = separar_archivo(modelo, &audio, &destino, &mut |f| {
        if f - ultimo >= 0.01 {
            ultimo = f;
            *estado.lock().unwrap_or_else(PoisonError::into_inner) =
                Some(Preparando { pista, fraccion: f });
            avisar();
        }
        true
    });
    *estado.lock().unwrap_or_else(PoisonError::into_inner) = None;
    match resultado {
        Ok(bytes) => marcar(
            db,
            "UPDATE stems SET estado = 'lista', instrumental = ?2, bytes = ?3, modelo = ?4,
                 sha256 = ?5, error = NULL,
                 terminada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
             WHERE pista_id = ?1",
            params![pista, relativa, bytes as i64, MODELO, sha],
        )?,
        Err(error) => {
            tracing::warn!(
                codigo = error.code(),
                "no se pudo preparar el karaoke de una pista"
            );
            marcar(
                db,
                "UPDATE stems SET estado = 'fallida', error = ?2 WHERE pista_id = ?1",
                params![pista, error.code()],
            )?;
        }
    }
    avisar();
    Ok(true)
}

/// El servicio: la cola y lo que se está preparando. Clonable.
#[derive(Clone)]
pub struct Karaoke {
    tx: Sender<()>,
    estado: Arc<Mutex<Option<Preparando>>>,
}

impl Karaoke {
    /// Arranca el hilo. Sin el agregado instalado espera: se le despierta al
    /// pedir una pista o al instalarlo.
    pub fn arrancar(db: BaseDeDatos, rutas: Rutas, avisar: impl Fn() + Send + 'static) -> Self {
        let (tx, rx): (Sender<()>, Receiver<()>) = mpsc::channel();
        let estado = Arc::new(Mutex::new(None));
        let e = Arc::clone(&estado);
        let lanzado = std::thread::Builder::new()
            .name("karaoke".into())
            .spawn(move || {
                let _ = retomar(&db);
                loop {
                    if let Some(modelo) = modelo_instalado(&rutas) {
                        match una(&db, &rutas, &modelo, &e, &avisar) {
                            Ok(true) => continue,
                            Ok(false) => {}
                            Err(error) => {
                                tracing::error!(codigo = error.code(), "falló la cola del karaoke")
                            }
                        }
                    }
                    match rx.recv_timeout(Duration::from_secs(300)) {
                        Ok(()) | Err(RecvTimeoutError::Timeout) => {}
                        Err(RecvTimeoutError::Disconnected) => return,
                    }
                }
            });
        if lanzado.is_err() {
            tracing::error!("no se pudo lanzar el karaoke");
        }
        Self { tx, estado }
    }

    /// Despierta la cola: hay algo nuevo que preparar o se instaló el agregado.
    pub fn despertar(&self) {
        let _ = self.tx.send(());
    }

    #[must_use]
    pub fn preparando(&self) -> Option<Preparando> {
        *self.estado.lock().unwrap_or_else(PoisonError::into_inner)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Un modelo de mentira que dice que todo es voz: copia la entrada en los
    /// cuatro stems.
    fn todo_voz(trozo: &[f32]) -> NsResult<Vec<f32>> {
        Ok(trozo.repeat(4))
    }

    fn senal(n: usize, f: f32, fase: f32) -> Vec<f32> {
        (0..n)
            .map(|i| (i as f32 * f / TASA as f32 * std::f32::consts::TAU + fase).sin() * 0.4 + 0.01)
            .collect()
    }

    #[test]
    fn si_todo_es_voz_el_instrumental_es_silencio_en_toda_la_pista() {
        // Más de dos segmentos y un trozo final corto: todas las muestras quedan
        // cubiertas por la ventana y se deshace bien la normalización.
        let n = SEGMENTO * 2 + 12_345;
        let (izq, der) = (senal(n, 440.0, 0.0), senal(n, 330.0, 1.0));
        let mut avance = Vec::new();
        let (a, b) = separar(&izq, &der, &mut todo_voz, &mut |f| {
            avance.push(f);
            true
        })
        .unwrap();
        assert_eq!((a.len(), b.len()), (n, n));
        let max = a.iter().chain(&b).fold(0.0f32, |m, v| m.max(v.abs()));
        assert!(max < 1e-4, "{max}");
        assert_eq!(avance.last(), Some(&1.0));
        assert!(avance.windows(2).all(|w| w[0] <= w[1]));
    }

    #[test]
    fn si_no_hay_voz_el_instrumental_es_la_mezcla() {
        let n = SEGMENTO + 1000;
        let (izq, der) = (senal(n, 220.0, 0.0), senal(n, 110.0, 0.5));
        let mut sin_voz = |t: &[f32]| -> NsResult<Vec<f32>> {
            let mut v = t.repeat(4);
            // La voz, a la mezcla normalizada de media cero: tras deshacer la
            // normalización vale la media, y el instrumental es la mezcla menos
            // ella.
            for x in &mut v[VOZ * 2 * SEGMENTO..] {
                *x = 0.0;
            }
            Ok(v)
        };
        let (a, _) = separar(&izq, &der, &mut sin_voz, &mut |_| true).unwrap();
        let media = (0..n).map(|i| (izq[i] + der[i]) * 0.5).sum::<f32>() / n as f32;
        for i in (0..n).step_by(997) {
            assert!((a[i] - (izq[i] - media)).abs() < 1e-4, "{i}");
        }
    }

    #[test]
    fn se_puede_cancelar_y_un_modelo_con_otra_forma_se_rechaza() {
        let n = SEGMENTO * 3;
        let (izq, der) = (senal(n, 220.0, 0.0), senal(n, 220.0, 0.0));
        let mut llamadas = 0;
        assert_eq!(
            separar(&izq, &der, &mut todo_voz, &mut |_| {
                llamadas += 1;
                llamadas < 2
            }),
            Err(NsError::Cancelled)
        );
        let mut corto = |t: &[f32]| -> NsResult<Vec<f32>> { Ok(t.to_vec()) };
        assert_eq!(
            separar(&izq, &der, &mut corto, &mut |_| true),
            Err(NsError::Internal)
        );
        assert_eq!(
            separar(&[], &[], &mut todo_voz, &mut |_| true),
            Err(NsError::AudioCorrupted)
        );
    }

    #[test]
    fn el_wav_escrito_lo_lee_el_reproductor() {
        let d = std::env::temp_dir().join(format!("ns-karaoke-wav-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        let ruta = d.join("x.wav");
        let s = senal(TASA as usize, 440.0, 0.0);
        let bytes = escribir_wav(&ruta, &s, &s).unwrap();
        assert_eq!(bytes, 44 + 4 * TASA as u64);
        let (a, b) = cargar(&ruta).unwrap();
        assert_eq!(a.len(), TASA as usize);
        assert!((a[1234] - s[1234]).abs() < 1e-3 && (b[99] - s[99]).abs() < 1e-3);
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn la_cola_va_por_orden_reintenta_lo_fallido_y_retoma_lo_cortado() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO pistas (id, titulo, ruta) VALUES (1, 'a', 'a.mp3'), (2, 'b', 'b.mp3'), (3, 'c', 'c.mp3');
                 INSERT INTO stems (pista_id, estado, error) VALUES (3, 'fallida', 'AUDIO_CORRUPTED');
                 INSERT INTO stems (pista_id, estado) VALUES (2, 'separando');",
            )
            .unwrap();
        pedir(&db, &[1, 3]).unwrap();
        retomar(&db).unwrap();
        let estados: String = db
            .conexion()
            .unwrap()
            .query_row(
                "SELECT group_concat(pista_id || estado, ',') FROM (SELECT * FROM stems ORDER BY pista_id)",
                [],
                |f| f.get(0),
            )
            .unwrap();
        assert_eq!(estados, "1pendiente,2pendiente,3pendiente");
        // Una lista no vuelve a la cola por pedirla otra vez.
        db.conexion()
            .unwrap()
            .execute(
                "UPDATE stems SET estado = 'lista', instrumental = 'x.wav' WHERE pista_id = 1",
                [],
            )
            .unwrap();
        pedir(&db, &[1]).unwrap();
        assert!(siguiente(&db).unwrap().is_some_and(|(id, _, _)| id != 1));
    }

    /// Con el modelo real, si alguien lo deja en `NS_MODELO_KARAOKE`: no está en el
    /// repositorio (`CLAUDE.md`), así que de ordinario se salta sola.
    #[test]
    fn con_el_modelo_real_separa_una_pista() {
        let (Some(modelo), Some(audio), Some(ort)) = (
            std::env::var_os("NS_MODELO_KARAOKE").map(PathBuf::from),
            std::env::var_os("NS_AUDIO_KARAOKE").map(PathBuf::from),
            std::env::var_os("NS_ONNXRUNTIME").map(PathBuf::from),
        ) else {
            return;
        };
        crate::onnx::fijar_ruta(&ort);
        let d = std::env::temp_dir().join(format!("ns-karaoke-real-{}", std::process::id()));
        let bytes = separar_archivo(&modelo, &audio, &d.join("i.wav"), &mut |_| true).unwrap();
        assert!(bytes > 44);
        let _ = std::fs::remove_dir_all(&d);
    }
}
