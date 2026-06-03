# Pipeline de análisis de audio

Documentación técnica del subsistema de análisis y extracción de características de audio: análisis básico local, análisis profundo con Essentia, y el feature store.

---

## Visión general

El análisis de audio opera en dos niveles independientes:

```
archivo de audio
  ├─ Análisis básico (librosa)          → track_audio_features + track_vibe_tags
  │    core/audio_features.py
  │    core/audio_feature_store.py
  │
  └─ Análisis profundo (Essentia/TF)   → track_deep_audio_features
       core/audio_intelligence_deep.py
       core/audio_intelligence_background.py
```

El análisis básico corre durante el pipeline de importación (como sidecar de enrichment). El análisis profundo corre en background, de forma asíncrona y reanudable.

---

## Análisis básico — librosa

### `core/audio_features.py` — `AudioFeatureAnalyzer`

Extrae features de audio usando librosa. Opera en modo *lazy*: solo carga las features que se le piden según el modo configurado.

**Features extraídas:**

| Feature | Descripción | Rango |
|---|---|---|
| `bpm` | Tempo estimado (beats por minuto) | 40–250 |
| `energia` | RMS promedio normalizado | 0.0–1.0 |
| `danceability` | Regularidad del beat estimada | 0.0–1.0 |
| `valence` | Positividad tonal (modo mayor vs menor) | 0.0–1.0 |
| `instrumentalness` | Proporción de energía en frecuencias vocales vs total | 0.0–1.0 |
| `spectral_centroid` | Centro de masa espectral normalizado | 0.0–1.0 |
| `zero_crossing_rate` | Tasa de cruce por cero | 0.0–1.0 |

**Modos de análisis** (controlados por `AUDIO_FEATURES_MODE`):

- `fast`: BPM + energía. Ideal para grandes colecciones.
- `standard`: todas las features básicas. Balance rendimiento/precisión.
- `full`: standard + análisis del track completo en lugar de muestras.

Los modos más ligeros muestrean segmentos del audio en lugar de procesar el track entero, lo que acelera el análisis a costa de menor precisión en tracks con cambios de tempo.

**Vibe tags:**

A partir de las features numéricas, el analyzer genera tags descriptivos (`chill`, `energetic`, `dark`, `upbeat`, `acoustic`, etc.) usando umbrales configurables en settings. Los vibe tags se almacenan en `track_vibe_tags` y se usan para búsqueda natural y recomendaciones del DJ Privado.

### `core/audio_feature_store.py` — `persist_basic_analysis`

Persiste los resultados del análisis básico en SQLite:

- `track_audio_features`: features numéricas normalizadas con `analysis_status` (`ready`/`failed`/`skipped`)
- `track_vibe_tags`: tags textuales derivados con `source='basic_analyzer'`

La función es idempotente: si el track ya tiene features con `analysis_status='ready'`, no las sobreescribe a menos que el archivo haya cambiado (verificado por hash).

---

## Análisis profundo — Essentia / TensorFlow

### `core/audio_intelligence_deep.py` — `EssentiaTensorflowAnalyzer`

Corre modelos de TensorFlow a través de Essentia para análisis semántico profundo:

**Modelos opcionales** (cada uno es independiente y se puede activar/desactivar):

| Grupo | Modelos | Salida |
|---|---|---|
| `mood_models` | MusiCNN mood classifiers | Tags de mood: happy, sad, aggressive, relaxed, etc. |
| `embeddings` | MusiCNN / EffNet embeddings | Vectores de 200 dims para similitud musical |
| `tagging_models` | Género, instrumentación, voz | Tags de género, presencia de voz, tipo de instrumento |

Los modelos requieren archivos `.pb` (TensorFlow SavedModel o protobuf) en `AUDIO_INTELLIGENCE_MODEL_DIR`. El analyzer verifica disponibilidad en el arranque; si un modelo no está disponible, lo omite sin fallar.

**Detección de backend:**

```
AUDIO_INTELLIGENCE_BACKEND = auto | tensorflow | essentia-tensorflow | none
```

En modo `auto`, el sistema detecta qué backend está instalado. Si no hay Essentia disponible, el análisis profundo se desactiva graciosamente.

**Versioning:**

Cada resultado se etiqueta con `ANALYZER_VERSION` (hash de la configuración activa de modelos). Si la versión cambia y `AUDIO_INTELLIGENCE_REANALYZE_ON_MODEL_CHANGE=true`, los tracks con versión anterior se re-encolan automáticamente.

### `core/audio_analysis_runs.py` — Modelo de jobs y runs

El sistema de procesamiento profundo usa un modelo de **run + jobs**:

```
audio_analysis_runs   ← una ejecución (puede abarcar muchos días)
  └─ audio_analysis_jobs  ← un job por track
       status: pending | running | paused | ready | failed | skipped
              cancelled_keep | cancelled_discard
```

