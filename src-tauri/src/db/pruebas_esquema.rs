//! Propiedades del esquema que no dependen de ningún servicio: las restricciones
//! hacen su trabajo y cada índice lo usa la consulta que lo justifica.

use rusqlite::Connection;

use super::BaseDeDatos;

fn base() -> (
    BaseDeDatos,
    r2d2::PooledConnection<r2d2_sqlite::SqliteConnectionManager>,
) {
    let db = BaseDeDatos::en_memoria().expect("base");
    let conn = db.conexion().expect("conexión");
    (db, conn)
}

fn sembrar(conn: &Connection) {
    conn.execute_batch(
        "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'Banda Uno', 'banda-uno');
         INSERT INTO albumes (id, artista_id, titulo, clave) VALUES (10, 1, 'Primer Disco', 'primer-disco');
         INSERT INTO pistas (id, album_id, artista_id, titulo, ruta) VALUES (100, 10, 1, 'Apertura', 'a/b.mp3');",
    )
    .expect("siembra");
}

/// El plan de una consulta, aplanado, para comprobar qué índice usa.
fn plan(conn: &Connection, sql: &str) -> String {
    let mut sentencia = conn
        .prepare(&format!("EXPLAIN QUERY PLAN {sql}"))
        .expect("plan");
    let filas = sentencia
        .query_map([], |f| f.get::<_, String>(3))
        .expect("filas");
    filas
        .map(|f| f.expect("fila"))
        .collect::<Vec<_>>()
        .join(" | ")
}

#[test]
fn el_esquema_completo_no_deja_referencias_rotas() {
    let (_db, conn) = base();
    let violaciones: i64 = conn
        .query_row("SELECT count(*) FROM pragma_foreign_key_check", [], |f| {
            f.get(0)
        })
        .unwrap();
    assert_eq!(violaciones, 0);
}

#[test]
fn borrar_un_artista_con_albumes_se_rechaza() {
    let (_db, conn) = base();
    sembrar(&conn);
    assert!(conn
        .execute("DELETE FROM artistas WHERE id = 1", [])
        .is_err());
}

#[test]
fn borrar_un_album_deja_sus_pistas_sin_album() {
    let (_db, conn) = base();
    sembrar(&conn);
    conn.execute("DELETE FROM albumes WHERE id = 10", [])
        .unwrap();
    let album: Option<i64> = conn
        .query_row("SELECT album_id FROM pistas WHERE id = 100", [], |f| {
            f.get(0)
        })
        .unwrap();
    assert_eq!(album, None);
}

#[test]
fn borrar_una_pista_se_lleva_su_letra() {
    let (_db, conn) = base();
    sembrar(&conn);
    conn.execute(
        "INSERT INTO letras (pista_id, planas) VALUES (100, 'la la la')",
        [],
    )
    .unwrap();
    conn.execute("DELETE FROM pistas WHERE id = 100", [])
        .unwrap();
    let n: i64 = conn
        .query_row("SELECT count(*) FROM letras", [], |f| f.get(0))
        .unwrap();
    assert_eq!(n, 0);
}

#[test]
fn una_letra_vacia_no_se_guarda() {
    let (_db, conn) = base();
    sembrar(&conn);
    assert!(conn
        .execute(
            "INSERT INTO letras (pista_id, planas, sincronizadas) VALUES (100, '', NULL)",
            []
        )
        .is_err());
}

#[test]
fn una_pista_solo_admite_los_estados_conocidos() {
    let (_db, conn) = base();
    sembrar(&conn);
    assert!(conn
        .execute("UPDATE pistas SET estado = 'cuarentena' WHERE id = 100", [])
        .is_err());
    conn.execute("UPDATE pistas SET estado = 'duplicado' WHERE id = 100", [])
        .unwrap();
}

#[test]
fn por_revisar_solo_admite_causas_que_tienen_mensaje() {
    let (_db, conn) = base();
    assert!(conn
        .execute(
            "INSERT INTO por_revisar (ruta, causa) VALUES ('/x.mp3', 'otra_cosa')",
            []
        )
        .is_err());
    conn.execute(
        "INSERT INTO por_revisar (ruta, causa) VALUES ('/x.mp3', 'candidatos_ambiguos')",
        [],
    )
    .unwrap();
}

