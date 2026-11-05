<!--
  @component
  Lo que se ve donde no hay nada: un icono, qué pasa y, si lo hay, el siguiente
  paso. Con la biblioteca vacía, Biblioteca y Playlists se quedaban en blanco, sin
  decir por qué ni qué hacer.
-->
<script lang="ts">
  import { anadirMusica } from '#lib/core/ipc/index.ts';
  import { textos } from '#lib/i18n/index.ts';

  import Icon from './Icon.svelte';
  import type { NombreDeIcono } from './iconos.ts';

  interface Props {
    icono: NombreDeIcono;
    titulo: string;
    texto?: string;
    /** Ofrece "Añadir música": tiene sentido cuando lo que falta es la biblioteca. */
    conAnadir?: boolean;
  }

  let { icono, titulo, texto, conAnadir = false }: Props = $props();
</script>

<div class="vacio">
  <span class="icono"><Icon nombre={icono} tamano={30} /></span>
  <strong>{titulo}</strong>
  {#if texto}<p>{texto}</p>{/if}
  {#if conAnadir}
    <button type="button" class="boton" onclick={() => void anadirMusica(false)}>
      <Icon nombre="mas" tamano={16} />{textos.importacion.anadir}
    </button>
  {/if}
</div>

<style>
  .vacio {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--ns-espacio-2);
    max-width: 30rem;
    margin: var(--ns-espacio-7) auto;
    text-align: center;
  }

  .icono {
    display: grid;
    place-items: center;
    width: 4rem;
    height: 4rem;
    margin-bottom: var(--ns-espacio-2);
    border-radius: var(--ns-radio-pleno);
    background: color-mix(in srgb, var(--m3c-primary) 14%, transparent);
    color: var(--m3c-primary);
  }

  strong {
    font-size: var(--ns-texto-lg);
  }

  p {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
    line-height: 1.5;
  }

  .boton {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-3);
    padding: var(--ns-espacio-2) var(--ns-espacio-5);
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 700;
    cursor: pointer;
  }
</style>
