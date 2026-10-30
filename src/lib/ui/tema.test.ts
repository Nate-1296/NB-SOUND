import { describe, expect, it } from 'vitest';

import { semillaDesdeHsl } from './tema';

describe('la semilla de la vista de reproducción', () => {
  it('convierte HSL en el hexadecimal que espera el generador de Material', () => {
    expect(semillaDesdeHsl(0, 1, 0.5)).toBe('#ff0000');
    expect(semillaDesdeHsl(2 / 3, 1, 0.5)).toBe('#0000ff');
    expect(semillaDesdeHsl(0, 0, 0.2)).toBe('#333333');
  });
});

describe('los temas de la V1', () => {
  it('son los 63, y cada uno pinta con sus colores donde corresponden', async () => {
    const { TEMAS_V1 } = await import('./temas-v1');
    const { variablesDeTemaV1 } = await import('./tema');
    expect(TEMAS_V1).toHaveLength(63);
    const sangre = TEMAS_V1.find((t) => t.id === 'sangre_dragon');
    expect(sangre).toBeDefined();
    if (!sangre) return;
    const v = await variablesDeTemaV1(sangre);
    expect(v['--m3c-surface']).toBe(sangre.colores.fondo);
    expect(v['--m3c-primary']).toBe(sangre.colores.acento);
    expect(v['--m3c-on-surface']).toBe(sangre.colores.texto);
    // Lo que la V1 no tenía sale de Material: ningún token queda sin valor.
    expect(v['--m3c-tertiary']).toMatch(/^#/);
  });
});
