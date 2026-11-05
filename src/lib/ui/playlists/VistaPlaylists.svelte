<!--
  @component
  Playlists, con la disposición de la V1 (`VistaPlaylists.qml`): título, Crear para
  mí, Nueva inteligente, Nueva playlist, la búsqueda, las categorías y los órdenes
  en fichas, la rejilla de tarjetas con su mosaico y, a la derecha, el panel de la
  seleccionada con Abrir, Anclar y Reproducir.
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import {
    anclarPlaylist,
    type Categoria,
    type OrdenPlaylists,
    type PistaResumen,
    type PlaylistResumen,
    playlistPistas,
    playlistsListar,
    reproducirPlaylist
  } from '#lib/core/ipc/index.ts';
  import { regenerarPlaylistsAutomaticas } from '#lib/core/ipc/aparte.ts';
  import { estadoPlaylists, type ModoRejilla } from '#lib/core/estadoVistas.svelte.ts';
  import { formatoTiempo } from '#lib/core/reproductor.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import { esAparte } from '#lib/i18n/es-aparte.ts';
  import Icon from '#lib/ui/Icon.svelte';
  import MenuSelector from '#lib/ui/MenuSelector.svelte';
  import DialogoInteligente from '#lib/ui/playlists/DialogoInteligente.svelte';
  import DialogoPlaylist from '#lib/ui/playlists/DialogoPlaylist.svelte';
  import Mosaico from '#lib/ui/playlists/Mosaico.svelte';

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

  let texto = $state(estadoPlaylists.busqueda);
  let categoria = $state<Categoria | null>(estadoPlaylists.categoria);
  let orden = $state<OrdenPlaylists>(estadoPlaylists.orden);
  let lista = $state<PlaylistResumen[]>([]);
  let seleccionada = $state<number | null>(estadoPlaylists.seleccionadaId);
  let creando = $state(false);
  let creandoInteligente = $state(false);
  let regenerando = $state(false);
  let version = $state(0);
  let modoRejilla = $state<ModoRejilla>(estadoPlaylists.modoRejilla);

  $effect(() => {
    estadoPlaylists.busqueda = texto;
    estadoPlaylists.categoria = categoria;
    estadoPlaylists.orden = orden;
    estadoPlaylists.seleccionadaId = seleccionada;
    estadoPlaylists.modoRejilla = modoRejilla;
  });

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

  const listaOrdenada = $derived.by(() => {
    const res = [...lista];
    res.sort((a, b) => {
      // Mis me gusta SIEMPRE de primero
      const aMeGusta = a.categoria === 'meGusta';
      const bMeGusta = b.categoria === 'meGusta';
      if (aMeGusta && !bMeGusta) return -1;
      if (!aMeGusta && bMeGusta) return 1;

      // Luego las ancladas
      if (a.anclada !== b.anclada) return a.anclada ? -1 : 1;

      return 0;
    });
    return res;
  });

  const elegida = $derived(listaOrdenada.find((p) => p.id === seleccionada) ?? null);
  let pistasAdelanto = $state<PistaResumen[]>([]);
  let cargandoPistas = $state(false);

  $effect(() => {
    const p = elegida;
    if (!p) {
      pistasAdelanto = [];
      return;
    }
    const pid = p.id;
    cargandoPistas = true;
    void playlistPistas(pid, 0, 30)
      .then((pag) => {
        if (elegida?.id === pid) {
          pistasAdelanto = pag.pistas;
        }
      })
      .catch(() => {
        if (elegida?.id === pid) {
          pistasAdelanto = [];
        }
      })
      .finally(() => {
        if (elegida?.id === pid) {
          cargandoPistas = false;
        }
      });
  });

  async function alternarAncla(p: PlaylistResumen) {
    if (p.categoria === 'meGusta') return;
    await anclarPlaylist(p.id, !p.anclada);
    version += 1;
  }

  async function crearParaMi() {
    regenerando = true;
    try {
      notificar.exito(ti.creadasParaTi(await regenerarPlaylistsAutomaticas()));
      version += 1;
    } catch {
      notificar.error(esAparte.comun.error);
    } finally {
      regenerando = false;
    }
  }
</script>

