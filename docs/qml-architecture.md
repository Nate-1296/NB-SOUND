# Arquitectura QML

Documentación técnica de la interfaz gráfica: el puente Python↔QML, el árbol de componentes, el sistema de temas y los contratos de datos.

---

## Visión general

La UI está construida con PySide6 6.x / Qt 6.x y QML. La arquitectura sigue una separación estricta de responsabilidades:

```
QML (vistas y componentes)
  │  context properties, señales, slots
  ▼
Modelos QML (ui/modelos_qml.py)  ←→  Servicios Python (servicios/)
  │  QObject, @Property, @Signal, @Slot               │
  │                                                   ▼
  └─────────────────────────────────────────── SQLite (db/)
```

**Regla fundamental**: QML no accede directamente a la base de datos ni llama a lógica de negocio. Todo pasa por modelos Python que coordinan con servicios.

---

## El shell maestro — `Principal.qml`

`Principal.qml` es la ventana raíz. Sus responsabilidades:

- **Navegación lateral**: `NavLateral.qml` con los ítems de menú; la selección cambia `vistaActual`
- **StackView central**: `loader` carga las vistas bajo demanda (lazy loading). Cada vista se crea solo cuando se navega a ella por primera vez
- **BarraReproduccion**: siempre visible en el borde inferior, independiente del contenido central
- **Overlays globales**: `ToastMessage`, indicadores de proceso, `DecisionPanel`, vista de lyrics expandida
- **Z-order global**: capas bien definidas — fondo (0), contenido (1), barra reproducción (2), overlays (10), modales (20)

### Lazy loading de vistas

```qml
// Ejemplo simplificado
Loader {
    source: _vistaActual === "biblioteca" ? "vistas/VistaBiblioteca.qml" : ""
    active: _vistaActual === "biblioteca"
}
```

Las vistas se cargan (y destruyen) según la navegación. Los datos persistentes entre navegaciones viven en los modelos Python, no en estado QML local.

---

## Puente Python↔QML — `ui/modelos_qml.py`

### Registro en contexto

`main_ui.py` registra todos los modelos como context properties antes de cargar el QML:

```python
engine.rootContext().setContextProperty("modeloBiblioteca", modelo_biblioteca)
engine.rootContext().setContextProperty("modeloReproductor", modelo_reproductor)
# ... resto de modelos
```

Las context properties son globales a todo el árbol QML. Cualquier componente puede acceder a `modeloBiblioteca` sin necesidad de propagación explícita por la jerarquía.

### Contrato de un modelo QML

```python
class ModeloX(QObject):
    # Señales → notifican a QML de cambios de estado
    cambioDatos = Signal()
    errorOcurrido = Signal(str)

    # @Property → propiedades reactivas que QML puede leer
    @Property(str, notify=cambioDatos)
    def titulo(self) -> str:
        return self._titulo

    # @Slot → funciones que QML puede llamar
    @Slot(int)
    def cargar(self, id: int) -> None:
        self._cargar_en_worker(id)
```

Las señales son el mecanismo de notificación unidireccional Python→QML. Las propiedades reactivas se actualizan cuando se emite su `notify`. Los slots son el canal QML→Python.

### Modelos disponibles en contexto QML

| Context property            | Clase                                 | Responsabilidad                                   |
| --------------------------- | ------------------------------------- | ------------------------------------------------- |
| `modeloBiblioteca`        | `ModeloBiblioteca`                  | Álbumes, artistas, pistas, detalle de álbum     |
| `modeloReproductor`       | `ModeloReproductor`                 | Estado de reproducción, cola, lyrics             |
| `modeloBusqueda`          | `ModeloBusqueda`                    | Búsqueda clásica y natural                      |
| `modeloEstadisticas`      | `ModeloEstadisticas`                | Estadísticas, inicio, tops                       |
| `modeloPlaylists`         | `ModeloPlaylists`                   | CRUD, automáticas, portadas                      |
| `modeloImportacion`       | `ModeloImportacion`                 | Progreso, historial, recovery                     |
| `modeloRevision`          | `ModeloRevision`                    | Pendientes de revisión manual                    |
| `modeloConfiguracion`     | `ModeloConfiguracion`               | Rutas, claves, modo simple/pro                    |
| `modeloTema`              | `ModeloTema`                        | Tema visual activo, tokens de diseño             |
| `modeloAudioIntelligence` | `ModeloAudioIntelligenceBackground` | Estado y control de análisis deep                |
| `modeloKaraoke`           | `ModeloKaraoke`                     | Cola y estado de separación vocal                |
| `modeloDjPrivado`         | `ModeloDjPrivado`                   | Sesiones DJ, intent, timeline                     |
| `exploradorCiego`         | `ModeloExploradorCiego`             | Estado del juego: ronda, reto, hints, validación |

