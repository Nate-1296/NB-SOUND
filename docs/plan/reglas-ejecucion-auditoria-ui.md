# Reglas de Ejecución y Salvaguardas Técnicas para la Auditoría de Interfaz

**Documento:** `docs/plan/reglas-ejecucion-auditoria-ui.md`  
**Referencia base:** [observaciones-antes-pruebas-finales.md](./observaciones-antes-pruebas-finales.md)  
**Propósito:** Definir exactamente cómo debe implementarse cada corrección, mejora ergonómica y restauración visual del informe de QA sin romper ninguno de los 17 guardianes arquitectónicos (`pnpm verify`), ni degradar el rendimiento en WebKitGTK sobre Linux, ni violar los contratos de accesibilidad, internacionalización, seguridad y empaquetado de NB Sound.

---

## 1. Reglas Transversales Innegociables (Los 17 Guardianes)

Antes de tocar cualquier línea de código para resolver los puntos del informe de auditoría, todo cambio debe respetar las reglas verificadas automáticamente por `scripts/guardianes.mjs`:

### 1.1. Reglas de Interfaz, CSS y Accesibilidad (`scripts/check-ui.mjs`)
1. **Cero colores literales fuera de `src/app.css` y `src/paletas.css`:** Prohibido usar `#hex`, `rgb()`, `rgba()`, `hsl()`, `oklch()`, `white`, `black` o `gray` en componentes `.svelte`. Todo color debe provenir de tokens Material 3 (`var(--m3c-...)`) o tokens propios (`var(--ns-...)`).
2. **Escala estricta de espaciado, radios y tipografía:** Prohibido escribir valores literales en `px`, `rem` o `em` (salvo `0`, `1px`, `2px` o porcentajes) en `padding`, `margin`, `gap`, `border-radius` y `font-size`. Se deben usar exclusivamente los tokens declarados en `src/app.css` (`var(--ns-espacio-...)`, `var(--ns-radio-...)`, `var(--ns-texto-...)`) o `clamp(...)` fluido con tokens.
3. **Prohibición de `!important` y `will-change`:** Ningún componente puede incluir `!important` ni `will-change`.
4. **Prohibición de `backdrop-filter` no autorizado:** En WebKitGTK, desenfocar cromo permanente provoca parpadeo y caída de fotogramas al hacer scroll. Si un modal o diálogo flotante transitorio requiere `backdrop-filter`, debe declararse en `CRISTAL_PERMITIDO` dentro de `scripts/check-ui.mjs` e incluir siempre la pareja `-webkit-backdrop-filter` y `backdrop-filter`.
5. **Contención obligatoria en Barra Superior:** En `src/lib/ui/BarraSuperior.svelte`, la regla `.superior` debe conservar siempre `contain: layout size` para evitar que escribir en el buscador recalcule la disposición de la vista inferior (120 ms por tecla en WebKitGTK).
6. **Reglas de `:hover` sin reflujo ni temblor:**
   - Ningún `:hover` sobre el propio elemento sujeto puede aplicar `translate` o `transform: translateY(...)` (provoca parpadeo al sacar el elemento de debajo del puntero); solo se permite `scale(...)` mayor a 1, color, sombra u opacidad.
   - Ningún `:hover` puede alterar propiedades de disposición (`width`, `height`, `padding`, `margin`, `font-size`, `gap`, `border-width`, `top`, `left`, `inset`).
7. **Prohibición de animaciones infinitas en reposo:** `animation: ... infinite` está prohibido fuera de `Spinner.svelte`. Cualquier indicador animado (como el ecualizador de pista activa o las barras de Inicio) debe acotarse al estado `reproductor.sonando`, pausarse en reposo, respetar `prefers-reduced-motion` y registrarse explícitamente si usa iteración continua.
8. **Prohibición de emojis y símbolos Unicode como iconos:** El guardián rechaza cualquier pictograma o símbolo tipográfico (`\u{1F300}-\u{1FAFF}`, triángulos de play, flechas Unicode, aspas, etc.) y también rechaza botones cuyo contenido sea una sola letra (`<button>X</button>`). Todo icono debe ser un trazo SVG en `src/lib/ui/Icon.svelte`.
9. **Paridad obligatoria Teclado + Ratón:** Cualquier elemento con `ondblclick`, `onmousedown`, `onpointerdown`, `onwheel` o `ondrag*` debe tener en la **misma etiqueta de apertura** un manejador `onkeydown`, `onkeyup` o `onkeypress` equivalente, además de rol e indicador de foco intacto (`outline` nunca puede ser `none` ni `0`).
10. **Consultas de contenedor en vez de `@media` por ancho:** Prohibido usar `@media (min-width: ...)` o `@media (max-width: ...)`. Toda adaptación por anchura se gobierna mediante `data-ancho` (`src/lib/ui/anchos.ts`) o `@container carcasa (...)`.
11. **Puntos de referencia accesibles y sin código muerto:** Todo `<nav>` y `<aside>` exige `aria-label` o `aria-labelledby`. Ningún componente `.svelte` en `src/lib/ui/` puede quedar sin consumidor real, ni ninguna clase `.nb-*` sin regla CSS.

### 1.2. Internacionalización (`scripts/check-i18n.mjs`)
1. **Cero texto incrustado en `.svelte`:** Ningún nodo de texto ni atributo legible (`aria-label`, `title`, `placeholder`, `alt`, `etiqueta`, `titulo`, `mensaje`, `descripcion`) puede contener cadenas literales en el marcado. Todo texto debe residir en `src/lib/i18n/es.ts` y consumirse mediante `textos.<seccion>`.
2. **Formato regional explícito:** Prohibido invocar `.toLocaleString()`, `.toLocaleDateString()` o `new Intl.*()` sin pasarle el idioma activo de la aplicación (`idioma()`).

