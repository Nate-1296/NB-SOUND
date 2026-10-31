/**
 * Sistema transversal de notificaciones Toast (COMP-03).
 *
 * Mantiene la cola de avisos y permite notificar éxito, información, error
 * o progreso de procesos en segundo plano con auto-cierre temporizado.
 */

export type TipoNotificacion = 'exito' | 'info' | 'error' | 'progreso';

export interface Notificacion {
  id: string;
  tipo: TipoNotificacion;
  mensaje: string;
  duracionMs?: number;
  progreso?: number;
}

class GestorNotificaciones {
  lista = $state<Notificacion[]>([]);

  notificar(tipo: TipoNotificacion, mensaje: string, duracionMs = 4000): string {
    const id = Math.random().toString(36).slice(2, 9);
    const item: Notificacion = { id, tipo, mensaje, duracionMs };
    this.lista.push(item);
    if (duracionMs > 0) {
      setTimeout(() => this.quitar(id), duracionMs);
    }
    return id;
  }

  exito(mensaje: string, duracionMs = 3500): string {
    return this.notificar('exito', mensaje, duracionMs);
  }

  info(mensaje: string, duracionMs = 4000): string {
    return this.notificar('info', mensaje, duracionMs);
  }

  error(mensaje: string, duracionMs = 5000): string {
    return this.notificar('error', mensaje, duracionMs);
  }

  progreso(id: string, mensaje: string, progreso: number): void {
    const item = this.lista.find((n) => n.id === id);
    if (item) {
      item.mensaje = mensaje;
      item.progreso = progreso;
    } else {
      this.lista.push({ id, tipo: 'progreso', mensaje, progreso, duracionMs: 0 });
    }
  }

  quitar(id: string): void {
    this.lista = this.lista.filter((n) => n.id !== id);
  }
}

export const notificaciones = new GestorNotificaciones();

if (typeof window !== 'undefined') {
  window.addEventListener('ns:notificacion', (e: Event) => {
    const d = (
      e as CustomEvent<{
        tipo: TipoNotificacion | 'quitar';
        id?: string;
        mensaje?: string;
        progreso?: number;
        duracionMs?: number;
      }>
    ).detail;
    if (!d) return;
    if (d.tipo === 'quitar' && d.id) {
      notificaciones.quitar(d.id);
    } else if (
      d.tipo === 'progreso' &&
      d.id &&
      d.mensaje !== undefined &&
      d.progreso !== undefined
    ) {
      notificaciones.progreso(d.id, d.mensaje, d.progreso);
    } else if (d.mensaje) {
      notificaciones.notificar(d.tipo as TipoNotificacion, d.mensaje, d.duracionMs);
    }
  });
}
