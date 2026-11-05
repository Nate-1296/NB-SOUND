<!--
  @component
  La consola de karaoke (DISC-01, enmienda de ADR-007): un cajón con lo que suena
  y si se puede cantar, la preparación en curso con su progreso real, cuántas
  canciones están listas y "Preparar mis favoritas".

  Lo primero es la canción que suena, con la acción que le toca: cantarla si
  está lista, prepararla si no. La versión anterior abría con una tarjeta de
  "Motor de separación activo · htdemucs (Meta)" y no dejaba cantar desde aquí.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { estadoBiblioteca } from '#lib/core/estadoVistas.svelte.ts';
  import {
    alCambiarElKaraoke,
    bibliotecaPistas,
    type EstadoKaraoke,
    karaokeEstado,
    karaokePreparar,
    karaokePrepararFavoritas,
    urlPortada
  } from '#lib/core/ipc/index.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { reproductor } from '#lib/core/reproductor.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import Cajon from '#lib/ui/Cajon.svelte';
  import Icon from '#lib/ui/Icon.svelte';

  const { oncerrar }: { oncerrar: () => void } = $props();

  const t = textos.karaokeConsola;
  let estado = $state<EstadoKaraoke | null>(null);
  let listas = $state<number | null>(null);
  let ofertaAgregado = $state(false);

  async function refrescar() {
    estado = await karaokeEstado().catch(() => null);
    listas = await bibliotecaPistas(
      {
        texto: null,
        favoritas: false,
        sinVerificar: false,
        paraCantar: true,
        albumId: null,
        artistaId: null,
        orden: 'tituloAsc'
      },
      0,
      1
    )
      .then((r) => r.total)
      .catch(() => null);
  }

  onMount(() => {
    void refrescar();
    const quitar = alCambiarElKaraoke(() => void refrescar());
    return () => void quitar.then((q) => q());
  });

  const pista = $derived(reproductor.pista);
  const preparando = $derived(estado?.preparando ?? null);
  const pct = $derived(Math.round((preparando?.fraccion ?? 0) * 100));
  const estaSePrepara = $derived(preparando !== null && preparando.pista === pista?.id);

  async function prepararActual() {
    if (!pista) return;
    if (!estado?.instalado) {
      ofertaAgregado = true;
      return;
    }
    try {
      await karaokePreparar([pista.id]);
      await refrescar();
    } catch {
      notificar.error(textos.reproductor.karaokePreparar);
    }
  }

  async function prepararFavoritas() {
    if (!estado?.instalado) {
      ofertaAgregado = true;
      return;
    }
    const n = await karaokePrepararFavoritas().catch(() => null);
    if (n === null) return;
    notificar.informacion(textos.biblioteca.favoritasEnCola(n));
    await refrescar();
  }

  function verListas() {
    estadoBiblioteca.vista = 'pistas';
    estadoBiblioteca.pistas.paraCantar = true;
    oncerrar();
    void goto('/biblioteca?vista=pistas&cantar=1');
  }
</script>

