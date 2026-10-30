//! Búsqueda de pistas sobre el índice FTS5 (F1.3.1).
//!
//! El texto del usuario nunca llega al motor tal cual: la sintaxis de FTS5
//! (`AND`, `NEAR`, comillas, `*`, `-`) convertiría una búsqueda como `AC/DC` o
//! `"Hey` en un error de sintaxis. Cada palabra se cita y se busca como prefijo,
//! que es lo que espera quien escribe en una caja de búsqueda.

use rusqlite::Connection;

use crate::error::{NsError, NsResult};

/// Tope de palabras: una búsqueda pegada con un párrafo entero no puede convertirse
/// en una consulta de cien términos.
const MAX_PALABRAS: usize = 8;

/// Convierte lo que escribió el usuario en una consulta FTS5 segura: cada palabra
/// entre comillas y como prefijo, todas obligatorias. `None` si no queda nada que
/// buscar.
pub fn consulta(texto: &str) -> Option<String> {
    let palabras: Vec<String> = texto
        .split(|c: char| !c.is_alphanumeric())
        .filter(|p| !p.is_empty())
        .take(MAX_PALABRAS)
        // Una sola letra como prefijo coincide con media biblioteca y no ayuda a
        // encontrar nada; se busca como palabra entera ("a", "y").
        .map(|p| {
            if p.chars().count() < 2 {
                format!("\"{p}\"")
            } else {
                format!("\"{p}\"*")
            }
        })
        .collect();
    (!palabras.is_empty()).then(|| palabras.join(" "))
}

