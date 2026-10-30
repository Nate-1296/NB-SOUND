//! TLS del servidor móvil (F3.1.1): la identidad y el oyente.
//!
//! El teléfono fija la huella del certificado la primera vez (TOFU) y la exige en
//! cada conexión. Por eso la identidad nunca se regenera si existe: la que copió el
//! importador de la V1 se usa tal cual, y la que crea una instalación nueva se
//! guarda para siempre, con una validez que no va a vencer.

use std::net::SocketAddr;
use std::path::Path;
use std::sync::Arc;
use std::time::Duration;

use tokio::net::{TcpListener, TcpStream};
use tokio::sync::mpsc;
use tokio_rustls::rustls::crypto::ring::default_provider;
use tokio_rustls::rustls::pki_types::pem::PemObject;
use tokio_rustls::rustls::pki_types::{CertificateDer, PrivateKeyDer};
use tokio_rustls::rustls::ServerConfig;
use tokio_rustls::server::TlsStream;
use tokio_rustls::TlsAcceptor;

use crate::error::{NsError, NsResult};
use crate::identidad_movil::{self, CERTIFICADO, CLAVE};

/// Un cliente que abre la conexión y no termina el saludo no puede retener el
/// hilo que acepta a los demás.
const PLAZO_SALUDO: Duration = Duration::from_secs(10);

/// Crea una identidad nueva en `dir`. ECDSA P-256, como la de la V1.
fn crear(dir: &Path) -> NsResult<()> {
    let mut params = rcgen::CertificateParams::new(vec!["nbsound.local".to_owned()])
        .map_err(|_| NsError::Internal)?;
    params
        .distinguished_name
        .push(rcgen::DnType::CommonName, "NB Sound");
    params.not_before = rcgen::date_time_ymd(2026, 1, 1);
    // El teléfono valida la huella, no la fecha; pero un certificado vencido
    // obligaría a regenerarlo, y eso sí rompería los emparejamientos.
    params.not_after = rcgen::date_time_ymd(2125, 1, 1);
    let clave = rcgen::KeyPair::generate().map_err(|_| NsError::Internal)?;
    let cert = params.self_signed(&clave).map_err(|_| NsError::Internal)?;
    std::fs::create_dir_all(dir).map_err(|_| NsError::StorageFailure)?;
    identidad_movil::escribir_privado(&dir.join(CLAVE), clave.serialize_pem().as_bytes())?;
    std::fs::write(dir.join(CERTIFICADO), cert.pem()).map_err(|_| NsError::StorageFailure)?;
    tracing::info!("identidad nueva del servidor móvil");
    Ok(())
}

/// La configuración TLS y la huella que se pone en el QR. Crea la identidad si no
/// la hay.
///
/// # Errors
///
/// - [`NsError::StorageFailure`] si no se puede leer o crear.
/// - [`NsError::IntegrityMismatch`] si el certificado o la clave no son válidos.
pub fn cargar(dir: &Path) -> NsResult<(Arc<ServerConfig>, String)> {
    let (cert, clave) = (dir.join(CERTIFICADO), dir.join(CLAVE));
    if !(cert.is_file() && clave.is_file()) {
        crear(dir)?;
    }
    let pem = std::fs::read(&cert).map_err(|_| NsError::StorageFailure)?;
    let huella = identidad_movil::huella_sha256(&String::from_utf8_lossy(&pem))
        .ok_or(NsError::IntegrityMismatch)?;
    let certs = CertificateDer::pem_slice_iter(&pem)
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| NsError::IntegrityMismatch)?;
    let clave = PrivateKeyDer::from_pem_file(&clave).map_err(|_| NsError::IntegrityMismatch)?;
    let mut config = ServerConfig::builder_with_provider(Arc::new(default_provider()))
        .with_safe_default_protocol_versions()
        .map_err(|_| NsError::Internal)?
        .with_no_client_auth()
        .with_single_cert(certs, clave)
        .map_err(|_| NsError::IntegrityMismatch)?;
    config.alpn_protocols = vec![b"http/1.1".to_vec()];
    Ok((Arc::new(config), huella))
}

/// Acepta conexiones y hace el saludo TLS de cada una en su propia tarea, para que
/// un cliente lento no detenga a los demás; axum recibe solo las que terminaron.
pub struct OyenteTls {
    listas: mpsc::Receiver<(TlsStream<TcpStream>, SocketAddr)>,
    direccion: SocketAddr,
}

impl OyenteTls {
    pub fn nuevo(tcp: TcpListener, config: Arc<ServerConfig>) -> std::io::Result<Self> {
        let direccion = tcp.local_addr()?;
        let (tx, listas) = mpsc::channel(64);
        let aceptor = TlsAcceptor::from(config);
        tokio::spawn(async move {
            loop {
                let (socket, origen) = match tcp.accept().await {
                    Ok(c) => c,
                    Err(_) => {
                        // Sin descriptores libres, por ejemplo: se espera y se sigue.
                        tokio::time::sleep(Duration::from_millis(100)).await;
                        continue;
                    }
                };
                let (aceptor, enviar) = (aceptor.clone(), tx.clone());
                tokio::spawn(async move {
                    if let Ok(Ok(tls)) =
                        tokio::time::timeout(PLAZO_SALUDO, aceptor.accept(socket)).await
                    {
                        let _ = enviar.send((tls, origen)).await;
                    }
                });
                if tx.is_closed() {
                    return;
                }
            }
        });
        Ok(Self { listas, direccion })
    }
}

impl axum::serve::Listener for OyenteTls {
    type Io = TlsStream<TcpStream>;
    type Addr = SocketAddr;

    async fn accept(&mut self) -> (Self::Io, Self::Addr) {
        match self.listas.recv().await {
            Some(c) => c,
            // El aceptador terminó: no habrá más conexiones.
            None => std::future::pending().await,
        }
    }

    fn local_addr(&self) -> std::io::Result<Self::Addr> {
        Ok(self.direccion)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn la_identidad_creada_no_cambia_entre_arranques() {
        let dir = std::env::temp_dir().join(format!("ns-tls-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let (_, a) = cargar(&dir).unwrap();
        let (_, b) = cargar(&dir).unwrap();
        assert_eq!(a, b);
        assert_eq!(a.len(), 64);
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let modo = std::fs::metadata(dir.join(CLAVE))
                .unwrap()
                .permissions()
                .mode();
            assert_eq!(modo & 0o777, 0o600, "la clave no la lee nadie más");
        }
    }
}
