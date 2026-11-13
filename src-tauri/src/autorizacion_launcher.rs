//! ADR-017: confianza local de Sound, excluida de los respaldos de biblioteca.
//! Ninguna API acepta una identidad declarada como sustituto de una prueba vigente.
use nb_capability::attachment::{Access, PublicIdentity, VerifiedClient};
use nb_protocol::capability::ResourceKey;
use rusqlite::{params, Connection, OptionalExtension};
use std::{
    collections::BTreeMap,
    fs::{File, OpenOptions},
    path::Path,
    sync::{Mutex, MutexGuard},
    time::Duration,
};
use tokio::sync::watch;

use crate::{
    db,
    error::{NsError, NsResult},
};

const MAX_REVISION: i64 = 9_007_199_254_740_991;

pub struct Almacen {
    resource: ResourceKey,
    scope: String,
    state: Mutex<State>,
    legacy_blocked: watch::Sender<bool>,
    _lock: File,
}
struct State {
    conn: Connection,
    sessions: BTreeMap<String, Vec<watch::Sender<bool>>>,
}
struct Record {
    revision: i64,
    revoked: bool,
    access: Option<Access>,
}

/// Una solicitud no puede construirse ni reconstruirse desde el webview.
pub struct Pendiente {
    client: VerifiedClient,
    expected_revision: i64,
    expected_generation: i64,
}
impl Pendiente {
    pub fn identidad(&self) -> &PublicIdentity {
        self.client.public()
    }
    pub fn permisos(&self) -> Access {
        self.client.access()
    }
    pub fn vigente(&self) -> bool {
        self.client.ensure_current().is_ok()
    }
}
pub struct Concesion {
    pub client: VerifiedClient,
    pub revoked: watch::Receiver<bool>,
}
pub enum Solicitud {
    Autorizada(Concesion),
    Consentimiento(Pendiente),
    Revocada,
}

fn storage(_: rusqlite::Error) -> NsError {
    NsError::StorageFailure
}
fn public_text(public: &PublicIdentity) -> String {
    public.clone().into()
}

fn read(conn: &Connection, scope: &str, public: &PublicIdentity) -> NsResult<Option<Record>> {
    let row: Option<(i64, bool, String)> = conn
        .query_row(
            "SELECT revision, revocado, permisos FROM concesiones WHERE recurso=?1 AND cliente=?2",
            params![scope, public_text(public)],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()
        .map_err(storage)?;
    row.map(|(revision, revoked, access)| {
        Ok(Record {
            revision,
            revoked,
            access: serde_json::from_str(&access).map_err(|_| NsError::StorageFailure)?,
        })
    })
    .transpose()
}
fn write(conn: &Connection, scope: &str, public: &PublicIdentity, record: &Record) -> NsResult<()> {
    let access = serde_json::to_string(&record.access).map_err(|_| NsError::Internal)?;
    conn.execute("INSERT INTO concesiones(recurso,cliente,revision,revocado,permisos) VALUES(?1,?2,?3,?4,?5)
        ON CONFLICT(recurso,cliente) DO UPDATE SET revision=excluded.revision, revocado=excluded.revocado, permisos=excluded.permisos",
        params![scope, public_text(public), record.revision, record.revoked, access]).map_err(storage)?;
    Ok(())
}
fn next(revision: i64) -> NsResult<i64> {
    revision
        .checked_add(1)
        .filter(|value| *value <= MAX_REVISION)
        .ok_or(NsError::StorageFailure)
}
fn generation(conn: &Connection, scope: &str) -> NsResult<i64> {
    conn.query_row(
        "SELECT generacion FROM generaciones WHERE recurso=?1",
        [scope],
        |row| row.get(0),
    )
    .optional()
    .map_err(storage)
    .map(|value| value.unwrap_or(0))
}

pub(crate) fn private_file(path: &Path) -> NsResult<File> {
    let mut options = OpenOptions::new();
    options.read(true).write(true).create(true).truncate(false);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK);
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        options.custom_flags(windows_sys::Win32::Storage::FileSystem::FILE_FLAG_OPEN_REPARSE_POINT);
    }
    let file = options.open(path).map_err(|_| NsError::PathNotAllowed)?;
    let metadata = file.metadata().map_err(|_| NsError::StorageFailure)?;
    if !metadata.is_file()
        || std::fs::symlink_metadata(path)
            .map_err(|_| NsError::StorageFailure)?
            .file_type()
            .is_symlink()
    {
        return Err(NsError::PathNotAllowed);
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if metadata.mode() & 0o7077 != 0 || metadata.nlink() != 1 {
            return Err(NsError::PathNotAllowed);
        }
    }
    Ok(file)
}

