<!--
  @component
  Ajustes > Biblioteca > Copia de seguridad (F4.2.6): crear una copia, restaurar
  una (que se aplica al reiniciar) y las copias automáticas. Los archivos y la
  carpeta se eligen con el selector nativo desde Rust: ninguna ruta cruza el
  puente. Se carga aparte del arranque.
-->
<script lang="ts">
  import {
    copiaCrear,
    copiaElegirCarpeta,
    copiaEstado,
    copiaFrecuencia,
    copiaRestaurar,
    type EstadoCopia,
    NsError,
    reiniciar
  } from '$core/ipc';
  import { textosAparte } from '$lib/i18n/aparte';

  const t = textosAparte.copia;
  const FRECUENCIAS = [0, 1, 7, 30];

  let estado = $state<EstadoCopia | null>(null);
  let ocupado = $state(false);
  let mensaje = $state<string | null>(null);
  let confirmar: HTMLDialogElement | undefined = $state();

  $effect(() => {
    void copiaEstado().then((e) => (estado = e));
  });

  function explicar(error: unknown): string {
    const codigo = error instanceof NsError ? error.code : '';
    if (codigo === 'FORMAT_UNSUPPORTED') return t.errorFormato;
    if (codigo === 'SCHEMA_MISMATCH') return t.errorNueva;
    if (codigo === 'INTEGRITY_MISMATCH') return t.errorDanada;
    return t.error;
  }

  async function crear() {
    ocupado = true;
    mensaje = t.creando;
    try {
      const r = await copiaCrear();
      mensaje = r ? t.creada((r.bytes / 1_048_576).toFixed(1), r.portadas) : null;
      estado = await copiaEstado();
    } catch (error) {
      mensaje = explicar(error);
    } finally {
      ocupado = false;
    }
  }

  async function restaurar() {
    confirmar?.close();
    ocupado = true;
    mensaje = null;
    try {
      if (await copiaRestaurar()) estado = await copiaEstado();
    } catch (error) {
      mensaje = explicar(error);
    } finally {
      ocupado = false;
    }
  }

  async function cambiar(paso: () => Promise<EstadoCopia>) {
    try {
      estado = await paso();
    } catch (error) {
      mensaje = explicar(error);
    }
  }

  function fecha(iso: string): string {
    const d = new Date(iso);
    return Number.isNaN(d.getTime())
      ? iso
      : d.toLocaleString('es', { dateStyle: 'medium', timeStyle: 'short' });
  }
</script>

<h3>{t.titulo}</h3>
<p>{t.ayuda}</p>
{#if estado?.restauracionPendiente}
  <div class="pendiente" role="status">
    <span>{t.pendiente}</span>
    <button type="button" class="boton principal" onclick={() => reiniciar()}>
      {t.reiniciar}
    </button>
  </div>
{/if}
<div class="botones">
  <button type="button" class="boton" disabled={ocupado} onclick={crear}>{t.crear}</button>
  <button type="button" class="boton" disabled={ocupado} onclick={() => confirmar?.showModal()}>
    {t.restaurar}
  </button>
</div>
{#if mensaje}<p role="status">{mensaje}</p>{/if}

{#if estado}
  <label class="ajuste">
    <span class="rotulo">
      {t.automaticas}
      <small>{estado.ultima ? t.ultima(fecha(estado.ultima)) : t.ninguna}</small>
    </span>
    <select
      class="campo"
      value={String(estado.cadaDias)}
      onchange={(e) => cambiar(() => copiaFrecuencia(Number(e.currentTarget.value)))}
    >
      {#each FRECUENCIAS as dias (dias)}
        <option value={String(dias)}>{t.frecuencias[dias]}</option>
      {/each}
    </select>
  </label>
  {#if estado.cadaDias > 0}
    <div class="ajuste">
      <span class="rotulo">
        {t.carpeta}
        <small>{estado.carpeta ?? t.sinCarpeta}</small>
      </span>
      <button type="button" class="boton" onclick={() => cambiar(copiaElegirCarpeta)}>
        {t.elegirCarpeta}
      </button>
    </div>
  {/if}
{/if}

<dialog bind:this={confirmar} class="confirmar" aria-labelledby="titulo-restaurar">
  <h2 id="titulo-restaurar">{t.confirmarTitulo}</h2>
  <p>{t.confirmarTexto}</p>
  <div class="botones fin">
    <button type="button" class="boton" onclick={() => confirmar?.close()}>{t.cancelar}</button>
    <button type="button" class="boton principal" onclick={restaurar}>{t.elegirCopia}</button>
  </div>
</dialog>

<style>
  h3 {
    margin: var(--ns-espacio-3) 0 0;
    font-size: var(--ns-texto-md);
  }

  p {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .ajuste {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-4);
  }

  .rotulo {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    font-size: var(--ns-texto-sm);
    font-weight: 600;
  }

  .rotulo small {
    color: var(--m3c-on-surface-variant);
    font-weight: 400;
  }

  .campo {
    min-width: 14rem;
    height: 2.5rem;
    padding: 0 var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
  }

  .botones {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ns-espacio-2);
  }

  .botones.fin {
    justify-content: flex-end;
    margin-top: var(--ns-espacio-4);
  }

  .pendiente {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-3);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
    font-size: var(--ns-texto-sm);
  }

  .boton {
    flex: none;
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

  .boton:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .confirmar {
    width: min(26rem, 90vw);
    padding: var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
  }

  .confirmar::backdrop {
    background: var(--m3c-scrim);
    opacity: 0.5;
  }

  .confirmar h2 {
    margin: 0 0 var(--ns-espacio-3);
    font-size: var(--ns-texto-lg);
  }
</style>