### 1.3. Presupuesto del Paquete de Arranque (`scripts/check-paquete.mjs`)
1. **Límite estricto de 250 KB sin comprimir en el arranque:** SvelteKit incluye todos los nodos `+page.svelte` en el cálculo del paquete inicial.
2. **Carga diferida real (`import()`):** Las vistas ricas o modales secundarios (como el rediseño de Ajustes, diálogos de confirmación, panel de duplicados o bienvenida de búsqueda) deben vivir en módulos bajo `src/lib/ui/` cargados dinámicamente con `{#await import('$ui/...')}` desde la ruta o al abrirse, y **jamás** ser importados estáticamente por ningún módulo del arranque.

### 1.4. Puente IPC, Rust, SQLite y Seguridad (`check-comandos`, `check-puente`, `check-bindings`, `check-error-contract`, `check-rutas`, `check-transacciones`, `check-listas`, `check-registro`, `check-plataforma`)
1. **Comandos asíncronos por defecto:** Todo `#[tauri::command]` en Rust debe ser `async fn` o `#[tauri::command(async)]`. Solo puede ser síncrono si toca directamente `WebviewWindow`, `Window`, diálogos nativos o bandeja del sistema, e incluye el comentario `// Se queda en el hilo principal: <motivo>`.
2. **Contrato de errores y tipos:** Todo comando devuelve `NsResult<T>` (nunca `Result<T, String>`). Cualquier struct/enum que cruce IPC debe derivar `ts_rs::TS` y regenerarse con `pnpm check:bindings`.
3. **Integridad 1:1 del puente:** Todo comando en `generate_handler!` (`src-tauri/src/lib.rs`) debe tener su función envoltorio en `src/lib/core/ipc/` y al menos un consumidor real en la interfaz (`src/routes` o `src/lib/ui`).
4. **Canonicalización de rutas (`check-rutas.mjs`):** Si un comando recibe un parámetro llamado `ruta`, `path`, `destino`, `carpeta` u `origen`, debe canonicalizarlo dentro del propio cuerpo del comando con `.canonicalize()`, `destino_admisible(...)` o `security::resolve_within(...)`.
5. **Transacciones de escritura (`check-transacciones.mjs`):** Prohibido usar `BEGIN`, `BEGIN DEFERRED` o `.transaction()`. Toda escritura en SQLite debe abrirse mediante `db::write_transaction` (`BEGIN IMMEDIATE`).
6. **Listas acotadas (`check-listas.mjs`):** Todo comando que devuelva `NsResult<Vec<...>>` debe recibir `limit` / `*Query` o declarar explícitamente `// Cota: <motivo>` en su comentario superior.
7. **Privacidad en logs (`check-registro.mjs`):** Ningún `info!`, `warn!`, `error!` o `debug!` puede imprimir rutas, títulos, artistas o consultas sin envolverlos en `redact_path(...)`, `redact_text(...)` o registrar únicamente su longitud (`.len()`).

### 1.5. Integridad Documental (`scripts/check-docs.mjs`)
1. Todo archivo `.md` dentro de `docs/` debe empezar con un encabezado `# `, no tener filas de tabla mal cerradas, no incluir enlaces relativos rotos, **no contener emojis Unicode** y **no incluir rutas absolutas de máquina** (como rutas del directorio de usuario o esquemas de archivo local) salvo que el archivo incluya la directiva `<!-- check-docs: allow-absolute-path -->`.
2. **Nota crítica sobre `observaciones-antes-pruebas-finales.md`:** Dado que ese informe utiliza pictogramas Unicode en sus encabezados y menciona una ruta absoluta del directorio local, antes de correr `pnpm verify` se deben sustituir dichos pictogramas por etiquetas de texto (`[BUG]`, `[EXP]`, `[DIS]`, `[FDB]`, `[COMP]`, `[DISC]`) y usar ruta relativa o añadir `<!-- check-docs: allow-absolute-path -->` para que `check-docs.mjs` pase en verde.

---

## 2. Reglas Específicas por cada Hallazgo del Informe de Auditoría

A continuación se detalla cómo implementar cada ítem del documento de QA cumpliendo todas las salvaguardas anteriores.

---

### 2.1. Hallazgos Críticos y Bugs de Interfaz (`BUG-01` a `BUG-07`)

#### BUG-01: Desplazamiento automático de letras rompe la vista de reproducción completa
- **Objetivo:** Mantener fija la columna izquierda (botón volver, portada, título, artista y fichas) mientras únicamente la columna derecha de letras hace scroll.
- **Cómo hacerlo sin romper nada:**
  1. En `src/routes/reproduciendo/+page.svelte`, cambiar `.vista` de `min-height: 100%` a `height: 100%; max-height: 100%; overflow: hidden; box-sizing: border-box;` (ajustando el margen negativo para no desbordar `<main class="contenido">`).
  2. En el `$effect` de la línea 58, **eliminar** `nodo?.scrollIntoView({ block: 'center', behavior: 'smooth' })` porque `scrollIntoView` desplaza a todos los ancestros desplazables del DOM, incluido `<main class="contenido">`.
  3. Usar una referencia `bind:this={contenedorLetras}` sobre `<aside class="letras">` y calcular el desplazamiento local:
     `contenedorLetras.scrollTo({ top: nodo.offsetTop - contenedorLetras.clientHeight / 2 + nodo.clientHeight / 2, behavior: 'smooth' })`.
  4. Añadir `overscroll-behavior: contain` en `.letras` usando solo tokens `--ns-*` para los rellenos.

#### BUG-02: Desbordamiento vertical en el modal "Nueva inteligente"
- **Objetivo:** Garantizar que la cabecera y los botones inferiores (`Cancelar` y `Crear`) estén siempre visibles y accesibles en pantallas 1080p con escalado 1.25x.
- **Cómo hacerlo sin romper nada:**
  1. En `src/lib/ui/playlists/DialogoInteligente.svelte`, convertir el contenedor del diálogo en `display: flex; flex-direction: column; max-height: 85vh; overflow: hidden;`.
  2. Aislar los 16 controles del formulario dentro de un `<div class="cuerpo-formulario">` con `flex: 1 1 auto; min-height: 0; overflow-y: auto; padding: var(--ns-espacio-4);`.
  3. Mantener la cabecera y el pie de acciones con `flex: 0 0 auto` y borde de separación `1px solid var(--m3c-outline-variant)`.
  4. No usar valores en `px` fuera de escala para márgenes o paddings.

