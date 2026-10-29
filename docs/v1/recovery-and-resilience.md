# Recovery y resiliencia

Documentación técnica de los mecanismos de recuperación ante fallos, interrupciones y estados inconsistentes.

---

## Principios de diseño

NB SOUND asume que cualquier proceso puede interrumpirse en cualquier momento: corte de luz, cierre de app, error de red, timeout de API. El sistema está diseñado para recuperarse de estas interrupciones sin pérdida de datos ni trabajo duplicado.

**Invariantes fundamentales:**
1. El archivo original **nunca** se modifica directamente. Toda escritura va sobre una copia.
2. Los estados intermedios (jobs `running`, sesiones `procesando`) se persisten antes de iniciarse.
3. El pipeline puede reanudarse desde el principio sin reprocesar archivos ya catalogados.
4. Los sidecars fallidos son retryable independientemente del pipeline principal.

---

## Recovery del pipeline CLI

### Evitar reprocesamiento

Un archivo ya catalogado tiene dos marcadores:

1. **Tag ID3** `TXXX:NB_TAGGER_V3` embebido en el MP3: verificación O(1) sin acceso a disco de procesados
2. **Archivo `.processed`** en `directorio_procesados/<hash_sha256>`: verificación por hash, independiente de la ruta del archivo

Si `SKIP_ALREADY_PROCESSED=true`, el pipeline omite archivos con cualquiera de estos marcadores al inicio de cada ejecución.

### Reanudación desde interrupciones

Dado que el pipeline procesa archivos en orden y marca cada uno al completar, una interrupción a mitad de ejecución resulta en:
- Archivos antes de la interrupción: ya marcados, se omitirán en la próxima ejecución
- Archivo en curso al momento de la interrupción: sin marcador, se reintentará desde cero

No hay estado intermedio a restaurar — el pipeline es stateless por archivo.

### Rollback por cancelación

Si el usuario cancela la ejecución, `PipelineCatalogacion._rollback_cambios()` revierte los movimientos físicos de la sesión actual:

```python
for origen, destino in reversed(self._ops_aplicadas):
    # Archivos en biblioteca: eliminar (ya estaban en entrada)
    # Archivos en procesados/cuarentena/revisión: mover de vuelta al origen
```

El rollback opera en orden inverso para evitar dependencias entre operaciones.

### Recovery del estado JSON

Si el proceso CLI termina abruptamente mientras actualiza el JSON de `ControlEjecucion`, la próxima ejecución puede encontrar:
- **JSON inconsistente** (write interrumpido): el rename atómico garantiza que el archivo en disco es siempre el JSON anterior completo o el nuevo completo, nunca un estado intermedio
- **JSON con `status: running`**: la UI detecta este estado al iniciar y lo marca como "interrupción inesperada"

---

## Recovery de audio intelligence deep

### Jobs zombies

Al iniciar `AudioIntelligenceBackgroundService.process_pending()`, se llama a `recover_interrupted_jobs()` que detecta jobs con `status='running'` en la BD (que quedaron así por un crash) y los revierte a `pending`.

Esto garantiza que el análisis de esas pistas se complete en la siguiente ejecución.

### Reintentos configurables

Los jobs con `status='failed'` pueden reintentarse:
- Automáticamente si `AUDIO_INTELLIGENCE_RETRY_FAILED=true` y `attempts < max_attempts`
- Manualmente desde la UI via `ModeloAudioIntelligenceBackground.retryFailed()`

El contador `attempts` persiste entre sesiones para evitar reintentar indefinidamente pistas que sistemáticamente fallan (p.ej., archivos de audio corruptos que Essentia no puede decodificar).

### `cancel_discard` vs `cancel_keep`

La cancelación tiene dos políticas:
- **`cancel_keep`**: los resultados ya persistidos en `track_deep_audio_features` se conservan; solo los jobs pendientes se cancelan
- **`cancel_discard`**: elimina también los features ya escritos (útil para limpiar análisis con una versión de modelo incorrecta)

---