### `ListaGenerica` — `QAbstractListModel` para listas dinámicas

`ListaGenerica` es un `QAbstractListModel` que envuelve una lista de dicts Python y la expone a QML con roles dinámicos. Permite que los modelos entreguen listas de datos estructurados a `ListView`, `Repeater` y `GridView` sin crear un `QAbstractListModel` por tipo de dato.

---

## Sistema de tokens de diseño — `UiTokens.qml`

`UiTokens.qml` es un singleton que expone todas las constantes visuales del sistema:

```qml
// Acceso desde cualquier componente
Rectangle {
    color: UiTokens.bgPrimary
    radius: UiTokens.radiusMd
}

Text {
    font.pixelSize: UiTokens.fontSizeMd
    color: UiTokens.textPrimary
}
```

### Temas

Los tokens se actualizan cuando cambia el tema (oscuro/claro/personalizado). El modelo `ModeloTema` emite una señal cuando el tema cambia; `UiTokens` la escucha y actualiza sus propiedades, lo que propaga el cambio reactivamente a todos los componentes que usan tokens.

Los temas se persisten en `config_ui` (SQLite) y se restauran al iniciar la app.

### Escala de UI

`UiTokens` incluye un factor de escala global (`uiScale`) que todos los componentes deben multiplicar contra sus tamaños fijos. Permite adaptación a diferentes densidades de pantalla sin duplicar componentes.

---

## Componentes reutilizables — `ui/qml/componentes/`

### `BarraReproduccion.qml`

Componente persistente en la parte inferior. Vinculado directamente a `modeloReproductor`:

- Progreso de reproducción con seek por click/drag
- Controles de transporte (play/pause/anterior/siguiente)
- Información de pista actual con portada animada
- Acceso a cola (`QueuePanel`), lyrics y vista expandida

El progreso usa un timer interno para suavizar la barra entre actualizaciones del modelo.

### `AnimatedPlaybackBackground.qml`

Fondo animado reactivo a la reproducción. Extrae colores dominantes de la portada activa (via QImage desde Python) y genera gradientes suaves. La animación se pausa cuando el reproductor está detenido para conservar CPU.

### `NavLateral.qml`

Barra de navegación lateral. Contiene ítems fijos y dinámicos:

- Ítems fijos: Inicio, Búsqueda, Biblioteca, Playlists, DJ Privado, A ciegas, Importar, Preparar Karaoke, Configuración, Perfil
- Switch simple/pro persistente en `config_ui`
- Estado de reproducción mini (muestra la pista actual)

La anchura colapsa a una barra de iconos cuando el espacio es reducido.

### `QueuePanel.qml`

Panel lateral de cola de reproducción. Soporta:

- Reordenamiento por drag & drop (implementado en QML puro)
- Eliminación individual
- Saltar a una pista específica

### `DecisionPanel.qml`

Panel de revisión manual de pistas pendientes. Se superpone al contenido principal cuando hay ítems en revisión. Permite aceptar/rechazar/cuarentenar con feedback visual inmediato.

### `ProgressPanel.qml`

Overlay de progreso de importación. Muestra:

- Fase actual del pipeline (fingerprint, MB, escritura, etc.)
- Progreso por pista con nombre del archivo actual
- ETA calculada
- Botones de pausa y cancelación

### `ToastMessage.qml`

Sistema de notificaciones no intrusivas. Apila toasts con severidades (info, ok, warn, error) y autocierre configurable. Se invoca desde Python via `modeloReproductor.toastMensaje(texto, tipo)`.

### `UiUtils.js`