#### BUG-03: Consulta de búsqueda congelada al navegar a otras pantallas
- **Objetivo:** Limpiar la caja de búsqueda superior cuando el usuario navega fuera de `/buscar`, y sincronizarla si navega hacia `/buscar?q=...`.
- **Cómo hacerlo sin romper nada:**
  1. En `src/lib/ui/BarraSuperior.svelte`, añadir un `$effect` reactivo a `page.url.pathname`:
     - Si `page.url.pathname !== '/buscar'`, asignar `consulta = ''`.
     - Si `page.url.pathname === '/buscar'`, sincronizar `consulta = page.url.searchParams.get('q') ?? ''` cuando el campo no tenga foco activo, para que al usar "Atrás/Adelante" o pulsar un chip de búsqueda la barra refleje la consulta real.
  2. Mantener intacta la regla `.superior { contain: layout size; }`.

#### BUG-04: Truncamiento de textos en el "Radar de ánimos"
- **Objetivo:** Evitar que etiquetas como `Bailable`, `Nocturna` o `Melancólica` se corten en los bordes del SVG.
- **Cómo hacerlo sin romper nada:**
  1. En `src/lib/ui/tu-musica/VistaTuMusica.svelte`, ampliar el `viewBox` del `<svg>` del radar para dar margen perimetral suficiente a los lados izquierdo y derecho (por ejemplo, de `0 0 240 240` a `-48 -24 336 288` o ajustando el radio del polígono respecto al lienzo).
  2. Calcular `text-anchor` según el ángulo de cada vértice (`middle` arriba/abajo, `start` a la derecha, `end` a la izquierda) y usar `fill="var(--m3c-on-surface)"` (nunca colores hexadecimales literales en atributos o estilos del SVG).

#### BUG-05: Fallo silencioso sin respuesta visual en "A ciegas"
- **Objetivo:** Mostrar estado de carga mientras se prepara la partida y notificar con claridad si no hay suficientes pistas válidas para la modalidad elegida.
- **Cómo hacerlo sin romper nada:**
  1. En `src/lib/ui/aciegas/VistaACiegas.svelte`, añadir estado `iniciando = $state(false)` que deshabilite el botón de inicio mientras la promesa IPC está en vuelo.
  2. Envolver la llamada en `try / catch / finally`. En caso de error o de lista vacía, disparar una notificación en el gestor global de Toasts (`COMP-03`) y mostrar un mensaje inline accesible (`role="status"` o `role="alert"`) usando cadenas de `src/lib/i18n/es.ts`.
  3. No usar emojis en el botón; usar `<Icon nombre="..." />`.

#### BUG-06: Inexistencia del modo de pantalla completa (F11 / Party Mode)
- **Objetivo:** Permitir alternar pantalla completa real de la ventana del sistema operativo con `F11`, con el atajo `F` (o según mapa de atajos) y mediante un botón en la interfaz.
- **Cómo hacerlo sin romper nada:**
  1. En `src/lib/core/atajos.ts`, registrar la tecla `F11` hacia una nueva acción `'pantallaCompleta'`.
  2. Como el proyecto canaliza el control de ventanas a través de Rust/Tauri o `@tauri-apps/api/window`, verificar si `getCurrentWindow().setFullscreen(...)` está habilitado por capabilities de Tauri 2 (`src-tauri/capabilities/`). Si las capabilities de ventana no exponen `core:window:allow-set-fullscreen`, o bien añadir el permiso en la capability correspondiente o exponer un comando en Rust `alternar_pantalla_completa(window: tauri::WebviewWindow) -> NsResult<bool>` con la declaración obligatoria `// Se queda en el hilo principal: modifica el estado de pantalla completa de la ventana GTK` para que `check-comandos.mjs` y `check-puente.mjs` lo aprueben.
  3. Añadir el icono SVG `pantallaCompleta` y `salirPantallaCompleta` en `src/lib/ui/Icon.svelte` y el botón correspondiente en `BarraReproduccion.svelte` (o `BarraSuperior.svelte`), con sus textos en `src/lib/i18n/es.ts`.

#### BUG-07: Spoiler visual en el modo "A ciegas" en la Barra de Reproducción
- **Objetivo:** Ocultar por completo portada, título, artista y álbum en `BarraReproduccion.svelte` mientras `i.ciego` sea `true`.
- **Cómo hacerlo sin romper nada:**
  1. En `src/lib/ui/BarraReproduccion.svelte` (líneas 118-143), evaluar `i.ciego` **antes** que `pista` tanto en el bloque de `.portada` como en el bloque de `.datos`:
     - En `.portada`: `{#if i.ciego} <Icon nombre="incognito" tamano={24} /> {:else if pista?.tienePortada && !portadaRota} <img ... /> {:else} <Icon nombre="cancion" tamano={24} /> {/if}`.
     - En `.datos`: `{#if i.ciego} <span class="titulo">{t.aCiegas}</span> <span class="artista">{t.adivina}</span> {:else if pista} ...`.
  2. Desactivar durante `i.ciego` los enlaces a artista/álbum (`EXP-01`) y la apertura de `/reproduciendo` (`EXP-02`) para que el usuario no pueda hacer clic y descubrir la pista en otra vista.

---

### 2.2. Convenciones y Modelos Mentales (`EXP-01` a `EXP-13`)

