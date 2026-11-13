//! ADR-017: consentimiento y ciclo de vida del enlace, propiedad de Sound.
use crate::{
    autorizacion_launcher::{self, Almacen},
    error::{NsError, NsResult},
    frecuencia_compartida::RecursoFrecuencia,
    paths::Rutas,
};
use serde::Serialize;
#[cfg(target_os = "linux")]
use std::fs::File;
use std::{
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex, OnceLock,
    },
    thread::JoinHandle,
};
use tokio::sync::{oneshot, watch};
use ts_rs::TS;

#[cfg(target_os = "linux")]
mod native;

#[derive(Clone, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct SolicitudLauncher {
    pub id: String,
    pub cambiar: bool,
    pub observar: bool,
}
#[derive(Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct EstadoEnlaceLauncher {
    pub disponible: bool,
    pub pendiente: Option<SolicitudLauncher>,
    pub recordadas: Option<u32>,
    pub revocadas: Option<u32>,
}
enum Resolution {
    #[cfg(target_os = "linux")]
    Allow(oneshot::Sender<NsResult<()>>),
    #[cfg(target_os = "linux")]
    Reject,
    Revoked,
}
struct Pending {
    info: SolicitudLauncher,
    answer: oneshot::Sender<Resolution>,
}

pub struct Servicio {
    pending: Mutex<Option<Pending>>,
    store: OnceLock<Arc<Almacen>>,
    available: AtomicBool,
    shutdown: watch::Sender<bool>,
    thread: Mutex<Option<JoinHandle<()>>>,
}
impl Servicio {
    pub fn nuevo() -> Arc<Self> {
        let (shutdown, _) = watch::channel(false);
        Arc::new(Self {
            pending: Mutex::new(None),
            store: OnceLock::new(),
            available: AtomicBool::new(false),
            shutdown,
            thread: Mutex::new(None),
        })
    }
    pub fn iniciar(
        self: &Arc<Self>,
        app: tauri::AppHandle,
        rutas: Rutas,
        resource: RecursoFrecuencia,
    ) {
        #[cfg(target_os = "linux")]
        {
            let service = Arc::clone(self);
            let thread = std::thread::Builder::new()
                .name("launcher-local".into())
                .spawn(move || {
                    if let Err(error) =
                        native::run(Arc::clone(&service), app.clone(), rutas, resource)
                    {
                        tracing::warn!(
                            codigo = error.code(),
                            "el enlace local de Launcher no está disponible"
                        );
                    }
                    service.available.store(false, Ordering::Release);
                    service.cancel_pending(Resolution::Reject);
                    notificar(&app);
                });
            if let Ok(thread) = thread {
                if let Ok(mut slot) = self.thread.lock() {
                    *slot = Some(thread);
                }
            }
        }
        #[cfg(not(target_os = "linux"))]
        let _ = (app, rutas, resource);
    }
    /// Prepara política antes del puerto heredado; un error de política nunca lo habilita.
    pub fn preparar(&self, rutas: &Rutas, resource: &RecursoFrecuencia) -> NsResult<()> {
        #[cfg(target_os = "linux")]
        {
            let key = resource
                .read()
                .map_err(|_| NsError::ComponentUnavailable)?
                .key
                .clone();
            self.store
                .set(Arc::new(Almacen::abrir(
                    &rutas.datos.join("autorizaciones-launcher.sqlite3"),
                    key,
                )?))
                .map_err(|_| NsError::Internal)?;
        }
        #[cfg(not(target_os = "linux"))]
        let _ = (rutas, resource);
        Ok(())
    }
    pub fn bloqueo_heredado(&self) -> NsResult<Option<watch::Receiver<bool>>> {
        #[cfg(target_os = "linux")]
        {
            self.store
                .get()
                .map(|store| Some(store.bloqueo_heredado()))
                .ok_or(NsError::ComponentUnavailable)
        }
        #[cfg(not(target_os = "linux"))]
        {
            Ok(None)
        }
    }
    fn cancel_pending(&self, resolution: Resolution) {
        if let Ok(mut slot) = self.pending.lock() {
            if let Some(pending) = slot.take() {
                let _ = pending.answer.send(resolution);
            }
        }
    }
    pub fn estado(&self) -> NsResult<EstadoEnlaceLauncher> {
        let counts = self.store.get().map(|store| store.resumen()).transpose()?;
        Ok(EstadoEnlaceLauncher {
            disponible: self.available.load(Ordering::Acquire),
            pendiente: self
                .pending
                .lock()
                .map_err(|_| NsError::Internal)?
                .as_ref()
                .map(|pending| pending.info.clone()),
            recordadas: counts.map(|(recordadas, _)| recordadas),
            revocadas: counts.map(|(_, revocadas)| revocadas),
        })
    }
    #[cfg(target_os = "linux")]
    pub async fn responder(&self, id: &str, accept: bool) -> NsResult<()> {
        let pending = {
            let mut slot = self.pending.lock().map_err(|_| NsError::Internal)?;
            if slot.as_ref().is_none_or(|pending| pending.info.id != id) {
                return Err(NsError::Cancelled);
            }
            slot.take().ok_or(NsError::Cancelled)?
        };
        if !accept {
            return pending
                .answer
                .send(Resolution::Reject)
                .map_err(|_| NsError::Cancelled);
        }
        let (ack, received) = oneshot::channel();
        pending
            .answer
            .send(Resolution::Allow(ack))
            .map_err(|_| NsError::Cancelled)?;
        tokio::time::timeout(std::time::Duration::from_secs(60), received)
            .await
            .map_err(|_| NsError::Cancelled)?
            .map_err(|_| NsError::Cancelled)?
    }
    #[cfg(not(target_os = "linux"))]
    pub async fn responder(&self, _: &str, _: bool) -> NsResult<()> {
        Err(NsError::ComponentUnavailable)
    }
    pub fn revocar(&self) -> NsResult<()> {
        self.store
            .get()
            .ok_or(NsError::ComponentUnavailable)?
            .revocar_todas()?;
        self.cancel_pending(Resolution::Revoked);
        Ok(())
    }
    pub fn permitir_solicitudes(&self) -> NsResult<()> {
        self.store
            .get()
            .ok_or(NsError::ComponentUnavailable)?
            .permitir_nuevas_solicitudes()
    }
    pub fn detener(&self) {
        self.shutdown.send_replace(true);
    }
    pub fn unir(&self) {
        self.detener();
        if let Ok(mut slot) = self.thread.lock() {
            if let Some(thread) = slot.take() {
                let _ = thread.join();
            }
        }
    }
}

