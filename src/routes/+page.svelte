<!--
  Inicio, con la disposición de la V1 (`VistaInicio.qml`): el saludo, las cifras
  de la biblioteca, Retomar reproducción y el álbum destacado del día; después
  "Vuelve a tu música", el top 10 y las filas de playlists, álbumes, artistas y
  últimos añadidos. Sin biblioteca, invita a importar.

  La V1 animaba unas barras en la cabecera aunque no sonara nada; aquí no hay
  animación en reposo (ADR-008).
-->
<script lang="ts">
  import { aparienciaActual } from '$core/apariencia.svelte';
  import { duracionDetallada } from '$core/formato';
  import { type Inicio, inicio, reproducirLista, reproducirPlaylist, urlPortada } from '$core/ipc';
  import { formatoTiempo, reproductor } from '$core/reproductor.svelte';
  import { textos } from '$lib/i18n';
  import Icon from '$ui/Icon.svelte';
  import Mosaico from '$ui/playlists/Mosaico.svelte';

  const t = textos.inicio;
  let datos = $state<Inicio | null>(null);

  $effect(() => {
    void inicio().then((d) => (datos = d));
  });

  function al<T>(lista: readonly T[]): T {
    return lista[Math.floor(Math.random() * lista.length)] as T;
  }

  /** Un saludo de la V1, al azar, según la hora y si hay nombre. */
  const saludo = $derived.by(() => {
    const nombre = aparienciaActual.actual.nombreUsuario;
    if (!nombre) return al(t.saludosSinNombre);
    const hora = new Date().getHours();
    const lista = hora < 12 ? t.saludosManana : hora < 19 ? t.saludosTarde : t.saludosNoche;
    return al(lista)(nombre);
  });

  const retomar = $derived(datos?.paraVolver[0] ?? null);
  const hayBiblioteca = $derived((datos?.cifras.pistas ?? 0) > 0);
  const idsVolver = $derived(datos?.paraVolver.map((x) => x.pista.id) ?? []);
  const idsTop = $derived(datos?.top.map((x) => x.pista.id) ?? []);
  const idsUltimos = $derived(datos?.ultimosAnadidos.map((x) => x.id) ?? []);

  function reproducir(ids: number[], desde = 0) {
    void reproductor.reproducirPistas(ids, desde);
  }

  function reproducirAlbum(albumId: number) {
    void reproducirLista(
      {
        texto: null,
        favoritas: false,
        sinVerificar: false,
        albumId,
        artistaId: null,
        orden: 'albumAsc'
      },
      0
    );
  }

  function desplazar(btn: HTMLButtonElement, direccion: -1 | 1) {
    const fila = btn.closest('.cabecera-carrusel')?.nextElementSibling as HTMLElement;
    fila?.scrollBy({ left: direccion * fila.clientWidth * 0.8, behavior: 'smooth' });
  }
</script>

