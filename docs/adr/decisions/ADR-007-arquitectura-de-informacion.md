# ADR-007: Arquitectura de información: qué destinos existen y qué deja de existir

**Fecha:** 2026-10-29
**Estado:** Aceptado

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
| **Importar** (vista) | Arrastrar archivos o carpetas sobre cualquier parte de la ventana, o "Añadir música" en Biblioteca. La carpeta de música se vigila y lo nuevo entra solo. El progreso es una tarjeta discreta: "Catalogando 150 canciones". Al terminar: "142 añadidas. 8 necesitan tu atención", que abre un panel lado a lado solo para esas 8 |
| **Preparar Karaoke** (vista) | El micrófono del reproductor. Si la canción no tiene stems, se preparan mientras sigue sonando el original, con su progreso real (no una cifra prometida). En Biblioteca, el filtro "Listas para cantar" y la acción "Preparar mis favoritas" |
| **Estado del Sistema** | Ajustes, sección Agregados ([ADR-006](./ADR-006-agregados.md)) |
| **Sincronización** (vista) | Ajustes, sección Dispositivos: botón "Conectar un teléfono" que muestra el QR, y la lista de teléfonos con quitar |
| Cuarentena y Revisión como carpetas visibles | Internas. Lo que necesita al usuario aparece en "necesitan tu atención" |
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
- **Negativas:** quien usaba la vista de importación avanzada pierde la tabla de causas. Es intencional: la
  información sigue en el registro y en el panel de atención.
- **Riesgos:** que "necesitan tu atención" se convierta en la vieja vista con otro nombre. El criterio de la
  iteración que lo construye limita el panel a resolver pistas concretas.
