<script lang="ts">
  import { onMount } from 'svelte';
  import { iniciarSolicitudLauncher } from '#lib/core/enlace-launcher.ts';
  import Avisos from './Avisos.svelte';

  let solicitudLauncher = $state(false);
  onMount(() => {
    let activo = true;
    let soltar: (() => void) | undefined;
    void iniciarSolicitudLauncher(() => {
      if (activo) solicitudLauncher = true;
    })
      .then((terminar) => {
        if (activo) soltar = terminar;
        else terminar();
      })
      .catch(() => {});
    return () => {
      activo = false;
      soltar?.();
    };
  });
</script>

<Avisos />
{#if solicitudLauncher}
  {#await import('./launcher/AutorizacionLauncher.svelte') then m}
    <m.default />
  {/await}
{/if}
