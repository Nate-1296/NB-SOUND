# Arquitectura técnica

NB SOUND está dividido en dos capas que comparten la misma base de datos SQLite: el cerebro CLI y la interfaz gráfica.

---

## Estructura de directorios

```text
nb_sound/
├── config/          # Carga de configuración desde .env
├── core/            # Lógica principal del pipeline de catalogación
├── db/              # Esquema SQLite y capa de conexión
├── domain/          # Contratos y modelos de dominio
├── external/        # Clientes para APIs externas (Shazam, MusicBrainz, AcoustID, etc.)
├── infra/           # Movimiento de archivos, logs, progreso, cuarentena
├── servicios/       # Servicios de aplicación usados por la UI
├── ui/              # Interfaz gráfica (modelos QML y archivos QML)
│   ├── modelos_qml.py
│   └── qml/
│       ├── Principal.qml
│       ├── componentes/
│       ├── vistas/
│       └── assets/icons/
├── utils/           # Utilidades compartidas
├── workers/         # Workers Qt para operaciones en background
├── tests/           # Suite de tests automatizados
├── main.py          # Punto de entrada del CLI
└── main_ui.py       # Punto de entrada de la UI
```

---

## El cerebro CLI

### `main.py`

Construye el parser de argumentos, valida la configuración y crea el `PipelineCatalogacion`. Antes de procesar valida rutas, parámetros numéricos, claves de API y riesgo de solapamiento de directorios.

### `core/`

| Módulo | Responsabilidad |
| --- | --- |
| `pipeline.py` | Orquestador principal: descubrimiento, normalización, identificación, decisión y escritura |
| `normalizer.py` | Limpieza de títulos, artistas, versiones y construcción de slugs |
| `matcher.py` | Scoring multi-señal y decisión de aceptar/revisar/cuarentenar |
| `writer.py` | Escritura segura de tags ID3 (copia → escribe → valida → mueve) |
| `second_stage.py` / `third_stage.py` | Recuperación conservadora de casos no resueltos |
| `assets_pipeline.py` | Descarga y gestión de portadas e imágenes de artistas |
| `audio_features.py` | Análisis local con librosa |
| `audio_intelligence_background.py` | Cola reanudable de análisis profundo |
| `audio_intelligence_deep.py` | Analyzer Essentia/TensorFlow (corre en bundle o en subprocess) |
| `audio_intelligence_deep_subprocess.py` | Adaptador thread-safe que delega `analyze` a un subprocess Python externo (`infra/deep_runner.py`) para aislar TensorFlow del proceso de la UI. Misma API que `EssentiaTensorflowAnalyzer`; se selecciona automáticamente cuando `sys.frozen` o `NB_SOUND_DEEP_SUBPROCESS=1` |
| `dedupe.py` | Detección de duplicados en tres ejes: exacto (hash SHA256), semántico (ISRC + `mb_recording_id`) y **observable** (título/artista/álbum normalizados + duración ±tolerancia + hash de la portada). Pre-carga desde la biblioteca para que reimportaciones no creen duplicados. La normalización de texto usa `utils.text.normalizar_para_comparar` (algoritmo único compartido con el explorador ciego) |
| `import_recovery_service.py` | Recuperación selectiva post-importación: assets faltantes, enrichment fallido, lyrics, sidecars, deep, audio features. Las acciones de retry NO importan archivos nuevos |
| `music_discovery_service.py` | Búsqueda natural sobre features disponibles |
| `discovery.py` | Ruteo de consultas externas (AcoustID, Shazam, MusicBrainz) |

### `external/`

Clientes para cada servicio externo, todos con timeout, reintento con backoff y degradación controlada si el servicio no está disponible.

### `db/`

- `esquema.py` — DDL completo con todas las tablas y migraciones
- `conexion.py` — Singleton con lock Python para acceso seguro desde múltiples hilos

---

## La interfaz gráfica

### `main_ui.py`

