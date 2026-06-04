# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [1.0.1] — 2026-06-04

Versión de parche centrada en consistencia de zona horaria, correcciones de
interfaz, diagnóstico de importación y disponibilidad de la CLI en la app
instalada.

### Corregido

- **Zona horaria en la interfaz**: todas las marcas de tiempo se muestran ahora
  en la hora local del sistema. Antes se veían en UTC (p. ej. +5 h en Colombia)
  en las ejecuciones/resultados de importación, la última conexión de los
  dispositivos vinculados, la última copia de seguridad y la hora pico del
  perfil. Los datos se siguen guardando en UTC; solo cambió la presentación.
- **Hora pico del perfil**: se calculaba sobre la hora UTC; ahora usa la hora
  local, consistente con el resto de las estadísticas.
- **Análisis musical en segundo plano**: al quedar "Completado" no aparecía el
  botón para buscar pistas pendientes e iniciar el análisis de las demás; ahora
  se muestra (también en los estados "Sin tareas", "Cancelado" y "Error
  parcial").
- **Diagnóstico y reintentos**: si se salía de Importación con un reintento en
  curso, el estado quedaba congelado hasta cerrar la app. El botón "Refrescar"
  ya no se desactiva y, además de refrescar, detecta y reconcilia el estado real
  del reintento; al volver a la vista la reconciliación también es automática.
- **Reintento de features**: el indicador incluía filas huérfanas en
  `track_audio_features` (de pistas movidas o re-importadas) que el reintento
  nunca podía procesar, por lo que el número no bajaba y parecía que "no hacía
  nada". El conteo se limita ahora a las pistas de la biblioteca actual,
  coherente con lo que el reintento procesa realmente.
- **Reproducir playlist con un clic**: en las tarjetas de playlist, el botón de
  reproducir requería doble clic (la carga de pistas era asíncrona); ahora suena
  con un solo clic. El doble clic sobre la tarjeta sigue abriendo la playlist.
- **Modo de visualización de playlists**: la elección de lista / cuadrícula
  (pequeña, mediana, grande) no se conservaba entre sesiones; ahora persiste.
- **Botón "Revocar"** (Sincronización): se alinea a la derecha y se centra
  verticalmente en la tarjeta del dispositivo vinculado.
- **Marca de tiempo de sincronización**: corregido un formato ISO que omitía los
  segundos.

### Cambiado

- **Rutas en Configuración** (básica y avanzada): los campos de carpeta
  (entrada, biblioteca, cuarentena, revisión, logs, procesados, assets, caché,
  temporales, manifiestos y modelos de Essentia) incorporan un botón "Examinar"
  que abre el explorador del sistema para elegir la carpeta, igual que el destino
  de la copia de seguridad. Se mantiene la edición manual del texto.
- **CLI en la app instalada**: el binario empaquetado sirve también la CLI.
  `nb-sound` abre la interfaz gráfica y `nb-sound cli ...` ejecuta el catalogador
  (la salida aparece en la terminal en Linux/macOS). Antes la CLI solo estaba
  disponible con el repositorio clonado.
- **Documentación**: se eliminaron las referencias a trabajo "a futuro" y el
  roadmap de construcción del ecosistema móvil, reescribiendo lo relativo a la
  app móvil como ya construido. El README incorpora un apartado de la app móvil
  (Android/iOS) con enlace al repositorio, la captura de la vista de
  Sincronización y una nota sobre las capturas tomadas en Pop!_OS.

### Eliminado

- **Opción "Deep al importar (legacy bloqueante)"** de Configuración avanzada y
  toda su lógica asociada (análisis profundo síncrono y bloqueante durante la
  importación). El análisis profundo se ejecuta en segundo plano mediante la
  cola reanudable.

## [1.0.0] — 2026-06-03

Primera versión pública de NB SOUND: catalogador inteligente de bibliotecas de
audio con motor de línea de comandos y aplicación de escritorio. Todo el
procesamiento ocurre en local, sin nube ni servicios de terceros para
administrar la colección. Esta entrada describe el conjunto completo de
funcionalidades incluidas en el lanzamiento inicial.

### Aplicación de escritorio (PySide6 / QML)

- Vistas funcionales: Inicio, Búsqueda, Biblioteca, Playlists, Importación,
  Configuración, Perfil, Karaoke, DJ Privado, Explorador Ciego, Sincronización
  y Estado del sistema.
- Reproductor global con cola persistente, reordenable y no consumible (estilo
  Spotify): la pista reproducida permanece en la cola, se puede retroceder y, al
  terminar la última sin repetición, queda marcada como actual lista para
  reanudar. Modos de repetición y aleatorio, pantalla completa, mini reproductor,
  letras sincronizadas y visualización de portada. La pista activa, la posición y
  la cola se conservan entre reinicios. Atajos de teclado para transporte, cambio
  de pista, karaoke y "sorpréndeme".
- Ecualizador del reproductor global (Configuración → Personalización): toggle
  de activación, 18 preajustes de libVLC más "Personalizado", 10 bandas
  (31 Hz – 16 kHz) y pre-amplificación, aplicados en vivo y reaplicados en cada
  pista. Opción "Estabilizar volumen" (normvol) por pista. La cadena de audio
  del reproductor global está aislada de la del DJ Privado.
- Sistema de temas con 63 paletas predefinidas más tema personalizado; el
  contraste de los acentos se calcula dinámicamente (WCAG).
- Búsqueda universal en tiempo real y búsqueda natural opcional asistida por IA
  (interpreta intención, no solo coincidencia exacta).
- Menú "agregar a playlist" estilo Spotify en Biblioteca, Búsqueda, detalle de
  playlist y reproductor; gestión completa de playlists, incluidas listas
  generadas tipo "This is…". Las carátulas de playlist se generan como mosaico
  con las portadas de sus canciones; al arrancar, un barrido en segundo plano
  regenera las que falten o estén obsoletas y refresca Inicio y Playlists, para
  asegurar que toda playlist tenga su carátula hecha.
- Refresco en vivo tras la importación: estadísticas, biblioteca, playlists,
  karaoke, análisis profundo y caché de letras se actualizan sin reiniciar.
- Cierre limpio: workers, timers, VLC y el ownership de audio del DJ se liberan
  antes de que Qt destruya los QObject; el mini reproductor no deja audio
  huérfano al cerrar la ventana principal.

### Pipeline de catalogación (CLI)

- Identificación por AcoustID, Shazam y MusicBrainz, con desempate opcional por
  IA (Anthropic u OpenAI) cuando los candidatos son ambiguos.
- Reescritura segura de tags ID3 con copia temporal, validación y movimiento
  atómico.
- Detección de duplicados en tres capas: exactos por hash SHA256, semánticos
  (`mb_recording_id` + ISRC) y observables (título, artista, álbum, duración y
  portada normalizados). Funciona durante la importación y como barrido
  periódico en background, reanudable e idempotente; la pista perdedora se marca
  como duplicada sin borrarse (reversible).
- Descarga organizada de portadas, imágenes de artistas y letras sincronizadas
  (LRC), priorizando alta resolución y validando contraste.
- Resolución en dos y tres fases post-clasificación para recuperar pistas
  enviadas inicialmente a revisión o cuarentena.
- Análisis de audio local por pista (BPM, energía, danceability, vibe tags) con
  `librosa`, ejecutado como sidecar de la importación.
- Análisis profundo opcional con modelos Essentia/TensorFlow (moods, géneros
  Discogs400, embeddings MusicNN/VGGish), aislado en un subprocess Python
  externo con protocolo JSON por línea para no bloquear la UI ni acoplar
  versiones nativas al bundle.
- Modo dry-run, recuperación post-importación basada en manifiestos y
  procesamiento reanudable.

### Karaoke local con IA

- Separación de voz e instrumental con Demucs/PyTorch, ejecutada localmente sin
  subir audio a servidores externos.
- Conmutación en vivo entre original e instrumental sin perder posición ni
  letras.
- Cola con cancelación fiable en cualquier estado y reconciliación de la caché
  cuando un job queda colgado tras un cierre forzado.

### DJ Privado

- Sesiones continuas generadas desde un prompt en lenguaje natural, con mezcla
  real: cortes alineados a beat, EQ kills, sweeps de filtro y crossfades
  stem-aware usando la salida del separador de karaoke.
- Persistencia de la sesión (pista y posición) entre reinicios, retomando en
  pausa para evitar reproducción inesperada.
- Guardar la sesión como playlist sin duplicar; volumen del player persistente.

### Explorador Ciego

- Redescubrimiento sobre la propia biblioteca con varios modos de juego, pistas
  progresivas y validación por escritura. Funciona sin conexión: todo sale del
  historial, las portadas y los metadatos ya catalogados.

### Ecosistema móvil (servidor local en el PC)

- Servidor HTTP REST + WebSocket bajo demanda (`aiohttp`) en su propio hilo y
  event loop, aislado de Qt: selección de puerto libre, bind a la IP de la LAN
  y anuncio por mDNS/DNS-SD para reconexión, con arranque y parada idempotentes.
- Emparejamiento por QR con token efímero de un solo uso y `device_token`
  persistente por dispositivo; todo el tráfico va autenticado. TLS (HTTPS/WSS)
  con certificado autofirmado y emparejamiento TOFU por huella SHA-256, con
  degradación a HTTP plano si falta `cryptography`.
- Protocolo de sincronización delta por `sync_version`: descarga de audio y
  portadas con `Range` (HTTP 206) validada por hash, merge de historial y
  favoritos (last-write-wins), stems de karaoke opt-in, paginación del manifest
  y control remoto bidireccional del reproductor por WebSocket.
- Vista de Sincronización en la app con estado del servidor, QR, dispositivos
  vinculados (revocables) y copia de seguridad.

### Copia de seguridad

- Exportación a un archivo `.nbsound-backup` (ZIP con la BD vía `VACUUM INTO`,
  assets y `manifest.json` con checksums) y restauración que valida integridad
  antes de reemplazar la BD viva de forma atómica.
- Copia de seguridad programada con carpeta de destino persistente y frecuencia
  configurable; el respaldo se crea en background con la app abierta cuando vence
  el plazo.

### Plug & play y Estado del sistema

- Detección automática de torch / demucs / essentia-tensorflow y modelos `.pb`
  al primer arranque, con instalación guiada (incluido "Instalar todo"
  secuencial y consciente del SO) sin reiniciar el proceso.
- Pre-descarga del modelo Demucs (`htdemucs`, ~80 MB) al caché configurado, con
  promoción automática si los pesos quedaron en otra caché histórica.
- Reparación asistida de Python del sistema (instalación de `pip`/`venv`
  faltantes) vía `pkexec` en Linux cuando se requiere para habilitar
  dependencias opcionales.

### Distribución y empaquetado

- Bundles nativos para Linux (`.deb`, `.rpm`, `.AppImage`, `.tar.gz`), Windows
  (`.exe` con instalador + `.zip` portable) y macOS (`.dmg` + `.zip`).
- Especificaciones de empaquetado PyInstaller por SO con un builder común
  (`packaging/_common.py`): hidden imports, datas y exclusión de librerías del
  sistema (libvlc, libstdc++, libdbus, libsystemd) para evitar conflictos ABI.
- `ffmpeg`, `ffprobe` y `fpcalc` empaquetados como datas y antepuestos al `PATH`
  del proceso para que demucs y AcoustID los encuentren sin depender del PATH
  del lanzador.
- Módulos fuente requeridos por el subprocess de análisis profundo incluidos
  como datas extraíbles; hidden imports preventivos de stdlib que cargan
  paquetes opcionales de forma dinámica.
- Integración de escritorio en Linux (icono en panel/dock vía
  `setDesktopFileName` + `StartupWMClass`, metainfo AppStream y archivo
  `.desktop`) y metadatos de versión/desarrollador embebidos en el `.exe` de
  Windows, con firma Authenticode opcional.
- Inicialización automática de directorios estándar al primer arranque (XDG en
  Linux, `%LOCALAPPDATA%`/`%APPDATA%` en Windows, `~/Library` en macOS).
- GitHub Actions: matriz de portabilidad (Linux/Windows/macOS × Python 3.12) en
  cada push y un workflow de release que construye los tres bundles nativos.

### Persistencia y arquitectura

- Base de datos SQLite con migraciones controladas y conexión bajo lock para
  acceso seguro desde múltiples hilos; las tablas y columnas de sincronización
  se crean de forma aditiva al abrir la BD.
- Configuración por entorno mediante `.env`; las preferencias de UI se guardan
  en `config_ui` y sobrescriben los defaults de `settings` en runtime.
- Worker genérico (`_UiQueryWorker`) que mueve queries SQL pesadas a un
  `QThread` descartable y aplica el resultado en el hilo principal vía signal,
  manteniendo la UI fluida en bibliotecas grandes.
- Defensa en profundidad contra duplicados: además del dedupe del pipeline, el
  indexador comprueba colisión de hash contra cualquier ruta existente antes de
  insertar y limpia el archivo recién copiado si detecta un duplicado.
- Logger reentrante con line-buffering: sobrevive a cierres abruptos y al cierre
  de handlers del pipeline, y se re-inicializa tras cada importación.
- Interfaz condicional por plataforma: en Windows (sin wheel funcional de
  `essentia-tensorflow`) la UI de análisis profundo se oculta sin eliminar la
  lógica Python.
- Amplia suite de tests automatizados que cubre pipeline, recovery, contratos de
  UI, tokens de tema, artefactos de empaquetado, fallbacks cross-platform, ciclo
  de vida de workers, deduplicación persistente, refresco en vivo
  post-importación, sincronización y ecualizador del reproductor.
