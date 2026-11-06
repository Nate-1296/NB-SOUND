import { describe, expect, it } from 'vitest';

import { semillaDesdeHsl } from './tema';

describe('la semilla de la vista de reproducción', () => {
  it('convierte HSL en el hexadecimal que espera el generador de Material', () => {
    expect(semillaDesdeHsl(0, 1, 0.5)).toBe('#ff0000');
    expect(semillaDesdeHsl(2 / 3, 1, 0.5)).toBe('#0000ff');
    expect(semillaDesdeHsl(0, 0, 0.2)).toBe('#333333');
  });
});

describe('los temas', () => {
  it('son los 63, y cada uno pinta con sus colores donde corresponden', async () => {
    const { TEMAS } = await import('./temas');
    const { variablesDeTema } = await import('./tema');
    expect(TEMAS).toHaveLength(63);
    const sangre = TEMAS.find((t) => t.id === 'sangre_dragon');
    expect(sangre).toBeDefined();
    if (!sangre) return;
    const v = await variablesDeTema(sangre);
    expect(v['--m3c-surface']).toBe(sangre.colores.fondo);
    expect(v['--m3c-primary']).toBe(sangre.colores.acento);
    expect(v['--m3c-on-surface']).toBe(sangre.colores.texto);
    // Lo que el tema no define sale de Material: ningún token queda sin valor.
    expect(v['--m3c-tertiary']).toMatch(/^#/);
  });
});