#### EXP-01: Nombre de artista y álbum clickeables en la barra de reproducción
- **Cómo hacerlo sin romper nada:**
  1. En `src/lib/ui/BarraReproduccion.svelte`, cuando `!i.ciego && pista`:
     - Si `pista.artistaId !== null`, renderizar `<a href="/biblioteca/artista?id={pista.artistaId}" class="artista enlace">{pista.artista}</a>`; si es `null`, mantener `<span>`.
     - Si `pista.albumId !== null`, renderizar `<a href="/biblioteca/album?id={pista.albumId}" class="album enlace">{pista.album}</a>`; si es `null`, mantener `<span>`.
  2. En el CSS de `.enlace:hover`, cambiar únicamente `color: var(--m3c-on-surface)` y `text-decoration: underline` (nunca cambiar `font-size`, `padding` ni `margin` en `:hover` para no disparar `check-ui.mjs`).

#### EXP-02: Portada y título en la barra inferior abren la vista de reproducción completa
- **Cómo hacerlo sin romper nada:**
  1. En `src/lib/ui/BarraReproduccion.svelte`, envolver `.portada` y `.titulo` en un `<button type="button" class="ir-reproduciendo" disabled={!hayPista || i.ciego} onclick={() => abrirVista(false)} aria-label={t.expandir}>` (no envolver los enlaces de artista/álbum dentro del botón, porque anidar `<a>` dentro de `<button>` es HTML inválido y rompe el compilador de accesibilidad de Svelte).
  2. Mantener el contenedor `.pista` con layout limpio donde la portada y el título sean botones hacia `/reproduciendo`, y debajo el artista y el álbum sean enlaces independientes.

#### EXP-03 y COMP-06: Botón de Importar Música / Carpetas en la Barra Superior Global
- **Cómo hacerlo sin romper nada:**
  1. Extraer o reutilizar la función de importación (`importacion.anadirArchivos()` / `importacion.anadirCarpeta()`) desde `src/lib/core/importacion.svelte.ts`.
  2. En `src/lib/ui/BarraSuperior.svelte`, añadir a la derecha del buscador un botón con menú desplegable (`popover="auto"`) o par de acciones rápidas (`Añadir música` / `Añadir carpeta`) usando `<Icon nombre="mas" />` y `<Icon nombre="carpeta" />`.
  3. **Regla crítica:** Verificar que `.superior` conserve `contain: layout size` (`check-ui.mjs` línea 373) y que el popover tenga `position: fixed; inset: auto;` para no alterar el tamaño intrínseco de la barra superior.

#### EXP-04 y COMP-04: Modo de Letras centrado e inmersivo + Fondo ambiental
- **Cómo hacerlo sin romper nada:**
  1. En `src/routes/reproduciendo/+page.svelte`, agregar un conmutador de disposición cuando `conLetras` está activo: `modoLetras: 'dividido' | 'centrado'` (persistido en preferencias de apariencia o estado local).
  2. En modo `'centrado'`, ocultar `.principal` (o mostrar una miniatura compacta en la cabecera superior izquierda con título y artista) y hacer que `<aside class="letras">` ocupe la columna central completa (`max-width: 48rem; margin: 0 auto; text-align: center;`), usando el token `var(--ns-texto-2xl)` para los versos.
  3. Para el fondo ambiental dinámico (`COMP-04`), modular suavemente los tokens `--m3c-primary-container` y `--m3c-surface-container-low` generados desde `ambienteDePista(id)` mediante un gradiente radial/lineal en CSS **sin usar `animation: ... infinite` ni `backdrop-filter`** en el contenedor permanente.

#### EXP-05 y COMP-07: Botón y comando IPC para Borrar Canción (de biblioteca y/o del disco)
- **Cómo hacerlo sin romper nada:**
  1. **En Rust (`src-tauri/src/`):**
     - Crear el comando `#[tauri::command(async)] pub async fn borrar_pista(estado: State<'_, ...>, id: i64, borrar_archivo: bool) -> NsResult<()>` usando `db::write_transaction` (`check-transacciones.mjs`).
     - Si `borrar_archivo` es `true`, verificar que la ruta del archivo en base de datos se resuelva de forma segura y registrar la operación con `redact_path` (`check-registro.mjs`).
     - Registrar `borrar_pista` en `generate_handler!` dentro de `src-tauri/src/lib.rs`.
  2. **En el puente (`src/lib/core/ipc/`):**
     - Añadir `export function borrarPista(id: number, borrarArchivo: boolean): Promise<void>` llamando a `call<void>('borrar_pista', { id, borrarArchivo })` (`check-puente.mjs`).
  3. **En la UI:**
     - Añadir la opción `Eliminar canción...` en el menú contextual `···` de `FilaPista.svelte`.
     - Abrir un diálogo modal propio en Svelte (nunca `window.confirm()`, ver `COMP-18`) con dos opciones claras: *Quitar solo de la biblioteca* o *Eliminar también el archivo del equipo*, seguido de notificación Toast (`COMP-03`).

#### EXP-06 y COMP-08: Colapso manual de la Barra Lateral (Sidebar Toggle)
- **Cómo hacerlo sin romper nada:**
  1. Añadir en `aparienciaActual` (`src/lib/core/apariencia.svelte.ts`) la preferencia booleana `barraLateralCompacta: boolean` (por defecto `false`).
  2. En `src/lib/ui/AppShell.svelte`, añadir el atributo o clase `class:compacta={aparienciaActual.actual.barraLateralCompacta}` sobre `.carcasa`, y actualizar la regla CSS:
     `.carcasa:not([data-ancho='amplio']), .carcasa.compacta { grid-template-columns: var(--ns-ancho-riel) minmax(0, 1fr); }`.
  3. En `src/lib/ui/NavLateral.svelte`, colocar un botón discreto con `<Icon nombre="colapsarLateral" />` / `<Icon nombre="expandirLateral" />` (nunca caracteres `«` o `»` sueltos) y su `aria-label` internacionalizado en `src/lib/i18n/es.ts`.

