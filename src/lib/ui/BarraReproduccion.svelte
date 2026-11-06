<!--
  @component
  La barra de reproducción permanente: la pista a la izquierda, los controles y el
  progreso en el centro, y a la derecha letras, karaoke, cola, volumen, pantalla
  completa y el menú ···. El micrófono del karaoke vive aquí y no en una vista propia (ADR-007).
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { urlPortada } from '#lib/core/ipc/index.ts';
  import { pantalla } from '#lib/core/pantalla.svelte.ts';
  import { formatoTiempo, reproductor } from '#lib/core/reproductor.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';

  import { tramoReproduccion } from './anchos';
  import FormaDeOnda from './FormaDeOnda.svelte';
  import DialogoConectar from './dispositivos/DialogoConectar.svelte';
  import Icon from './Icon.svelte';

  const t = textos.reproductor;
  const i = $derived(reproductor.instantanea);
  const pista = $derived(reproductor.pista);
  const hayPista = $derived(i.pistaId !== null);

  /** Lo que cabe depende del ancho de la propia barra (`anchos.ts`). */
  let anchoBarra = $state(0);
  const tramo = $derived(tramoReproduccion(anchoBarra));

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

  // El menú ···, en la misma capa superior que la cola.
  let capaMenu: HTMLDivElement | undefined = $state();
  let botonMenu: HTMLButtonElement | undefined = $state();
  let menuAbierto = $state(false);
  let conectando = $state(false);
  function alternarMenu() {
    if (!capaMenu || !botonMenu) return;
    if (menuAbierto) {
      capaMenu.hidePopover();
      return;
    }
    const r = botonMenu.getBoundingClientRect();
    capaMenu.style.right = `${Math.max(8, window.innerWidth - r.right)}px`;
    capaMenu.style.bottom = `${window.innerHeight - r.top + 8}px`;
    capaMenu.showPopover();
  }

  // En ventanas estrechas el deslizador no cabe en la barra: el altavoz abre una
  // capa con él. Con el deslizador a la vista, el altavoz silencia.
  let capaVolumen: HTMLDivElement | undefined = $state();
  let botonVolumen: HTMLButtonElement | undefined = $state();
  let volumenAbierto = $state(false);
  let deslizadorBarra: HTMLInputElement | undefined = $state();

  function alternarVolumen() {
    if (!capaVolumen || !botonVolumen) return;
    if (deslizadorBarra?.offsetParent) {
      void reproductor.alternarSilencio();
      return;
    }
    if (volumenAbierto) {
      capaVolumen.hidePopover();
      return;
    }
    const r = botonVolumen.getBoundingClientRect();
    capaVolumen.style.right = `${Math.max(8, window.innerWidth - r.right)}px`;
    capaVolumen.style.bottom = `${window.innerHeight - r.top + 8}px`;
    capaVolumen.showPopover();
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
    void goto(letras ? '/reproduciendo?letras' : '/reproduciendo', {
      replace: Boolean(ruta)
    });
  }

  // Los atajos de la carcasa (`atajos.ts`) piden la cola y la vista ampliada con
  // estos eventos: la barra es la dueña de las dos.
  $effect(() => {
    const cola = () => alternarCola();
    const vista = (e: Event) => abrirVista((e as CustomEvent<{ letras: boolean }>).detail.letras);
    window.addEventListener('ns:cola', cola);
    window.addEventListener('ns:vista', vista);
    return () => {
      window.removeEventListener('ns:cola', cola);
      window.removeEventListener('ns:vista', vista);
    };
  });

  function soltar(e: Event) {
    const valor = Number((e.currentTarget as HTMLInputElement).value);
    arrastrando = null;
    void reproductor.buscar(valor);
  }
</script>

<section
  class="reproductor"
  class:media={tramo === 'media'}
  class:estrecha={tramo === 'estrecha'}
  aria-label={t.region}
  bind:clientWidth={anchoBarra}
