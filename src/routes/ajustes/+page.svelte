<script lang="ts">
  import { salud } from '$core/ipc';
  import { textos } from '$lib/i18n';
  import VistaPendiente from '$ui/VistaPendiente.svelte';

  // La versión la da el runtime y no el paquete del frontend: es la del binario
  // que de verdad está corriendo.
  const version = salud()
    .then((informe) => informe.version)
    .catch(() => null);
</script>

<VistaPendiente titulo={textos.nav.ajustes} icono="ajustes" />

<section class="acerca" aria-labelledby="acerca-titulo">
  <h2 id="acerca-titulo">{textos.ajustes.acercaDe}</h2>
  {#await version then v}
    {#if v}
      <p>{textos.ajustes.version(v)}</p>
    {/if}
  {/await}
</section>

<style>
  .acerca {
    margin-top: var(--ns-espacio-5);
    color: var(--m3c-on-surface-variant);
  }

  h2 {
    font-size: var(--ns-texto-lg);
    color: var(--m3c-on-surface);
  }
</style>
