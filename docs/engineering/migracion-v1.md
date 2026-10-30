# Migración de la V1: inventario columna a columna

> **Estado:** Vigente desde el 2026-10-30 (F1.2.1). Decisión: [ADR-004](../adr/decisions/ADR-004-datos.md). Gobierna
> el esquema de F1.1.2 a F1.1.6 y el importador de F1.2.2 a F1.2.5.

## Cómo leer este documento

Para cada columna de la V1 dice **a dónde va en la V2** o **por qué no se migra**. Un dato que no aparece aquí y que
el importador pierde es un defecto de este documento, no del importador.

* `→ tabla.columna` es el destino en el esquema V2. Los nombres son los de la V2 y los fija la migración que crea
  cada tabla; si una migración los cambia, cambia también esta página.
* **Se descarta** quiere decir que no hay nada que perder: es operativo, derivable o está vacío en la instalación
  real y el código de la V1 ya no lo escribe.
* **Se recalcula** quiere decir que la V2 lo deriva de otra cosa que sí se migra.
* Las cifras son de la instalación real medida el 2026-10-30, leída con `mode=ro`.

## Lo que la V1 guarda fuera de la base

El inventario de las 30 tablas no basta. **Cuatro datos que el usuario ve viven en archivos**, y perderlos sería
perder parte de la biblioteca aunque la base cuadrara fila a fila.

| Dato | Dónde lo tiene la V1 | Cuánto | Destino en la V2 |
|---|---|---|---|
| **Letras** (planas y sincronizadas) | `assets/enrichment/enrichment_manifest.jsonl`, una línea por archivo, indexada por ruta; la última línea de cada ruta manda | 2.332 de las 2.397 pistas tienen letra, 2.249 sincronizada | `→ letras` (F1.1.2), por `pista_id`, con proveedor, idioma y fecha de obtención. Entra en la búsqueda (F1.3.1) |
| **Portadas de álbum y de pista** | `assets/covers/{albums,tracks}` y sus variantes `_hd`, enlazadas desde `albums.portada_ruta` y desde `assets_manifest.jsonl` | 1.409 álbumes con portada; 3,5 GB en total, 3,4 GB de ellos en `albums_hd` | `→ portadas` (F1.1.2), una fila por contenido, con el archivo copiado a la carpeta de la V2. Ver P11 |
| **Imágenes de artista** | `assets/artists` y `artists_hd`, resueltas **por el nombre** del artista a través de `assets_manifest.jsonl` | 434 y 166 imágenes | `→ portadas` con `artista_id`: la V2 resuelve por id, no por nombre, y el importador hace la correspondencia una sola vez |
| **Instrumentales del karaoke** | `cache/karaoke/instrumentales`, enlazados desde `pistas.karaoke_ruta_instrumental` | 115 archivos, cerca de 1 GB | `→ stems` (F1.1.6), con el archivo copiado a la carpeta de la V2 |

Lo que no se migra de los archivos:

* **Miniaturas de portada** (`cache/biblioteca/portadas`, 2,3 GB) y **mosaicos de playlist**
  (`cache/playlist_covers`, 300 MB): **se recalculan** desde las portadas.
* **Respuestas de servicios en caché** (`cache/{acoustid,musicbrainz,general,shazam}`): operativas; caducan solas.
* **Manifiestos de importación** (`manifests/`, 35 MB, y `manifests_index`): información operativa ([inventario de
  la V1](../contextual/inventario-v1.md)).
* **El resto de `enrichment_manifest.jsonl`:** `audio_analytics` no tiene sonoridad medida en ninguna pista y la V2
  la mide con `ebur128` (**se recalcula**); `acoustid.fingerprint` **se recalcula** con `fpcalc`; `embedded` es lo que
  ya traen las etiquetas del archivo, y la V2 lo lee de ahí.
* **`audio_features_manifest.jsonl`, `deep_audio_features_manifest.jsonl` y `vibe_tags_manifest.jsonl`:** copias en
  disco de lo que ya está en las tablas de análisis.
