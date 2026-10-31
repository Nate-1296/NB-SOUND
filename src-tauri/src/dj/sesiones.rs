//! Las sesiones del DJ en la base: el CRUD de `servicios/dj_privado/persistencia.py`
//! sobre `dj_sesiones`, `dj_sesion_pistas`, `dj_eventos`, `dj_preferencias` y
//! `dj_en_curso` (V6). Los estados, los tipos de evento y los JSON son los de la V1,
//! para que las sesiones importadas se lean igual que las nuevas.

use rusqlite::{params, OptionalExtension};
use serde::Serialize;

use super::constructor::Bloque;
use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};

fn bd<T>(r: rusqlite::Result<T>) -> NsResult<T> {
    r.map_err(|error| {
        tracing::error!(error = %error, "fallo en las sesiones del DJ");
        NsError::StorageFailure
    })
}

/// `SesionDjRow`.
#[derive(Debug, Clone, PartialEq)]
pub struct Sesion {
    pub id: i64,
    pub peticion: String,
    pub intencion: String,
    pub objetivo_minutos: u32,
    pub estado: String,
    pub motor_version: String,
    pub semilla: Option<i64>,
    pub resumen: String,
    pub playlist_id: Option<i64>,
    pub creada_en: String,
    pub terminada_en: Option<String>,
}

const COLUMNAS: &str =
    "id, peticion, intencion, objetivo_minutos, estado, motor_version, semilla, \
                        resumen, playlist_id, creada_en, terminada_en";

fn sesion(f: &rusqlite::Row<'_>) -> rusqlite::Result<Sesion> {
    Ok(Sesion {
        id: f.get(0)?,
        peticion: f.get(1)?,
        intencion: f.get(2)?,
        objetivo_minutos: f.get(3)?,
        estado: f.get(4)?,
        motor_version: f.get(5)?,
        semilla: f.get(6)?,
        resumen: f.get(7)?,
        playlist_id: f.get(8)?,
        creada_en: f.get(9)?,
        terminada_en: f.get(10)?,
    })
}

/// `crear_sesion`: en estado `construyendo`.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn crear(
    db: &BaseDeDatos,
    peticion: &str,
    intencion_json: &str,
    objetivo_minutos: u32,
    motor_version: &str,
    semilla: Option<i64>,
) -> NsResult<i64> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    bd(tx.execute(
        "INSERT INTO dj_sesiones (peticion, intencion, objetivo_minutos, estado, motor_version, semilla)
         VALUES (?1, ?2, ?3, 'construyendo', ?4, ?5)",
        params![peticion, intencion_json, objetivo_minutos, motor_version, semilla],
    ))?;
    let id = tx.last_insert_rowid();
    bd(tx.commit())?;
    Ok(id)
}

/// `actualizar_estado_sesion`. `terminar` apunta la hora de fin.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn cambiar_estado(db: &BaseDeDatos, id: i64, estado: &str, terminar: bool) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    bd(tx.execute(
        "UPDATE dj_sesiones SET estado = ?1,
             actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
             terminada_en = CASE WHEN ?3 THEN strftime('%Y-%m-%dT%H:%M:%fZ', 'now') ELSE terminada_en END
         WHERE id = ?2",
        params![estado, id, terminar],
    ))?;
    bd(tx.commit())
}

/// Añade las pistas de un bloque y deja el resumen de la sesión al día, en una
/// sola transacción: una sesión nunca queda con pistas que su resumen no cuenta.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn guardar_bloque(
    db: &BaseDeDatos,
    id: i64,
    bloque: &Bloque,
    resumen: &serde_json::Value,
) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    for (k, p) in bloque.pistas.iter().enumerate() {
        // `bloque_a_rows`: cada pista guarda la transición que la trae.
        let transicion = k
            .checked_sub(1)
            .and_then(|i| bloque.transiciones.get(i))
            .map(super::transiciones::Transicion::a_json);
        bd(tx.execute(
            "INSERT OR REPLACE INTO dj_sesion_pistas (sesion_id, posicion, pista_id, puntuacion,
                 puntuacion_intencion, puntuacion_transicion, puntuacion_curva, razones, transicion)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
            params![
                id,
                p.posicion as i64,
                p.pista.id,
                p.puntuacion,
                p.puntuacion_intencion,
                transicion
                    .as_ref()
                    .and_then(|t| t["score"].as_f64())
                    .unwrap_or(0.0),
                p.puntuacion_curva,
                serde_json::to_string(&p.razones).unwrap_or_else(|_| "[]".to_owned()),
                transicion.map_or_else(|| "{}".to_owned(), |t| t.to_string()),
            ],
        ))?;
    }
    bd(tx.execute(
        "UPDATE dj_sesiones SET resumen = ?1, actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
         WHERE id = ?2",
        params![resumen.to_string(), id],
    ))?;
    bd(tx.commit())
}

