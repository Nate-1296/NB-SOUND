<!--
  La reproducción expandida: la portada grande, título, artista y álbum con sus fichas,
  sobre un fondo dinámico del color de la portada.

  Ofrece dos modos limpios a pantalla completa:
  - Modo Portada: Arte del álbum protagónico con iluminación ambiental y metadatos.
  - Modo Letras: Letras inmersivas centradas vertical y horizontalmente que abarcan
    toda la vista, sincronizadas al milisegundo y desplazables.
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { aparienciaActual } from '#lib/core/apariencia.svelte.ts';
  import { pantalla } from '#lib/core/pantalla.svelte.ts';
  import { ambienteDePista, type Letra, letraDePista, urlPortada } from '#lib/core/ipc/index.ts';
  import { formatoTiempo, reproductor } from '#lib/core/reproductor.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import Icon from '#lib/ui/Icon.svelte';
  import { aplicarApariencia, semillaDesdeHsl } from '#lib/ui/tema.ts';

  const t = textos.reproduciendo;
  const pista = $derived(reproductor.pista);

  let modo = $state<'portada' | 'letras'>('portada');
  let vista: HTMLElement | undefined = $state();
  let letra = $state<Letra>({ sincronizada: [], plana: [] });
  let rota = $state(false);

  // Sincronizar el modo inicial o navegación con ?letras
  $effect(() => {
    modo = page.url.searchParams.has('letras') ? 'letras' : 'portada';
  });

  function alternarModo() {
    const nuevoModo = modo === 'portada' ? 'letras' : 'portada';
    modo = nuevoModo;
    const u = new URL(window.location.href);
    if (nuevoModo === 'letras') {
      u.searchParams.set('letras', '');
    } else {
      u.searchParams.delete('letras');
    }
    history.replaceState(history.state, '', u.pathname + u.search);
  }

  $effect(() => {
    const id = pista?.id;
    rota = false;
    if (id === undefined || !vista) return;
    const destino = vista;
    void letraDePista(id).then((l) => (letra = l));
    if (!aparienciaActual.actual.colorPorPortada) return;
    void ambienteDePista(id).then((a) =>
      aplicarApariencia(
        destino,
        { tema: 'oscuro', contraste: 'normal', semilla: semillaDesdeHsl(a.h, a.s, a.l) },
        true
      )
    );
  });

  /** La línea que suena: la última cuyo momento ya pasó. */
  const activa = $derived.by(() => {
    const ms = reproductor.posicion * 1000;
    let i = -1;
    for (const [k, linea] of letra.sincronizada.entries()) {
      if (linea.ms <= ms) i = k;
      else break;
    }
    return i;
  });

  let contenedorLetras: HTMLElement | undefined = $state();
  let lista: HTMLOListElement | undefined = $state();
  let letrasInicializadas = false;

  $effect(() => {
    if (modo !== 'letras') {
      letrasInicializadas = false;
    }
  });

  $effect(() => {
    const i = activa;
    if (i < 0 || !lista || !contenedorLetras || modo !== 'letras') return;
    const nodo = lista.children[i] as HTMLElement | undefined;
    if (!nodo) return;
    const objetivo = nodo.offsetTop - contenedorLetras.clientHeight / 2 + nodo.clientHeight / 2;
    const suave = letrasInicializadas;
    letrasInicializadas = true;
    contenedorLetras.scrollTo({
      top: Math.max(0, objetivo),
      behavior: suave ? 'smooth' : 'instant'
    });
  });

  function volver() {
    if (typeof window !== 'undefined' && window.history.length > 1) {
      window.history.back();
    } else {
      void goto('/');
    }
  }
</script>

