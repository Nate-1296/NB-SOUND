use super::*;
use nb_capability::attachment::{
    AttachmentError, ClientIdentity, Participants, PendingChallenge, SecretStore,
};
use std::path::PathBuf;

struct Temp(PathBuf);
impl Temp {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "ns-auth-{}",
            String::from(nb_protocol::local::new_session().unwrap())
        ));
        std::fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn path(&self) -> PathBuf {
        self.0.join("autorizaciones.sqlite3")
    }
    fn open(&self) -> Almacen {
        Almacen::abrir(&self.path(), resource()).unwrap()
    }
}
impl Drop for Temp {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}
struct Seed(u8);
impl SecretStore for Seed {
    fn load(&self) -> Result<Option<zeroize::Zeroizing<Vec<u8>>>, AttachmentError> {
        Ok(Some(zeroize::Zeroizing::new(vec![self.0; 32])))
    }
    fn save(&self, _: &[u8]) -> Result<(), AttachmentError> {
        unreachable!()
    }
}
fn resource() -> ResourceKey {
    ResourceKey {
        app_id: "nb.sound".to_owned().try_into().unwrap(),
        installation_id: "fixture".to_owned().try_into().unwrap(),
        capability_id: "backup.frequency".to_owned().try_into().unwrap(),
        major_version: std::num::NonZeroU16::MIN,
        resource_id: "schedule".to_owned().try_into().unwrap(),
    }
}
fn client(seed: u8, access: Access) -> VerifiedClient {
    client_for(seed, access, resource())
}
fn client_for(seed: u8, access: Access, resource: ResourceKey) -> VerifiedClient {
    let identity = ClientIdentity::open(&Seed(seed), false).unwrap();
    let participants = Participants::new(std::process::id(), std::process::id()).unwrap();
    let mut pending =
        PendingChallenge::new(resource.clone(), identity.public(), access, participants).unwrap();
    pending
        .consume(
            &identity
                .prove(pending.challenge(), &resource, access, participants)
                .unwrap(),
        )
        .unwrap()
}
fn pending(store: &Almacen, seed: u8, access: Access) -> Pendiente {
    let Solicitud::Consentimiento(pending) = store.solicitar(client(seed, access)).unwrap() else {
        panic!("requiere consentimiento");
    };
    pending
}

#[test]
fn denegar_no_persiste_y_aceptar_recuerda_identidad_ambito_e_instalacion() {
    let temp = Temp::new();
    let store = temp.open();
    drop(pending(&store, 7, Access::READ_ONLY));
    let request = pending(&store, 7, Access::READ_ONLY);
    assert!(request.vigente());
    assert_eq!(request.permisos(), Access::READ_ONLY);
    assert!(store.aceptar(request).unwrap().is_some());
    assert!(matches!(
        store.solicitar(client(7, Access::READ_ONLY)).unwrap(),
        Solicitud::Autorizada(_)
    ));
    assert!(matches!(
        store.solicitar(client(7, Access::ALL)).unwrap(),
        Solicitud::Consentimiento(_)
    ));
    assert!(matches!(
        store.solicitar(client(8, Access::READ_ONLY)).unwrap(),
        Solicitud::Consentimiento(_)
    ));
    drop(store);
    let reopened = temp.open();
    assert!(matches!(
        reopened.solicitar(client(7, Access::READ_ONLY)).unwrap(),
        Solicitud::Autorizada(_)
    ));
    drop(reopened);
    let mut other = resource();
    other.installation_id = "different".to_owned().try_into().unwrap();
    let store = Almacen::abrir(&temp.path(), other.clone()).unwrap();
    assert!(matches!(
        store
            .solicitar(client_for(7, Access::READ_ONLY, other))
            .unwrap(),
        Solicitud::Consentimiento(_)
    ));
    assert!(matches!(
        store.solicitar(client(7, Access::ALL)),
        Err(NsError::InvalidInput)
    ));
}