#### EXP-07: Lista de canciones populares y botón aleatorio en la vista de Artista
- **Cómo hacerlo sin romper nada:**
  1. En `src/lib/ui/biblioteca/VistaArtista.svelte`, antes de la cuadrícula de álbumes, mostrar la sección de canciones del artista reutilizando `FilaPista.svelte` (en modo contextual `'artista'` para no repetir el botón "Abrir artista").
  2. Añadir en la cabecera del artista los botones `Reproducir` y `Aleatorio` con `<Icon nombre="reproducir" />` y `<Icon nombre="aleatorio" />` (sin emojis).
  3. Si se requiere un comando o consulta a Rust para obtener las pistas del artista, asegurarse de que esté acotado por `limit` (`check-listas.mjs`).

#### EXP-08: Botón de reproducción aleatoria en cabecera de Playlist
- **Cómo hacerlo sin romper nada:**
  1. En `src/lib/ui/playlists/VistaPlaylistDetalle.svelte` (o `src/routes/playlists/ver/+page.svelte`), añadir junto al botón principal de reproducir un botón secundario con `<Icon nombre="aleatorio" />` y texto `{t.aleatorio}` desde `$lib/i18n`.
  2. Al pulsarlo, activar el modo aleatorio y lanzar la cola mezclada de las pistas de la playlist.

#### EXP-09: Menú contextual de acciones en resultados de Búsqueda
- **Cómo hacerlo sin romper nada:**
  1. En `src/routes/buscar/+page.svelte`, reemplazar los botones planos de pista o enriquecer cada fila de resultado de pista incorporando el menú contextual `···` (añadir a la cola, añadir a playlist con `MenuAnadir.svelte`, ir al álbum, ir al artista).
  2. Mantener todos los textos en `src/lib/i18n/es.ts`.

#### EXP-10 y COMP-19: Adaptación contextual de `FilaPista.svelte` (sin botones ni columnas redundantes)
- **Cómo hacerlo sin romper nada:**
  1. Añadir en `src/lib/ui/biblioteca/FilaPista.svelte` una prop opcional `contexto?: 'biblioteca' | 'album' | 'artista' | 'playlist'` (por defecto `'biblioteca'`).
  2. Cuando `contexto === 'album'`: ocultar la miniatura repetida de portada, la columna del nombre del álbum y la acción "Abrir álbum".
  3. Cuando `contexto === 'artista'`: ocultar la acción redundante "Abrir artista".
  4. Ajustar `grid-template-columns` mediante clases `.fila.en-album`, `.fila.en-artista` usando únicamente unidades `rem`/`fr` permitidas o variables `--ns-*`.

#### EXP-11: Doble clic en la fila para reproducir
- **Cómo hacerlo sin romper nada:**
  1. **Atención al guardián `check-ui.mjs` (línea 663):** Añadir `ondblclick={onreproducir}` a `<div class="fila">` en `FilaPista.svelte` **fallará en `pnpm verify`** si esa misma etiqueta `<div class="fila">` no tiene también un manejador `onkeydown` y atributos de accesibilidad.
  2. **Implementación correcta:** En `<div class="fila" role="row" tabindex="0" ondblclick={onreproducir} onkeydown={(e) => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onreproducir(); } }}>`. Verificar que si el doble clic o `Enter` ocurre sobre un `<button>` hijo (como favorito o menú), `e.target !== e.currentTarget` evite disparar la reproducción por accidente.

#### EXP-12: Indicador visual de "pista sonando actualmente" en las listas
- **Cómo hacerlo sin romper nada:**
  1. En `FilaPista.svelte`, cuando `sonando` es `true`, sustituir el número de pista en `<span class="numero">` por `<Icon nombre="sonando" tamano={16} />` coloreado con `var(--m3c-primary)`.
  2. **Atención al guardián `check-ui.mjs` (línea 523):** No usar `animation: ... infinite` en CSS salvo que se registre la excepción acotada al estado `reproductor.sonando` en `scripts/check-ui.mjs`, o bien usar un icono vectorial estático/transicionado de ondas acústicas en color primario junto al título en negrita acentuada.

#### EXP-13: Tarjetas de estadísticas clicables en Inicio y Tu Música
- **Cómo hacerlo sin romper nada:**
  1. En `src/routes/+page.svelte` y `src/lib/ui/tu-musica/VistaTuMusica.svelte`, convertir las tarjetas contadoras (`Pistas`, `Artistas`, `Álbumes`) en enlaces `<a href="/biblioteca?vista=pistas">`, `<a href="/biblioteca?vista=artistas">`, `<a href="/biblioteca?vista=albumes">`.
  2. En `src/routes/biblioteca/+page.svelte`, leer el parámetro `page.url.searchParams.get('vista')` al montar o cambiar la URL para activar la pestaña correspondiente.
  3. En `:hover` sobre las tarjetas, usar `transform: scale(1.01)` o cambio de `background: var(--m3c-surface-container-high)` (nunca `translateY(-2px)` porque `check-ui.mjs` prohíbe `translate` en `:hover`).

---

### 2.3. Pulido Estético y Sobrecarga Visual (`DIS-01` a `DIS-07`)

#### DIS-01 y COMP-02: Rediseño de Ajustes con patrón Master-Detail (Estándar NB Books)
- **Cómo hacerlo sin romper nada:**
  1. En `src/routes/ajustes/+page.svelte`, sustituir la lista de anclas `<a href="#...">` por navegación de estado reactivo `let seccionActiva = $state<'biblioteca' | 'reproduccion' | 'apariencia' | 'dispositivos' | 'agregados' | 'privacidad' | 'ia' | 'acerca'>('biblioteca')`.
  2. En el panel izquierdo (`<nav class="indice" aria-label={t.secciones}>`), usar botones de pestaña con `<Icon nombre="..." />`, texto e indicador activo (`aria-current={seccionActiva === ... ? 'page' : undefined}`).
  3. En el panel derecho (`.contenido`), renderizar **únicamente** la sección activa (`{#if seccionActiva === 'apariencia'} ... {/if}`), manteniendo los `{#await import('$ui/...')}` para que cada sub-panel se cargue bajo demanda y `check-paquete.mjs` mantenga el arranque muy por debajo de 250 KB.
  4. En la sección de Apariencia (`SeccionesEscucha.svelte`), agrupar los 63 temas por categorías (Oscuros, Claros, Alto Contraste / Especiales) y reemplazar los 3 círculos planos por una **mini-maqueta visual** (`.maqueta-tema`) que pinte en miniatura la barra lateral, cabecera, tarjeta y botón de acento usando las variables del tema.

