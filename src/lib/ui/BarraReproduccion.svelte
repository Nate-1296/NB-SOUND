<!--
  @component
  La barra de reproducción permanente, con la disposición de la V1
  (`legado/ui/qml/componentes/BarraReproduccion.qml`): la pista a la izquierda, los
  controles y el progreso en el centro, y a la derecha letras, karaoke, cola y
  volumen. El micrófono del karaoke vive aquí y no en una vista propia (ADR-007).
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import {
    abrirMinirreproductor,
    alCambiarElKaraoke,
    alternarPantallaCompleta,
    estaEnPantallaCompleta,
    karaokeEstado,
    karaokePreparar,
    urlPortada
  } from '$core/ipc';
  import { formatoTiempo, reproductor } from '$core/reproductor.svelte';
  import { textos } from '$lib/i18n';

  import SelectorDestino from './dispositivos/SelectorDestino.svelte';
  import FormaDeOnda from './FormaDeOnda.svelte';
  import Icon from './Icon.svelte';
  import PanelCola from './PanelCola.svelte';

  const t = textos.reproductor;
  const i = $derived(reproductor.instantanea);
  const pista = $derived(reproductor.pista);
  const hayPista = $derived(i.pistaId !== null);

  /** Mientras se arrastra, la barra sigue al dedo y no a la reproducción. */
  let arrastrando = $state<number | null>(null);
  const posicion = $derived(arrastrando ?? reproductor.posicion);

  let portadaRota = $state(false);
  $effect(() => {
    void i.pistaId;
    portadaRota = false;
  });

  // La cola, en la capa superior sobre la barra.
  let capaCola: HTMLDivElement | undefined = $state();
  let colaAbierta = $state(false);
  let botonCola: HTMLButtonElement | undefined = $state();
  function alternarCola() {
    if (!capaCola || !botonCola) return;
    if (colaAbierta) {
      capaCola.hidePopover();
      return;
    }
    const r = botonCola.getBoundingClientRect();
    capaCola.style.right = `${Math.max(8, window.innerWidth - r.right)}px`;
    capaCola.style.bottom = `${window.innerHeight - r.top + 8}px`;
    capaCola.showPopover();
  }

  // El micrófono (F5.2.2): con instrumental alterna; sin él, lo prepara mientras
  // suena el original; sin el agregado, lo ofrece ahí mismo (F5.1.4).
  let preparando = $state<number | null>(null);
  let ofertaKaraoke = $state(false);
  $effect(() => {
    void i.pistaId;
    preparando = null;
  });
  $effect(() => {
    const quitar = alCambiarElKaraoke(async () => {
      const e = await karaokeEstado();
      if (e.preparando && e.preparando.pista === i.pistaId) {
        preparando = e.preparando.fraccion;
        const pct = Math.round((preparando ?? 0) * 100);
        window.dispatchEvent(
          new CustomEvent('ns:notificacion', {
            detail: {
              tipo: 'progreso',
              id: 'karaoke-progreso',
              mensaje: t.karaokePreparando(pct),
              progreso: pct
            }
          })
        );
      } else if (preparando !== null && !e.pendientes) {
        preparando = null;
        window.dispatchEvent(
          new CustomEvent('ns:notificacion', {
            detail: { tipo: 'quitar', id: 'karaoke-progreso' }
          })
        );
        window.dispatchEvent(
          new CustomEvent('ns:notificacion', {
            detail: { tipo: 'exito', mensaje: t.karaokeListo }
          })
        );
      }
    });
    return () => void quitar.then((f) => f());
  });
  async function microfono() {
    if (i.karaokeDisponible) return reproductor.alternarKaraoke();
    if (i.pistaId === null) return;
    try {
      const e = await karaokeEstado();
      if (!e.instalado) {
        ofertaKaraoke = true;
        return;
      }
      await karaokePreparar([i.pistaId]);
      preparando ??= 0;
      window.dispatchEvent(
        new CustomEvent('ns:notificacion', {
          detail: {
            tipo: 'progreso',
            id: 'karaoke-progreso',
            mensaje: t.karaokePreparando(0),
            progreso: 0
          }
        })
      );
    } catch {
      window.dispatchEvent(
        new CustomEvent('ns:notificacion', {
          detail: { tipo: 'error', mensaje: t.karaokeError }
        })
      );
    }
  }

  /** Letras y pantalla completa abren la vista de reproducción; otra vez, vuelven. */
  function abrirVista(letras: boolean) {
    if (i.ciego) return;
    const ruta = page.url.pathname === '/reproduciendo';
    const tieneLetras = page.url.searchParams.has('letras');
    if (ruta && tieneLetras === letras) {
      history.back();
      return;
    }
    void goto(letras ? '/reproduciendo?letras' : '/reproduciendo', { replace: ruta });
  }

  // Los atajos de la carcasa (`atajos.ts`) piden la cola y la vista ampliada con
  // estos eventos: la barra es la dueña de las dos.
  let enPantallaCompleta = $state(false);
  async function conmutarPantallaCompleta() {
    enPantallaCompleta = await alternarPantallaCompleta();
  }

  $effect(() => {
    const cola = () => alternarCola();
    const vista = (e: Event) => abrirVista((e as CustomEvent<{ letras: boolean }>).detail.letras);
    const actualizarPantalla = () => {
      void estaEnPantallaCompleta().then((v) => (enPantallaCompleta = v));
    };
    actualizarPantalla();
    window.addEventListener('ns:cola', cola);
    window.addEventListener('ns:vista', vista);
    window.addEventListener('ns:pantalla-completa', actualizarPantalla);
    window.addEventListener('resize', actualizarPantalla);
    window.addEventListener('fullscreenchange', actualizarPantalla);
    return () => {
      window.removeEventListener('ns:cola', cola);
      window.removeEventListener('ns:vista', vista);
      window.removeEventListener('ns:pantalla-completa', actualizarPantalla);
      window.removeEventListener('resize', actualizarPantalla);
      window.removeEventListener('fullscreenchange', actualizarPantalla);
    };
  });

  function soltar(e: Event) {
    const valor = Number((e.currentTarget as HTMLInputElement).value);
    arrastrando = null;
    void reproductor.buscar(valor);
  }
