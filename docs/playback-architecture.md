# Arquitectura de reproducción

Documentación técnica del subsistema de reproducción: reproductor principal, karaoke y DJ Privado.

---

## Visión general

NB SOUND tiene tres modos de reproducción con diferentes características:

```
Reproducción estándar          → servicios/reproductor.py → VLC
Karaoke (vocal/instrumental)   → servicios/karaoke/ + reproductor.py → VLC (dos streams)
DJ Privado (sesiones mixadas)  → servicios/dj_privado/ → mix_engine → VLC
```

Todos los modos comparten el backend VLC pero con configuraciones y contratos diferentes.

---

## Reproductor principal — `servicios/reproductor.py`

### Backend VLC

La reproducción usa `python-vlc` como wrapper de LibVLC. VLC se instancia como un `MediaPlayer` con un hilo propio de decodificación y render de audio.

El reproductor no corre en el hilo principal de Qt. Las señales de estado (posición, duración, fin de pista) llegan via polling desde un `QTimer` en el modelo, no via callbacks de VLC directamente — VLC puede emitir callbacks desde hilos no-Qt, lo que requeriría sincronización compleja.

### Cola de reproducción

La cola persiste en SQLite (`cola_reproduccion`), lo que permite:
- Restaurar la cola entre reinicios de la app
- Compartir el estado de la cola entre el proceso de reproducción y la UI
- Reordenamiento por drag & drop desde QML con persistencia inmediata

La cola tiene un índice de posición actual. Las operaciones de "siguiente" y "anterior" incrementan/decrementan el índice. La operación "shuffle" reorganiza los índices sin modificar los datos de la pista.

### Historial de reproducción

Cada reproducción ≥30 segundos se registra en la tabla `historial` con timestamp, duración escuchada y tipo de fuente (manual, cola, dj, karaoke). Este historial alimenta las estadísticas de `VistaPerfil` y las recomendaciones automáticas.

### Lyrics

Las lyrics sincronizadas (con timestamps en formato LRC) se cargan desde el manifest de enrichment de la pista. El reproductor interpola la posición actual contra los timestamps para determinar el verso activo.

Las lyrics se exponen en `ModeloReproductor.lyricActual` (línea actual) y `ModeloReproductor.lyricsSincronizadas` (lista completa para `VistaLyrics.qml`).

---

## Karaoke — `servicios/karaoke/`

### Separación vocal/instrumental

La separación usa **Demucs** (Meta), un modelo de separación de fuentes neuronal. Demucs genera cuatro stems (vocals, drums, bass, other); el sistema combina drums+bass+other para generar la pista instrumental.

El proceso tarda entre 1–10 minutos por pista dependiendo del hardware:
- CPU: ~5–10 min por pista de 4 min
- GPU NVIDIA (CUDA): ~30–90 seg
- Apple Silicon (MPS): ~60–120 seg

### Cola persistente

Ver [background-processing.md](background-processing.md) para el detalle de la cola. Desde la perspectiva del reproductor:

- La UI encola pistas via `modeloKaraoke.encolar(pistaId)`
- El worker procesa la cola en background y notifica al modelo cuando la pista está lista
- El reproductor puede cargar el instrumental mientras continúa sonando la pista normal

### Conmutación en tiempo real

Cuando el karaoke está activo y la pista tiene su instrumental listo, el reproductor mantiene dos `MediaPlayer` de VLC sincronizados:
1. El audio original (voz + instrumental)
2. El stem instrumental separado

La conmutación se realiza con un crossfade de ~50ms para evitar clic. La posición se sincroniza entre los dos reproductores en cada cambio.

### Integración con DJ Privado

`servicios/dj_privado/stems_karaoke.py` consulta el estado del karaoke para determinar si los stems de una pista ya están disponibles. `stems_prefetch.py` anticipa la descarga de stems para la siguiente pista planificada por el scheduler, de forma que las transiciones con capas de stems no tengan latencia.

---

## DJ Privado — `servicios/dj_privado/`

