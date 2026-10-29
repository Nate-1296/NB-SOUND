<!--
  @component
  Un icono del catálogo.

  Catálogo: iconos.ts (ADR-008).

  Es el **único** sitio donde se dibuja un icono, y por eso el trazo, el tamaño y
  la accesibilidad no pueden divergir entre pantallas. Dos reglas:

  1. **Decorativo por defecto.** Un icono que acompaña a un texto no se anuncia:
     el lector de pantalla ya lee el texto, y oírlo dos veces es ruido. Solo
     cuando el icono va solo se le pone `etiqueta`, y entonces se anuncia como
     imagen con nombre.
  2. **Hereda el color.** Nunca lleva color propio, así que cambia con el tema y
     con el alto contraste sin que nadie tenga que acordarse de nada.
-->
<script lang="ts">
  import { ICONOS, type NombreDeIcono } from './iconos';

  interface Props {
    nombre: NombreDeIcono;
    /** Tamaño del lado, en píxeles. Por defecto hereda del texto. */
    tamano?: number;
    /**
     * Nombre accesible.
     *
     * Solo cuando el icono va **solo**. Si acompaña a un texto se omite, y el
     * icono queda oculto para las tecnologías de asistencia.
     */
    etiqueta?: string;
  }

  let { nombre, tamano, etiqueta }: Props = $props();
</script>

<svg
  class="ns-icono"
  viewBox="0 0 24 24"
  width={tamano ?? '1.25em'}
  height={tamano ?? '1.25em'}
  fill="none"
  stroke="currentColor"
  stroke-width="1.5"
  stroke-linecap="round"
  stroke-linejoin="round"
  role={etiqueta ? 'img' : undefined}
  aria-label={etiqueta}
  aria-hidden={etiqueta ? undefined : 'true'}
  focusable="false"
>
  <!-- eslint-disable-next-line svelte/no-at-html-tags -->
  {@html ICONOS[nombre]}
</svg>

<style>
  .ns-icono {
    display: block;
    flex: 0 0 auto;
  }
</style>
