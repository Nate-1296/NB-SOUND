<!--
  @component
  Los avisos, apilados en la esquina, sobre la barra de reproducción: la
  respuesta a "¿ha pasado algo?" que la V1 daba con `ToastMessage.qml`.

  Viene de NB Books (`Notificaciones.svelte`), con su contrato: dos regiones,
  porque una confirmación espera a que el lector de pantalla termine y un fallo
  interrumpe; no roba el foco ni exige respuesta, y mientras el puntero está
  encima o el foco dentro la cuenta atrás se detiene.
-->
<script lang="ts">
  import type { ClaseDeNotificacion } from '#lib/core/notificaciones.ts';
  import { notificaciones } from '#lib/core/notificaciones.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';

  import Icon from './Icon.svelte';
  import type { NombreDeIcono } from './iconos';

  const t = textos.avisos;

  const ICONO: Readonly<Record<ClaseDeNotificacion, NombreDeIcono>> = {
    exito: 'comprobado',
    error: 'error',
    informacion: 'informacion'
  };

  const lista = $derived(notificaciones.lista);
  const educadas = $derived(lista.filter((n) => n.clase !== 'error'));
  const urgentes = $derived(lista.filter((n) => n.clase === 'error'));
</script>

{#snippet pila(avisos: typeof lista, rol: 'status' | 'log', etiqueta: string)}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="pila"
    role={rol}
    aria-live={rol === 'log' ? 'assertive' : 'polite'}
    aria-label={etiqueta}
    onmouseenter={() => notificaciones.pausar(true)}
    onmouseleave={() => notificaciones.pausar(false)}
    onfocusin={() => notificaciones.pausar(true)}
    onfocusout={() => notificaciones.pausar(false)}
  >
    {#each avisos as aviso (aviso.id)}
      <div class="aviso" data-clase={aviso.clase}>
        <span class="icono" aria-hidden="true"
          ><Icon nombre={ICONO[aviso.clase]} tamano={18} /></span
        >
        <span class="texto">
          <span class="mensaje">
            {aviso.mensaje}
            {#if aviso.veces > 1}
              <span class="veces">{t.veces(aviso.veces)}</span>
            {/if}
          </span>
          {#if aviso.detalle}
            <span class="detalle">{aviso.detalle}</span>
          {/if}
        </span>
        <button
          class="cerrar"
          type="button"
          aria-label={t.cerrar}
          onclick={() => notificaciones.cerrar(aviso.id)}
        >
          <Icon nombre="cerrar" tamano={14} />
        </button>
      </div>
    {/each}
  </div>
{/snippet}

<div class="avisos">
  {@render pila(educadas, 'status', t.region)}
  {@render pila(urgentes, 'log', t.regionFallos)}
</div>

<style>
  /*
   * Fijo respecto a la ventana: en la vista de reproducción la carcasa cambia de
   * forma, y un aviso que viviera dentro de ella se movería con ella.
   * `pointer-events: none` en el contenedor para que la columna vacía no se coma
   * los clics del contenido de debajo.
   */
  .avisos {
    position: fixed;
    right: var(--ns-espacio-5);
    bottom: calc(var(--ns-alto-reproductor) + var(--ns-espacio-3));
    z-index: 60;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: var(--ns-espacio-2);
    max-width: min(26rem, calc(100vw - 2 * var(--ns-espacio-5)));
    pointer-events: none;
  }

  .pila {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    width: 100%;
  }

  /*
   * El color va en el borde y en el icono, nunca en el fondo: así el contraste
   * del texto es el del resto de la aplicación en los 63 temas.
   */
  .aviso {
    display: flex;
    align-items: flex-start;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-left: 3px solid var(--m3c-outline);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
    box-shadow: 0 4px 16px var(--m3c-shadow);
    pointer-events: auto;
    animation: entra var(--ns-duracion-media) var(--ns-curva);
  }

  .aviso[data-clase='exito'] {
    border-left-color: var(--m3c-primary);
  }

  .aviso[data-clase='error'] {
    border-left-color: var(--m3c-error);
  }

  .icono {
    display: flex;
    flex: 0 0 auto;
    color: var(--m3c-on-surface-variant);
  }

  .aviso[data-clase='exito'] .icono {
    color: var(--m3c-primary);
  }

  .aviso[data-clase='error'] .icono {
    color: var(--m3c-error);
  }

  .texto {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    min-width: 0;
    flex: 1 1 auto;
  }

  .mensaje {
    font-size: var(--ns-texto-sm);
    line-height: 1.4;
    overflow-wrap: anywhere;
  }

  .veces {
    margin-left: var(--ns-espacio-1);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-variant-numeric: tabular-nums;
  }

  .detalle {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    overflow-wrap: anywhere;
    user-select: text;
  }

  .cerrar {
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    width: 1.5rem;
    height: 1.5rem;
    padding: 0;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
  }

  .cerrar:hover {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
  }

  @keyframes entra {
    from {
      opacity: 0;
      transform: translateY(12px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .aviso {
      animation: none;
    }
  }
</style>
