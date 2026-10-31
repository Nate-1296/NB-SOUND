<!--
  @component
  Una playlist abierta: su mosaico y datos, Reproducir, Anclar, Editar regla en las
  inteligentes del usuario, Renombrar y ordenar en las manuales, y Borrar en las
  creadas por el usuario.
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import {
    anclarPlaylist,
    borrarPlaylist,
    fijarFavorita,
    moverEnPlaylist,
    type PistaResumen,
    type PlaylistResumen,
    playlist,
    playlistPistas,
    quitarDePlaylist,
    reproducirPlaylist
  } from '$core/ipc';
  import { formatoTiempo, reproductor } from '$core/reproductor.svelte';
  import { textos } from '$lib/i18n';
  import { esAparte } from '$lib/i18n/es-aparte';
  import FilaPista from '$ui/biblioteca/FilaPista.svelte';
  import Icon from '$ui/Icon.svelte';
  import DialogoInteligente from '$ui/playlists/DialogoInteligente.svelte';
  import DialogoPlaylist from '$ui/playlists/DialogoPlaylist.svelte';
  import Mosaico from '$ui/playlists/Mosaico.svelte';

  const t = textos.playlists;
  const ti = esAparte.inteligentes;
  const id = $derived(Number(page.url.searchParams.get('id')));

  let datos = $state<PlaylistResumen | null | undefined>(undefined);
  let pistas = $state<PistaResumen[]>([]);
  let renombrando = $state(false);
  let editandoRegla = $state(false);
  let version = $state(0);

  $effect(() => {
    void version;
    if (!Number.isFinite(id) || id <= 0) {
      datos = null;
      return;
    }
    void playlist(id).then((p) => (datos = p));
    // Una playlist manual rara vez pasa de unos cientos; las automáticas son de 50 a 200.
    void playlistPistas(id, 0, 500).then((p) => (pistas = p.pistas));
  });

  async function mover(desde: number, hasta: number) {
    const copia = [...pistas];
    const [p] = copia.splice(desde, 1);
    if (!p) return;
    copia.splice(hasta, 0, p);
    const anterior = pistas;
    pistas = copia;
    try {
      await moverEnPlaylist(id, desde, hasta);
    } catch {
      pistas = anterior;
      window.dispatchEvent(
        new CustomEvent('ns:notificacion', {
          detail: { tipo: 'error', mensaje: esAparte.comun.error }
        })
      );
    }
  }

  async function quitar(p: PistaResumen) {
    const anterior = pistas;
    pistas = pistas.filter((x) => x.id !== p.id);
    try {
      await quitarDePlaylist(id, p.id);
      version += 1;
    } catch {
      pistas = anterior;
      window.dispatchEvent(
        new CustomEvent('ns:notificacion', {
          detail: { tipo: 'error', mensaje: esAparte.comun.error }
        })
      );
    }
  }

  async function borrar() {
    if (!datos || !confirm(t.confirmarBorrar(datos.nombre))) return;
    await borrarPlaylist(id);
    await goto('/playlists');
  }

  function alternarFavorita(i: number) {
    const p = pistas[i];
    if (!p) return;
    pistas[i] = { ...p, favorita: !p.favorita };
    void fijarFavorita(p.id, !p.favorita);
  }
</script>

