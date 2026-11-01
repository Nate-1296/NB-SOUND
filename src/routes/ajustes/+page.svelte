<!--
  Ajustes, rediseñado con patrón Master-Detail (ADR-007, DIS-01, COMP-02).
  Navegación reactiva con panel lateral y renderizado exclusivo de la sección activa.
-->
<script lang="ts">
  import { aparienciaActual } from '$core/apariencia.svelte';
  import { carpetaMusica, perfilCambiarFoto, salud } from '$core/ipc';
  import { textos } from '$lib/i18n';
  import Icon from '$ui/Icon.svelte';
  import type { NombreDeIcono } from '$ui/iconos';

  const t = textos.ajustes;

  type SeccionAjustes =
    | 'biblioteca'
    | 'reproduccion'
    | 'apariencia'
    | 'dispositivos'
    | 'agregados'
    | 'privacidad'
    | 'ia'
    | 'acerca';

  const SECCIONES: { id: SeccionAjustes; etiqueta: string; icono: NombreDeIcono }[] = [
    { id: 'biblioteca', etiqueta: t.biblioteca, icono: 'biblioteca' },
    { id: 'reproduccion', etiqueta: t.reproduccion, icono: 'ecualizador' },
    { id: 'apariencia', etiqueta: t.apariencia, icono: 'apariencia' },
    { id: 'dispositivos', etiqueta: t.dispositivos, icono: 'telefono' },
    { id: 'agregados', etiqueta: t.agregados, icono: 'descargar' },
    { id: 'privacidad', etiqueta: t.privacidad, icono: 'privacidad' },
    { id: 'ia', etiqueta: t.ia, icono: 'dj' },
    { id: 'acerca', etiqueta: t.acercaDe, icono: 'informacion' }
  ];

  let seccionActiva = $state<SeccionAjustes>('biblioteca');

  const version = salud()
    .then((informe) => informe.version)
    .catch(() => null);
  const carpeta = carpetaMusica().catch(() => null);

  let nombre = $state(aparienciaActual.actual.nombreUsuario ?? '');
</script>

<div class="ajustes">
  <nav class="indice" aria-label={t.secciones}>
    {#each SECCIONES as s (s.id)}
      <button
        type="button"
        class="pestana-seccion"
        class:activa={seccionActiva === s.id}
        aria-current={seccionActiva === s.id ? 'page' : undefined}
        onclick={() => (seccionActiva = s.id)}
      >
        <Icon nombre={s.icono} tamano={18} />
        <span>{s.etiqueta}</span>
      </button>
    {/each}
  </nav>

  <div class="contenido">
    <h1>{t.titulo}</h1>

    {#if seccionActiva === 'biblioteca'}
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
        <div class="ajuste">
          <span class="rotulo">{t.fotoPerfil}<small>{t.fotoPerfilAyuda}</small></span>
          <button type="button" class="boton-cambiar-foto" onclick={() => void perfilCambiarFoto()}>
            <Icon nombre="editar" tamano={16} />
            <span>{t.cambiarFoto}</span>
          </button>
        </div>
        {#await import('$ui/copia/BloqueCopia.svelte') then m}
          <m.default />
        {/await}
        {#await import('$ui/biblioteca/TarjetaDuplicados.svelte') then m}
          <m.default />
        {/await}
      </section>
    {:else if seccionActiva === 'reproduccion'}
      {#await import('$ui/ajustes/SeccionesEscucha.svelte') then m}
        <m.default seccion="reproduccion" />
      {/await}
    {:else if seccionActiva === 'apariencia'}
      {#await import('$ui/ajustes/SeccionesEscucha.svelte') then m}
        <m.default seccion="apariencia" />
      {/await}
    {:else if seccionActiva === 'dispositivos'}
      {#await import('$ui/dispositivos/SeccionDispositivos.svelte') then m}
        <m.default />
      {/await}
    {:else if seccionActiva === 'agregados'}
      {#await import('$ui/agregados/SeccionAgregados.svelte') then m}
        <m.default />
      {/await}
    {:else if seccionActiva === 'privacidad'}
      {#await import('$ui/privacidad/SeccionesPrivacidad.svelte') then m}
        <m.default seccion="privacidad" />
      {/await}
    {:else if seccionActiva === 'ia'}
      {#await import('$ui/privacidad/SeccionesPrivacidad.svelte') then m}
        <m.default seccion="ia" />
      {/await}
    {:else if seccionActiva === 'acerca'}
      <section id="acerca" aria-labelledby="t-acerca">
        <h2 id="t-acerca">{t.acercaDe}</h2>
        {#await version then v}
          {#if v}<p>{t.version(v)}</p>{/if}
        {/await}
        {#await import('$ui/ajustes/BloqueActualizacion.svelte') then m}
          <m.default />
        {/await}
        <p>{t.licencia}</p>
        <p>{t.terceros}</p>
        <p>{t.modelos}</p>
      </section>
    {/if}
  </div>
</div>

<style>
  .ajustes {
    display: grid;
    grid-template-columns: 14rem minmax(0, 1fr);
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

  .pestana-seccion {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border: 1px solid transparent;
    border-radius: var(--ns-radio-md);
    background: none;
    color: var(--m3c-on-surface-variant);
    font: inherit;
    font-size: var(--ns-texto-sm);
    text-align: left;
    cursor: pointer;
    transition:
      background 150ms ease,
      color 150ms ease;
  }

  .pestana-seccion:hover {
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
  }

  .pestana-seccion.activa {
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
    font-weight: 600;
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

  .boton-cambiar-foto {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    min-height: 2.5rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 500;
    cursor: pointer;
    transition:
      background var(--ns-duracion-corta) var(--ns-curva),
      border-color var(--ns-duracion-corta) var(--ns-curva);
  }

  .boton-cambiar-foto:hover {
    background: var(--m3c-surface-container-high);
    border-color: var(--m3c-outline);
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
      position: static;
      flex-direction: row;
      overflow-x: auto;
      padding-top: 0;
      padding-bottom: var(--ns-espacio-2);
      white-space: nowrap;
      gap: var(--ns-espacio-2);
      scrollbar-width: thin;
      -webkit-overflow-scrolling: touch;
      overscroll-behavior-x: contain;
    }

    .pestana-seccion {
      flex-shrink: 0;
    }
  }
</style>