El DJ Privado es el subsistema más complejo de la aplicación. Genera sesiones continuas de música a partir de un prompt del usuario, con mezcla real en tiempo real.

### Componentes

```
DjPrivadoService (servicio.py)
  ├─ IntentParser (intencion.py)      → analiza el prompt del usuario
  ├─ OntologiaMusical (ontologia.py)  → grafo de géneros y relaciones semánticas
  ├─ EmbeddingEngine (embeddings.py)  → similitud vectorial entre pistas
  ├─ SessionConstructor (constructor.py) → plan de sesión (qué pistas, en qué orden)
  ├─ DjScheduler (scheduler.py)       → planificador dinámico de siguiente pista
  ├─ MixEngine (mix_engine.py)        → procesamiento de audio para transiciones
  ├─ TransitionEngine (transiciones.py) → tipos de transición
  ├─ ReproductorSesion (reproductor_sesion.py) → coordina VLC durante la sesión
  ├─ NarrativaEngine (narrativa.py)   → comentarios entre pistas
  └─ DjPersistencia (persistencia.py) → estado de sesión en SQLite
```

### Ciclo de vida de una sesión

```
1. usuario escribe prompt ("jazz tranquilo para estudiar")
2. IntentParser.analizar() → IntentMusical (mood, energía, géneros, BPM)
3. SessionConstructor.construir() → BloqueConstruido (lista de pistas)
4. ReproductorSesion.iniciar() → VLC empieza a reproducir la primera pista
5. DjScheduler monitorea el avance y planifica la siguiente pista
6. MixEngine prepara la transición cuando quedan ~15-30 seg de la pista actual
7. [transición]
8. → volver a 5
```

### Tipos de transición

`transiciones.py` implementa:

| Tipo | Descripción | Cuándo se usa |
|---|---|---|
| `cut` | Corte en el beat más cercano | Pistas del mismo BPM/compás |
| `crossfade` | Fundido de amplitudes | Cambio suave de energía |
| `eq_kill` | Corte de bajos/agudos antes del fade | Estilo DJ de club |
| `filter_sweep` | Barrido de filtro paso-bajo | Transición dramática |
| `stem_layer` | Crossfade usando stems (voz+instrumental por separado) | Disponible si hay stems karaoke |

El `MixEngine` determina el tipo de transición basándose en:
- Diferencia de BPM entre pistas (cut solo si < 5% de diferencia)
- Energía relativa de las pistas (crossfade para diferencias grandes)
- Disponibilidad de stems (stem_layer cuando están precargados)
- Preferencia de la sesión (configurada por el intent)

### Adaptación en tiempo real

El usuario puede intervenir durante la sesión:

- **Skip**: el scheduler excluye la pista y recalcula el bloque siguiente con una alternativa compatible
- **Like**: aumenta el peso de pistas similares en el scoring del scheduler
- **Dislike**: excluye pistas del mismo artista/álbum del bloque actual
- **Bloquear pista**: la protege de ser desplazada por replanificaciones
- **Replanificar desde**: recalcula el plan desde una posición específica

### Hardware profile

`hardware_profile.py` detecta el hardware de audio disponible y ajusta el comportamiento del mix engine:
- En sistemas sin GPU, evita procesamiento de señal complejo
- Detecta latencia del dispositivo de audio para ajustar el timing de crossfade
- Identifica si hay salida multicanal disponible

### Persistencia de sesiones

Las sesiones se guardan en SQLite con:
- El prompt original y el `IntentMusical` serializado
- La lista completa de pistas planificadas con sus posiciones
- El historial de acciones del usuario (skips, likes, replanificaciones)
- El estado de reproducción al momento del guardado (para restaurar)

Las sesiones guardadas se listan en `DjHistorial.qml` y se pueden retomar desde el mismo punto o regenerar con el mismo intent.

---

## Integración UI — `ModeloReproductor` y `ModeloDjPrivado`

### `ModeloReproductor`

El modelo de reproducción es el puente central entre VLC y QML. Sus responsabilidades:

- Polling de VLC via `QTimer` (cada 500ms) para actualizar posición y duración
- Manejo de señales de VLC (fin de pista, error de media)
- Gestión de la cola en memoria + sincronización con SQLite
- Coordinación de karaoke (dos streams sincronizados)
- Exposición de lyrics sincronizadas a QML
- **Modo ciego** para el Explorador Ciego (ver más abajo)

### Modo ciego (Explorador Ciego)

El reproductor expone un mecanismo de censura que el juego "¡A ciegas!" usa para que la barra inferior y el panel de cola no spoileen el título, artista, álbum o portada mientras el usuario está adivinando una pista de su biblioteca.

```python
@Slot(int)
def set_modo_ciego(self, pista_id: int) -> None: ...

@Slot()
def limpiar_modo_ciego(self) -> None: ...

@Property(int, notify=modoCiegoCambiado)
def blind_pista_id(self) -> int: ...
```

Mientras `blind_pista_id != 0` y la pista activa coincide:

- Los getters `titulo_activo`, `artista_activo`, `album_activo`, `pista_activa` y `pista_visual` devuelven `"???"` y portada vacía.
- La lista de cola (`cola`) reemplaza el mismo subconjunto de campos para los items cuya id coincida.
- Los slots de control humano (`pausar_reanudar`, `siguiente`, `anterior`, `buscar_posicion`, `reproducir_indice_cola`, `detener` y `reproducir(datos)` para pistas distintas) quedan bloqueados como no-op para que el usuario no pueda saltar/pausar/seekear la pista del reto y romper el juego.
- El propio juego usa métodos internos (no `@Slot`) que hacen bypass del bloqueo: `pausar_reanudar_forzado(reanudar)` y `detener_forzado()`. Esos métodos no son accesibles desde QML.

El modo ciego es estrictamente una capa de presentación: no toca el audio ni la cola subyacente. Al limpiar, todo vuelve a verse sin cambios de estado del reproductor.

### `ModeloExploradorCiego`

Expone el estado del juego a QML y coordina servicio puro Python + reproductor + timer del fragmento:

- `disponibles_por_modo`, `hay_biblioteca`: cuántas pistas hay listas para cada modo
- `modo_activo`, `ronda_activa`, `indice_reto`, `total_retos`, `conteo`: estado de la ronda
- `reto`: snapshot del reto actual con metadatos censurados, hints reveladas, alfabeto y `requiere_escritura`
- Slots para `iniciar_ronda`, `reproducir_fragmento`, `intentar_adivinar`, `revelar_hint`, `revelar_titulo`, `marcar_acertada`, `marcar_pasado`, `reproducir_completa`, `agregar_a_cola`, `alternar_favorita`, `siguiente_reto`, `terminar_ronda`
- Emite `mensajeUi(texto, tono)` con feedback del último intento (acierto, "muy cerca", fallido) — las `signal` de QML no devuelven valores, así que el feedback se centraliza aquí en lugar de en el callback de la vista

El timer del fragmento (12 s por defecto) corre en el hilo de UI: pausa el audio vía bypass al cumplirse el plazo. El juego usa el reproductor global como fuente de audio única, así que "Reproducir completa" sólo necesita reanudar la pista ya cargada.

→ Ver [docs/explorador-ciego.md](explorador-ciego.md) para el servicio Python puro y la máquina de estados del reto.

### `ModeloDjPrivado`

Expone el estado del DJ Privado a QML:
- `sesionActiva`: si hay una sesión en curso
- `pistaActual`, `pistaSiguiente`: pistas de la sesión
- `progreso`, `etaSeg`: avance de la sesión
- `bloqueConstruido`: lista de pistas planificadas visibles en el timeline
- Slots para skip, like, dislike, bloquear, extender y regenerar

Las operaciones del DJ Privado son síncronas en el hilo principal (son rápidas — no hacen I/O de audio) excepto el prefetch de stems, que corre en un worker separado.

---

← [Volver a arquitectura](architecture.md)