#### DIS-02 y COMP-05: Restauración de los 64 logotipos dinámicos por tema
- **Cómo hacerlo sin romper nada:**
  1. Copiar los iconos de tema a `static/logos/` asegurando que sus nombres coincidan con los identificadores canónicos de tema definidos en `src/lib/core/apariencia.svelte.ts`.
  2. En `src/lib/ui/NavLateral.svelte`, derivar la ruta:
     `const rutaLogo = $derived(\`/logos/logo_\${aparienciaActual.actual.tema}.png\`);` con fallback seguro a `/logo.png` en `onerror`.
  3. **Sincronización documental obligatoria:** Actualizar `docs/adr/decisions/ADR-008-sistema-de-diseno.md` (donde se había escrito que los 60 PNG desaparecían) registrando la enmienda que restaura el logotipo sincronizado por tema, para mantener la coherencia entre código y ADRs.

#### DIS-03: Colapsar los 10 botones de `FilaPista.svelte` en un menú contextual `···`
- **Cómo hacerlo sin romper nada:**
  1. Dejar visibles en la fila únicamente:
     - El botón de reproducción rápida (o al hacer hover/foco sobre el número/portada).
     - El botón de Favorito (`<Icon nombre="favorito" />`).
     - El botón de añadir a playlist (`+`) y el botón de más acciones (`<Icon nombre="masHorizontal" />` para el menú `···`).
  2. Mover al popover del menú `···`: *Añadir a la cola*, *Reproducir a continuación*, *Editar metadatos*, *Completar datos* (si no está verificada), *Ir al álbum*, *Ir al artista*, *Mostrar en explorador de archivos* (`COMP-13`) y *Eliminar canción* (`EXP-05`).
  3. **Regla crítica de `:hover` (`check-ui.mjs`):** Si ciertos iconos secundarios se atenúan cuando no hay hover en la fila, usar **únicamente `opacity: 0` -> `opacity: 1`** (y `:focus-within { opacity: 1 }`), jamás `display: none` ni cambios de `width` en `:hover`, porque cambiar cajas en `:hover` viola la regla de reflujo de `check-ui.mjs` y rompe la navegación por teclado.

#### DIS-04: Reemplazar la doble fila de 14 chips de ordenamiento en Biblioteca por un dropdown compacto
- **Cómo hacerlo sin romper nada:**
  1. En `src/routes/biblioteca/+page.svelte`, sustituir las dos hileras de pastillas de ordenamiento por una barra compacta de una sola línea: pestañas de vista (`Pistas`, `Álbumes`, `Artistas`), selector de modo de vista (`COMP-01`) y un control desplegable `Ordenar por: [Criterio]` + botón de dirección ascendente/descendente con `<Icon nombre="orden" />`.
  2. Todos los nombres de criterios deben provenir de `textos.biblioteca` (`check-i18n.mjs`).

#### DIS-05: Eliminar tooltips nativos redundantes (`title="..."`) que se solapan
- **Cómo hacerlo sin romper nada:**
  1. En `src/lib/ui/NavLateral.svelte` y botones que ya muestran su etiqueta de texto visible en pantalla, eliminar el atributo `title={...}` (o mostrarlo únicamente cuando la barra lateral esté en modo riel compacto donde el texto está oculto: `title={compacta ? item.etiqueta : undefined}`).
  2. En botones de solo icono, mantener `aria-label={...}` obligatorio para accesibilidad.

#### DIS-06: Añadir ejes horarios y tooltips al Mapa de actividad horaria (24h)
- **Cómo hacerlo sin romper nada:**
  1. En `src/lib/ui/tu-musica/VistaTuMusica.svelte`, agregar una fila de cabecera o pie en la cuadrícula de 24 columnas con las marcas horarias (`00h`, `06h`, `12h`, `18h`, `23h`) usando tokens `--ns-texto-xs` y `--m3c-on-surface-variant`.
  2. Añadir en cada celda descripción accesible e información al posar el cursor o enfocar con teclado (día, franja horaria y cantidad de escuchas formateada mediante `src/lib/i18n/es.ts`).

#### DIS-07 y COMP-11: Controles de avance (`‹` / `›`) y `scroll-snap` en carruseles de Inicio
- **Cómo hacerlo sin romper nada:**
  1. En `src/routes/+page.svelte`, dotar a cada sección de carrusel (`.fila`) de `scroll-snap-type: x mandatory; scroll-behavior: smooth;` y a sus tarjetas de `scroll-snap-align: start;`.
  2. Añadir en la cabecera de cada carrusel dos botones `<button type="button">` con `<Icon nombre="anterior" />` y `<Icon nombre="siguiente" />` (prohibido usar los caracteres `‹` o `›` como texto del botón, porque `check-ui.mjs` los rechaza).
  3. Al pulsarlos, ejecutar `contenedorFila.scrollBy({ left: direccion * contenedorFila.clientWidth * 0.8, behavior: 'smooth' })`.

---

### 2.4. Feedback, Estados de Carga y Notificaciones (`COMP-03` y `FDB-01` a `FDB-05`)

#### COMP-03: Sistema transversal de notificaciones Toast (`Toast.svelte`)
- **Cómo hacerlo sin romper nada:**
  1. Crear `src/lib/core/notificaciones.svelte.ts` con una cola reactiva `$state` (`exito`, `info`, `error`, `progreso`), auto-cierre temporizado y pausa al posar el ratón o recibir foco.
  2. Crear `src/lib/ui/ToastContenedor.svelte` y montarlo en `src/lib/ui/AppShell.svelte` (al tener un consumidor en `AppShell.svelte`, cumple la regla de componentes usados de `check-ui.mjs`).
  3. Usar región `aria-live="polite"` para avisos informativos/éxito y `role="alert"` para errores, sin colores literales ni `backdrop-filter`.
  4. Todas las funciones de mensajes deben recibir claves o funciones ya traducidas desde `src/lib/i18n/es.ts`.

