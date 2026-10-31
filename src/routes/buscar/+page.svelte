<!--
  Los resultados de la búsqueda global, con la disposición de la V1
  (`VistaBusqueda.qml`): secciones de Artistas, Álbumes y Pistas con su cuenta, y
  cada resultado con su imagen, su resumen y la flecha para abrirlo. Las pistas
  van por relevancia (el título pesa más que la letra) y se reproducen desde la
  elegida. Si la búsqueda expresa una intención ("algo triste"), sus secciones van
  primero (F5.3.3).
-->
<script lang="ts">
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
  } from '$core/ipc';
  import { formatoTiempo, reproductor } from '$core/reproductor.svelte';
  import { textos } from '$lib/i18n';
  import Icon from '$ui/Icon.svelte';
  import Mosaico from '$ui/playlists/Mosaico.svelte';

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
</script>

<section class="vista">
  <header class="tarjeta-titulo">
    <h1>{t.titulo}</h1>
    <p>{t.subtitulo}</p>
  </header>

  {#if q}
    {#await import('$ui/descubrir/SeccionesDescubrir.svelte') then m}
      <m.default consulta={q} />
    {/await}
  {/if}

  {#if !q}
    <p class="vacio">{t.escribe}</p>
  {:else if nada}
    <p class="vacio">{t.sinResultados(q)}</p>
  {:else}
    {#if artistas.length > 0}
      <h2 class="seccion">{t.artistas}<span class="cuenta">{totalArtistas}</span></h2>
      <ul class="resultados">
        {#each artistas as a (a.id)}
          <li>
            <a class="resultado" href={`/biblioteca/artista?id=${a.id}`}>
              <span class="imagen redonda">
                {#if a.tieneImagen}<img src={urlPortada('artista', a.id, 64)} alt="" />{:else}<Icon
                    nombre="artista"
                    tamano={20}
                  />{/if}
              </span>
              <span class="datos">
                <span class="nombre">{a.nombre}</span>
                <span class="sub"
                  >{textos.biblioteca.artista.resumen(a.numAlbumes, a.numPistas)}</span
                >
              </span>
              <Icon nombre="derecha" tamano={18} />
            </a>
          </li>
        {/each}
      </ul>
    {/if}

    {#if albumes.length > 0}
      <h2 class="seccion">{t.albumes}<span class="cuenta">{totalAlbumes}</span></h2>
      <ul class="resultados">
        {#each albumes as a (a.id)}
          <li>
            <a class="resultado" href={`/biblioteca/album?id=${a.id}`}>
              <span class="imagen">
                {#if a.tienePortada}<img src={urlPortada('album', a.id, 64)} alt="" />{:else}<Icon
                    nombre="album"
                    tamano={20}
                  />{/if}
              </span>
              <span class="datos">
                <span class="nombre">{a.titulo}</span>
                <span class="sub">{a.artista} · {textos.biblioteca.cuentaPistas(a.numPistas)}</span>
              </span>
              <Icon nombre="derecha" tamano={18} />
            </a>
          </li>
        {/each}
      </ul>
    {/if}

    {#if playlists.length > 0}
      <h2 class="seccion">{t.playlists}<span class="cuenta">{playlists.length}</span></h2>
      <ul class="resultados">
        {#each playlists as p (p.id)}
          <li>
            <a class="resultado" href={`/playlists/ver?id=${p.id}`}>
              <span class="imagen"><Mosaico pistas={p.mosaico} tamano={64} /></span>
              <span class="datos">
                <span class="nombre">{p.nombre}</span>
                <span class="sub">{p.etiqueta} · {textos.biblioteca.cuentaPistas(p.numPistas)}</span
                >
              </span>
              <Icon nombre="derecha" tamano={18} />
            </a>
          </li>
        {/each}
      </ul>
    {/if}

    {#if pistas.length > 0}
      <h2 class="seccion">{t.pistas}<span class="cuenta">{totalPistas}</span></h2>
      <ul class="resultados">
        {#each pistas as p, i (p.id)}
          <li>
            <button
              type="button"
              class="resultado"
              class:sonando={reproductor.instantanea.pistaId === p.id}
              onclick={() => reproducirLista(consulta, i)}
            >
              <span class="imagen">
                {#if p.tienePortada}<img src={urlPortada('pista', p.id, 64)} alt="" />{:else}<Icon
                    nombre="cancion"
                    tamano={20}
                  />{/if}
              </span>
              <span class="datos">
                <span class="nombre">{p.titulo}</span>
                <span class="sub">{p.artista} · {p.album}</span>
              </span>
              <span class="duracion">{formatoTiempo(p.duracionSeg)}</span>
              <Icon nombre="reproducir" tamano={18} />
            </button>
          </li>
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
  }

  .tarjeta-titulo {
    padding: var(--ns-espacio-4) var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container);
  }

  h1 {
    margin: 0;
    font-size: var(--ns-texto-xl);
  }

  .tarjeta-titulo p {
    margin: var(--ns-espacio-2) 0 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .seccion {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    margin: var(--ns-espacio-3) 0 0;
    padding-bottom: var(--ns-espacio-1);
    border-bottom: 1px solid var(--m3c-outline-variant);
    font-size: var(--ns-texto-md);
  }

  .cuenta {
    min-width: 1.5rem;
    padding: 0 var(--ns-espacio-2);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
    font-size: var(--ns-texto-xs);
    text-align: center;
  }

  .resultados {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .resultado {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    width: 100%;
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border: none;
    border-radius: var(--ns-radio-sm);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    text-align: left;
    text-decoration: none;
    cursor: pointer;
  }

  .resultado:hover {
    background: var(--m3c-surface-container);
  }

  .resultado.sonando .nombre {
    color: var(--m3c-primary);
  }

  .imagen {
    display: grid;
    place-items: center;
    flex: 0 0 2.75rem;
    width: 2.75rem;
    height: 2.75rem;
    overflow: hidden;
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
  }

  .imagen.redonda {
    border-radius: var(--ns-radio-pleno);
  }

  .imagen img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .datos {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-width: 0;
  }

  .nombre,
  .sub {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .nombre {
    font-weight: 700;
    font-size: var(--ns-texto-sm);
  }

  .sub,
  .duracion {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .vacio {
    color: var(--m3c-on-surface-variant);
  }
</style>
