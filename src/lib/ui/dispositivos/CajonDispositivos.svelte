<!--
  @component
  El cajón de Dispositivos de la barra superior: los teléfonos, la copia a una
  tarjeta o un USB y el modo fiesta.
-->
<script lang="ts">
  import { textos } from '#lib/i18n/index.ts';
  import Cajon from '#lib/ui/Cajon.svelte';

  import SeccionDispositivos from './SeccionDispositivos.svelte';

  const { oncerrar }: { oncerrar: () => void } = $props();

  const t = textos.ajustes;
</script>

<Cajon titulo={t.dispositivos} subtitulo={t.dispositivosSub} icono="telefono" {oncerrar}>
  <SeccionDispositivos />
</Cajon>
