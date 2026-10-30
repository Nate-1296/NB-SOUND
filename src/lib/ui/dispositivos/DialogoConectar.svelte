<!--
  @component
  Conectar un teléfono (F3.3.1): el QR, el código corto para teclearlo y cuánto
  falta para que caduque. No hay más pantallas: cuando el teléfono se empareja, el
  diálogo lo dice y se cierra solo.
-->
<script lang="ts">
  import { type Emparejar, movilEmparejar } from '$core/ipc';
  import { telefonos } from '$core/movil.svelte';
  import { textos } from '$lib/i18n';

  interface Props {
    abierto: boolean;
    oncerrar: () => void;
  }

  let { abierto, oncerrar }: Props = $props();
  const t = textos.ajustes;

  let dialogo: HTMLDialogElement | undefined = $state();
  let datos = $state<Emparejar | null>(null);
  let resta = $state(0);
  let error = $state(false);
  let emparejado = $state<string | null>(null);
  /** Los que ya estaban, para reconocer al nuevo. */
  let antes = new Set<number>();

  async function pedir() {
    error = false;
    emparejado = null;
    antes = new Set(telefonos.lista.map((x) => x.id));
    try {
      datos = await movilEmparejar();
      resta = datos.segundos;
    } catch {
      datos = null;
      error = true;
    }
  }

  $effect(() => {
    if (!dialogo) return;
    if (abierto && !dialogo.open) {
      dialogo.showModal();
      void pedir();
    } else if (!abierto && dialogo.open) {
      dialogo.close();
    }
  });

  // La cuenta atrás solo corre con el diálogo abierto.
  $effect(() => {
    if (!abierto || !datos) return;
    const reloj = setInterval(() => (resta = Math.max(0, resta - 1)), 1000);
    return () => clearInterval(reloj);
  });

  // El servidor avisa al emparejar; la lista nueva trae al recién llegado.
  $effect(() => {
    if (!abierto || emparejado) return;
    const nuevo = telefonos.lista.find((x) => !antes.has(x.id));
    if (!nuevo) return;
    emparejado = nuevo.nombre;
    const cierre = setTimeout(oncerrar, 2500);
    return () => clearTimeout(cierre);
  });
</script>

<dialog bind:this={dialogo} onclose={oncerrar} aria-labelledby="titulo-conectar">
  <h2 id="titulo-conectar">{t.tituloQr}</h2>
  {#if emparejado}
    <p class="hecho" role="status">{t.emparejado(emparejado)}</p>
  {:else if error}
    <p class="error" role="alert">{t.sinServidor}</p>
  {:else if datos}
    <p>{t.instruccionesQr}</p>
    <div class="qr" class:caducado={resta === 0}>
      <svg
        viewBox={`-4 -4 ${datos.qr.lado + 8} ${datos.qr.lado + 8}`}
        role="img"
        aria-label={t.qr}
        shape-rendering="crispEdges"
      >
        <rect x="-4" y="-4" width={datos.qr.lado + 8} height={datos.qr.lado + 8} class="fondo" />
        <path d={datos.qr.trazado} class="tinta" />
      </svg>
    </div>
    <p>{t.codigoManual}</p>
    <p class="codigo">{datos.codigo}</p>
    <p class="caduca" aria-live="polite">{resta > 0 ? t.caduca(resta) : t.caducado}</p>
  {/if}
  <div class="botones">
    {#if !emparejado}
      <button type="button" class="boton" onclick={pedir}>{t.otroCodigo}</button>
    {/if}
    <button type="button" class="boton principal" onclick={oncerrar}>{t.cerrar}</button>
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

  .qr {
    width: 15rem;
    margin: 0 auto var(--ns-espacio-4);
    border-radius: var(--ns-radio-md);
    overflow: hidden;
  }

  .qr.caducado {
    opacity: 0.25;
  }

  .qr svg {
    display: block;
    width: 100%;
    height: auto;
  }

  .fondo {
    fill: var(--ns-qr-fondo);
  }

  .tinta {
    fill: var(--ns-qr-tinta);
  }

  .codigo {
    color: var(--m3c-on-surface);
    font-family: var(--ns-font-mono);
    font-size: var(--ns-texto-xl);
    letter-spacing: 0.2em;
    text-align: center;
  }

  .caduca {
    font-variant-numeric: tabular-nums;
    text-align: center;
  }

  .hecho {
    color: var(--m3c-on-surface);
    font-size: var(--ns-texto-md);
  }

  .error {
    color: var(--m3c-error);
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
