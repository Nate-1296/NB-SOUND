//! El análisis musical con modelos (F5.3.1 y F5.3.2): `core/audio_intelligence_deep.py`
//! de la V1, sin Essentia ni TensorFlow (ADR-002).
//!
//! La cadena es la que F0.4.3 midió contra lo que guardó la V1 en 407 pistas (peor
//! diferencia 0,0041): la pista entera en mono, remuestreada a 16 kHz con el
//! conversor **lineal** de libsamplerate y la razón en `f32` (lo que hacía Essentia
//! con `resampleQuality = 4`; uno de calidad desviaba las salidas hasta 0,1), las 96
//! bandas mel de `TensorflowInputMusiCNN`, parches de 187 marcos cada 93
//! descartando el último incompleto, MusiCNN en lotes de 8 (con 64, como Essentia,
//! una pista llega a 3,6 GB) y sus siete cabezas sobre los embeddings. Cada salida
//! es la media sobre los parches.
//!
//! **Un defecto de la V1 que no se porta.** DEAM da valencia y activación en su
//! escala de 1 a 9, y la V1 las recortaba a `[0, 1]`: guardaba casi siempre 1. Aquí
//! se llevan a `(v − 1) / 8`, la escala con la que F0.4.3 las comparó. Por eso las
//! filas que trajo la V1 se vuelven a analizar: su versión no es esta (V4).

use std::path::{Path, PathBuf};
use std::time::Duration;

use rustfft::num_complex::Complex;
use rustfft::FftPlanner;

use crate::agregados::{self, IdAgregado};
use crate::audio::decodificador::Decodificador;
use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};
use crate::paths::Rutas;
use crate::reproductor::persistencia;

/// La versión del analizador en cada fila.
pub const VERSION: &str = "v2-musicnn-1";
const SR: f64 = 16_000.0;
/// Parches de MusiCNN: 187 marcos (unos 3 s) cada 93.
const PARCHE: usize = 187;
const SALTO_PARCHE: usize = 93;
const BANDAS: usize = 96;
/// Parches por llamada al modelo (F0.4.3: 445 MB frente a 3,6 GB con 64).
const LOTE: usize = 8;
/// Lo que se descansa entre dos pistas en segundo plano: unos 5 s de proceso por
/// pista con la mitad de pausa no se nota en el equipo.
const PAUSA: Duration = Duration::from_millis(2500);

/// Las 50 etiquetas de `msd-musicnn-1`, en el orden de su salida.
const ETIQUETAS_MSD: [&str; 50] = [
    "rock",
    "pop",
    "alternative",
    "indie",
    "electronic",
    "female vocalists",
    "dance",
    "00s",
    "alternative rock",
    "jazz",
    "beautiful",
    "metal",
    "chillout",
    "male vocalists",
    "classic rock",
    "soul",
    "indie rock",
    "Mellow",
    "electronica",
    "80s",
    "folk",
    "90s",
    "chill",
    "instrumental",
    "punk",
    "oldies",
    "blues",
    "hard rock",
    "ambient",
    "acoustic",
    "experimental",
    "female vocalist",
    "guitar",
    "Hip-Hop",
    "70s",
    "party",
    "country",
    "easy listening",
    "sexy",
    "catchy",
    "funk",
    "electro",
    "heavy metal",
    "Progressive rock",
    "60s",
    "rnb",
    "indie pop",
    "sad",
    "House",
    "happy",
];

/// Las cabezas, con su archivo y la clase positiva de cada una.
const CABEZAS: [(&str, usize); 6] = [
    ("danceability-msd-musicnn-1", 0),
    ("mood_happy-msd-musicnn-1", 0),
    ("mood_sad-msd-musicnn-1", 1),
    ("mood_relaxed-msd-musicnn-1", 1),
    ("mood_aggressive-msd-musicnn-1", 0),
    ("mood_party-msd-musicnn-1", 1),
];
const EMBEDDINGS: &str = "msd-musicnn-1";
const DEAM: &str = "deam-msd-musicnn-2";

// --- Preprocesado ----------------------------------------------------------------------

