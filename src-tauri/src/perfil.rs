//! Tu música (F2.2.8): lo que el historial local dice del usuario, con las
//! secciones de la V1 (`VistaPerfil.qml`): identidad, actividad, el ánimo del día,
//! los días activos del mes y los tops.
//!
//! Todo sale de `historial`, que la V2 trajo entero de la V1. Las horas y los días
//! se cuentan en la hora local del equipo (`'localtime'` de SQLite): la V1 los
//! guardaba en UTC, y la hora pico de alguien en Colombia no son las 23:00.

use serde::Serialize;
use ts_rs::TS;

use crate::biblioteca::{self, AlbumResumen, ArtistaResumen};
use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};
use crate::inicio::PistaEscuchada;

#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct ArtistaDelDia {
    #[ts(type = "number")]
    pub id: i64,
    pub nombre: String,
    pub escuchas: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct Perfil {
    pub reproducciones: u32,
    pub pistas_distintas: u32,
    pub pistas_en_biblioteca: u32,
    pub artistas_distintos: u32,
    pub albumes_distintos: u32,
    pub segundos_escuchados: f64,
    #[ts(type = "number | null")]
    pub anio_favorito: Option<i64>,
    /// De 0 a 23, en la hora local.
    pub hora_pico: Option<u32>,
    /// Escuchas de hoy y sus artistas, de más a menos.
    pub escuchas_hoy: u32,
    pub artistas_hoy: Vec<ArtistaDelDia>,
    /// Escuchas de cada día del mes en curso: el índice 0 es el día 1.
    pub dias_del_mes: Vec<u32>,
    pub top_canciones: Vec<PistaEscuchada>,
    pub top_albumes: Vec<AlbumResumen>,
    pub top_artistas: Vec<ArtistaResumen>,
}

fn uno<T: rusqlite::types::FromSql>(conn: &rusqlite::Connection, sql: &str) -> NsResult<T> {
    conn.query_row(sql, [], |f| f.get(0))
        .map_err(|_| NsError::StorageFailure)
}

fn pares(conn: &rusqlite::Connection, sql: &str) -> NsResult<Vec<(i64, i64)>> {
    let mut s = conn.prepare(sql).map_err(|_| NsError::StorageFailure)?;
    let filas = s
        .query_map([], |f| Ok((f.get(0)?, f.get(1)?)))
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(filas)
}

