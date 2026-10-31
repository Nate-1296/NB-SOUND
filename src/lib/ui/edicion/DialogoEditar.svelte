<!--
  @component
  Editar los datos de una canción o de un álbum (F4.2.5). Se carga aparte del
  arranque: solo lo abre quien pulsa "Editar datos". Pide los datos actuales al
  abrirse y, al guardar, devuelve el id con el que queda (el de un álbum cambia
  solo si se juntó con otro que ya existía).
-->
<script lang="ts">
  import { NsError } from '$core/ipc';
  import { datosAlbum, datosPista, editarAlbum, editarPista } from '$core/ipc/aparte';
  import { textosAparte } from '$lib/i18n/aparte';

  interface Props {
    tipo: 'pista' | 'album';
    id: number;
    oncerrar: () => void;
    onguardado: (id: number) => void;
  }

  let { tipo, id, oncerrar, onguardado }: Props = $props();
  const t = textosAparte.edicion;

  let dialogo: HTMLDialogElement | undefined = $state();
  let cargado = $state(false);
  let guardando = $state(false);
  let error = $state<string | null>(null);

  let titulo = $state('');
  let artista = $state('');
  let album = $state('');
  let numero = $state('');
  let anio = $state('');
  let genero = $state('');

  $effect(() => {
    dialogo?.showModal();
  });

  $effect(() => {
    const peticion =
      tipo === 'pista'
        ? datosPista(id).then((d) => {
            titulo = d.titulo;
            artista = d.artista;
            album = d.album;
            numero = d.numero?.toString() ?? '';
            anio = d.anio?.toString() ?? '';
            genero = d.genero ?? '';
          })
        : datosAlbum(id).then((d) => {
            titulo = d.titulo;
            artista = d.artista;
            anio = d.anio?.toString() ?? '';
          });
    void peticion.then(
      () => (cargado = true),
      () => (error = t.fallo)
    );
  });

  /** Un número vacío es "sin dato"; uno que no es entero no se manda. */
  function entero(v: string): number | null | undefined {
    const limpio = v.trim();
    if (limpio === '') return null;
    const n = Number(limpio);
    return Number.isInteger(n) ? n : undefined;
  }

  async function guardar(e: SubmitEvent) {
    e.preventDefault();
    const [n, a] = [entero(numero), entero(anio)];
    if (n === undefined || a === undefined) {
      error = t.invalido;
      return;
    }
    guardando = true;
    error = null;
    try {
      if (tipo === 'pista') {
        await editarPista(id, { titulo, artista, album, numero: n, anio: a, genero });
        onguardado(id);
      } else {
        onguardado(await editarAlbum(id, { titulo, artista, anio: a }));
      }
    } catch (causa) {
      const codigo = causa instanceof NsError ? causa.code : '';
      error =
        codigo === 'INVALID_INPUT'
          ? t.invalido
          : codigo === 'FILE_NOT_FOUND'
            ? t.sinArchivo
            : t.fallo;
    } finally {
      guardando = false;
    }
  }
</script>

<dialog bind:this={dialogo} onclose={oncerrar} aria-labelledby="titulo-editar">
  <form onsubmit={guardar}>
    <h2 id="titulo-editar">{tipo === 'pista' ? t.tituloPista : t.tituloAlbum}</h2>
    <p>{t.ayuda}</p>
    <label>
      <span>{t.titulo}</span>
      <input class="campo" required maxlength="300" disabled={!cargado} bind:value={titulo} />
    </label>
    <label>
      <span>{t.artista}</span>
      <input class="campo" required maxlength="300" disabled={!cargado} bind:value={artista} />
    </label>
    {#if tipo === 'pista'}
      <label>
        <span>{t.album}<small>{t.albumAyuda}</small></span>
        <input class="campo" maxlength="300" disabled={!cargado} bind:value={album} />
      </label>
      <div class="par">
        <label>
          <span>{t.numero}</span>
          <input
            class="campo"
            inputmode="numeric"
            maxlength="3"
            disabled={!cargado}
            bind:value={numero}
          />
        </label>
        <label>
          <span>{t.anio}</span>
          <input
            class="campo"
            inputmode="numeric"
            maxlength="4"
            disabled={!cargado}
            bind:value={anio}
          />
        </label>
      </div>
      <label>
        <span>{t.genero}</span>
        <input class="campo" maxlength="100" disabled={!cargado} bind:value={genero} />
      </label>
    {:else}
      <label>
        <span>{t.anio}</span>
        <input
          class="campo"
          inputmode="numeric"
          maxlength="4"
          disabled={!cargado}
          bind:value={anio}
        />
      </label>
    {/if}
    {#if error}<p role="alert" class="error">{error}</p>{/if}
    <div class="botones">
      <button type="button" class="boton" onclick={() => dialogo?.close()}>{t.cancelar}</button>
      <button type="submit" class="boton principal" disabled={!cargado || guardando}>
        {t.guardar}
      </button>
    </div>
  </form>
</dialog>

<style>
  dialog {
    width: min(30rem, 90vw);
    padding: var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-high);
    color: var(--m3c-on-surface);
  }

  dialog::backdrop {
    background: var(--m3c-scrim);
    opacity: 0.5;
  }

  form {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
  }

  p {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  p.error {
    color: var(--m3c-error);
  }

  label {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--ns-espacio-1);
    font-size: var(--ns-texto-sm);
    font-weight: 600;
  }

  label small {
    margin-left: var(--ns-espacio-2);
    color: var(--m3c-on-surface-variant);
    font-weight: 400;
  }

  .par {
    display: flex;
    gap: var(--ns-espacio-3);
  }

  .campo {
    height: 2.5rem;
    padding: 0 var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    font-weight: 400;
  }

  .botones {
    display: flex;
    justify-content: flex-end;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-2);
  }

  .boton {
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

  .boton:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
