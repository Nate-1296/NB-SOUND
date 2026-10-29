<!--
  @component
  La barra superior con la búsqueda global.

  La búsqueda no es un destino (ADR-007): es este campo, siempre visible, y
  `Ctrl+K` lo enfoca desde cualquier parte. Los resultados llegan en F2.2.5.
-->
<script lang="ts">
  import { textos } from '$lib/i18n';

  import Icon from './Icon.svelte';

  let campo: HTMLInputElement | undefined = $state();
  let consulta = $state('');

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
      <span class="ns-solo-lectores">{textos.busqueda.etiqueta}</span>
      <Icon nombre="buscar" tamano={20} />
      <input
        bind:this={campo}
        bind:value={consulta}
        type="search"
        placeholder={textos.busqueda.marcador}
        autocomplete="off"
        spellcheck="false"
      />
      <kbd>{textos.busqueda.atajo}</kbd>
    </label>
  </search>
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
</style>
