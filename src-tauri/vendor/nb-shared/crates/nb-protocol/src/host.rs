//! Autorización temporal y control privado del host. No es un SDK público.

use std::{fmt, path::PathBuf};

use crate::capability::{Epoch, ResourceKey};
use serde::{Deserialize, Deserializer, Serialize};
use zeroize::Zeroizing;

#[derive(Clone, Serialize)]
#[serde(transparent)]
pub struct Credential(Zeroizing<String>);

impl Credential {
    pub fn from_secret(value: String) -> Option<Self> {
        let value = Zeroizing::new(value);
        (value.len() == 64
            && value
                .bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()))
        .then_some(Self(value))
    }

    pub fn expose_secret(&self) -> &str {
        &self.0
    }
}

impl fmt::Debug for Credential {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("Credential([REDACTED])")
    }
}

impl<'de> Deserialize<'de> for Credential {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let value = Zeroizing::<String>::deserialize(deserializer)?;
        if value.len() == 64
            && value
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            Ok(Self(value))
        } else {
            Err(serde::de::Error::custom("INVALID_CREDENTIAL"))
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Permission {
    Ping,
    ListCapabilities,
    ReadResource(ResourceKey),
    ChangeResource(ResourceKey),
    ObserveResource(ResourceKey),
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Authenticate {
    pub credential: Credential,
}

#[derive(Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "status", rename_all = "snake_case")]
pub enum Authentication {
    Authenticated,
    Rejected,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct HostReady {
    pub endpoint: PathBuf,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct AdminRequest {
    pub id: u64,
    #[serde(flatten)]
    pub operation: AdminOperation,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "method", content = "params", rename_all = "snake_case")]
pub enum AdminOperation {
    ConfigureIdentity {
        directory: crate::attachment::PrivatePath,
    },
    BeginAttachment {
        spec: crate::attachment::AttachmentSpec,
        consent: bool,
    },
    AttachmentStatus {
        id: Epoch,
    },
    CancelAttachment {
        id: Epoch,
    },
    Grant {
        principal: String,
        permissions: Vec<Permission>,
    },
    Revoke {
        grant_id: u64,
    },
    Renew {
        grant_id: u64,
    },
    RegisterOwner {
        key: ResourceKey,
        session: Epoch,
        credential: Credential,
        pid: u32,
    },
    UnregisterOwner {
        key: ResourceKey,
    },
    Shutdown,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct AdminResponse {
    pub id: u64,
    #[serde(flatten)]
    pub outcome: AdminOutcome,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "status", content = "data", rename_all = "snake_case")]
pub enum AdminOutcome {
    IdentityConfigured,
    AttachmentStarted {
        id: Epoch,
    },
    AttachmentReport(crate::attachment::AttachmentReport),
    AttachmentCancelled,
    Granted {
        grant_id: u64,
        credential: Credential,
        expires_in_seconds: u64,
    },
    Revoked,
    Renewed {
        expires_in_seconds: u64,
    },
    Registered,
    Unregistered,
    ShuttingDown,
    Error {
        code: AdminError,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum AdminError {
    AttachmentNotConfigured,
    AttachmentNotFound,
    InvalidRequestId,
    InvalidPrincipal,
    InvalidPermissions,
    GrantLimit,
    GrantNotFound,
    EntropyUnavailable,
    OwnerUnavailable,
    OwnerMismatch,
    OwnerLimit,
}
