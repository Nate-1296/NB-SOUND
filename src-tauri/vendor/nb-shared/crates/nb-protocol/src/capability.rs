//! Modelos internos de recursos. Aún no son operaciones expuestas por el host local.

use std::{fmt, num::NonZeroU16};

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::MAX_REQUEST_ID;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Error)]
pub enum InvalidContract {
    #[error("INVALID_IDENTIFIER")]
    Identifier,
    #[error("INVALID_EPOCH")]
    Epoch,
    #[error("INVALID_SEQUENCE")]
    Sequence,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub struct Identifier(String);

impl TryFrom<String> for Identifier {
    type Error = InvalidContract;
    fn try_from(value: String) -> Result<Self, Self::Error> {
        if value.is_empty()
            || value.len() > 128
            || !value
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b"._-".contains(&b))
        {
            return Err(InvalidContract::Identifier);
        }
        Ok(Self(value))
    }
}

impl From<Identifier> for String {
    fn from(id: Identifier) -> Self {
        id.0
    }
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub struct Epoch(String);

impl TryFrom<String> for Epoch {
    type Error = InvalidContract;
    fn try_from(value: String) -> Result<Self, Self::Error> {
        if value.len() != 32
            || !value
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            return Err(InvalidContract::Epoch);
        }
        Ok(Self(value))
    }
}

impl From<Epoch> for String {
    fn from(epoch: Epoch) -> Self {
        epoch.0
    }
}

/// Rango representable sin pérdida por un consumidor JavaScript.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(try_from = "u64", into = "u64")]
pub struct Sequence(u64);

impl Sequence {
    pub const ZERO: Self = Self(0);
    pub fn get(self) -> u64 {
        self.0
    }
    pub fn checked_next(self) -> Option<Self> {
        Self::try_from(self.0.checked_add(1)?).ok()
    }
}

impl TryFrom<u64> for Sequence {
    type Error = InvalidContract;
    fn try_from(value: u64) -> Result<Self, Self::Error> {
        if value > MAX_REQUEST_ID {
            return Err(InvalidContract::Sequence);
        }
        Ok(Self(value))
    }
}

impl From<Sequence> for u64 {
    fn from(sequence: Sequence) -> Self {
        sequence.0
    }
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub struct ResourceKey {
    pub app_id: Identifier,
    pub installation_id: Identifier,
    pub capability_id: Identifier,
    pub major_version: NonZeroU16,
    pub resource_id: Identifier,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Revision {
    pub epoch: Epoch,
    pub sequence: Sequence,
}

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Snapshot<V> {
    pub key: ResourceKey,
    pub revision: Revision,
    pub value: V,
}

impl<V> fmt::Debug for Snapshot<V> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Snapshot")
            .field("revision", &self.revision)
            .field("value", &"[REDACTED]")
            .finish_non_exhaustive()
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "status", content = "data", rename_all = "snake_case")]
pub enum ChangeResult<V> {
    Applied(Snapshot<V>),
    Unchanged(Snapshot<V>),
    Conflict(Snapshot<V>),
}

/// No contiene datos libres de dominio ni detalles internos que puedan acabar en logs.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Error, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ResourceError {
    #[error("UNAVAILABLE")]
    Unavailable,
    #[error("INVALID_INPUT")]
    InvalidInput,
    #[error("PERSISTENCE_ERROR")]
    Persistence,
    #[error("RESULT_UNKNOWN")]
    ResultUnknown,
    #[error("OWNER_CONTRACT_VIOLATION")]
    OwnerContractViolation,
    #[error("REVISION_EXHAUSTED")]
    RevisionExhausted,
    #[error("SYNCHRONIZATION_ERROR")]
    Synchronization,
    #[error("ENTROPY_UNAVAILABLE")]
    EntropyUnavailable,
}
