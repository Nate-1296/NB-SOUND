//! Runtime de NB Sound.
//!
//! Contratos: docs/adr/README.md. Cada servicio vive en su módulo, y los comandos
//! del puente están en [`comandos`]: ninguno es síncrono, porque en Tauri un
//! comando sin `async` corre en el hilo de la ventana y la congela mientras dura
//! (lo vigila `scripts/check-comandos.mjs`).

pub mod agregados;
pub mod analisis;
pub mod audio;
pub mod bandeja;
pub mod biblioteca;
pub mod catalogo;
pub mod cola;
pub mod comandos;
pub mod controles_sistema;
pub mod copia_seguridad;
pub mod db;
pub mod descubrir;
pub mod dj;
pub mod error;
pub mod gpu;
pub mod identidad_movil;
pub mod importador_v1;
pub mod inicio;
pub mod karaoke;
pub mod letras;
pub mod medicion;
pub mod movil;
pub mod net;
pub mod onnx;
pub mod paths;
pub mod perfil;
pub mod playlists;
pub mod portadas;
pub mod preferencias;
pub mod privacidad;
pub mod rasgos;
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
    pub movil: Arc<movil::ServidorMovil>,
    pub importador: catalogo::importacion::Importador,
    pub agregados: agregados::Gestor,
    pub karaoke: karaoke::Karaoke,
    pub dj: dj::director::Director,
    pub equipo: dj::equipo::Equipo,
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
    servidor_movil: Arc<movil::ServidorMovil>,
) {
    let Some(v1) = RutasV1::estandar().filter(|v1| v1.base_de_datos().is_file()) else {
        return;
    };
    let lanzado = std::thread::Builder::new()
        .name("importador-v1".into())
        .spawn(move || {
            let env = v1.config.join(".env");
            let llavero = importador_v1::claves::LlaveroDelSistema;
            let importada =
                importador_v1::importar(&v1.base_de_datos(), Some(&env), &db, &rutas, &llavero);
            if let Err(error) =
                identidad_movil::copiar_de_la_v1(&v1.identidad_movil(), &rutas.identidad_movil())
            {
                tracing::error!(
                    codigo = error.code(),
                    "no se pudo copiar la identidad móvil de la V1"
                );
            }
            match importada {
                Ok(Some(_)) => {
                    red.cambiar_politica(politica_guardada(&db));
                    if let Some(r) = &reproductor {
                        r.enviar(reproductor::Orden::Recargar);
                    }
                    // La V1 traía su interruptor de encender el servidor al abrir; la
                    // identidad ya está copiada, así que los teléfonos la reconocen.
                    encender_movil_si_toca(&db, &servidor_movil);
                }
                Ok(None) => {}
                Err(error) => tracing::error!(codigo = error.code(), "no se pudo importar la V1"),
            }
        });
    if lanzado.is_err() {
        tracing::error!("no se pudo lanzar el importador de la V1");
    }
}

/// Enciende el servidor móvil si el usuario lo dejó así. Fuera del hilo de la
/// ventana: la primera vez crea la identidad TLS.
fn encender_movil_si_toca(db: &BaseDeDatos, servidor: &Arc<movil::ServidorMovil>) {
    if !movil::al_arrancar(db).unwrap_or(false) {
        return;
    }
    if let Err(error) = servidor.encender() {
        tracing::error!(codigo = error.code(), "el servidor móvil no arrancó");
    }
}

/// Cuenta lo que hace el reproductor a la interfaz, como eventos de Tauri; a los
/// controles del sistema, que llegan después porque necesitan su buzón, y al
/// servidor móvil.
struct OyenteTauri {
    app: tauri::AppHandle,
    controles: Arc<std::sync::OnceLock<controles_sistema::ControlesSistema>>,
    movil: movil::Puente,
}

impl reproductor::Oyente for OyenteTauri {
    fn instantanea(&self, i: &reproductor::Instantanea) {
        use tauri::Emitter;
        let _ = self.app.emit("reproductor:instantanea", i);
        if let Some(c) = self.controles.get() {
            c.actualizar(i);
        }
        self.movil.publicar(i);
    }

