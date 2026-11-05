<!--
  El detalle de un artista: su imagen y cifras, las más escuchadas, sus álbumes y
  sus sencillos por separado, y todas sus canciones, como en la V1 (que exponía
  todas las pistas y no solo las destacadas). Las canciones van en la ventana
  virtual, porque un artista puede tener cientos.
-->
<script lang="ts">
  import { cambios } from '#lib/core/cambios.svelte.ts';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import {
    type AlbumResumen,
    type ArtistaResumen,
    bibliotecaAlbumes,
    bibliotecaArtista,
    bibliotecaPistas,
    type ConsultaPistas,
    type PistaResumen,
    reproducirLista,
    urlPortada
  } from '#lib/core/ipc/index.ts';
  import { recordado, type PaginaAlbumes, type PaginaPistas } from '#lib/core/ipc/index.ts';
  import { reproductor } from '#lib/core/reproductor.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import FilaPista from '#lib/ui/biblioteca/FilaPista.svelte';
  import AccionesColeccion from '#lib/ui/AccionesColeccion.svelte';
  import { ambiente } from '#lib/ui/ambiente.ts';
  import Icon from '#lib/ui/Icon.svelte';
  import ListaVirtual from '#lib/ui/lista/ListaVirtual.svelte';
  import { TAM_BLOQUE } from '#lib/ui/lista/ventana.ts';

  const t = textos.biblioteca;
  const id = $derived(Number(page.url.searchParams.get('id')));

  let artista = $state<ArtistaResumen | null | undefined>(undefined);
  let albumes = $state<AlbumResumen[]>([]);
  let total = $state(0);
  let populares = $state<PistaResumen[]>([]);
  let todasLasPopulares = $state(false);

  // `tipo` es el de MusicBrainz: lo que no es un álbum va con los sencillos.
  const discos = $derived(albumes.filter((a) => a.tipo === 'Album'));
  const sencillos = $derived(albumes.filter((a) => a.tipo !== 'Album'));

  const consulta = $derived<ConsultaPistas>({
    texto: null,
    favoritas: false,
    sinVerificar: false,
    albumId: null,
    artistaId: id,
    orden: 'masReproducidas'
  });

  $effect(() => {
    const c = consulta;
    void cambios.version;
    if (!Number.isFinite(id) || id <= 0) {
      artista = null;
      return;
    }
    // Lo de la última visita, al instante; lo nuevo lo sustituye al llegar.
    if (artista?.id !== id) {
      artista = recordado<ArtistaResumen | null>('biblioteca_artista', { id });
      albumes =
        recordado<PaginaAlbumes>('biblioteca_albumes', {
          consulta: { texto: null, artistaId: id, orden: 'anioDesc' },
          desde: 0,
          limite: 200
        })?.albumes ?? [];
      const p = recordado<PaginaPistas>('biblioteca_pistas', { consulta: c, desde: 0, limite: 10 });
      total = p?.total ?? 0;
      populares = p?.pistas ?? [];
    }
    void bibliotecaArtista(id).then((a) => (artista = a));
    void bibliotecaAlbumes({ texto: null, artistaId: id, orden: 'anioDesc' }, 0, 200).then(
      (p) => (albumes = p.albumes)
    );
    todasLasPopulares = false;
    void bibliotecaPistas(c, 0, 10).then((p) => {
      total = p.total;
      populares = p.pistas;
    });
  });

  async function aleatorio() {
    if (!reproductor.instantanea.aleatorio) await reproductor.alternarAleatorio();
    await reproducirLista(consulta, Math.floor(Math.random() * Math.max(1, total)));
  }

  async function cargarBloque(b: number): Promise<PistaResumen[]> {
    return (await bibliotecaPistas(consulta, b * TAM_BLOQUE, TAM_BLOQUE)).pistas;
  }
</script>

