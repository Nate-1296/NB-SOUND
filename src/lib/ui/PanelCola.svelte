<!--
  @component
  La cola de reproducción (`QueuePanel.qml` de la V1): título y Vaciar (que deja la
  que suena), la cuenta y la duración total, y cada fila con su portada, la
  insignia Sonando o Pausada, su duración, reproducir y quitar. Se reordena
  arrastrando o, con el teclado, con Alt+Arriba y Alt+Abajo sobre la fila.
-->
<script lang="ts">
  import { type PistaResumen, pistasResumen, urlPortada } from '$core/ipc';
  import { duracionLarga } from '$core/formato';
  import { formatoTiempo, reproductor } from '$core/reproductor.svelte';
  import { textos } from '$lib/i18n';

  import Icon from './Icon.svelte';

  const t = textos.cola;
  const i = $derived(reproductor.instantanea);

  /** Los datos de cada id de la cola, pedidos por tramos de 500. */
  let datos = $state(new Map<number, PistaResumen>());
  $effect(() => {
    const faltan = i.cola.filter((id) => !datos.has(id));
    if (faltan.length === 0) return;
    void (async () => {
      const nuevo = new Map(datos);
      for (let k = 0; k < faltan.length; k += 500) {
        for (const p of await pistasResumen(faltan.slice(k, k + 500))) nuevo.set(p.id, p);
      }
      datos = nuevo;
    })();
  });

  const total = $derived(i.cola.reduce((s, id) => s + (datos.get(id)?.duracionSeg ?? 0), 0));

  let arrastrada = $state<number | null>(null);

  function mover(desde: number, hasta: number) {
    if (hasta < 0 || hasta >= i.cola.length || desde === hasta) return;
    void reproductor.orden({ tipo: 'mover', desde, hasta });
  }

  function alPulsar(e: KeyboardEvent, k: number) {
    if (!e.altKey) return;
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      mover(k, k - 1);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      mover(k, k + 1);
    }
  }
</script>

<section class="panel" aria-label={t.titulo}>
  <header>
    <h2>{t.titulo}</h2>
    <button
      type="button"
      class="boton"
      disabled={i.cola.length <= 1}
      onclick={() => reproductor.orden({ tipo: 'vaciar', salvoLaActual: true })}
    >
      {t.vaciar}
    </button>
  </header>
  <div class="fichas">
    <span class="ficha acento">{textos.biblioteca.cuentaPistas(i.cola.length)}</span>
    <span class="ficha">{duracionLarga(total)}</span>
  </div>

  {#if i.cola.length === 0}
    <p class="vacio">{t.vacia}</p>
  {:else}
    <ol>
      {#each i.cola as id, k (`${id}-${k}`)}
        {@const p = datos.get(id)}
        {@const actual = k === i.indiceCola}
        <!-- El teclado llega desde los botones de la fila: Alt+Arriba y Alt+Abajo
             mueven, que es el equivalente de arrastrar. -->
        <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
        <li
          class="fila"
          class:actual
          class:destino={arrastrada !== null && arrastrada !== k}
          draggable="true"
          onkeydown={(e) => alPulsar(e, k)}
          ondragstart={() => (arrastrada = k)}
          ondragend={() => (arrastrada = null)}
          ondragover={(e) => e.preventDefault()}
          ondrop={(e) => {
            e.preventDefault();
            if (arrastrada !== null) mover(arrastrada, k);
            arrastrada = null;
          }}
        >
          <span class="asa" aria-hidden="true"><Icon nombre="menu" tamano={16} /></span>
          <span class="portada" aria-hidden="true">
            {#if p?.tienePortada}<img src={urlPortada('pista', id, 64)} alt="" />{:else}<Icon
                nombre="cancion"
                tamano={16}
              />{/if}
          </span>
          <span class="datos">
            <span class="titulo">
              {p?.titulo ?? ''}
              {#if actual}
                <span class="insignia">{reproductor.sonando ? t.sonando : t.pausada}</span>
              {/if}
            </span>
            <span class="sub">{p ? `${p.artista} · ${p.album}` : ''}</span>
          </span>
          <span class="duracion">{p ? formatoTiempo(p.duracionSeg) : ''}</span>
          <button
            type="button"
            class="mini"
            aria-label={t.reproducir(p?.titulo ?? '')}
            title={t.moverConTeclado}
            onclick={() => reproductor.orden({ tipo: 'reproducirIndice', indice: k })}
          >
            <Icon nombre="reproducir" tamano={14} />
          </button>
          <button
            type="button"
            class="mini"
            aria-label={t.quitar(p?.titulo ?? '')}
            onclick={() => reproductor.orden({ tipo: 'quitar', indice: k })}
          >
            <Icon nombre="cerrar" tamano={14} />
          </button>
        </li>
      {/each}
    </ol>
  {/if}
</section>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    width: min(26rem, 90vw);
    max-height: min(32rem, 70vh);
    padding: var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
    box-shadow: var(--m3-elevation-3, none);
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
  }

  .boton {
    height: 2.25rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-sm);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    cursor: pointer;
  }

  .boton:disabled {
    opacity: 0.38;
    cursor: default;
  }

  .fichas {
    display: flex;
    gap: var(--ns-espacio-2);
  }

  .ficha {
    padding: 0 var(--ns-espacio-2);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    font-size: var(--ns-texto-xs);
    font-weight: 600;
  }

  .ficha.acento {
    border-color: var(--m3c-primary);
    color: var(--m3c-primary);
  }

  ol {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    margin: 0;
    padding: 0;
    overflow-y: auto;
    list-style: none;
  }

  .fila {
    display: grid;
    grid-template-columns: 1rem 2.5rem minmax(0, 1fr) auto auto auto;
    align-items: center;
    gap: var(--ns-espacio-2);
    padding: var(--ns-espacio-2);
    border: 1px solid transparent;
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container);
  }

  .fila.actual {
    border-color: var(--m3c-primary);
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
  }

  .fila.destino {
    border-style: dashed;
    border-color: var(--m3c-outline);
  }

  .asa {
    color: var(--m3c-on-surface-variant);
    cursor: grab;
  }

  .portada {
    display: grid;
    place-items: center;
    width: 2.5rem;
    height: 2.5rem;
    overflow: hidden;
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
  }

  .portada img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .datos {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .titulo,
  .sub {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .titulo {
    font-weight: 700;
    font-size: var(--ns-texto-sm);
  }

  .sub,
  .duracion {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .insignia {
    margin-left: var(--ns-espacio-2);
    padding: 0 var(--ns-espacio-2);
    border: 1px solid var(--m3c-primary);
    border-radius: var(--ns-radio-pleno);
    color: var(--m3c-primary);
    font-size: var(--ns-texto-xs);
  }

  .mini {
    display: grid;
    place-items: center;
    width: 1.75rem;
    height: 1.75rem;
    border: none;
    border-radius: var(--ns-radio-sm);
    background: none;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
  }

  .mini:hover {
    background: var(--m3c-surface-container-highest);
  }

  .vacio {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }
</style>
