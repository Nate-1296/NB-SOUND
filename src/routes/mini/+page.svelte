<!--
  El minirreproductor: una ventana pequeña, siempre encima, para seguir la música
  mientras se trabaja en otra cosa.

  La portada ocupa todo el alto a la izquierda; a su lado, la canción, los cinco
  controles y la barra de progreso pegada al borde de abajo. La ventana es un
  rectángulo sin bordes, así que la página también: la versión anterior dibujaba
  una tarjeta redondeada con sombra dentro de la ventana, y en las esquinas se
  veía el fondo opaco de la ventana. Arriba a la derecha, volver a la ventana
  grande y cerrar (que solo la esconde: reabrirla es instantáneo).
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { favoritas } from '#lib/core/acciones.svelte.ts';
  import { dejarMinirreproductor, urlPortada } from '#lib/core/ipc/index.ts';
  import { formatoTiempo, reproductor } from '#lib/core/reproductor.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import Icon from '#lib/ui/Icon.svelte';

  const t = textos.reproductor;
  const i = $derived(reproductor.instantanea);
  const pista = $derived(reproductor.pista);
  const avance = $derived(i.duracionSeg > 0 ? (reproductor.posicion / i.duracionSeg) * 100 : 0);
  const favorita = $derived(pista ? favoritas.es(pista) : false);

  onMount(() => {
    void reproductor.arrancar();
  });
</script>

