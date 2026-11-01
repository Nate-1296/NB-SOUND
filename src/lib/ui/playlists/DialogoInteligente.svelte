<!--
  @component
  Diálogo para crear o editar una lista inteligente viva (F8.2).
-->
<script lang="ts">
  import { NsError } from '$core/ipc';
  import {
    crearPlaylistInteligente,
    editarPlaylistInteligente,
    type OrdenInteligente,
    type ReglaInteligente
  } from '$core/ipc/aparte';
  import { textos } from '$lib/i18n';
  import { esAparte } from '$lib/i18n/es-aparte';
  import MenuSelector from '$ui/MenuSelector.svelte';

  interface Props {
    abierto: boolean;
    editar?: {
      id: number;
      nombre: string;
      descripcion: string | null;
      regla: ReglaInteligente;
    } | null;
    onlisto: (id: number) => void;
    oncerrar: () => void;
  }

  let { abierto, editar = null, onlisto, oncerrar }: Props = $props();
  const t = textos.playlists;
  const ti = esAparte.inteligentes;

  const ANIMOS = [
    'energetica',
    'tranquila',
    'bailable',
    'triste',
    'nocturna',
    'entrenamiento',
    'concentracion',
    'fiesta',
    'feliz',
    'relajada',
    'intensa'
  ] as const;

  const ORDENES: OrdenInteligente[] = [
    'recientes',
    'masEscuchadas',
    'menosEscuchadas',
    'ultimaEscuchaAsc',
    'bpmAsc',
    'bpmDesc',
    'energiaDesc',
    'tituloAsc'
  ];

  let dialogo: HTMLDialogElement | undefined = $state();
  let nombre = $state('');
  let descripcion = $state('');
  let animo = $state('');
  let bpmMin = $state('');
  let bpmMax = $state('');
  let energiaMin = $state('');
  let energiaMax = $state('');
  let instrumental = $state<'cualquiera' | 'con' | 'sin'>('cualquiera');
  let soloFavoritas = $state(false);
  let reproduccionesMin = $state('');
  let reproduccionesMax = $state('');
  let modoEscucha = $state<'cualquiera' | 'reciente' | 'olvidada'>('cualquiera');
  let diasEscucha = $state('30');
  let anioMin = $state('');
  let anioMax = $state('');
  let genero = $state('');
  let orden = $state<OrdenInteligente>('recientes');
  let limite = $state('50');
  let error = $state<string | null>(null);
  let enviando = $state(false);

  function aTexto(n: number | null | undefined, mult = 1): string {
    return n !== null && n !== undefined ? String(Math.round(n * mult)) : '';
  }

  function opcionInstrumental(v: boolean | null | undefined): 'cualquiera' | 'con' | 'sin' {
    if (v === true) return 'con';
    if (v === false) return 'sin';
    return 'cualquiera';
  }

  function cargarEscucha(r: ReglaInteligente | null) {
    if (r?.escuchadaEnDias) {
      modoEscucha = 'reciente';
      diasEscucha = String(r.escuchadaEnDias);
    } else if (r?.sinEscucharDias) {
      modoEscucha = 'olvidada';
      diasEscucha = String(r.sinEscucharDias);
    } else {
      modoEscucha = 'cualquiera';
      diasEscucha = '30';
    }
  }

  function cargarDesdeRegla(r: ReglaInteligente | null) {
    animo = r?.animo ?? '';
    bpmMin = aTexto(r?.bpmMin);
    bpmMax = aTexto(r?.bpmMax);
    energiaMin = aTexto(r?.energiaMin, 100);
    energiaMax = aTexto(r?.energiaMax, 100);
    instrumental = opcionInstrumental(r?.conInstrumental);
    soloFavoritas = r?.soloFavoritas ?? false;
    reproduccionesMin = aTexto(r?.reproduccionesMin);
    reproduccionesMax = aTexto(r?.reproduccionesMax);
    cargarEscucha(r);
    anioMin = aTexto(r?.anioMin);
    anioMax = aTexto(r?.anioMax);
    genero = r?.genero ?? '';
    orden = r?.orden ?? 'recientes';
    limite = String(r?.limite ?? 50);
  }

  $effect(() => {
    if (!dialogo) return;
    if (abierto && !dialogo.open) {
      nombre = editar?.nombre ?? '';
      descripcion = editar?.descripcion ?? '';
      cargarDesdeRegla(editar?.regla ?? null);
      error = null;
      dialogo.showModal();
    } else if (!abierto && dialogo.open) {
      dialogo.close();
    }
  });

  function numOpcional(valor: string): number | null {
    const limpio = valor.trim();
    if (!limpio) return null;
    const n = Number(limpio);
    return Number.isFinite(n) ? n : null;
  }

  function valorInstrumental(): boolean | null {
    if (instrumental === 'con') return true;
    if (instrumental === 'sin') return false;
    return null;
  }

  function construirRegla(): ReglaInteligente {
    const eMin = numOpcional(energiaMin);
    const eMax = numOpcional(energiaMax);
    const dias = numOpcional(diasEscucha);
    return {
      bpmMin: numOpcional(bpmMin),
      bpmMax: numOpcional(bpmMax),
      energiaMin: eMin !== null ? eMin / 100 : null,
      energiaMax: eMax !== null ? eMax / 100 : null,
      animo: animo || null,
      conInstrumental: valorInstrumental(),
      soloFavoritas,
      reproduccionesMin: numOpcional(reproduccionesMin),
      reproduccionesMax: numOpcional(reproduccionesMax),
      escuchadaEnDias: modoEscucha === 'reciente' && dias ? Math.round(dias) : null,
      sinEscucharDias: modoEscucha === 'olvidada' && dias ? Math.round(dias) : null,
      anioMin: numOpcional(anioMin),
      anioMax: numOpcional(anioMax),
      genero: genero.trim() || null,
      orden,
      limite: Math.max(1, Math.min(200, Math.round(numOpcional(limite) ?? 50)))
    };
  }

  function mensajeDeError(causa: unknown): string {
    if (causa instanceof NsError && causa.code === 'NAME_TAKEN') {
      return t.errores.NAME_TAKEN ?? ti.invalida;
    }
    return ti.invalida;
  }

  async function enviar(e: SubmitEvent) {
    e.preventDefault();
    enviando = true;
    error = null;
    try {
      const regla = construirRegla();
      const desc = descripcion.trim() || null;
      if (editar) {
        await editarPlaylistInteligente(editar.id, nombre, desc, regla);
        onlisto(editar.id);
      } else {
        onlisto(await crearPlaylistInteligente(nombre, desc, regla));
      }
    } catch (causa) {
      error = mensajeDeError(causa);
    } finally {
      enviando = false;
    }
  }
