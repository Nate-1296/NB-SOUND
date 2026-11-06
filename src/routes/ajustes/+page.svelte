<!--
  Ajustes, rediseñado con patrón Master-Detail (ADR-007, DIS-01, COMP-02).
  Navegación reactiva con panel lateral y renderizado exclusivo de la sección activa.
-->
<script lang="ts">
  import { aparienciaActual } from '#lib/core/apariencia.svelte.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { perfilCambiarFoto, salud, urlFotoPerfil } from '#lib/core/ipc/index.ts';
  import { textos } from '#lib/i18n/index.ts';
  import Icon from '#lib/ui/Icon.svelte';
  import type { NombreDeIcono } from '#lib/ui/iconos.ts';

  const t = textos.ajustes;

  type SeccionAjustes =
    | 'biblioteca'
    | 'reproduccion'
    | 'apariencia'
    | 'agregados'
    | 'permisos'
    | 'privacidad'
    | 'ia'
    | 'acerca';

  const SECCIONES: { id: SeccionAjustes; etiqueta: string; icono: NombreDeIcono }[] = [
    { id: 'biblioteca', etiqueta: t.biblioteca, icono: 'biblioteca' },
    { id: 'reproduccion', etiqueta: t.reproduccion, icono: 'ecualizador' },
    { id: 'apariencia', etiqueta: t.apariencia, icono: 'apariencia' },
    { id: 'agregados', etiqueta: t.agregados, icono: 'descargar' },
    { id: 'permisos', etiqueta: textos.permisos.titulo, icono: 'red' },
    { id: 'privacidad', etiqueta: t.privacidad, icono: 'privacidad' },
    { id: 'ia', etiqueta: t.ia, icono: 'dj' },
    { id: 'acerca', etiqueta: t.acercaDe, icono: 'informacion' }
  ];

  let seccionActiva = $state<SeccionAjustes>('biblioteca');

  const version = salud()
    .then((informe) => informe.version)
    .catch(() => null);

  let nombre = $state(aparienciaActual.actual.nombreUsuario ?? '');

  // La foto se ve aquí también: cambiarla sin verla no decía si había funcionado.
  let sinFoto = $state(false);
  let versionFoto = $state(0);

  async function cambiarFoto() {
    try {
      if (await perfilCambiarFoto()) {
        sinFoto = false;
        versionFoto = Date.now();
      }
    } catch {
      notificar.error(textos.tuMusica.fotoInvalida);
    }
  }
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
        {#await import('#lib/ui/ajustes/BloqueCarpeta.svelte') then m}
          <m.default />
        {/await}
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
          <span class="foto-fila">
            <span class="foto" aria-hidden="true">
              {#if !sinFoto}
                <img src={urlFotoPerfil(versionFoto)} alt="" onerror={() => (sinFoto = true)} />
              {:else}
                <Icon nombre="artista" tamano={20} />
              {/if}
            </span>
            <button type="button" class="boton-cambiar-foto" onclick={cambiarFoto}>
              <Icon nombre="editar" tamano={16} />
              <span>{t.cambiarFoto}</span>
            </button>
          </span>
        </div>
        {#await import('#lib/ui/copia/BloqueCopia.svelte') then m}
          <m.default />
        {/await}
      </section>
    {:else if seccionActiva === 'reproduccion'}
      {#await import('#lib/ui/ajustes/SeccionesEscucha.svelte') then m}
        <m.default seccion="reproduccion" />
      {/await}
    {:else if seccionActiva === 'apariencia'}
      {#await import('#lib/ui/ajustes/SeccionesEscucha.svelte') then m}
        <m.default seccion="apariencia" />
      {/await}
    {:else if seccionActiva === 'agregados'}
      {#await import('#lib/ui/agregados/SeccionAgregados.svelte') then m}
        <m.default />
      {/await}
    {:else if seccionActiva === 'permisos'}
      {#await import('#lib/ui/permisos/SeccionPermisos.svelte') then m}
        <m.default />
      {/await}
    {:else if seccionActiva === 'privacidad'}
      {#await import('#lib/ui/privacidad/SeccionesPrivacidad.svelte') then m}
        <m.default seccion="privacidad" />
      {/await}
    {:else if seccionActiva === 'ia'}
      {#await import('#lib/ui/privacidad/SeccionesPrivacidad.svelte') then m}
        <m.default seccion="ia" />
      {/await}
    {:else if seccionActiva === 'acerca'}
      <section id="acerca" aria-labelledby="t-acerca">
        <h2 id="t-acerca">{t.acercaDe}</h2>
        <div class="marca">
          <img
            src={`/logos/logo_${aparienciaActual.actual.tema}.png`}
            alt=""
            onerror={(e) => ((e.currentTarget as HTMLImageElement).src = '/logo.png')}
          />
          <div>
            <strong>{t.producto}</strong>
            {#await version then v}
              {#if v}<span>{t.version(v)}</span>{/if}
            {/await}
          </div>
        </div>
        {#await import('#lib/ui/ajustes/BloqueActualizacion.svelte') then m}
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
  .marca {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-4);
  }

  .marca img {
    width: 4rem;
    height: 4rem;
    border-radius: var(--ns-radio-pleno);
  }

  .marca div {
    display: flex;
    flex-direction: column;
  }

  .marca strong {
    font-size: var(--ns-texto-xl);
  }

  .marca span {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

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
    min-height: 2.75rem;
    padding: 0 var(--ns-espacio-4);
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface-variant);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 500;
    text-align: left;
    cursor: pointer;
    transition:
      background-color var(--ns-duracion-corta) var(--ns-curva),
      color var(--ns-duracion-corta) var(--ns-curva);
  }

  .pestana-seccion:hover {
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
  }

  .pestana-seccion.activa {
    background: var(--m3c-primary-container);
    color: var(--m3c-on-primary-container);
    font-weight: 700;
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

  .foto-fila {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
  }

  .foto {
    display: grid;
    place-items: center;
    width: 2.5rem;
    height: 2.5rem;
    overflow: hidden;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
  }

  .foto img {
    width: 100%;
    height: 100%;
    object-fit: cover;
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
