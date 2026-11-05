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
  import { textos } from '#lib/i18n/index.ts';
  import { untrack } from 'svelte';

  import Icon from './Icon.svelte';

  const t = textos.busqueda;
  const tImportacion = textos.importacion;

  let campo: HTMLInputElement | undefined = $state();
  let consulta = $state(
    page.url.pathname === '/buscar' ? (page.url.searchParams.get('q') ?? '') : ''
  );
  let rutaPrevia = $state(page.url.pathname);

  /** Los tres cajones de la barra: uno abierto a la vez, y el mismo botón lo cierra. */
  type Cajon = 'karaoke' | 'dispositivos' | 'anadir';
  let cajon = $state<Cajon | null>(null);
  function alternar(c: Cajon) {
    cajon = cajon === c ? null : c;
  }

  // Cada tecla no es una navegación: se espera a la pausa.
  let espera: ReturnType<typeof setTimeout> | undefined;

  $effect(() => {
    const ruta = page.url.pathname;
    const q = page.url.searchParams.get('q') ?? '';
    untrack(() => {
      if (ruta !== '/buscar') {
        clearTimeout(espera);
        if (rutaPrevia === '/buscar') {
          consulta = '';
        }
      } else if (document.activeElement !== campo && consulta !== q) {
        consulta = q;
      }
      rutaPrevia = ruta;
    });
  });

  function ejecutarBusqueda(inmediata = false) {
    clearTimeout(espera);
    const ejecutar = () => {
      const q = consulta.trim();
      if (q === '' && page.url.pathname !== '/buscar') return;
      void goto(`/buscar?q=${encodeURIComponent(q)}`, {
        replace: page.url.pathname === '/buscar',
        reset: false
      });
    };
    if (inmediata) {
      ejecutar();
    } else {
      espera = setTimeout(ejecutar, 200);
    }
  }

  function alEscribir() {
    ejecutarBusqueda(false);
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
      <span class="icono-buscar"><Icon nombre="buscar" tamano={20} /></span>
      <input
        bind:this={campo}
        bind:value={consulta}
        oninput={alEscribir}
        onfocus={() => {
          if (page.url.pathname !== '/buscar') {
            void goto(`/buscar${consulta ? `?q=${encodeURIComponent(consulta)}` : ''}`, {
              replace: false,
              reset: false
            });
          }
        }}
        onkeydown={(e) => {
          if (e.key === 'Escape') {
            if (page.url.pathname === '/buscar') {
              history.back();
            } else {
              campo?.blur();
            }
          } else if (e.key === 'Enter') {
            e.preventDefault();
            ejecutarBusqueda(true);
          }
        }}
        type="search"
        placeholder={t.marcador}
        title={t.ayudaAtajo}
        autocomplete="off"
        spellcheck="false"
      />
      {#if consulta || page.url.pathname === '/buscar'}
        <button
          type="button"
          class="boton-borrar"
          aria-label={page.url.pathname === '/buscar' ? t.cerrarBusqueda : t.borrar}
          title={page.url.pathname === '/buscar' ? t.cerrarBusqueda : t.borrar}
          onclick={() => {
            consulta = '';
            if (page.url.pathname === '/buscar') {
              history.back();
            } else {
              ejecutarBusqueda(true);
              campo?.focus();
            }
          }}
        >
          <Icon nombre="cerrar" tamano={16} />
        </button>
      {/if}
    </label>
  </search>

  <div class="acciones">
    <button
      type="button"
      class="boton-karaoke"
      class:activo={cajon === 'karaoke'}
      aria-label={textos.karaokeConsola.abrir}
      title={textos.karaokeConsola.abrir}
      aria-expanded={cajon === 'karaoke'}
      onclick={() => alternar('karaoke')}
    >
      <Icon nombre="microfono" tamano={18} />
      <span class="texto-karaoke">{textos.karaokeConsola.titulo}</span>
    </button>

    <button
      type="button"
      class="boton-dispositivos"
      class:activo={cajon === 'dispositivos'}
      aria-label={textos.ajustes.dispositivos}
      title={textos.ajustes.dispositivos}
      aria-expanded={cajon === 'dispositivos'}
      onclick={() => alternar('dispositivos')}
    >
      <Icon nombre="telefono" tamano={18} />
      <span class="texto-dispositivos">{textos.ajustes.dispositivos}</span>
    </button>

    <button
      type="button"
      class="boton-anadir"
      class:activo={cajon === 'anadir'}
      aria-label={tImportacion.anadir}
      title={tImportacion.anadir}
      aria-expanded={cajon === 'anadir'}
      onclick={() => alternar('anadir')}
    >
      <Icon nombre="mas" tamano={20} />
      <span class="texto-anadir">{tImportacion.anadir}</span>
    </button>
  </div>
</header>

{#if cajon === 'karaoke'}
  {#await import('#lib/ui/karaoke/CajonKaraoke.svelte') then m}
    <m.default oncerrar={() => (cajon = null)} />
  {/await}
{:else if cajon === 'dispositivos'}
  {#await import('#lib/ui/dispositivos/CajonDispositivos.svelte') then m}
    <m.default oncerrar={() => (cajon = null)} />
  {/await}
{:else if cajon === 'anadir'}
  {#await import('#lib/ui/importacion/CajonImportacion.svelte') then m}
    <m.default oncerrar={() => (cajon = null)} />
  {/await}
{/if}

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
    background: var(--m3c-surface);
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

  .caja:focus-within {
    outline: 2px solid var(--m3c-primary);
  }

  /* La caja entera ya marca el foco; el contorno del propio campo, dentro,
     dibujaba un segundo marco. */
  .caja input:focus-visible {
    outline-color: transparent;
  }

  .icono-buscar {
    display: grid;
    place-items: center;
    flex-shrink: 0;
  }

  input {
    flex: 1;
    min-width: 0;
    border: 0;
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
  }

  input::-webkit-search-cancel-button,
  input::-webkit-search-decoration {
    appearance: none;
    -webkit-appearance: none;
    display: none;
  }

  input::placeholder {
    color: var(--m3c-on-surface-variant);
  }

  .boton-borrar {
    display: grid;
    place-items: center;
    width: 1.75rem;
    height: 1.75rem;
    padding: 0;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
    flex-shrink: 0;
    transition:
      background-color var(--ns-duracion-corta) var(--ns-curva),
      color var(--ns-duracion-corta) var(--ns-curva);
  }

  .boton-borrar:hover {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
  }

  .acciones {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
  }

  .boton-karaoke,
  .boton-dispositivos {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    height: 2.75rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    white-space: nowrap;
    cursor: pointer;
    transition:
      background-color var(--ns-duracion-corta) var(--ns-curva),
      border-color var(--ns-duracion-corta) var(--ns-curva),
      color var(--ns-duracion-corta) var(--ns-curva);
  }

  .boton-karaoke:hover,
  .boton-dispositivos:hover {
    background: var(--m3c-surface-container-high);
  }

  .boton-karaoke.activo,
  .boton-karaoke[aria-expanded='true'],
  .boton-dispositivos.activo,
  .boton-dispositivos[aria-expanded='true'] {
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
    border-color: var(--m3c-primary);
  }

  :global(.carcasa:not([data-ancho='amplio'])) .texto-karaoke,
  :global(.carcasa:not([data-ancho='amplio'])) .texto-dispositivos,
  :global(.carcasa.compacta) .texto-karaoke,
  :global(.carcasa.compacta) .texto-dispositivos {
    display: none;
  }

  :global(.carcasa:not([data-ancho='amplio'])) .boton-karaoke,
  :global(.carcasa:not([data-ancho='amplio'])) .boton-dispositivos,
  :global(.carcasa.compacta) .boton-karaoke,
  :global(.carcasa.compacta) .boton-dispositivos {
    width: 2.75rem;
    padding: 0;
    justify-content: center;
  }

  .boton-anadir {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    height: 2.75rem;
    padding: 0 var(--ns-espacio-4);
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    white-space: nowrap;
    cursor: pointer;
    transition:
      background-color var(--ns-duracion-corta) var(--ns-curva),
      color var(--ns-duracion-corta) var(--ns-curva);
  }

  .boton-anadir:hover {
    background: var(--m3c-primary-dim, var(--m3c-primary));
  }

  .boton-anadir.activo,
  .boton-anadir[aria-expanded='true'] {
    background: var(--m3c-primary-container);
    color: var(--m3c-on-primary-container);
  }

  :global(.carcasa:not([data-ancho='amplio'])) .texto-anadir,
  :global(.carcasa.compacta) .texto-anadir {
    display: none;
  }

  :global(.carcasa:not([data-ancho='amplio'])) .boton-anadir,
  :global(.carcasa.compacta) .boton-anadir {
    width: 2.75rem;
    padding: 0;
    justify-content: center;
  }
</style>
