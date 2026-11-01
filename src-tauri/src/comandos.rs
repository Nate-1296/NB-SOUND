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

/// Borra una pista de la biblioteca y opcionalmente su archivo del disco.
#[tauri::command]
pub async fn borrar_pista(
    estado: tauri::State<'_, Estado>,
    id: i64,
    borrar_archivo: bool,
) -> NsResult<()> {
    let db = estado.db.clone();
    let importador = estado.importador.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut conn = db.conexion()?;
        let ruta: String = conn
            .query_row("SELECT ruta FROM pistas WHERE id = ?1", [id], |f| f.get(0))
            .map_err(|_| NsError::FileNotFound)?;

        let tx = crate::db::transaccion_de_escritura(&mut conn)?;
        tx.execute("DELETE FROM pistas WHERE id = ?1", [id])
            .map_err(|_| NsError::StorageFailure)?;
        tx.commit().map_err(|_| NsError::StorageFailure)?;

        if borrar_archivo {
            let _ = importador.con_entorno(|entorno| {
                if let Ok(archivo) =
                    crate::security::resolve_within(&entorno.musica, std::path::Path::new(&ruta))
                {
                    if archivo.is_file() {
                        let _ = std::fs::remove_file(&archivo);
                    }
                }
                Ok(())
            });
        }
        tracing::info!(id = id, "pista borrada de la biblioteca");
        Ok(())
    })
    .await
    .map_err(|_| NsError::Internal)?
}

fn abrir_en_explorador(archivo: &std::path::Path) {
    #[cfg(target_os = "windows")]
    {
        let _ = std::process::Command::new("explorer")
            .arg("/select,")
            .arg(archivo)
            .spawn();
    }
    #[cfg(target_os = "macos")]
    {
        let _ = std::process::Command::new("open")
            .arg("-R")
            .arg(archivo)
            .spawn();
    }
    #[cfg(target_os = "linux")]
    {
        let ruta_uri = format!("file://{}", archivo.to_string_lossy());
        let status = std::process::Command::new("dbus-send")
            .args([
                "--session",
                "--dest=org.freedesktop.FileManager1",
                "--type=method_call",
                "/org/freedesktop/FileManager1",
                "org.freedesktop.FileManager1.ShowItems",
                &format!("array:string:{ruta_uri}"),
                "string:",
            ])
            .status();

        if !matches!(status, Ok(s) if s.success()) {
            if let Some(padre) = archivo.parent() {
                let _ = std::process::Command::new("xdg-open").arg(padre).spawn();
            }
        }
    }
}

/// Muestra el archivo de una pista en el gestor de archivos nativo del sistema.
#[tauri::command]
pub async fn mostrar_en_explorador(
    estado: tauri::State<'_, Estado>,
    pista_id: i64,
) -> NsResult<()> {
    let db = estado.db.clone();
    let importador = estado.importador.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let conn = db.conexion()?;
        let ruta: String = conn
            .query_row("SELECT ruta FROM pistas WHERE id = ?1", [pista_id], |f| {
                f.get(0)
            })
            .map_err(|_| NsError::FileNotFound)?;

        importador.con_entorno(|entorno| {
            let archivo =
                crate::security::resolve_within(&entorno.musica, std::path::Path::new(&ruta))
                    .or_else(|_| {
                        std::path::PathBuf::from(&ruta)
                            .canonicalize()
                            .map_err(|_| NsError::FileNotFound)
                    })?;
            if !archivo.exists() {
                return Err(NsError::FileNotFound);
            }
            abrir_en_explorador(&archivo);
            tracing::info!(id = pista_id, "archivo mostrado en el explorador");
            Ok(())
        })
    })
    .await
    .map_err(|_| NsError::StorageFailure)?
}

/// Información de duplicados detectados en la biblioteca (FDB-02, COMP-07).
#[derive(Debug, Clone, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct ResumenDuplicados {
    pub total: u32,
    #[ts(type = "number")]
    pub bytes_recuperables: u64,
}

#[tauri::command]
pub async fn duplicados_resumen(estado: tauri::State<'_, Estado>) -> NsResult<ResumenDuplicados> {
    let db = estado.db.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let conn = db.conexion()?;
        let (total, bytes): (u32, Option<i64>) = conn
            .query_row(
                "SELECT COUNT(*), SUM(tamano) FROM pistas WHERE estado = 'duplicado'",
                [],
                |f| Ok((f.get(0)?, f.get(1)?)),
            )
            .map_err(|_| NsError::StorageFailure)?;
        Ok(ResumenDuplicados {
            total,
            bytes_recuperables: bytes.unwrap_or(0).max(0) as u64,
        })
    })
    .await
    .map_err(|_| NsError::Internal)?
}

