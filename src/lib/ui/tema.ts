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
import type { TemaV1 } from './temas-v1';

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

/**
 * La semilla, en hexadecimal, de un color HSL de 0 a 1: el del fondo de la vista
 * de reproducción, que se aplica como paleta de Material sobre esa vista.
 */
export function semillaDesdeHsl(h: number, s: number, l: number): string {
  const a = s * Math.min(l, 1 - l);
  const canal = (n: number) => {
    const k = (n + h * 12) % 12;
    const v = l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    return Math.round(v * 255)
      .toString(16)
      .padStart(2, '0');
  };
  return `#${canal(0)}${canal(8)}${canal(4)}`;
}

/** Luminancia relativa de un color `#rrggbb`, de 0 a 1. */
function luminancia(hex: string): number {
  const v = (i: number) => {
    const c = Number.parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.039_28 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * v(1) + 0.7152 * v(3) + 0.0722 * v(5);
}

/** El texto que se lee sobre un color: el más contrastado de los dos extremos. */
function textoSobre(hex: string, claro: string, oscuro: string): string {
  return luminancia(hex) > 0.4 ? oscuro : claro;
}

/**
 * Las variables de Material de un tema de la V1. Se parte de la paleta que Material
 * genera desde su acento, para que no falte ningún token, y encima se ponen los
 * colores de la V1 donde cada uno corresponde: así el tema se ve como en la V1 y
 * los componentes que usan tokens que la V1 no tenía siguen siendo coherentes.
 */
export async function variablesDeTemaV1(tema: TemaV1): Promise<Record<string, string>> {
  const c = tema.colores;
  const oscuro = luminancia(c.fondo) < 0.4;
  const { generarVariablesM3 } = await import('./generadorM3');
  const base = generarVariablesM3(c.acento, oscuro, 0);
  return {
    ...base,
    '--m3c-surface': c.fondo,
    '--m3c-surface-dim': c.fondo,
    '--m3c-surface-bright': c.superficieAlt,
    '--m3c-surface-container-lowest': c.fondo,
    '--m3c-surface-container-low': c.fondoElevado,
    '--m3c-surface-container': c.superficie,
    '--m3c-surface-container-high': c.superficieAlt,
    '--m3c-surface-container-highest': c.seleccion,
    '--m3c-on-surface': c.texto,
    '--m3c-on-surface-variant': c.textoSec,
    '--m3c-outline': c.textoMuted,
    '--m3c-outline-variant': c.borde,
    '--m3c-primary': c.acento,
    '--m3c-on-primary': textoSobre(c.acento, c.texto, c.fondo),
    '--m3c-primary-container': c.acentoFuerte,
    '--m3c-on-primary-container': textoSobre(c.acentoFuerte, c.texto, c.fondo),
    '--m3c-secondary-container': c.seleccion,
    '--m3c-on-secondary-container': c.texto,
    '--m3c-error': c.peligro,
    '--m3c-on-error': textoSobre(c.peligro, c.texto, c.fondo),
    '--m3c-inverse-surface': c.texto,
    '--m3c-inverse-on-surface': c.fondo,
    '--ns-exito': c.exito,
    '--ns-advertencia': c.advertencia
  };
}

/** El tema de fábrica, como en la V1 (`negro_puro` era su valor por defecto). */
export const TEMA_V1_DE_FABRICA = 'negro_puro';

/**
 * Aplica un tema de la V1 al elemento raíz. Devuelve las variables aplicadas, que
 * la carcasa guarda para pintar el siguiente arranque sin esperar al runtime.
 */
export async function aplicarTemaV1(
  raiz: HTMLElement,
  id: string
): Promise<Record<string, string> | null> {
  const { TEMAS_V1 } = await import('./temas-v1');
  const tema = TEMAS_V1.find((t) => t.id === id);
  if (!tema) return null;
  const variables = await variablesDeTemaV1(tema);
  aplicarVariables(raiz, variables, luminancia(tema.colores.fondo) < 0.4);
  return variables;
}

/** Escribe unas variables ya calculadas: el primer pintado no espera a nada. */
export function aplicarVariables(
  raiz: HTMLElement,
  variables: Record<string, string>,
  oscuro: boolean
): void {
  raiz.dataset.esquema = oscuro ? 'oscuro' : 'claro';
  for (const nombre of Array.from(raiz.style)) {
    if (
      nombre.startsWith('--m3c-') ||
      nombre.startsWith('--ns-exito') ||
      nombre.startsWith('--ns-advertencia')
    ) {
      raiz.style.removeProperty(nombre);
    }
  }
  for (const [nombre, valor] of Object.entries(variables)) raiz.style.setProperty(nombre, valor);
}
