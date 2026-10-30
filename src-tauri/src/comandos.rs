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
use crate::playlists;
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
    Ecualizador {
        ajustes: crate::reproductor::AjustesEcualizador,
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
            Self::Ecualizador { ajustes } => Orden::Ecualizador(ajustes),
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

// --- Biblioteca ------------------------------------------------------------------

/// Ejecuta una consulta de solo lectura fuera del hilo de la ventana.
async fn en_segundo_plano<T: Send + 'static>(
    estado: &tauri::State<'_, Estado>,
    trabajo: impl FnOnce(&crate::db::BaseDeDatos) -> NsResult<T> + Send + 'static,
) -> NsResult<T> {
    let db = estado.db.clone();
    tauri::async_runtime::spawn_blocking(move || trabajo(&db))
        .await
        .map_err(|_| NsError::Internal)?
}

#[tauri::command]
pub async fn biblioteca_pistas(
    estado: tauri::State<'_, Estado>,
    consulta: biblioteca::ConsultaPistas,
    desde: u32,
    limite: u32,
) -> NsResult<biblioteca::PaginaPistas> {
    en_segundo_plano(&estado, move |db| {
        biblioteca::pistas(db, &consulta, desde, limite)
    })
    .await
}

#[tauri::command]
pub async fn biblioteca_albumes(
    estado: tauri::State<'_, Estado>,
    consulta: biblioteca::ConsultaAlbumes,
    desde: u32,
    limite: u32,
) -> NsResult<biblioteca::PaginaAlbumes> {
    en_segundo_plano(&estado, move |db| {
        biblioteca::albumes(db, &consulta, desde, limite)
    })
    .await
}

#[tauri::command]
pub async fn biblioteca_artistas(
    estado: tauri::State<'_, Estado>,
    consulta: biblioteca::ConsultaArtistas,
    desde: u32,
    limite: u32,
) -> NsResult<biblioteca::PaginaArtistas> {
    en_segundo_plano(&estado, move |db| {
        biblioteca::artistas(db, &consulta, desde, limite)
    })
    .await
}

/// Reproduce una lista desde la canción elegida: la cola es la lista, recortada a
/// su alrededor si es enorme.
#[tauri::command]
pub async fn reproducir_lista(
    app: AppHandle,
    estado: tauri::State<'_, Estado>,
    consulta: biblioteca::ConsultaPistas,
    indice: u32,
) -> NsResult<()> {
    let (ids, desde) = en_segundo_plano(&estado, move |db| {
        biblioteca::ids_para_cola(db, &consulta, indice)
    })
    .await?;
    reproductor(&app)?.enviar(Orden::ReproducirPistas {
        ids,
        desde: desde as usize,
    });
    Ok(())
}

#[tauri::command]
pub async fn fijar_favorita(
    estado: tauri::State<'_, Estado>,
    pista_id: i64,
    favorita: bool,
) -> NsResult<()> {
    en_segundo_plano(&estado, move |db| {
        biblioteca::fijar_favorita(db, pista_id, favorita)
    })
    .await
}

#[tauri::command]
pub async fn biblioteca_album(
    estado: tauri::State<'_, Estado>,
    id: i64,
) -> NsResult<Option<biblioteca::AlbumResumen>> {
    en_segundo_plano(&estado, move |db| biblioteca::album(db, id)).await
}

#[tauri::command]
pub async fn biblioteca_artista(
    estado: tauri::State<'_, Estado>,
    id: i64,
) -> NsResult<Option<biblioteca::ArtistaResumen>> {
    en_segundo_plano(&estado, move |db| biblioteca::artista(db, id)).await
}

// --- Playlists -------------------------------------------------------------------

/// Cota: `playlists::MAX_PLAYLISTS`; las del usuario son decenas y las automáticas
/// las genera la aplicación con un número fijo.
#[tauri::command]
pub async fn playlists_listar(
    estado: tauri::State<'_, Estado>,
    consulta: playlists::ConsultaPlaylists,
) -> NsResult<Vec<playlists::PlaylistResumen>> {
    en_segundo_plano(&estado, move |db| playlists::listar(db, &consulta)).await
}

