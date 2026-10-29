<script lang="ts">
  // Las tipografías van antes que el resto: son lo primero que el navegador
  // necesita para maquetar.
  import '../fuentes.css';
  import '../app.css';

  import AppShell from '$ui/AppShell.svelte';
  import { APARIENCIA_DE_FABRICA, aplicarApariencia, elSistemaPrefiereOscuro } from '$ui/tema';

  let { children } = $props();

  // La apariencia se aplica antes de pintar. Hasta que las preferencias vivan en
  // la base (F2.2.9) es la de fábrica, que coincide con `paletas.css`.
  $effect.pre(() => {
    void aplicarApariencia(
      document.documentElement,
      APARIENCIA_DE_FABRICA,
      elSistemaPrefiereOscuro()
    );
  });
</script>

<AppShell>
  {@render children()}
</AppShell>
