<!--
  El minirreproductor (`Principal.qml` de la V1, ventana flotante): una ventana
  pequeña, siempre encima y sin bordes, con la portada, la pista, los controles y
  el progreso. Se arrastra desde cualquier zona sin botones.
-->
<script lang="ts">
  import { onMount } from 'svelte';

  import { cerrarEstaVentana, urlPortada } from '$core/ipc';
  import { reproductor } from '$core/reproductor.svelte';
  import { textos } from '$lib/i18n';
  import Icon from '$ui/Icon.svelte';

  const t = textos.reproductor;
  const i = $derived(reproductor.instantanea);
  const pista = $derived(reproductor.pista);
  const avance = $derived(i.duracionSeg > 0 ? (reproductor.posicion / i.duracionSeg) * 100 : 0);

  onMount(() => {
    void reproductor.arrancar();
  });
</script>

<main class="mini" data-tauri-drag-region>
  <div class="portada" data-tauri-drag-region>
    {#if pista?.tienePortada}
      <img src={urlPortada('pista', pista.id, 160)} alt="" data-tauri-drag-region />
    {:else}
      <Icon nombre="cancion" tamano={28} />
    {/if}
  </div>
  <div class="datos" data-tauri-drag-region>
    <span class="titulo" data-tauri-drag-region>{pista?.titulo ?? t.nadaSonando}</span>
    <span class="artista" data-tauri-drag-region>{pista?.artista ?? ''}</span>
    <div class="controles">
      <button
        type="button"
        aria-label={t.anterior}
        title={t.anterior}
        onclick={reproductor.anterior}
      >
        <Icon nombre="anterior" tamano={18} />
      </button>
      <button
        type="button"
        class="principal"
        aria-label={reproductor.sonando ? t.pausar : t.reproducir}
        title={reproductor.sonando ? t.pausar : t.reproducir}
        onclick={reproductor.pausarReanudar}
      >
        <Icon nombre={reproductor.sonando ? 'pausa' : 'reproducir'} tamano={18} />
      </button>
      <button
        type="button"
        aria-label={t.siguiente}
        title={t.siguiente}
        onclick={reproductor.siguiente}
      >
        <Icon nombre="siguiente" tamano={18} />
      </button>
    </div>
  </div>
  <button
    type="button"
    class="cerrar"
    aria-label={t.cerrarMini}
    title={t.cerrarMini}
    onclick={cerrarEstaVentana}
  >
    <Icon nombre="cerrar" tamano={16} />
  </button>
  <span
    class="progreso"
    style:--avance={`${avance}%`}
    role="progressbar"
    aria-label={t.progreso}
    aria-valuenow={Math.round(avance)}
  ></span>
</main>

<style>
  .mini {
    position: relative;
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--ns-espacio-3);
    height: 100vh;
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    overflow: hidden;
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    user-select: none;
  }

  .portada {
    display: grid;
    place-items: center;
    width: 5.5rem;
    height: 5.5rem;
    overflow: hidden;
    border-radius: var(--ns-radio-sm);
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
    gap: var(--ns-espacio-1);
    min-width: 0;
  }

  .titulo,
  .artista {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .titulo {
    font-weight: 700;
  }

  .artista {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .controles {
    display: flex;
    gap: var(--ns-espacio-2);
  }

  button {
    display: grid;
    place-items: center;
    width: 2rem;
    height: 2rem;
    border: none;
    border-radius: var(--ns-radio-sm);
    background: none;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
  }

  button:hover {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
  }

  .principal {
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .principal:hover {
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .cerrar {
    align-self: start;
  }

  .progreso {
    position: absolute;
    inset: auto 0 0 0;
    height: 3px;
    background: linear-gradient(
      to right,
      var(--m3c-primary) var(--avance),
      var(--m3c-surface-container-highest) var(--avance)
    );
  }
</style>
