import { describe, expect, it } from 'vitest';

import { ANCHO_MINIMO, clasificarAncho } from './anchos';

describe('clases de ancho', () => {
  it('cada umbral pertenece a la clase que empieza en él', () => {
    expect(clasificarAncho(ANCHO_MINIMO.medio - 1)).toBe('compacto');
    expect(clasificarAncho(ANCHO_MINIMO.medio)).toBe('medio');
    expect(clasificarAncho(ANCHO_MINIMO.amplio - 1)).toBe('medio');
    expect(clasificarAncho(ANCHO_MINIMO.amplio)).toBe('amplio');
  });

  it('un ancho imposible no rompe la carcasa', () => {
    expect(clasificarAncho(Number.NaN)).toBe('compacto');
    expect(clasificarAncho(-20)).toBe('compacto');
  });
});
