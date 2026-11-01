<!--
  @component
  Pantalla de bienvenida y 24 ideas musicales de "Háblale a tu biblioteca" (COMP-16).
  Se carga diferido cuando la consulta de búsqueda está vacía para proteger el
  presupuesto de arranque de la aplicación (250 KB).
-->
<script lang="ts">
  import { textosAparte } from '$lib/i18n/aparte';
  import Icon from '$ui/Icon.svelte';

  interface Props {
    onseleccionar: (idea: string) => void;
  }

  let { onseleccionar }: Props = $props();
  const t = textosAparte.buscar;
</script>

<div class="bienvenida">
  <div class="modos">
    <div class="modo-tarjeta">
      <div class="modo-icono">
        <Icon nombre="buscar" tamano={24} />
      </div>
      <div class="modo-info">
        <h3>{t.bienvenida.modoDirecto}</h3>
        <p>{t.bienvenida.modoDirectoDesc}</p>
      </div>
    </div>
    <div class="modo-tarjeta destacado">
      <div class="modo-icono destacado">
        <Icon nombre="dj" tamano={24} />
      </div>
      <div class="modo-info">
        <h3>{t.bienvenida.modoSemantico}</h3>
        <p>{t.bienvenida.modoSemanticoDesc}</p>
      </div>
    </div>
  </div>

  <section class="ideas-seccion" aria-labelledby="rotulo-ideas">
    <h2 id="rotulo-ideas" class="ideas-titulo">
      <Icon nombre="inicio" tamano={18} />
      {t.bienvenida.ideasTitulo}
    </h2>
    <div class="rejilla-ideas">
      {#each t.ideas as idea (idea)}
        <button type="button" class="chip-idea" onclick={() => onseleccionar(idea)}>
          <span class="punto" aria-hidden="true"></span>
          <span class="texto-idea">{idea}</span>
        </button>
      {/each}
    </div>
  </section>
</div>

<style>
  .bienvenida {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-5);
    margin-top: var(--ns-espacio-2);
  }

  .modos {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
    gap: var(--ns-espacio-4);
  }

  .modo-tarjeta {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container);
  }

  .modo-tarjeta.destacado {
    border-color: var(--m3c-primary);
    background: var(--m3c-surface-container-high);
  }

  .modo-icono {
    display: grid;
    place-items: center;
    width: 3rem;
    height: 3rem;
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
    flex: 0 0 3rem;
  }

  .modo-icono.destacado {
    background: var(--m3c-primary-container);
    color: var(--m3c-on-primary-container);
  }

  .modo-info h3 {
    margin: 0;
    font-size: var(--ns-texto-base);
    font-weight: 700;
  }

  .modo-info p {
    margin: var(--ns-espacio-1) 0 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .ideas-seccion {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
  }

  .ideas-titulo {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    margin: 0;
    color: var(--m3c-on-surface);
    font-size: var(--ns-texto-md);
    font-weight: 700;
  }

  .rejilla-ideas {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
    gap: var(--ns-espacio-2);
  }

  .chip-idea {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-low);
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-xs);
    text-align: left;
    cursor: pointer;
  }

  .chip-idea:hover {
    border-color: var(--m3c-primary);
    background: var(--m3c-surface-container);
  }

  .punto {
    width: 6px;
    height: 6px;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-primary);
    flex: 0 0 6px;
  }

  .texto-idea {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
