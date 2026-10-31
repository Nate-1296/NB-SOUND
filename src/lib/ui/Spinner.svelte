<!--
  @component
  Indicador de carga circular (Spinner). Autorizado para rotación continua.
-->
<script lang="ts">
  interface Props {
    tamano?: number;
    etiqueta?: string;
  }

  let { tamano = 20, etiqueta }: Props = $props();
</script>

<div
  class="spinner"
  role="status"
  aria-live="polite"
  aria-label={etiqueta}
  style:width="{tamano}px"
  style:height="{tamano}px"
>
  <svg viewBox="0 0 24 24" fill="none">
    <circle cx="12" cy="12" r="9" stroke="var(--m3c-outline-variant)" stroke-width="2.5" />
    <circle
      class="arco"
      cx="12"
      cy="12"
      r="9"
      stroke="var(--m3c-primary)"
      stroke-width="2.5"
      stroke-linecap="round"
      stroke-dasharray="28 56"
    />
  </svg>
</div>

<style>
  .spinner {
    display: inline-grid;
    place-items: center;
    flex-shrink: 0;
  }

  svg {
    width: 100%;
    height: 100%;
    animation: girar 0.9s linear infinite;
  }

  @keyframes girar {
    to {
      transform: rotate(360deg);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    svg {
      animation-duration: 2s;
    }
  }
</style>
