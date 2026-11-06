<!--
  @component
  Tu música: la identidad musical
  con la foto y el nombre, sus fichas y Reproducir tu esencia; Tu actividad; el
  mood del día y los días activos del mes; y Lo que más has querido, con los tops
  de canciones, álbumes y artistas.
-->
<script lang="ts" module>
  // El periodo elegido sobrevive a salir y volver a la vista.
  let ultimoPeriodo = 'todo';
</script>

<script lang="ts">
  import { untrack } from 'svelte';
  import { cambios } from '#lib/core/cambios.svelte.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { aparienciaActual } from '#lib/core/apariencia.svelte.ts';
  import { duracionDetallada } from '#lib/core/formato.ts';
  import {
    type Perfil,
    perfil,
    perfilCambiarFoto,
    recordado,
    urlFotoPerfil,
    urlPortada
  } from '#lib/core/ipc/index.ts';
  import {
    exportarResumenEscucha,
    type RadarAnimos,
    type ResumenEscucha,
    resumenEscucha
  } from '#lib/core/ipc/aparte.ts';
  import { reproductor } from '#lib/core/reproductor.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import { textosAparte } from '#lib/i18n/aparte.ts';
  import Icon from '#lib/ui/Icon.svelte';

  const t = textos.tuMusica;
  const tr = textosAparte.resumenEscucha;
  let datos = $state<Perfil | null>(recordado<Perfil>('perfil') ?? null);
  let periodoActivo = $state<string>(ultimoPeriodo);
  let resumen = $state<ResumenEscucha | null>(
    recordado<ResumenEscucha>('resumen_escucha', { periodo: ultimoPeriodo }) ?? null
  );
  let exportando = $state(false);
  let exportada = $state(false);
  let sinFoto = $state(false);
  let versionFoto = $state(Date.now());

  async function cambiarFoto() {
    try {
      if (await perfilCambiarFoto()) {
        sinFoto = false;
        versionFoto = Date.now();
      }
    } catch {
      notificar.error(t.fotoInvalida);
    }
  }

  function cargarResumen(periodo: string) {
    periodoActivo = periodo;
    ultimoPeriodo = periodo;
    exportada = false;
    void resumenEscucha(periodo).then((r) => (resumen = r));
  }

  function cargar() {
    void perfil().then((p) => (datos = p));
    cargarResumen(periodoActivo);
  }
  $effect(() => {
    void cambios.version;
    void perfil().then((p) => (datos = p));
    const periodo = untrack(() => periodoActivo);
    void resumenEscucha(periodo).then((r) => (resumen = r));
  });

  async function exportarTarjeta() {
    if (exportando) return;
    exportando = true;
    exportada = false;
    try {
      exportada = await exportarResumenEscucha(periodoActivo);
    } finally {
      exportando = false;
    }
  }

  function nombrePeriodo(p: string): string {
    if (p === 'todo') return tr.todo;
    if (p.length === 7 && p[4] === '-') {
      const m = tr.meses[p.slice(5)] ?? p.slice(5);
      return `${m} ${p.slice(0, 4)}`;
    }
    return p;
  }

  function puntosPoligonoRadar(r: RadarAnimos): string {
    const vals = [r.energia, r.bailable, r.alegre, r.calma, r.nocturna, r.melancolica];
    const cx = 110;
    const cy = 110;
    const radio = 76;
    return vals
      .map((v, i) => {
        const ang = -Math.PI / 2 + (i * Math.PI) / 3;
        const dist = radio * Math.min(1, Math.max(0.08, v));
        return `${(cx + dist * Math.cos(ang)).toFixed(1)},${(cy + dist * Math.sin(ang)).toFixed(1)}`;
      })
      .join(' ');
  }

  function puntosGuiaRadar(escala: number): string {
    const cx = 110;
    const cy = 110;
    const radio = 76 * escala;
    return [0, 1, 2, 3, 4, 5]
      .map((i) => {
        const ang = -Math.PI / 2 + (i * Math.PI) / 3;
        return `${(cx + radio * Math.cos(ang)).toFixed(1)},${(cy + radio * Math.sin(ang)).toFixed(1)}`;
      })
      .join(' ');
  }

  function nivelMapa(n: number, max: number): string {
    if (n === 0 || max === 0) return 'nada';
    const r = n / max;
    if (r <= 0.33) return 'poco';
    if (r <= 0.66) return 'medio';
    return 'mucho';
  }

  const maxPorDia = $derived(resumen ? Math.max(0, ...resumen.porDia) : 0);

  const MESES = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12'];
  const conteoMes = $derived(
    new Map((resumen?.porMes ?? []).map((c) => [c.mes, c.reproducciones]))
  );
  const maxPorMes = $derived(Math.max(0, ...conteoMes.values()));
  /** Los años de la rejilla: el elegido, o del más reciente al primero con escuchas. */
  const aniosMeses = $derived.by(() => {
    const p = resumen?.periodo ?? 'todo';
    if (/^\d{4}$/.test(p)) return [p];
    const anios = (resumen?.porMes ?? []).map((c) => Number(c.mes.slice(0, 4)));
    if (anios.length === 0) return [String(new Date().getFullYear())];
    const lista: string[] = [];
    for (let a = Math.max(...anios); a >= Math.min(...anios); a--) lista.push(String(a));
    return lista;
  });

  /** Huecos antes del día 1 para que caiga en su día de la semana (lunes primero). */
  const huecosMes = $derived.by(() => {
    const p = resumen?.periodo ?? '';
    if (p.length !== 7) return 0;
    const primero = new Date(Number(p.slice(0, 4)), Number(p.slice(5)) - 1, 1);
    return (primero.getDay() + 6) % 7;
  });

  const nombre = $derived(aparienciaActual.actual.nombreUsuario ?? t.anonimo);

  // El nombre se cambia aquí, tocándolo, además de en Ajustes: es la misma
  // preferencia, así que Ajustes y el saludo de Inicio lo ven al momento.
  let editandoNombre = $state(false);
  let nombreNuevo = $state('');

  async function guardarNombre() {
    if (!editandoNombre) return;
    editandoNombre = false;
    const limpio = nombreNuevo.trim();
    if (limpio === (aparienciaActual.actual.nombreUsuario ?? '')) return;
    await aparienciaActual.cambiar('nombreUsuario', limpio || null).catch(() => {
      notificar.error(textosAparte.comun.error);
    });
  }

  function enfocar(nodo: HTMLInputElement) {
    nodo.focus();
    nodo.select();
  }
  const diasActivos = $derived(datos?.diasDelMes.filter((n) => n > 0).length ?? 0);

  function hora(h: number): string {
    return new Date(2000, 0, 1, h).toLocaleTimeString('es', { hour: 'numeric', minute: '2-digit' });
  }

  function nivel(n: number): string {
    if (n === 0) return 'nada';
    if (n <= 5) return 'poco';
    if (n <= 15) return 'medio';
    return 'mucho';
  }
