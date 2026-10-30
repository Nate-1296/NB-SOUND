//! Capa de persistencia local (F1.1.1).
//!
//! Contrato: docs/adr/decisions/ADR-004-datos.md. Rust es el único dueño de la
//! base. Toda conexión se configura igual y esa configuración no es opcional: sin
//! WAL las lecturas bloquean a las escrituras y aparece el `database is locked`
//! que el usuario percibe como una aplicación colgada. Portado de NB Books
//! (`src-tauri/src/db/mod.rs`), donde cada regla de aquí costó un defecto.

pub mod migraciones;

use std::path::{Path, PathBuf};
use std::time::Duration;

use r2d2::Pool;
use r2d2_sqlite::SqliteConnectionManager;
use rusqlite::Connection;

use crate::error::{NsError, NsResult};

/// Tiempo que una conexión espera a que se libere un bloqueo antes de fallar.
pub(crate) const BUSY_TIMEOUT: Duration = Duration::from_secs(5);

/// A partir de cuánto esperar por una conexión se apunta en el registro.
const ESPERA_QUE_SE_DICE: Duration = Duration::from_millis(50);

/// Conexiones simultáneas. Una aplicación de escritorio no necesita más: la
/// interfaz, el reproductor, el servidor móvil y una tarea de fondo. Un pool
/// grande solo aumenta la contención.
const MAX_CONEXIONES: u32 = 4;

/// La configuración de cada conexión. `foreign_keys`, `synchronous` y
/// `busy_timeout` son de la conexión, no del archivo, así que se aplican en cada
/// una. `journal_mode` no: ver [`preparar_archivo`].
fn configurar(conn: &mut Connection) -> Result<(), rusqlite::Error> {
    conn.busy_timeout(BUSY_TIMEOUT)?;
    // Suficiente en WAL; `FULL` cuesta un fsync por escritura.
    conn.pragma_update(None, "synchronous", "NORMAL")?;
    // SQLite las trae apagadas: sin esto las claves foráneas son decoración.
    conn.pragma_update(None, "foreign_keys", "ON")?;
    Ok(())
}

/// Fija WAL en el archivo una sola vez, antes del pool. Hacerlo desde cada
/// conexión pone a varias a cambiar el modo del diario a la vez sobre una base
/// recién creada, y eso es `database is locked` en cada arranque en frío (lo midió
/// NB Books).
fn preparar_archivo(ruta: &Path) -> NsResult<()> {
    let conn = Connection::open(ruta).map_err(|error| {
        tracing::error!(error = %error, "no se pudo abrir la base de datos");
        NsError::StorageFailure
    })?;
    conn.busy_timeout(BUSY_TIMEOUT)
        .map_err(|_| NsError::StorageFailure)?;
    let modo: String = conn
        .pragma_update_and_check(None, "journal_mode", "WAL", |fila| fila.get(0))
        .map_err(|error| {
            tracing::error!(error = %error, "no se pudo activar el modo WAL");
            NsError::StorageFailure
        })?;
    if !modo.eq_ignore_ascii_case("wal") {
        tracing::error!(modo = %modo, "el modo WAL no quedó activo");
        return Err(NsError::StorageFailure);
    }
    Ok(())
}

/// Abre una transacción **de escritura** con `BEGIN IMMEDIATE`.
///
/// Nunca la diferida que da `Connection::transaction`: en WAL, una transacción
/// diferida que lee y después escribe recibe `SQLITE_BUSY` **de inmediato y sin
/// respetar `busy_timeout`** si otro escritor confirmó entre medias. NB Books
/// perdió así 1.207 documentos en una importación real, y la V1 abría `BEGIN` a
/// secas (`legado/db/conexion.py`). Lo vigila `scripts/check-transacciones.mjs`.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede abrir.
pub fn transaccion_de_escritura(conn: &mut Connection) -> NsResult<rusqlite::Transaction<'_>> {
    conn.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)
        .map_err(|error| {
            tracing::error!(error = %error, "no se pudo abrir una transacción de escritura");
            NsError::StorageFailure
        })
}

/// Abre una lectura que ve una sola foto de la base: varias consultas seguidas
/// sin transacción ven cada una un momento distinto si alguien escribe a la vez.
/// Solo lee, así que no es la diferida que prohíbe [`transaccion_de_escritura`].
///
/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede abrir.
pub fn lectura_coherente(conn: &mut Connection) -> NsResult<rusqlite::Transaction<'_>> {
    conn.transaction_with_behavior(rusqlite::TransactionBehavior::Deferred)
        .map_err(|error| {
            tracing::error!(error = %error, "no se pudo abrir una lectura coherente");
            NsError::StorageFailure
        })
}

/// Acceso a la base de datos local.
#[derive(Clone)]
pub struct BaseDeDatos {
    pool: Pool<SqliteConnectionManager>,
}

impl BaseDeDatos {
    /// Abre la base en `ruta`, la configura y aplica las migraciones pendientes.
    ///
    /// # Errors
    ///
    /// - [`NsError::SchemaMismatch`] si la base es más nueva que esta versión.
    /// - [`NsError::StorageFailure`] si no se puede abrir o migrar.
    pub fn abrir(ruta: &Path) -> NsResult<Self> {
        preparar_archivo(ruta)?;
        let gestor = SqliteConnectionManager::file(ruta).with_init(configurar);
        Self::construir(gestor, Some(ruta.to_path_buf()))
    }

