<!--
  @component
  El cajón de Dispositivos de la barra superior: los teléfonos, la copia a
  dispositivos externos y el modo fiesta, lo mismo que Ajustes > Dispositivos.
-->
<script lang="ts">
  import { textos } from '#lib/i18n/index.ts';
  import Cajon from '#lib/ui/Cajon.svelte';

  import SeccionDispositivos from './SeccionDispositivos.svelte';

  const { oncerrar }: { oncerrar: () => void } = $props();

  const t = textos.ajustes;
</script>

<Cajon titulo={t.dispositivos} subtitulo={t.permitirAyuda} icono="telefono" {oncerrar}>
  <div class="contenido">
    <SeccionDispositivos />
  </div>
</Cajon>

<style>
  /* El título ya lo pone el cajón. */
  .contenido :global(section#dispositivos) {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
  }

  .contenido :global(section#dispositivos h2) {
    display: none;
  }
</style>
