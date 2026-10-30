<!--
  @component
  Ajustes > Dispositivos (F3.3.1, ADR-007): el interruptor que deja conectarse a
  los teléfonos, el botón para conectar uno nuevo y la lista de los conectados,
  con quitar. Sustituye a la vista Sincronización de la V1.
-->
<script lang="ts">
  import { telefonos } from '$core/movil.svelte';
  import { textos } from '$lib/i18n';
  import Icon from '$ui/Icon.svelte';

  import DialogoConectar from './DialogoConectar.svelte';

  const t = textos.ajustes;
  let conectando = $state(false);
  let quitando = $state<{ id: number; nombre: string } | null>(null);
  let confirmar: HTMLDialogElement | undefined = $state();

  $effect(() => {
    void telefonos.refrescar();
  });

  $effect(() => {
    if (!confirmar) return;
    if (quitando && !confirmar.open) confirmar.showModal();
    else if (!quitando && confirmar.open) confirmar.close();
  });

  /** La V1 guardaba algunas fechas sin zona (`2026-05-24 05:45:57`), en UTC. */
  function fecha(iso: string): string {
    const normal = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso.replace(' ', 'T')}Z`;
    const d = new Date(normal);
    return Number.isNaN(d.getTime())
      ? iso
      : d.toLocaleString('es', { dateStyle: 'medium', timeStyle: 'short' });
  }

  async function quitarConfirmado() {
    if (!quitando) return;
    const { id } = quitando;
    quitando = null;
    await telefonos.quitar(id);
  }
</script>

<section id="dispositivos" aria-labelledby="t-dispositivos">
  <h2 id="t-dispositivos">{t.dispositivos}</h2>
  <label class="ajuste interruptor">
    <span class="rotulo">
      {t.permitirTelefonos}
      <small>
        {t.permitirAyuda}
        {#if telefonos.estado.direccion}{t.escuchandoEn(telefonos.estado.direccion)}{/if}
      </small>
    </span>
    <input
      type="checkbox"
      role="switch"
      checked={telefonos.estado.activo}
      onchange={(e) => telefonos.permitir(e.currentTarget.checked)}
    />
  </label>
  <div>
    <button type="button" class="boton principal" onclick={() => (conectando = true)}>
      <Icon nombre="telefono" tamano={18} />
      {t.conectarTelefono}
    </button>
  </div>

  {#if telefonos.lista.length === 0}
    <p>{t.sinTelefonos}</p>
  {:else}
    <ul class="telefonos">
      {#each telefonos.lista as tel (tel.id)}
        <li>
          <Icon nombre="telefono" tamano={22} />
          <span class="datos">
            <strong>{tel.nombre}</strong>
            <small class:vivo={tel.conectado}>
              {#if tel.controlando}
                {t.controlando}
              {:else if tel.conectado}
                {t.conectadoAhora}
              {:else if tel.ultimaConexion}
                {t.ultimaConexion(fecha(tel.ultimaConexion))}
              {:else}
                {t.sinConexiones}
              {/if}
            </small>
          </span>
          <button
            type="button"
            class="boton"
            aria-label={t.quitarTelefono(tel.nombre)}
            onclick={() => (quitando = { id: tel.id, nombre: tel.nombre })}
          >
            {t.quitar}
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<DialogoConectar abierto={conectando} oncerrar={() => (conectando = false)} />

<dialog
  bind:this={confirmar}
  class="confirmar"
  onclose={() => (quitando = null)}
  aria-labelledby="titulo-quitar"
>
  {#if quitando}
    <h2 id="titulo-quitar">{t.quitarTelefono(quitando.nombre)}</h2>
    <p>{t.quitarAyuda(quitando.nombre)}</p>
    <div class="botones">
      <button type="button" class="boton" onclick={() => (quitando = null)}>{t.cancelar}</button>
      <button type="button" class="boton peligro" onclick={quitarConfirmado}>{t.quitar}</button>
    </div>
  {/if}
</dialog>

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

  .rotulo small,
  p {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
    font-weight: 400;
  }

  input[type='checkbox'] {
    width: 2.75rem;
    height: 1.5rem;
    accent-color: var(--m3c-primary);
  }

  .telefonos {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .telefonos li {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container);
  }

  .datos {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-width: 0;
  }

  .datos strong {
    overflow: hidden;
    font-size: var(--ns-texto-sm);
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .datos small {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .datos small.vivo {
    color: var(--m3c-primary);
  }

  .boton {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
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

  .boton.peligro {
    border-color: var(--m3c-error);
    background: var(--m3c-error);
    color: var(--m3c-on-error);
  }

  .confirmar {
    width: min(26rem, 90vw);
    padding: var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
  }

  .confirmar::backdrop {
    background: var(--m3c-scrim);
    opacity: 0.5;
  }

  .confirmar h2 {
    margin-bottom: var(--ns-espacio-3);
  }

  .botones {
    display: flex;
    justify-content: flex-end;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-4);
  }
</style>
