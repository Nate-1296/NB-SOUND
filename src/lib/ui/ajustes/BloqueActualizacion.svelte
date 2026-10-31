<!--
  @component
  Ajustes > Acerca de > Buscar actualizaciones (F7.2.2). Nunca se busca sola: el
  botón es el consentimiento del servicio, y con la conexión general apagada no
  sale nada. Lo que se instala lleva la firma de NB Sound, que se comprueba en
  Rust antes de tocar nada. Se carga aparte del arranque.
-->
<script lang="ts">
  import { NsError } from '$core/ipc';
  import { actualizacionBuscar, actualizacionInstalar } from '$core/ipc/aparte';
  import type { Actualizacion } from '$lib/bindings';
  import { textosAparte } from '$lib/i18n/aparte';

  const t = textosAparte.actualizacion;

  let ocupado = $state(false);
  let nueva = $state<Actualizacion | null>(null);
  let mensaje = $state<string | null>(null);

  function explicar(error: unknown): string {
    const codigo = error instanceof NsError ? error.code : '';
    if (codigo === 'NETWORK_DISABLED') return t.sinConexion;
    if (codigo === 'COMPONENT_UNAVAILABLE') return t.noDisponible;
    if (codigo === 'INTEGRITY_MISMATCH') return t.firma;
    return t.error;
  }

  async function buscar() {
    ocupado = true;
    mensaje = t.buscando;
    try {
      nueva = await actualizacionBuscar();
      mensaje = nueva ? t.disponible(nueva.version) : t.alDia;
    } catch (error) {
      mensaje = explicar(error);
    } finally {
      ocupado = false;
    }
  }

  async function instalar() {
    ocupado = true;
    mensaje = t.instalando;
    try {
      await actualizacionInstalar();
    } catch (error) {
      mensaje = explicar(error);
    } finally {
      ocupado = false;
    }
  }
</script>

<div class="botones">
  {#if nueva}
    <button type="button" class="boton principal" disabled={ocupado} onclick={instalar}>
      {t.instalar}
    </button>
  {:else}
    <button type="button" class="boton" disabled={ocupado} onclick={buscar}>{t.buscar}</button>
  {/if}
</div>
{#if mensaje}<p role="status">{mensaje}</p>{/if}
{#if nueva?.notas}<p class="notas">{nueva.notas}</p>{/if}

<style>
  p {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .notas {
    white-space: pre-line;
  }

  .botones {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ns-espacio-2);
  }

  .boton {
    flex: none;
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

  .boton:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
