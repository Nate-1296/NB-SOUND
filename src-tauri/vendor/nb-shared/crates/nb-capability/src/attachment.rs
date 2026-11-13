//! Prueba de identidad para adhesión local. Una firma válida no concede permisos de dominio.
pub mod channel;
use ed25519_dalek::{Signature, Signer, SigningKey, VerifyingKey};
use nb_protocol::capability::{Epoch, ResourceKey};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    fmt,
    time::{Duration, SystemTime},
};
use subtle::ConstantTimeEq;
use tokio::time::Instant;
use zeroize::Zeroizing;

const DOMAIN: &[u8] = b"NB-LOCAL-ATTACH-V1\0";
const PROOF_LIFETIME: Duration = Duration::from_secs(60);

/// El reloj monotónico impide ampliar la vigencia ajustando el reloj civil.
/// El civil cubre suspensión en sistemas cuyo monotónico no cuenta el tiempo dormido.
/// Un retroceso anterior a la emisión también invalida el desafío.
struct Validity {
    deadline: Instant,
    issued_at: SystemTime,
}
impl Validity {
    fn new() -> Self {
        Self {
            deadline: Instant::now() + PROOF_LIFETIME,
            issued_at: SystemTime::now(),
        }
    }
    fn ensure_current(&self) -> Result<()> {
        self.check(Instant::now(), SystemTime::now())
    }
    fn check(&self, monotonic: Instant, civil: SystemTime) -> Result<()> {
        if monotonic >= self.deadline
            || civil
                .duration_since(self.issued_at)
                .map_or(true, |elapsed| elapsed >= PROOF_LIFETIME)
        {
            return Err(AttachmentError::Expired);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
pub enum AttachmentError {
    #[error("ATTACHMENT_INVALID")]
    Invalid,
    #[error("ATTACHMENT_EXPIRED")]
    Expired,
    #[error("ATTACHMENT_REPLAY")]
    Replay,
    #[error("ATTACHMENT_IDENTITY_MISSING")]
    IdentityMissing,
    #[error("ATTACHMENT_SECRET_STORE_FAILED")]
    SecretStore,
    #[error("ATTACHMENT_ENTROPY_UNAVAILABLE")]
    Entropy,
}
type Result<T> = std::result::Result<T, AttachmentError>;

fn hex(bytes: &[u8]) -> String {
    const HEX: &[u8] = b"0123456789abcdef";
    let mut text = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        text.push(HEX[(byte >> 4) as usize] as char);
        text.push(HEX[(byte & 15) as usize] as char);
    }
    text
}
fn unhex<const N: usize>(text: &str) -> Result<[u8; N]> {
    if text.len() != 2 * N
        || !text
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err(AttachmentError::Invalid);
    }
    let mut bytes = [0; N];
    for (index, pair) in text.as_bytes().as_chunks::<2>().0.iter().enumerate() {
        let digit = |b| if b <= b'9' { b - b'0' } else { b - b'a' + 10 };
        bytes[index] = (digit(pair[0]) << 4) | digit(pair[1]);
    }
    Ok(bytes)
}

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub struct PublicIdentity([u8; 32]);
impl TryFrom<String> for PublicIdentity {
    type Error = AttachmentError;
    fn try_from(text: String) -> Result<Self> {
        let bytes = unhex(&text)?;
        let key = VerifyingKey::from_bytes(&bytes).map_err(|_| AttachmentError::Invalid)?;
        if key.is_weak() {
            return Err(AttachmentError::Invalid);
        }
        Ok(Self(bytes))
    }
}
impl From<PublicIdentity> for String {
    fn from(identity: PublicIdentity) -> Self {
        hex(&identity.0)
    }
}
impl PublicIdentity {
    pub fn fingerprint(&self) -> String {
        hex(&Sha256::digest(self.0))
    }
}
impl fmt::Debug for PublicIdentity {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_tuple("PublicIdentity")
            .field(&self.fingerprint())
            .finish()
    }
}