#### FDB-01: Feedback visible en la preparación de Karaoke (`htdemucs`)
- **Cómo hacerlo sin romper nada:**
  1. Conectar los eventos de `alCambiarElKaraoke` (`BarraReproduccion.svelte`) con el sistema de notificaciones Toast o una píldora de estado visible sobre la barra inferior que muestre el título de la pista y el porcentaje numérico real (`Math.round(preparando * 100)%`).
  2. Si `karaokePreparar` lanza error o el agregado no está listo, emitir un Toast de error claro en lugar de fallar en silencio.

#### FDB-02 y COMP-07: Panel de visibilidad y purga de canciones duplicadas
- **Cómo hacerlo sin romper nada:**
  1. **En Rust:** Exponer comandos asíncronos acotados (`listar_duplicados(limit: u32)` con `check-listas.mjs` y `resolver_duplicados(...)` con `db::write_transaction` para `check-transacciones.mjs`) que consulten las pistas marcadas en `catalogo/duplicados.rs` y calculen los megabytes recuperables.
  2. **En la UI:** Añadir en Ajustes (sección *Biblioteca* o *Mantenimiento*) o en la vista de revisión una tarjeta que muestre el conteo de duplicados detectados, el espacio ocupando en disco y dos botones con confirmación modal: *Revisar duplicados* y *Limpiar duplicados dejando la mejor calidad*.

#### FDB-03: Confirmación Toast en acciones de mantenimiento y copia en Ajustes
- **Cómo hacerlo sin romper nada:**
  1. En `src/lib/ui/copia/BloqueCopia.svelte` y acciones de biblioteca/base de datos en Ajustes, disparar `notificar.exito(...)` o `notificar.error(...)` al resolver cada operación IPC.

#### FDB-04: Estado `disabled` en botones de reordenamiento de Playlist
- **Cómo hacerlo sin romper nada:**
  1. En `src/lib/ui/playlists/VistaPlaylistDetalle.svelte`, pasar `disabled={indice === 0}` al botón de subir pista y `disabled={indice === total - 1}` al botón de bajar pista, acompañados de un Toast discreto o cambio visual claro al reordenar.

#### FDB-05: Estado visual de carga en "Generar sesión" de DJ Privado
- **Cómo hacerlo sin romper nada:**
  1. En `src/lib/ui/dj/PedirSesion.svelte`, mientras la promesa de generación está en curso, mostrar un bloque de carga con `<Spinner />` (el único componente autorizado por `check-ui.mjs` para usar rotación infinita) o tarjetas esqueleto con opacidad estática, deshabilitando el botón de envío y cambiando su etiqueta a `{t.generandoSesion}`.

---

### 2.5. Restauraciones Forenses Adicionales (`COMP-01`, `COMP-09`, `COMP-13` a `COMP-18`)

#### COMP-01: Selector de Modos de Visualización (Cuadrícula Pequeña, Mediana, Grande y Lista)
- **Cómo hacerlo sin romper nada:**
  1. Añadir en `aparienciaActual` (o estado persistido de biblioteca/playlists) las preferencias `vistaBiblioteca: 'grid-sm' | 'grid-md' | 'grid-lg' | 'lista'` y `vistaPlaylists: 'grid-sm' | 'grid-md' | 'grid-lg' | 'lista'`.
  2. En la cabecera de Álbumes, Artistas y Playlists, colocar un grupo de botones conmutadores (`aria-pressed`) con iconos SVG para cada densidad.
  3. Definir en CSS las clases `.rejilla.sm`, `.rejilla.md`, `.rejilla.lg` y `.rejilla.lista` usando `grid-template-columns: repeat(auto-fill, minmax(..., 1fr))` y tokens `--ns-*`.

#### COMP-09: Selector de Playlists multi-selección y presencia en Barra de Reproducción y Búsqueda
- **Cómo hacerlo sin romper nada:**
  1. Mejorar `src/lib/ui/playlists/MenuAnadir.svelte` para que consulte a qué playlists pertenece ya la pista (o pistas), muestre casillas de verificación (`checkbox` accesibles) permitiendo marcar/desmarcar varias o crear una nueva in situ, y confirme con Toast.
  2. Incluir el botón de abrir `MenuAnadir` tanto en `BarraReproduccion.svelte` (para la pista que suena actualmente) como en los resultados de `/buscar`.

#### COMP-13: Acción "Mostrar en explorador de archivos" (Dolphin / File Manager)
- **Cómo hacerlo sin romper nada:**
  1. **En Rust:** Implementar `#[tauri::command(async)] pub async fn mostrar_en_explorador(estado: State<'_, ...>, pista_id: i64) -> NsResult<()>` (recibir `pista_id: i64` y consultar la ruta en SQLite evita incluso exponer rutas crudas desde el webview; si recibiera `ruta`, habría que canonicalizarla por `check-rutas.mjs`).
  2. En Linux/Windows/macOS, usar `#[cfg(target_os = "...")]` debidamente declarado (`check-plataforma.mjs`) o el comando del sistema (`xdg-open` sobre el directorio padre o invocación DBus `org.freedesktop.FileManager1.ShowItems`) registrando cualquier log con `redact_path` (`check-registro.mjs`).
  3. Conectar en `src/lib/core/ipc/` y añadir la opción en el menú `···` de `FilaPista.svelte` y en la vista `PorRevisar`.

#### COMP-14: Chips interactivos por categorías semánticas en DJ Privado
- **Cómo hacerlo sin romper nada:**
  1. En `src/lib/ui/dj/PedirSesion.svelte`, organizar los chips sugeridos en grupos categorizados (*Voces*, *Géneros*, *Ánimos*, *Energía*, *Contextos*) cuyos textos salgan íntegramente de `src/lib/i18n/es.ts` (`check-i18n.mjs`).
  2. Hacer que pulsar un chip **agregue o alterne** el término dentro del prompt actual (`consulta = consulta ? `${consulta}, ${chip}` : chip`) en vez de sobrescribir lo que el usuario ya escribió.