<section class="vista" class:con-panel={Boolean(elegida)}>
  <div class="principal">
    <header class="cabecera">
      <div>
        <h1>{t.titulo}</h1>
        <p class="sub">{t.subtitulo} · {t.cuenta(lista.length)}</p>
      </div>
      <div class="acciones">
        <button type="button" class="boton relleno" onclick={() => (creando = true)}>
          <Icon nombre="mas" tamano={16} />{t.nueva}
        </button>
        <button type="button" class="boton" onclick={() => (creandoInteligente = true)}>
          <Icon nombre="mas" tamano={16} />{ti.nueva}
        </button>
        <button type="button" class="boton" disabled={regenerando} onclick={crearParaMi}>
          <Icon nombre="reintentar" tamano={16} />{regenerando ? ti.creandoParaMi : ti.crearParaMi}
        </button>
      </div>
    </header>

    <div class="barra-filtros">
      <div class="filtros-izq">
        <label class="filtro-buscar">
          <Icon nombre="buscar" tamano={16} />
          <input type="search" placeholder={t.buscar} aria-label={t.buscar} bind:value={texto} />
        </label>
      </div>

      <div class="filtros-der">
        <MenuSelector
          rotulo={t.categoria}
          opciones={CATEGORIAS.map((c) => ({
            valor: c ?? 'todo',
            etiqueta: t.categorias[c ?? 'todo']
          }))}
          valor={categoria ?? 'todo'}
          onchange={(v) => (categoria = v === 'todo' ? null : (v as Categoria))}
        />

        <MenuSelector
          rotulo={textos.biblioteca.orden}
          opciones={ORDENES.map((o) => ({ valor: o, etiqueta: t.ordenes[o] }))}
          valor={orden}
          onchange={(v) => (orden = v as OrdenPlaylists)}
        />

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
    </div>

    <ul
      class="rejilla"
      class:sm={modoRejilla === 'sm'}
      class:md={modoRejilla === 'md'}
      class:lg={modoRejilla === 'lg'}
      class:lista={modoRejilla === 'lista'}
    >
      {#each listaOrdenada as p (p.id)}
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
      <div class="panel-cabecera">
        <Mosaico pistas={elegida.mosaico} tamano={320} />
        <span class="etiqueta">{elegida.etiqueta}</span>
        <h2>{elegida.nombre}</h2>
        <span class="sub">{t.resumen(elegida.numPistas, formatoTiempo(elegida.duracionSeg))}</span>
        {#if elegida.descripcion}<p class="descripcion">{elegida.descripcion}</p>{/if}
        <div class="botones">
          <button
            type="button"
            class="boton relleno"
            disabled={elegida.numPistas === 0}
            onclick={() => elegida && reproducirPlaylist(elegida.id, 0)}
          >
            <Icon nombre="reproducir" tamano={16} />{t.reproducir}
          </button>
          <div class="botones-secundarios">
            <a class="boton" href={`/playlists/ver?id=${elegida.id}`}>
              <Icon nombre="derecha" tamano={16} />{t.abrir}
            </a>
            {#if elegida.categoria !== 'meGusta'}
              <button type="button" class="boton" onclick={() => elegida && alternarAncla(elegida)}>
                {elegida.anclada ? t.desanclar : t.anclar}
              </button>
            {/if}
          </div>
        </div>
      </div>

      <div class="panel-pistas">
        <div class="pistas-encabezado">
          <span class="pistas-titulo">{textos.biblioteca.vistas.pistas}</span>
          <span class="pistas-cuenta">{elegida.numPistas}</span>
        </div>

        {#if cargandoPistas}
          <div class="pistas-cargando">
            <span>{textos.biblioteca.cargando}</span>
          </div>
        {:else if pistasAdelanto.length === 0}
          <p class="pistas-vacio">{t.vacia}</p>
        {:else}
          <ul class="lista-adelanto">
            {#each pistasAdelanto as pista, idx (pista.id)}
              <li>
                <button
                  type="button"
                  class="fila-adelanto"
                  onclick={() => elegida && reproducirPlaylist(elegida.id, idx)}
                  title={`${pista.titulo} · ${pista.artista}`}
                >
                  <span class="num">{idx + 1}</span>
                  <div class="info-pista">
                    <span class="titulo-pista">{pista.titulo}</span>
                    <span class="artista-pista">{pista.artista}</span>
                  </div>
                  <span class="duracion-pista">{formatoTiempo(pista.duracionSeg)}</span>
                </button>
              </li>
            {/each}
          </ul>
          {#if elegida.numPistas > pistasAdelanto.length}
            <a class="enlace-mas" href={`/playlists/ver?id=${elegida.id}`}>
              {t.verMasCanciones(elegida.numPistas - pistasAdelanto.length)}
            </a>
          {/if}
        {/if}
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
    grid-template-columns: 1fr;
    gap: var(--ns-espacio-4);
    height: 100%;
    min-height: 0;
    align-items: stretch;
  }

  .vista.con-panel {
    grid-template-columns: minmax(0, 1fr) 23rem;
  }

  .principal {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    min-width: 0;
    min-height: 0;
    height: 100%;
    overflow-y: auto;
    padding-right: var(--ns-espacio-2);
    padding-bottom: var(--ns-espacio-5);
  }

  .cabecera {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--ns-espacio-4);
    flex-wrap: wrap;
  }

  .acciones {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--ns-espacio-2);
  }

  h1 {
    margin: 0;
    font-size: var(--ns-texto-xl);
  }

  .sub,
  .detalle {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .sub {
    margin: 0;
  }

  .barra-filtros {
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--m3c-surface-container-low);
    padding: var(--ns-espacio-1) 0;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-3);
  }

  .filtros-izq {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    flex: 1 1 16rem;
    max-width: 32rem;
  }

  .filtros-der {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    flex-wrap: wrap;
    margin-left: auto;
  }

  .filtro-buscar {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    height: 2.125rem;
    width: 100%;
    padding: 0 var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface-variant);
    transition:
      border-color 120ms ease,
      background 120ms ease;
  }

  .filtro-buscar:focus-within {
    border-color: var(--m3c-primary);
    background: var(--m3c-surface-container-high);
  }

  .filtro-buscar input {
    flex: 1;
    width: 100%;
    border: none;
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-xs);
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
    width: 2.125rem;
    height: 2.125rem;
    border: none;
    background: none;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
    transition:
      background 120ms ease,
      color 120ms ease;
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
    gap: var(--ns-espacio-2);
    width: 100%;
    padding: var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-low);
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
    transition:
      background 140ms ease,
      border-color 140ms ease,
      box-shadow 140ms ease;
  }

  .tarjeta:hover {
    background: var(--m3c-surface-container);
    box-shadow: 0 4px 12px var(--m3c-shadow);
  }

  .tarjeta.elegida {
    border-color: var(--m3c-primary);
    background: var(--m3c-surface-container);
    box-shadow: 0 2px 8px var(--m3c-shadow);
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
    height: 100%;
    max-height: 100%;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-xl);
    background: color-mix(
      in srgb,
      var(--m3c-surface-container) 85%,
      var(--m3c-surface-container-high) 15%
    );
    box-sizing: border-box;
    box-shadow: 0 4px 20px var(--m3c-shadow);
    overflow: hidden;
  }

  .panel-cabecera {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    flex-shrink: 0;
  }

  .panel :global(.mosaico) {
    width: 100%;
    max-width: 8rem;
    margin: 0 auto;
    aspect-ratio: 1;
    border-radius: var(--ns-radio-lg);
    overflow: hidden;
    box-shadow: 0 6px 20px var(--m3c-shadow);
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
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .descripcion {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    line-height: 1.35;
  }

  .botones {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-1);
  }

  .botones-secundarios {
    display: flex;
    gap: var(--ns-espacio-2);
  }

  .botones-secundarios > :global(*) {
    flex: 1 1 0;
    text-align: center;
    justify-content: center;
  }

  .panel-pistas {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    border-top: 1px solid var(--m3c-outline-variant);
    padding-top: var(--ns-espacio-3);
    overflow-y: auto;
  }

  .pistas-encabezado {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--m3c-on-surface-variant);
  }

  .pistas-cargando,
  .pistas-vacio {
    margin: var(--ns-espacio-3) 0;
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
    text-align: center;
  }

  .lista-adelanto {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .fila-adelanto {
    width: 100%;
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    padding: var(--ns-espacio-1) var(--ns-espacio-2);
    border: none;
    border-radius: var(--ns-radio-sm);
    background: transparent;
    color: var(--m3c-on-surface);
    font: inherit;
    text-align: left;
    cursor: pointer;
    transition: background 120ms ease;
  }

  .fila-adelanto:hover {
    background: var(--m3c-surface-container-high);
  }

  .fila-adelanto .num {
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
    width: 1.25rem;
    text-align: center;
    flex-shrink: 0;
  }

  .info-pista {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  .titulo-pista {
    font-size: var(--ns-texto-xs);
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .artista-pista {
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .duracion-pista {
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
  }

  .enlace-mas {
    display: inline-block;
    padding: var(--ns-espacio-2);
    font-size: var(--ns-texto-xs);
    color: var(--m3c-primary);
    text-decoration: none;
    text-align: center;
  }

  .enlace-mas:hover {
    text-decoration: underline;
  }

  .boton {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--ns-espacio-2);
    height: 2.5rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    text-decoration: none;
    cursor: pointer;
    transition: background-color var(--ns-duracion-corta) var(--ns-curva);
  }

  .boton:hover:not(:disabled) {
    background: var(--m3c-surface-container-high);
  }

  .boton.relleno {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .boton.relleno:hover:not(:disabled) {
    background: var(--m3c-primary);
    filter: brightness(1.1);
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
