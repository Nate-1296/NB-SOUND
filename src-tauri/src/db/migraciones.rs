//! Migraciones de esquema.
//!
//! La base vive en la máquina del usuario: si una migración falla, esa persona
//! pierde su biblioteca. De ahí las reglas, las mismas que NB Books
//! (`src-tauri/src/db/migrations.rs`):
//!
//! 1. **Embebidas en el binario** con `include_str!`.
//! 2. **Transaccionales:** cada una se aplica entera o no se aplica.
//! 3. **Solo hacia adelante.**
//! 4. **Respaldo previo** antes de tocar una base con datos.
//! 5. Una versión antigua que encuentra una base más nueva **se niega a operar**.

use std::path::{Path, PathBuf};

use rusqlite::Connection;

use crate::error::{NsError, NsResult};

struct Migracion {
    version: u32,
    nombre: &'static str,
    sql: &'static str,
}

/// En orden estricto. **Nunca se edita una entrada publicada**: un error en una
/// migración aplicada se corrige con una migración nueva.
const MIGRACIONES: &[Migracion] = &[Migracion {
    version: 1,
    nombre: "metadatos de la instalación",
    sql: include_str!("../../migraciones/V1__instalacion.sql"),
}];

/// Versión de esquema aplicada (`PRAGMA user_version`).
///
/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede leer.
pub fn version_actual(conn: &Connection) -> NsResult<u32> {
    conn.query_row("PRAGMA user_version", [], |f| f.get::<_, i64>(0))
        .map(|v| v.max(0) as u32)
        .map_err(|_| NsError::StorageFailure)
}

/// Aplica las migraciones pendientes. `ruta` es la del archivo, para el
/// respaldo; `None` en las bases en memoria de las pruebas.
///
/// # Errors
///
/// - [`NsError::SchemaMismatch`] si la base es más nueva que esta versión, o si
///   una migración dejó referencias rotas.
/// - [`NsError::StorageFailure`] si una migración falla; se revierte y el
///   respaldo queda en disco.
pub fn aplicar_pendientes(conn: &mut Connection, ruta: Option<&Path>) -> NsResult<u32> {
    aplicar(conn, ruta, MIGRACIONES)
}

/// El motor, con la lista como parámetro para poder probar con listas sintéticas
/// las propiedades que importan (reversión, salto de versiones, respaldo).
fn aplicar(conn: &mut Connection, ruta: Option<&Path>, migraciones: &[Migracion]) -> NsResult<u32> {
    let actual = version_actual(conn)?;
    let objetivo = migraciones.last().map_or(0, |m| m.version);

    if actual > objetivo {
        tracing::error!(
            esquema_actual = actual,
            esquema_soportado = objetivo,
            "la base de datos es más nueva que esta versión de la aplicación"
        );
        return Err(NsError::SchemaMismatch);
    }
    if actual == objetivo {
        return Ok(actual);
    }
    if actual > 0 {
        if let Some(ruta) = ruta {
            respaldar(conn, ruta, actual)?;
        }
    }

    // Las claves foráneas se apagan alrededor de las migraciones y no dentro:
    // reconstruir una tabla con ellas encendidas dispara los `ON DELETE CASCADE`
    // de quien la referencia y borra hijos en silencio (lo midió NB Books). El
    // `PRAGMA` no hace nada dentro de una transacción, por eso va aquí, y la
    // comprobación de después convierte cualquier daño en un error ruidoso.
    conn.pragma_update(None, "foreign_keys", "OFF")
        .map_err(|_| NsError::StorageFailure)?;
    let resultado = aplicar_en_orden(conn, migraciones, actual);
    let reencendido = conn
        .pragma_update(None, "foreign_keys", "ON")
        .map_err(|_| NsError::StorageFailure);
    resultado?;
    reencendido?;
    comprobar_referencias(conn)?;

    tracing::info!(esquema = objetivo, "esquema actualizado");
    Ok(objetivo)
}

fn aplicar_en_orden(conn: &mut Connection, migraciones: &[Migracion], actual: u32) -> NsResult<()> {
    for m in migraciones.iter().filter(|m| m.version > actual) {
        tracing::info!(
            version = m.version,
            nombre = m.nombre,
            "aplicando migración"
        );
        let tx = super::transaccion_de_escritura(conn)?;
        tx.execute_batch(m.sql).map_err(|error| {
            tracing::error!(version = m.version, error = %error, "la migración falló; se revierte");
            NsError::StorageFailure
        })?;
        // `user_version` no admite parámetros ligados.
        tx.pragma_update(None, "user_version", m.version)
            .map_err(|_| NsError::StorageFailure)?;
        tx.commit().map_err(|_| NsError::StorageFailure)?;
    }
    Ok(())
}

fn comprobar_referencias(conn: &Connection) -> NsResult<()> {
    let violaciones: i64 = conn
        .query_row("SELECT count(*) FROM pragma_foreign_key_check", [], |f| {
            f.get(0)
        })
        .map_err(|_| NsError::StorageFailure)?;
    if violaciones > 0 {
        tracing::error!(violaciones, "una migración dejó referencias rotas");
        return Err(NsError::SchemaMismatch);
    }
    Ok(())
}

