//! Completar en segundo plano lo que le falta a la biblioteca (A9 de la revisión
//! de producto, pedido por Nathan el 2026-11-09).
//!
//! Una importación puede fallar a medias (la red cae, un servicio no responde) sin
//! que el dato falte en el servicio, y una biblioteca que llega de otra instalación
//! entra sin portadas ni letras. Este hilo recorre, sin prisa y con la prioridad
//! baja, las pistas sin portada, sin letra o con su artista sin imagen, y les pasa
//! lo mismo que "Completar datos" ([`completar_datos`]): las mismas fuentes, la
//! misma puerta de red y el mismo consentimiento. Con la conexión general apagada
//! no hace nada; lo que no encuentra lo vuelve a intentar pasado un mes.

use std::sync::Arc;
use std::time::Duration;

use crate::catalogo::completar_datos::completar_datos;
use crate::catalogo::importacion::Importador;
use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};
use crate::net::Red;

/// Tras abrir, lo primero es la ventana, lo que suena y la copia del día.
const ESPERA_INICIAL: Duration = Duration::from_secs(300);
/// Entre una pista y la siguiente: los servicios piden no más de una petición por
/// segundo y cada pista puede hacer varias.
const ENTRE_PISTAS: Duration = Duration::from_secs(2);
/// Sin nada que hacer, o con la red apagada, se vuelve a mirar al rato.
const DESCANSO: Duration = Duration::from_secs(6 * 3600);
const POR_TANDA: i64 = 200;

/// Las pistas a las que les falta algo y que no se intentaron en el último mes.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn pendientes(db: &BaseDeDatos, limite: i64) -> NsResult<Vec<i64>> {
    let conn = db.conexion()?;
    let mut s = conn
        .prepare(
            "SELECT p.id FROM pistas p
               LEFT JOIN albumes a ON a.id = p.album_id
               LEFT JOIN artistas ar ON ar.id = p.artista_id
               LEFT JOIN completado_fondo c ON c.pista_id = p.id
              WHERE p.estado = 'biblioteca'
                AND (coalesce(p.portada_id, a.portada_id) IS NULL
                     OR NOT EXISTS (SELECT 1 FROM letras l WHERE l.pista_id = p.id)
                     OR (p.artista_id IS NOT NULL AND ar.imagen_id IS NULL))
                AND (c.intentado_en IS NULL
                     OR c.intentado_en < strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-30 days'))
              ORDER BY p.id
              LIMIT ?1",
        )
        .map_err(|_| NsError::StorageFailure)?;
    let ids = s
        .query_map([limite], |f| f.get(0))
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<Vec<i64>>>()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(ids)
}

/// Apunta que la pista se intentó ahora, haya salido algo o no.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede escribir.
pub fn apuntar(db: &BaseDeDatos, pista: i64) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    tx.execute(
        "INSERT INTO completado_fondo (pista_id, intentado_en)
         VALUES (?1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
         ON CONFLICT (pista_id) DO UPDATE SET intentado_en = excluded.intentado_en",
        [pista],
    )
    .map_err(|_| NsError::StorageFailure)?;
    tx.commit().map_err(|_| NsError::StorageFailure)
}

/// Arranca el hilo. `avisar` se llama al terminar una tanda que añadió algo, para
/// que las vistas abiertas se refresquen.
pub fn arrancar(
    db: BaseDeDatos,
    red: Arc<Red>,
    importador: Importador,
    avisar: impl Fn() + Send + 'static,
) {
    let lanzado = std::thread::Builder::new()
        .name("completar-fondo".into())
        .spawn(move || {
            crate::prioridad::bajar_hilo_actual();
            std::thread::sleep(ESPERA_INICIAL);
            loop {
                if !red.politica().general {
                    std::thread::sleep(DESCANSO);
                    continue;
                }
                let ids = pendientes(&db, POR_TANDA).unwrap_or_default();
                if ids.is_empty() {
                    std::thread::sleep(DESCANSO);
                    continue;
                }
                let mut anadidos = 0usize;
                for id in ids {
                    // Si se apaga la red a mitad, la tanda para sin apuntar lo que
                    // no se llegó a intentar.
                    if !red.politica().general {
                        break;
                    }
                    let hecho = importador.con_entorno(|e| completar_datos(e, id));
                    if hecho.is_ok_and(|d| d.identificada || d.portada || d.letra) {
                        anadidos += 1;
                    }
                    let _ = apuntar(&db, id);
                    std::thread::sleep(ENTRE_PISTAS);
                }
                tracing::info!(anadidos, "tanda de completar en segundo plano");
                if anadidos > 0 {
                    avisar();
                }
            }
        })
        .is_ok();
    if !lanzado {
        tracing::error!("no se pudo lanzar el completado en segundo plano");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn solo_vuelve_a_lo_que_le_falta_algo_y_no_antes_de_un_mes() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO portadas (id, sha256, ruta, ancho, alto, bytes, mime, origen)
                     VALUES (1, printf('%064d', 0), 'a.jpg', 1, 1, 1, 'image/jpeg', 'etiqueta');
                 INSERT INTO artistas (id, nombre, clave, imagen_id) VALUES (1, 'a', 'a', 1),
                                                                          (2, 'b', 'b', NULL);
                 INSERT INTO albumes (id, artista_id, titulo, clave, portada_id) VALUES (1, 1, 'x', 'x', 1);
                 -- Completa: portada del álbum, letra e imagen del artista.
                 INSERT INTO pistas (id, artista_id, album_id, titulo, ruta) VALUES (1, 1, 1, 'uno', '1.mp3');
                 INSERT INTO letras (pista_id, planas) VALUES (1, 'la');
                 -- Sin letra.
                 INSERT INTO pistas (id, artista_id, album_id, titulo, ruta) VALUES (2, 1, 1, 'dos', '2.mp3');
                 -- Con todo menos la imagen del artista.
                 INSERT INTO pistas (id, artista_id, album_id, titulo, ruta) VALUES (3, 2, 1, 'tres', '3.mp3');
                 INSERT INTO letras (pista_id, planas) VALUES (3, 'la');
                 -- Sin nada, pero intentada hace dos meses.
                 INSERT INTO pistas (id, titulo, ruta) VALUES (4, 'cuatro', '4.mp3');
                 INSERT INTO completado_fondo VALUES (4, strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-60 days'));
                 -- Sin nada, intentada ayer.
                 INSERT INTO pistas (id, titulo, ruta) VALUES (5, 'cinco', '5.mp3');
                 INSERT INTO completado_fondo VALUES (5, strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-1 days'));",
            )
            .unwrap();
        assert_eq!(pendientes(&db, 100).unwrap(), [2, 3, 4]);
        apuntar(&db, 2).unwrap();
        assert_eq!(pendientes(&db, 100).unwrap(), [3, 4]);
    }
}
