<!--
  Biblioteca, con la disposición de la V1 (`VistaBiblioteca.qml`): título y cuenta,
  las pestañas Álbumes, Artistas y Pistas arriba a la derecha, la búsqueda, el
  filtro de favoritas y los órdenes en fichas. La lista de canciones es la ventana
  virtual medida en F0.4.7; Sin verificar es nuevo (enmienda de ADR-007).
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { untrack } from 'svelte';
  import {
    type AlbumResumen,
    type ArtistaResumen,
    bibliotecaAlbumes,
    bibliotecaArtistas,
    bibliotecaPistas,
    type ConsultaPistas,
    type OrdenAlbumes,
    type OrdenArtistas,
    type OrdenPistas,
    type PistaResumen,
    reproducirLista,
    urlPortada,
    karaokeEstado,
    karaokePrepararFavoritas
  } from '#lib/core/ipc/index.ts';
  import { estadoBiblioteca, type ModoRejilla } from '#lib/core/estadoVistas.svelte.ts';
  import { reproductor } from '#lib/core/reproductor.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import FilaPista from '#lib/ui/biblioteca/FilaPista.svelte';
  import Icon from '#lib/ui/Icon.svelte';
  import ListaVirtual from '#lib/ui/lista/ListaVirtual.svelte';
  import MenuSelector from '#lib/ui/MenuSelector.svelte';
  import { TAM_BLOQUE } from '#lib/ui/lista/ventana.ts';

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

  const paramVista = $derived(
    (['albumes', 'artistas', 'pistas'] as const).find(
      (v) => v === page.url.searchParams.get('vista')
    )
  );

  $effect(() => {
    if (paramVista && paramVista !== estadoBiblioteca.vista) {
      estadoBiblioteca.vista = paramVista;
    }
  });

  const vista = $derived<Vista>(estadoBiblioteca.vista);

  let texto = $state('');
  let textoAplicado = $state('');
  let modoRejilla = $state<ModoRejilla>('md');

  let favoritas = $state(estadoBiblioteca.pistas.favoritas);
  let sinVerificar = $state(estadoBiblioteca.pistas.sinVerificar);
  let paraCantar = $state(estadoBiblioteca.pistas.paraCantar);
  let ofertaKaraoke = $state(false);
  let avisoFavoritas = $state<string | null>(null);

  async function prepararFavoritas() {
    if (!(await karaokeEstado()).instalado) {
      ofertaKaraoke = true;
      return;
    }
    avisoFavoritas = t.favoritasEnCola(await karaokePrepararFavoritas());
  }

  let ordenPistas = $state<OrdenPistas>(estadoBiblioteca.pistas.orden);
  let ordenAlbumes = $state<OrdenAlbumes>(estadoBiblioteca.albumes.orden);
  let ordenArtistas = $state<OrdenArtistas>(estadoBiblioteca.artistas.orden);

  // Al cambiar de pestaña de Biblioteca, restaurar su estado propio e independiente
  $effect(() => {
    const v = vista;
    untrack(() => {
      estadoBiblioteca.vista = v;
      if (v === 'albumes') {
        texto = estadoBiblioteca.albumes.busqueda;
        modoRejilla = estadoBiblioteca.albumes.modoRejilla;
      } else if (v === 'artistas') {
        texto = estadoBiblioteca.artistas.busqueda;
        modoRejilla = estadoBiblioteca.artistas.modoRejilla;
      } else {
        texto = estadoBiblioteca.pistas.busqueda;
        modoRejilla = estadoBiblioteca.pistas.modoRejilla;
      }
      textoAplicado = texto;
    });
  });

  // Persistir en memoria para cada pestaña por separado
  $effect(() => {
    const v = vista;
    const t = texto;
    const m = modoRejilla;
    if (v === 'albumes') {
      estadoBiblioteca.albumes.busqueda = t;
      estadoBiblioteca.albumes.modoRejilla = m;
      estadoBiblioteca.albumes.orden = ordenAlbumes;
    } else if (v === 'artistas') {
      estadoBiblioteca.artistas.busqueda = t;
      estadoBiblioteca.artistas.modoRejilla = m;
      estadoBiblioteca.artistas.orden = ordenArtistas;
    } else {
      estadoBiblioteca.pistas.busqueda = t;
      estadoBiblioteca.pistas.modoRejilla = m;
      estadoBiblioteca.pistas.orden = ordenPistas;
      estadoBiblioteca.pistas.favoritas = favoritas;
      estadoBiblioteca.pistas.sinVerificar = sinVerificar;
      estadoBiblioteca.pistas.paraCantar = paraCantar;
    }
  });

  const ordenesActuales = $derived(
    vista === 'pistas' ? ORDENES_PISTAS : vista === 'albumes' ? ORDENES_ALBUMES : ORDENES_ARTISTAS
  );

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
  let pedido = 0;
  let version = $state(0);
  // Editar o completar una pista la cambia en la base: se vuelve a pedir la lista.
  let recargas = $state(0);
  $effect(() => {
    const c = consulta;
    void recargas;
    if (vista !== 'pistas') return;
    const v = ++pedido;
    void bibliotecaPistas(c, 0, TAM_BLOQUE).then((p) => {
      if (v !== pedido) return;
      primerBloque = p.pistas;
      total = p.total;
      version = v;
    });
  });

  async function cargarBloque(b: number): Promise<PistaResumen[]> {
    if (b === 0) return primerBloque;
    return (await bibliotecaPistas(consulta, b * TAM_BLOQUE, TAM_BLOQUE)).pistas;
  }

  // Una favorita cambia en el sitio, sin recargar la lista.

  // --- Álbumes y artistas: por páginas que se añaden al llegar al final ---
  let albumes = $state<AlbumResumen[]>([]);
  let artistas = $state<ArtistaResumen[]>([]);
  let pistasRejilla = $state<PistaResumen[]>([]);
  let totalAlbumes = $state(0);
  let totalArtistas = $state(0);
  let pedidoGrid = 0;
  let cargandoGrid = false;
  const PAGINA = 120;

  $effect(() => {
    const busqueda = textoAplicado || null;
    if (vista === 'pistas') {
      if (modoRejilla !== 'lista') {
        const g = ++pedidoGrid;
        cargandoGrid = true;
        void bibliotecaPistas(consulta, 0, PAGINA).then((p) => {
          if (g !== pedidoGrid) return;
          pistasRejilla = p.pistas;
          total = p.total;
          cargandoGrid = false;
        });
      }
    } else if (vista === 'albumes') {
      const orden = ordenAlbumes;
      const g = ++pedidoGrid;
      cargandoGrid = true;
      void bibliotecaAlbumes({ texto: busqueda, artistaId: null, orden }, 0, PAGINA).then((p) => {
        if (g !== pedidoGrid) return;
        albumes = p.albumes;
        totalAlbumes = p.total;
        cargandoGrid = false;
      });
    } else if (vista === 'artistas') {
      const orden = ordenArtistas;
      const g = ++pedidoGrid;
      cargandoGrid = true;
      void bibliotecaArtistas({ texto: busqueda, orden }, 0, PAGINA).then((p) => {
        if (g !== pedidoGrid) return;
        artistas = p.artistas;
        totalArtistas = p.total;
        cargandoGrid = false;
      });
    }
  });

  function anadirUnicos<T extends { id: number }>(actuales: T[], nuevos: T[]): T[] {
    const vistos = new Set(actuales.map((x) => x.id));
    return [...actuales, ...nuevos.filter((x) => !vistos.has(x.id))];
  }

  async function cargarMasPistas(g: number) {
    if (pistasRejilla.length === 0 || pistasRejilla.length >= (total ?? 0)) return;
    const p = await bibliotecaPistas(consulta, pistasRejilla.length, PAGINA);
    if (g === pedidoGrid) pistasRejilla = anadirUnicos(pistasRejilla, p.pistas);
  }

  async function cargarMasAlbumes(g: number, busqueda: string | null) {
    if (albumes.length === 0 || albumes.length >= totalAlbumes) return;
    const p = await bibliotecaAlbumes(
      { texto: busqueda, artistaId: null, orden: ordenAlbumes },
      albumes.length,
      PAGINA
    );
    if (g === pedidoGrid) albumes = anadirUnicos(albumes, p.albumes);
  }

  async function cargarMasArtistas(g: number, busqueda: string | null) {
    if (artistas.length === 0 || artistas.length >= totalArtistas) return;
    const p = await bibliotecaArtistas(
      { texto: busqueda, orden: ordenArtistas },
      artistas.length,
      PAGINA
    );
    if (g === pedidoGrid) artistas = anadirUnicos(artistas, p.artistas);
  }

  async function masGrid() {
    if (cargandoGrid) return;
    const busqueda = textoAplicado || null;
    const g = pedidoGrid;
    cargandoGrid = true;
    try {
      if (vista === 'pistas') await cargarMasPistas(g);
      else if (vista === 'albumes') await cargarMasAlbumes(g, busqueda);
      else if (vista === 'artistas') await cargarMasArtistas(g, busqueda);
    } finally {
      if (g === pedidoGrid) cargandoGrid = false;
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
        ? t.cuentaAlbumes(totalAlbumes)
        : t.cuentaArtistas(totalArtistas)
  );
</script>

<section class="vista">
  <header class="cabecera">
    <div class="cabecera-info">
      <h1>{t.titulo}</h1>
      <p class="cuenta">{cuenta}</p>
    </div>
    <div class="pestanas" role="tablist">
      {#each ['albumes', 'artistas', 'pistas'] as const as v (v)}
        <button
          type="button"
          role="tab"
          class="pestana"
          class:activa={vista === v}
          aria-selected={vista === v}
          onclick={() => {
            estadoBiblioteca.vista = v;
            void goto(`/biblioteca?vista=${v}`, {
              replace: true,
              reset: false
            });
          }}
        >
          {t.vistas[v]}
        </button>
      {/each}
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
      {/if}

      <div class="control-orden">
        <MenuSelector
          rotulo={t.orden}
          opciones={ordenesActuales.map((o) => ({ valor: o, etiqueta: t.ordenes[o] }))}
          valor={vista === 'pistas'
            ? ordenPistas
            : vista === 'albumes'
              ? ordenAlbumes
              : ordenArtistas}
          onchange={(v) => {
            if (vista === 'pistas') ordenPistas = v as OrdenPistas;
            else if (vista === 'albumes') ordenAlbumes = v as OrdenAlbumes;
            else ordenArtistas = v as OrdenArtistas;
          }}
        />
      </div>

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

  {#if vista === 'pistas'}
    {#if avisoFavoritas && paraCantar}<p class="aviso" role="status">{avisoFavoritas}</p>{/if}
    {#if ofertaKaraoke}
      {#await import('#lib/ui/agregados/OfertaAgregado.svelte') then m}
        <m.default id="karaoke" oncerrar={() => (ofertaKaraoke = false)} />
      {/await}
    {/if}
  {/if}

  {#if vista === 'pistas'}
    {#if modoRejilla === 'lista'}
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
                  pista={p}
                  numero={i + 1}
                  {rapido}
                  sonando={reproductor.instantanea.pistaId === p.id}
                  onreproducir={() => reproducirLista(consulta, i)}
                  oncambiada={() => recargas++}
                />
              {/snippet}
            </ListaVirtual>
          {/key}
        {/if}
      </div>
    {:else}
      <ul
        class="rejilla"
        class:sm={modoRejilla === 'sm'}
        class:md={modoRejilla === 'md'}
        class:lg={modoRejilla === 'lg'}
      >
        {#each pistasRejilla as p, i (p.id)}
          <li>
            <div class="tarjeta">
              <button
                type="button"
                class="caratula"
                onclick={() => reproducirLista(consulta, i)}
                aria-label={`${t.reproducir} ${p.titulo}`}
              >
                {#if p.tienePortada}
                  <img src={urlPortada('pista', p.id, 320)} alt="" loading="lazy" />
                {:else}
                  <Icon nombre="cancion" tamano={40} />
                {/if}
              </button>
              <span class="nombre" title={p.titulo}>{p.titulo}</span>
              <span class="sub" title={`${p.artista} · ${p.album}`}>
                {[p.artista, p.album].filter(Boolean).join(' · ')}
              </span>
            </div>
          </li>
        {/each}
      </ul>
      {#if pistasRejilla.length > 0 && pistasRejilla.length < (total ?? 0)}
        <div use:alFinal class="centinela"></div>
      {/if}
    {/if}
  {:else if vista === 'albumes'}
    <ul
      class="rejilla"
      class:sm={modoRejilla === 'sm'}
      class:md={modoRejilla === 'md'}
      class:lg={modoRejilla === 'lg'}
      class:lista={modoRejilla === 'lista'}
    >
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
    {#if albumes.length > 0 && albumes.length < totalAlbumes}
      <div use:alFinal class="centinela"></div>
    {/if}
  {:else}
    <ul
      class="rejilla"
      class:sm={modoRejilla === 'sm'}
      class:md={modoRejilla === 'md'}
      class:lg={modoRejilla === 'lg'}
      class:lista={modoRejilla === 'lista'}
    >
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
    {#if artistas.length > 0 && artistas.length < totalArtistas}
      <div use:alFinal class="centinela"></div>
    {/if}
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
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-4);
  }

  .cabecera-info {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
  }

  h1 {
    margin: 0;
    font-size: var(--ns-texto-xl);
    font-weight: 700;
  }

  .cuenta {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .pestanas {
    display: flex;
    background: var(--m3c-surface-container);
    border-radius: var(--ns-radio-pleno);
    padding: 2px;
    gap: var(--ns-espacio-1);
    border: 1px solid var(--m3c-outline-variant);
  }

  .pestana {
    min-width: 5.5rem;
    height: 2.125rem;
    padding: 0 var(--ns-espacio-3);
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface-variant);
    font: inherit;
    font-size: var(--ns-texto-sm);
    cursor: pointer;
    transition:
      background 120ms ease,
      color 120ms ease;
  }

  .pestana:hover:not(.activa) {
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
  }

  .pestana.activa {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-primary);
    font-weight: 700;
    box-shadow: 0 1px 3px var(--m3c-shadow);
  }

  .barra-filtros {
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
    flex: 1 1 24rem;
    max-width: 44rem;
  }

  .filtros-der {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    flex-wrap: wrap;
    margin-left: auto;
  }

  .fichas {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--ns-espacio-2);
  }

  .ficha {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-1);
    height: 2.125rem;
    padding: 0 var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface-variant);
    font: inherit;
    font-size: var(--ns-texto-xs);
    cursor: pointer;
    transition:
      background 120ms ease,
      color 120ms ease,
      border-color 120ms ease;
  }

  .ficha:hover:not(.activa) {
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
  }

  .ficha.activa {
    border-color: var(--m3c-primary);
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
    font-weight: 700;
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

  .control-orden {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
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

  .rejilla.lista .caratula {
    width: 3.5rem;
    height: 3.5rem;
    flex: 0 0 3.5rem;
  }

  .tarjeta {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    padding: var(--ns-espacio-3);
    border-radius: var(--ns-radio-md);
    color: inherit;
    text-decoration: none;
    background: transparent;
    transition: background 140ms ease;
  }

  .tarjeta:hover {
    background: var(--m3c-surface-container);
  }

  .caratula {
    display: grid;
    place-items: center;
    width: 100%;
    aspect-ratio: 1;
    overflow: hidden;
    padding: 0;
    border: none;
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
    box-shadow: 0 4px 12px var(--m3c-shadow);
    cursor: pointer;
    transition:
      transform 160ms ease,
      box-shadow 160ms ease;
  }

  .tarjeta:hover .caratula {
    transform: scale(1.02);
    box-shadow: 0 8px 20px var(--m3c-shadow);
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
