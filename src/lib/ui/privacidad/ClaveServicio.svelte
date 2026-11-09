<!--
  @component
  La clave de un servicio del catálogo (hoy, AcoustID), debajo de su
  interruptor en Privacidad. Va al llavero del sistema y nunca vuelve a la
  interfaz: aquí solo se ve si hay una.
-->
<script lang="ts">
  import type { ServicioConClave } from '#lib/core/ipc/aparte.ts';
  import { privacidad } from '#lib/core/privacidad.svelte.ts';
  import { textosAparte } from '#lib/i18n/aparte.ts';

  const { servicio }: { servicio: ServicioConClave } = $props();
  const a = textosAparte.privacidad;

  let clave = $state('');
  const claves = $derived(privacidad.claves);
  const guardada = $derived(claves?.acoustId ?? false);

  async function guardar() {
    if (!clave.trim()) return;
    // Se borra del campo pase lo que pase: no debe quedarse en la página.
    const nueva = clave;
    clave = '';
    await privacidad.guardarClaveServicio(servicio, nueva);
  }
</script>

{#if claves}
  <div class="clave-servicio">
    <span class="rotulo">
      {a.clave}
      {#if !claves.llavero}<small>{a.sinLlavero}</small>
      {:else if guardada}<small>{a.claveGuardada}</small>
      {:else}<small>{a.claveServicio[servicio]}</small>{/if}
    </span>
    {#if claves.llavero}
      {#if guardada}
        <button
          type="button"
          class="boton"
          onclick={() => privacidad.olvidarClaveServicio(servicio)}
        >
          {a.olvidarClave}
        </button>
      {:else}
        <form
          onsubmit={(e) => {
            e.preventDefault();
            void guardar();
          }}
        >
          <input
            class="campo"
            type="password"
            autocomplete="off"
            spellcheck="false"
            placeholder={a.claveNueva}
            aria-label={a.clave}
            bind:value={clave}
          />
          <button type="submit" class="boton principal" disabled={!clave.trim()}>
            {a.guardarClave}
          </button>
        </form>
      {/if}
    {/if}
  </div>
{/if}

<style>
  .clave-servicio {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-2) var(--ns-espacio-4);
    padding: var(--ns-espacio-2) 0 0 var(--ns-espacio-4);
  }

  .rotulo {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    font-size: var(--ns-texto-sm);
    font-weight: 600;
  }

  small {
    color: var(--m3c-on-surface-variant);
    font-weight: 400;
  }

  form {
    display: flex;
    gap: var(--ns-espacio-2);
  }

  .campo {
    height: 2.5rem;
    padding: 0 var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
  }

  .boton {
    display: inline-flex;
    flex: none;
    align-items: center;
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
