<!--
  @component
  Ajustes > Dispositivos (F3.3.1, ADR-007): el interruptor que deja conectarse a
  los teléfonos, el botón para conectar uno nuevo y la lista de los conectados,
  con quitar. Sustituye a la vista Sincronización de la V1.
-->
<script lang="ts">
  import { type PlaylistResumen, playlistsListar } from '$core/ipc';
  import {
    copiaDispositivoEjecutar,
    type EstructuraCarpetas,
    type OrigenCopia
  } from '$core/ipc/aparte';
  import { telefonos } from '$core/movil.svelte';
  import { textos } from '$lib/i18n';
  import { textosAparte } from '$lib/i18n/aparte';
  import Icon from '$ui/Icon.svelte';
  import MenuSelector from '$ui/MenuSelector.svelte';

  import BloqueFiesta from './BloqueFiesta.svelte';
  import DialogoConectar from './DialogoConectar.svelte';

  const t = textos.ajustes;
  const tc = textosAparte.copiaDispositivo;
  let conectando = $state(false);
  let quitando = $state<{ id: number; nombre: string } | null>(null);
  let confirmar: HTMLDialogElement | undefined = $state();

  let origen = $state<OrigenCopia>('favoritas');
  let playlistId = $state<number | null>(null);
  let playlists = $state<PlaylistResumen[]>([]);
  let estructura = $state<EstructuraCarpetas>('artistaAlbum');
  let incrustarPortada = $state(true);
  let convertirAWav = $state(false);
  let copiando = $state(false);
  let mensajeCopia = $state<string | null>(null);

  $effect(() => {
    void telefonos.refrescar();
    void playlistsListar({ texto: null, categoria: null, orden: 'recientes' }).then((lista) => {
      playlists = lista;
      if (playlistId === null && lista[0]) {
        playlistId = lista[0].id;
      }
    });
  });

  async function iniciarCopiaDispositivo() {
    if (copiando) return;
    if (origen === 'playlist' && playlistId === null) return;
    copiando = true;
    mensajeCopia = tc.copiando;
    try {
      const r = await copiaDispositivoEjecutar({
        origen,
        playlistId: origen === 'playlist' ? playlistId : null,
        estructura,
        incrustarPortada,
        convertirAWav
      });
      if (r) {
        const mb = (r.bytesEscritos / 1_048_576).toFixed(1);
        mensajeCopia = tc.resumen(r.copiadas, r.omitidas, mb, r.listaM3u8);
      } else {
        mensajeCopia = null;
      }
    } catch {
      mensajeCopia = tc.error;
    } finally {
      copiando = false;
    }
  }

  $effect(() => {
    if (!confirmar) return;
    if (quitando && !confirmar.open) confirmar.showModal();
    else if (!quitando && confirmar.open) confirmar.close();
  });

  /** La V1 guardaba algunas fechas sin zona (`2026-05-24 05:45:57`), en UTC. */
  function fecha(iso: string): string {
    const normal = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso.replace(' ', 'T')}Z`;
    const d = new Date(normal);
    return Number.isNaN(d.getTime())
      ? iso
      : d.toLocaleString('es', { dateStyle: 'medium', timeStyle: 'short' });
  }

  async function quitarConfirmado() {
    if (!quitando) return;
    const { id } = quitando;
    quitando = null;
    await telefonos.quitar(id);
  }
</script>

<section id="dispositivos" aria-labelledby="t-dispositivos">
  <h2 id="t-dispositivos">{t.dispositivos}</h2>
  <label class="ajuste interruptor">
    <span class="rotulo">
      {t.permitirTelefonos}
      <small>
        {t.permitirAyuda}
        {#if telefonos.estado.direccion}{t.escuchandoEn(telefonos.estado.direccion)}{/if}
      </small>
    </span>
    <input
      type="checkbox"
      role="switch"
      checked={telefonos.estado.activo}
      onchange={(e) => telefonos.permitir(e.currentTarget.checked)}
    />
  </label>
  <div>
    <button type="button" class="boton principal" onclick={() => (conectando = true)}>
      <Icon nombre="telefono" tamano={18} />
      {t.conectarTelefono}
    </button>
  </div>

  {#if telefonos.lista.length === 0}
    <p>{t.sinTelefonos}</p>
  {:else}
    <ul class="telefonos">
      {#each telefonos.lista as tel (tel.id)}
        <li>
          <Icon nombre="telefono" tamano={22} />
          <span class="datos">
            <strong>{tel.nombre}</strong>
            <small class:vivo={tel.conectado}>
              {#if tel.controlando}
                {t.controlando}
              {:else if tel.conectado}
                {t.conectadoAhora}
              {:else if tel.ultimaConexion}
                {t.ultimaConexion(fecha(tel.ultimaConexion))}
              {:else}
                {t.sinConexiones}
              {/if}
            </small>
          </span>
          <button
            type="button"
            class="boton"
            aria-label={t.quitarTelefono(tel.nombre)}
            onclick={() => (quitando = { id: tel.id, nombre: tel.nombre })}
          >
            {t.quitar}
          </button>
        </li>
      {/each}
    </ul>
  {/if}

  <div class="bloque-externo">
    <h3>{tc.titulo}</h3>
    <p>{tc.ayuda}</p>

    <div class="ajuste">
      <span class="rotulo">{tc.origen}</span>
      <MenuSelector
        opciones={[
          { valor: 'favoritas', etiqueta: tc.origenes.favoritas },
          { valor: 'playlist', etiqueta: tc.origenes.playlist },
          { valor: 'biblioteca', etiqueta: tc.origenes.biblioteca }
        ]}
        bind:valor={origen}
      />
    </div>

    {#if origen === 'playlist'}
      <div class="ajuste">
        <span class="rotulo">{tc.playlist}</span>
        {#if playlists.length === 0}
          <small>{tc.sinPlaylists}</small>
        {:else}
          <MenuSelector
            opciones={playlists.map((pl) => ({ valor: pl.id, etiqueta: pl.nombre }))}
            valor={playlistId ?? playlists[0]?.id ?? 0}
            onchange={(v) => (playlistId = v)}
          />
        {/if}
      </div>
    {/if}

    <div class="ajuste">
      <span class="rotulo">{tc.estructura}</span>
      <MenuSelector
        opciones={[
          { valor: 'artistaAlbum', etiqueta: tc.estructuras.artistaAlbum },
          { valor: 'artista', etiqueta: tc.estructuras.artista },
          { valor: 'plana', etiqueta: tc.estructuras.plana }
        ]}
        bind:valor={estructura}
      />
    </div>

    <label class="ajuste interruptor">
      <span class="rotulo">{tc.incrustarPortada}</span>
      <input type="checkbox" role="switch" bind:checked={incrustarPortada} />
    </label>

    <label class="ajuste interruptor">
      <span class="rotulo">{tc.convertirWav}</span>
      <input type="checkbox" role="switch" bind:checked={convertirAWav} />
    </label>

    <div class="fila-accion">
      <button
        type="button"
        class="boton"
        disabled={copiando || (origen === 'playlist' && playlistId === null)}
        onclick={iniciarCopiaDispositivo}
      >
        <Icon nombre="carpeta" tamano={18} />
        {copiando ? tc.copiando : tc.botonCopiar}
      </button>
      {#if mensajeCopia}
        <small class="estado-copia">{mensajeCopia}</small>
      {/if}
    </div>
  </div>

  <BloqueFiesta />
</section>

<DialogoConectar abierto={conectando} oncerrar={() => (conectando = false)} />

<dialog
  bind:this={confirmar}
  class="confirmar"
  onclose={() => (quitando = null)}
  aria-labelledby="titulo-quitar"
>
  {#if quitando}
    <h2 id="titulo-quitar">{t.quitarTelefono(quitando.nombre)}</h2>
    <p>{t.quitarAyuda(quitando.nombre)}</p>
    <div class="botones">
      <button type="button" class="boton" onclick={() => (quitando = null)}>{t.cancelar}</button>
      <button type="button" class="boton peligro" onclick={quitarConfirmado}>{t.quitar}</button>
    </div>
  {/if}
</dialog>

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

  input[type='checkbox'] {
    appearance: none;
    -webkit-appearance: none;
    position: relative;
    width: 3rem;
    height: 1.75rem;
    border: 2px solid var(--m3c-outline);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
    cursor: pointer;
    transition:
      background var(--ns-duracion-corta) var(--ns-curva),
      border-color var(--ns-duracion-corta) var(--ns-curva);
  }

  input[type='checkbox']::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 0.25rem;
    transform: translateY(-50%);
    width: 1rem;
    height: 1rem;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-outline);
    transition:
      transform var(--ns-duracion-corta) var(--ns-curva),
      background var(--ns-duracion-corta) var(--ns-curva),
      width var(--ns-duracion-corta) var(--ns-curva),
      height var(--ns-duracion-corta) var(--ns-curva);
  }

  input[type='checkbox']:checked {
    background: var(--m3c-primary);
    border-color: var(--m3c-primary);
  }

  input[type='checkbox']:checked::before {
    transform: translate(1.25rem, -50%);
    background: var(--m3c-on-primary);
    width: 1.25rem;
    height: 1.25rem;
  }

  input[type='checkbox']:focus-visible {
    outline: 2px solid var(--m3c-primary);
    outline-offset: 2px;
  }

  .telefonos {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .telefonos li {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container);
  }

  .datos {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-width: 0;
  }

  .datos strong {
    overflow: hidden;
    font-size: var(--ns-texto-sm);
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .datos small {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .datos small.vivo {
    color: var(--m3c-primary);
  }

  .boton {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
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

  .boton.peligro {
    border-color: var(--m3c-error);
    background: var(--m3c-error);
    color: var(--m3c-on-error);
  }

  .confirmar {
    width: min(26rem, 90vw);
    padding: var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
  }

  .confirmar::backdrop {
    background: var(--m3c-scrim);
    opacity: 0.5;
  }

  .confirmar h2 {
    margin-bottom: var(--ns-espacio-3);
  }

  .botones {
    display: flex;
    justify-content: flex-end;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-4);
  }

  .bloque-externo {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    padding-top: var(--ns-espacio-4);
    border-top: 1px solid var(--m3c-outline-variant);
  }

  .bloque-externo h3 {
    margin: 0;
    font-size: var(--ns-texto-md);
  }

  .fila-accion {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--ns-espacio-3);
  }

  .estado-copia {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }
</style>
