<!--
  @component
  Ajustes > Privacidad y servicios en línea (F4.2.7, ADR-007 y ADR-009): el
  interruptor general y uno por servicio, cada uno con lo que envía. De fábrica
  todo está apagado.
-->
<script lang="ts">
  import { privacidad, SERVICIOS_EN_LINEA } from '$core/privacidad.svelte';
  import { textos } from '$lib/i18n';
  import { textosAparte } from '$lib/i18n/aparte';

  const t = textos.ajustes;
  const a = textosAparte.privacidad;
</script>

<section id="privacidad" aria-labelledby="t-privacidad">
  <h2 id="t-privacidad">{t.privacidad}</h2>
  <p>{a.privacidadAyuda}</p>
  <label class="ajuste">
    <span class="rotulo">{a.conexion}<small>{a.conexionAyuda}</small></span>
    <input
      type="checkbox"
      role="switch"
      checked={privacidad.politica.general}
      onchange={(e) => privacidad.general(e.currentTarget.checked)}
    />
  </label>
  <ul class="servicios" class:apagado={!privacidad.politica.general}>
    {#each SERVICIOS_EN_LINEA as servicio (servicio)}
      <li>
        <label class="ajuste">
          <span class="rotulo">
            {a.servicios[servicio].nombre}<small>{a.servicios[servicio].envia}</small>
          </span>
          <input
            type="checkbox"
            role="switch"
            disabled={!privacidad.politica.general}
            checked={privacidad.activo(servicio)}
            onchange={(e) => privacidad.servicio(servicio, e.currentTarget.checked)}
          />
        </label>
      </li>
    {/each}
  </ul>
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

  .servicios {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    margin: 0;
    padding: var(--ns-espacio-3) 0 0;
    border-top: 1px solid var(--m3c-outline-variant);
    list-style: none;
  }

  .servicios.apagado {
    opacity: 0.6;
  }
</style>
