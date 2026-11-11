//! Puerto de desarrollo de un único recurso, autorizado mediante bootstrap privado.
//! No registra aplicaciones ni reemplaza el catálogo del host de la suite.

use crate::{OwnedResource, ResourceEvent, StateOwner};
use nb_protocol::{
    MAX_REQUEST_ID,
    capability::{ChangeResult, Epoch, ResourceError, Revision, Snapshot},
    frame::{FrameError, read_frame, write_frame},
    host::Credential,
    local,
};
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::time::Duration;
use subtle::ConstantTimeEq;
use tokio::{
    io::{AsyncRead, AsyncReadExt},
    task::{JoinSet, spawn_blocking},
    time::timeout,
};

const IO_TIMEOUT: Duration = Duration::from_secs(5);
const LIFETIME: Duration = Duration::from_secs(900);

#[derive(Serialize, Deserialize)]
pub struct Bootstrap {
    pub session: Epoch,
    pub credential: Credential,
}

#[derive(Serialize, Deserialize)]
struct Request {
    id: u64,
    #[serde(flatten)]
    operation: Operation,
}

#[derive(Serialize, Deserialize)]
#[serde(tag = "method", content = "params", rename_all = "snake_case")]
enum Operation {
    Hello {
        version: u16,
        credential: Credential,
    },
    Read,
    Change {
        expected: Revision,
        command: Value,
    },
    Observe {
        after: Revision,
        wait_ms: u16,
    },
    Close,
}

#[derive(Debug, Serialize, Deserialize)]
struct Response {
    id: u64,
    #[serde(flatten)]
    result: Reply,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "status", content = "data", rename_all = "snake_case")]
pub enum Reply {
    Snapshot(Snapshot<Value>),
    Change(ChangeResult<Value>),
    NoChange,
    Closed,
    Denied,
    Error(ResourceError),
}

