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

// --- Privacidad e inteligencia artificial (F4.2.7) ---------------------------------

/// La política de red que cumple la puerta ahora mismo.
#[tauri::command]
pub async fn politica_red(estado: tauri::State<'_, Estado>) -> NsResult<crate::net::PoliticaDeRed> {
    Ok(estado.red.politica())
}

/// Cambia el interruptor general o el de un servicio; rige desde la siguiente
/// petición.
#[tauri::command]
pub async fn cambiar_politica_red(
    estado: tauri::State<'_, Estado>,
    politica: crate::net::PoliticaDeRed,
) -> NsResult<()> {
    let red = std::sync::Arc::clone(&estado.red);
    en_segundo_plano(&estado, move |db| {
        crate::privacidad::cambiar_politica(db, &red, politica)
    })
    .await
}

#[tauri::command]
pub async fn ajustes_ia(
    estado: tauri::State<'_, Estado>,
) -> NsResult<crate::privacidad::AjustesIa> {
    en_segundo_plano(&estado, crate::privacidad::ajustes_ia).await
}

#[tauri::command]
pub async fn guardar_ajustes_ia(
    estado: tauri::State<'_, Estado>,
    proveedor: crate::privacidad::ProveedorIa,
    modelo: String,
) -> NsResult<crate::privacidad::AjustesIa> {
    en_segundo_plano(&estado, move |db| {
        crate::privacidad::guardar_ia(db, proveedor, &modelo)?;
        crate::privacidad::ajustes_ia(db)
    })
    .await
}

/// Guarda la clave del proveedor en el llavero. Devuelve los ajustes, que solo
/// dicen si hay clave: la clave no vuelve.
#[tauri::command]
pub async fn guardar_clave_ia(
    estado: tauri::State<'_, Estado>,
    clave: String,
) -> NsResult<crate::privacidad::AjustesIa> {
    en_segundo_plano(&estado, move |db| {
        crate::privacidad::guardar_clave_ia(db, &clave)?;
        crate::privacidad::ajustes_ia(db)
    })
    .await
}

#[tauri::command]
pub async fn borrar_clave_ia(
    estado: tauri::State<'_, Estado>,
) -> NsResult<crate::privacidad::AjustesIa> {
    en_segundo_plano(&estado, |db| {
        crate::privacidad::borrar_clave_ia(db)?;
        crate::privacidad::ajustes_ia(db)
    })
    .await
}

#[tauri::command]
pub async fn inicio(estado: tauri::State<'_, Estado>) -> NsResult<crate::inicio::Inicio> {
    en_segundo_plano(&estado, crate::inicio::resumen).await
}

#[tauri::command]
pub async fn perfil(estado: tauri::State<'_, Estado>) -> NsResult<crate::perfil::Perfil> {
    en_segundo_plano(&estado, crate::perfil::perfil).await
}

// --- Dispositivos (F3.3) ------------------------------------------------------

/// Ejecuta un trabajo con el servidor móvil fuera del hilo de la ventana: encender
/// espera a que escuche y, la primera vez, crea la identidad TLS.
async fn con_movil<T: Send + 'static>(
    estado: &tauri::State<'_, Estado>,
    trabajo: impl FnOnce(&crate::movil::ServidorMovil) -> NsResult<T> + Send + 'static,
) -> NsResult<T> {
    let movil = std::sync::Arc::clone(&estado.movil);
    tauri::async_runtime::spawn_blocking(move || trabajo(&movil))
        .await
        .map_err(|_| NsError::Internal)?
}

#[tauri::command]
pub async fn movil_estado(estado: tauri::State<'_, Estado>) -> NsResult<crate::movil::EstadoMovil> {
    con_movil(&estado, |m| m.estado()).await
}

/// Permite o deja de permitir que los teléfonos se conecten, y lo recuerda para el
/// próximo arranque, como el interruptor de la V1.
#[tauri::command]
pub async fn movil_permitir(
    estado: tauri::State<'_, Estado>,
    activo: bool,
) -> NsResult<crate::movil::EstadoMovil> {
    let db = estado.db.clone();
    con_movil(&estado, move |m| {
        crate::preferencias::guardar(
            &db,
            "servidor_movil_al_arrancar",
            &serde_json::Value::Bool(activo),
        )?;
        if activo {
            m.encender()?;
        } else {
            m.apagar();
        }
        m.estado()
    })
    .await
}

