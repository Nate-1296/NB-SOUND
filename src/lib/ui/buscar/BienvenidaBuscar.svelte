<!--
  @component
  Buscar sin nada escrito: qué se puede pedir y unas ideas para probar (COMP-16).
  Se carga aparte del arranque (250 KB).

  Antes había dos tarjetas de "modo" que parecían botones y no hacían nada: la
  búsqueda por palabras y la que entiende "algo triste" son la misma caja, y la
  pantalla lo dice en una frase. Las ideas son frases que el descubrimiento
  entiende (lo comprueba una prueba en `descubrir.rs`).
-->
<script lang="ts">
  import { textosAparte } from '#lib/i18n/aparte.ts';
  import Icon from '#lib/ui/Icon.svelte';

  interface Props {
    onseleccionar: (idea: string) => void;
  }

  let { onseleccionar }: Props = $props();
  const t = textosAparte.buscar;
</script>

<section class="bienvenida" aria-labelledby="rotulo-ideas">
  <span class="icono" aria-hidden="true"><Icon nombre="buscar" tamano={28} /></span>
  <h2 id="rotulo-ideas">{t.bienvenida.titulo}</h2>
  <p>{t.bienvenida.descripcion}</p>
  <ul class="ideas">
    {#each t.ideas as idea (idea)}
      <li>
        <button type="button" class="idea" onclick={() => onseleccionar(idea)}>{idea}</button>
      </li>
    {/each}
  </ul>
</section>

<style>
  .bienvenida {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--ns-espacio-3);
    max-width: 48rem;
    margin: var(--ns-espacio-6) auto 0;
    text-align: center;
  }

  .icono {
    display: grid;
    place-items: center;
    width: 4rem;
    height: 4rem;
    border-radius: var(--ns-radio-pleno);
    background: color-mix(in srgb, var(--m3c-primary) 14%, transparent);
    color: var(--m3c-primary);
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-xl);
  }

  p {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .ideas {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: var(--ns-espacio-2);
    margin: var(--ns-espacio-3) 0 0;
    padding: 0;
    list-style: none;
  }

  .idea {
    padding: var(--ns-espacio-2) var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    cursor: pointer;
    transition:
      background var(--ns-duracion-corta) var(--ns-curva),
      border-color var(--ns-duracion-corta) var(--ns-curva);
  }

  .idea:hover {
    border-color: var(--m3c-primary);
    background: var(--m3c-surface-container-high);
  }
</style>
