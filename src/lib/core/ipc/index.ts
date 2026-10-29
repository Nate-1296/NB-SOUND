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

import type { InformeDeSalud } from '$lib/bindings';

export type { InformeDeSalud } from '$lib/bindings';

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
