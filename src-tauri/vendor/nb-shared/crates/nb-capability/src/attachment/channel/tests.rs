use super::*;
use crate::attachment::{ClientIdentity, SecretStore};
use std::sync::{
    Arc,
    atomic::{AtomicBool, Ordering},
};
use zeroize::Zeroizing;

struct Fixture;
impl SecretStore for Fixture {
    fn load(&self) -> std::result::Result<Option<Zeroizing<Vec<u8>>>, AttachmentError> {
        Ok(Some(Zeroizing::new(vec![7; 32])))
    }
    fn save(&self, _: &[u8]) -> std::result::Result<(), AttachmentError> {
        panic!("no se crea una identidad de producto")
    }
}

#[tokio::test]
async fn activar_pide_la_ventana_sin_prueba_de_identidad_ni_credenciales_de_dominio() {
    let session = local::new_session().unwrap();
    let endpoint = local::Endpoint::bind_named(&session).unwrap();
    let server = async {
        let mut stream = endpoint.accept().await.unwrap();
        assert!(matches!(
            receive_invitation(&mut stream, resource()).await.unwrap(),
            Incoming::Activation
        ));
        confirm_activation(&mut stream).await.unwrap();
    };
    let consumer = async {
        activate(&session, std::process::id()).await.unwrap();
    };
    tokio::join!(server, consumer);
}
fn resource() -> ResourceKey {
    ResourceKey {
        app_id: "nb.test".to_owned().try_into().unwrap(),
        installation_id: "fixture".to_owned().try_into().unwrap(),
        capability_id: "counter".to_owned().try_into().unwrap(),
        major_version: std::num::NonZeroU16::MIN,
        resource_id: "primary".to_owned().try_into().unwrap(),
    }
}

#[tokio::test]
async fn la_prueba_verifica_el_peer_y_solo_el_propietario_entrega_el_control_privado() {
    let session = local::new_session().unwrap();
    let endpoint = local::Endpoint::bind_named(&session).unwrap();
    let port = local::new_session().unwrap();
    let credential = local::new_credential().unwrap();
    let client = ClientIdentity::open(&Fixture, false).unwrap();
    let expected_public = client.public();
    let expected_port = port.clone();
    let expected_credential = credential.clone();
    let server = async {
        let mut stream = endpoint.accept().await.unwrap();
        let verified = authenticate(&mut stream, resource()).await.unwrap();
        assert_eq!(verified.public(), &expected_public);
        assert_eq!(verified.participants().client_pid(), std::process::id());
        assert_eq!(verified.participants().owner_pid(), std::process::id());
        accept(
            &mut stream,
            &verified,
            Bootstrap {
                session: port,
                credential,
            },
        )
        .await
        .unwrap();
        assert!(matches!(
            read_frame(&mut stream).await.unwrap(),
            Some(crate::port::Control::Renew)
        ));
        assert!(
            read_frame::<_, crate::port::Control>(&mut stream)
                .await
                .unwrap()
                .is_none()
        );
    };
    let consumer = async {
        let mut accepted = connect(
            &session,
            std::process::id(),
            &resource(),
            client.public(),
            Access::ALL,
            |challenge, participants| {
                client.prove(challenge, &resource(), Access::ALL, participants)
            },
        )
        .await
        .unwrap();
        assert_eq!(accepted.bootstrap.session, expected_port);
        assert_eq!(
            accepted.bootstrap.credential.expose_secret(),
            expected_credential.expose_secret()
        );
        write_frame(&mut accepted.control, &crate::port::Control::Renew)
            .await
            .unwrap();
        drop(accepted);
    };
    tokio::join!(server, consumer);
}

#[tokio::test]
async fn una_identidad_valida_sin_concesion_no_obtiene_credenciales() {
    let session = local::new_session().unwrap();
    let endpoint = local::Endpoint::bind_named(&session).unwrap();
    let client = ClientIdentity::open(&Fixture, false).unwrap();
    let server = async {
        let mut stream = endpoint.accept().await.unwrap();
        authenticate(&mut stream, resource()).await.unwrap();
        reject(&mut stream, Denial::Revoked).await.unwrap();
    };
    let consumer = async {
        let result = connect(
            &session,
            std::process::id(),
            &resource(),
            client.public(),
            Access::ALL,
            |challenge, participants| {
                client.prove(challenge, &resource(), Access::ALL, participants)
            },
        )
        .await;
        assert!(matches!(result, Err(ChannelError::Denied(Denial::Revoked))));
    };
    tokio::join!(server, consumer);
}

#[tokio::test]
async fn ni_otro_propietario_ni_un_recurso_ampliado_reciben_una_firma() {
    let session = local::new_session().unwrap();
    let endpoint = local::Endpoint::bind_named(&session).unwrap();
    let client = ClientIdentity::open(&Fixture, false).unwrap();
    let signed = Arc::new(AtomicBool::new(false));
    let result = connect(
        &session,
        std::process::id() + 1,
        &resource(),
        client.public(),
        Access::ALL,
        |_, _| {
            signed.store(true, Ordering::SeqCst);
            unreachable!()
        },
    )
    .await;
    assert!(matches!(result, Err(ChannelError::Local(_))));
    assert!(!signed.load(Ordering::SeqCst));
    drop(endpoint);

    let session = local::new_session().unwrap();
    let endpoint = local::Endpoint::bind_named(&session).unwrap();
    let server = async {
        let mut stream = endpoint.accept().await.unwrap();
        let mut other = resource();
        other.installation_id = "other".to_owned().try_into().unwrap();
        assert!(authenticate(&mut stream, other).await.is_err());
    };
    let consumer = async {
        let result = connect(
            &session,
            std::process::id(),
            &resource(),
            client.public(),
            Access::ALL,
            |_, _| {
                signed.store(true, Ordering::SeqCst);
                unreachable!()
            },
        )
        .await;
        assert!(matches!(result, Err(ChannelError::Protocol)));
        assert!(!signed.load(Ordering::SeqCst));
    };
    tokio::join!(server, consumer);
}

#[tokio::test]
async fn protocolo_o_campos_desconocidos_no_generan_un_desafio() {
    for extra in [false, true] {
        let session = local::new_session().unwrap();
        let endpoint = local::Endpoint::bind_named(&session).unwrap();
        let server = async {
            let mut stream = endpoint.accept().await.unwrap();
            assert!(authenticate(&mut stream, resource()).await.is_err());
        };
        let consumer = async {
            let mut stream =
                local::connect_endpoint(&local::path_for(&session).unwrap(), std::process::id())
                    .await
                    .unwrap();
            let mut hello = serde_json::to_value(Invitation::Attach {
                version: if extra { 1 } else { 2 },
                client: ClientIdentity::open(&Fixture, false).unwrap().public(),
                access: Access::ALL,
            })
            .unwrap();
            if extra {
                hello["unknown"] = serde_json::json!(true);
            }
            write_frame(&mut stream, &hello).await.unwrap();
            assert!(
                read_frame::<_, Message>(&mut stream)
                    .await
                    .unwrap()
                    .is_none()
            );
        };
        tokio::join!(server, consumer);
    }
}