</script>

<section class="perfil">
  <header class="identidad">
    <button
      type="button"
      class="foto boton-foto"
      title={textos.ajustes.cambiarFoto}
      aria-label={textos.ajustes.cambiarFoto}
      onclick={cambiarFoto}
    >
      {#if !sinFoto}
        <img src={urlFotoPerfil(versionFoto)} alt="" onerror={() => (sinFoto = true)} />
      {:else}
        <Icon nombre="artista" tamano={48} />
      {/if}
      <span class="velo-foto" aria-hidden="true">
        <Icon nombre="editar" tamano={22} />
      </span>
    </button>
    <div class="datos">
      <span class="etiqueta">{t.identidad}</span>
      {#if editandoNombre}
        <input
          class="nombre-campo"
          aria-label={t.cambiarNombre}
          placeholder={t.nombreMarcador}
          maxlength="40"
          bind:value={nombreNuevo}
          use:enfocar
          onkeydown={(e) => {
            if (e.key === 'Enter') void guardarNombre();
            if (e.key === 'Escape') {
              e.stopPropagation();
              editandoNombre = false;
            }
          }}
          onblur={() => void guardarNombre()}
        />
      {:else}
        <h1>
          <button
            type="button"
            class="nombre"
            title={t.cambiarNombre}
            onclick={() => {
              nombreNuevo = aparienciaActual.actual.nombreUsuario ?? '';
              editandoNombre = true;
            }}
          >
            {nombre}<span class="lapiz" aria-hidden="true"
              ><Icon nombre="editar" tamano={22} /></span
            >
          </button>
        </h1>
      {/if}
      {#if datos}
        <p>{t.resumen(datos.reproducciones, datos.pistasDistintas, datos.pistasEnBiblioteca)}</p>
        <div class="fichas">
          {#if datos.anioFavorito}<span class="ficha acento"
              >{t.anioFavorito(datos.anioFavorito)}</span
            >{/if}
          {#if datos.horaPico !== null}<span class="ficha">{t.horaPico(hora(datos.horaPico))}</span
            >{/if}
          <span class="ficha">{t.diasActivos(diasActivos)}</span>
        </div>
        <div class="botones">
          <button
            type="button"
            class="boton relleno"
            disabled={datos.topCanciones.length === 0}
            onclick={() =>
              reproductor.reproducirPistas(datos?.topCanciones.map((e) => e.pista.id) ?? [])}
          >
            <Icon nombre="reproducir" tamano={16} />{t.esencia}
          </button>
          <button type="button" class="boton" onclick={cargar}>
            <Icon nombre="reintentar" tamano={16} />{t.actualizar}
          </button>
        </div>
      {/if}
    </div>
  </header>

  {#if datos && datos.reproducciones === 0}
    <p class="vacio">{t.vacio}</p>
  {:else if datos}
    <h2>{t.actividad}</h2>
    <p class="sub">{t.actividadSub}</p>
    <ul class="cifras">
      <li>
        <a class="cifra-enlace" href="/biblioteca?vista=pistas">
          <span>{t.escuchadas}</span><strong>{datos.pistasDistintas.toLocaleString('es')}</strong
          ><Icon nombre="cancion" tamano={16} />
        </a>
      </li>
      <li>
        <a class="cifra-enlace" href="/biblioteca?vista=artistas">
          <span>{t.artistas}</span><strong>{datos.artistasDistintos.toLocaleString('es')}</strong
          ><Icon nombre="artista" tamano={16} />
        </a>
      </li>
      <li>
        <a class="cifra-enlace" href="/biblioteca?vista=albumes">
          <span>{t.albumes}</span><strong>{datos.albumesDistintos.toLocaleString('es')}</strong
          ><Icon nombre="album" tamano={16} />
        </a>
      </li>
      <li>
        <div class="cifra-enlace estatica">
          <span>{t.tiempo}</span><strong
            >{duracionDetallada(datos.segundosEscuchados).split(' ').slice(0, 2).join(' ')}</strong
          ><Icon nombre="reloj" tamano={16} />
        </div>
      </li>
    </ul>

    <div class="dos">
      <article class="tarjeta">
        <span class="etiqueta">{t.animo}</span>
        {#if datos.artistasHoy[0]}
          <h3>{datos.artistasHoy[0].nombre}</h3>
          <p class="sub">{t.escuchasHoy(datos.escuchasHoy)}</p>
          <div class="fichas">
            {#each datos.artistasHoy as a (a.id)}
              <a class="ficha" href={`/biblioteca/artista?id=${a.id}`}>{a.nombre} · {a.escuchas}</a>
            {/each}
          </div>
        {:else}
          <p class="sub">{t.sinEscuchasHoy}</p>
        {/if}
      </article>

      <article class="tarjeta">
        <span class="etiqueta">{t.mes}</span>
        <h3>{t.diasActivos(diasActivos)}</h3>
        <ol class="calendario">
          {#each datos.diasDelMes as n, d (d)}
            <li class="dia {nivel(n)}" title={t.dia(d + 1, n)} aria-label={t.dia(d + 1, n)}></li>
          {/each}
        </ol>
        <div class="leyenda">
          {#each ['nada', 'poco', 'medio', 'mucho'] as const as k (k)}
            <span><i class="dia {k}"></i>{t.leyenda[k]}</span>
          {/each}
        </div>
      </article>
    </div>

    <h2>{t.querido}</h2>
    <p class="sub">{t.queridoSub}</p>
    <div class="tres">
      <article class="tarjeta">
        <h3 class="titulo-top">{t.topCanciones}</h3>
        <ol class="top">
          {#each datos.topCanciones as e, k (e.pista.id)}
            <li>
              <button
                type="button"
                class="fila"
                onclick={() =>
                  reproductor.reproducirPistas(datos?.topCanciones.map((x) => x.pista.id) ?? [], k)}
              >
                <span class="n">{String(k + 1).padStart(2, '0')}</span>
                <span class="img">
                  {#if e.pista.tienePortada}
                    <img src={urlPortada('pista', e.pista.id, 64)} alt="" />
                  {:else}
                    <Icon nombre="cancion" tamano={18} />
                  {/if}
                </span>
                <span class="texto"
                  ><strong>{e.pista.titulo}</strong><span class="sub"
                    >{e.pista.artista} · {e.pista.album}</span
                  ></span
                >
              </button>
            </li>
          {/each}
        </ol>
      </article>
      <article class="tarjeta">
        <h3 class="titulo-top">{t.topAlbumes}</h3>
        <ol class="top">
          {#each datos.topAlbumes as a, k (a.id)}
            <li>
              <a class="fila" href={`/biblioteca/album?id=${a.id}`}>
                <span class="n">{String(k + 1).padStart(2, '0')}</span>
                <span class="img">
                  {#if a.tienePortada}
                    <img src={urlPortada('album', a.id, 64)} alt="" />
                  {:else}
                    <Icon nombre="album" tamano={18} />
                  {/if}
                </span>
                <span class="texto"
                  ><strong>{a.titulo}</strong><span class="sub">{a.artista}</span></span
                >
                <Icon nombre="derecha" tamano={16} />
              </a>
            </li>
          {/each}
        </ol>
      </article>
      <article class="tarjeta">
        <h3 class="titulo-top">{t.topArtistas}</h3>
        <ol class="top">
          {#each datos.topArtistas as a, k (a.id)}
            <li>
              <a class="fila" href={`/biblioteca/artista?id=${a.id}`}>
                <span class="n">{String(k + 1).padStart(2, '0')}</span>
                <span class="img redonda">
                  {#if a.tieneImagen}
                    <img src={urlPortada('artista', a.id, 64)} alt="" />
                  {:else}
                    <Icon nombre="artista" tamano={18} />
                  {/if}
                </span>
                <span class="texto"><strong>{a.nombre}</strong></span>
                <Icon nombre="derecha" tamano={16} />
              </a>
            </li>
          {/each}
        </ol>
      </article>
    </div>

    {#if resumen}
      <div class="cabecera-resumen">
        <div>
          <h2>{tr.titulo}</h2>
          <p class="sub">
            {tr.sub} · {tr.reproduccionesPeriodo(resumen.reproducciones)} · {duracionDetallada(
              resumen.segundosEscuchados
            )
              .split(' ')
              .slice(0, 2)
              .join(' ')}
          </p>
        </div>
        <button
          type="button"
          class="boton"
          disabled={exportando || resumen.reproducciones === 0}
          onclick={exportarTarjeta}
        >
          <Icon nombre="carpeta" tamano={16} />
          {exportando ? tr.exportando : exportada ? tr.exportada : tr.exportar}
        </button>
      </div>

      <div class="fichas">
        {#each resumen.periodosDisponibles as p (p)}
          <button
            type="button"
            class="chip-periodo"
            class:activo={resumen.periodo === p}
            onclick={() => cargarResumen(p)}
          >
            {nombrePeriodo(p)}
          </button>
        {/each}
      </div>

      <div class="dos">
        <article class="tarjeta">
          <span class="etiqueta">{tr.radarTitulo}</span>
          <p class="sub">{tr.radarSub}</p>
          <svg class="radar-svg" viewBox="-55 -10 330 240" aria-label={tr.radarTitulo}>
            <polygon points={puntosGuiaRadar(1)} class="guia-ext" />
            <polygon points={puntosGuiaRadar(0.5)} class="guia-int" />
            <polygon points={puntosPoligonoRadar(resumen.radar)} class="area-radar" />
            <text x="110" y="18" text-anchor="middle">{tr.ejes.energia}</text>
            <text x="184" y="68" text-anchor="start">{tr.ejes.bailable}</text>
            <text x="184" y="158" text-anchor="start">{tr.ejes.alegre}</text>
            <text x="110" y="210" text-anchor="middle">{tr.ejes.calma}</text>
            <text x="36" y="158" text-anchor="end">{tr.ejes.nocturna}</text>
            <text x="36" y="68" text-anchor="end">{tr.ejes.melancolica}</text>
          </svg>
        </article>

        <article class="tarjeta">
          {#if resumen.porDia.length > 0}
            <!-- Un mes es un calendario: el mapa de días por horas quedaba casi
                 vacío y no decía qué días se escuchó. -->
            <span class="etiqueta">{tr.calendarioTitulo}</span>
            <p class="sub">{tr.calendarioSub}</p>
            <div class="mes-calendario">
              {#each tr.diasSemana as nombreDia (nombreDia)}
                <span class="cabeza-dia" aria-hidden="true">{nombreDia}</span>
              {/each}
              {#each Array.from({ length: huecosMes }, (_, k) => k) as k (k)}
                <span aria-hidden="true"></span>
              {/each}
              {#each resumen.porDia as cuenta, d (d)}
                <span
                  class="dia-mes celda-hora {nivelMapa(cuenta, maxPorDia)}"
                  title={tr.celdaDia(d + 1, cuenta)}
                  aria-label={tr.celdaDia(d + 1, cuenta)}>{d + 1}</span
                >
              {/each}
            </div>
          {:else}
            <!-- Un año o todo el historial: una fila de doce meses por año. El
                 mapa de días por horas no decía nada de un periodo tan largo. -->
            <span class="etiqueta">{tr.mesesTitulo}</span>
            <p class="sub">{tr.mesesSub}</p>
            <div class="rejilla-meses">
              <span aria-hidden="true"></span>
              {#each MESES as m (m)}
                <span class="cabeza-mes" aria-hidden="true">{tr.meses[m]}</span>
              {/each}
              {#each aniosMeses as anio (anio)}
                <span class="etiqueta-anio">{anio}</span>
                {#each MESES as m (m)}
                  {@const clave = `${anio}-${m}`}
                  {@const cuenta = conteoMes.get(clave) ?? 0}
                  <button
                    type="button"
                    class="celda-mes celda-hora {nivelMapa(cuenta, maxPorMes)}"
                    disabled={cuenta === 0}
                    title={tr.celdaMes(`${tr.meses[m]} ${anio}`, cuenta)}
                    aria-label={tr.celdaMes(`${tr.meses[m]} ${anio}`, cuenta)}
                    onclick={() => cargarResumen(clave)}
                  ></button>
                {/each}
              {/each}
            </div>
          {/if}
        </article>
      </div>
    {/if}
  {/if}
</section>

<style>
  .perfil {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
  }

  .identidad {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-5);
    margin: calc(-1 * var(--ns-espacio-2)) calc(-1 * var(--ns-espacio-5)) 0;
    padding: var(--ns-espacio-5);
    /* Acaba en el fondo del lienzo, como las cabeceras de álbum y artista. */
    background: linear-gradient(
      180deg,
      color-mix(in srgb, var(--m3c-primary-container) 75%, var(--m3c-surface-container-low)) 0%,
      var(--m3c-surface-container-low) 100%
    );
  }

  .foto {
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    width: 8rem;
    height: 8rem;
    overflow: hidden;
    border: 3px solid var(--m3c-primary);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
  }

  .boton-foto {
    position: relative;
    cursor: pointer;
    padding: 0;
  }

  .velo-foto {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-inverse-surface);
    color: var(--m3c-inverse-on-surface);
    opacity: 0;
    transition: opacity var(--ns-duracion-corta) var(--ns-curva);
  }

  .boton-foto:hover .velo-foto,
  .boton-foto:focus-visible .velo-foto {
    opacity: 0.7;
  }

  .foto img,
  .img img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .datos {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
  }

  .etiqueta {
    color: var(--m3c-primary);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  h1 {
    margin: 0;
    font-size: clamp(var(--ns-texto-2xl), 4vw, var(--ns-texto-4xl));
    line-height: 1.05;
  }

  .nombre {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: 0;
    border: none;
    background: none;
    color: inherit;
    font: inherit;
    cursor: text;
  }

  .lapiz {
    display: inline-flex;
    color: var(--m3c-on-surface-variant);
    opacity: 0;
    transition: opacity var(--ns-duracion-corta) var(--ns-curva);
  }

  .nombre:hover .lapiz,
  .nombre:focus-visible .lapiz {
    opacity: 1;
  }

  .nombre-campo {
    width: min(100%, 28rem);
    padding: 0 var(--ns-espacio-2);
    border: none;
    border-bottom: 2px solid var(--m3c-primary);
    border-radius: 0;
    background: transparent;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: clamp(var(--ns-texto-2xl), 4vw, var(--ns-texto-4xl));
    font-weight: 700;
    line-height: 1.05;
  }

  h2 {
    margin: var(--ns-espacio-5) 0 0;
    font-size: var(--ns-texto-xl);
  }

  h3 {
    margin: 0;
    font-size: var(--ns-texto-xl);
  }

  p {
    margin: 0;
  }

  .sub {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .fichas {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ns-espacio-2);
  }

  .ficha {
    padding: var(--ns-espacio-1) var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    color: var(--m3c-on-surface);
    font-size: var(--ns-texto-xs);
    text-decoration: none;
  }

  /* Sobre el degradado del contenedor primario, el texto en primario no se leía. */
  .ficha.acento {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
    font-weight: 600;
  }

  .botones {
    display: flex;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-2);
  }

  .boton {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    height: 2.75rem;
    padding: 0 var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-weight: 700;
    cursor: pointer;
  }

  .boton.relleno {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .boton:disabled {
    opacity: 0.38;
  }

  .cifras {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--ns-espacio-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .tarjeta {
    padding: var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-low);
  }

  .cifras li {
    padding: 0;
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-low);
    overflow: hidden;
  }

  .cifra-enlace {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: var(--ns-espacio-1);
    width: 100%;
    height: 100%;
    padding: var(--ns-espacio-4);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    text-decoration: none;
    transition: background-color var(--ns-duracion-corta) var(--ns-curva);
  }

  .cifra-enlace:not(.estatica):hover {
    background: var(--m3c-surface-container);
  }

  .cifras strong {
    grid-row: 2;
    color: var(--m3c-on-surface);
    font-size: var(--ns-texto-xl);
  }

  .dos {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--ns-espacio-3);
  }

  .tres {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--ns-espacio-3);
  }

  .tarjeta {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
  }

  .calendario {
    display: grid;
    grid-template-columns: repeat(15, 1rem);
    gap: 0.25rem;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .dia {
    display: inline-block;
    width: 1rem;
    height: 1rem;
    border-radius: 0.2rem;
    background: var(--m3c-surface-container-highest);
  }

  /* Tres pasos del acento sobre el fondo: el contenedor primario se parece al
     primario en la mitad de los temas y los tres niveles no se distinguían. */
  .dia.poco {
    background: color-mix(in srgb, var(--m3c-primary) 30%, var(--m3c-surface-container-highest));
  }

  .dia.medio {
    background: color-mix(in srgb, var(--m3c-primary) 62%, var(--m3c-surface-container-highest));
  }

  .dia.mucho {
    background: var(--m3c-primary);
  }

  .leyenda {
    display: flex;
    gap: var(--ns-espacio-3);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .leyenda span {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-1);
  }

  .leyenda .dia {
    width: 0.625rem;
    height: 0.625rem;
  }

  .titulo-top {
    font-size: var(--ns-texto-sm);
    padding-bottom: var(--ns-espacio-2);
    border-bottom: 1px solid var(--m3c-outline-variant);
  }

  .top {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .fila {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    width: 100%;
    padding: var(--ns-espacio-2) 0;
    border: none;
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    text-align: left;
    text-decoration: none;
    cursor: pointer;
  }

  .n {
    width: 1.75rem;
    color: var(--m3c-primary);
    font-weight: 700;
  }

  .img {
    display: grid;
    place-items: center;
    flex: 0 0 2.5rem;
    height: 2.5rem;
    overflow: hidden;
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
  }

  .img.redonda {
    border-radius: var(--ns-radio-pleno);
  }

  .texto {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-width: 0;
  }

  .texto strong,
  .texto .sub {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .texto strong {
    font-size: var(--ns-texto-sm);
  }

  .texto .sub {
    font-size: var(--ns-texto-xs);
  }

  .vacio {
    color: var(--m3c-on-surface-variant);
  }

  .cabecera-resumen {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--ns-espacio-3);
    margin-top: var(--ns-espacio-3);
  }

  .cabecera-resumen h2 {
    margin: 0;
  }

  .chip-periodo {
    padding: var(--ns-espacio-1) var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-low);
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-xs);
    cursor: pointer;
  }

  .chip-periodo.activo {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary-container);
    color: var(--m3c-on-primary-container);
    font-weight: 700;
  }

  .radar-svg {
    width: 100%;
    max-width: 18rem;
    height: auto;
    align-self: center;
  }

  .radar-svg .guia-ext {
    fill: var(--m3c-surface-container-highest);
    stroke: var(--m3c-outline-variant);
    stroke-width: 1;
  }

  .radar-svg .guia-int {
    fill: none;
    stroke: var(--m3c-outline-variant);
    stroke-width: 1;
    stroke-dasharray: 3 3;
  }

  .radar-svg .area-radar {
    fill: var(--m3c-primary);
    fill-opacity: 0.32;
    stroke: var(--m3c-primary);
    stroke-width: 2;
  }

  .radar-svg text {
    fill: var(--m3c-on-surface);
    font-size: var(--ns-texto-xs);
    font-weight: 500;
  }

  /* Siempre seis semanas y celdas de medida fija: al cambiar de mes la tarjeta
     no crece ni encoge. */
  .mes-calendario {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    grid-template-rows: auto repeat(6, 2.5rem);
    gap: 0.3rem;
    margin-top: var(--ns-espacio-2);
  }

  .cabeza-dia,
  .cabeza-mes {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    text-align: center;
  }

  .mes-calendario .dia-mes {
    display: grid;
    place-items: center;
    aspect-ratio: auto;
    width: 100%;
    height: 100%;
    border-radius: var(--ns-radio-sm);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-variant-numeric: tabular-nums;
  }

  .dia-mes.mucho {
    color: var(--m3c-on-primary);
  }

  .dia-mes.medio {
    color: var(--m3c-on-surface);
  }

  .rejilla-meses {
    display: grid;
    grid-template-columns: 3rem repeat(12, minmax(0, 1fr));
    grid-auto-rows: 3.5rem;
    align-items: center;
    gap: 0.3rem;
    margin-top: var(--ns-espacio-2);
  }

  .etiqueta-anio {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-variant-numeric: tabular-nums;
  }

  .rejilla-meses .celda-mes {
    aspect-ratio: auto;
    width: 100%;
    height: 100%;
    padding: 0;
    border: none;
    cursor: pointer;
  }

  .celda-mes:disabled {
    cursor: default;
  }

  .celda-mes:hover:not(:disabled) {
    outline: 2px solid var(--m3c-primary);
    outline-offset: 1px;
  }

  .celda-hora {
    aspect-ratio: 1;
    border-radius: 0.15rem;
    background: var(--m3c-surface-container-highest);
  }

  /* Tres pasos del acento sobre el fondo: el contenedor primario se parece al
     primario en la mitad de los temas y los tres niveles no se distinguían. */
  .celda-hora.poco {
    background: color-mix(in srgb, var(--m3c-primary) 30%, var(--m3c-surface-container-highest));
  }

  .celda-hora.medio {
    background: color-mix(in srgb, var(--m3c-primary) 62%, var(--m3c-surface-container-highest));
  }

  .celda-hora.mucho {
    background: var(--m3c-primary);
  }

  @container carcasa (max-width: 70rem) {
    .tres,
    .dos {
      grid-template-columns: minmax(0, 1fr);
    }

    .cifras {
      grid-template-columns: repeat(2, 1fr);
    }
  }
</style>
