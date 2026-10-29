//! Runtime de NB Sound.
//!
//! Contratos: docs/adr/README.md. Cada servicio vive en su módulo, y los comandos
//! del puente están en [`comandos`]: ninguno es síncrono, porque en Tauri un
//! comando sin `async` corre en el hilo de la ventana y la congela mientras dura
//! (lo vigila `scripts/check-comandos.mjs`).

pub mod comandos;
pub mod error;
pub mod net;
pub mod paths;
pub mod security;
pub mod telemetry;

use crate::net::{PoliticaDeRed, Red};
use crate::paths::Rutas;

/// Estado compartido del runtime.
pub struct Estado {
    pub rutas: Rutas,
    pub red: Red,
}

/// Arranca la aplicación.
///
/// # Panics
///
/// Si el sistema no ofrece un directorio de datos donde escribir: sin él no hay
/// biblioteca que abrir, y seguir sería peor que detenerse con un mensaje.
pub fn run() {
    let rutas = Rutas::resolver().expect("el sistema no ofrece un directorio de datos utilizable");
    let _registro = telemetry::init(&rutas.registros);
    tracing::info!(version = env!("CARGO_PKG_VERSION"), "arranca NB Sound");

    let estado = Estado {
        rutas,
        // La política de red real vive en la base a partir de F1; hasta entonces,
        // la de fábrica, que no deja salir nada.
        red: Red::new(PoliticaDeRed::default()),
    };

    tauri::Builder::default()
        .manage(estado)
        .invoke_handler(tauri::generate_handler![comandos::salud])
        .run(tauri::generate_context!())
        .expect("no se pudo arrancar la ventana de NB Sound");
}
