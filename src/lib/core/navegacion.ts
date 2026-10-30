/**
 * Los destinos de la barra lateral.
 *
 * Contrato: docs/adr/decisions/ADR-007-arquitectura-de-informacion.md. Siete
 * destinos fijos y uno, Por revisar, que solo existe mientras hay algo pendiente.
 * Añadir un destino exige enmendar ese ADR.
 */

import { textos } from '$lib/i18n';
import type { NombreDeIcono } from '$ui/iconos';

export interface Destino {
  readonly id: string;
  readonly ruta: string;
  readonly etiqueta: string;
  readonly icono: NombreDeIcono;
}

const INICIO: Destino = { id: 'inicio', ruta: '/', etiqueta: textos.nav.inicio, icono: 'inicio' };
const BIBLIOTECA: Destino = {
  id: 'biblioteca',
  ruta: '/biblioteca',
  etiqueta: textos.nav.biblioteca,
  icono: 'biblioteca'
};
const PLAYLISTS: Destino = {
  id: 'playlists',
  ruta: '/playlists',
  etiqueta: textos.nav.playlists,
  icono: 'playlists'
};
const DJ: Destino = { id: 'dj', ruta: '/dj', etiqueta: textos.nav.dj, icono: 'dj' };
const A_CIEGAS: Destino = {
  id: 'a-ciegas',
  ruta: '/a-ciegas',
  etiqueta: textos.nav.aCiegas,
  icono: 'aCiegas'
};
const TU_MUSICA: Destino = {
  id: 'tu-musica',
  ruta: '/tu-musica',
  etiqueta: textos.nav.tuMusica,
  icono: 'tuMusica'
};

export const DESTINOS: readonly Destino[] = [
  INICIO,
  BIBLIOTECA,
  PLAYLISTS,
  DJ,
  A_CIEGAS,
  TU_MUSICA
];

export const AJUSTES: Destino = {
  id: 'ajustes',
  ruta: '/ajustes',
  etiqueta: textos.nav.ajustes,
  icono: 'ajustes'
};

export const POR_REVISAR: Destino = {
  id: 'por-revisar',
  ruta: '/por-revisar',
  etiqueta: textos.nav.porRevisar,
  icono: 'porRevisar'
};

/**
 * Las secciones de la barra lateral, con los rótulos de la V1 (`NavLateral.qml`).
 * Ajustes y Por revisar van aparte, al pie.
 */
export const SECCIONES: readonly {
  readonly etiqueta: string;
  readonly destinos: readonly Destino[];
}[] = [
  { etiqueta: textos.nav.secciones.explorar, destinos: [INICIO] },
  { etiqueta: textos.nav.secciones.tuMusica, destinos: [BIBLIOTECA, PLAYLISTS, TU_MUSICA] },
  { etiqueta: textos.nav.secciones.experiencias, destinos: [DJ, A_CIEGAS] }
];

/** Los destinos que se pintan, en orden, según cuántos pendientes haya. */
export function destinosVisibles(pendientes: number): readonly Destino[] {
  return pendientes > 0 ? [...DESTINOS, POR_REVISAR, AJUSTES] : [...DESTINOS, AJUSTES];
}

/** Si una ruta pertenece a un destino (la raíz solo a sí misma). */
export function estaActivo(destino: Destino, ruta: string): boolean {
  if (destino.ruta === '/') return ruta === '/';
  return ruta === destino.ruta || ruta.startsWith(`${destino.ruta}/`);
}
