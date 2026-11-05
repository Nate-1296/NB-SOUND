<!--
  Inicio, con la disposición de la V1 (`VistaInicio.qml`): el saludo, las cifras
  de la biblioteca, Retomar reproducción y el álbum destacado del día; después
  "Vuelve a tu música", el top 10 y las filas de playlists, álbumes, artistas y
  últimos añadidos. Sin biblioteca, invita a importar.

  La V1 animaba unas barras en la cabecera aunque no sonara nada; aquí no hay
  animación en reposo (ADR-008).
-->
<script lang="ts">
  import { cambios } from '#lib/core/cambios.svelte.ts';
  import { goto } from '$app/navigation';
  import { aparienciaActual } from '#lib/core/apariencia.svelte.ts';
  import {
    type Inicio,
    inicio,
    reproducirLista,
    reproducirPlaylist,
    urlPortada
  } from '#lib/core/ipc/index.ts';
  import { formatoTiempo, reproductor } from '#lib/core/reproductor.svelte.ts';
  import { duracionDetallada } from '#lib/core/formato.ts';
  import { textos } from '#lib/i18n/index.ts';
  import Icon from '#lib/ui/Icon.svelte';
  import Mosaico from '#lib/ui/playlists/Mosaico.svelte';

  const t = textos.inicio;
  let datos = $state<Inicio | null>(null);

  $effect(() => {
    void inicio().then((d) => (datos = d));
    void cambios.version;
  });

  function al<T>(lista: readonly T[]): T {
    return lista[Math.floor(Math.random() * lista.length)] as T;
  }

  /** Un saludo de la V1, al azar, según la hora y si hay nombre. */
  const saludo = $derived.by(() => {
    const nombre = aparienciaActual.actual.nombreUsuario;
    if (!nombre) return al(t.saludosSinNombre);
    const hora = new Date().getHours();
    const lista =
      hora < 6
        ? t.saludosMadrugada
        : hora < 12
          ? t.saludosManana
          : hora < 19
            ? t.saludosTarde
            : t.saludosNoche;
    return al(lista)(nombre);
  });

  const pistaRetomar = $derived.by(() => {
    if (reproductor.pista) return reproductor.pista;
    return datos?.paraVolver[0]?.pista ?? null;
  });
  const hayBiblioteca = $derived((datos?.cifras.pistas ?? 0) > 0);
  const idsVolver = $derived(datos?.paraVolver.map((x) => x.pista.id) ?? []);
  const idsTop = $derived(datos?.top.map((x) => x.pista.id) ?? []);
  const idsUltimos = $derived(datos?.ultimosAnadidos.map((x) => x.id) ?? []);

  function activarRetomar() {
    if (pistaRetomar && reproductor.pista?.id === pistaRetomar.id) {
      void reproductor.pausarReanudar();
    } else if (pistaRetomar) {
      reproducir([pistaRetomar.id]);
    }
  }

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
    fila?.scrollBy({
      left: direccion * Math.min(fila.clientWidth * 0.75, 480),
      behavior: 'smooth'
    });
  }
</script>