</script>

<section class="reproductor" aria-label={t.region}>
  <div class="pista">
    <button
      type="button"
      class="portada"
      disabled={!hayPista || i.ciego}
      onclick={() => abrirVista(false)}
      aria-label={t.expandir}
    >
      {#if i.ciego}
        <Icon nombre="aCiegas" tamano={24} />
      {:else if pista?.tienePortada && !portadaRota}
        <img
          src={urlPortada('pista', pista.id, 160)}
          alt=""
          width="56"
          height="56"
          onerror={() => (portadaRota = true)}
        />
      {:else}
        <Icon nombre="cancion" tamano={24} />
      {/if}
    </button>
    <div class="datos">
      {#if i.ciego}
        <span class="titulo">{t.aCiegas}</span>
        <span class="artista">{t.adivina}</span>
      {:else if pista}
        <button type="button" class="titulo enlace-titulo" onclick={() => abrirVista(false)}>
          {pista.titulo}
        </button>
        {#if pista.artistaId !== null}
          <a href="/biblioteca/artista?id={pista.artistaId}" class="artista enlace">
            {pista.artista}
          </a>
        {:else}
          <span class="artista">{pista.artista}</span>
        {/if}
        {#if pista.albumId !== null}
          <a href="/biblioteca/album?id={pista.albumId}" class="album enlace">
            {pista.album}
          </a>
        {:else}
          <span class="album">{pista.album}</span>
        {/if}
      {:else}
        <span class="titulo">{t.nadaSonando}</span>
        <span class="artista">{t.eligeAlgo}</span>
      {/if}
    </div>
  </div>

  <div class="centro">
    <div class="controles">
      <button
        type="button"
        class="control conmutador"
        class:activo={i.aleatorio}
        aria-label={t.aleatorio}
        aria-pressed={i.aleatorio}
        title={t.aleatorio}
        onclick={reproductor.alternarAleatorio}
      >
        <Icon nombre="aleatorio" tamano={20} />
      </button>
      <button
        type="button"
        class="control"
        aria-label={t.anterior}
        title={t.anterior}
        disabled={i.cola.length === 0 && !hayPista}
        onclick={reproductor.anterior}
      >
        <Icon nombre="anterior" tamano={20} />
      </button>
      <button
        type="button"
        class="control principal"
        aria-label={reproductor.sonando ? t.pausar : t.reproducir}
        title={reproductor.sonando ? t.pausar : t.reproducir}
        disabled={i.cola.length === 0 && !hayPista}
        onclick={reproductor.pausarReanudar}
      >
        <Icon nombre={reproductor.sonando ? 'pausa' : 'reproducir'} tamano={22} />
      </button>
      <button
        type="button"
        class="control"
        aria-label={t.siguiente}
        title={t.siguiente}
        disabled={i.cola.length === 0 && !hayPista}
        onclick={reproductor.siguiente}
      >
        <Icon nombre="siguiente" tamano={20} />
      </button>
      <button
        type="button"
        class="control conmutador"
        class:activo={i.repeticion !== 'ninguno'}
        aria-label={t.repeticion[i.repeticion as keyof typeof t.repeticion] ?? t.repetir}
        title={t.repeticion[i.repeticion as keyof typeof t.repeticion] ?? t.repetir}
        onclick={reproductor.rotarRepeticion}
      >
        <Icon nombre={i.repeticion === 'uno' ? 'repetirUna' : 'repetir'} tamano={20} />
      </button>
    </div>
    <div class="progreso">
      <span class="tiempo">{formatoTiempo(posicion)}</span>
      <div class="barra-onda">
        {#if reproductor.picos.length > 0}
          <FormaDeOnda
            picos={reproductor.picos}
            {posicion}
            duracion={i.duracionSeg}
            entradaSeg={i.dj?.entradaSeg ?? null}
            salidaSeg={i.dj?.salidaSeg ?? null}
          />
        {/if}
        <input
          type="range"
          class="deslizador"
          class:sobre-onda={reproductor.picos.length > 0}
          aria-label={t.progreso}
          min="0"
          max={Math.max(i.duracionSeg, 0.001)}
          step="0.1"
          value={posicion}
          disabled={!hayPista || i.duracionSeg <= 0}
          style:--relleno={`${i.duracionSeg > 0 ? (posicion / i.duracionSeg) * 100 : 0}%`}
          oninput={(e) => (arrastrando = Number(e.currentTarget.value))}
          onchange={soltar}
        />
      </div>
      <span class="tiempo">{formatoTiempo(i.duracionSeg)}</span>
    </div>
  </div>

  <div class="extra">
    <button
      type="button"
      class="control"
      class:activo={page.url.pathname === '/reproduciendo' && page.url.searchParams.has('letras')}
      aria-label={t.letras}
      title={t.letras}
      disabled={!hayPista || i.ciego}
      onclick={() => abrirVista(true)}
    >
      <Icon nombre="letras" tamano={20} />
    </button>
    <button
      type="button"
      class="control conmutador"
      class:activo={i.karaokeActivo}
      class:preparando={preparando !== null}
      style:--progreso={`${Math.round((preparando ?? 0) * 100)}%`}
      aria-label={preparando !== null
        ? t.karaokePreparando(Math.round(preparando * 100))
        : t.karaoke}
      aria-pressed={i.karaokeActivo}
      disabled={!hayPista}
      onclick={microfono}
    >
      <Icon nombre="microfono" tamano={20} />
      {#if preparando !== null}
        <span class="pct-karaoke">{Math.round(preparando * 100)}%</span>
      {/if}
    </button>
    {#if ofertaKaraoke}
      {#await import('./agregados/OfertaAgregado.svelte') then m}
        <m.default id="karaoke" oncerrar={() => (ofertaKaraoke = false)} />
      {/await}
    {/if}
    <SelectorDestino />
    <button
      type="button"
      bind:this={botonCola}
      class="control cola conmutador"
      class:activo={colaAbierta}
      aria-label={t.colaCon(i.cola.length)}
      aria-expanded={colaAbierta}
      title={t.cola}
      onclick={alternarCola}
    >
      <Icon nombre="cola" tamano={20} />
      {#if i.cola.length > 0}<span class="cuenta">{i.cola.length}</span>{/if}
    </button>
    <div
      class="capa-cola"
      popover="auto"
      bind:this={capaCola}
      ontoggle={(e) => (colaAbierta = e.newState === 'open')}
    >
      {#if colaAbierta}<PanelCola />{/if}
    </div>
    <div class="volumen">
      <button
        type="button"
        class="control"
        aria-label={i.volumen > 0 ? t.silenciar : t.quitarSilencio}
        title={t.volumen}
        onclick={() => reproductor.volumen(i.volumen > 0 ? 0 : 1)}
      >
        <Icon nombre={i.volumen > 0 ? 'volumen' : 'silencio'} tamano={20} />
      </button>
      <input
        type="range"
        class="deslizador"
        aria-label={t.volumen}
        min="0"
        max="1"
        step="0.01"
        value={i.volumen}
        style:--relleno={`${i.volumen * 100}%`}
        oninput={(e) => reproductor.volumen(Number(e.currentTarget.value))}
      />
    </div>
    <button
      type="button"
      class="control"
      aria-label={t.mini}
      title={t.mini}
      disabled={!hayPista || i.ciego}
      onclick={abrirMinirreproductor}
    >
      <Icon nombre="minirreproductor" tamano={20} />
    </button>
    <button
      type="button"
      class="control conmutador"
      class:activo={enPantallaCompleta}
      aria-label={enPantallaCompleta ? t.salirPantallaCompleta : t.pantallaCompleta}
      aria-pressed={enPantallaCompleta}
      title={enPantallaCompleta ? t.salirPantallaCompleta : t.pantallaCompleta}
      onclick={conmutarPantallaCompleta}
    >
      <Icon
        nombre={enPantallaCompleta ? 'salirPantallaCompleta' : 'pantallaCompleta'}
        tamano={20}
      />
    </button>
    <button
      type="button"
      class="control"
      class:activo={page.url.pathname === '/reproduciendo' && !page.url.searchParams.has('letras')}
      aria-label={t.expandir}
      title={t.expandir}
      disabled={!hayPista || i.ciego}
      onclick={() => abrirVista(false)}
    >
      <Icon nombre="expandir" tamano={20} />
    </button>
  </div>
</section>

<style>
  .reproductor {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.6fr) minmax(0, 1fr);
    align-items: center;
    gap: var(--ns-espacio-4);
    height: var(--ns-alto-reproductor);
    padding: 0 var(--ns-espacio-4);
    background: var(--m3c-surface-container-low);
    border-top: 1px solid var(--m3c-outline-variant);
  }

  .pista {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    min-width: 0;
  }

  .portada {
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    width: 3.5rem;
    height: 3.5rem;
    padding: 0;
    border: none;
    overflow: hidden;
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-primary);
    cursor: pointer;
  }

  .portada:disabled {
    cursor: default;
  }

  .portada img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .datos {
    display: flex;
    flex-direction: column;
    min-width: 0;
    line-height: 1.3;
  }

  .titulo,
  .artista,
  .album {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .titulo {
    font-weight: 700;
  }

  .enlace-titulo {
    padding: 0;
    border: none;
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .enlace-titulo:hover {
    text-decoration: underline;
  }

  .artista {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .album {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .enlace {
    text-decoration: none;
  }

  .enlace:hover {
    color: var(--m3c-on-surface);
    text-decoration: underline;
  }

  .centro {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--ns-espacio-2);
    min-width: 0;
  }

  .controles,
  .extra,
  .volumen {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
  }

  .extra {
    justify-content: flex-end;
    gap: var(--ns-espacio-2);
  }

  .control {
    position: relative;
    display: grid;
    place-items: center;
    width: 2.25rem;
    height: 2.25rem;
    border: 1px solid transparent;
    border-radius: var(--ns-radio-sm);
    background: none;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
    transition: background-color var(--ns-duracion-corta) var(--ns-curva);
  }

  .control:hover:not(:disabled) {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
  }

  .control:disabled {
    opacity: 0.38;
    cursor: default;
  }

  /* Aleatorio, repetición y karaoke: recuadro de acento cuando están activos, como
     en la V1. */
  .conmutador.activo {
    border-color: var(--m3c-primary);
    color: var(--m3c-primary);
  }

  .principal {
    width: 2.75rem;
    height: 2.75rem;
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .principal:hover:not(:disabled) {
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
    filter: brightness(1.08);
  }

  .capa-cola {
    position: fixed;
    inset: auto;
    margin: 0;
    padding: 0;
    border: none;
    background: none;
  }

  .cola {
    width: auto;
    padding: 0 var(--ns-espacio-2);
    display: flex;
    gap: var(--ns-espacio-1);
  }

  .cuenta {
    font-size: var(--ns-texto-xs);
    font-variant-numeric: tabular-nums;
  }

  .progreso {
    display: grid;
    grid-template-columns: 3rem minmax(0, 1fr) 3rem;
    align-items: center;
    gap: var(--ns-espacio-2);
    width: 100%;
    max-width: 36rem;
  }

  .tiempo {
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
    font-variant-numeric: tabular-nums;
    text-align: center;
  }

  .barra-onda {
    position: relative;
    display: flex;
    align-items: center;
    height: 1.5rem;
  }

  .deslizador {
    appearance: none;
    width: 100%;
    height: 0.25rem;
    border-radius: var(--ns-radio-pleno);
    background: linear-gradient(
      to right,
      var(--m3c-primary) var(--relleno, 0%),
      var(--m3c-surface-container-highest) var(--relleno, 0%)
    );
    cursor: pointer;
  }

  .deslizador.sobre-onda {
    position: absolute;
    inset: 0;
    height: 100%;
    margin: 0;
    background: none;
  }

  .deslizador:disabled {
    cursor: default;
  }

  .deslizador::-webkit-slider-thumb {
    appearance: none;
    width: 0.875rem;
    height: 0.875rem;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-on-surface);
    border: 2px solid var(--m3c-primary);
  }

  .volumen .deslizador {
    width: 6.5rem;
  }

  @container carcasa (max-width: 60rem) {
    .album,
    .volumen .deslizador {
      display: none;
    }
  }

  /* Lo preparado del karaoke, como un anillo alrededor del micrófono. */
  .control.preparando {
    background: conic-gradient(
      var(--m3c-primary) var(--progreso),
      var(--m3c-surface-container-highest) 0
    );
  }

  .pct-karaoke {
    position: absolute;
    bottom: -1rem;
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: var(--m3c-primary);
  }
</style>
