# Procesamiento en background

Documentación técnica de todos los subsistemas de procesamiento asíncrono: workers Qt, cola de karaoke y Audio Intelligence background.

---

## Arquitectura general

NB SOUND tiene tres categorías de procesamiento en background:

```
UI Thread (QML)
  │
  ├─ Workers Qt (QThread)          ← operaciones que no deben bloquear la UI
  │    WorkerImportacion
  │    WorkerAudioIntelligenceBackground
  │    WorkerImportRecovery
  │    WorkerBusqueda / WorkerBusquedaNatural
  │    WorkerBusquedaPlaylist
  │    WorkerKaraokeCola
  │
  ├─ Sidecars del pipeline CLI     ← hilos daemon del proceso CLI
  │    _SidecarExecutorDaemon (assets, enrichment)
  │
  └─ Lock global de análisis deep  ← _PROCESS_LOCK en audio_intelligence_background.py
       (un solo worker deep por proceso)
```

Todos los workers Qt comunican resultados via señales Qt. Nunca modifican estado compartido directamente desde el hilo secundario — solo emiten señales que el hilo principal procesa.

---

## Workers Qt — `workers/workers_qt.py`

### Patrón común

Cada worker sigue este patrón:

```python
class WorkerX(QThread):
    resultado = Signal(dict)    # señal de resultado
    progreso  = Signal(dict)    # señal de progreso (si aplica)
    error     = Signal(str)     # señal de error

    def run(self):
        try:
            resultado = servicio.operacion()
            self.resultado.emit(resultado)
        except Exception as e:
            self.error.emit(str(e))
```

Los workers son instanciados por los modelos QML (`ui/modelos_qml.py`) y destruidos al completar. El modelo conecta las señales a sus slots antes de llamar `worker.start()`.

### `WorkerImportacion`

Ejecuta el pipeline de catalogación completo (`ServicioImportacion`). La comunicación entre el servicio Python (que corre en el hilo del worker) y la UI es bidireccional:

- **Hilo worker → UI**: señales `progreso`, `completado`, `cancelado`, `error`
- **UI → hilo worker**: llamada a `requestInterruption()` → el worker detecta con `svc.cancelar()`

El polling de interrupción es cooperativo: el worker verifica `isInterruptionRequested()` en cada ciclo de espera (`terminado.wait(0.1)`), no por interrupciones nativas del SO.

### `WorkerAudioIntelligenceBackground`

Encapsula `AudioIntelligenceBackgroundService.process_pending()`. Usa un `threading.Event` como `stop_event` que se setea en `requestInterruption()`, propagando la señal de parada al loop interno del servicio de forma limpia.

Solo puede haber un worker de este tipo activo por proceso — el servicio mantiene un `_PROCESS_LOCK` (threading.Lock) que rechaza una segunda invocación concurrente.

### `WorkerKaraokeCola`

Procesa la cola de karaoke vía `servicios.karaoke.procesar_cola()`. El `stop_event` se propaga hasta el separador Demucs, que lo verifica entre segmentos del modelo para cancelación en el punto más cercano posible.

La cancelación solo afecta al job en curso y a los siguientes — los jobs ya completados permanecen en estado `lista`.

### `WorkerBusqueda` y `WorkerBusquedaNatural`

Workers de búsqueda con **debounce implícito**: el modelo crea un nuevo worker por cada keystroke y solicita interrupción al anterior antes de iniciarlo. El worker verifica `isInterruptionRequested()` antes y después de la consulta, descartando resultados obsoletos.

La búsqueda natural (`WorkerBusquedaNatural`) agrega una llamada previa a `MusicDiscoveryService.analysis_state()` para determinar si hay suficientes features disponibles para responder la consulta.

---

## Cola de karaoke — `servicios/karaoke/`

### Diseño de un solo worker secuencial

La cola procesa un job a la vez — dos jobs de Demucs paralelos saturarían la GPU/CPU y degradarían ambas separaciones. El diseño es explícitamente secuencial.

### Estado de un job

```
en_cola → preparando → procesando → lista (éxito)
                     ↘             ↘ fallida (error)
                      ↘             ↘ cancelada (stop_event)
```

- `preparando`: el modelo está siendo cargado / la pista está siendo preparada
- `procesando`: Demucs está activo, se reporta progreso 0.0–1.0
- `lista`: archivo instrumental disponible en cache

