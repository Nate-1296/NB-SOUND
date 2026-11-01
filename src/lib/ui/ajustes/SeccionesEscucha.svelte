<!--
  @component
  Ajustes > Reproducción y Apariencia: el ecualizador, la normalización, los
  temas y las tipografías. Se cargan aparte del arranque (`check-paquete`).
-->
<script lang="ts">
  import { aparienciaActual } from '$core/apariencia.svelte';
  import {
    type AjustesEcualizador,
    ecualizador,
    type PreseleccionEcualizador,
    preseleccionesEcualizador
  } from '$core/ipc';
  import { reproductor } from '$core/reproductor.svelte';
  import { textos } from '$lib/i18n';
  import MenuSelector from '$ui/MenuSelector.svelte';
  import type { TemaV1 } from '$ui/temas-v1';

  interface Props {
    seccion?: 'reproduccion' | 'apariencia';
  }
  let { seccion }: Props = $props();

  const t = textos.ajustes;
  const TIPOGRAFIAS = [
    'Inter',
    'Fira Sans',
    'IBM Plex Sans',
    'Atkinson Hyperlegible',
    'Source Sans 3'
  ];
  const BANDAS = ['31', '62', '125', '250', '500', '1k', '2k', '4k', '8k', '16k'];

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

  function esClaro(fondo: string): boolean {
    const hex = fondo.replace('#', '');
    const r = parseInt(hex.slice(0, 2), 16);
    const g = parseInt(hex.slice(2, 4), 16);
    const b = parseInt(hex.slice(4, 6), 16);
    return 0.299 * r + 0.587 * g + 0.114 * b > 130;
  }

  function esEspecial(id: string): boolean {
    return (
      id === 'negro_puro' ||
      id === 'hielo_oled' ||
      id === 'terminal_verde' ||
      id === 'sangre_dragon'
    );
  }

  const temasEspeciales = $derived(temas.filter((tem) => esEspecial(tem.id)));
  const temasClaros = $derived(
    temas.filter((tem) => esClaro(tem.colores.fondo) && !esEspecial(tem.id))
  );
  const temasOscuros = $derived(
    temas.filter((tem) => !esClaro(tem.colores.fondo) && !esEspecial(tem.id))
  );
</script>