#[test]
fn la_duracion_conserva_toda_la_precision_de_la_v1() {
    let (_db, conn) = base();
    sembrar(&conn);
    // Tal como la escribe el JSON del contrato móvil.
    let v1: f64 = "285.91020408163263".parse().unwrap();
    conn.execute("UPDATE pistas SET duracion_seg = ?1 WHERE id = 100", [v1])
        .unwrap();
    let leida: f64 = conn
        .query_row("SELECT duracion_seg FROM pistas WHERE id = 100", [], |f| {
            f.get(0)
        })
        .unwrap();
    assert_eq!(leida.to_bits(), v1.to_bits());
}

#[test]
fn un_hash_que_no_es_sha256_se_rechaza() {
    let (_db, conn) = base();
    sembrar(&conn);
    assert!(conn
        .execute("UPDATE pistas SET sha256 = 'abc' WHERE id = 100", [])
        .is_err());
}

#[test]
fn el_manifiesto_movil_usa_el_indice_de_sync_version() {
    let (_db, conn) = base();
    for (tabla, indice) in [
        ("pistas", "pistas_por_sync_version"),
        ("albumes", "albumes_por_sync_version"),
        ("artistas", "artistas_por_sync_version"),
    ] {
        let p = plan(
            &conn,
            &format!("SELECT id FROM {tabla} WHERE sync_version > 5 ORDER BY sync_version"),
        );
        assert!(p.contains(indice), "{tabla}: {p}");
    }
}

#[test]
fn la_lista_de_canciones_se_ordena_con_su_indice() {
    let (_db, conn) = base();
    let p = plan(
        &conn,
        "SELECT id FROM pistas WHERE estado = 'biblioteca' \
         ORDER BY titulo COLLATE NOCASE LIMIT 256 OFFSET 512",
    );
    assert!(p.contains("pistas_por_titulo"), "{p}");
    assert!(!p.contains("TEMP B-TREE"), "ordena en memoria: {p}");
}

#[test]
fn el_detalle_de_un_album_sale_ordenado_de_su_indice() {
    let (_db, conn) = base();
    let p = plan(
        &conn,
        "SELECT id FROM pistas WHERE album_id = 10 ORDER BY disco, numero",
    );
    assert!(p.contains("pistas_por_album"), "{p}");
    assert!(!p.contains("TEMP B-TREE"), "ordena en memoria: {p}");
}

#[test]
fn las_favoritas_salen_del_indice_parcial() {
    let (_db, conn) = base();
    let p = plan(
        &conn,
        "SELECT id FROM pistas WHERE favorita = 1 ORDER BY favorita_actualizada_en DESC",
    );
    assert!(p.contains("pistas_favoritas"), "{p}");
}

#[test]
fn por_revisar_lista_lo_pendiente_sin_recorrer_lo_resuelto() {
    let (_db, conn) = base();
    let p = plan(
        &conn,
        "SELECT id FROM por_revisar WHERE resuelto_en IS NULL ORDER BY registrado_en",
    );
    assert!(p.contains("por_revisar_pendientes"), "{p}");
}

#[test]
fn una_pista_no_se_repite_en_una_playlist() {
    let (_db, conn) = base();
    sembrar(&conn);
    conn.execute(
        "INSERT INTO playlists (id, nombre) VALUES (5, 'Para correr')",
        [],
    )
    .unwrap();
    conn.execute(
        "INSERT INTO playlist_pistas (playlist_id, pista_id, posicion) VALUES (5, 100, 0)",
        [],
    )
    .unwrap();
    assert!(conn
        .execute(
            "INSERT INTO playlist_pistas (playlist_id, pista_id, posicion) VALUES (5, 100, 1)",
            []
        )
        .is_err());
}

