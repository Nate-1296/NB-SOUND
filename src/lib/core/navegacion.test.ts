import { describe, expect, it } from 'vitest';

import { DESTINOS, destinosVisibles, estaActivo, POR_REVISAR } from './navegacion';

describe('destinos de la barra lateral', () => {
  it('son siete fijos con Ajustes al final, como fija ADR-007', () => {
    const visibles = destinosVisibles(0);
    expect(visibles).toHaveLength(7);
    expect(visibles.at(-1)?.id).toBe('ajustes');
  });

  it('Por revisar solo aparece mientras hay algo pendiente', () => {
    expect(destinosVisibles(0)).not.toContain(POR_REVISAR);
    expect(destinosVisibles(3)).toContain(POR_REVISAR);
  });

  it('no repite rutas ni identificadores', () => {
    const todos = destinosVisibles(1);
    expect(new Set(todos.map((d) => d.ruta)).size).toBe(todos.length);
    expect(new Set(todos.map((d) => d.id)).size).toBe(todos.length);
  });

  it('la raíz solo está activa en sí misma y el resto también en sus subrutas', () => {
    const [inicio, biblioteca] = DESTINOS;
    if (!inicio || !biblioteca) throw new Error('faltan destinos');
    expect(estaActivo(inicio, '/')).toBe(true);
    expect(estaActivo(inicio, '/biblioteca')).toBe(false);
    expect(estaActivo(biblioteca, '/biblioteca/album/3')).toBe(true);
    expect(estaActivo(biblioteca, '/bibliotecas')).toBe(false);
  });
});
