<!--
  El detalle de un álbum: la portada grande, título, artista, año y duración, Reproducir, Aleatorio y Editar datos (F4.2.5),
  y sus canciones en orden.
-->
<script lang="ts">
  import { cambios } from '#lib/core/cambios.svelte.ts';
  import { encolar } from '#lib/core/acciones.svelte.ts';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import {
    type AlbumResumen,
    bibliotecaAlbum,
    bibliotecaAlbumes,
    bibliotecaPistas,
    type ConsultaPistas,
    type PistaResumen,
    reproducirLista,
    urlPortada
  } from '#lib/core/ipc/index.ts';
  import { recordado, type PaginaPistas } from '#lib/core/ipc/index.ts';
  import { formatoTiempo, reproductor } from '#lib/core/reproductor.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import CabeceraPistas from '#lib/ui/biblioteca/CabeceraPistas.svelte';
  import FilaPista from '#lib/ui/biblioteca/FilaPista.svelte';
  import AccionesColeccion from '#lib/ui/AccionesColeccion.svelte';
  import { ambiente } from '#lib/ui/ambiente.ts';
  import Icon from '#lib/ui/Icon.svelte';
  import type { Accion } from '#lib/ui/MenuAcciones.svelte';

  const t = textos.biblioteca;
  const id = $derived(Number(page.url.searchParams.get('id')));

  let album = $state<AlbumResumen | null | undefined>(undefined);
  let pistas = $state<PistaResumen[]>([]);
  let otrosAlbumes = $state<AlbumResumen[]>([]);
  let editando = $state(false);
  // Editar el álbum o una de sus pistas los cambia en la base: se vuelven a pedir.
  let recargas = $state(0);

  const consulta = $derived<ConsultaPistas>({
    texto: null,
    favoritas: false,
    sinVerificar: false,
    albumId: id,
    artistaId: null,
    orden: 'albumAsc'
  });

  $effect(() => {
    const c = consulta;
    void recargas;
    void cambios.version;
    if (!Number.isFinite(id) || id <= 0) {
      album = null;
      return;
    }
    // Lo de la última visita, al instante; lo nuevo lo sustituye al llegar.
    if (album?.id !== id) {
      album = recordado<AlbumResumen | null>('biblioteca_album', { id });
      pistas =
        recordado<PaginaPistas>('biblioteca_pistas', { consulta: c, desde: 0, limite: 500 })
          ?.pistas ?? [];
    }
    void bibliotecaAlbum(id).then((a) => {
      album = a;
      if (a && a.artistaId) {
        void bibliotecaAlbumes(
          { texto: null, artistaId: a.artistaId, orden: 'recientes' },
          0,
          8
        ).then((resp) => {
          otrosAlbumes = resp.albumes.filter((x) => x.id !== id);
        });
      } else {
        otrosAlbumes = [];
      }
    });
    void bibliotecaPistas(c, 0, 500).then((p) => (pistas = p.pistas));
  });

  const acciones = $derived<Accion[]>([
    {
      texto: t.anadirACola,
      icono: 'cola',
      accion: () =>
        encolar(
          pistas.map((p) => p.id),
          false
        ),
      deshabilitada: pistas.length === 0
    },
    ...(album?.artistaId
      ? [
          {
            texto: t.abrirArtista,
            icono: 'artista' as const,
            accion: () => goto(`/biblioteca/artista?id=${album?.artistaId}`)
          }
        ]
      : []),
    { texto: t.editarDatos, icono: 'editar', accion: () => (editando = true), separada: true }
  ]);

  function aleatorio() {
    if (!reproductor.instantanea.aleatorio) void reproductor.alternarAleatorio();
    void reproducirLista(consulta, Math.floor(Math.random() * pistas.length));
  }
</script>