#[test]
fn revocar_invalida_sesiones_dialogos_antiguos_y_adhesiones_tras_reabrir() {
    let temp = Temp::new();
    let store = temp.open();
    let request = pending(&store, 7, Access::READ_ONLY);
    let public = request.identidad().clone();
    let first = store.aceptar(request).unwrap().unwrap();
    let Solicitud::Autorizada(second) = store.solicitar(client(7, Access::READ_ONLY)).unwrap()
    else {
        panic!();
    };
    let expansion = pending(&store, 7, Access::ALL);
    store.revocar(&public).unwrap();
    assert!(*first.revoked.borrow());
    assert!(*second.revoked.borrow());
    assert!(store.aceptar(expansion).unwrap().is_none());
    assert!(matches!(
        store.solicitar(client(7, Access::ALL)).unwrap(),
        Solicitud::Revocada
    ));
    drop(store);
    assert!(matches!(
        temp.open().solicitar(client(7, Access::ALL)).unwrap(),
        Solicitud::Revocada
    ));
}

#[test]
fn revocar_antes_del_primer_consentimiento_tambien_persiste_una_tumba() {
    let temp = Temp::new();
    let store = temp.open();
    let request = pending(&store, 7, Access::ALL);
    store.revocar(request.identidad()).unwrap();
    assert!(store.aceptar(request).unwrap().is_none());
    drop(store);
    assert!(matches!(
        temp.open().solicitar(client(7, Access::ALL)).unwrap(),
        Solicitud::Revocada
    ));
}

#[test]
fn permitir_otra_solicitud_no_concede_permisos_ni_recupera_un_dialogo_anterior() {
    let temp = Temp::new();
    let store = temp.open();
    let stale = pending(&store, 7, Access::ALL);
    let public = stale.identidad().clone();
    store.revocar(&public).unwrap();
    assert!(store.permitir_nueva_solicitud(&public).unwrap());
    assert!(!store.permitir_nueva_solicitud(&public).unwrap());
    assert!(store.aceptar(stale).unwrap().is_none());
    drop(store);
    let reopened = temp.open();
    let fresh = pending(&reopened, 7, Access::ALL);
    assert!(reopened.aceptar(fresh).unwrap().is_some());
}

#[test]
fn revocacion_general_invalida_dialogos_sin_fila_y_no_recupera_permisos_al_desbloquear() {
    let temp = Temp::new();
    let store = temp.open();
    let unseen = pending(&store, 8, Access::ALL);
    let lease = store
        .aceptar(pending(&store, 7, Access::READ_ONLY))
        .unwrap()
        .unwrap();
    let expansion = pending(&store, 7, Access::ALL);
    assert_eq!(store.resumen().unwrap(), (1, 0));
    store.revocar_todas().unwrap();
    assert_eq!(store.resumen().unwrap(), (0, 1));
    assert!(*lease.revoked.borrow());
    assert!(store.aceptar(unseen).unwrap().is_none());
    assert!(store.aceptar(expansion).unwrap().is_none());
    store.permitir_nuevas_solicitudes().unwrap();
    assert_eq!(store.resumen().unwrap(), (0, 0));
    assert!(store
        .aceptar(pending(&store, 7, Access::ALL))
        .unwrap()
        .is_some());
}

#[test]
fn un_permiso_persistente_retira_la_compatibilidad_heredada_y_no_se_reactiva_al_restaurar() {
    let temp = Temp::new();
    let store = temp.open();
    let blocked = store.bloqueo_heredado();
    assert!(!*blocked.borrow());
    let request = pending(&store, 7, Access::ALL);
    let public = request.identidad().clone();
    store.aceptar(request).unwrap().unwrap();
    assert!(*blocked.borrow());
    store.revocar(&public).unwrap();
    store.permitir_nueva_solicitud(&public).unwrap();
    assert!(*blocked.borrow());
    drop(store);
    // Incluso cambiar la instalación de la biblioteca no rehabilita el bootstrap.
    let mut other = resource();
    other.installation_id = "restored".to_owned().try_into().unwrap();
    let store = Almacen::abrir(&temp.path(), other).unwrap();
    assert!(*store.bloqueo_heredado().borrow());
}

