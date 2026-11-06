<!--
  @component
  Por revisar (F4.2.4, enmienda de ADR-007): lo que no entró solo.

  Cada canción pide una sola decisión, y el motivo se dice una vez por grupo, no en
  cada fila: "¿Es la versión correcta?", "Sin confirmar", "No las encontramos",
  "Ya las tienes", "No se pudieron guardar" y "Archivos dañados". Cada fila es la
  canción (su portada, su título y su artista, no el nombre del archivo), la
  acción que casi siempre se quiere y un ··· con las demás: importar tal como
  está, buscar de nuevo, verla en su carpeta y descartar. Las candidatas están a
  la vista, sin desplegar nada; con una sola, confirmarla es un clic.

  Se descartaron las casillas de selección: cada grupo tiene su acción para todas
  ("Importar las 10", "Descartar las 2") y la cabecera la de todo, que es lo que se
  seleccionaba a mano. Lo que es en lote se confirma; lo de una fila, no, y se
  dice después: descartar va a la papelera del sistema y se puede recuperar.
-->
<script lang="ts">
  import { importacion } from '#lib/core/importacion.svelte.ts';
  import {
    type Pendiente,
    porRevisarDescartar,
    porRevisarImportar,
    porRevisarListar,
    porRevisarMostrar,
    porRevisarReintentar,
    urlPortadaPendiente
  } from '#lib/core/ipc/index.ts';
  import { duracionLarga } from '#lib/core/formato.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import EstadoVacio from '#lib/ui/EstadoVacio.svelte';
  import Icon from '#lib/ui/Icon.svelte';
  import type { NombreDeIcono } from '#lib/ui/iconos.ts';
  import MenuAcciones, { type Accion } from '#lib/ui/MenuAcciones.svelte';

  const t = textos.porRevisar;

  type Grupo = keyof typeof t.grupos;
  /** Qué hace la acción principal de las filas de un grupo. */
  type Principal = 'elegir' | 'importar' | 'descartar' | 'reintentar';

  const GRUPOS: { id: Grupo; icono: NombreDeIcono; principal: Principal }[] = [
    { id: 'elegir', icono: 'duplicado', principal: 'elegir' },
    { id: 'sinConfirmar', icono: 'informacion', principal: 'importar' },
    { id: 'noEncontradas', icono: 'buscar', principal: 'importar' },
    { id: 'repetidas', icono: 'biblioteca', principal: 'descartar' },
    { id: 'fallidas', icono: 'advertencia', principal: 'reintentar' },
    { id: 'danadas', icono: 'error', principal: 'descartar' }
  ];

  /** Si hay candidatas, lo que se decide es cuál es, sea cual sea la causa. */
  function grupoDe(p: Pendiente): Grupo {
    if (p.candidatos.length > 0) return 'elegir';
    switch (p.causa) {
      case 'duplicado':
        return 'repetidas';
      case 'escritura_fallida':
      case 'validacion_post_escritura':
        return 'fallidas';
      case 'duracion_invalida':
      case 'audio_ilegible':
        return 'danadas';
      case 'sin_candidatos':
      case 'metadata_insuficiente':
      case 'puntaje_bajo':
        return 'noEncontradas';
      default:
        return 'sinConfirmar';
    }
  }

  let lista = $state<Pendiente[]>([]);
  let cargada = $state(false);
  /** Las filas con una acción en marcha: se apagan solas, no la vista entera. */
  let ocupadas = $state(new Set<number>());
  let confirmando = $state<{ clase: 'importar' | 'descartar'; ps: Pendiente[] } | null>(null);
  let dialogo: HTMLDialogElement | undefined = $state();
  let sinPortada = $state(new Set<number>());

  const grupos = $derived(
    GRUPOS.map((g) => ({ ...g, filas: lista.filter((p) => grupoDe(p) === g.id) })).filter(
      (g) => g.filas.length > 0
    )
  );

  async function cargar() {
    try {
      lista = await porRevisarListar();
    } catch {
      notificar.error(t.error);
    }
    cargada = true;
    await importacion.contar();
  }

  $effect(() => {
    void cargar();
  });

  // Al terminar una importación puede haber pendientes nuevos.
  $effect(() => {
    if (!importacion.progreso.activa) void cargar();
  });

  $effect(() => {
    if (!dialogo) return;
    if (confirmando && !dialogo.open) dialogo.showModal();
    else if (!confirmando && dialogo.open) dialogo.close();
  });

  /** Hace algo con unas filas, las apaga mientras tanto y dice cómo fue. */
  async function hacer(ps: Pendiente[], trabajo: () => Promise<unknown>, exito: string) {
    ocupadas = new Set([...ocupadas, ...ps.map((p) => p.id)]);
    try {
      await trabajo();
      notificar.exito(exito);
    } catch {
      notificar.error(t.error);
    } finally {
      const fuera = new Set(ps.map((p) => p.id));
      ocupadas = new Set([...ocupadas].filter((id) => !fuera.has(id)));
      await cargar();
    }
  }

  const importar = (ps: Pendiente[]) =>
    hacer(
      ps,
      async () => {
        for (const p of ps) await porRevisarImportar(p.id, null);
      },
      ps.length === 1 ? t.importada : t.importadas(ps.length)
    );

  const descartar = (ps: Pendiente[]) =>
    hacer(ps, () => porRevisarDescartar(ps.map((p) => p.id)), t.descartadas(ps.length));

  const reintentar = (ps: Pendiente[]) =>
    hacer(
      ps,
      async () => {
        for (const p of ps) await porRevisarReintentar(p.id);
      },
      t.reintentando
    );

  const elegir = (p: Pendiente, i: number) =>
    hacer([p], () => porRevisarImportar(p.id, i), t.elegida);

  /** Lo de una fila se hace sin preguntar; en lote, se confirma antes. */
  function enLote(clase: 'importar' | 'descartar', ps: Pendiente[]) {
    if (ps.length === 1) void (clase === 'importar' ? importar(ps) : descartar(ps));
    else confirmando = { clase, ps };
  }

  function confirmar() {
    const c = confirmando;
    confirmando = null;
    if (!c) return;
    void (c.clase === 'importar' ? importar(c.ps) : descartar(c.ps));
  }

  function accionGrupo(g: (typeof grupos)[number]) {
    switch (g.principal) {
      case 'importar':
        return { texto: t.importarGrupo(g.filas.length), hacer: () => enLote('importar', g.filas) };
      case 'descartar':
        return {
          texto: t.descartarGrupo(g.filas.length),
          hacer: () => enLote('descartar', g.filas)
        };
      case 'reintentar':
        return { texto: t.reintentarGrupo(g.filas.length), hacer: () => reintentar(g.filas) };
      default:
        return null;
    }
  }

  function accionesDe(p: Pendiente): Accion[] {
    return [
      { texto: t.importarTalCual, icono: 'importar', accion: () => importar([p]) },
      { texto: t.buscarDeNuevo, icono: 'reintentar', accion: () => reintentar([p]) },
      {
        texto: textos.biblioteca.mostrarEnExplorador,
        icono: 'carpeta',
        accion: () =>
          porRevisarMostrar(p.id).catch(() => notificar.error(textos.biblioteca.explorarFallo))
      },
      {
        texto: t.descartar,
        icono: 'borrar',
        destructiva: true,
        separada: true,
        accion: () => descartar([p])
      }
    ];
  }

  /** El nombre del archivo sin extensión ni el sufijo de la web de la que vino. */
  function nombreLimpio(p: Pendiente): string {
    return p.nombre
      .replace(/\.[a-z0-9]{2,4}$/i, '')
      .replace(/_spotdown\.org$/i, '')
      .replace(/_/g, ' ')
      .trim();
  }

  /** Para comparar nombres: sin mayúsculas, tildes ni signos. */
  function plano(x: string | null): string {
    return (x ?? '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .trim();
  }

  /**
   * Las candidatas, la más probable primero: la del mismo artista que trae el
   * archivo y con su duración. El orden del catálogo no lo tiene en cuenta, y la
   * buena llegaba la quinta. Cada una conserva su índice, que es lo que se elige.
   */
  function ordenadas(p: Pendiente) {
    const artista = plano(p.artista);
    const titulo = plano(p.titulo);
    return p.candidatos
      .map((c, i) => {
        const a = plano(c.artista);
        let puntos = 0;
        if (a && artista && (artista.includes(a) || a.includes(artista))) puntos += 2;
        if (titulo && plano(c.titulo) && titulo.includes(plano(c.titulo))) puntos += 1;
        if (p.duracionSeg && c.duracionSeg)
          puntos += 1 - Math.min(1, Math.abs(p.duracionSeg - c.duracionSeg) / 10);
        return { c, i, puntos };
      })
      .sort((x, y) => y.puntos - x.puntos);
  }

  /** Las filas con todas sus candidatas a la vista; las demás enseñan dos. */
  let abiertas = $state(new Set<number>());
  const VISIBLES = 2;

  function detalleCandidata(c: Pendiente['candidatos'][number]): string {
    const tipos = textos.biblioteca.tipos as Record<string, string>;
    return [c.album, c.anio ?? '', c.tipo ? (tipos[c.tipo] ?? c.tipo) : '']
      .filter((x) => x !== '')
      .join(' · ');
  }

  const faltas = $derived(
    confirmando?.clase === 'importar'
      ? [...new Set(confirmando.ps.flatMap((p) => p.faltaria))].map((f) => t.falta[f] ?? f)
      : []
  );
</script>

<section class="vista">
  <header class="cabecera">
    <div>
      <h1>{t.titulo}</h1>
      {#if lista.length > 0}<p class="cuenta">{t.cuenta(lista.length)}</p>{/if}
    </div>
    {#if lista.length > 1}
      <MenuAcciones
        etiqueta={t.masAcciones}
        acciones={[
          {
            texto: t.importarTodas,
            icono: 'importar',
            accion: () => enLote('importar', lista)
          },
          {
            texto: t.descartarTodas,
            icono: 'borrar',
            destructiva: true,
            separada: true,
            accion: () => enLote('descartar', lista)
          }
        ]}
      />
    {/if}
  </header>

  {#if cargada && lista.length === 0}
    <EstadoVacio icono="correcto" titulo={t.vacioTitulo} texto={t.vacio} />
  {/if}

  {#each grupos as g (g.id)}
    {@const lote = accionGrupo(g)}
    <section class="grupo" aria-labelledby="g-{g.id}">
      <header class="grupo-cabecera">
        <span class="grupo-icono" aria-hidden="true"><Icon nombre={g.icono} tamano={18} /></span>
        <div class="grupo-texto">
          <h2 id="g-{g.id}">{t.grupos[g.id].titulo} <span>{g.filas.length}</span></h2>
          <p>{t.grupos[g.id].ayuda}</p>
        </div>
        {#if lote && g.filas.length > 1}
          <button
            type="button"
            class="boton relleno"
            class:destructivo={g.principal === 'descartar'}
            disabled={g.filas.some((p) => ocupadas.has(p.id))}
            onclick={lote.hacer}
          >
            {lote.texto}
          </button>
        {/if}
      </header>

      <ul class="filas">
        {#each g.filas as p (p.id)}
          {@const ocupada = ocupadas.has(p.id)}
          <li class="fila" class:ocupada class:con-candidatas={g.principal === 'elegir'}>
            <span class="portada" aria-hidden="true">
              {#if !sinPortada.has(p.id)}
                <img
                  src={urlPortadaPendiente(p.id)}
                  alt=""
                  loading="lazy"
                  onerror={() => (sinPortada = new Set([...sinPortada, p.id]))}
                />
              {:else}
                <Icon nombre="cancion" tamano={20} />
              {/if}
            </span>
            <div class="cancion" title={p.nombre}>
              <strong>{p.titulo ?? nombreLimpio(p)}</strong>
              <span>
                {[
                  p.artista ?? (p.duplicadoDe ? '' : t.sinEtiquetas),
                  p.duracionSeg ? duracionLarga(p.duracionSeg) : ''
                ]
                  .filter((x) => x !== '')
                  .join(' · ')}
              </span>
              {#if p.duplicadoDe}<span class="nota">{t.yaEsta(p.duplicadoDe)}</span>{/if}
            </div>

            {#if g.principal === 'elegir'}
              {@const todas = ordenadas(p)}
              {@const vistas = abiertas.has(p.id) ? todas : todas.slice(0, VISIBLES)}
              <ul class="candidatas">
                {#each vistas as { c, i }, n (i)}
                  <li class="candidata">
                    <div>
                      <strong>{c.titulo}</strong>
                      <span>{c.artista}</span>
                      <small>{detalleCandidata(c)}</small>
                    </div>
                    <button
                      type="button"
                      class="boton"
                      class:relleno={n === 0}
                      class:tonal={n > 0}
                      disabled={ocupada}
                      onclick={() => elegir(p, i)}
                    >
                      <Icon nombre="correcto" tamano={16} />{t.esEsta}
                    </button>
                  </li>
                {/each}
                {#if todas.length > VISIBLES}
                  <li>
                    <button
                      type="button"
                      class="mas"
                      aria-expanded={abiertas.has(p.id)}
                      onclick={() => {
                        const a = new Set(abiertas);
                        if (a.has(p.id)) a.delete(p.id);
                        else a.add(p.id);
                        abiertas = a;
                      }}
                    >
                      <Icon nombre={abiertas.has(p.id) ? 'arriba' : 'abajo'} tamano={16} />
                      {abiertas.has(p.id) ? t.verMenos : t.verMas(todas.length - VISIBLES)}
                    </button>
                  </li>
                {/if}
              </ul>
            {:else}
              <button
                type="button"
                class="boton tonal"
                disabled={ocupada}
                onclick={() =>
                  g.principal === 'importar'
                    ? importar([p])
                    : g.principal === 'reintentar'
                      ? reintentar([p])
                      : descartar([p])}
              >
                {g.principal === 'importar'
                  ? t.importar
                  : g.principal === 'reintentar'
                    ? t.reintentar
                    : t.descartar}
              </button>
            {/if}
            <span class="menu">
              <MenuAcciones acciones={accionesDe(p)} etiqueta={t.masAcciones} tamano="fila" />
            </span>
          </li>
        {/each}
      </ul>
    </section>
  {/each}
</section>

<dialog bind:this={dialogo} onclose={() => (confirmando = null)} aria-labelledby="titulo-lote">
  {#if confirmando}
    {#if confirmando.clase === 'importar'}
      <h2 id="titulo-lote">{t.confirmarImportar(confirmando.ps.length)}</h2>
      <p>{faltas.length > 0 ? `${t.faltara} ${faltas.join(', ')}.` : t.nadaFalta}</p>
    {:else}
      <h2 id="titulo-lote">{t.confirmarDescartar(confirmando.ps.length)}</h2>
      <p>{t.papelera}</p>
    {/if}
    <div class="botones">
      <button type="button" class="boton" onclick={() => (confirmando = null)}>{t.cancelar}</button>
      <button
        type="button"
        class="boton relleno"
        class:destructivo={confirmando.clase === 'descartar'}
        onclick={confirmar}
      >
        {confirmando.clase === 'importar' ? t.confirmar : t.confirmarDescarte}
      </button>
    </div>
  {/if}
</dialog>

<style>
  .vista {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-6);
    max-width: 64rem;
  }

  .cabecera {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-4);
  }

  h1 {
    margin: 0;
    font-size: var(--ns-texto-xl);
  }

  .cuenta {
    margin: var(--ns-espacio-1) 0 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .grupo {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
  }

  .grupo-cabecera {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
  }

  .grupo-icono {
    display: grid;
    flex: 0 0 auto;
    place-items: center;
    width: 2.25rem;
    height: 2.25rem;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
  }

  .grupo-texto {
    flex: 1;
    min-width: 0;
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-md);
  }

  h2 span {
    margin-left: var(--ns-espacio-1);
    color: var(--m3c-on-surface-variant);
    font-weight: 500;
  }

  .grupo-texto p {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .filas,
  .candidatas {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .filas {
    overflow: hidden;
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container);
  }

  .fila {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto auto;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-2) var(--ns-espacio-2) var(--ns-espacio-2) var(--ns-espacio-3);
    transition: opacity var(--ns-duracion-corta) var(--ns-curva);
  }

  .fila + .fila {
    border-top: 1px solid var(--m3c-outline-variant);
  }

  .fila.con-candidatas {
    grid-template-columns: auto minmax(0, 1fr) minmax(0, 1.3fr) auto;
    align-items: start;
  }

  .fila.ocupada {
    opacity: 0.5;
    pointer-events: none;
  }

  .portada {
    display: grid;
    place-items: center;
    width: 3rem;
    height: 3rem;
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

  .cancion,
  .candidata div {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .con-candidatas .cancion {
    padding-top: var(--ns-espacio-1);
  }

  .cancion strong,
  .cancion span,
  .candidata strong,
  .candidata span,
  .candidata small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .cancion span,
  .candidata span {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .cancion .nota {
    color: var(--m3c-primary);
    font-size: var(--ns-texto-xs);
  }

  .candidatas {
    gap: var(--ns-espacio-1);
  }

  .candidata {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-2) var(--ns-espacio-2) var(--ns-espacio-2) var(--ns-espacio-3);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-high);
  }

  .candidata small {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .menu {
    align-self: center;
  }

  .con-candidatas .menu {
    align-self: start;
    padding-top: var(--ns-espacio-1);
  }

  .mas {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    padding: var(--ns-espacio-1) var(--ns-espacio-3);
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-primary);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    cursor: pointer;
  }

  .mas:hover {
    background: var(--m3c-surface-container-highest);
  }

  .boton {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    gap: var(--ns-espacio-2);
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

  .boton:hover:not(:disabled) {
    background: var(--m3c-surface-container-highest);
  }

  .boton.relleno {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .boton.relleno:hover:not(:disabled) {
    background: var(--m3c-primary);
    filter: brightness(1.08);
  }

  .boton.tonal {
    border-color: transparent;
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
  }

  .boton.tonal:hover:not(:disabled) {
    background: var(--m3c-secondary-container);
    filter: brightness(1.1);
  }

  .boton.destructivo {
    border-color: var(--m3c-error);
    background: var(--m3c-error);
    color: var(--m3c-on-error);
  }

  .grupo-cabecera .boton.destructivo {
    border-color: transparent;
    background: var(--m3c-error-container);
    color: var(--m3c-on-error-container);
  }

  .boton:disabled {
    opacity: 0.5;
    cursor: default;
  }

  dialog {
    width: min(26rem, 90vw);
    padding: var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
  }

  dialog::backdrop {
    background: var(--m3c-scrim);
    opacity: 0.5;
  }

  dialog h2 {
    margin: 0 0 var(--ns-espacio-3);
    font-size: var(--ns-texto-lg);
  }

  dialog p {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
    line-height: 1.5;
  }

  .botones {
    display: flex;
    justify-content: flex-end;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-5);
  }

  /* Estrecho: la candidata baja debajo de la canción, a todo el ancho. */
  @container carcasa (max-width: 56rem) {
    .fila.con-candidatas {
      grid-template-columns: auto minmax(0, 1fr) auto;
    }

    .fila.con-candidatas .candidatas {
      grid-column: 1 / -1;
      grid-row: 2;
    }

    .fila.con-candidatas .menu {
      grid-column: 3;
      grid-row: 1;
    }
  }
</style>
