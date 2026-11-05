<!--
  @component
  Consola lateral de Karaoke (DISC-01):
  Panel lateral sencillo para gestión local y preparación instrumental con IA.
-->
<script lang="ts">
  import Cajon from '#lib/ui/Cajon.svelte';
  import { onMount } from 'svelte';
  import {
    alCambiarElKaraoke,
    type EstadoKaraoke,
    karaokeEstado,
    karaokePreparar,
    karaokePrepararFavoritas
  } from '#lib/core/ipc/index.ts';
  import { reproductor } from '#lib/core/reproductor.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import Icon from '#lib/ui/Icon.svelte';

  const { oncerrar }: { oncerrar: () => void } = $props();

  const t = textos.karaokeConsola;
  let estado = $state<EstadoKaraoke | null>(null);
  let aviso = $state<string | null>(null);
  let ofertaAgregado = $state(false);

  async function refrescar() {
    estado = await karaokeEstado();
  }

  onMount(() => {
    void refrescar();
    const promesaQuitar = alCambiarElKaraoke(() => {
      void refrescar();
    });
    return () => {
      void promesaQuitar.then((quitar) => quitar());
    };
  });

  async function prepararActual() {
    if (!reproductor.pista) return;
    if (!estado?.instalado) {
      ofertaAgregado = true;
      return;
    }
    await karaokePreparar([reproductor.pista.id]);
    await refrescar();
  }

  async function prepararFavoritas() {
    if (!estado?.instalado) {
      ofertaAgregado = true;
      return;
    }
    const n = await karaokePrepararFavoritas();
    aviso = textos.biblioteca.favoritasEnCola(n);
    await refrescar();
  }
</script>