/// El conversor lineal de libsamplerate con la razón en `f32`, como Essentia.
fn a_16k(mono: &[f32], origen: u32) -> Vec<f32> {
    if mono.is_empty() {
        return Vec::new();
    }
    let paso = 1.0 / f64::from(SR as f32 / origen as f32);
    let n = (mono.len() as f64 / paso).round() as usize;
    let mut out = Vec::with_capacity(n);
    out.push(mono[0]);
    let mut idx = paso;
    let mut usado = idx.floor() as usize;
    idx -= idx.floor();
    while out.len() < n && usado < mono.len() {
        let a = f64::from(mono[usado.max(1) - 1]);
        out.push((a + idx * (f64::from(mono[usado]) - a)) as f32);
        idx += paso;
        let entero = idx.floor();
        usado += entero as usize;
        idx -= entero;
    }
    out
}

/// Los marcos del `FrameCutter` de streaming con `startFromZero = false`.
fn marcos(senal: &[f32], tam: usize, salto: usize) -> Vec<Vec<f32>> {
    let mut salida = Vec::new();
    let n = senal.len() as i64;
    let mut inicio = -(tam as i64 / 2);
    while inicio < n {
        let marco: Vec<f32> = (0..tam as i64)
            .map(|k| {
                let i = inicio + k;
                if (0..n).contains(&i) {
                    senal[i as usize]
                } else {
                    0.0
                }
            })
            .collect();
        salida.push(marco);
        if inicio + tam as i64 > n && inicio + (tam as i64 / 2) >= n {
            break;
        }
        inicio += salto as i64;
    }
    salida
}

fn hz_a_mel(hz: f64) -> f64 {
    let lin = 3.0 / 200.0;
    if hz < 1000.0 {
        hz * lin
    } else {
        1000.0 * lin + (hz / 1000.0).ln() / (6.4f64.ln() / 27.0)
    }
}

fn mel_a_hz(mel: f64) -> f64 {
    let lin = 3.0 / 200.0;
    let min = 1000.0 * lin;
    if mel < min {
        mel / lin
    } else {
        1000.0 * ((mel - min) * (6.4f64.ln() / 27.0)).exp()
    }
}

/// `MelBands` de Essentia para MusiCNN: 96 bandas de 0 a 8 kHz, Slaney,
/// triángulos normalizados por área, sobre la potencia.
fn banco() -> Vec<(usize, Vec<f64>)> {
    let bins = 257usize;
    let (mb, ma) = (hz_a_mel(0.0), hz_a_mel(8000.0));
    let paso = (ma - mb) / (BANDAS + 1) as f64;
    let f: Vec<f64> = (0..BANDAS + 2)
        .map(|i| mel_a_hz(mb + paso * i as f64))
        .collect();
    let escala = (SR / 2.0) / (bins - 1) as f64;
    (0..BANDAS)
        .map(|i| {
            let (s1, s2) = (f[i + 1] - f[i], f[i + 2] - f[i + 1]);
            let ini = (f[i] / escala).ceil() as usize;
            let fin = ((f[i + 2] / escala).floor() as usize).min(bins - 1);
            let area = (s1 + s2) / 2.0;
            let w = (ini..=fin)
                .map(|j| {
                    let bf = j as f64 * escala;
                    let v = if bf < f[i + 1] {
                        (bf - f[i]) / s1
                    } else {
                        (f[i + 2] - bf) / s2
                    };
                    v / area
                })
                .collect();
            (ini, w)
        })
        .collect()
}

/// Las bandas de `TensorflowInputMusiCNN`: marcos de 512 cada 256, Hann
/// simétrica, potencia por las bandas y `log10(1 + 10000·x)`.
fn bandas(senal: &[f32]) -> Vec<[f32; BANDAS]> {
    let mut plan = FftPlanner::new();
    let fft = plan.plan_fft_forward(512);
    let ventana: Vec<f64> = (0..512)
        .map(|i| 0.5 - 0.5 * (2.0 * std::f64::consts::PI * f64::from(i) / 511.0).cos())
        .collect();
    let b = banco();
    let mut buf = vec![Complex::new(0.0, 0.0); 512];
    marcos(senal, 512, 256)
        .iter()
        .map(|m| {
            for (k, c) in buf.iter_mut().enumerate() {
                *c = Complex::new(f64::from(m[k]) * ventana[k], 0.0);
            }
            fft.process(&mut buf);
            let mut fila = [0f32; BANDAS];
            for (v, (ini, w)) in fila.iter_mut().zip(&b) {
                let e: f64 = w
                    .iter()
                    .enumerate()
                    .map(|(k, p)| p * buf[ini + k].norm_sqr())
                    .sum();
                *v = (10_000.0 * e + 1.0).log10() as f32;
            }
            fila
        })
        .collect()
}

