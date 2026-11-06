<!--
  @component
  Una playlist abierta: su mosaico y datos, Reproducir, Anclar, Editar regla en las
  inteligentes del usuario, Renombrar y ordenar en las manuales, y Borrar en las
  creadas por el usuario.
-->
<script lang="ts">
  import { cambios } from '#lib/core/cambios.svelte.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import {
    agregarAPlaylist,
    anclarPlaylist,
    bibliotecaPistas,
    borrarPlaylist,
    duplicarPlaylist,
    encolarPlaylist,
    moverEnPlaylist,
    type PistaResumen,
    type PlaylistResumen,
    playlist,
    playlistPistas,
    quitarDePlaylist,
    reproducirPlaylist,
    vaciarPlaylist
  } from '#lib/core/ipc/index.ts';
  import { formatoTiempo, reproductor } from '#lib/core/reproductor.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import { esAparte } from '#lib/i18n/es-aparte.ts';
  import CabeceraPistas from '#lib/ui/biblioteca/CabeceraPistas.svelte';
  import FilaPista from '#lib/ui/biblioteca/FilaPista.svelte';
  import AccionesColeccion from '#lib/ui/AccionesColeccion.svelte';
  import { ambiente } from '#lib/ui/ambiente.ts';
  import DialogoConfirmar from '#lib/ui/DialogoConfirmar.svelte';
  import Icon from '#lib/ui/Icon.svelte';
  import type { Accion } from '#lib/ui/MenuAcciones.svelte';
  import DialogoInteligente from '#lib/ui/playlists/DialogoInteligente.svelte';
  import DialogoPlaylist from '#lib/ui/playlists/DialogoPlaylist.svelte';
  import Mosaico from '#lib/ui/playlists/Mosaico.svelte';

  const t = textos.playlists;
  const ti = esAparte.inteligentes;
  const id = $derived(Number(page.url.searchParams.get('id')));

  let datos = $state<PlaylistResumen | null | undefined>(undefined);
  let pistas = $state<PistaResumen[]>([]);
  let renombrando = $state(false);
  let editandoRegla = $state(false);
  let confirmandoBorrado = $state(false);
  let confirmandoVaciado = $state(false);
  let anadiendo = $state(false);
  let busqueda = $state('');
  let encontradas = $state<PistaResumen[]>([]);
  const enLista = $derived(new Set(pistas.map((p) => p.id)));
  let version = $state(0);

  $effect(() => {
    void version;
    void cambios.version;
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
      notificar.error(esAparte.comun.error);
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
      notificar.error(esAparte.comun.error);
    }
  }

  // "Añadir canciones" desde la propia playlist (`buscar_pistas_para_playlist`).
  let espera: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const q = busqueda.trim();
    clearTimeout(espera);
    if (!anadiendo || q === '') {
      encontradas = [];
      return;
    }
    espera = setTimeout(async () => {
      const r = await bibliotecaPistas(
        {
          texto: q,
          favoritas: false,
          sinVerificar: false,
          paraCantar: false,
          albumId: null,
          artistaId: null,
          orden: 'tituloAsc'
        },
        0,
        30
      ).catch(() => null);
      if (r && busqueda.trim() === q) encontradas = r.pistas;
    }, 200);
    return () => clearTimeout(espera);
  });

  async function anadir(p: PistaResumen) {
    try {
      await agregarAPlaylist(id, [p.id]);
      notificar.exito(t.anadida(datos?.nombre ?? ''));
      version += 1;
    } catch {
      notificar.error(esAparte.comun.error);
    }
  }

  async function encolar() {
    try {
      notificar.exito(textos.biblioteca.anadidasACola(await encolarPlaylist(id, false)));
    } catch {
      notificar.error(textos.biblioteca.colaFallo);
    }
  }

  async function duplicar() {
    try {
      const copia = await duplicarPlaylist(id);
      notificar.exito(t.duplicada(datos?.nombre ?? ''));
      await goto(`/playlists/ver?id=${copia}`);
    } catch {
      notificar.error(esAparte.comun.error);
    }
  }

  async function vaciar() {
    confirmandoVaciado = false;
    try {
      await vaciarPlaylist(id);
      notificar.exito(t.vaciada);
      version += 1;
    } catch {
      notificar.error(esAparte.comun.error);
    }
  }

  async function aleatorio() {
    if (pistas.length === 0) return;
    if (!reproductor.instantanea.aleatorio) void reproductor.alternarAleatorio();
    await reproducirPlaylist(id, Math.floor(Math.random() * pistas.length));
  }

  async function anclar() {
    if (!datos) return;
    try {
      await anclarPlaylist(id, !datos.anclada);
      version += 1;
    } catch {
      notificar.error(esAparte.comun.error);
    }
  }

  // Lo secundario, en el menú ···; lo que borra, al final y separado.
  const acciones = $derived.by<Accion[]>(() => {
    if (!datos) return [];
    const d = datos;
    const vacia = pistas.length === 0;
    return [
      { texto: t.encolar, icono: 'cola', accion: encolar, deshabilitada: vacia },
      ...(d.categoria === 'meGusta'
        ? []
        : [
            { texto: d.anclada ? t.desanclar : t.anclar, icono: 'anclar' as const, accion: anclar }
          ]),
      ...(d.editable
        ? [{ texto: t.renombrar, icono: 'editar' as const, accion: () => (renombrando = true) }]
        : []),
      ...(d.reglaInteligente
        ? [{ texto: ti.editar, icono: 'filtrar' as const, accion: () => (editandoRegla = true) }]
        : []),
      { texto: t.duplicar, icono: 'copiar', accion: duplicar },
      ...(d.editable && !vacia
        ? [
            {
              texto: t.vaciar,
              icono: 'borrar' as const,
              accion: () => (confirmandoVaciado = true),
              destructiva: true,
              separada: true
            }
          ]
        : []),
      ...(d.borrable
        ? [
            {
              texto: t.borrar,
              icono: 'borrar' as const,
              accion: () => (confirmandoBorrado = true),
              destructiva: true,
              separada: !(d.editable && !vacia)
            }
          ]
        : [])
    ];
  });

  function accionesDeFila(i: number, p: PistaResumen): Accion[] {
    if (!datos?.editable) return [];
    return [
      {
        texto: t.subir,
        icono: 'arriba',
        accion: () => mover(i, i - 1),
        deshabilitada: i === 0,
        separada: true
      },
      {
        texto: t.bajar,
        icono: 'abajo',
        accion: () => mover(i, i + 1),
        deshabilitada: i === pistas.length - 1
      },
      { texto: t.quitar, icono: 'cerrar', accion: () => quitar(p) }
    ];
  }

  async function ejecutarBorrado() {
    if (!datos) return;
    await borrarPlaylist(id);
    await goto('/playlists');
  }
