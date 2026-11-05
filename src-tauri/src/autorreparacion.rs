//! Lo que la aplicación se repara sola al estrenar una versión.
//!
//! Cada servicio reintenta sus fallos pasajeros en el momento (el karaoke hasta
//! `karaoke::MAX_INTENTOS`, la importación hasta tres veces por archivo). Lo que
//! aun así quedó fallido puede deberse a un defecto que la versión nueva ya
//! corrige, como el del remuestreo del karaoke: la primera vez que arranca una
//! versión, se vuelve a intentar todo eso una vez, sin que nadie tenga que
//! pulsar nada. Las siguientes veces no, para no repetir en cada arranque lo que
//! falla por el propio archivo.

use std::path::PathBuf;

use rusqlite::OptionalExtension;

use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};

const CLAVE: &str = "autorreparacion_version";

/// `true` la primera vez que se llama con esta versión de la aplicación, y la
/// deja apuntada.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base no responde.
pub fn estrena_version(db: &BaseDeDatos, version: &str) -> NsResult<bool> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    let anterior: Option<String> = tx
        .query_row(
            "SELECT valor FROM preferencias WHERE clave = ?1",
            [CLAVE],
            |f| f.get(0),
        )
        .optional()
        .map_err(|_| NsError::StorageFailure)?;
    let actual = serde_json::Value::from(version).to_string();
    if anterior.as_deref() == Some(actual.as_str()) {
        return Ok(false);
    }
    tx.execute(
        "INSERT INTO preferencias (clave, valor) VALUES (?1, ?2)
         ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor",
        [CLAVE, actual.as_str()],
    )
    .map_err(|_| NsError::StorageFailure)?;
    tx.commit().map_err(|_| NsError::StorageFailure)?;
    Ok(true)
}

/// Los archivos de Por revisar que llegaron ahí por un fallo al escribir o uno
/// inesperado, no por lo que son: se devuelven a la importación. Los marca
/// resueltos; si vuelven a fallar, la importación los registra de nuevo.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base no responde.
pub fn por_revisar_reintentables(db: &BaseDeDatos) -> NsResult<Vec<PathBuf>> {
    let ids: Vec<i64> = {
        let conn = db.conexion()?;
        let mut s = conn
            .prepare(
                "SELECT id FROM por_revisar
                 WHERE causa = 'escritura_fallida' AND resuelto_en IS NULL",
            )
            .map_err(|_| NsError::StorageFailure)?;
        let filas = s
            .query_map([], |f| f.get(0))
            .map_err(|_| NsError::StorageFailure)?
            .collect::<rusqlite::Result<Vec<_>>>()
            .map_err(|_| NsError::StorageFailure)?;
        filas
    };
    Ok(ids
        .into_iter()
        .filter_map(|id| crate::catalogo::por_revisar::para_reintentar(db, id).ok())
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cada_version_se_estrena_una_sola_vez() {
        let db = BaseDeDatos::en_memoria().unwrap();
        assert!(estrena_version(&db, "2.0.7").unwrap());
        assert!(!estrena_version(&db, "2.0.7").unwrap());
        assert!(estrena_version(&db, "2.0.8").unwrap());
    }

    #[test]
    fn solo_vuelve_lo_que_fallo_al_escribir() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO por_revisar (id, ruta, causa) VALUES
                     (1, '/tmp/a.mp3', 'escritura_fallida'),
                     (2, '/tmp/b.mp3', 'duplicado'),
                     (3, '/tmp/c.mp3', 'audio_ilegible');",
            )
            .unwrap();
        let rutas = por_revisar_reintentables(&db).unwrap();
        assert_eq!(rutas, [PathBuf::from("/tmp/a.mp3")]);
        assert!(
            por_revisar_reintentables(&db).unwrap().is_empty(),
            "queda resuelto"
        );
    }

    #[test]
    fn las_fallidas_del_karaoke_vuelven_a_la_cola_desde_cero() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO pistas (id, titulo, ruta) VALUES (1, 'uno', 'a.mp3'), (2, 'dos', 'b.mp3');
                 INSERT INTO stems (pista_id, estado, intentos, error) VALUES
                     (1, 'fallida', 7, 'INTERNAL'), (2, 'pendiente', 1, NULL);",
            )
            .unwrap();
        crate::karaoke::reintentar_fallidas(&db).unwrap();
        let (estado, intentos): (String, i64) = db
            .conexion()
            .unwrap()
            .query_row(
                "SELECT estado, intentos FROM stems WHERE pista_id = 1",
                [],
                |f| Ok((f.get(0)?, f.get(1)?)),
            )
            .unwrap();
        assert_eq!((estado.as_str(), intentos), ("pendiente", 0));
    }
}
