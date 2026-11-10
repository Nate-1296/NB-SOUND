<!--
  @component
  Ajustes > Agregados (F5.1.3, ADR-006): una tarjeta por agregado con qué hace,
  cuánto ocupa y un solo botón. Mientras se descarga se ve el progreso y se puede
  seguir usando la aplicación. Se carga aparte del arranque.
-->
<script lang="ts">
  import { type EstadoAgregado, NsError, type Gpu } from '#lib/core/ipc/index.ts';
  import {
    agregadoInstalar,
    agregadoQuitar,
    agregadosEstado,
    alCambiarLosAgregados,
    gpuDetectada
  } from '#lib/core/ipc/aparte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import { textosAparte } from '#lib/i18n/aparte.ts';

  const t = textosAparte.agregados;
  const titulo = textos.ajustes.agregados;

  let lista = $state<EstadoAgregado[]>([]);
  let fallo = $state<string | null>(null);
  let gpu = $state<Gpu | null>(null);

  async function refrescar() {
    lista = await agregadosEstado();
  }

  $effect(() => {
    void refrescar();
    void gpuDetectada().then((g) => (gpu = g));
    const quitar = alCambiarLosAgregados(() => void refrescar());
    return () => void quitar.then((f) => f());
  });

  // Lo que todavía no se publica no se enseña: un "Todavía no disponible" en
  // Ajustes promete algo que no se puede hacer. Si ya estaba instalado, se ve
  // para poder quitarlo.
  // La aceleración solo se ofrece a quien tiene la tarjeta que aprovecha: son 2 GB
  // que en otro equipo no servirían de nada.
  const visibles = $derived(
    lista.filter(
      (a) => a.instalado || (a.publicado && (a.id !== 'aceleracion' || gpu?.acelerador === 'cuda'))
    )
  );

  const megas = (bytes: number) => Math.round(bytes / 1_048_576);

  async function instalar(a: EstadoAgregado) {
    fallo = null;
    try {
      await agregadoInstalar(a.id);
    } catch (error) {
      const codigo = error instanceof NsError ? error.code : '';
      fallo = t.errores[codigo] ?? t.error;
    }
  }

  async function quitar(a: EstadoAgregado) {
    lista = await agregadoQuitar(a.id);
  }
</script>

{#if visibles.length > 0}
  <section id="agregados" aria-labelledby="t-agregados">
    <h2 id="t-agregados">{titulo}</h2>
    <p>{t.ayuda}</p>
    <ul class="tarjetas">
      {#each visibles as a (a.id)}
        <li class="tarjeta">
          <div class="datos">
            <strong>{t.nombres[a.id]}</strong>
            <span>{t.descripciones[a.id]}</span>
            {#if a.id === 'aceleracion' && gpu && !a.instalado}
              <span class="recomendado">{t.recomendado(gpu.nombre ?? t.gpus[gpu.acelerador])}</span>
            {/if}
            {#if a.error}
              <span class="error" role="alert">{t.errores[a.error] ?? t.error}</span>
            {/if}
          </div>
          <div class="accion">
            {#if a.progreso !== null}
              <progress max="1" value={a.progreso} aria-label={t.nombres[a.id]}></progress>
              <small>{t.descargando(Math.floor(a.progreso * 100))}</small>
            {:else if a.instalado}
              {#if a.actualizable}
                <button type="button" class="boton principal" onclick={() => instalar(a)}>
                  {t.actualizar}
                </button>
              {/if}
              <button type="button" class="boton" onclick={() => quitar(a)}>{t.quitar}</button>
            {:else}
              <button type="button" class="boton principal" onclick={() => instalar(a)}>
                {t.instalar(megas(a.bytes))}
              </button>
            {/if}
          </div>
        </li>
      {/each}
    </ul>
    {#if fallo}<p role="alert" class="error">{fallo}</p>{/if}
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

  p {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .error {
    color: var(--m3c-error);
  }

  .datos .recomendado {
    color: var(--m3c-primary);
    font-weight: 600;
  }

  .tarjetas {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .tarjeta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-4);
    padding: var(--ns-espacio-3) var(--ns-espacio-4);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container);
  }

  .datos {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    min-width: 0;
    font-size: var(--ns-texto-sm);
  }

  .datos span {
    color: var(--m3c-on-surface-variant);
  }

  .accion {
    display: flex;
    flex: none;
    align-items: center;
    gap: var(--ns-espacio-2);
  }

  .accion small {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  progress {
    width: 8rem;
    accent-color: var(--m3c-primary);
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
