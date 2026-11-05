<!--
  Los resultados de la búsqueda global. De la V1 (`VistaBusqueda.qml`) quedan las
  secciones con su cuenta y las pistas por relevancia (el título pesa más que la
  letra); arriba, el mejor resultado junto a las primeras canciones, y artistas,
  álbumes y playlists en rejilla con su imagen, que es como se reconocen. Si la
  búsqueda expresa una intención ("algo triste"), sus secciones van primero
  (F5.3.3).

  Escape y la equis de la caja cierran la búsqueda desde la barra superior; la
  página escuchaba Escape también y volvía atrás dos veces.
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import {
    type AlbumResumen,
    type ArtistaResumen,
    bibliotecaAlbumes,
    bibliotecaArtistas,
    bibliotecaPistas,
    type ConsultaPistas,
    type PistaResumen,
    type PlaylistResumen,
    playlistsListar,
    reproducirLista,
    urlPortada
  } from '#lib/core/ipc/index.ts';
  import { reproductor } from '#lib/core/reproductor.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import CabeceraPistas from '#lib/ui/biblioteca/CabeceraPistas.svelte';
  import FilaPista from '#lib/ui/biblioteca/FilaPista.svelte';
  import Icon from '#lib/ui/Icon.svelte';
  import Mosaico from '#lib/ui/playlists/Mosaico.svelte';

  const t = textos.busqueda;
  const q = $derived((page.url.searchParams.get('q') ?? '').trim());

  let artistas = $state<ArtistaResumen[]>([]);
  let totalArtistas = $state(0);
  let albumes = $state<AlbumResumen[]>([]);
  let totalAlbumes = $state(0);
  let pistas = $state<PistaResumen[]>([]);
  let totalPistas = $state(0);
  let playlists = $state<PlaylistResumen[]>([]);
  let listo = $state(false);
  let descubiertas = $state(false);

  const consulta = $derived<ConsultaPistas>({
    texto: q,
    favoritas: false,
    sinVerificar: false,
    albumId: null,
    artistaId: null,
    orden: 'relevancia'
  });

  let version = 0;
  $effect(() => {
    const texto = q;
    const c = consulta;
    const v = ++version;
    listo = false;
    descubiertas = false;
    if (!texto) return;
    void Promise.all([
      bibliotecaArtistas({ texto, orden: 'masPistas' }, 0, 8),
      bibliotecaAlbumes({ texto, artistaId: null, orden: 'tituloAsc' }, 0, 12),
      bibliotecaPistas(c, 0, 50),
      playlistsListar({ texto, categoria: null, orden: 'nombreAsc' })
    ]).then(([ar, al, pi, pl]) => {
      if (v !== version) return;
      artistas = ar.artistas;
      totalArtistas = ar.total;
      albumes = al.albumes;
      totalAlbumes = al.total;
      pistas = pi.pistas;
      totalPistas = pi.total;
      playlists = pl.slice(0, 8);
      listo = true;
    });
  });

  const nada = $derived(
    listo && totalArtistas + totalAlbumes + totalPistas + playlists.length === 0
  );

  const igual = (a: string) => a.trim().toLocaleLowerCase('es') === q.toLocaleLowerCase('es');

  /** Lo que se buscaba con más probabilidad: lo que se llama exactamente así, o lo primero. */
  type Mejor =
    | { tipo: 'artista'; a: ArtistaResumen }
    | { tipo: 'album'; a: AlbumResumen }
    | { tipo: 'pista'; p: PistaResumen; i: number };
  const mejor = $derived.by<Mejor | null>(() => {
    const artista = artistas.find((a) => igual(a.nombre));
    if (artista) return { tipo: 'artista', a: artista };
    // La canción antes que el álbum: un sencillo se llama como su canción, y las
    // pistas ya vienen por relevancia (la más escuchada de las que se llaman así).
    const i = pistas.findIndex((p) => igual(p.titulo));
    if (i >= 0 && pistas[i]) return { tipo: 'pista', p: pistas[i], i };
    const album = albumes.find((a) => igual(a.titulo));
    if (album) return { tipo: 'album', a: album };
    if (artistas[0]) return { tipo: 'artista', a: artistas[0] };
    if (albumes[0]) return { tipo: 'album', a: albumes[0] };
    if (pistas[0]) return { tipo: 'pista', p: pistas[0], i: 0 };
    return null;
  });
</script>

