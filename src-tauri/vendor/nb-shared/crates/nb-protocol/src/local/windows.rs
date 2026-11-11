//! Named pipes locales con DACL explícita. Todas las llamadas FFI están en dependencias.

use super::{HANDSHAKE_TIMEOUT, LocalError as ServiceError, WRITE_TIMEOUT, new_session};
use interprocess::os::windows::{
    named_pipe::{
        PipeListenerOptions, pipe_mode,
        tokio::{PipeListener, PipeStream},
    },
    security_descriptor::SecurityDescriptor,
};
use std::{
    fs::OpenOptions,
    io,
    num::NonZeroU8,
    os::windows::{fs::OpenOptionsExt, io::OwnedHandle},
    path::{Path, PathBuf},
    pin::Pin,
    task::{Context, Poll},
    time::Duration,
};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWrite, ReadBuf},
    time::{sleep, timeout},
};
use widestring::U16CString;
use windows_sys::Win32::{
    Foundation::{ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND, ERROR_PIPE_BUSY},
    Security::TOKEN_QUERY,
    Storage::FileSystem::{
        FILE_FLAG_OVERLAPPED, FILE_SHARE_READ, FILE_SHARE_WRITE, SECURITY_IDENTIFICATION,
        SECURITY_SQOS_PRESENT,
    },
};
use windows_token::Token;

pub const TRANSPORT_NAME: &str = "named_pipe";
const PREFIX: &str = r"\\.\pipe\nb-";
type RawStream = PipeStream<pipe_mode::Bytes, pipe_mode::Bytes>;

pub struct Stream(RawStream);

impl Drop for Stream {
    fn drop(&mut self) {
        // No iniciar flush diferido no cancelable al cerrar una conexión no cooperativa.
        self.0.assume_flushed();
    }
}

impl AsyncRead for Stream {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        Pin::new(&mut self.get_mut().0).poll_read(cx, buf)
    }
}

impl AsyncWrite for Stream {
    fn poll_write(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        bytes: &[u8],
    ) -> Poll<io::Result<usize>> {
        Pin::new(&mut self.get_mut().0).poll_write(cx, bytes)
    }
    fn poll_flush(self: Pin<&mut Self>, _cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Poll::Ready(Ok(()))
    }
    fn poll_shutdown(self: Pin<&mut Self>, _cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Poll::Ready(Ok(()))
    }
}

pub struct Endpoint {
    listener: PipeListener<pipe_mode::Bytes, pipe_mode::Bytes>,
    path: PathBuf,
}

fn user_sid(pid: u32) -> Result<String, ServiceError> {
    Token::open_process(pid, TOKEN_QUERY)
        .and_then(|token| token.user_sid())
        .map(|sid| sid.to_display_string())
        .map_err(|_| ServiceError::AccessDenied)
}

fn current_sid() -> Result<String, ServiceError> {
    Token::open_current_process_with_access(TOKEN_QUERY)
        .and_then(|token| token.user_sid())
        .map(|sid| sid.to_display_string())
        .map_err(|_| ServiceError::AccessDenied)
}

fn descriptor(sid: &str) -> Result<SecurityDescriptor, ServiceError> {
    let sddl = U16CString::from_str(format!("O:{sid}D:P(A;;GA;;;{sid})"))
        .map_err(|_| ServiceError::AccessDenied)?;
    SecurityDescriptor::deserialize(&sddl).map_err(ServiceError::HostIo)
}

impl Endpoint {
    pub fn bind() -> Result<Self, ServiceError> {
        Self::bind_named(&new_session()?)
    }
    pub fn bind_named(session: &crate::capability::Epoch) -> Result<Self, ServiceError> {
        let sid = current_sid()?;
        let path = path_for(session)?;
        let listener = PipeListenerOptions::new()
            .path(path.as_path())
            .accept_remote(false)
            .inheritable(false)
            .instance_limit(NonZeroU8::new((super::MAX_SESSIONS + 1) as u8))
            .security_descriptor(Some(descriptor(&sid)?))
            .create_tokio_duplex::<pipe_mode::Bytes>()
            .map_err(ServiceError::HostIo)?;
        Ok(Self { listener, path })
    }
    pub fn path(&self) -> &Path {
        &self.path
    }
    pub async fn accept(&self) -> Result<Stream, ServiceError> {
        self.listener
            .accept()
            .await
            .map(Stream)
            .map_err(ServiceError::HostIo)
    }
}

pub fn validate_endpoint(path: &Path) -> Result<(), ServiceError> {
    let text = path.to_str().ok_or(ServiceError::AccessDenied)?;
    let suffix = text
        .strip_prefix(PREFIX)
        .ok_or(ServiceError::AccessDenied)?;
    if suffix.len() != 32
        || !suffix
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err(ServiceError::AccessDenied);
    }
    Ok(())
}

