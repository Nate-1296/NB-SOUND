import { describe, expect, it } from 'vitest';
import { frecuenciaMasReciente } from './frecuencia.ts';

describe('frecuencia compartida', () => {
  const estado = (sequence: number, cadaDias: number, epoch = 'a') => ({
    cadaDias,
    revision: { epoch, sequence }
  });

  it('no revierte un evento nuevo con la respuesta de una consulta anterior', () => {
    const actual = estado(2, 7);
    expect(frecuenciaMasReciente(actual, estado(1, 1))).toBe(actual);
  });

  it('acepta confirmaciones nuevas y no compara contadores entre épocas', () => {
    expect(frecuenciaMasReciente(estado(1, 1), estado(2, 7))?.cadaDias).toBe(7);
    expect(frecuenciaMasReciente(estado(10, 7), estado(0, 1, 'b'))?.cadaDias).toBe(1);
  });

  it('la indisponibilidad retira el estado utilizable para escribir', () => {
    expect(frecuenciaMasReciente(estado(2, 7), null)).toBeNull();
  });
});
