# Configuración

NB SOUND se configura mediante un archivo `.env` en la raíz del
proyecto. Usa `cp .env.example .env` para partir de la plantilla.

Si la aplicación gráfica se inicia sin `.env`, lo genera automáticamente
con rutas estándar del sistema operativo y crea los directorios
correspondientes. El archivo generado puede editarse libremente o
ajustarse desde la pantalla de Configuración.

---

## Rutas del sistema

Estas rutas definen dónde vive cada parte de tu biblioteca. Son las únicas variables verdaderamente obligatorias para que el proyecto funcione.

| Variable | Descripción | Obligatoria |
|---|---|---|
| `USER_INPUT_DIR` | Carpeta con música pendiente de catalogar | Sí |
| `USER_LIBRARY_DIR` | Biblioteca organizada y base de datos | Sí |
| `USER_QUARANTINE_DIR` | Archivos con problemas técnicos o sin evidencia | Sí |
| `USER_REVIEW_DIR` | Archivos ambiguos que requieren revisión manual | Sí |
| `USER_LOGS_DIR` | Logs y reportes de ejecución | Sí |
| `USER_PROCESSED_DIR` | Originales archivados tras catalogar | Sí |
| `USER_CACHE_DIR` | Caché de consultas externas | No |
| `USER_TEMP_DIR` | Archivos temporales de conversión | No |
| `USER_ASSETS_DIR` | Portadas, imágenes de artistas y assets | No |
| `USER_MANIFESTS_DIR` | Manifiestos canónicos por pista/álbum/artista | No |

> La UI usa `USER_LIBRARY_DIR/nb_sound.sqlite3` como base de datos
> cuando la ruta está configurada. Si no lo está, usa el equivalente
> en datos estándar del sistema operativo:
>
> - Linux: `$XDG_DATA_HOME/nb_sound/ui.db` (típicamente `~/.local/share/nb_sound/ui.db`)
> - macOS: `~/Library/Application Support/NBSound/ui.db`
> - Windows: `%LOCALAPPDATA%/NBSound/ui.db`

---

## Identificación externa

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `ACOUSTID_API_KEY` | Clave para fingerprint acústico AcoustID | — |
| `ENABLE_ACOUSTID` | Activa/desactiva AcoustID | `True` |
| `ENABLE_SHAZAM` | Activa/desactiva reconocimiento Shazam | `True` |
| `SHAZAM_TIMEOUT_SEG` | Timeout de reconocimiento Shazam | `12` |
| `SHAZAM_MIN_DURACION_SEG` | Duración mínima para consultar Shazam | `20` |

Sin clave de AcoustID, el sistema usa el resto de fuentes (Shazam, tags locales, MusicBrainz).

---

## IA para desempate (opcional)

NB SOUND puede usar IA para decidir entre candidatos ambiguos. No inventa metadata: solo desempata.

| Variable | Descripción | Valores |
|---|---|---|
| `IA_PROVEEDOR` | Proveedor de IA | `No`, `Anthropic`, `OpenAI` |
| `ANTHROPIC_API_KEY` | Clave Anthropic | — |
| `OPENAI_API_KEY` | Clave OpenAI | — |
| `ENABLE_IA_TIEBREAK` | Permite desempate con IA | `True` |
| `IA_TIEBREAK_MIN_GAP` | Gap mínimo para considerar empate | `0.12` |
| `IA_MAX_TOKENS` | Límite de tokens por respuesta | `512` |
| `IA_TIMEOUT_SEG` | Timeout de llamada IA | `20` |
| `ENABLE_IA_DISCOGRAPHY` | Reorganización discográfica asistida | `True` |
| `DISCOGRAPHY_IA_MIN_CONFIDENCE` | Confianza mínima para aplicar cambios | `0.90` |

---

## Comportamiento del pipeline

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `ENABLE_DEDUPLICATION` | Detecta duplicados exactos (hash SHA256) | `True` |
| `ENABLE_SEMANTIC_DEDUPLICATION` | Detecta duplicados por ISRC/recording ID | `True` |
| `DUPLICATE_POLICY` | Qué hacer con duplicados | `replace_if_better` |
| `DUPLICATE_BETTER_MIN_DELTA` | Delta mínimo para "reemplazar si mejor" | `0.08` |
| `SKIP_ALREADY_PROCESSED` | Omite hashes ya conocidos | `False` |
| `ENABLE_SECOND_STAGE_RESOLUTION` | Segunda fase conservadora de recuperación | `True` |
| `ENABLE_THIRD_STAGE_RESOLUTION` | Tercera fase, aún más estricta | `True` |

**Políticas de duplicados disponibles:**

