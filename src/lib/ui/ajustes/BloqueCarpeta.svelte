<!--
  @component
  Ajustes > Biblioteca: dónde vive tu música. La carpeta, si las canciones están
  en ella, "Comprobar" y "Cambiar".

  Quien formatea, cambia el nombre de su usuario o restaura una copia en otro
  equipo no tiene que hacer nada: al abrir, NB Sound busca la carpeta sola
  (`catalogo/ubicacion.rs`). Esto es para cuando no la encuentra, o para mudarla a
  propósito; elegir otra pasa por `DialogoCarpeta`, que dice antes cuántas
  canciones hay en ella.
-->
<script lang="ts">
  import { ubicacionMusica, type UbicacionMusica } from '#lib/core/ipc/index.ts';
  import { elegirCarpetaMusica, type RevisionCarpeta } from '#lib/core/ipc/aparte.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { textosAparte } from '#lib/i18n/aparte.ts';
  import Icon from '#lib/ui/Icon.svelte';
  import DialogoCarpeta from './DialogoCarpeta.svelte';

  const tc = textosAparte.carpetaMusica;
  const td = textosAparte.dondeVive;

  let u = $state<UbicacionMusica | null>(null);
  let revision = $state<RevisionCarpeta | null>(null);
  let comprobando = $state(false);

  async function leer() {
    u = await ubicacionMusica().catch(() => null);
  }
  void leer();

  async function comprobar() {
    comprobando = true;
    await leer();
    comprobando = false;
    if (u && !u.perdida && u.presentes >= u.total) notificar.exito(td.comprobado);
  }

  async function cambiar() {
    const r = await elegirCarpetaMusica().catch(() => {
      notificar.error(textosAparte.comun.error);
      return null;
    });
    if (!r) return;
    if (r.misma) {
      notificar.informacion(tc.misma);
      return;
    }
    revision = r;
  }

  const faltan = $derived(u ? u.total - u.presentes : 0);
  const clase = $derived(!u?.carpeta || u.total === 0 ? 'neutra' : faltan > 0 ? 'aviso' : 'bien');
</script>

<div class="donde">
  <div class="cabeza">
    <span class="icono {clase}" aria-hidden="true">
      <Icon
        nombre={clase === 'aviso' ? 'advertencia' : clase === 'bien' ? 'correcto' : 'carpeta'}
        tamano={20}
      />
    </span>
    <div class="texto">
      <span class="rotulo">{td.titulo}</span>
      {#if u}
        {#if u.carpeta}<code title={u.carpeta}>{u.carpeta}</code>{/if}
        <span class="estado" role="status">
          {#if !u.carpeta}
            {td.sinCarpeta}
          {:else if u.total === 0}
            {td.vacia}
          {:else if u.perdida}
            {td.perdida}
          {:else if faltan > 0}
            {td.faltan(faltan, u.total)}
          {:else}
            {td.todas(u.total)}
          {/if}
        </span>
      {/if}
    </div>
  </div>
  <p class="ayuda">{td.ayuda}</p>
  <div class="botones">
    <button type="button" class="boton" onclick={comprobar} disabled={comprobando}>
      <Icon nombre="reintentar" tamano={16} />{td.comprobar}
    </button>
    <button type="button" class="boton" class:relleno={u?.perdida} onclick={cambiar}>
      <Icon nombre="carpeta" tamano={16} />{tc.cambiar}
    </button>
  </div>
</div>

<DialogoCarpeta bind:revision puedeMover={!u?.perdida} onhecho={leer} onotra={cambiar} />

<style>
  .donde {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-low);
  }

  .cabeza {
    display: flex;
    align-items: flex-start;
    gap: var(--ns-espacio-3);
    min-width: 0;
  }

  .icono {
    display: grid;
    flex: 0 0 auto;
    place-items: center;
    width: 2.5rem;
    height: 2.5rem;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
  }

  .icono.bien {
    background: var(--m3c-primary-container);
    color: var(--m3c-on-primary-container);
  }

  .icono.aviso {
    background: var(--m3c-error-container);
    color: var(--m3c-on-error-container);
  }

  .texto {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    min-width: 0;
  }

  .rotulo {
    font-size: var(--ns-texto-md);
    font-weight: 600;
  }

  code {
    overflow: hidden;
    color: var(--m3c-on-surface-variant);
    font-family: var(--ns-font-mono);
    font-size: var(--ns-texto-sm);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .estado {
    font-size: var(--ns-texto-sm);
  }

  .ayuda {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    line-height: 1.5;
  }

  .botones {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ns-espacio-2);
  }

  .boton {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    gap: var(--ns-espacio-2);
    height: 2.5rem;
    padding: 0 var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    cursor: pointer;
  }

  .boton:hover:not(:disabled) {
    background: var(--m3c-surface-container-highest);
  }

  .boton:disabled {
    opacity: 0.38;
    cursor: default;
  }

  .boton.relleno {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }
</style>
