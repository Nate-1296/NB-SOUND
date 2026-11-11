# Cambios

Formato de [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versiones según
[SemVer](https://semver.org/lang/es/).

## [2.1.0] — 2026-11-11

### Novedades

- La frecuencia de copias puede consultarse y cambiarse desde un enlace local autorizado
  de NB Launcher. Sound conserva su validación, guardado y ejecución de copias.
- El ajuste abierto recibe los cambios confirmados sin recarga. Las ediciones simultáneas
  detectan conflictos y una respuesta perdida se reconcilia sin repetir la escritura.

### Compatibilidad

- Migración V12 con respaldo previo. Los binarios anteriores rechazan una base V12;
  para regresar hay que recuperar el respaldo anterior, sin downgrade automático.
- El enlace es explícito y temporal; Sound sigue funcionando al perderlo. No cambia el
  protocolo móvil ni el formato de copias. La ejecución nativa Windows/macOS del enlace
  sigue pendiente; el resto de Sound conserva sus plataformas existentes.

## [2.0.15] — 2026-11-09

El cierre de las pruebas finales.

### Novedades

- Agregado de aceleración para Linux con una tarjeta NVIDIA: el karaoke, el análisis y el DJ usan la GPU. Solo se
  ofrece si hay una NVIDIA; pesa 2 GB. Sin probar en una NVIDIA real.
- En Windows, el trabajo de fondo (karaoke, análisis, copia automática…) también corre con prioridad baja de
  procesador y de disco.

### Correcciones

- El sonido gasta mucho menos: el ecualizador y las bandas del DJ solo trabajan cuando no están planos (el motor pasa
  del 4,3 al 0,5 % de un núcleo).

## [2.0.14] — 2026-11-09

Lo que encontraron las pruebas finales, hechas por IA sobre una copia de la biblioteca real.

### Novedades

- Lo que le falta a la biblioteca (portadas, letras, fotos de artista) se completa solo, sin prisa, cinco minutos
  después de abrir y con los servicios en línea encendidos. Sirve para una importación que falló a medias y para una
  biblioteca que llega de otro equipo.
- La clave de AcoustID se pone en Ajustes > Privacidad y se guarda en el llavero del sistema. TheAudioDB usa su clave
  pública.
- Por revisar, centrada y más clara: una cabecera con lo que pasa, un resumen que lleva a cada grupo y cada grupo en
  su tarjeta.

### Correcciones

- En una instalación nueva, lo importado no sonaba hasta reiniciar.
- La primera canción del día podía entrecortarse mientras se hacía la copia automática: ahora espera dos minutos y
  no compite con lo que suena.
- El DJ tardaba más de un minuto en empezar a sonar; ahora, menos de dos segundos.
- Las mezclas del DJ con filtros bajaban el volumen a mitad de la transición.
- Descartar una sesión del DJ recién pedida movía la cola una canción adelante.
- En A ciegas, una letra mal en un título corto no contaba como acierto.
- El karaoke llegaba a 6,7 GB de memoria al preparar una canción; ahora no pasa de 1,5 GB.
- Cerrar NB Sound a mitad de una importación dejaba falsos duplicados en Por revisar, y la carpeta vigilada tomaba
  por nuevas canciones recién importadas.
- "Completar datos" nunca identificaba una canción por su sonido.
- La ventana ya no muestra un instante el tema de fábrica al abrir, y si algo falla al cargarla, aparece igual.

## [2.0.13] — 2026-11-06

Lo que encontró la prueba de punta a punta de la 2.0.12.

### Correcciones

- Al soltar la barra de progreso en su extremo, la canción se quedaba en "0:00" sin sonar y sin pasar a la
  siguiente. Ahora pasa a la siguiente.
- Con la música en pausa, mover la barra (o las flechas) no movía la posición hasta reanudar.
- En una instalación nueva, Biblioteca acababa en "500 Internal Error".
- Las listas inteligentes con un rango (año, BPM, energía, reproducciones) no se podían crear.
- La copia de seguridad no llevaba la foto de perfil: al restaurarla en otro equipo, se perdía.
- Por revisar cuenta por dónde va un lote ("Trabajando… 12 de 88") y quita cada canción al entrar.
- Buscar se quedaba en blanco con un texto de más de 200 caracteres.
- En el DJ, "sin reguetón" encendía la ficha de Reguetón.
- "Crear para mí" decía "0 listas hechas" cuando solo estaban al día.
- El resumen de una importación se queda solo si hay algo por revisar; si no, se va.
- "Copiar a una tarjeta o un USB" lleva su flecha: no se veía que se despliega.
- Editar una canción con un número de pista negativo decía "No se pudo guardar".
- "Dónde vive tu música" sin carpeta ofrece "Elegir", y con la biblioteca vacía la usa directamente.

## [2.0.12] — 2026-11-06

Por revisar nueva, tu música que se encuentra sola y barras que caben en cualquier ventana.

### Novedades

- Por revisar, rediseñada: las canciones se agrupan por lo que hay que decidir y el motivo se dice una vez. Cada
  fila es la canción con su portada, su título y su artista, y una sola acción a la vista ("Es esta", "Importar",
  "Descartar" o "Reintentar"); lo demás está en su ···. Las versiones posibles se ordenan por parecido con tu
  archivo, y cada grupo importa o descarta todo de una vez.
- Si tu música cambia de sitio (formateas, cambias el nombre de tu usuario o restauras una copia en otro equipo),
  NB Sound la busca sola al abrir; si no la encuentra, te pregunta dónde está. Ajustes > Biblioteca enseña
  "Dónde vive tu música", si están todas tus canciones, y deja comprobarlo y cambiarla.

### Correcciones

- A 720 px la barra de reproducción se pisaba consigo misma y la búsqueda tocaba los botones de arriba. Ahora cada
  barra mide su propio ancho y lo que no cabe pasa al menú ···, sin perderse.
- Las copias de seguridad automáticas no se hacían si su frecuencia estaba guardada con decimales. Además se
  guardaban para siempre (más de 3 GB cada una): ahora quedan las tres últimas, se hacen más rápido y también si
  NB Sound sigue abierto días.
- Lo descartado de Por revisar llega a la papelera con su nombre, no con un código.
- Una segunda copia de algo que ya esperaba en Por revisar le borraba sus versiones posibles y se catalogaba otra
  vez en cada arranque.
- Borrar una canción dejaba vacía la carpeta de su álbum.

## [2.0.11] — 2026-11-06

El teléfono, el Modo fiesta y los permisos de red.

### Novedades

- Ajustes > Permisos muestra si el cortafuegos del sistema deja pasar al teléfono y al Modo fiesta, y lo comprueba
  mientras está a la vista. Al encender cualquiera de los dos, si está bloqueado, NB Sound lo pide con la ventana de
  administrador del sistema; si se dice que no, Dispositivos lo avisa con un botón para pedirlo de nuevo.

### Correcciones

- Al cerrar la app del teléfono, Dispositivos seguía diciendo "Conectado ahora". Ahora deja de decirlo en menos de
  un minuto.
- El Modo fiesta no cargaba en el móvil cuando el cortafuegos solo dejaba pasar al teléfono.

## [2.0.10] — 2026-11-06

### Correcciones

- Karaoke, Dispositivos y Añadir música aparecían un momento en mitad de la ventana antes de colocarse a la derecha
  (en equipos con aceleración por GPU). Ahora entran deslizándose desde el borde.

## [2.0.9] — 2026-11-05

El trabajo de fondo deja de competir con la interfaz.

### Rendimiento

- Preparar el karaoke ocupaba la mitad de los núcleos a prioridad normal. Ahora el karaoke usa un cuarto de los
  núcleos y el análisis un octavo, sus hilos no giran en vacío mientras esperan, y en Linux y macOS corren a la
  prioridad más baja: solo usan lo que el equipo no está usando.

## [2.0.8] — 2026-11-05

Lo que encontró la prueba de la 2.0.7 ya instalada.

### Correcciones

- El karaoke y el análisis podían quedarse sin modelos toda la sesión si al arrancar había canciones pendientes de
  preparar: todas fallaban en un segundo. Ahora esperan a que ONNX Runtime esté listo y un fallo de carga no se
  queda guardado.
- La aplicación instalada no volvía a la pantalla en la que se cerró, e Inicio no se marcaba en la barra lateral
  al abrir.

## [2.0.7] — 2026-11-05

La revisión de Nathan con la aplicación en marcha: nada se reinicia, todo se recuerda, la interfaz se rehace donde
hacía falta y la aplicación se repara sola.

### Nada se reinicia y todo se recuerda

- Las vistas abiertas se actualizan solas cuando cambia la biblioteca (borrar, editar, importar, playlists).
- Se recuerdan la vista de cada pestaña, sus órdenes y filtros, la playlist elegida, la pantalla en la que se estaba
  y el segundo de la canción, aunque se cierre sin haber pulsado reproducir.
- Al volver a una vista ya visitada se ve al momento lo de antes mientras llega lo nuevo.

### La aplicación se repara sola

- El karaoke reintenta un fallo pasajero hasta tres veces, y lo que falló por no tener el modelo, al arrancar.
- La importación reintenta un archivo hasta tres veces antes de darlo por error.
- Al estrenar una versión, lo que había quedado fallido se intenta otra vez, una sola vez.
- El karaoke no preparaba las canciones cuyo audio mide un número exacto de trozos al remuestrear (por ejemplo, a
  48 kHz): fallaban siempre y parecían listas. La consola dice ahora qué prepara, qué espera y qué falló.

### Interfaz

- Barra de reproducción de forma fija; la favorita, añadir a una playlist, el minirreproductor y dónde suena pasan
  al menú ···, con Sorpréndeme.
- Inicio sin cifras, con el saludo junto a Sorpréndeme y un podio nuevo para el top 10.
- Biblioteca › Pistas, Buscar y las canciones de un artista son una lista sin cabecera ni números.
- Playlists: las ancladas llevan su distintivo; la barra lateral pierde las ancladas.
- Buscar: el mejor resultado por parecido y las canciones cuyo título empieza así, primero.
- Pantalla completa sin franja vacía; la letra que avanza ya no cuenta como movimiento del ratón.
- La cola solo pinta lo que se ve: abre al momento aunque tenga la biblioteca entera.
- Las barras de desplazamiento ya no se ven por encima de cajones, menús y la cola.
- Ajustes: el tamaño de la interfaz en botones; los agregados aún no publicados no se muestran.
- DJ: el historial a toda altura. A ciegas, grande y con la portada a la izquierda.
- Tu música: un mes se ve como calendario; un año o todo el historial, mes a mes.
- Minirreproductor rehecho, y reabrirlo es instantáneo.

## [2.0.6] — 2026-11-04

Perfeccionamiento ergonómico de la vista de Playlists y optimización del lienzo vertical.

### Mejoras y correcciones

- **Playlists**:
  - Panel inspector lateral optimizado al 100% del alto vertical (`height: 100%`) con diseño de contenedor fijado continuo, eliminando cualquier espacio residual inferior.
  - El panel inspector permanece completamente estable e inmóvil durante el desplazamiento vertical de la lista de playlists.
  - Barra de búsqueda y filtros con anclaje adhesivo (`position: sticky`) dentro de la columna de playlists.
  - Distribución refinada de botones secundarios en dos columnas (`Abrir` y `Anclar/Desanclar`) bajo el botón de reproducción principal.
  - Lista de pistas interna en el panel con desplazamiento propio y ajuste dinámico según el alto de la ventana.

## [2.0.5] — 2026-11-03

Auditoría visual y funcional completa: paneles laterales dedicados, persistencia de vistas en biblioteca, rediseño del minirreproductor y optimización global de la experiencia de usuario.

### Mejoras y correcciones

- **Inicio**:
  - Hero estilizado con degradados suaves y diseño uniforme en tarjetas de contenido.
  - Podio decorativo para el Top 1-3 con cuarta pista a ancho completo.
  - Carruseles continuos sin barra horizontal nativa y mensajes de bienvenida concisos.
- **Biblioteca y navegación**:
  - Pestaña inicial predeterminada en Álbumes.
  - Persistencia de estado independiente para Álbumes, Artistas y Pistas (modo cuadrícula/lista, orden y búsqueda).
  - Búsqueda cruzada inteligente entre títulos de canciones, álbumes y artistas.
  - Botón de retroceso consistente que conserva el contexto de procedencia.
- **Playlists**:
  - Panel inspector lateral fijado en vertical (sticky) que aprovecha la altura completa de la ventana con previsualización interactiva de pistas.
  - Lista de favoritos "Me gusta" anclada fija en primer lugar sin botón redundante de anclaje.
  - Barra de herramientas alineada con filtros Material 3 y selector de visualización en el extremo derecho.
- **Paneles laterales (Drawers) y barra superior**:
  - Panel lateral dedicado para la Consola de Karaoke.
  - Panel lateral de Dispositivos y destinos de reproducción, con ocultación dinámica del botón de cast en la barra inferior si no hay dispositivos conectados.
  - Panel lateral de Añadir Música / Importación con gestor de pistas duplicadas y purga inteligente en biblioteca activa.
- **Minirreproductor y modo inmersivo**:
  - Rediseño completo del minirreproductor (470x168 px) con apertura y cierre instantáneo mediante retención en memoria y control de favoritos directo.
  - Modo inmersivo/letras con desvanecimiento automático de controles en pantalla completa tras inactividad.

## [2.0.4] — 2026-11-02

Rediseño integral de la interfaz alineada con NB Books y corrección del buscador general.

### Mejoras y correcciones

- **Buscador general**:
  - Corrección de la reactividad del campo de búsqueda en `BarraSuperior.svelte`: aislamiento de dependencias con `untrack` para evitar el reinicio accidental de la consulta al teclear fuera de `/buscar`.
  - Soporte de pulsación de tecla Enter para ejecutar la búsqueda inmediata.
  - Botón accesible para borrar búsqueda (X) con texto localizado en diccionario i18n (`t.borrar`).
  - Ocultación del botón de borrado nativo de WebKit (`::-webkit-search-cancel-button`) para evitar controles duplicados.
  - Foco y contorno accesible M3 (`outline: 2px solid var(--m3c-primary)`) unificado en todo el contenedor de búsqueda.
- **Rediseño visual y arquitectura de capas (paridad con NB Books)**:
  - Estructura de capas sobre superficie de ventana (`var(--m3c-surface)`): eliminación de bordes toscos de separación en la barra lateral (`border-right: 3px solid var(--m3c-primary)` eliminado).
  - Contenedor flotante redondeado `.lienzo` (`var(--m3c-surface-container-low)`, `border-radius: var(--ns-radio-xl)`) para alojar las vistas de la aplicación.
  - Navegación lateral con destinos en forma de píldora Material 3 (`border-radius: var(--ns-radio-pleno)`), contenedor activo en `var(--m3c-primary-container)` y texto/icono en `var(--m3c-on-primary-container)`.
  - Botón de acción principal "+ Añadir música" con diseño de píldora destacada, icono y chevron de apertura de menú desplegable.
  - Pestañas de navegación de Ajustes actualizadas a píldoras Material 3 con estados activos de alto contraste.
  - Reducción del tamaño del logo en la barra lateral para una proporción visual armónica (6.5rem / 104px).

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

NB Sound sobre Tauri 2, Rust y Svelte. Habla con NB Sound Mobile por su contrato.

### Nuevo o rediseñado

- **Una sola aplicación, sin nada que instalar aparte.** Sin Python, sin VLC: el audio lo reproduce un motor propio
  en Rust. Lo opcional (karaoke, análisis musical, comprensión de texto del DJ y aceleración) son agregados de un
  clic en Ajustes.
- **Siete destinos** en vez de dieciocho vistas: Inicio, Biblioteca, Playlists, DJ Privado, A ciegas, Tu música y
  Ajustes. Sin Modo Pro. Lo que no se pudo importar aparece en **Por revisar**, con su motivo.
- **Importar es arrastrar**, o "Añadir música"; la carpeta de música se vigila sola.
- **Reproducción sin cortes** entre pistas, ecualizador de diez bandas con dieciocho preselecciones,
  normalización de volumen y karaoke con el micrófono de la barra, que prepara el instrumental mientras suena el
  original.
- **El DJ Privado** mezcla en el mismo reproductor con cinco técnicas, sin clics ni saltos de volumen. Con la misma
  semilla construye siempre la misma sesión.
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
