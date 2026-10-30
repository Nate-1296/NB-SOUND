//! El emparejamiento (F3.1.3): el token del QR, el código corto para teclearlo a
//! mano y el `device_token` que se queda el teléfono.
//!
//! Los dos primeros son de un solo uso y caducan a los 300 s, como en la V1
//! (`servidor_sync.py`). El `device_token` mide lo mismo que el de la V1
//! (`secrets.token_urlsafe(32)`, 43 caracteres): el teléfono lo guarda y el
//! servidor solo conserva su SHA-256.

use std::time::{Duration, Instant};

use serde::Serialize;
use sha2::{Digest, Sha256};
use tokio_rustls::rustls::crypto::ring::default_provider;
use ts_rs::TS;

use crate::error::{NsError, NsResult};

pub const TTL: Duration = Duration::from_secs(300);

/// Sin caracteres ambiguos (0/O, 1/I/L), como la V1: se lee en una pantalla y se
/// teclea en otra.
const ALFABETO_CODIGO: &[u8] = b"ABCDEFGHJKMNPQRSTUVWXYZ23456789";
const LARGO_CODIGO: usize = 8;

fn aleatorio(buf: &mut [u8]) -> NsResult<()> {
    default_provider()
        .secure_random
        .fill(buf)
        .map_err(|_| NsError::Internal)
}

/// Base64 para URL sin relleno, lo que da `secrets.token_urlsafe`.
fn base64_url(bytes: &[u8]) -> String {
    const A: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut s = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for trozo in bytes.chunks(3) {
        let n = trozo
            .iter()
            .enumerate()
            .fold(0u32, |n, (i, b)| n | u32::from(*b) << (16 - 8 * i));
        for i in 0..=trozo.len() {
            s.push(A[(n >> (18 - 6 * i) & 63) as usize] as char);
        }
    }
    s
}

/// 256 bits, como la V1.
pub fn generar_token() -> NsResult<String> {
    let mut buf = [0u8; 32];
    aleatorio(&mut buf)?;
    Ok(base64_url(&buf))
}

pub fn generar_codigo() -> NsResult<String> {
    let mut codigo = String::with_capacity(LARGO_CODIGO);
    // Se descartan los bytes que darían más peso a unas letras que a otras.
    let limite = 256 - 256 % ALFABETO_CODIGO.len();
    while codigo.len() < LARGO_CODIGO {
        let mut b = [0u8; 16];
        aleatorio(&mut b)?;
        for x in b.into_iter().filter(|x| usize::from(*x) < limite) {
            if codigo.len() < LARGO_CODIGO {
                codigo.push(ALFABETO_CODIGO[usize::from(x) % ALFABETO_CODIGO.len()] as char);
            }
        }
    }
    Ok(codigo)
}

/// El SHA-256 en hexadecimal: lo que se guarda del `device_token`.
pub fn huella_token(token: &str) -> String {
    Sha256::digest(token.as_bytes())
        .iter()
        .fold(String::with_capacity(64), |mut s, b| {
            use std::fmt::Write as _;
            let _ = write!(s, "{b:02x}");
            s
        })
}

/// Comparación que tarda lo mismo acierte o no, como `secrets.compare_digest`.
fn iguales(a: &[u8], b: &[u8]) -> bool {
    a.len() == b.len() && a.iter().zip(b).fold(0u8, |d, (x, y)| d | (x ^ y)) == 0
}

/// El token y el código vigentes.
#[derive(Debug, Default)]
pub struct Emparejamiento {
    vigente: Option<(String, String, Instant)>,
}

impl Emparejamiento {
    /// Emite un token y un código nuevos; los anteriores dejan de valer.
    ///
    /// # Errors
    ///
    /// [`NsError::Internal`] si el sistema no da aleatoriedad.
    pub fn regenerar(&mut self) -> NsResult<()> {
        self.vigente = Some((generar_token()?, generar_codigo()?, Instant::now() + TTL));
        Ok(())
    }

    pub fn olvidar(&mut self) {
        self.vigente = None;
    }