fn open(path: &Path) -> io::Result<std::fs::File> {
    OpenOptions::new()
        .read(true)
        .write(true)
        .share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE)
        .custom_flags(FILE_FLAG_OVERLAPPED | SECURITY_IDENTIFICATION | SECURITY_SQOS_PRESENT)
        .open(path)
}

pub async fn connect_endpoint(path: &Path, expected_pid: u32) -> Result<Stream, ServiceError> {
    validate_endpoint(path)?;
    let handle = timeout(HANDSHAKE_TIMEOUT, async {
        loop {
            match open(path) {
                Ok(file) => return Ok(OwnedHandle::from(file)),
                Err(error) if error.raw_os_error() == Some(ERROR_PIPE_BUSY as i32) => {
                    sleep(Duration::from_millis(10)).await
                }
                Err(error) => return Err(ServiceError::HostIo(error)),
            }
        }
    })
    .await
    .map_err(|_| ServiceError::Timeout)??;
    let stream = Stream(RawStream::try_from(handle).map_err(|_| ServiceError::AccessDenied)?);
    let server_pid = stream.0.server_process_id().map_err(ServiceError::HostIo)?;
    if server_pid != expected_pid || user_sid(server_pid)? != current_sid()? {
        return Err(ServiceError::AccessDenied);
    }
    Ok(stream)
}

pub fn validate_peer(stream: &Stream) -> Result<(), ServiceError> {
    let pid = stream.0.client_process_id().map_err(ServiceError::HostIo)?;
    if user_sid(pid)? != current_sid()? {
        return Err(ServiceError::AccessDenied);
    }
    Ok(())
}

pub fn endpoint_is_closed(path: &Path) -> Result<bool, ServiceError> {
    validate_endpoint(path)?;
    match open(path) {
        Err(error)
            if [
                Some(ERROR_FILE_NOT_FOUND as i32),
                Some(ERROR_PATH_NOT_FOUND as i32),
            ]
            .contains(&error.raw_os_error()) =>
        {
            Ok(true)
        }
        Err(error) if error.raw_os_error() == Some(ERROR_PIPE_BUSY as i32) => Ok(false),
        Err(error) => Err(ServiceError::HostIo(error)),
        Ok(_) => Ok(false),
    }
}

pub async fn finish_session(stream: &mut Stream) {
    let _ = timeout(WRITE_TIMEOUT, stream.read(&mut [0_u8; 1])).await;
}

pub fn path_for(session: &crate::capability::Epoch) -> Result<PathBuf, ServiceError> {
    Ok(PathBuf::from(format!(
        "{PREFIX}{}",
        String::from(session.clone())
    )))
}

#[cfg(test)]
mod tests {
    use super::*;
    use interprocess::os::windows::security_descriptor::AsSecurityDescriptorExt;
    use windows_sys::Win32::Security::{DACL_SECURITY_INFORMATION, OWNER_SECURITY_INFORMATION};

    #[test]
    fn el_descriptor_es_protegido_y_solo_concede_acceso_al_sid_del_usuario() {
        let sid = current_sid().unwrap();
        let sd = descriptor(&sid).unwrap();
        let text = sd
            .serialize(
                DACL_SECURITY_INFORMATION | OWNER_SECURITY_INFORMATION,
                |s| s.to_string_lossy(),
            )
            .unwrap();
        assert!(text.contains(&format!("O:{sid}")));
        assert!(text.contains(&format!("D:P(A;;GA;;;{sid})")));
        assert!(!text.contains(";;;WD"));
        assert!(!text.contains(";;;AU"));
    }

    #[test]
    fn se_rechazan_rutas_remotas_y_nombres_fuera_del_espacio_del_host() {
        for path in [
            r"\\remote\pipe\nb-00000000000000000000000000000000",
            r"\\.\pipe\otra-app",
            r"C:\pipe",
            r"\\.\pipe\nb-..suffix",
        ] {
            assert!(validate_endpoint(Path::new(path)).is_err());
        }
        validate_endpoint(Path::new(&format!("{PREFIX}{}", "0".repeat(32)))).unwrap();
    }

    #[tokio::test]
    async fn un_peer_que_no_lee_no_impone_flush_bloqueante_al_cerrar() {
        timeout(Duration::from_secs(10), async {
            let endpoint = Endpoint::bind().unwrap();
            let (server, client) = tokio::join!(
                endpoint.accept(),
                connect_endpoint(endpoint.path(), std::process::id())
            );
            let mut server = server.unwrap();
            let client = client.unwrap();
            tokio::io::AsyncWriteExt::write_all(&mut server, b"final")
                .await
                .unwrap();
            finish_session(&mut server).await;
            drop(server);
            drop(client);
        })
        .await
        .unwrap();
    }
}
