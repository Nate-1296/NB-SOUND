/**
 * Aritmética de la lista virtualizada.
 *
 * NB Books cambió su ventana virtual por páginas (su F1.6.16) por dos defectos:
 * el tamaño del bloque dependía de la altura de la ventana, así que desplazarse
 * movía el origen de la petición y la lista se rehacía sola; y sin sitios a los
 * que saltar, con 152.080 obras no se llegaba a ninguna parte. Aquí se evitan los
 * dos sin renunciar al desplazamiento continuo, que es lo que se espera de una
 * lista de canciones:
 *
 * * **Los bloques tienen tamaño fijo y origen alineado** (`TAM_BLOQUE`): bajar
 *   tres filas nunca cambia qué bloque se pide.
 * * **Las filas tienen alto fijo**, así que la posición de cualquier fila se
 *   calcula sin medir nada y el salto por letra (F2.2.3) es una suma.
 *
 * F0.4.7 lo midió en WebKitGTK: 0 fotogramas largos con 100.000 filas
 * (docs/audit/2026-10-29-prototipo-lista.md).
 */

/** Filas por bloque que se piden al runtime. */
export const TAM_BLOQUE = 256;

/** Filas que se pintan por encima y por debajo de lo visible. */
export const MARGEN = 8;

export interface Ventana {
  /** Primera fila que se pinta. */
  desde: number;
  /** Una más que la última fila que se pinta. */
  hasta: number;
  /** Desplazamiento vertical de la primera fila pintada, en píxeles. */
  desplazamiento: number;
}

/** Qué filas hay que pintar para un desplazamiento y un alto de vista dados. */
export function calcularVentana(
  total: number,
  altoFila: number,
  scrollTop: number,
  altoVista: number,
  margen = MARGEN
): Ventana {
  if (total <= 0 || altoFila <= 0) return { desde: 0, hasta: 0, desplazamiento: 0 };
  const primera = Math.floor(Math.max(0, scrollTop) / altoFila);
  const visibles = Math.ceil(Math.max(0, altoVista) / altoFila) + 1;
  const desde = Math.max(0, Math.min(total - 1, primera - margen));
  const hasta = Math.min(total, primera + visibles + margen);
  return { desde, hasta, desplazamiento: desde * altoFila };
}

/** Los bloques (por índice) que cubren las filas [desde, hasta). */
export function bloquesNecesarios(desde: number, hasta: number): number[] {
  if (hasta <= desde) return [];
  const primero = Math.floor(desde / TAM_BLOQUE);
  const ultimo = Math.floor((hasta - 1) / TAM_BLOQUE);
  const bloques: number[] = [];
  for (let b = primero; b <= ultimo; b += 1) bloques.push(b);
  return bloques;
}