* **La copia de seguridad de la V1** (`copia_seguridad`, 3,9 GB): es de la V1 y sigue siendo suya.

## Catálogo

### `artistas` (434)

| Columna | Destino |
|---|---|
| `id` | `→ artistas.id`, **tal cual**: el móvil lo tiene guardado |
| `nombre` | `→ artistas.nombre` |
| `nombre_slug` | `→ artistas.clave`, tal cual; las nuevas siguen la misma regla (`legado/utils/text.py`, `construir_slug`) para que importar dos veces el mismo artista no dé dos filas |
| `mb_artist_id` | `→ artistas.mbid`. Vacío en las 434 filas, pero el esquema lo conserva para el etiquetado |
| `creado_en` | `→ artistas.creado_en` |
| `sync_version` | `→ artistas.sync_version`, **tal cual** |

### `albums` (1.421)

| Columna | Destino |
|---|---|
| `id` | `→ albumes.id`, tal cual |
| `artista_id` | `→ albumes.artista_id` |
| `titulo` | `→ albumes.titulo` |
| `titulo_slug` | `→ albumes.clave`, tal cual, con la misma regla para las nuevas |
| `tipo` (`Album`, `Single`) | `→ albumes.tipo` |
| `anio` | `→ albumes.anio` |
| `mb_release_id` | `→ albumes.mbid` |
| `ruta_carpeta` | `→ albumes.carpeta`, relativa a la raíz de la biblioteca |
| `portada_ruta` | `→ portadas` (ver arriba); el álbum guarda `portada_id` |
| `creado_en` | `→ albumes.creado_en` |
| `sync_version` | `→ albumes.sync_version`, tal cual |

### `pistas` (2.397)

| Columna | Destino |
|---|---|
| `id` | `→ pistas.id`, tal cual |
| `album_id`, `artista_id` | `→ pistas.album_id`, `pistas.artista_id` |
| `titulo` | `→ pistas.titulo` |
| `artista_nombre`, `album_titulo` | `→ pistas.artista_nombre`, `pistas.album_titulo`. Parecen copias, pero no lo son: en 40 pistas el álbum que nombra la pista no es idéntico al título del álbum, y el móvil recibe el de la pista |
| `track_number` | `→ pistas.numero` (con `pistas.disco`, nueva). Vacío en las 2.397: la V1 no lo llegó a escribir. La V2 lo lee de las etiquetas |
| `duracion_seg` | `→ pistas.duracion_seg`, `REAL` con toda su precisión: el móvil recibe el valor de la V1 (`285.91020408163263`), y en 1.917 pistas pasarlo a milisegundos lo cambiaría |
| `bitrate_kbps` | `→ pistas.bitrate_kbps` |
| `anio` | `→ pistas.anio` |
| `genero` | `→ pistas.genero`. Vacío en las 2.397; se lee de las etiquetas |
| `isrc` | `→ pistas.isrc` |
| `ruta_archivo` | `→ pistas.ruta`, relativa a la raíz de la biblioteca: así la biblioteca sobrevive a un cambio de carpeta |
| `nombre_archivo` | **Se recalcula** de la ruta |
| `tamano_bytes` | `→ pistas.tamano` |
| `hash_sha256` | `→ pistas.sha256`. Es el `x-nb-sound-hash` del contrato móvil: se conserva tal cual |
| `mb_recording_id`, `mb_release_id`, `mb_release_type` | `→ pistas.mbid_grabacion`, `pistas.mbid_lanzamiento`, `pistas.tipo_lanzamiento` |
| `tagger_fuentes` | `→ pistas.fuentes_etiquetado` (JSON corto: de dónde salió cada etiqueta) |
| `estado` (`biblioteca` 2.240, `duplicado` 157) | `→ pistas.estado`, mismos valores. Las 157 duplicadas siguen sin verse ni ir al móvil, como en la V1 |
| `veces_reproducida` | `→ pistas.reproducciones` |
| `ultimo_acceso` | `→ pistas.ultima_reproduccion` |
| `favorita`, `favorita_actualizada_en` | `→ pistas.favorita`, `pistas.favorita_actualizada_en`. Se quedan en la pista y no en una tabla aparte: el móvil resuelve conflictos comparando la marca de tiempo, que también se guarda al desmarcar |
| `karaoke_estado`, `karaoke_ruta_instrumental`, `karaoke_actualizado_en` | `→ stems.estado`, `stems.instrumental`, `stems.terminada_en` (F1.1.6). Una pista con su instrumental en disco entra como `lista`, diga lo que diga su estado (existen los 115); las demás `en_cola` (57) entran como `pendiente`; `no_procesada` no deja fila |
| `karaoke_error_codigo`, `karaoke_error_mensaje` | **Se descartan**: vacíos en las 2.397; el error vive en el trabajo |
| `indexado_en`, `actualizado_en` | `→ pistas.creada_en`, `pistas.actualizada_en` |
| `sync_version` | `→ pistas.sync_version`, tal cual |
| — | **Nueva:** `pistas.verificada`, `1` para todas las importadas de la V1 (enmienda de ADR-007) |

