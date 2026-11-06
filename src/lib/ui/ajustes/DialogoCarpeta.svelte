<!--
  @component
  La confirmación de una carpeta de música elegida, compartida por Ajustes y por
  la pregunta del arranque cuando la música no está donde estaba.

  Primero se dice cuántas canciones hay en la elegida. Si están todas, basta con
  apuntar a ella. Si faltan y la carpeta de ahora existe, NB Sound puede llevarlas
  (`catalogo/carpeta.rs`); si la de ahora se perdió no hay nada que llevar, así
  que solo se ofrece usarla o elegir otra.
-->
<script lang="ts">
  import { NsError } from '#lib/core/ipc/index.ts';
  import {
    alMoverLaMusica,
    aplicarCarpetaMusica,
    type RevisionCarpeta
  } from '#lib/core/ipc/aparte.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import { textosAparte } from '#lib/i18n/aparte.ts';

  interface Props {
    revision: RevisionCarpeta | null;
    /** La carpeta de ahora tiene la música: se puede llevar a la nueva. */
    puedeMover: boolean;
    onhecho: () => void;
    /** Volver al selector, cuando la elegida no sirve. */
    onotra: () => void;
  }

  let { revision = $bindable(), puedeMover, onhecho, onotra }: Props = $props();

  const tc = textosAparte.carpetaMusica;
  const td = textosAparte.dondeVive;

  let avance = $state<[number, number] | null>(null);
  let dialogo = $state<HTMLDialogElement>();

  $effect(() => {
    if (!dialogo) return;
    if (revision && !dialogo.open) dialogo.showModal();
    else if (!revision && dialogo.open) dialogo.close();
  });

  async function aplicar(mover: boolean) {
    let soltar: (() => void) | null = null;
    if (mover) {
      avance = [0, revision?.total ?? 0];
      soltar = await alMoverLaMusica((a) => (avance = a));
    }
    try {
      const n = await aplicarCarpetaMusica(mover);
      notificar.exito(mover && n > 0 ? tc.movidas(n) : tc.hecho);
      revision = null;
      onhecho();
    } catch (e) {
      notificar.error(e instanceof NsError && e.code === 'INVALID_INPUT' ? tc.dentro : tc.fallo);
      revision = null;
    } finally {
      soltar?.();
      avance = null;
    }
  }
</script>

<dialog
  bind:this={dialogo}
  aria-labelledby="t-carpeta"
  oncancel={(e) => {
    e.preventDefault();
    if (!avance) revision = null;
  }}
>
  {#if revision}
    <h2 id="t-carpeta">{tc.titulo}</h2>
    <code class="ruta">{revision.carpeta}</code>
    {#if avance}
      <p>{tc.moviendo(avance[0], avance[1])}</p>
      <div
        class="barra"
        role="progressbar"
        aria-valuenow={avance[0]}
        aria-valuemin={0}
        aria-valuemax={avance[1]}
      >
        <span style:width={`${avance[1] ? (avance[0] / avance[1]) * 100 : 0}%`}></span>
      </div>
    {:else if revision.encontradas >= revision.total}
      <p>{tc.yaEsta(revision.total)}</p>
      <div class="botones">
        <button type="button" class="boton" onclick={() => (revision = null)}>
          {textos.biblioteca.cancelar}
        </button>
        <button type="button" class="boton relleno" onclick={() => aplicar(false)}>
          {tc.usar}
        </button>
      </div>
    {:else if !puedeMover && revision.encontradas === 0}
      <p>{td.ninguna}</p>
      <div class="botones">
        <button type="button" class="boton" onclick={() => (revision = null)}>
          {textos.biblioteca.cancelar}
        </button>
        <button
          type="button"
          class="boton relleno"
          onclick={() => {
            revision = null;
            onotra();
          }}
        >
          {tc.otra}
        </button>
      </div>
    {:else if !puedeMover}
      <p>{tc.parcial(revision.encontradas, revision.total)}</p>
      <div class="botones">
        <button
          type="button"
          class="boton"
          onclick={() => {
            revision = null;
            onotra();
          }}
        >
          {tc.otra}
        </button>
        <button type="button" class="boton relleno" onclick={() => aplicar(false)}>
          {tc.usar}
        </button>
      </div>
    {:else}
      <p>{tc.faltan(revision.encontradas, revision.total)}</p>
      <p class="aviso">{tc.usarSinMoverAviso}</p>
      <div class="botones">
        <button type="button" class="boton" onclick={() => (revision = null)}>
          {textos.biblioteca.cancelar}
        </button>
        <button type="button" class="boton" onclick={() => aplicar(false)}>
          {tc.usarSinMover}
        </button>
        <button type="button" class="boton relleno" onclick={() => aplicar(true)}>
          {tc.mover}
        </button>
      </div>
    {/if}
  {/if}
</dialog>

<style>
  dialog {
    width: min(34rem, 90vw);
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

  dialog[open] {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
  }

  .ruta {
    display: block;
    overflow-wrap: anywhere;
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
    font-family: var(--ns-font-mono);
    font-size: var(--ns-texto-sm);
  }

  p {
    margin: 0;
    font-size: var(--ns-texto-sm);
    line-height: 1.5;
  }

  .aviso {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .botones {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-2);
  }

  .boton {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    gap: var(--ns-espacio-2);
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

  .boton:hover {
    background: var(--m3c-surface-container-highest);
  }

  .boton.relleno {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .barra {
    height: 0.5rem;
    overflow: hidden;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
  }

  .barra span {
    display: block;
    height: 100%;
    background: var(--m3c-primary);
    transition: width var(--ns-duracion-corta) linear;
  }
</style>