/// Un QR nuevo para conectar un teléfono. Conectar uno es querer que se conecten:
/// el servidor queda encendido también en los próximos arranques.
#[tauri::command]
pub async fn movil_emparejar(
    estado: tauri::State<'_, Estado>,
) -> NsResult<crate::movil::Emparejar> {
    let db = estado.db.clone();
    con_movil(&estado, move |m| {
        crate::preferencias::guardar(
            &db,
            "servidor_movil_al_arrancar",
            &serde_json::Value::Bool(true),
        )?;
        m.emparejar()
    })
    .await
}

/// Cota: `movil::MAX_DISPOSITIVOS`; cada emparejamiento lo hace una persona a mano.
#[tauri::command]
pub async fn movil_telefonos(
    estado: tauri::State<'_, Estado>,
) -> NsResult<Vec<crate::movil::Telefono>> {
    con_movil(&estado, |m| m.telefonos()).await
}

#[tauri::command]
pub async fn movil_quitar(estado: tauri::State<'_, Estado>, id: i64) -> NsResult<()> {
    con_movil(&estado, move |m| m.quitar(id)).await
}

// --- Importar (F4.2) ----------------------------------------------------------

#[tauri::command]
pub async fn importacion_progreso(
    estado: tauri::State<'_, Estado>,
) -> NsResult<crate::catalogo::importacion::ProgresoImportacion> {
    Ok(estado.importador.progreso())
}

/// "Añadir música": el selector nativo de archivos o de carpeta, y lo elegido a
/// la cola. Las rutas no cruzan el puente: las elige el sistema y se quedan en
/// Rust.
#[tauri::command]
pub async fn anadir_musica(app: AppHandle, carpeta: bool) -> NsResult<u32> {
    use tauri_plugin_dialog::DialogExt;
    let elegidas = tauri::async_runtime::spawn_blocking(move || {
        let d = app.dialog().file().set_title("Añadir música");
        let rutas: Vec<std::path::PathBuf> = if carpeta {
            d.blocking_pick_folder()
                .and_then(|f| f.into_path().ok())
                .into_iter()
                .collect()
        } else {
            d.add_filter("Audio", &crate::catalogo::canalizacion::EXTENSIONES)
                .blocking_pick_files()
                .unwrap_or_default()
                .into_iter()
                .filter_map(|f| f.into_path().ok())
                .collect()
        };
        (app, rutas)
    })
    .await
    .map_err(|_| NsError::Internal)?;
    let (app, rutas) = elegidas;
    let n = rutas.len() as u32;
    if n > 0 {
        app.state::<Estado>().importador.importar(rutas);
    }
    Ok(n)
}

// --- Por revisar (F4.2.4) -----------------------------------------------------

/// Cota: `catalogo::por_revisar::MAX_PENDIENTES`.
#[tauri::command]
pub async fn por_revisar_listar(
    estado: tauri::State<'_, Estado>,
) -> NsResult<Vec<crate::catalogo::por_revisar::Pendiente>> {
    en_segundo_plano(&estado, crate::catalogo::por_revisar::listar).await
}

#[tauri::command]
pub async fn por_revisar_contar(estado: tauri::State<'_, Estado>) -> NsResult<u32> {
    en_segundo_plano(&estado, crate::catalogo::por_revisar::contar).await
}

/// Importa uno: tal como está, o con el candidato elegido.
#[tauri::command]
pub async fn por_revisar_importar(
    estado: tauri::State<'_, Estado>,
    id: i64,
    candidato: Option<u32>,
) -> NsResult<i64> {
    let importador = estado.importador.clone();
    tauri::async_runtime::spawn_blocking(move || {
        importador.con_entorno(|e| {
            crate::catalogo::por_revisar::importar(e, id, candidato.map(|c| c as usize))
        })
    })
    .await
    .map_err(|_| NsError::Internal)?
}

#[tauri::command]
pub async fn por_revisar_descartar(
    estado: tauri::State<'_, Estado>,
    ids: Vec<i64>,
) -> NsResult<()> {
    en_segundo_plano(&estado, move |db| {
        for id in &ids {
            crate::catalogo::por_revisar::descartar(db, *id)?;
        }
        Ok(())
    })
    .await
}

// --- Agregados (F5.1.3) ----------------------------------------------------------------

/// Cota: los cuatro agregados del catálogo compilado (`agregados::CATALOGO`).
#[tauri::command]
pub async fn agregados_estado(
    estado: tauri::State<'_, Estado>,
) -> NsResult<Vec<crate::agregados::EstadoAgregado>> {
    Ok(estado.agregados.estado(&estado.rutas))
}

