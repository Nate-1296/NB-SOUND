<!--
  @component
  DJ Privado (ADR-007, F6.1.6): pedir una sesión, la sesión que se ve (la que
  suena, la recién pedida o una del historial) y el historial. La sesión suena en
  el reproductor de siempre: la barra de abajo la controla. Se carga aparte del
  arranque.
-->
<script lang="ts">
  import { reproductor } from '$core/reproductor.svelte';
  import { textosDj } from '$lib/i18n/dj';
  import HistorialDj from '$ui/dj/HistorialDj.svelte';
  import PedirSesion from '$ui/dj/PedirSesion.svelte';
  import SesionActiva from '$ui/dj/SesionActiva.svelte';

  const t = textosDj;

  // Al entrar, la que suena; después, la que el usuario elija.
  let vista = $state<number | null>(reproductor.instantanea.dj?.sesionId ?? null);
  let version = $state(0);

  function ver(id: number | null) {
    vista = id;
    version += 1;
  }
</script>

<section class="vista">
  <div class="principal">
    <header>
      <h1>{t.titulo}</h1>
      <p class="sub">{t.subtitulo}</p>
    </header>
    <PedirSesion onpedida={ver} />
    {#if vista !== null}
      <SesionActiva sesionId={vista} oncambio={ver} />
    {/if}
  </div>
  <aside class="lateral" aria-labelledby="t-historial">
    <HistorialDj seleccionada={vista} onver={(id) => (vista = id)} {version} />
  </aside>
</section>

<style>
  .vista {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 22rem;
    gap: var(--ns-espacio-5);
    align-items: start;
  }

  .principal {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-4);
    min-width: 0;
  }

  header {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-1);
  }

  h1 {
    margin: 0;
    font-size: var(--ns-texto-xl);
  }

  .sub {
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .lateral {
    position: sticky;
    top: 0;
  }

  @container carcasa (max-width: 70rem) {
    .vista {
      grid-template-columns: minmax(0, 1fr);
    }

    .lateral {
      position: static;
    }
  }
</style>
