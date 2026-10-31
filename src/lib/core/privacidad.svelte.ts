/**
 * La política de red y los ajustes de IA, compartidos por las secciones
 * Privacidad e Inteligencia artificial de Ajustes: el interruptor de la IA es un
 * servicio más de la política, así que las dos leen y escriben el mismo estado.
 *
 * Cada cambio se manda al momento y lo que se pinta es lo que confirma Rust: si
 * no se puede guardar, el interruptor vuelve a como estaba.
 */

import type { AjustesIa, PoliticaDeRed, ProveedorIa, Servicio } from '$core/ipc';
import {
  ajustesIa,
  borrarClaveIa,
  cambiarPoliticaRed,
  guardarAjustesIa,
  guardarClaveIa,
  politicaRed
} from '$core/ipc/aparte';

/** Los servicios de la sección Privacidad, en el orden de `net.rs`. La IA tiene su
 * sección y los agregados la suya (Fase 5). */
export const SERVICIOS_EN_LINEA = [
  'acoustId',
  'musicBrainz',
  'coverArtArchive',
  'shazam',
  'itunes',
  'lrclib',
  'lyricsOvh',
  'deezer',
  'wikipedia',
  'theAudioDb',
  'actualizaciones'
] as const satisfies readonly Servicio[];

class Privacidad {
  politica = $state<PoliticaDeRed>({ general: false, servicios: [] });
  ia = $state<AjustesIa | null>(null);
  /** El último cambio no se pudo guardar. */
  fallo = $state(false);

  async refrescar(): Promise<void> {
    const [politica, ia] = await Promise.all([politicaRed(), ajustesIa()]);
    this.politica = politica;
    this.ia = ia;
  }

  activo(servicio: Servicio): boolean {
    return this.politica.servicios.includes(servicio);
  }

  async #aplicar(nueva: PoliticaDeRed): Promise<void> {
    const anterior = this.politica;
    this.politica = nueva;
    try {
      await cambiarPoliticaRed(nueva);
      this.fallo = false;
    } catch {
      this.politica = anterior;
      this.fallo = true;
    }
  }

  general(activo: boolean): Promise<void> {
    return this.#aplicar({ ...this.politica, general: activo });
  }

  servicio(servicio: Servicio, activo: boolean): Promise<void> {
    const resto = this.politica.servicios.filter((s) => s !== servicio);
    return this.#aplicar({
      ...this.politica,
      servicios: activo ? [...resto, servicio] : resto
    });
  }

  async #ia(cambio: () => Promise<AjustesIa>): Promise<boolean> {
    try {
      this.ia = await cambio();
      this.fallo = false;
      return true;
    } catch {
      this.fallo = true;
      return false;
    }
  }

  proveedorYModelo(proveedor: ProveedorIa, modelo: string): Promise<boolean> {
    return this.#ia(() => guardarAjustesIa(proveedor, modelo));
  }

  guardarClave(clave: string): Promise<boolean> {
    return this.#ia(() => guardarClaveIa(clave));
  }

  olvidarClave(): Promise<boolean> {
    return this.#ia(borrarClaveIa);
  }
}

export const privacidad = new Privacidad();
