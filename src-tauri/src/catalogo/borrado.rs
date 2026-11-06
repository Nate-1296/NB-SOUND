//! Quitar canciones de la biblioteca: una a una (`eliminar_pista`,
//! `servicios/biblioteca.py`) o las que la deduplicación ya apartó.
//!
//! **El archivo va a la papelera del sistema, nunca se borra del todo**, igual que
//! descartar desde Por revisar (enmienda de ADR-007; ADR-002): un clic equivocado se
//! deshace desde el gestor de archivos.
//!
//! **Lo demás lo hace la base.** Las claves foráneas borran en cascada letras,
//! rasgos, sonoridad, stems, posiciones en playlists y en sesiones del DJ, y la
//! cola guardada; los disparadores sacan la pista del índice de búsqueda y dejan
//! la marca de borrado que recibe NB Sound Mobile (ADR-005). Lo que la base no
//! alcanza son los archivos: el audio, el instrumental del karaoke y el álbum o el
//! artista que se queden sin nada.

use std::path::{Path, PathBuf};

use rusqlite::OptionalExtension;
use serde::Serialize;
use ts_rs::TS;

use super::canalizacion::bd;
use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};
use crate::paths::Rutas;

/// Lo que hay que saber de una pista antes de borrarla: después ya no está.
struct Borrable {
    ruta: String,
    album_id: Option<i64>,
    artista_id: Option<i64>,
    instrumental: Option<String>,
}

fn leer(tx: &rusqlite::Transaction<'_>, pista: i64) -> NsResult<Option<Borrable>> {
    bd(tx
        .query_row(
            "SELECT p.ruta, p.album_id, p.artista_id, s.instrumental
             FROM pistas p LEFT JOIN stems s ON s.pista_id = p.id
             WHERE p.id = ?1",
            [pista],
            |f| {
                Ok(Borrable {
                    ruta: f.get(0)?,
                    album_id: f.get(1)?,
                    artista_id: f.get(2)?,
                    instrumental: f.get(3)?,
                })
            },
        )
        .optional())
}

/// Borra la fila y lo que se queda vacío por ella. El álbum se mira antes que el
/// artista: un artista con un álbum vacío todavía no está vacío.
fn borrar_fila(tx: &rusqlite::Transaction<'_>, pista: i64, b: &Borrable) -> NsResult<()> {
    bd(tx.execute("DELETE FROM pistas WHERE id = ?1", [pista]))?;
    if let Some(a) = b.album_id {
        bd(tx.execute(
            "DELETE FROM albumes WHERE id = ?1
             AND NOT EXISTS (SELECT 1 FROM pistas WHERE album_id = ?1)",
            [a],
        ))?;
    }
    if let Some(a) = b.artista_id {
        bd(tx.execute(
            "DELETE FROM artistas WHERE id = ?1
             AND NOT EXISTS (SELECT 1 FROM pistas WHERE artista_id = ?1)
             AND NOT EXISTS (SELECT 1 FROM albumes WHERE artista_id = ?1)",
            [a],
        ))?;
    }
    Ok(())
}

/// Manda un archivo a la papelera. Solo si está dentro de `carpeta`: la ruta sale
/// de la base y se comprueba igual, como todo lo que se toca en disco. Un archivo
/// que ya no existe no es un error: el usuario quería que no estuviera.
fn a_la_papelera(carpeta: &Path, relativa: &str) -> NsResult<()> {
    let Ok(archivo) = crate::security::resolve_within(carpeta, Path::new(relativa)) else {
        return Ok(());
    };
    if !archivo.is_file() {
        return Ok(());
    }
    trash::delete(&archivo).map_err(|error| {
        tracing::error!(error = %error, "la papelera no aceptó un archivo");
        NsError::StorageFailure
    })
}

/// El instrumental es un derivado: no tiene sentido sin la pista y se puede
/// rehacer, así que se borra del todo en vez de llenar la papelera.
fn borrar_instrumental(rutas: &Rutas, relativa: Option<&str>) {
    let Some(relativa) = relativa else { return };
    if let Ok(archivo) = crate::security::resolve_within(&rutas.stems(), Path::new(relativa)) {
        let _ = std::fs::remove_file(archivo);
    }
}