<section class="inicio">
  {#if datos && !hayBiblioteca}
    {#await import('#lib/ui/inicio/BienvenidaInicio.svelte') then m}
      <m.default />
    {/await}
  {:else}
    <header class="saludo">
      <h1>{saludo}</h1>
      {#if hayBiblioteca && datos}
        <p>{t.subtitulo}</p>
        <ul class="cifras">
          {#each [{ icono: 'cancion', valor: datos.cifras.pistas.toLocaleString('es'), rotulo: t.pistas }, { icono: 'artista', valor: datos.cifras.artistas.toLocaleString('es'), rotulo: t.artistas }, { icono: 'album', valor: datos.cifras.albumes.toLocaleString('es'), rotulo: t.albumes }, { icono: 'reloj', valor: duracionDetallada(datos.cifras.duracionSeg), rotulo: t.duracion }] as const as c (c.rotulo)}
            <li>
              <span class="cifra-icono"><Icon nombre={c.icono} tamano={18} /></span>
              <span class="cifra-datos"><strong>{c.valor}</strong><span>{c.rotulo}</span></span>
            </li>
          {/each}
        </ul>
      {/if}
    </header>
  {/if}

  {#if datos && hayBiblioteca}
    <div class="heroe">
      {#if pistaRetomar}
        <section class="marquesina" aria-labelledby="inicio-retomar">
          <div class="marquesina-info">
            <span class="marquesina-etiqueta">
              <Icon nombre="cancion" tamano={16} />
              {t.retomar}
            </span>
            <h2 id="inicio-retomar" class="marquesina-titulo">{pistaRetomar.titulo}</h2>
            <p class="marquesina-sub">
              <span>{pistaRetomar.artista}</span>
              {#if pistaRetomar.album}
                <span class="punto" aria-hidden="true">·</span>
                <span>{pistaRetomar.album}</span>
              {/if}
            </p>
            <div class="marquesina-acciones">
              <button type="button" class="boton relleno" onclick={activarRetomar}>
                <Icon
                  nombre={reproductor.pista?.id === pistaRetomar.id && reproductor.sonando
                    ? 'pausa'
                    : 'reproducir'}
                  tamano={18}
                />
                <span
                  >{reproductor.pista?.id === pistaRetomar.id && reproductor.sonando
                    ? textos.reproductor.pausar
                    : t.continuar}</span
                >
              </button>
              {#if pistaRetomar.albumId}
                <a class="boton contorno" href={`/biblioteca/album?id=${pistaRetomar.albumId}`}>
                  <Icon nombre="album" tamano={16} />
                  <span>{t.verAlbum}</span>
                </a>
              {/if}
            </div>
          </div>
          <div class="marquesina-portada-box" aria-hidden="true">
            <div class="marquesina-portada">
              {#if pistaRetomar.tienePortada}
                <img src={urlPortada('pista', pistaRetomar.id, 320)} alt="" />
              {:else}
                <Icon nombre="cancion" tamano={64} />
              {/if}
            </div>
          </div>
        </section>
      {/if}

      {#if datos.albumDestacado}
        {@const a = datos.albumDestacado}
        <section class="destacado" aria-labelledby="inicio-destacado">
          <div class="destacado-info">
            <span class="destacado-etiqueta">
              <Icon nombre="album" tamano={16} />
              {t.destacado}
            </span>
            <h2 id="inicio-destacado" class="destacado-titulo">{a.titulo}</h2>
            <p class="destacado-sub">
              <span>{a.artista}</span>
              <span class="punto" aria-hidden="true">·</span>
              <span>{textos.biblioteca.cuentaPistas(a.numPistas)}</span>
              {#if a.anio}
                <span class="punto" aria-hidden="true">·</span>
                <span>{a.anio}</span>
              {/if}
            </p>
            <div class="destacado-acciones">
              <button type="button" class="boton relleno" onclick={() => reproducirAlbum(a.id)}>
                <Icon nombre="reproducir" tamano={18} />
                <span>{t.reproducir}</span>
              </button>
              <a class="boton contorno" href={`/biblioteca/album?id=${a.id}`}>
                <Icon nombre="album" tamano={16} />
                <span>{t.verAlbum}</span>
              </a>
            </div>
          </div>
          <div class="destacado-portada-box" aria-hidden="true">
            <div class="destacado-portada">
              {#if a.tienePortada}
                <img src={urlPortada('album', a.id, 320)} alt="" />
              {:else}
                <Icon nombre="album" tamano={64} />
              {/if}
            </div>
          </div>
        </section>
      {/if}
    </div>

    {#if datos.paraVolver.length > 0}
      <h2 class="seccion">{t.vuelve}</h2>
      <p class="seccion-sub">{t.vuelveSub}</p>
      <ul class="vuelve">
        {#each datos.paraVolver.slice(0, 9) as e, k (e.pista.id)}
          <li class:destacada={k === 0}>
            <button type="button" class="tarjeta-pista" onclick={() => reproducir(idsVolver, k)}>
              <span class="mini-portada">
                {#if e.pista.tienePortada}
                  <img src={urlPortada('pista', e.pista.id, k === 0 ? 320 : 64)} alt="" />
                {:else}
                  <Icon nombre="cancion" tamano={k === 0 ? 40 : 18} />
                {/if}
              </span>
              <span class="texto">
                {#if k === 0}<span class="etiqueta">{t.ultima}</span>{/if}
                <strong>{e.pista.titulo}</strong>
                <span class="sub">{e.pista.artista} · {e.pista.album}</span>
                <span class="sub">{t.reproducciones(e.reproducciones)}</span>
              </span>
              <span class="play"><Icon nombre="reproducir" tamano={k === 0 ? 22 : 16} /></span>
            </button>
          </li>
        {/each}
      </ul>
    {/if}

    {#snippet tarjetaPodio(
      p: NonNullable<typeof datos>['top'][number],
      lugar: number,
      insignia: string,
      clase: 'oro' | 'plata' | 'bronce',
      ordenIdx: number
    )}
      <button
        type="button"
        class="podio-tarjeta podio-{lugar}"
        onclick={() => reproducir(idsTop, ordenIdx)}
      >
        <div class="podio-insignia {clase}">{insignia}</div>
        <div class="podio-portada-box">
          <span class="podio-portada">
            {#if p.pista.tienePortada}
              <img src={urlPortada('pista', p.pista.id, lugar === 1 ? 320 : 240)} alt="" />
            {:else}
              <Icon nombre="cancion" tamano={lugar === 1 ? 40 : 32} />
            {/if}
          </span>
          <span class="podio-play"><Icon nombre="reproducir" tamano={lugar === 1 ? 22 : 18} /></span
          >
        </div>
        <div class="podio-texto">
          <strong title={p.pista.titulo}>{p.pista.titulo}</strong>
          <span class="sub">{p.pista.artista}</span>
          <span class="podio-escuchas">{t.reproducciones(p.reproducciones)}</span>
        </div>
        <div class="podio-pedestal pedestal-{lugar}">
          <span class="pedestal-num">{lugar}</span>
        </div>
      </button>
    {/snippet}

    {#snippet itemTop(e: NonNullable<typeof datos>['top'][number], num: number, ordenIdx: number)}
      <li>
        <button type="button" class="fila-top" onclick={() => reproducir(idsTop, ordenIdx)}>
          <span class="numero">{String(num).padStart(2, '0')}</span>
          <span class="mini-portada">
            {#if e.pista.tienePortada}
              <img src={urlPortada('pista', e.pista.id, 64)} alt="" />
            {:else}
              <Icon nombre="cancion" tamano={16} />
            {/if}
          </span>
          <span class="texto">
            <strong>{e.pista.titulo}</strong>
            <span class="sub">{e.pista.artista}</span>
          </span>
          <span class="sub">{t.reproducciones(e.reproducciones)}</span>
          <span class="sub">{formatoTiempo(e.pista.duracionSeg)}</span>
        </button>
      </li>
    {/snippet}

    {#if datos.top.length > 0}
      <h2 class="seccion">{t.top}</h2>
      <p class="seccion-sub">{t.topSub}</p>

      {#if datos.top[0] && datos.top[1] && datos.top[2]}
        {@const p0 = datos.top[0]}
        {@const p1 = datos.top[1]}
        {@const p2 = datos.top[2]}
        <div class="podio">
          {@render tarjetaPodio(p1, 2, t.podio.lugar2, 'plata', 1)}
          {@render tarjetaPodio(p0, 1, t.podio.lugar1, 'oro', 0)}
          {@render tarjetaPodio(p2, 3, t.podio.lugar3, 'bronce', 2)}
        </div>

        {#if datos.top.length > 3}
          <ol class="top-resto" start="4">
            {#each datos.top.slice(3) as e, k (e.pista.id)}
              {@render itemTop(e, k + 4, k + 3)}
            {/each}
          </ol>
        {/if}
      {:else}
        <ol class="top">
          {#each datos.top as e, k (e.pista.id)}
            {@render itemTop(e, k + 1, k)}
          {/each}
        </ol>
      {/if}
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
            <Icon nombre="izquierda" tamano={18} />
          </button>
          <button
            type="button"
            class="boton-avance"
            aria-label={t.siguiente}
            onclick={(e) => desplazar(e.currentTarget, 1)}
          >
            <Icon nombre="derecha" tamano={18} />
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

  /* El saludo grande y las cifras de la biblioteca, como la cabecera de la V1. */
  .saludo {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    margin: var(--ns-espacio-3) 0 var(--ns-espacio-2);
  }

  .saludo h1 {
    margin: 0;
    max-width: 52rem;
    color: var(--m3c-on-surface);
    font-size: clamp(var(--ns-texto-xl), 3.2vw, var(--ns-texto-3xl));
    font-weight: 800;
    line-height: 1.1;
    letter-spacing: -0.01em;
    text-wrap: balance;
  }

  .cifras {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: var(--ns-espacio-3);
    margin: var(--ns-espacio-3) 0 0;
    padding: 0;
    list-style: none;
  }

  .cifras li {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-3) var(--ns-espacio-4);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container);
  }

  .cifra-icono {
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    width: 2.5rem;
    height: 2.5rem;
    border-radius: var(--ns-radio-pleno);
    background: color-mix(in srgb, var(--m3c-primary) 16%, transparent);
    color: var(--m3c-primary);
  }

  .cifra-datos {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .cifra-datos strong {
    color: var(--m3c-on-surface);
    font-size: var(--ns-texto-lg);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .cifra-datos span {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  /*
   * "Vuelve a tu música": la última, grande, ocupa dos columnas y dos filas, como
   * la tarjeta de la V1; las demás llenan la rejilla de tres sin dejar huecos.
   */
  .vuelve {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--ns-espacio-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .vuelve li {
    display: flex;
    min-width: 0;
  }

  .vuelve li.destacada {
    grid-column: span 2;
    grid-row: span 2;
  }

  .destacada .tarjeta-pista {
    gap: var(--ns-espacio-4);
    padding: var(--ns-espacio-4);
    background: linear-gradient(
      135deg,
      var(--m3c-surface-container) 0%,
      color-mix(in srgb, var(--m3c-surface-container-high) 70%, var(--m3c-primary-container)) 100%
    );
  }

  .destacada .mini-portada {
    width: 8.5rem;
    height: 8.5rem;
    border-radius: var(--ns-radio-md);
    box-shadow: 0 8px 20px var(--m3c-shadow);
  }

  .destacada .texto strong {
    font-size: var(--ns-texto-lg);
  }

  .destacada .play {
    width: 3rem;
    height: 3rem;
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
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

  .heroe {
    display: grid;
    grid-template-columns: minmax(0, 1.8fr) minmax(0, 1.2fr);
    gap: var(--ns-espacio-4);
  }

  .marquesina,
  .destacado {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-5);
    padding: var(--ns-espacio-5);
    border-radius: var(--ns-radio-xl);
    background: linear-gradient(
      135deg,
      var(--m3c-surface-container) 0%,
      color-mix(in srgb, var(--m3c-surface-container-high) 65%, var(--m3c-primary-container) 35%)
        100%
    );
    border: 1px solid var(--m3c-outline-variant);
    min-height: 14rem;
    overflow: hidden;
    box-shadow: 0 2px 10px color-mix(in srgb, var(--m3c-shadow) 35%, transparent);
  }

  .destacado {
    background: linear-gradient(
      135deg,
      var(--m3c-surface-container) 0%,
      color-mix(in srgb, var(--m3c-surface-container-high) 65%, var(--m3c-secondary-container) 35%)
        100%
    );
  }

  .marquesina-info,
  .destacado-info {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--ns-espacio-2);
    min-width: 0;
    flex: 1 1 auto;
  }

  .marquesina-etiqueta,
  .destacado-etiqueta {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    color: var(--m3c-primary);
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .marquesina-titulo,
  .destacado-titulo {
    margin: 0;
    font-size: clamp(var(--ns-texto-lg), 2.5vw, var(--ns-texto-xl));
    line-height: 1.15;
    font-weight: 700;
    color: var(--m3c-on-surface);
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  .marquesina-sub,
  .destacado-sub {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    flex-wrap: wrap;
  }

  .marquesina-sub .punto,
  .destacado-sub .punto {
    color: var(--m3c-outline);
  }

  .marquesina-acciones,
  .destacado-acciones {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-2);
    flex-wrap: wrap;
  }

  .marquesina-portada-box,
  .destacado-portada-box {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .marquesina-portada,
  .destacado-portada {
    width: 8.5rem;
    height: 8.5rem;
    border-radius: var(--ns-radio-lg);
    overflow: hidden;
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-primary);
    display: grid;
    place-items: center;
    border: 1px solid var(--m3c-outline-variant);
    box-shadow: 0 var(--ns-espacio-3) var(--ns-espacio-5) var(--m3c-shadow);
  }

  .marquesina-portada img,
  .destacado-portada img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .tarjeta-pista,
  .fila-top {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    width: 100%;
    padding: var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    text-align: left;
    cursor: pointer;
    transition:
      background-color var(--ns-duracion-corta) var(--ns-curva),
      border-color var(--ns-duracion-corta) var(--ns-curva),
      box-shadow var(--ns-duracion-corta) var(--ns-curva);
  }

  .tarjeta-pista:hover {
    background: var(--m3c-surface-container-high);
    border-color: var(--m3c-outline);
    box-shadow: 0 4px 12px var(--m3c-shadow);
  }

  .fila-top {
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border: none;
    border-radius: var(--ns-radio-md);
    background: transparent;
  }

  .fila-top:hover {
    background: var(--m3c-surface-container);
  }

  .boton.contorno {
    border: 1px solid var(--m3c-outline-variant);
    background: var(--m3c-surface-container-high);
  }

  .boton.contorno:hover {
    background: var(--m3c-surface-container-highest);
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

  .podio {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--ns-espacio-3);
    align-items: end;
    margin-top: var(--ns-espacio-2);
    margin-bottom: var(--ns-espacio-4);
  }

  .podio-tarjeta {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 100%;
    padding: var(--ns-espacio-3) var(--ns-espacio-3) 0;
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-xl) var(--ns-radio-xl) 0 0;
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    text-align: center;
    cursor: pointer;
    transition:
      background-color var(--ns-duracion-corta) var(--ns-curva),
      border-color var(--ns-duracion-corta) var(--ns-curva),
      box-shadow var(--ns-duracion-corta) var(--ns-curva);
  }

  .podio-tarjeta:hover {
    border-color: var(--m3c-outline);
    box-shadow: 0 var(--ns-espacio-3) var(--ns-espacio-5) var(--m3c-shadow);
  }

  .podio-1 {
    background: linear-gradient(
      180deg,
      color-mix(in srgb, var(--m3c-primary-container) 40%, var(--m3c-surface-container-high)) 0%,
      var(--m3c-surface-container) 100%
    );
    border-color: color-mix(in srgb, var(--m3c-primary) 50%, var(--m3c-outline-variant));
  }

  /* Solo el primero lleva color: con los tres teñidos, el podio pesaba más que la música. */
  .podio-2,
  .podio-3 {
    background: var(--m3c-surface-container);
  }

  .podio-insignia {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.125rem var(--ns-espacio-3);
    border-radius: var(--ns-radio-pleno);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin-bottom: var(--ns-espacio-2);
  }

  .podio-insignia.oro {
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .podio-insignia.plata {
    background: var(--m3c-secondary);
    color: var(--m3c-on-secondary);
  }

  .podio-insignia.bronce {
    background: var(--m3c-tertiary);
    color: var(--m3c-on-tertiary);
  }

  .podio-portada-box {
    position: relative;
    width: 6.5rem;
    height: 6.5rem;
    margin-bottom: var(--ns-espacio-2);
  }

  .podio-1 .podio-portada-box {
    width: 8rem;
    height: 8rem;
  }

  .podio-portada {
    display: grid;
    place-items: center;
    width: 100%;
    height: 100%;
    border-radius: var(--ns-radio-lg);
    overflow: hidden;
    background: var(--m3c-surface-container-highest);
    border: 1px solid var(--m3c-outline-variant);
    box-shadow: 0 var(--ns-espacio-1) var(--ns-espacio-3) var(--m3c-shadow);
  }

  .podio-portada img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .podio-play {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    background: color-mix(in srgb, var(--m3c-scrim) 40%, transparent);
    color: var(--m3c-on-primary);
    border-radius: var(--ns-radio-lg);
    opacity: 0;
    transition: opacity var(--ns-duracion-corta) var(--ns-curva);
  }

  .podio-tarjeta:hover .podio-play {
    opacity: 1;
  }

  .podio-texto {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    width: 100%;
    padding: 0 var(--ns-espacio-1);
    margin-bottom: var(--ns-espacio-3);
  }

  .podio-texto strong {
    font-size: var(--ns-texto-sm);
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .podio-1 .podio-texto strong {
    font-size: var(--ns-texto-md);
  }

  .podio-escuchas {
    font-size: var(--ns-texto-xs);
    color: var(--m3c-primary);
    font-weight: 600;
  }

  .podio-pedestal {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--ns-radio-sm) var(--ns-radio-sm) 0 0;
  }

  .pedestal-1 {
    height: 3rem;
    background: color-mix(
      in srgb,
      var(--m3c-primary-container) 80%,
      var(--m3c-surface-container-highest)
    );
    color: var(--m3c-on-primary-container);
  }

  .pedestal-2 {
    height: 2.25rem;
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
  }

  .pedestal-3 {
    height: 1.5rem;
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
  }

  .pedestal-num {
    font-size: var(--ns-texto-lg);
    font-weight: 900;
    line-height: 1;
    opacity: 0.85;
  }

  .top-resto {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--ns-espacio-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .top-resto li:first-child {
    grid-column: 1 / -1;
  }

  .top-resto li:first-child .fila-top {
    padding: var(--ns-espacio-3) var(--ns-espacio-4);
    background: color-mix(
      in srgb,
      var(--m3c-surface-container) 85%,
      var(--m3c-primary-container) 15%
    );
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
  }

  .top-resto li:first-child .fila-top:hover {
    background: var(--m3c-surface-container-high);
    border-color: var(--m3c-primary);
    box-shadow: 0 4px 12px var(--m3c-shadow);
  }

  .top {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    margin: 0;
    padding: 0;
    list-style: none;
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
    grid-auto-columns: 10.5rem;
    grid-auto-flow: column;
    gap: var(--ns-espacio-3);
    margin: 0;
    padding: 0 0 var(--ns-espacio-2);
    overflow-x: auto;
    list-style: none;
    scroll-snap-type: x mandatory;
    scroll-behavior: smooth;
    scrollbar-width: none;
    -ms-overflow-style: none;
  }

  .fila::-webkit-scrollbar {
    display: none;
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
    border: 1px solid transparent;
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-low);
    color: var(--m3c-on-surface);
    font: inherit;
    text-align: left;
    text-decoration: none;
    cursor: pointer;
    transition:
      background-color var(--ns-duracion-corta) var(--ns-curva),
      border-color var(--ns-duracion-corta) var(--ns-curva),
      box-shadow var(--ns-duracion-corta) var(--ns-curva);
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
    margin-bottom: var(--ns-espacio-1);
    overflow: hidden;
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
    box-shadow: 0 4px 14px var(--m3c-shadow);
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
  }

  @container carcasa (max-width: 70rem) {
    .cifras {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @container carcasa (max-width: 52rem) {
    .vuelve {
      grid-template-columns: minmax(0, 1fr);
    }

    .vuelve li.destacada {
      grid-column: auto;
      grid-row: auto;
    }

    .top-resto {
      grid-template-columns: minmax(0, 1fr);
    }

    .pedestal-1 {
      height: 2.25rem;
    }

    .pedestal-2 {
      height: 1.75rem;
    }

    .pedestal-3 {
      height: 1.25rem;
    }
  }
</style>
