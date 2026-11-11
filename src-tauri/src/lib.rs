//! Runtime de NB Sound.
//!
//! Contratos: docs/adr/README.md. Cada servicio vive en su módulo, y los comandos
//! del puente están en [`comandos`]: ninguno es síncrono, porque en Tauri un
//! comando sin `async` corre en el hilo de la ventana y la congela mientras dura
//! (lo vigila `scripts/check-comandos.mjs`).

pub mod a_ciegas;
pub mod agregados;
pub mod analisis;
pub mod audio;
pub mod autorreparacion;
pub mod bandeja;
pub mod biblioteca;
pub mod catalogo;
pub mod cola;
pub mod comandos;
pub mod controles_sistema;
pub mod copia_dispositivo;
pub mod copia_seguridad;
pub mod cortafuegos;
pub mod db;
pub mod descubrir;
pub mod dj;
pub mod error;
pub mod explorador;
pub mod fiesta;
pub mod frecuencia_compartida;
pub mod gpu;
pub mod identidad_movil;
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
pub mod prioridad;
pub mod privacidad;
pub mod rasgos;
pub mod reproductor;
pub mod secrets;
pub mod security;
pub mod sorpresa;
pub mod telemetry;
pub mod ventana;

use std::sync::Arc;

use crate::db::BaseDeDatos;
use crate::net::{PoliticaDeRed, Red};
use crate::paths::Rutas;

/// Estado compartido del runtime.
pub struct Estado {
    pub frecuencia_copia: Option<frecuencia_compartida::RecursoFrecuencia>,
    pub rutas: Rutas,
    pub red: Arc<Red>,
    pub db: BaseDeDatos,
    pub movil: Arc<movil::ServidorMovil>,
    pub fiesta: Arc<fiesta::ServidorFiesta>,
    pub importador: catalogo::importacion::Importador,
    pub agregados: agregados::Gestor,
    pub karaoke: karaoke::Karaoke,
    pub dj: dj::director::Director,
    pub equipo: dj::equipo::Equipo,
    /// Lo que "Sorpréndeme" ya sugirió en esta sesión.
    pub sorpresa: sorpresa::Sorpresa,
    /// La carpeta de música que se eligió en Ajustes y aún no se aplicó: la ruta
    /// se queda en el proceso y no cruza el puente (ADR-001).
    pub carpeta_propuesta: std::sync::Mutex<Option<std::path::PathBuf>>,
    /// La ronda de A ciegas: vive en memoria.
    pub a_ciegas: Arc<std::sync::Mutex<a_ciegas::Juego>>,
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
    fiesta: Arc<fiesta::ServidorFiesta>,
}

