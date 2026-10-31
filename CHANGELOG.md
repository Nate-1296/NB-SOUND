# Cambios

Formato de [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versiones según
[SemVer](https://semver.org/lang/es/).

## [2.0.1] — 2026-10-31

Resolución de hallazgos de auditoría de interfaz: pulido estético (DIS-01 a DIS-07), feedback y estados de carga (FDB-01 a FDB-05), sistema de notificaciones Toast y restauración de componentes.

### Mejoras y correcciones

- **Feedback y estados de carga (FDB y COMP)**:
  - Notificaciones Toast en preparación de karaoke, copias de seguridad y purga de duplicados.
  - Panel y purga segura de duplicados en Ajustes (FDB-02 y COMP-07).
  - Indicador numérico de porcentaje de separación en el botón de karaoke (FDB-01).
  - Estado deshabilitado en controles de reordenamiento de playlist (FDB-04).
  - Estado de carga y animación con esqueleto en generación de sesión de DJ (FDB-05).
- **Diseño y ergonomía (DIS y COMP)**:
  - Rediseño Master-Detail en Ajustes siguiendo el estándar de NB Books (DIS-01 y COMP-02).
  - Restauración de los 64 logotipos sincronizados por tema (DIS-02 y COMP-05).
  - Menú contextual en filas de pistas para reducir saturación visual (DIS-03).
  - Selector compacto de ordenamiento en Biblioteca (DIS-04).
  - Eliminación de tooltips nativos redundantes (DIS-05).
  - Ejes horarios y tooltips en mapa de actividad 24h (DIS-06).
  - Controles de avance y scroll-snap en carruseles de Inicio (DIS-07 y COMP-11).

## [2.0.0] — 2026-10-31

La reescritura completa de NB Sound: de Python y Qt a Tauri 2, Rust y Svelte. Lee la biblioteca de la V1 (1.1.16)
la primera vez que se abre y conserva escuchas, favoritas, playlists, letras, karaoke y sesiones del DJ. Sigue
hablando con NB Sound Mobile con el mismo contrato.

### Nuevo o rediseñado

- **Una sola aplicación, sin nada que instalar aparte.** Sin Python, sin VLC: el audio lo reproduce un motor propio
  en Rust. Lo opcional (karaoke, análisis musical, comprensión de texto del DJ y aceleración) son agregados de un
  clic en Ajustes.
- **Siete destinos** en vez de dieciocho vistas: Inicio, Biblioteca, Playlists, DJ Privado, A ciegas, Tu música y
  Ajustes. Sin Modo Pro. Lo que no se pudo importar aparece en **Por revisar**, con su motivo.
- **Importar es arrastrar**, o "Añadir música"; la carpeta de música se vigila sola.
- **Reproducción sin cortes** entre pistas, ecualizador de diez bandas con las preselecciones de la V1,
  normalización de volumen y karaoke con el micrófono de la barra, que prepara el instrumental mientras suena el
  original.
- **El DJ Privado** mezcla en el mismo reproductor con cinco técnicas, sin clics ni saltos de volumen. Con la misma
  semilla construye la misma sesión que la V1.
- **A ciegas**: el fragmento suena sin que la barra ni el móvil digan qué canción es.
- **Actualizaciones desde la aplicación**, firmadas y solo si se piden.
- **Privacidad**: nada sale a la red sin consentimiento, servicio a servicio; los secretos van al llavero del
  sistema.

### Plataformas

Linux (AppImage, deb, rpm y tar.gz de sistema), Windows (MSI y NSIS) y macOS en Apple Silicon (dmg). macOS con Intel
deja de estar soportado: ONNX Runtime 1.31 ya no publica binario para esa arquitectura.

### Pendiente antes de publicar

Las comprobaciones con la instalación real y con máquinas limpias de
[docs/plan/pruebas-finales.md](docs/plan/pruebas-finales.md).

[2.0.1]: https://github.com/Nate-1296/NB-SOUND/releases/tag/v2.0.1
[2.0.0]: https://github.com/Nate-1296/NB-SOUND/releases/tag/v2.0.0