{#snippet fila(p: PistaResumen, i: number)}
  <li>
    <FilaPista
      pista={p}
      numero={i + 1}
      sonando={reproductor.instantanea.pistaId === p.id}
      onreproducir={() => reproducirLista(consulta, i)}
      oncambiada={() => {
        version += 1;
      }}
    />
  </li>
{/snippet}

<section class="vista">
  {#if q}
    <h1>{t.resultados(q)}</h1>
    {#await import('#lib/ui/descubrir/SeccionesDescubrir.svelte') then m}
      <m.default consulta={q} onresultado={(si) => (descubiertas = si)} />
    {/await}
  {/if}

  {#if !q}
    {#await import('#lib/ui/buscar/BienvenidaBuscar.svelte') then m}
      <m.default onseleccionar={(idea) => goto(`/buscar?q=${encodeURIComponent(idea)}`)} />
    {/await}
  {:else if nada && !descubiertas}
    <div class="vacio">
      <Icon nombre="buscar" tamano={32} />
      <p class="vacio-titulo">{t.sinResultados(q)}</p>
      <p>{t.sinResultadosSub}</p>
    </div>
  {:else if listo}
    {#if mejor}
      <div class="arriba">
        <section class="mejor" aria-labelledby="t-mejor">
          <h2 id="t-mejor" class="seccion">{t.mejor}</h2>
          {#if mejor.tipo === 'artista'}
            {@const a = mejor.a}
            <a class="tarjeta-mejor" href={`/biblioteca/artista?id=${a.id}`}>
              <span class="imagen-mejor redonda">
                {#if a.tieneImagen}<img src={urlPortada('artista', a.id, 240)} alt="" />{:else}<Icon
                    nombre="artista"
                    tamano={40}
                  />{/if}
              </span>
              <strong>{a.nombre}</strong>
              <span class="tipo">{t.tipoArtista}</span>
            </a>
          {:else if mejor.tipo === 'album'}
            {@const a = mejor.a}
            <a class="tarjeta-mejor" href={`/biblioteca/album?id=${a.id}`}>
              <span class="imagen-mejor">
                {#if a.tienePortada}<img src={urlPortada('album', a.id, 240)} alt="" />{:else}<Icon
                    nombre="album"
                    tamano={40}
                  />{/if}
              </span>
              <strong>{a.titulo}</strong>
              <span class="tipo">{t.tipoAlbum} · {a.artista}</span>
            </a>
          {:else}
            {@const p = mejor.p}
            {@const i = mejor.i}
            <button
              type="button"
              class="tarjeta-mejor"
              onclick={() => reproducirLista(consulta, i)}
            >
              <span class="imagen-mejor">
                {#if p.tienePortada}<img src={urlPortada('pista', p.id, 240)} alt="" />{:else}<Icon
                    nombre="cancion"
                    tamano={40}
                  />{/if}
              </span>
              <strong>{p.titulo}</strong>
              <span class="tipo">{t.tipoCancion} · {p.artista}</span>
            </button>
          {/if}
        </section>
        {#if pistas.length > 0}
          <section class="primeras" aria-labelledby="t-canciones">
            <h2 id="t-canciones" class="seccion">{t.canciones}</h2>
            <ul class="lista-pistas">
              {#each pistas.slice(0, 4) as p, i (p.id)}
                {@render fila(p, i)}
              {/each}
            </ul>
          </section>
        {/if}
      </div>
    {/if}

    {#if artistas.length > 0}
      <h2 class="seccion">{t.artistas}<span class="cuenta">{totalArtistas}</span></h2>
      <ul class="rejilla">
        {#each artistas as a (a.id)}
          <li>
            <a class="tarjeta centrada" href={`/biblioteca/artista?id=${a.id}`}>
              <span class="imagen redonda">
                {#if a.tieneImagen}<img
                    src={urlPortada('artista', a.id, 240)}
                    alt=""
                    loading="lazy"
                  />{:else}<Icon nombre="artista" tamano={32} />{/if}
              </span>
              <span class="nombre">{a.nombre}</span>
              <span class="sub">{textos.biblioteca.artista.resumen(a.numAlbumes, a.numPistas)}</span
              >
            </a>
          </li>
        {/each}
      </ul>
    {/if}

    {#if albumes.length > 0}
      <h2 class="seccion">{t.albumes}<span class="cuenta">{totalAlbumes}</span></h2>
      <ul class="rejilla">
        {#each albumes as a (a.id)}
          <li>
            <a class="tarjeta" href={`/biblioteca/album?id=${a.id}`}>
              <span class="imagen">
                {#if a.tienePortada}<img
                    src={urlPortada('album', a.id, 240)}
                    alt=""
                    loading="lazy"
                  />{:else}<Icon nombre="album" tamano={32} />{/if}
              </span>
              <span class="nombre">{a.titulo}</span>
              <span class="sub"
                >{[a.anio ?? '', a.artista].filter((x) => x !== '').join(' · ')}</span
              >
            </a>
          </li>
        {/each}
      </ul>
    {/if}

    {#if playlists.length > 0}
      <h2 class="seccion">{t.playlists}<span class="cuenta">{playlists.length}</span></h2>
      <ul class="rejilla">
        {#each playlists as p (p.id)}
          <li>
            <a class="tarjeta" href={`/playlists/ver?id=${p.id}`}>
              <span class="imagen"><Mosaico pistas={p.mosaico} tamano={240} /></span>
              <span class="nombre">{p.nombre}</span>
              <span class="sub">{p.etiqueta} · {textos.biblioteca.cuentaPistas(p.numPistas)}</span>
            </a>
          </li>
        {/each}
      </ul>
    {/if}

    {#if pistas.length > 4}
      <h2 class="seccion">{t.todas}<span class="cuenta">{totalPistas}</span></h2>
      <CabeceraPistas />
      <ul class="lista-pistas">
        {#each pistas as p, i (p.id)}
          {@render fila(p, i)}
        {/each}
      </ul>
    {/if}
  {/if}
</section>

<style>
  .vista {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    padding-top: var(--ns-espacio-3);
  }

  h1 {
    margin: 0;
    font-size: var(--ns-texto-xl);
    overflow-wrap: anywhere;
  }

  .seccion {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    margin: var(--ns-espacio-4) 0 0;
    font-size: var(--ns-texto-lg);
  }

  .cuenta {
    min-width: 1.5rem;
    padding: 0 var(--ns-espacio-2);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-weight: 600;
    text-align: center;
  }

  .arriba {
    display: grid;
    grid-template-columns: minmax(16rem, 2fr) minmax(0, 3fr);
    gap: var(--ns-espacio-5);
  }

  .mejor,
  .primeras {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    min-width: 0;
  }

  .tarjeta-mejor {
    display: flex;
    flex: 1;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--ns-espacio-2);
    padding: var(--ns-espacio-5);
    border: none;
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    text-align: left;
    text-decoration: none;
    cursor: pointer;
    transition: background var(--ns-duracion-corta) var(--ns-curva);
  }

  .tarjeta-mejor:hover {
    background: var(--m3c-surface-container-high);
  }

  .imagen-mejor {
    display: grid;
    place-items: center;
    width: 6.5rem;
    height: 6.5rem;
    margin-bottom: var(--ns-espacio-2);
    overflow: hidden;
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
    box-shadow: 0 8px 20px var(--m3c-shadow);
  }

  .tarjeta-mejor strong {
    max-width: 100%;
    overflow: hidden;
    font-size: var(--ns-texto-2xl);
    line-height: 1.1;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .tipo {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .lista-pistas {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .lista-pistas li {
    height: 3.5rem;
  }

  .rejilla {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr));
    gap: var(--ns-espacio-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .tarjeta {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    padding: var(--ns-espacio-2);
    border-radius: var(--ns-radio-md);
    color: var(--m3c-on-surface);
    text-decoration: none;
    transition: background var(--ns-duracion-corta) var(--ns-curva);
  }

  .tarjeta:hover {
    background: var(--m3c-surface-container);
  }

  .tarjeta.centrada {
    align-items: center;
    text-align: center;
  }

  .imagen {
    display: grid;
    place-items: center;
    width: 100%;
    aspect-ratio: 1;
    margin-bottom: var(--ns-espacio-1);
    overflow: hidden;
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
    box-shadow: 0 4px 14px var(--m3c-shadow);
  }

  .redonda {
    border-radius: var(--ns-radio-pleno);
  }

  .imagen img,
  .imagen-mejor img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .nombre,
  .sub {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .nombre {
    font-size: var(--ns-texto-sm);
    font-weight: 700;
  }

  .sub {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .vacio {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-7);
    color: var(--m3c-on-surface-variant);
    text-align: center;
  }

  .vacio p {
    margin: 0;
    font-size: var(--ns-texto-sm);
  }

  .vacio .vacio-titulo {
    color: var(--m3c-on-surface);
    font-size: var(--ns-texto-md);
    font-weight: 700;
  }

  @container carcasa (max-width: 60rem) {
    .arriba {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
