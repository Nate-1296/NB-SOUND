<!--
  @component
  Tarjeta y panel de gestión y purga de canciones duplicadas (FDB-02, COMP-07).
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { duplicadosResumen, purgarDuplicados, type ResumenDuplicados } from '$core/ipc/aparte';
  import { textos } from '$lib/i18n';
  import { esAparte } from '$lib/i18n/es-aparte';
  import Icon from '../Icon.svelte';

  const t = esAparte.duplicados;
  let resumen = $state<ResumenDuplicados | null>(null);
  let cargando = $state(true);
  let purgando = $state(false);
  let dialogoAbierto = $state(false);
  let borrarArchivos = $state(true);

  async function cargar() {
    cargando = true;
    try {
      resumen = await duplicadosResumen();
    } catch {
      resumen = null;
    } finally {
      cargando = false;
    }
  }

  onMount(() => {
    void cargar();
  });

  function formatearBytes(b: number): string {
    if (b < 1024 * 1024) return `${Math.round(b / 1024)} KB`;
    return `${(b / (1024 * 1024)).toFixed(1)} MB`;
  }

  async function confirmarPurga() {
    purgando = true;
    dialogoAbierto = false;
    try {
      const cantidad = await purgarDuplicados(borrarArchivos);
      window.dispatchEvent(
        new CustomEvent('ns:notificacion', {
          detail: { tipo: 'exito', mensaje: t.purgadas(cantidad) }
        })
      );
      await cargar();
    } catch {
      window.dispatchEvent(
        new CustomEvent('ns:notificacion', {
          detail: { tipo: 'error', mensaje: t.error }
        })
      );
    } finally {
      purgando = false;
    }
  }
</script>

<div class="tarjeta-duplicados">
  <div class="cabecera">
    <div class="icono-contenedor">
      <Icon nombre="cancion" tamano={22} />
    </div>
    <div class="info">
      <h3>{t.titulo}</h3>
      <p class="descripcion">{t.descripcion}</p>
    </div>
  </div>

  <div class="estado">
    {#if cargando}
      <p class="mensaje-estado">{textos.biblioteca.cargando}</p>
    {:else if !resumen || resumen.total === 0}
      <div class="vacio">
        <Icon nombre="comprobado" tamano={18} />
        <span>{t.sinDuplicados}</span>
      </div>
    {:else}
      <div class="con-duplicados">
        <span class="alerta">
          <Icon nombre="advertencia" tamano={18} />
          {t.encontrados(resumen.total, formatearBytes(resumen.bytesRecuperables))}
        </span>
        <button
          type="button"
          class="boton-accion"
          disabled={purgando}
          onclick={() => (dialogoAbierto = true)}
        >
          <Icon nombre="borrar" tamano={16} />
          {t.limpiar}
        </button>
      </div>
    {/if}
  </div>
</div>

{#if dialogoAbierto && resumen}
  <div
    class="velo-dialogo"
    role="presentation"
    onclick={(e) => {
      if (e.target === e.currentTarget) dialogoAbierto = false;
    }}
  >
    <div class="dialogo" role="dialog" aria-modal="true" aria-labelledby="t-dialogo-duplicados">
      <h4 id="t-dialogo-duplicados">{t.confirmarTitulo}</h4>
      <p>{t.confirmarPregunta(resumen.total)}</p>

      <label class="opcion-borrar">
        <input type="checkbox" bind:checked={borrarArchivos} />
        <span>{t.borrarArchivos}</span>
      </label>

      <div class="acciones">
        <button type="button" class="btn-cancelar" onclick={() => (dialogoAbierto = false)}>
          {t.cancelar}
        </button>
        <button type="button" class="btn-confirmar" onclick={confirmarPurga}>
          <Icon nombre="borrar" tamano={16} />
          {t.purgarBtn}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .tarjeta-duplicados {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-low);
    margin-top: var(--ns-espacio-3);
  }

  .cabecera {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
  }

  .icono-contenedor {
    display: grid;
    place-items: center;
    width: 2.5rem;
    height: 2.5rem;
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-primary);
  }

  .info h3 {
    margin: 0;
    font-size: var(--ns-texto-base);
    font-weight: 600;
    color: var(--m3c-on-surface);
  }

  .descripcion {
    margin: var(--ns-espacio-1) 0 0;
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
  }

  .estado {
    padding-top: var(--ns-espacio-2);
    border-top: 1px solid var(--m3c-outline-variant);
  }

  .mensaje-estado {
    margin: 0;
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
  }

  .vacio {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    font-size: var(--ns-texto-sm);
    color: var(--m3c-on-surface-variant);
  }

  .con-duplicados {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-3);
  }

  .alerta {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    font-size: var(--ns-texto-sm);
    color: var(--m3c-on-surface);
    font-weight: 500;
  }

  .boton-accion {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border: none;
    border-radius: var(--ns-radio-md);
    background: var(--m3c-error);
    color: var(--m3c-on-error);
    font-size: var(--ns-texto-xs);
    font-weight: 600;
    cursor: pointer;
  }

  .velo-dialogo {
    position: fixed;
    inset: 0;
    z-index: 1000;
    display: grid;
    place-items: center;
    background: var(--m3c-scrim);
  }

  .dialogo {
    width: min(90vw, 28rem);
    padding: var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-xl);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
    box-shadow: 0 8px 32px var(--m3c-shadow);
  }

  .dialogo h4 {
    margin: 0 0 var(--ns-espacio-2);
    font-size: var(--ns-texto-lg);
    font-weight: 600;
  }

  .dialogo p {
    margin: 0 0 var(--ns-espacio-3);
    font-size: var(--ns-texto-sm);
    color: var(--m3c-on-surface-variant);
    line-height: 1.4;
  }

  .opcion-borrar {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    margin-bottom: var(--ns-espacio-4);
    font-size: var(--ns-texto-sm);
    cursor: pointer;
  }

  .acciones {
    display: flex;
    justify-content: flex-end;
    gap: var(--ns-espacio-2);
  }

  .btn-cancelar {
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline);
    border-radius: var(--ns-radio-md);
    background: transparent;
    color: var(--m3c-on-surface);
    font-size: var(--ns-texto-xs);
    font-weight: 600;
    cursor: pointer;
  }

  .btn-confirmar {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border: none;
    border-radius: var(--ns-radio-md);
    background: var(--m3c-error);
    color: var(--m3c-on-error);
    font-size: var(--ns-texto-xs);
    font-weight: 600;
    cursor: pointer;
  }
</style>
