/**
 * La apariencia que eligió el usuario: tema de la V1, tipografía y escala.
 *
 * Las preferencias viven en la base, que solo se lee de forma asíncrona. Para que
 * el primer fotograma ya tenga el tema y no parpadee con el de fábrica, las
 * variables del último tema aplicado se guardan en `localStorage` y se aplican al
 * arrancar, antes de preguntar al runtime; si la respuesta trae otro tema, se
 * corrige.
 */

import { type Apariencia, apariencia, guardarPreferencia } from '#lib/core/ipc/index.ts';
import { aplicarTemaV1, aplicarVariables, TEMA_V1_DE_FABRICA } from '#lib/ui/tema.ts';

const CACHE = 'ns-apariencia';
const BARRA_COMPACTA = 'ns-barra-lateral-compacta';

interface EnCache {
  tema: string;
  variables: Record<string, string>;
  oscuro: boolean;
  tipografia: string;
  escala: number;
}

const DE_FABRICA: Apariencia = {
  tema: TEMA_V1_DE_FABRICA,
  tipografia: 'Inter',
  escala: 100,
  colorPorPortada: true,
  nombreUsuario: null
};

function aplicarTipografia(raiz: HTMLElement, familia: string, escala: number): void {
  raiz.style.setProperty(
    '--ns-font-ui',
    `'${familia}', system-ui, -apple-system, 'Segoe UI', sans-serif`
  );
  // La escala de la V1 (`ui_scale`) mueve el tamaño base: todo está en rem.
  raiz.style.fontSize = `${escala}%`;
}

class EstadoDeApariencia {
  actual = $state<Apariencia>(DE_FABRICA);
  /**
   * La barra lateral en riel por decisión del usuario (EXP-06). Es de este equipo
   * y no de la biblioteca: en otra pantalla puede caber entera, así que vive en
   * `localStorage` como la caché del tema y no en las preferencias.
   */
  barraLateralCompacta = $state(false);

  alternarBarraLateral(): void {
    this.barraLateralCompacta = !this.barraLateralCompacta;
    try {
      localStorage.setItem(BARRA_COMPACTA, String(this.barraLateralCompacta));
    } catch {
      // Sin almacenamiento, vale para esta sesión.
    }
  }

  /** Lo que haya en caché, sin esperar a nada. Se llama antes del primer pintado. */
  aplicarCache(raiz: HTMLElement): void {
    try {
      this.barraLateralCompacta = localStorage.getItem(BARRA_COMPACTA) === 'true';
      const guardado = localStorage.getItem(CACHE);
      if (!guardado) return;
      const c = JSON.parse(guardado) as EnCache;
      aplicarVariables(raiz, c.variables, c.oscuro);
      aplicarTipografia(raiz, c.tipografia, c.escala);
    } catch {
      // Una caché rota no impide arrancar: llega la de verdad enseguida.
    }
  }

  /** Lee las preferencias y las aplica. */
  async cargar(raiz: HTMLElement): Promise<void> {
    const a = await apariencia().catch(() => DE_FABRICA);
    await this.#aplicar(raiz, a);
  }

  async #aplicar(raiz: HTMLElement, a: Apariencia): Promise<void> {
    this.actual = a;
    const variables =
      (await aplicarTemaV1(raiz, a.tema)) ?? (await aplicarTemaV1(raiz, DE_FABRICA.tema));
    aplicarTipografia(raiz, a.tipografia, a.escala);
    if (!variables) return;
    try {
      const c: EnCache = {
        tema: a.tema,
        variables,
        oscuro: raiz.dataset.esquema === 'oscuro',
        tipografia: a.tipografia,
        escala: a.escala
      };
      localStorage.setItem(CACHE, JSON.stringify(c));
    } catch {
      // Sin almacenamiento, el próximo arranque parpadea un instante; nada más.
    }
  }

  /** Cambia una preferencia, la guarda y la aplica al momento. */
  async cambiar<K extends 'tema' | 'tipografia' | 'escala' | 'colorPorPortada' | 'nombreUsuario'>(
    clave: K,
    valor: Apariencia[K]
  ): Promise<void> {
    const claves: Record<K, string> = {
      tema: 'tema',
      tipografia: 'tipografia',
      escala: 'escala',
      colorPorPortada: 'color_por_portada',
      nombreUsuario: 'nombre_usuario'
    } as Record<K, string>;
    await guardarPreferencia(claves[clave], valor);
    await this.#aplicar(document.documentElement, { ...this.actual, [clave]: valor });
  }
}

export const aparienciaActual = new EstadoDeApariencia();