/// Parches como `VectorRealToTensor` con `lastPatchMode = discard`, aplanados.
fn parches(bandas: &[[f32; BANDAS]]) -> Vec<Vec<f32>> {
    (0..)
        .map(|k| k * SALTO_PARCHE)
        .take_while(|i| i + PARCHE <= bandas.len())
        .map(|ini| {
            bandas[ini..ini + PARCHE]
                .iter()
                .flatten()
                .copied()
                .collect()
        })
        .collect()
}

// --- Modelos ---------------------------------------------------------------------------

/// Lo que se guarda en `analisis_profundo`.
#[derive(Debug, Clone, PartialEq)]
pub struct Profundo {
    pub bailable: f64,
    pub feliz: f64,
    pub triste: f64,
    pub relajada: f64,
    pub agresiva: f64,
    pub fiesta: f64,
    /// De 0 a 1: `(v − 1) / 8` sobre la escala de DEAM.
    pub valencia: f64,
    pub activacion: f64,
    pub embedding: Vec<f32>,
    /// Las diez etiquetas de estilo más probables.
    pub etiquetas: Vec<(&'static str, f64)>,
}

/// La media de cada columna de una salida `[filas, columnas]` aplanada.
fn media_por_columna(datos: &[f32], columnas: usize) -> Vec<f64> {
    let filas = datos.len() / columnas.max(1);
    (0..columnas)
        .map(|c| {
            (0..filas)
                .map(|f| f64::from(datos[f * columnas + c]))
                .sum::<f64>()
                / filas.max(1) as f64
        })
        .collect()
}

/// Lo que hacen los modelos, separado de cómo se ejecutan, para probar la cadena
/// sin ellos: dado un lote, sus salidas aplanadas con su número de columnas.
pub trait Modelos {
    /// Embeddings y etiquetas de MusiCNN para un lote de parches.
    ///
    /// # Errors
    ///
    /// Los de la ejecución.
    fn musicnn(
        &mut self,
        parches: &[f32],
        n: usize,
    ) -> NsResult<(Vec<f32>, usize, Vec<f32>, usize)>;
    /// Una cabeza sobre los embeddings.
    ///
    /// # Errors
    ///
    /// Los de la ejecución.
    fn cabeza(
        &mut self,
        nombre: &str,
        embeddings: &[f32],
        n: usize,
        dim: usize,
    ) -> NsResult<(Vec<f32>, usize)>;
}

/// La cadena desde la señal a 16 kHz.
///
/// # Errors
///
/// [`NsError::AudioCorrupted`] si es más corta que un parche; los de `modelos`.
pub fn de_senal(senal: &[f32], modelos: &mut dyn Modelos) -> NsResult<Profundo> {
    let p = parches(&bandas(senal));
    if p.is_empty() {
        return Err(NsError::AudioCorrupted);
    }
    let (mut emb, mut dim, mut tags, mut n_tags) = (Vec::new(), 0, Vec::new(), 0);
    for lote in p.chunks(LOTE) {
        let entrada: Vec<f32> = lote.iter().flatten().copied().collect();
        let (e, d, t, nt) = modelos.musicnn(&entrada, lote.len())?;
        emb.extend_from_slice(&e);
        tags.extend_from_slice(&t);
        (dim, n_tags) = (d, nt);
    }
    let filas = p.len();
    let mut probabilidad = |nombre: &str, clase: usize| -> NsResult<f64> {
        let (salida, columnas) = modelos.cabeza(nombre, &emb, filas, dim)?;
        Ok(media_por_columna(&salida, columnas)
            .get(clase)
            .copied()
            .unwrap_or(0.0)
            .clamp(0.0, 1.0))
    };
    let valores: Vec<f64> = CABEZAS
        .iter()
        .map(|(n, c)| probabilidad(n, *c))
        .collect::<NsResult<_>>()?;
    let (deam, cols) = modelos.cabeza(DEAM, &emb, filas, dim)?;
    let av = media_por_columna(&deam, cols);
    let escala = |v: Option<&f64>| v.map_or(0.5, |v| ((v - 1.0) / 8.0).clamp(0.0, 1.0));
    let mut etiquetas: Vec<(&'static str, f64)> = media_por_columna(&tags, n_tags)
        .into_iter()
        .zip(ETIQUETAS_MSD)
        .map(|(p, e)| (e, (p * 10_000.0).round() / 10_000.0))
        .collect();
    etiquetas.sort_by(|a, b| b.1.total_cmp(&a.1));
    etiquetas.truncate(10);
    Ok(Profundo {
        bailable: valores[0],
        feliz: valores[1],
        triste: valores[2],
        relajada: valores[3],
        agresiva: valores[4],
        fiesta: valores[5],
        valencia: escala(av.first()),
        activacion: escala(av.get(1)),
        embedding: media_por_columna(&emb, dim)
            .into_iter()
            .map(|v| v as f32)
            .collect(),
        etiquetas,
    })
}

/// Los modelos del agregado, con ONNX Runtime.
struct EnOnnx {
    musicnn: ort::session::Session,
    cabezas: Vec<(&'static str, ort::session::Session)>,
}

impl EnOnnx {
    fn abrir(dir: &Path) -> NsResult<Self> {
        let entorno = crate::onnx::entorno()?;
        // Pocos hilos: el análisis va en segundo plano y no puede notarse.
        let hilos = std::thread::available_parallelism()
            .map(|n| (n.get() / 4).max(1))
            .unwrap_or(1);
        let abrir = |nombre: &str| -> NsResult<ort::session::Session> {
            ort::session::Session::builder(entorno)
                .map_err(|_| NsError::ComponentUnavailable)?
                .with_intra_threads(hilos)
                .map_err(|_| NsError::ComponentUnavailable)?
                .commit_from_file(dir.join(format!("{nombre}.onnx")))
                .map_err(|_| NsError::ComponentUnavailable)
        };
        let mut cabezas = Vec::new();
        for (n, _) in CABEZAS {
            cabezas.push((n, abrir(n)?));
        }
        cabezas.push((DEAM, abrir(DEAM)?));
        Ok(Self {
            musicnn: abrir(EMBEDDINGS)?,
            cabezas,
        })
    }
}

fn correr(
    s: &mut ort::session::Session,
    datos: &[f32],
    forma: Vec<usize>,
    salidas: &[usize],
) -> NsResult<Vec<(Vec<f32>, usize)>> {
    let t =
        ort::value::Tensor::from_array((forma, datos.to_vec())).map_err(|_| NsError::Internal)?;
    let r = s.run(ort::inputs![t]).map_err(|_| NsError::Internal)?;
    salidas
        .iter()
        .map(|&i| {
            let (forma, d) = r[i]
                .try_extract_tensor::<f32>()
                .map_err(|_| NsError::Internal)?;
            let cols = forma.last().copied().unwrap_or(1).max(1) as usize;
            Ok((d.to_vec(), cols))
        })
        .collect()
}

impl Modelos for EnOnnx {
    fn musicnn(
        &mut self,
        parches: &[f32],
        n: usize,
    ) -> NsResult<(Vec<f32>, usize, Vec<f32>, usize)> {
        // Tres salidas: 0, las etiquetas (Sigmoid); 2, los embeddings (dense).
        let mut r = correr(&mut self.musicnn, parches, vec![n, PARCHE, BANDAS], &[2, 0])?;
        let (tags, nt) = r.pop().ok_or(NsError::Internal)?;
        let (emb, d) = r.pop().ok_or(NsError::Internal)?;
        Ok((emb, d, tags, nt))
    }

    fn cabeza(
        &mut self,
        nombre: &str,
        embeddings: &[f32],
        n: usize,
        dim: usize,
    ) -> NsResult<(Vec<f32>, usize)> {
        let s = self
            .cabezas
            .iter_mut()
            .find(|(c, _)| *c == nombre)
            .map(|(_, s)| s)
            .ok_or(NsError::Internal)?;
        correr(s, embeddings, vec![n, dim], &[0])?
            .pop()
            .ok_or(NsError::Internal)
    }
}

/// La pista entera, mono a 16 kHz.
fn cargar(ruta: &Path) -> NsResult<Vec<f32>> {
    let mut d = Decodificador::abrir(ruta, 0.0)?;
    let origen = d.tasa;
    let mut frames = Vec::new();
    while d.leer(&mut frames, 65_536)? > 0 {}
    let mono: Vec<f32> = frames.iter().map(|f| (f.left + f.right) * 0.5).collect();
    Ok(a_16k(&mono, origen))
}

/// La carpeta de los modelos, si el agregado está instalado.
#[must_use]
pub fn modelos_instalados(rutas: &Rutas) -> Option<PathBuf> {
    agregados::instalado(rutas, IdAgregado::Analisis)?;
    let d = agregados::carpeta(rutas, IdAgregado::Analisis);
    d.join(format!("{EMBEDDINGS}.onnx")).is_file().then_some(d)
}

// --- En segundo plano (F5.3.2) ---------------------------------------------------------

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
    si("analisis_activado") && si("analisis_en_segundo_plano")
}

/// La siguiente sin análisis de esta versión, o cuyo archivo cambió.
fn siguiente(db: &BaseDeDatos, saltar: &[i64]) -> NsResult<Option<(i64, PathBuf, Option<String>)>> {
    let conn = db.conexion()?;
    let musica = persistencia::carpeta_musica(&conn)?;
    let mut s = conn
        .prepare(
            "SELECT p.id, p.ruta, p.sha256 FROM pistas p
             LEFT JOIN analisis_profundo a ON a.pista_id = p.id
             WHERE p.estado = 'biblioteca'
               AND (a.pista_id IS NULL OR a.version IS NOT ?1 OR a.sha256 IS NOT p.sha256)
             ORDER BY p.id DESC LIMIT ?2",
        )
        .map_err(|_| NsError::StorageFailure)?;
    let filas = s
        .query_map(rusqlite::params![VERSION, 1 + saltar.len() as i64], |f| {
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
        .find(|(id, _, _)| !saltar.contains(id))
        .map(|(id, ruta, sha)| {
            let r = PathBuf::from(ruta);
            let r = match &musica {
                Some(m) if r.is_relative() => m.join(r),
                _ => r,
            };
            (id, r, sha)
        }))
}

fn guardar(db: &BaseDeDatos, pista: i64, sha: Option<&str>, p: Option<&Profundo>) -> NsResult<()> {
    let embedding: Option<Vec<u8>> =
        p.map(|p| p.embedding.iter().flat_map(|v| v.to_le_bytes()).collect());
    let etiquetas = p.map(|p| {
        serde_json::to_string(
            &p.etiquetas
                .iter()
                .map(|(e, v)| serde_json::json!([e, v]))
                .collect::<Vec<_>>(),
        )
        .unwrap_or_default()
    });
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    tx.execute(
        "INSERT INTO analisis_profundo (pista_id, version, sha256, feliz, triste, relajada, agresiva,
             fiesta, bailable, activacion, valencia, embedding, dimensiones, etiquetas)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)
         ON CONFLICT (pista_id) DO UPDATE SET version = excluded.version, sha256 = excluded.sha256,
             feliz = excluded.feliz, triste = excluded.triste, relajada = excluded.relajada,
             agresiva = excluded.agresiva, fiesta = excluded.fiesta, bailable = excluded.bailable,
             activacion = excluded.activacion, valencia = excluded.valencia,
             embedding = excluded.embedding, dimensiones = excluded.dimensiones,
             etiquetas = excluded.etiquetas,
             analizado_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
        rusqlite::params![
            pista,
            VERSION,
            sha,
            p.map(|p| p.feliz),
            p.map(|p| p.triste),
            p.map(|p| p.relajada),
            p.map(|p| p.agresiva),
            p.map(|p| p.fiesta),
            p.map(|p| p.bailable),
            p.map(|p| p.activacion),
            p.map(|p| p.valencia),
            embedding,
            p.map(|p| p.embedding.len() as i64).filter(|d| *d > 0),
            etiquetas,
        ],
    )
    .map_err(|error| {
        tracing::error!(error = %error, "no se pudo guardar el análisis");
        NsError::StorageFailure
    })?;
    let ambiente = p.map_or_else(Vec::new, |p| {
        vec![
            ("feliz", p.feliz),
            ("triste", p.triste),
            ("relajada", p.relajada),
            ("intensa", p.agresiva),
            ("fiesta", p.fiesta),
            ("bailable", p.bailable),
        ]
    });
    crate::rasgos::guardar_ambiente(&tx, pista, "deep_model", VERSION, &ambiente)?;
    tx.commit().map_err(|_| NsError::StorageFailure)
}

/// Analiza lo pendiente hasta que no quede nada, con una pausa entre pistas.
/// Devuelve cuántas apuntó. Reanudable por construcción: lo pendiente es lo que no
/// tiene fila de esta versión.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn analizar_pendientes(
    db: &BaseDeDatos,
    modelos: &mut dyn Modelos,
    pausa: Duration,
) -> NsResult<usize> {
    let mut saltar = Vec::new();
    let mut apuntadas = 0;
    while let Some((pista, ruta, sha)) = siguiente(db, &saltar)? {
        if !activado(db) {
            break;
        }
        match cargar(&ruta).and_then(|s| de_senal(&s, modelos)) {
            Ok(p) => guardar(db, pista, sha.as_deref(), Some(&p))?,
            Err(NsError::AudioCorrupted | NsError::FormatUnsupported) => {
                guardar(db, pista, sha.as_deref(), None)?;
            }
            Err(_) => {
                saltar.push(pista);
                continue;
            }
        }
        apuntadas += 1;
        std::thread::sleep(pausa);
    }
    Ok(apuntadas)
}

