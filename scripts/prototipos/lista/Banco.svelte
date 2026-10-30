<!--
  Banco de F0.4.7: una lista de canciones con la forma que tendrá en la
  biblioteca (portada, título, artista, álbum y duración), alimentada por una
  fuente simulada con datos y portadas distintos por fila. El total sale de
  `?total=` (por defecto 100.000).
-->
<script lang="ts">
  import ListaVirtual from './ListaVirtual.svelte';
  import { TAM_BLOQUE } from './ventana';

  interface Cancion {
    titulo: string;
    artista: string;
    album: string;
    duracion: string;
    portada: string;
  }

  const parametros = new URLSearchParams(location.search);
  const total = Number(parametros.get('total') ?? 100_000);
  const conPortadas = parametros.get('portadas') !== '0';

  // Una portada distinta por fila: el motor decodifica por URL, y una sola para
  // todas no mediría nada (lo que NB Books aprendió con su banco). Se codifica
  // un JPEG y cada fila recibe ese mismo JPEG con 8 bytes distintos al final, que
  // el decodificador ignora: cuesta un blob, no una codificación, así que lo que
  // se mide es la lista y no el simulador.
  let base: Uint8Array | null = null;
  function bytesBase(): Uint8Array {
    if (base) return base;
    const lienzo = document.createElement('canvas');
    lienzo.width = 96;
    lienzo.height = 96;
    const ctx = lienzo.getContext('2d') as CanvasRenderingContext2D;
    for (let k = 0; k < 60; k += 1) {
      ctx.fillStyle = `hsl(${(k * 37) % 360} 60% ${20 + (k % 60)}%)`;
      ctx.fillRect((k * 29) % 96, (k * 41) % 96, 16, 16);
    }
    const crudo = atob(lienzo.toDataURL('image/jpeg', 0.8).split(',')[1] ?? '');
    base = Uint8Array.from(crudo, (c) => c.charCodeAt(0));
    return base;
  }

  function portada(i: number): string {
    const cola = new Uint8Array(8);
    for (let k = 0; k < 8; k += 1) cola[k] = (i >> (k * 4)) & 0xff;
    return URL.createObjectURL(new Blob([bytesBase(), cola], { type: 'image/jpeg' }));
  }

  function cargarBloque(b: number): Promise<Cancion[]> {
    const filas: Cancion[] = [];
    const desde = b * TAM_BLOQUE;
    for (let i = desde; i < Math.min(desde + TAM_BLOQUE, total); i += 1) {
      filas.push({
        titulo: `Canción de prueba número ${i + 1}`,
        artista: `Artista ${(i * 7) % 4_000}`,
        album: `Álbum ${(i * 13) % 9_000}`,
        duracion: `${3 + (i % 3)}:${String(i % 60).padStart(2, '0')}`,
        portada: conPortadas ? portada(i) : ''
      });
    }
    return new Promise((r) => setTimeout(() => r(filas), 4));
  }
</script>

<main class="banco">
  <ListaVirtual {total} altoFila={56} {cargarBloque} etiqueta="Canciones">
    {#snippet fila(c, i, rapido)}
      <div class="cancion">
        <span class="n">{i + 1}</span>
        {#if conPortadas && !rapido}<img
            src={c.portada}
            alt=""
            width="40"
            height="40"
            decoding="async"
          />{:else}<span></span>{/if}
        <span class="t">{c.titulo}<small>{c.artista}</small></span>
        <span class="a">{c.album}</span>
        <span class="d">{c.duracion}</span>
      </div>
    {/snippet}
  </ListaVirtual>
</main>

<style>
  .banco {
    height: 100vh;
  }

  .cancion {
    display: grid;
    grid-template-columns: 3rem 40px minmax(0, 2fr) minmax(0, 1fr) 4rem;
    align-items: center;
    gap: var(--ns-espacio-3);
    height: 100%;
    padding: 0 var(--ns-espacio-4);
    border-bottom: 1px solid var(--m3c-outline-variant);
  }

  .cancion:hover {
    background: var(--m3c-surface-container-high);
  }

  img {
    border-radius: var(--ns-radio-sm);
  }

  .t {
    display: flex;
    flex-direction: column;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  small,
  .a,
  .d,
  .n {
    color: var(--m3c-on-surface-variant);
  }
</style>
