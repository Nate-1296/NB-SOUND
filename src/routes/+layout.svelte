<script lang="ts">
  // Las tipografías van antes que el resto: son lo primero que el navegador
  // necesita para maquetar.
  import '../fuentes.css';
  import '../app.css';

  import { page } from '$app/state';
  import { aparienciaActual } from '$core/apariencia.svelte';
  import AppShell from '$ui/AppShell.svelte';

  let { children } = $props();

  // El tema de la V1 que eligió el usuario: el de la caché antes de pintar, y el
  // de la base en cuanto responde (ver `apariencia.svelte.ts`).
  $effect.pre(() => {
    aparienciaActual.aplicarCache(document.documentElement);
    void aparienciaActual.cargar(document.documentElement);
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