/// `obtener_sesion`.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn una(db: &BaseDeDatos, id: i64) -> NsResult<Option<Sesion>> {
    let conn = db.conexion()?;
    bd(conn
        .query_row(
            &format!("SELECT {COLUMNAS} FROM dj_sesiones WHERE id = ?1"),
            [id],
            sesion,
        )
        .optional())
}

/// `sesiones_recientes`: de la más nueva a la más vieja. Cota: `limite`.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn recientes(db: &BaseDeDatos, limite: u32) -> NsResult<Vec<Sesion>> {
    let conn = db.conexion()?;
    let mut s = bd(conn.prepare(&format!(
        "SELECT {COLUMNAS} FROM dj_sesiones ORDER BY creada_en DESC, id DESC LIMIT ?1"
    )))?;
    let filas = bd(s.query_map([limite], sesion))?;
    bd(filas.collect())
}

/// Una pista planificada, con lo que la vista muestra de ella.
#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PistaDeSesion {
    pub posicion: u32,
    pub pista_id: i64,
    pub titulo: String,
    pub artista: String,
    pub duracion_seg: f64,
    pub puntuacion: f64,
    pub puntuacion_transicion: f64,
    pub razones: Vec<String>,
    /// La transición que la trae, con las claves de la V1; `{}` en la primera.
    pub transicion: serde_json::Value,
    pub estado: String,
    pub bloqueada: bool,
}

/// `listar_pistas_sesion`, en su orden. Cota: las de una sesión, que el
/// constructor limita a 200 por bloque y a la duración pedida (8 h como mucho).
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn pistas(db: &BaseDeDatos, id: i64) -> NsResult<Vec<PistaDeSesion>> {
    let conn = db.conexion()?;
    let mut s = bd(conn.prepare(
        "SELECT s.posicion, s.pista_id, p.titulo, p.artista_nombre, COALESCE(p.duracion_seg, 0),
                s.puntuacion, s.puntuacion_transicion, s.razones, s.transicion, s.estado, s.bloqueada
         FROM dj_sesion_pistas s JOIN pistas p ON p.id = s.pista_id
         WHERE s.sesion_id = ?1 ORDER BY s.posicion",
    ))?;
    let filas = bd(s.query_map([id], |f| {
        let razones: String = f.get(7)?;
        let transicion: String = f.get(8)?;
        Ok(PistaDeSesion {
            posicion: f.get(0)?,
            pista_id: f.get(1)?,
            titulo: f.get(2)?,
            artista: f.get(3)?,
            duracion_seg: f.get(4)?,
            puntuacion: f.get(5)?,
            puntuacion_transicion: f.get(6)?,
            razones: serde_json::from_str(&razones).unwrap_or_default(),
            transicion: serde_json::from_str(&transicion).unwrap_or_default(),
            estado: f.get(9)?,
            bloqueada: f.get(10)?,
        })
    }))?;
    bd(filas.collect())
}

/// Lo que se hizo con una pista durante la sesión, con los tipos de la V1.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Evento {
    Reproducida,
    Saltada,
    MeGusta,
    NoMeGusta,
    Comentario,
}

impl Evento {
    const fn tipo(self) -> &'static str {
        match self {
            Self::Reproducida => "reproducida",
            Self::Saltada => "saltada",
            Self::MeGusta => "like",
            Self::NoMeGusta => "dislike",
            Self::Comentario => "feedback",
        }
    }

    /// El estado en que deja la pista en la sesión, si lo cambia.
    const fn estado(self) -> Option<&'static str> {
        match self {
            Self::Reproducida => Some("reproducida"),
            Self::Saltada | Self::NoMeGusta => Some("saltada"),
            Self::MeGusta | Self::Comentario => None,
        }
    }
}

