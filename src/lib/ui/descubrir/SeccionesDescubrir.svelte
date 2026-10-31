<!--
  @component
  Lo que se pide en palabras (F5.3.3): si la búsqueda expresa una intención
  ("algo triste", "para entrenar"), sus secciones de pistas, por encima de los
  resultados por texto. Si no se entiende ninguna, no pinta nada. Se carga
  aparte del arranque.
-->
<script lang="ts">
  import { type Descubrimiento, urlPortada } from '$core/ipc';
  import { descubrir } from '$core/ipc/aparte';
  import { reproductor } from '$core/reproductor.svelte';
  import { textosAparte } from '$lib/i18n/aparte';

  interface Props {
    consulta: string;
  }

  let { consulta }: Props = $props();
  const t = textosAparte.descubrir;

  let d = $state<Descubrimiento | null>(null);
  let version = 0;
  $effect(() => {
    const texto = consulta;
    const v = ++version;
    d = null;
    if (!texto) return;
    void descubrir(texto, 25).then((r) => {
      if (v === version) d = r;
    });
  });
</script>

{#if d?.entendida}
  <section class="descubrir" aria-labelledby="t-descubrir">
    <h2 id="t-descubrir">{t.titulo(d.intenciones.map((i) => t.intenciones[i]).join(' · '))}</h2>
    {#if d.secciones.length === 0}
      <p>{d.analizadas === 0 ? t.sinAnalisis : t.nada}</p>
    {/if}
    {#each d.secciones as s (s.id)}
      <h3>{t.secciones[s.id] ?? t.secciones.seleccionSugerida}</h3>
      <ul class="pistas">
        {#each s.pistas as p, k (p.id)}
          <li>
            <button
              type="button"
              class="pista"
              onclick={() =>
                reproductor.reproducirPistas(
                  s.pistas.map((x) => x.id),
                  k
                )}
            >
              {#if p.tienePortada}
                <img src={urlPortada('pista', p.id, 64)} alt="" width="40" height="40" />
              {/if}
              <span class="datos">
                <strong>{p.titulo}</strong>
                <small>{p.artista}</small>
              </span>
            </button>
          </li>
        {/each}
      </ul>
    {/each}
  </section>
{/if}

<style>
  .descubrir {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
  }

  h3 {
    margin: var(--ns-espacio-2) 0 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  p {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .pistas {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr));
    gap: var(--ns-espacio-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .pista {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    width: 100%;
    padding: var(--ns-espacio-2);
    border: none;
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .pista:hover {
    background: var(--m3c-surface-container-high);
  }

  img {
    border-radius: var(--ns-radio-sm);
    object-fit: cover;
  }

  .datos {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .datos strong,
  .datos small {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .datos small {
    color: var(--m3c-on-surface-variant);
  }
</style>