</script>

<dialog bind:this={dialogo} onclose={oncerrar} aria-labelledby="titulo-dialogo-inteligente">
  <form onsubmit={enviar}>
    <header class="cabecera">
      <h2 id="titulo-dialogo-inteligente">{editar ? ti.editar : ti.nueva}</h2>
      <p class="ayuda">{ti.ayuda}</p>
    </header>

    <div class="cuerpo-formulario">
      <div class="fila">
        <label>
          <span>{t.nombre}</span>
          <!-- svelte-ignore a11y_autofocus -->
          <input
            bind:value={nombre}
            maxlength="120"
            required
            autofocus
            aria-invalid={error !== null}
          />
        </label>
        <label>
          <span>{t.descripcion}</span>
          <input bind:value={descripcion} maxlength="240" />
        </label>
      </div>

      <div class="fila">
        <label>
          <span>{ti.animo}</span>
          <MenuSelector
            opciones={[
              { valor: '', etiqueta: ti.cualquierAnimo },
              ...ANIMOS.map((a) => ({ valor: a, etiqueta: ti.animos[a] ?? a }))
            ]}
            bind:valor={animo}
          />
        </label>
        <label>
          <span>{ti.instrumental}</span>
          <MenuSelector
            opciones={[
              { valor: 'cualquiera', etiqueta: ti.instrumentalOpciones.cualquiera },
              { valor: 'con', etiqueta: ti.instrumentalOpciones.con },
              { valor: 'sin', etiqueta: ti.instrumentalOpciones.sin }
            ]}
            bind:valor={instrumental}
          />
        </label>
      </div>

      <div class="fila">
        <label>
          <span>{ti.bpmMin}</span>
          <input type="number" min="1" max="400" step="1" bind:value={bpmMin} />
        </label>
        <label>
          <span>{ti.bpmMax}</span>
          <input type="number" min="1" max="400" step="1" bind:value={bpmMax} />
        </label>
        <label>
          <span>{ti.energiaMin}</span>
          <input type="number" min="0" max="100" step="1" bind:value={energiaMin} />
        </label>
        <label>
          <span>{ti.energiaMax}</span>
          <input type="number" min="0" max="100" step="1" bind:value={energiaMax} />
        </label>
      </div>

      <div class="fila">
        <label>
          <span>{ti.reproduccionesMin}</span>
          <input type="number" min="0" step="1" bind:value={reproduccionesMin} />
        </label>
        <label>
          <span>{ti.reproduccionesMax}</span>
          <input type="number" min="0" step="1" bind:value={reproduccionesMax} />
        </label>
        <label>
          <span>{ti.anioMin}</span>
          <input type="number" min="1000" max="9999" step="1" bind:value={anioMin} />
        </label>
        <label>
          <span>{ti.anioMax}</span>
          <input type="number" min="1000" max="9999" step="1" bind:value={anioMax} />
        </label>
      </div>

      <div class="fila">
        <label>
          <span>{ti.frecuencia}</span>
          <MenuSelector
            opciones={[
              { valor: 'cualquiera', etiqueta: ti.frecuenciaOpciones.cualquiera },
              { valor: 'reciente', etiqueta: ti.frecuenciaOpciones.reciente },
              { valor: 'olvidada', etiqueta: ti.frecuenciaOpciones.olvidada }
            ]}
            bind:valor={modoEscucha}
          />
        </label>
        {#if modoEscucha !== 'cualquiera'}
          <label>
            <span>{ti.dias}</span>
            <input type="number" min="1" max="3650" step="1" bind:value={diasEscucha} />
          </label>
        {/if}
        <label>
          <span>{ti.genero}</span>
          <input bind:value={genero} maxlength="80" />
        </label>
      </div>

      <div class="fila">
        <label>
          <span>{ti.orden}</span>
          <MenuSelector
            opciones={ORDENES.map((o) => ({ valor: o, etiqueta: ti.ordenes[o] }))}
            bind:valor={orden}
          />
        </label>
        <label>
          <span>{ti.limite}</span>
          <input type="number" min="1" max="200" step="1" required bind:value={limite} />
        </label>
      </div>

      <label class="casilla">
        <input type="checkbox" bind:checked={soloFavoritas} />
        <span>{ti.soloFavoritas}</span>
      </label>

      {#if error}<p class="error" role="alert">{error}</p>{/if}
    </div>

    <footer class="pie">
      <button type="button" class="boton" onclick={oncerrar}>{t.cancelar}</button>
      <button type="submit" class="boton principal" disabled={enviando}>
        {editar ? t.guardar : t.crear}
      </button>
    </footer>
  </form>
</dialog>

<style>
  dialog {
    width: min(38rem, 92vw);
    max-height: 85vh;
    padding: 0;
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
    overflow: hidden;
  }

  dialog::backdrop {
    background: var(--m3c-scrim);
    opacity: 0.5;
  }

  form {
    display: flex;
    flex-direction: column;
    max-height: 85vh;
    height: 100%;
    overflow: hidden;
  }

  .cabecera {
    flex: 0 0 auto;
    padding: var(--ns-espacio-4) var(--ns-espacio-5);
    border-bottom: 1px solid var(--m3c-outline-variant);
  }

  .cuerpo-formulario {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    padding: var(--ns-espacio-4) var(--ns-espacio-5);
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
  }

  .pie {
    flex: 0 0 auto;
    display: flex;
    justify-content: flex-end;
    gap: var(--ns-espacio-2);
    padding: var(--ns-espacio-3) var(--ns-espacio-5);
    border-top: 1px solid var(--m3c-outline-variant);
    background: var(--m3c-surface-container-high);
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
  }

  .ayuda {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .fila {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(8.5rem, 1fr));
    gap: var(--ns-espacio-3);
  }

  label {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    font-size: var(--ns-texto-xs);
  }

  .casilla {
    flex-direction: row;
    align-items: center;
    gap: var(--ns-espacio-2);
    font-size: var(--ns-texto-sm);
    cursor: pointer;
  }

  input:not([type='checkbox']) {
    height: 2.25rem;
    padding: 0 var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
  }

  .error {
    margin: 0;
    color: var(--m3c-error);
    font-size: var(--ns-texto-sm);
  }

  .boton {
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

  .boton.principal {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }
</style>
