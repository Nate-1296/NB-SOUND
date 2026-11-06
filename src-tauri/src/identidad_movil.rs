//! Identidad TLS del servidor móvil (ADR-005).
//!
//! NB Sound Mobile fija la huella SHA-256 del certificado la primera vez que se
//! empareja (TOFU). Si la huella cambia, el teléfono deja de confiar y hay que
//! volver a emparejarlo. Por eso NB Sound **no genera** un certificado nuevo cuando
//! hay uno: copia el certificado y la clave tal cual (F1.2.3).

use std::path::{Path, PathBuf};

use sha2::{Digest, Sha256};

use crate::error::{NsError, NsResult};

/// Los nombres, que NB Sound conserva.
pub const CERTIFICADO: &str = "sync_cert.pem";
pub const CLAVE: &str = "sync_key.pem";

/// Base64 estándar, sin dependencias: lo usan el PEM del certificado y las firmas
/// de las actualizaciones.
pub(crate) fn base64(texto: &str) -> Option<Vec<u8>> {
    let valor = |c: u8| -> Option<u32> {
        Some(match c {
            b'A'..=b'Z' => c - b'A',
            b'a'..=b'z' => c - b'a' + 26,
            b'0'..=b'9' => c - b'0' + 52,
            b'+' => 62,
            b'/' => 63,
            _ => return None,
        } as u32)
    };
    let mut salida = Vec::with_capacity(texto.len() * 3 / 4);
    let (mut acumulado, mut bits) = (0u32, 0u32);
    for c in texto.bytes().filter(|c| !c.is_ascii_whitespace()) {
        if c == b'=' {
            break;
        }
        acumulado = (acumulado << 6) | valor(c)?;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            salida.push((acumulado >> bits) as u8);
            acumulado &= (1 << bits) - 1;
        }
    }
    Some(salida)
}

/// La huella que fija el móvil: SHA-256 del certificado en DER, en hexadecimal
/// minúsculo y sin separadores.
pub fn huella_sha256(pem: &str) -> Option<String> {
    let inicio = pem.find("-----BEGIN CERTIFICATE-----")? + "-----BEGIN CERTIFICATE-----".len();
    let fin = pem[inicio..].find("-----END CERTIFICATE-----")? + inicio;
    let der = base64(&pem[inicio..fin]).filter(|d| !d.is_empty())?;
    Some(
        Sha256::digest(&der)
            .iter()
            .fold(String::with_capacity(64), |mut s, b| {
                use std::fmt::Write as _;
                let _ = write!(s, "{b:02x}");
                s
            }),
    )
}

/// Escribe una clave privada: se crea ya con `0600` y se renombra al terminar,
/// así que nunca hay una a medias ni legible por otros.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede escribir.
pub fn escribir_privado(destino: &Path, contenido: &[u8]) -> NsResult<()> {
    let temporal: PathBuf = destino.with_extension("pem.parcial");
    let mut opciones = std::fs::OpenOptions::new();
    opciones.write(true).create(true).truncate(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        opciones.mode(0o600);
    }
    let escrito = opciones.open(&temporal).and_then(|mut f| {
        use std::io::Write;
        f.write_all(contenido)?;
        f.sync_all()
    });
    let colocado = escrito.and_then(|()| std::fs::rename(&temporal, destino));
    colocado.map_err(|error| {
        let _ = std::fs::remove_file(&temporal);
        tracing::error!(error = %error, "no se pudo escribir la clave del servidor móvil");
        NsError::StorageFailure
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Generado con `openssl req -x509 -newkey ec`; la huella es la que da
    /// `openssl x509 -outform DER | sha256sum`, que es la que fija el móvil.
    const PEM: &str = "-----BEGIN CERTIFICATE-----
MIIBdjCCAR2gAwIBAgIUZPZsZ9VsrYuKotahhnllZVXw8TkwCgYIKoZIzj0EAwIw
ETEPMA0GA1UEAwwGcHJ1ZWJhMB4XDTI2MTAzMDA2MzE1OFoXDTI2MTAzMTA2MzE1
OFowETEPMA0GA1UEAwwGcHJ1ZWJhMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE
LAKVsFdtak2wRhnmpITrbhX6/y4NVMwbYJN0QmYvK+6jw9u1sd7XPMl1Wb6aFgF8
4LHYN0CgUIDgyaFWbQL836NTMFEwHQYDVR0OBBYEFJCJGotQuO+WyeysG5veiE00
rGYYMB8GA1UdIwQYMBaAFJCJGotQuO+WyeysG5veiE00rGYYMA8GA1UdEwEB/wQF
MAMBAf8wCgYIKoZIzj0EAwIDRwAwRAIgcvZ/HOfHYaVKFYH+kEdED+cO2U9Z09Xe
G+s3P5dBDiwCIAkDwvxlEaIYjVbclt9bmP/P/ZHo785YxIN91JGJYuz1
-----END CERTIFICATE-----
";
    const HUELLA: &str = "80d352cdef15e453af7343f4c58f8b4c384f349d94396c5c50f34bb53ae948b1";

    fn temporal(nombre: &str) -> PathBuf {
        let dir =
            std::env::temp_dir().join(format!("ns-identidad-{nombre}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn la_huella_es_la_misma_que_calcula_openssl() {
        assert_eq!(huella_sha256(PEM).as_deref(), Some(HUELLA));
        assert_eq!(huella_sha256("no es un certificado"), None);
    }

    #[test]
    fn la_clave_privada_se_escribe_sin_que_otros_la_lean() {
        let dir = temporal("privada");
        let clave = dir.join(CLAVE);
        escribir_privado(&clave, b"clave privada").unwrap();
        assert_eq!(std::fs::read_to_string(&clave).unwrap(), "clave privada");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let modo = std::fs::metadata(&clave).unwrap().permissions().mode();
            assert_eq!(modo & 0o077, 0, "la clave no la lee nadie más");
        }
        let _ = std::fs::remove_dir_all(dir);
    }
}
