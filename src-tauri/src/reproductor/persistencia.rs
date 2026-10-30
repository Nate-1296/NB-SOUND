//! Lo que el reproductor lee y escribe en la base: de dónde sale cada pista, la
//! sesión que se restaura al abrir y el historial.

use std::path::{Path, PathBuf};

use rusqlite::{Connection, OptionalExtension};

use crate::audio::sonoridad;
use crate::cola::{Fila, Repeticion};
use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};

fn bd<T>(r: rusqlite::Result<T>) -> NsResult<T> {
    r.map_err(|error| {
        tracing::error!(error = %error, "falló una consulta del reproductor");
        NsError::StorageFailure
    })
}

/// Lo que hace falta para tocar una pista.
#[derive(Debug, Clone, PartialEq)]
pub struct PistaResuelta {
    pub ruta: PathBuf,
    pub instrumental: Option<PathBuf>,
    pub duracion_seg: f64,
    pub ganancia_db: f32,
    pub titulo: String,
    pub artista: String,
}

/// La carpeta de la música, respecto a la que se guardan las rutas.
pub fn carpeta_musica(conn: &Connection) -> NsResult<Option<PathBuf>> {
    let valor: Option<String> = bd(conn
        .query_row(
            "SELECT valor FROM preferencias WHERE clave = 'carpeta_musica'",
            [],
            |f| f.get(0),
        )
        .optional())?;
    Ok(valor
        .and_then(|v| serde_json::from_str::<String>(&v).ok())
        .filter(|v| !v.is_empty())
        .map(PathBuf::from))
}

/// Resuelve una pista. `None` si no existe.
pub fn resolver(
    conn: &Connection,
    pista_id: i64,
    musica: Option<&Path>,
    stems: &Path,
    normalizar: bool,
) -> NsResult<Option<PistaResuelta>> {
    let fila = bd(conn
        .query_row(
            "SELECT p.ruta, coalesce(p.duracion_seg, 0), r.lufs, r.pico_verdadero, s.instrumental,
                    p.titulo, p.artista_nombre
             FROM pistas p
             LEFT JOIN rasgos r ON r.pista_id = p.id
             LEFT JOIN stems s ON s.pista_id = p.id AND s.estado = 'lista'
             WHERE p.id = ?1",
            [pista_id],
            |f| {
                Ok((
                    f.get::<_, String>(0)?,
                    f.get::<_, f64>(1)?,
                    f.get::<_, Option<f64>>(2)?,
                    f.get::<_, Option<f64>>(3)?,
                    f.get::<_, Option<String>>(4)?,
                    f.get::<_, String>(5)?,
                    f.get::<_, String>(6)?,
                ))
            },
        )
        .optional())?;
    let Some((ruta, duracion, lufs, pico, instrumental, titulo, artista)) = fila else {
        return Ok(None);
    };
    let ruta = PathBuf::from(ruta);
    let ruta = match musica {
        Some(m) if ruta.is_relative() => m.join(ruta),
        _ => ruta,
    };
    Ok(Some(PistaResuelta {
        ruta,
        instrumental: instrumental.map(|i| stems.join(i)),
        duracion_seg: duracion,
        ganancia_db: if normalizar {
            sonoridad::ganancia_db(lufs, pico)
        } else {
            0.0
        },
        titulo,
        artista,
    }))
}

/// La sesión guardada.
#[derive(Debug, Clone, PartialEq)]
pub struct Sesion {
    pub cola: Vec<Fila>,
    pub posicion_cola: usize,
    pub posicion_seg: f64,
    pub volumen: f32,
    pub aleatorio: bool,
    pub repeticion: Repeticion,
    pub normalizar: bool,
}

pub fn leer_sesion(conn: &Connection) -> NsResult<Sesion> {
    let mut s = bd(conn.prepare(
        "SELECT c.pista_id FROM cola c JOIN pistas p ON p.id = c.pista_id ORDER BY c.posicion",
    ))?;
    let cola = bd(s.query_map([], |f| {
        Ok(Fila {
            pista_id: f.get(0)?,
        })
    }))?
    .collect::<rusqlite::Result<Vec<_>>>()
    .map_err(|_| NsError::StorageFailure)?;
    let (posicion_cola, posicion_seg, volumen, aleatorio, repeticion, normalizar) = bd(conn
        .query_row(
            "SELECT coalesce(posicion_cola, 0), posicion_seg, volumen, aleatorio, repeticion,
                    normalizar
             FROM estado_reproductor WHERE id = 1",
            [],
            |f| {
                Ok((
                    f.get::<_, i64>(0)?,
                    f.get::<_, f64>(1)?,
                    f.get::<_, f64>(2)?,
                    f.get::<_, bool>(3)?,
                    f.get::<_, String>(4)?,
                    f.get::<_, bool>(5)?,
                ))
            },
        ))?;
    Ok(Sesion {
        cola,
        posicion_cola: posicion_cola.max(0) as usize,
        posicion_seg,
        volumen: volumen as f32,
        aleatorio,
        repeticion: Repeticion::desde_v1(&repeticion).unwrap_or(Repeticion::Ninguno),
        normalizar,
    })
}

