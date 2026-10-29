<!--
  @component
  La barra lateral con los destinos de ADR-007.

  En ventanas estrechas se queda en riel: solo iconos, con la etiqueta como
  nombre accesible y en el `title`. No hay interruptor de modos ni nada que
  parezca de desarrollo (Constitución, regla 2).
-->
<script lang="ts">
  import { page } from '$app/state';
  import { destinosVisibles, estaActivo } from '$core/navegacion';
  import { textos } from '$lib/i18n';

  import Icon from './Icon.svelte';

  interface Props {
    /** Archivos que esperan en Por revisar. */
    pendientes?: number;
  }

  let { pendientes = 0 }: Props = $props();

  const destinos = $derived(destinosVisibles(pendientes));
</script>

<nav class="lateral" aria-label={textos.nav.principal}>
  <div class="marca">
    <img src="/logo.png" alt="" width="32" height="32" />
    <span class="nombre">{textos.app.nombre}</span>
  </div>

  <ul>
    {#each destinos as destino (destino.id)}
      {@const activo = estaActivo(destino, page.url.pathname)}
      <li class:empuja={destino.id === 'ajustes'}>
        <a
          href={destino.ruta}
          class="destino"
          class:activo
          aria-current={activo ? 'page' : undefined}
          title={destino.etiqueta}
        >
          <span class="icono"><Icon nombre={destino.icono} tamano={22} /></span>
          <span class="etiqueta">{destino.etiqueta}</span>
          {#if destino.id === 'por-revisar'}
            <span class="contador" aria-label={textos.nav.pendientes(pendientes)}>{pendientes}</span
            >
          {/if}
        </a>
      </li>
    {/each}
  </ul>
</nav>

<style>
  .lateral {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
    height: 100%;
    padding: var(--ns-espacio-4) var(--ns-espacio-3);
    background: var(--m3c-surface-container-low);
    overflow-y: auto;
  }

  .marca {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: 0 var(--ns-espacio-2);
    min-height: 2.5rem;
  }

  .marca img {
    border-radius: var(--ns-radio-pleno);
  }

  .nombre {
    font-size: var(--ns-texto-lg);
    font-weight: 600;
    letter-spacing: 0.01em;
  }

  ul {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    flex: 1;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .empuja {
    margin-top: auto;
  }

  .destino {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    min-height: 3rem;
    padding: 0 var(--ns-espacio-4);
    border-radius: var(--ns-radio-pleno);
    color: var(--m3c-on-surface-variant);
    text-decoration: none;
    font-weight: 500;
    transition: background-color var(--ns-duracion-corta) var(--ns-curva);
  }

  .destino:hover {
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
  }

  .destino.activo {
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
  }

  .icono {
    display: grid;
    place-items: center;
  }

  .etiqueta {
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .contador {
    min-width: 1.5rem;
    padding: 0 var(--ns-espacio-2);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-error);
    color: var(--m3c-on-error);
    font-size: var(--ns-texto-xs);
    font-weight: 600;
    line-height: 1.5rem;
    text-align: center;
  }

  /* En riel: la carcasa no es amplia (ver anchos.ts). */
  :global(.carcasa:not([data-ancho='amplio'])) {
    .lateral {
      align-items: center;
      padding-inline: var(--ns-espacio-2);
    }

    .nombre,
    .etiqueta {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
    }

    .destino {
      position: relative;
      justify-content: center;
      width: 3.5rem;
      padding: 0;
    }

    .contador {
      position: absolute;
      top: 0.25rem;
      right: 0.25rem;
      min-width: 1.125rem;
      line-height: 1.125rem;
      padding: 0 var(--ns-espacio-1);
    }
  }
</style>
