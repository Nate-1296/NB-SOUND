//! Identidad TLS del servidor móvil (ADR-005).
//!
//! NB Sound Mobile fija la huella SHA-256 del certificado la primera vez que se
//! empareja (TOFU). Si la huella cambia, el teléfono deja de confiar y hay que
//! volver a emparejarlo. Por eso la V2 **no genera** un certificado nuevo cuando
//! hay uno de la V1: copia el certificado y la clave tal cual (F1.2.3).

use std::path::{Path, PathBuf};

use sha2::{Digest, Sha256};

use crate::error::{NsError, NsResult};

/// Los nombres de la V1 (`legado/infra/tls_local.py`), que la V2 conserva.
pub const CERTIFICADO: &str = "sync_cert.pem";
pub const CLAVE: &str = "sync_key.pem";

fn base64(texto: &str) -> Option<Vec<u8>> {
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
/// minúsculo y sin separadores, como la calculaba la V1.
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

/// Copia la identidad de la V1 a `destino` y devuelve su huella, calculada sobre
/// la copia. `None` si la V1 no tenía identidad, y entonces la V2 creará la suya
/// al encender el servidor (Fase 3). Si ya hay una en `destino`, no se toca:
/// sustituirla rompería los teléfonos emparejados con la V2.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede copiar o si el certificado de la
/// V1 no es un PEM legible.
pub fn copiar_de_la_v1(origen: &Path, destino: &Path) -> NsResult<Option<String>> {
    let (cert_v1, clave_v1) = (origen.join(CERTIFICADO), origen.join(CLAVE));
    if !(cert_v1.is_file() && clave_v1.is_file()) {
        return Ok(None);
    }
    let (cert, clave) = (destino.join(CERTIFICADO), destino.join(CLAVE));
    if !(cert.is_file() && clave.is_file()) {
        std::fs::create_dir_all(destino).map_err(|_| NsError::StorageFailure)?;
        copiar_privado(&clave_v1, &clave)?;
        std::fs::copy(&cert_v1, &cert).map_err(|error| {
            tracing::error!(error = %error, "no se pudo copiar el certificado del servidor móvil");
            NsError::StorageFailure
        })?;
    }
    let pem = std::fs::read_to_string(&cert).map_err(|_| NsError::StorageFailure)?;
    huella_sha256(&pem).map(Some).ok_or_else(|| {
        tracing::error!("el certificado del servidor móvil no es un PEM legible");
        NsError::StorageFailure
    })
}

/// Copia la clave privada sin que exista en ningún momento con permisos de
/// lectura para otros: se crea ya con `0600` y se renombra al terminar.
fn copiar_privado(origen: &Path, destino: &Path) -> NsResult<()> {
    let contenido = std::fs::read(origen).map_err(|_| NsError::StorageFailure)?;
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
        f.write_all(&contenido)?;
        f.sync_all()
    });
    let colocado = escrito.and_then(|()| std::fs::rename(&temporal, destino));
    colocado.map_err(|error| {
        let _ = std::fs::remove_file(&temporal);
        tracing::error!(error = %error, "no se pudo copiar la clave del servidor móvil");
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
    fn copiar_la_identidad_conserva_la_huella_y_protege_la_clave() {
        let dir = temporal("copia");
        let (v1, v2) = (dir.join("v1"), dir.join("v2"));
        std::fs::create_dir_all(&v1).unwrap();
        std::fs::write(v1.join(CERTIFICADO), PEM).unwrap();
        std::fs::write(v1.join(CLAVE), "clave privada").unwrap();
        assert_eq!(copiar_de_la_v1(&v1, &v2).unwrap().as_deref(), Some(HUELLA));
        assert_eq!(
            std::fs::read_to_string(v2.join(CLAVE)).unwrap(),
            "clave privada"
        );
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let modo = std::fs::metadata(v2.join(CLAVE))
                .unwrap()
                .permissions()
                .mode();
            assert_eq!(modo & 0o077, 0, "la clave no la lee nadie más");
        }
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn una_identidad_que_ya_tiene_la_v2_no_se_sustituye() {
        let dir = temporal("existente");
        let (v1, v2) = (dir.join("v1"), dir.join("v2"));
        std::fs::create_dir_all(&v1).unwrap();
        std::fs::create_dir_all(&v2).unwrap();
        std::fs::write(
            v1.join(CERTIFICADO),
            "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----",
        )
        .unwrap();
        std::fs::write(v1.join(CLAVE), "otra").unwrap();
        std::fs::write(v2.join(CERTIFICADO), PEM).unwrap();
        std::fs::write(v2.join(CLAVE), "la de la V2").unwrap();
        assert_eq!(copiar_de_la_v1(&v1, &v2).unwrap().as_deref(), Some(HUELLA));
        assert_eq!(
            std::fs::read_to_string(v2.join(CLAVE)).unwrap(),
            "la de la V2"
        );
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn sin_identidad_en_la_v1_no_se_copia_nada() {
        let dir = temporal("sin");
        assert_eq!(copiar_de_la_v1(&dir.join("v1"), &dir.join("v2")), Ok(None));
        let _ = std::fs::remove_dir_all(dir);
    }
}
