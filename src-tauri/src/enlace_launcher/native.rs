use super::*;
use crate::autorizacion_launcher::{Concesion, Pendiente, Solicitud};
use nb_capability::{
    attachment::channel::{self, Denial, Incoming},
    port::{self, Bootstrap, Session},
};
use nb_protocol::{
    capability::{Epoch, Identifier, ResourceKey},
    frame::read_frame,
    local::{self, rendezvous},
};
use sha2::{Digest, Sha256};
use std::{os::unix::ffi::OsStrExt, time::Duration};
use tauri::Manager;
use tokio::{
    task::JoinSet,
    time::{sleep, timeout, Instant},
};

fn app_id() -> NsResult<Identifier> {
    "nb.sound"
        .to_owned()
        .try_into()
        .map_err(|_| NsError::Internal)
}
fn profile(rutas: &Rutas) -> NsResult<Identifier> {
    let path = rutas
        .datos
        .canonicalize()
        .map_err(|_| NsError::StorageFailure)?;
    format!("{:x}", Sha256::digest(path.as_os_str().as_bytes()))
        .try_into()
        .map_err(|_| NsError::Internal)
}
fn default_profile() -> NsResult<Identifier> {
    "default"
        .to_owned()
        .try_into()
        .map_err(|_| NsError::Internal)
}
fn focus(app: &tauri::AppHandle) {
    let handle = app.clone();
    let _ = app.run_on_main_thread(move || {
        if let Some(window) = handle.get_webview_window("main") {
            let _ = window.unminimize();
            let _ = window.show();
            let _ = window.set_focus();
        }
    });
}
pub(super) fn activate(rutas: &Rutas) {
    let Ok(runtime) = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
    else {
        return;
    };
    let (Ok(app), Ok(profile)) = (app_id(), profile(rutas)) else {
        return;
    };
    runtime.block_on(async {
        let _ = timeout(Duration::from_secs(8), async {
            loop {
                if let Ok(Some(ad)) = rendezvous::discover(&app, &profile) {
                    if channel::activate(ad.invitation(), ad.pid()).await.is_ok() {
                        return;
                    }
                }
                sleep(Duration::from_millis(100)).await;
            }
        })
        .await;
    });
}

struct PendingGuard {
    service: Arc<Servicio>,
    app: tauri::AppHandle,
    id: String,
}
impl Drop for PendingGuard {
    fn drop(&mut self) {
        if let Ok(mut slot) = self.service.pending.lock() {
            if slot
                .as_ref()
                .is_some_and(|pending| pending.info.id == self.id)
            {
                *slot = None;
            }
        }
        notificar(&self.app);
    }
}
async fn consent(
    service: &Arc<Servicio>,
    app: &tauri::AppHandle,
    store: Arc<Almacen>,
    pending: Pendiente,
    stream: &mut local::Stream,
) -> Result<Concesion, Denial> {
    if !pending.vigente() {
        return Err(Denial::Expired);
    }
    let id = String::from(local::new_session().map_err(|_| Denial::Unavailable)?);
    let info = SolicitudLauncher {
        id: id.clone(),
        cambiar: pending.permisos().allows_change(),
        observar: pending.permisos().allows_observe(),
    };
    let (answer, receiver) = oneshot::channel();
    {
        let mut slot = service.pending.lock().map_err(|_| Denial::Unavailable)?;
        if slot.is_some() {
            return Err(Denial::Busy);
        }
        *slot = Some(Pending { info, answer });
    }
    let _guard = PendingGuard {
        service: Arc::clone(service),
        app: app.clone(),
        id,
    };
    notificar(app);
    focus(app);
    let resolution = tokio::select! {
        result = receiver => result.map_err(|_| Denial::Rejected)?,
        () = sleep(Duration::from_secs(45)) => return Err(Denial::Expired),
        _ = read_frame::<_, port::Control>(stream) => return Err(Denial::Rejected),
    };
    match resolution {
        Resolution::Reject => Err(Denial::Rejected),
        Resolution::Revoked => Err(Denial::Revoked),
        Resolution::Allow(ack) => {
            let result = match tokio::task::spawn_blocking(move || store.aceptar(pending)).await {
                Ok(result) => result,
                Err(_) => {
                    let _ = ack.send(Err(NsError::Internal));
                    return Err(Denial::Unavailable);
                }
            };
            match result {
                Ok(Some(lease)) => {
                    let _ = ack.send(Ok(()));
                    notificar(app);
                    Ok(lease)
                }
                Ok(None) => {
                    let _ = ack.send(Err(NsError::Cancelled));
                    Err(Denial::Revoked)
                }
                Err(NsError::ConsentRequired) => {
                    let _ = ack.send(Err(NsError::Cancelled));
                    Err(Denial::Expired)
                }
                Err(error) => {
                    let _ = ack.send(Err(error));
                    Err(Denial::Unavailable)
                }
            }
        }
    }
}

