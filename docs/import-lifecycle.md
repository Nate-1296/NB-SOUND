# Ciclo de vida de una importación

Documentación técnica del pipeline de catalogación: desde el descubrimiento de archivos hasta la persistencia final en biblioteca.

---

## Visión general

Una ejecución del pipeline (`python main.py`) pasa por tres fases secuenciales y un conjunto de tareas asíncronas (sidecars). El orquestador es `core/pipeline.py` (`PipelineCatalogacion`).

```
main.py
  └─ PipelineCatalogacion.ejecutar()
       ├─ 1. Descubrimiento
       ├─ 2. Pipeline individual por archivo (paralelo: AcoustID + Shazam)
       ├─ 3. Segunda fase de resolución (opcional)
       ├─ 4. Tercera fase de resolución (opcional)
       ├─ 5. Materialización de decisiones (cuarentena, procesados)
       └─ 6. Sidecars asíncronos (assets, enrichment, manifests)
```

---

## Fase 1: Descubrimiento

`core/discovery.py` escanea recursivamente el directorio de entrada y retorna los archivos de audio soportados (MP3, FLAC, OGG, WAV, M4A, etc.). Los archivos ya procesados se detectan por marcador ID3 (`TXXX:NB_TAGGER_V3`) y se omiten si `SKIP_ALREADY_PROCESSED=true`.

Los formatos no-MP3 se transcodifican temporalmente a MP3 vía FFmpeg (`external/transcoder.py`) antes de entrar al pipeline. El archivo original no se toca; la copia temporal se elimina al finalizar ese archivo.

---

## Fase 2: Pipeline individual (por archivo)

Cada archivo recorre estas etapas secuencialmente. Un fallo en cualquier etapa produce una decisión de cuarentena y corta las etapas siguientes.

### 2.1 Validación técnica

`core/validator.py` verifica duración mínima/máxima, bitrate, legibilidad, y que el archivo no esté truncado o corrompido. Un archivo inválido va a cuarentena con causa específica (`DURACION_INVALIDA`, `BITRATE_INVALIDO`, etc.).

### 2.2 Detección de duplicado exacto por hash

Si `ENABLE_DEDUPLICATION=true`, `core/dedupe.py` calcula el hash SHA-256 del archivo y lo compara contra un registro en memoria de la ejecución actual. Los duplicados exactos no se procesan más.

### 2.3 Identificación externa (paralela)

AcoustID y Shazam se ejecutan en paralelo con `ThreadPoolExecutor(max_workers=2)`:

- **AcoustID** (`external/acoustid_client.py`): genera un fingerprint acústico via `fpcalc` y consulta la API para obtener `recording_ids` de MusicBrainz.
- **Shazam** (`external/shazam_client.py`): identifica la pista a partir de un fragmento de audio. Retorna título, artista, ISRC y confianza.

Ambos servicios tienen cache local (`external/cache.py`) y degradación controlada: si fallan, el pipeline continúa con la información disponible.

### 2.4 Normalización y fusión de evidencias

`core/normalizer.py` limpia y normaliza los metadatos provenientes de tres fuentes:

1. Tags ID3 del archivo original
2. Resultado de Shazam (si identificó)
3. Recording IDs de AcoustID (si encontró)

Produce un `MetadataNormalizada` con título, artista, álbum y slug únicos normalizados.

### 2.5 Sobreescrituras (overrides)

`core/overrides.py` consulta un registro de sobreescrituras manuales. Si existe un override válido para el archivo, se salta la consulta a MusicBrainz y el scoring: la decisión ya está predeterminada.

### 2.6 Consulta a MusicBrainz

`external/musicbrainz_client.py` busca candidatos usando:
- Los `recording_ids` de AcoustID como búsqueda directa por ID
- El ISRC de Shazam como búsqueda por identificador estándar
- Título + artista como búsqueda textual con scoring de similitud

Retorna una lista de `CandidatoMB` con metadata canónica y todos los releases asociados al recording.

### 2.7 Scoring y decisión

`core/matcher.py` puntúa cada candidato según múltiples señales:
- Similitud de título (fuzzy matching normalizado)
- Similitud de artista
- Coincidencia de duración
- Coincidencia de ISRC (peso alto)
- Confirmación por recording_id directo de AcoustID (peso muy alto)
- Confirmación por Shazam (peso alto)
- Penalizaciones por inconsistencias entre fuentes

Si hay ambigüedad entre los candidatos mejor puntuados, el desempate puede delegarse a la IA (`external/ia_client.py`) si está configurada.

La decisión es una de:
- **ACEPTADO**: confianza suficiente, se escribe en biblioteca
- **ACEPTADO_PROVISIONAL**: confianza media, se escribe con marcador provisional
- **REVISION**: confianza baja, se mueve a directorio de revisión
- **CUARENTENA**: problema técnico o metadata insuficiente

### 2.8 Escritura y movimiento

`core/writer.py` implementa escritura segura:

```
archivo original
  → copia temporal en directorio_temp
    → escritura de tags ID3 sobre la copia
      → validación de los tags escritos
        → movimiento atómico a biblioteca/<artista>/<álbum>/
```

