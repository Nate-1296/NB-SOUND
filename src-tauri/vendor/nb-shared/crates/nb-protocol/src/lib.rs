//! Contrato local de desarrollo. No autentica aplicaciones instaladas ni implementa Mesh.

pub mod capability;
pub mod client;
pub mod frame;
pub mod host;
#[cfg(all(feature = "local", any(unix, windows)))]
pub mod local;

use capability::{ChangeResult, ResourceError, ResourceKey, Revision, Snapshot};
use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const PROTOCOL_VERSION: u16 = 1;
pub const MAX_FRAME_BYTES: usize = 64 * 1024;
pub const MAX_REQUEST_ID: u64 = 9_007_199_254_740_991;

/// Los identificadores permanecen representables exactamente en clientes JavaScript.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Request {
    pub id: u64,
    #[serde(flatten)]
    pub operation: Operation,
}

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "method", content = "params", rename_all = "snake_case")]
pub enum Operation {
    Hello {
        protocol_version: u16,
    },
    Ping,
    ListCapabilities,
    ReadResource {
        key: ResourceKey,
    },
    ChangeResource {
        key: ResourceKey,
        expected: Revision,
        command: Value,
    },
    ObserveResource {
        key: ResourceKey,
        after: Revision,
        wait_ms: u16,
    },
    Shutdown,
}

impl std::fmt::Debug for Operation {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("Operation([REDACTED])")
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Response {
    pub id: u64,
    #[serde(flatten)]
    pub outcome: Outcome,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "status", content = "data", rename_all = "snake_case")]
pub enum Outcome {
    Ok(ResultData),
    Error(ErrorCode),
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ResultData {
    Hello { protocol_version: u16 },
    Pong,
    Capabilities { capabilities: Vec<Capability> },
    ShuttingDown,
    ResourceSnapshot(Snapshot<Value>),
    ResourceChange(ChangeResult<Value>),
    ResourceNoChange,
    ResourceFailure { code: ResourceError },
}

/// Identidad declarativa de una capacidad; no constituye credencial ni autorización.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Capability {
    pub app_id: String,
    pub capability_id: String,
    pub version: u16,
    pub resource: ResourceKey,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ErrorCode {
    HandshakeRequired,
    AlreadyNegotiated,
    IncompatibleVersion,
    InvalidRequestId,
    RequestIdOutOfOrder,
    Unauthorized,
    PermissionDenied,
}

/// Estado de una única sesión privada. No contiene estado de dominio de las apps.
#[derive(Default)]
pub struct Session {
    negotiated: bool,
    last_id: u64,
}

pub struct Transition {
    pub response: Response,
    pub close: bool,
}

impl Session {
    pub fn handle(&mut self, request: Request) -> Transition {
        let id = request.id;
        if id == 0 || id > MAX_REQUEST_ID {
            return Self::error(id, ErrorCode::InvalidRequestId, true);
        }
        if id <= self.last_id {
            return Self::error(id, ErrorCode::RequestIdOutOfOrder, true);
        }
        self.last_id = id;

        if !self.negotiated {
            return match request.operation {
                Operation::Hello { protocol_version } if protocol_version == PROTOCOL_VERSION => {
                    self.negotiated = true;
                    Self::ok(id, ResultData::Hello { protocol_version }, false)
                }
                Operation::Hello { .. } => Self::error(id, ErrorCode::IncompatibleVersion, true),
                _ => Self::error(id, ErrorCode::HandshakeRequired, true),
            };
        }

        match request.operation {
            Operation::Hello { .. } => Self::error(id, ErrorCode::AlreadyNegotiated, true),
            Operation::Ping => Self::ok(id, ResultData::Pong, false),
            // No se anuncian proveedores ni capacidades que todavía no existen.
            Operation::ListCapabilities => Self::ok(
                id,
                ResultData::Capabilities {
                    capabilities: vec![],
                },
                false,
            ),
            Operation::ReadResource { .. }
            | Operation::ChangeResource { .. }
            | Operation::ObserveResource { .. } => Self::ok(
                id,
                ResultData::ResourceFailure {
                    code: ResourceError::Unavailable,
                },
                false,
            ),
            Operation::Shutdown => Self::ok(id, ResultData::ShuttingDown, true),
        }
    }

    fn ok(id: u64, data: ResultData, close: bool) -> Transition {
        Transition {
            response: Response {
                id,
                outcome: Outcome::Ok(data),
            },
            close,
        }
    }

    fn error(id: u64, code: ErrorCode, close: bool) -> Transition {
        Transition {
            response: Response {
                id,
                outcome: Outcome::Error(code),
            },
            close,
        }
    }
}