async fn connection(
    service: Arc<Servicio>,
    app: tauri::AppHandle,
    resource: RecursoFrecuencia,
    key: ResourceKey,
    mut stream: local::Stream,
) {
    let client = match channel::receive_invitation(&mut stream, key).await {
        Ok(Incoming::Activation) => {
            focus(&app);
            let _ = channel::confirm_activation(&mut stream).await;
            return;
        }
        Ok(Incoming::Verified(client)) => client,
        Err(_) => return,
    };
    let Some(store) = service.store.get().cloned() else {
        return;
    };
    let owner = Arc::clone(&store);
    let lease = match tokio::task::spawn_blocking(move || owner.solicitar(client)).await {
        Ok(Ok(Solicitud::Autorizada(lease))) => Ok(lease),
        Ok(Ok(Solicitud::Consentimiento(pending))) => {
            consent(&service, &app, store, pending, &mut stream).await
        }
        Ok(Ok(Solicitud::Revocada)) => Err(Denial::Revoked),
        _ => Err(Denial::Unavailable),
    };
    let lease = match lease {
        Ok(lease) => lease,
        Err(reason) => {
            let _ = channel::reject(&mut stream, reason).await;
            return;
        }
    };
    let Ok(session) = local::new_session() else {
        return;
    };
    let Ok(credential) = local::new_credential() else {
        return;
    };
    let server = Session::bind_authorized(
        resource,
        Bootstrap {
            session: session.clone(),
            credential: credential.clone(),
        },
        &lease.client,
        lease.revoked,
    );
    let Ok(server) = server else {
        let _ = channel::reject(&mut stream, Denial::Revoked).await;
        return;
    };
    if channel::accept(
        &mut stream,
        &lease.client,
        Bootstrap {
            session,
            credential,
        },
    )
    .await
    .is_err()
    {
        return;
    }
    let _ = server.serve(stream).await;
}

pub(super) fn run(
    service: Arc<Servicio>,
    app: tauri::AppHandle,
    rutas: Rutas,
    resource: RecursoFrecuencia,
) -> NsResult<()> {
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .map_err(|_| NsError::ComponentUnavailable)?;
    runtime.block_on(async {
        let key = resource.read().map_err(|_| NsError::ComponentUnavailable)?.key.clone();
        if service.store.get().is_none() { return Err(NsError::ComponentUnavailable); }
        let app_id = app_id()?;
        let mut claim = rendezvous::claim(&app_id, &profile(&rutas)?).map_err(|_| NsError::ComponentUnavailable)?;
        let invitation: Epoch = local::new_session().map_err(|_| NsError::ComponentUnavailable)?;
        let endpoint = local::Endpoint::bind_named(&invitation).map_err(|_| NsError::ComponentUnavailable)?;
        let ad = rendezvous::Advertisement::new(invitation, key.clone());
        claim.publish(&ad).map_err(|_| NsError::StorageFailure)?;
        let mut default_claim = if std::env::var_os(crate::paths::TEST_DIR_ENV).is_none() {
            rendezvous::claim(&app_id, &default_profile()?).ok()
        } else { None };
        if let Some(alias) = &mut default_claim { alias.publish(&ad).map_err(|_| NsError::StorageFailure)?; }
        service.available.store(true, Ordering::Release);
        notificar(&app);
        let mut shutdown = service.shutdown.subscribe();
        let mut tasks = JoinSet::new();
        let mut next_admission = Instant::now();
        loop {
            if *shutdown.borrow_and_update() { break; }
            tokio::select! {
                _ = shutdown.changed() => break,
                accepted = async { sleep(next_admission.saturating_duration_since(Instant::now())).await; endpoint.accept().await }, if tasks.len() < local::MAX_SESSIONS => {
                    let stream = accepted.map_err(|_| NsError::ComponentUnavailable)?;
                    next_admission = Instant::now() + Duration::from_millis(250);
                    tasks.spawn(connection(Arc::clone(&service), app.clone(), resource.clone(), key.clone(), stream));
                },
                Some(_) = tasks.join_next(), if !tasks.is_empty() => {},
            }
        }
        tasks.abort_all();
        while tasks.join_next().await.is_some() {}
        drop(default_claim);
        drop(claim);
        Ok(())
    })
}
