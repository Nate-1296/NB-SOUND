<!--
  Su contenido se carga a demanda: los nodos de ruta entran en el arranque
  (`check-paquete`).
-->

{#await import('$ui/playlists/VistaPlaylists.svelte') then m}
  <m.default />
{/await}