</script>

<section class="detalle">
  <header class="franja" use:ambiente={pistas[0]?.id ?? null}>
    <button
      type="button"
      class="volver"
      onclick={() => {
        if (typeof window !== 'undefined' && window.history.length > 1) {
          window.history.back();
        } else {
          void goto('/playlists');
        }
      }}
      title={t.volver}
    >
      <Icon nombre="atras" tamano={18} />
      <span>{t.volver}</span>
    </button>
    {#if datos}
      <div class="cabecera">
        <div class="portada"><Mosaico pistas={datos.mosaico} tamano={320} /></div>
        <div class="datos">
          <span class="etiqueta">{datos.etiqueta}</span>
          <h1>{datos.nombre}</h1>
          {#if datos.descripcion}<p class="descripcion">{datos.descripcion}</p>{/if}
          <span class="sub">{t.resumen(datos.numPistas, formatoTiempo(datos.duracionSeg))}</span>
        </div>
      </div>
    {/if}
  </header>

  {#if datos === null}
    <p class="vacio">{t.noEncontrada}</p>
  {:else if datos}
    <AccionesColeccion
      vacia={pistas.length === 0}
      onreproducir={() => reproducirPlaylist(id, 0)}
      onaleatorio={aleatorio}
      {acciones}
    >
      {#if datos.editable}
        <button
          type="button"
          class="pildora"
          aria-pressed={anadiendo}
          onclick={() => (anadiendo = !anadiendo)}
        >
          <Icon nombre="mas" tamano={16} />{t.anadirCanciones}
        </button>
      {/if}
    </AccionesColeccion>

    {#if anadiendo}
      <section class="anadir" aria-label={t.anadirCanciones}>
        <input
          type="search"
          class="campo"
          placeholder={t.buscarParaAnadir}
          aria-label={t.buscarParaAnadir}
          bind:value={busqueda}
        />
        {#if encontradas.length > 0}
          <ul class="resultados">
            {#each encontradas as p (p.id)}
              <li>
                <span class="resultado">
                  <strong>{p.titulo}</strong>
                  <span class="sub">{p.artista} · {p.album}</span>
                </span>
                <button
                  type="button"
                  class="mini"
                  disabled={enLista.has(p.id)}
                  aria-label={enLista.has(p.id) ? t.yaEnLista : t.anadirA}
                  title={enLista.has(p.id) ? t.yaEnLista : t.anadirA}
                  onclick={() => anadir(p)}
                >
                  <Icon nombre={enLista.has(p.id) ? 'comprobado' : 'mas'} tamano={16} />
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    {/if}

    {#if pistas.length === 0}
      <p class="vacio">{t.vacia}</p>
    {:else}
      <CabeceraPistas contexto="playlist" />
      <ul class="pistas" aria-label={textos.biblioteca.lista}>
        {#each pistas as p, i (p.id)}
          <li>
            <FilaPista
              contexto="playlist"
              pista={p}
              numero={i + 1}
              sonando={reproductor.instantanea.pistaId === p.id}
              onreproducir={() => reproducirPlaylist(id, i)}
              extra={accionesDeFila(i, p)}
            />
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

    {#if confirmandoVaciado}
      <DialogoConfirmar
        abierto={confirmandoVaciado}
        titulo={t.confirmarVaciarTitulo}
        mensaje={t.confirmarVaciar(datos.nombre)}
        destructivo={true}
        textoConfirmar={t.vaciar}
        onconfirmar={vaciar}
        oncerrar={() => (confirmandoVaciado = false)}
      />
    {/if}

    {#if confirmandoBorrado && datos}
      <DialogoConfirmar
        abierto={confirmandoBorrado}
        titulo={t.borrar}
        mensaje={t.confirmarBorrar(datos.nombre)}
        destructivo={true}
        textoConfirmar={t.borrar}
        onconfirmar={ejecutarBorrado}
        oncerrar={() => (confirmandoBorrado = false)}
      />
    {/if}
  {/if}
</section>

<style>
  .detalle {
    --fondo-lienzo: var(--m3c-surface-container-low);
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
  }

  .franja {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
    margin: calc(-1 * var(--ns-espacio-2)) calc(-1 * var(--ns-espacio-5)) 0;
    padding: var(--ns-espacio-4) var(--ns-espacio-5) var(--ns-espacio-5);
    background: linear-gradient(
      180deg,
      color-mix(in srgb, var(--m3c-primary-container) 70%, var(--fondo-lienzo)) 0%,
      var(--fondo-lienzo) 100%
    );
    color: var(--m3c-on-surface);
  }

  .volver {
    display: inline-flex;
    align-self: flex-start;
    align-items: center;
    gap: var(--ns-espacio-2);
    padding: 0;
    border: none;
    background: none;
    color: var(--m3c-on-surface-variant);
    font: inherit;
    font-size: var(--ns-texto-sm);
    cursor: pointer;
    transition: color var(--ns-duracion-corta) var(--ns-curva);
  }

  .volver:hover {
    color: var(--m3c-on-surface);
  }

  .cabecera {
    display: flex;
    align-items: flex-end;
    gap: var(--ns-espacio-5);
  }

  .portada {
    flex: 0 0 14rem;
    overflow: hidden;
    border-radius: var(--ns-radio-md);
    box-shadow: 0 12px 32px var(--m3c-shadow);
  }

  .datos {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    min-width: 0;
  }

  .etiqueta {
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  h1 {
    margin: 0;
    font-size: clamp(var(--ns-texto-2xl), 4vw, var(--ns-texto-3xl));
    line-height: 1.05;
    overflow-wrap: anywhere;
  }

  .sub {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .descripcion {
    margin: 0;
    font-size: var(--ns-texto-sm);
  }

  .pistas {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .pistas li {
    height: 3.5rem;
  }

  .anadir {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    padding: var(--ns-espacio-4);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container);
  }

  .campo {
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
    font: inherit;
  }

  .resultados {
    display: flex;
    flex-direction: column;
    max-height: 18rem;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    list-style: none;
  }

  .resultados li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-2) var(--ns-espacio-1);
  }

  .resultado {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .resultado strong,
  .resultado .sub {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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