<Cajon titulo={t.titulo} subtitulo={t.subtitulo} icono="microfono" {oncerrar}>
  {#if estado && !estado.instalado}
    <section class="tarjeta alerta">
      <Icon nombre="informacion" tamano={22} />
      <div class="alerta-info">
        <strong>{t.motorNoInstalado}</strong>
        <p>{t.motorExplicacion}</p>
        <button type="button" class="boton relleno" onclick={() => (ofertaAgregado = true)}>
          <Icon nombre="descargar" tamano={16} />{t.instalar}
        </button>
      </div>
    </section>
  {/if}

  <section class="tarjeta" aria-labelledby="k-ahora">
    <h3 id="k-ahora" class="rotulo">{t.ahora}</h3>
    {#if pista}
      <div class="pista">
        <span class="portada">
          {#if pista.tienePortada}
            <img src={urlPortada('pista', pista.id, 128)} alt="" />
          {:else}
            <Icon nombre="cancion" tamano={22} />
          {/if}
        </span>
        <span class="datos">
          <strong>{pista.titulo}</strong>
          <span>{pista.artista}</span>
          {#if reproductor.instantanea.karaokeDisponible}
            <span class="estado lista"><Icon nombre="comprobado" tamano={14} />{t.lista}</span>
          {:else if estaSePrepara}
            <span class="estado">{t.preparandoEsta(pct)}</span>
          {:else}
            <span class="estado">{t.noLista}</span>
          {/if}
        </span>
      </div>
      {#if estaSePrepara}
        <div
          class="barra"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <span style:width={`${pct}%`}></span>
        </div>
      {:else if reproductor.instantanea.karaokeDisponible}
        <button
          type="button"
          class="boton relleno"
          aria-pressed={reproductor.instantanea.karaokeActivo}
          onclick={() => reproductor.alternarKaraoke()}
        >
          <Icon nombre="microfono" tamano={16} />
          {reproductor.instantanea.karaokeActivo ? t.dejarDeCantar : t.cantar}
        </button>
      {:else}
        <button type="button" class="boton relleno" onclick={prepararActual}>
          <Icon nombre="microfono" tamano={16} />{t.prepararPistaActual}
        </button>
      {/if}
    {:else}
      <p class="nota">{t.nadaSonando}</p>
    {/if}
  </section>

  {#if estado?.instalado}
    <section class="tarjeta" aria-labelledby="k-prep">
      <h3 id="k-prep" class="rotulo">{t.enPreparacion}</h3>
      {#if preparando && !estaSePrepara}
        <p class="nota fuerte">{t.preparandoOtra(pct)}</p>
        <div
          class="barra"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <span style:width={`${pct}%`}></span>
        </div>
      {/if}
      <p class="nota">
        {estado.pendientes > 0 ? t.cancionesEnCola(estado.pendientes) : t.sinPendientes}
      </p>
    </section>
  {/if}

  <section class="tarjeta" aria-labelledby="k-rep">
    <h3 id="k-rep" class="rotulo">{t.repertorio}</h3>
    {#if listas !== null}
      <p class="cifra">{t.listas(listas)}</p>
    {/if}
    <div class="botones">
      {#if listas}
        <button type="button" class="boton" onclick={verListas}>
          <Icon nombre="biblioteca" tamano={16} />{t.verListas}
        </button>
      {/if}
      <button type="button" class="boton" onclick={prepararFavoritas}>
        <Icon nombre="favorito" tamano={16} />{t.prepararFavoritas}
      </button>
    </div>
  </section>
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
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-4);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-high);
  }

  .rotulo {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .pista {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    min-width: 0;
  }

  .portada {
    display: grid;
    flex: 0 0 auto;
    place-items: center;
    width: 4rem;
    height: 4rem;
    overflow: hidden;
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
  }

  .portada img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .datos {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    min-width: 0;
  }

  .datos strong,
  .datos > span:not(.estado) {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .datos > span:not(.estado) {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .estado {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-1);
    margin-top: var(--ns-espacio-1);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-weight: 600;
  }

  .estado.lista {
    color: var(--m3c-primary);
  }

  .barra {
    height: 0.375rem;
    overflow: hidden;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
  }

  .barra span {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: var(--m3c-primary);
    transition: width var(--ns-duracion-media) var(--ns-curva);
  }

  .nota {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .nota.fuerte {
    color: var(--m3c-on-surface);
    font-weight: 600;
  }

  .cifra {
    margin: 0;
    font-size: var(--ns-texto-lg);
    font-weight: 700;
  }

  .botones {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ns-espacio-2);
  }

  .boton {
    display: inline-flex;
    align-self: flex-start;
    align-items: center;
    justify-content: center;
    gap: var(--ns-espacio-2);
    height: 2.5rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    cursor: pointer;
    transition: background var(--ns-duracion-corta) var(--ns-curva);
  }

  .boton:hover {
    background: var(--m3c-surface-container-highest);
  }

  .boton.relleno {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .boton.relleno:hover {
    filter: brightness(1.06);
  }

  .alerta {
    flex-direction: row;
    align-items: flex-start;
    color: var(--m3c-primary);
  }

  .alerta-info {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    color: var(--m3c-on-surface);
  }

  .alerta-info p {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }
</style>
