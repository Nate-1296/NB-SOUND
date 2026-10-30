/**
 * Punto único de acceso al runtime de Rust.
 *
 * Ningún componente invoca el puente directamente: todo pasa por aquí, donde se
 * centralizan el tipado y la traducción de errores. Biome rechaza cualquier
 * importación de `@tauri-apps/api` fuera de esta carpeta, también en `.svelte`.
 *
 * Los tipos vienen de `$lib/bindings`, generados desde Rust con `ts-rs`; no se
 * escriben a mano.
 */

import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';

import type {
  AlbumResumen,
  ArtistaResumen,
  AvisoReproductor,
  ConsultaAlbumes,
  ConsultaArtistas,
  ConsultaPistas,
  InformeDeSalud,
  Instantanea,
  OrdenReproductor,
  PaginaAlbumes,
  PaginaArtistas,
  PaginaPistas,
  PistaResumen
} from '$lib/bindings';

export type {
  AlbumResumen,
  ArtistaResumen,
  AvisoReproductor,
  ConsultaAlbumes,
  ConsultaArtistas,
  ConsultaPistas,
  InformeDeSalud,
  Instantanea,
  OrdenAlbumes,
  OrdenArtistas,
  OrdenPistas,
  OrdenReproductor,
  PaginaAlbumes,
  PaginaArtistas,
  PaginaPistas,
  PistaResumen
} from '$lib/bindings';

/** Error del runtime con su código canónico (ver `src-tauri/src/error.rs`). */
export class NsError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.name = 'NsError';
    this.code = code;
  }
}

function aNsError(causa: unknown): NsError {
  if (typeof causa === 'object' && causa !== null && 'code' in causa) {
    const { code } = causa as { code: unknown };
    if (typeof code === 'string') return new NsError(code);
  }
  // Un fallo sin código canónico se saltó el contrato. Su contenido no se
  // propaga: podría llevar rutas del usuario.
  return new NsError('INTERNAL');
}

export async function call<T>(comando: string, args?: Record<string, unknown>): Promise<T> {
  try {
    return await invoke<T>(comando, args);
  } catch (causa) {
    throw aNsError(causa);
  }
}

/** Comprueba que el runtime responde y devuelve su versión. */
export function salud(): Promise<InformeDeSalud> {
  return call<InformeDeSalud>('salud');
}

/**
 * Se suscribe a un evento del runtime. Devuelve la función que cancela la
 * suscripción, que el componente llama al desmontarse.
 */
function escuchar<T>(evento: string, cada: (carga: T) => void): Promise<UnlistenFn> {
  return listen<T>(evento, (e) => cada(e.payload));
}

// --- Reproductor -----------------------------------------------------------------

/** Lo que suena y la cola; `null` mientras el reproductor arranca. */
export function reproductorEstado(): Promise<Instantanea | null> {
  return call<Instantanea | null>('reproductor_estado');
}

/** Manda una orden. El resultado llega por el evento `reproductor:instantanea`. */
export function reproductorOrden(orden: OrdenReproductor): Promise<void> {
  return call<void>('reproductor_orden', { orden });
}

export function alCambiarElReproductor(cada: (i: Instantanea) => void): Promise<UnlistenFn> {
  return escuchar<Instantanea>('reproductor:instantanea', cada);
}

export function alAvisarElReproductor(cada: (a: AvisoReproductor) => void): Promise<UnlistenFn> {
  return escuchar<AvisoReproductor>('reproductor:aviso', cada);
}

/** Resúmenes de pistas, en el orden pedido; como mucho 500 por petición. */
export function pistasResumen(ids: readonly number[]): Promise<PistaResumen[]> {
  return call<PistaResumen[]>('pistas_resumen', { ids });
}

export type ClaseDePortada = 'pista' | 'album' | 'artista';

/**
 * La URL de una portada. El runtime la sirve por su esquema propio: en Windows,
 * WebView2 lo expone como `http://portada.localhost`.
 */
export function urlPortada(clase: ClaseDePortada, id: number, tamano: number): string {
  const ruta = `${clase}/${id}/${tamano}`;
  const windows = typeof navigator !== 'undefined' && navigator.userAgent.includes('Windows');
  return windows ? `http://portada.localhost/${ruta}` : `portada://localhost/${ruta}`;
}

// --- Biblioteca ------------------------------------------------------------------

/** Un tramo de canciones (como mucho 500) y el total que cumple la consulta. */
export function bibliotecaPistas(
  consulta: ConsultaPistas,
  desde: number,
  limite: number
): Promise<PaginaPistas> {
  return call<PaginaPistas>('biblioteca_pistas', { consulta, desde, limite });
}

export function bibliotecaAlbumes(
  consulta: ConsultaAlbumes,
  desde: number,
  limite: number
): Promise<PaginaAlbumes> {
  return call<PaginaAlbumes>('biblioteca_albumes', { consulta, desde, limite });
}

export function bibliotecaArtistas(
  consulta: ConsultaArtistas,
  desde: number,
  limite: number
): Promise<PaginaArtistas> {
  return call<PaginaArtistas>('biblioteca_artistas', { consulta, desde, limite });
}

/** Reproduce la lista desde la canción en `indice`. */
export function reproducirLista(consulta: ConsultaPistas, indice: number): Promise<void> {
  return call<void>('reproducir_lista', { consulta, indice });
}

export function fijarFavorita(pistaId: number, favorita: boolean): Promise<void> {
  return call<void>('fijar_favorita', { pistaId, favorita });
}

export function bibliotecaAlbum(id: number): Promise<AlbumResumen | null> {
  return call<AlbumResumen | null>('biblioteca_album', { id });
}

export function bibliotecaArtista(id: number): Promise<ArtistaResumen | null> {
  return call<ArtistaResumen | null>('biblioteca_artista', { id });
}
