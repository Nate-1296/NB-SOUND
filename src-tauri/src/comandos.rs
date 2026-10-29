//! Los comandos del puente.
//!
//! Todos son `async` y devuelven [`NsResult`]: ni corren en el hilo de la ventana
//! ni devuelven cadenas como error.

use serde::Serialize;
use ts_rs::TS;

use crate::error::NsResult;

/// Lo que responde el runtime cuando se le pregunta si está vivo.
#[derive(Debug, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct InformeDeSalud {
    pub version: String,
}

#[tauri::command]
pub async fn salud() -> NsResult<InformeDeSalud> {
    Ok(InformeDeSalud {
        version: env!("CARGO_PKG_VERSION").to_owned(),
    })
}