{#if !seccion || seccion === 'reproduccion'}
  <section id="reproduccion" aria-labelledby="t-reproduccion">
    <h2 id="t-reproduccion">{t.reproduccion}</h2>
    <label class="ajuste interruptor">
      <span class="rotulo">{t.normalizar}<small>{t.normalizarAyuda}</small></span>
      <input
        type="checkbox"
        role="switch"
        checked={reproductor.instantanea.normalizar}
        onchange={(e) => reproductor.orden({ tipo: 'normalizar', activo: e.currentTarget.checked })}
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
    <div class="ajuste">
      <span class="rotulo">{t.preseleccion}</span>
      <MenuSelector
        deshabilitado={!eq.activo}
        opciones={[
          ...(eq.preseleccion === null ? [{ valor: '', etiqueta: t.personalizado }] : []),
          ...preselecciones.map((p, i) => ({ valor: String(i), etiqueta: p.nombre }))
        ]}
        valor={eq.preseleccion === null ? '' : String(eq.preseleccion)}
        onchange={elegirPreseleccion}
      />
    </div>
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
{/if}

{#if !seccion || seccion === 'apariencia'}
  <section id="apariencia" aria-labelledby="t-apariencia">
    <h2 id="t-apariencia">{t.apariencia}</h2>

    <h3>{t.temasOscuros}</h3>
    <div class="temas" role="radiogroup" aria-label={t.temasOscuros}>
      {#each temasOscuros as tema (tema.id)}
        {@const elegido = aparienciaActual.actual.tema === tema.id}
        <button
          type="button"
          role="radio"
          class="tema"
          class:elegido
          aria-checked={elegido}
          onclick={() => aparienciaActual.cambiar('tema', tema.id)}
        >
          <span
            class="maqueta-tema"
            style:--fondo={tema.colores.fondo}
            style:--superficie={tema.colores.superficie}
            style:--elevado={tema.colores.fondoElevado}
            style:--acento={tema.colores.acento}
            aria-hidden="true"
          >
            <span class="maqueta-lateral"></span>
            <span class="maqueta-principal">
              <span class="maqueta-cabecera"></span>
              <span class="maqueta-cuerpo">
                <span class="maqueta-tarjeta"></span>
                <span class="maqueta-boton"></span>
              </span>
            </span>
          </span>
          <span class="nombre-tema">{tema.nombre}</span>
        </button>
      {/each}
    </div>

    <h3>{t.temasClaros}</h3>
    <div class="temas" role="radiogroup" aria-label={t.temasClaros}>
      {#each temasClaros as tema (tema.id)}
        {@const elegido = aparienciaActual.actual.tema === tema.id}
        <button
          type="button"
          role="radio"
          class="tema"
          class:elegido
          aria-checked={elegido}
          onclick={() => aparienciaActual.cambiar('tema', tema.id)}
        >
          <span
            class="maqueta-tema"
            style:--fondo={tema.colores.fondo}
            style:--superficie={tema.colores.superficie}
            style:--elevado={tema.colores.fondoElevado}
            style:--acento={tema.colores.acento}
            aria-hidden="true"
          >
            <span class="maqueta-lateral"></span>
            <span class="maqueta-principal">
              <span class="maqueta-cabecera"></span>
              <span class="maqueta-cuerpo">
                <span class="maqueta-tarjeta"></span>
                <span class="maqueta-boton"></span>
              </span>
            </span>
          </span>
          <span class="nombre-tema">{tema.nombre}</span>
        </button>
      {/each}
    </div>

    <h3>{t.temasEspeciales}</h3>
    <div class="temas" role="radiogroup" aria-label={t.temasEspeciales}>
      {#each temasEspeciales as tema (tema.id)}
        {@const elegido = aparienciaActual.actual.tema === tema.id}
        <button
          type="button"
          role="radio"
          class="tema"
          class:elegido
          aria-checked={elegido}
          onclick={() => aparienciaActual.cambiar('tema', tema.id)}
        >
          <span
            class="maqueta-tema"
            style:--fondo={tema.colores.fondo}
            style:--superficie={tema.colores.superficie}
            style:--elevado={tema.colores.fondoElevado}
            style:--acento={tema.colores.acento}
            aria-hidden="true"
          >
            <span class="maqueta-lateral"></span>
            <span class="maqueta-principal">
              <span class="maqueta-cabecera"></span>
              <span class="maqueta-cuerpo">
                <span class="maqueta-tarjeta"></span>
                <span class="maqueta-boton"></span>
              </span>
            </span>
          </span>
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
{/if}

<style>
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

  input[type='checkbox'] {
    appearance: none;
    -webkit-appearance: none;
    position: relative;
    width: 3rem;
    height: 1.75rem;
    border: 2px solid var(--m3c-outline);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
    cursor: pointer;
    transition:
      background var(--ns-duracion-corta) var(--ns-curva),
      border-color var(--ns-duracion-corta) var(--ns-curva);
  }

  input[type='checkbox']::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 0.25rem;
    transform: translateY(-50%);
    width: 1rem;
    height: 1rem;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-outline);
    transition:
      transform var(--ns-duracion-corta) var(--ns-curva),
      background var(--ns-duracion-corta) var(--ns-curva),
      width var(--ns-duracion-corta) var(--ns-curva),
      height var(--ns-duracion-corta) var(--ns-curva);
  }

  input[type='checkbox']:checked {
    background: var(--m3c-primary);
    border-color: var(--m3c-primary);
  }

  input[type='checkbox']:checked::before {
    transform: translate(1.25rem, -50%);
    background: var(--m3c-on-primary);
    width: 1.25rem;
    height: 1.25rem;
  }

  input[type='checkbox']:focus-visible {
    outline: 2px solid var(--m3c-primary);
    outline-offset: 2px;
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

  /* La maqueta dibuja la interfaz en miniatura con los colores del tema */
  .maqueta-tema {
    position: relative;
    display: flex;
    width: 100%;
    height: 3.5rem;
    overflow: hidden;
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-sm);
    background: var(--fondo);
  }

  .maqueta-lateral {
    width: 24%;
    height: 100%;
    border-right: 1px solid var(--m3c-outline-variant);
    background: var(--superficie);
  }

  .maqueta-principal {
    display: flex;
    flex: 1 1 auto;
    flex-direction: column;
    min-width: 0;
  }

  .maqueta-cabecera {
    width: 100%;
    height: 30%;
    border-bottom: 1px solid var(--m3c-outline-variant);
    background: var(--elevado);
  }

  .maqueta-cuerpo {
    display: flex;
    flex: 1 1 auto;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-1);
    padding: var(--ns-espacio-1);
  }

  .maqueta-tarjeta {
    flex: 1 1 auto;
    height: 80%;
    border-radius: var(--ns-radio-sm);
    background: var(--superficie);
  }

  .maqueta-boton {
    width: 1rem;
    height: 80%;
    border-radius: var(--ns-radio-sm);
    background: var(--acento);
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
</style>
