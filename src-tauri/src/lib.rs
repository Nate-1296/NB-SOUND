//! Runtime de NB Sound.
//!
//! Contratos: docs/adr/README.md. Cada servicio vive en su módulo, y los comandos
//! del puente están en [`comandos`]: ninguno es síncrono, porque en Tauri un
//! comando sin `async` corre en el hilo de la ventana y la congela mientras dura
//! (lo vigila `scripts/check-comandos.mjs`).

pub mod audio;
pub mod biblioteca;
pub mod cola;
pub mod comandos;
pub mod db;
pub mod error;
pub mod identidad_movil;
pub mod importador_v1;
pub mod letras;
pub mod net;
pub mod paths;
pub mod playlists;
pub mod portadas;
pub mod reproductor;
pub mod secrets;
pub mod security;
pub mod telemetry;

use std::sync::Arc;

use crate::db::BaseDeDatos;
use crate::net::{PoliticaDeRed, Red};
use crate::paths::{Rutas, RutasV1};

/// Estado compartido del runtime.
pub struct Estado {
    pub rutas: Rutas,
    pub red: Arc<Red>,
    pub db: BaseDeDatos,
}

/// La política de red que el usuario dejó guardada; la de fábrica, que no deja
/// salir nada, si no hay ninguna o no se puede leer.
fn politica_guardada(db: &BaseDeDatos) -> PoliticaDeRed {
    let leida = db.conexion().ok().and_then(|conn| {
        conn.query_row(
            "SELECT valor FROM preferencias WHERE clave = 'politica_de_red'",
            [],
            |f| f.get::<_, String>(0),
        )
        .ok()
    });
    leida
        .and_then(|json| serde_json::from_str(&json).ok())
        .unwrap_or_default()
}

/// La primera vez que la V2 encuentra la V1, la importa en segundo plano: copiar
/// varios GB de portadas no puede retrasar la ventana. Las siguientes veces no
/// hace nada, porque el importador deja su marca (ADR-004).
fn importar_v1_en_segundo_plano(
    db: BaseDeDatos,
    rutas: Rutas,
    red: Arc<Red>,
    reproductor: Option<reproductor::Buzon>,
) {
    let Some(v1) = RutasV1::estandar().filter(|v1| v1.base_de_datos().is_file()) else {
        return;
    };
    let lanzado = std::thread::Builder::new()
        .name("importador-v1".into())
        .spawn(move || {
            let env = v1.config.join(".env");
            let llavero = importador_v1::claves::LlaveroDelSistema;
            match importador_v1::importar(&v1.base_de_datos(), Some(&env), &db, &rutas, &llavero) {
                Ok(Some(_)) => {
                    red.cambiar_politica(politica_guardada(&db));
                    if let Some(r) = &reproductor {
                        r.enviar(reproductor::Orden::Recargar);
                    }
                }
                Ok(None) => {}
                Err(error) => tracing::error!(codigo = error.code(), "no se pudo importar la V1"),
            }
            if let Err(error) =
                identidad_movil::copiar_de_la_v1(&v1.identidad_movil(), &rutas.identidad_movil())
            {
                tracing::error!(
                    codigo = error.code(),
                    "no se pudo copiar la identidad móvil de la V1"
                );
            }
        });
    if lanzado.is_err() {
        tracing::error!("no se pudo lanzar el importador de la V1");
    }
}

/// Cuenta a la interfaz lo que hace el reproductor, como eventos de Tauri.
struct OyenteTauri(tauri::AppHandle);

impl reproductor::Oyente for OyenteTauri {
    fn instantanea(&self, i: &reproductor::Instantanea) {
        use tauri::Emitter;
        let _ = self.0.emit("reproductor:instantanea", i);
    }

    fn aviso(&self, a: &reproductor::AvisoReproductor) {
        use tauri::Emitter;
        let _ = self.0.emit("reproductor:aviso", a);
    }
}

