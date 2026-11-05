<!--
  @component
  Las copias que la deduplicación apartó al importar (FDB-02): cuántas son, qué
  ocupan y cómo quitarlas. Solo cuenta lo que decidió la deduplicación, con sus
  tres ejes (`catalogo/duplicados.rs`): adivinar duplicados por título y duración
  juntaba canciones distintas. Los archivos van a la papelera, nunca se borran.
-->
<script lang="ts">
  import { onMount } from 'svelte';

  import {
    duplicadosResumen,
    purgarDuplicados,
    type ResumenDuplicados
  } from '#lib/core/ipc/aparte.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import { esAparte } from '#lib/i18n/es-aparte.ts';

  import Icon from '../Icon.svelte';

  const t = esAparte.duplicados;
  let resumen = $state<ResumenDuplicados | null>(null);
  let cargando = $state(true);
  let limpiando = $state(false);
  let conArchivos = $state(true);
  let dialogo: HTMLDialogElement | undefined = $state();

  const megas = $derived(Math.max(1, Math.round((resumen?.bytes ?? 0) / (1024 * 1024))));

  async function cargar() {
    cargando = true;
    resumen = await duplicadosResumen().catch(() => null);
    cargando = false;
  }

  onMount(() => void cargar());

  async function limpiar() {
    dialogo?.close();
    limpiando = true;
    try {
      notificar.exito(t.purgadas(await purgarDuplicados(conArchivos)));
      await cargar();
    } catch {
      notificar.error(t.error);
    } finally {
      limpiando = false;
    }
  }
</script>

<section class="tarjeta" aria-labelledby="duplicados-titulo">
  <div class="cabecera">
    <span class="icono"><Icon nombre="cancion" tamano={22} /></span>
    <div>
      <h3 id="duplicados-titulo">{t.titulo}</h3>
      <p class="descripcion">{t.descripcion}</p>
    </div>
  </div>

  <div class="estado" role="status">
    {#if cargando}
      <span class="tenue">{textos.biblioteca.cargando}</span>
    {:else if !resumen || resumen.total === 0}
      <span class="tenue"><Icon nombre="comprobado" tamano={18} />{t.sinDuplicados}</span>
    {:else}
      <span class="alerta"
        ><Icon nombre="advertencia" tamano={18} />{t.encontrados(resumen.total, megas)}</span
      >
      <button
        type="button"
        class="boton destructivo"
        disabled={limpiando}
        onclick={() => dialogo?.showModal()}
      >
        <Icon nombre="borrar" tamano={16} />{t.limpiar}
      </button>
    {/if}
  </div>
</section>

<dialog bind:this={dialogo} aria-labelledby="duplicados-confirmar">
  <h4 id="duplicados-confirmar">{t.confirmarTitulo}</h4>
  <p>{t.confirmarPregunta(resumen?.total ?? 0)}</p>
  <label class="opcion">
    <input type="checkbox" bind:checked={conArchivos} />
    <span>{t.borrarArchivos}</span>
  </label>
  <div class="acciones">
    <button type="button" class="boton" onclick={() => dialogo?.close()}>{t.cancelar}</button>
    <button type="button" class="boton destructivo" onclick={limpiar}>
      <Icon nombre="borrar" tamano={16} />{t.purgarBtn}
    </button>
  </div>
</dialog>

<style>
  .tarjeta {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    margin-top: var(--ns-espacio-3);
    padding: var(--ns-espacio-4);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container);
  }

  .cabecera {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
  }

  .icono {
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    width: 2.5rem;
    height: 2.5rem;
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-primary);
  }

  h3 {
    margin: 0;
    font-size: var(--ns-texto-md);
    font-weight: 600;
  }

  .descripcion {
    margin: var(--ns-espacio-1) 0 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .estado {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-3);
    padding-top: var(--ns-espacio-3);
    border-top: 1px solid var(--m3c-outline-variant);
    font-size: var(--ns-texto-sm);
  }

  .tenue,
  .alerta {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
  }

  .tenue {
    color: var(--m3c-on-surface-variant);
  }

  .alerta {
    font-weight: 500;
  }

  .boton {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    padding: var(--ns-espacio-2) var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline);
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    cursor: pointer;
  }

  .boton.destructivo {
    border-color: transparent;
    background: var(--m3c-error);
    color: var(--m3c-on-error);
  }

  .boton:disabled {
    opacity: 0.5;
    cursor: default;
  }

  dialog {
    width: min(90vw, 28rem);
    padding: var(--ns-espacio-5);
    border: none;
    border-radius: var(--ns-radio-xl);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
    box-shadow: 0 8px 32px var(--m3c-shadow);
  }

  dialog::backdrop {
    background: var(--m3c-scrim);
    opacity: 0.4;
  }

  h4 {
    margin: 0 0 var(--ns-espacio-2);
    font-size: var(--ns-texto-lg);
  }

  dialog p {
    margin: 0 0 var(--ns-espacio-4);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
    line-height: 1.45;
  }

  .opcion {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    margin-bottom: var(--ns-espacio-5);
    font-size: var(--ns-texto-sm);
    cursor: pointer;
  }

  .acciones {
    display: flex;
    justify-content: flex-end;
    gap: var(--ns-espacio-2);
  }
</style>
