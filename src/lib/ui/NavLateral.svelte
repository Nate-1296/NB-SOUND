<!--
  @component
  La barra lateral, con la disposición de la V1 (`legado/ui/qml/componentes/NavLateral.qml`):
  el logo grande arriba, los destinos agrupados bajo sus rótulos y, al pie, Por
  revisar (solo si hay algo pendiente) y Ajustes. Los destinos son los de ADR-007:
  Importar, Preparar Karaoke, Estado del Sistema y Sincronización ya no tienen
  vista propia, y el botón de Modo Pro desaparece.

  En ventanas estrechas se queda en riel: solo iconos, con la etiqueta como nombre
  accesible y en el `title`.
-->
<script lang="ts">
  import { page } from '$app/state';
  import { AJUSTES, estaActivo, POR_REVISAR, SECCIONES, type Destino } from '$core/navegacion';
  import { textos } from '$lib/i18n';

  import Icon from './Icon.svelte';

  interface Props {
    /** Archivos que esperan en Por revisar. */
    pendientes?: number;
  }

  let { pendientes = 0 }: Props = $props();

  const pie = $derived<Destino[]>(pendientes > 0 ? [POR_REVISAR, AJUSTES] : [AJUSTES]);
</script>

{#snippet enlace(destino: Destino)}
  {@const activo = estaActivo(destino, page.url.pathname)}
  <li>
    <a
      href={destino.ruta}
      class="destino"
      class:activo
      aria-current={activo ? 'page' : undefined}
      title={destino.etiqueta}
    >
      <span class="icono"><Icon nombre={destino.icono} tamano={20} /></span>
      <span class="etiqueta">{destino.etiqueta}</span>
      {#if destino.id === 'por-revisar'}
        <span class="contador" aria-label={textos.nav.pendientes(pendientes)}>{pendientes}</span>
      {/if}
    </a>
  </li>
{/snippet}

<nav class="lateral" aria-label={textos.nav.principal}>
  <a class="marca" href="/" aria-label={textos.app.nombre}>
    <img src="/logo.png" alt="" width="136" height="136" />
  </a>

  {#each SECCIONES as seccion (seccion.etiqueta)}
    <section class="seccion">
      <h2 class="rotulo">{seccion.etiqueta}</h2>
      <ul>
        {#each seccion.destinos as destino (destino.id)}
          {@render enlace(destino)}
        {/each}
      </ul>
    </section>
  {/each}

  <ul class="pie">
    {#each pie as destino (destino.id)}
      {@render enlace(destino)}
    {/each}
  </ul>
</nav>

<style>
  .lateral {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
    height: 100%;
    padding: var(--ns-espacio-5) var(--ns-espacio-2) var(--ns-espacio-4);
    background: var(--m3c-surface-container-lowest);
    border-right: 3px solid var(--m3c-primary);
    overflow-y: auto;
  }

  .marca {
    display: grid;
    place-items: center;
    padding-bottom: var(--ns-espacio-3);
  }

  .marca img {
    width: 8.5rem;
    height: 8.5rem;
    border-radius: var(--ns-radio-pleno);
  }

  .rotulo {
    margin: 0 0 var(--ns-espacio-2);
    padding: 0 var(--ns-espacio-3);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  ul {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .pie {
    margin-top: auto;
  }

  .destino {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    min-height: 2.75rem;
    padding: 0 var(--ns-espacio-3);
    border: 1px solid transparent;
    border-radius: var(--ns-radio-sm);
    color: var(--m3c-on-surface);
    text-decoration: none;
    font-size: var(--ns-texto-sm);
    font-weight: 500;
    transition: background-color var(--ns-duracion-corta) var(--ns-curva);
  }

  .destino:hover {
    background: var(--m3c-surface-container-high);
  }

  /* El destino activo, como en la V1: recuadro de acento con la barra a la
     izquierda. */
  .destino.activo {
    border-color: var(--m3c-primary);
    border-left-width: 3px;
    background: var(--m3c-surface-container);
    font-weight: 700;
  }

  .icono {
    display: grid;
    place-items: center;
    color: var(--m3c-on-surface-variant);
  }

  .activo .icono {
    color: var(--m3c-on-surface);
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

    .marca img {
      width: 3rem;
      height: 3rem;
    }

    .rotulo,
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
      width: 3.25rem;
      padding: 0;
    }

    .contador {
      position: absolute;
      top: 0.125rem;
      right: 0.125rem;
      min-width: 1.125rem;
      line-height: 1.125rem;
      padding: 0 var(--ns-espacio-1);
    }
  }
</style>
