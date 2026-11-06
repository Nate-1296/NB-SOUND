/**
 * Los permisos de red del sistema, para Ajustes > Permisos y los avisos de
 * Dispositivos (`cortafuegos.rs`).
 *
 * El teléfono y el Modo fiesta escuchan en la red local. Si el cortafuegos los
 * bloquea, no fallan: simplemente nadie llega, y la función parece rota. Por eso se
 * comprueba al encender cada uno y, si está bloqueado, se pide al sistema en ese
 * momento. Si se dice que no, el aviso se queda con su botón y se vuelve a pedir la
 * próxima vez que se encienda.
 */

import { type EstadoRed, type PermisosRed, redPermisos, redPermitir } from '#lib/core/ipc/index.ts';

export type Servicio = 'telefono' | 'fiesta';

class Permisos {
  red = $state<PermisosRed | null>(null);
  pidiendo = $state(false);

  /** Lo que sabe del servicio: `null` mientras no se ha comprobado. */
  estado(servicio: Servicio): EstadoRed | null {
    return this.red ? this.red[servicio] : null;
  }

  /** Si hay que avisar: está bloqueado y se puede pedir. */
  bloqueado(servicio: Servicio): boolean {
    return this.estado(servicio) === 'bloqueado';
  }

  async comprobar(): Promise<PermisosRed | null> {
    this.red = await redPermisos().catch(() => this.red);
    return this.red;
  }

  /** Pide al sistema que los deje pasar. Devuelve si quedaron abiertos. */
  async pedir(servicio: Servicio): Promise<boolean> {
    if (this.pidiendo) return false;
    this.pidiendo = true;
    try {
      this.red = await redPermitir().catch(() => this.red);
    } finally {
      this.pidiendo = false;
    }
    return !this.bloqueado(servicio);
  }

  /**
   * Al encender el teléfono o la fiesta: se comprueba y, si el cortafuegos lo
   * bloquea, se pide una vez. Si se dice que no, el aviso queda en pantalla.
   */
  async alEncender(servicio: Servicio): Promise<void> {
    const red = await this.comprobar();
    if (red?.[servicio] === 'bloqueado' && red.sePuedePedir) await this.pedir(servicio);
  }
}

export const permisos = new Permisos();
