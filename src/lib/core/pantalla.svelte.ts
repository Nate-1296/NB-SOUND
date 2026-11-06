/**
 * La pantalla completa de la ventana (F11) y los controles que se esconden en
 * ella mientras el ratón no se mueve, como la reproducción ampliada.
 *
 * Una sola fuente: la ventana. Se puede entrar y salir también desde el gestor
 * de ventanas, así que el estado se vuelve a leer cada vez que cambia el tamaño
 * en lugar de suponerlo por lo que pulsó el usuario.
 */

import { estaEnPantallaCompleta, fijarPantallaCompleta } from '#lib/core/ipc/index.ts';

class Pantalla {
  completa = $state(false);
  /** Barra y cabecera visibles; en pantalla completa se esconden en reposo. */
  controlesVisibles = $state(true);

  async alternar(): Promise<void> {
    await fijarPantallaCompleta(!this.completa).catch(() => undefined);
    await this.sincronizar();
  }

  async sincronizar(): Promise<void> {
    this.completa = await estaEnPantallaCompleta().catch(() => false);
    if (!this.completa) this.controlesVisibles = true;
  }
}

export const pantalla = new Pantalla();
