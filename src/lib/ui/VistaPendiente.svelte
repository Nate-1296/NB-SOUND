<!--
  @component
  Lo que muestra un destino cuya fase del plan aún no ha llegado.

  Existe para que la carcasa se pueda recorrer entera desde la Fase 0 sin
  inventar contenido falso.
-->
<script lang="ts">
  import { textos } from '$lib/i18n';

  import Icon from './Icon.svelte';
  import type { NombreDeIcono } from './iconos';

  interface Props {
    titulo: string;
    icono: NombreDeIcono;
  }

  let { titulo, icono }: Props = $props();
</script>

<section class="vista">
  <h1>{titulo}</h1>
  <div class="vacio">
    <Icon nombre={icono} tamano={40} />
    <p>{textos.vistas.proximamente}</p>
  </div>
</section>

<style>
  .vista {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-5);
  }

  h1 {
    font-size: var(--ns-texto-2xl);
  }

  .vacio {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-7) var(--ns-espacio-4);
    border-radius: var(--ns-radio-xl);
    background: var(--m3c-surface-container-low);
    color: var(--m3c-on-surface-variant);
    text-align: center;
  }

  p {
    margin: 0;
  }
</style>
