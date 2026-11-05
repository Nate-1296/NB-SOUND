<!--
  @component
  El menú ··· de la barra de reproducción: lo que antes ocupaba sitio junto al
  título (la favorita y "+") y en los extras (el minirreproductor y dónde suena).
  Con ellos fuera, el título, el artista y el álbum largos se leen enteros.

  Es una capa como la de la cola: la canción arriba y sus acciones debajo; "Añadir
  a una playlist" se despliega dentro, sin abrir otra capa encima.
-->
<script lang="ts">
  import { favoritas } from '#lib/core/acciones.svelte.ts';
  import { abrirMinirreproductor, sorprendeme, urlPortada } from '#lib/core/ipc/index.ts';
  import { telefonos } from '#lib/core/movil.svelte.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { reproductor } from '#lib/core/reproductor.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';

  import Icon from './Icon.svelte';
  import MenuAnadir from './playlists/MenuAnadir.svelte';

  interface Props {
    oncerrar: () => void;
  }

  let { oncerrar }: Props = $props();
  const t = textos.reproductor;
  const pista = $derived(reproductor.pista);
  const favorita = $derived(pista ? favoritas.es(pista) : false);
  let anadiendo = $state(false);

  function mini() {
    oncerrar();
    void abrirMinirreproductor();
  }

  function dispositivos() {
    oncerrar();
    window.dispatchEvent(new CustomEvent('ns:cajon', { detail: 'dispositivos' }));
  }

  async function sorpresa() {
    oncerrar();
    const p = await sorprendeme().catch(() => null);
    if (p) notificar.informacion(textos.inicio.sorprendeme(p.titulo, p.artista));
  }
</script>

<div class="menu" role="menu" aria-label={t.masOpciones}>
  {#if pista}
    <header>
      <span class="portada">
        {#if pista.tienePortada}<img src={urlPortada('pista', pista.id, 128)} alt="" />{:else}<Icon
            nombre="cancion"
            tamano={22}
          />{/if}
      </span>
      <span class="datos">
        <strong>{pista.titulo}</strong>
        <small>{pista.artista}</small>
        {#if pista.album}<small>{pista.album}</small>{/if}
      </span>
    </header>

    <button
      type="button"
      role="menuitemcheckbox"
      class="opcion"
      class:activa={favorita}
      aria-checked={favorita}
      onclick={() => pista && favoritas.alternar(pista)}
    >
      <Icon nombre="favorito" tamano={20} />
      {favorita ? t.quitarFavorita : t.marcarFavorita}
    </button>
    <button
      type="button"
      role="menuitem"
      class="opcion"
      aria-expanded={anadiendo}
      onclick={() => (anadiendo = !anadiendo)}
    >
      <Icon nombre="mas" tamano={20} />
      {t.anadirAPlaylist}
      <span class="flecha"><Icon nombre={anadiendo ? 'arriba' : 'abajo'} tamano={16} /></span>
    </button>
    {#if anadiendo}
      <div class="anadir"><MenuAnadir pistas={[pista.id]} {oncerrar} /></div>
    {/if}
    <button type="button" role="menuitem" class="opcion" onclick={mini}>
      <Icon nombre="minirreproductor" tamano={20} />
      {t.mini}
    </button>
  {/if}

  <hr />
  <div class="destino">
    <Icon nombre="volumen" tamano={20} />
    <span class="datos">
      <strong>{t.esteEquipo}</strong>
      <small>
        {telefonos.controlando[0]
          ? t.controlandoDesde(telefonos.controlando[0].nombre)
          : t.sonandoAqui}
      </small>
    </span>
  </div>
  <button type="button" role="menuitem" class="opcion" onclick={dispositivos}>
    <Icon nombre="telefono" tamano={20} />
    {t.abrirDispositivos}
  </button>
  <hr />
  <button type="button" role="menuitem" class="opcion" onclick={sorpresa}>
    <Icon nombre="aleatorio" tamano={20} />
    {t.sorprendeme}
    <kbd>D</kbd>
  </button>
</div>

<style>
  .menu {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    width: min(22rem, 90vw);
    max-height: min(36rem, 75vh);
    overflow-y: auto;
    padding: var(--ns-espacio-2);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
    box-shadow: 0 12px 32px var(--m3c-shadow);
  }

  header {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-2);
    margin-bottom: var(--ns-espacio-1);
  }

  .portada {
    display: grid;
    flex: 0 0 auto;
    place-items: center;
    width: 3.5rem;
    height: 3.5rem;
    overflow: hidden;
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
  }

  .portada img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .datos {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .datos strong,
  .datos small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .datos small {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .opcion {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    width: 100%;
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border: none;
    border-radius: var(--ns-radio-sm);
    background: none;
    color: inherit;
    font: inherit;
    font-size: var(--ns-texto-sm);
    text-align: left;
    cursor: pointer;
  }

  .opcion:hover,
  .opcion:focus-visible {
    background: var(--m3c-surface-container-highest);
  }

  .opcion.activa {
    color: var(--m3c-primary);
  }

  .flecha,
  kbd {
    margin-left: auto;
    color: var(--m3c-on-surface-variant);
  }

  kbd {
    padding: 0 var(--ns-espacio-2);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-sm);
    font-family: var(--ns-font-mono);
    font-size: var(--ns-texto-xs);
  }

  .anadir {
    padding: 0 var(--ns-espacio-2) var(--ns-espacio-2);
  }

  .anadir :global(.menu-anadir),
  .anadir :global(> *) {
    box-shadow: none;
  }

  hr {
    width: 100%;
    margin: var(--ns-espacio-1) 0;
    border: none;
    border-top: 1px solid var(--m3c-outline-variant);
  }

  .destino {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    color: var(--m3c-primary);
  }

  .destino .datos {
    color: var(--m3c-on-surface);
  }
</style>
