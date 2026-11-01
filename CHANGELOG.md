# Cambios

Formato de [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versiones según
[SemVer](https://semver.org/lang/es/).

## [2.0.3] — 2026-11-01

Auditoría visual y funcional exhaustiva: resolución de los 18 hallazgos QA-01 a QA-18 de la suite final.

### Mejoras y correcciones

- **Reproducción y cola (QA-01, QA-03, QA-05, QA-08, QA-13, QA-18)**:
  - Restauración inmediata del estado de la cola en el arranque con pista activa, metadatos y tiempo precargado sin requerir presionar Play (QA-01).
  - El botón "Continuar escuchando" en Inicio reanuda reactivamente la pista restaurada o en pausa y sincroniza su icono de reproducción (QA-03).
  - Popover de volumen accesible e interactivo con control deslizante y porcentaje para pantallas estrechas y vista compacta (QA-05).
  - Eliminación de barras decorativas estáticas en Inicio y componente `EcualizadorBarras.svelte` huérfano (QA-08).
  - Elevación visual y tokens semánticos M3 (`surface-container-high`, `elevation-3`) en el panel flotante de cola (QA-13).
  - Atajos visibles y accesibles para modo pantalla completa (F11) y vista inmersiva (F) en la barra de reproducción (QA-18).
- **Diseño del sistema y selectores (QA-09, QA-10, QA-11)**:
  - Componente accesible `MenuSelector.svelte` con popover y foco por teclado, sustituyendo elementos `<select>` nativos en toda la aplicación (QA-09).
  - Alineación ergonómica y barra de herramientas unificada en la vista de playlists, destacando "+ Nueva playlist" como botón primario (QA-10).
  - Conmutadores estilo Material 3 Switch con animación deslizante y estados interactivos en los ajustes (QA-11).
- **Navegación e inmersión (QA-02, QA-04, QA-06, QA-07, QA-17)**:
  - Saludos circadianos de cuatro tramos según la hora local: madrugada, mañana, tarde y noche (QA-02).
  - Navegación lateral en Ajustes adaptativa y desplazable sin desbordamientos en resoluciones reducidas (QA-04).
  - Icono y etiqueta dinámicos en el botón de colapso de la barra lateral para indicar claramente la dirección de expansión (QA-06).
  - Escape en el campo de búsqueda rápida desenfoca el foco y restaura inmediatamente los atajos globales (QA-07).
  - Barra lateral colapsada automáticamente en la vista de reproducción inmersiva `/reproduciendo` para dar protagonismo total a las letras (QA-17).
- **Biblioteca, perfil y juego a ciegas (QA-12, QA-14, QA-15, QA-16)**:
  - Historial de récords y gráfica de actividad de los últimos 7 días en la vista "A ciegas", junto a ambientación de portadas y sección "Más del artista" en el detalle de álbum (QA-12).
  - Fallbacks visuales limpios con iconos vectoriales en tarjetas y elementos sin imagen en Tu Música (QA-14).
  - Selección y guardado de foto de perfil personalizada con diálogo de archivos nativo y persistencia local (QA-15).
  - Discografía de álbumes reorganizada en la cabecera del perfil de artista antes de la lista plana de pistas (QA-16).

## [2.0.2] — 2026-10-31

Resolución completa de hallazgos de paridad y componentes (COMP-01 a COMP-19) y corrección del actualizador del sistema en Linux (BUG-08).

### Mejoras y correcciones

- **Actualizador de sistema en Linux (BUG-08)**:
  - Implementación nativa de instalación y reinicio de actualizaciones en Linux vía descarga del tarball oficial, verificación de firma criptográfica con minisign, extracción atómica en sistema con permisos elevados y reinicio seguro del proceso.
- **Componentes y paridad visual (COMP)**:
  - Selector de modo de vista (cuadrícula pequeña, mediana, grande y lista) en Biblioteca y Playlists (COMP-01).
  - Vista inmersiva centrada de letras sincronizadas con fondo ambiental dinámico (COMP-04).
  - Botón global de importación con menú desplegable para añadir música o carpetas desde la barra superior (COMP-06).
  - Botón de colapso de barra lateral en modo riel y atajo/botón de pantalla completa del sistema F11 (COMP-08).
  - Modal multi-selección de playlists con estado interactivo y botón directo en barra de reproducción (COMP-09).
  - Opción de menú contextual "Mostrar en el explorador de archivos" conectada a Rust (COMP-13).
  - Chips interactivos categorizados (Voces, Géneros, Ánimos, Energía, Contextos) en el asistente DJ (COMP-14).
  - Indicador visual reactivo de barras en Inicio que responde dinámicamente a la reproducción sin loops infinitos en reposo (COMP-15).
  - Pantalla de bienvenida en búsqueda con 24 ideas musicales y carga diferida para cumplir presupuesto (COMP-16).
  - Atajo global 'D' ("Sorpréndeme") con selección y reproducción aleatoria de biblioteca (COMP-17).
  - Diálogo modal accesible `DialogoConfirmar` con backdrop scrim nativo reemplazando confirmaciones de navegador (COMP-18).
  - Optimización contextual de columnas y visualización en filas de pistas para álbumes, artistas y playlists (COMP-19).

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