>
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
      {#if tramo !== 'estrecha'}
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
      {/if}
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
      {#if tramo !== 'estrecha'}
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
      {/if}
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
    {#if tramo === 'amplia'}
      <button
        type="button"
        class="control conmutador"
        class:activo={page.url.pathname === '/reproduciendo' && page.url.searchParams.has('letras')}
        aria-label={t.letras}
        title={t.letras}
        aria-pressed={page.url.pathname === '/reproduciendo' && page.url.searchParams.has('letras')}
        disabled={!hayPista || i.ciego}
        onclick={() => abrirVista(true)}
      >
        <Icon nombre="letras" tamano={20} />
      </button>
    {/if}
    {#if tramo !== 'estrecha'}
      <!-- Siempre está, apagado si la canción no está preparada: si aparecía y
           desaparecía, la barra cambiaba de forma de una canción a otra. -->
      <button
        type="button"
        class="control conmutador"
        class:activo={i.karaokeActivo}
        aria-label={t.karaoke}
        aria-pressed={i.karaokeActivo}
        title={t.karaoke}
        disabled={!hayPista || !i.karaokeDisponible}
        onclick={reproductor.alternarKaraoke}
      >
        <Icon nombre="microfono" tamano={20} />
      </button>
    {/if}
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
      <span class="cuenta">{i.cola.length > 0 ? i.cola.length : ''}</span>
    </button>
    <div
      class="capa-cola"
      popover="auto"
      bind:this={capaCola}
      ontoggle={(e) => (colaAbierta = e.newState === 'open')}
    >
      {#if colaAbierta}
        {#await import('./PanelCola.svelte') then m}
          <m.default />
        {/await}
      {/if}
    </div>
    <div class="volumen">
      <button
        type="button"
        class="control"
        bind:this={botonVolumen}
        aria-label={i.volumen > 0 ? t.silenciar : t.quitarSilencio}
        title={t.volumen}
        onclick={alternarVolumen}
      >
        <Icon nombre={i.volumen > 0 ? 'volumen' : 'silencio'} tamano={20} />
      </button>
      <div
        class="capa-volumen"
        popover="auto"
        bind:this={capaVolumen}
        ontoggle={(e) => (volumenAbierto = e.newState === 'open')}
      >
        <div class="popup-volumen">
          <button
            type="button"
            class="control"
            aria-label={i.volumen > 0 ? t.silenciar : t.quitarSilencio}
            onclick={reproductor.alternarSilencio}
          >
            <Icon nombre={i.volumen > 0 ? 'volumen' : 'silencio'} tamano={18} />
          </button>
          <input
            type="range"
            class="deslizador deslizador-popup"
            aria-label={t.volumen}
            min="0"
            max="1"
            step="0.01"
            value={i.volumen}
            style:--relleno={`${i.volumen * 100}%`}
            oninput={(e) => reproductor.volumen(Number(e.currentTarget.value))}
          />
          <span class="pct-volumen">{Math.round(i.volumen * 100)}%</span>
        </div>
      </div>
      <input
        type="range"
        class="deslizador deslizador-barra"
        bind:this={deslizadorBarra}
        aria-label={t.volumen}
        min="0"
        max="1"
        step="0.01"
        value={i.volumen}
        style:--relleno={`${i.volumen * 100}%`}
        oninput={(e) => reproductor.volumen(Number(e.currentTarget.value))}
      />
    </div>
    {#if tramo === 'amplia'}
      <button
        type="button"
        class="control conmutador"
        class:activo={pantalla.completa}
        aria-label={pantalla.completa ? t.salirPantallaCompleta : t.pantallaCompleta}
        aria-pressed={pantalla.completa}
        title={pantalla.completa ? t.salirPantallaCompleta : t.pantallaCompleta}
        onclick={() => pantalla.alternar()}
      >
        <Icon
          nombre={pantalla.completa ? 'salirPantallaCompleta' : 'pantallaCompleta'}
          tamano={20}
        />
      </button>
    {/if}
    <button
      type="button"
      bind:this={botonMenu}
      class="control conmutador"
      class:activo={menuAbierto}
      aria-label={t.masOpciones}
      title={t.masOpciones}
      aria-haspopup="menu"
      aria-expanded={menuAbierto}
      disabled={i.ciego}
      onclick={alternarMenu}
    >
      <Icon nombre="masHorizontal" tamano={20} />
    </button>
    <div
      class="capa-cola"
      popover="auto"
      bind:this={capaMenu}
      ontoggle={(e) => (menuAbierto = e.newState === 'open')}
    >
      {#if menuAbierto}
        {#await import('./MenuBarra.svelte') then m}
          <m.default
            oncerrar={() => capaMenu?.hidePopover()}
            onconectar={() => (conectando = true)}
            {tramo}
            onletras={() => abrirVista(true)}
          />
        {/await}
      {/if}
    </div>
  </div>
</section>

<DialogoConectar abierto={conectando} oncerrar={() => (conectando = false)} />

<style>
  /*
   * Los extras van a su ancho: en tercios iguales, a 1100 px desbordaban sobre
   * los controles del centro y el micrófono quedaba encima de "repetir".
   */
  .reproductor {
    display: grid;
    grid-template-columns: minmax(12rem, 1fr) minmax(0, 2fr) auto;
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
    box-shadow: 0 2px 8px var(--m3c-shadow);
    cursor: pointer;
    transition: transform 120ms ease;
  }

  .portada:hover:not(:disabled) {
    transform: scale(1.04);
  }

  .portada:disabled {
    cursor: default;
    box-shadow: none;
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
    border-radius: var(--ns-radio-pleno);
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

  /*
   * Aleatorio, repetición, karaoke y los paneles: activos, el icono toma el acento
   * y lleva un punto debajo. Antes se rellenaban con el contenedor primario, que en
   * la mitad de los temas es casi el color del botón de reproducir: tres círculos
   * iguales y no se distinguía qué era un botón y qué un estado.
   */
  .conmutador.activo {
    background: color-mix(in srgb, var(--m3c-primary) 12%, transparent);
    color: var(--m3c-primary);
  }

  .conmutador.activo::after {
    content: '';
    position: absolute;
    bottom: 1px;
    left: 50%;
    width: 4px;
    height: 4px;
    border-radius: var(--ns-radio-pleno);
    background: currentColor;
    translate: -50% 0;
  }

  .conmutador.activo:hover:not(:disabled) {
    background: color-mix(in srgb, var(--m3c-primary) 20%, transparent);
    color: var(--m3c-primary);
  }

  .principal {
    width: 2.75rem;
    height: 2.75rem;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
    box-shadow: 0 2px 8px var(--m3c-shadow);
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

  /* Ancho de cuatro cifras: la cuenta no empuja a los botones al crecer. */
  .cuenta {
    min-width: 4ch;
    font-size: var(--ns-texto-xs);
    font-variant-numeric: tabular-nums;
    text-align: left;
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

  .capa-volumen {
    position: fixed;
    inset: auto;
    margin: 0;
    padding: 0;
    border: none;
    background: none;
    overflow: visible;
  }

  .capa-volumen:popover-open {
    display: flex;
  }

  .popup-volumen {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    box-shadow: var(--m3-elevation-2, none);
  }

  .deslizador-popup {
    width: 6.5rem;
  }

  .pct-volumen {
    font-size: var(--ns-texto-xs);
    font-variant-numeric: tabular-nums;
    color: var(--m3c-on-surface-variant);
    min-width: 2.25rem;
    text-align: right;
  }

  /* Lo que no cabe ya está en el menú ···: aquí solo se aprieta lo que queda. */
  .reproductor.media,
  .reproductor.estrecha {
    gap: var(--ns-espacio-3);
    padding: 0 var(--ns-espacio-3);
  }

  .reproductor.estrecha {
    grid-template-columns: minmax(7rem, 1fr) minmax(13rem, 1.4fr) auto;
  }

  .reproductor.estrecha .portada {
    width: 3rem;
    height: 3rem;
  }

  .reproductor.media .album,
  .reproductor.estrecha .album {
    display: none;
  }

  .reproductor.estrecha .progreso {
    grid-template-columns: 2.5rem minmax(0, 1fr) 2.5rem;
    gap: var(--ns-espacio-1);
  }

  @container carcasa (max-width: 75rem) {
    .volumen .deslizador-barra {
      display: none;
    }
  }

  @container carcasa (max-width: 50rem) {
    .extra {
      gap: 0.25rem;
    }
  }
</style>