#[tauri::command]
pub async fn purgar_duplicados(
    estado: tauri::State<'_, Estado>,
    borrar_archivos: bool,
) -> NsResult<u32> {
    let db = estado.db.clone();
    let importador = estado.importador.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut conn = db.conexion()?;
        let mut s = conn
            .prepare("SELECT id, ruta FROM pistas WHERE estado = 'duplicado'")
            .map_err(|_| NsError::StorageFailure)?;
        let filas = s
            .query_map([], |f| Ok((f.get::<_, i64>(0)?, f.get::<_, String>(1)?)))
            .map_err(|_| NsError::StorageFailure)?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| NsError::StorageFailure)?;
        drop(s);

        if filas.is_empty() {
            return Ok(0);
        }

        let total = filas.len() as u32;

        if borrar_archivos {
            let _ = importador.con_entorno(|entorno| {
                for (_, ruta) in &filas {
                    if let Ok(archivo) =
                        crate::security::resolve_within(&entorno.musica, std::path::Path::new(ruta))
                    {
                        if archivo.is_file() {
                            let _ = std::fs::remove_file(&archivo);
                        }
                    }
                }
                Ok(())
            });
        }

        let tx = crate::db::transaccion_de_escritura(&mut conn)?;
        tx.execute("DELETE FROM pistas WHERE estado = 'duplicado'", [])
            .map_err(|_| NsError::StorageFailure)?;
        tx.commit().map_err(|_| NsError::StorageFailure)?;

        tracing::info!(total = total, "duplicados purgados de la biblioteca");
        Ok(total)
    })
    .await
    .map_err(|_| NsError::Internal)?
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

#[tauri::command]
pub async fn crear_playlist_inteligente(
    estado: tauri::State<'_, Estado>,
    nombre: String,
    descripcion: Option<String>,
    regla: playlists::ReglaInteligente,
) -> NsResult<i64> {
    en_segundo_plano(&estado, move |db| {
        playlists::crear_inteligente(db, &nombre, descripcion.as_deref(), &regla)
    })
    .await
}

#[tauri::command]
pub async fn editar_playlist_inteligente(
    estado: tauri::State<'_, Estado>,
    id: i64,
    nombre: String,
    descripcion: Option<String>,
    regla: playlists::ReglaInteligente,
) -> NsResult<()> {
    en_segundo_plano(&estado, move |db| {
        playlists::editar_inteligente(db, id, &nombre, descripcion.as_deref(), &regla)
    })
    .await
}