#[tauri::command]
pub async fn playlist(
    estado: tauri::State<'_, Estado>,
    id: i64,
) -> NsResult<Option<playlists::PlaylistResumen>> {
    en_segundo_plano(&estado, move |db| playlists::una(db, id)).await
}

#[tauri::command]
pub async fn playlist_pistas(
    estado: tauri::State<'_, Estado>,
    id: i64,
    desde: u32,
    limite: u32,
) -> NsResult<biblioteca::PaginaPistas> {
    en_segundo_plano(&estado, move |db| playlists::pistas(db, id, desde, limite)).await
}

#[tauri::command]
pub async fn reproducir_playlist(
    app: AppHandle,
    estado: tauri::State<'_, Estado>,
    id: i64,
    indice: u32,
) -> NsResult<()> {
    let ids = en_segundo_plano(&estado, move |db| playlists::ids(db, id)).await?;
    reproductor(&app)?.enviar(Orden::ReproducirPistas {
        ids,
        desde: indice as usize,
    });
    Ok(())
}

#[tauri::command]
pub async fn crear_playlist(
    estado: tauri::State<'_, Estado>,
    nombre: String,
    descripcion: Option<String>,
) -> NsResult<i64> {
    en_segundo_plano(&estado, move |db| {
        playlists::crear(db, &nombre, descripcion.as_deref())
    })
    .await
}

#[tauri::command]
pub async fn renombrar_playlist(
    estado: tauri::State<'_, Estado>,
    id: i64,
    nombre: String,
    descripcion: Option<String>,
) -> NsResult<()> {
    en_segundo_plano(&estado, move |db| {
        playlists::renombrar(db, id, &nombre, descripcion.as_deref())
    })
    .await
}

#[tauri::command]
pub async fn borrar_playlist(estado: tauri::State<'_, Estado>, id: i64) -> NsResult<()> {
    en_segundo_plano(&estado, move |db| playlists::borrar(db, id)).await
}

#[tauri::command]
pub async fn agregar_a_playlist(
    estado: tauri::State<'_, Estado>,
    id: i64,
    pistas: Vec<i64>,
) -> NsResult<u32> {
    en_segundo_plano(&estado, move |db| playlists::agregar(db, id, &pistas)).await
}

#[tauri::command]
pub async fn quitar_de_playlist(
    estado: tauri::State<'_, Estado>,
    id: i64,
    pista_id: i64,
) -> NsResult<()> {
    en_segundo_plano(&estado, move |db| playlists::quitar(db, id, pista_id)).await
}

#[tauri::command]
pub async fn mover_en_playlist(
    estado: tauri::State<'_, Estado>,
    id: i64,
    desde: u32,
    hasta: u32,
) -> NsResult<()> {
    en_segundo_plano(&estado, move |db| {
        playlists::mover(db, id, desde as usize, hasta as usize)
    })
    .await
}

#[tauri::command]
pub async fn anclar_playlist(
    estado: tauri::State<'_, Estado>,
    id: i64,
    anclada: bool,
) -> NsResult<()> {
    en_segundo_plano(&estado, move |db| playlists::anclar(db, id, anclada)).await
}

// --- Vista de reproducción ------------------------------------------------------

#[tauri::command]
pub async fn letra_de_pista(
    estado: tauri::State<'_, Estado>,
    pista_id: i64,
) -> NsResult<crate::letras::Letra> {
    en_segundo_plano(&estado, move |db| crate::letras::de_pista(db, pista_id)).await
}

