//! Runtime de NB Sound.
//!
//! Contratos: docs/adr/README.md. Cada servicio vive en su módulo, y los comandos
//! del puente están en [`comandos`]: ninguno es síncrono, porque en Tauri un
//! comando sin `async` corre en el hilo de la ventana y la congela mientras dura
//! (lo vigila `scripts/check-comandos.mjs`).

pub mod comandos;
pub mod db;
pub mod error;
pub mod identidad_movil;
pub mod importador_v1;
pub mod net;
pub mod paths;
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
fn importar_v1_en_segundo_plano(db: BaseDeDatos, rutas: Rutas, red: Arc<Red>) {
    let Some(v1) = RutasV1::estandar().filter(|v1| v1.base_de_datos().is_file()) else {
        return;
    };
    let lanzado = std::thread::Builder::new()
        .name("importador-v1".into())
        .spawn(move || {
            let env = v1.config.join(".env");
            let llavero = importador_v1::claves::LlaveroDelSistema;
            match importador_v1::importar(&v1.base_de_datos(), Some(&env), &db, &rutas, &llavero) {
                Ok(Some(_)) => red.cambiar_politica(politica_guardada(&db)),
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
    importar_v1_en_segundo_plano(db.clone(), rutas.clone(), Arc::clone(&red));

    let estado = Estado { rutas, red, db };

    tauri::Builder::default()
        .manage(estado)
        .invoke_handler(tauri::generate_handler![comandos::salud])
        .run(tauri::generate_context!())
        .expect("no se pudo arrancar la ventana de NB Sound");
}