/// Instala un agregado en segundo plano; el progreso llega con el evento
/// `agregados:cambio`. Pulsar "Instalar", con el tamaño y el origen a la vista,
/// es el consentimiento del servicio de agregados; con la conexión general
/// apagada no sale nada.
#[tauri::command]
pub async fn agregado_instalar(app: AppHandle, id: crate::agregados::IdAgregado) -> NsResult<()> {
    use tauri::Emitter;
    let (db, rutas, red, gestor) = {
        let e = app.state::<Estado>();
        (
            e.db.clone(),
            e.rutas.clone(),
            std::sync::Arc::clone(&e.red),
            e.agregados.clone(),
        )
    };
    let mut politica = red.politica();
    if !politica.general {
        return Err(NsError::NetworkDisabled);
    }
    if politica.servicios.insert(crate::net::Servicio::Agregados) {
        let r = std::sync::Arc::clone(&red);
        tauri::async_runtime::spawn_blocking(move || {
            crate::privacidad::cambiar_politica(&db, &r, politica)
        })
        .await
        .map_err(|_| NsError::Internal)??;
    }
    gestor.instalar(rutas, red, id, move || {
        let _ = app.emit("agregados:cambio", ());
    })
}

/// Cota: los cuatro agregados del catálogo compilado (`agregados::CATALOGO`).
#[tauri::command]
pub async fn agregado_quitar(
    estado: tauri::State<'_, Estado>,
    id: crate::agregados::IdAgregado,
) -> NsResult<Vec<crate::agregados::EstadoAgregado>> {
    let (rutas, gestor) = (estado.rutas.clone(), estado.agregados.clone());
    tauri::async_runtime::spawn_blocking(move || {
        crate::agregados::quitar(&rutas, id)?;
        Ok(gestor.estado(&rutas))
    })
    .await
    .map_err(|_| NsError::Internal)?
}

// --- Copia de seguridad (F4.2.6) ------------------------------------------------------

#[tauri::command]
pub async fn copia_estado(
    estado: tauri::State<'_, Estado>,
) -> NsResult<crate::copia_seguridad::EstadoCopia> {
    let rutas = estado.rutas.clone();
    en_segundo_plano(&estado, move |db| {
        crate::copia_seguridad::estado(db, &rutas)
    })
    .await
}

/// Crea una copia donde diga el selector nativo. `None` si se canceló. La ruta no
/// cruza el puente: la elige el sistema y se queda en Rust.
#[tauri::command]
pub async fn copia_crear(app: AppHandle) -> NsResult<Option<crate::copia_seguridad::ResumenCopia>> {
    use tauri_plugin_dialog::DialogExt;
    let (db, rutas) = {
        let e = app.state::<Estado>();
        (e.db.clone(), e.rutas.clone())
    };
    tauri::async_runtime::spawn_blocking(move || {
        let fecha: String = db
            .conexion()?
            .query_row("SELECT date('now', 'localtime')", [], |f| f.get(0))
            .map_err(|_| NsError::StorageFailure)?;
        let Some(destino) = app
            .dialog()
            .file()
            .set_title("Guardar una copia de seguridad")
            .add_filter("Copia de NB Sound", &[crate::copia_seguridad::EXTENSION])
            .set_file_name(format!(
                "nb-sound-{fecha}.{}",
                crate::copia_seguridad::EXTENSION
            ))
            .blocking_save_file()
            .and_then(|f| f.into_path().ok())
        else {
            return Ok(None);
        };
        crate::copia_seguridad::crear(&db, &rutas, &destino).map(Some)
    })
    .await
    .map_err(|_| NsError::Internal)?
}

/// Elige una copia con el selector nativo, la valida entera y la deja lista para
/// el próximo arranque. `false` si se canceló.
#[tauri::command]
pub async fn copia_restaurar(app: AppHandle) -> NsResult<bool> {
    use tauri_plugin_dialog::DialogExt;
    let rutas = app.state::<Estado>().rutas.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let Some(copia) = app
            .dialog()
            .file()
            .set_title("Restaurar una copia de seguridad")
            .add_filter("Copia de NB Sound", &[crate::copia_seguridad::EXTENSION])
            .blocking_pick_file()
            .and_then(|f| f.into_path().ok())
        else {
            return Ok(false);
        };
        crate::copia_seguridad::preparar_restauracion(&rutas, &copia).map(|()| true)
    })
    .await
    .map_err(|_| NsError::Internal)?
}

