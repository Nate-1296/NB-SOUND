use super::*;
use std::{cell::RefCell, num::NonZeroU16};

#[derive(Default)]
struct MemoryStore {
    bytes: RefCell<Option<Vec<u8>>>,
    reject: bool,
    alter: bool,
}
impl SecretStore for MemoryStore {
    fn load(&self) -> Result<Option<Zeroizing<Vec<u8>>>> {
        if self.reject {
            return Err(AttachmentError::SecretStore);
        }
        Ok(self
            .bytes
            .borrow()
            .as_ref()
            .map(|bytes| Zeroizing::new(bytes.clone())))
    }
    fn save(&self, secret: &[u8]) -> Result<()> {
        if self.reject {
            return Err(AttachmentError::SecretStore);
        }
        *self.bytes.borrow_mut() = Some(if self.alter {
            vec![42; 32]
        } else {
            secret.to_vec()
        });
        Ok(())
    }
}
fn resource() -> ResourceKey {
    ResourceKey {
        app_id: "nb.sound".to_owned().try_into().unwrap(),
        installation_id: "installation-a".to_owned().try_into().unwrap(),
        capability_id: "backup.frequency".to_owned().try_into().unwrap(),
        major_version: NonZeroU16::new(1).unwrap(),
        resource_id: "schedule".to_owned().try_into().unwrap(),
    }
}
fn peers() -> Participants {
    Participants::new(100, 200).unwrap()
}
fn identity(seed: u8) -> ClientIdentity {
    ClientIdentity(SigningKey::from_bytes(&[seed; 32]))
}