/// El adaptador del consumidor usa su llavero. No hay implementación de archivos en claro.
pub trait SecretStore {
    fn load(&self) -> Result<Option<Zeroizing<Vec<u8>>>>;
    fn save(&self, secret: &[u8]) -> Result<()>;
}
pub struct ClientIdentity(SigningKey);
impl fmt::Debug for ClientIdentity {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("ClientIdentity(<redacted>)")
    }
}
impl ClientIdentity {
    /// `allow_creation` solo corresponde a una identidad local todavía pendiente.
    /// Una identidad confirmada sin clave no se reemplaza silenciosamente.
    /// El llamador serializa creación/confirmación entre procesos de la instalación.
    pub fn open(store: &impl SecretStore, allow_creation: bool) -> Result<Self> {
        let bytes = match store.load()? {
            Some(bytes) => bytes,
            None if allow_creation => {
                let mut generated = Zeroizing::new(vec![0; 32]);
                getrandom::fill(&mut generated).map_err(|_| AttachmentError::Entropy)?;
                store.save(&generated)?;
                let confirmed = store.load()?.ok_or(AttachmentError::SecretStore)?;
                if confirmed.len() != 32
                    || !bool::from(confirmed.as_slice().ct_eq(generated.as_slice()))
                {
                    return Err(AttachmentError::SecretStore);
                }
                confirmed
            }
            None => return Err(AttachmentError::IdentityMissing),
        };
        if bytes.len() != 32 {
            return Err(AttachmentError::Invalid);
        }
        let mut seed = Zeroizing::new([0; 32]);
        seed.copy_from_slice(&bytes);
        Ok(Self(SigningKey::from_bytes(&seed)))
    }
    pub fn public(&self) -> PublicIdentity {
        PublicIdentity(self.0.verifying_key().to_bytes())
    }
    pub fn prove(
        &self,
        challenge: &Challenge,
        resource: &ResourceKey,
        access: Access,
        participants: Participants,
    ) -> Result<Proof> {
        challenge.validate()?;
        if challenge.client != self.public()
            || &challenge.resource != resource
            || challenge.access != access
            || challenge.participants != participants
        {
            return Err(AttachmentError::Invalid);
        }
        Ok(Proof(self.0.sign(&challenge.message()?).to_bytes()))
    }
}

