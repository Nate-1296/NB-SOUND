/**
 * El avisador: el único sitio por el que la aplicación cuenta lo que ha pasado.
 *
 * Es un singleton, y como en NB Books, de donde viene: hay una
 * pantalla, y dos colas de avisos compitiendo por la misma esquina se taparían
 * la una a la otra. La cola vive en `notificaciones.ts`, que es pura; aquí solo
 * está el reloj y el estado reactivo.
 *
 * **No traduce.** El texto llega ya traducido de quien llama, que es el que
 * tiene el diccionario a mano. Un avisador que tradujera obligaría a que cada
 * clave del diccionario pasara por aquí.
 */

import {
  type ClaseDeNotificacion,
  caducar,
  descartar,
  encolar,
  type Notificacion,
  type PeticionDeAviso,
  posponer
} from './notificaciones';

let cola = $state<Notificacion[]>([]);
let siguienteId = 1;

/**
 * Si la cuenta atrás está detenida porque alguien está mirando.
 *
 * Lo enciende quien pinta cuando el puntero entra en la pila o el foco cae
 * dentro. Sin esto, un fallo con su código podría irse a mitad de leerlo, que es
 * el motivo por el que antes no caducaba.
 */
let pausada = false;

/**
 * Repaso periódico de la cola.
 *
 * Uno solo para todas, y solo mientras hay algo que caducar: un temporizador por
 * notificación deja temporizadores vivos cuando la ventana se cierra a mitad, y
 * uno permanente despierta el proceso cada segundo sin nada que hacer.
 */
let repaso: ReturnType<typeof setInterval> | null = null;

/** Cada cuánto se repasa la cola, en milisegundos. */
const REPASO = 250;

function vigilar(): void {
  if (repaso !== null) return;
  repaso = setInterval(() => {
    // En pausa no se caduca nada: se mueve el reloj de cada aviso, para que al
    // soltar siga por donde iba en lugar de empezar de cero.
    if (pausada) {
      cola = posponer(cola, REPASO);
      return;
    }
    cola = caducar(cola, Date.now());
    if (cola.length === 0 && repaso !== null) {
      clearInterval(repaso);
      repaso = null;
    }
  }, REPASO);
}

function anunciar(peticion: PeticionDeAviso): void {
  cola = encolar(cola, peticion, Date.now(), siguienteId);
  siguienteId += 1;
  vigilar();
}

/**
 * El avisador.
 *
 * Se usa como `notificar.exito('Nota guardada')`. Los tres verbos existen para
 * que quien llama no tenga que acordarse de una cadena: pasar la clase como
 * texto invita a escribirla mal y a que el aviso salga con el color que no es.
 */
export const notificar = {
  exito(mensaje: string, detalle?: string): void {
    anunciar({ clase: 'exito', mensaje, detalle });
  },
  informacion(mensaje: string, detalle?: string): void {
    anunciar({ clase: 'informacion', mensaje, detalle });
  },
  /**
   * Un fallo. No caduca: se queda hasta que lo cierren.
   *
   * El detalle es el sitio del código canónico. Nunca se enseña
   * `error.message`: en un `NsError` el mensaje **es** el código, y el texto en
   * palabras lo pone quien llama, con su diccionario.
   */
  error(mensaje: string, detalle?: string): void {
    anunciar({ clase: 'error', mensaje, detalle });
  }
};

/** Lo que hay que pintar, y cómo se quita. */
export const notificaciones = {
  get lista(): readonly Notificacion[] {
    return cola;
  },
  cerrar(id: number): void {
    cola = descartar(cola, id);
  },
  /**
   * Detiene o reanuda la cuenta atrás de todos los avisos.
   *
   * La enciende quien pinta mientras el puntero está encima o el foco dentro: un
   * fallo lleva su código en la segunda línea, y que se vaya a mitad de copiarlo
   * sería el defecto que se arregló al dejar de hacerlos eternos.
   */
  pausar(detenida: boolean): void {
    pausada = detenida;
  },
  /** Vacía la cola. Solo para las pruebas: en la aplicación nada la usa. */
  vaciar(): void {
    cola = [];
    if (repaso !== null) {
      clearInterval(repaso);
      repaso = null;
    }
  }
};

export type { ClaseDeNotificacion, Notificacion };
