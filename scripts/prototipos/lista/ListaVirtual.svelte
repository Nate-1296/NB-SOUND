<!--
  @component
  Lista virtualizada de filas de alto fijo.

  Pinta solo las filas visibles más un margen (`ventana.ts`) y pide los datos por
  bloques alineados de tamaño fijo, así que desplazarse dentro de un bloque no
  vuelve a pedir nada. El número de nodos no depende del total: con 3.000 o con
  150.000 canciones se pintan las mismas filas.

  Un bloque que aún no llegó se pinta como filas vacías del mismo alto, para que
  la barra de desplazamiento no salte.
-->
<script lang="ts" generics="T">
  import type { Snippet } from 'svelte';
  import { SvelteMap } from 'svelte/reactivity';

  import { bloquesNecesarios, calcularVentana, TAM_BLOQUE } from './ventana';

  interface Props {
    total: number;
    altoFila: number;
    /** Devuelve las filas del bloque `b`: de `b * TAM_BLOQUE` en adelante. */
    cargarBloque: (bloque: number) => Promise<T[]>;
    fila: Snippet<[T, number]>;
    etiqueta: string;
  }

  let { total, altoFila, cargarBloque, fila, etiqueta }: Props = $props();

  let scrollTop = $state(0);
  let altoVista = $state(0);
  const bloques = new SvelteMap<number, T[]>();
  const pedidos = new Set<number>();

  const ventana = $derived(calcularVentana(total, altoFila, scrollTop, altoVista));

  $effect(() => {
    for (const b of bloquesNecesarios(ventana.desde, ventana.hasta)) {
      if (pedidos.has(b)) continue;
      pedidos.add(b);
      void cargarBloque(b).then(
        (filas) => bloques.set(b, filas),
        () => pedidos.delete(b)
      );
    }
  });

  function elemento(i: number): T | undefined {
    return bloques.get(Math.floor(i / TAM_BLOQUE))?.[i % TAM_BLOQUE];
  }

  const indices = $derived(
    Array.from({ length: ventana.hasta - ventana.desde }, (_, k) => ventana.desde + k)
  );
</script>

<div
  class="lista"
  role="list"
  aria-label={etiqueta}
  bind:clientHeight={altoVista}
  onscroll={(e) => (scrollTop = e.currentTarget.scrollTop)}
>
  <div class="relleno" style:height="{total * altoFila}px">
    <div class="filas" style:transform="translateY({ventana.desplazamiento}px)">
      {#each indices as i (i)}
        {@const item = elemento(i)}
        <div class="fila" role="listitem" style:height="{altoFila}px">
          {#if item !== undefined}{@render fila(item, i)}{/if}
        </div>
      {/each}
    </div>
  </div>
</div>

<style>
  .lista {
    height: 100%;
    overflow-y: auto;
    contain: strict;
  }

  .relleno {
    position: relative;
  }

  .filas {
    position: absolute;
    inset: 0 0 auto 0;
  }

  .fila {
    overflow: hidden;
  }
</style>
