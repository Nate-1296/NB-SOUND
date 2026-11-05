<!--
  @component
  Una canción en una lista, con la disposición de la V1 (`VistaBiblioteca.qml`):
  número, portada, título con el artista debajo, álbum, favorita, duración y las
  acciones (añadir a playlist y el menú ··· con las secundarias: DIS-03).

  El número se cambia por el botón de reproducir al pasar por encima o con el
  foco, y por el ecualizador mientras suena: la V1 tenía un botón "Reproducir"
  por fila y la versión anterior de esta, uno más junto a la favorita. La
  favorita se ve siempre que lo es, como la estrella de la V1; si no, al pasar.
  Las columnas las comparte con `CabeceraPistas`.
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { encolar, favoritas } from '#lib/core/acciones.svelte.ts';
  import {
    completarDatos,
    mostrarEnExplorador,
    NsError,
    type PistaResumen,
    urlPortada
  } from '#lib/core/ipc/index.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { formatoTiempo } from '#lib/core/reproductor.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';

  import Icon from '../Icon.svelte';
  import MenuAcciones, { type Accion } from '../MenuAcciones.svelte';

  interface Props {
    pista: PistaResumen;
    numero: number;
    rapido?: boolean;
    sonando?: boolean;
    contexto?: 'biblioteca' | 'album' | 'artista' | 'playlist';
    onreproducir: () => void;
    /** Sus datos cambiaron: la página recarga la lista para mostrarlo. */
    oncambiada?: () => void;
    /** Lo que la lista añade al menú: mover o quitar de una playlist. */
    extra?: readonly Accion[];
  }

  let {
    pista,
    numero,
    rapido = false,
    sonando = false,
    contexto = 'biblioteca',
    onreproducir,
    oncambiada,
    extra = []
  }: Props = $props();

  const t = textos.biblioteca;
  let rota = $state(false);
  const favorita = $derived(favoritas.es(pista));

  function mostrarArchivo() {
    mostrarEnExplorador(pista.id).catch(() => notificar.error(t.explorarFallo));
  }

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

  // El álbum tiene su columna; en el álbum, el año está en la cabecera.
  const subtitulo = $derived(pista.artista);

  const acciones = $derived<Accion[]>([
    { texto: t.reproducirDespues, icono: 'siguiente', accion: () => encolar([pista.id], true) },
    { texto: t.anadirACola, icono: 'cola', accion: () => encolar([pista.id], false) },
    ...extra,
    ...(pista.albumId !== null && contexto !== 'album'
      ? [
          {
            texto: t.abrirAlbum,
            icono: 'album' as const,
            accion: () => goto(`/biblioteca/album?id=${pista.albumId}`),
            separada: true
          }
        ]
      : []),
    ...(pista.artistaId !== null && contexto !== 'artista'
      ? [
          {
            texto: t.abrirArtista,
            icono: 'artista' as const,
            accion: () => goto(`/biblioteca/artista?id=${pista.artistaId}`),
            separada: pista.albumId === null || contexto === 'album'
          }
        ]
      : []),
    ...(pista.verificada
      ? []
      : [
          {
            texto: t.completarDatos,
            icono: 'comprobado' as const,
            accion: completar,
            deshabilitada: completando,
            separada: true
          }
        ]),
    {
      texto: t.editarDatos,
      icono: 'editar',
      accion: () => (editando = true),
      separada: pista.verificada
    },
    { texto: t.mostrarEnExplorador, icono: 'carpeta', accion: mostrarArchivo },
    {
      texto: t.borrarCancion,
      icono: 'borrar',
      accion: () => (borrando = true),
      destructiva: true,
      separada: true
    }
  ]);
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
      <span class="cifra">{numero}</span>
    {/if}
    <button type="button" class="reproducir" aria-label={t.reproducir} onclick={onreproducir}>
      <Icon nombre="reproducir" tamano={16} />
    </button>
  </span>
  {#if contexto !== 'album'}
    <span class="portada" aria-hidden="true">
      {#if pista.tienePortada && !rapido && !rota}
        <img
          src={urlPortada('pista', pista.id, 64)}
          alt=""
          width="40"
          height="40"
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
  <button
    type="button"
    class="icono favorita"
    class:activo={favorita}
    aria-label={favorita ? t.quitarFavorita : t.marcarFavorita}
    aria-pressed={favorita}
    onclick={() => favoritas.alternar(pista)}
  >
    <Icon nombre="favorito" tamano={18} />
  </button>
  <span class="duracion">{formatoTiempo(pista.duracionSeg)}</span>
  <span class="acciones">
    <button
      type="button"
      class="icono"
      aria-label={textos.playlists.anadirA}
      aria-haspopup="menu"
      aria-expanded={menuPlaylistsAbierto}
      onclick={abrirMenuPlaylists}
    >
      <Icon nombre="mas" tamano={18} />
    </button>
    <div
      class="capa"
      popover="auto"
      bind:this={menuPlaylists}
      ontoggle={(e) => (menuPlaylistsAbierto = e.newState === 'open')}
    >
      {#if menuPlaylistsAbierto}
        {#await import('../playlists/MenuAnadir.svelte') then m}
          {@const Comp = m.default}
          <Comp pistas={[pista.id]} oncerrar={cerrarMenuPlaylists} />
        {/await}
      {/if}
    </div>

    <MenuAcciones {acciones} etiqueta={t.masAcciones} tamano="fila" />

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
  /* Las mismas columnas que `CabeceraPistas`. */
  .fila {
    display: grid;
    grid-template-columns:
      2.5rem 2.5rem minmax(10rem, 2fr) minmax(6rem, 1fr) 2.25rem 3.25rem
      4.5rem;
    align-items: center;
    gap: var(--ns-espacio-3);
    height: 100%;
    min-height: 3.5rem;
    padding: 0 var(--ns-espacio-3);
    border-radius: var(--ns-radio-sm);
    transition: background var(--ns-duracion-corta) var(--ns-curva);
  }

  .fila.contexto-album {
    grid-template-columns: 2.5rem minmax(10rem, 1fr) 2.25rem 3.25rem 4.5rem;
  }

  .fila:hover,
  .fila:focus-within {
    background: var(--m3c-surface-container);
  }

  .fila.sonando {
    background: color-mix(in srgb, var(--m3c-primary) 10%, transparent);
  }

  .fila.sonando .titulo {
    color: var(--m3c-primary);
  }

  .numero {
    position: relative;
    display: grid;
    place-items: center;
    height: 2.25rem;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
    font-variant-numeric: tabular-nums;
  }

  .icono-sonando {
    display: inline-flex;
    color: var(--m3c-primary);
  }

  /* El botón ocupa el sitio del número; se ve al pasar o con el foco. */
  .reproducir {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    padding: 0;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface);
    cursor: pointer;
    opacity: 0;
  }

  .fila:hover .reproducir,
  .reproducir:focus-visible {
    opacity: 1;
  }

  .fila:hover .cifra,
  .fila:hover .icono-sonando,
  .fila:has(.reproducir:focus-visible) .cifra {
    visibility: hidden;
  }

  .duracion {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-variant-numeric: tabular-nums;
    text-align: right;
  }

  .portada {
    display: grid;
    place-items: center;
    width: 2.5rem;
    height: 2.5rem;
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

  .titulo,
  .sub,
  .album {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .titulo {
    color: var(--m3c-on-surface);
    font-weight: 600;
    font-size: var(--ns-texto-sm);
  }

  .sub,
  .album {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
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

  .acciones {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: var(--ns-espacio-1);
  }

  .icono {
    display: grid;
    place-items: center;
    width: 2.125rem;
    height: 2.125rem;
    padding: 0;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
    opacity: 0;
    transition:
      opacity var(--ns-duracion-corta) var(--ns-curva),
      background var(--ns-duracion-corta) var(--ns-curva),
      color var(--ns-duracion-corta) var(--ns-curva);
  }

  .acciones :global(.disparador) {
    opacity: 0;
  }

  .fila:hover .icono,
  .fila:focus-within .icono,
  .icono[aria-expanded='true'],
  .fila:hover .acciones :global(.disparador),
  .fila:focus-within .acciones :global(.disparador),
  .acciones :global(.disparador[aria-expanded='true']) {
    opacity: 1;
  }

  .icono.activo {
    opacity: 1;
    color: var(--m3c-primary);
  }

  .icono:hover {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
  }

  .icono.activo:hover {
    color: var(--m3c-primary);
  }

  @container carcasa (max-width: 75rem) {
    .album {
      display: none;
    }

    .fila {
      grid-template-columns: 2.5rem 2.5rem minmax(10rem, 1fr) 2.25rem 3.25rem 4.5rem;
    }
  }
</style>
