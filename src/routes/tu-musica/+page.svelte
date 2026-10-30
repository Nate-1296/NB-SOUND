<!--
  Tu música, con la disposición de la V1 (`VistaPerfil.qml`): la identidad musical
  con la foto y el nombre, sus fichas y Reproducir tu esencia; Tu actividad; el
  mood del día y los días activos del mes; y Lo que más has querido, con los tops
  de canciones, álbumes y artistas.
-->
<script lang="ts">
  import { aparienciaActual } from '$core/apariencia.svelte';
  import { duracionDetallada } from '$core/formato';
  import { type Perfil, perfil, urlFotoPerfil, urlPortada } from '$core/ipc';
  import { reproductor } from '$core/reproductor.svelte';
  import { textos } from '$lib/i18n';
  import Icon from '$ui/Icon.svelte';

  const t = textos.tuMusica;
  let datos = $state<Perfil | null>(null);
  let sinFoto = $state(false);

  function cargar() {
    void perfil().then((p) => (datos = p));
  }
  $effect(cargar);

  const nombre = $derived(aparienciaActual.actual.nombreUsuario ?? t.anonimo);
  const diasActivos = $derived(datos?.diasDelMes.filter((n) => n > 0).length ?? 0);

  function hora(h: number): string {
    return new Date(2000, 0, 1, h).toLocaleTimeString('es', { hour: 'numeric', minute: '2-digit' });
  }

  function nivel(n: number): string {
    if (n === 0) return 'nada';
    if (n <= 5) return 'poco';
    if (n <= 15) return 'medio';
    return 'mucho';
  }
</script>

