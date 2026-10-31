<!--
  La reproducción expandida (`VistaReproduccionExpandida.qml` y `VistaLyrics.qml` de
  la V1): la portada grande, título, artista y álbum con sus fichas, sobre un fondo
  del color de la portada. Con `?letras`, las letras ocupan la derecha: la línea
  que suena resaltada y en el centro, y cada línea lleva a su segundo.

  El fondo es una paleta de Material generada desde el color de la portada y
  aplicada solo a esta vista: así no hay colores escritos a mano y el texto sigue
  teniendo contraste.
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { aparienciaActual } from '$core/apariencia.svelte';
  import { ambienteDePista, type Letra, letraDePista, urlPortada } from '$core/ipc';
  import { formatoTiempo, reproductor } from '$core/reproductor.svelte';
  import { textos } from '$lib/i18n';
  import Icon from '$ui/Icon.svelte';
  import { aplicarApariencia, semillaDesdeHsl } from '$ui/tema';

  const t = textos.reproduciendo;
  const conLetras = $derived(page.url.searchParams.has('letras'));
  const pista = $derived(reproductor.pista);

  let modoLetras = $state<'dividido' | 'centrado'>('dividido');
  let vista: HTMLElement | undefined = $state();
  let letra = $state<Letra>({ sincronizada: [], plana: [] });
  let rota = $state(false);

  $effect(() => {
    const id = pista?.id;
    rota = false;
    if (id === undefined || !vista) return;
    const destino = vista;
    void letraDePista(id).then((l) => (letra = l));
    // El color de la portada es una opción (enmienda de ADR-008); sin ella, el tema.
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
  $effect(() => {
    const i = activa;
    if (i < 0 || !lista || !contenedorLetras) return;
    const nodo = lista.children[i] as HTMLElement | undefined;
    if (!nodo) return;
    const objetivo = nodo.offsetTop - contenedorLetras.clientHeight / 2 + nodo.clientHeight / 2;
    contenedorLetras.scrollTo({ top: Math.max(0, objetivo), behavior: 'smooth' });
  });
</script>

<section
  class="vista"
  class:con-letras={conLetras}
  class:letras-centradas={conLetras && modoLetras === 'centrado'}
  bind:this={vista}
>
  <div class="cabecera-vista">
    <button type="button" class="volver" onclick={() => history.back()}>
      <Icon nombre="atras" tamano={18} />{t.volver}
    </button>
    {#if conLetras && modoLetras === 'centrado' && pista}
      <div class="pista-compacta" aria-hidden="true">
        <span class="titulo-compacto">{pista.titulo}</span>
        <span>·</span>
        <span>{pista.artista}</span>
      </div>
    {/if}
    {#if conLetras}
      <button
        type="button"
        class="conmutador-modo"
        onclick={() => (modoLetras = modoLetras === 'dividido' ? 'centrado' : 'dividido')}
        aria-label={modoLetras === 'centrado' ? t.modoDividido : t.modoCentrado}
        title={modoLetras === 'centrado' ? t.modoDividido : t.modoCentrado}
      >
        <Icon nombre={modoLetras === 'centrado' ? 'cuadricula' : 'lista'} tamano={18} />
        <span>{modoLetras === 'centrado' ? t.modoDividido : t.modoCentrado}</span>
      </button>
    {/if}
  </div>

  {#if !pista}
    <p class="vacio">{t.nadaSonando}</p>
  {:else}
    <div class="principal">
      <div class="portada">
        {#if pista.tienePortada && !rota}
          <img src={urlPortada('pista', pista.id, 640)} alt="" onerror={() => (rota = true)} />
        {:else}
          <Icon nombre="cancion" tamano={96} />
        {/if}
      </div>
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
        <span class="album">{pista.album}</span>
        <div class="fichas">
          {#if pista.album}<span class="ficha">{t.album(pista.album)}</span>{/if}
          {#if pista.anio}<span class="ficha">{t.anio(pista.anio)}</span>{/if}
          <span class="ficha">{t.duracion(formatoTiempo(pista.duracionSeg))}</span>
        </div>
      </div>
    </div>

    {#if conLetras}
      <aside class="letras" aria-label={t.letras} bind:this={contenedorLetras}>
        {#if letra.sincronizada.length > 0}
          <ol bind:this={lista}>
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
          <p class="vacio">{t.sinLetra}</p>
        {/if}
      </aside>
    {/if}
  {/if}
</section>

<style>
  .vista {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
    gap: var(--ns-espacio-4);
    height: calc(100% + var(--ns-espacio-2) + var(--ns-espacio-6));
    max-height: calc(100% + var(--ns-espacio-2) + var(--ns-espacio-6));
    box-sizing: border-box;
    overflow: hidden;
    margin: calc(-1 * var(--ns-espacio-2)) calc(-1 * var(--ns-espacio-5))
      calc(-1 * var(--ns-espacio-6));
    padding: var(--ns-espacio-4) var(--ns-espacio-6);
    background: radial-gradient(
      circle at 50% 25%,
      var(--m3c-primary-container),
      var(--m3c-surface-container-low)
    );
    color: var(--m3c-on-surface);
  }

  .vista.con-letras {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .vista.letras-centradas {
    grid-template-columns: minmax(0, 1fr);
  }

  .cabecera-vista {
    grid-column: 1 / -1;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-4);
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
    cursor: pointer;
  }

  .conmutador-modo:hover {
    background: var(--m3c-surface-container-high);
  }

  .volver {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    border: none;
    background: none;
    color: var(--m3c-on-surface-variant);
    font: inherit;
    font-size: var(--ns-texto-sm);
    cursor: pointer;
  }

  .principal {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-6);
    min-width: 0;
  }

  .con-letras .principal {
    flex-direction: column;
    align-items: flex-start;
    justify-content: center;
  }

  .portada {
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    width: min(40vh, 26rem);
    aspect-ratio: 1;
    overflow: hidden;
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-primary);
  }

  .portada img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .datos {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--ns-espacio-2);
    min-width: 0;
  }

  h1 {
    margin: 0;
    font-size: clamp(var(--ns-texto-2xl), 5vw, 4rem);
    line-height: 1.05;
  }

  .artista {
    padding: 0;
    border: none;
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-xl);
    font-weight: 700;
    cursor: pointer;
  }

  .album {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-lg);
  }

  .fichas {
    display: flex;
    flex-wrap: wrap;
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

  .letras {
    position: relative;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
    padding: 30vh 0;
  }

  ol {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .linea {
    display: block;
    width: 100%;
    padding: var(--ns-espacio-2) 0;
    border: none;
    background: none;
    color: var(--m3c-on-surface-variant);
    font: inherit;
    font-size: var(--ns-texto-xl);
    font-weight: 700;
    text-align: left;
    opacity: 0.55;
    cursor: pointer;
    transition:
      opacity var(--ns-duracion-media) var(--ns-curva),
      color var(--ns-duracion-media) var(--ns-curva);
  }

  .linea.pasada {
    opacity: 0.4;
  }

  .linea.activa {
    color: var(--m3c-on-surface);
    opacity: 1;
  }

  .plana p {
    margin: 0 0 var(--ns-espacio-2);
    font-size: var(--ns-texto-lg);
  }

  .vacio {
    color: var(--m3c-on-surface-variant);
  }

  .vista.letras-centradas .principal {
    display: none;
  }

  .vista.letras-centradas .letras {
    max-width: 48rem;
    margin: 0 auto;
    width: 100%;
    text-align: center;
  }

  .vista.letras-centradas .linea {
    font-size: var(--ns-texto-2xl);
    text-align: center;
  }

  .vista.letras-centradas .plana p {
    text-align: center;
  }
</style>
