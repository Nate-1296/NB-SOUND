<!--
  @component
  La carcasa: barra lateral, barra superior, contenido y reproductor.

  El reproductor es permanente y el contenido es lo único que se desplaza; el
  cromo que queda encima del contenido es opaco, sin desenfoques (regla de
  ADR-008 heredada de NB Books).
-->
<script lang="ts">
  import type { Snippet } from 'svelte';

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
</script>

<div class="carcasa" data-ancho={clase} bind:clientWidth={ancho}>
  <div class="lateral"><NavLateral {pendientes} /></div>
  <div class="superior"><BarraSuperior /></div>
  <main class="contenido">{@render children()}</main>
  <div class="reproductor"><BarraReproduccion /></div>
</div>

<style>
  .carcasa {
    display: grid;
    grid-template-columns: var(--ns-ancho-lateral) minmax(0, 1fr);
    grid-template-rows: var(--ns-alto-superior) minmax(0, 1fr) var(--ns-alto-reproductor);
    grid-template-areas:
      'lateral superior'
      'lateral contenido'
      'reproductor reproductor';
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
  }

  .carcasa:not([data-ancho='amplio']) {
    grid-template-columns: var(--ns-ancho-riel) minmax(0, 1fr);
  }
</style>
