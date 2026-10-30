//! El icono de la bandeja del sistema (F2.1.6): reproducir o pausar, anterior,
//! siguiente, volver a la ventana y salir, sin tener que buscarla.
//!
//! Cerrar la ventana sigue cerrando la aplicación, como en la V1: la bandeja es un
//! atajo, no un sitio donde la música se queda sonando sin ventana.

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Manager};

use crate::reproductor::{Buzon, Orden};

/// Pone el icono. Si el escritorio no tiene bandeja, no pasa nada.
pub fn poner(app: &AppHandle, buzon: Buzon) {
    let resultado = (|| -> tauri::Result<()> {
        let menu = Menu::with_items(
            app,
            &[
                &MenuItem::with_id(app, "pausar", "Reproducir o pausar", true, None::<&str>)?,
                &MenuItem::with_id(app, "anterior", "Anterior", true, None::<&str>)?,
                &MenuItem::with_id(app, "siguiente", "Siguiente", true, None::<&str>)?,
                &PredefinedMenuItem::separator(app)?,
                &MenuItem::with_id(app, "mostrar", "Mostrar NB Sound", true, None::<&str>)?,
                &MenuItem::with_id(app, "salir", "Salir", true, None::<&str>)?,
            ],
        )?;
        let mut constructor = TrayIconBuilder::with_id("nb-sound")
            .tooltip("NB Sound")
            .menu(&menu)
            .on_menu_event(move |app, evento| match evento.id().as_ref() {
                "pausar" => buzon.enviar(Orden::PausarReanudar),
                "anterior" => buzon.enviar(Orden::Anterior),
                "siguiente" => buzon.enviar(Orden::Siguiente),
                "mostrar" => {
                    if let Some(v) = app.get_webview_window("main") {
                        let _ = v.unminimize();
                        let _ = v.show();
                        let _ = v.set_focus();
                    }
                }
                "salir" => app.exit(0),
                _ => {}
            });
        if let Some(icono) = app.default_window_icon() {
            constructor = constructor.icon(icono.clone());
        }
        constructor.build(app)?;
        Ok(())
    })();
    if let Err(error) = resultado {
        tracing::info!(error = %error, "sin icono en la bandeja");
    }
}
