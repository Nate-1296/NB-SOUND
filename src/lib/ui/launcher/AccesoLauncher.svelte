<script lang="ts">
  import { onMount } from 'svelte';
  import {
    alCambiarEnlaceLauncher,
    estadoEnlaceLauncher,
    revocarLauncher,
    permitirSolicitudesLauncher,
    type EstadoEnlaceLauncher
  } from '#lib/core/ipc/launcher.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { textosLauncher } from '#lib/i18n/launcher.ts';
  const t = textosLauncher;
  let estado = $state<EstadoEnlaceLauncher | null>(null);
  let ocupado = $state(false);
  let activo = false;
  let revision = 0;
  async function cargar() {
    const actual = ++revision;
    const siguiente = await estadoEnlaceLauncher();
    if (activo && actual === revision) estado = siguiente;
  }
  onMount(() => {
    activo = true;
    let soltar: (() => void) | undefined;
    void (async () => {
      soltar = await alCambiarEnlaceLauncher(() => {
        void cargar().catch(() => {});
      });
      if (!activo) {
        soltar();
        return;
      }
      await cargar();
    })().catch(() => notificar.error(t.fallo));
    return () => {
      activo = false;
      revision++;
      soltar?.();
    };
  });
  async function aplicar(permitir: boolean) {
    if (ocupado) return;
    ocupado = true;
    try {
      if (permitir) await permitirSolicitudesLauncher();
      else await revocarLauncher();
      await cargar();
    } catch {
      notificar.error(t.fallo);
    } finally {
      ocupado = false;
    }
  }
</script>

<section aria-labelledby="titulo-launcher">
  <h2 id="titulo-launcher">{t.titulo}</h2>
  <p>{t.descripcion}</p>
  {#if estado}
    {#if !estado.disponible}<p>{t.noDisponible}</p>{/if}
    {#if estado.recordadas !== null}
      <p role="status">{estado.recordadas ? t.recordadas(estado.recordadas) : t.ninguna}</p>
    {/if}
    {#if (estado.recordadas ?? 0) > 0}
      <p>{t.efectoRevocar}</p>
      <button
        type="button"
        disabled={ocupado}
        onclick={() => {
          void aplicar(false);
        }}
      >
        {ocupado ? t.trabajando : t.revocar}
      </button>
    {/if}
    {#if (estado.revocadas ?? 0) > 0}
      <p>{t.revocadas}</p>
      <p>{t.efectoPermitir}</p>
      <button
        type="button"
        disabled={ocupado}
        onclick={() => {
          void aplicar(true);
        }}
      >
        {ocupado ? t.trabajando : t.permitirSolicitudes}
      </button>
    {/if}
  {/if}
</section>

<style>
  section {
    margin-top: var(--ns-espacio-6);
  }
  p {
    color: var(--m3c-on-surface-variant);
    line-height: 1.5;
  }
  button {
    padding: var(--ns-espacio-3) var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    cursor: pointer;
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
