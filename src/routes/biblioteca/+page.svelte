<!--
  Biblioteca: carga diferida para mantener el presupuesto de arranque (F0.4.7).
-->
<script lang="ts">
  import { textos } from '$lib/i18n';
</script>

{#await import('$ui/biblioteca/VistaBiblioteca.svelte')}
  <div class="cargando-contenedor">
    <p class="cargando">{textos.biblioteca.cargando}...</p>
  </div>
{:then m}
  <m.default />
{/await}

<style>
  .cargando-contenedor {
    display: grid;
    place-items: center;
    min-height: 20rem;
  }

  .cargando {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }
</style>