Utilidades JavaScript compartidas:

- Formateo de duración (`formatDuracion(seg)`)
- Formateo de fechas relativas
- Truncado de texto con ellipsis
- Cálculo de contraste para texto sobre portadas
- Generación de colores desde strings (para avatares sin imagen)

---

## Vistas principales — `ui/qml/vistas/`

### Patrón de carga de datos

Cada vista carga sus datos en `Component.onCompleted` o en `onVistaActivada`:

```qml
Component.onCompleted: {
    modeloBiblioteca.cargarAlbumes()
}
```

Las vistas no cachean datos localmente — los modelos Python son la fuente de verdad. Si el usuario navega fuera y vuelve, los datos se recargan desde el modelo (que puede tener cache interna).

### `VistaInicio.qml`

Dashboard con secciones dinámicas: recientes, más escuchados, sugerencias. Cada sección es un `ListView` horizontal que consume `ListaGenerica` del `modeloEstadisticas`.

### `VistaBiblioteca.qml`

Vista tabbed: Álbumes / Artistas / Pistas. Cada tab tiene su propio `GridView` o `ListView` con virtualización para colecciones grandes. Los filtros de orden y búsqueda se envían al modelo sin recargar el componente.

### `VistaDetalleAlbum.qml`

Muestra todas las pistas de un álbum con portada en gran formato. Al reproducir una pista, popula la cola con todo el álbum y salta a la pista seleccionada.

### `VistaImportacion.qml`

Tres estados: configuración previa, progreso en tiempo real, y resumen post-importación con opciones de recovery. Los botones de recovery (reintentar portadas, reintentar letras, etc.) disparan `WorkerImportRecovery` con la acción correspondiente.

### `VistaKaraoke.qml`

Vista de karaoke con cola visual de pistas, controles de separación y conmutación vocal/instrumental en tiempo real. El estado del reproductor de karaoke es independiente del reproductor principal.

### `VistaDJPrivado.qml` / `DjSesionActiva.qml`

La vista DJ tiene dos modos:

- **Sin sesión**: formulario de intent (prompt + duración) y historial de sesiones previas
- **Con sesión activa**: timeline interactivo de pistas, controles de adaptación en vivo, feedback de narrativa

`DjSesionActiva.qml` es un sub-componente que maneja la sesión en curso. `DjHistorial.qml` y `DjHistorialAccion.qml` muestran sesiones anteriores con las acciones del usuario.

### `VistaExploradorCiego.qml`

Vista del juego "¡A ciegas!". Tiene tres pantallas en un `StackLayout`:

- **Inicio** — selector de modo (4 tarjetas) y selector de cantidad de canciones por ronda (`PillOption` con 3/5/8/12).
- **Jugando** — barra de progreso de ronda, tarjeta central del reto (portada con blur progresivo o placeholder de audio, metadatos censurados, botón de play del fragmento) y panel de adivinanza con `TextField` o `BotonPrincipal` según alfabeto del título.
- **Fin** — resumen animado de la ronda con acertadas/reveladas/saltadas y CTA para repetir modo o elegir otro.

La vista usa solo SVGs (vía un `IconoSvg` interno con `MultiEffect colorization`) y consume `exploradorCiego` como única fuente de estado. Cuando hay un fragmento del juego sonando, los controles del reproductor en `BarraReproduccion` quedan bloqueados sobre esa pista para evitar spoilers — esa lógica vive en `ModeloReproductor` (ver [docs/playback-architecture.md](playback-architecture.md)).

---

## Reglas de QML en este proyecto

Extraídas de `CONTRIBUTING.md`:

1. **No lógica de negocio en QML**: cálculos complejos, formateo de datos, decisiones → Python
2. **No acceso directo a SQLite**: todo a través de modelos → servicios
3. **No ToolTip**: no se usan tooltips en ningún componente
4. **Bindings simples**: evitar bindings que dependen de múltiples estados volátiles
5. **Componentes propios**: usar siempre tokens de `UiTokens` en lugar de valores hardcoded
6. **No timers redundantes**: el motor de bindings de Qt ya es reactivo; los timers son excepciones justificadas

---

← [Volver a arquitectura](architecture.md)
