<!--
  @component
  Una canción en una lista, con la disposición de la V1 (`VistaBiblioteca.qml`):
  número, portada, título con artista, álbum y año debajo, álbum, duración, la
  estrella, el menú y las acciones Reproducir, Añadir a cola, Abrir álbum y Abrir
  artista.

  Durante el desplazamiento rápido no pide la portada (F0.4.7): pinta el hueco y
  la pide al frenar.
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { type PistaResumen, urlPortada } from '$core/ipc';
  import { formatoTiempo } from '$core/reproductor.svelte';
  import { textos } from '$lib/i18n';

  import Icon from '../Icon.svelte';

  interface Props {
    pista: PistaResumen;
    numero: number;
    rapido?: boolean;
    sonando?: boolean;
    onreproducir: () => void;
    onanadir: () => void;
    onfavorita: () => void;
  }

  let {
    pista,
    numero,
    rapido = false,
    sonando = false,
    onreproducir,
    onanadir,
    onfavorita
  }: Props = $props();

  const t = textos.biblioteca;
  let rota = $state(false);
  const subtitulo = $derived(
    [pista.artista, pista.album, pista.anio ?? ''].filter((x) => x !== '').join(' · ')
  );
</script>

<div class="fila" class:sonando>
  <span class="numero">{numero}</span>
  <span class="portada" aria-hidden="true">
    {#if pista.tienePortada && !rapido && !rota}
      <img
        src={urlPortada('pista', pista.id, 64)}
        alt=""
        width="42"
        height="42"
        loading="lazy"
        onerror={() => (rota = true)}
      />
    {:else}
      <Icon nombre="cancion" tamano={18} />
    {/if}
  </span>
  <span class="datos">
    <span class="titulo" title={pista.titulo}>
      {pista.titulo}
      {#if !pista.verificada}<span class="insignia">{t.sinVerificarInsignia}</span>{/if}
    </span>
    <span class="sub" title={subtitulo}>{subtitulo}</span>
  </span>
  <span class="album" title={pista.album}>{pista.album}</span>
  <span class="duracion">{formatoTiempo(pista.duracionSeg)}</span>
  <span class="acciones">
    <button
      type="button"
      class="icono"
      class:activo={pista.favorita}
      aria-label={pista.favorita ? t.quitarFavorita : t.marcarFavorita}
      aria-pressed={pista.favorita}
      title={pista.favorita ? t.quitarFavorita : t.marcarFavorita}
      onclick={onfavorita}
    >
      <Icon nombre="favorito" tamano={18} />
    </button>
    <button type="button" class="icono" aria-label={t.masAcciones} title={t.masAcciones}>
      <Icon nombre="mas" tamano={18} />
    </button>
    <button type="button" class="boton principal" onclick={onreproducir}>
      <Icon nombre="reproducir" tamano={14} />{t.reproducir}
    </button>
    <button type="button" class="boton" onclick={onanadir}>
      <Icon nombre="reproducir" tamano={14} />{t.anadirACola}
    </button>
    <button
      type="button"
      class="boton"
      disabled={pista.albumId === null}
      onclick={() => goto(`/biblioteca/album?id=${pista.albumId}`)}
    >
      {t.abrirAlbum}
    </button>
    <button
      type="button"
      class="boton"
      disabled={pista.artistaId === null}
      onclick={() => goto(`/biblioteca/artista?id=${pista.artistaId}`)}
    >
      {t.abrirArtista}
    </button>
  </span>
</div>

<style>
  .fila {
    display: grid;
    grid-template-columns: 2.5rem 2.625rem minmax(10rem, 2fr) minmax(6rem, 1fr) 3.5rem auto;
    align-items: center;
    gap: var(--ns-espacio-3);
    height: 100%;
    padding: 0 var(--ns-espacio-3);
    border-radius: var(--ns-radio-sm);
  }

  .fila:hover {
    background: var(--m3c-surface-container);
  }

  .fila.sonando .titulo {
    color: var(--m3c-primary);
  }

  .numero,
  .duracion {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-variant-numeric: tabular-nums;
    text-align: center;
  }

  .portada {
    display: grid;
    place-items: center;
    width: 2.625rem;
    height: 2.625rem;
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
    min-width: 0;
  }

  .titulo,
  .sub,
  .album {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .titulo {
    font-weight: 700;
    font-size: var(--ns-texto-sm);
  }

  .sub {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .album {
    font-size: var(--ns-texto-sm);
  }

  .insignia {
    margin-left: var(--ns-espacio-2);
    padding: 0 var(--ns-espacio-2);
    border: 1px solid var(--m3c-outline);
    border-radius: var(--ns-radio-pleno);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-weight: 500;
  }

  .acciones {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
  }

  .icono {
    display: grid;
    place-items: center;
    width: 2.25rem;
    height: 2.25rem;
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
  }

  .icono.activo {
    border-color: var(--m3c-primary);
    color: var(--m3c-primary);
  }

  .boton {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-1);
    height: 2.25rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    white-space: nowrap;
    cursor: pointer;
  }

  .boton:hover:not(:disabled),
  .icono:hover {
    background: var(--m3c-surface-container-high);
  }

  .boton:disabled {
    opacity: 0.38;
    cursor: default;
  }

  .boton.principal {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .boton.principal:hover {
    background: var(--m3c-primary);
    filter: brightness(1.08);
  }

  @container carcasa (max-width: 75rem) {
    .album {
      display: none;
    }

    .fila {
      grid-template-columns: 2.5rem 2.625rem minmax(10rem, 1fr) 3.5rem auto;
    }

    .boton:not(.principal) {
      display: none;
    }
  }
</style>
