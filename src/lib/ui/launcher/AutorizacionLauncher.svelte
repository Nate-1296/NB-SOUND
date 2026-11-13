<script lang="ts">
  import { onMount } from 'svelte';
  import {
    alCambiarEnlaceLauncher,
    estadoEnlaceLauncher,
    responderLauncher,
    type EstadoEnlaceLauncher
  } from '#lib/core/ipc/launcher.ts';
  import { NsError } from '#lib/core/ipc/index.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { textosLauncher } from '#lib/i18n/launcher.ts';
  import DialogoConfirmar from '#lib/ui/DialogoConfirmar.svelte';

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
    })().catch(() => {});
    return () => {
      activo = false;
      revision++;
      soltar?.();
    };
  });
  async function responder(permitir: boolean) {
    const id = estado?.pendiente?.id;
    if (!id || ocupado) return;
    ocupado = true;
    try {
      await responderLauncher(id, permitir);
    } catch (causa) {
      if (!(causa instanceof NsError && causa.code === 'CANCELLED')) notificar.error(t.fallo);
    } finally {
      ocupado = false;
      await cargar().catch(() => {});
    }
  }
</script>

<DialogoConfirmar
  abierto={Boolean(estado?.pendiente)}
  titulo={t.solicitud}
  mensaje={t.alcance(estado?.pendiente?.cambiar ?? false, estado?.pendiente?.observar ?? false)}
  textoConfirmar={ocupado ? t.trabajando : t.permitir}
  {ocupado}
  onconfirmar={() => {
    void responder(true);
  }}
  oncerrar={() => {
    void responder(false);
  }}
/>
