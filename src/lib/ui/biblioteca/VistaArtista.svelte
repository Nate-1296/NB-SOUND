<!--
  El detalle de un artista: su imagen y cifras, sus álbumes y todas sus canciones,
  como en la V1 (que exponía todas las pistas y no solo las destacadas). Las
  canciones van en la ventana virtual, porque un artista puede tener cientos.
-->
<script lang="ts">
  import { page } from '$app/state';
  import {
    type AlbumResumen,
    type ArtistaResumen,
    bibliotecaAlbumes,
    bibliotecaArtista,
    bibliotecaPistas,
    type ConsultaPistas,
    fijarFavorita,
    type PistaResumen,
    reproducirLista,
    urlPortada
  } from '$core/ipc';
  import { reproductor } from '$core/reproductor.svelte';
  import { textos } from '$lib/i18n';
  import FilaPista from '$ui/biblioteca/FilaPista.svelte';
  import Icon from '$ui/Icon.svelte';
  import ListaVirtual from '$ui/lista/ListaVirtual.svelte';
  import { TAM_BLOQUE } from '$ui/lista/ventana';

  const t = textos.biblioteca;
  const id = $derived(Number(page.url.searchParams.get('id')));

  let artista = $state<ArtistaResumen | null | undefined>(undefined);
  let albumes = $state<AlbumResumen[]>([]);
  let total = $state(0);

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
    if (!Number.isFinite(id) || id <= 0) {
      artista = null;
      return;
    }
    void bibliotecaArtista(id).then((a) => (artista = a));
    void bibliotecaAlbumes({ texto: null, artistaId: id, orden: 'anioDesc' }, 0, 200).then(
      (p) => (albumes = p.albumes)
    );
    void bibliotecaPistas(c, 0, 1).then((p) => (total = p.total));
  });

  async function cargarBloque(b: number): Promise<PistaResumen[]> {
    return (await bibliotecaPistas(consulta, b * TAM_BLOQUE, TAM_BLOQUE)).pistas;
  }

  let favoritas = $state(new Map<number, boolean>());
  function alternarFavorita(p: PistaResumen) {
    const nueva = !(favoritas.get(p.id) ?? p.favorita);
    favoritas = new Map(favoritas).set(p.id, nueva);
    void fijarFavorita(p.id, nueva);
  }
</script>

<section class="detalle">
  <a class="volver" href="/biblioteca?vista=artistas">
    <Icon nombre="atras" tamano={18} />{t.album.volver}
  </a>

  {#if artista === null}
    <p class="vacio">{t.artista.noEncontrado}</p>
  {:else if artista}
    <header class="cabecera">
      <div class="imagen">
        {#if artista.tieneImagen}
          <img src={urlPortada('artista', artista.id, 320)} alt="" />
        {:else}
          <Icon nombre="artista" tamano={56} />
        {/if}
      </div>
      <div class="datos">
        <h1>{artista.nombre}</h1>
        <span class="sub">{t.artista.resumen(artista.numAlbumes, artista.numPistas)}</span>
        <div class="acciones">
          <button type="button" class="boton relleno" onclick={() => reproducirLista(consulta, 0)}>
            <Icon nombre="reproducir" tamano={16} />{t.reproducir}
          </button>
          <button
            type="button"
            class="boton"
            onclick={async () => {
              await reproductor.orden({ tipo: 'aleatorio', activo: true });
              await reproducirLista(consulta, 0);
            }}
          >
            <Icon nombre="aleatorio" tamano={16} />{t.artista.aleatorio}
          </button>
        </div>
      </div>
    </header>

    {#if albumes.length > 0}
      <section class="seccion-albumes" aria-labelledby="t-albumes-artista">
        <h2 id="t-albumes-artista">{t.artista.albumes}</h2>
        <ul class="rejilla">
          {#each albumes as a (a.id)}
            <li>
              <a class="tarjeta" href={`/biblioteca/album?id=${a.id}`}>
                <span class="caratula">
                  {#if a.tienePortada}
                    <img src={urlPortada('album', a.id, 320)} alt="" loading="lazy" />
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

    <h2>{t.artista.canciones}</h2>
    {#if total > 0}
      <div class="lista">
        {#key id}
          <ListaVirtual {total} altoFila={66} {cargarBloque} etiqueta={t.artista.canciones}>
            {#snippet fila(p: PistaResumen, i: number, rapido: boolean)}
              <FilaPista
                contexto="artista"
                pista={{ ...p, favorita: favoritas.get(p.id) ?? p.favorita }}
                numero={i + 1}
                {rapido}
                sonando={reproductor.instantanea.pistaId === p.id}
                onreproducir={() => reproducirLista(consulta, i)}
                onanadir={() =>
                  reproductor.orden({ tipo: 'agregar', ids: [p.id], justoDespues: false })}
                onfavorita={() => alternarFavorita(p)}
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
    align-items: center;
    gap: var(--ns-espacio-5);
  }

  .imagen {
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    width: 10rem;
    height: 10rem;
    overflow: hidden;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
  }

  .imagen img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .datos {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--ns-espacio-2);
  }

  h1 {
    margin: 0;
    font-size: var(--ns-texto-2xl);
  }

  h2 {
    margin: var(--ns-espacio-3) 0 0;
    font-size: var(--ns-texto-lg);
  }

  .sub {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .acciones {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    margin-top: var(--ns-espacio-2);
  }

  .boton {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    height: 2.75rem;
    padding: 0 var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline);
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface);
    font: inherit;
    font-weight: 700;
    cursor: pointer;
    transition: background-color var(--ns-duracion-corta) var(--ns-curva);
  }

  .boton:hover {
    background: var(--m3c-surface-container-high);
  }

  .boton.relleno {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .boton.relleno:hover {
    background: var(--m3c-primary);
    opacity: 0.9;
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