<main class="mini" data-tauri-drag-region>
  <div class="portada" data-tauri-drag-region>
    {#if pista?.tienePortada}
      {#key pista.id}
        <img src={urlPortada('pista', pista.id, 320)} alt="" data-tauri-drag-region />
      {/key}
    {:else}
      <Icon nombre="cancion" tamano={36} />
    {/if}
  </div>

  <div class="lado" data-tauri-drag-region>
    <div class="cabecera" data-tauri-drag-region>
      <div class="textos" data-tauri-drag-region>
        <span class="titulo" title={pista?.titulo ?? t.nadaSonando} data-tauri-drag-region>
          {pista?.titulo ?? t.nadaSonando}
        </span>
        <span class="artista" title={pista?.artista ?? ''} data-tauri-drag-region>
          {pista?.artista ?? ''}
        </span>
      </div>
      <button
        type="button"
        class="accion"
        aria-label={t.volverDeMini}
        title={t.volverDeMini}
        onclick={() => void dejarMinirreproductor(true)}
      >
        <Icon nombre="expandir" tamano={16} />
      </button>
      <button
        type="button"
        class="accion"
        aria-label={t.cerrarMini}
        title={t.cerrarMini}
        onclick={() => void dejarMinirreproductor(false)}
      >
        <Icon nombre="cerrar" tamano={16} />
      </button>
    </div>

    <div class="controles" data-tauri-drag-region>
      <button
        type="button"
        class="control"
        class:activo={favorita}
        aria-label={favorita ? t.quitarFavorita : t.marcarFavorita}
        aria-pressed={favorita}
        title={favorita ? t.quitarFavorita : t.marcarFavorita}
        disabled={!pista}
        onclick={() => pista && favoritas.alternar(pista)}
      >
        <Icon nombre="favorito" tamano={17} />
      </button>
      <button
        type="button"
        class="control"
        aria-label={t.anterior}
        title={t.anterior}
        disabled={!pista}
        onclick={reproductor.anterior}
      >
        <Icon nombre="anterior" tamano={19} />
      </button>
      <button
        type="button"
        class="control principal"
        aria-label={reproductor.sonando ? t.pausar : t.reproducir}
        title={reproductor.sonando ? t.pausar : t.reproducir}
        disabled={!pista}
        onclick={reproductor.pausarReanudar}
      >
        <Icon nombre={reproductor.sonando ? 'pausa' : 'reproducir'} tamano={20} />
      </button>
      <button
        type="button"
        class="control"
        aria-label={t.siguiente}
        title={t.siguiente}
        disabled={!pista}
        onclick={reproductor.siguiente}
      >
        <Icon nombre="siguiente" tamano={19} />
      </button>
      <button
        type="button"
        class="control"
        class:activo={i.repeticion !== 'ninguno'}
        aria-label={t.repetir}
        title={t.repetir}
        disabled={!pista}
        onclick={reproductor.rotarRepeticion}
      >
        <Icon nombre={i.repeticion === 'uno' ? 'repetirUna' : 'repetir'} tamano={17} />
      </button>
    </div>

    <div class="tiempos" data-tauri-drag-region>
      <span>{formatoTiempo(reproductor.posicion)}</span>
      <span>{formatoTiempo(i.duracionSeg)}</span>
    </div>
  </div>

  <input
    type="range"
    class="progreso"
    aria-label={t.progreso}
    min="0"
    max={Math.max(i.duracionSeg, 0.001)}
    step="0.1"
    value={reproductor.posicion}
    disabled={!pista || i.duracionSeg <= 0}
    style:--relleno={`${avance}%`}
    oninput={(e) => reproductor.buscar(Number(e.currentTarget.value))}
  />
</main>

<style>
  :global(html),
  :global(body) {
    height: 100%;
    margin: 0;
    overflow: hidden;
    background: var(--m3c-surface-container);
  }

  .mini {
    position: relative;
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    height: 100vh;
    background:
      radial-gradient(
        circle at 0% 50%,
        color-mix(in srgb, var(--m3c-primary) 16%, transparent),
        transparent 60%
      ),
      var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    user-select: none;
  }

  .portada {
    display: grid;
    place-items: center;
    /* Cuadrada si la ventana tiene la medida pedida; si el gestor de ventanas
       impone más alto, recorta en vez de comerse el sitio de los controles. */
    width: min(100vh, 36vw);
    height: 100vh;
    overflow: hidden;
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-primary);
  }

  .portada img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .lado {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    min-width: 0;
    padding: var(--ns-espacio-3) var(--ns-espacio-3) var(--ns-espacio-3) var(--ns-espacio-4);
  }

  .cabecera {
    display: flex;
    align-items: flex-start;
    gap: var(--ns-espacio-1);
    min-width: 0;
  }

  .textos {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-width: 0;
  }

  .titulo,
  .artista {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .titulo {
    font-size: var(--ns-texto-md);
    font-weight: 700;
    line-height: 1.3;
  }

  .artista {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
    line-height: 1.3;
  }

  .accion,
  .control {
    display: grid;
    flex: 0 0 auto;
    place-items: center;
    padding: 0;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
    transition:
      background-color var(--ns-duracion-corta) var(--ns-curva),
      color var(--ns-duracion-corta) var(--ns-curva);
  }

  .accion {
    width: 1.75rem;
    height: 1.75rem;
  }

  .accion:hover,
  .control:hover:not(:disabled) {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
  }

  .controles {
    display: flex;
    align-items: center;
    justify-content: space-between;
    max-width: 16rem;
  }

  .control {
    width: 2.25rem;
    height: 2.25rem;
  }

  .control.activo {
    color: var(--m3c-primary);
  }

  .control:disabled {
    opacity: 0.38;
    cursor: default;
  }

  .control.principal {
    width: 2.75rem;
    height: 2.75rem;
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .control.principal:hover:not(:disabled) {
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
    filter: brightness(1.08);
  }

  .tiempos {
    display: flex;
    justify-content: space-between;
    max-width: 16rem;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-variant-numeric: tabular-nums;
  }

  /* La barra de progreso es el borde de abajo de la ventana, de lado a lado. */
  .progreso {
    position: absolute;
    right: 0;
    bottom: 0;
    left: 0;
    width: 100%;
    height: 0.25rem;
    margin: 0;
    appearance: none;
    background: linear-gradient(
      to right,
      var(--m3c-primary) 0%,
      var(--m3c-primary) var(--relleno, 0%),
      var(--m3c-surface-container-highest) var(--relleno, 0%)
    );
    cursor: pointer;
  }

  .progreso::-webkit-slider-thumb {
    width: 0.75rem;
    height: 0.75rem;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-primary);
    opacity: 0;
    appearance: none;
    transition: opacity var(--ns-duracion-corta) var(--ns-curva);
  }

  .mini:hover .progreso::-webkit-slider-thumb {
    opacity: 1;
  }

  .progreso:disabled {
    cursor: default;
  }
</style>