### Persistencia y recovery

Los jobs se persisten en `karaoke_jobs` (SQLite). Al iniciar el worker, `limpiar_jobs_zombies()` detecta jobs en estados intermedios (`preparando`, `procesando`, `generando`) que quedaron colgados por un crash y los marca como `cancelada`.

El archivo separado (instrumental) se guarda en `cache_dir/karaoke/<pista_id>/`. Si ya existe un archivo válido (>1KB) para una pista, se reutiliza sin re-ejecutar Demucs (cache hit).

### Cache de stems para DJ Privado

`servicios/dj_privado/stems_karaoke.py` consulta el estado de la cola karaoke para determinar si los stems de una pista ya están disponibles. `stems_prefetch.py` precarga anticipadamente los stems de la siguiente pista planificada por el scheduler, de forma que la transición en vivo no espere a que Demucs termine.

### Progreso y ETA

El snapshot de progreso implementa estimación de ETA en tres niveles:

1. Si ya hay ≥1 pista completa: ETA = tiempo_promedio_por_pista × pendientes
2. Si el job actual tiene progreso medible (>5%): extrapolación desde progreso actual
3. Sin datos: "calculando..."

Esto hace que la ETA aparezca desde los primeros segundos sin esperar a que complete la primera pista.

---

## Sidecars del pipeline CLI — `core/pipeline.py`

Los sidecars son tareas asíncronas que corren en paralelo con el pipeline principal pero cuyo resultado no es crítico para la decisión del archivo.

### `_SidecarExecutorDaemon`

Implementación propia de executor de hilos daemon con dos workers. Características que justifican la implementación propia en lugar de `ThreadPoolExecutor`:

1. **Control de timeout por tarea**: el pipeline espera hasta `SIDECAR_FUTURE_TIMEOUT_SEG` por sidecar; después lo marca como timeout y continúa.
2. **Estado `late_saved`**: un sidecar que termina *después* de su timeout no pierde el resultado — lo detecta verificando si su key está en `_sidecars_timeout` y lo persiste con estado especial.
3. **Shutdown con cancelación de futures pendientes**: al cancelar el pipeline, los futures no iniciados se cancelan para liberar recursos.

### Tipos de sidecar

| Sidecar | Descripción | Fallo |
|---|---|---|
| `assets` | Descarga portadas e imágenes de artista | No bloqueante; manifest incluye `status: error` |
| `enrichment` | Letras, análisis básico | No bloqueante; retryable via ImportRecovery |
| `manifest` | Escribe JSON de pista | Se reintenta una vez; warning en log |

Los manifests de pistas aceptadas con sidecars activos se difieren hasta que al menos un sidecar complete. Esto evita escribir un manifest sin información de assets que se publicará segundos después.

---

## Concurrencia y thread-safety

### SQLite

La conexión a SQLite usa un `threading.RLock()` en `db/conexion.py`. Todas las operaciones de escritura pasan por este lock, garantizando serialización. El modo WAL de SQLite permite lecturas concurrentes mientras hay una escritura activa.

### Estado de audio intelligence

`_PROCESS_LOCK` (threading.Lock) en `core/audio_intelligence_background.py` garantiza que solo un worker de análisis profundo corra simultáneamente por proceso. Una segunda llamada a `process_pending()` retorna inmediatamente con warning.

### Feature store

Las operaciones de lectura del feature store (para música discovery, estadísticas) no requieren lock porque SQLite garantiza consistencia de lectura. Las escrituras pasan por el RLock del módulo de conexión.

### Workers Qt y el hilo principal

Los modelos QML (`ui/modelos_qml.py`) son QObjects que viven en el hilo principal. Los workers emiten señales que Qt despacha al hilo principal de forma segura (queued connections). Los workers nunca acceden directamente a propiedades de los modelos QML.

---

## Monitoreo y observabilidad

Ver [observability.md](observability.md) para el sistema de logging y `ControlEjecucion`.

El snapshot de progreso del worker de importación se mapea directamente a propiedades del `ModeloImportacion`:
- `fase`, `etapa`: fase del pipeline y etapa actual
- `procesados`, `total`: contadores globales
- `eta_segundos`, `velocidad`: métricas de rendimiento
- `extras`: contadores por tipo de sidecar

---

← [Volver a arquitectura](architecture.md)
