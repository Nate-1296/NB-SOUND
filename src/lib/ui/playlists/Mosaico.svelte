<!--
  @component
  La portada de una playlist: el mosaico de las portadas de sus canciones, como en
  la V1. Con una sola, ocupa todo; sin ninguna, un hueco con el icono.
-->
<script lang="ts">
  import { urlPortada } from '$core/ipc';

  import Icon from '../Icon.svelte';

  interface Props {
    pistas: number[];
    tamano?: number;
  }

  let { pistas, tamano = 160 }: Props = $props();
  const lado = $derived(pistas.length >= 4 ? 2 : 1);
  const visibles = $derived(pistas.slice(0, lado * lado));
</script>

<span class="mosaico" style:--lado={lado} aria-hidden="true">
  {#if visibles.length === 0}
    <span class="vacio"><Icon nombre="playlists" tamano={40} /></span>
  {:else}
    {#each visibles as id (id)}
      <img src={urlPortada('pista', id, lado === 2 ? tamano / 2 : tamano)} alt="" loading="lazy" />
    {/each}
  {/if}
</span>

<style>
  .mosaico {
    display: grid;
    grid-template-columns: repeat(var(--lado), 1fr);
    aspect-ratio: 1;
    overflow: hidden;
    border-radius: var(--ns-radio-sm);
    background: linear-gradient(
      160deg,
      var(--m3c-primary-container),
      var(--m3c-tertiary-container)
    );
  }

  img {
    width: 100%;
    height: 100%;
    aspect-ratio: 1;
    object-fit: cover;
  }

  .vacio {
    display: grid;
    place-items: center;
    color: var(--m3c-on-primary-container);
  }
</style>
