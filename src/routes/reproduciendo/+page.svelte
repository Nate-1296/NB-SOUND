<!--
  Su contenido se carga a demanda: los nodos de ruta entran en el arranque
  (`check-paquete`).
-->

{#await import('$ui/reproduciendo/VistaReproduciendo.svelte') then m}
  <m.default />
{/await}
