<!--
  @component
  Una sesión del DJ (F6.1.6): cómo entendió el DJ el pedido, sus números, sus
  canciones con la transición que trae cada una y, si está sonando, por dónde va
  y con qué técnica mezcla. Sus acciones: escuchar, otra parecida, guardar como
  playlist, descartar y valorar la canción que suena.
-->
<script lang="ts">
  import { onDestroy } from 'svelte';
  import {
    alCambiarDj,
    djDescartar,
    djGuardar,
    djReproducir,
    djRegenerar,
    djSesion,
    djValorar,
    type VistaSesionDj
  } from '$core/ipc/dj';
  import { formatoTiempo, reproductor } from '$core/reproductor.svelte';
  import { textosDj } from '$lib/i18n/dj';
  import FormaDeOnda from '$ui/FormaDeOnda.svelte';
  import Icon from '$ui/Icon.svelte';

  interface Props {
    sesionId: number;
    /** Otra sesión pasó a ser la que se ve (al regenerar), o ninguna (al descartar). */
    oncambio: (sesionId: number | null) => void;
  }

  let { sesionId, oncambio }: Props = $props();
  const t = textosDj.sesion;

  let sesion = $state<VistaSesionDj | null>(null);
  let aviso = $state<string | null>(null);

  function cargar(id: number) {
    void djSesion(id).then((s) => {
      if (id === sesionId) sesion = s;
    });
  }

  $effect(() => {
    aviso = null;
    cargar(sesionId);
  });

  const dejar = alCambiarDj((id) => {
    if (id === sesionId) cargar(id);
  });
  onDestroy(() => void dejar.then((f) => f()));

  const dj = $derived(reproductor.instantanea.dj);
  const sonando = $derived(dj?.sesionId === sesionId ? dj : null);
  const actual = $derived(sesion?.pistas.find((p) => p.posicion === sonando?.posicion) ?? null);

  function calidad(score: unknown): keyof typeof t.transicion {
    const s = typeof score === 'number' ? score : 0.5;
    return s >= 0.7 ? 'limpia' : s >= 0.5 ? 'aceptable' : 'forzada';
  }

  async function regenerar() {
    const r = await djRegenerar(sesionId);
    oncambio(r.sinCandidatas ? null : r.sesionId);
  }

  async function descartar() {
    await djDescartar(sesionId);
    oncambio(null);
  }

  async function guardar() {
    await djGuardar(sesionId, '');
    aviso = t.guardada;
  }

  async function valorar(gusta: boolean) {
    if (!actual) return;
    await djValorar(sesionId, actual.posicion, actual.pistaId, gusta);
    aviso = t.valorada;
  }
</script>

