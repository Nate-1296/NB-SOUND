<!--
  @component
  "Añadir a playlist" desde cualquier canción (`MenuAgregarPlaylist.qml` de la V1):
  las playlists manuales y, arriba, crear una nueva con la canción dentro.
-->
<script lang="ts">
  import { agregarAPlaylist, type PlaylistResumen, playlistsListar } from '$core/ipc';
  import { textos } from '$lib/i18n';

  import Icon from '../Icon.svelte';
  import DialogoPlaylist from './DialogoPlaylist.svelte';

  interface Props {
    pistas: number[];
    oncerrar: () => void;
  }

  let { pistas, oncerrar }: Props = $props();
  const t = textos.playlists;

  let lista = $state<PlaylistResumen[]>([]);
  let creando = $state(false);
  let aviso = $state<string | null>(null);

  $effect(() => {
    void playlistsListar({ texto: null, categoria: 'creada', orden: 'nombreAsc' }).then(
      (p) => (lista = p)
    );
  });

  async function anadir(id: number, nombre: string) {
    const entraron = await agregarAPlaylist(id, pistas);
    aviso = entraron > 0 ? t.anadida(nombre) : t.yaEstaba(nombre);
    setTimeout(oncerrar, 900);
  }
</script>

<div class="menu" role="menu" aria-label={t.anadirA}>
  {#if aviso}
    <p class="aviso" role="status">{aviso}</p>
  {:else}
    <button type="button" role="menuitem" class="opcion nueva" onclick={() => (creando = true)}>
      <Icon nombre="mas" tamano={16} />{t.nueva}
    </button>
    {#each lista as p (p.id)}
      <button type="button" role="menuitem" class="opcion" onclick={() => anadir(p.id, p.nombre)}>
        <Icon nombre="playlists" tamano={16} />
        <span class="nombre">{p.nombre}</span>
      </button>
    {/each}
  {/if}
</div>

<DialogoPlaylist
  abierto={creando}
  onlisto={(id, nombre) => {
    creando = false;
    void anadir(id, nombre);
  }}
  oncerrar={() => (creando = false)}
/>

<style>
  .menu {
    display: flex;
    flex-direction: column;
    min-width: 14rem;
    max-height: 18rem;
    overflow-y: auto;
    padding: var(--ns-espacio-1);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-high);
    box-shadow: var(--m3-elevation-2, none);
  }

  .opcion {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    height: 2.25rem;
    padding: 0 var(--ns-espacio-3);
    border: none;
    border-radius: var(--ns-radio-sm);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    text-align: left;
    cursor: pointer;
  }

  .opcion:hover {
    background: var(--m3c-surface-container-highest);
  }

  .nueva {
    color: var(--m3c-primary);
    font-weight: 700;
  }

  .nombre {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .aviso {
    margin: 0;
    padding: var(--ns-espacio-3);
    font-size: var(--ns-texto-sm);
  }
</style>
