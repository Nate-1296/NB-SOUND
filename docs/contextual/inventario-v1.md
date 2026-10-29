# Inventario de la V1 y su destino en la V2

> **Estado:** Vigente desde el 2026-10-29. Se audita en F7.1.1: cada fila debe terminar Hecha, Rediseñada o
> Eliminada.

Base: NB Sound v1.1.16. Unas 111.000 líneas: 60.000 de Python de aplicación (`servicios` 22.397, `core` 11.216,
`ui/modelos_qml.py` 11.844, `infra` 5.077, `external` 2.979, `db` 1.358, `utils` 1.036, `config` 774,
`packaging` 682, `domain` 486, `workers` 408, `main.py` y `main_ui.py` 1.872), 23.381 de pruebas y 27.261 de QML.

**Destinos:** **Se porta** (misma función, otro lenguaje) · **Se rediseña** (la función sigue, la forma cambia) ·
**Se elimina** (con su motivo).

## Funciones del producto

| Función de la V1 | Dónde está | Destino | Fase |
|---|---|---|---|
| Reproductor, cola, aleatorio, repetición | `servicios/reproductor.py` | Se porta al motor de Rust | F2.1 |
| Ecualizador de 10 bandas, 18 preselecciones | `servicios/reproductor.py` | Se porta con `eq_filter` de Kira | F2.1.3 |
| MPRIS | `infra/mpris_linux.py` | Se porta con `mpris-server`; se añaden SMTC y macOS | F2.1.5 |
| Inicio | `VistaInicio.qml` | Se porta | F2.2.2 |
| Biblioteca y detalle de álbum | `VistaBiblioteca.qml`, `VistaDetalleAlbum.qml` | Se porta; artistas y álbumes como pestañas | F2.2.3 |
| Playlists manuales, de sistema y automáticas | `VistaPlaylists.qml`, `servicios/biblioteca.py` | Se porta; las automáticas convergen con las inteligentes | F2.2.4, F8.2 |
| Búsqueda | `VistaBusqueda.qml` | Se rediseña: barra global y `Ctrl+K` | F2.2.5 |
| Letras sincronizadas | `VistaLyrics.qml`, `external/lyrics_client.py` | Se porta | F2.2.6, F4.1.11 |
| Reproducción expandida y minirreproductor | `VistaReproduccionExpandida.qml` | Se porta | F2.2.6 |
| Perfil (identidad musical, ánimo, actividad) | `VistaPerfil.qml` | Se porta como **Tu música** | F2.2.8 |
| Temas (unas 60 paletas, un PNG de logo por paleta) | `ui/modelos_qml.py`, `ui/qml/assets/logo/` | Se rediseña: Material 3, color por portada, las paletas como acentos | F0.2.7, F2.2.7 |
| Importación | `VistaImportacion.qml`, `core/pipeline.py` | Se rediseña: sin vista; arrastrar, carpeta vigilada y **Por revisar** | F4.2 |
| Catalogación: normalización, AcoustID, MusicBrainz, Shazam, iTunes, segunda y tercera etapa, desempate por IA | `core/`, `external/` | Se porta | F4.1 |
| Duplicados exactos y semánticos | `core/dedupe.py`, `servicios/dedupe_observable.py` | Se porta | F4.1.8 |
| Overrides de catalogación | `core/overrides.py` | Se porta como "editar metadatos" | F4.2.5 |
| Portadas e imágenes de artista (seis fuentes) | `core/assets_pipeline.py` | Se porta | F4.1.10 |
| Transcodificación | `external/transcoder.py` | Se porta con el `ffmpeg` empaquetado | F4.1.9 |
| Cuarentena y revisión | `infra/quarantine.py`, `archivos_pendientes` | Se rediseña: **Por revisar**, con motivo claro e "importar tal como está"; las pistas así importadas entran en la misma base y llegan al móvil ([ADR-007](../adr/decisions/ADR-007-arquitectura-de-informacion.md#enmienda-del-2026-10-29-por-revisar)) | F4.2.4, F4.2.8 |
| Recuperación tras cierre a medias | `core/import_recovery_service.py` | Se porta | F4.1.13 |
| Auditoría de la biblioteca | `core/audit.py` | Se rediseña: comprobación en segundo plano; lo que necesite al usuario va a Por revisar | F4.2.4 |
| Copia de seguridad y restauración | `servicios/backup.py` | Se porta | F4.2.6 |
| Rasgos básicos (librosa) | `core/audio_features.py` | Se porta a Rust; tonalidad con modo | F0.4.4, F4.1.12 |
| Análisis profundo (Essentia) | `core/audio_intelligence_*.py` | Se porta a ONNX como agregado | F0.4.3, F5.3 |
| Descubrimiento musical por lenguaje natural | `core/music_discovery_service.py` | Se porta | F5.3.3 |
| Karaoke (Demucs) | `servicios/karaoke/` | Se porta a ONNX como agregado | F0.4.2, F5.2 |
| Preparar Karaoke (vista) | `VistaKaraoke.qml` | **Se elimina**: el micrófono del reproductor y "Listas para cantar" | F5.2 |
| DJ Privado | `servicios/dj_privado/`, vistas `Dj*` | Se porta | F6.1 |
| A ciegas | `servicios/explorador_ciego/`, `VistaExploradorCiego.qml` | Se porta | F6.2 |
| Servidor de sincronización y control remoto | `servicios/servidor_sync.py`, `sync_repositorio.py`, `infra/tls_local.py` | Se porta, compatible byte a byte | F3 |
| Sincronización (vista) | `VistaSincronizacion.qml` | Se rediseña: Ajustes > Dispositivos | F3.3.1 |
| Configuración | `VistaConfiguracion.qml` (2.951 líneas) | Se rediseña según ADR-007 | F2.2.9, F4.2.7, F5.1.3 |

## Lo que se elimina

| Elemento | Dónde está | Motivo |
|---|---|---|
| Modo Pro / Modo Simple | `NavLateral.qml`, `ui_mode` | Constitución, regla 2 |
| Estado del Sistema | `VistaEstadoSistema.qml` | Sustituido por Agregados ([ADR-006](../adr/decisions/ADR-006-agregados.md)) |
| Detector e instalador de dependencias, Python del sistema, `pip` | `infra/dependencias.py`, `infra/instalador.py`, `infra/binarios.py`, `infra/modelos_essentia.py` | Constitución, regla 1 |
| Subproceso de análisis profundo | `infra/deep_runner.py`, `core/audio_intelligence_deep_subprocess.py` | Existía para aislar TensorFlow de Qt; sin Python no hay nada que aislar |
| Ganchos de PyInstaller y del bundle de VLC | `packaging/` | Tauri empaqueta |
| Puente QML y trabajadores de Qt | `ui/modelos_qml.py`, `workers/workers_qt.py` | Lo sustituyen el puente de Tauri y las tareas de Tokio |
| Más de 100 variables de `.env` | `config/settings.py`, `.env` | [ADR-009](../adr/decisions/ADR-009-configuracion-y-red.md) |
| Seis directorios configurables (incluidas las carpetas de cuarentena y revisión) | `config/settings.py` | Una sola carpeta de música; cuarentena y revisión siguen como estado en Por revisar ([ADR-007](../adr/decisions/ADR-007-arquitectura-de-informacion.md)) |
| CLI de la canalización | `main.py`, `docs/v1/cli.md` | Era una herramienta de desarrollo; la aplicación importa sola |
| Manifiestos de importación en disco | `core/manifests.py` | Información operativa; va al registro |
| Modo de progreso de terminal | `infra/progress.py` | Sin terminal |
| Salidas crudas de los modelos en la base (441 MB) | `track_deep_audio_features.raw_output_json` | [ADR-004](../adr/decisions/ADR-004-datos.md) |