    /// Base en memoria compartida por el pool. Solo para pruebas.
    ///
    /// # Errors
    ///
    /// [`NsError::StorageFailure`] si no se puede inicializar.
    pub fn en_memoria() -> NsResult<Self> {
        // Un nombre único por base: `memory()` daría a cada conexión del pool su
        // propia base vacía, y una prueba con dos conexiones vería dos mundos.
        static CONTADOR: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
        let n = CONTADOR.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        let uri = format!(
            "file:ns-memoria-{}-{n}?mode=memory&cache=shared",
            std::process::id()
        );
        let gestor = SqliteConnectionManager::file(uri)
            .with_flags(
                rusqlite::OpenFlags::SQLITE_OPEN_READ_WRITE
                    | rusqlite::OpenFlags::SQLITE_OPEN_CREATE
                    | rusqlite::OpenFlags::SQLITE_OPEN_URI,
            )
            .with_init(configurar);
        Self::construir(gestor, None)
    }

    fn construir(gestor: SqliteConnectionManager, ruta: Option<PathBuf>) -> NsResult<Self> {
        let pool = Pool::builder()
            .max_size(MAX_CONEXIONES)
            // Sin conexiones ociosas al arrancar: crearlas en paralelo solo da
            // contención, y en escritorio no hay carga que lo justifique.
            .min_idle(Some(0))
            .connection_timeout(BUSY_TIMEOUT)
            .build(gestor)
            .map_err(|error| {
                tracing::error!(error = %error, "no se pudo crear el pool de conexiones");
                NsError::StorageFailure
            })?;
        let db = Self { pool };
        let mut conn = db.conexion()?;
        migraciones::aplicar_pendientes(&mut conn, ruta.as_deref())?;
        drop(conn);
        Ok(db)
    }

    /// Toma una conexión del pool. Si hubo que esperar más de lo que se nota,
    /// queda en el registro con cuántas estaban en uso.
    ///
    /// # Errors
    ///
    /// [`NsError::StorageFailure`] si el pool está agotado.
    pub fn conexion(&self) -> NsResult<r2d2::PooledConnection<SqliteConnectionManager>> {
        let inicio = std::time::Instant::now();
        let conexion = self.pool.get().map_err(|error| {
            tracing::error!(error = %error, "no se pudo obtener una conexión del pool");
            NsError::StorageFailure
        })?;
        let espera = inicio.elapsed();
        if espera >= ESPERA_QUE_SE_DICE {
            let estado = self.pool.state();
            tracing::warn!(
                ms = espera.as_millis(),
                en_uso = estado.connections - estado.idle_connections,
                "se esperó por una conexión del pool"
            );
        }
        Ok(conexion)
    }

    /// Versión de esquema aplicada.
    ///
    /// # Errors
    ///
    /// [`NsError::StorageFailure`] si no se puede consultar.
    pub fn version_de_esquema(&self) -> NsResult<u32> {
        let conn = self.conexion()?;
        migraciones::version_actual(&conn)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temporal(nombre: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("ns-db-{nombre}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).expect("carpeta");
        dir
    }

    #[test]
    fn la_base_queda_en_wal_con_claves_foraneas() {
        let dir = temporal("wal");
        let db = BaseDeDatos::abrir(&dir.join("prueba.sqlite")).expect("abre");
        let conn = db.conexion().expect("conexión");
        let modo: String = conn
            .query_row("PRAGMA journal_mode", [], |f| f.get(0))
            .unwrap();
        let fk: i64 = conn
            .query_row("PRAGMA foreign_keys", [], |f| f.get(0))
            .unwrap();
        assert_eq!(modo.to_lowercase(), "wal");
        assert_eq!(fk, 1);
        drop(conn);
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn la_base_en_memoria_es_la_misma_para_todas_las_conexiones() {
        let db = BaseDeDatos::en_memoria().expect("abre");
        let a = db.conexion().unwrap();
        a.execute_batch("CREATE TABLE prueba (x INTEGER); INSERT INTO prueba VALUES (1);")
            .unwrap();
        let b = db.conexion().unwrap();
        let n: i64 = b
            .query_row("SELECT count(*) FROM prueba", [], |f| f.get(0))
            .unwrap();
        assert_eq!(n, 1);
    }

    /// El criterio de F1.1.1: ocho escritores concurrentes sin un solo
    /// `SQLITE_BUSY`. Es la prueba que habría evitado la pérdida de NB Books.
    #[test]
    fn ocho_escritores_concurrentes_no_reciben_busy() {
        let dir = temporal("concurrencia");
        let db = BaseDeDatos::abrir(&dir.join("prueba.sqlite")).expect("abre");
        db.conexion()
            .unwrap()
            .execute_batch("CREATE TABLE contador (id INTEGER PRIMARY KEY, n INTEGER NOT NULL); INSERT INTO contador VALUES (1, 0);")
            .unwrap();
        let hilos: Vec<_> = (0..8)
            .map(|_| {
                let db = db.clone();
                std::thread::spawn(move || {
                    for _ in 0..50 {
                        let mut conn = db.conexion().expect("conexión");
                        let tx = transaccion_de_escritura(&mut conn).expect("transacción");
                        // Leer y después escribir: exactamente lo que falla en diferido.
                        let n: i64 = tx
                            .query_row("SELECT n FROM contador WHERE id = 1", [], |f| f.get(0))
                            .unwrap();
                        tx.execute("UPDATE contador SET n = ?1 WHERE id = 1", [n + 1])
                            .unwrap();
                        tx.commit().expect("confirma sin BUSY");
                    }
                })
            })
            .collect();
        for h in hilos {
            h.join().expect("ningún hilo falla");
        }
        let n: i64 = db
            .conexion()
            .unwrap()
            .query_row("SELECT n FROM contador", [], |f| f.get(0))
            .unwrap();
        assert_eq!(n, 400, "ninguna escritura se perdió");
        let _ = std::fs::remove_dir_all(dir);
    }
}
