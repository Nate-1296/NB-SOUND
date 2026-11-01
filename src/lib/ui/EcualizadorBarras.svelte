<!--
  @component
  Ecualizador visual de barras en la cabecera de Inicio (COMP-15).
  Reacciona a los picos y posición reales solo mientras la música está sonando.
  En reposo mantiene una silueta de onda estática elegante sin consumir CPU ni fotogramas.
-->
<script lang="ts">
  import { reproductor } from '$core/reproductor.svelte';

  const BARRAS = 24;
  const SILUETA_ESTATICA = [
    25, 35, 55, 75, 90, 65, 45, 30, 25, 40, 60, 80, 100, 85, 70, 50, 35, 25, 40, 65, 50, 35, 25, 15
  ];

  const alturas = $derived.by(() => {
    if (!reproductor.sonando) {
      return SILUETA_ESTATICA;
    }
    const picos = reproductor.picos;
    const pos = reproductor.posicion;
    const dur = reproductor.instantanea.duracionSeg || 1;
    const fraccion = Math.min(1, Math.max(0, pos / dur));

    return SILUETA_ESTATICA.map((base, idx) => {
      if (picos.length > 0) {
        const indicePico = Math.floor((fraccion * picos.length + idx * 3) % picos.length);
        const valorPico = (picos[indicePico] ?? 0.5) * 100;
        return Math.max(15, Math.min(100, valorPico * 0.8 + base * 0.2));
      }
      const osc = Math.sin(pos * 5 + idx * 0.6) * 30;
      return Math.max(15, Math.min(100, base * 0.6 + osc));
    });
  });
</script>

<div class="ecualizador" aria-hidden="true">
  {#each alturas as altura, i (i)}
    <span class="barra" class:sonando={reproductor.sonando} style:height={`${Math.round(altura)}%`}
    ></span>
  {/each}
</div>

<style>
  .ecualizador {
    display: flex;
    align-items: flex-end;
    gap: var(--ns-espacio-1);
    height: 3rem;
    padding: var(--ns-espacio-1) var(--ns-espacio-2);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container);
  }

  .barra {
    flex: 0 0 4px;
    width: 4px;
    border-radius: var(--ns-radio-pleno);
    background: linear-gradient(to top, var(--m3c-primary), var(--m3c-tertiary));
    opacity: 0.6;
    transition: height var(--ns-duracion-corta) var(--ns-curva);
  }

  .barra.sonando {
    opacity: 1;
  }
</style>
