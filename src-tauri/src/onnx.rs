//! El entorno de ONNX Runtime, compartido por el karaoke y el análisis (ADR-002).
//!
//! La biblioteca viaja dentro del instalador (`binarios/`, ADR-006) y se carga en
//! tiempo de ejecución (`load-dynamic`): sin ella la aplicación arranca igual y
//! solo lo que usa modelos dice que no está disponible. La ruta la fija el
//! arranque, que es quien sabe dónde quedaron los recursos de la aplicación.

use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock, PoisonError};

use ort::environment::Environment;

use crate::error::{NsError, NsResult};

static RUTA: OnceLock<PathBuf> = OnceLock::new();
/// La carpeta del agregado de aceleración, si está instalado (F5.1.5).
static ACELERADA: OnceLock<PathBuf> = OnceLock::new();
static ENTORNO: OnceLock<Environment> = OnceLock::new();
/// Una carga a la vez; el resultado bueno queda en `ENTORNO`.
static CARGANDO: Mutex<()> = Mutex::new(());

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
/// Con el agregado de aceleración instalado, su ONNX Runtime (con el proveedor de
/// la GPU) sustituye al que viaja dentro. Se fija al arrancar: el entorno de ONNX
/// Runtime se carga una vez por proceso, así que instalarlo se nota al reiniciar.
pub fn fijar_aceleracion(carpeta: &Path) {
    if carpeta.join(nombre_biblioteca()).is_file() {
        let _ = ACELERADA.set(carpeta.to_path_buf());
    }
}

/// Las bibliotecas de CUDA del agregado, cargadas antes que ONNX Runtime y a la
/// vista del resto (`RTLD_GLOBAL`): su proveedor las busca por su nombre y no
/// mira en la carpeta del agregado. En orden de dependencias.
#[cfg(target_os = "linux")]
fn precargar(carpeta: &Path) {
    let Ok(leidas) = std::fs::read_dir(carpeta) else {
        return;
    };
    let mut todas: Vec<PathBuf> = leidas.flatten().map(|e| e.path()).collect();
    todas.sort();
    for prefijo in [
        "libcudart",
        "libcublasLt",
        "libcublas.",
        "libcufft",
        "libcurand",
        "libcudnn",
    ] {
        for ruta in todas.iter().filter(|r| {
            r.file_name()
                .and_then(|n| n.to_str())
                .is_some_and(|n| n.starts_with(prefijo) && n.contains(".so"))
        }) {
            let Ok(c) = std::ffi::CString::new(ruta.as_os_str().as_encoded_bytes()) else {
                continue;
            };
            // SAFETY: `c` es una ruta terminada en cero que vive durante la llamada;
            // la biblioteca queda cargada para todo el proceso, que es lo que se busca.
            let h = unsafe { libc::dlopen(c.as_ptr(), libc::RTLD_NOW | libc::RTLD_GLOBAL) };
            if h.is_null() {
                tracing::debug!("una biblioteca del agregado de aceleración no cargó");
            }
        }
    }
}

/// Los proveedores de ejecución de una sesión: el de la GPU primero si el agregado
/// está cargado, y siempre el de CPU detrás. Si la GPU no está (otro equipo, sin
/// controlador), ONNX Runtime sigue con la CPU sin fallar.
#[must_use]
pub fn proveedores(
    cpu: ort::ep::ExecutionProviderDispatch,
) -> Vec<ort::ep::ExecutionProviderDispatch> {
    let mut v = Vec::new();
    if ACELERADA.get().is_some()
        && ENTORNO.get().is_some()
        && CON_GPU.get().copied().unwrap_or(false)
    {
        #[cfg(target_os = "linux")]
        v.push(ort::ep::CUDA::default().build());
    }
    v.push(cpu);
    v
}

/// Si el entorno que se cargó es el del agregado de aceleración.
static CON_GPU: OnceLock<bool> = OnceLock::new();

pub fn fijar_ruta(ruta: &Path) {
    let _ = RUTA.set(ruta.to_path_buf());
}

/// El entorno, cargado la primera vez que se pide.
///
/// # Errors
///
/// [`NsError::ComponentUnavailable`] si no hay biblioteca o no se puede cargar.
pub fn entorno() -> NsResult<&'static Environment> {
    if let Some(e) = ENTORNO.get() {
        return Ok(e);
    }
    let _cargando = CARGANDO.lock().unwrap_or_else(PoisonError::into_inner);
    if let Some(e) = ENTORNO.get() {
        return Ok(e);
    }
    // Antes el fallo se guardaba para siempre: el karaoke arranca antes de que se
    // fije la ruta, y si tenía trabajo pendiente pedía el entorno primero; desde
    // ese momento ni el karaoke ni el análisis podían usar modelos en toda la
    // sesión. Ahora solo se guarda el entorno que cargó, y lo demás se reintenta.
    if let Some(carpeta) = ACELERADA.get() {
        #[cfg(target_os = "linux")]
        precargar(carpeta);
        if let Ok(Ok(e)) = ort::init_from(carpeta.join(nombre_biblioteca()))
            .map(|b| b.with_name("nb-sound").build())
        {
            tracing::info!("ONNX Runtime con aceleración");
            let _ = CON_GPU.set(true);
            return Ok(ENTORNO.get_or_init(|| e));
        }
        tracing::warn!("el agregado de aceleración no cargó; sigue con el de CPU");
    }
    let ruta = RUTA.get().ok_or(NsError::ComponentUnavailable)?;
    if !ruta.is_file() {
        tracing::warn!("no está la biblioteca de ONNX Runtime");
        return Err(NsError::ComponentUnavailable);
    }
    match ort::init_from(ruta).map(|b| b.with_name("nb-sound").build()) {
        Ok(Ok(e)) => {
            let _ = CON_GPU.set(false);
            Ok(ENTORNO.get_or_init(|| e))
        }
        _ => {
            tracing::error!("no se pudo cargar ONNX Runtime");
            Err(NsError::ComponentUnavailable)
        }
    }
}

/// Hilos para un trabajo de fondo con modelos: una fracción `1/divisor` de los
/// núcleos, al menos uno. El karaoke y el análisis nunca deben competir con la
/// interfaz ni con el audio.
#[must_use]
pub fn hilos_de_fondo(divisor: usize) -> usize {
    std::thread::available_parallelism()
        .map(|n| n.get() / divisor.max(1))
        .unwrap_or(1)
        .max(1)
}

/// Si el arranque ya dijo dónde está la biblioteca. Hasta entonces, quien usa
/// modelos espera en vez de dar su trabajo por fallido.
#[must_use]
pub fn ruta_fijada() -> bool {
    RUTA.get().is_some()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn el_trabajo_de_fondo_deja_libre_la_mayor_parte_del_equipo() {
        let n = std::thread::available_parallelism().map_or(1, |n| n.get());
        assert!(hilos_de_fondo(4) >= 1);
        assert!(hilos_de_fondo(4) <= n.div_ceil(4).max(1));
        assert_eq!(hilos_de_fondo(10_000), 1, "al menos uno");
    }

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
