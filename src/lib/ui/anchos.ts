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

/**
 * Lo que cabe en cada barra según **su propio** ancho, no el de la ventana: la
 * misma ventana deja más o menos sitio según la barra lateral esté plegada o se
 * esté en la reproducción ampliada. Antes las barras decidían por la carcasa y,
 * a 720 px, los extras pisaban "repetir" y el título se metía bajo "aleatorio".
 *
 * - Barra de reproducción: `amplia` lo tiene todo; `media` lleva letras y
 *   pantalla completa al menú ···; `estrecha` lleva además aleatorio, repetir,
 *   karaoke y el volumen. Lo que se esconde nunca se pierde: pasa al menú.
 * - Barra superior: los botones llevan su nombre solo si queda sitio para una
 *   búsqueda cómoda al lado.
 */
export type TramoDeBarra = 'estrecha' | 'media' | 'amplia';

/** Desde qué ancho de la barra de reproducción, en píxeles CSS, rige cada tramo. */
export const BARRA_REPRODUCCION: Readonly<Record<TramoDeBarra, number>> = {
  estrecha: 0,
  media: 704,
  amplia: 832
};

/** Desde qué ancho de la barra superior los botones llevan su nombre. */
export const BARRA_SUPERIOR_CON_NOMBRES = 816;

/** El tramo de la barra de reproducción. Mientras no se ha medido, `amplia`. */
export function tramoReproduccion(px: number): TramoDeBarra {
  if (!Number.isFinite(px) || px <= 0) return 'amplia';
  if (px >= BARRA_REPRODUCCION.amplia) return 'amplia';
  if (px >= BARRA_REPRODUCCION.media) return 'media';
  return 'estrecha';
}
