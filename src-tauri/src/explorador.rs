//! "Mostrar en la carpeta": abre el gestor de archivos del sistema con el archivo
//! señalado (`DecisionPanel.qml`).
//!
//! En Linux se pide por D-Bus a `org.freedesktop.FileManager1`, que Dolphin,
//! Nautilus, Nemo y Thunar implementan y que deja el archivo seleccionado; si no
//! responde nadie, se abre la carpeta con `xdg-open`. Se descartó `xdg-open`
//! sobre el archivo: abriría la canción en otro reproductor, no la carpeta.

use std::fmt::Write as _;
use std::path::Path;

/// La URI `file://` de una ruta absoluta, con todo lo que no es seguro escapado.
///
/// La coma también se escapa aunque RFC 3986 la admita: `dbus-send` separa con
/// ella los elementos de un `array:string`, y un álbum con coma en el nombre se
/// partiría en dos rutas que no existen.
pub fn uri_de_archivo(ruta: &Path) -> String {
    let texto = ruta.to_string_lossy();
    let mut uri = String::with_capacity(texto.len() + 8);
    uri.push_str("file://");
    for b in texto.bytes() {
        let seguro = b.is_ascii_alphanumeric() || matches!(b, b'/' | b'-' | b'_' | b'.' | b'~');
        if seguro {
            uri.push(char::from(b));
        } else {
            let _ = write!(uri, "%{b:02X}");
        }
    }
    uri
}

/// Señala el archivo en el gestor de archivos. No espera a que el gestor se
/// abra: si no hay ninguno, no hay nada más que hacer.
pub fn mostrar(archivo: &Path) {
    #[cfg(target_os = "windows")]
    {
        // `explorer` quiere `/select,` y la ruta en el mismo argumento.
        let mut arg = std::ffi::OsString::from("/select,");
        arg.push(archivo);
        let _ = std::process::Command::new("explorer").arg(arg).spawn();
    }
    #[cfg(target_os = "macos")]
    {
        let _ = std::process::Command::new("open")
            .arg("-R")
            .arg(archivo)
            .spawn();
    }
    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    {
        let pedido = std::process::Command::new("dbus-send")
            .args([
                "--session",
                "--print-reply",
                "--dest=org.freedesktop.FileManager1",
                "--type=method_call",
                "/org/freedesktop/FileManager1",
                "org.freedesktop.FileManager1.ShowItems",
            ])
            .arg(format!("array:string:{}", uri_de_archivo(archivo)))
            .arg("string:")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();
        if !matches!(pedido, Ok(s) if s.success()) {
            if let Some(carpeta) = archivo.parent() {
                let _ = std::process::Command::new("xdg-open").arg(carpeta).spawn();
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn la_uri_escapa_espacios_tildes_y_comas() {
        assert_eq!(
            uri_de_archivo(Path::new("/música/Maná, en vivo/01 Rayando el sol.mp3")),
            "file:///m%C3%BAsica/Man%C3%A1%2C%20en%20vivo/01%20Rayando%20el%20sol.mp3"
        );
    }

    #[test]
    fn la_uri_deja_intacto_lo_seguro() {
        assert_eq!(
            uri_de_archivo(Path::new("/a/b-c_d.e~f")),
            "file:///a/b-c_d.e~f"
        );
    }
}
