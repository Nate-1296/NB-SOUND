<!--
  @component
  Por revisar (F4.2.4, enmienda de ADR-007): lo que no entró solo, cada archivo
  como "No importado" con su motivo en lenguaje llano y sus acciones. Sustituye a
  Cuarentena y Revisión de la V1.

  Importar tal como está avisa antes de lo que le faltará; descartar lo manda a
  la papelera del sistema.
-->
<script lang="ts">
  import { importacion } from '$core/importacion.svelte';
  import {
    type Pendiente,
    porRevisarDescartar,
    porRevisarImportar,
    porRevisarListar,
    porRevisarReintentar
  } from '$core/ipc';
  import { duracionLarga } from '$core/formato';
  import { textos } from '$lib/i18n';
  import Icon from '$ui/Icon.svelte';

  const t = textos.porRevisar;

  let lista = $state<Pendiente[]>([]);
  let seleccion = $state(new Set<number>());
  let abierto = $state<number | null>(null);
  let confirmando = $state<Pendiente[] | null>(null);
  let ocupado = $state(false);
  let error = $state(false);
  let dialogo: HTMLDialogElement | undefined = $state();

  async function cargar() {
    lista = await porRevisarListar();
    seleccion = new Set([...seleccion].filter((id) => lista.some((p) => p.id === id)));
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

  async function hacer(trabajo: () => Promise<unknown>) {
    ocupado = true;
    error = false;
    try {
      await trabajo();
    } catch {
      error = true;
    } finally {
      ocupado = false;
      await cargar();
    }
  }

  function importarTalCual(ps: Pendiente[]) {
    confirmando = ps;
  }

  async function confirmar() {
    const ps = confirmando ?? [];
    confirmando = null;
    await hacer(async () => {
      for (const p of ps) await porRevisarImportar(p.id, null);
    });
  }

  function alternar(id: number) {
    const s = new Set(seleccion);
    if (s.has(id)) s.delete(id);
    else s.add(id);
    seleccion = s;
  }

  const faltas = $derived(
    [...new Set((confirmando ?? []).flatMap((p) => p.faltaria))].map((f) => t.falta[f] ?? f)
  );
</script>

<section class="vista">
  <header class="cabecera">
    <div>
      <h1>{t.titulo}</h1>
      <p class="cuenta">{t.cuenta(lista.length)}</p>
    </div>
    {#if lista.length > 0}
      <div class="lote">
        <button
          type="button"
          class="boton"
          disabled={ocupado}
          onclick={() => importarTalCual(lista)}
        >
          {t.importarTodas}
        </button>
        <button
          type="button"
          class="boton"
          disabled={ocupado || seleccion.size === 0}
          onclick={() => hacer(() => porRevisarDescartar([...seleccion]))}
        >
          {t.descartarSeleccionadas}
        </button>
      </div>
    {/if}
  </header>

  {#if error}<p class="error" role="alert">{t.error}</p>{/if}

  {#if lista.length === 0}
    <p class="vacio">{t.vacio}</p>
  {:else}
    <ul class="lista">
      {#each lista as p (p.id)}
        <li class:abierto={abierto === p.id}>
          <div class="fila">
            <input
              type="checkbox"
              checked={seleccion.has(p.id)}
              aria-label={t.seleccionar(p.nombre)}
              onchange={() => alternar(p.id)}
            />
            <button
              type="button"
              class="resumen"
              aria-expanded={abierto === p.id}
              onclick={() => (abierto = abierto === p.id ? null : p.id)}
            >
              <span class="nombre">{p.nombre}</span>
              <span class="motivo"
                ><span class="insignia">{t.noImportado}</span>{t.causas[p.causa] ?? p.causa}</span
              >
            </button>
            <Icon nombre={abierto === p.id ? 'arriba' : 'abajo'} tamano={18} />
          </div>
          {#if abierto === p.id}
            <div class="detalle">
              <div class="comparador">
                <div class="columna">
                  <h3>{t.tuArchivo}</h3>
                  <p><strong>{p.titulo ?? t.sinDatos}</strong></p>
                  <p>{p.artista ?? t.sinDatos}</p>
                  <p>{p.album ?? t.sinDatos}</p>
                  {#if p.duracionSeg}<p>{duracionLarga(p.duracionSeg)}</p>{/if}
                </div>
                {#if p.candidatos.length > 0}
                  <div class="columna candidatos">
                    <h3>{t.candidatos}</h3>
                    {#each p.candidatos as c, i (i)}
                      <div class="candidato">
                        <div>
                          <p><strong>{c.titulo}</strong></p>
                          <p>{c.artista}</p>
                          <p>
                            {c.album}{#if c.anio}
                              · {c.anio}{/if}{#if c.tipo}
                              · {c.tipo}{/if}
                          </p>
                          {#if c.duracionSeg}<p>{duracionLarga(c.duracionSeg)}</p>{/if}
                        </div>
                        <button
                          type="button"
                          class="boton principal"
                          disabled={ocupado}
                          onclick={() => hacer(() => porRevisarImportar(p.id, i))}
                        >
                          {t.elegir}
                        </button>
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>
              <div class="acciones">
                <button
                  type="button"
                  class="boton principal"
                  disabled={ocupado}
                  onclick={() => importarTalCual([p])}
                >
                  {t.importarTalCual}
                </button>
                <button
                  type="button"
                  class="boton"
                  disabled={ocupado}
                  onclick={() => hacer(() => porRevisarReintentar(p.id))}
                >
                  {t.buscarDeNuevo}
                </button>
                <button
                  type="button"
                  class="boton"
                  disabled={ocupado}
                  onclick={() => hacer(() => porRevisarDescartar([p.id]))}
                >
                  {t.descartar}
                </button>
              </div>
            </div>
          {/if}
        </li>
      {/each}
    </ul>
    <p class="nota">{t.papelera}</p>
  {/if}
</section>

<dialog bind:this={dialogo} onclose={() => (confirmando = null)} aria-labelledby="titulo-tal-cual">
  <h2 id="titulo-tal-cual">{t.importarTalCual}</h2>
  {#if faltas.length > 0}
    <p>{t.faltara} {faltas.join(', ')}.</p>
  {:else}
    <p>{t.nadaFalta}</p>
  {/if}
  <div class="botones">
    <button type="button" class="boton" onclick={() => (confirmando = null)}>{t.cancelar}</button>
    <button type="button" class="boton principal" onclick={confirmar}>{t.confirmar}</button>
  </div>
</dialog>

<style>
  .vista {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
    max-width: 64rem;
  }

  .cabecera {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--ns-espacio-4);
  }

  h1 {
    margin: 0;
    font-size: var(--ns-texto-xl);
  }

  .cuenta,
  .vacio,
  .nota {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .lote,
  .acciones,
  .botones {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ns-espacio-2);
  }

  .lista {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-low);
  }

  .fila {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
  }

  .resumen {
    display: flex;
    flex: 1;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--ns-espacio-1);
    min-width: 0;
    padding: 0;
    border: none;
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .nombre {
    overflow: hidden;
    max-width: 100%;
    font-weight: 600;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .motivo {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .insignia {
    padding: 0 var(--ns-espacio-2);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-error-container);
    color: var(--m3c-on-error-container);
    font-size: var(--ns-texto-xs);
    font-weight: 600;
  }

  .detalle {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
    padding: 0 var(--ns-espacio-4) var(--ns-espacio-4);
  }

  .comparador {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
    gap: var(--ns-espacio-4);
  }

  .columna {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
  }

  h3 {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .columna p,
  dialog p {
    margin: 0;
    font-size: var(--ns-texto-sm);
  }

  .candidato {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container);
  }

  .boton {
    height: 2.25rem;
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

  .boton:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .error {
    margin: 0;
    color: var(--m3c-error);
  }

  input[type='checkbox'] {
    accent-color: var(--m3c-primary);
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

  .botones {
    justify-content: flex-end;
    margin-top: var(--ns-espacio-4);
  }

  @container carcasa (max-width: 50rem) {
    .comparador {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