{#if sesion}
  <section class="sesion" aria-labelledby="t-sesion">
    <header>
      <span class="estado">
        {sonando
          ? reproductor.instantanea.estado === 'pausado'
            ? t.enPausa
            : t.sonando
          : (textosDj.historial.estados[sesion.estado] ?? sesion.estado)}
      </span>
      <h2 id="t-sesion">{sesion.peticion}</h2>
      {#if sesion.resumen}<p class="resumen">{sesion.resumen}</p>{/if}
      {#each sesion.notas as n (n)}<p class="nota">{n}</p>{/each}
      <p class="cifras">
        {t.resumen(
          sesion.pistas.length,
          formatoTiempo(sesion.duracionSeg),
          sesion.artistasDistintos
        )}
        · {t.transiciones(sesion.transicionesBuenas, sesion.transicionesTotal)}
      </p>
      {#if sesion.estado === 'construyendo'}<p class="nota">{t.construyendo}</p>{/if}
      {#if sesion.sinAnalisis}
        <p class="sin-analisis"><Icon nombre="informacion" tamano={16} />{t.sinAnalisis}</p>
      {/if}
    </header>

    {#if sonando}
      <div class="pista-sonando">
        {#if reproductor.picos.length > 0}
          <FormaDeOnda
            picos={reproductor.picos}
            posicion={reproductor.posicion}
            duracion={reproductor.instantanea.duracionSeg}
            entradaSeg={sonando.entradaSeg}
            salidaSeg={sonando.salidaSeg}
          />
        {/if}
        <p class="puntos-dj">
          <span class="punto-entrada">{t.entrada(formatoTiempo(sonando.entradaSeg))}</span>
          {#if sonando.salidaSeg !== null}
            <span>·</span>
            <span class="punto-salida">{t.salida(formatoTiempo(sonando.salidaSeg))}</span>
          {/if}
        </p>
      </div>
    {/if}

    {#if sonando?.mezcla}
      <div class="mezcla" role="status">
        <span>{t.mezclando(t.tecnicas[sonando.mezcla.tecnica], sonando.mezcla.progreso)}</span>
        <span class="barra"
          ><span style:width={`${Math.round(sonando.mezcla.progreso * 100)}%`}></span></span
        >
      </div>
    {/if}

    <div class="botones">
      {#if !sonando}
        <button type="button" class="boton relleno" onclick={() => djReproducir(sesionId, 0)}>
          <Icon nombre="reproducir" tamano={16} />{t.escuchar}
        </button>
      {/if}
      {#if actual}
        <button type="button" class="boton" onclick={() => valorar(true)}>
          <Icon nombre="favorito" tamano={16} />{t.meGusta}
        </button>
        <button type="button" class="boton" onclick={() => valorar(false)}>
          <Icon nombre="noDisponible" tamano={16} />{t.noMeGusta}
        </button>
      {/if}
      <button type="button" class="boton" onclick={regenerar}>
        <Icon nombre="reintentar" tamano={16} />{t.regenerar}
      </button>
      <button type="button" class="boton" onclick={guardar} disabled={sesion.pistas.length === 0}>
        <Icon nombre="playlists" tamano={16} />{t.guardar}
      </button>
      <button type="button" class="boton" onclick={descartar}>
        <Icon nombre="cerrar" tamano={16} />{t.descartar}
      </button>
    </div>
    {#if aviso}<p class="nota" role="status">{aviso}</p>{/if}

    <h3>{t.pistas}</h3>
    <ol class="pistas">
      {#each sesion.pistas as p, k (p.posicion)}
        {#if k > 0}
          {@const c = calidad(p.transicion.score)}
          <li class="transicion {c}" title={p.razones.join(' · ')}>
            <span class="punto"></span>{t.transicion[c]}
          </li>
        {/if}
        <li>
          <button
            type="button"
            class="pista"
            class:actual={sonando?.posicion === p.posicion}
            aria-current={sonando?.posicion === p.posicion ? 'true' : undefined}
            aria-label={t.tocarDesde(p.titulo)}
            onclick={() => djReproducir(sesionId, p.posicion)}
          >
            <span class="numero">{p.posicion + 1}</span>
            <span class="datos">
              <strong>{p.titulo}</strong>
              <small>{p.artista}</small>
            </span>
            <span class="duracion">{formatoTiempo(p.duracionSeg)}</span>
          </button>
        </li>
      {/each}
    </ol>
  </section>
{/if}

<style>
  .sesion {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-low);
  }

  header {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
  }

  .estado {
    color: var(--m3c-primary);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    text-transform: uppercase;
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
  }

  h3 {
    margin: var(--ns-espacio-2) 0 0;
    font-size: var(--ns-texto-sm);
  }

  p {
    margin: 0;
  }

  .resumen {
    font-size: var(--ns-texto-sm);
  }

  .nota,
  .cifras {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .sin-analisis {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .mezcla {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    font-size: var(--ns-texto-sm);
    font-weight: 600;
  }

  .pista-sonando {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
  }

  .puntos-dj {
    display: flex;
    gap: var(--ns-espacio-2);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-variant-numeric: tabular-nums;
  }

  .punto-entrada {
    color: var(--m3c-tertiary);
  }

  .punto-salida {
    color: var(--m3c-secondary);
  }

  .barra {
    height: 0.25rem;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
    overflow: hidden;
  }

  .barra span {
    display: block;
    height: 100%;
    background: var(--m3c-primary);
  }

  .botones {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ns-espacio-2);
  }

  .boton {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-1);
    height: 2.5rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-sm);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    cursor: pointer;
  }

  .boton.relleno {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
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

  .pista {
    display: grid;
    grid-template-columns: 2rem minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--ns-espacio-3);
    width: 100%;
    padding: var(--ns-espacio-2);
    border: none;
    border-radius: var(--ns-radio-sm);
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .pista:hover {
    background: var(--m3c-surface-container);
  }

  .pista.actual {
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
  }

  .numero,
  .duracion {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-variant-numeric: tabular-nums;
  }

  .datos {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .datos strong,
  .datos small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .datos small {
    color: var(--m3c-on-surface-variant);
  }

  .transicion {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    padding: 0 var(--ns-espacio-2) 0 var(--ns-espacio-6);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .punto {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-outline);
  }

  .limpia .punto {
    background: var(--m3c-primary);
  }

  .forzada .punto {
    background: var(--m3c-error);
  }
</style>