## Recovery de karaoke

### Jobs zombies

`limpiar_jobs_zombies()` se llama al iniciar `WorkerKaraokeCola`. Detecta jobs en estados intermedios (`preparando`, `procesando`, `generando`) y los marca como `cancelada` con mensaje "Recuperado tras reinicio".

Esto evita que jobs bloqueados impidan el procesamiento de la cola.

### Cache de stems

Los archivos de stems ya generados persisten en `cache_dir/karaoke/<pista_id>/`. Si el archivo existe y tiene tamaño válido (>1KB), se reutiliza sin re-ejecutar Demucs, incluso si el job anterior terminó en estado `cancelada`.

El hash del directorio de caché incluye el `pista_id`, no la ruta del archivo, para que renombrar el archivo no invalide el cache.

### Archivos temporales

Durante la separación, Demucs usa un directorio temporal `cache_dir/karaoke/tmp/<job_id>/`. Este directorio se elimina en el bloque `finally` del procesamiento, independientemente del resultado. Si el directorio existe al iniciar un nuevo job (por un crash anterior), se elimina antes de empezar.

---

## Recovery post-import — `core/import_recovery_service.py`

`ImportRecoveryService` permite recuperar subsistemas fallidos sin re-ejecutar el pipeline completo. Esto es crítico porque los sidecars (assets, enrichment) pueden fallar por razones transitorias (red, timeout) que no justifican re-catalogar toda la biblioteca.

### Detección de estado

`ImportRecoveryService.status()` audita la biblioteca completa contra los manifests de assets y enrichment:

```python
{
    "missing_track_covers": 12,     # tracks sin portada
    "missing_album_covers": 3,      # tracks sin portada de álbum HD
    "missing_artist_images": 8,     # tracks sin foto de artista
    "missing_lyrics": 25,           # tracks sin letras
    "audio_features_missing": 5,    # tracks sin análisis básico
    "deep_failed": 2,               # jobs deep fallidos
}
```

### Acciones de recovery

| Acción | Qué reprocesa | Idempotencia |
|---|---|---|
| `retry_assets_missing` | Pistas sin portada/foto de artista | Sí: omite si ya existe |
| `retry_enrichment_missing` | Pistas sin letras o análisis básico | Sí: omite si ya existe |
| `retry_audio_features_failed` | Pistas con features en `failed` | Sí: actualiza solo si no hay `ready` |
| `retry_deep_failed` | Jobs deep con `status='failed'` y `attempts < max` | Sí: no duplica jobs |
| `retry_sidecars_failed` | assets + enrichment en una sola llamada | Sí |

### Caché negativa

Para el retry de assets, existe el concepto de "caché negativa": si en la ejecución original se intentó descargar una imagen y el servicio respondió "no existe", se cachea ese resultado negativo para evitar reintentos redundantes.

`retry_assets_missing(clear_negative_cache=True)` invalida estas entradas antes de reintentar, permitiendo que un nuevo intento consulte los servicios directamente.

---

## Resiliencia de clientes externos

### Degradación controlada

Todos los clientes externos (`external/*.py`) están diseñados para degradar sin lanzar excepciones al pipeline:

- **Timeout**: configurado por cliente (típicamente 5–30 segundos)
- **Reintentos**: backoff exponencial (máximo 3 reintentos por defecto)
- **Respuesta vacía**: si el servicio no responde, retorna el objeto de resultado con `identificado=False` o lista vacía

El pipeline nunca falla por la indisponibilidad de un servicio externo. Lo peor que puede pasar es que la decisión se base en menos evidencia de lo habitual.

### Cache como buffer de red

`external/cache.py` (`CacheLocal`) persiste las respuestas de cada servicio externo en disco con TTL diferenciado:
- Fingerprints AcoustID: TTL largo (semanas) — el fingerprint de un archivo no cambia
- Búsquedas MusicBrainz: TTL medio (días)
- Portadas e imágenes: TTL largo (semanas)
- Letras: TTL medio (días)

