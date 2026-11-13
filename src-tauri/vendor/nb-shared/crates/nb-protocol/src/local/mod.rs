//! Transporte reutilizable: sin autorización de dominio ni datos de aplicaciones.

use crate::{capability::Epoch, host::Credential};
use std::time::Duration;
use thiserror::Error;

#[cfg(target_os = "linux")]
pub mod rendezvous;

#[cfg(unix)]
mod unix;
#[cfg(unix)]
pub use unix::*;
#[cfg(windows)]
mod windows;
#[cfg(windows)]
pub use windows::*;

pub const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(5);
pub const WRITE_TIMEOUT: Duration = Duration::from_secs(5);
pub const MAX_SESSIONS: usize = 16;

#[derive(Debug, Error)]
pub enum LocalError {
    #[error("HOST_IO_ERROR")]
    HostIo(#[source] std::io::Error),
    #[error("LOCAL_ACCESS_DENIED")]
    AccessDenied,
    #[error("SESSION_TIMEOUT")]
    Timeout,
    #[error("ENTROPY_UNAVAILABLE")]
    EntropyUnavailable,
}

fn hex_random(length: usize) -> Result<String, LocalError> {
    let mut bytes = zeroize::Zeroizing::new(vec![0_u8; length]);
    getrandom::fill(&mut bytes).map_err(|_| LocalError::EntropyUnavailable)?;
    let mut result = String::with_capacity(length * 2);
    const HEX: &[u8; 16] = b"0123456789abcdef";
    for byte in bytes.iter() {
        result.push(HEX[(byte >> 4) as usize] as char);
        result.push(HEX[(byte & 15) as usize] as char);
    }
    Ok(result)
}

pub fn new_session() -> Result<Epoch, LocalError> {
    Epoch::try_from(hex_random(16)?).map_err(|_| LocalError::EntropyUnavailable)
}

pub fn new_credential() -> Result<Credential, LocalError> {
    Credential::from_secret(hex_random(32)?).ok_or(LocalError::EntropyUnavailable)
}
