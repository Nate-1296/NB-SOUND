<!--
  Ajustes, rediseñado (ADR-007): una sola página con sus secciones en orden y un
  índice para saltar entre ellas. Las de esta fase son Biblioteca, Reproducción,
  Apariencia y Acerca de; Dispositivos, Agregados, Privacidad e Inteligencia
  artificial llegan con sus fases. Todo cambio se guarda al momento, sin botón de
  guardar.
-->
<script lang="ts">
  import { aparienciaActual } from '$core/apariencia.svelte';
  import {
    type AjustesEcualizador,
    carpetaMusica,
    ecualizador,
    type PreseleccionEcualizador,
    preseleccionesEcualizador,
    salud
  } from '$core/ipc';
  import { reproductor } from '$core/reproductor.svelte';
  import { textos } from '$lib/i18n';
  import type { TemaV1 } from '$ui/temas-v1';

  const t = textos.ajustes;
  const TIPOGRAFIAS = [
    'Inter',
    'Fira Sans',
    'IBM Plex Sans',
    'Atkinson Hyperlegible',
    'Source Sans 3'
  ];
  const BANDAS = ['31', '62', '125', '250', '500', '1k', '2k', '4k', '8k', '16k'];

  const version = salud()
    .then((informe) => informe.version)
    .catch(() => null);
  const carpeta = carpetaMusica().catch(() => null);

  let eq = $state<AjustesEcualizador>({
    activo: false,
    preseleccion: 0,
    bandas: Array(10).fill(0),
    preamp: 0
  });
  let preselecciones = $state<PreseleccionEcualizador[]>([]);
  $effect(() => {
    void ecualizador().then((e) => (eq = e));
    void preseleccionesEcualizador().then((p) => (preselecciones = p));
  });

  function enviarEq(nuevo: AjustesEcualizador) {
    eq = nuevo;
    void reproductor.orden({ tipo: 'ecualizador', ajustes: nuevo });
  }

  function elegirPreseleccion(indice: string) {
    if (indice === '') return;
    const i = Number(indice);
    const p = preselecciones[i];
    if (!p) return;
    enviarEq({ activo: true, preseleccion: i, bandas: [...p.bandasDb], preamp: p.preampDb });
  }

  // Los deslizadores mandan a la pausa: arrastrar no es una orden por píxel.
  let espera: ReturnType<typeof setTimeout> | undefined;
  function moverBanda(k: number, valor: number) {
    const bandas = [...eq.bandas];
    bandas[k] = valor;
    eq = { ...eq, preseleccion: null, bandas };
    clearTimeout(espera);
    espera = setTimeout(() => enviarEq(eq), 120);
  }

  // Los 63 temas se cargan aparte: no pesan en el arranque (`check-paquete`).
  let temas = $state<readonly TemaV1[]>([]);
  $effect(() => {
    void import('$ui/temas-v1').then((m) => (temas = m.TEMAS_V1));
  });

  let nombre = $state(aparienciaActual.actual.nombreUsuario ?? '');
</script>

