use super::*;
use std::os::unix::fs::PermissionsExt;

struct Fixture {
    app: Identifier,
    profile: Identifier,
    path: PathBuf,
}
impl Fixture {
    fn new() -> Self {
        let app: Identifier = "nb.test".to_owned().try_into().unwrap();
        let profile: Identifier = String::from(crate::local::new_session().unwrap())
            .try_into()
            .unwrap();
        let path = root()
            .unwrap()
            .join("app-nb.test")
            .join(format!("profile-{}", String::from(profile.clone())));
        Self { app, profile, path }
    }
    fn claim(&self) -> Result<Claim> {
        claim(&self.app, &self.profile)
    }
    fn discover(&self) -> Result<Option<Advertisement>> {
        discover(&self.app, &self.profile)
    }
    fn advertisement(&self) -> Advertisement {
        Advertisement::new(
            crate::local::new_session().unwrap(),
            ResourceKey {
                app_id: self.app.clone(),
                installation_id: "fixture".to_owned().try_into().unwrap(),
                capability_id: "counter".to_owned().try_into().unwrap(),
                major_version: std::num::NonZeroU16::MIN,
                resource_id: "primary".to_owned().try_into().unwrap(),
            },
        )
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.path);
    }
}

#[test]
fn descubrir_no_crea_estado_y_una_sola_instancia_publica_hasta_cerrar() {
    let fixture = Fixture::new();
    assert!(fixture.discover().unwrap().is_none());
    assert!(!fixture.path.exists());
    let mut first = fixture.claim().unwrap();
    assert!(matches!(fixture.claim(), Err(Error::Busy)));
    let ad = fixture.advertisement();
    first.publish(&ad).unwrap();
    let read = fixture.discover().unwrap().unwrap();
    assert_eq!(read.pid(), std::process::id());
    assert_eq!(read.invitation(), ad.invitation());
    assert_eq!(read.resource(), ad.resource());
    let inode = std::fs::metadata(fixture.path.join("instance.lock"))
        .unwrap()
        .ino();
    drop(first);
    assert!(fixture.discover().unwrap().is_none());
    let _next = fixture.claim().unwrap();
    assert_eq!(
        std::fs::metadata(fixture.path.join("instance.lock"))
            .unwrap()
            .ino(),
        inode
    );
}

#[test]
fn publicar_no_acepta_otro_pid_aplicacion_o_version() {
    let fixture = Fixture::new();
    let mut claim = fixture.claim().unwrap();
    for field in ["pid", "application", "version"] {
        let mut ad = fixture.advertisement();
        match field {
            "pid" => ad.pid = NonZeroU32::new(std::process::id() + 1).unwrap(),
            "application" => ad.resource.app_id = "nb.other".to_owned().try_into().unwrap(),
            _ => ad.version = 2,
        }
        assert!(matches!(claim.publish(&ad), Err(Error::Invalid)));
        assert!(fixture.discover().unwrap().is_none());
    }
}

#[test]
fn un_anuncio_incompleto_extendido_o_excesivo_no_es_descubrimiento_valido() {
    let fixture = Fixture::new();
    let mut claim = fixture.claim().unwrap();
    claim.publish(&fixture.advertisement()).unwrap();
    let path = fixture.path.join("instance.json");
    let mut extended = serde_json::to_value(fixture.advertisement()).unwrap();
    extended["private_config"] = serde_json::json!(true);
    for bytes in [
        b"{".to_vec(),
        serde_json::to_vec(&extended).unwrap(),
        vec![b' '; LIMIT + 1],
    ] {
        std::fs::write(&path, bytes).unwrap();
        assert!(matches!(fixture.discover(), Err(Error::Invalid)));
    }
}

#[test]
fn archivos_enlazados_y_permisos_abiertos_no_redirigen_el_anuncio_ni_el_bloqueo() {
    for name in ["instance.lock", "instance.json"] {
        let fixture = Fixture::new();
        let mut claim = fixture.claim().unwrap();
        claim.publish(&fixture.advertisement()).unwrap();
        drop(claim);
        let destination = fixture.path.join("untouched");
        std::fs::write(&destination, b"fixture").unwrap();
        let path = fixture.path.join(name);
        let _ = std::fs::remove_file(&path);
        std::os::unix::fs::symlink(&destination, &path).unwrap();
        if name == "instance.lock" {
            assert!(matches!(fixture.claim(), Err(Error::Unsafe)));
        } else {
            assert!(matches!(fixture.discover(), Err(Error::Unsafe)));
        }
        assert_eq!(std::fs::read(&destination).unwrap(), b"fixture");
    }
    let fixture = Fixture::new();
    let claim = fixture.claim().unwrap();
    std::fs::set_permissions(&fixture.path, std::fs::Permissions::from_mode(0o777)).unwrap();
    assert!(matches!(fixture.discover(), Err(Error::Unsafe)));
    assert!(matches!(fixture.claim(), Err(Error::Unsafe)));
    drop(claim);
}
