/**
 * La cola de avisos.
 *
 * Se prueba la aritmética y no el pintado, por el mismo motivo que en la ventana
 * virtualizada de F1.6.3: lo que puede fallar en silencio aquí es que un aviso
 * desaparezca antes de leerse o que un fallo se vaya solo, y las dos cosas son
 * cuentas de tiempo. Que el aviso se **vea** lo comprueban los recorridos de
 * Playwright, que es donde hay pantalla.
 */

import { describe, expect, it } from 'vitest';

import {
  caducar,
  DURACION,
  descartar,
  encolar,
  type Notificacion,
  posponer,
  VISIBLES
} from './notificaciones';

const peticion = (mensaje: string, clase: 'exito' | 'error' | 'informacion' = 'exito') => ({
  clase,
  mensaje
});

describe('la cola de avisos', () => {
  it('nunca enseña más avisos de los que caben en la esquina', () => {
    let cola: Notificacion[] = [];
    for (let i = 0; i < VISIBLES + 3; i += 1) {
      cola = encolar(cola, peticion(`aviso ${i}`), i, i);
    }

    expect(cola).toHaveLength(VISIBLES);
    // Lo último que pasó es lo que el usuario está mirando: son las últimas las
    // que sobreviven, no las primeras.
    expect(cola.at(-1)?.mensaje).toBe(`aviso ${VISIBLES + 2}`);
  });

  it('cuenta lo repetido en lugar de apilarlo', () => {
    let cola = encolar([], peticion('Marcador puesto'), 0, 1);
    cola = encolar(cola, peticion('Marcador puesto'), 500, 2);
    cola = encolar(cola, peticion('Marcador puesto'), 900, 3);

    expect(cola).toHaveLength(1);
    expect(cola[0]?.veces).toBe(3);
  });

  it('a lo repetido le vuelve a empezar la cuenta atrás', () => {
    let cola = encolar([], peticion('Marcador puesto'), 0, 1);
    cola = encolar(cola, peticion('Marcador puesto'), 3000, 2);

    // Con la cuenta de la primera, a los 4001 ms ya habría caducado; con la de
    // la segunda, todavía no. La segunda vez que pasa algo es tan reciente como
    // la primera.
    expect(caducar(cola, 4001)).toHaveLength(1);
    expect(caducar(cola, 7001)).toHaveLength(0);
  });

  it('un mensaje distinto no se cuenta como el mismo', () => {
    let cola = encolar([], peticion('Nota guardada'), 0, 1);
    cola = encolar(cola, peticion('Marcador puesto'), 0, 2);

    expect(cola).toHaveLength(2);
  });

  it('un fallo dura más que lo demás, y se va solo', () => {
    const cola = encolar([], peticion('No se pudo escribir', 'error'), 0, 1);
    const error = DURACION.error as number;
    const informacion = DURACION.informacion as number;

    // Más que un aviso informativo, porque lleva dos líneas y la segunda es un
    // código. Y **caduca**: hasta el 2026-09-18 no lo hacía, y la esquina
    // acababa ocupada por avisos que nadie había cerrado.
    expect(error).toBeGreaterThan(informacion);
    expect(caducar(cola, error - 1)).toHaveLength(1);
    expect(caducar(cola, error)).toHaveLength(0);
  });

  /**
   * **Lo que sostiene que un fallo pueda caducar.** Mientras alguien lo mira, el
   * tiempo no corre: sin esto, un código de error se podría ir a mitad de
   * copiarlo, que es justo lo que hacía que antes fueran eternos.
   */
  it('mientras se mira, la cuenta atrás no avanza', () => {
    const error = DURACION.error as number;
    let cola = encolar([], peticion('No se pudo escribir', 'error'), 0, 1);

    // Diez repasos en pausa: pasan 2,5 segundos de reloj y ninguno cuenta.
    for (let i = 0; i < 10; i += 1) cola = posponer(cola, 250);

    expect(caducar(cola, error)).toHaveLength(1);
    expect(caducar(cola, error + 2500)).toHaveLength(0);
  });

  it('un acierto se va cuando cumple su tiempo', () => {
    const cola = encolar([], peticion('Nota guardada'), 0, 1);
    const duracion = DURACION.exito as number;

    expect(caducar(cola, duracion - 1)).toHaveLength(1);
    expect(caducar(cola, duracion)).toHaveLength(0);
  });

  it('la información dura más que el acierto, porque hay más que leer', () => {
    const informacion = DURACION.informacion as number;
    const exito = DURACION.exito as number;

    expect(informacion).toBeGreaterThan(exito);
  });

  it('cerrar quita solo el que se cierra', () => {
    let cola = encolar([], peticion('Nota guardada'), 0, 1);
    cola = encolar(cola, peticion('Marcador puesto'), 0, 2);

    expect(descartar(cola, 1)).toHaveLength(1);
    expect(descartar(cola, 1)[0]?.mensaje).toBe('Marcador puesto');
  });

  it('cerrar uno que ya no está no rompe la cola', () => {
    const cola = encolar([], peticion('Nota guardada'), 0, 1);

    expect(descartar(cola, 99)).toHaveLength(1);
  });
});
