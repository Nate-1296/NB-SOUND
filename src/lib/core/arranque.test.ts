import { afterEach, describe, expect, it, vi } from 'vitest';

import { ESPERA_APARIENCIA_MS, mostrarVentanaTrasApariencia } from './arranque';

afterEach(() => {
  vi.useRealTimers();
});

describe('el primer fotograma visible', () => {
  it('muestra la ventana una sola vez cuando la apariencia carga', async () => {
    const mostrar = vi.fn(async () => {});
    await mostrarVentanaTrasApariencia(Promise.resolve(), mostrar);
    expect(mostrar).toHaveBeenCalledTimes(1);
  });

  it('muestra la ventana una sola vez cuando la apariencia se rechaza', async () => {
    const mostrar = vi.fn(async () => {});
    await mostrarVentanaTrasApariencia(Promise.reject(new Error('sin base')), mostrar);
    expect(mostrar).toHaveBeenCalledTimes(1);
  });

  it('muestra la ventana una sola vez cuando la apariencia no responde', async () => {
    vi.useFakeTimers();
    const mostrar = vi.fn(async () => {});
    const pendiente = new Promise<void>(() => {});
    const arranque = mostrarVentanaTrasApariencia(pendiente, mostrar);

    await vi.advanceTimersByTimeAsync(ESPERA_APARIENCIA_MS - 1);
    expect(mostrar).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    await arranque;

    expect(mostrar).toHaveBeenCalledTimes(1);
  });

  it('propaga el fallo de mostrar sin intentarlo otra vez', async () => {
    const fallo = new Error('sin ventana');
    const mostrar = vi.fn(async () => {
      throw fallo;
    });

    await expect(mostrarVentanaTrasApariencia(Promise.resolve(), mostrar)).rejects.toBe(fallo);
    expect(mostrar).toHaveBeenCalledTimes(1);
  });
});
