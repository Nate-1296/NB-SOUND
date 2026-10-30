//! SMTC en Windows y el centro de reproducción de macOS, con `souvlaki`.
//!
//! Los controles se crean en el hilo principal, que es donde las dos plataformas
//! los quieren, y viven en una variable de ese hilo; las actualizaciones llegan
//! con `run_on_main_thread`. Aleatorio y repetición no los expone `souvlaki`: en
//! estas plataformas solo van de la aplicación al sistema por los botones de
//! siempre (F2.1.5 pide decir lo que no se puede comprobar).

use std::cell::RefCell;
use std::time::Duration;

use souvlaki::{
    MediaControlEvent, MediaControls, MediaMetadata, MediaPlayback, MediaPosition, PlatformConfig,
    SeekDirection,
};
use tauri::{AppHandle, Manager};

use super::{metadatos, Metadatos};
use crate::db::BaseDeDatos;
use crate::paths::Rutas;
use crate::reproductor::{Buzon, Instantanea, Orden};

thread_local! {
    static CONTROLES: RefCell<Option<(MediaControls, Option<i64>)>> = const { RefCell::new(None) };
}

pub struct Controles {
    app: AppHandle,
    db: BaseDeDatos,
    rutas: Rutas,
    /// La última posición conocida, para los saltos relativos del sistema.
    posicion: std::sync::Arc<std::sync::Mutex<f64>>,
}

impl Controles {
    pub fn arrancar(app: &AppHandle, db: BaseDeDatos, rutas: Rutas, buzon: Buzon) -> Option<Self> {
        #[cfg(target_os = "windows")]
        let hwnd = {
            let ventana = app.get_webview_window("main")?;
            Some(ventana.hwnd().ok()?.0 as *mut std::ffi::c_void)
        };
        #[cfg(not(target_os = "windows"))]
        let hwnd = None;

        let config = PlatformConfig {
            display_name: "NB Sound",
            dbus_name: "nbsound",
            hwnd,
        };
        let mut controles = MediaControls::new(config).ok()?;
        let posicion = std::sync::Arc::new(std::sync::Mutex::new(0.0f64));
        let pos = std::sync::Arc::clone(&posicion);
        controles
            .attach(move |e| match e {
                MediaControlEvent::Play | MediaControlEvent::Pause | MediaControlEvent::Toggle => {
                    buzon.enviar(Orden::PausarReanudar);
                }
                MediaControlEvent::Next => buzon.enviar(Orden::Siguiente),
                MediaControlEvent::Previous => buzon.enviar(Orden::Anterior),
                MediaControlEvent::SetPosition(MediaPosition(d)) => {
                    buzon.enviar(Orden::Buscar(d.as_secs_f64()));
                }
                MediaControlEvent::SeekBy(dir, d) => {
                    let actual = pos.lock().map_or(0.0, |p| *p);
                    let paso = match dir {
                        SeekDirection::Forward => d.as_secs_f64(),
                        SeekDirection::Backward => -d.as_secs_f64(),
                    };
                    buzon.enviar(Orden::Buscar(actual + paso));
                }
                MediaControlEvent::SetVolume(v) => buzon.enviar(Orden::Volumen(v as f32)),
                MediaControlEvent::SetShuffle(a) => buzon.enviar(Orden::Aleatorio(a)),
                _ => {}
            })
            .ok()?;
        CONTROLES.with(|c| *c.borrow_mut() = Some((controles, None)));
        Some(Self {
            app: app.clone(),
            db,
            rutas,
            posicion,
        })
    }

    pub fn actualizar(&self, i: &Instantanea) {
        if let Ok(mut p) = self.posicion.lock() {
            *p = i.posicion_seg;
        }
        // Los datos de la pista se resuelven aquí, fuera del hilo principal.
        let datos: Option<Metadatos> = i
            .pista_id
            .and_then(|id| metadatos(&self.db, &self.rutas, id));
        let i = i.clone();
        let _ = self.app.run_on_main_thread(move || {
            CONTROLES.with(|c| {
                let mut c = c.borrow_mut();
                let Some((controles, pista)) = c.as_mut() else {
                    return;
                };
                if *pista != i.pista_id {
                    *pista = i.pista_id;
                    let portada = datos
                        .as_ref()
                        .and_then(|m| m.portada.as_ref())
                        .map(|p| format!("file://{}", p.display()));
                    let m = datos.as_ref();
                    let _ = controles.set_metadata(MediaMetadata {
                        title: m.map(|m| m.titulo.as_str()),
                        artist: m.map(|m| m.artista.as_str()),
                        album: m.map(|m| m.album.as_str()),
                        cover_url: portada.as_deref(),
                        duration: m.map(|m| Duration::from_secs_f64(m.duracion_seg.max(0.0))),
                    });
                }
                let progreso = Some(MediaPosition(Duration::from_secs_f64(
                    i.posicion_seg.max(0.0),
                )));
                let _ = controles.set_playback(match i.estado.as_str() {
                    "reproduciendo" => MediaPlayback::Playing { progress: progreso },
                    "pausado" => MediaPlayback::Paused { progress: progreso },
                    _ => MediaPlayback::Stopped,
                });
            });
        });
    }
}
