<!--
  @component
  Ofrecer un agregado donde hace falta (F5.1.4, ADR-006): pulsar el micrófono sin
  el agregado de karaoke lo ofrece ahí mismo, con su tamaño, y se sigue
  escuchando mientras se instala. Se carga aparte del arranque.
-->
<script lang="ts">
  import { type EstadoAgregado, type IdAgregado, NsError } from '$core/ipc';
  import { agregadoInstalar, agregadosEstado, alCambiarLosAgregados } from '$core/ipc/aparte';
  import { textosAparte } from '$lib/i18n/aparte';

  interface Props {
    id: IdAgregado;
    oncerrar: () => void;
  }

  let { id, oncerrar }: Props = $props();
  const t = textosAparte.agregados;

  let dialogo: HTMLDialogElement | undefined = $state();
  let agregado = $state<EstadoAgregado | null>(null);
  let fallo = $state<string | null>(null);

  async function refrescar() {
    agregado = (await agregadosEstado()).find((a) => a.id === id) ?? null;
  }

  $effect(() => {
    dialogo?.showModal();
    void refrescar();
    const quitar = alCambiarLosAgregados(() => void refrescar());
    return () => void quitar.then((f) => f());
  });

  async function instalar() {
    fallo = null;
    try {
      await agregadoInstalar(id);
    } catch (error) {
      const codigo = error instanceof NsError ? error.code : '';
      fallo = t.errores[codigo] ?? t.error;
    }
  }

  const megas = (bytes: number) => Math.round(bytes / 1_048_576);
</script>

<dialog bind:this={dialogo} onclose={oncerrar} aria-labelledby="titulo-oferta">
  <h2 id="titulo-oferta">{t.nombres[id]}</h2>
  <p>{t.descripciones[id]}</p>
  {#if agregado}
    {#if agregado.instalado}
      <p>{t.ofertaLista}</p>
    {:else if agregado.progreso !== null}
      <progress max="1" value={agregado.progreso} aria-label={t.nombres[id]}></progress>
      <p>{t.descargando(Math.floor(agregado.progreso * 100))} · {t.ofertaSigue}</p>
    {:else if !agregado.publicado}
      <p>{t.noDisponible}</p>
    {:else}
      <p>{t.ofertaNecesita(megas(agregado.bytes))}</p>
    {/if}
    {#if agregado.error}<p class="error" role="alert">
        {t.errores[agregado.error] ?? t.error}
      </p>{/if}
  {/if}
  {#if fallo}<p class="error" role="alert">{fallo}</p>{/if}
  <div class="botones">
    <button type="button" class="boton" onclick={() => dialogo?.close()}>{t.cerrar}</button>
    {#if agregado?.publicado && !agregado.instalado && agregado.progreso === null}
      <button type="button" class="boton principal" onclick={instalar}>
        {t.instalar(megas(agregado.bytes))}
      </button>
    {/if}
  </div>
</dialog>

<style>
  dialog {
    width: min(26rem, 90vw);
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

  h2 {
    margin: 0 0 var(--ns-espacio-3);
    font-size: var(--ns-texto-lg);
  }

  p {
    margin: 0 0 var(--ns-espacio-3);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .error {
    color: var(--m3c-error);
  }

  progress {
    width: 100%;
    accent-color: var(--m3c-primary);
  }

  .botones {
    display: flex;
    justify-content: flex-end;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-4);
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
