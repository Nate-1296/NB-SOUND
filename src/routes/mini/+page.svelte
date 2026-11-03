<!--
  El minirreproductor (ventana flotante de NB Sound):
  Diseño refinado, táctil y equilibrado inspirado en Material 3 y NB Books.
  Arte de álbum protagonista, tipografía clara, controles completos (aleatorio,
  anterior, play/pause, siguiente, repetición y favorita) y barra de progreso fluida.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { cerrarEstaVentana, fijarFavorita, urlPortada } from '$core/ipc';
  import { formatoTiempo, reproductor } from '$core/reproductor.svelte';
  import { textos } from '$lib/i18n';
  import Icon from '$ui/Icon.svelte';

  const t = textos.reproductor;
  const i = $derived(reproductor.instantanea);
  const pista = $derived(reproductor.pista);
  const avance = $derived(i.duracionSeg > 0 ? (reproductor.posicion / i.duracionSeg) * 100 : 0);

  onMount(() => {
    void reproductor.arrancar();
  });

  async function alternarFavorita() {
    if (!pista) return;
    void fijarFavorita(pista.id, !pista.favorita);
  }
</script>

<main class="mini" data-tauri-drag-region>
  <div class="cuerpo" data-tauri-drag-region>
    <div class="portada-contenedor" data-tauri-drag-region>
      <div class="portada" data-tauri-drag-region>
        {#if pista?.tienePortada}
          <img src={urlPortada('pista', pista.id, 320)} alt="" data-tauri-drag-region />
        {:else}
          <Icon nombre="cancion" tamano={32} />
        {/if}
      </div>
    </div>

    <div class="datos" data-tauri-drag-region>
      <div class="cabecera-info" data-tauri-drag-region>
        <div class="textos-pista" data-tauri-drag-region>
          <span class="titulo" title={pista?.titulo ?? t.nadaSonando} data-tauri-drag-region>
            {pista?.titulo ?? t.nadaSonando}
          </span>
          <span class="artista" title={pista?.artista ?? ''} data-tauri-drag-region>
            {pista?.artista ?? ''}
          </span>
        </div>
        <div class="acciones-superiores" data-tauri-drag-region>
          {#if pista}
            <button
              type="button"
              class="boton-accion"
              class:favorita={pista.favorita}
              aria-label={pista.favorita ? t.quitarFavorita : t.marcarFavorita}
              title={pista.favorita ? t.quitarFavorita : t.marcarFavorita}
              onclick={alternarFavorita}
            >
              <Icon nombre="favorito" tamano={16} />
            </button>
          {/if}
          <button
            type="button"
            class="boton-accion cerrar"
            aria-label={t.cerrarMini}
            title={t.cerrarMini}
            onclick={cerrarEstaVentana}
          >
            <Icon nombre="cerrar" tamano={16} />
          </button>
        </div>
      </div>

      <div class="fila-controles" data-tauri-drag-region>
        <button
          type="button"
          class="control"
          class:activo={i.aleatorio}
          aria-label={t.aleatorio}
          title={t.aleatorio}
          disabled={!pista}
          onclick={reproductor.alternarAleatorio}
        >
          <Icon nombre="aleatorio" tamano={15} />
        </button>

        <button
          type="button"
          class="control"
          aria-label={t.anterior}
          title={t.anterior}
          disabled={!pista}
          onclick={reproductor.anterior}
        >
          <Icon nombre="anterior" tamano={17} />
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
          <Icon nombre="siguiente" tamano={17} />
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
          <Icon nombre={i.repeticion === 'uno' ? 'repetirUna' : 'repetir'} tamano={15} />
        </button>
      </div>
    </div>
  </div>

  <div class="progreso-fila" data-tauri-drag-region>
    <span class="tiempo">{formatoTiempo(reproductor.posicion)}</span>
    <div class="progreso-riel">
      <input
        type="range"
        class="deslizador-mini"
        aria-label={t.progreso}
        min="0"
        max={Math.max(i.duracionSeg, 0.001)}
        step="0.1"
        value={reproductor.posicion}
        disabled={!pista || i.duracionSeg <= 0}
        style:--relleno={`${avance}%`}
        oninput={(e) => reproductor.buscar(Number(e.currentTarget.value))}
      />
    </div>
    <span class="tiempo">{formatoTiempo(i.duracionSeg)}</span>
  </div>
</main>

<style>
  :global(body) {
    margin: 0;
    overflow: hidden;
    background: transparent;
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100vh;
  }

  .mini {
    position: relative;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    width: 100%;
    max-width: 470px;
    height: 100%;
    max-height: 168px;
    margin: 0 auto;
    padding: var(--ns-espacio-3) var(--ns-espacio-4);
    box-sizing: border-box;
    background: linear-gradient(
      160deg,
      var(--m3c-surface-container) 0%,
      var(--m3c-surface-container-high) 100%
    );
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-xl);
    box-shadow: 0 10px 30px var(--m3c-shadow);
    color: var(--m3c-on-surface);
    user-select: none;
    overflow: hidden;
  }

  .cuerpo {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    min-width: 0;
    flex: 1;
  }

  .portada-contenedor {
    flex: 0 0 auto;
  }

  .portada {
    width: 4.875rem;
    height: 4.875rem;
    display: grid;
    place-items: center;
    overflow: hidden;
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-primary);
    border: 1px solid var(--m3c-outline-variant);
    box-shadow: 0 4px 16px var(--m3c-shadow);
  }

  .portada img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .datos {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    min-width: 0;
    height: 4.875rem;
  }

  .cabecera-info {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--ns-espacio-2);
    min-width: 0;
  }

  .textos-pista {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .titulo,
  .artista {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .titulo {
    font-size: var(--ns-texto-sm);
    font-weight: 700;
    line-height: 1.25;
    color: var(--m3c-on-surface);
  }

  .artista {
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
    line-height: 1.25;
  }

  .acciones-superiores {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-1);
    flex: 0 0 auto;
  }

  .boton-accion {
    display: grid;
    place-items: center;
    width: 1.75rem;
    height: 1.75rem;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
    transition:
      background-color var(--ns-duracion-corta) var(--ns-curva),
      color var(--ns-duracion-corta) var(--ns-curva);
  }

  .boton-accion:hover {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
  }

  .boton-accion.favorita {
    color: var(--m3c-primary);
  }

  .fila-controles {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-1);
  }

  .control {
    display: grid;
    place-items: center;
    width: 1.875rem;
    height: 1.875rem;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
    transition:
      background-color var(--ns-duracion-corta) var(--ns-curva),
      color var(--ns-duracion-corta) var(--ns-curva);
  }

  .control:hover:not(:disabled) {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
  }

  .control.activo {
    color: var(--m3c-primary);
  }

  .control:disabled {
    opacity: 0.38;
    cursor: default;
  }

  .control.principal {
    width: 2.25rem;
    height: 2.25rem;
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
    box-shadow: 0 2px 8px var(--m3c-shadow);
  }

  .control.principal:hover:not(:disabled) {
    background: var(--m3c-primary);
    filter: brightness(1.1);
  }

  .progreso-fila {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    width: 100%;
    margin-top: 0.25rem;
  }

  .tiempo {
    font-size: var(--ns-texto-xs);
    font-variant-numeric: tabular-nums;
    color: var(--m3c-on-surface-variant);
    min-width: 2.25rem;
  }

  .tiempo:last-child {
    text-align: right;
  }

  .progreso-riel {
    flex: 1;
    display: flex;
    align-items: center;
  }

  .deslizador-mini {
    width: 100%;
    height: 4px;
    appearance: none;
    -webkit-appearance: none;
    background: linear-gradient(
      to right,
      var(--m3c-primary) 0%,
      var(--m3c-primary) var(--relleno, 0%),
      var(--m3c-surface-container-highest) var(--relleno, 0%),
      var(--m3c-surface-container-highest) 100%
    );
    border-radius: var(--ns-radio-pleno);
    cursor: pointer;
  }

  .deslizador-mini::-webkit-slider-thumb {
    appearance: none;
    -webkit-appearance: none;
    width: 10px;
    height: 10px;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-primary);
    cursor: pointer;
    box-shadow: 0 1px 4px var(--m3c-shadow);
  }

  .deslizador-mini:disabled {
    cursor: default;
    opacity: 0.38;
  }
</style>
