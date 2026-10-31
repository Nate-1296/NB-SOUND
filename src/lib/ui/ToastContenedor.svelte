<!--
  @component
  Contenedor global de avisos toast (COMP-03).
-->
<script lang="ts">
  import { notificaciones } from '$core/notificaciones.svelte';
  import { textos } from '$lib/i18n';
  import Icon from './Icon.svelte';
  import type { NombreDeIcono } from './iconos';

  function iconoTipo(tipo: string): NombreDeIcono {
    switch (tipo) {
      case 'exito':
        return 'comprobado';
      case 'error':
        return 'error';
      case 'progreso':
        return 'cargando';
      default:
        return 'informacion';
    }
  }
</script>

<div class="toast-contenedor" aria-live="polite">
  {#each notificaciones.lista as item (item.id)}
    <div class="toast {item.tipo}" role={item.tipo === 'error' ? 'alert' : 'status'}>
      <Icon nombre={iconoTipo(item.tipo)} tamano={18} />
      <span class="mensaje">{item.mensaje}</span>
      {#if item.tipo === 'progreso' && item.progreso !== undefined}
        <span class="porcentaje">{Math.round(item.progreso)}%</span>
      {/if}
      <button
        type="button"
        class="boton-cerrar"
        aria-label={textos.ajustes.cerrar}
        onclick={() => notificaciones.quitar(item.id)}
      >
        <Icon nombre="cerrar" tamano={14} />
      </button>
    </div>
  {/each}
</div>

<style>
  .toast-contenedor {
    position: fixed;
    right: var(--ns-espacio-5);
    bottom: calc(var(--ns-alto-barra) + var(--ns-espacio-4));
    z-index: 1000;
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    max-width: 26rem;
    pointer-events: none;
  }

  .toast {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-3) var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
    box-shadow: 0 4px 16px var(--m3c-shadow);
    font-size: var(--ns-texto-sm);
    pointer-events: auto;
    animation: aparecer 150ms ease;
  }

  .toast.exito {
    border-color: var(--m3c-primary);
    background: var(--m3c-surface-container-highest);
  }

  .toast.error {
    border-color: var(--m3c-error);
    background: var(--m3c-error-container);
    color: var(--m3c-on-error-container);
  }

  .mensaje {
    flex: 1 1 auto;
    word-break: break-word;
  }

  .porcentaje {
    color: var(--m3c-primary);
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }

  .boton-cerrar {
    display: grid;
    place-items: center;
    width: 1.5rem;
    height: 1.5rem;
    padding: 0;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: inherit;
    cursor: pointer;
    opacity: 0.7;
  }

  .boton-cerrar:hover {
    background: var(--m3c-surface-container);
    opacity: 1;
  }

  @keyframes aparecer {
    from {
      opacity: 0;
      transform: translateY(8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
</style>