Configura Qt, ejecuta el [bootstrap inicial](#bootstrap-de-primer-arranque)
si la app arranca sin configuración previa, inicializa SQLite,
instancia los modelos Python y carga `Principal.qml`. Registra todos
los modelos como propiedades de contexto QML y conecta el cierre
ordenado al evento `aboutToQuit` (ver [recovery y resiliencia](recovery-and-resilience.md#cierre-ordenado-de-la-aplicación)).

### `servicios/`

Aíslan lógica que no debe vivir en QML ni en los modelos reactivos:

| Servicio | Responsabilidad |
| --- | --- |
| `biblioteca.py` | Consultas de colección, inicio, búsqueda, estadísticas y playlists |
| `importacion.py` | Ejecución de importaciones, progreso e historial |
| `indexador.py` | Indexado de música existente hacia SQLite |
| `dedupe_observable.py` | Barrido periódico en background (tercera capa de dedupe) sobre la biblioteca catalogada: detecta duplicados observables y resuelve según `DUPLICATE_POLICY` marcando la pista perdedora con `estado='duplicado'` (no borra, reversible). Reanudable e idempotente; lo lanza `ModeloBiblioteca.ejecutarDedupeObservable()` vía `WorkerDedupeObservable` y refresca las vistas en vivo |
| `reproductor.py` | Reproducción, cola, lyrics, karaoke y avisos del backend |
| `karaoke/` | Separación voz/instrumental (Demucs), cola persistente |
| `dj_privado/` | Director musical: ontología, intent, scheduler, transiciones (ver [dj_privado.md](dj_privado.md)) |

### `ui/modelos_qml.py`

Modelos reactivos que conectan Python con QML mediante señales, propiedades (`@Property`) y slots (`@Slot`):

| Modelo | Uso |
| --- | --- |
| `ModeloBiblioteca` | Álbumes, artistas, pistas y detalle |
| `ModeloReproductor` | Estado del reproductor, cola, progreso, lyrics |
| `ModeloBusqueda` | Búsqueda clásica y natural |
| `ModeloEstadisticas` | Métricas de biblioteca e inicio |
| `ModeloPlaylists` | CRUD, automáticas, colecciones y portadas |
| `ModeloImportacion` | Progreso, historial y audio intelligence background |
| `ModeloRevision` | Elementos pendientes y decisiones manuales |
| `ModeloConfiguracion` | Rutas, claves, temas y modo simple/pro |
| `ModeloTema` | Tema visual y tokens de diseño |
| `ModeloAudioIntelligenceBackground` | Estado y control del deep background |
| `ModeloKaraoke` | Cola de preparación de instrumentales, snapshot de procesamiento |
| `ModeloDjPrivado` | DJ Privado: intent, sesión, timeline, adaptación en vivo |
| `ModeloExploradorCiego` | Estado de la ronda, retos visibles, modos y validación |
| `ModeloDependencias` | Plug & play: detecta torch/demucs/essentia + modelos, instalación guiada |
| `ListaGenerica` | `QAbstractListModel` genérico para cualquier lista de dicts |
| `_UiQueryWorker` | Helper genérico que ejecuta queries SQL en un `QThread` descartable y aplica el resultado en el hilo principal vía signal; usado por todos los modelos cuyas queries pueden tardar (biblioteca, karaoke, playlists, estadísticas, diagnóstico backend) para mantener la UI a 60 fps |

### `ui/qml/`

Arquitectura QML:

- `Principal.qml` — shell maestro: navegación lateral, área central con lazy loading, barra de reproducción, overlays y z-order global
- `componentes/` — componentes reutilizables (barra de reproducción, cola, lyrics, toast, tokens, etc.)
- `vistas/` — cada vista principal en su propio archivo `.qml`
- `assets/icons/` — iconografía SVG reactiva al tema

---

## Base de datos

SQLite local en `USER_LIBRARY_DIR/nb_sound.sqlite3`. Tablas principales:

```text
artistas, albums, pistas               — Biblioteca catalogada
historial                              — Reproducciones registradas
playlists, pistas_playlist             — Sistema de playlists
config_ui                              — Configuración persistida de la UI
cola_reproduccion                      — Estado de la cola
sesiones_import                        — Historial de importaciones
track_audio_features, track_vibe_tags  — Features de audio básicas
track_deep_audio_features              — Features profundas (Essentia)
audio_analysis_jobs, audio_analysis_runs — Control de jobs deep
```

La conexión usa un lock Python para garantizar acceso seguro desde múltiples hilos (workers de importación, búsqueda, background deep).

---

## Workers Qt

`workers/workers_qt.py` contiene `QThread`-based workers para operaciones que no deben bloquear la UI:

- `WorkerBusqueda` — búsqueda clásica con descarte de resultados obsoletos
- `WorkerBusquedaNatural` — búsqueda natural sobre Music Discovery
- `WorkerImportacion` — ejecución del pipeline CLI desde la UI
- Otros workers para indexado, diagnóstico y control de deep background

---

## Bootstrap de primer arranque

`infra/bootstrap.py` resuelve rutas estándar por sistema operativo y
garantiza que la aplicación se pueda iniciar sin configuración previa.

Se ejecuta dentro de `inicializar_aplicacion()` antes de inicializar la
base de datos:

1. **Resolución de rutas** según el sistema operativo:
   - Linux: `$XDG_DATA_HOME`, `$XDG_CACHE_HOME`, `$XDG_CONFIG_HOME`.
   - Windows: `%LOCALAPPDATA%`, `%APPDATA%`, `%USERPROFILE%/Music`.
   - macOS: `~/Library/Application Support`, `~/Library/Caches`, `~/Library/Preferences`.
2. **Creación idempotente** de los directorios faltantes (biblioteca,
   logs, cuarentena, revisión, cache, temp, assets, manifests, config).
   Si un directorio ya existe se respeta intacto.
3. **Generación condicional de `.env`**: solo cuando no existe `.env` en
   el proyecto y `USER_LIBRARY_DIR` no está resuelto vía variables de
   entorno. Nunca sobreescribe configuración del usuario.

El bootstrap reporta a `stderr` lo que crea; un fallo de filesystem
(permisos, partición de solo lectura) no detiene el arranque: la app
intenta operar en modo degradado y registra el aviso.

---

## Documentación técnica por subsistema

Para mayor detalle sobre subsistemas específicos:

| Documento | Contenido |
| --- | --- |
| [Ciclo de vida de importación](import-lifecycle.md) | Pipeline completo: descubrimiento → escritura → sidecars → recovery |
| [Pipeline de audio](audio-pipeline.md) | Análisis básico (librosa), análisis profundo (Essentia), feature store |
| [Procesamiento en background](background-processing.md) | Workers Qt, cola karaoke, sidecars del CLI |
| [Arquitectura de reproducción](playback-architecture.md) | VLC, karaoke, DJ Privado y mezcla real |
| [Arquitectura QML](qml-architecture.md) | Puente Python↔QML, modelos reactivos, componentes |
| [Observabilidad](observability.md) | Logging estructurado, ControlEjecucion, reports |
| [Recovery y resiliencia](recovery-and-resilience.md) | Mecanismos de recuperación ante fallos e interrupciones |

---

## Filosofía de diseño

**El cerebro no inventa metadata.** Si no hay evidencia suficiente, manda a revisión o cuarentena. La IA solo desempata entre candidatos ya encontrados.

**La UI no llama directamente a la base de datos.** Todo pasa por servicios Python que controlan el acceso, normalizan los datos y gestionan la concurrencia.

**El procesamiento es reanudable.** Jobs y runs se registran en SQLite. Si el proceso muere, puede retomarse exactamente desde donde estaba.

**La UI nunca bloquea.** Todas las operaciones largas corren en workers Qt y reportan estado mediante señales. Queries SQL pesadas pasan por `_UiQueryWorker` (QThread descartable); el análisis deep corre en un subprocess Python externo aislado del proceso Qt para evitar acoplar versiones nativas de TensorFlow al bundle y para no acaparar el GIL.

**Nada se duplica al reimportar.** El dedupe del pipeline se carga desde la biblioteca al inicio de cada corrida, y el indexador comprueba colisión de hash contra cualquier ruta existente antes de insertar — defensa en profundidad ante cualquier fallo del flujo principal.

**Los logs sobreviven a todo.** El logger usa line-buffering para no perder líneas en cierres abruptos, es reentrante (se reabre si el directorio cambia o si el pipeline cierra sus handlers) y se re-inicializa automáticamente tras cada importación para que cualquier error posterior quede auditable.

---

← [Volver al README](../README.md)
