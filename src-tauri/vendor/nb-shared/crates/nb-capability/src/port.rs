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
    io::AsyncRead,
    sync::watch,
    task::{JoinSet, spawn_blocking},
    time::timeout,
};

const IO_TIMEOUT: Duration = Duration::from_secs(5);
const LIFETIME: Duration = Duration::from_secs(900);

#[derive(Clone)]
struct Policy {
    client_pid: Option<u32>,
    access: [bool; 3],
    revoked: Option<watch::Receiver<bool>>,
}
impl Policy {
    fn private_supervisor() -> Self {
        Self {
            client_pid: None,
            access: [true; 3],
            revoked: None,
        }
    }
    fn current(&self) -> bool {
        self.revoked
            .as_ref()
            .is_none_or(|revoked| !*revoked.borrow() && revoked.has_changed().is_ok())
    }
    fn allows(&self, operation: &Operation) -> bool {
        self.current()
            && match operation {
                Operation::Hello { .. } | Operation::Read => self.access[0],
                Operation::Change { .. } => self.access[1],
                Operation::Observe { .. } => self.access[2],
                Operation::Close => true,
            }
    }
    async fn wait_revoked(mut self) {
        let Some(ref mut revoked) = self.revoked else {
            return std::future::pending().await;
        };
        while !*revoked.borrow_and_update() {
            if revoked.changed().await.is_err() {
                return;
            }
        }
    }
}

/// Puerto ya enlazado. Permite anunciarlo por el canal de adhesión antes de
/// empezar a aceptar solicitudes, sin una carrera de creación del endpoint.
pub struct Session<O: StateOwner> {
    endpoint: local::Endpoint,
    resource: OwnedResource<O>,
    digest: [u8; 32],
    policy: Policy,
}
impl<O: StateOwner> Session<O>
where
    O::Value: Serialize,
    O::Command: DeserializeOwned + Send + 'static,
{
    fn bind(
        resource: OwnedResource<O>,
        bootstrap: Bootstrap,
        policy: Policy,
    ) -> Result<Self, PortError> {
        let digest = Sha256::digest(bootstrap.credential.expose_secret().as_bytes()).into();
        let endpoint = local::Endpoint::bind_named(&bootstrap.session)?;
        Ok(Self {
            endpoint,
            resource,
            digest,
            policy,
        })
    }

    /// La app propietaria debe comprobar su concesión persistente antes de llamar.
    /// Revocar o perder el emisor cierra este puerto y todas sus conexiones.
    #[cfg(feature = "attachment")]
    pub fn bind_authorized(
        resource: OwnedResource<O>,
        bootstrap: Bootstrap,
        client: &crate::attachment::VerifiedClient,
        revoked: watch::Receiver<bool>,
    ) -> Result<Self, PortError> {
        client.ensure_current().map_err(|_| PortError::Protocol)?;
        // Hello 1/2 siempre devuelve una instantánea: no admitir ámbitos sin lectura.
        if !client.access().allows_read()
            || &resource
                .lock()
                .map_err(|_| PortError::Protocol)?
                .current
                .key
                != client.resource()
        {
            return Err(PortError::Protocol);
        }
        let policy = Policy {
            client_pid: Some(client.participants().client_pid()),
            access: [
                client.access().allows_read(),
                client.access().allows_change(),
                client.access().allows_observe(),
            ],
            revoked: Some(revoked),
        };
        if !policy.current() {
            return Err(PortError::Protocol);
        }
        Self::bind(resource, bootstrap, policy)
    }

    pub async fn serve<R: AsyncRead + Unpin>(self, supervisor: R) -> Result<(), PortError> {
        let accept = async {
            let mut sessions = JoinSet::new();
            loop {
                tokio::select! {
                    accepted = self.endpoint.accept(), if sessions.len() < local::MAX_SESSIONS => {
                        let stream = accepted?;
                        let resource = self.resource.clone();
                        let digest = self.digest;
                        let policy = self.policy.clone();
                        sessions.spawn(async move { let _ = connection(stream, resource, digest, policy).await; });
                    },
                    Some(_) = sessions.join_next(), if !sessions.is_empty() => {},
                }
            }
        };
        tokio::select! {
            result = accept => result,
            result = supervise(supervisor) => result,
            () = self.policy.clone().wait_revoked() => Ok(()),
        }
    }
}

#[derive(Serialize, Deserialize)]
pub struct Bootstrap {
    pub session: Epoch,
    pub credential: Credential,
}

/// Solo viaja por la tubería privada heredada, nunca por el puerto de clientes.
#[derive(Serialize, Deserialize)]
#[serde(tag = "method", rename_all = "snake_case", deny_unknown_fields)]
pub enum Control {
    Renew,
}