#### COMP-15: Ecualizador visual en cabecera de Inicio (`EcualizadorBarras.svelte`)
- **Cómo hacerlo sin romper nada:**
  1. Crear `src/lib/ui/EcualizadorBarras.svelte` usando barras SVG o CSS con tokens `var(--m3c-primary)` y `var(--m3c-tertiary)`.
  2. **Regla crítica (`check-ui.mjs` línea 523):** Para no violar la prohibición de animaciones infinitas en reposo ni consumir CPU cuando no suena nada, las barras deben reaccionar a los picos reales (`reproductor.picos` y `reproductor.posicion`) cuando `reproductor.sonando === true`, permaneciendo en una onda estática estilizada cuando el reproductor está en pausa o detenido. De este modo no usa `animation: ... infinite`, no gasta fotogramas en reposo y pasa `check-ui.mjs` limpiamente.

#### COMP-16: Pantalla de bienvenida y 24 chips de "Háblale a tu biblioteca" en `/buscar`
- **Cómo hacerlo sin romper nada:**
  1. En `src/routes/buscar/+page.svelte` (o en un componente diferido `src/lib/ui/buscar/BienvenidaBuscar.svelte` cargado cuando la consulta está vacía para proteger `check-paquete.mjs`), mostrar el selector de modo (*Búsqueda directa* vs *Háblale a tu biblioteca*) y la cuadrícula con las 24 ideas musicales traducidas en `src/lib/i18n/es.ts`.
  2. Al hacer clic en cualquier chip, actualizar la URL `/buscar?q=...` y ejecutar la consulta semántica.

#### COMP-17: Atajo de teclado `D` ("Sorpréndeme")
- **Cómo hacerlo sin romper nada:**
  1. En `src/lib/core/atajos.ts`, añadir `if ( minuscula === 'd' ) return 'sorprendeme';` (cuando `!e.escribiendo && !conModificador`).
  2. En `src/lib/ui/AppShell.svelte`, conectar la acción `sorprendeme` para que pida una selección aleatoria de pistas de la biblioteca y comience a reproducirla inmediatamente, mostrando un Toast con la pista elegida.

#### COMP-18: Reemplazar `window.confirm()` por un diálogo modal nativo en Svelte
- **Cómo hacerlo sin romper nada:**
  1. Crear `src/lib/ui/DialogoConfirmar.svelte` usando `<dialog>` nativo o popover modal con los tokens Material 3 (`--m3c-surface-container-high`, botón destructivo con `--m3c-error` y `--m3c-on-error`), enfoque automático en el botón `Cancelar` y cierre con tecla `Escape`.
  2. Sustituir el uso de `confirm(...)` en `src/lib/ui/playlists/VistaPlaylistDetalle.svelte:68` y reutilizar este mismo componente para confirmar el borrado de pistas (`EXP-05`) y la purga de duplicados (`FDB-02`).

---

### 2.6. Directriz sobre los Puntos a Discusión (`DISC-01` y `DISC-02`)

1. **DISC-01 (Consola de Karaoke):** **No recrear `VistaKaraoke.qml` como ruta independiente.** Mantener el diseño integrado actual (ADR-007) y resolver toda la fricción de usuario mediante el feedback explícito de progreso y notificaciones definido en `FDB-01`.
2. **DISC-02 (Avatar y bloques de redescubrimiento en Perfil):** **No añadir subida de foto de perfil ni duplicar listas de redescubrimiento en `/tu-musica`.** Mantener `/tu-musica` enfocada en analítica visual impecable (corrigiendo `BUG-04`, `DIS-06` y `EXP-13`) y potenciar el redescubrimiento a través del atajo `D` (`COMP-17`), *A ciegas* (`/a-ciegas`) y *DJ Privado* (`/dj`).

---

## 3. Protocolo de Ejecución Segura por Fase

Para garantizar que ninguna fase introduzca regresiones, cada bloque de cambios debe ejecutarse bajo el siguiente ciclo estricto:

1. **Saneamiento previo de documentación:** Limpiar los emojis y rutas absolutas en `docs/plan/observaciones-antes-pruebas-finales.md` para que `node scripts/check-docs.mjs` valide ambos documentos en `docs/plan/`.
2. **Si el paso toca Rust o añade comandos IPC (Fases 1, 3 y 4):**
   - Escribir el comando con `#[tauri::command(async)]` y retorno `NsResult<T>`.
   - Si escribe en SQLite, usar `db::write_transaction`.
   - Si devuelve `Vec<T>`, incluir `limit` o `// Cota: ...`.
   - Si registra logs con datos del usuario, usar `redact_path` / `redact_text`.
   - Ejecutar `node scripts/check-bindings.mjs` para actualizar `src/lib/bindings/`.
   - Exponer la función en `src/lib/core/ipc/` y conectarla de inmediato al componente `.svelte` que la consume.
3. **Si el paso toca Svelte, CSS o Textos (Fases 1, 2, 3 y 4):**
   - Declarar primero todas las cadenas nuevas en `src/lib/i18n/es.ts`.
   - Añadir primero cualquier icono nuevo en `src/lib/ui/Icon.svelte`.
   - Escribir los estilos usando exclusivamente tokens `--m3c-*` y `--ns-*`, respetando las reglas de `:hover` y `data-ancho`.
   - Si el componente es pesado o modal, cargarlo con `{#await import(...)}` para proteger el límite de 250 KB de `check-paquete.mjs`.
4. **Verificación obligatoria al cierre de cada sub-tarea:**
   - Ejecutar `pnpm verify` (`pnpm lint && pnpm check && pnpm test && pnpm guardianes`).
   - Ninguna fase se da por terminada si un solo guardián reporta advertencias o errores.
