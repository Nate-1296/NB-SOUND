<!--
  Su contenido se carga a demanda: los nodos de ruta entran en el arranque
  (`check-paquete`).
-->

{#await import('#lib/ui/reproduciendo/VistaReproduciendo.svelte') then m}
  <m.default />
{/await}
