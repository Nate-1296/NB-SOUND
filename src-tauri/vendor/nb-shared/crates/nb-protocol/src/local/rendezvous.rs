//! Anuncio operativo e instancia única por aplicación/perfil en Linux.
//! Descubrir no autoriza; el consumidor todavía comprueba ejecutable, PID y desafío.
use crate::capability::{Epoch, Identifier, ResourceKey};
use rustix::fs::{Mode, OFlags};
use serde::{Deserialize, Serialize};
use std::{
    fs::{DirBuilder, File},
    io::{Read, Write},
    num::NonZeroU32,
    os::unix::fs::{DirBuilderExt, MetadataExt},
    path::{Path, PathBuf},
};

const LIMIT: usize = 4096;
#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("RENDEZVOUS_UNSAFE")]
    Unsafe,
    #[error("RENDEZVOUS_STORAGE_FAILED")]
    Storage,
    #[error("RENDEZVOUS_BUSY")]
    Busy,
    #[error("RENDEZVOUS_INVALID")]
    Invalid,
}
type Result<T> = std::result::Result<T, Error>;

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Advertisement {
    version: u16,
    pid: NonZeroU32,
    invitation: Epoch,
    resource: ResourceKey,
}
impl Advertisement {
    pub fn new(invitation: Epoch, resource: ResourceKey) -> Self {
        Self {
            version: 1,
            pid: NonZeroU32::new(std::process::id()).expect("PID del SO no nulo"),
            invitation,
            resource,
        }
    }
    pub fn pid(&self) -> u32 {
        self.pid.get()
    }
    pub fn invitation(&self) -> &Epoch {
        &self.invitation
    }
    pub fn resource(&self) -> &ResourceKey {
        &self.resource
    }
}

fn validate(file: &File, directory: bool) -> Result<()> {
    let info = file.metadata().map_err(|_| Error::Storage)?;
    if info.uid() != rustix::process::geteuid().as_raw()
        || (directory && (!info.is_dir() || info.mode() & 0o7777 != 0o700))
        || (!directory && (!info.is_file() || info.mode() & 0o7777 != 0o600 || info.nlink() != 1))
    {
        return Err(Error::Unsafe);
    }
    Ok(())
}
fn root() -> Result<PathBuf> {
    if let Some(base) = std::env::var_os("XDG_RUNTIME_DIR") {
        let base = PathBuf::from(base);
        if !base.is_absolute() {
            return Err(Error::Unsafe);
        }
        let directory = File::from(
            rustix::fs::open(
                &base,
                OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )
            .map_err(|_| Error::Unsafe)?,
        );
        validate(&directory, true)?;
        return Ok(base.join("nb-local"));
    }
    Ok(Path::new("/tmp")
        .canonicalize()
        .map_err(|_| Error::Storage)?
        .join(format!("nb-local-{}", rustix::process::geteuid().as_raw())))
}
struct Directory(File);
impl Directory {
    fn root(create: bool) -> Result<Option<Self>> {
        let path = root()?;
        if create {
            match DirBuilder::new().mode(0o700).create(&path) {
                Ok(()) => {}
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(_) => return Err(Error::Storage),
            }
        }
        match rustix::fs::open(
            path,
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        ) {
            Ok(fd) => {
                let file = File::from(fd);
                validate(&file, true)?;
                Ok(Some(Self(file)))
            }
            Err(rustix::io::Errno::NOENT) if !create => Ok(None),
            Err(_) => Err(Error::Unsafe),
        }
    }
    fn child(&self, name: &str, create: bool) -> Result<Option<Self>> {
        if create {
            match rustix::fs::mkdirat(&self.0, name, Mode::RWXU) {
                Ok(()) | Err(rustix::io::Errno::EXIST) => {}
                Err(_) => return Err(Error::Storage),
            }
        }
        match rustix::fs::openat(
            &self.0,
            name,
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        ) {
            Ok(fd) => {
                let file = File::from(fd);
                validate(&file, true)?;
                Ok(Some(Self(file)))
            }
            Err(rustix::io::Errno::NOENT) if !create => Ok(None),
            Err(_) => Err(Error::Unsafe),
        }
    }
    fn open_file(&self, name: &str, create: bool, exclusive: bool) -> Result<Option<File>> {
        let mut flags = OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::CLOEXEC;
        flags |= if create {
            OFlags::RDWR | OFlags::CREATE
        } else {
            OFlags::RDONLY
        };
        if exclusive {
            flags |= OFlags::EXCL;
        }
        match rustix::fs::openat(&self.0, name, flags, Mode::RUSR | Mode::WUSR) {
            Ok(fd) => {
                let file = File::from(fd);
                validate(&file, false)?;
                Ok(Some(file))
            }
            Err(rustix::io::Errno::NOENT) if !create => Ok(None),
            Err(_) => Err(Error::Unsafe),
        }
    }
    fn remove(&self, name: &str) -> Result<()> {
        match rustix::fs::unlinkat(&self.0, name, rustix::fs::AtFlags::empty()) {
            Ok(()) | Err(rustix::io::Errno::NOENT) => Ok(()),
            Err(_) => Err(Error::Storage),
        }
    }
}
fn namespace(app: &Identifier, profile: &Identifier, create: bool) -> Result<Option<Directory>> {
    let Some(root) = Directory::root(create)? else {
        return Ok(None);
    };
    let Some(app) = root.child(&format!("app-{}", String::from(app.clone())), create)? else {
        return Ok(None);
    };
    app.child(
        &format!("profile-{}", String::from(profile.clone())),
        create,
    )
}

