<!--
  @component
  Diálogo modal estilizado de confirmación (COMP-18).
  Sustituye a window.confirm() con soporte completo de accesibilidad: enfoque
  inicial en Cancelar, cierre con Escape y botón de confirmación destacable.
-->
<script lang="ts">
  import { textos } from '$lib/i18n';
  import Icon from './Icon.svelte';

  interface Props {
    abierto: boolean;
    titulo: string;
    mensaje: string;
    textoConfirmar?: string;
    destructivo?: boolean;
    onconfirmar: () => void;
    oncerrar: () => void;
  }

  let {
    abierto,
    titulo,
    mensaje,
    textoConfirmar,
    destructivo = false,
    onconfirmar,
    oncerrar
  }: Props = $props();

  let dialogo: HTMLDialogElement | undefined = $state();
  let botonCancelar: HTMLButtonElement | undefined = $state();

  $effect(() => {
    if (!dialogo) return;
    if (abierto) {
      if (!dialogo.open) {
        dialogo.showModal();
        botonCancelar?.focus();
      }
    } else if (dialogo.open) {
      dialogo.close();
    }
  });

  function alPulsarFondo(e: MouseEvent) {
    if (e.target === dialogo) {
      oncerrar();
    }
  }
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
<dialog
  bind:this={dialogo}
  class="dialogo"
  oncancel={(e) => {
    e.preventDefault();
    oncerrar();
  }}
  onclick={alPulsarFondo}
>
  <div class="contenido">
    <div class="cabecera">
      <div class="icono" class:destructivo>
        <Icon nombre={destructivo ? 'advertencia' : 'informacion'} tamano={24} />
      </div>
      <h2>{titulo}</h2>
    </div>

    <p class="mensaje">{mensaje}</p>

    <div class="acciones">
      <button type="button" bind:this={botonCancelar} class="boton cancelar" onclick={oncerrar}>
        {textos.playlists.cancelar}
      </button>
      <button
        type="button"
        class="boton confirmar"
        class:destructivo
        onclick={() => {
          onconfirmar();
          oncerrar();
        }}
      >
        {textoConfirmar ?? (destructivo ? textos.playlists.borrar : textos.playlists.guardar)}
      </button>
    </div>
  </div>
</dialog>

<style>
  .dialogo {
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
    padding: 0;
    max-width: 28rem;
    width: calc(100% - var(--ns-espacio-6));
    box-shadow: var(--m3-elevation-3, none);
  }

  .dialogo::backdrop {
    background: var(--m3c-scrim);
    opacity: 0.5;
  }

  .contenido {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-5);
  }

  .cabecera {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
  }

  .icono {
    display: grid;
    place-items: center;
    width: 2.5rem;
    height: 2.5rem;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-primary);
    flex: 0 0 2.5rem;
  }

  .icono.destructivo {
    background: var(--m3c-error-container);
    color: var(--m3c-on-error-container);
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
    font-weight: 700;
  }

  .mensaje {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
    line-height: 1.4;
  }

  .acciones {
    display: flex;
    justify-content: flex-end;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-2);
  }

  .boton {
    height: 2.5rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    cursor: pointer;
  }

  .boton.cancelar:hover {
    background: var(--m3c-surface-container-highest);
  }

  .boton.confirmar {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .boton.confirmar:hover {
    filter: brightness(1.08);
  }

  .boton.confirmar.destructivo {
    border-color: var(--m3c-error);
    background: var(--m3c-error);
    color: var(--m3c-on-error);
  }
</style>
