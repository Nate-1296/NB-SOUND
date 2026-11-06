<!--
  @component
  Ajustes > Permisos: lo que NB Sound necesita del sistema y si lo tiene. Se mide
  al abrir y cada pocos segundos mientras está a la vista, así que si el permiso
  se quita desde el sistema, aquí se ve. Lo que falta se pide desde aquí mismo.

  Lo único que NB Sound necesita del sistema es que el cortafuegos deje pasar al
  teléfono y a los invitados del Modo fiesta en la red local. No usa micrófono,
  cámara ni ubicación, y la música se lee de la carpeta que eliges.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import type { EstadoRed } from '#lib/core/ipc/index.ts';
  import { permisos, type Servicio } from '#lib/core/permisos.svelte.ts';
  import { textos } from '#lib/i18n/index.ts';
  import Icon from '#lib/ui/Icon.svelte';
  import type { NombreDeIcono } from '#lib/ui/iconos.ts';

  const t = textos.permisos;
  const FILAS: { servicio: Servicio; icono: NombreDeIcono }[] = [
    { servicio: 'telefono', icono: 'telefono' },
    { servicio: 'fiesta', icono: 'red' }
  ];

  onMount(() => {
    void permisos.comprobar();
    const vigia = setInterval(() => {
      if (!permisos.pidiendo) void permisos.comprobar();
    }, 5000);
    return () => clearInterval(vigia);
  });

  const textoEstado = (e: EstadoRed | null) => (e ? t.estados[e] : t.comprobando);
</script>

<section aria-labelledby="t-permisos">
  <h2 id="t-permisos">{t.titulo}</h2>
  <p class="ayuda">{t.ayuda}</p>

  <ul class="filas">
    {#each FILAS as f (f.servicio)}
      {@const estado = permisos.estado(f.servicio)}
      <li>
        <span class="icono"><Icon nombre={f.icono} tamano={20} /></span>
        <span class="datos">
          <strong>{t.servicios[f.servicio]}</strong>
          <small>{t.para[f.servicio]}</small>
        </span>
        <span
          class="ficha"
          class:bien={estado === 'abierto' || estado === 'sinCortafuegos'}
          class:mal={estado === 'bloqueado'}>{textoEstado(estado)}</span
        >
        {#if (estado === 'bloqueado' || estado === 'desconocido') && permisos.red?.sePuedePedir}
          <button
            type="button"
            class="boton"
            disabled={permisos.pidiendo}
            onclick={() => void permisos.pedir(f.servicio)}
          >
            {permisos.pidiendo ? t.pidiendo : t.permitir}
          </button>
        {/if}
      </li>
    {/each}
  </ul>

  {#if permisos.red?.cortafuegos}
    <p class="nota">{t.cortafuegos(permisos.red.cortafuegos)}</p>
  {/if}
  <p class="nota">{t.nadaMas}</p>
</section>

<style>
  section {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-lg);
    background: var(--m3c-surface-container-low);
  }

  h2 {
    margin: 0;
    font-size: var(--ns-texto-lg);
  }

  .ayuda,
  .nota {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
    line-height: 1.5;
  }

  .nota {
    font-size: var(--ns-texto-xs);
  }

  .filas {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    padding: var(--ns-espacio-3);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container);
  }

  .icono {
    display: grid;
    place-items: center;
    width: 2.5rem;
    height: 2.5rem;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-primary);
  }

  .datos {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 0.125rem;
    min-width: 0;
  }

  .datos small {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .ficha {
    padding: 0.125rem var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
    font-weight: 600;
    white-space: nowrap;
  }

  .ficha.bien {
    border-color: var(--m3c-primary);
    color: var(--m3c-primary);
  }

  .ficha.mal {
    border-color: var(--m3c-error);
    color: var(--m3c-error);
  }

  .boton {
    height: 2.25rem;
    padding: 0 var(--ns-espacio-4);
    border: none;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 600;
    cursor: pointer;
  }

  .boton:disabled {
    opacity: 0.6;
    cursor: default;
  }
</style>
