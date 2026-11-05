/**
 * Estado en memoria de las vistas principales de la aplicación durante la sesión.
 *
 * Se conserva entre navegaciones internas para que el usuario no pierda su pestaña
 * activa, filtros, búsqueda o modo de cuadrícula al explorar artistas, álbumes o playlists,
 * y se reinicia naturalmente al cerrar y volver a abrir la aplicación.
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
