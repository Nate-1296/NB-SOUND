//! ADR-013: Sound conserva validación y transacción; la biblioteca coordina revisiones.

use nb_capability::{Commit, OwnedResource, OwnerError, StateOwner, StoredSnapshot};
use nb_protocol::capability::{
    ChangeResult, Epoch, Identifier, ResourceError, ResourceKey, Revision, Sequence, Snapshot,
};
use serde::{Deserialize, Serialize};
use ts_rs::TS;

use crate::{
    copia_seguridad,
    db::{self, BaseDeDatos},
    error::{NsError, NsResult},
};

pub type RecursoFrecuencia = OwnedResource<Propietario>;

pub struct Propietario {
    db: BaseDeDatos,
}

impl Propietario {
    pub fn nuevo(db: BaseDeDatos) -> Self {
        Self { db }
    }
}

fn leer(conn: &rusqlite::Connection) -> NsResult<StoredSnapshot<u32>> {
    let sequence: i64 = conn
        .query_row(
            "SELECT secuencia FROM revision_de_recursos WHERE recurso='copia_frecuencia'",
            [],
            |row| row.get(0),
        )
        .map_err(|_| NsError::StorageFailure)?;
    Ok(StoredSnapshot {
        sequence: Sequence::try_from(u64::try_from(sequence).map_err(|_| NsError::StorageFailure)?)
            .map_err(|_| NsError::StorageFailure)?,
        value: copia_seguridad::leer_frecuencia(conn)?,
    })
}

fn almacenamiento(_: NsError) -> OwnerError {
    OwnerError::Persistence
}

impl StateOwner for Propietario {
    type Value = u32;
    type Command = u32;

    fn read(&mut self) -> Result<StoredSnapshot<u32>, OwnerError> {
        let mut conn = self.db.conexion().map_err(almacenamiento)?;
        let tx = db::lectura_coherente(&mut conn).map_err(almacenamiento)?;
        leer(&tx).map_err(almacenamiento)
    }

    fn compare_and_set(
        &mut self,
        expected: Sequence,
        dias: u32,
    ) -> Result<Commit<u32>, OwnerError> {
        if !copia_seguridad::FRECUENCIAS.contains(&dias) {
            return Err(OwnerError::InvalidInput);
        }
        let mut conn = self.db.conexion().map_err(almacenamiento)?;
        let tx = db::transaccion_de_escritura(&mut conn).map_err(almacenamiento)?;
        let actual = leer(&tx).map_err(almacenamiento)?;
        if actual.sequence != expected {
            return Ok(Commit::Conflict(actual));
        }
        if actual.value == dias {
            return Ok(Commit::Unchanged(actual));
        }
        let siguiente = expected
            .checked_next()
            .ok_or(OwnerError::RevisionExhausted)?;
        copia_seguridad::fijar_frecuencia_en(&tx, dias).map_err(almacenamiento)?;
        tx.execute(
            "UPDATE revision_de_recursos SET secuencia=?1 WHERE recurso='copia_frecuencia'",
            [i64::try_from(siguiente.get()).map_err(|_| OwnerError::RevisionExhausted)?],
        )
        .map_err(|_| OwnerError::Persistence)?;
        tx.commit().map_err(|_| OwnerError::ResultUnknown)?;
        Ok(Commit::Applied(StoredSnapshot {
            sequence: siguiente,
            value: dias,
        }))
    }
}

/// Solo se construye tras abrir/migrar la base y aplicar una restauración pendiente.
pub fn nuevo(db: &BaseDeDatos) -> NsResult<RecursoFrecuencia> {
    let installation: String = db
        .conexion()?
        .query_row(
            "SELECT valor FROM instalacion WHERE clave='id_instalacion'",
            [],
            |row| row.get(0),
        )
        .map_err(|_| NsError::StorageFailure)?;
    let id = |text: String| Identifier::try_from(text).map_err(|_| NsError::InvalidInput);
    let key = ResourceKey {
        app_id: id("nb.sound".into())?,
        installation_id: id(installation)?,
        capability_id: id("backup.frequency".into())?,
        major_version: std::num::NonZeroU16::MIN,
        resource_id: id("schedule".into())?,
    };
    OwnedResource::new(key, Propietario::nuevo(db.clone())).map_err(error_recurso)
}

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
pub struct RevisionCopia {
    pub epoch: String,
    #[ts(type = "number")]
    pub sequence: u64,
}

impl TryFrom<RevisionCopia> for Revision {
    type Error = NsError;
    fn try_from(value: RevisionCopia) -> NsResult<Self> {
        Ok(Self {
            epoch: Epoch::try_from(value.epoch).map_err(|_| NsError::InvalidInput)?,
            sequence: Sequence::try_from(value.sequence).map_err(|_| NsError::InvalidInput)?,
        })
    }
}

