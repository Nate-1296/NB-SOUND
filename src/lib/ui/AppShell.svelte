<!--
  @component
  La carcasa, con la disposición de la V1 (`legado/ui/qml/Principal.qml`): la barra
  lateral ocupa toda la altura y, a su derecha, la barra superior, el contenido y la
  barra de reproducción.

  El reproductor es permanente y el contenido es lo único que se desplaza; el
  cromo que queda encima del contenido es opaco, sin desenfoques (ADR-008).
-->
<script lang="ts">
  import { onMount, type Snippet } from 'svelte';

  import { accionDeTecla, esCampoDeTexto } from '$core/atajos';
  import { abrirMinirreproductor } from '$core/ipc';
  import { reproductor } from '$core/reproductor.svelte';

  import { clasificarAncho } from './anchos';
  import BarraReproduccion from './BarraReproduccion.svelte';
  import BarraSuperior from './BarraSuperior.svelte';
  import NavLateral from './NavLateral.svelte';

  interface Props {
    pendientes?: number;
    children: Snippet;
  }

  let { pendientes = 0, children }: Props = $props();

  let ancho = $state(0);
  const clase = $derived(clasificarAncho(ancho));

  onMount(() => {
    void reproductor.arrancar();
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
      mini: abrirMinirreproductor
    };
    void acciones[accion]();
  }
</script>

<svelte:window onkeydown={alPulsar} />

<div class="carcasa" data-ancho={clase} bind:clientWidth={ancho}>
  <div class="lateral"><NavLateral {pendientes} /></div>
  <div class="superior"><BarraSuperior /></div>
  <main class="contenido">{@render children()}</main>
  <div class="reproductor"><BarraReproduccion /></div>
</div>

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

  .contenido {
    grid-area: contenido;
    min-height: 0;
    overflow-y: auto;
    padding: var(--ns-espacio-2) var(--ns-espacio-5) var(--ns-espacio-6);
  }

  .reproductor {
    grid-area: reproductor;
    min-width: 0;
  }

  .carcasa:not([data-ancho='amplio']) {
    grid-template-columns: var(--ns-ancho-riel) minmax(0, 1fr);
  }
</style>
