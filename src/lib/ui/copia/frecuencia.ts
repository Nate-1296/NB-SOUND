import type { FrecuenciaCopia } from '#lib/core/ipc/aparte.ts';

/** Una respuesta que llegó tarde no revierte una notificación ya confirmada. */
export function frecuenciaMasReciente(
  actual: FrecuenciaCopia | null,
  siguiente: FrecuenciaCopia | null
): FrecuenciaCopia | null {
  if (
    actual &&
    siguiente &&
    actual.revision.epoch === siguiente.revision.epoch &&
    actual.revision.sequence > siguiente.revision.sequence
  ) {
    return actual;
  }
  return siguiente;
}