pub fn notificar(app: &tauri::AppHandle) {
    use tauri::Emitter;
    let _ = app.emit("launcher:cambio", ());
}

/// En Linux se adquiere antes de abrir la biblioteca y no depende del anuncio.
/// Otras plataformas conservan el arranque anterior hasta tener activación nativa.
pub struct Instancia {
    #[cfg(target_os = "linux")]
    _lock: File,
}
#[cfg(target_os = "linux")]
pub fn adquirir_instancia(rutas: &Rutas) -> NsResult<Option<Instancia>> {
    let lock = autorizacion_launcher::private_file(&rutas.datos.join("instance.lock"))?;
    match lock.try_lock() {
        Ok(()) => Ok(Some(Instancia { _lock: lock })),
        Err(std::fs::TryLockError::WouldBlock) => Ok(None),
        Err(_) => Err(NsError::StorageFailure),
    }
}
#[cfg(not(target_os = "linux"))]
pub fn adquirir_instancia(_: &Rutas) -> NsResult<Option<Instancia>> {
    Ok(Some(Instancia {}))
}
pub fn activar_instancia(rutas: &Rutas) {
    #[cfg(target_os = "linux")]
    native::activate(rutas);
    #[cfg(not(target_os = "linux"))]
    let _ = rutas;
}

#[cfg(all(test, not(target_os = "linux")))]
mod pruebas_arranque {
    use super::*;

    #[test]
    fn plataformas_sin_activacion_conservan_el_arranque_anterior() {
        let base = std::env::temp_dir().join(format!(
            "ns-no-instance-{}",
            String::from(nb_protocol::local::new_session().unwrap())
        ));
        let rutas = Rutas {
            datos: base.join("datos"),
            cache: base.join("cache"),
            registros: base.join("registros"),
        };
        let _primera = adquirir_instancia(&rutas).unwrap().unwrap();
        let _segunda = adquirir_instancia(&rutas).unwrap().unwrap();
        assert!(!base.exists());
    }

    #[tokio::test]
    async fn plataformas_sin_adhesion_no_aceptan_respuestas_de_consentimiento() {
        let servicio = Servicio::nuevo();
        assert!(matches!(
            servicio.responder("sin-solicitud", true).await,
            Err(NsError::ComponentUnavailable)
        ));
    }
}
