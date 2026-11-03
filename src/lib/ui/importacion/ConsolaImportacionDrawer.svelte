<!--
  @component
  Consola lateral de Añadir música:
  Panel lateral para importar pistas, carpetas, ver progreso activo y estado de la biblioteca.
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { importacion } from '$core/importacion.svelte';
  import { anadirMusica, type Cifras, inicio } from '$core/ipc';
  import { textos } from '$lib/i18n';
  import Icon from '$ui/Icon.svelte';
  import { onMount } from 'svelte';

  const { oncerrar }: { oncerrar: () => void } = $props();

  const t = textos.importacion;
  const p = $derived(importacion.progreso);
  const r = $derived(importacion.resumen);

  let cifras = $state<Cifras | null>(null);
  let importando = $state(false);

  onMount(() => {
    void cargarCifras();
  });

  async function cargarCifras() {
    try {
      const data = await inicio();
      cifras = data.cifras;
    } catch {
      // Ignorar si no está disponible de inmediato
    }
  }

  async function ejecutarAnadirArchivos() {
    importando = true;
    try {
      await anadirMusica(false);
      await cargarCifras();
    } finally {
      importando = false;
    }
  }

  async function ejecutarAnadirCarpeta() {
    importando = true;
    try {
      await anadirMusica(true);
      await cargarCifras();
    } finally {
      importando = false;
    }
  }

  function irAPorRevisar() {
    oncerrar();
    void goto('/por-revisar');
  }

  function alPulsar(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      oncerrar();
    }
  }
</script>

<svelte:window onkeydown={alPulsar} />

<div
  class="fondo-drawer"
  role="presentation"
  onclick={oncerrar}
  onkeydown={(e) => e.key === 'Escape' && oncerrar()}
></div>