/// El color del fondo de la vista de reproducción: el de la portada o, sin ella,
/// uno estable por pista.
#[tauri::command]
pub async fn ambiente_de_pista(
    estado: tauri::State<'_, Estado>,
    pista_id: i64,
) -> NsResult<crate::letras::Ambiente> {
    let rutas = estado.rutas.clone();
    en_segundo_plano(&estado, move |db| {
        let peticion = crate::portadas::Peticion {
            clase: crate::portadas::Clase::Pista,
            id: pista_id,
            tamano: Some(64),
        };
        let desde_portada = crate::portadas::servir(db, &rutas, peticion)
            .ok()
            .and_then(|(bytes, _)| image::load_from_memory(&bytes).ok())
            .and_then(|imagen| crate::letras::ambiente_de_imagen(&imagen));
        Ok(desde_portada
            .unwrap_or_else(|| crate::letras::ambiente_de_semilla(&format!("pista:{pista_id}"))))
    })
    .await
}

/// Abre el minirreproductor flotante, o lo trae delante si ya está abierto.
#[tauri::command]
pub async fn abrir_minirreproductor(app: AppHandle) -> NsResult<()> {
    if let Some(v) = app.get_webview_window("mini") {
        let _ = v.set_focus();
        return Ok(());
    }
    tauri::WebviewWindowBuilder::new(&app, "mini", tauri::WebviewUrl::App("mini".into()))
        .title("NB Sound")
        .inner_size(400.0, 112.0)
        .resizable(false)
        .always_on_top(true)
        .decorations(false)
        .skip_taskbar(true)
        .build()
        .map(|_| ())
        .map_err(|_| {
            tracing::error!("no se pudo abrir el minirreproductor");
            NsError::Internal
        })
}

// --- Preferencias -------------------------------------------------------------------

#[tauri::command]
pub async fn apariencia(
    estado: tauri::State<'_, Estado>,
) -> NsResult<crate::preferencias::Apariencia> {
    en_segundo_plano(&estado, crate::preferencias::apariencia).await
}

/// Cambia una preferencia de la lista de `preferencias.rs`; las demás se rechazan.
#[tauri::command]
pub async fn guardar_preferencia(
    estado: tauri::State<'_, Estado>,
    clave: String,
    valor: serde_json::Value,
) -> NsResult<()> {
    en_segundo_plano(&estado, move |db| {
        crate::preferencias::guardar(db, &clave, &valor)
    })
    .await
}

/// Una preselección del ecualizador, para pintar la lista.
#[derive(Debug, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct PreseleccionEcualizador {
    pub nombre: String,
    pub preamp_db: f32,
    pub bandas_db: Vec<f32>,
}

/// El ecualizador como está guardado.
#[tauri::command]
pub async fn ecualizador(
    estado: tauri::State<'_, Estado>,
) -> NsResult<crate::reproductor::AjustesEcualizador> {
    en_segundo_plano(&estado, |db| {
        crate::reproductor::leer_ecualizador(&*db.conexion()?)
    })
    .await
}

/// Cota: las 18 preselecciones de libVLC.
#[tauri::command]
pub async fn preselecciones_ecualizador() -> NsResult<Vec<PreseleccionEcualizador>> {
    Ok(crate::audio::ecualizador::PRESELECCIONES
        .iter()
        .map(|p| PreseleccionEcualizador {
            nombre: p.nombre.to_owned(),
            preamp_db: p.preamp_db,
            bandas_db: p.bandas_db.to_vec(),
        })
        .collect())
}

/// La carpeta de la música, para mostrarla en Ajustes. `None` si no hay.
#[tauri::command]
pub async fn carpeta_musica(estado: tauri::State<'_, Estado>) -> NsResult<Option<String>> {
    en_segundo_plano(&estado, |db| {
        Ok(crate::reproductor::carpeta_musica(&*db.conexion()?)?
            .map(|p| p.to_string_lossy().into_owned()))
    })
    .await
}

#[tauri::command]
pub async fn inicio(estado: tauri::State<'_, Estado>) -> NsResult<crate::inicio::Inicio> {
    en_segundo_plano(&estado, crate::inicio::resumen).await
}