fn texto_repeticion(r: Repeticion) -> &'static str {
    match r {
        Repeticion::Ninguno => "ninguno",
        Repeticion::Todo => "todo",
        Repeticion::Uno => "uno",
    }
}

/// Guarda la cola y los ajustes. En una sola transacción: una cola a medias es
/// peor que la anterior entera.
pub fn guardar_sesion(db: &BaseDeDatos, s: &Sesion, pista_id: Option<i64>) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    bd(tx.execute("DELETE FROM cola", []))?;
    {
        let mut insertar = bd(tx.prepare("INSERT INTO cola (posicion, pista_id) VALUES (?1, ?2)"))?;
        for (i, f) in s.cola.iter().enumerate() {
            bd(insertar.execute(rusqlite::params![i as i64, f.pista_id]))?;
        }
    }
    bd(tx.execute(
        "UPDATE estado_reproductor SET
             pista_id = (SELECT id FROM pistas WHERE id = ?1),
             posicion_cola = ?2, posicion_seg = ?3, volumen = ?4, aleatorio = ?5,
             repeticion = ?6, normalizar = ?7,
             actualizado_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
         WHERE id = 1",
        rusqlite::params![
            pista_id,
            s.posicion_cola as i64,
            s.posicion_seg.max(0.0),
            f64::from(s.volumen.clamp(0.0, 1.0)),
            s.aleatorio,
            texto_repeticion(s.repeticion),
            s.normalizar,
        ],
    ))?;
    bd(tx.commit())
}

/// Una pista que sonó entera: al historial, y una reproducción más.
pub fn registrar_escucha(db: &BaseDeDatos, pista_id: i64, segundos: f64) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    bd(tx.execute(
        "INSERT INTO historial (pista_id, titulo, artista, escuchado_seg, completada)
         SELECT id, titulo, artista_nombre, ?2, 1 FROM pistas WHERE id = ?1",
        rusqlite::params![pista_id, segundos.max(0.0)],
    ))?;
    bd(tx.execute(
        "UPDATE pistas SET reproducciones = reproducciones + 1,
                           ultima_reproduccion = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
         WHERE id = ?1",
        [pista_id],
    ))?;
    bd(tx.commit())
}

/// Las preferencias del ecualizador, como las dejó el usuario (o la V1).
#[derive(Debug, Clone, PartialEq)]
pub struct AjustesEcualizador {
    pub activo: bool,
    pub preseleccion: Option<usize>,
    pub bandas: [f32; 10],
    pub preamp: f32,
}

impl Default for AjustesEcualizador {
    fn default() -> Self {
        Self {
            activo: false,
            preseleccion: Some(0),
            bandas: [0.0; 10],
            preamp: 0.0,
        }
    }
}

fn preferencia(conn: &Connection, clave: &str) -> NsResult<Option<serde_json::Value>> {
    let v: Option<String> = bd(conn
        .query_row(
            "SELECT valor FROM preferencias WHERE clave = ?1",
            [clave],
            |f| f.get(0),
        )
        .optional())?;
    Ok(v.and_then(|v| serde_json::from_str(&v).ok()))
}

pub fn leer_ecualizador(conn: &Connection) -> NsResult<AjustesEcualizador> {
    let mut a = AjustesEcualizador::default();
    if let Some(v) = preferencia(conn, "ecualizador_activo")?.and_then(|v| v.as_bool()) {
        a.activo = v;
    }
    // La V1 guardaba el índice como texto, o "custom" para el personalizado.
    a.preseleccion = match preferencia(conn, "ecualizador_preajuste")? {
        Some(serde_json::Value::String(s)) => s.parse().ok(),
        Some(serde_json::Value::Number(n)) => n.as_u64().map(|n| n as usize),
        Some(serde_json::Value::Null) => None,
        _ => Some(0),
    }
    .filter(|i| *i < crate::audio::ecualizador::PRESELECCIONES.len());
    if let Some(bandas) = preferencia(conn, "ecualizador_bandas")?.and_then(|v| {
        serde_json::from_value::<Vec<f32>>(v)
            .ok()
            .filter(|b| b.len() == 10)
    }) {
        a.bandas.copy_from_slice(&bandas);
    }
    if let Some(p) = preferencia(conn, "ecualizador_preamplificacion")?.and_then(|v| v.as_f64()) {
        a.preamp = p as f32;
    }
    Ok(a)
}

pub fn guardar_ecualizador(db: &BaseDeDatos, a: &AjustesEcualizador) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    let valores = [
        ("ecualizador_activo", serde_json::json!(a.activo)),
        (
            "ecualizador_preajuste",
            a.preseleccion.map_or(
                serde_json::Value::Null,
                |i| serde_json::json!(i.to_string()),
            ),
        ),
        ("ecualizador_bandas", serde_json::json!(a.bandas)),
        ("ecualizador_preamplificacion", serde_json::json!(a.preamp)),
    ];
    for (clave, valor) in valores {
        bd(tx.execute(
            "INSERT INTO preferencias (clave, valor) VALUES (?1, ?2)
             ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor,
                 actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
            rusqlite::params![clave, valor.to_string()],
        ))?;
    }
    bd(tx.commit())
}