    fn aviso(&self, a: &reproductor::AvisoReproductor) {
        use tauri::Emitter;
        let _ = self.app.emit("reproductor:aviso", a);
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

    // Una copia de seguridad preparada se pone antes de abrir la base, nunca con
    // la base abierta (F4.2.6).
    copia_seguridad::aplicar_restauracion_pendiente(&rutas);
    let db = BaseDeDatos::abrir(&rutas.base_de_datos()).expect("no se pudo abrir la base de datos");
    let red = Arc::new(Red::new(politica_guardada(&db)));
    let puente = movil::Puente::default();
    // El servidor avisa a Ajustes de lo que cambia; la ventana aún no existe.
    let ventana: Arc<std::sync::OnceLock<tauri::AppHandle>> = Arc::default();
    let aviso = Arc::clone(&ventana);
    let servidor_movil = Arc::new(movil::ServidorMovil::nuevo(
        db.clone(),
        rutas.clone(),
        puente.clone(),
        movil::Opciones {
            identidad_v1: RutasV1::estandar().map(|v1| v1.identidad_movil()),
            ..movil::Opciones::default()
        },
        move || {
            use tauri::Emitter;
            if let Some(app) = aviso.get() {
                let _ = app.emit("movil:cambio", ());
            }
        },
    ));
    let aviso = Arc::clone(&ventana);
    let importador = catalogo::importacion::Importador::arrancar(
        catalogo::importacion::Recursos {
            db: db.clone(),
            rutas: rutas.clone(),
            red: Arc::clone(&red),
            fpcalc: catalogo::acoustid::ruta_fpcalc(),
        },
        move |p| {
            use tauri::Emitter;
            if let Some(app) = aviso.get() {
                let _ = app.emit("importacion:progreso", p);
            }
        },
    );
    let aviso = Arc::clone(&ventana);
    // El reproductor arranca con la ventana; hasta entonces no hay a quién avisar.
    let buzon_karaoke: Arc<std::sync::OnceLock<reproductor::Buzon>> = Arc::default();
    let al_reproductor = Arc::clone(&buzon_karaoke);
    let servicio_karaoke = karaoke::Karaoke::arrancar(db.clone(), rutas.clone(), move |lista| {
        use tauri::Emitter;
        if let Some(app) = aviso.get() {
            let _ = app.emit("karaoke:cambio", ());
        }
        if let (Some(pista), Some(b)) = (lista, al_reproductor.get()) {
            b.enviar(reproductor::Orden::InstrumentalListo(pista));
        }
    });
    // El DJ, en su hilo (F6.1.6): sigue construyendo la sesión mientras suena, y
    // cada bloque nuevo llega al reproductor y a la vista.
    let aviso = Arc::clone(&ventana);
    let al_reproductor = Arc::clone(&buzon_karaoke);
    let rutas_dj = rutas.clone();
    let director = dj::director::Director::arrancar(
        dj::servicio::Dj::new(
            db.clone(),
            Box::new(move || dj::embeddings::proveedor(&rutas_dj)),
        ),
        Arc::new(move |sesion| {
            use tauri::Emitter;
            if let Some(b) = al_reproductor.get() {
                b.enviar(reproductor::Orden::Dj(reproductor::OrdenDj::Recargar(
                    sesion,
                )));
            }
            if let Some(app) = aviso.get() {
                let _ = app.emit("dj:cambio", sesion);
            }
        }),
    )
    .expect("no se pudo arrancar el hilo del DJ");
    // La medida del equipo para mezclar (F6.1.4): la comparten el DJ, que la lanza
    // al abrirse, y el reproductor, que la usa en cada mezcla.
    let equipo = dj::equipo::Equipo::default();
    let estado = Estado {
        rutas: rutas.clone(),
        red: Arc::clone(&red),
        db: db.clone(),
        movil: Arc::clone(&servidor_movil),
        importador: importador.clone(),
        agregados: agregados::Gestor::default(),
        karaoke: servicio_karaoke,
        dj: director,
        equipo: equipo.clone(),
    };
    let importador_setup = importador.clone();

    let aplicacion = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(estado)
        .setup(move |app| {
            use tauri::Manager;
            let _ = ventana.set(app.handle().clone());
            // ONNX Runtime viaja entre los recursos. Solo en depuración se busca
            // también en `binarios/`, para no dejar en el binario publicado la ruta
            // de la máquina que lo compiló.
            let biblioteca = app
                .path()
                .resource_dir()
                .map(|d| d.join(onnx::nombre_biblioteca()))
                .ok()
                .filter(|r| r.is_file());
            #[cfg(debug_assertions)]
            let biblioteca = biblioteca.or_else(|| {
                Some(
                    std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                        .join("binarios")
                        .join(onnx::nombre_biblioteca()),
                )
            });
            if let Some(b) = biblioteca {
                onnx::fijar_ruta(&b);
            }
            // Sin salida de audio la aplicación sigue abriendo: la biblioteca se ve,
            // y Ajustes dice qué pasa con el sonido.
            let controles = Arc::new(std::sync::OnceLock::new());
            let buzon = match reproductor::Reproductor::arrancar(
                db.clone(),
                rutas.stems(),
                Box::new(OyenteTauri {
                    app: app.handle().clone(),
                    controles: Arc::clone(&controles),
                    movil: puente.clone(),
                }),
                equipo.clone(),
            ) {
                Ok(r) => {
                    let b = r.buzon();
                    let _ = buzon_karaoke.set(b.clone());
                    app.manage(r);
                    // Teclas multimedia y el reproductor del escritorio (F2.1.5).
                    if let Some(c) = controles_sistema::ControlesSistema::arrancar(
                        app.handle(),
                        db.clone(),
                        rutas.clone(),
                        b.clone(),
                    ) {
                        let _ = controles.set(c);
                    }
                    bandeja::poner(app.handle(), b.clone());
                    let ordenes = b.clone();
                    puente.conectar(move |o| ordenes.enviar(o));
                    Some(b)
                }
                Err(error) => {
                    tracing::error!(codigo = error.code(), "el reproductor no arrancó");
                    None
                }
            };
            importar_v1_en_segundo_plano(
                db.clone(),
                rutas.clone(),
                Arc::clone(&red),
                buzon,
                Arc::clone(&servidor_movil),
            );
            medicion::arrancar(db.clone());
            // El análisis con modelos, en su hilo y con pausas (F5.3.2).
            analisis::arrancar(db.clone(), rutas.clone());
            // La carpeta de música vigilada (F4.2.2).
            catalogo::vigilancia::vigilar(db.clone(), importador_setup.clone());
            // La copia automática, si toca (F4.2.6). Comprimir las portadas tarda:
            // en su hilo.
            let (d, r) = (db.clone(), rutas.clone());
            let _ = std::thread::Builder::new()
                .name("copia-automatica".into())
                .spawn(move || copia_seguridad::automatica_si_toca(&d, &r));
            let (d, s) = (db.clone(), Arc::clone(&servidor_movil));
            let _ = std::thread::Builder::new()
                .name("encender-movil".into())
                .spawn(move || encender_movil_si_toca(&d, &s));
            Ok(())
        })
        .register_asynchronous_uri_scheme_protocol("portada", move |ctx, peticion, responder| {
            use tauri::Manager;
            let estado = ctx.app_handle().state::<Estado>();
            let (db, rutas) = (estado.db.clone(), estado.rutas.clone());
            let ruta = peticion.uri().path().to_owned();
            // Reducir una portada es trabajo de CPU: fuera del hilo de la ventana.
            tauri::async_runtime::spawn_blocking(move || {
                let servida = if ruta == "/perfil" {
                    portadas::servir_perfil(&db, &rutas)
                } else {
                    portadas::interpretar(&ruta)
                        .ok_or(error::NsError::PathNotAllowed)
                        .and_then(|p| portadas::servir(&db, &rutas, p))
                };
                let respuesta = match servida {
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
        .on_window_event(move |ventana, evento| {
            use tauri::{DragDropEvent, Emitter, Manager, WindowEvent};
            if ventana.label() != "main" {
                return;
            }
            match evento {
                WindowEvent::CloseRequested { .. } => ventana.app_handle().exit(0),
                // Soltar archivos en cualquier parte de la ventana los importa
                // (F4.2.1). Las rutas no pasan por el webview: van del sistema al
                // importador.
                WindowEvent::DragDrop(DragDropEvent::Drop { paths, .. }) => {
                    let _ = ventana.emit("importacion:arrastre", false);
                    importador.importar(paths.clone());
                }
                WindowEvent::DragDrop(DragDropEvent::Enter { .. }) => {
                    let _ = ventana.emit("importacion:arrastre", true);
                }
                WindowEvent::DragDrop(DragDropEvent::Leave) => {
                    let _ = ventana.emit("importacion:arrastre", false);
                }
                _ => {}
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
            comandos::abrir_minirreproductor,
            comandos::apariencia,
            comandos::guardar_preferencia,
            comandos::ecualizador,
            comandos::preselecciones_ecualizador,
            comandos::carpeta_musica,
            comandos::politica_red,
            comandos::cambiar_politica_red,
            comandos::ajustes_ia,
            comandos::guardar_ajustes_ia,
            comandos::guardar_clave_ia,
            comandos::borrar_clave_ia,
            comandos::inicio,
            comandos::perfil,
            comandos::movil_estado,
            comandos::movil_permitir,
            comandos::movil_emparejar,
            comandos::movil_telefonos,
            comandos::movil_quitar,
            comandos::importacion_progreso,
            comandos::anadir_musica,
            comandos::por_revisar_listar,
            comandos::por_revisar_contar,
            comandos::por_revisar_importar,
            comandos::por_revisar_descartar,
            comandos::por_revisar_reintentar,
            comandos::completar_datos,
            comandos::datos_pista,
            comandos::editar_pista,
            comandos::datos_album,
            comandos::editar_album,
            comandos::copia_estado,
            comandos::copia_crear,
            comandos::copia_restaurar,
            comandos::copia_frecuencia,
            comandos::copia_elegir_carpeta,
            comandos::reiniciar,
            comandos::agregados_estado,
            comandos::agregado_instalar,
            comandos::agregado_quitar,
            comandos::gpu_detectada,
            comandos::karaoke_estado,
            comandos::karaoke_preparar,
            comandos::karaoke_preparar_favoritas,
            comandos::descubrir,
            comandos::dj_pedir,
            comandos::dj_sesion,
            comandos::dj_reproducir,
            comandos::dj_valorar,
            comandos::dj_regenerar,
            comandos::dj_descartar,
            comandos::dj_guardar,
            comandos::dj_historial,
            comandos::dj_eliminar
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
            // Los teléfonos dejan de ver el equipo en el acto, no al caducar mDNS.
            if let Some(e) = app.try_state::<Estado>() {
                e.movil.apagar();
            }
        }
    });
}