### `pistas_fts` y sus tablas internas

**Se recalcula.** La V2 construye su propio índice FTS5 (F1.3.1), que además incluye las letras. La V1 indexaba
`genero`, vacío en todas.

### `archivos_pendientes` (116)

La futura vista **Por revisar** ([ADR-007](../adr/decisions/ADR-007-arquitectura-de-informacion.md)).

| Columna | Destino |
|---|---|
| `id` | `→ por_revisar.id` |
| `ruta_archivo`, `nombre_archivo` | `→ por_revisar.ruta`; el nombre se recalcula de ella |
| `tipo` (`cuarentena`, `revision`) | **Se descarta** como distinción: la V2 tiene una sola lista y la causa ya dice la gravedad |
| `causa` | `→ por_revisar.causa`, con los mensajes de la enmienda de ADR-007 |
| `manifiesto_json` | `→ por_revisar.metadatos`, solo lo que hace falta para importar tal como está |
| `sesion_id` | `→ por_revisar.importacion_id` |
| `registrado_en` | `→ por_revisar.registrado_en` |
| `resuelto`, `resuelto_en` | Solo se migran las filas **sin resolver** cuyo archivo exista (ADR-004). Hoy las 116 están resueltas, así que la vista arranca vacía |

### `sesiones_import` (37)

| Columna | Destino |
|---|---|
| `id`, `iniciado_en`, `finalizado_en`, `estado` | `→ importaciones.id`, `iniciada_en`, `terminada_en`, `estado` |
| `total_descubiertos`, `total_aceptados`, `total_revision`, `total_cuarentena`, `total_errores` | `→ importaciones.descubiertos`, `aceptados`, `por_revisar` (revisión más cuarentena) y `errores` |
| `directorio_entrada` | `→ importaciones.origen` |
| `reporte_json` | **Se descarta**: informe operativo de la V1 |

### `overrides_catalogacion` (0)

| Columna | Destino |
|---|---|
| `match_type`, `match_value`, `payload_json`, `reason`, `source`, `active` | `→ correcciones_catalogo.tipo`, `valor`, `cambios`, `motivo`, `origen`, `activa`, como manda ADR-004. Vacía hoy, pero el esquema la conserva y el importador la copia si alguien la tiene |
| `id`, `created_at`, `updated_at` | `→ correcciones_catalogo.id`, `creada_en`, `actualizada_en` |
| `created_by` | **Se descarta**: siempre `system` o el único usuario |

### `auditorias_biblioteca` (0)

**Se descarta**: informe operativo de la V1, vacío.

## Uso

### `playlists` (56)

