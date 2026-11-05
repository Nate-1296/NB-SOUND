<!--
  @component
  La fila de acciones bajo la cabecera de un álbum, un artista o una playlist: el
  botón grande de reproducir, aleatorio, lo propio de cada uno y el menú ··· con
  lo secundario. Las tres vistas tenían su propia fila, con los mismos botones en
  píldora y en distinto orden.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';

  import { textos } from '#lib/i18n/index.ts';

  import Icon from './Icon.svelte';
  import MenuAcciones, { type Accion } from './MenuAcciones.svelte';

  interface Props {
    onreproducir: () => unknown;
    onaleatorio: () => unknown;
    /** Sin canciones no hay nada que reproducir. */
    vacia?: boolean;
    acciones?: readonly Accion[];
    children?: Snippet;
  }

  let { onreproducir, onaleatorio, vacia = false, acciones = [], children }: Props = $props();
  const t = textos.biblioteca;
</script>

<div class="acciones">
  <button
    type="button"
    class="reproducir"
    disabled={vacia}
    aria-label={t.reproducir}
    title={t.reproducir}
    onclick={onreproducir}
  >
    <Icon nombre="reproducir" tamano={26} />
  </button>
  <button
    type="button"
    class="redondo"
    disabled={vacia}
    aria-label={t.album.aleatorio}
    title={t.album.aleatorio}
    onclick={onaleatorio}
  >
    <Icon nombre="aleatorio" tamano={22} />
  </button>
  {@render children?.()}
  {#if acciones.length > 0}
    <MenuAcciones {acciones} etiqueta={t.masAcciones} />
  {/if}
</div>

<style>
  .acciones {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--ns-espacio-3);
  }

  .reproducir {
    display: grid;
    place-items: center;
    width: 3.5rem;
    height: 3.5rem;
    padding: 0;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
    box-shadow: 0 6px 18px var(--m3c-shadow);
    cursor: pointer;
    transition:
      transform var(--ns-duracion-corta) var(--ns-curva),
      filter var(--ns-duracion-corta) var(--ns-curva);
  }

  .reproducir:hover:not(:disabled) {
    transform: scale(1.05);
    filter: brightness(1.06);
  }

  .redondo {
    display: grid;
    place-items: center;
    width: 2.75rem;
    height: 2.75rem;
    padding: 0;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
    transition:
      background var(--ns-duracion-corta) var(--ns-curva),
      color var(--ns-duracion-corta) var(--ns-curva);
  }

  .redondo:hover:not(:disabled) {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
  }

  button:disabled {
    opacity: 0.38;
    cursor: default;
  }

  /* Lo propio de cada vista ("Añadir canciones") va en píldora con contorno. */
  .acciones :global(.pildora) {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    height: 2.5rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    cursor: pointer;
  }

  .acciones :global(.pildora:hover),
  .acciones :global(.pildora[aria-pressed='true']) {
    border-color: var(--m3c-outline);
    background: var(--m3c-surface-container-highest);
  }
</style>