<div class="drawer" aria-label={t.anadir} aria-modal="true" role="dialog">
  <header class="drawer-cabecera">
    <div class="drawer-titulos">
      <div class="icono-titulo">
        <Icon nombre="mas" tamano={22} />
        <h2>{t.anadir}</h2>
      </div>
      <p class="drawer-sub">{t.subtitulo}</p>
    </div>
    <button
      type="button"
      class="boton-cerrar"
      onclick={oncerrar}
      aria-label={t.cerrar}
      title={t.cerrar}
    >
      <Icon nombre="cerrar" tamano={20} />
    </button>
  </header>

  <div class="drawer-cuerpo">
    <!-- Acciones de importación -->
    <div class="seccion-acciones">
      <button
        type="button"
        class="tarjeta-accion"
        onclick={ejecutarAnadirArchivos}
        disabled={importando || p.activa}
      >
        <div class="accion-icono">
          <Icon nombre="cancion" tamano={24} />
        </div>
        <div class="accion-info">
          <strong class="accion-titulo">{t.anadirArchivos}</strong>
          <span class="accion-desc">{t.archivosDesc}</span>
        </div>
      </button>

      <button
        type="button"
        class="tarjeta-accion"
        onclick={ejecutarAnadirCarpeta}
        disabled={importando || p.activa}
      >
        <div class="accion-icono">
          <Icon nombre="carpeta" tamano={24} />
        </div>
        <div class="accion-info">
          <strong class="accion-titulo">{t.anadirCarpeta}</strong>
          <span class="accion-desc">{t.carpetaDesc}</span>
        </div>
      </button>
    </div>

    <!-- Progreso activo de importación -->
    {#if p.activa}
      {@const total = Math.max(1, p.total)}
      {@const pct = Math.min(100, Math.round((p.hechos / total) * 100))}
      <div class="tarjeta progreso-caja" role="status" aria-live="polite">
        <div class="progreso-cabecera">
          <span class="seccion-rotulo">{t.catalogando(p.total)}</span>
          <span class="progreso-pct">{pct}%</span>
        </div>
        <div class="barra-riel" role="progressbar" aria-valuenow={pct}>
          <div class="barra-fill" style:width={`${pct}%`}></div>
        </div>
        <div class="progreso-detalle">
          <span>{t.deTotal(p.hechos, p.total)}</span>
          {#if p.actual}
            <span class="archivo-actual" title={p.actual}>{p.actual}</span>
          {/if}
        </div>
      </div>
    {/if}

    <!-- Resumen de la última importación -->
    {#if r}
      <div class="tarjeta resumen-caja" role="status">
        <div class="resumen-icono" class:aviso={r.porRevisar > 0}>
          <Icon nombre={r.porRevisar > 0 ? 'porRevisar' : 'correcto'} tamano={22} />
        </div>
        <div class="resumen-info">
          <strong>{t.resumen(r.importadas, r.porRevisar)}</strong>
          {#if r.sinVerificar > 0}
            <span class="resumen-sub">{t.sinVerificar(r.sinVerificar)}</span>
          {/if}
          {#if r.porRevisar > 0}
            <button type="button" class="enlace-accion" onclick={irAPorRevisar}>
              {t.verPorRevisar}
            </button>
          {/if}
        </div>
        <button
          type="button"
          class="boton-cerrar-resumen"
          aria-label={t.cerrar}
          title={t.cerrar}
          onclick={() => importacion.cerrarResumen()}
        >
          <Icon nombre="cerrar" tamano={16} />
        </button>
      </div>
    {/if}

    <!-- Zona de arrastre explicativa -->
    <div class="tarjeta arrastre-caja" class:activo={importacion.arrastrando}>
      <div class="arrastre-icono">
        <Icon nombre="descargar" tamano={24} />
      </div>
      <div class="arrastre-info">
        <strong class="arrastre-titulo">
          {importacion.arrastrando ? t.arrastrarActivo : t.arrastrarTitulo}
        </strong>
        <p class="arrastre-desc">{t.arrastrarDesc}</p>
      </div>
    </div>

    <!-- Estado y cifras de la biblioteca -->
    <div class="tarjeta cifras-caja">
      <span class="seccion-rotulo">{t.estadoBiblioteca}</span>

      {#if cifras}
        <div class="cifras-grid">
          <div class="cifra-item">
            <span class="cifra-valor">{cifras.pistas}</span>
            <span class="cifra-etiqueta">{t.totalPistas(cifras.pistas)}</span>
          </div>
          <div class="cifra-item">
            <span class="cifra-valor">{cifras.albumes}</span>
            <span class="cifra-etiqueta">{t.totalAlbumes(cifras.albumes)}</span>
          </div>
          <div class="cifra-item">
            <span class="cifra-valor">{cifras.artistas}</span>
            <span class="cifra-etiqueta">{t.totalArtistas(cifras.artistas)}</span>
          </div>
        </div>
      {/if}

      <div class="pendientes-bloque">
        {#if importacion.pendientes > 0}
          <div class="alerta-pendientes">
            <Icon nombre="porRevisar" tamano={18} />
            <span class="pendientes-texto">
              {t.archivosPorRevisar(importacion.pendientes)}
            </span>
          </div>
          <button type="button" class="boton contorno" onclick={irAPorRevisar}>
            <Icon nombre="porRevisar" tamano={16} />
            <span>{t.verPorRevisar}</span>
          </button>
        {:else}
          <div class="insignia-limpio">
            <Icon nombre="comprobado" tamano={18} />
            <span>{t.sinPendientes}</span>
          </div>
        {/if}
      </div>
    </div>

    <!-- Gestión de duplicados -->
    <div class="duplicados-bloque">
      {#await import('$ui/biblioteca/TarjetaDuplicados.svelte') then m}
        <m.default />
      {/await}
    </div>
  </div>
</div>

<style>
  .fondo-drawer {
    position: fixed;
    inset: 0;
    background: color-mix(in srgb, var(--m3c-scrim) 45%, transparent);
    z-index: 100;
  }

  .drawer {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(26rem, 90vw);
    background: var(--m3c-surface-container);
    z-index: 101;
    box-shadow: -4px 0 24px var(--m3c-shadow);
    border-left: 1px solid var(--m3c-outline-variant);
    display: flex;
    flex-direction: column;
    animation: deslizar-izq 200ms var(--ns-curva);
  }

  @keyframes deslizar-izq {
    from {
      transform: translateX(100%);
    }
    to {
      transform: translateX(0);
    }
  }

  .drawer-cabecera {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    padding: var(--ns-espacio-4) var(--ns-espacio-5);
    border-bottom: 1px solid var(--m3c-outline-variant);
    background: var(--m3c-surface-container-high);
  }

  .icono-titulo {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    color: var(--m3c-primary);
  }

  .icono-titulo h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
    font-weight: 700;
    color: var(--m3c-on-surface);
  }

  .drawer-sub {
    margin: var(--ns-espacio-1) 0 0 0;
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
  }

  .boton-cerrar {
    display: grid;
    place-items: center;
    width: 2rem;
    height: 2rem;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
    transition: background-color var(--ns-duracion-corta) var(--ns-curva);
  }

  .boton-cerrar:hover {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
  }

  .drawer-cuerpo {
    flex: 1;
    overflow-y: auto;
    padding: var(--ns-espacio-5);
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
  }

  .seccion-acciones {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
  }

  .tarjeta-accion {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-4);
    padding: var(--ns-espacio-4);
    border-radius: var(--ns-radio-lg);
    border: 1px solid var(--m3c-outline-variant);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
    cursor: pointer;
    text-align: left;
    transition:
      background-color var(--ns-duracion-corta) var(--ns-curva),
      border-color var(--ns-duracion-corta) var(--ns-curva),
      box-shadow var(--ns-duracion-corta) var(--ns-curva);
  }

  .tarjeta-accion:hover:not(:disabled) {
    background: color-mix(
      in srgb,
      var(--m3c-surface-container-high) 85%,
      var(--m3c-primary-container) 15%
    );
    border-color: var(--m3c-primary);
    box-shadow: var(--ns-sombra-1);
  }

  .tarjeta-accion:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .accion-icono {
    display: grid;
    place-items: center;
    width: 2.75rem;
    height: 2.75rem;
    border-radius: var(--ns-radio-md);
    background: var(--m3c-primary-container);
    color: var(--m3c-on-primary-container);
    flex-shrink: 0;
  }

  .accion-info {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
  }

  .accion-titulo {
    font-size: var(--ns-texto-sm);
    font-weight: 700;
    color: var(--m3c-on-surface);
  }

  .accion-desc {
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
  }

  .tarjeta {
    padding: var(--ns-espacio-4);
    border-radius: var(--ns-radio-lg);
    border: 1px solid var(--m3c-outline-variant);
    background: var(--m3c-surface-container-high);
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
  }

  .seccion-rotulo {
    font-size: var(--ns-texto-xs);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-weight: 700;
    color: var(--m3c-primary);
  }

  .progreso-caja {
    gap: var(--ns-espacio-2);
    background: color-mix(
      in srgb,
      var(--m3c-surface-container-high) 90%,
      var(--m3c-primary-container) 10%
    );
  }

  .progreso-cabecera {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .progreso-pct {
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    color: var(--m3c-primary);
  }

  .barra-riel {
    height: 6px;
    background: var(--m3c-surface-container-highest);
    border-radius: var(--ns-radio-pleno);
    overflow: hidden;
  }

  .barra-fill {
    height: 100%;
    background: var(--m3c-primary);
    border-radius: var(--ns-radio-pleno);
    transition: width 200ms linear;
  }

  .progreso-detalle {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .archivo-actual {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .resumen-caja {
    flex-direction: row;
    align-items: flex-start;
    gap: var(--ns-espacio-3);
  }

  .resumen-icono {
    color: var(--m3c-primary);
    flex-shrink: 0;
    margin-top: 0.125rem;
  }

  .resumen-icono.aviso {
    color: var(--m3c-tertiary);
  }

  .resumen-info {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: var(--ns-texto-sm);
  }

  .resumen-sub {
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
  }

  .enlace-accion {
    align-self: flex-start;
    background: none;
    border: none;
    padding: 0;
    color: var(--m3c-primary);
    font-weight: 600;
    font-size: var(--ns-texto-xs);
    cursor: pointer;
    text-decoration: underline;
  }

  .boton-cerrar-resumen {
    display: grid;
    place-items: center;
    width: 1.5rem;
    height: 1.5rem;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
  }

  .arrastre-caja {
    flex-direction: row;
    align-items: center;
    gap: var(--ns-espacio-3);
    border: 1px dashed var(--m3c-outline-variant);
    background: transparent;
    transition:
      border-color var(--ns-duracion-corta) var(--ns-curva),
      background-color var(--ns-duracion-corta) var(--ns-curva);
  }

  .arrastre-caja.activo {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary-container);
    color: var(--m3c-on-primary-container);
  }

  .arrastre-icono {
    color: var(--m3c-primary);
    flex-shrink: 0;
  }

  .arrastre-info {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
  }

  .arrastre-titulo {
    font-size: var(--ns-texto-sm);
    color: var(--m3c-on-surface);
  }

  .arrastre-desc {
    margin: 0;
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
  }

  .cifras-caja {
    gap: var(--ns-espacio-3);
  }

  .cifras-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--ns-espacio-2);
  }

  .cifra-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: var(--ns-espacio-3) var(--ns-espacio-2);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container);
    text-align: center;
  }

  .cifra-valor {
    font-size: var(--ns-texto-lg);
    font-weight: 700;
    color: var(--m3c-on-surface);
  }

  .cifra-etiqueta {
    font-size: var(--ns-texto-xs);
    color: var(--m3c-on-surface-variant);
  }

  .pendientes-bloque {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-1);
  }

  .alerta-pendientes {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    font-size: var(--ns-texto-xs);
    color: var(--m3c-tertiary);
    font-weight: 600;
  }

  .insignia-limpio {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    font-size: var(--ns-texto-xs);
    color: var(--m3c-primary);
    font-weight: 600;
  }

  .boton {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--ns-espacio-2);
    height: 2.25rem;
    padding: 0 var(--ns-espacio-3);
    border-radius: var(--ns-radio-pleno);
    font: inherit;
    font-size: var(--ns-texto-xs);
    font-weight: 600;
    cursor: pointer;
    border: none;
    transition: background-color var(--ns-duracion-corta) var(--ns-curva);
  }

  .boton.contorno {
    background: transparent;
    border: 1px solid var(--m3c-outline-variant);
    color: var(--m3c-on-surface);
  }

  .boton.contorno:hover {
    background: var(--m3c-surface-container-highest);
  }
</style>
