<!--
  @component
  Diálogo para eliminar una canción de la biblioteca o también del equipo (ADR-007, EXP-05).
-->
<script lang="ts">
  import { borrarPista } from '$core/ipc';
  import { textos } from '$lib/i18n';

  interface Props {
    pistaId: number;
    titulo: string;
    oneliminada: () => void;
    oncerrar: () => void;
  }

  let { pistaId, titulo, oneliminada, oncerrar }: Props = $props();
  const t = textos.biblioteca;

  let dialogo: HTMLDialogElement | undefined = $state();
  let eliminando = $state(false);

  $effect(() => {
    if (dialogo && !dialogo.open) {
      dialogo.showModal();
    }
  });

  async function ejecutarBorrado(borrarArchivo: boolean) {
    if (eliminando) return;
    eliminando = true;
    try {
      await borrarPista(pistaId, borrarArchivo);
      dialogo?.close();
      oneliminada();
    } catch {
      // fallo
    } finally {
      eliminando = false;
    }
  }
</script>

<dialog bind:this={dialogo} onclose={oncerrar} aria-labelledby="titulo-dialogo-borrar">
  <div class="contenido">
    <h2 id="titulo-dialogo-borrar">{t.confirmarBorrarTitulo}</h2>
    <p class="detalle">{t.confirmarBorrarDetalle(titulo)}</p>
    <div class="acciones-borrado">
      <button
        type="button"
        class="boton"
        disabled={eliminando}
        onclick={() => void ejecutarBorrado(false)}
      >
        {t.borrarSoloBiblioteca}
      </button>
      <button
        type="button"
        class="boton destructivo"
        disabled={eliminando}
        onclick={() => void ejecutarBorrado(true)}
      >
        {t.borrarTambienArchivo}
      </button>
    </div>
    <div class="pie">
      <button type="button" class="boton cancel" onclick={oncerrar}>{t.cancelar}</button>
    </div>
  </div>
</dialog>

<style>
  dialog {
    width: min(32rem, 90vw);
    padding: var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
  }

  dialog::backdrop {
    background: var(--m3c-scrim);
    opacity: 0.5;
  }

  .contenido {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
  }

  .detalle {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .acciones-borrado {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
  }

  .pie {
    display: flex;
    justify-content: flex-end;
    margin-top: var(--ns-espacio-2);
  }

  .boton {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: 2.5rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    cursor: pointer;
  }

  .boton:hover:not(:disabled) {
    background: var(--m3c-surface-container-highest);
  }

  .boton.destructivo {
    border-color: var(--m3c-error);
    background: var(--m3c-error-container);
    color: var(--m3c-on-error-container);
  }

  .boton.destructivo:hover:not(:disabled) {
    background: var(--m3c-error);
    color: var(--m3c-on-error);
  }

  .boton:disabled {
    opacity: 0.38;
    cursor: default;
  }
</style>
