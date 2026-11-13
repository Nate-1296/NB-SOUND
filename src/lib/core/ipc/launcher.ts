import type { EstadoEnlaceLauncher } from '#lib/bindings/index.ts';
import { call, escuchar } from './index.ts';

export function estadoEnlaceLauncher(): Promise<EstadoEnlaceLauncher> {
  return call<EstadoEnlaceLauncher>('launcher_estado');
}
export function responderLauncher(id: string, permitir: boolean): Promise<void> {
  return call<void>('launcher_responder', { id, permitir });
}
export function revocarLauncher(): Promise<void> {
  return call<void>('launcher_revocar');
}
export function permitirSolicitudesLauncher(): Promise<void> {
  return call<void>('launcher_permitir_solicitudes');
}
export function alCambiarEnlaceLauncher(cada: () => void) {
  return escuchar<void>('launcher:cambio', cada);
}
export type { EstadoEnlaceLauncher };