<section class="detalle">
  <a class="volver" href="/playlists"><Icon nombre="atras" tamano={18} />{t.volver}</a>

  {#if datos === null}
    <p class="vacio">{t.noEncontrada}</p>
  {:else if datos}
    <header class="cabecera">
      <div class="portada"><Mosaico pistas={datos.mosaico} tamano={320} /></div>
      <div class="datos">
        <span class="etiqueta">{datos.etiqueta}</span>
        <h1>{datos.nombre}</h1>
        <span class="sub">{t.resumen(datos.numPistas, formatoTiempo(datos.duracionSeg))}</span>
        {#if datos.descripcion}<p class="descripcion">{datos.descripcion}</p>{/if}
        <div class="botones">
          <button
            type="button"
            class="boton relleno"
            disabled={pistas.length === 0}
            onclick={() => reproducirPlaylist(id, 0)}
          >
            <Icon nombre="reproducir" tamano={16} />{t.reproducir}
          </button>
          <button
            type="button"
            class="boton"
            disabled={pistas.length === 0}
            onclick={async () => {
              if (pistas.length === 0) return;
              if (!reproductor.instantanea.aleatorio) void reproductor.alternarAleatorio();
              await reproducirPlaylist(id, Math.floor(Math.random() * pistas.length));
            }}
          >
            <Icon nombre="aleatorio" tamano={16} />{t.aleatorio}
          </button>
          <button
            type="button"
            class="boton"
            onclick={async () => {
              if (!datos) return;
              await anclarPlaylist(id, !datos.anclada);
              version += 1;
            }}
          >
            {datos.anclada ? t.desanclar : t.anclar}
          </button>
          {#if datos.editable}
            <button type="button" class="boton" onclick={() => (renombrando = true)}>
              <Icon nombre="editar" tamano={16} />{t.renombrar}
            </button>
          {/if}
          {#if datos.reglaInteligente}
            <button type="button" class="boton" onclick={() => (editandoRegla = true)}>
              <Icon nombre="editar" tamano={16} />{ti.editar}
            </button>
          {/if}
          {#if datos.borrable}
            <button type="button" class="boton peligro" onclick={borrar}>
              <Icon nombre="borrar" tamano={16} />{t.borrar}
            </button>
          {/if}
        </div>
      </div>
    </header>

    {#if pistas.length === 0}
      <p class="vacio">{t.vacia}</p>
    {:else}
      <ul class="pistas" aria-label={textos.biblioteca.lista}>
        {#each pistas as p, i (p.id)}
          <li class:editable={datos.editable}>
            <FilaPista
              contexto="playlist"
              pista={p}
              numero={i + 1}
              sonando={reproductor.instantanea.pistaId === p.id}
              onreproducir={() => reproducirPlaylist(id, i)}
              onanadir={() =>
                reproductor.orden({ tipo: 'agregar', ids: [p.id], justoDespues: false })}
              onfavorita={() => alternarFavorita(i)}
            />
            {#if datos.editable}
              <span class="orden">
                <button
                  type="button"
                  class="mini"
                  aria-label={t.subir}
                  title={t.subir}
                  disabled={i === 0}
                  onclick={() => mover(i, i - 1)}
                >
                  <Icon nombre="arriba" tamano={16} />
                </button>
                <button
                  type="button"
                  class="mini"
                  aria-label={t.bajar}
                  title={t.bajar}
                  disabled={i === pistas.length - 1}
                  onclick={() => mover(i, i + 1)}
                >
                  <Icon nombre="abajo" tamano={16} />
                </button>
                <button
                  type="button"
                  class="mini"
                  aria-label={t.quitar}
                  title={t.quitar}
                  onclick={() => quitar(p)}
                >
                  <Icon nombre="cerrar" tamano={16} />
                </button>
              </span>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}

    <DialogoPlaylist
      abierto={renombrando}
      editar={{ id, nombre: datos.nombre, descripcion: datos.descripcion }}
      onlisto={() => {
        renombrando = false;
        version += 1;
      }}
      oncerrar={() => (renombrando = false)}
    />

    {#if datos.reglaInteligente}
      <DialogoInteligente
        abierto={editandoRegla}
        editar={{
          id,
          nombre: datos.nombre,
          descripcion: datos.descripcion,
          regla: datos.reglaInteligente
        }}
        onlisto={() => {
          editandoRegla = false;
          version += 1;
        }}
        oncerrar={() => (editandoRegla = false)}
      />
    {/if}
  {/if}
</section>

<style>
  .detalle {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
  }

  .volver {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
    text-decoration: none;
  }

  .cabecera {
    display: flex;
    align-items: flex-end;
    gap: var(--ns-espacio-5);
  }

  .portada {
    flex: 0 0 13rem;
  }

  .datos {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    min-width: 0;
  }

  .etiqueta {
    align-self: flex-start;
    padding: 0 var(--ns-espacio-2);
    border: 1px solid var(--m3c-primary);
    border-radius: var(--ns-radio-pleno);
    color: var(--m3c-primary);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
  }

  h1 {
    margin: 0;
    font-size: var(--ns-texto-2xl);
  }

  .sub {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .descripcion {
    margin: 0;
    font-size: var(--ns-texto-sm);
  }

  .botones {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-3);
  }

  .boton {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    height: 2.5rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }

  .boton.relleno {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .boton.peligro {
    color: var(--m3c-error);
  }

  .boton:disabled {
    opacity: 0.38;
    cursor: default;
  }

  .pistas {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .pistas li {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    height: 4.125rem;
  }

  .pistas li.editable {
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
  }

  .orden {
    display: flex;
    gap: var(--ns-espacio-1);
  }

  .mini {
    display: grid;
    place-items: center;
    width: 2rem;
    height: 2rem;
    border: none;
    border-radius: var(--ns-radio-sm);
    background: none;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
  }

  .mini:hover:not(:disabled) {
    background: var(--m3c-surface-container-high);
  }

  .mini:disabled {
    opacity: 0.38;
    cursor: default;
  }

  .vacio {
    color: var(--m3c-on-surface-variant);
  }
</style>