#[test]
fn borrar_una_pista_la_saca_de_playlists_y_cola_pero_no_del_historial() {
    let (_db, conn) = base();
    sembrar(&conn);
    conn.execute_batch(
        "INSERT INTO playlists (id, nombre) VALUES (5, 'Para correr');
         INSERT INTO playlist_pistas (playlist_id, pista_id, posicion) VALUES (5, 100, 0);
         INSERT INTO cola (posicion, pista_id) VALUES (0, 100);
         INSERT INTO historial (pista_id, titulo, artista) VALUES (100, 'Apertura', 'Banda Uno');
         UPDATE estado_reproductor SET pista_id = 100;
         DELETE FROM pistas WHERE id = 100;",
    )
    .unwrap();
    let cuenta = |sql: &str| -> i64 { conn.query_row(sql, [], |f| f.get(0)).unwrap() };
    assert_eq!(cuenta("SELECT count(*) FROM playlist_pistas"), 0);
    assert_eq!(cuenta("SELECT count(*) FROM cola"), 0);
    assert_eq!(
        cuenta("SELECT count(*) FROM historial WHERE pista_id IS NULL AND titulo = 'Apertura'"),
        1
    );
    assert_eq!(
        cuenta("SELECT count(*) FROM estado_reproductor WHERE pista_id IS NULL"),
        1
    );
}

#[test]
fn el_estado_del_reproductor_es_una_sola_fila() {
    let (_db, conn) = base();
    assert!(conn
        .execute("INSERT INTO estado_reproductor (id) VALUES (2)", [])
        .is_err());
    assert!(conn
        .execute("UPDATE estado_reproductor SET volumen = 100", [])
        .is_err());
}

#[test]
fn una_preferencia_tiene_que_ser_json() {
    let (_db, conn) = base();
    assert!(conn
        .execute(
            "INSERT INTO preferencias (clave, valor) VALUES ('tema', 'oceano')",
            []
        )
        .is_err());
    conn.execute(
        "INSERT INTO preferencias (clave, valor) VALUES ('tema', '\"oceano\"')",
        [],
    )
    .unwrap();
}

#[test]
fn una_playlist_se_abre_en_orden_desde_su_indice() {
    let (_db, conn) = base();
    let p = plan(
        &conn,
        "SELECT pista_id FROM playlist_pistas WHERE playlist_id = 5 ORDER BY posicion",
    );
    assert!(p.contains("playlist_pistas_en_orden"), "{p}");
    assert!(!p.contains("TEMP B-TREE"), "ordena en memoria: {p}");
}

#[test]
fn los_recientes_salen_del_indice_por_fecha() {
    let (_db, conn) = base();
    let p = plan(
        &conn,
        "SELECT pista_id FROM historial ORDER BY reproducida_en DESC LIMIT 50",
    );
    assert!(p.contains("historial_por_fecha"), "{p}");
}