/// # Errors
///
/// [`NsError::StorageFailure`] si alguna consulta falla.
pub fn perfil(db: &BaseDeDatos) -> NsResult<Perfil> {
    let conn = db.conexion()?;
    let reproducciones: i64 = uno(&conn, "SELECT count(*) FROM historial")?;
    let pistas_distintas: i64 = uno(&conn, "SELECT count(DISTINCT pista_id) FROM historial")?;
    let pistas_en_biblioteca: i64 = uno(
        &conn,
        "SELECT count(*) FROM pistas WHERE estado = 'biblioteca'",
    )?;
    let artistas_distintos: i64 = uno(
        &conn,
        "SELECT count(DISTINCT p.artista_id) FROM historial h JOIN pistas p ON p.id = h.pista_id",
    )?;
    let albumes_distintos: i64 = uno(
        &conn,
        "SELECT count(DISTINCT p.album_id) FROM historial h JOIN pistas p ON p.id = h.pista_id",
    )?;
    // La V1 no apuntó cuánto se escuchó en más de la mitad de las filas: entonces
    // cuenta la duración de la pista, que es lo que la V1 sumaba.
    let segundos_escuchados: f64 = uno(
        &conn,
        "SELECT total(coalesce(h.escuchado_seg, p.duracion_seg, 0))
         FROM historial h LEFT JOIN pistas p ON p.id = h.pista_id",
    )?;
    let anio_favorito = pares(
        &conn,
        "SELECT p.anio, count(*) AS n FROM historial h JOIN pistas p ON p.id = h.pista_id
         WHERE p.anio IS NOT NULL GROUP BY p.anio ORDER BY n DESC, p.anio DESC LIMIT 1",
    )?
    .first()
    .map(|f| f.0);
    let hora_pico = pares(
        &conn,
        "SELECT CAST(strftime('%H', reproducida_en, 'localtime') AS INTEGER) AS h, count(*) AS n
         FROM historial GROUP BY h ORDER BY n DESC, h LIMIT 1",
    )?
    .first()
    .map(|f| f.0.clamp(0, 23) as u32);

    let hoy = "date(h.reproducida_en, 'localtime') = date('now', 'localtime')";
    let escuchas_hoy: i64 = uno(
        &conn,
        &format!("SELECT count(*) FROM historial h WHERE {hoy}"),
    )?;
    let artistas_hoy = {
        let mut s = conn
            .prepare(&format!(
                "SELECT a.id, a.nombre, count(*) AS n FROM historial h
                 JOIN pistas p ON p.id = h.pista_id JOIN artistas a ON a.id = p.artista_id
                 WHERE {hoy} GROUP BY a.id ORDER BY n DESC, a.nombre LIMIT 3"
            ))
            .map_err(|_| NsError::StorageFailure)?;
        let filas = s
            .query_map([], |f| {
                Ok(ArtistaDelDia {
                    id: f.get(0)?,
                    nombre: f.get(1)?,
                    escuchas: f.get::<_, i64>(2)? as u32,
                })
            })
            .map_err(|_| NsError::StorageFailure)?
            .collect::<rusqlite::Result<Vec<_>>>()
            .map_err(|_| NsError::StorageFailure)?;
        filas
    };

    let dias: i64 = uno(
        &conn,
        "SELECT CAST(strftime('%d', date('now', 'localtime', 'start of month', '+1 month', '-1 day')) AS INTEGER)",
    )?;
    let mut dias_del_mes = vec![0u32; dias.max(0) as usize];
    for (dia, n) in pares(
        &conn,
        "SELECT CAST(strftime('%d', reproducida_en, 'localtime') AS INTEGER), count(*) FROM historial
         WHERE strftime('%Y-%m', reproducida_en, 'localtime') = strftime('%Y-%m', 'now', 'localtime')
         GROUP BY 1",
    )? {
        if let Some(d) = dias_del_mes.get_mut((dia - 1).max(0) as usize) {
            *d = n as u32;
        }
    }

    let canciones = pares(
        &conn,
        "SELECT h.pista_id, count(*) AS n FROM historial h JOIN pistas p ON p.id = h.pista_id
         WHERE p.estado = 'biblioteca' GROUP BY h.pista_id ORDER BY n DESC, h.pista_id LIMIT 10",
    )?;
    let albumes = pares(
        &conn,
        "SELECT p.album_id, count(*) AS n FROM historial h JOIN pistas p ON p.id = h.pista_id
         WHERE p.album_id IS NOT NULL GROUP BY p.album_id ORDER BY n DESC, p.album_id LIMIT 10",
    )?;
    let artistas = pares(
        &conn,
        "SELECT p.artista_id, count(*) AS n FROM historial h JOIN pistas p ON p.id = h.pista_id
         WHERE p.artista_id IS NOT NULL GROUP BY p.artista_id ORDER BY n DESC, p.artista_id LIMIT 10",
    )?;
    drop(conn);

    let ids: Vec<i64> = canciones.iter().map(|f| f.0).collect();
    let top_canciones = biblioteca::resumenes(db, &ids)?
        .into_iter()
        .map(|pista| {
            let n = canciones
                .iter()
                .find(|f| f.0 == pista.id)
                .map_or(0, |f| f.1);
            PistaEscuchada {
                pista,
                reproducciones: n as u32,
            }
        })
        .collect();
    let top_albumes = albumes
        .iter()
        .filter_map(|(id, _)| biblioteca::album(db, *id).transpose())
        .collect::<NsResult<Vec<_>>>()?;
    let top_artistas = artistas
        .iter()
        .filter_map(|(id, _)| biblioteca::artista(db, *id).transpose())
        .collect::<NsResult<Vec<_>>>()?;

    Ok(Perfil {
        reproducciones: reproducciones as u32,
        pistas_distintas: pistas_distintas as u32,
        pistas_en_biblioteca: pistas_en_biblioteca as u32,
        artistas_distintos: artistas_distintos as u32,
        albumes_distintos: albumes_distintos as u32,
        segundos_escuchados,
        anio_favorito,
        hora_pico,
        escuchas_hoy: escuchas_hoy as u32,
        artistas_hoy,
        dias_del_mes,
        top_canciones,
        top_albumes,
        top_artistas,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sin_historial_todo_esta_a_cero() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let p = perfil(&db).unwrap();
        assert_eq!(p.reproducciones, 0);
        assert_eq!(p.anio_favorito, None);
        assert_eq!(p.hora_pico, None);
        assert!((28..=31).contains(&p.dias_del_mes.len()));
    }

    #[test]
    fn el_historial_da_la_identidad_la_actividad_y_los_tops() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'a', 'a'), (2, 'b', 'b');
                 INSERT INTO albumes (id, artista_id, titulo, clave) VALUES (10, 1, 'x', 'x');
                 INSERT INTO pistas (id, album_id, artista_id, titulo, ruta, duracion_seg, anio) VALUES
                     (1, 10, 1, 'uno', 'a', 100, 2020), (2, NULL, 2, 'dos', 'b', 200, 1999);
                 INSERT INTO historial (pista_id, escuchado_seg, reproducida_en) VALUES
                     (1, NULL, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                     (1, 50, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                     (2, NULL, '2000-01-01T00:00:00Z');",
            )
            .unwrap();
        let p = perfil(&db).unwrap();
        assert_eq!(
            (p.reproducciones, p.pistas_distintas, p.pistas_en_biblioteca),
            (3, 2, 2)
        );
        assert_eq!((p.artistas_distintos, p.albumes_distintos), (2, 1));
        assert_eq!(p.segundos_escuchados, 350.0, "sin dato, cuenta la duración");
        assert_eq!(p.anio_favorito, Some(2020));
        assert_eq!(p.escuchas_hoy, 2);
        assert_eq!(p.artistas_hoy[0].nombre, "a");
        assert_eq!(p.dias_del_mes.iter().sum::<u32>(), 2);
        assert_eq!(p.top_canciones[0].pista.id, 1);
        assert_eq!(p.top_canciones[0].reproducciones, 2);
        assert_eq!(p.top_artistas[0].id, 1);
    }
}
