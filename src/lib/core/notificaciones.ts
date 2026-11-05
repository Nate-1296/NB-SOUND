/**
 * La cola de notificaciones: qué se anuncia, cuánto dura y qué desplaza a qué.
 *
 * # Por qué existe
 *
 * En NB Books, hasta F1.6.15, la aplicación **no decía nunca qué había pasado**. Cada fallo
 * del runtime se guardaba en una variable que solo se pintaba dentro del panel
 * de estado, y ese panel solo aparece cuando hay un componente en mal estado:
 * abrir un documento que falla, guardar una nota que falla o importar una
 * carpeta que falla dejaban la pantalla exactamente igual que si hubiera ido
 * bien. Lo confirmado sufría lo mismo por el otro lado: anotar, resaltar,
 * marcar o descargar no dejaban ninguna señal, así que no había forma de saber
 * si la pulsación había llegado.
 *
 * La referencia es el `AdwToastOverlay` de Foliate: un aviso corto, no modal,
 * que no roba el foco y que se va solo. Aquí se separa la cola —que es
 * aritmética y se prueba sin navegador— de su pintado, igual que se hizo con la
 * ventana virtualizada de F1.6.3 y con la máquina del lector de F1.6.4.
 *
 * # Lo que esta cola garantiza
 *
 * 1. **Nada se pierde por llegar tarde.** Más de `VISIBLES` a la vez no se
 *    apilan hasta tapar la pantalla: las viejas salen y las nuevas entran.
 * 2. **Un error no se va solo.** Un acierto se lee de pasada y desaparece; un
 *    fallo hay que poder leerlo dos veces, así que espera a que lo cierren.
 * 3. **Lo repetido no se repite.** Anotar cinco párrafos seguidos produce cinco
 *    veces el mismo texto: se cuenta, no se apila.
 *
 * Viene de NB Books tal cual (`src/lib/ui/notificaciones.ts`), con su contrato.
 */

/** Qué clase de cosa se está contando. */
export type ClaseDeNotificacion = 'exito' | 'error' | 'informacion';

/** Una notificación viva. */
export interface Notificacion {
  id: number;
  clase: ClaseDeNotificacion;
  /** La frase, ya traducida. Esta capa no traduce nada. */
  mensaje: string;
  /**
   * Detalle opcional, en segunda línea.
   *
   * Es donde va el código canónico de un error: el mensaje dice qué pasó en
   * palabras y el detalle dice qué fue, para poder buscarlo o contarlo.
   */
  detalle?: string;
  /** Cuántas veces ha llegado la misma. Uno significa una. */
  veces: number;
  /** Momento en que entró, en milisegundos del reloj monótono de la interfaz. */
  desde: number;
}

/** Cuántas se ven a la vez. Más que esto tapa la pantalla en lugar de informar. */
export const VISIBLES = 3;

/**
 * Cuánto dura cada clase, en milisegundos.
 *
 * # Por qué un fallo también caduca, desde el 2026-09-18
 *
 * Hasta esta fecha un fallo se quedaba hasta que alguien lo cerraba, y el motivo
 * escrito era bueno: hay que poder volver a leerlo y copiar su código. Lo que
 * pasaba en la práctica es que la esquina se llenaba de avisos que nadie había
 * cerrado, y un rincón permanentemente ocupado deja de leerse entero. Lo pidió
 * Nathan el 2026-09-18.
 *
 * **Lo que sostiene el motivo viejo es la pausa**: mientras el puntero está
 * encima o el foco dentro, la cuenta atrás se detiene —ver [`posponer`]—, así
 * que leerlo dos veces o seleccionar el código sigue siendo posible; lo que ya
 * no ocurre es que se quede ahí solo porque nadie lo miró.
 *
 * Quince segundos, que es más del doble que un aviso informativo: un fallo lleva
 * dos líneas y la segunda es un código que hay que poder leer sin prisa.
 */
export const DURACION: Readonly<Record<ClaseDeNotificacion, number | null>> = {
  exito: 4000,
  informacion: 6000,
  error: 15000
};

/** Lo que hace falta para crear una notificación. El resto lo pone la cola. */
export interface PeticionDeAviso {
  clase: ClaseDeNotificacion;
  mensaje: string;
  detalle?: string;
}

/**
 * Añade una notificación a la cola y devuelve la cola resultante.
 *
 * Función pura: no toca relojes ni temporizadores. El momento entra como
 * argumento para que la prueba pueda avanzar el tiempo sin esperarlo.
 */
export function encolar(
  cola: readonly Notificacion[],
  peticion: PeticionDeAviso,
  ahora: number,
  siguienteId: number
): Notificacion[] {
  // Lo repetido se cuenta en la que ya está, y vuelve a empezar su cuenta atrás:
  // la segunda vez que pasa algo es tan reciente como la primera.
  const igual = cola.findIndex(
    (n) =>
      n.clase === peticion.clase && n.mensaje === peticion.mensaje && n.detalle === peticion.detalle
  );
  if (igual >= 0) {
    const repetida = cola[igual] as Notificacion;
    return cola.map((n, i) =>
      i === igual ? { ...repetida, veces: repetida.veces + 1, desde: ahora } : n
    );
  }

  const nueva: Notificacion = { ...peticion, id: siguienteId, veces: 1, desde: ahora };
  // Las más viejas salen por arriba. Se descartan las primeras y no las últimas
  // porque lo último que pasó es lo que el usuario está mirando.
  return [...cola, nueva].slice(-VISIBLES);
}

/**
 * Retrasa la cuenta atrás de todas, como si el tiempo no hubiera pasado.
 *
 * Es lo que hace que un aviso no se vaya mientras alguien lo está leyendo: quien
 * pinta llama a esto en cada repaso mientras el puntero está encima o el foco
 * dentro. Se mueve el momento de entrada en lugar de guardar un estado de pausa
 * por notificación, para que la cola siga siendo una lista de datos y no una
 * máquina con dos modos.
 */
export function posponer(cola: readonly Notificacion[], delta: number): Notificacion[] {
  if (delta <= 0) return [...cola];
  return cola.map((n) => ({ ...n, desde: n.desde + delta }));
}

/** Quita una notificación por su identificador. */
export function descartar(cola: readonly Notificacion[], id: number): Notificacion[] {
  return cola.filter((n) => n.id !== id);
}

/**
 * Las que ya han cumplido su tiempo.
 *
 * Se devuelve la cola sin ellas, no la lista de caducadas: quien llama quiere el
 * estado siguiente y no una diferencia que tendría que aplicar.
 */
export function caducar(cola: readonly Notificacion[], ahora: number): Notificacion[] {
  return cola.filter((n) => {
    const duracion = DURACION[n.clase];
    return duracion === null || ahora - n.desde < duracion;
  });
}
