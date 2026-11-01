<!--
  @component
  Selector desplegable con estética de app de escritorio (Material 3 Menu / Popover).
  Reemplaza el elemento nativo <select> con un botón interactivo y un menú flotante accesible.
-->
<script lang="ts" generics="T extends string | number">
  import Icon from '$ui/Icon.svelte';
  import type { NombreDeIcono } from '$ui/iconos';

  interface Opcion {
    valor: T;
    etiqueta: string;
    icono?: NombreDeIcono;
  }

  interface Props {
    opciones: readonly Opcion[];
    valor: T;
    onchange?: (nuevoValor: T) => void;
    rotulo?: string;
    ariaLabel?: string;
    deshabilitado?: boolean;
    icono?: NombreDeIcono;
    compacto?: boolean;
  }

  let {
    opciones,
    valor = $bindable(),
    onchange,
    rotulo,
    ariaLabel,
    deshabilitado = false,
    icono,
    compacto = false
  }: Props = $props();

  let abierto = $state(false);
  let botonRef = $state<HTMLButtonElement | null>(null);
  let popoverRef = $state<HTMLDivElement | null>(null);

  const opcionSeleccionada = $derived(opciones.find((o) => o.valor === valor) ?? opciones[0]);

  function alternar() {
    if (deshabilitado || !popoverRef || !botonRef) return;
    if (abierto) {
      popoverRef.hidePopover();
    } else {
      const r = botonRef.getBoundingClientRect();
      popoverRef.style.left = `${Math.max(8, r.left)}px`;
      popoverRef.style.top = `${r.bottom + 4}px`;
      popoverRef.showPopover();
    }
  }

  function seleccionar(op: Opcion) {
    valor = op.valor;
    onchange?.(op.valor);
    popoverRef?.hidePopover();
    botonRef?.focus();
  }

  function alPulsarTecla(e: KeyboardEvent) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const idx = opciones.findIndex((o) => o.valor === valor);
      const siguiente =
        e.key === 'ArrowDown' ? Math.min(opciones.length - 1, idx + 1) : Math.max(0, idx - 1);
      if (opciones[siguiente]) {
        seleccionar(opciones[siguiente]);
      }
    }
  }
</script>

<div class="menu-selector" class:compacto>
  {#if rotulo}
    <span class="rotulo">{rotulo}</span>
  {/if}
  <button
    type="button"
    class="gatillo"
    bind:this={botonRef}
    onclick={alternar}
    onkeydown={alPulsarTecla}
    disabled={deshabilitado}
    aria-haspopup="listbox"
    aria-expanded={abierto}
    aria-label={ariaLabel ?? rotulo}
  >
    {#if icono || opcionSeleccionada?.icono}
      <Icon nombre={opcionSeleccionada?.icono ?? icono!} tamano={16} />
    {/if}
    <span class="texto-seleccion">{opcionSeleccionada?.etiqueta ?? ''}</span>
    <Icon nombre="abajo" tamano={14} />
  </button>

  <div
    class="capa-popover"
    popover="auto"
    bind:this={popoverRef}
    ontoggle={(e) => (abierto = e.newState === 'open')}
  >
    {#if abierto}
      <div class="menu-opciones" role="listbox" tabindex="-1">
        {#each opciones as op (op.valor)}
          {@const esActivo = op.valor === valor}
          <button
            type="button"
            class="opcion"
            class:activa={esActivo}
            role="option"
            aria-selected={esActivo}
            onclick={() => seleccionar(op)}
          >
            {#if op.icono}
              <Icon nombre={op.icono} tamano={16} />
            {/if}
            <span class="etiqueta-opcion">{op.etiqueta}</span>
            {#if esActivo}
              <span class="marca-check">
                <Icon nombre="comprobado" tamano={14} />
              </span>
            {/if}
          </button>
        {/each}
      </div>
    {/if}
  </div>
</div>

<style>
  .menu-selector {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
  }

  .rotulo {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-weight: 500;
  }

  .gatillo {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    min-height: 2.25rem;
    padding: 0 var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 500;
    cursor: pointer;
    transition:
      background var(--ns-duracion-corta) var(--ns-curva),
      border-color var(--ns-duracion-corta) var(--ns-curva);
  }

  .gatillo:hover:not(:disabled) {
    background: var(--m3c-surface-container-high);
    border-color: var(--m3c-outline);
  }

  .gatillo:focus-visible {
    outline: 2px solid var(--m3c-primary);
    outline-offset: 1px;
  }

  .gatillo:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .texto-seleccion {
    white-space: nowrap;
  }

  .capa-popover {
    position: fixed;
    inset: auto;
    margin: 0;
    padding: 0;
    border: none;
    background: none;
    overflow: visible;
  }

  .capa-popover:popover-open {
    display: block;
  }

  .menu-opciones {
    display: flex;
    flex-direction: column;
    min-width: 11rem;
    max-height: 20rem;
    overflow-y: auto;
    padding: var(--ns-espacio-1);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-high);
    box-shadow: var(--m3-elevation-2, none);
  }

  .opcion {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    width: 100%;
    min-height: 2rem;
    padding: var(--ns-espacio-1) var(--ns-espacio-3);
    border: none;
    border-radius: var(--ns-radio-sm);
    background: transparent;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    text-align: left;
    cursor: pointer;
    transition: background var(--ns-duracion-corta) var(--ns-curva);
  }

  .opcion:hover {
    background: var(--m3c-surface-container-highest);
  }

  .opcion.activa {
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
    font-weight: 600;
  }

  .etiqueta-opcion {
    flex: 1;
    white-space: nowrap;
  }

  .marca-check {
    display: inline-flex;
    align-items: center;
    color: var(--m3c-primary);
  }

  .compacto .gatillo {
    min-height: 1.875rem;
    padding: 0 var(--ns-espacio-2);
    font-size: var(--ns-texto-xs);
  }
</style>