- `skip_keep_existing` — deja el que ya está, ignora el nuevo
- `replace_if_better` — reemplaza si el nuevo tiene mejor calidad (recomendado)
- `merge_assets_only` — solo actualiza portadas/assets
- `prefer_existing_if_canonical` — favorece siempre el que ya está en biblioteca
- `prefer_new_if_quality_higher` — favorece siempre el nuevo si supera en bitrate/calidad

---

## Assets visuales

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `ENABLE_ASSETS_PIPELINE` | Descarga portadas e imágenes | `True` |
| `ENABLE_COVER_ART_ARCHIVE` | Usa Cover Art Archive | `True` |
| `ENABLE_THEAUDIODB_ARTIST_IMAGES` | Imágenes de artistas de TheAudioDB | `True` |
| `ENABLE_ITUNES_COVER_FALLBACK` | Portadas de iTunes como fallback | `True` |
| `ENABLE_DEEZER_ARTIST_IMAGES` | Imágenes de artistas de Deezer | `True` |
| `ENABLE_WIKIPEDIA_ARTIST_IMAGES` | Imágenes de artistas de Wikipedia | `True` |
| `THEAUDIODB_API_KEY` | Clave TheAudioDB | `123` (pública básica) |
| `ASSETS_TIMEOUT_SEG` | Timeout de descarga por asset | `10` |
| `ASSETS_MIN_RESOLUTION` | Resolución mínima aceptable (px) | `250` |

---

## Letras

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `ENABLE_LYRICS_ENRICHMENT` | Busca letras tras catalogar | `True` |
| `ENABLE_LRCLIB` | Usa LRCLIB como fuente | `True` |
| `ENABLE_LYRICS_OVH` | Usa lyrics.ovh como fuente | `True` |
| `LYRICS_TIMEOUT_SEG` | Timeout por consulta | `8` |

---

## Audio Features (análisis local)

Genera BPM, energía, brillo, danceability y vibe tags usando `librosa`. Rápido y sin modelos externos.

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `ENABLE_AUDIO_FEATURES` | Activa el análisis local | `True` |
| `AUDIO_FEATURES_MODE` | `light` (recomendado) o `standard` | `light` |
| `AUDIO_FEATURES_ANALYZE_ON_IMPORT` | Analiza durante la importación | `True` |
| `AUDIO_FEATURES_BACKGROUND` | Ejecuta en background cuando aplica | `True` |
| `AUDIO_FEATURES_MAX_WORKERS` | Workers paralelos | `1` |
| `AUDIO_FEATURES_SAMPLE_STRATEGY` | Estrategia de muestreo | `smart_segments` |
| `AUDIO_FEATURES_SEGMENT_SECONDS` | Segundos a analizar por pista | `90` |

---

## Audio Intelligence profunda (opcional)

Modelos Essentia/TensorFlow para moods, embeddings y géneros. Pesado; apagado por defecto.

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `ENABLE_AUDIO_INTELLIGENCE_DEEP` | Activa el análisis profundo | `False` |
| `AUDIO_INTELLIGENCE_BACKEND` | `none` o `essentia_tensorflow` | `none` |
| `AUDIO_INTELLIGENCE_MODEL_DIR` | Carpeta con modelos `.pb/.json` | — |
| `ENABLE_AUDIO_MOOD_MODELS` | Modelos de mood (happy, sad, relaxed…) | `False` |
| `ENABLE_AUDIO_EMBEDDINGS` | Embeddings MusicNN/VGGish | `False` |
| `ENABLE_AUDIO_TAGGING_MODELS` | Géneros Discogs400 y tags MSD | `False` |
| `AUDIO_INTELLIGENCE_BACKGROUND_AUTOSTART` | Inicia background al arrancar | `True` |
| `AUDIO_INTELLIGENCE_RESUME_PENDING_ON_STARTUP` | Reanuda jobs pendientes al arrancar | `True` |
| `AUDIO_INTELLIGENCE_MAX_WORKERS` | Workers paralelos de deep | `1` |

→ Guía completa en [docs/audio-features.md](audio-features.md)

---

## Music Discovery

Permite búsqueda natural sobre la biblioteca ("algo triste pero con energía").

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `ENABLE_MUSIC_DISCOVERY` | Activa la búsqueda natural | `True` |
| `MUSIC_DISCOVERY_USE_AUDIO_FEATURES` | Usa features básicas en la búsqueda | `True` |
| `MUSIC_DISCOVERY_USE_DEEP_FEATURES` | Usa features profundas si existen | `True` |
| `MUSIC_DISCOVERY_MIN_CONFIDENCE` | Confianza mínima de resultados | `0.35` |
| `MUSIC_DISCOVERY_DEFAULT_LIMIT` | Resultados por defecto | `25` |

---

← [Volver al README](../README.md)
