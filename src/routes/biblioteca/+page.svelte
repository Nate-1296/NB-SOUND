<!--
  Biblioteca, con la disposición de la V1 (`VistaBiblioteca.qml`): título y cuenta,
  las pestañas Álbumes, Artistas y Pistas arriba a la derecha, la búsqueda, el
  filtro de favoritas y los órdenes en fichas. La lista de canciones es la ventana
  virtual medida en F0.4.7; Sin verificar es nuevo (enmienda de ADR-007).
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import {
    anadirMusica,
    type AlbumResumen,
    type ArtistaResumen,
    bibliotecaAlbumes,
    bibliotecaArtistas,
    bibliotecaPistas,
    type ConsultaPistas,
    fijarFavorita,
    type OrdenAlbumes,
    type OrdenArtistas,
    type OrdenPistas,
    type PistaResumen,
    reproducirLista,
    urlPortada,
    karaokeEstado,
    karaokePrepararFavoritas
  } from '$core/ipc';
  import { reproductor } from '$core/reproductor.svelte';
  import { textos } from '$lib/i18n';
  import FilaPista from '$ui/biblioteca/FilaPista.svelte';
  import Icon from '$ui/Icon.svelte';
  import ListaVirtual from '$ui/lista/ListaVirtual.svelte';
  import { TAM_BLOQUE } from '$ui/lista/ventana';

  type Vista = 'albumes' | 'artistas' | 'pistas';
  const t = textos.biblioteca;

  const ORDENES_PISTAS: OrdenPistas[] = [
    'tituloAsc',
    'tituloDesc',
    'artistaAsc',
    'artistaDesc',
    'albumAsc',
    'albumDesc',
    'anioDesc',
    'anioAsc',
    'duracionDesc',
    'duracionAsc',
    'recientes',
    'antiguas',
    'masReproducidas',
    'menosReproducidas'
  ];
  const ORDENES_ALBUMES: OrdenAlbumes[] = [
    'tituloAsc',
    'tituloDesc',
    'artistaAsc',
    'anioDesc',
    'anioAsc',
    'recientes'
  ];
  const ORDENES_ARTISTAS: OrdenArtistas[] = ['nombreAsc', 'nombreDesc', 'masPistas'];

  const vista = $derived<Vista>(
    (['albumes', 'artistas', 'pistas'] as const).find(
      (v) => v === page.url.searchParams.get('vista')
    ) ?? 'pistas'
  );

  let texto = $state('');
  let textoAplicado = $state('');
  let favoritas = $state(false);
  let sinVerificar = $state(false);
  let paraCantar = $state(false);
  let ofertaKaraoke = $state(false);
  let avisoFavoritas = $state<string | null>(null);

  // "Preparar mis favoritas" (F5.2.3); sin el agregado, se ofrece (F5.1.4).
  async function prepararFavoritas() {
    if (!(await karaokeEstado()).instalado) {
      ofertaKaraoke = true;
      return;
    }
    avisoFavoritas = t.favoritasEnCola(await karaokePrepararFavoritas());
  }
  let ordenPistas = $state<OrdenPistas>('tituloAsc');
  let ordenAlbumes = $state<OrdenAlbumes>('tituloAsc');
  let ordenArtistas = $state<OrdenArtistas>('nombreAsc');

  // La búsqueda espera a que se deje de escribir: cada tecla no es una consulta.
  let espera: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const valor = texto;
    clearTimeout(espera);
    espera = setTimeout(() => (textoAplicado = valor.trim()), 200);
    return () => clearTimeout(espera);
  });

  const consulta = $derived<ConsultaPistas>({
    texto: textoAplicado || null,
    favoritas,
    sinVerificar,
    paraCantar,
    albumId: null,
    artistaId: null,
    orden: ordenPistas
  });

  // --- Pistas ---
  let total = $state<number | null>(null);
  let primerBloque: PistaResumen[] = [];
  let version = $state(0);
  // Editar o completar una pista la cambia en la base: se vuelve a pedir la lista.
  let recargas = $state(0);
  $effect(() => {
    const c = consulta;
    void recargas;
    if (vista !== 'pistas') return;
    const v = ++version;
    void bibliotecaPistas(c, 0, TAM_BLOQUE).then((p) => {
      if (v !== version) return;
      primerBloque = p.pistas;
      total = p.total;
    });
  });

  async function cargarBloque(b: number): Promise<PistaResumen[]> {
    if (b === 0) return primerBloque;
    return (await bibliotecaPistas(consulta, b * TAM_BLOQUE, TAM_BLOQUE)).pistas;
  }

  // Una favorita cambia en el sitio, sin recargar la lista.
  let favoritasCambiadas = $state(new Map<number, boolean>());
  function alternarFavorita(p: PistaResumen) {
    const nueva = !(favoritasCambiadas.get(p.id) ?? p.favorita);
    favoritasCambiadas = new Map(favoritasCambiadas).set(p.id, nueva);
    void fijarFavorita(p.id, nueva);
  }

  // --- Álbumes y artistas: por páginas que se añaden al llegar al final ---
  let albumes = $state<AlbumResumen[]>([]);
  let artistas = $state<ArtistaResumen[]>([]);
  let totalGrid = $state(0);
  let cargandoGrid = false;
  const PAGINA = 120;

  $effect(() => {
    const busqueda = textoAplicado || null;
    if (vista === 'albumes') {
      const orden = ordenAlbumes;
      void bibliotecaAlbumes({ texto: busqueda, artistaId: null, orden }, 0, PAGINA).then((p) => {
        albumes = p.albumes;
        totalGrid = p.total;
      });
    } else if (vista === 'artistas') {
      const orden = ordenArtistas;
      void bibliotecaArtistas({ texto: busqueda, orden }, 0, PAGINA).then((p) => {
        artistas = p.artistas;
        totalGrid = p.total;
      });
    }
  });

  async function masGrid() {
    if (cargandoGrid) return;
    const busqueda = textoAplicado || null;
    cargandoGrid = true;
    try {
      if (vista === 'albumes' && albumes.length < totalGrid) {
        const p = await bibliotecaAlbumes(
          { texto: busqueda, artistaId: null, orden: ordenAlbumes },
          albumes.length,
          PAGINA
        );
        albumes = [...albumes, ...p.albumes];
      } else if (vista === 'artistas' && artistas.length < totalGrid) {
        const p = await bibliotecaArtistas(
          { texto: busqueda, orden: ordenArtistas },
          artistas.length,
          PAGINA
        );
        artistas = [...artistas, ...p.artistas];
      }
    } finally {
      cargandoGrid = false;
    }
  }

  function alFinal(nodo: HTMLElement) {
    const o = new IntersectionObserver((e) => {
      if (e.some((x) => x.isIntersecting)) void masGrid();
    });
    o.observe(nodo);
    return { destroy: () => o.disconnect() };
  }

  const cuenta = $derived(
    vista === 'pistas'
      ? t.cuentaPistas(total ?? 0)
      : vista === 'albumes'
        ? t.cuentaAlbumes(totalGrid)
        : t.cuentaArtistas(totalGrid)
  );
