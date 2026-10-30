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