impl Almacen {
    /// Ruta propia de Sound; debe ejecutarse fuera del hilo de UI. No abre la biblioteca.
    pub fn abrir(path: &Path, resource: ResourceKey) -> NsResult<Self> {
        let lock = private_file(&path.with_extension("lock"))?;
        lock.try_lock().map_err(|_| NsError::ComponentUnavailable)?;
        let _file = private_file(path)?;
        let mut conn = Connection::open_with_flags(
            path,
            rusqlite::OpenFlags::SQLITE_OPEN_READ_WRITE | rusqlite::OpenFlags::SQLITE_OPEN_NO_MUTEX,
        )
        .map_err(storage)?;
        conn.busy_timeout(Duration::from_secs(2)).map_err(storage)?;
        let tx = db::transaccion_de_escritura(&mut conn)?;
        let version: i64 = tx
            .query_row("PRAGMA user_version", [], |row| row.get(0))
            .map_err(storage)?;
        if !matches!(version, 0 | 1) {
            return Err(NsError::SchemaMismatch);
        }
        if version == 0 {
            tx.execute_batch(
                "CREATE TABLE concesiones (
                recurso TEXT NOT NULL, cliente TEXT NOT NULL CHECK(length(cliente)=64),
                revision INTEGER NOT NULL CHECK(revision BETWEEN 1 AND 9007199254740991),
                revocado INTEGER NOT NULL CHECK(revocado IN (0,1)), permisos TEXT NOT NULL,
                PRIMARY KEY(recurso,cliente)
            ) STRICT;
            CREATE TABLE generaciones (recurso TEXT PRIMARY KEY, generacion INTEGER NOT NULL
                CHECK(generacion BETWEEN 1 AND 9007199254740991)) STRICT;
            PRAGMA user_version=1;",
            )
            .map_err(storage)?;
        }
        tx.commit().map_err(storage)?;
        let blocked: bool = conn
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM concesiones) OR EXISTS(SELECT 1 FROM generaciones)",
                [],
                |row| row.get(0),
            )
            .map_err(storage)?;
        let (legacy_blocked, _) = watch::channel(blocked);
        let scope = serde_json::to_string(&resource).map_err(|_| NsError::Internal)?;
        Ok(Self {
            resource,
            scope,
            state: Mutex::new(State {
                conn,
                sessions: BTreeMap::new(),
            }),
            _lock: lock,
            legacy_blocked,
        })
    }
    fn lock(&self) -> NsResult<MutexGuard<'_, State>> {
        self.state.lock().map_err(|_| NsError::Internal)
    }
    pub fn bloqueo_heredado(&self) -> watch::Receiver<bool> {
        self.legacy_blocked.subscribe()
    }
    fn validate(&self, client: &VerifiedClient) -> NsResult<()> {
        client
            .ensure_current()
            .map_err(|_| NsError::ConsentRequired)?;
        if client.resource() != &self.resource || !client.access().allows_read() {
            return Err(NsError::InvalidInput);
        }
        Ok(())
    }
    fn lease(state: &mut State, client: VerifiedClient) -> NsResult<Concesion> {
        client
            .ensure_current()
            .map_err(|_| NsError::ConsentRequired)?;
        let sessions = state
            .sessions
            .entry(public_text(client.public()))
            .or_default();
        sessions.retain(|sender| sender.receiver_count() != 0);
        if sessions.len() >= nb_protocol::local::MAX_SESSIONS {
            return Err(NsError::ComponentUnavailable);
        }
        let (sender, revoked) = watch::channel(false);
        sessions.push(sender);
        Ok(Concesion { client, revoked })
    }
    pub fn solicitar(&self, client: VerifiedClient) -> NsResult<Solicitud> {
        self.validate(&client)?;
        let mut state = self.lock()?;
        let record = read(&state.conn, &self.scope, client.public())?;
        if let Some(record) = &record {
            if record.revoked {
                return Ok(Solicitud::Revocada);
            }
            if record
                .access
                .is_some_and(|access| client.access().is_subset_of(access))
            {
                return Self::lease(&mut state, client).map(Solicitud::Autorizada);
            }
        }
        Ok(Solicitud::Consentimiento(Pendiente {
            client,
            expected_revision: record.map_or(0, |record| record.revision),
            expected_generation: generation(&state.conn, &self.scope)?,
        }))
    }
    /// El UI entrega el ID de la solicitud que Sound conserva en memoria. No entrega claves ni permisos.
    /// None indica que una decisión posterior invalidó el diálogo; no se reintenta a ciegas.
    pub fn aceptar(&self, pending: Pendiente) -> NsResult<Option<Concesion>> {
        self.validate(&pending.client)?;
        let mut state = self.lock()?;
        let tx = db::transaccion_de_escritura(&mut state.conn)?;
        let record = read(&tx, &self.scope, pending.client.public())?;
        if record.as_ref().map_or(0, |record| record.revision) != pending.expected_revision
            || record.as_ref().is_some_and(|record| record.revoked)
            || generation(&tx, &self.scope)? != pending.expected_generation
        {
            return Ok(None);
        }
        self.validate(&pending.client)?;
        write(
            &tx,
            &self.scope,
            pending.client.public(),
            &Record {
                revision: next(pending.expected_revision)?,
                revoked: false,
                access: Some(pending.client.access()),
            },
        )?;
        tx.commit().map_err(storage)?;
        self.legacy_blocked.send_replace(true);
        if let Some(sessions) = state.sessions.remove(&public_text(pending.client.public())) {
            for session in sessions {
                session.send_replace(true);
            }
        }
        Self::lease(&mut state, pending.client).map(Some)
    }
    /// Persiste antes de cerrar sesiones. Se conserva la tumba aunque no hubiera permiso previo.
    pub fn revocar(&self, public: &PublicIdentity) -> NsResult<()> {
        let mut state = self.lock()?;
        let tx = db::transaccion_de_escritura(&mut state.conn)?;
        let record = read(&tx, &self.scope, public)?;
        write(
            &tx,
            &self.scope,
            public,
            &Record {
                revision: next(record.as_ref().map_or(0, |record| record.revision))?,
                revoked: true,
                access: record.and_then(|record| record.access),
            },
        )?;
        tx.commit().map_err(storage)?;
        self.legacy_blocked.send_replace(true);
        if let Some(sessions) = state.sessions.remove(&public_text(public)) {
            for session in sessions {
                session.send_replace(true);
            }
        }
        Ok(())
    }
    /// Acción explícita en Sound: admite una solicitud nueva, sin conceder ningún permiso.
    /// Conserva la revisión para que un diálogo anterior a revocar no vuelva a ser válido.
    pub fn permitir_nueva_solicitud(&self, public: &PublicIdentity) -> NsResult<bool> {
        let mut state = self.lock()?;
        let tx = db::transaccion_de_escritura(&mut state.conn)?;
        let Some(record) = read(&tx, &self.scope, public)?.filter(|record| record.revoked) else {
            return Ok(false);
        };
        write(
            &tx,
            &self.scope,
            public,
            &Record {
                revision: next(record.revision)?,
                revoked: false,
                access: None,
            },
        )?;
        tx.commit().map_err(storage)?;
        self.legacy_blocked.send_replace(true);
        Ok(true)
    }
    /// Contadores confirmados del ámbito; la UI no necesita recibir claves públicas.
    pub fn resumen(&self) -> NsResult<(u32, u32)> {
        self.lock()?
            .conn
            .query_row(
                "SELECT
            COUNT(CASE WHEN revocado=0 AND permisos!='null' THEN 1 END),
            COUNT(CASE WHEN revocado=1 THEN 1 END)
            FROM concesiones WHERE recurso=?1",
                [&self.scope],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .map_err(storage)
    }
    /// Acción de Sound sobre todas las identidades de Launcher del recurso, no sobre otras apps.
    /// La generación invalida incluso diálogos de clientes todavía sin fila persistida.
    pub fn revocar_todas(&self) -> NsResult<()> {
        self.actualizar_todas(true)
    }
    /// Solo permite pedir consentimiento otra vez. Nunca restaura permisos anteriores.
    pub fn permitir_nuevas_solicitudes(&self) -> NsResult<()> {
        self.actualizar_todas(false)
    }
    fn actualizar_todas(&self, revoke: bool) -> NsResult<()> {
        let mut state = self.lock()?;
        let tx = db::transaccion_de_escritura(&mut state.conn)?;
        let version = next(generation(&tx, &self.scope)?)?;
        tx.execute(
            "INSERT INTO generaciones(recurso,generacion) VALUES(?1,?2)
            ON CONFLICT(recurso) DO UPDATE SET generacion=excluded.generacion",
            params![self.scope, version],
        )
        .map_err(storage)?;
        // Un desbordamiento incumple CHECK: todo el lote y su generación retroceden juntos.
        if revoke {
            tx.execute(
                "UPDATE concesiones SET revision=revision+1,revocado=1 WHERE recurso=?1",
                [&self.scope],
            )
            .map_err(storage)?;
        } else {
            tx.execute("UPDATE concesiones SET revision=revision+1,revocado=0,permisos='null' WHERE recurso=?1 AND revocado=1", [&self.scope]).map_err(storage)?;
        }
        tx.commit().map_err(storage)?;
        self.legacy_blocked.send_replace(true);
        if revoke {
            for (_, sessions) in std::mem::take(&mut state.sessions) {
                for session in sessions {
                    session.send_replace(true);
                }
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests;
