<!--
  @component
  Consola lateral de Dispositivos:
  Panel lateral para sincronización remota, gestión de teléfonos y modo fiesta.
-->
<script lang="ts">
  import { textos } from '$lib/i18n';
  import Icon from '$ui/Icon.svelte';
  import SeccionDispositivos from './SeccionDispositivos.svelte';

  const { oncerrar }: { oncerrar: () => void } = $props();

  const t = textos.ajustes;

  function alPulsar(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      oncerrar();
    }
  }
</script>

<svelte:window onkeydown={alPulsar} />

<div
  class="fondo-drawer"
  role="presentation"
  onclick={oncerrar}
  onkeydown={(e) => e.key === 'Escape' && oncerrar()}
></div>

<div class="drawer" aria-label={t.dispositivos} aria-modal="true" role="dialog">
  <header class="drawer-cabecera">
    <div class="drawer-titulos">
      <div class="icono-titulo">
        <Icon nombre="telefono" tamano={22} />
        <h2>{t.dispositivos}</h2>
      </div>
      <p class="drawer-sub">{t.permitirAyuda}</p>
    </div>
    <button
      type="button"
      class="boton-cerrar"
      onclick={oncerrar}
      aria-label={textos.importacion.cerrar}
      title={textos.importacion.cerrar}
    >
      <Icon nombre="cerrar" tamano={20} />
    </button>
  </header>

  <div class="drawer-cuerpo">
    <SeccionDispositivos />
  </div>
</div>

<style>
  .fondo-drawer {
    position: fixed;
    inset: 0;
    background: color-mix(in srgb, var(--m3c-scrim) 45%, transparent);
    z-index: 100;
  }

  .drawer {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(92vw, 32rem);
    background: var(--m3c-surface);
    border-left: 1px solid var(--m3c-outline-variant);
    z-index: 101;
    display: flex;
    flex-direction: column;
    box-shadow: -8px 0 32px var(--m3c-shadow);
    animation: aparecer 200ms cubic-bezier(0.2, 0, 0, 1);
  }

  @keyframes aparecer {
    from {
      transform: translateX(100%);
    }
    to {
      transform: translateX(0);
    }
  }

  .drawer-cabecera {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-5);
    border-bottom: 1px solid var(--m3c-outline-variant);
    background: var(--m3c-surface-container-low);
  }

  .drawer-titulos {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    min-width: 0;
  }

  .icono-titulo {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    color: var(--m3c-primary);
  }

  .icono-titulo h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
    font-weight: 700;
    color: var(--m3c-on-surface);
  }

  .drawer-sub {
    margin: 0;
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
    line-height: 1.35;
  }

  .boton-cerrar {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2.25rem;
    height: 2.25rem;
    padding: 0;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
    flex-shrink: 0;
    transition: background 120ms ease;
  }

  .boton-cerrar:hover {
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
  }

  .drawer-cuerpo {
    flex: 1;
    overflow-y: auto;
    padding: var(--ns-espacio-5);
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
  }

  .drawer-cuerpo :global(section#dispositivos) {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
  }

  .drawer-cuerpo :global(section#dispositivos h2) {
    display: none;
  }
</style>