/// Los `id` de las pistas visibles que coinciden, de más a menos relevante.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn buscar(conn: &Connection, texto: &str, limite: u32) -> NsResult<Vec<i64>> {
    let Some(consulta) = consulta(texto) else {
        return Ok(Vec::new());
    };
    let mut sentencia = conn
        // `rank` es el `bm25` con los pesos que fija la migración V7.
        .prepare_cached(
            "SELECT b.rowid FROM busqueda b JOIN pistas p ON p.id = b.rowid
             WHERE busqueda MATCH ?1 AND p.estado = 'biblioteca'
             ORDER BY b.rank LIMIT ?2",
        )
        .map_err(|_| NsError::StorageFailure)?;
    let filas = sentencia
        .query_map(rusqlite::params![consulta, limite], |f| f.get(0))
        .map_err(|error| {
            tracing::error!(error = %error, "falló una búsqueda");
            NsError::StorageFailure
        })?;
    filas
        .collect::<rusqlite::Result<_>>()
        .map_err(|_| NsError::StorageFailure)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::BaseDeDatos;

    fn base() -> BaseDeDatos {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'Maná', 'mana'), (2, 'AC/DC', 'acdc');
                 INSERT INTO pistas (id, artista_id, titulo, artista_nombre, album_titulo, ruta) VALUES
                     (1, 1, 'Rayando el sol', 'Maná', 'Falta amor', 'a'),
                     (2, 1, 'Clavado en un bar', 'Maná', 'Sueños líquidos', 'b'),
                     (3, 2, 'Back in Black', 'AC/DC', 'Back in Black', 'c'),
                     (4, 2, 'Highway to Hell', 'AC/DC', 'Highway to Hell', 'd');
                 INSERT INTO letras (pista_id, planas) VALUES (2, 'me dejaste en un bar, solo');",
            )
            .unwrap();
        db
    }

    fn ids(db: &BaseDeDatos, texto: &str) -> Vec<i64> {
        buscar(&db.conexion().unwrap(), texto, 50).unwrap()
    }

    #[test]
    fn las_tildes_no_hacen_falta() {
        let db = base();
        assert_eq!(ids(&db, "mana rayando"), [1]);
        assert_eq!(ids(&db, "SUEÑOS liquidos"), [2]);
    }

    #[test]
    fn se_busca_mientras_se_escribe() {
        let db = base();
        assert_eq!(ids(&db, "ray"), [1]);
        assert_eq!(ids(&db, "hi"), [4]);
    }

    #[test]
    fn la_sintaxis_de_fts5_no_rompe_la_busqueda() {
        let db = base();
        assert_eq!(ids(&db, "AC/DC back").len(), 1);
        for raro in ["\"hey", "NEAR(", "a AND", "-", "*", "()", "   "] {
            assert!(buscar(&db.conexion().unwrap(), raro, 10).is_ok(), "{raro}");
        }
    }

    #[test]
    fn un_titulo_pesa_mas_que_una_letra() {
        let db = base();
        db.conexion()
            .unwrap()
            .execute(
                "INSERT INTO pistas (id, artista_id, titulo, artista_nombre, ruta) VALUES (5, 1, 'Bar', 'Maná', 'e')",
                [],
            )
            .unwrap();
        assert_eq!(ids(&db, "bar"), [5, 2]);
    }

    #[test]
    fn el_indice_sigue_a_las_pistas_y_sus_letras() {
        let db = base();
        let conn = db.conexion().unwrap();
        assert_eq!(ids(&db, "dejaste"), [2]);
        conn.execute(
            "UPDATE letras SET planas = 'otra cosa' WHERE pista_id = 2",
            [],
        )
        .unwrap();
        assert!(ids(&db, "dejaste").is_empty());
        conn.execute(
            "UPDATE pistas SET titulo = 'Thunderstruck' WHERE id = 4",
            [],
        )
        .unwrap();
        assert_eq!(ids(&db, "thunder"), [4]);
        assert_eq!(ids(&db, "highway"), [4], "el álbum sigue llamándose así");
        conn.execute("DELETE FROM pistas WHERE id = 2", []).unwrap();
        assert!(ids(&db, "otra").is_empty());
        conn.execute("UPDATE pistas SET estado = 'duplicado' WHERE id = 1", [])
            .unwrap();
        assert!(
            ids(&db, "rayando").is_empty(),
            "las duplicadas no se encuentran"
        );
    }

    /// El criterio de F1.3.1: con 100.000 pistas, una búsqueda responde en menos
    /// de 30 ms. El vocabulario sigue una distribución de Zipf, como el de una
    /// biblioteca real: unas pocas palabras ("amor", "love") salen en miles de
    /// títulos y la mayoría en muy pocos. Se mide la peor de varias consultas,
    /// incluidas las de las palabras más frecuentes, que son las caras.
    #[test]
    fn cien_mil_pistas_se_buscan_en_menos_de_30_ms() {
        let mut semilla = 0x2545_f491_4f6c_dd1d_u64;
        let mut palabra = move || {
            semilla ^= semilla << 13;
            semilla ^= semilla >> 7;
            semilla ^= semilla << 17;
            let u = (semilla >> 11) as f64 / (1u64 << 53) as f64;
            // Zipf aproximado sobre 20.000 palabras: el rango crece como u^4.
            format!("p{}", (20_000.0 * u.powi(4)) as u32)
        };
        let db = BaseDeDatos::en_memoria().unwrap();
        let mut conn = db.conexion().unwrap();
        {
            let tx = crate::db::transaccion_de_escritura(&mut conn).unwrap();
            for a in 1..=1000 {
                tx.execute(
                    "INSERT INTO artistas (id, nombre, clave) VALUES (?1, ?2, ?2)",
                    rusqlite::params![a, format!("artista {a}")],
                )
                .unwrap();
            }
            let mut insertar = tx
                .prepare(
                    "INSERT INTO pistas (id, artista_id, titulo, artista_nombre, album_titulo, ruta)
                     VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
                )
                .unwrap();
            for i in 1..=100_000_i64 {
                let titulo = format!("{} {} {}", palabra(), palabra(), palabra());
                let album = format!("{} {}", palabra(), palabra());
                insertar
                    .execute(rusqlite::params![
                        i,
                        i % 1000 + 1,
                        titulo,
                        format!("artista {}", i % 1000 + 1),
                        album,
                        format!("{i}.mp3"),
                    ])
                    .unwrap();
            }
            drop(insertar);
            tx.commit().unwrap();
        }
        let mut peor = std::time::Duration::ZERO;
        for texto in [
            "a",
            "am",
            "amor",
            "noche luna",
            "artista 512",
            "corazon de fuego",
            "zzz",
        ] {
            let inicio = std::time::Instant::now();
            let _ = buscar(&conn, texto, 50).unwrap();
            peor = peor.max(inicio.elapsed());
        }
        assert!(peor.as_millis() < 30, "la peor búsqueda tardó {peor:?}");
    }
}