<section class="detalle">
  <header class="franja" use:ambiente={pistas[0]?.id ?? null}>
    <button
      type="button"
      class="volver"
      onclick={() => {
        if (typeof window !== 'undefined' && window.history.length > 1) {
          window.history.back();
        } else {
          void goto('/biblioteca?vista=albumes');
        }
      }}
      title={t.album.volver}
    >
      <Icon nombre="atras" tamano={18} />
      <span>{t.album.volver}</span>
    </button>
    {#if album}
      <div class="cabecera">
        <div class="portada">
          {#if album.tienePortada}
            <img src={urlPortada('album', album.id, 640)} alt="" />
          {:else}
            <Icon nombre="album" tamano={64} />
          {/if}
        </div>
        <div class="datos">
          <span class="tipo">{t.tipos[album.tipo as keyof typeof t.tipos] ?? album.tipo}</span>
          <h1>{album.titulo}</h1>
          <p class="sub">
            {#if album.artistaId}
              <a class="artista" href={`/biblioteca/artista?id=${album.artistaId}`}
                >{album.artista}</a
              >
            {:else}
              <span class="artista">{album.artista}</span>
            {/if}
            {#each [album.anio ?? '', t.album.pistas(album.numPistas, formatoTiempo(album.duracionSeg))].filter((x) => x !== '') as dato (dato)}
              <span aria-hidden="true">·</span><span>{dato}</span>
            {/each}
          </p>
        </div>
      </div>
    {/if}
  </header>

  {#if album === null}
    <p class="vacio">{t.album.noEncontrado}</p>
  {:else if album}
    <AccionesColeccion
      vacia={pistas.length === 0}
      onreproducir={() => reproducirLista(consulta, 0)}
      onaleatorio={aleatorio}
      {acciones}
    />

    <CabeceraPistas contexto="album" />
    <ul class="pistas" aria-label={t.lista}>
      {#each pistas as p, i (p.id)}
        <li>
          <FilaPista
            contexto="album"
            pista={p}
            numero={i + 1}
            sonando={reproductor.instantanea.pistaId === p.id}
            onreproducir={() => reproducirLista(consulta, i)}
            oncambiada={() => recargas++}
          />
        </li>
      {/each}
    </ul>

    {#if otrosAlbumes.length > 0}
      <section class="mas-artista" aria-labelledby="t-mas-artista">
        <h2 id="t-mas-artista">{t.album.masDe(album.artista)}</h2>
        <div class="rejilla-otros">
          {#each otrosAlbumes as o (o.id)}
            <a class="tarjeta-otro" href={`/biblioteca/album?id=${o.id}`}>
              <div class="mini-portada-otro">
                {#if o.tienePortada}
                  <img src={urlPortada('album', o.id, 240)} alt="" />
                {:else}
                  <Icon nombre="album" tamano={32} />
                {/if}
              </div>
              <strong class="otro-titulo">{o.titulo}</strong>
              <span class="otro-anio">{o.anio ?? ''}</span>
            </a>
          {/each}
        </div>
      </section>
    {/if}
  {/if}
  {#if editando}
    {#await import('#lib/ui/edicion/DialogoEditar.svelte') then m}
      <m.default
        tipo="album"
        {id}
        oncerrar={() => (editando = false)}
        onguardado={(nuevo) => {
          editando = false;
          // Si se juntó con otro álbum, este ya no existe: se va al resultante.
          if (nuevo !== id) void goto(`/biblioteca/album?id=${nuevo}`);
          else recargas++;
        }}
      />
    {/await}
  {/if}
</section>

<style>
  .detalle {
    /* El fondo del lienzo, resuelto aquí: dentro de la franja los tokens son los de
       la portada, y el degradado tiene que acabar en el color de fuera. */
    --fondo-lienzo: var(--m3c-surface-container-low);
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
  }

  .franja {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
    margin: calc(-1 * var(--ns-espacio-2)) calc(-1 * var(--ns-espacio-5)) 0;
    padding: var(--ns-espacio-4) var(--ns-espacio-5) var(--ns-espacio-5);
    background: linear-gradient(
      180deg,
      color-mix(in srgb, var(--m3c-primary-container) 70%, var(--fondo-lienzo)) 0%,
      var(--fondo-lienzo) 100%
    );
    color: var(--m3c-on-surface);
  }

  .volver {
    display: inline-flex;
    align-self: flex-start;
    align-items: center;
    gap: var(--ns-espacio-2);
    padding: 0;
    border: none;
    background: none;
    color: var(--m3c-on-surface-variant);
    font: inherit;
    font-size: var(--ns-texto-sm);
    cursor: pointer;
    transition: color var(--ns-duracion-corta) var(--ns-curva);
  }

  .volver:hover {
    color: var(--m3c-on-surface);
  }

  .cabecera {
    display: flex;
    align-items: flex-end;
    gap: var(--ns-espacio-5);
  }

  .portada {
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    width: 14rem;
    height: 14rem;
    overflow: hidden;
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
    box-shadow: 0 12px 32px var(--m3c-shadow);
  }

  .portada img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .datos {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    min-width: 0;
  }

  .tipo {
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  h1 {
    margin: 0;
    font-size: clamp(var(--ns-texto-2xl), 4.5vw, var(--ns-texto-4xl));
    line-height: 1.02;
    overflow-wrap: anywhere;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .sub {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--ns-espacio-2);
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .artista {
    color: var(--m3c-on-surface);
    font-weight: 700;
    text-decoration: none;
  }

  a.artista:hover {
    text-decoration: underline;
  }

  .pistas {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .pistas li {
    height: 3.5rem;
  }

  .vacio {
    color: var(--m3c-on-surface-variant);
  }

  .mas-artista {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    margin-top: var(--ns-espacio-6);
    padding-top: var(--ns-espacio-5);
    border-top: 1px solid var(--m3c-outline-variant);
  }

  .mas-artista h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
  }

  .rejilla-otros {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(8.5rem, 1fr));
    gap: var(--ns-espacio-3);
  }

  .tarjeta-otro {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    padding: var(--ns-espacio-2);
    border-radius: var(--ns-radio-md);
    text-decoration: none;
    color: var(--m3c-on-surface);
    transition: background var(--ns-duracion-corta) var(--ns-curva);
  }

  .tarjeta-otro:hover {
    background: var(--m3c-surface-container-high);
  }

  .mini-portada-otro {
    aspect-ratio: 1;
    display: grid;
    place-items: center;
    border-radius: var(--ns-radio-sm);
    overflow: hidden;
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
  }

  .mini-portada-otro img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .otro-titulo {
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .otro-anio {
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
  }
</style>