| Columna | Destino |
|---|---|
| `id` | `→ playlists.id`, tal cual |
| `nombre`, `descripcion` | `→ playlists.nombre`, `playlists.descripcion` |
| `tipo` (`manual` 4, `automatica` 51, `sistema` 1), `subtipo`, `origen` | `→ playlists.tipo`, `playlists.subtipo`, `playlists.origen`, mismos valores: el contrato móvil los envía |
| `regla_json`, `auto_key` | `→ playlists.regla`, `playlists.clave_auto` (única, como en la instalación real) |
| `es_anclada`, `anclada_en` | `→ playlists.anclada`, `playlists.anclada_en`. Las dos: hay una anclada sin fecha |
| `visible` | `→ playlists.visible` |
| `portada_ruta` | **Se recalcula**: es el mosaico de las portadas de sus pistas |
| `ultima_generacion_en`, `auto_actualizable`, `editada_por_usuario` | `→ playlists.generada_en`, `playlists.auto_actualizable`, `playlists.editada` |
| `creado_en`, `actualizado_en` | `→ playlists.creada_en`, `playlists.actualizada_en` |
| `sync_version` | tal cual |

### `pistas_playlist` (2.360)

| Columna | Destino |
|---|---|
| `playlist_id`, `pista_id`, `posicion` | `→ playlist_pistas`, **con el orden exacto**: la prueba de conservación compara la secuencia de cada playlist |
| `agregado_en` | `→ playlist_pistas.agregada_en` |

### `historial` (3.225)

| Columna | Destino |
|---|---|
| `id`, `pista_id`, `reproducido_en`, `completada` | `→ historial.id`, `pista_id`, `reproducida_en`, `completada` |
| `titulo_snap`, `artista_snap` | `→ historial.titulo`, `historial.artista`: sobreviven a que la pista se borre, que es para lo que la V1 los guardaba |
| `duracion_seg` | `→ historial.escuchado_seg` |

### `cola` (8)

`posicion`, `pista_id`, `agregado_en` `→ cola.posicion`, `pista_id`, `agregada_en`, con el mismo orden.

### `estado_reproductor` (0) y las claves `reproductor_*` de `config_ui`

La tabla está vacía: la V1 guarda el estado en `config_ui`. `reproductor_pista_id`, `reproductor_pos_cola`,
`reproductor_pos_seg`, `volumen`, `modo_aleatorio`, `modo_repeticion` y `audio_normalizar` `→ estado_reproductor`, una sola fila con tipos. El volumen pasa de 0–100 a 0–1; la repetición conserva los valores de la V1 (`ninguno`, `todo`, `uno`).
El ecualizador (`eq_activo`, `eq_bandas`, `eq_preamp`, `eq_preset`) `→ preferencias`.

### `config_ui` (153 claves)

Ninguna clave se copia a ciegas. Cada grupo tiene su destino:

| Claves | Destino |
|---|---|
| `acoustid_key`, `anthropic_key`, `openai_key`, `theaudiodb_api_key` | **Al llavero del sistema** (F1.2.4), nunca a la base de la V2. La V1 las guardaba en texto plano en la base. El importador no las escribe en el registro ni en el informe |
| `tema`, `ui_font_family`, `ui_scale`, `nombre_usuario`, `foto_perfil` | `→ preferencias`. El tema y la tipografía con los valores de la enmienda de ADR-008; la foto de perfil se copia a la carpeta de la V2 |
| `ultima_vista`, `vista_biblioteca`, `vista_biblioteca_estado`, `panel_derecho_visible`, `playlists_categoria`, `playlists_modo_vista`, `playlists_orden`, `playlists_seleccionada_id`, `karaoke_tab_activa` | `→ preferencias`, las que tengan vista equivalente en la V2. `karaoke_tab_activa` se descarta: Preparar Karaoke se rediseña |
| `ui_mode` | **Se descarta**: el modo Pro y Simple desaparece (ADR-007) |
| `dir_biblioteca` | `→ preferencias.biblioteca`, la raíz respecto a la que se guardan las rutas relativas |
| `dir_entrada`, `dir_procesados`, `dir_revision`, `dir_cuarentena`, `dir_assets`, `dir_cache`, `dir_logs`, `dir_manifests`, `dir_temp` | **Se descartan**: la V2 tiene sus propias carpetas (`paths.rs`) y la importación se rediseña. El importador las lee para encontrar letras, portadas e instrumentales |
| `backup_carpeta`, `backup_frecuencia_dias`, `backup_ultimo` | `→ preferencias`, para la copia de seguridad de la V2 |
| `enable_*` de servicios externos (`acoustid`, `cover_art_archive`, `lrclib`, `lyrics_ovh`, `shazam`, imágenes de artista, IA…) | `→ politica_de_red`, **como consentimiento ya dado**: el usuario los activó en la V1. Los que la V2 no tiene se descartan |
| `enable_audio_features`, `audio_features_*`, `enable_audio_intelligence_deep`, `audio_intelligence_*`, `enable_audio_*_models`, `enable_audio_embeddings` | Lo que el usuario decide (análisis activado, en segundo plano, al importar) `→ preferencias`. Lo que era ajuste interno del motor de Python (`max_workers`, `segment_seconds`, `sample_strategy`, `backend`, `model_dir`, `allow_model_downloads`…) se descarta |
| `score_accept`, `score_review`, `duplicate_policy`, `duplicate_better_min_delta`, `enable_deduplication`, `enable_semantic_deduplication`, `enable_overrides`, `skip_already_processed`, `enable_second_stage_resolution`, `enable_third_stage_resolution`, `second_stage_*`, `third_stage_*`, `discography_ia_min_confidence`, `enable_ia_discography`, `enable_ia_tiebreak`, `ia_*` | `→ preferencias` los umbrales que la importación rediseñada conserve (F4); el resto se descarta con ella |
| `assets_*`, `lyrics_*`, `shazam_*`, `music_discovery_*`, `enable_music_discovery` | Tiempos de espera y reintentos de los clientes de Python: **se descartan**. Los límites de la V2 viven en `net.rs` |
| `dj_sesion_id`, `dj_indice_pista`, `dj_pos_global_seg`, `dj_pos_pista_seg`, `dj_volumen` | `→ dj_en_curso`, una sola fila. `dj_pista_id` **se recalcula** de la sesión y el índice |
| `dj_privado_perfil_hardware` | **Se descarta**: la V2 mide el equipo al arrancar |
| `sync_auto_encender` | `→ preferencias.servidor_movil_al_arrancar` |
| `sync_exposicion_inicial_v1` | **Se descarta**: marca de una migración interna de la V1 ya hecha |
| `dependencias_*`, `init_component_*`, `sidecar_*`, `nb_sound_progress_*`, `manifest_schema_version`, `dedupe_observable_*` | **Se descartan**: estado de los procesos de Python de la V1 |

## Análisis

### `track_audio_features` (4.127)

Hay **1.730 filas huérfanas**, de pistas que ya no existen; solo se migran las de pistas vivas, y de esas solo las
`ready`.

| Columna | Destino |
|---|---|
| `track_id` | `→ rasgos.pista_id` |
| `file_hash`, `analyzer_version` | `→ rasgos.sha256`, `rasgos.version`: deciden si hay que reanalizar |
| `bpm`, `beat_count`, `onset_rate`, `key_name`, `mode` | `→ rasgos` |
| `rms_mean`, `rms_std`, `loudness_proxy`, `spectral_centroid_mean`, `spectral_bandwidth_mean`, `spectral_rolloff_mean`, `zero_crossing_rate_mean`, `brightness`, `darkness_proxy` | `→ rasgos` |
| `danceability_proxy`, `energy`, `valence_proxy`, `arousal_proxy`, `aggressiveness_proxy`, `calmness_proxy`, `melancholy_proxy`, `focus_score_proxy`, `workout_score_proxy`, `party_score_proxy`, `night_score_proxy` | `→ rasgos`: alimentan las listas por ánimo y el DJ, y el prototipo de rasgos los reproduce |
| `duration_sec`, `sample_rate`, `channels` | **Se descartan**: están en `archivos` |
| `file_path` | **Se descarta**: la pista ya tiene su archivo |
| `analysis_mode`, `analysis_status`, `error_code`, `error_message`, `started_at`, `updated_at` | **Se descartan**: estado operativo. Las fallidas (1.693) se reanalizan |
| `analyzed_at` | `→ rasgos.analizado_en` |
| `raw_basic_json` | **Se descarta**: salida cruda; lo útil ya está en columnas |