#[derive(Debug, Clone, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct FrecuenciaCopia {
    pub cada_dias: u32,
    pub revision: RevisionCopia,
}

impl From<&Snapshot<u32>> for FrecuenciaCopia {
    fn from(snapshot: &Snapshot<u32>) -> Self {
        Self {
            cada_dias: snapshot.value,
            revision: RevisionCopia {
                epoch: String::from(snapshot.revision.epoch.clone()),
                sequence: snapshot.revision.sequence.get(),
            },
        }
    }
}

#[derive(Debug, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(tag = "resultado", content = "frecuencia", rename_all = "camelCase")]
pub enum CambioFrecuenciaCopia {
    Aplicado(FrecuenciaCopia),
    SinCambios(FrecuenciaCopia),
    Conflicto(FrecuenciaCopia),
}

pub fn consultar(recurso: &RecursoFrecuencia) -> NsResult<FrecuenciaCopia> {
    recurso
        .read()
        .map(|snapshot| FrecuenciaCopia::from(snapshot.as_ref()))
        .map_err(error_recurso)
}

pub fn cambiar(
    recurso: &RecursoFrecuencia,
    revision: RevisionCopia,
    dias: u32,
) -> NsResult<CambioFrecuenciaCopia> {
    match recurso
        .compare_and_set(&Revision::try_from(revision)?, dias)
        .map_err(error_recurso)?
    {
        ChangeResult::Applied(s) => Ok(CambioFrecuenciaCopia::Aplicado(FrecuenciaCopia::from(&s))),
        ChangeResult::Unchanged(s) => {
            Ok(CambioFrecuenciaCopia::SinCambios(FrecuenciaCopia::from(&s)))
        }
        ChangeResult::Conflict(s) => {
            Ok(CambioFrecuenciaCopia::Conflicto(FrecuenciaCopia::from(&s)))
        }
    }
}

pub fn error_propietario(error: OwnerError) -> NsError {
    error_recurso(ResourceError::from(error))
}

pub fn error_recurso(error: ResourceError) -> NsError {
    match error {
        ResourceError::InvalidInput => NsError::InvalidInput,
        ResourceError::Persistence | ResourceError::ResultUnknown => NsError::StorageFailure,
        ResourceError::Unavailable | ResourceError::EntropyUnavailable => {
            NsError::ComponentUnavailable
        }
        _ => NsError::Internal,
    }
}

/// El recurso publica después del commit; el listener también recibe cambios del enlace local.
pub fn escuchar(app: tauri::AppHandle, recurso: RecursoFrecuencia) {
    tauri::async_runtime::spawn(async move {
        use tauri::Emitter;
        let observation = tauri::async_runtime::spawn_blocking(move || recurso.subscribe()).await;
        let Ok(Ok((initial, mut changes))) = observation else {
            return;
        };
        let _ = app.emit(
            "copia:frecuencia",
            Some(FrecuenciaCopia::from(initial.as_ref())),
        );
        while let Ok(event) = changes.next().await {
            let value = match event {
                nb_capability::ResourceEvent::Confirmed(snapshot) => {
                    Some(FrecuenciaCopia::from(snapshot.as_ref()))
                }
                nb_capability::ResourceEvent::Unavailable(_) => None,
            };
            let _ = app.emit("copia:frecuencia", value);
        }
    });
}

/// Se activa solo por el supervisor de desarrollo; stdout conserva sus registros normales.
pub fn iniciar_enlace_si_se_pidio(
    recurso: RecursoFrecuencia,
    bloqueo: Option<tokio::sync::watch::Receiver<bool>>,
) {
    if !std::env::args_os().any(|arg| arg == "--nb-launcher") {
        return;
    }
    let _ = std::thread::Builder::new()
        .name("enlace-launcher".into())
        .spawn(move || {
            let Ok(runtime) = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
            else {
                return;
            };
            if runtime
                .block_on(servir_heredado(recurso, tokio::io::stdin(), bloqueo))
                .is_err()
            {
                tracing::warn!("el enlace local del Launcher terminó sin completarse");
            }
            runtime.shutdown_background();
        });
}

async fn servir_heredado<R: tokio::io::AsyncRead + Unpin>(
    recurso: RecursoFrecuencia,
    supervisor: R,
    bloqueo: Option<tokio::sync::watch::Receiver<bool>>,
) -> Result<(), nb_capability::port::PortError> {
    if let Some(bloqueo) = bloqueo {
        if *bloqueo.borrow() {
            return Ok(());
        }
        nb_capability::port::serve_revocable(recurso, supervisor, bloqueo).await
    } else {
        nb_capability::port::serve(recurso, supervisor).await
    }
}

