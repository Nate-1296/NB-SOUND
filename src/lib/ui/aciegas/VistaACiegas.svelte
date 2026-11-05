<!--
  @component
  A ciegas (ADR-007, F6.2.2): elegir un modo, jugar una ronda de retos y ver el
  resumen. La vista solo recibe lo ya revelado; el fragmento suena por el
  reproductor de siempre, que mientras tanto no dice qué canción es. Se carga
  aparte del arranque.
-->
<script module lang="ts">
  // Las canciones ya jugadas en esta sesión, para no repetirlas enseguida. Vive
  // lo que la aplicación, como la memoria de la V1.
  const jugadas: number[] = [];
</script>

<script lang="ts">
  import { onMount } from 'svelte';
  import { urlPortada } from '#lib/core/ipc/index.ts';
  import {
    aciegasDisponibles,
    aciegasFragmento,
    aciegasIniciar,
    aciegasIntentar,
    aciegasJugar,
    aciegasRonda,
    type Indicio,
    type Jugada,
    type Modo,
    type ModoDisponible,
    type ResultadoIntento,
    type RetoVisible,
    type Ronda
  } from '#lib/core/ipc/aciegas.ts';
  import { reproductor } from '#lib/core/reproductor.svelte.ts';
  import { textosACiegas } from '#lib/i18n/aciegas.ts';
  import EstadoVacio from '#lib/ui/EstadoVacio.svelte';
  import Icon from '#lib/ui/Icon.svelte';

  const t = textosACiegas;
  const MODOS: Modo[] = ['portada', 'audio', 'redescubrimiento', 'nunca_eliges'];
  const INDICIOS: Indicio[] = [
    'alfabeto',
    'empiezaCon',
    'terminaCon',
    'cantidadPalabras',
    'cantidadLetras'
  ];
  const RETOS = [5, 10, 15];
  const SEGUNDOS = [8, 12, 20];

  let ronda = $state<Ronda | null>(null);
  let disponibles = $state<ModoDisponible[]>([]);
  let modo = $state<Modo>('portada');
  let retos = $state(5);
  let texto = $state('');
  let intento = $state<ResultadoIntento['intento'] | null>(null);
  let aviso = $state<string | null>(null);
  let avisoEsError = $state(false);
  let enCola = $state(false);
  let iniciando = $state(false);

  const reto = $derived(ronda?.reto ?? null);
  const resuelto = $derived(reto?.titulo != null);
  const ultimo = $derived(ronda ? ronda.indice + 1 >= ronda.total : false);
  const cuenta = (m: Modo) => disponibles.find((d) => d.modo === m)?.canciones ?? 0;
  const conPortada = $derived(ronda?.modo !== 'audio');
  const conSonido = $derived(ronda?.modo !== 'portada');

  onMount(() => {
    void aciegasRonda().then((r) => {
      if (r.modo) ronda = r;
    });
    void aciegasDisponibles().then((d) => {
      disponibles = d;
      modo = MODOS.find((m) => cuenta(m) > 0) ?? 'portada';
    });
  });

  // Lo que se va revelando en la ronda, para el resumen: antes solo decía
  // "0 acertadas · 5 reveladas" sin las canciones, que es lo que uno quiere volver
  // a escuchar.
  let deLaRonda = $state<RetoVisible[]>([]);

  function recordar(r: Ronda) {
    const id = r.reto?.pistaId;
    if (id != null && r.reto?.titulo != null && !jugadas.includes(id)) jugadas.push(id);
    if (r.reto && r.reto.titulo != null) {
      const visto = r.reto;
      deLaRonda = [...deLaRonda.filter((x) => x.pistaId !== visto.pistaId), visto];
    }
  }

  function nueva(r: Ronda) {
    recordar(r);
    if (r.reto?.pistaId !== ronda?.reto?.pistaId) {
      texto = '';
      intento = null;
      enCola = false;
    }
    ronda = r;
  }

  async function empezar(m: Modo) {
    if (iniciando) return;
    aviso = null;
    avisoEsError = false;
    iniciando = true;
    try {
      const r = await aciegasIniciar(m, retos, jugadas);
      if (!r.modo) {
        aviso = t.sinCanciones;
        avisoEsError = true;
        return;
      }
      texto = '';
      intento = null;
      deLaRonda = [];
      ronda = r;
    } catch {
      aviso = t.errorAlIniciar;
      avisoEsError = true;
    } finally {
      iniciando = false;
    }
  }

  async function jugar(j: Jugada) {
    nueva(await aciegasJugar(j));
  }

  async function comprobar() {
    if (!texto.trim()) return;
    const r = await aciegasIntentar(texto);
    intento = r.intento;
    nueva(r.ronda);
  }

  async function cambiarDeModo() {
    ronda = (await aciegasJugar({ tipo: 'cerrar' })).modo ? ronda : null;
    disponibles = await aciegasDisponibles();
  }

  function valorIndicio(i: Indicio, valor: string): string {
    return i === 'alfabeto' ? (t.alfabetos[valor] ?? valor) : valor;
  }