#[tauri::command]
pub async fn regenerar_playlists_automaticas(estado: tauri::State<'_, Estado>) -> NsResult<u32> {
    en_segundo_plano(&estado, playlists::regenerar_automaticas).await
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

/// La forma de onda de una pista (F8.1): mil picos de 0 a 255, o ninguno si aún
/// no se ha medido. Cota: `sonoridad::PICOS` (1.000 bytes).
#[tauri::command]
pub async fn forma_de_onda(estado: tauri::State<'_, Estado>, pista_id: i64) -> NsResult<Vec<u8>> {
    en_segundo_plano(&estado, move |db| crate::medicion::picos(db, pista_id)).await
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

/// Cambia la foto de perfil del usuario mediante el selector nativo de archivos.
#[tauri::command]
pub async fn perfil_cambiar_foto(app: AppHandle) -> NsResult<bool> {
    use tauri_plugin_dialog::DialogExt;
    let (db, rutas) = {
        let e = app.state::<Estado>();
        (e.db.clone(), e.rutas.clone())
    };
    tauri::async_runtime::spawn_blocking(move || {
        let Some(archivo) = app
            .dialog()
            .file()
            .set_title("Elegir foto de perfil")
            .add_filter("Imágenes", &["png", "jpg", "jpeg", "webp"])
            .blocking_pick_file()
            .and_then(|f| f.into_path().ok())
        else {
            return Ok(false);
        };
        let bytes = std::fs::read(&archivo).map_err(|_| NsError::FileNotFound)?;
        let ext = archivo
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("jpg")
            .to_lowercase();
        let ext = if ext == "png" { "png" } else { "jpg" };
        let nombre_archivo = format!("foto.{ext}");
        let carpeta = rutas.datos.join("perfil");
        std::fs::create_dir_all(&carpeta).map_err(|_| NsError::StorageFailure)?;
        let destino = carpeta.join(&nombre_archivo);
        std::fs::write(&destino, bytes).map_err(|_| NsError::StorageFailure)?;

        let conn = db.conexion()?;
        let valor_json =
            serde_json::to_string(&nombre_archivo).map_err(|_| NsError::StorageFailure)?;
        conn.execute(
            "INSERT INTO preferencias (clave, valor) VALUES ('foto_perfil', ?1)
             ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            [&valor_json],
        )
        .map_err(|_| NsError::StorageFailure)?;
        Ok(true)
    })
    .await
    .map_err(|_| NsError::Internal)?
}

/// Resumen local de escucha (F8.3) por mes (`YYYY-MM`), año (`YYYY`) o `"todo"`.
#[tauri::command]
pub async fn resumen_escucha(
    estado: tauri::State<'_, Estado>,
    periodo: Option<String>,
) -> NsResult<crate::perfil::ResumenEscucha> {
    en_segundo_plano(&estado, move |db| {
        crate::perfil::resumen_escucha(db, periodo.as_deref())
    })
    .await
}

/// Exporta la tarjeta SVG del resumen de escucha donde elija el selector nativo (F8.3).
/// Devuelve `false` si se canceló. La ruta no cruza el puente IPC.
#[tauri::command]
pub async fn exportar_resumen_escucha(app: AppHandle, periodo: Option<String>) -> NsResult<bool> {
    use tauri_plugin_dialog::DialogExt;
    let db = app.state::<Estado>().db.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let sufijo = periodo
            .as_deref()
            .filter(|p| !p.is_empty())
            .unwrap_or("todo");
        let Some(destino) = app
            .dialog()
            .file()
            .set_title("Exportar resumen de escucha")
            .add_filter("Tarjeta SVG", &["svg"])
            .set_file_name(format!("nb-sound-resumen-{sufijo}.svg"))
            .blocking_save_file()
            .and_then(|f| f.into_path().ok())
        else {
            return Ok(false);
        };
        crate::perfil::exportar_tarjeta(&db, periodo.as_deref(), &destino)?;
        Ok(true)
    })
    .await
    .map_err(|_| NsError::Internal)?
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

/// Copia música a una carpeta o dispositivo externo elegido con el selector
/// nativo (F8.4). Devuelve `None` si el usuario cancela el selector. La ruta no
/// cruza el puente IPC.
#[tauri::command]
pub async fn copia_dispositivo_ejecutar(
    app: AppHandle,
    opciones: crate::copia_dispositivo::OpcionesCopiaDispositivo,
) -> NsResult<Option<crate::copia_dispositivo::ResumenCopiaDispositivo>> {
    use tauri_plugin_dialog::DialogExt;
    let (db, rutas) = {
        let e = app.state::<Estado>();
        (e.db.clone(), e.rutas.clone())
    };
    tauri::async_runtime::spawn_blocking(move || {
        let Some(destino) = app
            .dialog()
            .file()
            .set_title("Elegir carpeta del dispositivo externo")
            .blocking_pick_folder()
            .and_then(|f| f.into_path().ok())
        else {
            return Ok(None);
        };
        crate::copia_dispositivo::copiar(&db, &rutas, &opciones, &destino).map(Some)
    })
    .await
    .map_err(|_| NsError::Internal)?
}

// --- Modo fiesta (F8.5, ADR-012) ----------------------------------------------

async fn con_fiesta<T: Send + 'static>(
    estado: &tauri::State<'_, Estado>,
    trabajo: impl FnOnce(&crate::fiesta::ServidorFiesta) -> NsResult<T> + Send + 'static,
) -> NsResult<T> {
    let fiesta = std::sync::Arc::clone(&estado.fiesta);
    tauri::async_runtime::spawn_blocking(move || trabajo(&fiesta))
        .await
        .map_err(|_| NsError::Internal)?
}

#[tauri::command]
pub async fn fiesta_estado(
    estado: tauri::State<'_, Estado>,
) -> NsResult<crate::fiesta::EstadoFiesta> {
    con_fiesta(&estado, |f| f.estado()).await
}

#[tauri::command]
pub async fn fiesta_encender(
    estado: tauri::State<'_, Estado>,
    activo: bool,
) -> NsResult<crate::fiesta::EstadoFiesta> {
    con_fiesta(
        &estado,
        move |f| {
            if activo {
                f.encender()
            } else {
                f.apagar()
            }
        },
    )
    .await
}

