//! Consultas de la biblioteca para la interfaz.
//!
//! Solo lectura. Toda lista que devuelve tiene un tope, aunque hoy quepa entera
//! (`check-listas`): con 2.397 pistas no se nota y con 100.000 sí.

use serde::Serialize;
use ts_rs::TS;

use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};

/// Lo que se pinta de una pista en la barra, la cola y las listas.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
// Los `id` caben de sobra en un `number` de JavaScript: se tipan así y no como
// `bigint`, que obligaría a convertir en cada comparación.
pub struct PistaResumen {
    #[ts(type = "number")]
    pub id: i64,
    pub titulo: String,
    pub artista: String,
    pub album: String,
    #[ts(type = "number | null")]
    pub album_id: Option<i64>,
    #[ts(type = "number | null")]
    pub artista_id: Option<i64>,
    pub duracion_seg: f64,
    #[ts(type = "number | null")]
    pub anio: Option<i64>,
    pub favorita: bool,
    pub verificada: bool,
    pub tiene_portada: bool,
}

/// Tope de pistas por petición de resúmenes: una ventana de la lista virtual o una
/// cola. Una cola más larga se pide en tramos.
pub const MAX_RESUMENES: usize = 500;

/// Resúmenes de las pistas pedidas, en el mismo orden; las que no existen se
/// omiten.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn resumenes(db: &BaseDeDatos, ids: &[i64]) -> NsResult<Vec<PistaResumen>> {
    let ids = &ids[..ids.len().min(MAX_RESUMENES)];
    if ids.is_empty() {
        return Ok(Vec::new());
    }
    let conn = db.conexion()?;
    let json = serde_json::to_string(ids).map_err(|_| NsError::Internal)?;
    let mut s = conn
        .prepare_cached(
            "SELECT p.id, p.titulo, p.artista_nombre, p.album_titulo, p.album_id, p.artista_id,
                    coalesce(p.duracion_seg, 0), p.anio, p.favorita, p.verificada,
                    coalesce(p.portada_id, a.portada_id) IS NOT NULL
             FROM json_each(?1) j
             JOIN pistas p ON p.id = j.value
             LEFT JOIN albumes a ON a.id = p.album_id
             ORDER BY j.key",
        )
        .map_err(|_| NsError::StorageFailure)?;
    let filas = s
        .query_map([json], |f| {
            Ok(PistaResumen {
                id: f.get(0)?,
                titulo: f.get(1)?,
                artista: f.get(2)?,
                album: f.get(3)?,
                album_id: f.get(4)?,
                artista_id: f.get(5)?,
                duracion_seg: f.get(6)?,
                anio: f.get(7)?,
                favorita: f.get(8)?,
                verificada: f.get(9)?,
                tiene_portada: f.get(10)?,
            })
        })
        .map_err(|_| NsError::StorageFailure)?;
    filas
        .collect::<rusqlite::Result<_>>()
        .map_err(|_| NsError::StorageFailure)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn los_resumenes_salen_en_el_orden_pedido_y_sin_los_que_faltan() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'a', 'a');
                 INSERT INTO pistas (id, artista_id, titulo, artista_nombre, ruta) VALUES
                     (1, 1, 'uno', 'a', 'x1'), (2, 1, 'dos', 'a', 'x2'), (3, 1, 'tres', 'a', 'x3');",
            )
            .unwrap();
        let r = resumenes(&db, &[3, 99, 1]).unwrap();
        assert_eq!(r.iter().map(|p| p.id).collect::<Vec<_>>(), [3, 1]);
        assert_eq!(r[0].titulo, "tres");
        assert!(!r[0].tiene_portada);
    }

    #[test]
    fn una_peticion_desmesurada_se_recorta_al_tope() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let ids: Vec<i64> = (1..=10_000).collect();
        assert!(resumenes(&db, &ids).unwrap().is_empty());
    }
}
