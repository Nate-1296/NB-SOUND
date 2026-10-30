<!--
  @component
  El diálogo para crear o renombrar una playlist. Los errores del runtime
  (nombre vacío o repetido) se dicen debajo del campo, con su texto.
-->
<script lang="ts">
  import { crearPlaylist, NsError, renombrarPlaylist } from '$core/ipc';
  import { textos } from '$lib/i18n';

  interface Props {
    abierto: boolean;
    /** Para renombrar; sin él, se crea una nueva. */
    editar?: { id: number; nombre: string; descripcion: string | null } | null;
    onlisto: (id: number, nombre: string) => void;
    oncerrar: () => void;
  }

  let { abierto, editar = null, onlisto, oncerrar }: Props = $props();
  const t = textos.playlists;

  let dialogo: HTMLDialogElement | undefined = $state();
  let nombre = $state('');
  let descripcion = $state('');
  let error = $state<string | null>(null);
  let enviando = $state(false);

  $effect(() => {
    if (!dialogo) return;
    if (abierto && !dialogo.open) {
      nombre = editar?.nombre ?? '';
      descripcion = editar?.descripcion ?? '';
      error = null;
      dialogo.showModal();
    } else if (!abierto && dialogo.open) {
      dialogo.close();
    }
  });

  async function enviar(e: SubmitEvent) {
    e.preventDefault();
    enviando = true;
    try {
      const d = descripcion.trim() || null;
      if (editar) {
        await renombrarPlaylist(editar.id, nombre, d);
        onlisto(editar.id, nombre.trim());
      } else {
        onlisto(await crearPlaylist(nombre, d), nombre.trim());
      }
    } catch (causa) {
      error =
        (causa instanceof NsError ? t.errores[causa.code] : undefined) ??
        t.errores.INVALID_INPUT ??
        null;
    } finally {
      enviando = false;
    }
  }
</script>

<dialog bind:this={dialogo} onclose={oncerrar} aria-labelledby="titulo-dialogo-playlist">
  <form onsubmit={enviar}>
    <h2 id="titulo-dialogo-playlist">{editar ? t.renombrar : t.nueva}</h2>
    <label>
      <span>{t.nombre}</span>
      <!-- svelte-ignore a11y_autofocus -->
      <input bind:value={nombre} maxlength="120" required autofocus aria-invalid={error !== null} />
    </label>
    <label>
      <span>{t.descripcion}</span>
      <textarea bind:value={descripcion} rows="3"></textarea>
    </label>
    {#if error}<p class="error" role="alert">{error}</p>{/if}
    <div class="botones">
      <button type="button" class="boton" onclick={oncerrar}>{t.cancelar}</button>
      <button type="submit" class="boton principal" disabled={enviando}>
        {editar ? t.guardar : t.crear}
      </button>
    </div>
  </form>
</dialog>

<style>
  dialog {
    width: min(28rem, 90vw);
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

  form {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
  }

  label {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    font-size: var(--ns-texto-sm);
  }

  input,
  textarea {
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    resize: vertical;
  }

  .error {
    margin: 0;
    color: var(--m3c-error);
    font-size: var(--ns-texto-sm);
  }

  .botones {
    display: flex;
    justify-content: flex-end;
    gap: var(--ns-espacio-2);
  }

  .boton {
    height: 2.5rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }

  .boton.principal {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }
</style>
