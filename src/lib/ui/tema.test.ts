import { describe, expect, it } from 'vitest';

import { semillaDesdeHsl } from './tema';

describe('la semilla de la vista de reproducción', () => {
  it('convierte HSL en el hexadecimal que espera el generador de Material', () => {
    expect(semillaDesdeHsl(0, 1, 0.5)).toBe('#ff0000');
    expect(semillaDesdeHsl(2 / 3, 1, 0.5)).toBe('#0000ff');
    expect(semillaDesdeHsl(0, 0, 0.2)).toBe('#333333');
  });
});
