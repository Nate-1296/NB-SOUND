<!--
  @component
  Pedir una sesión (F6.1.6): lo que se quiere escuchar, en palabras, y cuánto
  dura. La sesión empieza a sonar en cuanto tiene su primer bloque; el resto se
  construye mientras suena.
-->
<script lang="ts">
  import { djPedir } from '$core/ipc/dj';
  import { textosDj } from '$lib/i18n/dj';
  import Icon from '$ui/Icon.svelte';
  import Spinner from '$ui/Spinner.svelte';

  interface Props {
    onpedida: (sesionId: number) => void;
  }

  let { onpedida }: Props = $props();
  const t = textosDj.pedir;
  const DURACIONES = [30, 60, 90, 120];

  let texto = $state('');
  let minutos = $state(60);
  let ocupado = $state(false);
  let aviso = $state<string | null>(null);

  function alternarChip(chip: string) {
    const actual = texto.trim();
    if (!actual) {
      texto = chip;
      return;
    }
    const partes = actual
      .split(',')
      .map((p) => p.trim())
      .filter(Boolean);
    const indice = partes.findIndex((p) => p.toLowerCase() === chip.toLowerCase());
    if (indice >= 0) {
      partes.splice(indice, 1);
      texto = partes.join(', ');
    } else {
      texto = `${actual}, ${chip}`;
    }
  }

  async function pedir() {
    const peticion = texto.trim();
    if (!peticion) {
      aviso = t.vacia;
      return;
    }
    ocupado = true;
    aviso = null;
    try {
      const r = await djPedir(peticion, minutos);
      if (r.sinCandidatas) {
        aviso = t.sinCandidatas;
      } else {
        onpedida(r.sesionId);
      }
    } catch {
      aviso = t.error;
    } finally {
      ocupado = false;
    }
  }
</script>

<form
  class="pedir"
  onsubmit={(e) => {
    e.preventDefault();
    void pedir();
  }}
>
  <label class="campo">
    <span class="rotulo">{t.etiqueta}</span>
    <textarea rows="2" maxlength="500" placeholder={t.ejemplo} bind:value={texto} disabled={ocupado}
    ></textarea>
  </label>

  <div class="fila">
    <span class="rotulo">{t.duracion}</span>
    {#each DURACIONES as d (d)}
      <button
        type="button"
        class="ficha"
        class:activa={minutos === d}
        aria-pressed={minutos === d}
        disabled={ocupado}
        onclick={() => (minutos = d)}
      >
        {t.minutos(d)}
      </button>
    {/each}
    <button type="submit" class="boton" disabled={ocupado}>
      {#if ocupado}
        <Spinner tamano={16} />
      {:else}
        <Icon nombre="dj" tamano={16} />
      {/if}
      {ocupado ? t.creando : t.crear}
    </button>
  </div>

  <div class="bloque-categorias">
    {#each t.categoriasSugeridas as cat (cat.nombre)}
      <div class="grupo-chips">
        <span class="rotulo-categoria">{cat.nombre}:</span>
        <div class="chips">
          {#each cat.chips as chip (chip)}
            {@const activa = texto.toLowerCase().includes(chip.toLowerCase())}
            <button
              type="button"
              class="ficha chip"
              class:activa
              aria-pressed={activa}
              disabled={ocupado}
              onclick={() => alternarChip(chip)}
            >
              {chip}
            </button>
          {/each}
        </div>
      </div>
    {/each}
  </div>

  <div class="fila">
    <span class="rotulo">{t.ideas}</span>
    {#each t.sugerencias as s (s)}
      <button type="button" class="ficha" disabled={ocupado} onclick={() => (texto = s)}>
        {s}
      </button>
    {/each}
  </div>

  {#if ocupado}
    <div class="bloque-carga" role="status" aria-live="polite">
      <div class="indicador-carga">
        <Spinner tamano={22} />
        <span class="texto-carga">{t.creando}</span>
      </div>
      <div class="esqueletos">
        <div class="esqueleto-tarjeta"></div>
        <div class="esqueleto-tarjeta"></div>
        <div class="esqueleto-tarjeta"></div>
      </div>
    </div>
  {/if}

  {#if aviso}<p class="aviso" role="status">{aviso}</p>{/if}
</form>

<style>
  .pedir {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-low);
  }

  .campo {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
  }

  textarea {
    padding: var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    resize: vertical;
  }

  textarea:focus {
    border-color: var(--m3c-primary);
  }

  .fila {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--ns-espacio-2);
  }

  .rotulo {
    margin-right: var(--ns-espacio-2);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-weight: 600;
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

  .ficha:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .ficha.activa {
    border-color: var(--m3c-primary);
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
    font-weight: 700;
  }

  .bloque-categorias {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-1);
    padding: var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container);
  }

  .grupo-chips {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--ns-espacio-2);
  }

  .rotulo-categoria {
    min-width: 5.5rem;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ns-espacio-1);
  }

  .ficha.chip {
    height: 1.75rem;
    padding: 0 var(--ns-espacio-2);
  }

  .boton {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    height: 2.5rem;
    margin-left: auto;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-primary);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    cursor: pointer;
  }

  .boton:disabled {
    opacity: 0.38;
    cursor: default;
  }

  .bloque-carga {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-4);
    border: 1px dashed var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container);
  }

  .indicador-carga {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
  }

  .texto-carga {
    color: var(--m3c-on-surface);
    font-size: var(--ns-texto-sm);
    font-weight: 600;
  }

  .esqueletos {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    width: 100%;
  }

  .esqueleto-tarjeta {
    height: 3rem;
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-high);
    opacity: 0.5;
  }

  .aviso {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }
</style>
