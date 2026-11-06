import { describe, expect, it } from 'vitest';

import { ANCHO_MINIMO, BARRA_REPRODUCCION, clasificarAncho, tramoReproduccion } from './anchos';

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

describe('tramos de la barra de reproducción', () => {
  it('cada umbral pertenece al tramo que empieza en él', () => {
    expect(tramoReproduccion(BARRA_REPRODUCCION.media - 1)).toBe('estrecha');
    expect(tramoReproduccion(BARRA_REPRODUCCION.media)).toBe('media');
    expect(tramoReproduccion(BARRA_REPRODUCCION.amplia - 1)).toBe('media');
    expect(tramoReproduccion(BARRA_REPRODUCCION.amplia)).toBe('amplia');
  });

  it('la ventana más estrecha que se permite cae en el tramo estrecho', () => {
    // 720 px de ventana menos el riel de la barra lateral.
    expect(tramoReproduccion(720 - 80)).toBe('estrecha');
  });

  it('sin medir todavía no se esconde nada', () => {
    expect(tramoReproduccion(0)).toBe('amplia');
    expect(tramoReproduccion(Number.NaN)).toBe('amplia');
  });
});
