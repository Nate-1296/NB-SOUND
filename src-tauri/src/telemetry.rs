//! Observabilidad local con redacción obligatoria.
//!
//! En un producto local-first no tenemos acceso a la máquina del usuario: los
//! registros son la única herramienta de diagnóstico en producción. Y a la vez,
//! lo que una persona escucha es un dato íntimo.
//!
//! De esa tensión sale la regla de este módulo: **se registra el comportamiento
//! del sistema, nunca el contenido del usuario**: ni rutas, ni títulos, ni
//! artistas, ni claves (Constitución, regla 5). Portado de NB Books.

use std::path::Path;

// Solo lo usa el escritor de consola de depuración, que en release se compila
// fuera: sin esta condición, el perfil de release avisa de un import sin usar. No
// lo veía `pnpm verify` porque **la verificación nunca compila en release**, y lo
// destapó la puerta de empaquetado de F1.12 la primera vez que se cruzó.
#[cfg(debug_assertions)]
use tracing_subscriber::fmt::writer::MakeWriterExt;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;
use tracing_subscriber::EnvFilter;

/// Guarda que mantiene viva la escritura asíncrona a archivo.
///
/// Debe conservarse durante toda la vida del proceso: al soltarlo se vacía el
/// búfer y se deja de escribir.
pub struct TelemetryGuard(#[allow(dead_code)] tracing_appender::non_blocking::WorkerGuard);

/// Inicializa el registro estructurado.
///
/// Escribe a un archivo rotado por día en `logs_dir` y, en compilaciones de
/// depuración, también a la salida estándar.
///
/// El nivel se controla con la variable `NB_SOUND_LOG` siguiendo la sintaxis de
/// filtros de `tracing`. Por defecto es `info`.
///
/// # Errors
///
/// No falla: si el archivo de registro no se puede abrir, la aplicación debe
/// seguir arrancando. Perder el diagnóstico es malo; impedir que el usuario
/// escuche su música por ello es peor.
#[must_use]
pub fn init(logs_dir: &Path) -> TelemetryGuard {
    let appender = tracing_appender::rolling::daily(logs_dir, "nb-sound.log");
    let (writer, guard) = tracing_appender::non_blocking(appender);

    let filter = EnvFilter::try_from_env("NB_SOUND_LOG").unwrap_or_else(|_| EnvFilter::new("info"));

    let file_layer = tracing_subscriber::fmt::layer()
        .with_writer(writer)
        .with_ansi(false)
        .with_target(true)
        .with_file(false)
        .with_line_number(false);

    let registry = tracing_subscriber::registry().with(filter).with(file_layer);

    #[cfg(debug_assertions)]
    let registry = registry.with(
        tracing_subscriber::fmt::layer()
            .with_writer(std::io::stdout.with_max_level(tracing::Level::DEBUG)),
    );

    // `try_init` y no `init`: un segundo arranque en el mismo proceso -el de una
    // prueba que comprueba qué ve la sesión siguiente- no puede tumbar el
    // runtime por un registro que ya está puesto. Sigue escribiendo el primero.
    let _ = registry.try_init();

    TelemetryGuard(guard)
}

/// Redacta una ruta del sistema de archivos para que pueda registrarse.
///
/// Devuelve únicamente la extensión y la longitud, que es lo que sirve para
/// diagnosticar, sin revelar el nombre del archivo, la estructura de carpetas ni
/// el nombre de usuario del sistema operativo.
///
/// ```
/// use nb_sound_lib::telemetry::redact_path;
///
/// let redacted = redact_path(std::path::Path::new("/home/ana/Música/Cold Shoulder.mp3"));
///
/// assert!(redacted.contains("mp3"));    // la extensión sirve para diagnosticar
/// assert!(!redacted.contains("ana"));   // el nombre de usuario, no
/// assert!(!redacted.contains("Shoulder"));
/// ```
#[must_use]
pub fn redact_path(path: &Path) -> String {
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("desconocida");
    let len = path.as_os_str().len();
    format!("<ruta ext={ext} len={len}>")
}

/// Redacta un texto libre que podría contener contenido del usuario.
///
/// Se usa cuando hay que registrar que *algo* tenía un valor sin registrar cuál:
/// títulos, artistas, consultas de búsqueda o letras.
#[must_use]
pub fn redact_text(text: &str) -> String {
    format!("<texto len={}>", text.chars().count())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Si esta prueba falla, los registros pueden estar filtrando la biblioteca
    /// del usuario y su nombre de cuenta del sistema operativo.
    #[test]
    fn la_redaccion_de_rutas_no_revela_nada_del_usuario() {
        let redacted = redact_path(Path::new("/home/ana/Música/Secreto.flac"));

        assert!(!redacted.contains("ana"));
        assert!(!redacted.contains("Secreto"));
        assert!(!redacted.contains("Música"));
        assert!(!redacted.contains('/'));
        assert!(
            redacted.contains("flac"),
            "la extensión sí es útil: {redacted}"
        );
    }

    #[test]
    fn la_redaccion_de_rutas_funciona_con_rutas_de_windows() {
        let redacted = redact_path(Path::new(r"C:\Users\Ana\Music\Adele.m4a"));

        assert!(!redacted.contains("Ana"));
        assert!(!redacted.contains("Adele"));
        assert!(redacted.contains("m4a"));
    }

    #[test]
    fn la_redaccion_de_rutas_sin_extension_no_entra_en_panico() {
        assert_eq!(
            redact_path(Path::new("/tmp/sin_extension")),
            "<ruta ext=desconocida len=18>"
        );
    }

    #[test]
    fn la_redaccion_de_texto_conserva_solo_la_longitud() {
        let redacted = redact_text("Canción de cuna");

        assert!(!redacted.contains("cuna"));
        assert_eq!(redacted, "<texto len=15>");
    }
}