/// PIDs comprobados por el transporte, nunca tomados del anuncio como autorización.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Participants {
    client_pid: std::num::NonZeroU32,
    owner_pid: std::num::NonZeroU32,
}
impl Participants {
    pub fn new(client_pid: u32, owner_pid: u32) -> Result<Self> {
        Ok(Self {
            client_pid: std::num::NonZeroU32::new(client_pid).ok_or(AttachmentError::Invalid)?,
            owner_pid: std::num::NonZeroU32::new(owner_pid).ok_or(AttachmentError::Invalid)?,
        })
    }
    pub fn client_pid(self) -> u32 {
        self.client_pid.get()
    }
    pub fn owner_pid(self) -> u32 {
        self.owner_pid.get()
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Access {
    read: bool,
    change: bool,
    observe: bool,
}
impl Access {
    pub const ALL: Self = Self {
        read: true,
        change: true,
        observe: true,
    };
    pub const READ_ONLY: Self = Self {
        read: true,
        change: false,
        observe: true,
    };
    pub fn allows_read(self) -> bool {
        self.read
    }
    pub fn allows_change(self) -> bool {
        self.change
    }
    pub fn allows_observe(self) -> bool {
        self.observe
    }
    pub fn is_subset_of(self, permitted: Self) -> bool {
        (!self.read || permitted.read)
            && (!self.change || permitted.change)
            && (!self.observe || permitted.observe)
    }
    fn valid(self) -> bool {
        self.read || self.change || self.observe
    }
}

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Challenge {
    schema: u16,
    #[serde(deserialize_with = "strict_resource")]
    resource: ResourceKey,
    client: PublicIdentity,
    access: Access,
    nonce: Epoch,
    participants: Participants,
}
// El protocolo histórico de recursos admite extensiones. Este mensaje firmado tiene
// esquema cerrado: no debe ignorar ámbitos que el cliente todavía no entiende.
fn strict_resource<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> std::result::Result<ResourceKey, D::Error> {
    use nb_protocol::capability::Identifier;
    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Scope {
        app_id: Identifier,
        installation_id: Identifier,
        capability_id: Identifier,
        major_version: std::num::NonZeroU16,
        resource_id: Identifier,
    }
    let scope = Scope::deserialize(deserializer)?;
    Ok(ResourceKey {
        app_id: scope.app_id,
        installation_id: scope.installation_id,
        capability_id: scope.capability_id,
        major_version: scope.major_version,
        resource_id: scope.resource_id,
    })
}
impl fmt::Debug for Challenge {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("Challenge(<redacted>)")
    }
}
impl Challenge {
    pub fn resource(&self) -> &ResourceKey {
        &self.resource
    }
    pub fn access(&self) -> Access {
        self.access
    }
    pub fn participants(&self) -> Participants {
        self.participants
    }
    fn validate(&self) -> Result<()> {
        if self.schema != 1 || !self.access.valid() {
            return Err(AttachmentError::Invalid);
        }
        Ok(())
    }
    fn message(&self) -> Result<Vec<u8>> {
        let mut bytes = DOMAIN.to_vec();
        bytes.extend(serde_json::to_vec(self).map_err(|_| AttachmentError::Invalid)?);
        Ok(bytes)
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub struct Proof([u8; 64]);
impl TryFrom<String> for Proof {
    type Error = AttachmentError;
    fn try_from(text: String) -> Result<Self> {
        Ok(Self(unhex(&text)?))
    }
}
impl From<Proof> for String {
    fn from(proof: Proof) -> Self {
        hex(&proof.0)
    }
}
impl fmt::Debug for Proof {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("Proof(<redacted>)")
    }
}

/// Solo se construye al comprobar la firma sobre un desafío local vigente y no usado.
/// El propietario todavía debe consultar su concesión persistente/consentimiento.
pub struct VerifiedClient {
    public: PublicIdentity,
    resource: ResourceKey,
    access: Access,
    validity: Validity,
    participants: Participants,
}
impl VerifiedClient {
    pub fn public(&self) -> &PublicIdentity {
        &self.public
    }
    pub fn resource(&self) -> &ResourceKey {
        &self.resource
    }
    pub fn access(&self) -> Access {
        self.access
    }
    pub fn participants(&self) -> Participants {
        self.participants
    }
    pub fn ensure_current(&self) -> Result<()> {
        self.validity.ensure_current()
    }
}
pub struct PendingChallenge {
    challenge: Challenge,
    validity: Validity,
    consumed: bool,
}
impl PendingChallenge {
    pub fn new(
        resource: ResourceKey,
        client: PublicIdentity,
        access: Access,
        participants: Participants,
    ) -> Result<Self> {
        if !access.valid() {
            return Err(AttachmentError::Invalid);
        }
        Ok(Self {
            challenge: Challenge {
                schema: 1,
                resource,
                client,
                access,
                nonce: nb_protocol::local::new_session().map_err(|_| AttachmentError::Entropy)?,
                participants,
            },
            validity: Validity::new(),
            consumed: false,
        })
    }
    pub fn challenge(&self) -> &Challenge {
        &self.challenge
    }
    pub fn consume(&mut self, proof: &Proof) -> Result<VerifiedClient> {
        if self.consumed {
            return Err(AttachmentError::Replay);
        }
        self.consumed = true;
        self.validity.ensure_current()?;
        self.challenge.validate()?;
        VerifyingKey::from_bytes(&self.challenge.client.0)
            .map_err(|_| AttachmentError::Invalid)?
            .verify_strict(&self.challenge.message()?, &Signature::from_bytes(&proof.0))
            .map_err(|_| AttachmentError::Invalid)?;
        let client = VerifiedClient {
            public: self.challenge.client.clone(),
            resource: self.challenge.resource.clone(),
            access: self.challenge.access,
            validity: Validity {
                deadline: self.validity.deadline,
                issued_at: self.validity.issued_at,
            },
            participants: self.challenge.participants,
        };
        client.ensure_current()?;
        Ok(client)
    }
}

#[cfg(test)]
mod tests;
