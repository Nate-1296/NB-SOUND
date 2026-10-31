//! De qué canciones sale cada modo: `servicios/explorador_ciego/selectores.py`.
//!
//! Cada modo tiene su universo. Por la portada, las que tienen una que ver; por el
//! audio, las de más de 30 segundos; redescubrir, las favoritas o escuchadas, de la
//! que hace más tiempo que no suena a la más reciente; y "nunca la eliges", las que
//! nunca sonaron (o, si no hay, las que menos). Se toman como mucho 400, al azar
//! salvo en redescubrir, que va por antigüedad.

use super::Modo;
use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};

const TOPE: u32 = 400;

/// Una canción candidata, con lo que el juego puede llegar a revelar.
#[derive(Debug, Clone, PartialEq)]
pub struct Candidata {
    pub id: i64,
    pub titulo: String,
    pub artista: String,
    pub album: String,
    pub anio: Option<i64>,
    pub artista_id: Option<i64>,
    pub album_id: Option<i64>,
    pub duracion_seg: f64,
    pub tiene_portada: bool,
    pub reproducciones: i64,
    pub favorita: bool,
}

const DESDE: &str = "FROM pistas p
     LEFT JOIN albumes a ON a.id = p.album_id
     LEFT JOIN (SELECT pista_id, count(*) AS n, max(reproducida_en) AS ultima
                FROM historial GROUP BY pista_id) h ON h.pista_id = p.id
     WHERE p.estado = 'biblioteca'";

fn condicion(modo: Modo) -> &'static str {
    match modo {
        Modo::Portada => "AND coalesce(p.portada_id, a.portada_id) IS NOT NULL",
        Modo::Audio => "AND coalesce(p.duracion_seg, 0) > 30",
        Modo::Redescubrimiento => "AND (p.favorita = 1 OR coalesce(h.n, p.reproducciones, 0) > 0)",
        Modo::NuncaEliges => "AND coalesce(h.n, 0) = 0 AND p.reproducciones = 0",
    }
}

fn orden(modo: Modo) -> &'static str {
    match modo {
        Modo::Redescubrimiento => {
            "ORDER BY coalesce(h.ultima, p.ultima_reproduccion, p.creada_en) ASC,
                      coalesce(h.n, p.reproducciones, 0) DESC"
        }
        _ => "ORDER BY random()",
    }
}

fn leer(db: &BaseDeDatos, condicion: &str, orden: &str) -> NsResult<Vec<Candidata>> {
    let conn = db.conexion()?;
    let sql = format!(
        "SELECT p.id, p.titulo, p.artista_nombre, p.album_titulo, coalesce(p.anio, a.anio),
                p.artista_id, p.album_id, coalesce(p.duracion_seg, 0),
                coalesce(p.portada_id, a.portada_id) IS NOT NULL,
                coalesce(h.n, p.reproducciones, 0), p.favorita
         {DESDE} {condicion} {orden} LIMIT {TOPE}"
    );
    let mut s = conn.prepare(&sql).map_err(|_| NsError::StorageFailure)?;
    let filas = s
        .query_map([], |f| {
            Ok(Candidata {
                id: f.get(0)?,
                titulo: f.get(1)?,
                artista: f.get(2)?,
                album: f.get(3)?,
                anio: f.get(4)?,
                artista_id: f.get(5)?,
                album_id: f.get(6)?,
                duracion_seg: f.get(7)?,
                tiene_portada: f.get(8)?,
                reproducciones: f.get(9)?,
                favorita: f.get(10)?,
            })
        })
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(filas)
}

/// `candidatos_para`. Cota: 400.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn candidatas(db: &BaseDeDatos, modo: Modo) -> NsResult<Vec<Candidata>> {
    let c = leer(db, condicion(modo), orden(modo))?;
    if c.is_empty() && modo == Modo::NuncaEliges {
        // Una biblioteca muy escuchada no tiene cola larga: las menos escuchadas.
        return leer(
            db,
            "AND coalesce(h.n, p.reproducciones, 0) <= 2",
            "ORDER BY coalesce(h.n, p.reproducciones, 0) ASC, random()",
        );
    }
    Ok(c)
}

/// `contar_disponibles`: cuántas hay sin leerlas.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn disponibles(db: &BaseDeDatos, modo: Modo) -> NsResult<u32> {
    let conn = db.conexion()?;
    conn.query_row(
        &format!("SELECT count(*) {DESDE} {}", condicion(modo)),
        [],
        |f| f.get(0),
    )
    .map_err(|_| NsError::StorageFailure)
}
