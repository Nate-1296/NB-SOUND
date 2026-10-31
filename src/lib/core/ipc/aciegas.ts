/**
 * El puente de A ciegas (F6.2.2). Solo lo importa su vista, que se carga aparte:
 * no entra en el arranque (`check-paquete`).
 */

import type {
  Indicio,
  Jugada,
  Modo,
  ModoDisponible,
  ResultadoIntento,
  RetoVisible,
  Ronda
} from '$lib/bindings';

import { call } from './index';

export type { Indicio, Jugada, Modo, ModoDisponible, ResultadoIntento, RetoVisible, Ronda };

export function aciegasDisponibles(): Promise<ModoDisponible[]> {
  return call<ModoDisponible[]>('aciegas_disponibles');
}

export function aciegasRonda(): Promise<Ronda> {
  return call<Ronda>('aciegas_ronda');
}

/** Empieza una ronda; sin canciones para el modo, la ronda vuelve sin modo. */
export function aciegasIniciar(modo: Modo, retos: number, evitar: number[]): Promise<Ronda> {
  return call<Ronda>('aciegas_iniciar', { modo, retos, evitar });
}

export function aciegasJugar(jugada: Jugada): Promise<Ronda> {
  return call<Ronda>('aciegas_jugar', { jugada });
}

export function aciegasIntentar(texto: string): Promise<ResultadoIntento> {
  return call<ResultadoIntento>('aciegas_intentar', { texto });
}

/** Toca el fragmento del reto en curso por el reproductor, sin decir cuál es. */
export function aciegasFragmento(): Promise<Ronda> {
  return call<Ronda>('aciegas_fragmento');
}
