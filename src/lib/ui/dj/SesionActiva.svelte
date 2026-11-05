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
  } from '#lib/core/ipc/dj.ts';
  import { urlPortada } from '#lib/core/ipc/index.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { formatoTiempo, reproductor } from '#lib/core/reproductor.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import { textosDj } from '#lib/i18n/dj.ts';
  import FormaDeOnda from '#lib/ui/FormaDeOnda.svelte';
  import Icon from '#lib/ui/Icon.svelte';
  import MenuAcciones from '#lib/ui/MenuAcciones.svelte';
  import Mosaico from '#lib/ui/playlists/Mosaico.svelte';

  interface Props {
    sesionId: number;
    /** Otra sesión pasó a ser la que se ve (al regenerar), o ninguna (al descartar). */
    oncambio: (sesionId: number | null) => void;
  }

  let { sesionId, oncambio }: Props = $props();
  const t = textosDj.sesion;

  let sesion = $state<VistaSesionDj | null>(null);

  function cargar(id: number) {
    void djSesion(id).then((s) => {
      if (id === sesionId) sesion = s;
    });
  }

  $effect(() => {
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
    notificar.exito(t.guardada);
  }

  async function valorar(gusta: boolean) {
    if (!actual) return;
    await djValorar(sesionId, actual.posicion, actual.pistaId, gusta);
    notificar.informacion(t.valorada);
  }

  function reproducirOPausar() {
    if (sonando) void reproductor.pausarReanudar();
    else void djReproducir(sesionId, 0);
  }

  const enPausa = $derived(!sonando || reproductor.instantanea.estado === 'pausado');
</script>

{#if sesion}
  <section class="sesion" aria-labelledby="t-sesion">
    <header class="cabecera">
      <div class="portada">
        <Mosaico pistas={sesion.pistas.map((p) => p.pistaId)} tamano={320} />
      </div>
      <div class="datos">
        <span class="estado">
          {sonando
            ? enPausa
              ? t.enPausa
              : t.sonando
            : (textosDj.historial.estados[sesion.estado] ?? sesion.estado)}
        </span>
        <h2 id="t-sesion">{sesion.peticion}</h2>
        {#if sesion.pide.length + sesion.evita.length === 0}
          <p class="nota">{t.general}</p>
        {:else}
          <ul class="lectura" aria-label={t.entendi}>
            {#each sesion.pide as c (c)}
              <li class="concepto">{t.conceptos[c] ?? c.replaceAll('_', ' ')}</li>
            {/each}
            {#if t.curvas[sesion.curva]}
              <li class="concepto curva">{t.curvas[sesion.curva]}</li>
            {/if}
            {#each sesion.evita as c (c)}
              <li class="concepto evitado">
                {t.evitare}
                {t.conceptos[c] ?? c.replaceAll('_', ' ')}
              </li>
            {/each}
          </ul>
        {/if}
        <p class="cifras">
          {t.resumen(
            sesion.pistas.length,
            formatoTiempo(sesion.duracionSeg),
            sesion.artistasDistintos
          )}
          · {t.transiciones(sesion.transicionesBuenas, sesion.transicionesTotal)}
        </p>
      </div>
    </header>

    {#if sesion.estado === 'construyendo'}<p class="nota">{t.construyendo}</p>{/if}
    {#if sesion.sinAnalisis}
      <p class="sin-analisis"><Icon nombre="informacion" tamano={16} />{t.sinAnalisis}</p>
    {/if}

    <div class="acciones">
      <button
        type="button"
        class="reproducir"
        aria-label={enPausa ? t.escuchar : textos.reproductor.pausar}
        title={enPausa ? t.escuchar : textos.reproductor.pausar}
        onclick={reproducirOPausar}
      >
        <Icon nombre={enPausa ? 'reproducir' : 'pausa'} tamano={26} />
      </button>
      {#if actual}
        <button
          type="button"
          class="redondo"
          aria-label={t.meGusta}
          title={t.meGusta}
          onclick={() => valorar(true)}
        >
          <Icon nombre="favorito" tamano={22} />
        </button>
        <button
          type="button"
          class="redondo"
          aria-label={t.noMeGusta}
          title={t.noMeGusta}
          onclick={() => valorar(false)}
        >
          <Icon nombre="noDisponible" tamano={22} />
        </button>
      {/if}
      <button type="button" class="pildora" onclick={regenerar}>
        <Icon nombre="reintentar" tamano={16} />{t.regenerar}
      </button>
      <button type="button" class="pildora" onclick={guardar} disabled={sesion.pistas.length === 0}>
        <Icon nombre="playlists" tamano={16} />{t.guardar}
      </button>
      <MenuAcciones
        etiqueta={textos.biblioteca.masAcciones}
        acciones={[{ texto: t.descartar, icono: 'cerrar', accion: descartar, destructiva: true }]}
      />
    </div>

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
          {#if sonando.mezcla}
            <span>·</span>
            <span class="mezclando" role="status">
              {t.mezclando(t.tecnicas[sonando.mezcla.tecnica], sonando.mezcla.progreso)}
            </span>
          {/if}
        </p>
      </div>
    {/if}

    <h3>{t.pistas}</h3>
    <ol class="pistas">
      {#each sesion.pistas as p, k (p.posicion)}
        {@const c = k > 0 ? calidad(p.transicion.score) : null}
        <li>
          <button
            type="button"
            class="pista"
            class:actual={sonando?.posicion === p.posicion}
            aria-current={sonando?.posicion === p.posicion ? 'true' : undefined}
            aria-label={t.tocarDesde(p.titulo)}
            onclick={() => djReproducir(sesionId, p.posicion)}
          >
            <span class="numero">
              {#if sonando?.posicion === p.posicion}
                <Icon nombre="ecualizador" tamano={16} />
              {:else}
                {p.posicion + 1}
              {/if}
            </span>
            <img class="mini" src={urlPortada('pista', p.pistaId, 64)} alt="" loading="lazy" />
            <span class="datos-pista">
              <strong>{p.titulo}</strong>
              <small>{p.artista}</small>
            </span>
            {#if c}
              <span class="transicion {c}" title={t.transicion[c]}>
                <span class="punto"></span>{t.transicion[c]}
              </span>
            {:else}
              <span></span>
            {/if}
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
    gap: var(--ns-espacio-4);
    padding: var(--ns-espacio-5);
    border-radius: var(--ns-radio-xl);
    background: linear-gradient(
      180deg,
      color-mix(in srgb, var(--m3c-primary-container) 40%, var(--m3c-surface-container)) 0%,
      var(--m3c-surface-container-low) 22rem
    );
  }

  .cabecera {
    display: flex;
    align-items: flex-end;
    gap: var(--ns-espacio-5);
  }

  .portada {
    flex: 0 0 10rem;
    overflow: hidden;
    border-radius: var(--ns-radio-md);
    box-shadow: 0 12px 28px var(--m3c-shadow);
  }

  .datos {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    min-width: 0;
  }

  .estado {
    color: var(--m3c-primary);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  h2 {
    margin: 0;
    font-size: clamp(var(--ns-texto-xl), 3vw, var(--ns-texto-2xl));
    line-height: 1.1;
    overflow-wrap: anywhere;
  }

  h3 {
    margin: 0;
    font-size: var(--ns-texto-md);
  }

  p {
    margin: 0;
  }

  .lectura {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ns-espacio-1);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .concepto {
    padding: var(--ns-espacio-1) var(--ns-espacio-3);
    border-radius: var(--ns-radio-pleno);
    background: color-mix(in srgb, var(--m3c-primary) 16%, transparent);
    color: var(--m3c-on-surface);
    font-size: var(--ns-texto-xs);
    font-weight: 600;
  }

  .concepto.curva {
    background: var(--m3c-surface-container-highest);
  }

  .concepto.evitado {
    background: color-mix(in srgb, var(--m3c-error) 16%, transparent);
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
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .acciones {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--ns-espacio-3);
  }

  .reproducir {
    display: grid;
    place-items: center;
    width: 3.5rem;
    height: 3.5rem;
    padding: 0;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
    box-shadow: 0 6px 18px var(--m3c-shadow);
    cursor: pointer;
    transition: transform var(--ns-duracion-corta) var(--ns-curva);
  }

  .reproducir:hover {
    transform: scale(1.05);
  }

  .redondo {
    display: grid;
    place-items: center;
    width: 2.75rem;
    height: 2.75rem;
    padding: 0;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
  }

  .redondo:hover {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
  }

  .pildora {
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
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    cursor: pointer;
  }

  .pildora:hover:not(:disabled) {
    background: var(--m3c-surface-container-highest);
  }

  .pildora:disabled {
    opacity: 0.38;
    cursor: default;
  }

  .pista-sonando {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
  }

  .puntos-dj {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ns-espacio-2);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .punto-entrada,
  .mezclando {
    color: var(--m3c-primary);
    font-weight: 600;
  }

  .punto-salida {
    color: var(--m3c-tertiary);
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
    grid-template-columns: 2rem 2.5rem minmax(0, 1fr) auto 3.25rem;
    align-items: center;
    gap: var(--ns-espacio-3);
    width: 100%;
    min-height: 3.5rem;
    padding: 0 var(--ns-espacio-3);
    border: none;
    border-radius: var(--ns-radio-sm);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .pista:hover {
    background: var(--m3c-surface-container);
  }

  .pista.actual {
    background: color-mix(in srgb, var(--m3c-primary) 12%, transparent);
  }

  .pista.actual strong {
    color: var(--m3c-primary);
  }

  .numero,
  .duracion {
    display: flex;
    justify-content: center;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
    font-variant-numeric: tabular-nums;
  }

  .numero {
    color: var(--m3c-on-surface-variant);
  }

  .pista.actual .numero {
    color: var(--m3c-primary);
  }

  .duracion {
    justify-content: flex-end;
    font-size: var(--ns-texto-xs);
  }

  .mini {
    width: 2.5rem;
    height: 2.5rem;
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
    object-fit: cover;
  }

  .datos-pista {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    min-width: 0;
  }

  .datos-pista strong,
  .datos-pista small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .datos-pista strong {
    font-size: var(--ns-texto-sm);
    font-weight: 600;
  }

  .datos-pista small {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .transicion {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    white-space: nowrap;
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

  @container carcasa (max-width: 60rem) {
    .transicion {
      display: none;
    }
  }
</style>
