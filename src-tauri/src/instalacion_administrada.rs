//! ADR-015: el gestor controla los binarios; Sound conserva todos sus datos.
#[cfg(target_os = "linux")]
use crate::error::NsError;
use crate::error::NsResult;
use std::{fs::File, path::PathBuf};

pub const MARCA: &[u8] = b"nb-launcher-managed-v1\n";

pub struct Instalacion {
    _uso: File,
    pub recursos: PathBuf,
}

#[cfg(target_os = "linux")]
fn base(executable: &std::path::Path) -> NsResult<Option<PathBuf>> {
    let bin = executable.parent().ok_or(NsError::StorageFailure)?;
    let version = bin.parent().and_then(|p| p.parent());
    let managed_layout = version.is_some_and(|version| {
        let hash = version.file_name().and_then(|v| v.to_str()).unwrap_or("");
        bin.file_name().is_some_and(|n| n == "bin")
            && bin
                .parent()
                .and_then(|p| p.file_name())
                .is_some_and(|n| n == "usr")
            && version
                .parent()
                .and_then(|p| p.file_name())
                .is_some_and(|n| n == "nb.sound")
            && hash.len() == 64
            && hash
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    });
    let marker = bin.join(".nb-launcher-managed");
    match std::fs::symlink_metadata(&marker) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            // Un ejecutable retirado durante su arranque no se convierte en una
            // instalación independiente por haber perdido ya su marca.
            return if managed_layout {
                Err(NsError::StorageFailure)
            } else {
                Ok(None)
            };
        }
        Ok(meta) if meta.is_file() && meta.len() == MARCA.len() as u64 => {}
        _ => return Err(NsError::StorageFailure),
    }
    if !managed_layout
        || executable.file_name().is_none_or(|n| n != "nb-sound")
        || std::fs::read(marker).map_err(|_| NsError::StorageFailure)? != MARCA
    {
        return Err(NsError::StorageFailure);
    }
    let version = version.ok_or(NsError::StorageFailure)?;
    Ok(Some(version.to_path_buf()))
}

pub fn abrir() -> NsResult<Option<Instalacion>> {
    #[cfg(target_os = "linux")]
    {
        let executable = std::env::current_exe().map_err(|_| NsError::StorageFailure)?;
        abrir_en(&executable)
    }
    #[cfg(not(target_os = "linux"))]
    {
        Ok(None)
    }
}

#[cfg(target_os = "linux")]
fn abrir_en(executable: &std::path::Path) -> NsResult<Option<Instalacion>> {
    let Some(version) = base(executable)? else {
        return Ok(None);
    };
    let lock = version
        .parent()
        .ok_or(NsError::StorageFailure)?
        .join("running.lock");
    // El gestor crea este archivo y nunca lo retira, para no dividir el bloqueo.
    if !std::fs::symlink_metadata(&lock).is_ok_and(|m| m.is_file()) {
        return Err(NsError::StorageFailure);
    }
    let usage = File::open(lock).map_err(|_| NsError::StorageFailure)?;
    usage
        .try_lock_shared()
        .map_err(|_| NsError::ComponentUnavailable)?;
    Ok(Some(Instalacion {
        _uso: usage,
        recursos: version.join("usr/lib/NB Sound"),
    }))
}

pub fn comprobar_actualizador_propio() -> NsResult<()> {
    #[cfg(target_os = "linux")]
    {
        let executable = std::env::current_exe().map_err(|_| NsError::StorageFailure)?;
        if base(&executable)?.is_some() {
            return Err(NsError::InstallationManaged);
        }
    }
    Ok(())
}

#[cfg(all(test, target_os = "linux"))]
mod pruebas {
    use super::*;
    #[test]
    fn el_bloqueo_impide_sustituir_binarios_en_uso_y_los_recursos_son_locales() {
        let root = std::env::temp_dir().join(format!(
            "nb-managed-{}",
            String::from(nb_protocol::local::new_session().unwrap())
        ));
        struct Cleanup(PathBuf);
        impl Drop for Cleanup {
            fn drop(&mut self) {
                let _ = std::fs::remove_dir_all(&self.0);
            }
        }
        let _cleanup = Cleanup(root.clone());
        let app = root.join("nb.sound");
        let version = app.join("a".repeat(64));
        let bin = version.join("usr/bin");
        std::fs::create_dir_all(&bin).unwrap();
        let executable = bin.join("nb-sound");
        assert!(abrir_en(&root.join("nb-sound")).unwrap().is_none());
        assert!(matches!(
            abrir_en(&executable),
            Err(NsError::StorageFailure)
        ));
        std::fs::write(bin.join(".nb-launcher-managed"), MARCA).unwrap();
        let mutation = File::create(app.join("running.lock")).unwrap();
        let active = abrir_en(&executable).unwrap().unwrap();
        assert_eq!(active.recursos, version.join("usr/lib/NB Sound"));
        assert!(mutation.try_lock().is_err());
        drop(active);
        mutation.try_lock().unwrap();
        assert!(matches!(
            abrir_en(&executable),
            Err(NsError::ComponentUnavailable)
        ));
        std::fs::write(bin.join(".nb-launcher-managed"), b"invalid").unwrap();
        assert!(matches!(
            abrir_en(&executable),
            Err(NsError::StorageFailure)
        ));
    }
}