#[tauri::command]
pub async fn fiesta_regenerar_qr(
    estado: tauri::State<'_, Estado>,
) -> NsResult<crate::fiesta::EstadoFiesta> {
    con_fiesta(&estado, |f| f.regenerar_qr()).await
}

#[tauri::command]
pub async fn fiesta_modo_automatico(
    estado: tauri::State<'_, Estado>,
    activo: bool,
) -> NsResult<crate::fiesta::EstadoFiesta> {
    con_fiesta(&estado, move |f| f.fijar_automatico(activo)).await
}

#[tauri::command]
pub async fn fiesta_resolver_sugerencia(
    estado: tauri::State<'_, Estado>,
    id: u64,
    aceptar: bool,
    bloquear: bool,
) -> NsResult<crate::fiesta::EstadoFiesta> {
    con_fiesta(&estado, move |f| f.resolver(id, aceptar, bloquear)).await
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

// --- Actualizaciones de la aplicación (F7.2.2) -----------------------------------

/// Pulsar "Buscar actualizaciones" es el consentimiento del servicio, como
/// "Instalar" lo es de los agregados; con la conexión general apagada no sale
/// nada. Nunca se busca sin que el usuario lo pida.
async fn consentir_actualizaciones(app: &AppHandle) -> NsResult<std::sync::Arc<crate::net::Red>> {
    let (db, red) = {
        let e = app.state::<Estado>();
        (e.db.clone(), std::sync::Arc::clone(&e.red))
    };
    let mut politica = red.politica();
    if !politica.general {
        return Err(NsError::NetworkDisabled);
    }
    if politica
        .servicios
        .insert(crate::net::Servicio::Actualizaciones)
    {
        let r = std::sync::Arc::clone(&red);
        tauri::async_runtime::spawn_blocking(move || {
            crate::privacidad::cambiar_politica(&db, &r, politica)
        })
        .await
        .map_err(|_| NsError::Internal)??;
    }
    Ok(red)
}

/// La versión publicada más nueva que la instalada, si la hay.
#[tauri::command]
pub async fn actualizacion_buscar(app: AppHandle) -> NsResult<Option<crate::net::Actualizacion>> {
    let red = consentir_actualizaciones(&app).await?;
    crate::net::buscar_actualizacion(&app, &red).await
}

/// Instala la versión más nueva y reinicia la aplicación con ella.
#[tauri::command]
pub async fn actualizacion_instalar(app: AppHandle) -> NsResult<()> {
    let red = consentir_actualizaciones(&app).await?;
    if crate::net::instalar_actualizacion(&app, &red).await? {
        app.restart();
    }
    Ok(())
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
    let karaoke = app.state::<Estado>().karaoke.clone();
    gestor.instalar(rutas, red, id, move || {
        let _ = app.emit("agregados:cambio", ());
        // Recién instalado, la cola del karaoke puede empezar sin esperar.
        if id == crate::agregados::IdAgregado::Karaoke {
            karaoke.despertar();
        }
    })
}

/// La GPU que aprovecharía el agregado de aceleración, para recomendarlo con su
/// motivo (F5.1.5). Leer `/proc` es rápido, pero no en el hilo de la ventana.
#[tauri::command]
pub async fn gpu_detectada() -> NsResult<Option<crate::gpu::Gpu>> {
    tauri::async_runtime::spawn_blocking(crate::gpu::detectar)
        .await
        .map_err(|_| NsError::Internal)
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

// --- Karaoke (F5.2.2 y F5.2.3) ---------------------------------------------------------

/// Lo que necesita el micrófono para decidir qué ofrecer.
#[derive(Debug, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct EstadoKaraoke {
    /// El agregado está instalado y puede preparar instrumentales.
    pub instalado: bool,
    /// Hay archivo publicado que instalar (P13).
    pub publicado: bool,
    #[ts(type = "number")]
    pub bytes: u64,
    pub preparando: Option<crate::karaoke::Preparando>,
    /// Cuántas esperan en la cola.
    pub pendientes: u32,
}

#[tauri::command]
pub async fn karaoke_estado(estado: tauri::State<'_, Estado>) -> NsResult<EstadoKaraoke> {
    let (rutas, preparando) = (estado.rutas.clone(), estado.karaoke.preparando());
    en_segundo_plano(&estado, move |db| {
        let pendientes: u32 = db
            .conexion()?
            .query_row(
                "SELECT count(*) FROM stems WHERE estado IN ('pendiente', 'separando')",
                [],
                |f| f.get(0),
            )
            .map_err(|_| NsError::StorageFailure)?;
        let e = crate::agregados::entrada(crate::agregados::IdAgregado::Karaoke)?;
        Ok(EstadoKaraoke {
            instalado: crate::karaoke::modelo_instalado(&rutas).is_some(),
            publicado: e.publicada(),
            bytes: e.bytes,
            preparando,
            pendientes,
        })
    })
    .await
}

/// "Preparar mis favoritas": las favoritas sin instrumental, a la cola. Devuelve
/// cuántas entraron.
#[tauri::command]
pub async fn karaoke_preparar_favoritas(estado: tauri::State<'_, Estado>) -> NsResult<u32> {
    let karaoke = estado.karaoke.clone();
    let n = en_segundo_plano(&estado, crate::karaoke::pedir_favoritas).await?;
    karaoke.despertar();
    Ok(n)
}

/// Pone pistas en la cola del karaoke: la que suena al pulsar el micrófono, o
/// "Preparar mis favoritas". Se preparan mientras suena el original.
#[tauri::command]
pub async fn karaoke_preparar(estado: tauri::State<'_, Estado>, pistas: Vec<i64>) -> NsResult<()> {
    if pistas.len() > 10_000 {
        return Err(NsError::InvalidInput);
    }
    let karaoke = estado.karaoke.clone();
    en_segundo_plano(&estado, move |db| crate::karaoke::pedir(db, &pistas)).await?;
    karaoke.despertar();
    Ok(())
}

// --- Descubrir (F5.3.3) ------------------------------------------------------------------

/// "Algo triste", "para entrenar": secciones de pistas para una frase. Cota:
/// `limite`, como mucho `descubrir::LIMITE_MAXIMO`, en secciones de ocho.
#[tauri::command]
pub async fn descubrir(
    estado: tauri::State<'_, Estado>,
    consulta: String,
    limite: u32,
) -> NsResult<crate::descubrir::Descubrimiento> {
    if consulta.chars().count() > 200 {
        return Err(NsError::InvalidInput);
    }
    en_segundo_plano(&estado, move |db| {
        crate::descubrir::descubrir(db, &consulta, limite)
    })
    .await
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

// --- DJ Privado (F6.1.6) -----------------------------------------------------------------

/// Lo que devuelve pedir una sesión: cuál, y si no hubo ninguna pista que encajara.
#[derive(Debug, Clone, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct PedidoDj {
    #[ts(type = "number")]
    pub sesion_id: i64,
    pub sin_candidatas: bool,
}

/// Una sesión como la ve su vista: cómo se entendió el pedido, sus números y sus
/// pistas con la transición que trae cada una.
#[derive(Debug, Clone, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct VistaSesionDj {
    #[ts(type = "number")]
    pub sesion_id: i64,
    pub peticion: String,
    pub estado: String,
    pub minutos: u32,
    /// El resumen de la intención, con las frases de la V1.
    pub resumen: String,
    pub notas: Vec<String>,
    pub pistas: Vec<crate::dj::sesiones::PistaDeSesion>,
    pub duracion_seg: f64,
    #[ts(type = "number")]
    pub artistas_distintos: u64,
    #[ts(type = "number")]
    pub transiciones_buenas: u64,
    #[ts(type = "number")]
    pub transiciones_total: u64,
    /// Sin el agregado de análisis el DJ elige con los rasgos básicos, y la vista
    /// lo dice (criterio de la Fase 6).
    pub sin_analisis: bool,
}

