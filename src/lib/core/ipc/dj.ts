/**
 * El puente del DJ Privado (F6.1.6). Solo lo importa su vista, que se carga
 * aparte: no entra en el arranque (`check-paquete`).
 */

import type { UnlistenFn } from '@tauri-apps/api/event';
import type { FilaHistorial, PedidoDj, PistaDeSesion, Tecnica, VistaSesionDj } from '$lib/bindings';

import { call, escuchar } from './index';

export type { FilaHistorial, PedidoDj, PistaDeSesion, Tecnica, VistaSesionDj };

/** Pide una sesión con palabras; suena en cuanto tiene su primer bloque. */
export function djPedir(peticion: string, minutos: number): Promise<PedidoDj> {
  return call<PedidoDj>('dj_pedir', { peticion, minutos });
}

export function djSesion(sesionId: number): Promise<VistaSesionDj> {
  return call<VistaSesionDj>('dj_sesion', { sesionId });
}

/** Toca una sesión desde la pista en `posicion`. */
export function djReproducir(sesionId: number, posicion = 0): Promise<void> {
  return call<void>('dj_reproducir', { sesionId, posicion });
}

export function djValorar(
  sesionId: number,
  posicion: number,
  pistaId: number,
  gusta: boolean
): Promise<void> {
  return call<void>('dj_valorar', { sesionId, posicion, pistaId, gusta });
}

/** Otra sesión con el mismo pedido; la anterior queda descartada. */
export function djRegenerar(sesionId: number): Promise<PedidoDj> {
  return call<PedidoDj>('dj_regenerar', { sesionId });
}

export function djDescartar(sesionId: number): Promise<void> {
  return call<void>('dj_descartar', { sesionId });
}

/** Guarda la sesión como playlist y devuelve su id; sin nombre, uno numerado. */
export function djGuardar(sesionId: number, nombre: string): Promise<number> {
  return call<number>('dj_guardar', { sesionId, nombre });
}

export function djHistorial(texto: string, filtro: string): Promise<FilaHistorial[]> {
  return call<FilaHistorial[]>('dj_historial', { texto, filtro });
}

export function djEliminar(sesionId: number): Promise<void> {
  return call<void>('dj_eliminar', { sesionId });
}

/** La sesión creció o cambió de estado mientras se construía. */
export function alCambiarDj(cada: (sesionId: number) => void): Promise<UnlistenFn> {
  return escuchar<number>('dj:cambio', cada);
}
