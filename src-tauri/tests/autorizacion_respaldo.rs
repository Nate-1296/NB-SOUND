//! ADR-017: restaurar biblioteca nunca recupera confianza ni elimina revocaciones.
use nb_capability::attachment::{
    Access, AttachmentError, ClientIdentity, Participants, PendingChallenge, SecretStore,
    VerifiedClient,
};
use nb_protocol::capability::ResourceKey;
use nb_sound_lib::{
    autorizacion_launcher::{Almacen, Solicitud},
    copia_seguridad,
    db::BaseDeDatos,
    frecuencia_compartida,
    paths::Rutas,
};
use std::{fs::File, path::PathBuf};
use zeroize::Zeroizing;

struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "ns-auth-backup-{}",
            String::from(nb_protocol::local::new_session().unwrap())
        ));
        std::fs::create_dir(&path).unwrap();
        Self(path)
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}
struct Seed;
impl SecretStore for Seed {
    fn load(&self) -> Result<Option<Zeroizing<Vec<u8>>>, AttachmentError> {
        Ok(Some(Zeroizing::new(vec![7; 32])))
    }
    fn save(&self, _: &[u8]) -> Result<(), AttachmentError> {
        unreachable!()
    }
}
fn client(resource: ResourceKey) -> VerifiedClient {
    let identity = ClientIdentity::open(&Seed, false).unwrap();
    let participants = Participants::new(std::process::id(), std::process::id()).unwrap();
    let mut pending = PendingChallenge::new(
        resource.clone(),
        identity.public(),
        Access::ALL,
        participants,
    )
    .unwrap();
    pending
        .consume(
            &identity
                .prove(pending.challenge(), &resource, Access::ALL, participants)
                .unwrap(),
        )
        .unwrap()
}

#[test]
fn restaurar_datos_conserva_revocacion_y_no_transporta_permisos_a_otro_perfil() {
    let fixture = Fixture::new();
    let rutas = Rutas::bajo(&fixture.0.join("original")).unwrap();
    let db = BaseDeDatos::abrir(&rutas.base_de_datos()).unwrap();
    let resource = frecuencia_compartida::nuevo(&db).unwrap();
    let initial = resource.read().unwrap();
    resource.compare_and_set(&initial.revision, 7).unwrap();
    let key = initial.key.clone();
    let path = rutas.datos.join("autorizaciones-launcher.sqlite3");
    let store = Almacen::abrir(&path, key.clone()).unwrap();
    let Solicitud::Consentimiento(pending) = store.solicitar(client(key.clone())).unwrap() else {
        panic!();
    };
    let lease = store.aceptar(pending).unwrap().unwrap();
    let public = lease.client.public().clone();
    let backup = fixture.0.join("copia.nbsound-backup");
    copia_seguridad::crear(&db, &rutas, &backup).unwrap();
    let mut zip = zip::ZipArchive::new(File::open(&backup).unwrap()).unwrap();
    for index in 0..zip.len() {
        let entry = zip.by_index(index).unwrap();
        let name = entry.name().unwrap();
        assert!(!name.contains("autorizaciones"));
        assert!(!name.contains("instance.lock"));
    }
    drop(zip);
    store.revocar(&public).unwrap();
    assert!(*lease.revoked.borrow());
    resource
        .compare_and_set(&resource.read().unwrap().revision, 30)
        .unwrap();
    drop(lease);
    drop(store);
    drop(resource);
    drop(db);
    copia_seguridad::preparar_restauracion(&rutas, &backup).unwrap();
    copia_seguridad::aplicar_restauracion_pendiente(&rutas);
    let restored_db = BaseDeDatos::abrir(&rutas.base_de_datos()).unwrap();
    let restored = frecuencia_compartida::nuevo(&restored_db).unwrap();
    let snapshot = restored.read().unwrap();
    assert_eq!(snapshot.value, 7);
    assert_eq!(snapshot.key, key);
    let store = Almacen::abrir(&path, snapshot.key.clone()).unwrap();
    assert!(matches!(
        store.solicitar(client(snapshot.key.clone())).unwrap(),
        Solicitud::Revocada
    ));

    let other = Rutas::bajo(&fixture.0.join("another")).unwrap();
    copia_seguridad::preparar_restauracion(&other, &backup).unwrap();
    copia_seguridad::aplicar_restauracion_pendiente(&other);
    let other_db = BaseDeDatos::abrir(&other.base_de_datos()).unwrap();
    let other_resource = frecuencia_compartida::nuevo(&other_db).unwrap();
    let other_key = other_resource.read().unwrap().key.clone();
    let store = Almacen::abrir(
        &other.datos.join("autorizaciones-launcher.sqlite3"),
        other_key.clone(),
    )
    .unwrap();
    assert!(matches!(
        store.solicitar(client(other_key)).unwrap(),
        Solicitud::Consentimiento(_)
    ));
}
