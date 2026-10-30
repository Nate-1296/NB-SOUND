-- Esquema de la V1 (v1.1.16), solo las sentencias CREATE, sin datos.
--
-- Es el que dejan `legado/db/esquema.py` y sus migraciones en una instalación al
-- día. Lo usa la prueba del importador para sembrar una V1 sintética.

CREATE TABLE artistas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre         TEXT    NOT NULL,
    nombre_slug    TEXT    NOT NULL UNIQUE,
    mb_artist_id   TEXT,
    creado_en      TEXT    NOT NULL DEFAULT (datetime('now'))
, sync_version INTEGER NOT NULL DEFAULT 0);
CREATE TABLE albums (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    artista_id     INTEGER NOT NULL REFERENCES artistas(id) ON DELETE CASCADE,
    titulo         TEXT    NOT NULL,
    titulo_slug    TEXT    NOT NULL,
    tipo           TEXT    NOT NULL DEFAULT 'Album',  -- Album, Single, EP, otros
    anio           INTEGER,
    mb_release_id  TEXT,
    ruta_carpeta   TEXT,
    portada_ruta   TEXT,
    creado_en      TEXT    NOT NULL DEFAULT (datetime('now')), sync_version INTEGER NOT NULL DEFAULT 0,
    UNIQUE(artista_id, titulo_slug)
);
CREATE TABLE pistas (
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
, sync_version INTEGER NOT NULL DEFAULT 0, favorita_actualizada_en TEXT);
CREATE TABLE playlists (
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
, sync_version INTEGER NOT NULL DEFAULT 0);
CREATE TABLE pistas_playlist (
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    pista_id    INTEGER NOT NULL REFERENCES pistas(id)    ON DELETE CASCADE,
    posicion    INTEGER NOT NULL DEFAULT 0,
    agregado_en TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (playlist_id, pista_id)
);
CREATE TABLE historial (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    pista_id      INTEGER REFERENCES pistas(id) ON DELETE SET NULL,
    titulo_snap   TEXT,   -- snapshot del titulo al momento de reproducir
    artista_snap  TEXT,
    reproducido_en TEXT NOT NULL DEFAULT (datetime('now')),
    duracion_seg  REAL,
    completada    INTEGER NOT NULL DEFAULT 1  -- 1 si se escucho completa, 0 si se salto
);
CREATE TABLE cola (
    posicion    INTEGER PRIMARY KEY,
    pista_id    INTEGER NOT NULL REFERENCES pistas(id) ON DELETE CASCADE,
    agregado_en TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE estado_reproductor (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
CREATE TABLE sesiones_import (
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
CREATE TABLE archivos_pendientes (
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
CREATE TABLE config_ui (
    clave     TEXT PRIMARY KEY,
    valor     TEXT NOT NULL,
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE overrides_catalogacion (
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
CREATE TABLE manifests_index (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type      TEXT    NOT NULL,   -- track | album | artist
    entity_key       TEXT    NOT NULL,
    manifest_path    TEXT    NOT NULL,
    schema_version   INTEGER NOT NULL DEFAULT 1,
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(entity_type, entity_key)
);
CREATE TABLE auditorias_biblioteca (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    mode             TEXT    NOT NULL, -- audit | repair
    dry_run          INTEGER NOT NULL DEFAULT 1,
    resumen_json     TEXT    NOT NULL,
    creado_en        TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE track_audio_features (
    track_id TEXT PRIMARY KEY, file_hash TEXT, file_path TEXT, analyzer_version TEXT NOT NULL,
    analysis_mode TEXT NOT NULL, analysis_status TEXT NOT NULL, duration_sec REAL, sample_rate INTEGER, channels INTEGER,
    bpm REAL, beat_count INTEGER, onset_rate REAL, rms_mean REAL, rms_std REAL, loudness_proxy REAL,
    spectral_centroid_mean REAL, spectral_bandwidth_mean REAL, spectral_rolloff_mean REAL, zero_crossing_rate_mean REAL,
    brightness REAL, darkness_proxy REAL, key_name TEXT, mode TEXT, danceability_proxy REAL, energy REAL,
    valence_proxy REAL, arousal_proxy REAL, aggressiveness_proxy REAL, calmness_proxy REAL, melancholy_proxy REAL,
    focus_score_proxy REAL, workout_score_proxy REAL, party_score_proxy REAL, night_score_proxy REAL, raw_basic_json TEXT,
    error_code TEXT, error_message TEXT, started_at TEXT, analyzed_at TEXT, updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE track_vibe_tags (
  track_id TEXT NOT NULL, tag TEXT NOT NULL, score REAL, confidence REAL, source TEXT NOT NULL, explanation TEXT,
  analyzer_version TEXT, created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')),
  PRIMARY KEY(track_id, tag, source)
);
CREATE TABLE track_deep_audio_features (
  track_id TEXT PRIMARY KEY, file_hash TEXT, analyzer_version TEXT, analysis_status TEXT,
  mood_happy REAL, mood_sad REAL, mood_relaxed REAL, mood_aggressive REAL, mood_party REAL,
  danceability_model REAL, arousal REAL, valence REAL, embeddings_path TEXT, embeddings_dim INTEGER,
  tags_json TEXT, model_outputs_json TEXT, raw_output_json TEXT, inference_time_ms INTEGER, model_summary_json TEXT,
  error_code TEXT, error_message TEXT, started_at TEXT, analyzed_at TEXT, last_run_id TEXT,
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE karaoke_jobs (
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
CREATE TABLE audio_analysis_jobs (
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
CREATE TABLE audio_analysis_runs (
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
CREATE TABLE dj_sesiones (
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
CREATE TABLE dj_pistas_sesion (
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
CREATE TABLE dj_eventos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sesion_id   INTEGER NOT NULL REFERENCES dj_sesiones(id) ON DELETE CASCADE,
    pista_id    INTEGER REFERENCES pistas(id) ON DELETE SET NULL,
    tipo        TEXT    NOT NULL,
    -- tipo: reproducida | saltada | like | dislike | bloqueada | extendida | replanificada | feedback
    payload_json TEXT   NOT NULL DEFAULT '{}',
    creado_en   TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE dj_concepto_emb (
    concepto       TEXT PRIMARY KEY,
    modelo         TEXT NOT NULL,
    dim            INTEGER NOT NULL,
    vector_json    TEXT NOT NULL,
    creado_en      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE dj_track_emb (
    pista_id       INTEGER PRIMARY KEY REFERENCES pistas(id) ON DELETE CASCADE,
    modelo         TEXT NOT NULL,
    dim            INTEGER NOT NULL,
    vector_json    TEXT NOT NULL,
    fuente_hash    TEXT NOT NULL,
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE dj_preferencias (
    clave        TEXT PRIMARY KEY,
    valor_json   TEXT NOT NULL,
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE sync_dispositivos (
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
CREATE TABLE sync_tombstones (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    entidad       TEXT    NOT NULL,   -- pista | album | artista | playlist
    entidad_id    INTEGER NOT NULL,
    sync_version  INTEGER NOT NULL,
    creado_en     TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE sync_stem_transfers (
    dispositivo_id INTEGER NOT NULL REFERENCES sync_dispositivos(id) ON DELETE CASCADE,
    pista_id       INTEGER NOT NULL REFERENCES pistas(id) ON DELETE CASCADE,
    estado         TEXT    NOT NULL DEFAULT 'pending', -- pending|in_progress|done|failed
    bytes_enviados INTEGER NOT NULL DEFAULT 0,
    actualizado_en TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (dispositivo_id, pista_id)
);
CREATE TABLE sync_estado (
    clave TEXT PRIMARY KEY,   -- p.ej. 'sync_version_actual'
    valor TEXT NOT NULL
);
CREATE INDEX idx_artistas_slug ON artistas(nombre_slug);
CREATE INDEX idx_albums_artista ON albums(artista_id);
CREATE INDEX idx_albums_tipo    ON albums(tipo);
CREATE INDEX idx_albums_titulo  ON albums(titulo COLLATE NOCASE);
CREATE INDEX idx_pistas_album     ON pistas(album_id);
CREATE INDEX idx_pistas_artista   ON pistas(artista_id);
CREATE INDEX idx_pistas_estado    ON pistas(estado);
CREATE INDEX idx_pistas_favorita  ON pistas(favorita);
CREATE INDEX idx_pistas_hash      ON pistas(hash_sha256);
CREATE INDEX idx_pistas_titulo    ON pistas(titulo COLLATE NOCASE);
CREATE INDEX idx_pistas_artista_n ON pistas(artista_nombre COLLATE NOCASE);
CREATE INDEX idx_pistas_ruta      ON pistas(ruta_archivo);
CREATE INDEX idx_playlists_tipo ON playlists(tipo);
CREATE INDEX idx_playlists_subtipo ON playlists(subtipo);
CREATE INDEX idx_playlists_auto_key ON playlists(auto_key);
CREATE INDEX idx_playlists_visible ON playlists(visible);
CREATE INDEX idx_pp_playlist ON pistas_playlist(playlist_id, posicion);
CREATE INDEX idx_historial_pista  ON historial(pista_id);
CREATE INDEX idx_historial_fecha  ON historial(reproducido_en);
CREATE INDEX idx_pendientes_tipo     ON archivos_pendientes(tipo);
CREATE INDEX idx_pendientes_resuelto ON archivos_pendientes(resuelto);
CREATE INDEX idx_overrides_lookup
ON overrides_catalogacion(match_type, match_value, active);
CREATE INDEX idx_track_audio_features_status ON track_audio_features(analysis_status);
CREATE INDEX idx_track_audio_features_bpm ON track_audio_features(bpm);
CREATE INDEX idx_track_audio_features_energy ON track_audio_features(energy);
CREATE INDEX idx_track_audio_features_danceability ON track_audio_features(danceability_proxy);
CREATE INDEX idx_track_vibe_tags_tag_score ON track_vibe_tags(tag, score DESC);
CREATE INDEX idx_track_deep_audio_features_status ON track_deep_audio_features(analysis_status);
CREATE INDEX idx_karaoke_jobs_pista  ON karaoke_jobs(pista_id);
CREATE INDEX idx_karaoke_jobs_estado ON karaoke_jobs(estado);
CREATE INDEX idx_karaoke_jobs_creado ON karaoke_jobs(creado_en);
CREATE INDEX idx_audio_analysis_jobs_status_priority ON audio_analysis_jobs(status, priority);
CREATE INDEX idx_audio_analysis_jobs_run ON audio_analysis_jobs(run_id);
CREATE INDEX idx_dj_sesiones_estado ON dj_sesiones(estado);
CREATE INDEX idx_dj_sesiones_creado ON dj_sesiones(creado_en DESC);
CREATE INDEX idx_dj_pistas_sesion ON dj_pistas_sesion(sesion_id, posicion);
CREATE INDEX idx_dj_pistas_pista  ON dj_pistas_sesion(pista_id);
CREATE INDEX idx_dj_eventos_sesion ON dj_eventos(sesion_id, creado_en);
CREATE INDEX idx_dj_eventos_tipo   ON dj_eventos(tipo);
CREATE INDEX idx_dj_track_emb_modelo ON dj_track_emb(modelo);
CREATE INDEX idx_audio_analysis_jobs_deep_track ON audio_analysis_jobs(job_type, track_id, model_version, file_hash);
CREATE INDEX idx_track_deep_audio_features_run ON track_deep_audio_features(last_run_id);
CREATE INDEX idx_sync_dispositivos_token ON sync_dispositivos(device_token);
CREATE INDEX idx_sync_dispositivos_revocado ON sync_dispositivos(revocado);
CREATE INDEX idx_sync_tombstones_version ON sync_tombstones(sync_version);
CREATE INDEX idx_pistas_sync_version ON pistas(sync_version);
CREATE INDEX idx_albums_sync_version ON albums(sync_version);
CREATE INDEX idx_artistas_sync_version ON artistas(sync_version);
CREATE INDEX idx_playlists_sync_version ON playlists(sync_version);
CREATE VIRTUAL TABLE pistas_fts USING fts5(
    titulo,
    artista_nombre,
    album_titulo,
    genero,
    content='pistas',
    content_rowid='id'
);
CREATE TRIGGER pistas_fts_insert
    AFTER INSERT ON pistas BEGIN
        INSERT INTO pistas_fts(rowid, titulo, artista_nombre, album_titulo, genero)
        VALUES (new.id, new.titulo, new.artista_nombre, new.album_titulo, coalesce(new.genero,''));
    END;
CREATE TRIGGER pistas_fts_delete
    AFTER DELETE ON pistas BEGIN
        INSERT INTO pistas_fts(pistas_fts, rowid, titulo, artista_nombre, album_titulo, genero)
        VALUES ('delete', old.id, old.titulo, old.artista_nombre, old.album_titulo, coalesce(old.genero,''));
    END;
CREATE TRIGGER pistas_fts_update
    AFTER UPDATE ON pistas BEGIN
        INSERT INTO pistas_fts(pistas_fts, rowid, titulo, artista_nombre, album_titulo, genero)
        VALUES ('delete', old.id, old.titulo, old.artista_nombre, old.album_titulo, coalesce(old.genero,''));
        INSERT INTO pistas_fts(rowid, titulo, artista_nombre, album_titulo, genero)
        VALUES (new.id, new.titulo, new.artista_nombre, new.album_titulo, coalesce(new.genero,''));
    END;
