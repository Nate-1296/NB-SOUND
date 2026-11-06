<!--
  @component
  Al abrir, si la música no está donde estaba y NB Sound no la encontró sola
  (`catalogo/ubicacion.rs`), se pregunta dónde está. Si la encontró, se dice una
  vez. Se carga solo en esos dos casos: en un arranque normal no existe.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import type { UbicacionMusica } from '#lib/core/ipc/index.ts';
  import { elegirCarpetaMusica, type RevisionCarpeta } from '#lib/core/ipc/aparte.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { textosAparte } from '#lib/i18n/aparte.ts';
  import Icon from '#lib/ui/Icon.svelte';
  import DialogoCarpeta from './DialogoCarpeta.svelte';

  interface Props {
    ubicacion: UbicacionMusica;
  }

  let { ubicacion }: Props = $props();

  const td = textosAparte.dondeVive;

  let preguntando = $state(false);
  let revision = $state<RevisionCarpeta | null>(null);
  let dialogo = $state<HTMLDialogElement>();

  // El aviso llega una sola vez desde el runtime: se lee al montar y no se sigue.
  onMount(() => {
    if (ubicacion.perdida) preguntando = true;
    else if (ubicacion.recuperadaDe) {
      notificar.informacion(td.recuperada, ubicacion.carpeta ?? undefined);
    }
  });

  $effect(() => {
    if (!dialogo) return;
    const abierto = preguntando && !revision;
    if (abierto && !dialogo.open) dialogo.showModal();
    else if (!abierto && dialogo.open) dialogo.close();
  });

  async function buscar() {
    const r = await elegirCarpetaMusica().catch(() => {
      notificar.error(textosAparte.comun.error);
      return null;
    });
    if (r) revision = r;
  }
</script>

<dialog
  bind:this={dialogo}
  aria-labelledby="t-perdida"
  oncancel={(e) => {
    e.preventDefault();
    preguntando = false;
  }}
>
  <span class="icono" aria-hidden="true"><Icon nombre="carpeta" tamano={28} /></span>
  <h2 id="t-perdida">{td.preguntaTitulo}</h2>
  {#if ubicacion.carpeta}<code>{ubicacion.carpeta}</code>{/if}
  <p>{td.pregunta(ubicacion.total)}</p>
  <div class="botones">
    <button type="button" class="boton" onclick={() => (preguntando = false)}>{td.ahoraNo}</button>
    <!-- svelte-ignore a11y_autofocus -->
    <button type="button" class="boton relleno" autofocus onclick={buscar}>{td.buscar}</button>
  </div>
</dialog>

<DialogoCarpeta
  bind:revision
  puedeMover={false}
  onhecho={() => (preguntando = false)}
  onotra={buscar}
/>

<style>
  dialog {
    width: min(30rem, 90vw);
    padding: var(--ns-espacio-6);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
    text-align: center;
  }

  dialog::backdrop {
    background: var(--m3c-scrim);
    opacity: 0.5;
  }

  dialog[open] {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--ns-espacio-3);
  }

  .icono {
    display: grid;
    place-items: center;
    width: 3.5rem;
    height: 3.5rem;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-primary-container);
    color: var(--m3c-on-primary-container);
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-xl);
  }

  code {
    max-width: 100%;
    overflow-wrap: anywhere;
    padding: var(--ns-espacio-1) var(--ns-espacio-3);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
    font-family: var(--ns-font-mono);
    font-size: var(--ns-texto-sm);
  }

  p {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
    line-height: 1.5;
  }

  .botones {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-3);
  }

  .boton {
    height: 2.5rem;
    padding: 0 var(--ns-espacio-5);
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
</style>
