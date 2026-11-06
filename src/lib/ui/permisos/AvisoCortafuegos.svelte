<!--
  @component
  El aviso de que el cortafuegos del sistema bloquea al teléfono o a la fiesta, con
  el botón para pedir permiso. Se queda mientras siga bloqueado: si se dijo que no
  al sistema, aquí se puede volver a pedir.
-->
<script lang="ts">
  import { permisos, type Servicio } from '#lib/core/permisos.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import Icon from '#lib/ui/Icon.svelte';

  const { servicio }: { servicio: Servicio } = $props();
  const t = textos.permisos;
</script>

{#if permisos.bloqueado(servicio)}
  <div class="aviso" role="alert">
    <Icon nombre="advertencia" tamano={20} />
    <div class="texto">
      <strong>{t.bloqueadoTitulo}</strong>
      <span>{servicio === 'telefono' ? t.bloqueadoTelefono : t.bloqueadoFiesta}</span>
    </div>
    {#if permisos.red?.sePuedePedir}
      <button
        type="button"
        class="boton"
        disabled={permisos.pidiendo}
        onclick={() => void permisos.pedir(servicio)}
      >
        {permisos.pidiendo ? t.pidiendo : t.permitir}
      </button>
    {/if}
  </div>
{/if}

<style>
  .aviso {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-3);
    border: 1px solid var(--m3c-error);
    border-radius: var(--ns-radio-md);
    background: color-mix(in srgb, var(--m3c-error) 10%, transparent);
    color: var(--m3c-error);
  }

  .texto {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 0.125rem;
    min-width: 0;
    color: var(--m3c-on-surface);
    font-size: var(--ns-texto-sm);
  }

  .texto span {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    line-height: 1.4;
  }

  .boton {
    flex: 0 0 auto;
    height: 2.25rem;
    padding: 0 var(--ns-espacio-4);
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    cursor: pointer;
  }

  .boton:disabled {
    opacity: 0.6;
    cursor: default;
  }
</style>
