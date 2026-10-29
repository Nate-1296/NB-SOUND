# ADR-007: Arquitectura de información: qué destinos existen y qué deja de existir

**Fecha:** 2026-10-29
**Estado:** Aceptado
**Enmendado:** 2026-10-29, por Nathan: cuarentena y revisión no desaparecen; pasan a **Por revisar**. Ver
[la enmienda](#enmienda-del-2026-10-29-por-revisar)

## Contexto

La V1 tiene 18 vistas y 23.848 líneas de QML solo en ellas. Las más grandes son justo las que menos deberían pesar:
Configuración (2.951 líneas), Importación (1.726), Karaoke (1.277) y Estado del Sistema (587). La barra lateral
tiene un interruptor **Modo Pro / Modo Simple** (`NavLateral.qml`, `ui_mode`) que activa "Configuración avanzada e
Importación avanzada". Es decir: la aplicación admite que tiene dos productos y le pide al usuario que elija.

La V1 pide además configurar seis directorios (entrada, biblioteca, cuarentena, revisión, logs, procesados) y
expone más de 100 variables en `.env`.

## Decisión

### Destinos (barra lateral)

| Destino | Qué contiene | De dónde viene |
|---|---|---|
| **Inicio** | Continuar escuchando, recientes, recomendaciones del día, mezclas automáticas | `VistaInicio` |
| **Biblioteca** | Canciones, Álbumes y Artistas como pestañas; filtros Favoritas y **Listas para cantar**; detalle de álbum y de artista dentro | `VistaBiblioteca`, `VistaDetalleAlbum` |
| **Playlists** | Manuales e inteligentes, en una sola lista | `VistaPlaylists` |
| **DJ Privado** | Pedir una sesión, sesión activa, historial | `VistaDJPrivado`, `DjSesionActiva`, `DjHistorial` |
| **A ciegas** | El juego de redescubrimiento | `VistaExploradorCiego` |
| **Tu música** | Identidad musical, estado de ánimo del día, actividad, resumen anual local | `VistaPerfil` |
| **Ajustes** | Ver abajo | `VistaConfiguracion`, `VistaEstadoSistema`, `VistaSincronizacion` |

**Búsqueda** no es un destino: es un campo permanente en la barra superior (y `Ctrl+K`) que busca en canciones,
álbumes, artistas, playlists y letras, con resultados agrupados.

**El reproductor** es la barra inferior permanente, con vista expandida (portada grande, letras sincronizadas,
cola) y minirreproductor. El **karaoke** es un botón de micrófono en esa barra y en la vista de letras.

### Lo que deja de existir

| Se elimina | Qué ocurre con su función |
|---|---|
| **Modo Pro / Modo Simple** | Desaparece. Hay una sola aplicación, sencilla por defecto |
| **Importar** (vista) | Arrastrar archivos o carpetas sobre cualquier parte de la ventana, o "Añadir música" en Biblioteca. La carpeta de música se vigila y lo nuevo entra solo. El progreso es una tarjeta discreta: "Catalogando 150 canciones". Al terminar: "142 añadidas. 8 por revisar", que lleva a **Por revisar** |
| **Preparar Karaoke** (vista) | El micrófono del reproductor. Si la canción no tiene stems, se preparan mientras sigue sonando el original, con su progreso real (no una cifra prometida). En Biblioteca, el filtro "Listas para cantar" y la acción "Preparar mis favoritas" |
| **Estado del Sistema** | Ajustes, sección Agregados ([ADR-006](./ADR-006-agregados.md)) |
| **Sincronización** (vista) | Ajustes, sección Dispositivos: botón "Conectar un teléfono" que muestra el QR, y la lista de teléfonos con quitar |
| Cuarentena y Revisión como carpetas que el usuario configura | Siguen existiendo como estados, no como carpetas: **Por revisar** (ver la enmienda) |
| Seis directorios configurables | Una sola **Carpeta de tu música**. El resto va a los directorios estándar del sistema operativo |
| Causas internas ("puntaje_intermedio", "candidatos_ambiguos"), colas, versiones | Solo en el registro |

### Ajustes

Secciones, en este orden: **Biblioteca** (carpeta de música, organizar archivos sí/no), **Reproducción**
(ecualizador, transiciones, normalización de volumen), **Apariencia** (tema claro/oscuro/sistema, color por
portada, color de acento), **Dispositivos**, **Agregados**, **Privacidad y servicios en línea** (un interruptor por
servicio, con qué envía), **Inteligencia artificial** (opcional: proveedor y clave para desempates) y
**Acerca de**. "Avanzado" es una sección plegada al final con lo poco que de verdad lo sea (por ejemplo, política
ante duplicados).

## Consecuencias

- **Positivas:** de 18 vistas a 7 destinos y un panel; nada que parezca de desarrollo.
- **Negativas:** quien usaba la vista de importación avanzada pierde la tabla de causas internas. Es
  intencional: cada causa se traduce a un mensaje claro en Por revisar, y el detalle técnico queda en el registro.
- **Riesgos:** que Por revisar se convierta en la vieja vista con otro nombre. El criterio de F4.2.4 lo limita a
  pistas concretas, con su motivo en lenguaje llano y sus acciones.

## Enmienda del 2026-10-29: Por revisar

**Decidido por Nathan.** La primera versión de este ADR hacía internas la cuarentena y la revisión. Se corrige: lo
que no entra solo **no se esconde ni se pierde**; queda visible con su motivo, y el usuario decide si entra tal como
está.

**Dónde vive.** Una entrada **Por revisar** en la barra lateral, con su número, que **solo aparece cuando hay algo
pendiente** y desaparece al vaciarse (revelación progresiva). No se cuenta entre los siete destinos fijos.

**Qué muestra.** Cada archivo como "No importado", con el motivo en lenguaje llano. Las causas reales de la V1
(116 casos en la instalación real) se traducen así:

| Causa interna (V1) | Lo que ve el usuario | Acciones |
|---|---|---|
| `candidatos_ambiguos` | "Encontramos varias versiones posibles de esta canción" | Elegir una (comparador lado a lado), importar tal como está, descartar |
| `puntaje_intermedio`, `duracion_marginal` | "No estamos seguros de que sea esta canción" | Confirmar el candidato, importar tal como está, descartar |
| `release_type_dudoso` | "No sabemos si es de un álbum o de un sencillo" | Elegir álbum o sencillo, importar tal como está |
| `sin_candidatos`, `metadata_insuficiente`, `puntaje_bajo` | "No encontramos esta canción en ninguna fuente" | Importar tal como está, editar los datos, buscar de nuevo, descartar |
| `escritura_fallida`, `validacion_post_escritura` | "No pudimos guardar los datos en el archivo" (por ejemplo, porque es de solo lectura) | Importar sin modificar el archivo, reintentar, descartar |
| Duplicado según la política | "Ya tienes esta canción" (con la comparación de calidad) | Conservar las dos, reemplazar, descartar |
| `duracion_invalida` o audio ilegible | "El archivo parece dañado o incompleto" | Importar solo si se puede reproducir; si no, descartar |

Hay acciones en lote: "Importar todas tal como están" y "Descartar las seleccionadas".

**Importar tal como está.** La pista entra en la **misma base y la misma biblioteca** que las demás, con las
etiquetas que trae el archivo (o el nombre del archivo si no trae ninguna). Antes de confirmar, se advierte lo que
le puede faltar: portada, letra, álbum o año. Queda marcada como **sin verificar**: una insignia discreta en su
detalle, un filtro en Biblioteca y la acción "Completar datos" (buscar portada, letra o identificarla de nuevo)
siempre disponible. Por lo demás es una pista normal: se reproduce, entra en playlists, en el DJ y en el análisis.

**El móvil.** Como es una fila más de la biblioteca, el manifiesto de sincronización la incluye y el teléfono la
descarga como cualquier otra, **sin cambiar nada en NB Sound Mobile**. Si se añade un campo `verificada`, es
aditivo y el móvil lo ignora ([ADR-005](./ADR-005-contrato-movil.md)).

**Los archivos.** Mientras está pendiente, el archivo se conserva en el directorio interno de la aplicación, nunca
en una carpeta que el usuario tenga que gestionar. Al importarlo se organiza en la carpeta de música por sus
etiquetas (si está activado "organizar archivos"; si no, se queda donde estaba). Descartar lo manda a la papelera
del sistema; nunca se borra definitivamente.

