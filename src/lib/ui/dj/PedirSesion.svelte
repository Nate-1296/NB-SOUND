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
    <textarea rows="2" maxlength="500" placeholder={t.ejemplo} bind:value={texto}></textarea>
  </label>

  <div class="fila">
    <span class="rotulo">{t.duracion}</span>
    {#each DURACIONES as d (d)}
      <button
        type="button"
        class="ficha"
        class:activa={minutos === d}
        aria-pressed={minutos === d}
        onclick={() => (minutos = d)}
      >
        {t.minutos(d)}
      </button>
    {/each}
    <button type="submit" class="boton" disabled={ocupado}>
      <Icon nombre="dj" tamano={16} />{ocupado ? t.creando : t.crear}
    </button>
  </div>

  <div class="fila">
    <span class="rotulo">{t.ideas}</span>
    {#each t.sugerencias as s (s)}
      <button type="button" class="ficha" onclick={() => (texto = s)}>{s}</button>
    {/each}
  </div>

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

  .aviso {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }
</style>
