/**
 * Estado en memoria de las vistas principales de la aplicación durante la sesión.
 *
 * Se conserva entre navegaciones internas para que el usuario no pierda su pestaña
 * activa, filtros, búsqueda o modo de cuadrícula al explorar artistas, álbumes o playlists,
 * y, salvo las búsquedas, también entre sesiones (ver al final).
 */

import type {
  Categoria,
  OrdenAlbumes,
  OrdenArtistas,
  OrdenPistas,
  OrdenPlaylists
} from '#lib/core/ipc/index.ts';

export type ModoRejilla = 'sm' | 'md' | 'lg' | 'lista';
export type VistaBiblioteca = 'albumes' | 'artistas' | 'pistas';

export class EstadoTabAlbumes {
  busqueda = $state('');
  orden = $state<OrdenAlbumes>('tituloAsc');
  /** Los grupos de la V1: todos, solo álbumes o solo sencillos y EP. */
  grupo = $state<'todos' | 'albumes' | 'sencillos'>('todos');
  modoRejilla = $state<ModoRejilla>('md');
}

export class EstadoTabArtistas {
  busqueda = $state('');
  orden = $state<OrdenArtistas>('nombreAsc');
  modoRejilla = $state<ModoRejilla>('md');
}

export class EstadoTabPistas {
  busqueda = $state('');
  favoritas = $state(false);
  sinVerificar = $state(false);
  paraCantar = $state(false);
  orden = $state<OrdenPistas>('tituloAsc');
  modoRejilla = $state<ModoRejilla>('lista');
}

class EstadoBiblioteca {
  vista = $state<VistaBiblioteca>('albumes');
  albumes = new EstadoTabAlbumes();
  artistas = new EstadoTabArtistas();
  pistas = new EstadoTabPistas();
}

export const estadoBiblioteca = new EstadoBiblioteca();

class EstadoPlaylists {
  busqueda = $state('');
  /** `null` es «Todas». */
  categoria = $state<Categoria | null>(null);
  orden = $state<OrdenPlaylists>('recientes');
  seleccionadaId = $state<number | null>(null);
  modoRejilla = $state<ModoRejilla>('md');
}

export const estadoPlaylists = new EstadoPlaylists();

/*
 * Lo de arriba se guarda entre sesiones: al volver a abrir, cada vista está como
 * se dejó (pestaña, orden, filtros, cuadrícula o lista, la playlist elegida). Las
 * búsquedas escritas no: se abren limpias. En el almacenamiento del webview, que
 * es de este equipo; si no está, se sigue con lo de fábrica.
 */
const CLAVE = 'ns:estado-vistas';

interface Guardado {
  vista?: VistaBiblioteca;
  albumes?: Partial<Pick<EstadoTabAlbumes, 'orden' | 'grupo' | 'modoRejilla'>>;
  artistas?: Partial<Pick<EstadoTabArtistas, 'orden' | 'modoRejilla'>>;
  pistas?: Partial<
    Pick<EstadoTabPistas, 'favoritas' | 'sinVerificar' | 'paraCantar' | 'orden' | 'modoRejilla'>
  >;
  playlists?: Partial<
    Pick<EstadoPlaylists, 'categoria' | 'orden' | 'seleccionadaId' | 'modoRejilla'>
  >;
}

function restaurar() {
  let g: Guardado | null = null;
  try {
    g = JSON.parse(localStorage.getItem(CLAVE) ?? 'null') as Guardado | null;
  } catch {
    return;
  }
  if (!g) return;
  if (g.vista) estadoBiblioteca.vista = g.vista;
  Object.assign(estadoBiblioteca.albumes, g.albumes ?? {});
  Object.assign(estadoBiblioteca.artistas, g.artistas ?? {});
  Object.assign(estadoBiblioteca.pistas, g.pistas ?? {});
  Object.assign(estadoPlaylists, g.playlists ?? {});
}

if (typeof window !== 'undefined') {
  restaurar();
  $effect.root(() => {
    $effect(() => {
      const b = estadoBiblioteca;
      const p = estadoPlaylists;
      const g: Guardado = {
        vista: b.vista,
        albumes: {
          orden: b.albumes.orden,
          grupo: b.albumes.grupo,
          modoRejilla: b.albumes.modoRejilla
        },
        artistas: { orden: b.artistas.orden, modoRejilla: b.artistas.modoRejilla },
        pistas: {
          favoritas: b.pistas.favoritas,
          sinVerificar: b.pistas.sinVerificar,
          paraCantar: b.pistas.paraCantar,
          orden: b.pistas.orden,
          modoRejilla: b.pistas.modoRejilla
        },
        playlists: {
          categoria: p.categoria,
          orden: p.orden,
          seleccionadaId: p.seleccionadaId,
          modoRejilla: p.modoRejilla
        }
      };
      try {
        localStorage.setItem(CLAVE, JSON.stringify(g));
      } catch {
        // Sin almacenamiento, vale para esta sesión.
      }
    });
  });
}
