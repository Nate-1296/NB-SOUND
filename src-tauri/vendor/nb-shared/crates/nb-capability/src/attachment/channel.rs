//! Negociación local: el propietario decide consentimiento y concesión después de la prueba.
use super::{
    Access, AttachmentError, Challenge, Participants, PendingChallenge, Proof, PublicIdentity,
    VerifiedClient,
};
use crate::port::Bootstrap;
use nb_protocol::{
    capability::{Epoch, ResourceKey},
    frame::{FrameError, read_frame, write_frame},
    local,
};
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tokio::time::timeout;

const IO_TIMEOUT: Duration = Duration::from_secs(5);
const CONSENT_TIMEOUT: Duration = Duration::from_secs(60);

#[derive(Debug, thiserror::Error)]
pub enum ChannelError {
    #[error(transparent)]
    Local(#[from] local::LocalError),
    #[error(transparent)]
    Frame(#[from] FrameError),
    #[error(transparent)]
    Attachment(#[from] AttachmentError),
    #[error("ATTACHMENT_TIMEOUT")]
    Timeout,
    #[error("ATTACHMENT_PROTOCOL_ERROR")]
    Protocol,
    #[error("ATTACHMENT_DENIED")]
    Denied(Denial),
}
type Result<T> = std::result::Result<T, ChannelError>;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Denial {
    Rejected,
    Busy,
    Unavailable,
    Expired,
    Revoked,
}

#[derive(Serialize, Deserialize)]
#[serde(tag = "method", rename_all = "snake_case", deny_unknown_fields)]
enum Invitation {
    Activate {
        version: u16,
    },
    Attach {
        version: u16,
        client: PublicIdentity,
        access: Access,
    },
}

#[derive(Serialize, Deserialize)]
#[serde(
    tag = "status",
    content = "data",
    rename_all = "snake_case",
    deny_unknown_fields
)]
enum Message {
    Challenge(Challenge),
    Accepted(Bootstrap),
    Denied(Denial),
    ActivationRequested,
}

async fn receive<T: serde::de::DeserializeOwned>(
    stream: &mut local::Stream,
    wait: Duration,
) -> Result<T> {
    timeout(wait, read_frame(stream))
        .await
        .map_err(|_| ChannelError::Timeout)??
        .ok_or(ChannelError::Protocol)
}
async fn send<T: Serialize>(stream: &mut local::Stream, message: &T) -> Result<()> {
    timeout(IO_TIMEOUT, write_frame(stream, message))
        .await
        .map_err(|_| ChannelError::Timeout)??;
    Ok(())
}

/// El stream debe haber sido aceptado por el endpoint propietario. La identidad
/// comprobada todavía no concede acceso al recurso ni crea estado persistente.
pub async fn authenticate(
    stream: &mut local::Stream,
    resource: ResourceKey,
) -> Result<VerifiedClient> {
    match receive_invitation(stream, resource).await? {
        Incoming::Verified(client) => Ok(client),
        Incoming::Activation => Err(ChannelError::Protocol),
    }
}

pub enum Incoming {
    Activation,
    Verified(VerifiedClient),
}

/// La activación solo solicita mostrar la ventana y nunca emite una credencial.
pub async fn receive_invitation(
    stream: &mut local::Stream,
    resource: ResourceKey,
) -> Result<Incoming> {
    let client_pid = local::client_process_id(stream)?;
    let invitation: Invitation = receive(stream, IO_TIMEOUT).await?;
    let (client, access) = match invitation {
        Invitation::Activate { version: 1 } => return Ok(Incoming::Activation),
        Invitation::Attach {
            version: 1,
            client,
            access,
        } => (client, access),
        _ => return Err(ChannelError::Protocol),
    };
    let participants = Participants::new(client_pid, std::process::id())?;
    let mut pending = PendingChallenge::new(resource, client, access, participants)?;
    send(stream, &Message::Challenge(pending.challenge().clone())).await?;
    let proof: Proof = receive(stream, IO_TIMEOUT).await?;
    Ok(Incoming::Verified(pending.consume(&proof)?))
}

pub async fn confirm_activation(stream: &mut local::Stream) -> Result<()> {
    send(stream, &Message::ActivationRequested).await
}

/// Confirma recepción de la solicitud, sin prometer foco forzado en el compositor.
pub async fn activate(session: &Epoch, expected_pid: u32) -> Result<()> {
    let mut stream = local::connect_endpoint(&local::path_for(session)?, expected_pid).await?;
    send(&mut stream, &Invitation::Activate { version: 1 }).await?;
    match receive(&mut stream, IO_TIMEOUT).await? {
        Message::ActivationRequested => Ok(()),
        _ => Err(ChannelError::Protocol),
    }
}

/// Solo después del consentimiento o de comprobar una concesión vigente. El
/// propietario debe enlazar el puerto antes de anunciarlo y vigilar su revocación.
pub async fn accept(
    stream: &mut local::Stream,
    client: &VerifiedClient,
    bootstrap: Bootstrap,
) -> Result<()> {
    client.ensure_current()?;
    if local::client_process_id(stream)? != client.participants().client_pid() {
        return Err(ChannelError::Protocol);
    }
    send(stream, &Message::Accepted(bootstrap)).await
}
pub async fn reject(stream: &mut local::Stream, reason: Denial) -> Result<()> {
    send(stream, &Message::Denied(reason)).await
}

/// La conexión mantiene el canal de control privado de la sesión aceptada.
/// No se registra como recurso del host hasta verificar el puerto propietario.
pub struct AcceptedSession {
    pub bootstrap: Bootstrap,
    pub control: local::Stream,
}

/// Valida el PID del propietario antes de enviar identidad o firma. `sign` debe
/// usar el recurso, los permisos y los participantes esperados, sin firmar bytes libres.
pub async fn connect<F>(
    session: &Epoch,
    expected_pid: u32,
    resource: &ResourceKey,
    public: PublicIdentity,
    access: Access,
    sign: F,
) -> Result<AcceptedSession>
where
    F: FnOnce(&Challenge, Participants) -> std::result::Result<Proof, AttachmentError>,
{
    let mut stream = local::connect_endpoint(&local::path_for(session)?, expected_pid).await?;
    let participants = Participants::new(std::process::id(), expected_pid)?;
    send(
        &mut stream,
        &Invitation::Attach {
            version: 1,
            client: public.clone(),
            access,
        },
    )
    .await?;
    let challenge = match receive(&mut stream, IO_TIMEOUT).await? {
        Message::Challenge(challenge) => challenge,
        Message::Denied(reason) => return Err(ChannelError::Denied(reason)),
        _ => return Err(ChannelError::Protocol),
    };
    if challenge.resource() != resource
        || challenge.access() != access
        || challenge.participants() != participants
        || challenge.client != public
    {
        return Err(ChannelError::Protocol);
    }
    let proof = sign(&challenge, participants)?;
    send(&mut stream, &proof).await?;
    match receive(&mut stream, CONSENT_TIMEOUT).await? {
        Message::Accepted(bootstrap) => Ok(AcceptedSession {
            bootstrap,
            control: stream,
        }),
        Message::Denied(reason) => Err(ChannelError::Denied(reason)),
        _ => Err(ChannelError::Protocol),
    }
}

#[cfg(test)]
mod tests;