/// El presupuesto de ADR-004: menos de 16 KB de análisis por pista. Se mide en el
/// peor caso que el esquema admite (todas las columnas llenas, las etiquetas de
/// estilo al tope y cada etiqueta de ambiente por las dos fuentes) y sobre un
/// archivo real, porque lo que cuenta son las páginas que ocupa, no los bytes.
#[test]
fn el_analisis_de_una_pista_cabe_en_16_kb() {
    const PISTAS: i64 = 500;
    const ETIQUETAS: [&str; 11] = [
        "bailable",
        "concentracion",
        "energetica",
        "entrenamiento",
        "feliz",
        "fiesta",
        "intensa",
        "nocturna",
        "relajada",
        "tranquila",
        "triste",
    ];
    let dir = std::env::temp_dir().join(format!("ns-presupuesto-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let db = BaseDeDatos::abrir(&dir.join("base.sqlite")).unwrap();
    let mut conn = db.conexion().unwrap();
    let paginas = |conn: &Connection| -> i64 {
        conn.query_row("PRAGMA page_count", [], |f| f.get(0))
            .unwrap()
    };
    let tamano_pagina: i64 = conn
        .query_row("PRAGMA page_size", [], |f| f.get(0))
        .unwrap();

    {
        let tx = super::transaccion_de_escritura(&mut conn).unwrap();
        tx.execute(
            "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'a', 'a')",
            [],
        )
        .unwrap();
        for id in 1..=PISTAS {
            tx.execute(
                "INSERT INTO pistas (id, artista_id, titulo, ruta) VALUES (?1, 1, 't', ?2)",
                rusqlite::params![id, format!("{id}.mp3")],
            )
            .unwrap();
        }
        tx.commit().unwrap();
    }
    conn.execute_batch("PRAGMA wal_checkpoint(TRUNCATE)")
        .unwrap();
    let antes = paginas(&conn);

    let embedding = vec![0x3fu8; 200 * 4];
    let etiquetas = format!("[{}]", vec!["[\"classic rock\",0.123456789]"; 70].join(","));
    assert!(etiquetas.len() <= 2048, "{}", etiquetas.len());
    let sha = "f".repeat(64);
    {
        let tx = super::transaccion_de_escritura(&mut conn).unwrap();
        for id in 1..=PISTAS {
            let r = id as f64 + 0.123_456_789;
            tx.execute(
                "INSERT INTO rasgos VALUES (?1, 'audio_basic_v3', ?2, ?3, 512, ?3, 'G#', 'minor',
                 ?3, ?3, ?3, ?3, ?3, ?3, ?3, ?3, ?3, ?3, ?3, ?3, ?3, ?3, ?3, ?3, ?3, ?3, ?3, ?3,
                 '2026-10-30T00:00:00.000Z')",
                rusqlite::params![id, sha, r],
            )
            .unwrap();
            tx.execute(
                "INSERT INTO analisis_profundo VALUES (?1, 'musicnn_v1', ?2, 0.1, 0.2, 0.3, 0.4,
                 0.5, 0.6, 0.7, 0.8, ?3, 200, ?4, '2026-10-30T00:00:00.000Z')",
                rusqlite::params![id, sha, embedding, etiquetas],
            )
            .unwrap();
            tx.execute(
                "INSERT INTO sonoridad VALUES (?1, ?2, -9.5, -0.3, 7.2, '2026-10-30T00:00:00.000Z')",
                rusqlite::params![id, sha],
            )
            .unwrap();
            for etiqueta in ETIQUETAS {
                for fuente in ["basic_rules", "deep_model"] {
                    tx.execute(
                        "INSERT INTO etiquetas_ambiente VALUES (?1, ?2, ?3, 0.123456, 0.654321,
                         'audio_vibe_v1', '2026-10-30T00:00:00.000Z')",
                        rusqlite::params![id, etiqueta, fuente],
                    )
                    .unwrap();
                }
            }
        }
        tx.commit().unwrap();
    }
    conn.execute_batch("PRAGMA wal_checkpoint(TRUNCATE)")
        .unwrap();
    let por_pista = (paginas(&conn) - antes) * tamano_pagina / PISTAS;
    drop(conn);
    drop(db);
    let _ = std::fs::remove_dir_all(&dir);
    assert!(por_pista < 16 * 1024, "{por_pista} bytes por pista");
}

#[test]
fn un_embedding_que_no_cuadra_con_sus_dimensiones_se_rechaza() {
    let (_db, conn) = base();
    sembrar(&conn);
    assert!(conn
        .execute(
            "INSERT INTO analisis_profundo (pista_id, version, embedding, dimensiones)
             VALUES (100, 'v', zeroblob(799), 200)",
            []
        )
        .is_err());
}

#[test]
fn las_listas_por_animo_salen_del_indice_de_etiquetas() {
    let (_db, conn) = base();
    let p = plan(
        &conn,
        "SELECT pista_id FROM etiquetas_ambiente WHERE etiqueta = 'nocturna' \
         ORDER BY puntuacion DESC LIMIT 50",
    );
    assert!(p.contains("etiquetas_por_ambiente"), "{p}");
    assert!(!p.contains("TEMP B-TREE"), "ordena en memoria: {p}");
}

#[test]
fn un_color_de_portada_que_no_es_hexadecimal_se_rechaza() {
    let (_db, conn) = base();
    let sha = "a".repeat(64);
    assert!(conn
        .execute(
            "INSERT INTO portadas (sha256, ruta, ancho, alto, bytes, mime, origen, color)
             VALUES (?1, 'x.jpg', 1, 1, 1, 'image/jpeg', 'v1', 'rojo')",
            [&sha]
        )
        .is_err());
    conn.execute(
        "INSERT INTO portadas (sha256, ruta, ancho, alto, bytes, mime, origen, color)
         VALUES (?1, 'x.jpg', 1, 1, 1, 'image/jpeg', 'v1', '#1a2b3c')",
        [&sha],
    )
    .unwrap();
}

fn version_de(conn: &Connection, tabla: &str, id: i64) -> i64 {
    conn.query_row(
        &format!("SELECT sync_version FROM {tabla} WHERE id = ?1"),
        [id],
        |f| f.get(0),
    )
    .unwrap()
}