</script>

<section class="vista">
  <header>
    <h1>{t.titulo}</h1>
    <p class="sub">{t.subtitulo}</p>
  </header>

  {#if !ronda && disponibles.length > 0 && disponibles.every((d) => d.canciones === 0)}
    <EstadoVacio icono="aCiegas" titulo={t.sinMusica} conAnadir />
  {:else if !ronda}
    <div class="modos">
      {#each MODOS as m (m)}
        <button
          type="button"
          class="modo"
          class:elegido={modo === m}
          aria-pressed={modo === m}
          disabled={cuenta(m) === 0}
          onclick={() => (modo = m)}
        >
          <strong>{t.modos[m].nombre}</strong>
          <span>{t.modos[m].detalle}</span>
          <small>{t.canciones(cuenta(m))}</small>
        </button>
      {/each}
    </div>
    <div class="fila">
      <span class="rotulo">{t.retos}</span>
      {#each RETOS as n (n)}
        <button
          type="button"
          class="ficha"
          class:activa={retos === n}
          aria-pressed={retos === n}
          onclick={() => (retos = n)}>{n}</button
        >
      {/each}
      <button
        type="button"
        class="boton relleno"
        disabled={cuenta(modo) === 0 || iniciando}
        onclick={() => empezar(modo)}
      >
        <Icon nombre="aCiegas" tamano={16} />{iniciando ? t.cargando : t.empezar}
      </button>
    </div>
    {#if aviso}<p class="aviso" class:error={avisoEsError} role="status">{aviso}</p>{/if}
  {:else if ronda.terminada}
    <div class="tarjeta resumen">
      <h2>{t.resumen.titulo}</h2>
      <p>{t.resumen.cifras(ronda.acertados, ronda.revelados, ronda.pasados)}</p>
      {#if deLaRonda.length > 0}
        <ol class="de-la-ronda">
          {#each deLaRonda as r (r.pistaId)}
            <li>
              <img src={urlPortada('pista', r.pistaId, 64)} alt="" />
              <span class="datos-ronda">
                <strong>{r.titulo}</strong>
                <small>{r.artista}</small>
              </span>
              <span class="resultado {r.estado}">{t.resumen.estados[r.estado]}</span>
              <button
                type="button"
                class="escuchar"
                aria-label={t.resumen.escuchar(r.titulo ?? '')}
                title={t.resumen.escuchar(r.titulo ?? '')}
                onclick={() => reproductor.reproducirPistas([r.pistaId])}
              >
                <Icon nombre="reproducir" tamano={16} />
              </button>
            </li>
          {/each}
        </ol>
      {/if}
      <div class="fila">
        <button
          type="button"
          class="boton relleno"
          disabled={iniciando}
          onclick={() => ronda?.modo && empezar(ronda.modo)}
        >
          {iniciando ? t.cargando : t.resumen.otra}
        </button>
        <button type="button" class="boton" onclick={cambiarDeModo}>{t.resumen.cambiar}</button>
      </div>
    </div>
  {:else if reto}
    <div class="tarjeta">
      <div class="cabecera">
        <span class="estado">{t.reto(ronda.indice + 1, ronda.total)}</span>
        <span class="marcador">{t.marcador(ronda.acertados)}</span>
      </div>

      <div class="pista">
        {#if conPortada}
          <div class="portada">
            {#if reto.tienePortada}
              <img src={urlPortada('pista', reto.pistaId, 480)} alt="" width="240" height="240" />
            {:else}
              <Icon nombre="cancion" tamano={64} />
            {/if}
          </div>
        {/if}
        <dl class="campos">
          <dt>{t.campos.titulo}</dt>
          <dd class:oculto={reto.titulo == null}>
            {reto.titulo ?? t.oculto}{#if reto.anio}<small class="anio">{reto.anio}</small>{/if}
          </dd>
          <dt>{t.campos.artista}</dt>
          <dd class:oculto={reto.artista == null}>{reto.artista ?? t.oculto}</dd>
          <dt>{t.campos.album}</dt>
          <dd class:oculto={reto.album == null}>{reto.album ?? t.oculto}</dd>
        </dl>
      </div>

      {#if conSonido && !resuelto}
        <div class="fila">
          <button
            type="button"
            class="boton relleno"
            onclick={() => aciegasFragmento().then(nueva)}
          >
            <Icon nombre="reproducir" tamano={16} />{t.escuchar}
          </button>
          <span class="rotulo">{t.duracionFragmento}</span>
          {#each SEGUNDOS as s (s)}
            <button
              type="button"
              class="ficha"
              class:activa={ronda.segundosFragmento === s}
              aria-pressed={ronda.segundosFragmento === s}
              onclick={() => jugar({ tipo: 'segundosFragmento', segundos: s })}
              >{t.segundos(s)}</button
            >
          {/each}
          {#if reproductor.instantanea.ciego}
            <span class="barra" aria-hidden="true"
              ><span
                style:width={`${Math.round(
                  (reproductor.posicion / Math.max(reproductor.instantanea.duracionSeg, 1)) * 100
                )}%`}
              ></span></span
            >
          {/if}
        </div>
      {/if}

      {#if !resuelto}
        {#if reto.sePuedeEscribir}
          <form
            class="fila"
            onsubmit={(e) => {
              e.preventDefault();
              void comprobar();
            }}
          >
            <input
              class="campo"
              maxlength="300"
              placeholder={t.escribir}
              aria-label={t.escribir}
              bind:value={texto}
            />
            <button type="submit" class="boton relleno">{t.comprobar}</button>
          </form>
        {:else}
          <div class="fila">
            <p class="aviso">{t.noSeEscribe}</p>
            <button type="button" class="boton relleno" onclick={() => jugar({ tipo: 'laSe' })}
              >{t.laSe}</button
            >
          </div>
        {/if}
        {#if intento && !intento.acierto}
          <p class="aviso" role="status">{intento.cerca ? t.cerca : t.fallo}</p>
        {/if}
        {#if reto.fallos > 0}<p class="aviso">{t.fallos(reto.fallos)}</p>{/if}

        <div class="fila">
          <span class="rotulo">{t.indicios}</span>
          {#each INDICIOS as i (i)}
            {@const visto = reto.indicios.find((v) => v.indicio === i)}
            {#if visto}
              <span class="indicio"
                >{t.nombresIndicio[i]}: <strong>{valorIndicio(i, visto.valor)}</strong></span
              >
            {:else}
              <button
                type="button"
                class="ficha"
                onclick={() => jugar({ tipo: 'indicio', indicio: i })}>{t.nombresIndicio[i]}</button
              >
            {/if}
          {/each}
        </div>

        <div class="fila">
          {#if reto.artista == null}
            <button type="button" class="boton" onclick={() => jugar({ tipo: 'revelarArtista' })}
              >{t.verArtista}</button
            >
          {/if}
          {#if reto.album == null}
            <button type="button" class="boton" onclick={() => jugar({ tipo: 'revelarAlbum' })}
              >{t.verAlbum}</button
            >
          {/if}
          <button type="button" class="boton" onclick={() => jugar({ tipo: 'revelarTodo' })}
            >{t.rendirse}</button
          >
        </div>
      {:else}
        {#if reto.estado === 'acertado'}<p class="exito" role="status">{t.acierto}</p>{/if}
        <div class="fila">
          <button
            type="button"
            class="boton"
            onclick={() => reto && reproductor.reproducirPistas([reto.pistaId])}
          >
            <Icon nombre="reproducir" tamano={16} />{t.escucharEntera}
          </button>
          <button
            type="button"
            class="boton"
            disabled={enCola}
            onclick={() => {
              if (!reto) return;
              void reproductor.orden({ tipo: 'agregar', ids: [reto.pistaId], justoDespues: false });
              enCola = true;
            }}
          >
            <Icon nombre="cola" tamano={16} />{enCola ? t.enCola : t.aLaCola}
          </button>
        </div>
      {/if}

      <div class="fila navegacion">
        {#if ronda.indice > 0}
          <button type="button" class="boton" onclick={() => jugar({ tipo: 'retroceder' })}>
            <Icon nombre="anterior" tamano={16} />{t.anterior}
          </button>
        {/if}
        <button type="button" class="boton relleno" onclick={() => jugar({ tipo: 'avanzar' })}>
          {ultimo ? t.terminar : t.siguiente}<Icon nombre="siguiente" tamano={16} />
        </button>
      </div>
    </div>
  {/if}
</section>

<style>
  .anio {
    margin-left: var(--ns-espacio-2);
    color: var(--m3c-on-surface-variant);
    font-weight: 400;
  }

  .de-la-ronda {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    margin: 0;
    padding: 0;
    list-style: none;
    text-align: left;
  }

  .de-la-ronda li {
    display: grid;
    grid-template-columns: 2.5rem minmax(0, 1fr) auto auto;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-2);
    border-radius: var(--ns-radio-sm);
  }

  .de-la-ronda li:hover {
    background: var(--m3c-surface-container-high);
  }

  .de-la-ronda img {
    width: 2.5rem;
    height: 2.5rem;
    border-radius: var(--ns-radio-sm);
    object-fit: cover;
  }

  .datos-ronda {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .datos-ronda strong,
  .datos-ronda small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .datos-ronda small {
    color: var(--m3c-on-surface-variant);
  }

  .resultado {
    padding: 0 var(--ns-espacio-2);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
  }

  .resultado.acertado {
    background: color-mix(in srgb, var(--m3c-primary) 18%, transparent);
    color: var(--m3c-primary);
  }

  .escuchar {
    display: grid;
    place-items: center;
    width: 2.25rem;
    height: 2.25rem;
    padding: 0;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
    cursor: pointer;
  }

  .vista {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
    max-width: 50rem;
    margin: 0 auto;
    width: 100%;
  }

  header {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: var(--ns-espacio-1);
    margin-bottom: var(--ns-espacio-1);
  }

  h1 {
    margin: 0;
    font-size: var(--ns-texto-xl);
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
  }

  p {
    margin: 0;
  }

  .sub,
  .aviso {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .aviso.error {
    color: var(--m3c-error);
  }

  .exito {
    color: var(--m3c-primary);
    font-weight: 700;
  }

  .modos {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--ns-espacio-3);
  }

  .modo {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    padding: var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-xl);
    background: var(--m3c-surface-container);
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
    transition:
      border-color var(--ns-duracion-corta) var(--ns-curva),
      background-color var(--ns-duracion-corta) var(--ns-curva),
      box-shadow var(--ns-duracion-corta) var(--ns-curva);
  }

  .modo:hover:not(:disabled) {
    background: var(--m3c-surface-container-high);
    border-color: var(--m3c-outline);
    box-shadow: 0 4px 12px var(--m3c-shadow);
  }

  .modo.elegido {
    border-color: var(--m3c-primary);
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
  }

  .modo:disabled {
    opacity: 0.38;
    cursor: default;
  }

  .modo span,
  .modo small {
    font-size: var(--ns-texto-sm);
  }

  .modo small {
    color: var(--m3c-on-surface-variant);
  }

  .tarjeta {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
    padding: var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-xl);
    background: var(--m3c-surface-container);
    box-shadow: 0 4px 20px var(--m3c-shadow);
  }

  .cabecera {
    display: flex;
    justify-content: space-between;
    font-size: var(--ns-texto-sm);
  }

  .estado {
    color: var(--m3c-primary);
    font-weight: 700;
  }

  .marcador {
    color: var(--m3c-on-surface-variant);
  }

  .pista {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: var(--ns-espacio-4);
  }

  .portada {
    display: grid;
    place-items: center;
    width: 12rem;
    height: 12rem;
    overflow: hidden;
    border-radius: var(--ns-radio-xl);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface-variant);
    box-shadow: 0 8px 24px var(--m3c-shadow);
  }

  .portada img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .campos {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: var(--ns-espacio-2) var(--ns-espacio-4);
    margin: 0;
    text-align: left;
  }

  dt {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  dd {
    margin: 0;
    font-weight: 700;
  }

  dd.oculto {
    color: var(--m3c-on-surface-variant);
    letter-spacing: 0.2em;
  }

  dd small {
    color: var(--m3c-on-surface-variant);
    font-weight: 400;
  }

  .fila {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: center;
    gap: var(--ns-espacio-2);
  }

  .navegacion {
    justify-content: flex-end;
  }

  .rotulo {
    margin-right: var(--ns-espacio-1);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-weight: 600;
  }

  .indicio {
    font-size: var(--ns-texto-sm);
  }

  .campo {
    flex: 1;
    min-width: 14rem;
    max-width: 28rem;
    height: 2.75rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
  }

  .campo:focus {
    border-color: var(--m3c-primary);
    background: var(--m3c-surface-container-highest);
  }

  .ficha {
    height: 2rem;
    padding: 0 var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-xs);
    cursor: pointer;
  }

  .ficha.activa {
    border-color: var(--m3c-primary);
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
    font-weight: 700;
  }

  .boton {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-1);
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

  .boton.relleno {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .boton:disabled {
    opacity: 0.38;
    cursor: default;
  }

  .barra {
    flex: 1;
    min-width: 6rem;
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
</style>