async fn supervise<R: AsyncRead + Unpin>(mut supervisor: R) -> Result<(), PortError> {
    loop {
        match timeout(LIFETIME, read_frame::<_, Control>(&mut supervisor)).await {
            Ok(Ok(Some(Control::Renew))) => {}
            Ok(Ok(None)) | Err(_) => return Ok(()),
            Ok(Err(error)) => return Err(error.into()),
        }
    }
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
    policy: Policy,
) -> Result<(), PortError>
where
    O: StateOwner,
    O::Value: Serialize,
    O::Command: DeserializeOwned + Send + 'static,
{
    local::validate_peer(&stream)?;
    if let Some(expected) = policy.client_pid
        && local::client_process_id(&stream)? != expected
    {
        return Err(PortError::Protocol);
    }
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
                if !policy.allows(&request.operation) {
                    Reply::Denied
                } else if !negotiated {
                    match request.operation {
                        Operation::Hello {
                            version: 1 | 2,
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

pub async fn serve<O, R>(resource: OwnedResource<O>, supervisor: R) -> Result<(), PortError>
where
    O: StateOwner,
    O::Value: Serialize,
    O::Command: DeserializeOwned + Send + 'static,
    R: AsyncRead + Unpin,
{
    serve_with_policy(resource, supervisor, Policy::private_supervisor()).await
}

/// El propietario puede retirar también un bootstrap heredado. La señal se
/// comprueba antes de cada operación, además de cerrar puerto y conexiones.
pub async fn serve_revocable<O, R>(
    resource: OwnedResource<O>,
    supervisor: R,
    revoked: watch::Receiver<bool>,
) -> Result<(), PortError>
where
    O: StateOwner,
    O::Value: Serialize,
    O::Command: DeserializeOwned + Send + 'static,
    R: AsyncRead + Unpin,
{
    let mut policy = Policy::private_supervisor();
    policy.revoked = Some(revoked);
    serve_with_policy(resource, supervisor, policy).await
}

async fn serve_with_policy<O, R>(
    resource: OwnedResource<O>,
    mut supervisor: R,
    policy: Policy,
) -> Result<(), PortError>
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
    if !policy.current() {
        return Err(PortError::Protocol);
    }
    Session::bind(resource, bootstrap, policy)?
        .serve(supervisor)
        .await
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
        Self::connect_version(session, credential, expected_pid, 1).await
    }

    /// El `hello` 2 acredita soporte de renovación por el canal privado.
    /// Propietarios anteriores rechazan esa negociación sin modificar el recurso.
    pub async fn connect_with_renewal(
        session: &Epoch,
        credential: Credential,
        expected_pid: u32,
    ) -> Result<(Self, Snapshot<Value>, bool), PortError> {
        if let Ok((client, snapshot)) =
            Self::connect_version(session, credential.clone(), expected_pid, 2).await
        {
            return Ok((client, snapshot, true));
        }
        let (client, snapshot) = Self::connect(session, credential, expected_pid).await?;
        Ok((client, snapshot, false))
    }

    async fn connect_version(
        session: &Epoch,
        credential: Credential,
        expected_pid: u32,
        version: u16,
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
                version,
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

#[cfg(test)]
mod lease_tests {
    use super::*;

    #[tokio::test(start_paused = true)]
    async fn solo_un_frame_completo_privado_extiende_el_plazo_y_eof_lo_cierra() {
        let (mut parent, supervisor) = tokio::io::duplex(4096);
        let task = tokio::spawn(supervise(supervisor));
        tokio::task::yield_now().await;
        tokio::time::advance(LIFETIME - Duration::from_secs(1)).await;
        assert!(!task.is_finished());
        write_frame(&mut parent, &Control::Renew).await.unwrap();
        tokio::task::yield_now().await;
        tokio::time::advance(LIFETIME - Duration::from_secs(1)).await;
        assert!(!task.is_finished());
        drop(parent);
        task.await.unwrap().unwrap();
    }

    #[tokio::test(start_paused = true)]
    async fn el_enlace_sin_renovacion_caduca_y_un_frame_parcial_no_lo_prolonga() {
        use tokio::io::AsyncWriteExt;
        for partial in [false, true] {
            let (mut parent, supervisor) = tokio::io::duplex(4096);
            let task = tokio::spawn(supervise(supervisor));
            tokio::task::yield_now().await;
            if partial {
                let mut frame = Vec::new();
                write_frame(&mut frame, &Control::Renew).await.unwrap();
                parent.write_all(&frame[..frame.len() - 1]).await.unwrap();
            }
            tokio::time::advance(LIFETIME).await;
            task.await.unwrap().unwrap();
        }
    }

    #[tokio::test]
    async fn un_control_malformado_no_se_acepta_como_renovacion() {
        let (mut parent, supervisor) = tokio::io::duplex(4096);
        write_frame(&mut parent, &serde_json::json!({"method":"grant"}))
            .await
            .unwrap();
        assert!(supervise(supervisor).await.is_err());
    }
}