/// En un hilo de trabajo, para no esperar al hilo del DJ en el de la ventana.
async fn con_dj<T: Send + 'static>(
    estado: &tauri::State<'_, Estado>,
    f: impl FnOnce(&mut crate::dj::servicio::Dj) -> NsResult<T> + Send + 'static,
) -> NsResult<T> {
    let director = estado.dj.clone();
    tauri::async_runtime::spawn_blocking(move || director.con(f))
        .await
        .map_err(|_| NsError::Internal)?
}

fn tocar_sesion(app: &AppHandle, sesion: i64, posicion: u32) {
    if let Ok(r) = reproductor(app) {
        r.enviar(Orden::Dj(crate::reproductor::OrdenDj::Reproducir {
            sesion,
            posicion,
            desde_seg: 0.0,
        }));
    }
}

fn pedido(app: &AppHandle, inicio: crate::dj::servicio::Inicio) -> PedidoDj {
    use crate::dj::servicio::Inicio;
    match inicio {
        Inicio::Lista { id } => {
            tocar_sesion(app, id, 0);
            PedidoDj {
                sesion_id: id,
                sin_candidatas: false,
            }
        }
        Inicio::SinCandidatas { id } => PedidoDj {
            sesion_id: id,
            sin_candidatas: true,
        },
    }
}

