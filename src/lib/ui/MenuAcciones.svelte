<!--
  @component
  El botón ··· con las acciones secundarias de algo: un álbum, una playlist o una
  canción. Las cabeceras ponían cada acción en su propio botón y una playlist
  llegaba a nueve, en dos renglones; lo primario se queda a la vista y el resto
  vive aquí.

  Es un `popover` del navegador: se cierra con Escape, al pulsar fuera y al
  elegir, y las flechas recorren las opciones como en un menú de escritorio.
-->
<script lang="ts" module>
  import type { NombreDeIcono } from './iconos.ts';

  export interface Accion {
    texto: string;
    icono: NombreDeIcono;
    accion: () => unknown;
    destructiva?: boolean;
    deshabilitada?: boolean;
    /** Una raya encima, para separar lo que borra de lo demás. */
    separada?: boolean;
  }
</script>

<script lang="ts">
  import Icon from './Icon.svelte';

  interface Props {
    acciones: readonly Accion[];
    etiqueta: string;
    /** Tamaño del botón: el de una cabecera o el de una fila. */
    tamano?: 'grande' | 'fila';
  }

  let { acciones, etiqueta, tamano = 'grande' }: Props = $props();

  let boton = $state<HTMLButtonElement>();
  let menu = $state<HTMLDivElement>();
  let abierto = $state(false);

  function abrir() {
    if (!boton || !menu) return;
    const r = boton.getBoundingClientRect();
    menu.showPopover();
    const ancho = menu.offsetWidth;
    const alto = menu.offsetHeight;
    menu.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - ancho - 8))}px`;
    menu.style.top = `${r.bottom + alto + 8 > window.innerHeight ? Math.max(8, r.top - alto - 4) : r.bottom + 4}px`;
    menu.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus();
  }

  function elegir(a: Accion) {
    menu?.hidePopover();
    boton?.focus();
    void a.accion();
  }

  function alPulsar(e: KeyboardEvent) {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    const opciones = [
      ...(menu?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])
    ];
    const i = opciones.indexOf(document.activeElement as HTMLButtonElement);
    const siguiente = e.key === 'ArrowDown' ? i + 1 : i - 1;
    opciones[(siguiente + opciones.length) % opciones.length]?.focus();
  }
</script>

<button
  bind:this={boton}
  type="button"
  class="disparador {tamano}"
  aria-label={etiqueta}
  title={etiqueta}
  aria-haspopup="menu"
  aria-expanded={abierto}
  onclick={() => (abierto ? menu?.hidePopover() : abrir())}
>
  <Icon nombre="masHorizontal" tamano={tamano === 'grande' ? 22 : 18} />
</button>

<div
  bind:this={menu}
  class="menu"
  popover="auto"
  role="menu"
  tabindex="-1"
  aria-label={etiqueta}
  onkeydown={alPulsar}
  ontoggle={(e) => (abierto = e.newState === 'open')}
>
  {#each acciones as a (a.texto)}
    {#if a.separada}<hr />{/if}
    <button
      type="button"
      role="menuitem"
      class="opcion"
      class:destructiva={a.destructiva}
      disabled={a.deshabilitada}
      onclick={() => elegir(a)}
    >
      <Icon nombre={a.icono} tamano={18} />
      <span>{a.texto}</span>
    </button>
  {/each}
</div>

<style>
  .disparador {
    display: grid;
    flex: 0 0 auto;
    place-items: center;
    padding: 0;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
    transition:
      background var(--ns-duracion-corta) var(--ns-curva),
      color var(--ns-duracion-corta) var(--ns-curva);
  }

  .disparador.grande {
    width: 2.75rem;
    height: 2.75rem;
  }

  .disparador.fila {
    width: 2.125rem;
    height: 2.125rem;
  }

  .disparador:hover,
  .disparador[aria-expanded='true'] {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
  }

  .menu {
    position: fixed;
    inset: auto;
    min-width: 15rem;
    margin: 0;
    padding: var(--ns-espacio-1);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
    box-shadow: 0 8px 24px var(--m3c-shadow);
  }

  .menu:popover-open {
    display: flex;
    flex-direction: column;
  }

  hr {
    margin: var(--ns-espacio-1) 0;
    border: none;
    border-top: 1px solid var(--m3c-outline-variant);
  }

  .opcion {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border: none;
    border-radius: var(--ns-radio-sm);
    background: none;
    color: inherit;
    font: inherit;
    font-size: var(--ns-texto-sm);
    text-align: left;
    cursor: pointer;
  }

  .opcion:hover:not(:disabled),
  .opcion:focus-visible {
    background: var(--m3c-surface-container-highest);
  }

  .opcion:disabled {
    opacity: 0.38;
    cursor: default;
  }

  .opcion.destructiva {
    color: var(--m3c-error);
  }
</style>
