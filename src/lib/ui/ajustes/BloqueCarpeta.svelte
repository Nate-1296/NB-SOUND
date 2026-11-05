<!--
  @component
  Ajustes > Biblioteca: la carpeta de tu música y "Cambiar". Antes solo se veía
  la ruta.

  Elegir otra no cambia nada todavía: primero se dice cuántas canciones de la
  biblioteca hay en ella. Si están todas (la moviste tú, a otro disco por
  ejemplo), basta con apuntar a ella; si no, NB Sound puede llevarlas, con su
  progreso, y si algo falla todo vuelve a su sitio (`catalogo/carpeta.rs`).
-->
<script lang="ts">
  import { onDestroy } from 'svelte';
  import { carpetaMusica, NsError } from '#lib/core/ipc/index.ts';
  import {
    alMoverLaMusica,
    aplicarCarpetaMusica,
    elegirCarpetaMusica,
    type RevisionCarpeta
  } from '#lib/core/ipc/aparte.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import { textosAparte } from '#lib/i18n/aparte.ts';
  import Icon from '#lib/ui/Icon.svelte';

  const t = textos.ajustes;
  const tc = textosAparte.carpetaMusica;

  let actual = $state<string | null | undefined>(undefined);
  let revision = $state<RevisionCarpeta | null>(null);
  let avance = $state<[number, number] | null>(null);
  let dialogo = $state<HTMLDialogElement>();
  let soltar: (() => void) | null = null;

  async function leer() {
    actual = await carpetaMusica().catch(() => null);
  }
  void leer();

  onDestroy(() => soltar?.());

  $effect(() => {
    if (!dialogo) return;
    if (revision && !dialogo.open) dialogo.showModal();
    else if (!revision && dialogo.open) dialogo.close();
  });

  async function cambiar() {
    const r = await elegirCarpetaMusica().catch(() => {
      notificar.error(textosAparte.comun.error);
      return null;
    });
    if (!r) return;
    if (r.misma) {
      notificar.informacion(tc.misma);
      return;
    }
    revision = r;
  }

  async function aplicar(mover: boolean) {
    if (mover) {
      avance = [0, revision?.total ?? 0];
      soltar = await alMoverLaMusica((a) => (avance = a));
    }
    try {
      const n = await aplicarCarpetaMusica(mover);
      notificar.exito(mover && n > 0 ? tc.movidas(n) : tc.hecho);
      revision = null;
      await leer();
    } catch (e) {
      notificar.error(e instanceof NsError && e.code === 'INVALID_INPUT' ? tc.dentro : tc.fallo);
      revision = null;
    } finally {
      soltar?.();
      soltar = null;
      avance = null;
    }
  }
</script>

<div class="ajuste">
  <span class="rotulo">{t.carpeta}</span>
  <span class="valor">
    {#if actual !== undefined}<code>{actual ?? t.sinCarpeta}</code>{/if}
    <button type="button" class="boton" onclick={cambiar} disabled={avance !== null}>
      <Icon nombre="carpeta" tamano={16} />{tc.cambiar}
    </button>
  </span>
</div>

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
  .ajuste {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-4);
  }

  .rotulo {
    font-size: var(--ns-texto-sm);
    font-weight: 600;
  }

  .valor {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    min-width: 0;
  }

  code {
    overflow: hidden;
    color: var(--m3c-on-surface-variant);
    font-family: var(--ns-font-mono);
    font-size: var(--ns-texto-sm);
    text-overflow: ellipsis;
    white-space: nowrap;
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

  .boton:hover:not(:disabled) {
    background: var(--m3c-surface-container-highest);
  }

  .boton:disabled {
    opacity: 0.38;
    cursor: default;
  }

  .boton.relleno {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

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
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
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