/// Arranca la aplicación.
///
/// # Panics
///
/// Si el sistema no ofrece un directorio de datos donde escribir, o si la base de
/// datos no se puede abrir: sin ellos no hay biblioteca que mostrar, y seguir
/// sería peor que detenerse con un mensaje.
pub fn run() {
    let rutas = Rutas::resolver().expect("el sistema no ofrece un directorio de datos utilizable");
    let _registro = telemetry::init(&rutas.registros);
    tracing::info!(version = env!("CARGO_PKG_VERSION"), "arranca NB Sound");

    let db = BaseDeDatos::abrir(&rutas.base_de_datos()).expect("no se pudo abrir la base de datos");
    let red = Arc::new(Red::new(politica_guardada(&db)));
    let estado = Estado {
        rutas: rutas.clone(),
        red: Arc::clone(&red),
        db: db.clone(),
    };

    let aplicacion = tauri::Builder::default()
        .manage(estado)
        .setup(move |app| {
            use tauri::Manager;
            // Sin salida de audio la aplicación sigue abriendo: la biblioteca se ve,
            // y Ajustes dice qué pasa con el sonido.
            let buzon = match reproductor::Reproductor::arrancar(
                db.clone(),
                rutas.stems(),
                Box::new(OyenteTauri(app.handle().clone())),
            ) {
                Ok(r) => {
                    let b = r.buzon();
                    app.manage(r);
                    Some(b)
                }
                Err(error) => {
                    tracing::error!(codigo = error.code(), "el reproductor no arrancó");
                    None
                }
            };
            importar_v1_en_segundo_plano(db.clone(), rutas.clone(), Arc::clone(&red), buzon);
            Ok(())
        })
        .register_asynchronous_uri_scheme_protocol("portada", move |ctx, peticion, responder| {
            use tauri::Manager;
            let estado = ctx.app_handle().state::<Estado>();
            let (db, rutas) = (estado.db.clone(), estado.rutas.clone());
            let ruta = peticion.uri().path().to_owned();
            // Reducir una portada es trabajo de CPU: fuera del hilo de la ventana.
            tauri::async_runtime::spawn_blocking(move || {
                let respuesta = match portadas::interpretar(&ruta)
                    .ok_or(error::NsError::PathNotAllowed)
                    .and_then(|p| portadas::servir(&db, &rutas, p))
                {
                    Ok((bytes, mime)) => tauri::http::Response::builder()
                        .header("Content-Type", mime)
                        .header("Cache-Control", "max-age=31536000, immutable")
                        .body(bytes),
                    Err(_) => tauri::http::Response::builder()
                        .status(404)
                        .body(Vec::new()),
                };
                if let Ok(r) = respuesta {
                    responder.respond(r);
                }
            });
        })
        // Cerrar la ventana principal cierra la aplicación aunque el
        // minirreproductor siga abierto: si no, la música seguiría sonando sin
        // ventana desde la que pararla.
        .on_window_event(|ventana, evento| {
            if ventana.label() == "main"
                && matches!(evento, tauri::WindowEvent::CloseRequested { .. })
            {
                use tauri::Manager;
                ventana.app_handle().exit(0);
            }
        })
        .invoke_handler(tauri::generate_handler![
            comandos::salud,
            comandos::reproductor_estado,
            comandos::reproductor_orden,
            comandos::pistas_resumen,
            comandos::biblioteca_pistas,
            comandos::biblioteca_albumes,
            comandos::biblioteca_artistas,
            comandos::reproducir_lista,
            comandos::fijar_favorita,
            comandos::biblioteca_album,
            comandos::biblioteca_artista,
            comandos::playlists_listar,
            comandos::playlist,
            comandos::playlist_pistas,
            comandos::reproducir_playlist,
            comandos::crear_playlist,
            comandos::renombrar_playlist,
            comandos::borrar_playlist,
            comandos::agregar_a_playlist,
            comandos::quitar_de_playlist,
            comandos::mover_en_playlist,
            comandos::anclar_playlist,
            comandos::letra_de_pista,
            comandos::ambiente_de_pista,
            comandos::abrir_minirreproductor
        ])
        .build(tauri::generate_context!())
        .expect("no se pudo arrancar la ventana de NB Sound");

    aplicacion.run(|app, evento| {
        // Cerrar no puede dejar audio sonando ni la sesión sin guardar (F2.1.6).
        if let tauri::RunEvent::Exit = evento {
            use tauri::Manager;
            if let Some(r) = app.try_state::<reproductor::Reproductor>() {
                r.cerrar();
            }
        }
    });
}