/// Bloqueo de inode persistente: nunca se elimina para sustituir una instancia.
pub struct Claim {
    directory: Directory,
    app: Identifier,
    _lock: File,
    published: bool,
}
pub fn claim(app: &Identifier, profile: &Identifier) -> Result<Claim> {
    let directory = namespace(app, profile, true)?.ok_or(Error::Storage)?;
    let lock = directory
        .open_file("instance.lock", true, false)?
        .ok_or(Error::Storage)?;
    lock.try_lock().map_err(|error| match error {
        std::fs::TryLockError::WouldBlock => Error::Busy,
        _ => Error::Storage,
    })?;
    Ok(Claim {
        directory,
        app: app.clone(),
        _lock: lock,
        published: false,
    })
}
impl Claim {
    pub fn publish(&mut self, advertisement: &Advertisement) -> Result<()> {
        if advertisement.version != 1
            || advertisement.pid() != std::process::id()
            || advertisement.resource.app_id != self.app
        {
            return Err(Error::Invalid);
        }
        let bytes = serde_json::to_vec(advertisement).map_err(|_| Error::Invalid)?;
        if bytes.len() > LIMIT {
            return Err(Error::Invalid);
        }
        self.directory.remove("instance.next")?;
        let mut staging = self
            .directory
            .open_file("instance.next", true, true)?
            .ok_or(Error::Storage)?;
        staging
            .write_all(&bytes)
            .and_then(|_| staging.sync_all())
            .map_err(|_| Error::Storage)?;
        drop(staging);
        rustix::fs::renameat(
            &self.directory.0,
            "instance.next",
            &self.directory.0,
            "instance.json",
        )
        .map_err(|_| Error::Storage)?;
        self.published = true;
        self.directory.0.sync_all().map_err(|_| Error::Storage)?;
        Ok(())
    }
}
impl Drop for Claim {
    fn drop(&mut self) {
        if self.published {
            let _ = self.directory.remove("instance.json");
        }
        let _ = self.directory.remove("instance.next");
    }
}
pub fn discover(app: &Identifier, profile: &Identifier) -> Result<Option<Advertisement>> {
    let Some(directory) = namespace(app, profile, false)? else {
        return Ok(None);
    };
    let Some(file) = directory.open_file("instance.json", false, false)? else {
        return Ok(None);
    };
    let mut bytes = Vec::new();
    file.take((LIMIT + 1) as u64)
        .read_to_end(&mut bytes)
        .map_err(|_| Error::Storage)?;
    if bytes.len() > LIMIT {
        return Err(Error::Invalid);
    }
    let ad: Advertisement = serde_json::from_slice(&bytes).map_err(|_| Error::Invalid)?;
    if ad.version != 1 || &ad.resource.app_id != app {
        return Err(Error::Invalid);
    }
    Ok(Some(ad))
}

#[cfg(test)]
mod tests;
