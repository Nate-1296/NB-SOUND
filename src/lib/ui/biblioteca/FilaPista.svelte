<!--
  @component
  Una canción en una lista, con la disposición de la V1 (`VistaBiblioteca.qml`):
  número, portada, título con artista, álbum y año debajo, álbum, duración y
  acciones limpias (reproducir, favorita, añadir a playlist y menú desplegable
  ··· con acciones secundarias: DIS-03).
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { completarDatos, NsError, type PistaResumen, urlPortada } from '$core/ipc';
  import { formatoTiempo } from '$core/reproductor.svelte';
  import { textos } from '$lib/i18n';

  import Icon from '../Icon.svelte';
  import MenuAnadir from '../playlists/MenuAnadir.svelte';

  interface Props {
    pista: PistaResumen;
    numero: number;
    rapido?: boolean;
    sonando?: boolean;
    contexto?: 'biblioteca' | 'album' | 'artista' | 'playlist';
    onreproducir: () => void;
    onanadir: () => void;
    onfavorita: () => void;
    /** Sus datos cambiaron: la página recarga la lista para mostrarlo. */
    oncambiada?: () => void;
  }

  let {
    pista,
    numero,
    rapido = false,
    sonando = false,
    contexto = 'biblioteca',
    onreproducir,
    onanadir,
    onfavorita,
    oncambiada
  }: Props = $props();

  const t = textos.biblioteca;
  let rota = $state(false);

  // Popover para añadir a playlists
  let menuPlaylists: HTMLDivElement | undefined = $state();
  let menuPlaylistsAbierto = $state(false);
  function abrirMenuPlaylists(e: MouseEvent) {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    if (!menuPlaylists) return;
    menuPlaylists.style.top = `${Math.min(r.bottom + 4, window.innerHeight - 300)}px`;
    menuPlaylists.style.left = `${Math.max(8, r.right - 224)}px`;
    menuPlaylistsAbierto = true;
    menuPlaylists.showPopover();
  }
  function cerrarMenuPlaylists() {
    menuPlaylists?.hidePopover();
  }

  // Popover para más acciones (···)
  let menuAcciones: HTMLDivElement | undefined = $state();
  let menuAccionesAbierto = $state(false);
  function abrirMenuAcciones(e: MouseEvent) {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    if (!menuAcciones) return;
    menuAcciones.style.top = `${Math.min(r.bottom + 4, window.innerHeight - 300)}px`;
    menuAcciones.style.left = `${Math.max(8, r.right - 200)}px`;
    menuAccionesAbierto = true;
    menuAcciones.showPopover();
  }
  function cerrarMenuAcciones() {
    menuAcciones?.hidePopover();
  }

  let editando = $state(false);
  let borrando = $state(false);
  let completando = $state(false);
  let resultado = $state<string | null>(null);

  async function completar() {
    completando = true;
    resultado = null;
    try {
      const r = await completarDatos(pista.id);
      resultado = t.completado(r);
      if (r.identificada || r.portada || r.letra) oncambiada?.();
    } catch (error) {
      resultado =
        error instanceof NsError && error.code === 'FILE_NOT_FOUND'
          ? t.completarSinArchivo
          : t.completarFallo;
    } finally {
      completando = false;
    }
  }

  const subtitulo = $derived(
    contexto === 'album'
      ? [pista.artista, pista.anio ?? ''].filter((x) => x !== '').join(' · ')
      : [pista.artista, pista.album, pista.anio ?? ''].filter((x) => x !== '').join(' · ')
  );
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div
  class="fila"
  class:sonando
  class:contexto-album={contexto === 'album'}
  role="row"
  tabindex="0"
  ondblclick={(e) => {
    if ((e.target as HTMLElement).closest('button, a, [popover]')) return;
    onreproducir();
  }}
  onkeydown={(e) => {
    if (e.key === 'Enter' && e.target === e.currentTarget) {
      e.preventDefault();
      onreproducir();
    }
  }}
