/**
 * Apariencia de NB Sound: esquema claro u oscuro, contraste y color de acento.
 *
 * Contrato: docs/adr/decisions/ADR-008-sistema-de-diseno.md
 *
 * La paleta de fábrica sale de `src/paletas.css`, que genera
 * `scripts/generar-paletas.mjs`, para que el primer fotograma ya tenga sus
 * colores. Solo cuando hay un acento propio o un color de portada se calcula la
 * paleta en caliente, y entonces se carga el generador de Material a demanda: el
 * arranque no lo paga.
 */

import { ACENTO_POR_DEFECTO } from './acentos';

/** Lo que elige el usuario. `sistema` sigue al sistema operativo. */
export type Tema = 'sistema' | 'claro' | 'oscuro';
/** Lo que se pinta de verdad. */
export type Esquema = 'claro' | 'oscuro';
export type Contraste = 'normal' | 'alto';

export const TEMAS: readonly Tema[] = ['sistema', 'claro', 'oscuro'];
export const ESQUEMAS: readonly Esquema[] = ['claro', 'oscuro'];

/**
 * Nivel de contraste de Material para cada opción. El alto no cambia la semilla:
 * recalcula cada par de colores contra su fondo con una curva más exigente, que
 * es lo que NB Books midió como el único alto contraste real.
 */
export const NIVEL_DE_CONTRASTE: Readonly<Record<Contraste, number>> = {
  normal: 0,
  alto: 1
};

/** La semilla con la que se generan las paletas de fábrica. */
export const SEMILLA_DE_FABRICA = ACENTO_POR_DEFECTO.semilla;

export function resolverEsquema(tema: Tema, sistemaOscuro: boolean): Esquema {
  if (tema === 'sistema') return sistemaOscuro ? 'oscuro' : 'claro';
  return tema;
}

export function elSistemaPrefiereOscuro(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches;
}

export interface Apariencia {
  tema: Tema;
  contraste: Contraste;
  /** Semilla del acento; `null` es la de fábrica. */
  semilla: string | null;
}

/** La V1 solo tenía esquema oscuro, y la V2 arranca igual (enmienda de ADR-008). */
export const APARIENCIA_DE_FABRICA: Apariencia = {
  tema: 'oscuro',
  contraste: 'normal',
  semilla: null
};

/**
 * Aplica la apariencia al elemento raíz.
 *
 * Con la semilla de fábrica basta con los atributos: las reglas de `paletas.css`
 * hacen el resto. Con otra semilla se escriben las variables en línea, que pisan
 * a las de la hoja.
 */
export async function aplicarApariencia(
  raiz: HTMLElement,
  apariencia: Apariencia,
  sistemaOscuro: boolean
): Promise<void> {
  const esquema = resolverEsquema(apariencia.tema, sistemaOscuro);
  raiz.dataset.esquema = esquema;
  raiz.dataset.contraste = apariencia.contraste;

  for (const nombre of Array.from(raiz.style)) {
    if (nombre.startsWith('--m3c-')) raiz.style.removeProperty(nombre);
  }
  const semilla = apariencia.semilla;
  if (semilla === null || semilla.toLowerCase() === SEMILLA_DE_FABRICA) return;

  const { generarVariablesM3 } = await import('./generadorM3');
  const variables = generarVariablesM3(
    semilla,
    esquema === 'oscuro',
    NIVEL_DE_CONTRASTE[apariencia.contraste]
  );
  for (const [nombre, valor] of Object.entries(variables)) {
    raiz.style.setProperty(nombre, valor);
  }
}
