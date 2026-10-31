//! El entorno de ONNX Runtime, compartido por el karaoke y el análisis (ADR-002).
//!
//! La biblioteca viaja dentro del instalador (`binarios/`, ADR-006) y se carga en
//! tiempo de ejecución (`load-dynamic`): sin ella la aplicación arranca igual y
//! solo lo que usa modelos dice que no está disponible. La ruta la fija el
//! arranque, que es quien sabe dónde quedaron los recursos de la aplicación.

use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use ort::environment::Environment;

use crate::error::{NsError, NsResult};

static RUTA: OnceLock<PathBuf> = OnceLock::new();
static ENTORNO: OnceLock<Option<Environment>> = OnceLock::new();

/// El nombre de la biblioteca en cada plataforma.
#[must_use]
pub fn nombre_biblioteca() -> &'static str {
    if cfg!(target_os = "windows") {
        "onnxruntime.dll"
    } else if cfg!(target_os = "macos") {
        "libonnxruntime.dylib"
    } else {
        "libonnxruntime.so"
    }
}

/// Dónde está la biblioteca. Solo cuenta la primera llamada.
pub fn fijar_ruta(ruta: &Path) {
    let _ = RUTA.set(ruta.to_path_buf());
}

/// El entorno, cargado la primera vez que se pide.
///
/// # Errors
///
/// [`NsError::ComponentUnavailable`] si no hay biblioteca o no se puede cargar.
pub fn entorno() -> NsResult<&'static Environment> {
    ENTORNO
        .get_or_init(|| {
            let ruta = RUTA.get()?;
            if !ruta.is_file() {
                tracing::warn!("no está la biblioteca de ONNX Runtime");
                return None;
            }
            match ort::init_from(ruta).map(|b| b.with_name("nb-sound").build()) {
                Ok(Ok(e)) => Some(e),
                _ => {
                    tracing::error!("no se pudo cargar ONNX Runtime");
                    None
                }
            }
        })
        .as_ref()
        .ok_or(NsError::ComponentUnavailable)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// La biblioteca de `binarios/` la deja `scripts/fetch-binarios.mjs`; sin ella
    /// la prueba se salta sola.
    #[test]
    fn la_biblioteca_que_viaja_dentro_se_carga() {
        let ruta = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("binarios")
            .join(nombre_biblioteca());
        if !ruta.is_file() {
            return;
        }
        fijar_ruta(&ruta);
        assert!(entorno().is_ok());
    }
}
