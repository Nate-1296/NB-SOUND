//! Prueba de conservación sobre la instalación real de la V1 (F1.2.5).
//!
//! Se salta sola si no hay V1 en esta máquina o si no se le da dónde escribir:
//! copia las portadas y los instrumentales, varios GB, y no puede ir a un `/tmp`
//! en memoria. Se ejecuta con
//!
//! ```text
//! NB_SOUND_PRUEBA_REAL=/una/carpeta/en/disco cargo test --test importacion_real -- --nocapture
//! ```
//!
//! No imprime nada de la biblioteca: solo cifras.

use std::collections::BTreeMap;
use std::path::PathBuf;

use nb_sound_lib::db::BaseDeDatos;
use nb_sound_lib::importador_v1::{archivos, importar};
use nb_sound_lib::paths::{Rutas, RutasV1};
use rusqlite::{Connection, OpenFlags};

fn v1_en_solo_lectura(ruta: &std::path::Path) -> Connection {
    Connection::open_with_flags(ruta, OpenFlags::SQLITE_OPEN_READ_ONLY).unwrap()
}

fn cuenta(conn: &Connection, sql: &str) -> i64 {
    conn.query_row(sql, [], |f| f.get(0)).unwrap()
}

fn secuencias(conn: &Connection, sql: &str) -> BTreeMap<i64, Vec<i64>> {
    let mut s = conn.prepare(sql).unwrap();
    let mut mapa: BTreeMap<i64, Vec<i64>> = BTreeMap::new();
    for fila in s
        .query_map([], |f| Ok((f.get::<_, i64>(0)?, f.get::<_, i64>(1)?)))
        .unwrap()
    {
        let (playlist, pista) = fila.unwrap();
        mapa.entry(playlist).or_default().push(pista);
    }
    mapa
}

#[test]
fn la_instalacion_real_se_importa_sin_perder_nada() {
    let Some(base_v1) = RutasV1::estandar()
        .map(|r| r.base_de_datos())
        .filter(|b| b.is_file())
    else {
        eprintln!("sin V1 en esta máquina: se salta");
        return;
    };
    let Some(destino) = std::env::var_os("NB_SOUND_PRUEBA_REAL").map(PathBuf::from) else {
        eprintln!("NB_SOUND_PRUEBA_REAL no está definida: se salta");
        return;
    };
    let _ = std::fs::remove_dir_all(&destino);
    let rutas = Rutas::bajo(&destino).unwrap();
    let hash_antes = archivos::sha256_de(&base_v1).unwrap();

    let inicio = std::time::Instant::now();
    let db = BaseDeDatos::abrir(&rutas.base_de_datos()).unwrap();
    let informe = importar(&base_v1, &db, &rutas).unwrap().unwrap();
    eprintln!("importada en {:.1} s", inicio.elapsed().as_secs_f64());
    eprintln!("{}", serde_json::to_string_pretty(&informe).unwrap());

    let v1 = v1_en_solo_lectura(&base_v1);
    let conn = db.conexion().unwrap();

    // Fila a fila contra la V1, no contra cifras escritas a mano: la V1 sigue en
    // uso y crece.
    for (v2, sql_v1) in [
        ("artistas", "SELECT count(*) FROM artistas"),
        ("albumes", "SELECT count(*) FROM albums"),
        ("pistas", "SELECT count(*) FROM pistas"),
        ("playlists", "SELECT count(*) FROM playlists"),
        ("playlist_pistas", "SELECT count(*) FROM pistas_playlist"),
        ("historial", "SELECT count(*) FROM historial"),
        ("cola", "SELECT count(*) FROM cola"),
        ("dispositivos", "SELECT count(*) FROM sync_dispositivos"),
        ("tumbas", "SELECT count(*) FROM sync_tombstones"),
        ("dj_sesiones", "SELECT count(*) FROM dj_sesiones"),
        ("dj_sesion_pistas", "SELECT count(*) FROM dj_pistas_sesion"),
    ] {
        assert_eq!(informe.filas[v2], cuenta(&v1, sql_v1), "{v2}");
    }

    // Los identificadores y las versiones, uno por uno.
    for (v2, v1_tabla) in [
        ("artistas", "artistas"),
        ("albumes", "albums"),
        ("pistas", "pistas"),
        ("playlists", "playlists"),
    ] {
        let v1_suma: f64 = v1
            .query_row(
                &format!("SELECT total(id * 1000003.0 + sync_version) FROM {v1_tabla}"),
                [],
                |f| f.get(0),
            )
            .unwrap();
        let v2_suma: f64 = conn
            .query_row(
                &format!("SELECT total(id * 1000003.0 + sync_version) FROM {v2}"),
                [],
                |f| f.get(0),
            )
            .unwrap();
        assert_eq!(v1_suma, v2_suma, "{v2}: ids o sync_version distintos");
    }
    let version_v1: i64 = v1
        .query_row(
            "SELECT CAST(valor AS INTEGER) FROM sync_estado WHERE clave = 'sync_version_actual'",
            [],
            |f| f.get(0),
        )
        .unwrap();
    assert_eq!(
        cuenta(&conn, "SELECT version FROM sincronizacion"),
        version_v1
    );

    assert_eq!(
        secuencias(
            &conn,
            "SELECT playlist_id, pista_id FROM playlist_pistas ORDER BY playlist_id, posicion, pista_id"
        ),
        secuencias(
            &v1,
            "SELECT playlist_id, pista_id FROM pistas_playlist ORDER BY playlist_id, posicion, pista_id"
        ),
        "el orden de alguna playlist cambió"
    );

    // Lo que vivía fuera de la base.
    let con_portada_v1 = cuenta(
        &v1,
        "SELECT count(*) FROM albums WHERE coalesce(portada_ruta, '') <> ''",
    );
    assert_eq!(
        cuenta(
            &conn,
            "SELECT count(*) FROM albumes WHERE portada_id IS NOT NULL"
        ),
        con_portada_v1
    );
    assert_eq!(
        cuenta(
            &conn,
            "SELECT count(*) FROM artistas WHERE imagen_id IS NOT NULL"
        ),
        cuenta(&v1, "SELECT count(*) FROM artistas")
    );
    assert_eq!(
        cuenta(&conn, "SELECT count(*) FROM stems WHERE estado = 'lista'"),
        cuenta(
            &v1,
            "SELECT count(*) FROM pistas WHERE coalesce(karaoke_ruta_instrumental, '') <> ''"
        )
    );
    assert!(informe.filas["letras"] > 0);

    drop(conn);
    drop(db);
    assert_eq!(
        archivos::sha256_de(&base_v1).unwrap(),
        hash_antes,
        "la base de la V1 cambió"
    );
    let tamano = std::fs::metadata(rutas.base_de_datos()).unwrap().len();
    eprintln!("base de la V2: {:.1} MB", tamano as f64 / 1e6);
    assert!(tamano < 40 * 1024 * 1024, "{tamano} bytes");
}
