<!--
  @component
  Ajustes > Inteligencia artificial (F4.2.7, ADR-009): el desempate por IA,
  apagado de fábrica. El interruptor es el consentimiento del servicio en la
  política de red; el proveedor y el modelo se guardan como preferencias y la
  clave va al llavero del sistema, del que nunca vuelve a la interfaz.
-->
<script lang="ts">
  import type { ProveedorIa } from '$core/ipc';
  import { privacidad } from '$core/privacidad.svelte';
  import { textos } from '$lib/i18n';
  import { textosAparte } from '$lib/i18n/aparte';

  const t = textos.ajustes;
  const a = textosAparte.privacidad;
  const PROVEEDORES: ProveedorIa[] = ['anthropic', 'openai'];

  let modelo = $state('');
  let clave = $state('');
  $effect(() => {
    if (privacidad.ia) modelo = privacidad.ia.modelo;
  });

  const activa = $derived(privacidad.activo('proveedorIa'));

  async function guardarClave() {
    if (!clave.trim()) return;
    // Se borra del campo pase lo que pase: no debe quedarse en la página.
    const nueva = clave;
    clave = '';
    await privacidad.guardarClave(nueva);
  }
</script>

<section id="ia" aria-labelledby="t-ia">
  <h2 id="t-ia">{t.ia}</h2>
  <p>{a.iaAyuda}</p>
  <label class="ajuste">
    <span class="rotulo">
      {a.iaActiva}
      {#if !privacidad.politica.general}<small>{a.iaSinConexion}</small>{/if}
    </span>
    <input
      type="checkbox"
      role="switch"
      disabled={!privacidad.politica.general}
      checked={activa}
      onchange={(e) => privacidad.servicio('proveedorIa', e.currentTarget.checked)}
    />
  </label>

  {#if privacidad.ia}
    {@const ia = privacidad.ia}
    <label class="ajuste">
      <span class="rotulo">{a.proveedor}</span>
      <select
        class="campo"
        value={ia.proveedor}
        onchange={(e) => privacidad.proveedorYModelo(e.currentTarget.value as ProveedorIa, '')}
      >
        {#each PROVEEDORES as p (p)}
          <option value={p}>{a.proveedores[p]}</option>
        {/each}
      </select>
    </label>
    <label class="ajuste">
      <span class="rotulo">{a.modelo}<small>{a.modeloAyuda}</small></span>
      <input
        class="campo"
        maxlength="100"
        spellcheck="false"
        autocomplete="off"
        bind:value={modelo}
        onchange={() => privacidad.proveedorYModelo(ia.proveedor, modelo)}
      />
    </label>
    <div class="ajuste">
      <span class="rotulo">
        {a.clave}
        {#if !ia.llavero}<small>{a.sinLlavero}</small>
        {:else if ia.tieneClave}<small>{a.claveGuardada}</small>{/if}
      </span>
      {#if ia.llavero}
        {#if ia.tieneClave}
          <button type="button" class="boton" onclick={() => privacidad.olvidarClave()}>
            {a.olvidarClave}
          </button>
        {:else}
          <form
            class="clave"
            onsubmit={(e) => {
              e.preventDefault();
              void guardarClave();
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
  {#if privacidad.fallo}<p role="alert" class="fallo">{a.noGuardado}</p>{/if}
</section>

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

  p.fallo {
    color: var(--m3c-error);
  }

  input[type='checkbox'] {
    flex: none;
    width: 2.75rem;
    height: 1.5rem;
    accent-color: var(--m3c-primary);
  }

  .campo {
    min-width: 14rem;
    height: 2.5rem;
    padding: 0 var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
  }

  .clave {
    display: flex;
    gap: var(--ns-espacio-2);
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
