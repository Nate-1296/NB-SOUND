<!--
  @component
  El progreso discreto de la importación y su resumen (F4.2.3, ADR-007):
  "Catalogando 150 canciones" mientras dura y "142 añadidas. 8 por revisar" al
  terminar, con un enlace a Por revisar si hay algo pendiente.
-->
<script lang="ts">
  import { importacion } from '$core/importacion.svelte';
  import { textos } from '$lib/i18n';
  import Icon from '$ui/Icon.svelte';

  const t = textos.importacion;
  const p = $derived(importacion.progreso);
  const r = $derived(importacion.resumen);
</script>

{#if p.activa}
  <div class="tarjeta" role="status" aria-live="polite">
    <Icon nombre="cargando" tamano={20} />
    <div class="texto">
      <strong>{t.catalogando(p.total)}</strong>
      <span
        >{t.deTotal(p.hechos, p.total)}{#if p.actual}<span class="actual">
            · {p.actual}</span
          >{/if}</span
      >
      <progress max={p.total} value={p.hechos}></progress>
    </div>
  </div>
{:else if r}
  <div class="tarjeta" role="status">
    <Icon nombre={r.porRevisar > 0 ? 'porRevisar' : 'correcto'} tamano={20} />
    <div class="texto">
      <strong>{t.resumen(r.importadas, r.porRevisar)}</strong>
      {#if r.sinVerificar > 0}<span>{t.sinVerificar(r.sinVerificar)}</span>{/if}
      {#if r.porRevisar > 0}
        <a href="/por-revisar" onclick={() => importacion.cerrarResumen()}>{t.verPorRevisar}</a>
      {/if}
    </div>
    <button
      type="button"
      class="cerrar"
      aria-label={t.cerrar}
      onclick={() => importacion.cerrarResumen()}
    >
      <Icon nombre="cerrar" tamano={16} />
    </button>
  </div>
{/if}

<style>
  .tarjeta {
    position: fixed;
    right: var(--ns-espacio-5);
    bottom: calc(var(--ns-alto-reproductor) + var(--ns-espacio-4));
    z-index: 30;
    display: flex;
    align-items: flex-start;
    gap: var(--ns-espacio-3);
    width: min(22rem, calc(100vw - 2 * var(--ns-espacio-5)));
    padding: var(--ns-espacio-3) var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
  }

  .texto {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    min-width: 0;
    font-size: var(--ns-texto-sm);
  }

  .texto span {
    overflow: hidden;
    color: var(--m3c-on-surface-variant);
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  progress {
    width: 100%;
    height: 0.25rem;
    accent-color: var(--m3c-primary);
  }

  a {
    color: var(--m3c-primary);
    font-weight: 600;
  }

  .cerrar {
    display: grid;
    place-items: center;
    width: 1.75rem;
    height: 1.75rem;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
  }
</style>
