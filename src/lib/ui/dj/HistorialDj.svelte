<!--
  @component
  El historial del DJ (F6.1.6): las sesiones pedidas, de la más reciente a la más
  antigua, con una búsqueda que no distingue tildes ni mayúsculas.
-->
<script lang="ts">
  import { onDestroy } from 'svelte';
  import { alCambiarDj, djEliminar, djHistorial, type FilaHistorial } from '$core/ipc/dj';
  import { formatoTiempo } from '$core/reproductor.svelte';
  import { textosDj } from '$lib/i18n/dj';
  import Icon from '$ui/Icon.svelte';

  interface Props {
    seleccionada: number | null;
    onver: (sesionId: number) => void;
    /** Para volver a leerlo cuando la vista sabe que cambió. */
    version: number;
  }

  let { seleccionada, onver, version }: Props = $props();
  const t = textosDj.historial;

  let texto = $state('');
  let filas = $state<FilaHistorial[]>([]);
  let leidas = $state(false);
  let propia = $state(0);

  $effect(() => {
    const consulta = texto;
    void version;
    void propia;
    void djHistorial(consulta, '').then((f) => {
      if (consulta === texto) {
        filas = f;
        leidas = true;
      }
    });
  });

  const dejar = alCambiarDj(() => (propia += 1));
  onDestroy(() => void dejar.then((f) => f()));

  async function eliminar(id: number) {
    await djEliminar(id);
    propia += 1;
  }

  function fecha(iso: string): string {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('es', { dateStyle: 'medium' });
  }
</script>

<section class="historial" aria-labelledby="t-historial">
  <h2 id="t-historial">{t.titulo}</h2>
  <label class="busqueda">
    <Icon nombre="buscar" tamano={18} />
    <input type="search" placeholder={t.buscar} aria-label={t.buscar} bind:value={texto} />
  </label>

  {#if leidas && filas.length === 0}
    <p class="vacio">{texto.trim() ? t.nada : t.vacio}</p>
  {/if}

  <ul>
    {#each filas as f (f.id)}
      <li class:elegida={f.id === seleccionada}>
        <button type="button" class="fila" onclick={() => onver(f.id)}>
          <strong>{f.peticion}</strong>
          <small>
            {t.estados[f.estado] ?? f.estado} · {fecha(f.creadaEn)} ·
            {t.resumen(f.totalPistas, formatoTiempo(f.duracionSeg))}
          </small>
        </button>
        <button
          type="button"
          class="icono"
          aria-label={t.eliminarSesion(f.peticion)}
          title={t.eliminar}
          onclick={() => eliminar(f.id)}
        >
          <Icon nombre="borrar" tamano={16} />
        </button>
      </li>
    {/each}
  </ul>
</section>

<style>
  .historial {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
  }

  .busqueda {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    height: 2.5rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface-variant);
  }

  .busqueda:focus-within {
    border-color: var(--m3c-primary);
  }

  .busqueda input {
    flex: 1;
    border: none;
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
  }

  .vacio {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  ul {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    display: flex;
    align-items: center;
    border-radius: var(--ns-radio-sm);
  }

  li.elegida {
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
  }

  .fila {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    min-width: 0;
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border: none;
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .fila strong,
  .fila small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .fila small {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .icono {
    display: grid;
    place-items: center;
    width: 2.5rem;
    height: 2.5rem;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
  }

  .icono:hover {
    background: var(--m3c-surface-container);
  }
</style>