### `track_deep_audio_features` (407)

| Columna | Destino |
|---|---|
| `track_id`, `file_hash`, `analyzer_version`, `analyzed_at` | `→ analisis_profundo` |
| `mood_happy`, `mood_sad`, `mood_relaxed`, `mood_aggressive`, `mood_party`, `danceability_model`, `arousal`, `valence` | `→ analisis_profundo`, como `REAL`. Son las siete cabezas del agregado de análisis más la de baile |
| `embeddings_dim`, `embeddings_path` | **Se descartan**: `embeddings_path` está vacío en las 407; el embedding de MusiCNN se recalcula en `f32` (ADR-004, punto 4) |
| `tags_json`, `model_summary_json` | `→ analisis_profundo.etiquetas`, resumido a probabilidad por clase |
| `model_outputs_json`, `raw_output_json` | **Se descartan**: son los 441 MB de salidas crudas fotograma a fotograma (ADR-004) |
| `analysis_status`, `error_code`, `error_message`, `started_at`, `inference_time_ms`, `last_run_id`, `updated_at` | **Se descartan**: operativos |

### `track_vibe_tags` (16.814)

Se migran las 16.572 de pistas vivas.

| Columna | Destino |
|---|---|
| `track_id`, `tag`, `source` (`basic_rules`, `deep_model`) | `→ etiquetas_ambiente`, misma clave primaria |
| `score`, `confidence` | `→ etiquetas_ambiente` |
| `explanation` | **Se recalcula**: es un texto generado por regla que la V2 compone en la interfaz desde la etiqueta y el rasgo |
| `analyzer_version`, `created_at`, `updated_at` | `→ etiquetas_ambiente.version`, `etiquetas_ambiente.actualizada_en` |

### `audio_analysis_jobs` (6.510) y `audio_analysis_runs` (4.145)

**Se descartan** (ADR-004): colas y ejecuciones terminadas. Lo único con valor, saber qué pistas fallaron, ya lo dice
la ausencia de rasgos.

## Sincronización con el móvil

### `sync_dispositivos` (12)

| Columna | Destino |
|---|---|
| `id`, `nombre`, `plataforma`, `ultima_conexion`, `ultima_sync_version`, `creado_en`, `revocado` | `→ dispositivos`, **tal cual** (ADR-005). Once de los doce están revocados y se migran igual: un token revocado tiene que seguir rechazándose |
| `device_token` | `→ dispositivos.token_sha256`: su SHA-256, no el token. El teléfono sigue enviando el mismo token y el servidor lo reconoce calculando el hash |
| `seleccion_json` | `→ dispositivos.seleccion`. Vacía en los 12 |

El `device_token` es un secreto de autenticación y la V1 lo guardaba en claro. El contrato móvil solo lo envía al
emparejar, en la respuesta de `/pair`, que la V2 genera en ese momento: guardar el hash no le quita nada.

### `sync_estado` (3)

| Clave | Destino |
|---|---|
| `sync_version_actual` | `→ sincronizacion.version`, tal cual: el siguiente cambio de la V2 tiene que ser mayor |
| `backfill_playlists_sync_v1`, `backfill_sync_version_v1` | **Se descartan**: marcas de migraciones internas de la V1 |

### Cómo se mantiene la `sync_version`

La V1 la subía a mano desde cada servicio. La V2 lo hace con disparadores en las tablas que el móvil recibe, solo
para las columnas que el contrato envía, y deja una tumba en cada borrado. Mientras importa, el importador pausa los
disparadores (`sincronizacion.pausada`) para que cada fila conserve la versión de la V1: 153 pistas tienen
`sync_version = 0` y no pueden recibir una nueva, o el móvil volvería a descargarlas.

### `sync_tombstones` (21)