#[derive(Debug, thiserror::Error)]
pub enum PortError {
    #[error(transparent)]
    Frame(#[from] FrameError),
    #[error(transparent)]
    Local(#[from] local::LocalError),
    #[error("PORT_TIMEOUT")]
    Timeout,
    #[error("PORT_PROTOCOL_ERROR")]
    Protocol,
}

fn encode<V: Serialize>(snapshot: &Snapshot<V>) -> Result<Snapshot<Value>, ResourceError> {
    Ok(Snapshot {
        key: snapshot.key.clone(),
        revision: snapshot.revision.clone(),
        value: serde_json::to_value(&snapshot.value)
            .map_err(|_| ResourceError::OwnerContractViolation)?,
    })
}

async fn dispatch<O>(resource: &OwnedResource<O>, operation: Operation) -> Reply
where
    O: StateOwner,
    O::Value: Serialize,
    O::Command: DeserializeOwned + Send + 'static,
{
    let resource = resource.clone();
    match operation {
        Operation::Read => {
            match spawn_blocking(move || resource.read().and_then(|s| encode(&s))).await {
                Ok(Ok(snapshot)) => Reply::Snapshot(snapshot),
                Ok(Err(error)) => Reply::Error(error),
                Err(_) => Reply::Error(ResourceError::Unavailable),
            }
        }
        Operation::Change { expected, command } => {
            let Ok(command) = serde_json::from_value(command) else {
                return Reply::Error(ResourceError::InvalidInput);
            };
            match spawn_blocking(move || resource.compare_and_set(&expected, command)).await {
                Ok(Ok(result)) => {
                    let mapped = match result {
                        ChangeResult::Applied(s) => encode(&s).map(ChangeResult::Applied),
                        ChangeResult::Unchanged(s) => encode(&s).map(ChangeResult::Unchanged),
                        ChangeResult::Conflict(s) => encode(&s).map(ChangeResult::Conflict),
                    };
                    match mapped {
                        Ok(result) => Reply::Change(result),
                        Err(error) => Reply::Error(error),
                    }
                }
                Ok(Err(error)) => Reply::Error(error),
                Err(_) => Reply::Error(ResourceError::ResultUnknown),
            }
        }
        Operation::Observe { after, wait_ms } if wait_ms <= 5000 => {
            let observation = spawn_blocking(move || resource.subscribe()).await;
            let (snapshot, mut subscription) = match observation {
                Ok(Ok(observation)) => observation,
                Ok(Err(error)) => return Reply::Error(error),
                Err(_) => return Reply::Error(ResourceError::Unavailable),
            };
            if snapshot.revision != after {
                return match encode(&snapshot) {
                    Ok(s) => Reply::Snapshot(s),
                    Err(e) => Reply::Error(e),
                };
            }
            match timeout(
                Duration::from_millis(u64::from(wait_ms)),
                subscription.next(),
            )
            .await
            {
                Err(_) => Reply::NoChange,
                Ok(Ok(ResourceEvent::Confirmed(snapshot))) => match encode(&snapshot) {
                    Ok(s) => Reply::Snapshot(s),
                    Err(e) => Reply::Error(e),
                },
                Ok(Ok(ResourceEvent::Unavailable(e))) | Ok(Err(e)) => Reply::Error(e),
            }
        }
        Operation::Close => Reply::Closed,
        _ => Reply::Error(ResourceError::InvalidInput),
    }
}

async fn connection<O>(
    mut stream: local::Stream,
    resource: OwnedResource<O>,
    digest: [u8; 32],
) -> Result<(), PortError>
where
    O: StateOwner,
    O::Value: Serialize,
    O::Command: DeserializeOwned + Send + 'static,
{
    local::validate_peer(&stream)?;
    let result = async {
        let mut negotiated = false;
        let mut last_id = 0;
        loop {
            let request: Option<Request> = timeout(
                if negotiated {
                    Duration::from_secs(60)
                } else {
                    IO_TIMEOUT
                },
                read_frame(&mut stream),
            )
            .await
            .map_err(|_| PortError::Timeout)??;
            let Some(request) = request else {
                return Ok(());
            };
            if request.id == 0 || request.id > MAX_REQUEST_ID || request.id <= last_id {
                return Err(PortError::Protocol);
            }
            last_id = request.id;
            let reply =
                if !negotiated {
                    match request.operation {
                        Operation::Hello {
                            version: 1,
                            credential,
                        } if bool::from(digest.as_slice().ct_eq(
                            Sha256::digest(credential.expose_secret().as_bytes()).as_ref(),
                        )) =>
                        {
                            negotiated = true;
                            dispatch(&resource, Operation::Read).await
                        }
                        _ => Reply::Denied,
                    }
                } else {
                    dispatch(&resource, request.operation).await
                };
            let close = matches!(reply, Reply::Closed | Reply::Denied);
            timeout(
                IO_TIMEOUT,
                write_frame(
                    &mut stream,
                    &Response {
                        id: request.id,
                        result: reply,
                    },
                ),
            )
            .await
            .map_err(|_| PortError::Timeout)??;
            if close {
                return Ok(());
            }
        }
    }
    .await;
    local::finish_session(&mut stream).await;
    result
}

pub async fn serve<O, R>(resource: OwnedResource<O>, mut supervisor: R) -> Result<(), PortError>
where
    O: StateOwner,
    O::Value: Serialize,
    O::Command: DeserializeOwned + Send + 'static,
    R: AsyncRead + Unpin,
{
    let bootstrap: Bootstrap = timeout(IO_TIMEOUT, read_frame(&mut supervisor))
        .await
        .map_err(|_| PortError::Timeout)??
        .ok_or(PortError::Protocol)?;
    let digest: [u8; 32] = Sha256::digest(bootstrap.credential.expose_secret().as_bytes()).into();
    let endpoint = local::Endpoint::bind_named(&bootstrap.session)?;
    drop(bootstrap);
    let accept = async {
        let mut sessions = JoinSet::new();
        loop {
            tokio::select! {
                accepted = endpoint.accept(), if sessions.len() < local::MAX_SESSIONS => {
                    let stream = match accepted { Ok(stream) => stream, Err(error) => return Err(PortError::from(error)) };
                    let resource = resource.clone();
                    sessions.spawn(async move { let _ = connection(stream, resource, digest).await; });
                },
                Some(_) = sessions.join_next(), if !sessions.is_empty() => {},
            }
        }
    };
    let mut control = [0_u8; 1];
    tokio::select! {
        result = accept => result,
        _ = supervisor.read(&mut control) => Ok(()),
        _ = tokio::time::sleep(LIFETIME) => Ok(()),
    }
}

pub struct Client {
    stream: local::Stream,
    next_id: u64,
    usable: bool,
}

impl Client {
    pub async fn connect(
        session: &Epoch,
        credential: Credential,
        expected_pid: u32,
    ) -> Result<(Self, Snapshot<Value>), PortError> {
        let path = local::path_for(session)?;
        let stream = local::connect_endpoint(&path, expected_pid).await?;
        let mut client = Self {
            stream,
            next_id: 1,
            usable: true,
        };
        let reply = client
            .call(Operation::Hello {
                version: 1,
                credential,
            })
            .await?;
        match reply {
            Reply::Snapshot(snapshot) => Ok((client, snapshot)),
            _ => Err(PortError::Protocol),
        }
    }

    async fn call(&mut self, operation: Operation) -> Result<Reply, PortError> {
        if !self.usable || self.next_id > MAX_REQUEST_ID {
            return Err(PortError::Protocol);
        }
        self.usable = false;
        let id = self.next_id;
        self.next_id += 1;
        let close = matches!(operation, Operation::Close);
        let expected_reply = match &operation {
            Operation::Hello { .. } | Operation::Read | Operation::Observe { .. } => 0,
            Operation::Change { .. } => 1,
            Operation::Close => 2,
        };
        let observes = matches!(operation, Operation::Observe { .. });
        let result = timeout(Duration::from_secs(10), async {
            write_frame(&mut self.stream, &Request { id, operation }).await?;
            let response: Response = read_frame(&mut self.stream)
                .await?
                .ok_or(PortError::Protocol)?;
            if response.id != id {
                return Err(PortError::Protocol);
            }
            let valid = match &response.result {
                Reply::Snapshot(_) => expected_reply == 0,
                Reply::Change(_) => expected_reply == 1,
                Reply::Closed => expected_reply == 2,
                Reply::NoChange => observes,
                Reply::Denied | Reply::Error(_) => true,
            };
            if !valid {
                return Err(PortError::Protocol);
            }
            Ok(response.result)
        })
        .await
        .map_err(|_| PortError::Timeout)??;
        self.usable = !close && !matches!(result, Reply::Denied);
        Ok(result)
    }

    pub async fn read(&mut self) -> Result<Reply, PortError> {
        self.call(Operation::Read).await
    }
    pub async fn change(&mut self, expected: Revision, command: Value) -> Result<Reply, PortError> {
        self.call(Operation::Change { expected, command }).await
    }
    pub async fn observe(&mut self, after: Revision, wait_ms: u16) -> Result<Reply, PortError> {
        self.call(Operation::Observe { after, wait_ms }).await
    }
    pub async fn close(&mut self) -> Result<Reply, PortError> {
        self.call(Operation::Close).await
    }
}