<div class="ajustes">
  <nav class="indice" aria-label={t.secciones}>
    <a href="#biblioteca">{t.biblioteca}</a>
    <a href="#reproduccion">{t.reproduccion}</a>
    <a href="#apariencia">{t.apariencia}</a>
    <a href="#acerca">{t.acercaDe}</a>
  </nav>

  <div class="contenido">
    <h1>{t.titulo}</h1>

    <section id="biblioteca" aria-labelledby="t-biblioteca">
      <h2 id="t-biblioteca">{t.biblioteca}</h2>
      <div class="ajuste">
        <span class="rotulo">{t.carpeta}</span>
        {#await carpeta then c}
          <code class="valor">{c ?? t.sinCarpeta}</code>
        {/await}
      </div>
      <label class="ajuste">
        <span class="rotulo">{t.nombre}<small>{t.nombreAyuda}</small></span>
        <input
          class="campo"
          maxlength="60"
          bind:value={nombre}
          onchange={() => aparienciaActual.cambiar('nombreUsuario', nombre.trim() || null)}
        />
      </label>
    </section>

    <section id="reproduccion" aria-labelledby="t-reproduccion">
      <h2 id="t-reproduccion">{t.reproduccion}</h2>
      <label class="ajuste interruptor">
        <span class="rotulo">{t.normalizar}<small>{t.normalizarAyuda}</small></span>
        <input
          type="checkbox"
          role="switch"
          checked={reproductor.instantanea.normalizar}
          onchange={(e) =>
            reproductor.orden({ tipo: 'normalizar', activo: e.currentTarget.checked })}
        />
      </label>

      <h3>{t.ecualizador}</h3>
      <label class="ajuste interruptor">
        <span class="rotulo">{t.ecualizadorActivo}</span>
        <input
          type="checkbox"
          role="switch"
          checked={eq.activo}
          onchange={(e) => enviarEq({ ...eq, activo: e.currentTarget.checked })}
        />
      </label>
      <label class="ajuste">
        <span class="rotulo">{t.preseleccion}</span>
        <select
          class="campo"
          disabled={!eq.activo}
          value={eq.preseleccion === null ? '' : String(eq.preseleccion)}
          onchange={(e) => elegirPreseleccion(e.currentTarget.value)}
        >
          {#if eq.preseleccion === null}<option value="">{t.personalizado}</option>{/if}
          {#each preselecciones as p, i (p.nombre)}
            <option value={String(i)}>{p.nombre}</option>
          {/each}
        </select>
      </label>
      <div class="bandas" class:apagado={!eq.activo}>
        {#each eq.bandas as valor, k (k)}
          <label class="banda">
            <span class="db">{valor > 0 ? '+' : ''}{valor.toFixed(1)}</span>
            <input
              type="range"
              min="-20"
              max="20"
              step="0.1"
              value={valor}
              disabled={!eq.activo}
              aria-label={t.banda(BANDAS[k] ?? '')}
              oninput={(e) => moverBanda(k, Number(e.currentTarget.value))}
            />
            <span class="hz">{BANDAS[k]}</span>
          </label>
        {/each}
      </div>
    </section>

    <section id="apariencia" aria-labelledby="t-apariencia">
      <h2 id="t-apariencia">{t.apariencia}</h2>
      <h3>{t.tema}</h3>
      <div class="temas" role="radiogroup" aria-label={t.tema}>
        {#each temas as tema (tema.id)}
          {@const elegido = aparienciaActual.actual.tema === tema.id}
          <button
            type="button"
            role="radio"
            class="tema"
            class:elegido
            aria-checked={elegido}
            title={tema.nombre}
            onclick={() => aparienciaActual.cambiar('tema', tema.id)}
          >
            <span
              class="muestra-tema"
              style:--fondo={tema.colores.fondo}
              style:--superficie={tema.colores.superficie}
              style:--acento={tema.colores.acento}
            ></span>
            <span class="nombre-tema">{tema.nombre}</span>
          </button>
        {/each}
      </div>

      <h3>{t.tipografia}</h3>
      <div class="tipografias" role="radiogroup" aria-label={t.tipografia}>
        {#each TIPOGRAFIAS as familia (familia)}
          {@const elegida = aparienciaActual.actual.tipografia === familia}
          <button
            type="button"
            role="radio"
            class="tipografia"
            class:elegido={elegida}
            aria-checked={elegida}
            style:font-family={`'${familia}'`}
            onclick={() => aparienciaActual.cambiar('tipografia', familia)}
          >
            <strong>{familia}</strong>
            <span>{t.muestra}</span>
          </button>
        {/each}
      </div>

      <label class="ajuste">
        <span class="rotulo">{t.escala} · {aparienciaActual.actual.escala}%</span>
        <input
          type="range"
          min="75"
          max="150"
          step="5"
          value={aparienciaActual.actual.escala}
          onchange={(e) => aparienciaActual.cambiar('escala', Number(e.currentTarget.value))}
        />
      </label>
      <label class="ajuste interruptor">
        <span class="rotulo">{t.colorPortada}</span>
        <input
          type="checkbox"
          role="switch"
          checked={aparienciaActual.actual.colorPorPortada}
          onchange={(e) => aparienciaActual.cambiar('colorPorPortada', e.currentTarget.checked)}
        />
      </label>
    </section>

    <section id="acerca" aria-labelledby="t-acerca">
      <h2 id="t-acerca">{t.acercaDe}</h2>
      {#await version then v}
        {#if v}<p>{t.version(v)}</p>{/if}
      {/await}
      <p>{t.licencia}</p>
      <p>{t.terceros}</p>
    </section>
  </div>
</div>

<style>
  .ajustes {
    display: grid;
    grid-template-columns: 11rem minmax(0, 1fr);
    gap: var(--ns-espacio-6);
  }

  .indice {
    position: sticky;
    top: 0;
    align-self: start;
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    padding-top: var(--ns-espacio-7);
  }

  .indice a {
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border-radius: var(--ns-radio-sm);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
    text-decoration: none;
  }

  .indice a:hover {
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
  }

  .contenido {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-5);
    max-width: 56rem;
  }

  h1 {
    margin: 0;
    font-size: var(--ns-texto-xl);
  }

  section {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-low);
    scroll-margin-top: var(--ns-espacio-4);
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
  }

  h3 {
    margin: var(--ns-espacio-3) 0 0;
    font-size: var(--ns-texto-md);
  }

  .ajuste {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-4);
  }

  .rotulo {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    font-size: var(--ns-texto-sm);
    font-weight: 600;
  }

  .rotulo small {
    color: var(--m3c-on-surface-variant);
    font-weight: 400;
  }

  .valor {
    max-width: 60%;
    overflow-wrap: anywhere;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .campo {
    min-width: 14rem;
    height: 2.5rem;
    padding: 0 var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
  }

  input[type='checkbox'] {
    width: 2.75rem;
    height: 1.5rem;
    accent-color: var(--m3c-primary);
  }

  input[type='range'] {
    accent-color: var(--m3c-primary);
  }

  .bandas {
    display: grid;
    grid-template-columns: repeat(10, 1fr);
    gap: var(--ns-espacio-2);
  }

  .bandas.apagado {
    opacity: 0.5;
  }

  .banda {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--ns-espacio-2);
  }

  .banda input {
    writing-mode: vertical-lr;
    direction: rtl;
    height: 8rem;
  }

  .db,
  .hz {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-variant-numeric: tabular-nums;
  }

  .temas {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(8.5rem, 1fr));
    gap: var(--ns-espacio-2);
  }

  .tema,
  .tipografia {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    padding: var(--ns-espacio-2);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-md);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .tema.elegido,
  .tipografia.elegido {
    border-color: var(--m3c-primary);
    border-width: 2px;
  }

  /* La muestra pinta los colores del propio tema: son datos, no estilo. */
  .muestra-tema {
    height: 2.5rem;
    border-radius: var(--ns-radio-sm);
    background: linear-gradient(
      90deg,
      var(--fondo) 0 40%,
      var(--superficie) 40% 75%,
      var(--acento) 75%
    );
  }

  .nombre-tema {
    overflow: hidden;
    font-size: var(--ns-texto-xs);
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .tipografias {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
    gap: var(--ns-espacio-2);
  }

  .tipografia span {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  p {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  @container carcasa (max-width: 60rem) {
    .ajustes {
      grid-template-columns: minmax(0, 1fr);
    }

    .indice {
      display: none;
    }
  }
</style>
