//! Las copias que son SQL puro, de la base de la V1 adjunta como `v1` en solo
//! lectura a la de la V2.
//!
//! Adjuntarla y copiar con `INSERT … SELECT` hace que todas las lecturas de la V1
//! vean **la misma foto**, la de la transacción de escritura de la V2, aunque la
//! V1 esté abierta y escribiendo a la vez; y evita pasar cada fila por Rust. El
//! destino de cada columna está en docs/engineering/migracion-v1.md: si una
//! sentencia de aquí cambia, cambia también esa página.
//!
//! `:musica` es la carpeta de la música de la V1 terminada en separador, o vacía;
//! las rutas que empiezan por ella se guardan relativas.

/// En orden: cada tabla después de aquellas a las que referencia.
pub const SENTENCIAS: &[(&str, &str)] = &[
    (
        "artistas",
        "INSERT INTO artistas (id, nombre, clave, mbid, creado_en, sync_version)
         SELECT id, nombre, nombre_slug, NULLIF(mb_artist_id, ''), creado_en, sync_version
         FROM v1.artistas",
    ),
    (
        "albumes",
        "INSERT INTO albumes (id, artista_id, titulo, clave, tipo, anio, mbid, carpeta, creado_en,
                              sync_version)
         SELECT id, artista_id, titulo, titulo_slug, tipo, anio, NULLIF(mb_release_id, ''),
                CASE WHEN :musica <> '' AND substr(ruta_carpeta, 1, length(:musica)) = :musica
                     THEN substr(ruta_carpeta, length(:musica) + 1) ELSE NULLIF(ruta_carpeta, '') END,
                creado_en, sync_version
         FROM v1.albums",
    ),
    (
        "pistas",
        "INSERT INTO pistas (id, album_id, artista_id, titulo, artista_nombre, album_titulo, numero,
                             duracion_seg, anio, genero, isrc, mbid_grabacion, mbid_lanzamiento,
                             tipo_lanzamiento, fuentes_etiquetado, ruta, tamano, sha256,
                             bitrate_kbps, estado, verificada, favorita, favorita_actualizada_en,
                             reproducciones, ultima_reproduccion, creada_en, actualizada_en,
                             sync_version)
         SELECT id, album_id, artista_id, titulo, artista_nombre, album_titulo,
                NULLIF(track_number, 0), duracion_seg, anio, NULLIF(genero, ''), NULLIF(isrc, ''),
                NULLIF(mb_recording_id, ''), NULLIF(mb_release_id, ''), NULLIF(mb_release_type, ''),
                NULLIF(tagger_fuentes, ''),
                CASE WHEN :musica <> '' AND substr(ruta_archivo, 1, length(:musica)) = :musica
                     THEN substr(ruta_archivo, length(:musica) + 1) ELSE ruta_archivo END,
                tamano_bytes, NULLIF(hash_sha256, ''), NULLIF(bitrate_kbps, 0), estado, 1, favorita,
                favorita_actualizada_en, veces_reproducida, ultimo_acceso, indexado_en,
                actualizado_en, sync_version
         FROM v1.pistas",
    ),
    (
        "playlists",
        "INSERT INTO playlists (id, nombre, descripcion, tipo, subtipo, origen, regla, clave_auto,
                                anclada, anclada_en, visible, generada_en, auto_actualizable,
                                editada, creada_en, actualizada_en, sync_version)
         SELECT id, nombre, descripcion, tipo, subtipo, origen, NULLIF(regla_json, ''),
                NULLIF(auto_key, ''), es_anclada, anclada_en, visible, ultima_generacion_en,
                auto_actualizable, editada_por_usuario, creado_en, actualizado_en, sync_version
         FROM v1.playlists",
    ),
    (
        "playlist_pistas",
        "INSERT INTO playlist_pistas (playlist_id, pista_id, posicion, agregada_en)
         SELECT playlist_id, pista_id, posicion, agregado_en FROM v1.pistas_playlist",
    ),
    (
        "historial",
        "INSERT INTO historial (id, pista_id, titulo, artista, reproducida_en, escuchado_seg,
                                completada)
         SELECT id, CASE WHEN pista_id IN (SELECT id FROM v1.pistas) THEN pista_id END,
                titulo_snap, artista_snap, reproducido_en, duracion_seg, completada
         FROM v1.historial",
    ),
    (
        "cola",
        "INSERT INTO cola (posicion, pista_id, agregada_en)
         SELECT posicion, pista_id, agregado_en FROM v1.cola",
    ),
    (
        "rasgos",
        "INSERT INTO rasgos (pista_id, version, sha256, bpm, pulsos, ataques_por_seg, tonalidad,
                             modo, rms_media, rms_desviacion, sonoridad_aprox, centroide,
                             ancho_banda, caida_espectral, cruces_por_cero, brillo, oscuridad,
                             bailabilidad, energia, valencia, activacion, agresividad, calma,
                             melancolia, para_concentrarse, para_entrenar, para_fiesta,
                             para_la_noche, analizado_en)
         SELECT CAST(track_id AS INTEGER), analyzer_version,
                CASE WHEN length(file_hash) = 64 THEN file_hash END,
                CASE WHEN bpm > 0 THEN bpm END, beat_count, onset_rate,
                CASE WHEN key_name IN ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A',
                                       'A#', 'B') THEN key_name END,
                CASE WHEN mode IN ('major', 'minor') THEN mode END,
                rms_mean, rms_std, loudness_proxy, spectral_centroid_mean,
                spectral_bandwidth_mean, spectral_rolloff_mean, zero_crossing_rate_mean,
                brightness, darkness_proxy, danceability_proxy, energy, valence_proxy,
                arousal_proxy, aggressiveness_proxy, calmness_proxy, melancholy_proxy,
                focus_score_proxy, workout_score_proxy, party_score_proxy, night_score_proxy,
                coalesce(analyzed_at, updated_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
         FROM v1.track_audio_features
         WHERE analysis_status = 'ready'
           AND CAST(track_id AS INTEGER) IN (SELECT id FROM v1.pistas)",
    ),
    (
        // Las etiquetas de estilo se quedan en las diez más probables, redondeadas
        // a cuatro decimales: el resto de la distribución no lo lee nadie.
        "analisis_profundo",
        "INSERT INTO analisis_profundo (pista_id, version, sha256, feliz, triste, relajada,
                                        agresiva, fiesta, bailable, activacion, valencia,
                                        etiquetas, analizado_en)
         SELECT CAST(track_id AS INTEGER), coalesce(analyzer_version, ''),
                CASE WHEN length(file_hash) = 64 THEN file_hash END,
                mood_happy, mood_sad, mood_relaxed, mood_aggressive, mood_party,
                danceability_model, arousal, valence,
                CASE WHEN json_valid(tags_json) THEN (
                    SELECT json_group_array(json_array(etiqueta, round(puntuacion, 4)))
                    FROM (SELECT json_extract(value, '$.label') AS etiqueta,
                                 json_extract(value, '$.score') AS puntuacion
                          FROM json_each(tags_json, '$.tags_msd50')
                          ORDER BY puntuacion DESC LIMIT 10)
                ) END,
                coalesce(analyzed_at, updated_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
         FROM v1.track_deep_audio_features
         WHERE mood_happy IS NOT NULL
           AND CAST(track_id AS INTEGER) IN (SELECT id FROM v1.pistas)",
    ),
    (
        "etiquetas_ambiente",
        "INSERT INTO etiquetas_ambiente (pista_id, etiqueta, fuente, puntuacion, confianza, version,
                                         actualizada_en)
         SELECT CAST(track_id AS INTEGER), tag, source, score, confidence,
                coalesce(analyzer_version, ''),
                coalesce(updated_at, created_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
         FROM v1.track_vibe_tags
         WHERE CAST(track_id AS INTEGER) IN (SELECT id FROM v1.pistas)",
    ),
    (
        "importaciones",
        "INSERT INTO importaciones (id, origen, iniciada_en, terminada_en, estado, descubiertos,
                                    aceptados, por_revisar, errores)
         SELECT id, directorio_entrada, iniciado_en, finalizado_en,
                CASE estado WHEN 'completado' THEN 'terminada' ELSE 'cancelada' END,
                total_descubiertos, total_aceptados, total_revision + total_cuarentena,
                total_errores
         FROM v1.sesiones_import",
    ),
    (
        "correcciones_catalogo",
        "INSERT INTO correcciones_catalogo (id, tipo, valor, cambios, motivo, origen, activa,
                                            creada_en, actualizada_en)
         SELECT id, match_type, match_value, payload_json, coalesce(reason, ''), source, active,
                created_at, updated_at
         FROM v1.overrides_catalogacion",
    ),
    (
        "tumbas",
        "INSERT INTO tumbas (id, entidad, entidad_id, sync_version, creada_en)
         SELECT id, entidad, entidad_id, sync_version, creado_en FROM v1.sync_tombstones",
    ),
    (
        "dj_sesiones",
        "INSERT INTO dj_sesiones (id, peticion, intencion, objetivo_minutos, estado, motor_version,
                                  semilla, notas, resumen, playlist_id, creada_en, actualizada_en,
                                  terminada_en)
         SELECT id, prompt_original,
                CASE WHEN json_valid(intent_json) THEN intent_json ELSE '{}' END,
                objetivo_minutos, estado, motor_version, semilla, notas,
                CASE WHEN json_valid(resumen_json) THEN resumen_json ELSE '{}' END,
                CASE WHEN playlist_id IN (SELECT id FROM v1.playlists) THEN playlist_id END,
                creado_en, actualizado_en, finalizado_en
         FROM v1.dj_sesiones",
    ),
    (
        "dj_sesion_pistas",
        "INSERT INTO dj_sesion_pistas (sesion_id, posicion, pista_id, puntuacion,
                                       puntuacion_intencion, puntuacion_transicion,
                                       puntuacion_curva, razones, transicion, estado, bloqueada,
                                       fundido_en_seg, agregada_en)
         SELECT sesion_id, posicion, pista_id, score_total, score_intent, score_transicion,
                score_curva,
                CASE WHEN json_valid(razones_json) THEN razones_json ELSE '[]' END,
                CASE WHEN json_valid(transicion_json) THEN transicion_json ELSE '{}' END,
                estado, bloqueada, fade_out_at_seg, agregado_en
         FROM v1.dj_pistas_sesion",
    ),
    (
        "dj_eventos",
        "INSERT INTO dj_eventos (id, sesion_id, pista_id, tipo, datos, creado_en)
         SELECT id, sesion_id, CASE WHEN pista_id IN (SELECT id FROM v1.pistas) THEN pista_id END,
                tipo, CASE WHEN json_valid(payload_json) THEN payload_json ELSE '{}' END, creado_en
         FROM v1.dj_eventos",
    ),
    (
        "dj_preferencias",
        "INSERT INTO dj_preferencias (clave, valor, actualizada_en)
         SELECT clave, CASE WHEN json_valid(valor_json) THEN valor_json ELSE json_quote(valor_json) END,
                actualizado_en
         FROM v1.dj_preferencias",
    ),
];

/// Después de los dispositivos, que se copian desde Rust porque su token se
/// guarda como hash. Una transferencia a medias se reinicia: el móvil la vuelve a
/// pedir y no hay forma de reanudarla donde se quedó.
pub const TRANSFERENCIAS: &str = "
    INSERT INTO transferencias_stems (dispositivo_id, pista_id, estado, bytes_enviados,
                                      actualizada_en)
    SELECT dispositivo_id, pista_id,
           CASE estado WHEN 'in_progress' THEN 'pending' ELSE estado END,
           CASE estado WHEN 'in_progress' THEN 0 ELSE bytes_enviados END,
           actualizado_en
    FROM v1.sync_stem_transfers";