#[tauri::command]
pub async fn copia_frecuencia(
    estado: tauri::State<'_, Estado>,
    dias: u32,
) -> NsResult<crate::copia_seguridad::EstadoCopia> {
    let rutas = estado.rutas.clone();
    en_segundo_plano(&estado, move |db| {
        crate::copia_seguridad::fijar_frecuencia(db, dias)?;
        crate::copia_seguridad::estado(db, &rutas)
    })
    .await
}

/// La carpeta de las copias automáticas, con el selector nativo.
#[tauri::command]
pub async fn copia_elegir_carpeta(app: AppHandle) -> NsResult<crate::copia_seguridad::EstadoCopia> {
    use tauri_plugin_dialog::DialogExt;
    let (db, rutas) = {
        let e = app.state::<Estado>();
        (e.db.clone(), e.rutas.clone())
    };
    tauri::async_runtime::spawn_blocking(move || {
        if let Some(carpeta) = app
            .dialog()
            .file()
            .set_title("Carpeta de las copias de seguridad")
            .blocking_pick_folder()
            .and_then(|f| f.into_path().ok())
        {
            crate::copia_seguridad::fijar_carpeta(&db, &carpeta)?;
        }
        crate::copia_seguridad::estado(&db, &rutas)
    })
    .await
    .map_err(|_| NsError::Internal)?
}

/// Reinicia la aplicación: lo pide restaurar una copia, que se aplica al
/// arrancar. Cerrar pasa por el mismo camino que salir (sesión guardada, audio
/// parado, teléfonos avisados).
#[tauri::command]
pub async fn reiniciar(app: AppHandle) -> NsResult<()> {
    app.request_restart();
    Ok(())
}

// --- Editar metadatos (F4.2.5) -------------------------------------------------------

#[tauri::command]
pub async fn datos_pista(
    estado: tauri::State<'_, Estado>,
    pista: i64,
) -> NsResult<crate::catalogo::edicion::DatosPista> {
    en_segundo_plano(&estado, move |db| {
        crate::catalogo::edicion::datos_pista(db, pista)
    })
    .await
}

/// Guarda los datos de una pista en la base y, si se puede, en su archivo.
#[tauri::command]
pub async fn editar_pista(
    estado: tauri::State<'_, Estado>,
    pista: i64,
    datos: crate::catalogo::edicion::DatosPista,
) -> NsResult<()> {
    let importador = estado.importador.clone();
    tauri::async_runtime::spawn_blocking(move || {
        importador.con_entorno(|e| crate::catalogo::edicion::editar_pista(e, pista, &datos))
    })
    .await
    .map_err(|_| NsError::Internal)?
}

#[tauri::command]
pub async fn datos_album(
    estado: tauri::State<'_, Estado>,
    album: i64,
) -> NsResult<crate::catalogo::edicion::DatosAlbum> {
    en_segundo_plano(&estado, move |db| {
        crate::catalogo::edicion::datos_album(db, album)
    })
    .await
}

/// Guarda los datos de un álbum y de sus pistas. Devuelve el id del álbum
/// resultante, que cambia solo si se juntó con otro que ya existía.
#[tauri::command]
pub async fn editar_album(
    estado: tauri::State<'_, Estado>,
    album: i64,
    datos: crate::catalogo::edicion::DatosAlbum,
) -> NsResult<i64> {
    let importador = estado.importador.clone();
    tauri::async_runtime::spawn_blocking(move || {
        importador.con_entorno(|e| crate::catalogo::edicion::editar_album(e, album, &datos))
    })
    .await
    .map_err(|_| NsError::Internal)?
}

/// "Completar datos" de una pista sin verificar (F4.2.8): identificarla de nuevo
/// y buscarle portada y letra, sin cambiar su id.
#[tauri::command]
pub async fn completar_datos(
    estado: tauri::State<'_, Estado>,
    pista: i64,
) -> NsResult<crate::catalogo::completar_datos::DatosCompletados> {
    let importador = estado.importador.clone();
    tauri::async_runtime::spawn_blocking(move || {
        importador.con_entorno(|e| crate::catalogo::completar_datos::completar_datos(e, pista))
    })
    .await
    .map_err(|_| NsError::Internal)?
}

/// Vuelve a buscarlo: a la cola de importación.
#[tauri::command]
pub async fn por_revisar_reintentar(estado: tauri::State<'_, Estado>, id: i64) -> NsResult<()> {
    let importador = estado.importador.clone();
    let ruta = en_segundo_plano(&estado, move |db| {
        crate::catalogo::por_revisar::para_reintentar(db, id)
    })
    .await?;
    importador.importar(vec![ruta]);
    Ok(())
}
