<!--
  @component
  Las playlists ancladas, en la barra lateral: a un clic desde cualquier vista.
  Anclar ya existía (la V1 lo tenía), pero solo ordenaba la vista de Playlists;
  aquí es un acceso directo, como en los reproductores que se usan a diario. Se
  carga aparte del arranque y se refresca al navegar, que es cuando se ancla o
  se desancla.
-->
<script lang="ts">
  import { page } from '$app/state';
  import { type PlaylistResumen, playlistsListar } from '#lib/core/ipc/index.ts';
  import { textos } from '#lib/i18n/index.ts';

  import Mosaico from './Mosaico.svelte';

  let ancladas = $state<PlaylistResumen[]>([]);

  $effect(() => {
    void page.url.href;
    void playlistsListar({ texto: null, categoria: null, orden: 'recientes' })
      .then((l) => (ancladas = l.filter((p) => p.anclada).slice(0, 12)))
      .catch(() => {});
  });

  const abierta = $derived(
    page.url.pathname === '/playlists/ver' ? Number(page.url.searchParams.get('id')) : null
  );
</script>

{#if ancladas.length > 0}
  <section class="ancladas" aria-labelledby="t-ancladas">
    <h2 id="t-ancladas" class="rotulo">{textos.nav.ancladas}</h2>
    <ul>
      {#each ancladas as p (p.id)}
        <li>
          <a
            href={`/playlists/ver?id=${p.id}`}
            class:activa={abierta === p.id}
            aria-current={abierta === p.id ? 'page' : undefined}
          >
            <span class="mini"><Mosaico pistas={p.mosaico} tamano={64} /></span>
            <span class="nombre">{p.nombre}</span>
          </a>
        </li>
      {/each}
    </ul>
  </section>
{/if}

<style>
  /* El único tramo de la barra que se encoge: con muchas ancladas, se desplaza él
     y Ajustes sigue al pie. */
  .ancladas {
    flex: 1 1 0;
    min-height: 5rem;
    overflow-y: auto;
  }

  .rotulo {
    margin: 0 0 var(--ns-espacio-2);
    padding: 0 var(--ns-espacio-4);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  ul {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  a {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-1) var(--ns-espacio-3);
    border-radius: var(--ns-radio-md);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
    text-decoration: none;
    transition: background var(--ns-duracion-corta) var(--ns-curva);
  }

  a:hover {
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
  }

  a.activa {
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
    font-weight: 700;
  }

  .mini {
    flex: 0 0 2rem;
    width: 2rem;
    overflow: hidden;
    border-radius: var(--ns-radio-sm);
  }

  .nombre {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
