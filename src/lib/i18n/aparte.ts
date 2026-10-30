/**
 * Punto de entrada a los textos de lo que se carga aparte del arranque. Solo lo
 * importan módulos diferidos: importarlo desde el arranque lo metería en él.
 */
import { esAparte } from './es-aparte';

export type { TextosAparte } from './es-aparte';

export const textosAparte = esAparte;