<section class="vista" class:modo-letras={modo === 'letras'} bind:this={vista}>
  <header class="cabecera-vista" class:oculta={pantalla.completa && !pantalla.controlesVisibles}>
    <button type="button" class="volver" onclick={volver} title={t.volver}>
      <Icon nombre="atras" tamano={18} />
      <span>{t.volver}</span>
    </button>

    {#if pista}
      <div class="pista-compacta" aria-hidden="true">
        <span class="titulo-compacto">{pista.titulo}</span>
        <span>·</span>
        <span>{pista.artista}</span>
        {#if reproductor.instantanea.karaokeActivo}
          <span class="karaoke"><Icon nombre="microfono" tamano={14} />{t.karaoke}</span>
        {/if}
      </div>
    {/if}

    <button
      type="button"
      class="conmutador-modo"
      onclick={alternarModo}
      aria-label={modo === 'letras' ? t.verPortada : t.verLetras}
      title={modo === 'letras' ? t.verPortada : t.verLetras}
    >
      <Icon nombre={modo === 'letras' ? 'album' : 'letras'} tamano={18} />
      <span>{modo === 'letras' ? t.verPortada : t.verLetras}</span>
    </button>
  </header>

  {#if !pista}
    <div class="vacio-contenedor">
      <Icon nombre="cancion" tamano={48} />
      <p class="vacio">{t.nadaSonando}</p>
    </div>
  {:else if modo === 'portada'}
    <div class="vista-portada">
      <button
        type="button"
        class="portada-contenedor"
        onclick={alternarModo}
        title={t.verLetras}
        aria-label={t.verLetras}
      >
        <div class="portada">
          {#if pista.tienePortada && !rota}
            <img src={urlPortada('pista', pista.id, 640)} alt="" onerror={() => (rota = true)} />
          {:else}
            <Icon nombre="cancion" tamano={96} />
          {/if}
        </div>
      </button>

      <div class="datos">
        <h1>{pista.titulo}</h1>
        <button
          type="button"
          class="artista"
          disabled={pista.artistaId === null}
          onclick={() => goto(`/biblioteca/artista?id=${pista.artistaId}`)}
        >
          {pista.artista}
        </button>
        {#if pista.album}
          <span class="album">{pista.album}</span>
        {/if}
        <div class="fichas">
          {#if pista.album}<span class="ficha">{t.album(pista.album)}</span>{/if}
          {#if pista.anio}<span class="ficha">{t.anio(pista.anio)}</span>{/if}
          <span class="ficha">{t.duracion(formatoTiempo(pista.duracionSeg))}</span>
        </div>
      </div>
    </div>
  {:else}
    <aside class="vista-letras" aria-label={t.letras} bind:this={contenedorLetras}>
      {#if letra.sincronizada.length > 0}
        <ol bind:this={lista} class="lista-letras">
          {#each letra.sincronizada as linea, i (`${linea.ms}-${i}`)}
            <li>
              <button
                type="button"
                class="linea"
                class:activa={i === activa}
                class:pasada={i < activa}
                aria-current={i === activa ? 'true' : undefined}
                title={t.irA(formatoTiempo(linea.ms / 1000))}
                onclick={() => reproductor.buscar(linea.ms / 1000)}
              >
                {linea.texto}
              </button>
            </li>
          {/each}
        </ol>
      {:else if letra.plana.length > 0}
        <div class="plana">
          {#each letra.plana as linea, i (i)}<p>{linea}</p>{/each}
        </div>
      {:else}
        <div class="vacio-contenedor">
          <Icon nombre="letras" tamano={40} />
          <p class="vacio">{t.sinLetra}</p>
        </div>
      {/if}
    </aside>
  {/if}
</section>

<style>
  .vista {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
    gap: var(--ns-espacio-4);
    height: 100%;
    max-height: 100%;
    box-sizing: border-box;
    overflow: hidden;
    padding: var(--ns-espacio-4) var(--ns-espacio-6);
    background: radial-gradient(
      circle at 50% 25%,
      var(--m3c-primary-container),
      var(--m3c-surface) 80%
    );
    color: var(--m3c-on-surface);
  }

  /* En karaoke la voz no suena: la cabecera lo dice, que la letra es para cantarla. */
  .karaoke {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-1);
    margin-left: var(--ns-espacio-2);
    padding: 0 var(--ns-espacio-2);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
  }

  .cabecera-vista {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-4);
    z-index: 2;
    transition:
      opacity 300ms var(--ns-curva),
      transform 300ms var(--ns-curva);
  }

  .cabecera-vista.oculta {
    opacity: 0;
    transform: translateY(-100%);
    pointer-events: none;
  }

  .pista-compacta {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    font-size: var(--ns-texto-sm);
    color: var(--m3c-on-surface-variant);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    padding: var(--ns-espacio-1) var(--ns-espacio-3);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container);
    border: 1px solid var(--m3c-outline-variant);
  }

  .titulo-compacto {
    color: var(--m3c-on-surface);
    font-weight: 700;
  }

  .conmutador-modo {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    padding: var(--ns-espacio-1) var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-xs);
    font-weight: 600;
    cursor: pointer;
    transition: background var(--ns-duracion-corta) var(--ns-curva);
  }

  .conmutador-modo:hover {
    background: var(--m3c-surface-container-high);
  }

  .volver {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    padding: var(--ns-espacio-1) var(--ns-espacio-3);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    cursor: pointer;
    transition: background var(--ns-duracion-corta) var(--ns-curva);
  }

  .volver:hover {
    background: var(--m3c-surface-container-high);
  }

  .vista-portada {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--ns-espacio-5);
    text-align: center;
    max-width: 48rem;
    margin: 0 auto;
    width: 100%;
    min-height: 0;
  }

  .portada-contenedor {
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    border-radius: var(--ns-radio-lg);
  }

  .portada-contenedor:hover .portada {
    transform: scale(1.02);
  }

  .portada {
    display: grid;
    place-items: center;
    width: min(44vh, 26rem);
    aspect-ratio: 1;
    overflow: hidden;
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-primary);
    border: 1px solid var(--m3c-outline-variant);
    box-shadow: 0 var(--ns-espacio-4) var(--ns-espacio-6) var(--m3c-shadow);
    transition:
      transform var(--ns-duracion-media) var(--ns-curva),
      box-shadow var(--ns-duracion-media) var(--ns-curva);
  }

  .portada img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .datos {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--ns-espacio-2);
    min-width: 0;
  }

  h1 {
    margin: 0;
    font-size: clamp(var(--ns-texto-xl), 4vw, var(--ns-texto-2xl));
    line-height: 1.1;
  }

  .artista {
    padding: 0;
    border: none;
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-lg);
    font-weight: 700;
    cursor: pointer;
  }

  .album {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-md);
  }

  .fichas {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-2);
  }

  .ficha {
    padding: var(--ns-espacio-1) var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
  }

  /* Vista de letras centradas */
  .vista-letras {
    position: relative;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
    padding: 35vh 0;
    width: 100%;
  }

  .lista-letras {
    margin: 0 auto;
    padding: 0;
    list-style: none;
    max-width: 52rem;
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--ns-espacio-3);
  }

  .lista-letras li {
    width: 100%;
    display: flex;
    justify-content: center;
  }

  .linea {
    display: inline-block;
    max-width: 48rem;
    padding: var(--ns-espacio-2) var(--ns-espacio-4);
    border: none;
    background: none;
    color: var(--m3c-on-surface-variant);
    font: inherit;
    font-size: var(--ns-texto-xl);
    font-weight: 600;
    text-align: center;
    opacity: 0.35;
    cursor: pointer;
    border-radius: var(--ns-radio-md);
    transition:
      opacity var(--ns-duracion-media) var(--ns-curva),
      color var(--ns-duracion-media) var(--ns-curva),
      transform var(--ns-duracion-media) var(--ns-curva);
  }

  .linea:hover {
    opacity: 0.85;
  }

  .linea.activa {
    color: var(--m3c-on-surface);
    opacity: 1;
    font-size: var(--ns-texto-2xl);
    font-weight: 700;
    transform: scale(1.04);
  }

  .plana {
    max-width: 48rem;
    margin: 0 auto;
    text-align: center;
    padding: var(--ns-espacio-6) 0;
  }

  .plana p {
    margin: 0 0 var(--ns-espacio-3);
    font-size: var(--ns-texto-lg);
    line-height: 1.6;
  }

  .vacio-contenedor {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--ns-espacio-3);
    margin: auto;
    color: var(--m3c-on-surface-variant);
    text-align: center;
  }

  .vacio {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-md);
  }
</style>
