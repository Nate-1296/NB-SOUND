# Inventario de la V1 y su destino en la V2

> **Estado:** Vigente desde el 2026-10-29. **Auditado en F7.1.1 el 2026-10-31:** cada fila está Hecha, Rediseñada o
> Eliminada; la columna de la derecha dice cuál y dónde.

Base: NB Sound v1.1.16. Unas 111.000 líneas: 60.000 de Python de aplicación (`servicios` 22.397, `core` 11.216,
`ui/modelos_qml.py` 11.844, `infra` 5.077, `external` 2.979, `db` 1.358, `utils` 1.036, `config` 774,
`packaging` 682, `domain` 486, `workers` 408, `main.py` y `main_ui.py` 1.872), 23.381 de pruebas y 27.261 de QML.

**Destinos:** **Se porta** (misma función, otro lenguaje) · **Se rediseña** (la función sigue, la forma cambia) ·
**Se elimina** (con su motivo).

## Funciones del producto

| Función de la V1 | Dónde está | Destino | Fase | Estado (F7.1.1) |
|---|---|---|---|---|
| Reproductor, cola, aleatorio, repetición | `servicios/reproductor.py` | Se porta al motor de Rust | F2.1 | Hecha (`audio/`, `cola.rs`, `reproductor/`) |
| Ecualizador de 10 bandas, 18 preselecciones | `servicios/reproductor.py` | Se porta con `eq_filter` de Kira | F2.1.3 | Hecha, con filtros de campana propios en lugar de `eq_filter`: sus ganancias se corrigen analíticamente para quedar a 0,5 dB (`audio/ecualizador.rs`) |
| MPRIS | `infra/mpris_linux.py` | Se porta con `mpris-server`; se añaden SMTC y macOS | F2.1.5 | Hecha (`controles_sistema/`) |
| Inicio | `VistaInicio.qml` | Se porta | F2.2.2 | Hecha |
| Biblioteca y detalle de álbum | `VistaBiblioteca.qml`, `VistaDetalleAlbum.qml` | Se porta; artistas y álbumes como pestañas | F2.2.3 | Hecha |
| Playlists manuales, de sistema y automáticas | `VistaPlaylists.qml`, `servicios/biblioteca.py` | Se porta; las automáticas convergen con las inteligentes | F2.2.4, F8.2 | Hecha (`playlists.rs`, `playlists/inteligentes.rs`): manuales, "Me gusta", listas inteligentes vivas del usuario y regeneración de las automáticas ("Crear para mí") |
| Búsqueda | `VistaBusqueda.qml` | Se rediseña: barra global y `Ctrl+K` | F2.2.5 | Rediseñada (FTS5, barra global y `Ctrl+K`) |
| Letras sincronizadas | `VistaLyrics.qml`, `external/lyrics_client.py` | Se porta | F2.2.6, F4.1.11 | Hecha |
| Reproducción expandida y minirreproductor | `VistaReproduccionExpandida.qml` | Se porta | F2.2.6 | Hecha |
| Perfil (identidad musical, ánimo, actividad) | `VistaPerfil.qml` | Se porta como **Tu música** | F2.2.8 | Hecha (Tu música) |
| Temas (unas 60 paletas, un PNG de logo por paleta) | `ui/modelos_qml.py`, `ui/qml/assets/logo/` | Se rediseña: Material 3, color por portada, las paletas como acentos | F0.2.7, F2.2.7 | Rediseñada (los 63 temas, generados, y el color por portada) |
| Importación | `VistaImportacion.qml`, `core/pipeline.py` | Se rediseña: sin vista; arrastrar, carpeta vigilada y **Por revisar** | F4.2 | Rediseñada (arrastrar, "Añadir música", carpeta vigilada y Por revisar) |
| Catalogación: normalización, AcoustID, MusicBrainz, Shazam, iTunes, segunda y tercera etapa, desempate por IA | `core/`, `external/` | Se porta | F4.1 | Hecha (`catalogo/`), con la decisión de la V1 reproducida en 400 casos grabados |
| Duplicados exactos y semánticos | `core/dedupe.py`, `servicios/dedupe_observable.py` | Se porta | F4.1.8 | Hecha |
| Overrides de catalogación | `core/overrides.py` | Se porta como "editar metadatos" | F4.2.5 | Hecha (`catalogo/correcciones.rs`, `catalogo/edicion.rs`) |
| Portadas e imágenes de artista (seis fuentes) | `core/assets_pipeline.py` | Se porta | F4.1.10 | Hecha |
| Transcodificación a MP3 al importar | `external/transcoder.py` | **Se elimina**: cada archivo se queda en su formato; la V1 convertía FLAC a MP3 y perdía calidad ([enmienda de ADR-006](../adr/decisions/ADR-006-agregados.md#enmienda-del-2026-10-29-ffmpeg-no-viaja-dentro)) | F4.1.9 | Eliminada |
| Cuarentena y revisión | `infra/quarantine.py`, `archivos_pendientes` | Se rediseña: **Por revisar**, con motivo claro e "importar tal como está"; las pistas así importadas entran en la misma base y llegan al móvil ([ADR-007](../adr/decisions/ADR-007-arquitectura-de-informacion.md#enmienda-del-2026-10-29-por-revisar)) | F4.2.4, F4.2.8 | Rediseñada (Por revisar) |
| Recuperación tras cierre a medias | `core/import_recovery_service.py` | Se porta | F4.1.13 | Hecha (`pendientes_importacion`) |
| Auditoría de la biblioteca | `core/audit.py` | Se rediseña: comprobación en segundo plano; lo que necesite al usuario va a Por revisar | F4.2.4 | Rediseñada (`catalogo/auditoria.rs`): una pasada por arranque que arregla lo interno y solo cuenta lo del usuario |
| Copia de seguridad y restauración | `servicios/backup.py` | Se porta | F4.2.6 | Hecha |
| Rasgos básicos (librosa) | `core/audio_features.py` | Se porta a Rust; tonalidad con modo | F0.4.4, F4.1.12 | Hecha |
| Análisis profundo (Essentia) | `core/audio_intelligence_*.py` | Se porta a ONNX como agregado: MusiCNN y sus siete cabezas. **Se eliminan** VGGish y EffNet/Discogs400: la V1 los calculaba o los tenía preparados y nada los usaba | F0.4.3, F5.3 | Hecha como agregado; VGGish y EffNet eliminados |
| Descubrimiento musical por lenguaje natural | `core/music_discovery_service.py` | Se porta | F5.3.3 | Hecha |
| Karaoke (Demucs) | `servicios/karaoke/` | Se porta a ONNX como agregado | F0.4.2, F5.2 | Hecha como agregado |
| Preparar Karaoke (vista) | `VistaKaraoke.qml` | **Se elimina**: el micrófono del reproductor y "Listas para cantar" | F5.2 | Eliminada |
| DJ Privado | `servicios/dj_privado/`, vistas `Dj*` | Se porta | F6.1 | Hecha |
| A ciegas | `servicios/explorador_ciego/`, `VistaExploradorCiego.qml` | Se porta | F6.2 | Hecha |
| Servidor de sincronización y control remoto | `servicios/servidor_sync.py`, `sync_repositorio.py`, `infra/tls_local.py` | Se porta, compatible byte a byte | F3 | Hecha, con las respuestas doradas de la V1 en verde |
| Sincronización (vista) | `VistaSincronizacion.qml` | Se rediseña: Ajustes > Dispositivos | F3.3.1 | Rediseñada (Ajustes > Dispositivos) |
| Configuración | `VistaConfiguracion.qml` (2.951 líneas) | Se rediseña según ADR-007 | F2.2.9, F4.2.7, F5.1.3 | Rediseñada (Ajustes) |

## Lo que se elimina

| Elemento | Dónde está | Motivo | Estado (F7.1.1) |
|---|---|---|---|
| Modo Pro / Modo Simple | `NavLateral.qml`, `ui_mode` | Constitución, regla 2 | Eliminada |
| Estado del Sistema | `VistaEstadoSistema.qml` | Sustituido por Agregados ([ADR-006](../adr/decisions/ADR-006-agregados.md)) | Eliminada |
| Detector e instalador de dependencias, Python del sistema, `pip` | `infra/dependencias.py`, `infra/instalador.py`, `infra/binarios.py`, `infra/modelos_essentia.py` | Constitución, regla 1 | Eliminada |
| Subproceso de análisis profundo | `infra/deep_runner.py`, `core/audio_intelligence_deep_subprocess.py` | Existía para aislar TensorFlow de Qt; sin Python no hay nada que aislar | Eliminada |
| Ganchos de PyInstaller y del bundle de VLC | `packaging/` | Tauri empaqueta | Eliminada |
| Puente QML y trabajadores de Qt | `ui/modelos_qml.py`, `workers/workers_qt.py` | Lo sustituyen el puente de Tauri y las tareas de Tokio | Eliminada |
| Más de 100 variables de `.env` | `config/settings.py`, `.env` | [ADR-009](../adr/decisions/ADR-009-configuracion-y-red.md) | Eliminada |
| Seis directorios configurables (incluidas las carpetas de cuarentena y revisión) | `config/settings.py` | Una sola carpeta de música; cuarentena y revisión siguen como estado en Por revisar ([ADR-007](../adr/decisions/ADR-007-arquitectura-de-informacion.md)) | Eliminada |
| CLI de la canalización | `main.py`, `docs/v1/cli.md` | Era una herramienta de desarrollo; la aplicación importa sola | Eliminada |
| Manifiestos de importación en disco | `core/manifests.py` | Información operativa; va al registro | Eliminada |
| Modo de progreso de terminal | `infra/progress.py` | Sin terminal | Eliminada |
| Salidas crudas de los modelos en la base (441 MB) | `track_deep_audio_features.raw_output_json` | [ADR-004](../adr/decisions/ADR-004-datos.md) | Eliminada |
