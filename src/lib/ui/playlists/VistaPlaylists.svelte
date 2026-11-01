<!--
  @component
  Playlists, con la disposición de la V1 (`VistaPlaylists.qml`): título, Crear para
  mí, Nueva inteligente, Nueva playlist, la búsqueda, las categorías y los órdenes
  en fichas, la rejilla de tarjetas con su mosaico y, a la derecha, el panel de la
  seleccionada con Abrir, Anclar y Reproducir.
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import {
    anclarPlaylist,
    type Categoria,
    type OrdenPlaylists,
    type PlaylistResumen,
    playlistsListar,
    reproducirPlaylist
  } from '$core/ipc';
  import { regenerarPlaylistsAutomaticas } from '$core/ipc/aparte';
  import { formatoTiempo } from '$core/reproductor.svelte';
  import { textos } from '$lib/i18n';
  import { esAparte } from '$lib/i18n/es-aparte';
  import Icon from '$ui/Icon.svelte';
  import DialogoInteligente from '$ui/playlists/DialogoInteligente.svelte';
  import DialogoPlaylist from '$ui/playlists/DialogoPlaylist.svelte';
  import Mosaico from '$ui/playlists/Mosaico.svelte';

  const t = textos.playlists;
  const ti = esAparte.inteligentes;
  const CATEGORIAS: (Categoria | null)[] = [null, 'meGusta', 'creada', 'inteligente', 'thisIs'];
  const ORDENES: OrdenPlaylists[] = [
    'recientes',
    'antiguas',
    'nombreAsc',
    'nombreDesc',
    'masCanciones',
    'menosCanciones'
  ];

  let texto = $state('');
  let categoria = $state<Categoria | null>(null);
  let orden = $state<OrdenPlaylists>('recientes');
  let lista = $state<PlaylistResumen[]>([]);
  let seleccionada = $state<number | null>(null);
  let creando = $state(false);
  let creandoInteligente = $state(false);
  let regenerando = $state(false);
  let version = $state(0);
  let modoRejilla = $state<'sm' | 'md' | 'lg' | 'lista'>('md');

  $effect(() => {
    const consulta = { texto: texto.trim() || null, categoria, orden };
    void version;
    void playlistsListar(consulta).then((p) => {
      lista = p;
      if (seleccionada === null || !p.some((x) => x.id === seleccionada)) {
        seleccionada = p[0]?.id ?? null;
      }
    });
  });

  const elegida = $derived(lista.find((p) => p.id === seleccionada) ?? null);

  async function alternarAncla(p: PlaylistResumen) {
    await anclarPlaylist(p.id, !p.anclada);
    version += 1;
  }

  async function crearParaMi() {
    regenerando = true;
    try {
      await regenerarPlaylistsAutomaticas();
      version += 1;
    } finally {
      regenerando = false;
    }
  }
</script>