fn contador(conn: &Connection) -> i64 {
    conn.query_row("SELECT version FROM sincronizacion", [], |f| f.get(0))
        .unwrap()
}

#[test]
fn cada_alta_recibe_una_sync_version_nueva() {
    let (_db, conn) = base();
    sembrar(&conn);
    let (artista, album, pista) = (
        version_de(&conn, "artistas", 1),
        version_de(&conn, "albumes", 10),
        version_de(&conn, "pistas", 100),
    );
    assert!(artista > 0 && album > artista && pista > album);
    assert_eq!(contador(&conn), pista);
}

#[test]
fn solo_los_cambios_que_ve_el_movil_suben_la_version() {
    let (_db, conn) = base();
    sembrar(&conn);
    let antes = version_de(&conn, "pistas", 100);
    conn.execute(
        "UPDATE pistas SET reproducciones = reproducciones + 1 WHERE id = 100",
        [],
    )
    .unwrap();
    assert_eq!(version_de(&conn, "pistas", 100), antes);
    conn.execute(
        "UPDATE pistas SET favorita = 1, favorita_actualizada_en = '2026-10-30T00:00:00.000Z' \
         WHERE id = 100",
        [],
    )
    .unwrap();
    assert!(version_de(&conn, "pistas", 100) > antes);
}

#[test]
fn borrar_un_album_sube_la_version_de_sus_pistas_y_deja_tumba() {
    let (_db, conn) = base();
    sembrar(&conn);
    let antes = version_de(&conn, "pistas", 100);
    conn.execute("DELETE FROM albumes WHERE id = 10", [])
        .unwrap();
    assert!(version_de(&conn, "pistas", 100) > antes);
    let tumba: i64 = conn
        .query_row(
            "SELECT sync_version FROM tumbas WHERE entidad = 'album' AND entidad_id = 10",
            [],
            |f| f.get(0),
        )
        .unwrap();
    assert!(tumba > antes);
}

#[test]
fn borrar_una_pista_deja_tumba_y_cambia_sus_playlists() {
    let (_db, conn) = base();
    sembrar(&conn);
    conn.execute_batch(
        "INSERT INTO playlists (id, nombre) VALUES (5, 'Para correr');
         INSERT INTO playlist_pistas (playlist_id, pista_id, posicion) VALUES (5, 100, 0);",
    )
    .unwrap();
    let antes = version_de(&conn, "playlists", 5);
    conn.execute("DELETE FROM pistas WHERE id = 100", [])
        .unwrap();
    assert!(version_de(&conn, "playlists", 5) > antes);
    let tumbas: i64 = conn
        .query_row(
            "SELECT count(*) FROM tumbas WHERE entidad = 'pista' AND entidad_id = 100",
            [],
            |f| f.get(0),
        )
        .unwrap();
    assert_eq!(tumbas, 1);
}

#[test]
fn reordenar_una_playlist_es_un_cambio_de_la_playlist() {
    let (_db, conn) = base();
    sembrar(&conn);
    conn.execute_batch(
        "INSERT INTO playlists (id, nombre) VALUES (5, 'Para correr');
         INSERT INTO playlist_pistas (playlist_id, pista_id, posicion) VALUES (5, 100, 0);",
    )
    .unwrap();
    let antes = version_de(&conn, "playlists", 5);
    conn.execute("UPDATE playlist_pistas SET posicion = 3", [])
        .unwrap();
    assert!(version_de(&conn, "playlists", 5) > antes);
}

/// El importador copia las filas de la V1 con su `sync_version`: si recibieran
/// una nueva, el móvil volvería a descargar la biblioteca entera.
#[test]
fn con_la_sincronizacion_pausada_se_conserva_la_version_de_la_v1() {
    let (_db, conn) = base();
    conn.execute_batch(
        "UPDATE sincronizacion SET pausada = 1, version = 5217;
         INSERT INTO artistas (id, nombre, clave, sync_version) VALUES (1, 'a', 'a', 7);
         INSERT INTO pistas (id, artista_id, titulo, ruta, sync_version) VALUES (100, 1, 't', 'x', 5203);
         UPDATE sincronizacion SET pausada = 0;",
    )
    .unwrap();
    assert_eq!(version_de(&conn, "artistas", 1), 7);
    assert_eq!(version_de(&conn, "pistas", 100), 5203);
    assert_eq!(contador(&conn), 5217);
    conn.execute("UPDATE pistas SET titulo = 'u' WHERE id = 100", [])
        .unwrap();
    assert_eq!(version_de(&conn, "pistas", 100), 5218);
}

