# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [1.0.0] — 2026-05-24

Primera versión estable y distribuible de NB Sound.

### Aplicación de escritorio (PySide6 / QML)

- Diez vistas funcionales: Inicio, Búsqueda, Biblioteca, Playlists,
  Importación, Configuración, Perfil, Karaoke, DJ Privado y
  Explorador Ciego.
- Reproductor con cola persistente, modos de repetición y aleatorio,
  pantalla completa, mini reproductor, letras sincronizadas y
  visualización de portada.
- Sistema de temas con 61 paletas predefinidas más tema personalizado;
  contraste calculado dinámicamente (WCAG) sobre todos los acentos.
- Búsqueda universal en tiempo real y búsqueda natural opcional vía IA.
- Karaoke local con separación voz/instrumental Demucs y conmutación en
  vivo entre original e instrumental sin perder posición ni lyrics.
- DJ Privado: sesiones continuas desde un prompt en lenguaje natural,
  con mezcla real (cortes alineados a beat, EQ kills, sweeps de filtro
  y crossfades stem-aware usando la salida del separador de karaoke).
- Explorador Ciego: redescubrimiento sobre la propia biblioteca con
  cuatro modos, pistas progresivas y validación por escritura.
- Refresco en vivo tras importación: estadísticas, biblioteca,
  playlists, karaoke, deep y cache de letras se actualizan sin
  reiniciar la app.
- Cierre limpio: workers, timers, VLC y ownership DJ se liberan antes
  de que Qt destruya los QObject; el mini reproductor no deja audio
  huérfano tras cerrar la ventana principal.

### Pipeline de catalogación (CLI)

- Identificación por AcoustID, Shazam y MusicBrainz, con desempate
  opcional por IA (Anthropic u OpenAI) cuando los candidatos son
  ambiguos.
- Reescritura segura de tags ID3 con copia temporal, validación y
  movimiento atómico.
- Detección de duplicados exactos (hash SHA256) y semánticos
  (`mb_recording_id` + ISRC) con pre-carga desde la biblioteca: las
  reimportaciones no crean duplicados aunque el writer haya generado
  rutas distintas.
- Descarga organizada de portadas, imágenes de artistas y letras
  sincronizadas (LRC) priorizando alta resolución y validando contraste.
- Resolución en dos y tres fases post-clasificación para recuperar
  pistas inicialmente enviadas a revisión o cuarentena.
- Análisis de audio local (BPM, energía, danceability, vibe tags) por
  pista usando `librosa`; corre en background como sidecar de la
  importación.
- Análisis profundo opcional con modelos Essentia/TensorFlow (moods,
  géneros Discogs400, embeddings MusicNN/VGGish), aislado en un
  subprocess Python externo con protocolo JSON por línea para no
  bloquear el proceso de la UI ni acoplar versiones nativas al bundle.
- Modo dry-run, recuperación post-importación basada en manifiestos y
  procesamiento reanudable.

### Plug & play

- Detección automática de torch / demucs / essentia-tensorflow y
  modelos `.pb` al primer arranque, con instalación guiada desde la
  vista "Estado del sistema" sin reiniciar el proceso.
- Pre-descarga del modelo Demucs (`htdemucs`, ~80 MB) directamente al
  cache configurado por el usuario, con promoción automática si los
  pesos quedaron en otra cache histórica.
- Reparación asistida de Python del sistema (instalación de `pip` y
  `venv` faltantes) vía `pkexec` en Linux cuando se requiere para
  habilitar la instalación de dependencias opcionales.

### Distribución

- Bundles nativos para Linux (`.deb`, `.rpm`, `.AppImage`, `.tar.gz`),
  Windows (`.exe` con installer + `.zip` portable) y macOS (`.dmg` +
  `.zip`).
- Especificaciones de empaquetado PyInstaller por SO compartiendo un
  builder común (`packaging/_common.py`) con hidden imports, datas y
  exclusión de librerías del sistema (libvlc, libstdc++, libdbus,
  libsystemd) para evitar conflictos ABI en distros derivadas.
- `ffmpeg` + `ffprobe` + `fpcalc` empaquetados como datas y antepuestos
  al `PATH` del proceso para que demucs y AcoustID los encuentren sin
  depender del PATH del lanzador (cubre lanzamiento desde COSMIC,
  GNOME, KDE, SDDM minimal, etc.).
- Módulos fuente `.py` requeridos por el subprocess externo
  (`infra/`, `config/`, `core.audio_intelligence_deep`) incluidos en
  el bundle como datas extraíbles.
- Hidden imports preventivos para stdlib que paquetes opcionales
  cargan dinámicamente: `pickletools`, `logging.config/handlers`,
  `lzma`, `bz2`, `pdb`, `ssl`, `tomllib`, submódulos de `email`,
  `encodings`, `ctypes`, `multiprocessing` y `concurrent.futures`.
- Inicialización automática de directorios estándar en el primer
  arranque (XDG en Linux, `%LOCALAPPDATA%` / `%APPDATA%` en Windows,
  `~/Library` en macOS).
- AppStream metainfo y archivo `.desktop` freedesktop incluidos para
  integración con stores y launchers de distros Linux.
- GitHub Actions: matriz de portabilidad (Linux/Windows/macOS × Python
  3.12) en cada push, más un workflow de release que construye los tres
  bundles nativos al crear el tag.

### Persistencia y arquitectura

- Base de datos SQLite con migraciones controladas y conexión bajo
  lock para acceso seguro desde múltiples hilos.
- Configuración por entorno mediante `.env`; las preferencias de UI
  se guardan adicionalmente en `config_ui` y sobrescriben los defaults
  de `settings` en runtime.
- Worker genérico (`_UiQueryWorker`) que mueve queries SQL pesadas a
  un `QThread` y aplica el resultado en el hilo principal vía signal;
  la UI mantiene 60 fps incluso en bibliotecas grandes.
- Defensa en profundidad contra duplicados: además del dedupe del
  pipeline, el indexador comprueba colisión de hash contra cualquier
  ruta existente antes de insertar y limpia el archivo recién copiado
  si detecta duplicado.
- Logger reentrante con line-buffering: sobrevive al cierre del
  pipeline (que cierra sus handlers en `finally`), se re-inicializa
  tras cada importación y redirige al directorio configurado si éste
  cambia en runtime.
- Suite de 1044+ tests cubriendo pipeline, recovery, contratos UI,
  tokens de tema, artefactos de empaquetado, fallbacks cross-platform,
  ciclo de vida de workers, dedupe persistente, refresco live
  post-importación y API del subprocess deep.