/// Quita una pista de la biblioteca y, si `con_archivo`, manda su audio a la
/// papelera. Si la papelera no acepta el archivo, la pista se queda donde estaba:
/// nada a medias.
///
/// # Errors
///
/// [`NsError::FileNotFound`] si la pista no existe; [`NsError::StorageFailure`] si
/// la base o la papelera fallan.
pub fn borrar_pista(
    db: &BaseDeDatos,
    rutas: &Rutas,
    musica: Option<&Path>,
    pista: i64,
    con_archivo: bool,
) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    let b = leer(&tx, pista)?.ok_or(NsError::FileNotFound)?;
    borrar_fila(&tx, pista, &b)?;
    // El archivo, antes de confirmar: si falla, la transacción se deshace sola.
    if con_archivo {
        a_la_papelera(musica.ok_or(NsError::StorageFailure)?, &b.ruta)?;
    }
    bd(tx.commit())?;
    borrar_instrumental(rutas, b.instrumental.as_deref());
    tracing::info!(
        pista,
        // no es del usuario: solo dice si se pidió la papelera.
        con_archivo,
        "pista quitada de la biblioteca"
    );
    Ok(())
}

/// Las canciones que la deduplicación apartó (`estado = 'duplicado'`): copias que
/// ya tienen su original en la biblioteca y que ni se ven ni van al móvil.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct ResumenDuplicados {
    pub total: u32,
    /// Lo que ocupan sus archivos.
    #[ts(type = "number")]
    pub bytes: u64,
}

/// Cuántas copias apartadas hay y cuánto ocupan.
///
/// Solo cuenta lo que la deduplicación decidió, con sus tres ejes (`duplicados.rs`).
/// Se descartó adivinar duplicados por título, artista y duración: en la biblioteca
/// real eso junta 23 grupos de canciones distintas (la versión del álbum y la del
/// recopilatorio duran lo mismo), y limpiar a partir de ahí borraría música.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn duplicados(db: &BaseDeDatos) -> NsResult<ResumenDuplicados> {
    let (total, bytes): (i64, i64) = bd(db.conexion()?.query_row(
        "SELECT count(*), coalesce(sum(tamano), 0) FROM pistas WHERE estado = 'duplicado'",
        [],
        |f| Ok((f.get(0)?, f.get(1)?)),
    ))?;
    Ok(ResumenDuplicados {
        total: u32::try_from(total).unwrap_or(u32::MAX),
        bytes: u64::try_from(bytes).unwrap_or(0),
    })
}

/// Quita de la biblioteca las copias apartadas y, si `con_archivos`, manda sus
/// archivos a la papelera. Devuelve cuántas se quitaron. Una copia cuyo archivo
/// la papelera no acepta se queda, y se sigue con las demás.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base falla.
pub fn limpiar_duplicados(
    db: &BaseDeDatos,
    rutas: &Rutas,
    musica: Option<&Path>,
    con_archivos: bool,
) -> NsResult<u32> {
    let ids: Vec<i64> = {
        let conn = db.conexion()?;
        let mut s = bd(conn.prepare("SELECT id FROM pistas WHERE estado = 'duplicado'"))?;
        let filas = bd(s.query_map([], |f| f.get(0)))?;
        bd(filas.collect::<rusqlite::Result<_>>())?
    };
    let mut quitadas = 0u32;
    for id in ids {
        match borrar_pista(db, rutas, musica, id, con_archivos) {
            Ok(()) => quitadas += 1,
            // Ya no estaba, o su archivo no se pudo mover: se sigue con las demás.
            Err(NsError::FileNotFound | NsError::StorageFailure) => {}
            Err(otro) => return Err(otro),
        }
    }
    Ok(quitadas)
}