impl reproductor::Oyente for OyenteTauri {
    fn instantanea(&self, i: &reproductor::Instantanea) {
        use tauri::Emitter;
        let _ = self.app.emit("reproductor:instantanea", i);
        if let Some(c) = self.controles.get() {
            c.actualizar(i);
        }
        self.movil.publicar(i);
        self.fiesta.actualizar_sonando_id(i.pista_id);
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
    let frecuencia_copia = match frecuencia_compartida::nuevo(&db) {
        Ok(recurso) => Some(recurso),
        Err(error) => {
            tracing::warn!(
                codigo = error.code(),
                "la frecuencia compartida no está disponible"
            );
            None
        }
    };
    if let Some(recurso) = &frecuencia_copia {
        frecuencia_compartida::iniciar_enlace_si_se_pidio(recurso.clone());
    }
    // Si la música ya no está donde estaba (otro equipo, otro usuario, una copia
    // restaurada), se busca antes de vigilar e importar nada (`ubicacion.rs`).
    if let Err(error) = catalogo::ubicacion::recuperar_si_hace_falta(
        &db,
        catalogo::ubicacion::casa().as_deref(),
        paths::musica_por_defecto().as_deref(),
    ) {
        tracing::warn!(
            codigo = error.code(),
            "no se pudo comprobar la carpeta de la música"
        );
    }
    let red = Arc::new(Red::new(politica_guardada(&db)));
    let puente = movil::Puente::default();
    // El servidor avisa a Ajustes de lo que cambia; la ventana aún no existe.
    let ventana: Arc<std::sync::OnceLock<tauri::AppHandle>> = Arc::default();
    let aviso = Arc::clone(&ventana);
    let servidor_movil = Arc::new(movil::ServidorMovil::nuevo(
        db.clone(),
        rutas.clone(),
        puente.clone(),
        movil::Opciones::default(),
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
    // Al estrenar una versión, lo que había fallado se vuelve a intentar solo
    // (`autorreparacion.rs`), en su hilo para no retrasar la ventana.
    {
        let (db, importador, karaoke) = (db.clone(), importador.clone(), servicio_karaoke.clone());
        let lanzado = std::thread::Builder::new()
            .name("autorreparacion".into())
            .spawn(move || {
                match autorreparacion::estrena_version(&db, env!("CARGO_PKG_VERSION")) {
                    Ok(true) => {
                        if let Err(error) = karaoke::reintentar_fallidas(&db) {
                            tracing::warn!(
                                codigo = error.code(),
                                "no se pudo reintentar el karaoke"
                            );
                        }
                        karaoke.despertar();
                        match autorreparacion::por_revisar_reintentables(&db) {
                            Ok(rutas) if !rutas.is_empty() => {
                                tracing::info!(
                                    archivos = rutas.len(),
                                    "se reintenta lo que falló al importar"
                                );
                                importador.importar(rutas);
                            }
                            Ok(_) => {}
                            Err(error) => tracing::warn!(
                                codigo = error.code(),
                                "no se pudo revisar lo que falló al importar"
                            ),
                        }
                    }
                    Ok(false) => {}
                    Err(error) => {
                        tracing::warn!(codigo = error.code(), "no se pudo comprobar la versión")
                    }
                }
            });
        if lanzado.is_err() {
            tracing::error!("no se pudo lanzar la autorreparación");
        }
    }
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
    let aviso = Arc::clone(&ventana);
    let al_reproductor = Arc::clone(&buzon_karaoke);
    let servidor_fiesta = Arc::new(fiesta::ServidorFiesta::nuevo(
        db.clone(),
        rutas.clone(),
        fiesta::OpcionesFiesta::default(),
        move |pista_id| {
            if let Some(b) = al_reproductor.get() {
                b.enviar(reproductor::Orden::Agregar {
                    ids: vec![pista_id],
                    justo_despues: false,
                });
            }
        },
        move || {
            use tauri::Emitter;
            if let Some(app) = aviso.get() {
                let _ = app.emit("fiesta:cambio", ());
            }
        },
    ));
    let frecuencia_para_ventana = frecuencia_copia.clone();
    let estado = Estado {
        frecuencia_copia,
        rutas: rutas.clone(),
        red: Arc::clone(&red),
        db: db.clone(),
        movil: Arc::clone(&servidor_movil),
        fiesta: Arc::clone(&servidor_fiesta),
        importador: importador.clone(),
        agregados: agregados::Gestor::default(),
        karaoke: servicio_karaoke,
        dj: director,
        equipo: equipo.clone(),
        a_ciegas: Arc::default(),
        sorpresa: sorpresa::Sorpresa::default(),
        carpeta_propuesta: std::sync::Mutex::new(None),
    };
    let importador_setup = importador.clone();
    let fiesta_setup = Arc::clone(&servidor_fiesta);
    let (rutas_vectores, db_vectores) = (rutas.clone(), db.clone());
    let (db_fondo, red_fondo) = (db.clone(), Arc::clone(&red));

    let aplicacion = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(net::plugin_de_actualizaciones())
        .manage(estado)
        .setup(move |app| {
            use tauri::Manager;
            let _ = ventana.set(app.handle().clone());
            if let Some(recurso) = frecuencia_para_ventana {
                frecuencia_compartida::escuchar(app.handle().clone(), recurso);
            }
            crate::ventana::programar_red_de_seguridad(app.handle().clone());
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
            if agregados::instalado(&rutas_vectores, agregados::IdAgregado::Aceleracion).is_some() {
                onnx::fijar_aceleracion(&agregados::carpeta(
                    &rutas_vectores,
                    agregados::IdAgregado::Aceleracion,
                ));
            }
            // Los vectores del DJ, antes de que haga falta pedir una sesión. Aquí y
            // no antes: sin la ruta de ONNX Runtime el modelo no abre.
            dj::embeddings::precalentar(rutas_vectores.clone(), db_vectores.clone());
            // Sin salida de audio la aplicación sigue abriendo: la biblioteca se ve,
            // y Ajustes dice qué pasa con el sonido.
            let controles = Arc::new(std::sync::OnceLock::new());
            match reproductor::Reproductor::arrancar(
                db.clone(),
                rutas.stems(),
                Box::new(OyenteTauri {
                    app: app.handle().clone(),
                    controles: Arc::clone(&controles),
                    movil: puente.clone(),
                    fiesta: Arc::clone(&fiesta_setup),
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
                }
                Err(error) => {
                    tracing::error!(codigo = error.code(), "el reproductor no arrancó");
                }
            }
            medicion::arrancar(db.clone());
            catalogo::auditoria::arrancar(db.clone(), rutas.clone());
            // El análisis con modelos, en su hilo y con pausas (F5.3.2).
            analisis::arrancar(db.clone(), rutas.clone());
            // La carpeta de música vigilada (F4.2.2).
            catalogo::vigilancia::vigilar(db.clone(), importador_setup.clone());
            // Lo que le falta a la biblioteca, sin prisa (A9).
            let app_fondo = app.handle().clone();
            catalogo::completar_fondo::arrancar(
                db_fondo.clone(),
                Arc::clone(&red_fondo),
                importador_setup.clone(),
                move || {
                    use tauri::Emitter;
                    let _ = app_fondo.emit("biblioteca:cambio", ());
                },
            );
            // La copia automática, si toca (F4.2.6). Comprimir las portadas tarda:
            // en su hilo.
            let (d, r) = (db.clone(), rutas.clone());
            let _ = std::thread::Builder::new()
                .name("copia-automatica".into())
                .spawn(move || {
                    crate::prioridad::bajar_hilo_actual();
                    // Al abrir, NB Sound ya lee mucho (la biblioteca, las portadas, lo
                    // que suena): la copia espera a que eso pase.
                    std::thread::sleep(std::time::Duration::from_secs(120));
                    loop {
                        // Quien deja NB Sound abierto días también tiene sus copias.
                        copia_seguridad::automatica_si_toca(&d, &r);
                        std::thread::sleep(std::time::Duration::from_secs(6 * 3600));
                    }
                });
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
                let pendiente = ruta
                    .strip_prefix("/pendiente/")
                    .and_then(|id| id.parse::<i64>().ok());
                let servida = if ruta == "/perfil" {
                    portadas::servir_perfil(&db, &rutas)
                } else if let Some(id) = pendiente {
                    portadas::servir_pendiente(&db, id)
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
            comandos::registrar_ventana_no_visible,
            comandos::pistas_resumen,
            comandos::biblioteca_pistas,
            comandos::biblioteca_albumes,
            comandos::biblioteca_artistas,
            comandos::reproducir_lista,
            comandos::fijar_favorita,
            comandos::borrar_pista,
            comandos::mostrar_en_explorador,
            comandos::sorprendeme,
            comandos::duplicados_resumen,
            comandos::buscar_duplicados,
            comandos::purgar_duplicados,
            comandos::biblioteca_album,
            comandos::biblioteca_artista,
            comandos::playlists_listar,
            comandos::playlist,
            comandos::playlist_pistas,
            comandos::reproducir_playlist,
            comandos::crear_playlist,
            comandos::renombrar_playlist,
            comandos::borrar_playlist,
            comandos::playlists_de_pista,
            comandos::duplicar_playlist,
            comandos::vaciar_playlist,
            comandos::encolar_playlist,
            comandos::agregar_a_playlist,
            comandos::quitar_de_playlist,
            comandos::mover_en_playlist,
            comandos::anclar_playlist,
            comandos::crear_playlist_inteligente,
            comandos::editar_playlist_inteligente,
            comandos::regenerar_playlists_automaticas,
            comandos::letra_de_pista,
            comandos::ambiente_de_pista,
            comandos::forma_de_onda,
            comandos::abrir_minirreproductor,
            comandos::red_permisos,
            comandos::red_permitir,
            comandos::dejar_minirreproductor,
            comandos::apariencia,
            comandos::guardar_preferencia,
            comandos::ecualizador,
            comandos::preselecciones_ecualizador,
            comandos::carpeta_musica,
            comandos::ubicacion_musica,
            comandos::carpeta_musica_elegir,
            comandos::carpeta_musica_aplicar,
            comandos::politica_red,
            comandos::cambiar_politica_red,
            comandos::ajustes_ia,
            comandos::guardar_ajustes_ia,
            comandos::guardar_clave_ia,
            comandos::borrar_clave_ia,
            comandos::claves_servicios,
            comandos::guardar_clave_servicio,
            comandos::borrar_clave_servicio,
            comandos::inicio,
            comandos::perfil,
            comandos::perfil_cambiar_foto,
            comandos::resumen_escucha,
            comandos::exportar_resumen_escucha,
            comandos::movil_estado,
            comandos::movil_permitir,
            comandos::movil_emparejar,
            comandos::movil_telefonos,
            comandos::movil_quitar,
            comandos::copia_dispositivo_ejecutar,
            comandos::fiesta_estado,
            comandos::fiesta_encender,
            comandos::fiesta_regenerar_qr,
            comandos::fiesta_modo_automatico,
            comandos::fiesta_resolver_sugerencia,
            comandos::importacion_progreso,
            comandos::importacion_cancelar,
            comandos::anadir_musica,
            comandos::qa_importar_carpeta,
            comandos::por_revisar_listar,
            comandos::por_revisar_contar,
            comandos::por_revisar_importar,
            comandos::por_revisar_mostrar,
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
            comandos::copia_frecuencia_estado,
            comandos::copia_elegir_carpeta,
            comandos::reiniciar,
            comandos::agregados_estado,
            comandos::agregado_instalar,
            comandos::actualizacion_buscar,
            comandos::actualizacion_instalar,
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
            comandos::dj_eliminar,
            comandos::aciegas_disponibles,
            comandos::aciegas_ronda,
            comandos::aciegas_iniciar,
            comandos::aciegas_jugar,
            comandos::aciegas_intentar,
            comandos::aciegas_fragmento
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
                let _ = e.fiesta.apagar();
            }
        }
    });
}
