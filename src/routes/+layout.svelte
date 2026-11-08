<script lang="ts">
  // Las tipografías van antes que el resto: son lo primero que el navegador
  // necesita para maquetar.
  import '../fuentes.css';
  import '../app.css';

  import { onMount, tick } from 'svelte';
  import { page } from '$app/state';
  import { aparienciaActual } from '#lib/core/apariencia.svelte.ts';
  import { mostrarVentanaPrincipal } from '#lib/core/ipc/index.ts';
  import AppShell from '#lib/ui/AppShell.svelte';

  let { children } = $props();

  // El tema que eligió el usuario: el de la caché antes de pintar, y el de la
  // base en cuanto responde (ver `apariencia.svelte.ts`).
  let aparienciaLista: Promise<void> = Promise.resolve();

  $effect.pre(() => {
    aparienciaActual.aplicarCache(document.documentElement);
    aparienciaLista = aparienciaActual.cargar(document.documentElement);
  });

  onMount(() => {
    if (page.url.pathname === '/mini') return;
    void (async () => {
      await aparienciaLista;
      await tick();
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
      await mostrarVentanaPrincipal();
    })();
  });
</script>

<!-- El minirreproductor es otra ventana: sin carcasa. -->
{#if page.url.pathname === '/mini'}
  {@render children()}
{:else}
  <AppShell>
    {@render children()}
  </AppShell>
{/if}
