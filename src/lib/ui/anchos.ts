/**
 * Las tres clases de ancho de la carcasa.
 *
 * Es la **única fuente** de los puntos de corte, como en NB Books: la carcasa
 * pone `data-ancho` y las hojas de estilo deciden por ese atributo, nunca con una
 * consulta de medios por ancho (lo vigila `scripts/check-ui.mjs`).
 */

export type ClaseDeAncho = 'compacto' | 'medio' | 'amplio';

/**
 * Ancho mínimo, en píxeles CSS, de cada clase. Por debajo de 1080 la barra
 * lateral se queda en riel; por debajo de 720 el reproductor esconde sus
 * controles secundarios.
 */
export const ANCHO_MINIMO: Readonly<Record<ClaseDeAncho, number>> = {
  compacto: 0,
  medio: 720,
  amplio: 1080
};

/** Clasifica un ancho. Un ancho no finito se trata como compacto. */
export function clasificarAncho(px: number): ClaseDeAncho {
  if (!Number.isFinite(px)) return 'compacto';
  if (px >= ANCHO_MINIMO.amplio) return 'amplio';
  if (px >= ANCHO_MINIMO.medio) return 'medio';
  return 'compacto';
}