/// Lanza el hilo del análisis. Mira cada pocos minutos si hay agregado y trabajo.
pub fn arrancar(db: BaseDeDatos, rutas: Rutas) {
    let lanzado = std::thread::Builder::new()
        .name("analisis".into())
        .spawn(move || loop {
            if activado(&db) {
                if let Some(dir) = modelos_instalados(&rutas) {
                    match EnOnnx::abrir(&dir) {
                        Ok(mut m) => match analizar_pendientes(&db, &mut m, PAUSA) {
                            Ok(n) if n > 0 => tracing::info!(pistas = n, "análisis profundo"),
                            Ok(_) => {}
                            Err(e) => tracing::error!(codigo = e.code(), "falló el análisis"),
                        },
                        Err(e) => {
                            tracing::error!(codigo = e.code(), "no se pudieron abrir los modelos");
                        }
                    }
                }
            }
            std::thread::sleep(Duration::from_secs(180));
        });
    if lanzado.is_err() {
        tracing::error!("no se pudo lanzar el análisis");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Modelos de mentira que devuelven valores fijos con las formas reales:
    /// embeddings de 200, 50 etiquetas, dos clases por cabeza y DEAM de 1 a 9.
    struct Falsos {
        llamadas_musicnn: Vec<usize>,
    }

    impl Modelos for Falsos {
        fn musicnn(
            &mut self,
            _p: &[f32],
            n: usize,
        ) -> NsResult<(Vec<f32>, usize, Vec<f32>, usize)> {
            self.llamadas_musicnn.push(n);
            let tags: Vec<f32> = (0..n)
                .flat_map(|_| (0..50).map(|i| i as f32 / 100.0))
                .collect();
            Ok((vec![0.5; n * 200], 200, tags, 50))
        }

        fn cabeza(
            &mut self,
            nombre: &str,
            _e: &[f32],
            n: usize,
            dim: usize,
        ) -> NsResult<(Vec<f32>, usize)> {
            assert_eq!(dim, 200);
            if nombre == DEAM {
                return Ok(((0..n).flat_map(|_| [5.0, 9.0]).collect(), 2));
            }
            Ok(((0..n).flat_map(|_| [0.2, 0.8]).collect(), 2))
        }
    }

    fn tono(segundos: f64) -> Vec<f32> {
        (0..(segundos * SR) as usize)
            .map(|i| (i as f32 * 0.07).sin() * 0.3)
            .collect()
    }

    #[test]
    fn la_cadena_usa_la_clase_positiva_de_cada_cabeza_y_la_escala_de_deam() {
        let mut m = Falsos {
            llamadas_musicnn: Vec::new(),
        };
        let p = de_senal(&tono(30.0), &mut m).unwrap();
        // Bailable, feliz y agresiva toman la clase 0; triste, relajada y fiesta, la 1.
        assert_eq!(
            (p.bailable, p.feliz, p.agresiva),
            (0.2f32 as f64, 0.2f32 as f64, 0.2f32 as f64)
        );
        assert_eq!(
            (p.triste, p.relajada, p.fiesta),
            (0.8f32 as f64, 0.8f32 as f64, 0.8f32 as f64)
        );
        // DEAM: 5 y 9 sobre 1..9 son 0,5 y 1.
        assert_eq!((p.valencia, p.activacion), (0.5, 1.0));
        assert_eq!(p.embedding.len(), 200);
        assert_eq!(p.etiquetas.len(), 10);
        assert_eq!(p.etiquetas[0].0, "happy", "la de más puntuación primero");
        // En lotes de 8 como mucho.
        assert!(m.llamadas_musicnn.iter().all(|n| *n <= LOTE));
        assert!(m.llamadas_musicnn.len() > 1);
    }

    #[test]
    fn los_parches_son_los_de_essentia() {
        // 30 s a 16 kHz con marcos cada 256 son unos 1876 marcos: los parches de
        // 187 cada 93 que caben enteros, sin el último incompleto.
        let b = bandas(&tono(30.0));
        let p = parches(&b);
        assert_eq!(p.len(), (b.len() - PARCHE) / SALTO_PARCHE + 1);
        assert_eq!(p[0].len(), PARCHE * BANDAS);
        assert_eq!(&p[1][..BANDAS], &b[SALTO_PARCHE][..]);
        assert_eq!(
            de_senal(
                &tono(1.0),
                &mut Falsos {
                    llamadas_musicnn: vec![]
                }
            )
            .unwrap_err(),
            NsError::AudioCorrupted
        );
    }

    #[test]
    fn el_remuestreo_lineal_conserva_la_duracion_y_la_forma() {
        let origen: Vec<f32> = (0..44_100)
            .map(|i| (i as f32 / 44_100.0 * 50.0).sin())
            .collect();
        let r = a_16k(&origen, 44_100);
        assert_eq!(r.len(), 16_000);
        // Lineal sobre una senoide lenta: cerca de la muestra equivalente, con la
        // muestra de retardo del conversor de libsamplerate, que es lo que coincide
        // con Essentia (F0.4.3). Con esta pendiente, una muestra son 1,1e-3.
        assert!((r[8000] - origen[22_050]).abs() < 3e-3);
    }

    #[test]
    fn lo_de_la_v1_se_vuelve_a_analizar_y_lo_hecho_no() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO pistas (id, titulo, ruta) VALUES (1, 'a', 'a.mp3'), (2, 'b', 'b.mp3');
                 INSERT INTO analisis_profundo (pista_id, version, valencia) VALUES (1, 'audio_intel_essentia_v2', 1.0);",
            )
            .unwrap();
        assert_eq!(siguiente(&db, &[]).unwrap().map(|s| s.0), Some(2));
        assert_eq!(
            siguiente(&db, &[2]).unwrap().map(|s| s.0),
            Some(1),
            "la de la V1 caduca"
        );
        guardar(&db, 1, None, None).unwrap();
        assert_eq!(siguiente(&db, &[2]).unwrap(), None);
    }
}
