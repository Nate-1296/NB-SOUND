<!--
  @component
  La barra de reproducción permanente.

  Hasta F2.1 no hay motor detrás, así que se pinta inerte: los controles existen,
  con su nombre accesible, pero están desactivados. El micrófono del karaoke vive
  aquí y no en una vista propia (ADR-007).
-->
<script lang="ts">
  import { textos } from '$lib/i18n';

  import Icon from './Icon.svelte';
  import type { NombreDeIcono } from './iconos';

  const t = textos.reproductor;

  const principales: { icono: NombreDeIcono; etiqueta: string }[] = [
    { icono: 'aleatorio', etiqueta: t.aleatorio },
    { icono: 'anterior', etiqueta: t.anterior },
    { icono: 'reproducir', etiqueta: t.reproducir },
    { icono: 'siguiente', etiqueta: t.siguiente },
    { icono: 'repetir', etiqueta: t.repetir }
  ];

  const secundarios: { icono: NombreDeIcono; etiqueta: string }[] = [
    { icono: 'microfono', etiqueta: t.karaoke },
    { icono: 'letras', etiqueta: t.letras },
    { icono: 'cola', etiqueta: t.cola },
    { icono: 'volumen', etiqueta: t.volumen }
  ];
</script>

<section class="reproductor" aria-label={t.region}>
  <div class="pista">
    <div class="portada" aria-hidden="true"><Icon nombre="cancion" tamano={24} /></div>
    <div class="datos">
      <span class="titulo">{t.nadaSonando}</span>
      <span class="artista">{t.eligeAlgo}</span>
    </div>
  </div>

  <div class="centro">
    <div class="controles">
      {#each principales as control (control.icono)}
        <button
          type="button"
          class="control"
          class:principal={control.icono === 'reproducir'}
          aria-label={control.etiqueta}
          title={control.etiqueta}
          disabled
        >
          <Icon nombre={control.icono} tamano={control.icono === 'reproducir' ? 24 : 20} />
        </button>
      {/each}
    </div>
    <div class="progreso" role="progressbar" aria-label={t.progreso} aria-valuenow={0}>
      <span class="relleno"></span>
    </div>
  </div>

  <div class="extra">
    {#each secundarios as control (control.icono)}
      <button
        type="button"
        class="control"
        aria-label={control.etiqueta}
        title={control.etiqueta}
        disabled
      >
        <Icon nombre={control.icono} tamano={20} />
      </button>
    {/each}
  </div>
</section>

<style>
  .reproductor {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) minmax(0, 1fr);
    align-items: center;
    gap: var(--ns-espacio-4);
    height: var(--ns-alto-reproductor);
    padding: 0 var(--ns-espacio-5);
    background: var(--m3c-surface-container);
  }

  .pista {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    min-width: 0;
  }

  .portada {
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    width: 3.5rem;
    height: 3.5rem;
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
  }

  .datos {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .titulo,
  .artista {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .titulo {
    font-weight: 600;
  }

  .artista {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .centro {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--ns-espacio-2);
  }

  .controles,
  .extra {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-2);
  }

  .extra {
    justify-content: flex-end;
  }

  .control {
    display: grid;
    place-items: center;
    width: 2.5rem;
    height: 2.5rem;
    border: 0;
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface-variant);
    cursor: pointer;
  }

  .control:hover:not(:disabled) {
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface);
  }

  .control:disabled {
    cursor: default;
    opacity: 0.38;
  }

  .control.principal {
    width: 3rem;
    height: 3rem;
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .progreso {
    width: 100%;
    max-width: 36rem;
    height: 0.25rem;
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
    overflow: hidden;
  }

  .relleno {
    display: block;
    width: 0;
    height: 100%;
    background: var(--m3c-primary);
  }

  :global(.carcasa[data-ancho='compacto']) {
    .reproductor {
      grid-template-columns: minmax(0, 1fr) auto;
    }

    .extra {
      display: none;
    }
  }
</style>