>
  <span class="numero">
    {#if sonando}
      <span class="icono-sonando" title={t.sonando} aria-label={t.sonando}>
        <Icon nombre="ecualizador" tamano={16} />
      </span>
    {:else}
      {numero}
    {/if}
  </span>
  {#if contexto !== 'album'}
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
  {/if}
  <span class="datos">
    <span class="titulo" title={pista.titulo}>
      {pista.titulo}
      {#if !pista.verificada}<span class="insignia">{t.sinVerificarInsignia}</span>{/if}
    </span>
    {#if completando || resultado}
      <span class="sub" role="status">{completando ? t.completando : resultado}</span>
    {:else}
      <span class="sub" title={subtitulo}>{subtitulo}</span>
    {/if}
  </span>
  {#if contexto !== 'album'}
    <span class="album" title={pista.album}>{pista.album}</span>
  {/if}
  <span class="duracion">{formatoTiempo(pista.duracionSeg)}</span>
  <span class="acciones">
    <button type="button" class="icono reproducir" aria-label={t.reproducir} onclick={onreproducir}>
      <Icon nombre="reproducir" tamano={16} />
    </button>
    <button
      type="button"
      class="icono"
      class:activo={pista.favorita}
      aria-label={pista.favorita ? t.quitarFavorita : t.marcarFavorita}
      aria-pressed={pista.favorita}
      onclick={onfavorita}
    >
      <Icon nombre="favorito" tamano={18} />
    </button>
    <button
      type="button"
      class="icono"
      aria-label={textos.playlists.anadirA}
      aria-haspopup="menu"
      onclick={abrirMenuPlaylists}
    >
      <Icon nombre="mas" tamano={18} />
    </button>
    <button
      type="button"
      class="icono"
      aria-label={t.masAcciones}
      aria-haspopup="menu"
      onclick={abrirMenuAcciones}
    >
      <Icon nombre="masHorizontal" tamano={18} />
    </button>

    <div
      class="capa"
      popover="auto"
      bind:this={menuPlaylists}
      ontoggle={(e) => (menuPlaylistsAbierto = e.newState === 'open')}
    >
      {#if menuPlaylistsAbierto}
        <MenuAnadir pistas={[pista.id]} oncerrar={cerrarMenuPlaylists} />
      {/if}
    </div>

    <div
      class="capa"
      popover="auto"
      bind:this={menuAcciones}
      ontoggle={(e) => (menuAccionesAbierto = e.newState === 'open')}
    >
      {#if menuAccionesAbierto}
        <div class="menu-contextual" role="menu">
          <button
            type="button"
            role="menuitem"
            class="opcion-menu"
            onclick={() => {
              cerrarMenuAcciones();
              onanadir();
            }}
          >
            <Icon nombre="cola" tamano={18} />
            <span>{t.anadirACola}</span>
          </button>
          {#if !pista.verificada}
            <button
              type="button"
              role="menuitem"
              class="opcion-menu"
              disabled={completando}
              onclick={() => {
                cerrarMenuAcciones();
                completar();
              }}
            >
              <Icon nombre="comprobado" tamano={18} />
              <span>{t.completarDatos}</span>
            </button>
          {/if}
          <button
            type="button"
            role="menuitem"
            class="opcion-menu"
            onclick={() => {
              cerrarMenuAcciones();
              editando = true;
            }}
          >
            <Icon nombre="editar" tamano={18} />
            <span>{t.editarDatos}</span>
          </button>
          {#if contexto !== 'album' && pista.albumId !== null}
            <button
              type="button"
              role="menuitem"
              class="opcion-menu"
              onclick={() => {
                cerrarMenuAcciones();
                goto(`/biblioteca/album?id=${pista.albumId}`);
              }}
            >
              <Icon nombre="album" tamano={18} />
              <span>{t.abrirAlbum}</span>
            </button>
          {/if}
          {#if contexto !== 'artista' && pista.artistaId !== null}
            <button
              type="button"
              role="menuitem"
              class="opcion-menu"
              onclick={() => {
                cerrarMenuAcciones();
                goto(`/biblioteca/artista?id=${pista.artistaId}`);
              }}
            >
              <Icon nombre="artista" tamano={18} />
              <span>{t.abrirArtista}</span>
            </button>
          {/if}
          <hr class="separador-menu" />
          <button
            type="button"
            role="menuitem"
            class="opcion-menu destructiva"
            onclick={() => {
              cerrarMenuAcciones();
              borrando = true;
            }}
          >
            <Icon nombre="borrar" tamano={18} />
            <span>{t.borrarCancion}</span>
          </button>
        </div>
      {/if}
    </div>

    {#if editando}
      {#await import('../edicion/DialogoEditar.svelte') then m}
        <m.default
          tipo="pista"
          id={pista.id}
          oncerrar={() => (editando = false)}
          onguardado={() => {
            editando = false;
            oncambiada?.();
          }}
        />
      {/await}
    {/if}
    {#if borrando}
      {#await import('./DialogoBorrarPista.svelte') then m}
        <m.default
          pistaId={pista.id}
          titulo={pista.titulo}
          oneliminada={() => {
            borrando = false;
            oncambiada?.();
          }}
          oncerrar={() => (borrando = false)}
        />
      {/await}
    {/if}
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

  .fila.contexto-album {
    grid-template-columns: 2.5rem minmax(10rem, 2fr) 3.5rem auto;
  }

  .icono-sonando {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--m3c-primary);
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

  .capa {
    position: fixed;
    inset: auto;
    margin: 0;
    padding: 0;
    border: none;
    background: none;
  }

  .menu-contextual {
    display: flex;
    flex-direction: column;
    min-width: 14rem;
    padding: var(--ns-espacio-1);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-high);
    box-shadow: 0 4px 16px var(--m3c-shadow);
  }

  .separador-menu {
    margin: var(--ns-espacio-1) 0;
    border: none;
    border-top: 1px solid var(--m3c-outline-variant);
  }

  .opcion-menu {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border: none;
    border-radius: var(--ns-radio-sm);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    text-align: left;
    cursor: pointer;
    transition: background 120ms ease;
  }

  .opcion-menu:hover:not(:disabled) {
    background: var(--m3c-surface-container-highest);
  }

  .opcion-menu:disabled {
    opacity: 0.38;
    cursor: default;
  }

  .opcion-menu.destructiva {
    color: var(--m3c-error);
  }

  .opcion-menu.destructiva:hover {
    background: var(--m3c-error-container);
    color: var(--m3c-on-error-container);
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

  .icono:hover {
    background: var(--m3c-surface-container-high);
  }

  .icono.reproducir {
    color: var(--m3c-primary);
  }

  .icono.reproducir:hover {
    background: var(--m3c-primary-container);
    color: var(--m3c-on-primary-container);
  }

  @container carcasa (max-width: 75rem) {
    .album {
      display: none;
    }

    .fila {
      grid-template-columns: 2.5rem 2.625rem minmax(10rem, 1fr) 3.5rem auto;
    }
  }
</style>
