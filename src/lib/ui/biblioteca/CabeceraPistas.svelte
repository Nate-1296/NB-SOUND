<!--
  @component
  Los rótulos de las columnas encima de una lista de canciones: número, título,
  álbum y duración, con las mismas columnas que `FilaPista`. Sin ellos, el álbum
  de la derecha y el artista de debajo del título se confundían.
-->
<script lang="ts">
  import { textos } from '#lib/i18n/index.ts';

  import Icon from '../Icon.svelte';

  interface Props {
    contexto?: 'biblioteca' | 'album' | 'artista' | 'playlist';
  }

  let { contexto = 'biblioteca' }: Props = $props();
  const t = textos.biblioteca.columnas;
</script>

<div class="cabecera" class:contexto-album={contexto === 'album'} aria-hidden="true">
  <span class="numero">#</span>
  {#if contexto !== 'album'}<span></span>{/if}
  <span>{t.titulo}</span>
  {#if contexto !== 'album'}<span class="album">{t.album}</span>{/if}
  <span></span>
  <span class="duracion" title={t.duracion}><Icon nombre="reloj" tamano={16} /></span>
  <span></span>
</div>

<style>
  .cabecera {
    display: grid;
    grid-template-columns:
      2.5rem 2.5rem minmax(10rem, 2fr) minmax(6rem, 1fr) 2.25rem 3.25rem
      4.5rem;
    align-items: center;
    gap: var(--ns-espacio-3);
    height: 2.25rem;
    padding: 0 var(--ns-espacio-3);
    border-bottom: 1px solid var(--m3c-outline-variant);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .cabecera.contexto-album {
    grid-template-columns: 2.5rem minmax(10rem, 1fr) 2.25rem 3.25rem 4.5rem;
  }

  .numero {
    text-align: center;
  }

  .duracion {
    display: flex;
    justify-content: flex-end;
  }

  @container carcasa (max-width: 75rem) {
    .album {
      display: none;
    }

    .cabecera {
      grid-template-columns: 2.5rem 2.5rem minmax(10rem, 1fr) 2.25rem 3.25rem 4.5rem;
    }
  }
</style>