<Cajon titulo={t.titulo} subtitulo={t.subtitulo} icono="microfono" {oncerrar}>
  {#if estado && !estado.instalado}
    <div class="tarjeta alerta">
      <div class="alerta-icono"><Icon nombre="informacion" tamano={24} /></div>
      <div class="alerta-info">
        <strong>{t.motorNoInstalado}</strong>
        <p>{t.motorExplicacion}</p>
        <button type="button" class="boton relleno" onclick={() => (ofertaAgregado = true)}>
          <Icon nombre="descargar" tamano={16} />
          <span>{t.instalar}</span>
        </button>
      </div>
    </div>
  {:else if estado}
    <div class="tarjeta estado-motor">
      <div class="motor-insignia">
        <span class="punto-verde"></span>
        <span>{t.motorActivo}</span>
      </div>
      <span class="motor-detalle">{t.motorModelo}</span>
    </div>

    {#if reproductor.pista}
      {@const p = reproductor.pista}
      {@const lista = reproductor.instantanea.karaokeDisponible}
      <div class="tarjeta pista-actual">
        <span class="seccion-rotulo">{textos.reproductor.sonandoAqui}</span>
        <div class="pista-info">
          <strong class="pista-titulo">{p.titulo}</strong>
          <span class="pista-artista">{p.artista}</span>
        </div>

        {#if lista}
          <div class="insignia-lista">
            <Icon nombre="comprobado" tamano={16} />
            <span>{t.pistaActualLista}</span>
          </div>
        {:else}
          <button type="button" class="boton relleno" onclick={prepararActual}>
            <Icon nombre="microfono" tamano={16} />
            <span>{t.prepararPistaActual}</span>
          </button>
        {/if}
      </div>
    {/if}

    {#if estado.preparando}
      {@const prep = estado.preparando}
      {@const pct = Math.round(prep.fraccion * 100)}
      <div class="tarjeta progreso-caja">
        <div class="progreso-cabecera">
          <span class="seccion-rotulo">
            {t.progresoActual(
              reproductor.pista?.id === prep.pista ? (reproductor.pista?.titulo ?? '') : '',
              pct
            )}
          </span>
          <span class="progreso-pct">{pct}%</span>
        </div>
        <div class="barra-riel" role="progressbar" aria-valuenow={pct}>
          <div class="barra-fill" style:width={`${pct}%`}></div>
        </div>
      </div>
    {/if}

    <div class="tarjeta cola-info">
      <span class="seccion-rotulo">{textos.cola.titulo}</span>
      <p class="cola-descripcion">
        {estado.pendientes > 0 ? t.cancionesEnCola(estado.pendientes) : t.sinPendientes}
      </p>

      <button type="button" class="boton contorno" onclick={prepararFavoritas}>
        <Icon nombre="favorito" tamano={16} />
        <span>{t.prepararFavoritas}</span>
      </button>

      {#if aviso}
        <p class="aviso-favoritas">{aviso}</p>
      {/if}
    </div>
  {/if}
</Cajon>

{#if ofertaAgregado}
  {#await import('../agregados/OfertaAgregado.svelte') then m}
    <m.default
      id="karaoke"
      oncerrar={() => {
        ofertaAgregado = false;
        void refrescar();
      }}
    />
  {/await}
{/if}

<style>
  .tarjeta {
    padding: var(--ns-espacio-4);
    border-radius: var(--ns-radio-lg);
    border: 1px solid var(--m3c-outline-variant);
    background: var(--m3c-surface-container-high);
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
  }

  .estado-motor {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    background: color-mix(
      in srgb,
      var(--m3c-surface-container-high) 85%,
      var(--m3c-primary-container) 15%
    );
  }

  .motor-insignia {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    color: var(--m3c-on-surface);
  }

  .punto-verde {
    width: 8px;
    height: 8px;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-primary);
    box-shadow: 0 0 6px var(--m3c-primary);
  }

  .motor-detalle {
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
  }

  .seccion-rotulo {
    font-size: var(--ns-texto-xs);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-weight: 700;
    color: var(--m3c-primary);
  }

  .pista-actual {
    gap: var(--ns-espacio-3);
  }

  .pista-info {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
  }

  .pista-titulo {
    font-size: var(--ns-texto-md);
    color: var(--m3c-on-surface);
  }

  .pista-artista {
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
  }

  .insignia-lista {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    color: var(--m3c-primary);
    font-size: var(--ns-texto-xs);
    font-weight: 600;
  }

  .progreso-caja {
    gap: var(--ns-espacio-2);
  }

  .progreso-cabecera {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .progreso-pct {
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    color: var(--m3c-primary);
  }

  .barra-riel {
    height: 6px;
    background: var(--m3c-surface-container-highest);
    border-radius: var(--ns-radio-pleno);
    overflow: hidden;
  }

  .barra-fill {
    height: 100%;
    background: var(--m3c-primary);
    border-radius: var(--ns-radio-pleno);
    transition: width 200ms linear;
  }

  .cola-descripcion {
    margin: 0;
    font-size: var(--ns-texto-sm);
    color: var(--m3c-on-surface-variant);
  }

  .aviso-favoritas {
    margin: 0;
    font-size: var(--ns-texto-xs);
    color: var(--m3c-primary);
  }

  .boton {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--ns-espacio-2);
    height: 2.5rem;
    padding: 0 var(--ns-espacio-4);
    border-radius: var(--ns-radio-pleno);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    cursor: pointer;
    border: none;
    transition: background-color var(--ns-duracion-corta) var(--ns-curva);
  }

  .boton.relleno {
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .boton.relleno:hover {
    background: var(--m3c-primary);
    filter: brightness(1.1);
  }

  .boton.contorno {
    background: transparent;
    border: 1px solid var(--m3c-outline-variant);
    color: var(--m3c-on-surface);
  }

  .boton.contorno:hover {
    background: var(--m3c-surface-container-highest);
  }

  .alerta {
    flex-direction: row;
    gap: var(--ns-espacio-3);
  }

  .alerta-icono {
    color: var(--m3c-primary);
  }

  .alerta-info {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
  }

  .alerta-info p {
    margin: 0;
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
  }
</style>