<section class="perfil">
  <header class="identidad">
    <span class="foto">
      {#if !sinFoto}
        <img src={urlFotoPerfil()} alt="" onerror={() => (sinFoto = true)} />
      {:else}
        <Icon nombre="artista" tamano={48} />
      {/if}
    </span>
    <div class="datos">
      <span class="etiqueta">{t.identidad}</span>
      <h1>{nombre}</h1>
      {#if datos}
        <p>{t.resumen(datos.reproducciones, datos.pistasDistintas, datos.pistasEnBiblioteca)}</p>
        <div class="fichas">
          {#if datos.anioFavorito}<span class="ficha acento"
              >{t.anioFavorito(datos.anioFavorito)}</span
            >{/if}
          {#if datos.horaPico !== null}<span class="ficha">{t.horaPico(hora(datos.horaPico))}</span
            >{/if}
          <span class="ficha">{t.diasActivos(diasActivos)}</span>
        </div>
        <div class="botones">
          <button
            type="button"
            class="boton relleno"
            disabled={datos.topCanciones.length === 0}
            onclick={() =>
              reproductor.reproducirPistas(datos?.topCanciones.map((e) => e.pista.id) ?? [])}
          >
            <Icon nombre="reproducir" tamano={16} />{t.esencia}
          </button>
          <button type="button" class="boton" onclick={cargar}>
            <Icon nombre="reintentar" tamano={16} />{t.actualizar}
          </button>
        </div>
      {/if}
    </div>
  </header>

  {#if datos && datos.reproducciones === 0}
    <p class="vacio">{t.vacio}</p>
  {:else if datos}
    <h2>{t.actividad}</h2>
    <p class="sub">{t.actividadSub}</p>
    <ul class="cifras">
      <li>
        <span>{t.escuchadas}</span><strong>{datos.pistasDistintas.toLocaleString('es')}</strong
        ><Icon nombre="cancion" tamano={16} />
      </li>
      <li>
        <span>{t.artistas}</span><strong>{datos.artistasDistintos.toLocaleString('es')}</strong
        ><Icon nombre="artista" tamano={16} />
      </li>
      <li>
        <span>{t.albumes}</span><strong>{datos.albumesDistintos.toLocaleString('es')}</strong><Icon
          nombre="album"
          tamano={16}
        />
      </li>
      <li>
        <span>{t.tiempo}</span><strong
          >{duracionDetallada(datos.segundosEscuchados).split(' ').slice(0, 2).join(' ')}</strong
        ><Icon nombre="reloj" tamano={16} />
      </li>
    </ul>

    <div class="dos">
      <article class="tarjeta">
        <span class="etiqueta">{t.animo}</span>
        {#if datos.artistasHoy[0]}
          <h3>{datos.artistasHoy[0].nombre}</h3>
          <p class="sub">{t.escuchasHoy(datos.escuchasHoy)}</p>
          <div class="fichas">
            {#each datos.artistasHoy as a (a.id)}
              <a class="ficha" href={`/biblioteca/artista?id=${a.id}`}>{a.nombre} · {a.escuchas}</a>
            {/each}
          </div>
        {:else}
          <p class="sub">{t.sinEscuchasHoy}</p>
        {/if}
      </article>

      <article class="tarjeta">
        <span class="etiqueta">{t.mes}</span>
        <h3>{t.diasActivos(diasActivos)}</h3>
        <ol class="calendario">
          {#each datos.diasDelMes as n, d (d)}
            <li class="dia {nivel(n)}" title={t.dia(d + 1, n)} aria-label={t.dia(d + 1, n)}></li>
          {/each}
        </ol>
        <div class="leyenda">
          {#each ['nada', 'poco', 'medio', 'mucho'] as const as k (k)}
            <span><i class="dia {k}"></i>{t.leyenda[k]}</span>
          {/each}
        </div>
      </article>
    </div>

    <h2>{t.querido}</h2>
    <p class="sub">{t.queridoSub}</p>
    <div class="tres">
      <article class="tarjeta">
        <h3 class="titulo-top">{t.topCanciones}</h3>
        <ol class="top">
          {#each datos.topCanciones as e, k (e.pista.id)}
            <li>
              <button
                type="button"
                class="fila"
                onclick={() =>
                  reproductor.reproducirPistas(datos?.topCanciones.map((x) => x.pista.id) ?? [], k)}
              >
                <span class="n">{String(k + 1).padStart(2, '0')}</span>
                <span class="img"
                  >{#if e.pista.tienePortada}<img
                      src={urlPortada('pista', e.pista.id, 64)}
                      alt=""
                    />{/if}</span
                >
                <span class="texto"
                  ><strong>{e.pista.titulo}</strong><span class="sub"
                    >{e.pista.artista} · {e.pista.album}</span
                  ></span
                >
              </button>
            </li>
          {/each}
        </ol>
      </article>
      <article class="tarjeta">
        <h3 class="titulo-top">{t.topAlbumes}</h3>
        <ol class="top">
          {#each datos.topAlbumes as a, k (a.id)}
            <li>
              <a class="fila" href={`/biblioteca/album?id=${a.id}`}>
                <span class="n">{String(k + 1).padStart(2, '0')}</span>
                <span class="img"
                  >{#if a.tienePortada}<img src={urlPortada('album', a.id, 64)} alt="" />{/if}</span
                >
                <span class="texto"
                  ><strong>{a.titulo}</strong><span class="sub">{a.artista}</span></span
                >
                <Icon nombre="derecha" tamano={16} />
              </a>
            </li>
          {/each}
        </ol>
      </article>
      <article class="tarjeta">
        <h3 class="titulo-top">{t.topArtistas}</h3>
        <ol class="top">
          {#each datos.topArtistas as a, k (a.id)}
            <li>
              <a class="fila" href={`/biblioteca/artista?id=${a.id}`}>
                <span class="n">{String(k + 1).padStart(2, '0')}</span>
                <span class="img redonda"
                  >{#if a.tieneImagen}<img
                      src={urlPortada('artista', a.id, 64)}
                      alt=""
                    />{/if}</span
                >
                <span class="texto"><strong>{a.nombre}</strong></span>
                <Icon nombre="derecha" tamano={16} />
              </a>
            </li>
          {/each}
        </ol>
      </article>
    </div>
  {/if}
</section>

<style>
  .perfil {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-3);
  }

  .identidad {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-5);
    margin: calc(-1 * var(--ns-espacio-2)) calc(-1 * var(--ns-espacio-5)) 0;
    padding: var(--ns-espacio-5);
    background: linear-gradient(90deg, var(--m3c-primary-container), var(--m3c-surface));
  }

  .foto {
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    width: 8rem;
    height: 8rem;
    overflow: hidden;
    border: 3px solid var(--m3c-primary);
    border-radius: var(--ns-radio-pleno);
    background: var(--m3c-surface-container-highest);
    color: var(--m3c-on-surface-variant);
  }

  .foto img,
  .img img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .datos {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
  }

  .etiqueta {
    color: var(--m3c-primary);
    font-size: var(--ns-texto-xs);
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  h1 {
    margin: 0;
    font-size: clamp(var(--ns-texto-2xl), 4vw, 3rem);
  }

  h2 {
    margin: var(--ns-espacio-5) 0 0;
    font-size: var(--ns-texto-xl);
  }

  h3 {
    margin: 0;
    font-size: var(--ns-texto-xl);
  }

  p {
    margin: 0;
  }

  .sub {
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-sm);
  }

  .fichas {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ns-espacio-2);
  }

  .ficha {
    padding: var(--ns-espacio-1) var(--ns-espacio-3);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    color: var(--m3c-on-surface);
    font-size: var(--ns-texto-xs);
    text-decoration: none;
  }

  .ficha.acento {
    border-color: var(--m3c-primary);
    color: var(--m3c-primary);
  }

  .botones {
    display: flex;
    gap: var(--ns-espacio-2);
    margin-top: var(--ns-espacio-2);
  }

  .boton {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-2);
    height: 2.75rem;
    padding: 0 var(--ns-espacio-5);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-pleno);
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    font-weight: 700;
    cursor: pointer;
  }

  .boton.relleno {
    border-color: var(--m3c-primary);
    background: var(--m3c-primary);
    color: var(--m3c-on-primary);
  }

  .boton:disabled {
    opacity: 0.38;
  }

  .cifras {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--ns-espacio-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .cifras li,
  .tarjeta {
    padding: var(--ns-espacio-4);
    border: 1px solid var(--m3c-outline-variant);
    border-radius: var(--ns-radio-md);
    background: var(--m3c-surface-container-low);
  }

  .cifras li {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: var(--ns-espacio-1);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .cifras strong {
    grid-row: 2;
    color: var(--m3c-on-surface);
    font-size: var(--ns-texto-xl);
  }

  .dos {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--ns-espacio-3);
  }

  .tres {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--ns-espacio-3);
  }

  .tarjeta {
    display: flex;
    flex-direction: column;
    gap: var(--ns-espacio-2);
  }

  .calendario {
    display: grid;
    grid-template-columns: repeat(15, 1rem);
    gap: 0.25rem;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .dia {
    display: inline-block;
    width: 1rem;
    height: 1rem;
    border-radius: 0.2rem;
    background: var(--m3c-surface-container-highest);
  }

  .dia.poco {
    background: var(--m3c-primary-container);
  }

  .dia.medio {
    background: var(--m3c-primary);
    opacity: 0.7;
  }

  .dia.mucho {
    background: var(--m3c-primary);
  }

  .leyenda {
    display: flex;
    gap: var(--ns-espacio-3);
    color: var(--m3c-on-surface-variant);
    font-size: var(--ns-texto-xs);
  }

  .leyenda span {
    display: inline-flex;
    align-items: center;
    gap: var(--ns-espacio-1);
  }

  .leyenda .dia {
    width: 0.625rem;
    height: 0.625rem;
  }

  .titulo-top {
    font-size: var(--ns-texto-sm);
    padding-bottom: var(--ns-espacio-2);
    border-bottom: 1px solid var(--m3c-outline-variant);
  }

  .top {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .fila {
    display: flex;
    align-items: center;
    gap: var(--ns-espacio-3);
    width: 100%;
    padding: var(--ns-espacio-2) 0;
    border: none;
    background: none;
    color: var(--m3c-on-surface);
    font: inherit;
    text-align: left;
    text-decoration: none;
    cursor: pointer;
  }

  .n {
    width: 1.75rem;
    color: var(--m3c-primary);
    font-weight: 700;
  }

  .img {
    flex: 0 0 2.5rem;
    height: 2.5rem;
    overflow: hidden;
    border-radius: var(--ns-radio-sm);
    background: var(--m3c-surface-container-highest);
  }

  .img.redonda {
    border-radius: var(--ns-radio-pleno);
  }

  .texto {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-width: 0;
  }

  .texto strong,
  .texto .sub {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .texto strong {
    font-size: var(--ns-texto-sm);
  }

  .texto .sub {
    font-size: var(--ns-texto-xs);
  }

  .vacio {
    color: var(--m3c-on-surface-variant);
  }

  @container carcasa (max-width: 70rem) {
    .tres,
    .dos {
      grid-template-columns: minmax(0, 1fr);
    }

    .cifras {
      grid-template-columns: repeat(2, 1fr);
    }
  }
</style>
