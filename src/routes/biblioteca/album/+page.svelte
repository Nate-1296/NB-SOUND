<!--
  El detalle de un álbum (`VistaDetalleAlbum.qml` de la V1): la portada grande,
  título, artista, año y duración, Reproducir y Aleatorio, y sus canciones en orden.
-->
<script lang="ts">
  import { page } from '$app/state';
  import {
    type AlbumResumen,
    bibliotecaAlbum,
    bibliotecaPistas,
    type ConsultaPistas,
    fijarFavorita,
    type PistaResumen,
    reproducirLista,
    urlPortada
  } from '$core/ipc';
  import { formatoTiempo, reproductor } from '$core/reproductor.svelte';
  import { textos } from '$lib/i18n';
  import FilaPista from '$ui/biblioteca/FilaPista.svelte';
  import Icon from '$ui/Icon.svelte';

  const t = textos.biblioteca;
  const id = $derived(Number(page.url.searchParams.get('id')));

  let album = $state<AlbumResumen | null | undefined>(undefined);
  let pistas = $state<PistaResumen[]>([]);

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
    if (!Number.isFinite(id) || id <= 0) {
      album = null;
      return;
    }
    void bibliotecaAlbum(id).then((a) => (album = a));
    void bibliotecaPistas(c, 0, 500).then((p) => (pistas = p.pistas));
  });

  function alternarFavorita(i: number) {
    const p = pistas[i];
    if (!p) return;
    pistas[i] = { ...p, favorita: !p.favorita };
    void fijarFavorita(p.id, !p.favorita);
  }

  function aleatorio() {
    if (!reproductor.instantanea.aleatorio) void reproductor.alternarAleatorio();
    void reproducirLista(consulta, Math.floor(Math.random() * pistas.length));
  }
</script>

<section class="detalle">
  <a class="volver" href="/biblioteca?vista=albumes">
    <Icon nombre="atras" tamano={18} />{t.album.volver}
  </a>

  {#if album === null}
    <p class="vacio">{t.album.noEncontrado}</p>
  {:else if album}
    <header class="cabecera">
      <div class="portada">
        {#if album.tienePortada}
          <img src={urlPortada('album', album.id, 640)} alt="" />
        {:else}
          <Icon nombre="album" tamano={64} />
        {/if}
      </div>
      <div class="datos">
        <span class="tipo">{album.tipo}</span>
        <h1>{album.titulo}</h1>
        <a class="artista" href={`/biblioteca/artista?id=${album.artistaId}`}>{album.artista}</a>
        <span class="sub">
          {[album.anio ?? '', t.album.pistas(album.numPistas, formatoTiempo(album.duracionSeg))]
            .filter((x) => x !== '')
            .join(' · ')}
        </span>
        <div class="botones">
          <button
            type="button"
            class="boton principal"
            onclick={() => reproducirLista(consulta, 0)}
          >
            <Icon nombre="reproducir" tamano={16} />{t.reproducir}
          </button>
          <button type="button" class="boton" onclick={aleatorio}>
            <Icon nombre="aleatorio" tamano={16} />{t.album.aleatorio}
          </button>
        </div>
      </div>
    </header>

    <ul class="pistas" aria-label={t.lista}>
      {#each pistas as p, i (p.id)}
        <li>
          <FilaPista
            pista={p}
            numero={i + 1}
            sonando={reproductor.instantanea.pistaId === p.id}
            onreproducir={() => reproducirLista(consulta, i)}
            onanadir={() =>
              reproductor.orden({ tipo: 'agregar', ids: [p.id], justoDespues: false })}
            onfavorita={() => alternarFavorita(i)}
          />
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .detalle {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
  }

  .volver {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
    text-decoration: none;
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
    width: 13rem;
    height: 13rem;
    overflow: hidden;
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
  }

  .portada img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .datos {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    min-width: 0;
  }

  .tipo {
    color: var(--m3c-primary);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  h1 {
    margin: 0;
    font-size: var(--ns-texto-2xl);
  }

  .artista {
    color: var(--m3c-on-surface);
    font-weight: 600;
    text-decoration: none;
  }

  .sub {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .botones {
    display: flex;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-3);
  }

  .boton {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    height: 2.75rem;
    padding: 0 var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-weight: 700;
    cursor: pointer;
  }

  .boton.principal {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .pistas {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .pistas li {
    height: 4.125rem;
  }

  .vacio {
    color: var(--m3c-on-surface-variant);
  }
</style>