Un **run** representa una sesión de análisis completa. Un **job** es la unidad de trabajo para un track individual. Esta separación permite:

- Pausar y reanudar entre sesiones de app
- Reintento granular de jobs fallidos
- Métricas de velocidad y ETA precisas
- Auditoría post-ejecución de qué tracks se procesaron con qué versión de modelo

---

## Background service — `core/audio_intelligence_background.py`

`AudioIntelligenceBackgroundService` orquesta el procesamiento profundo como cola persistente:

### Ciclo de vida de una sesión de procesamiento

```
1. enqueue_pending_tracks()   — detecta tracks sin features deep y crea jobs
2. process_pending()          — procesa jobs de forma secuencial con el analyzer
3. [opcional] pause()         — persiste estado; los jobs pasan a 'paused'
4. resume()                   — reactiva jobs paused
5. cancel_keep()              — cancela pero mantiene resultados parciales
6. cancel_discard()           — cancela y elimina features ya persistidas
```

### Recovery de interrupciones

Al iniciar cada sesión, `recover_interrupted_jobs()` detecta jobs en estado `running` (que quedaron colgados por un crash) y los revierte a `pending`. Esto garantiza que ningún track quede bloqueado indefinidamente.

### Configuración dinámica

La configuración (`AudioIntelligenceBackgroundConfig`) se lee desde SQLite (`config_ui`) y del entorno en cada llamada a `process_pending()`. Esto permite cambiar parámetros (batch size, idle delay, modelos activos) sin reiniciar la app.

Los parámetros clave:

| Parámetro | Descripción | Por defecto |
|---|---|---|
| `batch_size` | Jobs por lote antes de la pausa idle | 10 |
| `idle_delay_sec` | Pausa entre lotes (ceder CPU) | 2.0 |
| `max_runtime_min` | Tiempo máximo por sesión | 0 (ilimitado) |
| `max_attempts` | Intentos máximos por job fallido | 3 |
| `retry_failed` | Reintentar automáticamente fallidos | false |

### Integración con la UI

El worker Qt `WorkerAudioIntelligenceBackground` (en `workers/workers_qt.py`) ejecuta `process_pending()` en un `QThread` separado y emite señales de progreso al modelo `ModeloAudioIntelligenceBackground`. La UI muestra ETA, velocidad (tracks/min) y pista actual en tiempo real.

El `stop_event` de Python se conecta a `requestInterruption()` de Qt, lo que permite cancelación limpia desde la UI sin matar el hilo forzosamente.

---

## Feature store — `core/audio_feature_store.py`

### Esquema de persistencia

```sql
-- Features básicas por track
track_audio_features (
    track_id TEXT PRIMARY KEY,     -- FK a pistas.id
    analysis_status TEXT,          -- ready | failed | skipped
    analyzer_version TEXT,
    file_hash TEXT,
    bpm REAL, energia REAL, danceability REAL, ...
    analyzed_at DATETIME
)

-- Tags derivados (básicos y profundos)
track_vibe_tags (
    track_id TEXT,
    tag TEXT,
    score REAL,                    -- 0.0–1.0
    source TEXT                    -- basic_analyzer | deep_model
)

-- Features profundas
track_deep_audio_features (
    track_id TEXT PRIMARY KEY,
    analysis_status TEXT,
    analyzer_version TEXT,
    file_hash TEXT,
    last_run_id TEXT,              -- FK a audio_analysis_runs.run_id
    mood_tags_json TEXT,           -- JSON: {"happy": 0.8, "sad": 0.1, ...}
    genre_tags_json TEXT,
    embedding_json TEXT,           -- JSON: [0.12, -0.34, ...]
    analyzed_at DATETIME
)
```

### Acceso desde MusicDiscoveryService

`core/music_discovery_service.py` consulta el feature store para responder a búsquedas en lenguaje natural:

- "algo triste pero con energía" → filtro por valence < 0.3 AND energia > 0.6
- "jazz instrumental" → filtro por tags de género + instrumentalness alto
- "para correr" → filtro por bpm > 140 AND danceability > 0.7

La disponibilidad de features básicas vs profundas se comunica al usuario en `VistaExploradorCiego` para indicar qué tipo de búsqueda es posible.

---

## Analytics — `core/audio_analytics.py`

Calcula estadísticas agregadas sobre el corpus de features:

- Distribución de BPMs (histograma)
- Top moods de la colección
- Diversidad espectral (varianza de centroid)
- Cobertura de análisis (% con features básicas, % con deep)

Estas métricas se exponen en `ModeloEstadisticas` y se muestran en `VistaPerfil` y `VistaInicio`.

---

← [Volver a arquitectura](architecture.md)
