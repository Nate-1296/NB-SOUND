# =============================================================================
# db/esquema.py
#
# Esquema SQLite de la base de datos local de Music Hub.
#
# La BD actua como indice rapido de la biblioteca fisica, historial de
# reproduccion, estado de la cola, playlists y estadisticas de uso.
# No reemplaza los tags ID3 — los tags del archivo siguen siendo la fuente
# de verdad. La BD se puede reconstruir completamente con un rescan.
#
# Tablas:
#   - artistas         : artistas indexados
#   - albums           : albumes indexados
#   - pistas           : tracks individuales con metadata completa
#   - playlists        : listas de reproduccion (manuales)
#   - pistas_playlist  : tabla de relacion playlist<->pista (orden)
#   - historial        : cada reproduccion registrada
#   - cola             : estado persistente de la cola de reproduccion
#   - sesiones_import  : registro de cada importacion ejecutada
#   - config_ui        : preferencias de la interfaz (clave/valor)
# =============================================================================

CREAR_TABLAS_SQL = """
-- -------------------------------------------------------------------------
-- ARTISTAS
-- nombre_slug: version normalizada del nombre usada como clave unica para
-- evitar duplicados por variaciones de capitalización o acentos.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS artistas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre         TEXT    NOT NULL,
    nombre_slug    TEXT    NOT NULL UNIQUE,
    mb_artist_id   TEXT,
    creado_en      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_artistas_slug ON artistas(nombre_slug);

-- -------------------------------------------------------------------------
-- ALBUMS
-- tipo: refleja el primary type de MusicBrainz (Album, Single, EP, otros).
-- ruta_carpeta: directorio fisico donde residen los archivos del album.
-- UNIQUE(artista_id, titulo_slug): un artista no puede tener dos albums con
-- el mismo slug, lo que previene duplicados por re-escaneos.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS albums (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    artista_id     INTEGER NOT NULL REFERENCES artistas(id) ON DELETE CASCADE,
    titulo         TEXT    NOT NULL,
    titulo_slug    TEXT    NOT NULL,
    tipo           TEXT    NOT NULL DEFAULT 'Album',  -- Album, Single, EP, otros
    anio           INTEGER,
    mb_release_id  TEXT,
    ruta_carpeta   TEXT,
    portada_ruta   TEXT,
    creado_en      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(artista_id, titulo_slug)
);
CREATE INDEX IF NOT EXISTS idx_albums_artista ON albums(artista_id);
CREATE INDEX IF NOT EXISTS idx_albums_tipo    ON albums(tipo);
CREATE INDEX IF NOT EXISTS idx_albums_titulo  ON albums(titulo COLLATE NOCASE);

-- -------------------------------------------------------------------------
-- PISTAS
-- ruta_archivo: clave unica de identidad fisica del archivo. Es la unica
-- columna que nunca debe repetirse; el sistema la usa para detectar
-- reimportaciones del mismo archivo.
-- hash_sha256: permite detectar duplicados binarios exactos aunque la ruta
-- cambie (p.ej. el usuario mueve o renombra el archivo manualmente).
-- artista_nombre / album_titulo: columnas desnormalizadas para evitar JOINs
-- en consultas frecuentes del reproductor. Se mantienen sincronizadas
-- con las tablas artistas/albums via la capa de servicio.
-- estado: ciclo de vida del archivo dentro de la biblioteca.
-- karaoke_estado: cache del estado del job de separacion voz/instrumental.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pistas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id            INTEGER REFERENCES albums(id) ON DELETE SET NULL,
    artista_id          INTEGER REFERENCES artistas(id) ON DELETE SET NULL,
    titulo              TEXT    NOT NULL,
    artista_nombre      TEXT    NOT NULL DEFAULT '',
    album_titulo        TEXT    NOT NULL DEFAULT '',
    track_number        INTEGER,
    duracion_seg        REAL,
    bitrate_kbps        INTEGER,
    anio                INTEGER,
    genero              TEXT,
    isrc                TEXT,
    ruta_archivo        TEXT    NOT NULL UNIQUE,
    nombre_archivo      TEXT    NOT NULL,
    tamano_bytes        INTEGER NOT NULL DEFAULT 0,
    hash_sha256         TEXT,
    mb_recording_id     TEXT,
    mb_release_id       TEXT,
    mb_release_type     TEXT,
    tagger_fuentes      TEXT,
    estado              TEXT    NOT NULL DEFAULT 'biblioteca',
    -- estado: biblioteca | revision | cuarentena
    veces_reproducida   INTEGER NOT NULL DEFAULT 0,
    ultimo_acceso       TEXT,
    favorita            INTEGER NOT NULL DEFAULT 0,  -- 0/1 booleano
    karaoke_estado      TEXT    NOT NULL DEFAULT 'no_procesada',
    -- karaoke_estado: no_procesada | en_cola | procesando | lista | fallida | no_aplica
    karaoke_ruta_instrumental TEXT,
    karaoke_actualizado_en TEXT,
    karaoke_error_codigo    TEXT,
    karaoke_error_mensaje   TEXT,
    indexado_en         TEXT    NOT NULL DEFAULT (datetime('now')),
    actualizado_en      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pistas_album     ON pistas(album_id);
CREATE INDEX IF NOT EXISTS idx_pistas_artista   ON pistas(artista_id);
CREATE INDEX IF NOT EXISTS idx_pistas_estado    ON pistas(estado);
CREATE INDEX IF NOT EXISTS idx_pistas_favorita  ON pistas(favorita);
CREATE INDEX IF NOT EXISTS idx_pistas_hash      ON pistas(hash_sha256);
CREATE INDEX IF NOT EXISTS idx_pistas_titulo    ON pistas(titulo COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_pistas_artista_n ON pistas(artista_nombre COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_pistas_ruta      ON pistas(ruta_archivo);

-- -------------------------------------------------------------------------
-- FTS5 para busqueda universal rapida
-- content='pistas' / content_rowid='id': tabla de contenido externo.
-- SQLite no mantiene el indice FTS automaticamente; los triggers de abajo
-- se encargan de mantenerlo sincronizado ante INSERT, DELETE y UPDATE.
-- Consultar siempre via "pistas_fts MATCH ?" para aprovechar el indice.
-- -------------------------------------------------------------------------
CREATE VIRTUAL TABLE IF NOT EXISTS pistas_fts USING fts5(
    titulo,
    artista_nombre,
    album_titulo,
    genero,
    content='pistas',
    content_rowid='id'
);

-- Triggers para mantener FTS sincronizado
CREATE TRIGGER IF NOT EXISTS pistas_fts_insert
    AFTER INSERT ON pistas BEGIN
        INSERT INTO pistas_fts(rowid, titulo, artista_nombre, album_titulo, genero)
        VALUES (new.id, new.titulo, new.artista_nombre, new.album_titulo, coalesce(new.genero,''));
    END;

CREATE TRIGGER IF NOT EXISTS pistas_fts_delete
    AFTER DELETE ON pistas BEGIN
        INSERT INTO pistas_fts(pistas_fts, rowid, titulo, artista_nombre, album_titulo, genero)
        VALUES ('delete', old.id, old.titulo, old.artista_nombre, old.album_titulo, coalesce(old.genero,''));
    END;

CREATE TRIGGER IF NOT EXISTS pistas_fts_update
    AFTER UPDATE ON pistas BEGIN
        INSERT INTO pistas_fts(pistas_fts, rowid, titulo, artista_nombre, album_titulo, genero)
        VALUES ('delete', old.id, old.titulo, old.artista_nombre, old.album_titulo, coalesce(old.genero,''));
        INSERT INTO pistas_fts(rowid, titulo, artista_nombre, album_titulo, genero)
        VALUES (new.id, new.titulo, new.artista_nombre, new.album_titulo, coalesce(new.genero,''));
    END;

-- -------------------------------------------------------------------------
-- PLAYLISTS
-- tipo: "manual" (creada por el usuario) | "automatica" (generada por regla)
--       | "sistema" (ancla de navegacion interna, no visible directamente).
-- regla_json: JSON con criterios de la playlist automatica. Vacio en manuales.
-- auto_key: clave semantica unica para playlists del sistema (p.ej.
--   "recientes", "favoritas"). Permite localizarlas sin depender del id.
-- es_anclada: si 1, la playlist aparece siempre en posicion fija en la UI.
-- visible: si 0, la playlist existe pero no se muestra al usuario.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS playlists (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre      TEXT    NOT NULL,
    descripcion TEXT,
    tipo        TEXT    NOT NULL DEFAULT 'manual',  -- manual | automatica | sistema
    subtipo     TEXT,
    origen      TEXT    NOT NULL DEFAULT 'usuario', -- usuario | sistema | generado
    regla_json  TEXT,   -- JSON con regla para playlists automaticas
    auto_key    TEXT,
    es_anclada  INTEGER NOT NULL DEFAULT 0,
    anclada_en  TEXT,
    visible     INTEGER NOT NULL DEFAULT 1,
    portada_ruta TEXT,
    ultima_generacion_en TEXT,
    auto_actualizable INTEGER NOT NULL DEFAULT 0,
    editada_por_usuario INTEGER NOT NULL DEFAULT 0,
    creado_en   TEXT    NOT NULL DEFAULT (datetime('now')),
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_playlists_tipo ON playlists(tipo);
CREATE INDEX IF NOT EXISTS idx_playlists_subtipo ON playlists(subtipo);
CREATE INDEX IF NOT EXISTS idx_playlists_auto_key ON playlists(auto_key);
CREATE INDEX IF NOT EXISTS idx_playlists_visible ON playlists(visible);

CREATE TABLE IF NOT EXISTS pistas_playlist (
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    pista_id    INTEGER NOT NULL REFERENCES pistas(id)    ON DELETE CASCADE,
    posicion    INTEGER NOT NULL DEFAULT 0,
    agregado_en TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (playlist_id, pista_id)
);
CREATE INDEX IF NOT EXISTS idx_pp_playlist ON pistas_playlist(playlist_id, posicion);

-- -------------------------------------------------------------------------
-- HISTORIAL DE REPRODUCCION
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historial (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    pista_id      INTEGER REFERENCES pistas(id) ON DELETE SET NULL,
    titulo_snap   TEXT,   -- snapshot del titulo al momento de reproducir
    artista_snap  TEXT,
    reproducido_en TEXT NOT NULL DEFAULT (datetime('now')),
    duracion_seg  REAL,
    completada    INTEGER NOT NULL DEFAULT 1  -- 1 si se escucho completa, 0 si se salto
);
CREATE INDEX IF NOT EXISTS idx_historial_pista  ON historial(pista_id);
CREATE INDEX IF NOT EXISTS idx_historial_fecha  ON historial(reproducido_en);

-- -------------------------------------------------------------------------
-- COLA DE REPRODUCCION
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cola (
    posicion    INTEGER PRIMARY KEY,
    pista_id    INTEGER NOT NULL REFERENCES pistas(id) ON DELETE CASCADE,
    agregado_en TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Estado actual del reproductor (singleton)
CREATE TABLE IF NOT EXISTS estado_reproductor (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

-- -------------------------------------------------------------------------
-- SESIONES DE IMPORTACION
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sesiones_import (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    directorio_entrada  TEXT    NOT NULL,
    iniciado_en         TEXT    NOT NULL DEFAULT (datetime('now')),
    finalizado_en       TEXT,
    total_descubiertos  INTEGER NOT NULL DEFAULT 0,
    total_aceptados     INTEGER NOT NULL DEFAULT 0,
    total_revision      INTEGER NOT NULL DEFAULT 0,
    total_cuarentena    INTEGER NOT NULL DEFAULT 0,
    total_errores       INTEGER NOT NULL DEFAULT 0,
    estado              TEXT    NOT NULL DEFAULT 'en_progreso',
    reporte_json        TEXT    -- JSON del ResultadoEjecucion completo
);

-- -------------------------------------------------------------------------
-- REVISION Y CUARENTENA — registro de archivos pendientes
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS archivos_pendientes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ruta_archivo    TEXT    NOT NULL UNIQUE,
    nombre_archivo  TEXT    NOT NULL,
    tipo            TEXT    NOT NULL,  -- revision | cuarentena
    causa           TEXT    NOT NULL,
    manifiesto_json TEXT,             -- JSON del manifiesto del tagger
    sesion_id       INTEGER REFERENCES sesiones_import(id) ON DELETE SET NULL,
    registrado_en   TEXT    NOT NULL DEFAULT (datetime('now')),
    resuelto        INTEGER NOT NULL DEFAULT 0,
    resuelto_en     TEXT
);
CREATE INDEX IF NOT EXISTS idx_pendientes_tipo     ON archivos_pendientes(tipo);
CREATE INDEX IF NOT EXISTS idx_pendientes_resuelto ON archivos_pendientes(resuelto);

-- -------------------------------------------------------------------------
-- PREFERENCIAS DE LA UI
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS config_ui (
    clave     TEXT PRIMARY KEY,
    valor     TEXT NOT NULL,
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Valores iniciales de configuracion
INSERT OR IGNORE INTO config_ui(clave, valor) VALUES
    ('tema',                  'oscuro'),
    ('volumen',               '100'),
    ('modo_repeticion',       'ninguno'),
    ('modo_aleatorio',        '0'),
    ('vista_biblioteca',      'album'),
    ('vista_biblioteca_estado', '{"seccion":"albums","grupo_albums":"albums","detalle":"","album_id":0,"artista_id":0,"filtro_albums":"","filtro_artistas":"","filtro_pistas":"","solo_favoritas":false,"orden_pistas":"titulo","orden_albums":"artista","orden_artistas":"nombre","scroll_albums":0,"scroll_artistas":0,"scroll_pistas":0}'),
    ('panel_derecho_visible', '0'),
    ('ultima_vista',          'inicio');

-- -------------------------------------------------------------------------
-- OVERRIDES OPERATIVOS (memoria persistente de decisiones manuales)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS overrides_catalogacion (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    match_type       TEXT    NOT NULL,   -- hash | isrc | recording_mbid | artist_title
    match_value      TEXT    NOT NULL,
    payload_json     TEXT    NOT NULL,   -- decision canónica serializada
    reason           TEXT    DEFAULT '',
    source           TEXT    NOT NULL DEFAULT 'manual',
    created_by       TEXT    DEFAULT 'system',
    active           INTEGER NOT NULL DEFAULT 1,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(match_type, match_value)
);
CREATE INDEX IF NOT EXISTS idx_overrides_lookup
ON overrides_catalogacion(match_type, match_value, active);

-- -------------------------------------------------------------------------
-- ÍNDICE DE MANIFIESTOS
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS manifests_index (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type      TEXT    NOT NULL,   -- track | album | artist
    entity_key       TEXT    NOT NULL,
    manifest_path    TEXT    NOT NULL,
    schema_version   INTEGER NOT NULL DEFAULT 1,
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(entity_type, entity_key)
);

-- -------------------------------------------------------------------------
-- REPORTES DE AUDITORÍA/REPARACIÓN
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS auditorias_biblioteca (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    mode             TEXT    NOT NULL, -- audit | repair
    dry_run          INTEGER NOT NULL DEFAULT 1,
    resumen_json     TEXT    NOT NULL,
    creado_en        TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- -------------------------------------------------------------------------
-- AUDIO FEATURES / DISCOVERY
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS track_audio_features (
    track_id TEXT PRIMARY KEY, file_hash TEXT, file_path TEXT, analyzer_version TEXT NOT NULL,
    analysis_mode TEXT NOT NULL, analysis_status TEXT NOT NULL, duration_sec REAL, sample_rate INTEGER, channels INTEGER,
    bpm REAL, beat_count INTEGER, onset_rate REAL, rms_mean REAL, rms_std REAL, loudness_proxy REAL,
    spectral_centroid_mean REAL, spectral_bandwidth_mean REAL, spectral_rolloff_mean REAL, zero_crossing_rate_mean REAL,
    brightness REAL, darkness_proxy REAL, key_name TEXT, mode TEXT, danceability_proxy REAL, energy REAL,
    valence_proxy REAL, arousal_proxy REAL, aggressiveness_proxy REAL, calmness_proxy REAL, melancholy_proxy REAL,
    focus_score_proxy REAL, workout_score_proxy REAL, party_score_proxy REAL, night_score_proxy REAL, raw_basic_json TEXT,
    error_code TEXT, error_message TEXT, started_at TEXT, analyzed_at TEXT, updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_track_audio_features_status ON track_audio_features(analysis_status);
CREATE INDEX IF NOT EXISTS idx_track_audio_features_bpm ON track_audio_features(bpm);
CREATE INDEX IF NOT EXISTS idx_track_audio_features_energy ON track_audio_features(energy);
CREATE INDEX IF NOT EXISTS idx_track_audio_features_danceability ON track_audio_features(danceability_proxy);

CREATE TABLE IF NOT EXISTS track_vibe_tags (
  track_id TEXT NOT NULL, tag TEXT NOT NULL, score REAL, confidence REAL, source TEXT NOT NULL, explanation TEXT,
  analyzer_version TEXT, created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')),
  PRIMARY KEY(track_id, tag, source)
);
CREATE INDEX IF NOT EXISTS idx_track_vibe_tags_tag_score ON track_vibe_tags(tag, score DESC);

CREATE TABLE IF NOT EXISTS track_deep_audio_features (
  track_id TEXT PRIMARY KEY, file_hash TEXT, analyzer_version TEXT, analysis_status TEXT,
  mood_happy REAL, mood_sad REAL, mood_relaxed REAL, mood_aggressive REAL, mood_party REAL,
  danceability_model REAL, arousal REAL, valence REAL, embeddings_path TEXT, embeddings_dim INTEGER,
  tags_json TEXT, model_outputs_json TEXT, raw_output_json TEXT, inference_time_ms INTEGER, model_summary_json TEXT,
  error_code TEXT, error_message TEXT, started_at TEXT, analyzed_at TEXT, last_run_id TEXT,
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_track_deep_audio_features_status ON track_deep_audio_features(analysis_status);

-- -------------------------------------------------------------------------
-- KARAOKE JOBS — cola persistente de separaciones voz/instrumental.
-- Cada job representa un intento de procesamiento de una pista. La columna
-- pistas.karaoke_estado actua como cache desnormalizado del estado vigente
-- (lo consume el reproductor sin JOIN extra).
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS karaoke_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pista_id        INTEGER NOT NULL REFERENCES pistas(id) ON DELETE CASCADE,
    estado          TEXT    NOT NULL,
    -- estado: en_cola | preparando | procesando | generando | lista | fallida | cancelada
    progreso        REAL    NOT NULL DEFAULT 0.0,
    intento         INTEGER NOT NULL DEFAULT 0,
    max_intentos    INTEGER NOT NULL DEFAULT 2,
    modelo          TEXT,
    backend         TEXT,
    device          TEXT,
    ruta_salida     TEXT,
    bytes_salida    INTEGER,
    duracion_proc_ms INTEGER,
    error_codigo    TEXT,
    error_mensaje   TEXT,
    creado_en       TEXT    NOT NULL DEFAULT (datetime('now')),
    actualizado_en  TEXT    NOT NULL DEFAULT (datetime('now')),
    iniciado_en     TEXT,
    finalizado_en   TEXT
);
CREATE INDEX IF NOT EXISTS idx_karaoke_jobs_pista  ON karaoke_jobs(pista_id);
CREATE INDEX IF NOT EXISTS idx_karaoke_jobs_estado ON karaoke_jobs(estado);
CREATE INDEX IF NOT EXISTS idx_karaoke_jobs_creado ON karaoke_jobs(creado_en);

CREATE TABLE IF NOT EXISTS audio_analysis_jobs (
  job_id TEXT PRIMARY KEY,
  run_id TEXT,
  track_id TEXT,
  job_type TEXT,
  status TEXT,
  priority INTEGER DEFAULT 5,
  attempts INTEGER DEFAULT 0,
  max_attempts INTEGER DEFAULT 1,
  model_version TEXT,
  file_hash TEXT,
  error_code TEXT,
  error_message TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  started_at TEXT,
  updated_at TEXT DEFAULT (datetime('now')),
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_audio_analysis_jobs_status_priority ON audio_analysis_jobs(status, priority);
CREATE INDEX IF NOT EXISTS idx_audio_analysis_jobs_run ON audio_analysis_jobs(run_id);

CREATE TABLE IF NOT EXISTS audio_analysis_runs (
  run_id TEXT PRIMARY KEY,
  mode TEXT,
  status TEXT DEFAULT 'pending',
  total_tracks INTEGER DEFAULT 0,
  processed_tracks INTEGER DEFAULT 0,
  ready_tracks INTEGER DEFAULT 0,
  failed_tracks INTEGER DEFAULT 0,
  skipped_tracks INTEGER DEFAULT 0,
  pending_tracks INTEGER DEFAULT 0,
  current_track_id TEXT,
  current_file_path TEXT,
  current_stage TEXT,
  started_at TEXT,
  last_update_at TEXT,
  finished_at TEXT,
  elapsed_ms INTEGER DEFAULT 0,
  avg_ms_per_track REAL,
  tracks_per_minute REAL,
  eta_seconds REAL,
  eta_human TEXT,
  eta_last_value TEXT,
  config_snapshot_json TEXT,
  summary_json TEXT,
  cancel_policy TEXT
);

-- -------------------------------------------------------------------------
-- DJ PRIVADO — Sesiones musicales generadas por intencion.
--
-- Una sesion DJ representa una secuencia coherente de pistas construida a
-- partir de una intencion estructurada (no de filtros simples). La sesion
-- vive de forma independiente al historial y a las playlists, pero puede
-- guardarse como playlist normal cuando el usuario lo decide.
--
-- Tablas:
--   dj_sesiones        : cabecera con intencion (texto y estructurada)
--   dj_pistas_sesion   : pistas planificadas para una sesion (ordenadas)
--   dj_eventos         : eventos de reproduccion/adaptacion (skips, likes)
--   dj_concepto_emb    : cache de embeddings de conceptos de ontologia
--   dj_track_emb       : cache de embeddings derivados por pista
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dj_sesiones (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_original     TEXT    NOT NULL,
    intent_json         TEXT    NOT NULL DEFAULT '{}',
    objetivo_minutos    INTEGER NOT NULL DEFAULT 60,
    estado              TEXT    NOT NULL DEFAULT 'construyendo',
    -- estado: construyendo | lista | reproduciendo | pausada | finalizada | descartada | error
    motor_version       TEXT    NOT NULL DEFAULT 'dj_v1',
    semilla             INTEGER,
    notas               TEXT,
    resumen_json        TEXT    NOT NULL DEFAULT '{}',
    playlist_id         INTEGER REFERENCES playlists(id) ON DELETE SET NULL,
    creado_en           TEXT    NOT NULL DEFAULT (datetime('now')),
    actualizado_en      TEXT    NOT NULL DEFAULT (datetime('now')),
    finalizado_en       TEXT
);
CREATE INDEX IF NOT EXISTS idx_dj_sesiones_estado ON dj_sesiones(estado);
CREATE INDEX IF NOT EXISTS idx_dj_sesiones_creado ON dj_sesiones(creado_en DESC);

CREATE TABLE IF NOT EXISTS dj_pistas_sesion (
    sesion_id        INTEGER NOT NULL REFERENCES dj_sesiones(id) ON DELETE CASCADE,
    posicion         INTEGER NOT NULL,
    pista_id         INTEGER NOT NULL REFERENCES pistas(id) ON DELETE CASCADE,
    score_total      REAL    NOT NULL DEFAULT 0.0,
    score_intent     REAL    NOT NULL DEFAULT 0.0,
    score_transicion REAL    NOT NULL DEFAULT 0.0,
    score_curva      REAL    NOT NULL DEFAULT 0.0,
    razones_json     TEXT    NOT NULL DEFAULT '[]',
    transicion_json  TEXT    NOT NULL DEFAULT '{}',
    estado           TEXT    NOT NULL DEFAULT 'planificada',
    -- estado: planificada | reproducida | saltada | bloqueada | excluida
    bloqueada        INTEGER NOT NULL DEFAULT 0,
    -- fade_out_at_seg: si != NULL, el reproductor arranca la siguiente
    -- transicion en este timestamp (trim para respetar duracion objetivo).
    fade_out_at_seg  REAL,
    agregado_en      TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (sesion_id, posicion)
);
CREATE INDEX IF NOT EXISTS idx_dj_pistas_sesion ON dj_pistas_sesion(sesion_id, posicion);
CREATE INDEX IF NOT EXISTS idx_dj_pistas_pista  ON dj_pistas_sesion(pista_id);

CREATE TABLE IF NOT EXISTS dj_eventos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sesion_id   INTEGER NOT NULL REFERENCES dj_sesiones(id) ON DELETE CASCADE,
    pista_id    INTEGER REFERENCES pistas(id) ON DELETE SET NULL,
    tipo        TEXT    NOT NULL,
    -- tipo: reproducida | saltada | like | dislike | bloqueada | extendida | replanificada | feedback
    payload_json TEXT   NOT NULL DEFAULT '{}',
    creado_en   TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_dj_eventos_sesion ON dj_eventos(sesion_id, creado_en);
CREATE INDEX IF NOT EXISTS idx_dj_eventos_tipo   ON dj_eventos(tipo);

-- Cache de embeddings de conceptos de la ontologia (k=concepto, v=vector)
-- Si la capa de embeddings no esta disponible, esta tabla puede quedar vacia
-- sin afectar al motor (modo determinista).
CREATE TABLE IF NOT EXISTS dj_concepto_emb (
    concepto       TEXT PRIMARY KEY,
    modelo         TEXT NOT NULL,
    dim            INTEGER NOT NULL,
    vector_json    TEXT NOT NULL,
    creado_en      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Cache de embeddings derivados por pista (vector compuesto desde tags/genero/mood).
-- Persistir aqui evita recomputar embeddings cada vez que se construye una sesion.
CREATE TABLE IF NOT EXISTS dj_track_emb (
    pista_id       INTEGER PRIMARY KEY REFERENCES pistas(id) ON DELETE CASCADE,
    modelo         TEXT NOT NULL,
    dim            INTEGER NOT NULL,
    vector_json    TEXT NOT NULL,
    fuente_hash    TEXT NOT NULL,
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_dj_track_emb_modelo ON dj_track_emb(modelo);

-- Preferencias del DJ (presets de intencion, bloqueos persistentes, etc.)
CREATE TABLE IF NOT EXISTS dj_preferencias (
    clave        TEXT PRIMARY KEY,
    valor_json   TEXT NOT NULL,
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);

-- -------------------------------------------------------------------------
-- ECOSISTEMA MOVIL — Sincronizacion local con la app de telefono/tablet.
--
-- El PC actua como servidor local (HTTP/WS sobre LAN) y fuente de verdad de
-- la metadata enriquecida. Estas tablas modelan: dispositivos emparejados,
-- borrados a propagar (tombstones), transferencias de stems reanudables y un
-- contador global monotonico de version de sync. Todo es aditivo: no rompe
-- nada del esquema existente (ver docs/mobile-ecosystem.md, seccion C).
-- -------------------------------------------------------------------------

-- Dispositivos moviles emparejados.
-- device_token: credencial persistente emitida tras el handshake /pair.
-- seleccion_json: que sincroniza este device (todo/nada/por playlist/artista).
CREATE TABLE IF NOT EXISTS sync_dispositivos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    device_token        TEXT    NOT NULL UNIQUE,
    nombre              TEXT    NOT NULL,
    plataforma          TEXT,                       -- android | ios | desconocida
    ultima_conexion     TEXT,
    ultima_sync_version INTEGER NOT NULL DEFAULT 0,
    seleccion_json      TEXT,
    creado_en           TEXT    NOT NULL DEFAULT (datetime('now')),
    revocado            INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sync_dispositivos_token ON sync_dispositivos(device_token);
CREATE INDEX IF NOT EXISTS idx_sync_dispositivos_revocado ON sync_dispositivos(revocado);

-- Borrados a propagar (un DELETE no se detecta por sync_version).
CREATE TABLE IF NOT EXISTS sync_tombstones (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    entidad       TEXT    NOT NULL,   -- pista | album | artista | playlist
    entidad_id    INTEGER NOT NULL,
    sync_version  INTEGER NOT NULL,
    creado_en     TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sync_tombstones_version ON sync_tombstones(sync_version);

-- Estado de transferencia de stems por dispositivo (reanudable).
CREATE TABLE IF NOT EXISTS sync_stem_transfers (
    dispositivo_id INTEGER NOT NULL REFERENCES sync_dispositivos(id) ON DELETE CASCADE,
    pista_id       INTEGER NOT NULL REFERENCES pistas(id) ON DELETE CASCADE,
    estado         TEXT    NOT NULL DEFAULT 'pending', -- pending|in_progress|done|failed
    bytes_enviados INTEGER NOT NULL DEFAULT 0,
    actualizado_en TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (dispositivo_id, pista_id)
);

-- Contador global monotonico de version de sync (clave/valor).
CREATE TABLE IF NOT EXISTS sync_estado (
    clave TEXT PRIMARY KEY,   -- p.ej. 'sync_version_actual'
    valor TEXT NOT NULL
);
"""
