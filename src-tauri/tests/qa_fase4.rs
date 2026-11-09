//! Operaciones de Fase 4 que el arnés ejecuta sobre la copia QA.

use std::path::Path;

use nb_sound_lib::catalogo::etiquetas;
use nb_sound_lib::copia_seguridad;
use nb_sound_lib::db::BaseDeDatos;
use nb_sound_lib::paths::Rutas;
use serde_json::json;

fn db() -> BaseDeDatos {
    BaseDeDatos::abrir(Path::new(&std::env::var("NB_QA_DB").unwrap())).unwrap()
}

fn rutas() -> Rutas {
    Rutas::bajo(Path::new(&std::env::var("NB_QA_ROOT").unwrap())).unwrap()
}

fn resumen(db: &BaseDeDatos) -> serde_json::Value {
    let conn = db.conexion().unwrap();
    let uno = |sql: &str| -> i64 { conn.query_row(sql, [], |f| f.get(0)).unwrap() };
    json!({
        "pistas": uno("SELECT count(*) FROM pistas"),
        "albumes": uno("SELECT count(*) FROM albumes"),
        "artistas": uno("SELECT count(*) FROM artistas"),
        "playlists": uno("SELECT count(*) FROM playlists"),
        "historial": uno("SELECT count(*) FROM historial"),
        "correcciones": uno("SELECT count(*) FROM correcciones_catalogo")
    })
}

#[test]
#[ignore = "lo ejecuta scripts/qa/ui-qa.sh sobre la copia"]
fn crea_la_copia_desde_el_arnes() {
    let db = db();
    let antes = resumen(&db);
    let destino = std::env::var("NB_QA_BACKUP").unwrap();
    let creada = copia_seguridad::crear(&db, &rutas(), Path::new(&destino)).unwrap();
    println!(
        "INFORME_QA {}",
        json!({"caso":"copia_creada","datos":{"antes":antes,"bytes":creada.bytes,"portadas":creada.portadas}})
    );
}

#[test]
#[ignore = "lo ejecuta scripts/qa/ui-qa.sh sobre la copia"]
fn prepara_la_restauracion_desde_el_arnes() {
    let copia = std::env::var("NB_QA_BACKUP").unwrap();
    copia_seguridad::preparar_restauracion(&rutas(), Path::new(&copia)).unwrap();
    assert!(copia_seguridad::restauracion_pendiente(&rutas()));
    println!(
        "INFORME_QA {}",
        json!({"caso":"restauracion_preparada","datos":{"pendiente":true}})
    );
}

#[test]
#[ignore = "lo ejecuta scripts/qa/ui-qa.sh sobre la copia"]
fn lee_las_etiquetas_del_archivo_editado() {
    let ruta = std::env::var("NB_QA_ARCHIVO").unwrap();
    let (_, etiquetas) = etiquetas::leer(Path::new(&ruta)).unwrap();
    println!(
        "INFORME_QA {}",
        json!({
            "caso":"etiquetas_copiadas",
            "datos":{
                "titulo":etiquetas.titulo,
                "artista":etiquetas.artista,
                "album":etiquetas.album,
                "numero":etiquetas.numero,
                "isrc":etiquetas.isrc
            }
        })
    );
}
