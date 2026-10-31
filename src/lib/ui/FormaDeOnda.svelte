<!--
  @component
  La forma de onda de una pista (F8.1): lo reproducido en el color primario y,
  cuando suena una sesión del DJ, las marcas de entrada y salida.
-->
<script lang="ts">
  interface Props {
    picos: readonly number[];
    posicion: number;
    duracion: number;
    entradaSeg?: number | null;
    salidaSeg?: number | null;
  }

  let { picos, posicion, duracion, entradaSeg = null, salidaSeg = null }: Props = $props();

  const COLUMNAS = 96;

  /** Un único trazo con las barras simétricas: solo se recalcula al cambiar de pista. */
  const trazo = $derived.by(() => {
    const n = picos.length;
    if (n === 0) return '';
    let d = '';
    for (let i = 0; i < COLUMNAS; i++) {
      const desde = Math.floor((i * n) / COLUMNAS);
      const hasta = Math.max(desde + 1, Math.floor(((i + 1) * n) / COLUMNAS));
      let max = 0;
      for (let j = desde; j < hasta; j++) {
        const v = picos[j] ?? 0;
        if (v > max) max = v;
      }
      const h = Math.max(1.5, (max / 255) * 10.5);
      const x = ((i + 0.5) * (100 / COLUMNAS)).toFixed(2);
      d += `M${x} ${(12 - h).toFixed(2)}V${(12 + h).toFixed(2)}`;
    }
    return d;
  });

  const porcentaje = (s: number) =>
    duracion > 0 ? Math.min(100, Math.max(0, (s / duracion) * 100)) : 0;
  const avance = $derived(porcentaje(posicion));
  const entrada = $derived(entradaSeg !== null && duracion > 0 ? porcentaje(entradaSeg) : null);
  const salida = $derived(salidaSeg !== null && duracion > 0 ? porcentaje(salidaSeg) : null);
</script>

<svg class="onda" viewBox="0 0 100 24" preserveAspectRatio="none" aria-hidden="true">
  <path class="fondo" d={trazo} />
  <path class="reproducido" d={trazo} style:clip-path={`inset(0 ${100 - avance}% 0 0)`} />
  {#if entrada !== null}
    <line class="marca entrada" x1={entrada} y1="0" x2={entrada} y2="24" />
  {/if}
  {#if salida !== null}
    <line class="marca salida" x1={salida} y1="0" x2={salida} y2="24" />
  {/if}
</svg>

<style>
  .onda {
    display: block;
    width: 100%;
    height: 1.5rem;
    overflow: visible;
    pointer-events: none;
  }

  path,
  line {
    fill: none;
    stroke-width: 2;
    stroke-linecap: round;
    vector-effect: non-scaling-stroke;
  }

  .fondo {
    stroke: var(--m3c-surface-container-highest);
  }

  .reproducido {
    stroke: var(--m3c-primary);
  }

  .marca.entrada {
    stroke: var(--m3c-tertiary);
  }

  .marca.salida {
    stroke: var(--m3c-secondary);
  }
</style>
