/**
 * La importación en la interfaz: el progreso que publica el runtime, si hay
 * archivos arrastrándose sobre la ventana y cuántos esperan en Por revisar (el
 * número de la barra lateral, que solo aparece si hay alguno).
 */

import {
  alArrastrarArchivos,
  alCambiarLaImportacion,
  importacionProgreso,
  type ProgresoImportacion,
  porRevisarContar
} from '$core/ipc';

const QUIETO: ProgresoImportacion = {
  activa: false,
  total: 0,
  hechos: 0,
  importadas: 0,
  sinVerificar: 0,
  porRevisar: 0,
  actual: null
};

class Importacion {
  progreso = $state<ProgresoImportacion>(QUIETO);
  arrastrando = $state(false);
  pendientes = $state(0);
  /** El resumen de la última tanda, hasta que se cierra. */
  resumen = $state<ProgresoImportacion | null>(null);
  #arrancado = false;

  async contar(): Promise<void> {
    this.pendientes = await porRevisarContar();
  }

  /** Se llama una vez, desde la carcasa. */
  async arrancar(): Promise<void> {
    if (this.#arrancado) return;
    this.#arrancado = true;
    await alArrastrarArchivos((encima) => {
      this.arrastrando = encima;
    });
    await alCambiarLaImportacion((p) => {
      const terminaba = this.progreso.activa && !p.activa;
      this.progreso = p;
      if (terminaba) {
        this.resumen = p;
        void this.contar();
      }
    });
    this.progreso = await importacionProgreso();
    await this.contar();
  }

  cerrarResumen(): void {
    this.resumen = null;
  }
}

export const importacion = new Importacion();