<section class="vista">
  <div class="principal">
    <header class="cabecera">
      <div>
        <h1>{t.titulo}</h1>
        <p class="sub">{t.subtitulo}</p>
      </div>
      <div class="acciones">
        <button type="button" class="boton" disabled={regenerando} onclick={crearParaMi}>
          <Icon nombre="reintentar" tamano={16} />{regenerando ? ti.creandoParaMi : ti.crearParaMi}
        </button>
        <button type="button" class="boton" onclick={() => (creandoInteligente = true)}>
          <Icon nombre="mas" tamano={16} />{ti.nueva}
        </button>
        <button type="button" class="boton relleno" onclick={() => (creando = true)}>
          <Icon nombre="mas" tamano={16} />{t.nueva}
        </button>
      </div>
    </header>

    <label class="busqueda">
      <Icon nombre="buscar" tamano={18} />
      <input type="search" placeholder={t.buscar} aria-label={t.buscar} bind:value={texto} />
    </label>

    <div class="fichas">
      {#each CATEGORIAS as c (c ?? 'todo')}
        <button
          type="button"
          class="ficha"
          class:activa={categoria === c}
          aria-pressed={categoria === c}
          onclick={() => (categoria = c)}
        >
          {t.categorias[c ?? 'todo']}
        </button>
      {/each}
    </div>
    <div class="fichas">
      <span class="rotulo">{textos.biblioteca.orden}</span>
      {#each ORDENES as o (o)}
        <button
          type="button"
          class="ficha"
          class:activa={orden === o}
          aria-pressed={orden === o}
          onclick={() => (orden = o)}
        >
          {t.ordenes[o]}
        </button>
      {/each}
    </div>

    <div class="fila-control">
      <span class="cuenta">{t.cuenta(lista.length)}</span>
      <div class="densidades" role="group" aria-label={t.densidad.gridMd}>
        <button
          type="button"
          class="boton-densidad"
          class:activa={modoRejilla === 'sm'}
          aria-pressed={modoRejilla === 'sm'}
          aria-label={t.densidad.gridSm}
          onclick={() => (modoRejilla = 'sm')}
        >
          <Icon nombre="cuadriculaPequena" tamano={16} />
        </button>
        <button
          type="button"
          class="boton-densidad"
          class:activa={modoRejilla === 'md'}
          aria-pressed={modoRejilla === 'md'}
          aria-label={t.densidad.gridMd}
          onclick={() => (modoRejilla = 'md')}
        >
          <Icon nombre="cuadricula" tamano={16} />
        </button>
        <button
          type="button"
          class="boton-densidad"
          class:activa={modoRejilla === 'lg'}
          aria-pressed={modoRejilla === 'lg'}
          aria-label={t.densidad.gridLg}
          onclick={() => (modoRejilla = 'lg')}
        >
          <Icon nombre="cuadriculaGrande" tamano={16} />
        </button>
        <button
          type="button"
          class="boton-densidad"
          class:activa={modoRejilla === 'lista'}
          aria-pressed={modoRejilla === 'lista'}
          aria-label={t.densidad.lista}
          onclick={() => (modoRejilla = 'lista')}
        >
          <Icon nombre="lista" tamano={16} />
        </button>
      </div>
    </div>

    <ul
      class="rejilla"
      class:sm={modoRejilla === 'sm'}
      class:md={modoRejilla === 'md'}
      class:lg={modoRejilla === 'lg'}
      class:lista={modoRejilla === 'lista'}
    >
      {#each lista as p (p.id)}
        <li>
          <button
            type="button"
            class="tarjeta"
            class:elegida={p.id === seleccionada}
            aria-pressed={p.id === seleccionada}
            onclick={() => (seleccionada = p.id)}
          >
            <Mosaico pistas={p.mosaico} />
            <span class="nombre" title={p.nombre}>{p.nombre}</span>
            <span class="detalle"
              >{p.etiqueta} · {t.resumen(p.numPistas, formatoTiempo(p.duracionSeg))}</span
            >
          </button>
        </li>
      {/each}
    </ul>
  </div>

  {#if elegida}
    <aside class="panel" aria-label={elegida.nombre}>
      <Mosaico pistas={elegida.mosaico} tamano={320} />
      <span class="etiqueta">{elegida.etiqueta}</span>
      <h2>{elegida.nombre}</h2>
      <span class="sub">{t.resumen(elegida.numPistas, formatoTiempo(elegida.duracionSeg))}</span>
      {#if elegida.descripcion}<p class="descripcion">{elegida.descripcion}</p>{/if}
      <div class="botones">
        <a class="boton" href={`/playlists/ver?id=${elegida.id}`}>
          <Icon nombre="derecha" tamano={16} />{t.abrir}
        </a>
        <button type="button" class="boton" onclick={() => elegida && alternarAncla(elegida)}>
          {elegida.anclada ? t.desanclar : t.anclar}
        </button>
        <button
          type="button"
          class="boton relleno"
          disabled={elegida.numPistas === 0}
          onclick={() => elegida && reproducirPlaylist(elegida.id, 0)}
        >
          <Icon nombre="reproducir" tamano={16} />{t.reproducir}
        </button>
      </div>
    </aside>
  {/if}
</section>

<DialogoPlaylist
  abierto={creando}
  onlisto={(id) => {
    creando = false;
    void goto(`/playlists/ver?id=${id}`);
  }}
  oncerrar={() => (creando = false)}
/>

<DialogoInteligente
  abierto={creandoInteligente}
  onlisto={(id) => {
    creandoInteligente = false;
    void goto(`/playlists/ver?id=${id}`);
  }}
  oncerrar={() => (creandoInteligente = false)}
/>

<style>
  .vista {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 22rem;
    gap: var(--ns-espacio-5);
    align-items: start;
  }

  .principal {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    min-width: 0;
  }

  .cabecera {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--ns-espacio-4);
  }

  .acciones {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ns-espacio-2);
  }

  h1 {
    margin: 0;
    font-size: var(--ns-texto-xl);
  }

  .sub,
  .detalle,
  .cuenta {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .sub {
    margin: 0;
  }

  .busqueda {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    height: 2.5rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface-variant);
  }

  .busqueda:focus-within {
    border-color: var(--m3c-primary);
  }

  .busqueda input {
    flex: 1;
    border: none;
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
  }

  .fichas {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--ns-espacio-2);
  }

  .rotulo {
    margin-right: var(--ns-espacio-2);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-weight: 600;
  }

  .ficha {
    height: 2rem;
    padding: 0 var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-xs);
    cursor: pointer;
  }

  .ficha.activa {
    border-color: var(--m3c-primary);
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
    font-weight: 700;
  }

  .fila-control {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-2);
  }

  .densidades {
    display: inline-flex;
    align-items: center;
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    overflow: hidden;
    background: var(--m3c-surface-container);
  }

  .boton-densidad {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2.25rem;
    height: 2.25rem;
    border: none;
    background: none;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
  }

  .boton-densidad:hover {
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
  }

  .boton-densidad.activa {
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
  }

  .rejilla {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(10.5rem, 1fr));
    gap: var(--ns-espacio-4);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .rejilla.sm {
    grid-template-columns: repeat(auto-fill, minmax(7.5rem, 1fr));
    gap: var(--ns-espacio-2);
  }

  .rejilla.md {
    grid-template-columns: repeat(auto-fill, minmax(10.5rem, 1fr));
    gap: var(--ns-espacio-4);
  }

  .rejilla.lg {
    grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
    gap: var(--ns-espacio-5);
  }

  .rejilla.lista {
    grid-template-columns: 1fr;
    gap: var(--ns-espacio-1);
  }

  .rejilla.lista .tarjeta {
    flex-direction: row;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-2);
  }

  .rejilla.lista .tarjeta :global(.mosaico) {
    width: 3.5rem;
    height: 3.5rem;
    flex: 0 0 3.5rem;
  }

  .tarjeta {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    width: 100%;
    padding: var(--ns-espacio-2);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-low);
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .tarjeta.elegida {
    border-color: var(--m3c-primary);
  }

  .nombre {
    font-weight: 700;
    font-size: var(--ns-texto-sm);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .detalle {
    font-size: var(--ns-texto-xs);
  }

  .panel {
    position: sticky;
    top: 0;
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    padding: var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-low);
  }

  .etiqueta {
    align-self: flex-start;
    padding: 0 var(--ns-espacio-2);
    border: 1px solid var(--m3c-primary);
    border-radius: var(--ns-radio-pleno);
    color: var(--m3c-primary);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
  }

  .descripcion {
    margin: 0;
    font-size: var(--ns-texto-sm);
  }

  .botones {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-2);
  }

  .boton {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-1);
    height: 2.5rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-sm);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    text-decoration: none;
    cursor: pointer;
  }

  .boton.relleno {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .boton:disabled {
    opacity: 0.38;
    cursor: default;
  }

  @container carcasa (max-width: 70rem) {
    .vista {
      grid-template-columns: minmax(0, 1fr);
    }

    .panel {
      display: none;
    }
  }
</style>
