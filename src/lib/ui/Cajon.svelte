<!--
  @component
  Un cajón lateral: el panel que se abre desde la derecha con la consola de
  karaoke, los dispositivos o "Añadir música".

  Es un `<dialog>` modal de verdad y no un `div` con `role="dialog"`: el
  navegador encierra el foco dentro, deja inerte lo de detrás y cierra con
  Escape, y nada de eso hay que escribirlo (ni olvidarlo) en cada cajón. Las
  tres consolas tenían cada una su copia de esto, con anchos, fondos y
  animaciones distintos.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';

  import { textos } from '#lib/i18n/index.ts';

  import Icon from './Icon.svelte';
  import type { NombreDeIcono } from './iconos.ts';

  interface Props {
    titulo: string;
    subtitulo?: string;
    icono: NombreDeIcono;
    oncerrar: () => void;
    children: Snippet;
  }

  let { titulo, subtitulo, icono, oncerrar, children }: Props = $props();

  let dialogo: HTMLDialogElement | undefined = $state();

  $effect(() => {
    if (dialogo && !dialogo.open) dialogo.showModal();
  });

  function alPulsarFondo(e: MouseEvent) {
    // El fondo es el propio `<dialog>`: el cajón ocupa solo su lado derecho.
    if (e.target === dialogo) oncerrar();
  }
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
<dialog
  bind:this={dialogo}
  class="cajon"
  aria-label={titulo}
  oncancel={(e) => {
    e.preventDefault();
    oncerrar();
  }}
  onclick={alPulsarFondo}
>
  <div class="panel">
    <header class="cabecera">
      <div class="titulos">
        <h2><Icon nombre={icono} tamano={22} />{titulo}</h2>
        {#if subtitulo}<p class="sub">{subtitulo}</p>{/if}
      </div>
      <button
        type="button"
        class="cerrar"
        onclick={oncerrar}
        aria-label={textos.comun.cerrar}
        title={textos.comun.cerrar}
      >
        <Icon nombre="cerrar" tamano={20} />
      </button>
    </header>
    <div class="cuerpo">
      {@render children()}
    </div>
  </div>
</dialog>

<style>
  .cajon {
    position: fixed;
    inset: 0;
    width: 100%;
    max-width: none;
    height: 100%;
    max-height: none;
    margin: 0;
    padding: 0;
    border: none;
    background: transparent;
    color: var(--m3c-on-surface);
  }

  .cajon::backdrop {
    background: var(--m3c-scrim);
    opacity: 0.45;
  }

  .panel {
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    display: flex;
    flex-direction: column;
    width: min(92vw, 30rem);
    border-left: 1px solid var(--m3c-outline-variant);
    background: var(--m3c-surface-container);
    box-shadow: -8px 0 32px var(--m3c-shadow);
    animation: entra var(--ns-duracion-media) var(--ns-curva);
  }

  /*
   * Entra animando su borde derecho, no con `transform`: con la GPU, WebKitGTK
   * pintaba el panel en mitad de la ventana mientras duraba la animación de
   * `translateX` dentro del `<dialog>` modal, y al acabar saltaba a la derecha.
   * Sin GPU no pasaba, por eso no se veía en la máquina de pruebas.
   */
  @keyframes entra {
    from {
      right: calc(-1 * min(92vw, 30rem));
    }
    to {
      right: 0;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .panel {
      animation: none;
    }
  }

  .cabecera {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-5);
    border-bottom: 1px solid var(--m3c-outline-variant);
    background: var(--m3c-surface-container-high);
  }

  .titulos {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    min-width: 0;
  }

  h2 {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    margin: 0;
    font-size: var(--ns-texto-lg);
    font-weight: 700;
  }

  h2 :global(svg) {
    color: var(--m3c-primary);
  }

  .sub {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    line-height: 1.35;
  }

  .cerrar {
    display: grid;
    flex: 0 0 auto;
    place-items: center;
    width: 2.25rem;
    height: 2.25rem;
    padding: 0;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
  }

  .cerrar:hover {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
  }

  .cuerpo {
    display: flex;
    flex: 1 1 auto;
    flex-direction: column;
    gap: var(--ns-espacio-4);
    min-height: 0;
    padding: var(--ns-espacio-5);
    overflow-y: auto;
    overscroll-behavior: contain;
  }
</style>