#[cfg(test)]
mod pruebas {
    use super::*;

    #[tokio::test]
    async fn activar_permisos_persistentes_retira_el_puerto_heredado_y_sus_clientes() {
        use nb_capability::port::{Bootstrap, Client};
        use nb_protocol::{frame::write_frame, local};
        use std::time::Duration;
        use tokio::time::{sleep, timeout};
        let db = BaseDeDatos::en_memoria().unwrap();
        let resource = nuevo(&db).unwrap();
        let before = resource.read().unwrap();
        let session = local::new_session().unwrap();
        let credential = local::new_credential().unwrap();
        let (mut parent, supervisor) = tokio::io::duplex(4096);
        write_frame(
            &mut parent,
            &Bootstrap {
                session: session.clone(),
                credential: credential.clone(),
            },
        )
        .await
        .unwrap();
        let (block, blocked) = tokio::sync::watch::channel(false);
        let task = tokio::spawn(servir_heredado(resource.clone(), supervisor, Some(blocked)));
        let (mut client, _) = timeout(Duration::from_secs(3), async {
            loop {
                if let Ok(client) =
                    Client::connect(&session, credential.clone(), std::process::id()).await
                {
                    break client;
                }
                sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .unwrap();
        block.send_replace(true);
        timeout(Duration::from_secs(2), task)
            .await
            .unwrap()
            .unwrap()
            .unwrap();
        assert!(client.read().await.is_err());
        assert!(Client::connect(&session, credential, std::process::id())
            .await
            .is_err());
        assert_eq!(resource.read().unwrap().value, before.value);
        assert_eq!(resource.read().unwrap().revision, before.revision);
    }

    #[tokio::test]
    async fn renovar_el_enlace_no_escribe_y_desconectarlo_conserva_el_control_nativo() {
        use nb_capability::port::{Bootstrap, Client, Control, Reply};
        use nb_protocol::{frame::write_frame, local};
        use std::time::Duration;
        use tokio::time::{sleep, timeout};

        let db = BaseDeDatos::en_memoria().unwrap();
        let recurso = nuevo(&db).unwrap();
        let antes = consultar(&recurso).unwrap();
        let session = local::new_session().unwrap();
        let credential = local::new_credential().unwrap();
        let (mut parent, supervisor) = tokio::io::duplex(4096);
        write_frame(
            &mut parent,
            &Bootstrap {
                session: session.clone(),
                credential: credential.clone(),
            },
        )
        .await
        .unwrap();
        let task = tokio::spawn(nb_capability::port::serve(recurso.clone(), supervisor));
        let (mut client, _, renewable) = timeout(Duration::from_secs(3), async {
            loop {
                if let Ok(connection) =
                    Client::connect_with_renewal(&session, credential.clone(), std::process::id())
                        .await
                {
                    break connection;
                }
                sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .unwrap();
        assert!(renewable);
        write_frame(&mut parent, &Control::Renew).await.unwrap();
        assert!(
            matches!(client.read().await.unwrap(), Reply::Snapshot(s) if s.revision == recurso.read().unwrap().revision)
        );
        let despues = consultar(&recurso).unwrap();
        assert_eq!(despues.revision.epoch, antes.revision.epoch);
        assert_eq!(despues.revision.sequence, antes.revision.sequence);
        drop(parent);
        timeout(Duration::from_secs(2), task)
            .await
            .unwrap()
            .unwrap()
            .unwrap();
        assert!(client.read().await.is_err());
        cambiar(&recurso, antes.revision, 7).unwrap();
        assert_eq!(consultar(&recurso).unwrap().cada_dias, 7);
    }

    #[test]
    fn dos_controles_no_sobrescriben_una_revision_antigua() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let recurso = nuevo(&db).unwrap();
        let inicial = consultar(&recurso).unwrap();
        let CambioFrecuenciaCopia::Aplicado(actual) =
            cambiar(&recurso, inicial.revision.clone(), 7).unwrap()
        else {
            panic!("cambio esperado")
        };
        assert_eq!(actual.cada_dias, 7);
        assert_eq!(actual.revision.sequence, 1);
        assert!(
            matches!(cambiar(&recurso, inicial.revision, 1).unwrap(), CambioFrecuenciaCopia::Conflicto(s) if s.cada_dias == 7)
        );
        assert!(
            matches!(cambiar(&recurso, actual.revision.clone(), 7).unwrap(), CambioFrecuenciaCopia::SinCambios(s) if s.revision.sequence == 1)
        );
        assert!(matches!(
            cambiar(&recurso, actual.revision, 3),
            Err(NsError::InvalidInput)
        ));
        assert_eq!(consultar(&recurso).unwrap().revision.sequence, 1);
    }

    #[test]
    fn una_revision_que_no_puede_guardarse_revierte_la_preferencia() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let recurso = nuevo(&db).unwrap();
        let antes = consultar(&recurso).unwrap();
        let mut conn = db.conexion().unwrap();
        let tx = db::transaccion_de_escritura(&mut conn).unwrap();
        tx.execute_batch("CREATE TRIGGER impedir_revision BEFORE UPDATE ON revision_de_recursos BEGIN SELECT RAISE(ABORT, 'fallo de prueba'); END;").unwrap();
        tx.commit().unwrap();
        assert!(matches!(
            cambiar(&recurso, antes.revision, 7),
            Err(NsError::StorageFailure)
        ));
        let despues = consultar(&recurso).unwrap();
        assert_eq!(despues.cada_dias, antes.cada_dias);
        assert_eq!(despues.revision.sequence, 0);
    }

    #[tokio::test]
    async fn un_cambio_nativo_publica_la_misma_revision_que_el_enlace() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let recurso = nuevo(&db).unwrap();
        let (inicial, mut observador) = recurso.subscribe().unwrap();
        cambiar(
            &recurso,
            FrecuenciaCopia::from(inicial.as_ref()).revision,
            30,
        )
        .unwrap();
        let nb_capability::ResourceEvent::Confirmed(actual) = observador.next().await.unwrap()
        else {
            panic!("confirmacion esperada")
        };
        assert_eq!(actual.value, 30);
        assert_eq!(actual.revision.sequence.get(), 1);
        assert_eq!(recurso.read().unwrap().revision, actual.revision);
    }

    #[test]
    fn migrar_v11_conserva_la_identidad_la_preferencia_heredada_y_el_respaldo() {
        let dir = std::env::temp_dir().join(format!(
            "nb-sound-frecuencia-{}-{}",
            std::process::id(),
            String::from(nb_protocol::local::new_session().unwrap())
        ));
        std::fs::create_dir(&dir).unwrap();
        struct Limpiar(std::path::PathBuf);
        impl Drop for Limpiar {
            fn drop(&mut self) {
                let _ = std::fs::remove_dir_all(&self.0);
            }
        }
        let _limpiar = Limpiar(dir.clone());
        let path = dir.join("sound.sqlite");
        let db = BaseDeDatos::abrir(&path).unwrap();
        let id: String = db
            .conexion()
            .unwrap()
            .query_row(
                "SELECT valor FROM instalacion WHERE clave='id_instalacion'",
                [],
                |r| r.get(0),
            )
            .unwrap();
        {
            let mut conn = db.conexion().unwrap();
            let tx = db::transaccion_de_escritura(&mut conn).unwrap();
            tx.execute_batch("DROP TABLE revision_de_recursos; INSERT INTO preferencias(clave,valor) VALUES('copia_cada_dias','1.0'); PRAGMA user_version=11;").unwrap();
            tx.commit().unwrap();
        }
        drop(db);
        let db = BaseDeDatos::abrir(&path).unwrap();
        let recurso = nuevo(&db).unwrap();
        let antes = recurso.read().unwrap();
        assert_eq!(antes.value, 1);
        assert_eq!(antes.revision.sequence.get(), 0);
        assert_eq!(String::from(antes.key.installation_id.clone()), id);
        let backup_path = dir.join("sound.sqlite.v11.respaldo");
        let backup = rusqlite::Connection::open(&backup_path).unwrap();
        assert_eq!(
            backup
                .pragma_query_value::<i64, _>(None, "user_version", |r| r.get(0))
                .unwrap(),
            11
        );
        let frecuencia: String = backup
            .query_row(
                "SELECT valor FROM preferencias WHERE clave='copia_cada_dias'",
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(frecuencia, "1.0");
        drop(backup);
        recurso.compare_and_set(&antes.revision, 7).unwrap();
        drop(recurso);
        drop(db);
        let db = BaseDeDatos::abrir(&path).unwrap();
        let reabierto = nuevo(&db).unwrap();
        let despues = reabierto.read().unwrap();
        assert_eq!(despues.value, 7);
        assert_eq!(despues.revision.sequence.get(), 1);
        assert_ne!(despues.revision.epoch, antes.revision.epoch);
        assert!(matches!(
            reabierto.compare_and_set(&antes.revision, 30).unwrap(),
            ChangeResult::Conflict(_)
        ));
        // Una base procedente del respaldo V11 también puede migrar por sí sola.
        let restaurada = BaseDeDatos::abrir(&backup_path).unwrap();
        assert_eq!(
            consultar(&nuevo(&restaurada).unwrap()).unwrap().cada_dias,
            1
        );
    }
}
