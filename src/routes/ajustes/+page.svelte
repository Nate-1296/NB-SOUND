<!--
  Ajustes, rediseñado (ADR-007): una sola página con sus secciones en orden y un
  índice para saltar entre ellas. Hay Biblioteca, Reproducción, Apariencia,
  Dispositivos, Agregados, Privacidad y servicios en línea, Inteligencia
  artificial y Acerca de. Todo cambio se guarda al momento, sin botón de
  guardar.
-->
<script lang="ts">
  import { aparienciaActual } from '$core/apariencia.svelte';
  import { carpetaMusica, salud } from '$core/ipc';
  import { textos } from '$lib/i18n';

  const t = textos.ajustes;

  const version = salud()
    .then((informe) => informe.version)
    .catch(() => null);
  const carpeta = carpetaMusica().catch(() => null);

  let nombre = $state(aparienciaActual.actual.nombreUsuario ?? '');
</script>

<div class="ajustes">
  <nav class="indice" aria-label={t.secciones}>
    <a href="#biblioteca">{t.biblioteca}</a>
    <a href="#reproduccion">{t.reproduccion}</a>
    <a href="#apariencia">{t.apariencia}</a>
    <a href="#dispositivos">{t.dispositivos}</a>
    <a href="#agregados">{t.agregados}</a>
    <a href="#privacidad">{t.privacidad}</a>
    <a href="#ia">{t.ia}</a>
    <a href="#acerca">{t.acercaDe}</a>
  </nav>

  <div class="contenido">
    <h1>{t.titulo}</h1>

    <section id="biblioteca" aria-labelledby="t-biblioteca">
      <h2 id="t-biblioteca">{t.biblioteca}</h2>
      <div class="ajuste">
        <span class="rotulo">{t.carpeta}</span>
        {#await carpeta then c}
          <code class="valor">{c ?? t.sinCarpeta}</code>
        {/await}
      </div>
      <label class="ajuste">
        <span class="rotulo">{t.nombre}<small>{t.nombreAyuda}</small></span>
        <input
          class="campo"
          maxlength="60"
          bind:value={nombre}
          onchange={() => aparienciaActual.cambiar('nombreUsuario', nombre.trim() || null)}
        />
      </label>
      {#await import('$ui/copia/BloqueCopia.svelte') then m}
        <m.default />
      {/await}
    </section>

    {#await import('$ui/ajustes/SeccionesEscucha.svelte') then m}
      <m.default />
    {/await}

    {#await import('$ui/dispositivos/SeccionDispositivos.svelte') then m}
      <m.default />
    {/await}
    {#await import('$ui/agregados/SeccionAgregados.svelte') then m}
      <m.default />
    {/await}
    {#await import('$ui/privacidad/SeccionesPrivacidad.svelte') then m}
      <m.default />
    {/await}

    <section id="acerca" aria-labelledby="t-acerca">
      <h2 id="t-acerca">{t.acercaDe}</h2>
      {#await version then v}
        {#if v}<p>{t.version(v)}</p>{/if}
      {/await}
      <p>{t.licencia}</p>
      <p>{t.terceros}</p>
      <p>{t.modelos}</p>
    </section>
  </div>
</div>

<style>
  .ajustes {
    display: grid;
    grid-template-columns: 11rem minmax(0, 1fr);
    gap: var(--ns-espacio-6);
  }

  .indice {
    position: sticky;
    top: 0;
    align-self: start;
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    padding-top: var(--ns-espacio-7);
  }

  .indice a {
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border-radius: var(--ns-radio-sm);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
    text-decoration: none;
  }

  .indice a:hover {
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
  }

  .contenido {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-5);
    max-width: 56rem;
  }

  h1 {
    margin: 0;
    font-size: var(--ns-texto-xl);
  }

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

  .rotulo small {
    color: var(--m3c-on-surface-variant);
    font-weight: 400;
  }

  .valor {
    max-width: 60%;
    overflow-wrap: anywhere;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
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

  p {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  @container carcasa (max-width: 60rem) {
    .ajustes {
      grid-template-columns: minmax(0, 1fr);
    }

    .indice {
      display: none;
    }
  }
</style>