El cache reduce la exposición a fallos de red y respeta los rate limits de los servicios (especialmente MusicBrainz).

### `_ComponenteInactivo` — null object pattern

Si un servicio externo no pudo inicializarse tras los reintentos (`INIT_COMPONENT_MAX_RETRIES`), se reemplaza por `_ComponenteInactivo`:

```python
class _ComponenteInactivo:
    activo = False
    def __getattr__(self, name):
        return lambda *args, **kwargs: []  # cualquier método retorna lista vacía
```

Esto permite que el pipeline arranque y procese la colección aunque AcoustID, Shazam o la IA no estén disponibles. El atributo `activo=False` permite al pipeline saber que el servicio está deshabilitado y ajustar logs y contadores.

---

## Resiliencia de la base de datos

### Write-Ahead Log (WAL)

SQLite corre en modo WAL (`PRAGMA journal_mode=WAL`), lo que permite:
- Lecturas concurrentes mientras hay una escritura activa
- Recovery automático tras un crash (el WAL se aplica o descarta en el siguiente arranque)
- Mayor throughput en escrituras frecuentes

### Lock Python sobre SQLite

`db/conexion.py` mantiene un `threading.RLock()` sobre todas las operaciones de escritura. Esto serializa el acceso desde los distintos hilos (worker de importación, worker de deep, worker de búsqueda) sin depender del locking interno de SQLite.

### Migraciones forward-only

`db/esquema.py` implementa migraciones de esquema usando `ALTER TABLE ADD COLUMN` para columnas nuevas. Las migraciones son forward-only (no hay rollback de esquema) y se aplican automáticamente en cada `inicializar_db()`. Las columnas existentes nunca se eliminan para mantener compatibilidad con datos históricos.

---

## Cierre ordenado de la aplicación

El cierre de la UI desencadena `QGuiApplication.aboutToQuit`, que invoca
`cerrar()` sobre los modelos que mantienen recursos vivos. El orden está
fijado en `main_ui.py` y libera primero los consumidores y por último el
reproductor central:

```text
exploradorCiego → karaoke → djPrivado → importacion →
audioDeep → busqueda → playlists → reproductor
```

### Garantías por componente

| Componente | Acciones de cierre |
| --- | --- |
| `Reproductor` | Marca `_cerrado`, cancela el `Timer` diferido, desconecta el callback `MediaPlayerEndReached`, detiene reproducción, espera al hilo de progreso, llama a `release()` sobre `media_player` e `instancia_vlc`, limpia callbacks |
| `ModeloKaraoke` / `ModeloDjPrivado` | `requestInterruption()` cooperativo + `wait()` con timeout; cierra el reproductor de sesión DJ liberando ambos decks |
| `ModeloImportacion` | Interrupción cooperativa del worker (10 s) y del recovery worker (3 s) |
| `ModeloAudioIntelligenceBackground` | Detiene el timer de refresco y propaga `stop_event` al servicio batch para terminar la pista en curso y persistir el progreso parcial |
| `ModeloBusqueda` / `ModeloPlaylists` | Interrumpen workers de búsqueda actuales y archivados |
| `ModeloExploradorCiego` | Detiene el `QTimer` de fragmento del juego |

### Idempotencia

`Reproductor.cerrar()` es idempotente. Llamarlo más de una vez (por
ejemplo, desde `aboutToQuit` y luego desde el destructor de `ModeloReproductor`)
no genera efectos secundarios ni libera recursos ya liberados.

### Resistencia a cierres abruptos

Si la app termina sin disparar `aboutToQuit` (SIGKILL, panic del SO,
corte de energía), los mecanismos de recovery descritos arriba se
encargan del estado en el próximo arranque:

- Jobs `running` se revierten a `pending` (audio deep y karaoke).
- El JSON de `ControlEjecucion` se restaura desde el último write
  atómico.
- La cola de reproducción persiste pista a pista, por lo que la
  siguiente sesión comienza con la misma cola.

---

← [Volver a arquitectura](architecture.md)