<section class="inicio">
  <header class="saludo">
    <div class="saludo-texto">
      <h1>{saludo}</h1>
      <p>{t.subtitulo}</p>
    </div>
    {#await import('$ui/EcualizadorBarras.svelte') then m}
      <m.default />
    {/await}
  </header>

  {#if datos && !hayBiblioteca}
    <div class="vacia">
      <Icon nombre="biblioteca" tamano={40} />
      <h2>{t.vacia}</h2>
      <p>{t.vaciaSub}</p>
    </div>
  {:else if datos}
    <div class="heroe">
      <div class="izquierda">
        <ul class="cifras">
          {#each [{ href: '/biblioteca?vista=pistas', icono: 'cancion', valor: datos.cifras.pistas.toLocaleString('es'), rotulo: t.pistas }, { href: '/biblioteca?vista=artistas', icono: 'artista', valor: datos.cifras.artistas.toLocaleString('es'), rotulo: t.artistas }, { href: '/biblioteca?vista=albumes', icono: 'album', valor: datos.cifras.albumes.toLocaleString('es'), rotulo: t.albumes }, { href: null, icono: 'reloj', valor: duracionDetallada(datos.cifras.duracionSeg), rotulo: t.duracion }] as c (c.rotulo)}
            <li>
              {#if c.href}
                <a class="cifra-enlace" href={c.href}>
                  <Icon nombre={c.icono as any} tamano={18} /><strong>{c.valor}</strong><span
                    >{c.rotulo}</span
                  >
                </a>
              {:else}
                <div class="cifra-estatica">
                  <Icon nombre={c.icono as any} tamano={18} /><strong>{c.valor}</strong><span
                    >{c.rotulo}</span
                  >
                </div>
              {/if}
            </li>
          {/each}
        </ul>

        {#if retomar}
          <button type="button" class="retomar" onclick={() => reproducir([retomar.pista.id])}>
            <span class="mini-portada">
              {#if retomar.pista.tienePortada}<img
                  src={urlPortada('pista', retomar.pista.id, 64)}
                  alt=""
                />{:else}<Icon nombre="cancion" tamano={18} />{/if}
            </span>
            <span class="texto">
              <span class="etiqueta">{t.retomar}</span>
              <strong>{retomar.pista.titulo}</strong>
              <span class="sub">{retomar.pista.artista} · {retomar.pista.album}</span>
            </span>
            <span class="play"><Icon nombre="reproducir" tamano={18} /></span>
          </button>
        {/if}
      </div>

      {#if datos.albumDestacado}
        {@const a = datos.albumDestacado}
        <div class="destacado">
          {#if a.tienePortada}<img src={urlPortada('album', a.id, 640)} alt="" />{/if}
          <div class="velo">
            <span class="etiqueta">{t.destacado}</span>
            <h2>{a.titulo}</h2>
            <span class="sub">
              {[a.artista, textos.biblioteca.cuentaPistas(a.numPistas), a.anio ?? '']
                .filter((x) => x !== '')
                .join(' · ')}
            </span>
            <div class="botones">
              <button type="button" class="boton relleno" onclick={() => reproducirAlbum(a.id)}>
                <Icon nombre="reproducir" tamano={16} />{t.reproducir}
              </button>
              <a class="boton" href={`/biblioteca/album?id=${a.id}`}>{t.verAlbum}</a>
            </div>
          </div>
        </div>
      {/if}
    </div>

    {#if datos.paraVolver.length > 0}
      <h2 class="seccion">{t.vuelve}</h2>
      <p class="seccion-sub">{t.vuelveSub}</p>
      <ul class="vuelve">
        {#each datos.paraVolver.slice(0, 7) as e, k (e.pista.id)}
          <li class:grande={k === 0}>
            <button type="button" class="tarjeta-pista" onclick={() => reproducir(idsVolver, k)}>
              <span class="mini-portada">
                {#if e.pista.tienePortada}<img
                    src={urlPortada('pista', e.pista.id, k === 0 ? 320 : 64)}
                    alt=""
                  />{:else}<Icon nombre="cancion" tamano={18} />{/if}
              </span>
              <span class="texto">
                {#if k === 0}<span class="etiqueta">{t.ultima}</span>{/if}
                <strong>{e.pista.titulo}</strong>
                <span class="sub">{e.pista.artista} · {e.pista.album}</span>
                <span class="sub">{t.reproducciones(e.reproducciones)}</span>
              </span>
              <span class="play"><Icon nombre="reproducir" tamano={16} /></span>
            </button>
          </li>
        {/each}
      </ul>
    {/if}

    {#if datos.top.length > 0}
      <h2 class="seccion">{t.top}</h2>
      <p class="seccion-sub">{t.topSub}</p>
      <ol class="top">
        {#each datos.top as e, k (e.pista.id)}
          <li>
            <button type="button" class="fila-top" onclick={() => reproducir(idsTop, k)}>
              <span class="numero">{String(k + 1).padStart(2, '0')}</span>
              <span class="mini-portada">
                {#if e.pista.tienePortada}<img
                    src={urlPortada('pista', e.pista.id, 64)}
                    alt=""
                  />{:else}<Icon nombre="cancion" tamano={16} />{/if}
              </span>
              <span class="texto">
                <strong>{e.pista.titulo}</strong>
                <span class="sub">{e.pista.artista}</span>
              </span>
              <span class="sub">{t.reproducciones(e.reproducciones)}</span>
              <span class="sub">{formatoTiempo(e.pista.duracionSeg)}</span>
            </button>
          </li>
        {/each}
      </ol>
    {/if}

    {#snippet carruselCabecera(titulo: string, sub: string)}
      <div class="cabecera-carrusel">
        <div>
          <h2 class="seccion">{titulo}</h2>
          <p class="seccion-sub">{sub}</p>
        </div>
        <div class="controles-carrusel">
          <button
            type="button"
            class="boton-avance"
            aria-label={t.anterior}
            onclick={(e) => desplazar(e.currentTarget, -1)}
          >
            <Icon nombre="anterior" tamano={16} />
          </button>
          <button
            type="button"
            class="boton-avance"
            aria-label={t.siguiente}
            onclick={(e) => desplazar(e.currentTarget, 1)}
          >
            <Icon nombre="siguiente" tamano={16} />
          </button>
        </div>
      </div>
    {/snippet}

    {#snippet tarjetaCaratula(
      titulo: string,
      sub: string,
      url: string,
      placeholder: 'album' | 'cancion'
    )}
      <span class="caratula">
        {#if url}<img src={url} alt="" loading="lazy" />{:else}<Icon
            nombre={placeholder}
            tamano={32}
          />{/if}
      </span>
      <strong>{titulo}</strong>
      <span class="sub">{sub}</span>
    {/snippet}

    {#if datos.playlistsDestacadas.length > 0}
      {@render carruselCabecera(t.playlists, t.playlistsSub)}
      <ul class="fila">
        {#each datos.playlistsDestacadas as p (p.id)}
          <li>
            <div class="tarjeta">
              <a href={`/playlists/ver?id=${p.id}`} class="enlace"><Mosaico pistas={p.mosaico} /></a
              >
              <strong>{p.nombre}</strong>
              <span class="sub">{p.etiqueta} · {textos.biblioteca.cuentaPistas(p.numPistas)}</span>
              <button
                type="button"
                class="play flotante"
                aria-label={`${t.reproducir} ${p.nombre}`}
                onclick={() => reproducirPlaylist(p.id, 0)}
              >
                <Icon nombre="reproducir" tamano={16} />
              </button>
            </div>
          </li>
        {/each}
      </ul>
    {/if}

    {#snippet carruselAlbumes(titulo: string, sub: string, lista: Inicio['albumesQueGustan'])}
      {#if lista.length > 0}
        {@render carruselCabecera(titulo, sub)}
        <ul class="fila">
          {#each lista as a (a.id)}
            <li>
              <a class="tarjeta enlace" href={`/biblioteca/album?id=${a.id}`}>
                {@render tarjetaCaratula(
                  a.titulo,
                  a.artista,
                  a.tienePortada ? urlPortada('album', a.id, 320) : '',
                  'album'
                )}
              </a>
            </li>
          {/each}
        </ul>
      {/if}
    {/snippet}

    {@render carruselAlbumes(t.queGustan, t.queGustanSub, datos.albumesQueGustan)}
    {@render carruselAlbumes(t.masEscuchados, t.masEscuchadosSub, datos.albumesMasEscuchados)}

    {#if datos.artistasQueSuenan.length > 0}
      {@render carruselCabecera(t.artistas10, t.artistasSub)}
      <ul class="fila">
        {#each datos.artistasQueSuenan as a (a.id)}
          <li>
            <a class="tarjeta enlace centrada" href={`/biblioteca/artista?id=${a.id}`}>
              <span class="caratula redonda">
                {#if a.tieneImagen}<img
                    src={urlPortada('artista', a.id, 320)}
                    alt=""
                    loading="lazy"
                  />{:else}<Icon nombre="artista" tamano={32} />{/if}
              </span>
              <strong>{a.nombre}</strong>
            </a>
          </li>
        {/each}
      </ul>
    {/if}

    {#if datos.ultimosAnadidos.length > 0}
      {@render carruselCabecera(t.anadidos, t.anadidosSub)}
      <ul class="fila">
        {#each datos.ultimosAnadidos as p, k (p.id)}
          <li>
            <button type="button" class="tarjeta" onclick={() => reproducir(idsUltimos, k)}>
              {@render tarjetaCaratula(
                p.titulo,
                p.artista,
                p.tienePortada ? urlPortada('pista', p.id, 320) : '',
                'cancion'
              )}
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  {/if}
</section>

<style>
  .inicio {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
  }

  .saludo {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--ns-espacio-4);
    flex-wrap: wrap;
  }

  .saludo-texto {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
  }

  .saludo h1 {
    margin: var(--ns-espacio-3) 0 0;
    font-size: clamp(var(--ns-texto-2xl), 4vw, 3.25rem);
    line-height: 1.1;
  }

  .saludo p,
  .seccion-sub,
  .sub {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .sub {
    font-size: var(--ns-texto-xs);
  }

  .vacia {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--ns-espacio-2);
    padding: var(--ns-espacio-7);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    color: var(--m3c-primary);
    text-align: center;
  }

  .vacia h2 {
    margin: 0;
    color: var(--m3c-on-surface);
  }

  .heroe {
    display: grid;
    grid-template-columns: minmax(0, 2.3fr) minmax(0, 1fr);
    gap: var(--ns-espacio-5);
  }

  .izquierda {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
  }

  .cifras {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--ns-espacio-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .cifras li {
    display: flex;
    padding: 0;
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container);
    color: var(--m3c-primary);
    overflow: hidden;
  }

  .cifra-enlace,
  .cifra-estatica {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--ns-espacio-1);
    width: 100%;
    height: 100%;
    padding: var(--ns-espacio-4);
    color: inherit;
    text-decoration: none;
    transition: background-color var(--ns-duracion-corta) var(--ns-curva);
  }

  .cifra-enlace:hover {
    background: var(--m3c-surface-container-high);
  }

  .cifras strong {
    color: var(--m3c-on-surface);
    font-size: var(--ns-texto-lg);
  }

  .cifras span {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .retomar,
  .tarjeta-pista,
  .fila-top {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    width: 100%;
    padding: var(--ns-espacio-3);
    border: none;
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .retomar {
    flex: 1;
    padding: var(--ns-espacio-4);
  }

  .retomar:hover,
  .tarjeta-pista:hover,
  .fila-top:hover {
    background: var(--m3c-surface-container-high);
  }

  .mini-portada {
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    width: 3.5rem;
    height: 3.5rem;
    overflow: hidden;
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-primary);
  }

  .mini-portada img,
  .caratula img,
  .destacado img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .texto {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 0.125rem;
    min-width: 0;
  }

  .texto strong,
  .texto .sub,
  .tarjeta strong,
  .tarjeta .sub {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .etiqueta {
    color: var(--m3c-primary);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .play {
    display: grid;
    place-items: center;
    width: 2.5rem;
    height: 2.5rem;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
    cursor: pointer;
  }

  .destacado {
    position: relative;
    min-height: 18rem;
    overflow: hidden;
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-high);
  }

  .destacado img {
    position: absolute;
    inset: 0;
  }

  .velo {
    position: absolute;
    inset: auto 0 0 0;
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    padding: var(--ns-espacio-4);
    background: linear-gradient(to top, var(--m3c-surface-container-lowest), transparent);
  }

  .velo h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
  }

  .botones {
    display: flex;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-2);
  }

  .boton {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-1);
    height: 2.5rem;
    padding: 0 var(--ns-espacio-4);
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-weight: 700;
    text-decoration: none;
    cursor: pointer;
  }

  .boton.relleno {
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .seccion {
    margin: var(--ns-espacio-5) 0 0;
    font-size: var(--ns-texto-lg);
  }

  .vuelve {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--ns-espacio-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .vuelve li.grande {
    grid-column: span 2;
    grid-row: span 2;
  }

  .vuelve li.grande .tarjeta-pista {
    height: 100%;
  }

  .vuelve li.grande .mini-portada {
    width: 11rem;
    height: 11rem;
  }

  .top {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .fila-top {
    background: none;
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
  }

  .numero {
    width: 2rem;
    color: var(--m3c-primary);
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }

  .fila-top .mini-portada {
    width: 2.75rem;
    height: 2.75rem;
  }

  .fila {
    display: grid;
    grid-auto-columns: 10rem;
    grid-auto-flow: column;
    gap: var(--ns-espacio-3);
    margin: 0;
    padding: 0 0 var(--ns-espacio-2);
    overflow-x: auto;
    list-style: none;
    scroll-snap-type: x mandatory;
    scroll-behavior: smooth;
  }

  .fila li {
    scroll-snap-align: start;
  }

  .cabecera-carrusel {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--ns-espacio-3);
    margin-top: var(--ns-espacio-5);
  }

  .cabecera-carrusel .seccion {
    margin-top: 0;
  }

  .controles-carrusel {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
  }

  .boton-avance {
    display: grid;
    place-items: center;
    width: 2rem;
    height: 2rem;
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    cursor: pointer;
    transition: background 120ms ease;
  }

  .boton-avance:hover {
    background: var(--m3c-surface-container-high);
  }

  .tarjeta {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    width: 100%;
    padding: var(--ns-espacio-2);
    border: none;
    border-radius: var(--ns-radio-md);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    text-align: left;
    text-decoration: none;
    cursor: pointer;
  }

  .tarjeta:hover {
    background: var(--m3c-surface-container);
  }

  .centrada {
    align-items: center;
    text-align: center;
  }

  .caratula {
    display: grid;
    place-items: center;
    width: 100%;
    aspect-ratio: 1;
    overflow: hidden;
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
  }

  .caratula.redonda {
    border-radius: var(--ns-radio-pleno);
  }

  .flotante {
    position: absolute;
    top: 7rem;
    right: var(--ns-espacio-3);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .enlace {
    color: inherit;
    text-decoration: none;
  }

  @container carcasa (max-width: 70rem) {
    .heroe {
      grid-template-columns: minmax(0, 1fr);
    }

    .destacado {
      display: none;
    }

    .cifras {
      grid-template-columns: repeat(2, 1fr);
    }
  }
</style>
