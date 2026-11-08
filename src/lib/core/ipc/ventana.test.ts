import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ show: vi.fn() }));

vi.mock('@tauri-apps/api/window', () => ({
  getCurrentWindow: () => ({ show: mocks.show })
}));

import { mostrarVentanaPrincipal } from './index';

beforeEach(() => {
  mocks.show.mockReset();
});

describe('mostrar la ventana', () => {
  it('conserva el código canónico cuando Tauri rechaza show', async () => {
    mocks.show.mockRejectedValue({ code: 'STORAGE_FAILURE' });

    await expect(mostrarVentanaPrincipal()).rejects.toEqual(
      expect.objectContaining({ code: 'STORAGE_FAILURE' })
    );
  });

  it('convierte un rechazo sin código en el error interno canónico', async () => {
    mocks.show.mockRejectedValue(new Error('detalle privado'));

    await expect(mostrarVentanaPrincipal()).rejects.toEqual(
      expect.objectContaining({ code: 'INTERNAL' })
    );
  });
});
