# Observabilidad

Documentación técnica del sistema de logging, control de ejecución y monitoreo de estado en NB SOUND.

---

## Logging — `infra/logger.py`

### Estructura

El logger usa dos canales con configuración diferenciada:

```
logger "nb_sound"          → archivo de log rotativo (directorio_logs/)
logger "nb_sound.console"  → stdout formateado para el operador
```

El canal de archivo usa `RotatingFileHandler` con rotación por tamaño. El canal de consola filtra por nivel mínimo configurable via `LOG_LEVEL_CONSOLA`.

### API de logging

```python
# Logger por módulo (convención estándar)
from infra.logger import obtener_logger
_log = obtener_logger("pipeline")

# Helpers estructurados de alto nivel
log_inicio_archivo(nombre)           # inicio de procesamiento de un archivo
log_decision(nombre, tipo, score, msg)  # decisión final del archivo
log_error_archivo(nombre, etapa, msg)   # error en una etapa específica
registrar_evento(evento, archivo=None, datos={})  # evento estructurado JSON
```

### Eventos estructurados

`registrar_evento()` escribe líneas JSON al log de eventos separado. Cada evento tiene:

```json
{
  "ts": "2026-05-17T10:23:45Z",
  "evento": "archivo_resumen",
  "archivo": "track.mp3",
  "datos": {
    "resultado": "aceptado",
    "puntaje": 0.9412,
    "etapas_ms": {"acoustid": 1230, "shazam": 890, "musicbrainz": 340},
    "explain": {...}
  }
}
```

Los eventos clave son:
- `archivo_resumen`: resultado de cada archivo con desglose de scoring
- `pipeline_phase`: transición entre fases del pipeline
- `ejecucion_completada`: métricas globales de la ejecución
- `sidecar_assets`, `sidecar_enrichment`: resultado de cada sidecar
- `sidecar_*_timeout`: sidecars que alcanzaron timeout

### Lifecycle del logging

`inicializar_logging(directorio_logs)` configura los handlers al inicio del pipeline CLI. `cerrar_logging()` los cierra limpiamente en el bloque `finally` de `PipelineCatalogacion.ejecutar()`.

La UI no usa el sistema de logging del CLI. Los modelos QML tienen sus propios logs via `obtener_logger(__name__)` que van al mismo sink pero con namespace diferente.

---

## Control de ejecución — `infra/execution_control.py`

### Propósito

`ControlEjecucion` es el contrato entre el proceso CLI y la UI para coordinar pausa/cancelación y visualizar el progreso en tiempo real. El archivo JSON que persiste es el canal de comunicación.

### Flujo de datos

```
WorkerImportacion (QThread)
  │  llama a ServicioImportacion
  │
  └─ ServicioImportacion
       │  instancia PipelineCatalogacion con control=ControlEjecucion(ruta_estado)
       │
       └─ PipelineCatalogacion.ejecutar()
            │  llama checkpoint() en cada iteración
            │  llama esperar_si_pausado() al inicio de cada archivo
            │
            └─ ControlEjecucion
                 │  actualiza EstadoEjecucion en memoria
                 └─ _persistir() → escribe JSON a disco (rename atómico)

ModeloImportacion (QObject, hilo principal)
  └─ lee ruta_estado periódicamente via QTimer
       └─ actualiza propiedades reactivas del modelo
            └─ QML recibe notificaciones via Property bindings
```

### Estado persistido

El JSON de estado contiene todos los campos de `EstadoEjecucion`:

```json
{
  "status": "running",
  "phase_id": "file_processing",
  "phase_label": "Procesando archivos",
  "phase_current": 42,
  "phase_total": 150,
  "current_file": "Queen - Bohemian Rhapsody.mp3",
  "eta_seconds": 234.5,
  "counters": {"aceptados": 38, "revision": 3, "cuarentena": 1},
  "extras": {
    "assets": {"scheduled": 38, "completed": 35, "pending": 3, "error": 0},
    "enrichment": {"scheduled": 38, "completed": 33, "pending": 5}
  }
}
```

### Atomicidad de escritura

`_persistir()` usa rename atómico para garantizar que el lector nunca vea un JSON parcial:

```python
ruta_tmp = ruta_estado.with_name(f".{nombre}.{thread_id}.tmp")
ruta_tmp.write_text(contenido)
ruta_tmp.replace(ruta_estado)  # atómico en Linux/macOS
```

El sufijo con `thread_id` evita colisiones si múltiples hilos llaman a `_persistir()` simultáneamente (aunque el lock interno ya previene esto).

### Integración con pausa/cancelación

```python
# Hilo worker
ControlEjecucion.esperar_si_pausado()  # bloquea hasta que pause_event.clear()
ControlEjecucion.cancelado()           # retorna True si cancel_event.is_set()

# Hilo UI (via modelo Python)
ModeloImportacion.pausar()    → control.pausar()
ModeloImportacion.reanudar()  → control.reanudar()
ModeloImportacion.cancelar()  → control.cancelar()
```

La cancelación es cooperativa: el pipeline verifica `cancelado()` entre archivos y al inicio de cada fase. Nunca se interrumpe forzosamente un hilo.

---

## Progreso de la barra — `infra/progress.py`

`BarraProgreso` mantiene el estado de progreso CLI en memoria y calcula métricas en tiempo real:

- ETA global (basada en tiempo promedio por archivo)
- ETA de fase (basada en progreso de la fase actual)
- Velocidad (archivos/minuto)
- Resumen de resultados por tipo

El pipeline actualiza la barra via:
- `establecer_fase()`: transición a una nueva fase
- `actualizar_fase()`: progreso dentro de la fase actual
- `actualizar_archivo()`: etapa del archivo en curso
- `registrar_resultado()`: finalización de un archivo

La barra puede operar en modo silencioso (sin output a consola) cuando corre desde la UI, actualizando solo el `ControlEjecucion`.

---

## Reports — `infra/reports.py`

Al finalizar una ejecución del pipeline, `guardar_reporte()` escribe un JSON con el `ResultadoEjecucion` completo en `directorio_logs/`. El nombre incluye el timestamp de la ejecución.

```json
{
  "timestamp_inicio": "2026-05-17T10:00:00Z",
  "timestamp_fin": "2026-05-17T10:23:45Z",
  "duracion_total_seg": 1425.3,
  "total_descubiertos": 150,
  "total_aceptados": 138,
  "total_revision": 8,
  "total_cuarentena": 4,
  "total_identificados_acoustid": 120,
  "total_identificados_shazam": 95,
  "segunda_fase_resueltos": 5,
  "tercera_fase_promovidos": 2,
  ...
}
```

`imprimir_resumen_consola()` formatea estos datos para la salida estándar.

---

## Quarantine — `infra/quarantine.py`

`GestorCuarentena` materializa las decisiones finales de cuarentena y revisión:

- **Cuarentena**: archivos con problemas técnicos irrecuperables
- **Revisión**: archivos con metadata insuficiente pero recuperables

Para cada destino, crea un directorio con timestamp de la sesión y copia el archivo. La copia (no movimiento) garantiza que el archivo original no se pierde si la copia falla.

Incluye un archivo `_reporte.txt` por sesión con el detalle de cada decisión.

---

## Processed — `infra/processed.py`

`GestorProcesados` registra los archivos que ya fueron procesados para evitar reprocesamiento:

- Directorio de procesados con estructura `año/mes/`
- Un archivo `.processed` por archivo procesado, nombrado por hash SHA-256
- Búsqueda O(1) por hash para verificación rápida

Esta es la capa persistente del mecanismo de skip. El tag ID3 `TXXX:NB_TAGGER_V3` es la capa rápida (sin acceso a disco de procesados), pero el directorio de procesados es autoritativo.

---

## Auditoría — `core/audit.py`

`DoctorBiblioteca` opera en dos modos:

- **`audit()`**: detecta inconsistencias (asset faltante en manifest, manifest sin archivo en disco, etc.) y retorna una lista de issues con severidad y código
- **`repair()`**: ejecuta reparaciones seguras basadas en el informe de auditoría

Ambos modos soportan `dry_run=True` para inspección sin cambios.

---

← [Volver a arquitectura](architecture.md)
