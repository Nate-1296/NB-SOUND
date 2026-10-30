<!--
  @component
  Lo que se ve al arrastrar archivos sobre la ventana (F4.2.1): soltarlos en
  cualquier parte los importa. Las rutas las recibe Rust del sistema; esta capa
  solo lo dice.
-->
<script lang="ts">
  import { importacion } from '$core/importacion.svelte';
  import { textos } from '$lib/i18n';
  import Icon from '$ui/Icon.svelte';

  const t = textos.importacion;
</script>

{#if importacion.arrastrando}
  <div class="capa" role="status">
    <div class="marco">
      <Icon nombre="importar" tamano={48} />
      <strong>{t.soltar}</strong>
      <span>{t.soltarAyuda}</span>
    </div>
  </div>
{/if}

<style>
  .capa {
    position: fixed;
    inset: 0;
    z-index: 50;
    display: grid;
    place-items: center;
    padding: var(--ns-espacio-6);
    background: var(--m3c-scrim);
    pointer-events: none;
  }

  .marco {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--ns-espacio-3);
    width: min(32rem, 100%);
    padding: var(--ns-espacio-7) var(--ns-espacio-5);
    border: 2px dashed var(--m3c-primary);
    border-radius: var(--ns-radio-xl);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
    text-align: center;
  }

  strong {
    font-size: var(--ns-texto-lg);
  }

  span {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }
</style>
