import { describe, expect, it } from 'vitest';

import { duracionDetallada, duracionLarga } from './formato';

describe('los formatos de duración de la V1', () => {
  it('modelo_estadisticas_formatear_duracion_detallada', () => {
    expect(duracionDetallada(86400 + 3661)).toBe('1d 1h 1m 1s');
    expect(duracionDetallada(86400)).toBe('1d');
    expect(duracionDetallada(3661)).toBe('1h 1m 1s');
    expect(duracionDetallada(3600)).toBe('1h');
    expect(duracionDetallada(125)).toBe('2m 5s');
    expect(duracionDetallada(5)).toBe('5s');
    expect(duracionDetallada(0)).toBe('0s');
    expect(duracionDetallada(null)).toBe('0s');
  });

  it('modelo_reproductor_formatea_duracion_larga_para_cola', () => {
    expect(duracionLarga(3725)).toBe('1h 2m 5s');
    expect(duracionLarga(3600)).toBe('1h 0m 0s');
    expect(duracionLarga(65)).toBe('1m 5s');
    expect(duracionLarga(5)).toBe('5s');
    expect(duracionLarga(0)).toBe('0s');
    expect(duracionLarga(-12)).toBe('0s');
    expect(duracionLarga(null)).toBe('0s');
  });
});
