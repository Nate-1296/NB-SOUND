<!--
  @component
  Modo fiesta (F8.5, ADR-012): panel del anfitrión en Ajustes > Dispositivos.
  Permite encender o apagar el listener efímero en la red local, mostrar o rotar el
  código QR con el token de sesión, alternar la aceptación automática y aprobar,
  descartar o bloquear las sugerencias de los invitados.
-->
<script lang="ts">
  import {
    alCambiarFiesta,
    type EstadoFiesta,
    fiestaEncender,
    fiestaEstado,
    fiestaModoAutomatico,
    fiestaRegenerarQr,
    fiestaResolverSugerencia
  } from '$core/ipc/aparte';
  import { textosAparte } from '$lib/i18n/aparte';

  const tf = textosAparte.modoFiesta;

  let estado = $state<EstadoFiesta>({
    activo: false,
    url: null,
    qr: null,
    aceptarAutomaticamente: false,
    sugerencias: [],
    bloqueados: 0
  });
  let cargando = $state(false);

  async function refrescar() {
    try {
      estado = await fiestaEstado();
    } catch {
      // Mantiene el último estado conocido si falla la lectura puntual.
    }
  }

  $effect(() => {
    void refrescar();
    let soltar: (() => void) | null = null;
    void alCambiarFiesta(() => {
      void refrescar();
    }).then((fn) => {
      soltar = fn;
    });
    return () => {
      soltar?.();
    };
  });

  async function alternarActivo(activo: boolean) {
    if (cargando) return;
    cargando = true;
    try {
      estado = await fiestaEncender(activo);
    } finally {
      cargando = false;
    }
  }

  async function rotarQr() {
    if (cargando || !estado.activo) return;
    cargando = true;
    try {
      estado = await fiestaRegenerarQr();
    } finally {
      cargando = false;
    }
  }

  async function alternarAutomatico(activo: boolean) {
    try {
      estado = await fiestaModoAutomatico(activo);
    } catch {
      // Si falla, el siguiente refresco restaura el interruptor.
    }
  }

  async function resolver(id: number, aceptar: boolean, bloquear: boolean) {
    try {
      estado = await fiestaResolverSugerencia(id, aceptar, bloquear);
    } catch {
      // Ignorado.
    }
  }
</script>

<div class="bloque-fiesta">
  <h3>{tf.titulo}</h3>
  <p>{tf.ayuda}</p>

  <label class="ajuste interruptor">
    <span class="rotulo">
      {tf.interruptor}
      <small>{tf.interruptorAyuda}</small>
    </span>
    <input
      type="checkbox"
      role="switch"
      disabled={cargando}
      checked={estado.activo}
      onchange={(e) => alternarActivo(e.currentTarget.checked)}
    />
  </label>

  {#if estado.activo && estado.qr && estado.url}
    <div class="panel-qr">
      <div class="qr">
        <svg
          viewBox={`-4 -4 ${estado.qr.lado + 8} ${estado.qr.lado + 8}`}
          role="img"
          aria-label={tf.qrEtiqueta}
          shape-rendering="crispEdges"
        >
          <rect
            x="-4"
            y="-4"
            width={estado.qr.lado + 8}
            height={estado.qr.lado + 8}
            class="fondo"
          />
          <path d={estado.qr.trazado} class="tinta" />
        </svg>
      </div>

      <div class="info-qr">
        <small>{tf.urlEtiqueta}</small>
        <code class="enlace-fiesta">{estado.url}</code>
        <div class="acciones-qr">
          <button type="button" class="boton" disabled={cargando} onclick={rotarQr}>
            {tf.regenerarQr}
          </button>
        </div>
      </div>
    </div>

    <label class="ajuste interruptor">
      <span class="rotulo">
        {tf.automatico}
        <small>{tf.automaticoAyuda}</small>
      </span>
      <input
        type="checkbox"
        role="switch"
        checked={estado.aceptarAutomaticamente}
        onchange={(e) => alternarAutomatico(e.currentTarget.checked)}
      />
    </label>

    <div class="sugerencias-bloque">
      <div class="cabecera-sugerencias">
        <h4>{tf.sugerenciasTitulo}</h4>
        {#if estado.bloqueados > 0}
          <small>{tf.bloqueados(estado.bloqueados)}</small>
        {/if}
      </div>

      {#if estado.sugerencias.length === 0}
        <p>{tf.sinSugerencias}</p>
      {:else}
        <ul class="lista-sugerencias">
          {#each estado.sugerencias as s (s.id)}
            <li>
              <div class="datos-sugerencia">
                <strong>{s.pista.titulo}</strong>
                <small>
                  {s.pista.artista}
                  {#if s.alias}
                    · {tf.porInvitado(s.alias)}
                  {/if}
                </small>
              </div>

              {#if s.aceptada}
                <span class="insignia-cola">{tf.enCola}</span>
              {:else}
                <div class="botones-sugerencia">
                  <button
                    type="button"
                    class="boton principal"
                    onclick={() => resolver(s.id, true, false)}
                  >
                    {tf.aceptar}
                  </button>
                  <button type="button" class="boton" onclick={() => resolver(s.id, false, false)}>
                    {tf.descartar}
                  </button>
                  <button
                    type="button"
                    class="boton peligro"
                    onclick={() => resolver(s.id, false, true)}
                  >
                    {tf.bloquear}
                  </button>
                </div>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</div>

<style>
  .bloque-fiesta {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    padding-top: var(--ns-espacio-4);
    border-top: 1px solid var(--m3c-outline-variant);
  }

  h3 {
    margin: 0;
    font-size: var(--ns-texto-md);
  }

  h4 {
    margin: 0;
    font-size: var(--ns-texto-sm);
  }

  p {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
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

  .panel-qr {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--ns-espacio-4);
    padding: var(--ns-espacio-4);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container);
  }

  .qr {
    width: 11rem;
    border-radius: var(--ns-radio-sm);
    overflow: hidden;
    flex-shrink: 0;
  }

  .qr svg {
    display: block;
    width: 100%;
    height: auto;
  }

  .fondo {
    fill: var(--ns-qr-fondo);
  }

  .tinta {
    fill: var(--ns-qr-tinta);
  }

  .info-qr {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    min-width: 14rem;
  }

  .info-qr small {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .enlace-fiesta {
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-high);
    font-family: var(--ns-font-mono);
    font-size: var(--ns-texto-xs);
    word-break: break-all;
  }

  .acciones-qr {
    display: flex;
    gap: var(--ns-espacio-2);
  }

  .sugerencias-bloque {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
  }

  .cabecera-sugerencias {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-2);
  }

  .cabecera-sugerencias small {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .lista-sugerencias {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .lista-sugerencias li {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-2) var(--ns-espacio-3);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container);
  }

  .datos-sugerencia {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-width: 12rem;
  }

  .datos-sugerencia strong {
    overflow: hidden;
    font-size: var(--ns-texto-sm);
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .datos-sugerencia small {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .botones-sugerencia {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ns-espacio-2);
  }

  .insignia-cola {
    padding: var(--ns-espacio-1) var(--ns-espacio-3);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-secondary-container);
    color: var(--m3c-on-secondary-container);
    font-size: var(--ns-texto-xs);
    font-weight: 600;
  }

  .boton {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    height: 2.25rem;
    padding: 0 var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-xs);
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
</style>
