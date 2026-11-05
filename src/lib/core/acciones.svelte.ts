/**
 * Lo que se hace con una canción desde cualquier lista: marcarla como favorita y
 * mandarla a la cola. Antes cada vista tenía su copia, cada una con su forma de
 * recordar el cambio, y la barra de reproducción no se enteraba de lo marcado en
 * una lista ni al revés.
 *
 * Las favoritas se apuntan aquí en cuanto se pulsan, sin esperar al runtime, y
 * vuelven a como estaban si no se pudieron guardar. Las listas no se recargan por
 * esto: cada fila pregunta por su pista a [`favoritas.es`].
 */

import { SvelteMap } from 'svelte/reactivity';

import { fijarFavorita, type PistaResumen, reproductorOrden } from '#lib/core/ipc/index.ts';
import { notificar } from '#lib/core/notificaciones.svelte.ts';
import { textos } from '#lib/i18n/index.ts';

class Favoritas {
  /** Lo cambiado en esta sesión, por id: manda sobre lo que trajo cada lista. */
  #cambios = new SvelteMap<number, boolean>();

  es(p: Pick<PistaResumen, 'id' | 'favorita'>): boolean {
    return this.#cambios.get(p.id) ?? p.favorita;
  }

  async alternar(p: Pick<PistaResumen, 'id' | 'favorita'>): Promise<void> {
    const antes = this.es(p);
    this.#cambios.set(p.id, !antes);
    try {
      await fijarFavorita(p.id, !antes);
    } catch {
      this.#cambios.set(p.id, antes);
      notificar.error(textos.biblioteca.favoritaFallo);
    }
  }
}

export const favoritas = new Favoritas();

/** A la cola: al final, o justo detrás de la que suena ("Reproducir a continuación"). */
export async function encolar(ids: number[], justoDespues: boolean): Promise<void> {
  if (ids.length === 0) return;
  try {
    await reproductorOrden({ tipo: 'agregar', ids, justoDespues });
    const t = textos.biblioteca;
    notificar.exito(justoDespues ? t.sonaraDespues(ids.length) : t.anadidasACola(ids.length));
  } catch {
    notificar.error(textos.biblioteca.colaFallo);
  }
}