{#snippet rejilla(lista: AlbumResumen[], titulo: string, idTitulo: string)}
  {#if lista.length > 0}
    <section class="seccion" aria-labelledby={idTitulo}>
      <h2 id={idTitulo}>{titulo}</h2>
      <ul class="rejilla">
        {#each lista as a (a.id)}
          <li>
            <a class="tarjeta" href={`/biblioteca/album?id=${a.id}`}>
              <span class="caratula">
                {#if a.tienePortada}
                  <img
                    src={urlPortada('album', a.id, 320)}
                    alt=""
                    loading="lazy"
                    decoding="async"
                  />
                {:else}
                  <Icon nombre="album" tamano={40} />
                {/if}
              </span>
              <span class="nombre" title={a.titulo}>{a.titulo}</span>
              <span class="sub">{a.anio ?? ''}</span>
            </a>
          </li>
        {/each}
      </ul>
    </section>
  {/if}
{/snippet}

<section class="detalle">
  <header class="franja" use:ambiente={populares[0]?.id ?? null}>
    <button
      type="button"
      class="volver"
      onclick={() => {
        if (typeof window !== 'undefined' && window.history.length > 1) {
          window.history.back();
        } else {
          void goto('/biblioteca?vista=artistas');
        }
      }}
      title={t.album.volver}
    >
      <Icon nombre="atras" tamano={18} />
      <span>{t.album.volver}</span>
    </button>
    {#if artista}
      <div class="cabecera">
        <div class="imagen">
          {#if artista.tieneImagen}
            <img src={urlPortada('artista', artista.id, 320)} alt="" />
          {:else}
            <Icon nombre="artista" tamano={56} />
          {/if}
        </div>
        <div class="datos">
          <span class="tipo">{t.artista.tipo}</span>
          <h1>{artista.nombre}</h1>
          <span class="sub">{t.artista.resumen(artista.numAlbumes, artista.numPistas)}</span>
        </div>
      </div>
    {/if}
  </header>

  {#if artista === null}
    <p class="vacio">{t.artista.noEncontrado}</p>
  {:else if artista}
    <AccionesColeccion
      vacia={total === 0}
      onreproducir={() => reproducirLista(consulta, 0)}
      onaleatorio={aleatorio}
    />

    {#if populares.length > 0}
      <section class="seccion" aria-labelledby="t-populares">
        <h2 id="t-populares">{t.artista.populares}</h2>
        <ul class="populares">
          {#each todasLasPopulares ? populares : populares.slice(0, 5) as p, i (p.id)}
            <li>
              <FilaPista
                contexto="artista"
                numerada
                pista={p}
                numero={i + 1}
                sonando={reproductor.instantanea.pistaId === p.id}
                onreproducir={() => reproducirLista(consulta, i)}
              />
            </li>
          {/each}
        </ul>
        {#if populares.length > 5}
          <button
            type="button"
            class="mas"
            onclick={() => (todasLasPopulares = !todasLasPopulares)}
          >
            {todasLasPopulares ? t.artista.mostrarMenos : t.artista.mostrarMas}
          </button>
        {/if}
      </section>
    {/if}

    {@render rejilla(discos, t.artista.albumes, 't-albumes-artista')}
    {@render rejilla(sencillos, t.artista.sencillos, 't-sencillos-artista')}

    <h2>{t.artista.canciones}</h2>
    {#if total > 0}
      <div class="lista">
        {#key id}
          <ListaVirtual {total} altoFila={56} {cargarBloque} etiqueta={t.artista.canciones}>
            {#snippet fila(p: PistaResumen, i: number, rapido: boolean)}
              <FilaPista
                contexto="artista"
                pista={p}
                numero={i + 1}
                {rapido}
                sonando={reproductor.instantanea.pistaId === p.id}
                onreproducir={() => reproducirLista(consulta, i)}
              />
            {/snippet}
          </ListaVirtual>
        {/key}
      </div>
    {/if}
  {/if}
</section>

<style>
  .detalle {
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

  .imagen {
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    width: 13rem;
    height: 13rem;
    overflow: hidden;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
    box-shadow: 0 12px 32px var(--m3c-shadow);
  }

  .imagen img {
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
    font-size: clamp(var(--ns-texto-2xl), 5vw, var(--ns-texto-4xl));
    line-height: 1.02;
    overflow-wrap: anywhere;
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
  }

  .sub {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .seccion {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    margin-top: var(--ns-espacio-2);
  }

  .populares {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .populares li {
    height: 3.5rem;
  }

  .mas {
    align-self: flex-start;
    padding: var(--ns-espacio-1) var(--ns-espacio-3);
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface-variant);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 700;
    cursor: pointer;
  }

  .mas:hover {
    color: var(--m3c-on-surface);
  }

  .rejilla {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr));
    gap: var(--ns-espacio-4);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .tarjeta {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    color: inherit;
    text-decoration: none;
  }

  .caratula {
    display: grid;
    place-items: center;
    aspect-ratio: 1;
    overflow: hidden;
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
  }

  .caratula img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .nombre {
    font-weight: 700;
    font-size: var(--ns-texto-sm);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .lista {
    height: 60vh;
  }

  .vacio {
    color: var(--m3c-on-surface-variant);
  }
</style>
