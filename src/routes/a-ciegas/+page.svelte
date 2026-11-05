<!--
  A ciegas. Su contenido se carga a demanda: los nodos de ruta entran en el
  arranque (`check-paquete`).
-->

{#await import('#lib/ui/aciegas/VistaACiegas.svelte') then m}
  <m.default />
{/await}