/// Pide una sesión con palabras y la empieza a tocar en cuanto tiene su primer
/// bloque; el resto se construye mientras suena.
#[tauri::command]
pub async fn dj_pedir(
    app: AppHandle,
    estado: tauri::State<'_, Estado>,
    peticion: String,
    minutos: u32,
) -> NsResult<PedidoDj> {
    if peticion.chars().count() > 500 {
        return Err(NsError::InvalidInput);
    }
    // La medida del equipo, la primera vez que se usa el DJ (F6.1.4).
    estado.equipo.medir_con_karaoke(&estado.rutas, false);
    let inicio = con_dj(&estado, move |dj| {
        dj.iniciar(&peticion, minutos, None, None)
    })
    .await?;
    Ok(pedido(&app, inicio))
}

/// Una sesión para su vista. Cota: sus pistas, que el constructor limita a la
/// duración pedida (ocho horas como mucho).
#[tauri::command]
pub async fn dj_sesion(
    estado: tauri::State<'_, Estado>,
    sesion_id: i64,
) -> NsResult<VistaSesionDj> {
    en_segundo_plano(&estado, move |db| {
        let s = crate::dj::sesiones::una(db, sesion_id)?.ok_or(NsError::InvalidInput)?;
        let intencion: crate::dj::intencion::Intencion =
            serde_json::from_str(&s.intencion).unwrap_or_default();
        let r: serde_json::Value = serde_json::from_str(&s.resumen).unwrap_or_default();
        let n = |k: &str| r[k].as_u64().unwrap_or(0);
        let sin_analisis = !db
            .conexion()?
            .query_row(
                "SELECT EXISTS (SELECT 1 FROM analisis_profundo WHERE feliz IS NOT NULL)",
                [],
                |f| f.get::<_, bool>(0),
            )
            .map_err(|_| NsError::StorageFailure)?;
        Ok(VistaSesionDj {
            sesion_id,
            peticion: s.peticion,
            estado: s.estado,
            minutos: s.objetivo_minutos,
            resumen: intencion.resumen,
            notas: intencion.notas,
            pistas: crate::dj::sesiones::pistas(db, sesion_id)?,
            duracion_seg: r["duracion_seg"].as_f64().unwrap_or(0.0),
            artistas_distintos: n("artistas_distintos"),
            transiciones_buenas: n("transiciones_buenas"),
            transiciones_total: n("transiciones_total"),
            sin_analisis,
        })
    })
    .await
}

/// Toca una sesión (del historial, o la activa desde otra pista).
#[tauri::command]
pub async fn dj_reproducir(
    app: AppHandle,
    estado: tauri::State<'_, Estado>,
    sesion_id: i64,
    posicion: u32,
) -> NsResult<()> {
    estado.equipo.medir_con_karaoke(&estado.rutas, false);
    con_dj(&estado, move |dj| dj.asegurar(sesion_id)).await?;
    tocar_sesion(&app, sesion_id, posicion);
    Ok(())
}

/// "Me gusta" o "No me gusta" para una pista de la sesión.
#[tauri::command]
pub async fn dj_valorar(
    estado: tauri::State<'_, Estado>,
    sesion_id: i64,
    posicion: u32,
    pista_id: i64,
    gusta: bool,
) -> NsResult<()> {
    use crate::dj::sesiones::Evento;
    con_dj(&estado, move |dj| {
        dj.asegurar(sesion_id)?;
        dj.registrar(
            posicion,
            pista_id,
            if gusta {
                Evento::MeGusta
            } else {
                Evento::NoMeGusta
            },
        )
    })
    .await
}

/// Otra sesión con el mismo pedido; la anterior queda descartada.
#[tauri::command]
pub async fn dj_regenerar(
    app: AppHandle,
    estado: tauri::State<'_, Estado>,
    sesion_id: i64,
) -> NsResult<PedidoDj> {
    let inicio = con_dj(&estado, move |dj| {
        dj.asegurar(sesion_id)?;
        dj.regenerar()?.ok_or(NsError::InvalidInput)
    })
    .await?;
    Ok(pedido(&app, inicio))
}