    /// El token y el código, si no han caducado.
    pub fn actual(&self) -> Option<(&str, &str, Duration)> {
        let (t, c, expira) = self.vigente.as_ref()?;
        let resta = expira.checked_duration_since(Instant::now())?;
        Some((t.as_str(), c.as_str(), resta))
    }

    /// El token del QR, o el código corto sin distinguir mayúsculas ni espacios.
    pub fn valida(&self, valor: &str) -> bool {
        let Some((token, codigo, _)) = self.actual() else {
            return false;
        };
        !valor.is_empty()
            && (iguales(valor.as_bytes(), token.as_bytes())
                || iguales(valor.trim().to_uppercase().as_bytes(), codigo.as_bytes()))
    }
}

/// Lo que va dentro del QR, con los campos y el orden de la V1 (`payload_qr`).
#[derive(Debug, Serialize)]
pub struct ContenidoQr<'a> {
    pub host: &'a str,
    pub puerto: u16,
    pub token: &'a str,
    pub version: u32,
    pub tls: bool,
    pub tls_fingerprint: &'a str,
    pub servicio: &'a str,
}

/// El QR para la interfaz: la matriz de módulos como un trazado SVG, que la
/// interfaz pinta con sus colores (los módulos oscuros son el trazado).
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct Qr {
    /// Módulos por lado, sin margen.
    pub lado: u32,
    pub trazado: String,
}

/// # Errors
///
/// [`NsError::Internal`] si el contenido no cabe en un QR.
pub fn qr(contenido: &[u8]) -> NsResult<Qr> {
    let codigo = qrcode::QrCode::with_error_correction_level(contenido, qrcode::EcLevel::M)
        .map_err(|_| NsError::Internal)?;
    let lado = codigo.width();
    let mut trazado = String::new();
    for (i, color) in codigo.to_colors().into_iter().enumerate() {
        if color == qrcode::Color::Dark {
            use std::fmt::Write as _;
            let _ = write!(trazado, "M{} {}h1v1h-1z", i % lado, i / lado);
        }
    }
    Ok(Qr {
        lado: lado as u32,
        trazado,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn el_device_token_mide_lo_mismo_que_el_de_la_v1() {
        let t = generar_token().unwrap();
        assert_eq!(t.len(), 43);
        assert!(t
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_'));
        assert_ne!(t, generar_token().unwrap());
    }

    #[test]
    fn base64_url_coincide_con_la_referencia() {
        assert_eq!(base64_url(b""), "");
        assert_eq!(base64_url(b"f"), "Zg");
        assert_eq!(base64_url(b"fo"), "Zm8");
        assert_eq!(base64_url(b"foo"), "Zm9v");
        assert_eq!(base64_url(&[0xfb, 0xff]), "-_8");
    }

    #[test]
    fn el_codigo_corto_no_tiene_caracteres_ambiguos() {
        for _ in 0..50 {
            let c = generar_codigo().unwrap();
            assert_eq!(c.len(), 8);
            assert!(c.bytes().all(|b| ALFABETO_CODIGO.contains(&b)), "{c}");
        }
    }

    #[test]
    fn el_token_y_el_codigo_valen_hasta_regenerarse() {
        let mut e = Emparejamiento::default();
        assert!(!e.valida(""));
        e.regenerar().unwrap();
        let (token, codigo, resta) = e
            .actual()
            .map(|(t, c, r)| (t.to_owned(), c.to_owned(), r))
            .unwrap();
        assert!(resta <= TTL);
        assert!(e.valida(&token));
        assert!(e.valida(&format!("  {}  ", codigo.to_lowercase())));
        assert!(!e.valida("otro"));
        e.regenerar().unwrap();
        assert!(!e.valida(&token), "un solo uso");
        e.olvidar();
        assert!(e.actual().is_none());
    }

    #[test]
    fn el_qr_dibuja_un_modulo_por_cuadrado_oscuro() {
        let q = qr(br#"{"host": "192.168.1.40"}"#).unwrap();
        assert!(q.lado >= 21);
        assert!(
            q.trazado.starts_with("M0 0h1v1h-1z"),
            "la esquina es un buscador"
        );
    }
}
