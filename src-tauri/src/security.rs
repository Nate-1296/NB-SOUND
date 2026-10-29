//! Validación de rutas: la defensa de la frontera IPC.
//!
//! El webview es una zona no confiable: una portada o una letra descargadas
//! podrían comprometerlo. Ninguna ruta que venga de ahí se usa tal cual; tampoco
//! las que trae un manifiesto de agregado. Portado de NB Books.

use std::path::{Path, PathBuf};

use crate::error::{NsError, NsResult};

/// Resuelve una ruta y comprueba que queda dentro de `scope`.
///
/// Resuelve la ruta canónicamente, lo que sigue los enlaces simbólicos, y
/// después comprueba la contención. Ese orden es el que importa: comprobar
/// antes de resolver permite escapar con un enlace simbólico.
///
/// # Errors
///
/// - [`NsError::FileNotFound`] si la ruta no existe.
/// - [`NsError::PathNotAllowed`] si, una vez resuelta, queda fuera del ámbito.
pub fn resolve_within(scope: &Path, candidate: &Path) -> NsResult<PathBuf> {
    let scope = scope.canonicalize().map_err(|_| NsError::StorageFailure)?;

    let candidate = if candidate.is_absolute() {
        candidate.to_path_buf()
    } else {
        scope.join(candidate)
    };

    let resolved = candidate.canonicalize().map_err(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            NsError::FileNotFound
        } else {
            NsError::PathNotAllowed
        }
    })?;

    if !resolved.starts_with(&scope) {
        tracing::warn!(
            ruta = %crate::telemetry::redact_path(&resolved),
            "se rechazó una ruta fuera del ámbito permitido"
        );
        return Err(NsError::PathNotAllowed);
    }

    Ok(resolved)
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Temporal(PathBuf);

    impl Temporal {
        fn nuevo(nombre: &str) -> Self {
            let dir = std::env::temp_dir().join(format!("ns-sec-{nombre}-{}", std::process::id()));
            let _ = std::fs::remove_dir_all(&dir);
            std::fs::create_dir_all(&dir).expect("directorio");
            Self(dir)
        }
    }

    impl Drop for Temporal {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn acepta_una_ruta_dentro_del_ambito() {
        let tmp = Temporal::nuevo("dentro");
        let archivo = tmp.0.join("cancion.mp3");
        std::fs::write(&archivo, b"x").expect("escritura");

        let resuelta = resolve_within(&tmp.0, Path::new("cancion.mp3")).expect("aceptada");
        assert!(resuelta.starts_with(tmp.0.canonicalize().expect("canónica")));
    }

    /// El archivo objetivo se crea de verdad fuera del ámbito. Aceptar también
    /// `FileNotFound` haría pasar esta prueba en una máquina donde el objetivo
    /// simplemente no exista, que es justo el caso en que no prueba nada.
    #[test]
    fn rechaza_el_recorrido_de_directorios() {
        let tmp = Temporal::nuevo("recorrido");
        let fuera = tmp.0.join("..").join(format!(
            "ns-sec-objetivo-{}-{}",
            std::process::id(),
            "recorrido"
        ));
        std::fs::write(&fuera, b"secreto").expect("archivo fuera del ámbito");

        let relativa = Path::new("..").join(fuera.file_name().expect("nombre"));
        let resultado = resolve_within(&tmp.0, &relativa);

        let _ = std::fs::remove_file(&fuera);
        assert!(
            matches!(resultado, Err(NsError::PathNotAllowed)),
            "un objetivo existente fuera del ámbito debe rechazarse por ámbito: {resultado:?}"
        );
    }

    #[test]
    fn rechaza_una_ruta_absoluta_fuera_del_ambito() {
        let tmp = Temporal::nuevo("absoluta");
        let fuera = Temporal::nuevo("absoluta-destino");
        let archivo = fuera.0.join("ajena.mp3");
        std::fs::write(&archivo, b"x").expect("archivo");

        let resultado = resolve_within(&tmp.0, &archivo);

        assert!(
            matches!(resultado, Err(NsError::PathNotAllowed)),
            "una ruta absoluta existente fuera del ámbito debe rechazarse: {resultado:?}"
        );
    }

    /// El caso que hace obligatorio canonicalizar **antes** de comprobar: una
    /// comprobación textual aceptaría este enlace porque su ruta empieza dentro
    /// del ámbito.
    #[cfg(unix)]
    #[test]
    fn rechaza_un_enlace_simbolico_que_escapa_del_ambito() {
        let tmp = Temporal::nuevo("enlace");
        let enlace = tmp.0.join("fuga");
        std::os::unix::fs::symlink("/etc", &enlace).expect("enlace");

        let resultado = resolve_within(&tmp.0, Path::new("fuga/hostname"));
        assert!(matches!(resultado, Err(NsError::PathNotAllowed)));
    }

    #[test]
    fn una_ruta_inexistente_se_distingue_de_una_prohibida() {
        let tmp = Temporal::nuevo("inexistente");
        let resultado = resolve_within(&tmp.0, Path::new("no-existe.mp3"));
        assert!(matches!(resultado, Err(NsError::FileNotFound)));
    }
}