fn salir_si_suena(app: &AppHandle, sesion: i64) {
    if let Ok(r) = reproductor(app) {
        if r.instantanea()
            .and_then(|i| i.dj)
            .is_some_and(|d| d.sesion_id == sesion)
        {
            r.enviar(Orden::Dj(crate::reproductor::OrdenDj::Salir));
        }
    }
}

/// Descarta la sesión: deja de sonar y vuelve la cola.
#[tauri::command]
pub async fn dj_descartar(
    app: AppHandle,
    estado: tauri::State<'_, Estado>,
    sesion_id: i64,
) -> NsResult<()> {
    salir_si_suena(&app, sesion_id);
    con_dj(&estado, move |dj| {
        dj.asegurar(sesion_id)?;
        dj.descartar()
    })
    .await
}

/// Guarda la sesión como playlist; sin nombre, "DJ Privado: Music Session, Vol. N".
#[tauri::command]
pub async fn dj_guardar(
    estado: tauri::State<'_, Estado>,
    sesion_id: i64,
    nombre: String,
) -> NsResult<i64> {
    if nombre.chars().count() > 200 {
        return Err(NsError::InvalidInput);
    }
    con_dj(&estado, move |dj| {
        dj.asegurar(sesion_id)?;
        dj.guardar_como_playlist(&nombre)
    })
    .await
}

/// El historial, filtrado por texto (sin tildes) y estado. Cota: las 60 sesiones
/// más recientes, como la V1.
#[tauri::command]
pub async fn dj_historial(
    estado: tauri::State<'_, Estado>,
    texto: String,
    filtro: String,
) -> NsResult<Vec<crate::dj::servicio::FilaHistorial>> {
    if texto.chars().count() > 200 || filtro.len() > 32 {
        return Err(NsError::InvalidInput);
    }
    con_dj(&estado, move |dj| dj.historial(&texto, &filtro)).await
}

/// Borra una sesión del historial; si sonaba, deja de sonar.
#[tauri::command]
pub async fn dj_eliminar(
    app: AppHandle,
    estado: tauri::State<'_, Estado>,
    sesion_id: i64,
) -> NsResult<()> {
    salir_si_suena(&app, sesion_id);
    con_dj(&estado, move |dj| dj.eliminar(sesion_id)).await
}

// --- A ciegas (F6.2.2) -------------------------------------------------------------------

/// Cuántas canciones tiene cada modo.
#[derive(Debug, Clone, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
pub struct ModoDisponible {
    pub modo: crate::a_ciegas::Modo,
    pub canciones: u32,
}

/// Una jugada sobre el reto en curso.
#[derive(Debug, Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(
    tag = "tipo",
    rename_all = "camelCase",
    rename_all_fields = "camelCase"
)]
pub enum Jugada {
    RevelarArtista,
    RevelarAlbum,
    RevelarTodo,
    /// "¡La sé!": para los títulos que no se pueden escribir.
    LaSe,
    Indicio {
        indicio: crate::a_ciegas::indicios::Indicio,
    },
    Pasar,
    Avanzar,
    Retroceder,
    Cerrar,
    SegundosFragmento {
        segundos: f64,
    },
}

/// Lo que devuelve escribir el título: cómo de cerca, y la ronda tras el intento.
#[derive(Debug, Clone, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
pub struct ResultadoIntento {
    pub intento: crate::a_ciegas::indicios::Intento,
    pub ronda: crate::a_ciegas::Ronda,
}

/// Cuántas canciones tiene cada modo, para elegir. Cota: los cuatro modos.
#[tauri::command]
pub async fn aciegas_disponibles(
    estado: tauri::State<'_, Estado>,
) -> NsResult<Vec<ModoDisponible>> {
    en_segundo_plano(&estado, |db| {
        Ok(crate::a_ciegas::disponibles(db)?
            .into_iter()
            .map(|(modo, canciones)| ModoDisponible { modo, canciones })
            .collect())
    })
    .await
}

/// La ronda tal como está, para volver a la vista.
#[tauri::command]
pub async fn aciegas_ronda(estado: tauri::State<'_, Estado>) -> NsResult<crate::a_ciegas::Ronda> {
    let j = std::sync::Arc::clone(&estado.a_ciegas);
    let r = j.lock().map_err(|_| NsError::Internal)?.ronda();
    Ok(r)
}