`id`, `entidad`, `entidad_id`, `sync_version`, `creado_en` `→ tumbas`, tal cual: el móvil todavía puede pedir los
cambios desde una versión anterior a cualquiera de ellas.

### `sync_stem_transfers` (221)

`dispositivo_id`, `pista_id`, `estado`, `bytes_enviados`, `actualizado_en` `→ transferencias_stems`, con los valores de estado de la V1. Las 221 están
`in_progress`: se migran como pendientes, y el móvil las vuelve a pedir.

### Identidad del servidor

El certificado y la clave (`~/.config/nb_sound/sync/`) se copian a la carpeta de la V2 sin regenerarlos (F1.2.3).

## Karaoke y DJ

### `karaoke_jobs` (323)

**Se descartan** los terminados (ADR-004). El estado útil, qué pista tiene instrumental, ya va a `stems` desde
`pistas`. Los trabajos en cola son los mismos 57 que `pistas.karaoke_estado = 'en_cola'`, y entran como pendientes.

### `dj_sesiones` (1), `dj_pistas_sesion` (12), `dj_eventos` (0)

`→ dj_sesiones`, `dj_sesion_pistas` y `dj_eventos`, con todas sus columnas, como manda ADR-004: `prompt_original` pasa
a `peticion`, `intent_json` a `intencion`, `score_*` a `puntuacion_*`, `fade_out_at_seg` a `fundido_en_seg` y cada
`*_json` a su columna sin el sufijo. Se guardan tal cual porque el DJ de la V2 los lee para explicar por qué eligió
cada pista.

### `dj_preferencias` (0)

`clave`, `valor_json`, `actualizado_en` `→ dj_preferencias`.

### `dj_track_emb` (0) y `dj_concepto_emb` (0)

**Se descartan**: vacías, y la V2 usa los embeddings de `analisis_profundo` en `f32`, no `vector_json`.

## Operativo

### `manifests_index` (8.328)

**Se descarta** (ADR-004).

## Lo que la prueba de conservación comprueba

F1.2.5 no se da por buena si no cuadran, sobre la instalación real:

* 434 artistas, 1.421 álbumes, 2.397 pistas (2.240 en biblioteca y 157 duplicadas) con sus `id` y sus
  `sync_version`.
* 56 playlists con la misma secuencia de pistas cada una; 3.225 entradas de historial; 8 en la cola.
* 12 dispositivos, 21 tumbas y la `sync_version` actual.
* 2.332 letras, 1.409 portadas de álbum, 434 imágenes de artista y 115 instrumentales, con su archivo presente.
* Las claves con valor, en el llavero y **en ningún otro sitio** de la carpeta de la V2.
* Que el archivo de la base de la V1 y las carpetas que el importador lee no cambian (hash antes y después).

## Resultado sobre la instalación real (2026-10-30)

`src-tauri/tests/importacion_real.rs`, con la V1 en solo lectura y el destino en disco:

* Cuadran fila a fila con la V1: 434 artistas, 1.421 álbumes, 2.397 pistas, 56 playlists con sus 2.360 entradas en
  el mismo orden, 3.225 entradas de historial, 8 en la cola, 12 dispositivos, 21 tumbas y la sesión del DJ. Los `id`
  y las `sync_version` son los mismos, y el contador queda en el de la V1.
* Fuera de la base: 2.332 letras, 1.805 portadas distintas (las de 1.409 álbumes y 434 artistas), 115
  instrumentales listos y 56 pistas que esperaban en cola, pendientes.
* Análisis: 2.396 pistas con rasgos, 407 con análisis profundo y 16.572 etiquetas de ambiente.
* **La base de la V2 pesa 26,2 MB** con el índice de búsqueda (18,2 MB sin él), frente a los 464 MB de la V1 y al
  tope de 40 MB. El hash de la base de la V1 no cambia.
* La huella del servidor móvil es la misma, y la clave de servicio que había pasa al llavero (la prueba la cuenta sin
  escribir en el llavero de quien la ejecuta).
* La importación tarda 42 s, casi todo en copiar 4 GB de portadas e instrumentales.