</script>

<section class="vista">
  <header class="cabecera">
    <div>
      <h1>{t.titulo}</h1>
      <p class="cuenta">{cuenta}</p>
    </div>
    <div class="anadir">
      <button type="button" class="boton principal" onclick={() => anadirMusica(false)}>
        <Icon nombre="mas" tamano={18} />
        {textos.importacion.anadir}
      </button>
      <button type="button" class="boton" onclick={() => anadirMusica(true)}>
        <Icon nombre="carpeta" tamano={18} />
        {textos.importacion.anadirCarpeta}
      </button>
    </div>
    <div class="pestanas" role="tablist">
      {#each ['albumes', 'artistas', 'pistas'] as const as v (v)}
        <button
          type="button"
          role="tab"
          class="pestana"
          class:activa={vista === v}
          aria-selected={vista === v}
          onclick={() => goto(`/biblioteca?vista=${v}`, { replace: true, reset: false })}
        >
          {t.vistas[v]}
        </button>
      {/each}
    </div>
  </header>

  <label class="busqueda">
    <Icon nombre="buscar" tamano={18} />
    <input type="search" placeholder={t.buscar} aria-label={t.buscar} bind:value={texto} />
  </label>

  {#if vista === 'pistas'}
    <div class="fichas">
      <button
        type="button"
        class="ficha"
        class:activa={favoritas}
        aria-pressed={favoritas}
        onclick={() => (favoritas = !favoritas)}
      >
        <Icon nombre="favorito" tamano={14} />{t.favoritas}
      </button>
      <button
        type="button"
        class="ficha"
        class:activa={sinVerificar}
        aria-pressed={sinVerificar}
        onclick={() => (sinVerificar = !sinVerificar)}
      >
        <Icon nombre="advertencia" tamano={14} />{t.sinVerificar}
      </button>
      <button
        type="button"
        class="ficha"
        class:activa={paraCantar}
        aria-pressed={paraCantar}
        onclick={() => (paraCantar = !paraCantar)}
      >
        <Icon nombre="microfono" tamano={14} />{t.paraCantar}
      </button>
      {#if paraCantar}
        <button type="button" class="ficha" onclick={prepararFavoritas}>
          <Icon nombre="favorito" tamano={14} />{t.prepararFavoritas}
        </button>
      {/if}
    </div>
    {#if avisoFavoritas && paraCantar}<p class="aviso" role="status">{avisoFavoritas}</p>{/if}
    {#if ofertaKaraoke}
      {#await import('$ui/agregados/OfertaAgregado.svelte') then m}
        <m.default id="karaoke" oncerrar={() => (ofertaKaraoke = false)} />
      {/await}
    {/if}
  {/if}

  <div class="fichas ordenes">
    <span class="rotulo">{t.orden}</span>
    {#if vista === 'pistas'}
      {#each ORDENES_PISTAS as o (o)}
        <button
          type="button"
          class="ficha"
          class:activa={ordenPistas === o}
          aria-pressed={ordenPistas === o}
          onclick={() => (ordenPistas = o)}
        >
          <Icon nombre="ordenar" tamano={14} />{t.ordenes[o]}
        </button>
      {/each}
    {:else if vista === 'albumes'}
      {#each ORDENES_ALBUMES as o (o)}
        <button
          type="button"
          class="ficha"
          class:activa={ordenAlbumes === o}
          aria-pressed={ordenAlbumes === o}
          onclick={() => (ordenAlbumes = o)}
        >
          <Icon nombre="ordenar" tamano={14} />{t.ordenes[o]}
        </button>
      {/each}
    {:else}
      {#each ORDENES_ARTISTAS as o (o)}
        <button
          type="button"
          class="ficha"
          class:activa={ordenArtistas === o}
          aria-pressed={ordenArtistas === o}
          onclick={() => (ordenArtistas = o)}
        >
          <Icon nombre="ordenar" tamano={14} />{t.ordenes[o]}
        </button>
      {/each}
    {/if}
  </div>

  {#if vista === 'pistas'}
    <div class="lista">
      {#if total === 0}
        <p class="vacio">
          {textoAplicado || favoritas || sinVerificar || paraCantar ? t.vacia : t.vaciaBiblioteca}
        </p>
      {:else if total !== null}
        {#key version}
          <ListaVirtual {total} altoFila={66} {cargarBloque} etiqueta={t.lista}>
            {#snippet fila(p: PistaResumen, i: number, rapido: boolean)}
              <FilaPista
                pista={{ ...p, favorita: favoritasCambiadas.get(p.id) ?? p.favorita }}
                numero={i + 1}
                {rapido}
                sonando={reproductor.instantanea.pistaId === p.id}
                onreproducir={() => reproducirLista(consulta, i)}
                onanadir={() =>
                  reproductor.orden({ tipo: 'agregar', ids: [p.id], justoDespues: false })}
                onfavorita={() => alternarFavorita(p)}
                oncambiada={() => recargas++}
              />
            {/snippet}
          </ListaVirtual>
        {/key}
      {/if}
    </div>
  {:else if vista === 'albumes'}
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
            <span class="sub">{[a.artista, a.anio ?? ''].filter((x) => x !== '').join(' · ')}</span>
          </a>
        </li>
      {/each}
    </ul>
    <div use:alFinal class="centinela"></div>
  {:else}
    <ul class="rejilla">
      {#each artistas as a (a.id)}
        <li>
          <a class="tarjeta artista" href={`/biblioteca/artista?id=${a.id}`}>
            <span class="caratula redonda">
              {#if a.tieneImagen}
                <img src={urlPortada('artista', a.id, 320)} alt="" loading="lazy" />
              {:else}
                <Icon nombre="artista" tamano={40} />
              {/if}
            </span>
            <span class="nombre" title={a.nombre}>{a.nombre}</span>
            <span class="sub">{textos.biblioteca.artista.resumen(a.numAlbumes, a.numPistas)}</span>
          </a>
        </li>
      {/each}
    </ul>
    <div use:alFinal class="centinela"></div>
  {/if}
</section>

<style>
  .vista {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    height: 100%;
  }

  .cabecera {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--ns-espacio-4);
  }

  h1 {
    margin: 0;
    font-size: var(--ns-texto-xl);
  }

  .anadir {
    display: flex;
    gap: var(--ns-espacio-2);
    margin-left: auto;
  }

  .boton {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    height: 2.5rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }

  .boton.principal {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .cuenta {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .pestanas {
    display: flex;
    gap: var(--ns-espacio-2);
  }

  .pestana {
    min-width: 5.5rem;
    height: 2.5rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-sm);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    cursor: pointer;
  }

  .pestana.activa {
    border-color: var(--m3c-primary);
    background: var(--m3c-surface-container-high);
    font-weight: 700;
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

  .busqueda input {
    flex: 1;
    border: none;
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
  }

  /* El foco se ve en la cápsula entera, no en el campo de dentro. */
  .busqueda:focus-within {
    border-color: var(--m3c-primary);
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
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-1);
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

  .lista {
    flex: 1;
    min-height: 0;
    border-top: 1px solid var(--m3c-outline-variant);
    padding-top: var(--ns-espacio-2);
  }

  .vacio {
    color: var(--m3c-on-surface-variant);
    text-align: center;
    margin-top: var(--ns-espacio-7);
  }

  .rejilla {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(10.5rem, 1fr));
    gap: var(--ns-espacio-4);
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
    color: inherit;
    text-decoration: none;
  }

  .tarjeta:hover {
    background: var(--m3c-surface-container);
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

  .caratula.redonda {
    border-radius: var(--ns-radio-pleno);
  }

  .caratula img {
    width: 100%;
    height: 100%;
    object-fit: cover;
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

  .sub {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .artista {
    text-align: center;
  }

  .centinela {
    height: 1px;
  }

  .aviso {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }
</style>