/// Copia de seguridad antes de migrar, con `VACUUM INTO`: ve la base entera,
/// incluido lo que aún está en el `-wal` (una copia del archivo no lo vería, que
/// es el error que NB Books encontró en la suya). Se escribe aparte y se renombra
/// al terminar, así que un respaldo a medias nunca sustituye a uno entero.
fn respaldar(conn: &Connection, ruta: &Path, desde: u32) -> NsResult<()> {
    let mut destino = ruta.as_os_str().to_owned();
    destino.push(format!(".v{desde}.respaldo"));
    let destino = PathBuf::from(destino);
    let mut parcial = destino.as_os_str().to_owned();
    parcial.push(".parcial");
    let parcial = PathBuf::from(parcial);
    let _ = std::fs::remove_file(&parcial);

    conn.execute("VACUUM INTO ?1", [parcial.to_string_lossy()])
        .map_err(|error| {
            let _ = std::fs::remove_file(&parcial);
            tracing::error!(error = %error, "no se pudo crear el respaldo previo a la migración");
            NsError::StorageFailure
        })?;
    std::fs::rename(&parcial, &destino).map_err(|error| {
        let _ = std::fs::remove_file(&parcial);
        tracing::error!(error = %error, "no se pudo dejar en su sitio el respaldo");
        NsError::StorageFailure
    })?;
    tracing::info!(
        desde_version = desde,
        respaldo = %crate::telemetry::redact_path(&destino),
        "respaldo previo a la migración creado"
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    const UNA: &[Migracion] = &[Migracion {
        version: 1,
        nombre: "una",
        sql: "CREATE TABLE a (x INTEGER) STRICT;",
    }];
    const DOS: &[Migracion] = &[
        Migracion {
            version: 1,
            nombre: "una",
            sql: "CREATE TABLE a (x INTEGER) STRICT;",
        },
        Migracion {
            version: 2,
            nombre: "dos",
            sql: "ALTER TABLE a ADD COLUMN y TEXT;",
        },
    ];
    const ROTA: &[Migracion] = &[
        Migracion {
            version: 1,
            nombre: "una",
            sql: "CREATE TABLE a (x INTEGER) STRICT;",
        },
        Migracion {
            version: 2,
            nombre: "rota",
            sql: "INSERT INTO a VALUES (1); ESTO NO ES SQL;",
        },
    ];

    fn temporal(nombre: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("ns-mig-{nombre}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).expect("carpeta");
        dir
    }

    #[test]
    fn las_migraciones_reales_se_aplican_y_son_idempotentes() {
        let mut conn = Connection::open_in_memory().unwrap();
        let v = aplicar_pendientes(&mut conn, None).unwrap();
        assert_eq!(v, MIGRACIONES.last().unwrap().version);
        assert_eq!(aplicar_pendientes(&mut conn, None).unwrap(), v);
    }

    #[test]
    fn una_migracion_que_falla_no_deja_nada_a_medias() {
        let mut conn = Connection::open_in_memory().unwrap();
        aplicar(&mut conn, None, UNA).unwrap();
        assert!(aplicar(&mut conn, None, ROTA).is_err());
        assert_eq!(version_actual(&conn).unwrap(), 1);
        let filas: i64 = conn
            .query_row("SELECT count(*) FROM a", [], |f| f.get(0))
            .unwrap();
        assert_eq!(filas, 0, "el INSERT de la migración rota se revirtió");
    }

    #[test]
    fn una_base_mas_nueva_se_rechaza() {
        let mut conn = Connection::open_in_memory().unwrap();
        aplicar(&mut conn, None, DOS).unwrap();
        assert_eq!(aplicar(&mut conn, None, UNA), Err(NsError::SchemaMismatch));
    }

    #[test]
    fn migrar_una_base_con_datos_deja_un_respaldo_legible() {
        let dir = temporal("respaldo");
        let ruta = dir.join("base.sqlite");
        let mut conn = Connection::open(&ruta).unwrap();
        aplicar(&mut conn, Some(&ruta), UNA).unwrap();
        conn.execute("INSERT INTO a VALUES (42)", []).unwrap();
        aplicar(&mut conn, Some(&ruta), DOS).unwrap();
        let respaldo = Connection::open(dir.join("base.sqlite.v1.respaldo")).unwrap();
        let x: i64 = respaldo
            .query_row("SELECT x FROM a", [], |f| f.get(0))
            .unwrap();
        assert_eq!(x, 42);
        assert!(!dir.join("base.sqlite.v1.respaldo.parcial").exists());
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn una_referencia_rota_tras_migrar_es_un_error() {
        let mut conn = Connection::open_in_memory().unwrap();
        const HUERFANA: &[Migracion] = &[Migracion {
            version: 1,
            nombre: "huérfana",
            sql: "CREATE TABLE p (id INTEGER PRIMARY KEY) STRICT;
                  CREATE TABLE h (p INTEGER REFERENCES p(id)) STRICT;
                  INSERT INTO h VALUES (7);",
        }];
        assert_eq!(
            aplicar(&mut conn, None, HUERFANA),
            Err(NsError::SchemaMismatch)
        );
    }
}
