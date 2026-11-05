<!--
  Su contenido se carga a demanda: los nodos de ruta entran en el arranque
  (`check-paquete`).
-->

{#await import('#lib/ui/playlists/VistaPlaylistDetalle.svelte') then m}
  <m.default />
{/await}