/// Dónde está el archivo de una pista, para enseñarlo en el gestor de archivos.
/// Dentro de la carpeta de la música, o donde diga la base si es absoluta.
///
/// # Errors
///
/// [`NsError::FileNotFound`] si la pista o su archivo no existen.
pub fn archivo_de(db: &BaseDeDatos, musica: Option<&Path>, pista: i64) -> NsResult<PathBuf> {
    let ruta: String = bd(db
        .conexion()?
        .query_row("SELECT ruta FROM pistas WHERE id = ?1", [pista], |f| {
            f.get(0)
        })
        .optional())?
    .ok_or(NsError::FileNotFound)?;
    let relativa = Path::new(&ruta);
    let archivo = match musica {
        Some(m) if relativa.is_relative() => crate::security::resolve_within(m, relativa)?,
        _ => relativa.canonicalize().map_err(|_| NsError::FileNotFound)?,
    };
    if archivo.is_file() {
        Ok(archivo)
    } else {
        Err(NsError::FileNotFound)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entorno(nombre: &str) -> (PathBuf, Rutas, PathBuf, BaseDeDatos) {
        let d = std::env::temp_dir().join(format!("ns-borrado-{nombre}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        let rutas = Rutas::bajo(&d).unwrap();
        let musica = d.join("musica");
        std::fs::create_dir_all(&musica).unwrap();
        let musica = musica.canonicalize().unwrap();
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'Maná', 'mana'), (2, 'Solo', 'solo');
                 INSERT INTO albumes (id, artista_id, titulo, clave) VALUES (10, 1, 'Sueños', 's'), (20, 2, 'Único', 'u');
                 INSERT INTO pistas (id, album_id, artista_id, titulo, ruta, tamano, estado) VALUES
                     (1, 10, 1, 'Clavado', 'a.mp3', 100, 'biblioteca'),
                     (2, 10, 1, 'Hechicera', 'b.mp3', 200, 'biblioteca'),
                     (3, 20, 2, 'Única', 'c.mp3', 300, 'biblioteca'),
                     (4, 10, 1, 'Clavado (copia)', 'd.mp3', 400, 'duplicado');
                 INSERT INTO playlists (id, nombre) VALUES (1, 'Lista');
                 INSERT INTO playlist_pistas (playlist_id, pista_id, posicion) VALUES (1, 3, 0), (1, 1, 1);",
            )
            .unwrap();
        (d, rutas, musica, db)
    }

    fn existe(db: &BaseDeDatos, sql: &str) -> bool {
        db.conexion()
            .unwrap()
            .query_row(&format!("SELECT EXISTS ({sql})"), [], |f| f.get(0))
            .unwrap()
    }

    #[test]
    fn quitar_la_ultima_cancion_de_un_artista_se_lleva_su_album_y_a_el() {
        let (d, rutas, musica, db) = entorno("vacios");
        borrar_pista(&db, &rutas, Some(&musica), 3, false).unwrap();
        assert!(!existe(&db, "SELECT 1 FROM pistas WHERE id = 3"));
        assert!(!existe(&db, "SELECT 1 FROM albumes WHERE id = 20"));
        assert!(!existe(&db, "SELECT 1 FROM artistas WHERE id = 2"));
        assert!(!existe(
            &db,
            "SELECT 1 FROM playlist_pistas WHERE pista_id = 3"
        ));
        // El álbum que aún tiene canciones sigue.
        borrar_pista(&db, &rutas, Some(&musica), 1, false).unwrap();
        assert!(existe(&db, "SELECT 1 FROM albumes WHERE id = 10"));
        assert!(existe(&db, "SELECT 1 FROM artistas WHERE id = 1"));
        let _ = std::fs::remove_dir_all(d);
    }

    #[test]
    fn quitar_solo_de_la_biblioteca_no_toca_el_archivo() {
        let (d, rutas, musica, db) = entorno("sin-archivo");
        std::fs::write(musica.join("a.mp3"), b"x").unwrap();
        borrar_pista(&db, &rutas, Some(&musica), 1, false).unwrap();
        assert!(musica.join("a.mp3").is_file());
        let _ = std::fs::remove_dir_all(d);
    }

    #[test]
    fn una_pista_que_no_existe_es_un_error_y_no_cambia_nada() {
        let (d, rutas, musica, db) = entorno("no-existe");
        assert_eq!(
            borrar_pista(&db, &rutas, Some(&musica), 99, true),
            Err(NsError::FileNotFound)
        );
        assert!(existe(&db, "SELECT 1 FROM pistas WHERE id = 1"));
        let _ = std::fs::remove_dir_all(d);
    }

    #[test]
    fn sin_carpeta_de_musica_no_se_quita_nada_si_se_pidio_el_archivo() {
        let (d, rutas, _, db) = entorno("sin-musica");
        assert_eq!(
            borrar_pista(&db, &rutas, None, 1, true),
            Err(NsError::StorageFailure)
        );
        assert!(existe(&db, "SELECT 1 FROM pistas WHERE id = 1"));
        let _ = std::fs::remove_dir_all(d);
    }

    #[test]
    fn el_instrumental_se_va_con_la_pista() {
        let (d, rutas, musica, db) = entorno("stems");
        std::fs::create_dir_all(rutas.stems()).unwrap();
        std::fs::write(rutas.stems().join("v2-2.wav"), b"x").unwrap();
        db.conexion()
            .unwrap()
            .execute(
                "INSERT INTO stems (pista_id, estado, instrumental) VALUES (2, 'lista', 'v2-2.wav')",
                [],
            )
            .unwrap();
        borrar_pista(&db, &rutas, Some(&musica), 2, false).unwrap();
        assert!(!rutas.stems().join("v2-2.wav").exists());
        let _ = std::fs::remove_dir_all(d);
    }

    #[test]
    fn solo_cuentan_como_duplicadas_las_que_aparto_la_deduplicacion() {
        let (d, _, _, db) = entorno("resumen");
        // Mismo título, artista y duración que otra, pero no apartada: no cuenta.
        db.conexion()
            .unwrap()
            .execute(
                "INSERT INTO pistas (id, titulo, artista_nombre, duracion_seg, ruta)
                 VALUES (5, 'Clavado', 'Maná', 300, 'e.mp3'), (6, 'Clavado', 'Maná', 300, 'f.mp3')",
                [],
            )
            .unwrap();
        assert_eq!(
            duplicados(&db).unwrap(),
            ResumenDuplicados {
                total: 1,
                bytes: 400
            }
        );
        let _ = std::fs::remove_dir_all(d);
    }

    #[test]
    fn limpiar_duplicados_deja_intacta_la_biblioteca() {
        let (d, rutas, musica, db) = entorno("limpiar");
        assert_eq!(
            limpiar_duplicados(&db, &rutas, Some(&musica), false).unwrap(),
            1
        );
        assert_eq!(duplicados(&db).unwrap().total, 0);
        let quedan: i64 = db
            .conexion()
            .unwrap()
            .query_row("SELECT count(*) FROM pistas", [], |f| f.get(0))
            .unwrap();
        assert_eq!(quedan, 3);
        let _ = std::fs::remove_dir_all(d);
    }

    #[test]
    fn el_archivo_de_una_pista_no_sale_de_la_carpeta_de_musica() {
        let (d, _, musica, db) = entorno("archivo");
        std::fs::write(musica.join("a.mp3"), b"x").unwrap();
        assert_eq!(
            archivo_de(&db, Some(&musica), 1).unwrap(),
            musica.join("a.mp3")
        );
        assert_eq!(
            archivo_de(&db, Some(&musica), 2),
            Err(NsError::FileNotFound)
        );
        db.conexion()
            .unwrap()
            .execute("UPDATE pistas SET ruta = '../fuera.mp3' WHERE id = 3", [])
            .unwrap();
        assert!(archivo_de(&db, Some(&musica), 3).is_err());
        let _ = std::fs::remove_dir_all(d);
    }
}