#[test]
fn la_identidad_persistida_se_reutiliza_y_una_clave_perdida_o_danada_no_se_reemplaza() {
    let store = MemoryStore::default();
    let initial = ClientIdentity::open(&store, true).unwrap();
    assert_eq!(
        ClientIdentity::open(&store, false).unwrap().public(),
        initial.public()
    );
    assert_eq!(
        ClientIdentity::open(&store, true).unwrap().public(),
        initial.public()
    );
    *store.bytes.borrow_mut() = None;
    assert_eq!(
        ClientIdentity::open(&store, false).unwrap_err(),
        AttachmentError::IdentityMissing
    );
    assert!(store.bytes.borrow().is_none());
    *store.bytes.borrow_mut() = Some(vec![1; 4]);
    assert_eq!(
        ClientIdentity::open(&store, true).unwrap_err(),
        AttachmentError::Invalid
    );
    assert_eq!(store.bytes.borrow().as_ref().unwrap().len(), 4);
}
#[test]
fn un_llavero_fallido_o_que_no_confirma_la_misma_clave_no_entrega_una_identidad() {
    let failed = MemoryStore {
        reject: true,
        ..Default::default()
    };
    assert_eq!(
        ClientIdentity::open(&failed, true).unwrap_err(),
        AttachmentError::SecretStore
    );
    let changed = MemoryStore {
        alter: true,
        ..Default::default()
    };
    assert_eq!(
        ClientIdentity::open(&changed, true).unwrap_err(),
        AttachmentError::SecretStore
    );
}
#[test]
fn una_prueba_valida_se_vincula_a_instalacion_ambito_e_identidad_y_no_se_repite() {
    let client = identity(7);
    let mut pending =
        PendingChallenge::new(resource(), client.public(), Access::ALL, peers()).unwrap();
    let wire = serde_json::to_vec(pending.challenge()).unwrap();
    let challenge: Challenge = serde_json::from_slice(&wire).unwrap();
    let proof = client
        .prove(&challenge, &resource(), Access::ALL, peers())
        .unwrap();
    let verified = pending.consume(&proof).unwrap();
    assert_eq!(verified.public(), &client.public());
    assert_eq!(verified.resource(), &resource());
    assert_eq!(verified.access(), Access::ALL);
    verified.ensure_current().unwrap();
    assert_eq!(pending.consume(&proof).err(), Some(AttachmentError::Replay));
    let mut other_session =
        PendingChallenge::new(resource(), client.public(), Access::ALL, peers()).unwrap();
    assert!(other_session.consume(&proof).is_err());
}
#[test]
fn el_cliente_no_firma_una_ampliacion_del_ambito_ni_otra_instalacion() {
    let client = identity(7);
    let pending = PendingChallenge::new(resource(), client.public(), Access::ALL, peers()).unwrap();
    assert_eq!(
        client
            .prove(pending.challenge(), &resource(), Access::READ_ONLY, peers())
            .err(),
        Some(AttachmentError::Invalid)
    );
    let mut other = resource();
    other.installation_id = "installation-b".to_owned().try_into().unwrap();
    assert_eq!(
        client
            .prove(pending.challenge(), &other, Access::ALL, peers())
            .err(),
        Some(AttachmentError::Invalid)
    );
    assert!(
        identity(8)
            .prove(pending.challenge(), &resource(), Access::ALL, peers())
            .is_err()
    );
    assert!(Access::READ_ONLY.is_subset_of(Access::ALL));
    assert!(!Access::ALL.is_subset_of(Access::READ_ONLY));
    assert!(
        client
            .prove(
                pending.challenge(),
                &resource(),
                Access::ALL,
                Participants::new(101, 200).unwrap()
            )
            .is_err()
    );
    assert!(
        client
            .prove(
                pending.challenge(),
                &resource(),
                Access::ALL,
                Participants::new(100, 201).unwrap()
            )
            .is_err()
    );
    assert!(Participants::new(0, 200).is_err());
    assert!(Participants::new(100, 0).is_err());
}
#[test]
fn la_firma_no_sirve_para_otro_dominio_y_una_prueba_invalida_tambien_se_consume() {
    let client = identity(7);
    let mut pending =
        PendingChallenge::new(resource(), client.public(), Access::ALL, peers()).unwrap();
    let proof = Proof(client.0.sign(b"NB-RELEASE-V1\0payload").to_bytes());
    assert_eq!(
        pending.consume(&proof).err(),
        Some(AttachmentError::Invalid)
    );
    let correct = client
        .prove(pending.challenge(), &resource(), Access::ALL, peers())
        .unwrap();
    assert_eq!(
        pending.consume(&correct).err(),
        Some(AttachmentError::Replay)
    );
}
#[tokio::test(start_paused = true)]
async fn un_desafio_o_una_prueba_que_caducan_no_autorizan_una_sesion() {
    let client = identity(7);
    let mut expired =
        PendingChallenge::new(resource(), client.public(), Access::ALL, peers()).unwrap();
    let proof = client
        .prove(expired.challenge(), &resource(), Access::ALL, peers())
        .unwrap();
    tokio::time::advance(PROOF_LIFETIME).await;
    assert_eq!(
        expired.consume(&proof).err(),
        Some(AttachmentError::Expired)
    );
    let mut pending =
        PendingChallenge::new(resource(), client.public(), Access::ALL, peers()).unwrap();
    let proof = client
        .prove(pending.challenge(), &resource(), Access::ALL, peers())
        .unwrap();
    let verified = pending.consume(&proof).unwrap();
    tokio::time::advance(PROOF_LIFETIME).await;
    assert_eq!(verified.ensure_current(), Err(AttachmentError::Expired));
}
#[test]
fn suspender_o_cambiar_el_reloj_no_extiende_la_vigencia() {
    let validity = Validity::new();
    let monotonic = validity.deadline - PROOF_LIFETIME;
    let civil = validity.issued_at;
    assert!(validity.check(monotonic, civil).is_ok());
    // Simula suspensión con monotónico detenido y reloj civil avanzado.
    assert_eq!(
        validity.check(monotonic, civil + PROOF_LIFETIME),
        Err(AttachmentError::Expired)
    );
    assert_eq!(
        validity.check(monotonic, civil - Duration::from_secs(1)),
        Err(AttachmentError::Expired)
    );
    // Aunque el civil siga dentro de plazo, el monotónico basta para caducar.
    assert_eq!(
        validity.check(validity.deadline, civil + Duration::from_secs(1)),
        Err(AttachmentError::Expired)
    );
}
#[test]
fn las_entradas_de_red_y_los_registros_no_admiten_identidades_debiles_ni_secretos() {
    assert!(PublicIdentity::try_from("0".repeat(64)).is_err());
    assert!(PublicIdentity::try_from("f".repeat(63)).is_err());
    let client = identity(7);
    let pending = PendingChallenge::new(resource(), client.public(), Access::ALL, peers()).unwrap();
    let mut value = serde_json::to_value(pending.challenge()).unwrap();
    value["extra"] = serde_json::json!(true);
    assert!(serde_json::from_value::<Challenge>(value).is_err());
    let mut value = serde_json::to_value(pending.challenge()).unwrap();
    value["resource"]["device"] = serde_json::json!("another-device");
    assert!(serde_json::from_value::<Challenge>(value).is_err());
    let mut value = serde_json::to_value(pending.challenge()).unwrap();
    value["access"]["restore"] = serde_json::json!(true);
    assert!(serde_json::from_value::<Challenge>(value).is_err());
    let proof = client
        .prove(pending.challenge(), &resource(), Access::ALL, peers())
        .unwrap();
    assert_eq!(format!("{client:?}"), "ClientIdentity(<redacted>)");
    assert_eq!(format!("{proof:?}"), "Proof(<redacted>)");
    assert_eq!(
        format!("{:?}", pending.challenge()),
        "Challenge(<redacted>)"
    );
}