/// Empieza una ronda de `retos` (1 a 25) del modo, evitando las ya jugadas en esta
/// sesión si quedan otras. Sin canciones, la ronda no empieza (`modo` nulo).
#[tauri::command]
pub async fn aciegas_iniciar(
    estado: tauri::State<'_, Estado>,
    modo: crate::a_ciegas::Modo,
    retos: u32,
    evitar: Vec<i64>,
) -> NsResult<crate::a_ciegas::Ronda> {
    if evitar.len() > 10_000 {
        return Err(NsError::InvalidInput);
    }
    let j = std::sync::Arc::clone(&estado.a_ciegas);
    en_segundo_plano(&estado, move |db| {
        let mut j = j.lock().map_err(|_| NsError::Internal)?;
        j.iniciar(db, modo, retos, &evitar)?;
        Ok(j.ronda())
    })
    .await
}

/// Calla el fragmento a ciegas si suena: al cambiar de reto, al revelarlo o al
/// cerrar la ronda, para que no se oiga una canción con la pantalla de otra.
fn callar_fragmento(app: &AppHandle) {
    if let Ok(r) = reproductor(app) {
        if r.instantanea().is_some_and(|i| i.ciego) {
            r.enviar(Orden::PausarReanudar);
        }
    }
}

/// Si la jugada deja otro reto, ninguno o el mismo ya resuelto.
fn cambio_de_reto(antes: &crate::a_ciegas::Ronda, despues: &crate::a_ciegas::Ronda) -> bool {
    antes.indice != despues.indice || despues.reto.as_ref().is_none_or(|v| v.titulo.is_some())
}

/// Una jugada sobre el reto en curso.
#[tauri::command]
pub async fn aciegas_jugar(
    app: AppHandle,
    estado: tauri::State<'_, Estado>,
    jugada: Jugada,
) -> NsResult<crate::a_ciegas::Ronda> {
    let j = std::sync::Arc::clone(&estado.a_ciegas);
    let mut j = j.lock().map_err(|_| NsError::Internal)?;
    let antes = j.ronda();
    match jugada {
        Jugada::RevelarArtista => j.revelar_artista(),
        Jugada::RevelarAlbum => j.revelar_album(),
        Jugada::RevelarTodo => j.revelar_todo(),
        Jugada::LaSe => j.la_se(),
        Jugada::Indicio { indicio } => j.revelar_indicio(indicio),
        Jugada::Pasar => j.pasar(),
        Jugada::Avanzar => j.avanzar(),
        Jugada::Retroceder => j.retroceder(),
        Jugada::Cerrar => j.cerrar(),
        Jugada::SegundosFragmento { segundos } => j.fijar_segundos_fragmento(segundos),
    }
    let r = j.ronda();
    drop(j);
    if cambio_de_reto(&antes, &r) {
        callar_fragmento(&app);
    }
    Ok(r)
}

/// Escribe el título: acierta con los umbrales de la V1 o suma un fallo.
#[tauri::command]
pub async fn aciegas_intentar(
    app: AppHandle,
    estado: tauri::State<'_, Estado>,
    texto: String,
) -> NsResult<ResultadoIntento> {
    if texto.chars().count() > 300 {
        return Err(NsError::InvalidInput);
    }
    let j = std::sync::Arc::clone(&estado.a_ciegas);
    let mut j = j.lock().map_err(|_| NsError::Internal)?;
    let intento = j.intentar(&texto);
    let ronda = j.ronda();
    drop(j);
    if intento.acierto {
        callar_fragmento(&app);
    }
    Ok(ResultadoIntento { intento, ronda })
}

/// Toca el fragmento del reto en curso, a ciegas.
#[tauri::command]
pub async fn aciegas_fragmento(
    app: AppHandle,
    estado: tauri::State<'_, Estado>,
) -> NsResult<crate::a_ciegas::Ronda> {
    let j = std::sync::Arc::clone(&estado.a_ciegas);
    let mut j = j.lock().map_err(|_| NsError::Internal)?;
    let (pista_id, duracion) = j.pista_en_curso().ok_or(NsError::InvalidInput)?;
    let segundos = j.ronda().segundos_fragmento;
    j.fragmento_escuchado();
    reproductor(&app)?.enviar(Orden::Fragmento {
        pista_id,
        desde_seg: crate::a_ciegas::Juego::inicio_fragmento(duracion),
        segundos,
    });
    Ok(j.ronda())
}
