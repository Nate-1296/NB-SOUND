# Subsistema karaoke

Documenta la arquitectura del sistema de preparación karaoke implementado en el
refactor de 2026-05-15.

## Visión general

El sistema separa la voz del instrumental de cada pista usando **Demucs** (modelo
`htdemucs`) y persiste el resultado como archivo MP3 320 kbps. Cuando una pista
tiene su instrumental listo, el reproductor expone el botón **Karaoke** que
alterna entre la mezcla original y la versión sin voz, conservando la letra y
la sincronización con LRC.

## Componentes

```
servicios/karaoke/
├── __init__.py        # API pública del paquete
├── backend.py         # Detección de demucs, ffmpeg, device (CUDA/MPS/CPU)
├── cola.py            # Orquestador: procesa jobs uno por uno + snapshots
├── errores.py         # Excepciones tipadas con códigos estables
├── jobs_repo.py       # CRUD de la tabla karaoke_jobs
├── modelo.py          # Carga + cache del modelo htdemucs
├── rutas.py           # Resolución de paths (cache/models/instrumentales)
└── separador.py       # Pipeline: cargar → separar → guardar → mp3
```

Capas externas:
- `workers/workers_qt.py::WorkerKaraokeCola` — QThread que invoca `cola.procesar_cola`.
- `ui/modelos_qml.py::ModeloKaraoke` — fachada delgada para QML.
- `ui/qml/vistas/VistaKaraoke.qml` — UI con acciones por estado.

Dependencias externas en runtime:
- `ffmpeg` + `ffprobe`: demucs los invoca por nombre vía `subprocess`
  para decodificar cualquier formato (MP3, FLAC, WAV, OGG, etc.). Los
  bundles oficiales los traen empaquetados y `main_ui.py` antepone el
  directorio `bin/` del bundle al `PATH` del proceso, así demucs los
  encuentra sin depender del PATH del lanzador del sistema. En
  desarrollo desde código fuente, deben estar en el PATH del sistema
  (ver [docs/requirements.md](requirements.md)).

## Persistencia

### Tabla `karaoke_jobs`

```sql
karaoke_jobs (
    id              INTEGER PK,
    pista_id        INTEGER FK pistas(id),
    estado          TEXT,            -- en_cola|preparando|procesando|generando|lista|fallida|cancelada
    progreso        REAL,            -- 0..1 dentro del job
    intento         INTEGER,
    max_intentos    INTEGER,         -- default 2
    modelo, backend, device, ruta_salida,
    bytes_salida, duracion_proc_ms,
    error_codigo, error_mensaje,
    creado_en, actualizado_en, iniciado_en, finalizado_en
)
```

### Cache desnormalizado en `pistas`

Para que el reproductor consulte el estado sin un JOIN, se mantiene en `pistas`:

- `karaoke_estado` — uno de `no_procesada|en_cola|procesando|lista|fallida|no_aplica`
- `karaoke_ruta_instrumental` — path absoluto del MP3 generado
- `karaoke_error_codigo`, `karaoke_error_mensaje` — última falla (si la hubo)

Los `jobs_repo` actualizan ambas tablas en transacción.

## Estados de un job

```
            ┌────────────────┐
            │   en_cola      │ ← encolar()
            └───────┬────────┘
                    │
                    ▼
            ┌────────────────┐
            │  preparando    │  (modelo carga, intento++)
            └───────┬────────┘
                    │
                    ▼
            ┌────────────────┐
            │  procesando    │  (apply_model por chunks)
            └───────┬────────┘
                    │
        ┌───────────┼────────────┐
        ▼           ▼            ▼
   ┌─────────┐ ┌─────────┐ ┌───────────┐
   │  lista  │ │ fallida │ │ cancelada │
   └─────────┘ └─────────┘ └───────────┘
```

## Detección de hardware

`backend.seleccionar_device("auto")` prioriza `cuda` > `mps` > `cpu` según
disponibilidad en runtime, sin depender del fabricante de GPU. El wheel de PyTorch
instalado por defecto es CPU (universal); para acelerar con NVIDIA basta
reinstalar el wheel CUDA correspondiente, el código lo usará automáticamente.

## Cancelación

Cooperativa, entre segmentos del modelo (chunks de ~7-8 s):

1. Usuario pulsa "Cancelar actual".
2. `ModeloKaraoke.cancelar_procesamiento()` → `Worker.requestInterruption()`.
3. El worker setea `stop_event`.
4. El separador, antes de procesar el siguiente chunk, comprueba `stop_event` y
   lanza `KaraokeCanceladoError`.
5. `cola.procesar_cola` captura la excepción, marca el job como `cancelada`,
   restaura la pista a `no_procesada` y limpia temporales.

"Cancelar y vaciar cola" añade además `vaciar_cola()` para cancelar los jobs
`en_cola` no procesados.

## Errores tipados

Cada error mapea a un código estable que la UI traduce a mensaje user-friendly:

| Código | Causa típica |
|---|---|
| `backend_no_disponible` | demucs/torch no instalados |
| `ffmpeg_faltante` | ffmpeg no está en PATH |
| `modelo_faltante` | sin internet en primera descarga |
| `audio_corrupto` | archivo no decodificable |
| `archivo_no_existe` | la pista apunta a una ruta inexistente |
| `memoria_insuficiente` | RAM/VRAM agotada |
| `timeout` | excedió tiempo máximo |
| `cancelado` | usuario canceló |

El último error queda en `karaoke_jobs.error_*` y se desnormaliza a
`pistas.karaoke_error_*`. La UI lo muestra en el delegate de la fila y en un
modal de detalle (`detalle_job`).

## Compatibilidad con la letra (lyrics)

El modo karaoke **no toca la asociación pista↔letra**. `ModeloReproductor.alternar_karaoke()`
solo cambia el archivo de audio (`ruta_archivo`) que VLC reproduce, manteniendo
el mismo `pista_id` lógico. Por eso las propiedades `letra_*`, `tiene_letra`,
`letra_synced_activa` siguen funcionando idénticas a las de la mezcla original.

## Pruebas

- `tests/test_karaoke_service.py` — 67 tests unitarios (repo, modelo, contrato QML).
- `tests/test_karaoke_separador.py` — 4 tests del separador. El test de
  integración real está marcado `@pytest.mark.slow` y solo corre con
  `NB_SOUND_RUN_SLOW_TESTS=1` (descarga modelo y separa audio sintético).

## Cómo correr el procesamiento manualmente

```python
from pathlib import Path
from servicios.karaoke import encolar, procesar_cola
import threading

# Encolar una pista
encolar(pista_id=42)

# Procesar la cola
snap = procesar_cola(
    cache_dir=Path.home() / ".cache" / "nb_sound",
    device_pref="auto",
    progress_callback=lambda s: print(s["estado"], s["porcentaje_job"]),
    stop_event=threading.Event(),
)
print(snap)
```