#[test]
fn una_revocacion_sin_filas_bloquea_el_enlace_heredado_pero_un_commit_fallido_no_lo_simula() {
    let temp = Temp::new();
    let store = temp.open();
    store
        .lock()
        .unwrap()
        .conn
        .execute_batch(
            "CREATE TRIGGER negar INSERT ON concesiones BEGIN SELECT RAISE(ABORT,'fixture'); END;",
        )
        .unwrap();
    assert!(matches!(
        store.aceptar(pending(&store, 7, Access::ALL)),
        Err(NsError::StorageFailure)
    ));
    assert!(!*store.bloqueo_heredado().borrow());
    store.revocar_todas().unwrap();
    assert!(*store.bloqueo_heredado().borrow());
    drop(store);
    assert!(*temp.open().bloqueo_heredado().borrow());
}

#[test]
fn una_segunda_autoridad_no_mantiene_sesiones_ajenas_a_la_revocacion() {
    let temp = Temp::new();
    let store = temp.open();
    assert!(matches!(
        Almacen::abrir(&temp.path(), resource()),
        Err(NsError::ComponentUnavailable)
    ));
    let lease = store
        .aceptar(pending(&store, 7, Access::ALL))
        .unwrap()
        .unwrap();
    drop(store);
    assert!(lease.revoked.has_changed().is_err());
    assert!(Almacen::abrir(&temp.path(), resource()).is_ok());
}

#[test]
fn respuestas_de_consentimiento_duplicadas_no_sobrescriben_decisiones_nuevas() {
    let temp = Temp::new();
    let store = temp.open();
    let first = pending(&store, 7, Access::READ_ONLY);
    let stale = pending(&store, 7, Access::ALL);
    let lease = store.aceptar(first).unwrap().unwrap();
    assert!(store.aceptar(stale).unwrap().is_none());
    assert!(!*lease.revoked.borrow());
    let expanded = store
        .aceptar(pending(&store, 7, Access::ALL))
        .unwrap()
        .unwrap();
    assert!(*lease.revoked.borrow());
    assert!(!*expanded.revoked.borrow());
}

#[test]
fn un_error_de_persistencia_no_confirma_revocacion_ni_cierra_una_concesion_valida() {
    let temp = Temp::new();
    let store = temp.open();
    let lease = store
        .aceptar(pending(&store, 7, Access::ALL))
        .unwrap()
        .unwrap();
    store
        .lock()
        .unwrap()
        .conn
        .execute_batch(
            "CREATE TRIGGER negar UPDATE ON concesiones BEGIN SELECT RAISE(ABORT,'fixture'); END;",
        )
        .unwrap();
    assert!(matches!(
        store.revocar(lease.client.public()),
        Err(NsError::StorageFailure)
    ));
    assert!(!*lease.revoked.borrow());
    assert!(matches!(
        store.solicitar(client(7, Access::ALL)).unwrap(),
        Solicitud::Autorizada(_)
    ));
}

#[cfg(unix)]
#[test]
fn un_enlace_simbolico_no_redirige_el_registro_o_su_bloqueo() {
    for lock in [false, true] {
        let temp = Temp::new();
        let other = temp.0.join("other");
        std::fs::write(&other, b"untouched").unwrap();
        std::os::unix::fs::symlink(
            &other,
            if lock {
                temp.path().with_extension("lock")
            } else {
                temp.path()
            },
        )
        .unwrap();
        assert!(matches!(
            Almacen::abrir(&temp.path(), resource()),
            Err(NsError::PathNotAllowed)
        ));
        assert_eq!(std::fs::read(&other).unwrap(), b"untouched");
    }
}
