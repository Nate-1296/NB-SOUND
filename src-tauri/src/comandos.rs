//! Los comandos del puente.
//!
//! Todos son `async` y devuelven [`NsResult`]: ni corren en el hilo de la ventana
//! ni devuelven cadenas como error.

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};
use ts_rs::TS;

use crate::biblioteca::{self, PistaResumen};
use crate::cola::Repeticion;
use crate::error::{NsError, NsResult};
use crate::reproductor::{Instantanea, Orden, Reproductor};
use crate::Estado;

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

// --- Reproductor ---------------------------------------------------------------

/// Una orden al reproductor, tal como la manda la interfaz.
#[derive(Debug, Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(
    tag = "tipo",
    rename_all = "camelCase",
    rename_all_fields = "camelCase"
)]
pub enum OrdenReproductor {
    ReproducirPistas {
        #[ts(type = "number[]")]
        ids: Vec<i64>,
        desde: u32,
    },
    ReproducirPista {
        #[ts(type = "number")]
        id: i64,
    },
    ReproducirIndice {
        indice: u32,
    },
    PausarReanudar,
    Siguiente,
    Anterior,
    Buscar {
        segundos: f64,
    },
    Volumen {
        valor: f32,
    },
    Aleatorio {
        activo: bool,
    },
    /// `ninguno`, `todo` o `uno`.
    Repeticion {
        modo: String,
    },
    Agregar {
        #[ts(type = "number[]")]
        ids: Vec<i64>,
        justo_despues: bool,
    },
    Quitar {
        indice: u32,
    },
    Mover {
        desde: u32,
        hasta: u32,
    },
    Vaciar {
        salvo_la_actual: bool,
    },
    Normalizar {
        activo: bool,
    },
    Karaoke {
        activo: bool,
    },
}

impl OrdenReproductor {
    fn traducir(self) -> NsResult<Orden> {
        Ok(match self {
            Self::ReproducirPistas { ids, desde } => Orden::ReproducirPistas {
                ids,
                desde: desde as usize,
            },
            Self::ReproducirPista { id } => Orden::ReproducirPista(id),
            Self::ReproducirIndice { indice } => Orden::ReproducirIndice(indice as usize),
            Self::PausarReanudar => Orden::PausarReanudar,
            Self::Siguiente => Orden::Siguiente,
            Self::Anterior => Orden::Anterior,
            Self::Buscar { segundos } if segundos.is_finite() => Orden::Buscar(segundos),
            Self::Volumen { valor } if valor.is_finite() => Orden::Volumen(valor),
            Self::Aleatorio { activo } => Orden::Aleatorio(activo),
            Self::Repeticion { modo } => {
                Orden::Repeticion(Repeticion::desde_v1(&modo).ok_or(NsError::PathNotAllowed)?)
            }
            Self::Agregar { ids, justo_despues } => Orden::Agregar { ids, justo_despues },
            Self::Quitar { indice } => Orden::Quitar(indice as usize),
            Self::Mover { desde, hasta } => Orden::Mover {
                desde: desde as usize,
                hasta: hasta as usize,
            },
            Self::Vaciar { salvo_la_actual } => Orden::Vaciar { salvo_la_actual },
            Self::Normalizar { activo } => Orden::Normalizar(activo),
            Self::Karaoke { activo } => Orden::Karaoke(activo),
            // Un número que no es un número no llega al motor.
            Self::Buscar { .. } | Self::Volumen { .. } => return Err(NsError::PathNotAllowed),
        })
    }
}

fn reproductor(app: &AppHandle) -> NsResult<tauri::State<'_, Reproductor>> {
    app.try_state::<Reproductor>()
        .ok_or(NsError::ComponentUnavailable)
}

/// Lo que suena y la cola. `None` mientras el reproductor arranca.
#[tauri::command]
pub async fn reproductor_estado(app: AppHandle) -> NsResult<Option<Instantanea>> {
    Ok(reproductor(&app)?.instantanea())
}

/// Manda una orden; el resultado llega como evento `reproductor:instantanea`.
#[tauri::command]
pub async fn reproductor_orden(app: AppHandle, orden: OrdenReproductor) -> NsResult<()> {
    reproductor(&app)?.enviar(orden.traducir()?);
    Ok(())
}

/// Cota: `biblioteca::MAX_RESUMENES` pistas por petición; la interfaz pide por tramos.
#[tauri::command]
pub async fn pistas_resumen(
    estado: tauri::State<'_, Estado>,
    ids: Vec<i64>,
) -> NsResult<Vec<PistaResumen>> {
    let db = estado.db.clone();
    tauri::async_runtime::spawn_blocking(move || biblioteca::resumenes(&db, &ids))
        .await
        .map_err(|_| NsError::Internal)?
}
