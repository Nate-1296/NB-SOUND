<!--
  @component
  Inicio con la biblioteca vacía: la primera pantalla de quien acaba de instalar
  NB Sound. Antes era una tarjeta que decía "Tu biblioteca empieza al importar
  música" sin ningún botón para hacerlo.

  Tres caminos, cada uno con su botón: la carpeta donde ya está la música (la
  importa entera y la vigila: elegirla es el consentimiento que la vigilancia
  espera), canciones sueltas, o una copia de seguridad de otro equipo. Y el
  nombre, que es lo primero que usa Inicio para saludar.
-->
<script lang="ts">
  import { aparienciaActual } from '#lib/core/apariencia.svelte.ts';
  import { anadirMusica } from '#lib/core/ipc/index.ts';
  import {
    aplicarCarpetaMusica,
    copiaRestaurar,
    elegirCarpetaMusica,
    reiniciar
  } from '#lib/core/ipc/aparte.ts';
  import { notificar } from '#lib/core/notificaciones.svelte.ts';
  import { textosAparte } from '#lib/i18n/aparte.ts';
  import Icon from '#lib/ui/Icon.svelte';
  import type { NombreDeIcono } from '#lib/ui/iconos.ts';

  const t = textosAparte.bienvenida;
  let nombre = $state(aparienciaActual.actual.nombreUsuario ?? '');
  let ocupado = $state(false);

  async function con(paso: () => Promise<unknown>) {
    if (ocupado) return;
    ocupado = true;
    try {
      await paso();
    } catch {
      notificar.error(textosAparte.comun.error);
    } finally {
      ocupado = false;
    }
  }

  const caminos: {
    icono: NombreDeIcono;
    titulo: string;
    texto: string;
    boton: string;
    accion: () => Promise<unknown>;
    principal?: boolean;
  }[] = [
    {
      icono: 'carpeta',
      titulo: t.carpetaTitulo,
      texto: t.carpetaTexto,
      boton: t.carpetaBoton,
      principal: true,
      accion: async () => {
        if (!(await elegirCarpetaMusica())) return;
        await aplicarCarpetaMusica(false);
        notificar.informacion(t.buscando);
      }
    },
    {
      icono: 'cancion',
      titulo: t.sueltaTitulo,
      texto: t.sueltaTexto,
      boton: t.sueltaBoton,
      accion: () => anadirMusica(false)
    },
    {
      icono: 'reintentar',
      titulo: t.copiaTitulo,
      texto: t.copiaTexto,
      boton: t.copiaBoton,
      accion: async () => {
        if (!(await copiaRestaurar())) return;
        notificar.exito(t.restaurada);
        await reiniciar();
      }
    }
  ];
</script>

<section class="bienvenida">
  <div class="cabecera">
    <img
      class="logo"
      src={`/logos/logo_${aparienciaActual.actual.tema}.png`}
      alt=""
      onerror={(e) => ((e.currentTarget as HTMLImageElement).src = '/logo.png')}
    />
    <h2>{t.titulo}</h2>
    <p>{t.subtitulo}</p>
  </div>

  <label class="nombre">
    <span>{t.nombre}</span>
    <input
      maxlength="40"
      placeholder={t.nombreMarcador}
      bind:value={nombre}
      onchange={() => aparienciaActual.cambiar('nombreUsuario', nombre.trim() || null)}
    />
  </label>

  <ul class="caminos">
    {#each caminos as c (c.titulo)}
      <li class:principal={c.principal}>
        <span class="icono"><Icon nombre={c.icono} tamano={26} /></span>
        <strong>{c.titulo}</strong>
        <p>{c.texto}</p>
        <button type="button" class="boton" disabled={ocupado} onclick={() => con(c.accion)}>
          {c.boton}
        </button>
      </li>
    {/each}
  </ul>
</section>

<style>
  .bienvenida {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--ns-espacio-6);
    max-width: 64rem;
    margin: var(--ns-espacio-5) auto 0;
  }

  .cabecera {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--ns-espacio-3);
    text-align: center;
  }

  .logo {
    width: 6rem;
    height: 6rem;
    border-radius: var(--ns-radio-pleno);
    box-shadow: 0 12px 36px color-mix(in srgb, var(--m3c-primary) 40%, transparent);
  }

  h2 {
    margin: 0;
    font-size: clamp(var(--ns-texto-2xl), 4vw, var(--ns-texto-3xl));
    line-height: 1.1;
  }

  .cabecera p {
    max-width: 40rem;
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-md);
  }

  .nombre {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    font-size: var(--ns-texto-sm);
    font-weight: 600;
  }

  .nombre input {
    width: 16rem;
    padding: var(--ns-espacio-2) var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container);
    color: var(--m3c-on-surface);
    font: inherit;
    font-weight: 400;
  }

  .caminos {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--ns-espacio-4);
    width: 100%;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .caminos li {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--ns-espacio-2);
    padding: var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-xl);
    background: var(--m3c-surface-container);
  }

  .caminos li.principal {
    border-color: color-mix(in srgb, var(--m3c-primary) 50%, transparent);
    background: linear-gradient(
      160deg,
      color-mix(in srgb, var(--m3c-primary-container) 55%, var(--m3c-surface-container)) 0%,
      var(--m3c-surface-container) 100%
    );
  }

  .icono {
    display: grid;
    place-items: center;
    width: 3rem;
    height: 3rem;
    margin-bottom: var(--ns-espacio-2);
    border-radius: var(--ns-radio-md);
    background: color-mix(in srgb, var(--m3c-primary) 16%, transparent);
    color: var(--m3c-primary);
  }

  strong {
    font-size: var(--ns-texto-md);
  }

  li p {
    flex: 1;
    margin: 0;
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
    line-height: 1.5;
  }

  .boton {
    margin-top: var(--ns-espacio-2);
    padding: var(--ns-espacio-2) var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: transparent;
    color: var(--m3c-on-surface);
    font: inherit;
    font-size: var(--ns-texto-sm);
    font-weight: 700;
    cursor: pointer;
  }

  .boton:hover:not(:disabled) {
    background: var(--m3c-surface-container-highest);
  }

  .principal .boton {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .boton:disabled {
    opacity: 0.38;
    cursor: default;
  }

  @container carcasa (max-width: 60rem) {
    .caminos {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