#[test]
fn un_dispositivo_guarda_el_hash_del_token_y_no_el_token() {
    let (_db, conn) = base();
    assert!(conn
        .execute(
            "INSERT INTO dispositivos (token_sha256, nombre) VALUES ('token-en-claro', 'tel')",
            []
        )
        .is_err());
}

#[test]
fn el_manifiesto_pide_las_tumbas_por_su_indice() {
    let (_db, conn) = base();
    let p = plan(
        &conn,
        "SELECT entidad, entidad_id FROM tumbas WHERE sync_version > 5 ORDER BY sync_version",
    );
    assert!(p.contains("tumbas_por_sync_version"), "{p}");
}

#[test]
fn una_pista_lista_para_cantar_tiene_su_instrumental() {
    let (_db, conn) = base();
    sembrar(&conn);
    assert!(conn
        .execute(
            "INSERT INTO stems (pista_id, estado) VALUES (100, 'lista')",
            []
        )
        .is_err());
    assert!(conn
        .execute(
            "INSERT INTO stems (pista_id, estado, instrumental) VALUES (100, 'pendiente', 'x.ogg')",
            []
        )
        .is_err());
}

#[test]
fn terminar_una_separacion_es_un_cambio_que_ve_el_movil() {
    let (_db, conn) = base();
    sembrar(&conn);
    conn.execute("INSERT INTO stems (pista_id) VALUES (100)", [])
        .unwrap();
    let antes = version_de(&conn, "pistas", 100);
    conn.execute(
        "UPDATE stems SET intentos = 1, estado = 'separando' WHERE pista_id = 100",
        [],
    )
    .unwrap();
    assert_eq!(
        version_de(&conn, "pistas", 100),
        antes,
        "separando no cambia nada"
    );
    conn.execute(
        "UPDATE stems SET estado = 'lista', instrumental = '100.ogg' WHERE pista_id = 100",
        [],
    )
    .unwrap();
    let lista = version_de(&conn, "pistas", 100);
    assert!(lista > antes);
    conn.execute("DELETE FROM stems WHERE pista_id = 100", [])
        .unwrap();
    assert!(version_de(&conn, "pistas", 100) > lista);
}

#[test]
fn la_cola_de_separacion_sale_de_su_indice() {
    let (_db, conn) = base();
    let p = plan(
        &conn,
        "SELECT pista_id FROM stems WHERE estado = 'pendiente' ORDER BY solicitada_en LIMIT 1",
    );
    assert!(p.contains("stems_por_estado"), "{p}");
    assert!(!p.contains("TEMP B-TREE"), "ordena en memoria: {p}");
}

#[test]
fn borrar_una_sesion_del_dj_se_lleva_sus_pistas_y_eventos() {
    let (_db, conn) = base();
    sembrar(&conn);
    conn.execute_batch(
        "INSERT INTO dj_sesiones (id, peticion, motor_version) VALUES (1, 'algo tranquilo', 'dj_v1');
         INSERT INTO dj_sesion_pistas (sesion_id, posicion, pista_id) VALUES (1, 0, 100);
         INSERT INTO dj_eventos (sesion_id, pista_id, tipo) VALUES (1, 100, 'saltada');
         UPDATE dj_en_curso SET sesion_id = 1, indice = 0;
         DELETE FROM dj_sesiones WHERE id = 1;",
    )
    .unwrap();
    let cuenta = |sql: &str| -> i64 { conn.query_row(sql, [], |f| f.get(0)).unwrap() };
    assert_eq!(cuenta("SELECT count(*) FROM dj_sesion_pistas"), 0);
    assert_eq!(cuenta("SELECT count(*) FROM dj_eventos"), 0);
    assert_eq!(
        cuenta("SELECT count(*) FROM dj_en_curso WHERE sesion_id IS NULL"),
        1
    );
}
