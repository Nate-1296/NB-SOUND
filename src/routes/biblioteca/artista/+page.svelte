<!--
  Detalle de artista. Su contenido se carga a demanda: los nodos de ruta entran
  en el arranque (`check-paquete`).
-->

{#await import('$ui/biblioteca/VistaArtista.svelte') then m}
  <m.default />
{/await}
