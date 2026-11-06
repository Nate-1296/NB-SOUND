/**
 * Los teléfonos, para Ajustes > Dispositivos y para el selector de la barra de
 * reproducción. El servidor avisa de cada cambio (`movil:cambio`) y aquí se vuelve
 * a pedir la lista: son pocos y el aviso no dice qué cambió.
 */

import {
  alCambiarLosTelefonos,
  type EstadoMovil,
  movilEstado,
  movilPermitir,
  movilQuitar,
  movilTelefonos,
  type Telefono
} from '#lib/core/ipc/index.ts';

class Telefonos {
  estado = $state<EstadoMovil>({ activo: false, direccion: null, alArrancar: false });
  lista = $state<Telefono[]>([]);
  /** Los que manejan este equipo ahora mismo. */
  readonly controlando = $derived(this.lista.filter((t) => t.controlando));
  #arrancado = false;
  #pendiente: ReturnType<typeof setTimeout> | null = null;

  #vigia: ReturnType<typeof setInterval> | null = null;

  async refrescar(): Promise<void> {
    const [estado, lista] = await Promise.all([movilEstado(), movilTelefonos()]);
    this.estado = estado;
    this.lista = lista;
    this.#vigilar();
  }

  /**
   * "Conectado" sale de la última vez que el teléfono habló con el equipo: cuando
   * deja de hablar (se cerró la app) no llega ningún aviso, y antes la lista se
   * quedaba en "Conectado ahora" para siempre. Mientras haya alguno conectado, se
   * vuelve a pedir cada pocos segundos; sin ninguno, no se pregunta nada.
   */
  #vigilar(): void {
    const hayConectados = this.lista.some((t) => t.conectado);
    if (hayConectados && !this.#vigia) {
      this.#vigia = setInterval(() => void this.refrescar(), 10_000);
    } else if (!hayConectados && this.#vigia) {
      clearInterval(this.#vigia);
      this.#vigia = null;
    }
  }

  /** Se llama una vez, desde la carcasa. */
  async arrancar(): Promise<void> {
    if (this.#arrancado) return;
    this.#arrancado = true;
    // Una descarga con muchos tramos avisa muchas veces: se agrupan.
    await alCambiarLosTelefonos(() => {
      if (this.#pendiente) return;
      this.#pendiente = setTimeout(() => {
        this.#pendiente = null;
        void this.refrescar();
      }, 300);
    });
    await this.refrescar();
  }

  async permitir(activo: boolean): Promise<void> {
    this.estado = await movilPermitir(activo);
  }

  async quitar(id: number): Promise<void> {
    await movilQuitar(id);
    this.lista = this.lista.filter((t) => t.id !== id);
  }
}

export const telefonos = new Telefonos();
