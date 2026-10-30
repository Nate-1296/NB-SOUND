import { describe, expect, it } from 'vitest';

import { bloquesNecesarios, calcularVentana, TAM_BLOQUE } from './ventana';

describe('la ventana virtual', () => {
  it('pinta lo visible más el margen, sin pasarse del total', () => {
    const v = calcularVentana(1000, 56, 56 * 100, 560, 8);
    expect(v.desde).toBe(92);
    expect(v.hasta).toBe(100 + 11 + 8);
    expect(v.desplazamiento).toBe(92 * 56);
    expect(calcularVentana(5, 56, 0, 10_000).hasta).toBe(5);
    expect(calcularVentana(0, 56, 0, 560)).toEqual({ desde: 0, hasta: 0, desplazamiento: 0 });
  });

  it('desplazarse dentro de un bloque no cambia qué bloque se pide', () => {
    const a = calcularVentana(100_000, 56, 56 * 10, 800);
    const b = calcularVentana(100_000, 56, 56 * 13, 800);
    expect(bloquesNecesarios(a.desde, a.hasta)).toEqual([0]);
    expect(bloquesNecesarios(b.desde, b.hasta)).toEqual([0]);
  });

  it('una ventana que cruza el borde pide los dos bloques', () => {
    expect(bloquesNecesarios(TAM_BLOQUE - 3, TAM_BLOQUE + 3)).toEqual([0, 1]);
    expect(bloquesNecesarios(10, 10)).toEqual([]);
  });
});
