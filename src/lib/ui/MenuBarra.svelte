<!--
  @component
  El menú ··· de la barra de reproducción: lo que antes ocupaba sitio junto al
  título (la favorita y "+") y en los extras (el minirreproductor y dónde suena).
  Con ellos fuera, el título, el artista y el álbum largos se leen enteros.

  Cuando la barra es estrecha (`anchos.ts`), lo que no cabe en ella aparece aquí
  arriba, en una fila de botones: aleatorio, repetir, letras, karaoke y pantalla
  completa. Esconder un control nunca lo quita.

  Es una capa como la de la cola: la canción arriba y sus acciones debajo; "Añadir
  a una playlist" se despliega dentro, sin abrir otra capa encima.
-->
<script lang="ts">
  import { favoritas } from '#lib/core/acciones.svelte.ts';
  import { abrirMinirreproductor, sorprendeme, urlPortada } from '#lib/core/ipc/index.ts';
  import { telefonos } from '#lib/core/movil.svelte.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { pantalla } from '#lib/core/pantalla.svelte.ts';
  import { reproductor } from '#lib/core/reproductor.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';

  import type { TramoDeBarra } from './anchos';
  import Icon from './Icon.svelte';
  import MenuAnadir from './playlists/MenuAnadir.svelte';

  interface Props {
    oncerrar: () => void;
    /** Abre el diálogo de conectar un teléfono, que vive fuera de este menú. */
    onconectar: () => void;
    /** El tramo de la barra: decide qué controles viven aquí. */
    tramo: TramoDeBarra;
    onletras: () => void;
  }

  let { oncerrar, onconectar, tramo, onletras }: Props = $props();
  const t = textos.reproductor;
  const i = $derived(reproductor.instantanea);
  const hayPista = $derived(i.pistaId !== null);
  const pista = $derived(reproductor.pista);
  const favorita = $derived(pista ? favoritas.es(pista) : false);
  let anadiendo = $state(false);

  function mini() {
    oncerrar();
    void abrirMinirreproductor();
  }

  // Dónde suena, como el botón que tenía la barra: este equipo y los teléfonos que
  // lo controlan, aquí mismo. No abre la consola de dispositivos entera.
  function conectar() {
    oncerrar();
    onconectar();
  }

  async function sorpresa() {
    oncerrar();
    const p = await sorprendeme().catch(() => null);
    if (p) notificar.informacion(textos.inicio.sorprendeme(p.titulo, p.artista));
  }
</script>

<div class="menu" role="menu" aria-label={t.masOpciones}>
  {#if tramo !== 'amplia'}
    <div class="controles" role="group" aria-label={t.region}>
      {#if tramo === 'estrecha'}
        <button
          type="button"
          class="control"
          class:activo={i.aleatorio}
          aria-label={t.aleatorio}
          aria-pressed={i.aleatorio}
          title={t.aleatorio}
          onclick={reproductor.alternarAleatorio}
        >
          <Icon nombre="aleatorio" tamano={20} />
        </button>
        <button
          type="button"
          class="control"
          class:activo={i.repeticion !== 'ninguno'}
          aria-label={t.repeticion[i.repeticion as keyof typeof t.repeticion] ?? t.repetir}
          title={t.repeticion[i.repeticion as keyof typeof t.repeticion] ?? t.repetir}
          onclick={reproductor.rotarRepeticion}
        >
          <Icon nombre={i.repeticion === 'uno' ? 'repetirUna' : 'repetir'} tamano={20} />
        </button>
        <button
          type="button"
          class="control"
          class:activo={i.karaokeActivo}
          aria-label={t.karaoke}
          aria-pressed={i.karaokeActivo}
          title={t.karaoke}
          disabled={!hayPista || !i.karaokeDisponible}
          onclick={reproductor.alternarKaraoke}
        >
          <Icon nombre="microfono" tamano={20} />
        </button>
      {/if}
      <button
        type="button"
        class="control"
        aria-label={t.letras}
        title={t.letras}
        disabled={!hayPista}
        onclick={() => {
          oncerrar();
          onletras();
        }}
      >
        <Icon nombre="letras" tamano={20} />
      </button>
      <button
        type="button"
        class="control"
        class:activo={pantalla.completa}
        aria-label={pantalla.completa ? t.salirPantallaCompleta : t.pantallaCompleta}
        aria-pressed={pantalla.completa}
        title={pantalla.completa ? t.salirPantallaCompleta : t.pantallaCompleta}
        onclick={() => {
          oncerrar();
          void pantalla.alternar();
        }}
      >
        <Icon
          nombre={pantalla.completa ? 'salirPantallaCompleta' : 'pantallaCompleta'}
          tamano={20}
        />
      </button>
    </div>
    <hr />
  {/if}
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
  <span class="rotulo">{t.destino}</span>
  <div class="destino">
    <Icon nombre="volumen" tamano={20} />
    <span class="datos">
      <strong>{t.esteEquipo}</strong>
      <small>{t.sonandoAqui}</small>
    </span>
  </div>
  {#each telefonos.controlando as tel (tel.id)}
    <div class="destino">
      <Icon nombre="telefono" tamano={20} />
      <span class="datos">
        <strong>{tel.nombre}</strong>
        <small>{t.controlandoDesde(tel.nombre)}</small>
      </span>
    </div>
  {/each}
  <p class="nota">{t.escucharEnElTelefono}</p>
  <button type="button" role="menuitem" class="opcion" onclick={conectar}>
    <Icon nombre="telefono" tamano={20} />
    {t.conectarTelefono}
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

  .controles {
    display: flex;
    justify-content: space-around;
    gap: var(--ns-espacio-1);
    padding: var(--ns-espacio-1) 0;
  }

  .control {
    position: relative;
    display: grid;
    place-items: center;
    width: 2.5rem;
    height: 2.5rem;
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
  }

  .control:hover:not(:disabled),
  .control:focus-visible {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
  }

  .control:disabled {
    opacity: 0.38;
    cursor: default;
  }

  .control.activo {
    background: color-mix(in srgb, var(--m3c-primary) 12%, transparent);
    color: var(--m3c-primary);
  }

  .control.activo::after {
    content: '';
    position: absolute;
    bottom: 2px;
    left: 50%;
    width: 4px;
    height: 4px;
    border-radius: var(--ns-radio-pleno);
    background: currentColor;
    translate: -50% 0;
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

  .rotulo {
    padding: var(--ns-espacio-1) var(--ns-espacio-3) 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .nota {
    margin: 0;
    padding: 0 var(--ns-espacio-3);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    line-height: 1.4;
  }
</style>
