//! Operaciones administrativas privadas de adhesión; no contienen credenciales persistentes.
use crate::capability::{Epoch, ResourceKey};
use serde::{Deserialize, Serialize};
use std::{
    fmt,
    num::NonZeroU32,
    path::{Path, PathBuf},
};

#[derive(Clone, Serialize, Deserialize)]
#[serde(transparent)]
pub struct PrivatePath(PathBuf);
impl PrivatePath {
    pub fn new(path: PathBuf) -> Self {
        Self(path)
    }
    pub fn as_path(&self) -> &Path {
        &self.0
    }
}
impl fmt::Debug for PrivatePath {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("PrivatePath(<redacted>)")
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AttachmentSpec {
    pub key: ResourceKey,
    pub invitation: Epoch,
    pub pid: NonZeroU32,
    pub executable: PrivatePath,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AttachmentFailure {
    NoConsent,
    IdentityUnavailable,
    OwnerUnavailable,
    OwnerMismatch,
    Unsupported,
    Internal,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AttachmentDenial {
    Rejected,
    Busy,
    Unavailable,
    Expired,
    Revoked,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(
    tag = "state",
    content = "data",
    rename_all = "snake_case",
    deny_unknown_fields
)]
pub enum AttachmentState {
    Pending,
    Connected { key: ResourceKey },
    Denied { reason: AttachmentDenial },
    Failed { code: AttachmentFailure },
    Disconnected,
    Cancelled,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AttachmentReport {
    pub id: Epoch,
    pub result: AttachmentState,
}
