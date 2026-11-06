<!--
  @component
  "Añadir a playlist" desde cualquier canción: las playlists manuales y, arriba,
  crear una nueva con la canción dentro.
-->
<script lang="ts">
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import {
    agregarAPlaylist,
    type PlaylistResumen,
    playlistsDePista,
    playlistsListar,
    quitarDePlaylist
  } from '#lib/core/ipc/index.ts';
  import { esAparte } from '#lib/i18n/es-aparte.ts';
  import { textos } from '#lib/i18n/index.ts';

  import Icon from '../Icon.svelte';
  import DialogoPlaylist from './DialogoPlaylist.svelte';

  interface Props {
    pistas: number[];
    oncerrar: () => void;
  }

  let { pistas, oncerrar }: Props = $props();
  const t = textos.playlists;

  let lista = $state<PlaylistResumen[]>([]);
  let contenidas = $state<Set<number>>(new Set());
  let creando = $state(false);

  $effect(() => {
    void playlistsListar({ texto: null, categoria: 'creada', orden: 'nombreAsc' }).then((p) => {
      // Las inteligentes también son «creadas», pero se llenan solas.
      lista = p.filter((x) => x.editable);
    });
    const [una] = pistas;
    if (pistas.length === 1 && una !== undefined) {
      void playlistsDePista(una).then((ids) => (contenidas = new Set(ids)));
    }
  });

  async function alternar(p: PlaylistResumen) {
    const [una] = pistas;
    try {
      if (contenidas.has(p.id) && pistas.length === 1 && una !== undefined) {
        await quitarDePlaylist(p.id, una);
        contenidas.delete(p.id);
        notificar.informacion(t.quitada(p.nombre));
      } else {
        const entraron = await agregarAPlaylist(p.id, pistas);
        contenidas.add(p.id);
        notificar.exito(entraron > 0 ? t.anadida(p.nombre) : t.yaEstaba(p.nombre));
      }
      contenidas = new Set(contenidas);
    } catch {
      notificar.error(esAparte.comun.error);
    }
  }
</script>

<div class="menu" role="menu" aria-label={t.anadirA}>
  <button type="button" role="menuitem" class="opcion nueva" onclick={() => (creando = true)}>
    <Icon nombre="mas" tamano={16} />{t.nueva}
  </button>
  {#each lista as p (p.id)}
    {@const esta = contenidas.has(p.id)}
    <button
      type="button"
      role="menuitemcheckbox"
      aria-checked={esta}
      class="opcion"
      class:activa={esta}
      onclick={() => alternar(p)}
    >
      <span class="icono-check">
        {#if esta}
          <Icon nombre="comprobado" tamano={16} />
        {:else}
          <Icon nombre="playlists" tamano={16} />
        {/if}
      </span>
      <span class="nombre">{p.nombre}</span>
    </button>
  {/each}
</div>

<DialogoPlaylist
  abierto={creando}
  onlisto={(id, nombre) => {
    creando = false;
    void agregarAPlaylist(id, pistas).then(() => {
      contenidas.add(id);
      contenidas = new Set(contenidas);
      notificar.exito(t.anadida(nombre));
    });
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

  .opcion.activa {
    color: var(--m3c-primary);
    font-weight: 600;
  }

  .icono-check {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 1.25rem;
    height: 1.25rem;
  }

  .nueva {
    color: var(--m3c-primary);
    font-weight: 700;
  }

  .nombre {
    flex: 1;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
</style>
