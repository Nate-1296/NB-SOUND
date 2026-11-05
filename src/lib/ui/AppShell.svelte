<!--
  @component
  La carcasa, con la disposición de capas inspirada en Material 3 y NB Books:
  la barra lateral y la barra superior sobre la superficie de la ventana, el contenido
  en un lienzo redondeado de contenedor suave, y la barra de reproducción permanente.

  El reproductor es permanente y el contenido es lo único que se desplaza; el
  cromo que queda encima del contenido es opaco, sin desenfoques (ADR-008).
-->
<script lang="ts">
  import { onMount, type Snippet } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';

  import { accionDeTecla, esCampoDeTexto } from '#lib/core/atajos.ts';
  import { aparienciaActual } from '#lib/core/apariencia.svelte.ts';
  import { abrirMinirreproductor, sorprendeme } from '#lib/core/ipc/index.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { importacion } from '#lib/core/importacion.svelte.ts';
  import { pantalla } from '#lib/core/pantalla.svelte.ts';
  import { telefonos } from '#lib/core/movil.svelte.ts';
  import { reproductor } from '#lib/core/reproductor.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';

  import { clasificarAncho } from './anchos';
  import BarraReproduccion from './BarraReproduccion.svelte';
  import BarraSuperior from './BarraSuperior.svelte';
  import NavLateral from './NavLateral.svelte';

  interface Props {
    children: Snippet;
  }

  let { children }: Props = $props();

  let ancho = $state(0);
  const clase = $derived(clasificarAncho(ancho));
  const enReproduciendo = $derived(page.url.pathname === '/reproduciendo');
  const vistaFijada = $derived(page.url.pathname === '/playlists');

  // Se abre donde se dejó: la ruta va al almacenamiento del webview al navegar.
  const ULTIMA_RUTA = 'ns:ultima-ruta';
  // Se lee al crear la carcasa, antes de que el efecto de abajo guarde la de ahora.
  const rutaGuardada = (() => {
    try {
      return localStorage.getItem(ULTIMA_RUTA);
    } catch {
      return null;
    }
  })();

  $effect(() => {
    const ruta = page.url.pathname + page.url.search;
    try {
      localStorage.setItem(ULTIMA_RUTA, ruta);
    } catch {
      // Sin almacenamiento se abre en Inicio, como siempre.
    }
  });

  onMount(() => {
    if (rutaGuardada && rutaGuardada !== '/' && page.url.pathname === '/') {
      void goto(rutaGuardada, { replaceState: true });
    }
    void reproductor.arrancar();
    void pantalla.sincronizar();
    void telefonos.arrancar();
    void importacion.arrancar();
  });

  function alPulsar(e: KeyboardEvent) {
    const accion = accionDeTecla({
      key: e.key,
      ctrlKey: e.ctrlKey,
      metaKey: e.metaKey,
      altKey: e.altKey,
      escribiendo: esCampoDeTexto(document.activeElement)
    });
    if (!accion) return;
    // Un botón con el foco ya responde al espacio: no se toca dos veces.
    if (accion === 'pausarReanudar' && document.activeElement instanceof HTMLButtonElement) return;
    // Con un diálogo o un menú abierto, Escape es suyo.
    if (accion === 'salir' && document.querySelector('dialog[open], [popover]:popover-open'))
      return;
    e.preventDefault();
    const i = reproductor.instantanea;
    const r = reproductor;
    const acciones: Record<typeof accion, () => unknown> = {
      pausarReanudar: r.pausarReanudar,
      retroceder: () => r.buscar(Math.max(0, r.posicion - 10)),
      avanzar: () => r.buscar(r.posicion + 10),
      anterior: r.anterior,
      siguiente: r.siguiente,
      aleatorio: r.alternarAleatorio,
      repeticion: r.rotarRepeticion,
      karaoke: () => i.karaokeDisponible && r.alternarKaraoke(),
      subirVolumen: () => r.volumen(Math.min(1, i.volumen + 0.05)),
      bajarVolumen: () => r.volumen(Math.max(0, i.volumen - 0.05)),
      letras: () => window.dispatchEvent(new CustomEvent('ns:vista', { detail: { letras: true } })),
      ampliada: () =>
        window.dispatchEvent(new CustomEvent('ns:vista', { detail: { letras: false } })),
      cola: () => window.dispatchEvent(new CustomEvent('ns:cola')),
      mini: abrirMinirreproductor,
      pantallaCompleta: () => pantalla.alternar(),
      // Primero se sale de la pantalla completa; después, de la reproducción ampliada.
      salir: () => {
        if (pantalla.completa) return pantalla.alternar();
        if (enReproduciendo) history.back();
      },
      sorprendeme: async () => {
        const p = await sorprendeme().catch(() => null);
        if (p) notificar.informacion(textos.inicio.sorprendeme(p.titulo, p.artista));
      }
    };
    void acciones[accion]();
  }

  let temporizadorOcultar: ReturnType<typeof setTimeout> | undefined;

  let ultimoPuntero = { x: -1, y: -1 };

  /**
   * En pantalla completa, la reproducción esconde sus controles a los 3,5 s quieta.
   * Solo cuenta el ratón que se mueve de verdad: WebKit también emite `mousemove`
   * cuando lo que hay debajo se desplaza (la letra que avanza sola), y entonces
   * los controles no se escondían nunca.
   */
  function alMoverRaton(e: MouseEvent) {
    if (e.screenX === ultimoPuntero.x && e.screenY === ultimoPuntero.y) return;
    ultimoPuntero = { x: e.screenX, y: e.screenY };
    pantalla.controlesVisibles = true;
    if (!enReproduciendo || !pantalla.completa) return;
    clearTimeout(temporizadorOcultar);
    temporizadorOcultar = setTimeout(() => {
      pantalla.controlesVisibles = false;
    }, 3500);
  }

  $effect(() => {
    if (!enReproduciendo || !pantalla.completa) {
      clearTimeout(temporizadorOcultar);
      pantalla.controlesVisibles = true;
    }
  });