/// `registrar_evento` y, si el evento lo pide, `marcar_pista_estado`, juntos.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn registrar(
    db: &BaseDeDatos,
    sesion: i64,
    posicion: Option<u32>,
    pista: Option<i64>,
    evento: Evento,
    datos: &serde_json::Value,
) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    if let (Some(estado), Some(posicion)) = (evento.estado(), posicion) {
        bd(tx.execute(
            "UPDATE dj_sesion_pistas SET estado = ?1 WHERE sesion_id = ?2 AND posicion = ?3",
            params![estado, sesion, posicion],
        ))?;
    }
    bd(tx.execute(
        "INSERT INTO dj_eventos (sesion_id, pista_id, tipo, datos) VALUES (?1, ?2, ?3, ?4)",
        params![sesion, pista, evento.tipo(), datos.to_string()],
    ))?;
    bd(tx.commit())
}

/// `vincular_playlist`.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn vincular_playlist(db: &BaseDeDatos, sesion: i64, playlist: i64) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    bd(tx.execute(
        "UPDATE dj_sesiones SET playlist_id = ?1,
             actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?2",
        params![playlist, sesion],
    ))?;
    bd(tx.commit())
}

/// Borra una sesión con sus pistas y sus eventos (por la cascada del esquema), y
/// deja de recordarla como la que sonaba.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn borrar(db: &BaseDeDatos, id: i64) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    bd(tx.execute("DELETE FROM dj_sesiones WHERE id = ?1", [id]))?;
    bd(tx.commit())
}

/// `leer_preferencia`.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn preferencia(db: &BaseDeDatos, clave: &str) -> NsResult<Option<serde_json::Value>> {
    let conn = db.conexion()?;
    let valor: Option<String> = bd(conn
        .query_row(
            "SELECT valor FROM dj_preferencias WHERE clave = ?1",
            [clave],
            |f| f.get(0),
        )
        .optional())?;
    Ok(valor.and_then(|v| serde_json::from_str(&v).ok()))
}

/// `guardar_preferencia`.
///
/// # Errors
///
/// [`NsError::InvalidInput`] con una clave vacía; [`NsError::StorageFailure`].
pub fn guardar_preferencia(
    db: &BaseDeDatos,
    clave: &str,
    valor: &serde_json::Value,
) -> NsResult<()> {
    if clave.trim().is_empty() {
        return Err(NsError::InvalidInput);
    }
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    bd(tx.execute(
        "INSERT INTO dj_preferencias (clave, valor) VALUES (?1, ?2)
         ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor,
             actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
        params![clave, valor.to_string()],
    ))?;
    bd(tx.commit())
}

/// Dónde iba la sesión que sonaba al cerrar (`dj_en_curso`). La pista se guarda por
/// su posición en la sesión, que no cambia, y no por su índice en el reproductor,
/// que cambia si se salta una pista ilegible: la V1 guardaba también el id de la
/// pista para no perderse por eso.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct EnCurso {
    pub sesion: i64,
    pub posicion: u32,
    pub segundos: f64,
    pub segundos_global: f64,
    pub volumen: f64,
}

/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn en_curso(db: &BaseDeDatos) -> NsResult<Option<EnCurso>> {
    let conn = db.conexion()?;
    let fila = bd(conn
        .query_row(
            "SELECT sesion_id, indice, posicion_seg, posicion_global_seg, volumen
             FROM dj_en_curso WHERE id = 1",
            [],
            |f| {
                Ok(f.get::<_, Option<i64>>(0)?.map(|sesion| EnCurso {
                    sesion,
                    posicion: f.get::<_, Option<u32>>(1).ok().flatten().unwrap_or(0),
                    segundos: f.get(2).unwrap_or(0.0),
                    segundos_global: f.get(3).unwrap_or(0.0),
                    volumen: f.get(4).unwrap_or(1.0),
                }))
            },
        )
        .optional())?;
    Ok(fila.flatten())
}

/// Guarda o, con `None`, olvida la sesión en curso. El volumen se conserva.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn guardar_en_curso(db: &BaseDeDatos, estado: Option<&EnCurso>) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    match estado {
        Some(e) => bd(tx.execute(
            "UPDATE dj_en_curso SET sesion_id = ?1, indice = ?2, posicion_seg = ?3,
                 posicion_global_seg = ?4, volumen = ?5 WHERE id = 1",
            params![
                e.sesion,
                e.posicion,
                e.segundos.max(0.0),
                e.segundos_global.max(0.0),
                e.volumen.clamp(0.0, 1.0)
            ],
        ))?,
        None => bd(tx.execute(
            "UPDATE dj_en_curso SET sesion_id = NULL, indice = NULL, posicion_seg = 0,
                 posicion_global_seg = 0 WHERE id = 1",
            [],
        ))?,
    };
    bd(tx.commit())
}