Nunca se modifica el archivo original directamente. Si la escritura falla en cualquier punto, la copia temporal se descarta y la decisión cambia a CUARENTENA.

---

## Fase 3 y 4: Resolución secundaria y terciaria

### Segunda fase (`core/second_stage.py`)

Toma los archivos que quedaron en REVISION o CUARENTENA elegible y los reintenta con estrategias alternativas:
- Búsqueda más amplia en MusicBrainz
- Combinación diferente de señales disponibles
- Relajación de umbrales de scoring

### Tercera fase (`core/third_stage.py`)

Intento final conservador sobre los aún no resueltos:
- Búsqueda por metadata mínima (solo artista o solo título)
- Consulta a iTunes como fuente alternativa de metadata
- Promueve algunos CUARENTENA a REVISION si hay evidencia parcial

Ambas fases son opcionales y se controlan con `ENABLE_SECOND_STAGE_RESOLUTION` y `ENABLE_THIRD_STAGE_RESOLUTION`.

---

## Fase 5: Materialización de decisiones

Una vez terminadas las tres fases, se aplican los movimientos finales:

| Decisión | Acción |
|---|---|
| ACEPTADO / ACEPTADO_PROVISIONAL | Registro en directorio de procesados |
| REVISION | Copia a `directorio_revision/` |
| CUARENTENA | Copia a `directorio_cuarentena/` |
| DUPLICADO_* | Registro en procesados sin escritura |
| OMITIDO | Sin acción |

La lista `_ops_aplicadas` registra cada movimiento para permitir rollback si el pipeline se cancela.

---

## Fase 6: Sidecars asíncronos

Los sidecars corren en `_SidecarExecutorDaemon` (dos hilos daemon) y son no bloqueantes para el pipeline principal.

### Assets (`core/assets_pipeline.py`)

Descarga y gestiona portadas e imágenes de artistas:
- Portada de álbum HD desde MusicBrainz Cover Art Archive
- Foto de artista HD desde Internet Archive o Wikimedia
- Portada de track embebida en ID3

### Enrichment (`core/enrichment_pipeline.py`)

Enriquecimiento adicional post-catalogación:
- Letras sincronizadas y no sincronizadas
- Análisis de audio básico (BPM, energía, danceability) vía librosa
- Vibe tags (mood, feeling, energy level)

### Manifests (`core/manifests.py`)

Genera un archivo JSON por pista en `directorio_manifests/` con toda la metadata canónica, resultado del scoring, rutas de assets y estado de enrichment.

Los manifests se escriben después de que los sidecars terminen (o alcanzan timeout `SIDECAR_FUTURE_TIMEOUT_SEG`). Un sidecar que alcanza timeout retorna un estado `retryable: true` en el manifest para que `ImportRecoveryService` pueda reintentarlo.

---

## Control de ejecución

`infra/execution_control.py` (`ControlEjecucion`) coordina pausa y cancelación entre el hilo worker y la UI:

- El hilo worker llama `esperar_si_pausado()` al inicio de cada archivo
- La UI llama `pausar()` / `reanudar()` / `cancelar()` según interacción del usuario
- El estado se persiste en un JSON (`ruta_estado`) que la UI puede leer periódicamente

Si el pipeline se cancela, `_rollback_cambios()` revierte los movimientos aplicados hasta ese punto.

---

## Reanudación

El pipeline es reanudable porque:
1. Los archivos procesados se marcan con tag ID3 `TXXX:NB_TAGGER_V3`
2. Los archivos en cuarentena/revisión no se retocan en próximas ejecuciones
3. El cache local (`external/cache.py`) persiste entre ejecuciones, evitando llamadas duplicadas a servicios externos

---

## Recovery post-import

`core/import_recovery_service.py` (`ImportRecoveryService`) permite reintentar subsistemas que fallaron sin re-ejecutar el pipeline completo:

| Acción | Descripción |
|---|---|
| `retry_assets_missing` | Reintentar descarga de imágenes faltantes |
| `retry_enrichment_missing` | Reintentar letras y análisis básico |
| `retry_audio_features_failed` | Reintentar análisis de features locales |
| `retry_deep_failed` | Reintentar análisis Essentia fallidos |
| `retry_sidecars_failed` | Reintentar assets + enrichment en una sola llamada |

La UI expone estas acciones en la vista de importación a través de `ModeloImportacion` y `WorkerImportRecovery`.

---

## Modos de ejecución alternativos

El pipeline soporta modos especiales que evitan el flujo completo:

| Modo | Descripción |
|---|---|
| `metadata_only` | Sin assets pipeline |
| `review_only` | Usa el directorio de revisión como entrada |
| `assets_only` | Solo descarga imágenes para biblioteca existente |
| `missing_assets_only` | Solo pistas sin imágenes |
| `rebuild_manifests` | Regenera todos los JSON de manifests desde la BD |
| `audit` | Detecta inconsistencias en la biblioteca |
| `repair` | Repara inconsistencias detectadas |
| `duplicates_only` | Auditoría de duplicados en la BD |
| `discography_organize` | Reorganiza carpetas por discografía canónica |
| `explain <target>` | Muestra el scoring detallado de un archivo específico |

---

← [Volver a arquitectura](architecture.md)