</script>

<svelte:window
  onkeydown={alPulsar}
  onmousemove={alMoverRaton}
  onresize={() => void pantalla.sincronizar()}
/>

<div
  class="carcasa"
  class:compacta={aparienciaActual.barraLateralCompacta}
  class:sin-lateral={enReproduciendo}
  class:inmersiva={enReproduciendo && pantalla.completa}
  class:ocultar-controles={enReproduciendo && pantalla.completa && !pantalla.controlesVisibles}
  data-ancho={clase}
  bind:clientWidth={ancho}
>
  <div class="lateral" class:oculta={enReproduciendo}>
    <NavLateral pendientes={importacion.pendientes} estrecha={clase !== 'amplio'} />
  </div>
  <div class="superior" class:oculta={enReproduciendo}><BarraSuperior /></div>
  <div class="lienzo" class:en-reproduciendo={enReproduciendo}>
    <main
      class="contenido"
      class:en-reproduciendo={enReproduciendo}
      class:vista-fijada={vistaFijada}
    >
      {@render children()}
    </main>
  </div>
  <div class="reproductor"><BarraReproduccion /></div>
</div>
{#if importacion.arrastrando}
  {#await import('./importacion/CapaArrastre.svelte') then m}
    <m.default />
  {/await}
{/if}
{#if importacion.progreso.activa || importacion.resumen}
  {#await import('./importacion/TarjetaImportacion.svelte') then m}
    <m.default />
  {/await}
{/if}
{#await import('./Avisos.svelte') then m}
  <m.default />
{/await}

<style>
  .carcasa {
    container: carcasa / inline-size;
    display: grid;
    grid-template-columns: var(--ns-ancho-lateral) minmax(0, 1fr);
    grid-template-rows: var(--ns-alto-superior) minmax(0, 1fr) var(--ns-alto-reproductor);
    grid-template-areas:
      'lateral superior'
      'lateral contenido'
      'lateral reproductor';
    height: 100vh;
    background: var(--m3c-surface);
  }

  .lateral {
    grid-area: lateral;
    min-height: 0;
  }

  .superior {
    grid-area: superior;
  }

  /*
   * El lienzo del contenido: como en NB Books (ADR-012 / ADR-008), la jerarquía
   * visual la dan las capas y no los bordes toscos. El contenido flota en una
   * tarjeta redondeada de contenedor suave (surface-container-low) sobre la superficie
   * de la ventana.
   */
  .lienzo {
    grid-area: contenido;
    min-height: 0;
    min-width: 0;
    display: flex;
    flex-direction: column;
    background: var(--m3c-surface-container-low);
    border-radius: var(--ns-radio-xl);
    margin: 0 var(--ns-espacio-4) var(--ns-espacio-2) 0;
    overflow: hidden;
    position: relative;
  }

  .lienzo.en-reproduciendo {
    margin: 0;
    border-radius: 0;
    background: transparent;
  }

  .contenido {
    flex: 1 1 auto;
    min-height: 0;
    min-width: 0;
    overflow-y: auto;
    padding: var(--ns-espacio-2) var(--ns-espacio-5) var(--ns-espacio-6);
  }

  .contenido.en-reproduciendo {
    padding: 0;
    overflow: hidden;
  }

  .contenido.vista-fijada {
    overflow: hidden;
    padding: var(--ns-espacio-3) var(--ns-espacio-4) var(--ns-espacio-3) var(--ns-espacio-5);
  }

  .reproductor {
    grid-area: reproductor;
    min-width: 0;
    transition:
      transform 300ms var(--ns-curva),
      opacity 300ms var(--ns-curva);
  }

  .carcasa.ocultar-controles .reproductor {
    transform: translateY(100%);
    opacity: 0;
    pointer-events: none;
  }

  /*
   * En pantalla completa la reproducción ocupa toda la altura y la barra flota
   * encima: al esconderse no deja una franja vacía abajo, y el contenido no se
   * recoloca cada vez que aparece.
   */
  .carcasa.inmersiva .lienzo {
    grid-row: 1 / -1;
  }

  .carcasa.inmersiva .reproductor {
    position: relative;
    z-index: 1;
    grid-row: 2;
  }

  .lateral.oculta,
  .superior.oculta {
    display: none;
  }

  .carcasa.sin-lateral {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) var(--ns-alto-reproductor);
    grid-template-areas:
      'contenido'
      'reproductor';
  }

  .carcasa:not(.sin-lateral):not([data-ancho='amplio']),
  .carcasa:not(.sin-lateral).compacta {
    grid-template-columns: var(--ns-ancho-riel) minmax(0, 1fr);
  }
</style>
