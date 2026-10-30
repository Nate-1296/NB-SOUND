<!--
  @component
  Dónde suena (F3.3.2), en la barra de reproducción, como el selector de
  dispositivos de Spotify Connect que imita NB Sound Mobile.

  El protocolo 1 no tiene orden del equipo al teléfono: el traspaso al teléfono se
  hace desde el teléfono (`remote-control.md`, "Transición de destino"). Aquí se ve
  qué suena en este equipo y qué teléfono lo controla, y se puede conectar uno.
-->
<script lang="ts">
  import { telefonos } from '$core/movil.svelte';
  import { textos } from '$lib/i18n';

  import DialogoConectar from './DialogoConectar.svelte';
  import Icon from '../Icon.svelte';

  const t = textos.reproductor;
  let capa: HTMLDivElement | undefined = $state();
  let boton: HTMLButtonElement | undefined = $state();
  let abierta = $state(false);
  let conectando = $state(false);

  const controlando = $derived(telefonos.controlando[0]?.nombre ?? null);

  function alternar() {
    if (!capa || !boton) return;
    if (abierta) {
      capa.hidePopover();
      return;
    }
    const r = boton.getBoundingClientRect();
    capa.style.right = `${Math.max(8, window.innerWidth - r.right)}px`;
    capa.style.bottom = `${window.innerHeight - r.top + 8}px`;
    capa.showPopover();
  }

  function conectar() {
    capa?.hidePopover();
    conectando = true;
  }
</script>

<button
  type="button"
  bind:this={boton}
  class="control conmutador"
  class:activo={controlando !== null}
  aria-label={controlando ? t.controlandoDesde(controlando) : t.destino}
  aria-expanded={abierta}
  title={controlando ? t.controlandoDesde(controlando) : t.destino}
  onclick={alternar}
>
  <Icon nombre="telefono" tamano={20} />
</button>
<div
  class="capa"
  popover="auto"
  bind:this={capa}
  ontoggle={(e) => (abierta = e.newState === 'open')}
>
  <h2>{t.destino}</h2>
  <div class="fila actual">
    <Icon nombre="volumen" tamano={22} />
    <span>
      <strong>{t.esteEquipo}</strong>
      <small>{t.sonandoAqui}</small>
    </span>
  </div>
  {#each telefonos.controlando as tel (tel.id)}
    <div class="fila">
      <Icon nombre="telefono" tamano={22} />
      <span>
        <strong>{tel.nombre}</strong>
        <small>{t.controlandoDesde(tel.nombre)}</small>
      </span>
    </div>
  {/each}
  <p>{t.escucharEnElTelefono}</p>
  <button type="button" class="boton" onclick={conectar}>{t.conectarTelefono}</button>
</div>

<DialogoConectar abierto={conectando} oncerrar={() => (conectando = false)} />

<style>
  /* Las medidas de los demás controles de la barra. */
  .control {
    display: grid;
    place-items: center;
    width: 2.25rem;
    height: 2.25rem;
    border: 1px solid transparent;
    border-radius: var(--ns-radio-sm);
    background: none;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
    transition: background-color var(--ns-duracion-corta) var(--ns-curva);
  }

  .control:hover {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
  }

  .control.activo {
    border-color: var(--m3c-primary);
    color: var(--m3c-primary);
  }

  .capa {
    position: fixed;
    inset: auto;
    width: 18rem;
    margin: 0;
    padding: var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
  }

  h2 {
    margin: 0 0 var(--ns-espacio-3);
    font-size: var(--ns-texto-md);
  }

  .fila {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-2);
    border-radius: var(--ns-radio-md);
  }

  .fila.actual {
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
  }

  .fila span {
    display: flex;
    flex-direction: column;
  }

  .fila strong {
    font-size: var(--ns-texto-sm);
  }

  .fila small {
    font-size: var(--ns-texto-xs);
    opacity: 0.8;
  }

  p {
    margin: var(--ns-espacio-3) 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .boton {
    width: 100%;
    height: 2.25rem;
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }
</style>
