//! Directorio privado, socket Unix y comprobación de credenciales del peer.

use super::{HANDSHAKE_TIMEOUT, LocalError as ServiceError, new_session};
use std::{
    fs::{self, DirBuilder},
    os::unix::fs::{DirBuilderExt, FileTypeExt, MetadataExt, PermissionsExt},
    path::{Path, PathBuf},
};
use tokio::{
    net::{UnixListener, UnixStream},
    time::timeout,
};

pub const TRANSPORT_NAME: &str = "unix_socket";
pub type Stream = UnixStream;

pub struct Endpoint {
    listener: UnixListener,
    cleanup: Cleanup,
}

struct Cleanup {
    directory: PathBuf,
    socket: PathBuf,
}

impl Drop for Cleanup {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.socket);
        let _ = fs::remove_dir(&self.directory);
    }
}

impl Endpoint {
    pub fn bind() -> Result<Self, ServiceError> {
        for _ in 0..8 {
            match Self::bind_named(&new_session()?) {
                Err(ServiceError::HostIo(error))
                    if error.kind() == std::io::ErrorKind::AlreadyExists =>
                {
                    continue;
                }
                result => return result,
            }
        }
        Err(ServiceError::AccessDenied)
    }

    pub fn bind_named(session: &crate::capability::Epoch) -> Result<Self, ServiceError> {
        let socket = path_for(session)?;
        let directory = socket
            .parent()
            .ok_or(ServiceError::AccessDenied)?
            .to_owned();
        DirBuilder::new()
            .mode(0o700)
            .create(&directory)
            .map_err(ServiceError::HostIo)?;
        let cleanup = Cleanup { socket, directory };
        fs::set_permissions(&cleanup.directory, fs::Permissions::from_mode(0o700))
            .map_err(ServiceError::HostIo)?;
        let listener = UnixListener::bind(&cleanup.socket).map_err(ServiceError::HostIo)?;
        fs::set_permissions(&cleanup.socket, fs::Permissions::from_mode(0o600))
            .map_err(ServiceError::HostIo)?;
        validate_endpoint(&cleanup.socket)?;
        Ok(Self { listener, cleanup })
    }

    pub fn path(&self) -> &Path {
        &self.cleanup.socket
    }

    pub async fn accept(&self) -> Result<Stream, ServiceError> {
        self.listener
            .accept()
            .await
            .map(|(stream, _)| stream)
            .map_err(ServiceError::HostIo)
    }
}

pub fn validate_endpoint(path: &Path) -> Result<(), ServiceError> {
    let directory = path.parent().ok_or(ServiceError::AccessDenied)?;
    let parent = fs::symlink_metadata(directory).map_err(ServiceError::HostIo)?;
    let socket = fs::symlink_metadata(path).map_err(ServiceError::HostIo)?;
    let uid = rustix::process::geteuid().as_raw();
    if !parent.is_dir()
        || parent.uid() != uid
        || parent.mode() & 0o777 != 0o700
        || !socket.file_type().is_socket()
        || socket.uid() != uid
        || socket.mode() & 0o777 != 0o600
    {
        return Err(ServiceError::AccessDenied);
    }
    Ok(())
}

pub fn validate_peer(stream: &Stream) -> Result<(), ServiceError> {
    if stream.peer_cred().map_err(ServiceError::HostIo)?.uid()
        != rustix::process::geteuid().as_raw()
    {
        return Err(ServiceError::AccessDenied);
    }
    Ok(())
}

pub async fn connect_endpoint(path: &Path, expected_pid: u32) -> Result<Stream, ServiceError> {
    validate_endpoint(path)?;
    let stream = timeout(HANDSHAKE_TIMEOUT, UnixStream::connect(path))
        .await
        .map_err(|_| ServiceError::Timeout)?
        .map_err(ServiceError::HostIo)?;
    validate_peer(&stream)?;
    if stream
        .peer_cred()
        .map_err(ServiceError::HostIo)?
        .pid()
        .and_then(|pid| u32::try_from(pid).ok())
        != Some(expected_pid)
    {
        return Err(ServiceError::AccessDenied);
    }
    Ok(stream)
}

pub fn endpoint_is_closed(path: &Path) -> Result<bool, ServiceError> {
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(true),
        Err(error) => Err(ServiceError::HostIo(error)),
        Ok(_) => Ok(false),
    }
}

pub async fn finish_session(_stream: &mut Stream) {}

pub fn path_for(session: &crate::capability::Epoch) -> Result<PathBuf, ServiceError> {
    let base = Path::new("/tmp")
        .canonicalize()
        .map_err(ServiceError::HostIo)?;
    Ok(base
        .join(format!("nb-{}", String::from(session.clone())))
        .join("ipc.sock"))
}
