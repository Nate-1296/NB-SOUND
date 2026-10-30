//! El importador contra una V1 sintética: el esquema real de la V1 con unas
//! pocas filas de cada clase y sus archivos en una carpeta temporal.

use std::path::{Path, PathBuf};

use rusqlite::Connection;

use super::{archivos, importar, Informe};
use crate::db::BaseDeDatos;
use crate::paths::Rutas;

const ESQUEMA_V1: &str = include_str!("../../tests/fixtures/esquema_v1.sql");

/// Un PNG mínimo, distinto para cada `n`.
fn png(ancho: u32, n: u8) -> Vec<u8> {
    let mut b = b"\x89PNG\r\n\x1a\n\0\0\0\x0dIHDR".to_vec();
    b.extend(ancho.to_be_bytes());
    b.extend(ancho.to_be_bytes());
    b.extend([8, 2, 0, 0, n]);
    b
}

struct Escenario {
    dir: PathBuf,
    base_v1: PathBuf,
    rutas: Rutas,
}

impl Drop for Escenario {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.dir);
    }
}

fn escenario(nombre: &str) -> Escenario {
    let dir = std::env::temp_dir().join(format!("ns-importador-{nombre}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    let musica = dir.join("Música");
    let assets = dir.join("assets");
    for d in [&musica, &assets.join("enrichment"), &dir.join("karaoke")] {
        std::fs::create_dir_all(d).unwrap();
    }
    let pista_a = musica.join("Banda Uno/Primer Disco/01 Apertura.mp3");
    let pista_b = musica.join("Banda Uno/Primer Disco/02 Cierre.mp3");
    std::fs::create_dir_all(pista_a.parent().unwrap()).unwrap();
    std::fs::write(&pista_a, b"audio a").unwrap();
    std::fs::write(&pista_b, b"audio b").unwrap();
    let normal = assets.join("normal.png");
    let hd = assets.join("hd.png");
    let avatar = assets.join("avatar.png");
    std::fs::write(&normal, png(300, 1)).unwrap();
    std::fs::write(&hd, png(1200, 2)).unwrap();
    std::fs::write(&avatar, png(500, 3)).unwrap();
    let instrumental = dir.join("karaoke/100.ogg");
    std::fs::write(&instrumental, b"instrumental").unwrap();
    let pendiente = dir.join("entrada/raro.mp3");
    std::fs::create_dir_all(pendiente.parent().unwrap()).unwrap();
    std::fs::write(&pendiente, b"raro").unwrap();

    let s = |p: &Path| p.to_string_lossy().into_owned();
    std::fs::write(
        assets.join("assets_manifest.jsonl"),
        format!(
            "{}\n",
            serde_json::json!({"release_id": "rel-1", "album_cover_hd": s(&hd),
                               "artista": "Banda Uno", "artist_avatar": s(&avatar)})
        ),
    )
    .unwrap();
    std::fs::write(
        assets.join("enrichment/enrichment_manifest.jsonl"),
        format!(
            "{}\n",
            serde_json::json!({"file": s(&pista_a), "timestamp": "2026-01-01",
                               "lyrics": {"plain_lyrics": "la la", "synced_lyrics": "[00:01.00] la la",
                                          "provider": "lrclib", "language": "es"}})
        ),
    )
    .unwrap();

    let base_v1 = dir.join("v1.sqlite3");
    let v1 = Connection::open(&base_v1).unwrap();
    v1.execute_batch(ESQUEMA_V1).unwrap();
    v1.execute_batch("PRAGMA journal_mode = WAL;").unwrap();
    let musica_con_barra = format!("{}/", s(&musica));
    v1.execute_batch(&format!(
        "INSERT INTO config_ui (clave, valor) VALUES
            ('dir_biblioteca', '{musica}'), ('dir_assets', '{assets}'),
            ('tema', 'sangre_dragon'), ('ui_font_family', 'Fira Sans'), ('ui_scale', '100'),
            ('volumen', '80'), ('modo_repeticion', 'todo'), ('modo_aleatorio', '1'),
            ('reproductor_pista_id', '101'), ('reproductor_pos_seg', '12.5'),
            ('eq_bandas', '[-1.6, 4.8]'), ('enable_lrclib', '1'), ('enable_lyrics_enrichment', '1'),
            ('enable_shazam', '0'), ('openai_key', 'sk-que-no-debe-salir'),
            ('ui_mode', 'pro');
         INSERT INTO artistas (id, nombre, nombre_slug, sync_version) VALUES (1, 'Banda Uno', 'banda-uno', 3);
         INSERT INTO albums (id, artista_id, titulo, titulo_slug, anio, mb_release_id, ruta_carpeta,
                             portada_ruta, sync_version)
             VALUES (10, 1, 'Primer Disco', 'primer-disco', 2001, 'rel-1', '{musica_con_barra}Banda Uno',
                     '{normal}', 4);
         INSERT INTO pistas (id, album_id, artista_id, titulo, artista_nombre, album_titulo,
                             duracion_seg, ruta_archivo, nombre_archivo, tamano_bytes, hash_sha256,
                             estado, favorita, favorita_actualizada_en, karaoke_estado,
                             karaoke_ruta_instrumental, sync_version)
             VALUES (100, 10, 1, 'Apertura', 'Banda Uno', 'Primer disco', 285.91020408163263,
                     '{a}', '01 Apertura.mp3', 7, '{sha}', 'biblioteca', 1,
                     '2026-06-04T08:38:33.000Z', 'lista', '{instrumental}', 0),
                    (101, 10, 1, 'Cierre', 'Banda Uno', 'Primer Disco', 200.0, '{b}',
                     '02 Cierre.mp3', 7, '{sha2}', 'duplicado', 0, NULL, 'en_cola', NULL, 5203);
         INSERT INTO playlists (id, nombre, tipo, subtipo, origen, es_anclada, sync_version)
             VALUES (5, 'Para correr', 'manual', 'usuario', 'usuario', 1, 9);
         INSERT INTO pistas_playlist (playlist_id, pista_id, posicion) VALUES (5, 101, 1), (5, 100, 2);
         INSERT INTO historial (id, pista_id, titulo_snap, artista_snap, duracion_seg, completada)
             VALUES (1, 100, 'Apertura', 'Banda Uno', 30.0, 0);
         INSERT INTO cola (posicion, pista_id) VALUES (0, 101);
         INSERT INTO track_audio_features (track_id, analyzer_version, analysis_mode, analysis_status,
                                           bpm, key_name, mode, energy, file_path)
             VALUES ('100', 'audio_basic_v3', 'light', 'ready', 120.0, 'G#', 'minor', 0.7, 'x'),
                    ('999', 'audio_basic_v3', 'light', 'ready', 90.0, 'C', 'major', 0.1, 'x'),
                    ('101', 'audio_basic_v3', 'light', 'failed', NULL, 'unknown', 'unknown', NULL, 'x');
         INSERT INTO track_deep_audio_features (track_id, analyzer_version, mood_happy, mood_sad,
                                                tags_json, raw_output_json)
             VALUES ('100', 'audio_intel_v2', 0.4, 0.1,
                     '{{\"tags_msd50\": [{{\"label\": \"pop\", \"score\": 0.17}},
                                         {{\"label\": \"rock\", \"score\": 0.19}}]}}',
                     '[1, 2, 3]');
         INSERT INTO track_vibe_tags (track_id, tag, score, confidence, source, analyzer_version)
             VALUES ('100', 'nocturna', 0.8, 0.9, 'basic_rules', 'v1'),
                    ('999', 'nocturna', 0.8, 0.9, 'basic_rules', 'v1');
         INSERT INTO sesiones_import (id, directorio_entrada, estado) VALUES (1, '/entrada', 'completado');
         INSERT INTO archivos_pendientes (id, ruta_archivo, nombre_archivo, tipo, causa, sesion_id, resuelto)
             VALUES (1, '{pendiente}', 'raro.mp3', 'revision', 'candidatos_ambiguos', 1, 0),
                    (2, '/no/existe.mp3', 'no.mp3', 'cuarentena', 'puntaje_bajo', 1, 0),
                    (3, '{pendiente}x', 'r.mp3', 'revision', 'puntaje_bajo', 1, 1);
         INSERT INTO sync_dispositivos (id, device_token, nombre, plataforma, revocado)
             VALUES (1, 'token-del-telefono', 'Pixel', 'android', 0),
                    (2, 'token-revocado', 'Viejo', 'android', 1);
         INSERT INTO sync_estado (clave, valor) VALUES ('sync_version_actual', '5217');
         INSERT INTO sync_tombstones (id, entidad, entidad_id, sync_version) VALUES (1, 'pista', 77, 40);
         INSERT INTO sync_stem_transfers (dispositivo_id, pista_id, estado, bytes_enviados)
             VALUES (1, 100, 'in_progress', 500);
         INSERT INTO dj_sesiones (id, prompt_original, estado, motor_version) VALUES (1, 'algo tranquilo', 'lista', 'dj_v1');
         INSERT INTO dj_pistas_sesion (sesion_id, posicion, pista_id) VALUES (1, 0, 100);",
        musica = s(&musica),
        assets = s(&assets),
        normal = s(&normal),
        a = s(&pista_a),
        b = s(&pista_b),
        sha = "a".repeat(64),
        sha2 = "b".repeat(64),
        instrumental = s(&instrumental),
        pendiente = s(&pendiente),
    ))
    .unwrap();
    drop(v1);

    let rutas = Rutas::bajo(&dir.join("v2")).unwrap();
    Escenario {
        dir,
        base_v1,
        rutas,
    }
}

fn importar_escenario(e: &Escenario) -> (BaseDeDatos, Informe) {
    let db = BaseDeDatos::abrir(&e.rutas.base_de_datos()).unwrap();
    let informe = importar(&e.base_v1, &db, &e.rutas)
        .expect("importa")
        .expect("primera vez");
    (db, informe)
}

fn valor<T: rusqlite::types::FromSql>(db: &BaseDeDatos, sql: &str) -> T {
    db.conexion()
        .unwrap()
        .query_row(sql, [], |f| f.get(0))
        .unwrap()
}

#[test]
fn la_base_de_la_v1_no_cambia_al_importar() {
    let e = escenario("intacta");
    let antes = archivos::sha256_de(&e.base_v1).unwrap();
    let _ = importar_escenario(&e);
    assert_eq!(archivos::sha256_de(&e.base_v1).unwrap(), antes);
}

#[test]
fn los_ids_y_las_sync_version_se_conservan() {
    let e = escenario("ids");
    let (db, informe) = importar_escenario(&e);
    assert_eq!(informe.filas["pistas"], 2);
    assert_eq!(
        valor::<i64>(&db, "SELECT sync_version FROM artistas WHERE id = 1"),
        3
    );
    assert_eq!(
        valor::<i64>(&db, "SELECT sync_version FROM albumes WHERE id = 10"),
        4
    );
    assert_eq!(
        valor::<i64>(&db, "SELECT sync_version FROM pistas WHERE id = 100"),
        0,
        "una pista con versión 0 no recibe otra"
    );
    assert_eq!(
        valor::<i64>(&db, "SELECT sync_version FROM pistas WHERE id = 101"),
        5203
    );
    assert_eq!(
        valor::<i64>(&db, "SELECT sync_version FROM playlists WHERE id = 5"),
        9
    );
    assert_eq!(
        valor::<i64>(&db, "SELECT version FROM sincronizacion"),
        5217
    );
    assert_eq!(valor::<i64>(&db, "SELECT pausada FROM sincronizacion"), 0);
    // Y el siguiente cambio de la V2 ya es mayor que todo lo de la V1.
    db.conexion()
        .unwrap()
        .execute("UPDATE pistas SET titulo = 'Otra' WHERE id = 100", [])
        .unwrap();
    assert_eq!(
        valor::<i64>(&db, "SELECT sync_version FROM pistas WHERE id = 100"),
        5218
    );
}

#[test]
fn las_pistas_conservan_lo_que_ve_el_movil() {
    let e = escenario("pistas");
    let (db, _) = importar_escenario(&e);
    let duracion: f64 = valor(&db, "SELECT duracion_seg FROM pistas WHERE id = 100");
    assert_eq!(duracion.to_bits(), 285.910_204_081_632_6_f64.to_bits());
    assert_eq!(
        valor::<String>(&db, "SELECT album_titulo FROM pistas WHERE id = 100"),
        "Primer disco",
        "el álbum como lo nombra la pista, aunque difiera del álbum"
    );
    assert_eq!(
        valor::<String>(&db, "SELECT ruta FROM pistas WHERE id = 100"),
        "Banda Uno/Primer Disco/01 Apertura.mp3"
    );
    assert_eq!(
        valor::<String>(&db, "SELECT carpeta FROM albumes WHERE id = 10"),
        "Banda Uno"
    );
    assert_eq!(
        valor::<String>(
            &db,
            "SELECT favorita_actualizada_en FROM pistas WHERE id = 100"
        ),
        "2026-06-04T08:38:33.000Z"
    );
    assert_eq!(
        valor::<String>(&db, "SELECT estado FROM pistas WHERE id = 101"),
        "duplicado"
    );
    assert_eq!(
        valor::<i64>(&db, "SELECT count(*) FROM pistas WHERE verificada = 1"),
        2
    );
}

#[test]
fn las_playlists_conservan_su_orden() {
    let e = escenario("orden");
    let (db, _) = importar_escenario(&e);
    let conn = db.conexion().unwrap();
    let mut s = conn
        .prepare("SELECT pista_id FROM playlist_pistas WHERE playlist_id = 5 ORDER BY posicion")
        .unwrap();
    let orden: Vec<i64> = s
        .query_map([], |f| f.get(0))
        .unwrap()
        .map(Result::unwrap)
        .collect();
    assert_eq!(orden, [101, 100]);
    assert_eq!(
        valor::<i64>(&db, "SELECT anclada FROM playlists WHERE id = 5"),
        1
    );
}

#[test]
fn las_letras_entran_en_la_base() {
    let e = escenario("letras");
    let (db, informe) = importar_escenario(&e);
    assert_eq!(informe.filas["letras"], 1);
    assert_eq!(
        valor::<String>(&db, "SELECT sincronizadas FROM letras WHERE pista_id = 100"),
        "[00:01.00] la la"
    );
    assert_eq!(
        valor::<String>(&db, "SELECT proveedor FROM letras WHERE pista_id = 100"),
        "lrclib"
    );
}

#[test]
fn cada_album_trae_su_portada_hd_y_cada_artista_su_imagen() {
    let e = escenario("portadas");
    let (db, _) = importar_escenario(&e);
    assert_eq!(
        valor::<i64>(
            &db,
            "SELECT p.ancho FROM albumes a JOIN portadas p ON p.id = a.portada_id WHERE a.id = 10"
        ),
        1200,
        "la HD, no la normal"
    );
    assert_eq!(
        valor::<i64>(
            &db,
            "SELECT p.ancho FROM artistas a JOIN portadas p ON p.id = a.imagen_id WHERE a.id = 1"
        ),
        500
    );
    let ruta: String = valor(&db, "SELECT ruta FROM portadas WHERE ancho = 1200");
    assert!(e.rutas.portadas().join(ruta).is_file());
}

#[test]
fn los_instrumentales_se_copian_y_la_cola_queda_pendiente() {
    let e = escenario("stems");
    let (db, _) = importar_escenario(&e);
    let instrumental: String = valor(&db, "SELECT instrumental FROM stems WHERE pista_id = 100");
    assert_eq!(
        std::fs::read(e.rutas.stems().join(instrumental)).unwrap(),
        b"instrumental"
    );
    assert_eq!(
        valor::<String>(&db, "SELECT estado FROM stems WHERE pista_id = 101"),
        "pendiente"
    );
    assert_eq!(
        valor::<String>(
            &db,
            "SELECT estado FROM transferencias_stems WHERE pista_id = 100"
        ),
        "pending",
        "una transferencia a medias se reinicia"
    );
}

#[test]
fn el_analisis_se_resume_y_se_descartan_los_huerfanos() {
    let e = escenario("analisis");
    let (db, informe) = importar_escenario(&e);
    assert_eq!(informe.filas["rasgos"], 1, "ni el huérfano ni el fallido");
    assert_eq!(informe.filas["etiquetas_ambiente"], 1);
    assert_eq!(
        valor::<String>(&db, "SELECT tonalidad FROM rasgos WHERE pista_id = 100"),
        "G#"
    );
    assert_eq!(
        valor::<String>(
            &db,
            "SELECT etiquetas FROM analisis_profundo WHERE pista_id = 100"
        ),
        r#"[["rock",0.19],["pop",0.17]]"#
    );
}

#[test]
fn los_tokens_de_los_telefonos_se_guardan_como_hash() {
    let e = escenario("tokens");
    let (db, informe) = importar_escenario(&e);
    assert_eq!(informe.filas["dispositivos"], 2, "también el revocado");
    let hash: String = valor(&db, "SELECT token_sha256 FROM dispositivos WHERE id = 1");
    assert_eq!(hash, super::sha256_texto("token-del-telefono"));
    let base = std::fs::read(e.rutas.base_de_datos()).unwrap();
    let en_claro = base.windows(18).any(|w| w == b"token-del-telefono");
    assert!(!en_claro, "el token no está en la base de la V2");
}

#[test]
fn ninguna_clave_de_servicio_entra_en_la_base() {
    let e = escenario("claves");
    let (db, _) = importar_escenario(&e);
    drop(db);
    let mut contenido = std::fs::read(e.rutas.base_de_datos()).unwrap();
    if let Ok(wal) = std::fs::read(format!("{}-wal", e.rutas.base_de_datos().display())) {
        contenido.extend(wal);
    }
    let fuga = contenido.windows(20).any(|w| w == b"sk-que-no-debe-salir");
    assert!(!fuga);
}

#[test]
fn las_preferencias_y_el_reproductor_tienen_su_tipo() {
    let e = escenario("preferencias");
    let (db, _) = importar_escenario(&e);
    assert_eq!(
        valor::<String>(&db, "SELECT valor FROM preferencias WHERE clave = 'tema'"),
        "\"sangre_dragon\""
    );
    assert_eq!(
        valor::<String>(
            &db,
            "SELECT valor FROM preferencias WHERE clave = 'ecualizador_bandas'"
        ),
        "[-1.6,4.8]"
    );
    assert_eq!(
        valor::<i64>(
            &db,
            "SELECT count(*) FROM preferencias WHERE clave = 'ui_mode'"
        ),
        0,
        "el modo Pro desaparece"
    );
    let politica: String = valor(
        &db,
        "SELECT valor FROM preferencias WHERE clave = 'politica_de_red'",
    );
    assert_eq!(politica, r#"{"general":true,"servicios":["lrclib"]}"#);
    assert_eq!(
        valor::<f64>(&db, "SELECT volumen FROM estado_reproductor"),
        0.8
    );
    assert_eq!(
        valor::<String>(&db, "SELECT repeticion FROM estado_reproductor"),
        "todo"
    );
    assert_eq!(
        valor::<i64>(&db, "SELECT pista_id FROM estado_reproductor"),
        101
    );
}

#[test]
fn por_revisar_trae_solo_lo_pendiente_que_existe() {
    let e = escenario("revisar");
    let (db, informe) = importar_escenario(&e);
    assert_eq!(informe.filas["por_revisar"], 1);
    assert_eq!(valor::<i64>(&db, "SELECT id FROM por_revisar"), 1);
    assert_eq!(
        valor::<i64>(&db, "SELECT importacion_id FROM por_revisar"),
        1
    );
    assert!(informe.archivos_ausentes >= 1);
}

#[test]
fn importar_dos_veces_no_hace_nada_la_segunda() {
    let e = escenario("dos-veces");
    let (db, _) = importar_escenario(&e);
    assert_eq!(importar(&e.base_v1, &db, &e.rutas), Ok(None));
    assert_eq!(valor::<i64>(&db, "SELECT count(*) FROM pistas"), 2);
}

#[test]
fn sin_base_de_la_v1_no_hay_nada_que_importar() {
    let e = escenario("sin-v1");
    let db = BaseDeDatos::abrir(&e.rutas.base_de_datos()).unwrap();
    assert_eq!(
        importar(&e.dir.join("no-existe.sqlite3"), &db, &e.rutas),
        Err(crate::error::NsError::FileNotFound)
    );
}
