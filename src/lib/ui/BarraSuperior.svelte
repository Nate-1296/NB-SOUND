<!--
  @component
  La barra superior con la búsqueda global.

  La búsqueda no es un destino de la barra lateral (ADR-007): es este campo,
  siempre visible, y `Ctrl+K` lo enfoca desde cualquier parte. Al escribir se abre
  la página de resultados, que se actualiza con cada pausa al teclear.
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { anadirMusica } from '$core/ipc';
  import { textos } from '$lib/i18n';

  import Icon from './Icon.svelte';

  const t = textos.busqueda;
  const tImportacion = textos.importacion;

  let campo: HTMLInputElement | undefined = $state();
  let consulta = $state(
    page.url.pathname === '/buscar' ? (page.url.searchParams.get('q') ?? '') : ''
  );

  let menuAbierto = $state(false);
  let botonAnadir: HTMLButtonElement | undefined = $state();
  let capaMenu: HTMLDivElement | undefined = $state();

  function alternarMenu() {
    if (!capaMenu || !botonAnadir) return;
    if (menuAbierto) {
      capaMenu.hidePopover();
      return;
    }
    const r = botonAnadir.getBoundingClientRect();
    capaMenu.style.left = `${r.left}px`;
    capaMenu.style.top = `${r.bottom + 8}px`;
    capaMenu.showPopover();
  }

  // Cada tecla no es una navegación: se espera a la pausa.
  let espera: ReturnType<typeof setTimeout> | undefined;

  $effect(() => {
    const ruta = page.url.pathname;
    const q = page.url.searchParams.get('q') ?? '';
    if (ruta !== '/buscar') {
      clearTimeout(espera);
      if (consulta !== '') consulta = '';
    } else if (document.activeElement !== campo && consulta !== q) {
      consulta = q;
    }
  });

  function alEscribir() {
    clearTimeout(espera);
    espera = setTimeout(() => {
      const q = consulta.trim();
      if (q === '' && page.url.pathname !== '/buscar') return;
      void goto(`/buscar?q=${encodeURIComponent(q)}`, {
        replace: page.url.pathname === '/buscar',
        // Sin devolver el foco ni el desplazamiento: se sigue escribiendo.
        reset: false
      });
    }, 200);
  }

  function alPulsar(evento: KeyboardEvent) {
    if ((evento.ctrlKey || evento.metaKey) && evento.key.toLowerCase() === 'k') {
      evento.preventDefault();
      campo?.focus();
      campo?.select();
    }
  }
</script>

<svelte:window onkeydown={alPulsar} />

<header class="superior">
  <search class="busqueda">
    <label class="caja">
      <span class="ns-solo-lectores">{t.etiqueta}</span>
      <Icon nombre="buscar" tamano={20} />
      <input
        bind:this={campo}
        bind:value={consulta}
        oninput={alEscribir}
        onkeydown={(e) => {
          if (e.key === 'Escape') {
            campo?.blur();
          }
        }}
        type="search"
        placeholder={t.marcador}
        autocomplete="off"
        spellcheck="false"
      />
      <kbd>{t.atajo}</kbd>
    </label>
  </search>

  <div class="acciones">
    <button
      type="button"
      bind:this={botonAnadir}
      class="boton-anadir"
      aria-label={tImportacion.anadir}
      title={tImportacion.anadir}
      aria-expanded={menuAbierto}
      onclick={alternarMenu}
    >
      <Icon nombre="mas" tamano={20} />
    </button>
    <div
      class="menu-anadir"
      popover="auto"
      bind:this={capaMenu}
      ontoggle={(e) => (menuAbierto = e.newState === 'open')}
    >
      <button
        type="button"
        class="opcion"
        onclick={() => {
          capaMenu?.hidePopover();
          void anadirMusica(false);
        }}
      >
        <Icon nombre="cancion" tamano={18} />
        <span>{tImportacion.anadirArchivos}</span>
      </button>
      <button
        type="button"
        class="opcion"
        onclick={() => {
          capaMenu?.hidePopover();
          void anadirMusica(true);
        }}
      >
        <Icon nombre="carpeta" tamano={18} />
        <span>{tImportacion.anadirCarpeta}</span>
      </button>
    </div>
  </div>
</header>

<style>
  /*
   * `contain: layout size`: escribir en la búsqueda no puede ensuciar la
   * disposición de lo que hay debajo. NB Books lo midió en WebKitGTK: sin esto,
   * 133 ms por letra; con esto, 17.
   */
  .superior {
    contain: layout size;
    display: flex;
    align-items: center;
    height: var(--ns-alto-superior);
    padding: 0 var(--ns-espacio-5);
  }

  .busqueda {
    flex: 1;
    max-width: 40rem;
  }

  .caja {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    height: 2.75rem;
    padding: 0 var(--ns-espacio-4);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface-variant);
  }

  input {
    flex: 1;
    min-width: 0;
    border: 0;
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
  }

  input::placeholder {
    color: var(--m3c-on-surface-variant);
  }

  kbd {
    padding: 0.125rem var(--ns-espacio-2);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
    font-family: var(--ns-font-mono);
    font-size: var(--ns-texto-xs);
  }

  :global(.carcasa[data-ancho='compacto']) kbd {
    display: none;
  }

  .acciones {
    margin-left: var(--ns-espacio-4);
  }

  .boton-anadir {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 2.75rem;
    height: 2.75rem;
    padding: 0;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
  }

  .boton-anadir:hover {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
  }

  .menu-anadir {
    position: fixed;
    inset: auto;
    margin: 0;
    padding: var(--ns-espacio-2);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    display: none;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    box-shadow: var(--m3-elevation-2, none);
  }

  .menu-anadir:popover-open {
    display: flex;
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
    white-space: nowrap;
  }

  .opcion:hover {
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
  }
</style>
