/**
 * El estado del reproductor en la interfaz.
 *
 * El reproductor vive en Rust (ADR-003): aquí solo hay su última instantánea, que
 * llega por evento cada vez que cambia algo, y los datos de las pistas que se
 * pintan. La posición avanza entre instantáneas con el reloj del navegador, para
 * que la barra no salte a saltos de un cuarto de segundo.
 */

import {
  type AvisoReproductor,
  alAvisarElReproductor,
  alCambiarElReproductor,
  formaDeOnda,
  type Instantanea,
  type OrdenReproductor,
  type PistaResumen,
  pistasResumen,
  reproductorEstado,
  reproductorOrden
} from '$core/ipc';

const VACIA: Instantanea = {
  estado: 'detenido',
  pistaId: null,
  posicionSeg: 0,
  duracionSeg: 0,
  indiceCola: null,
  cola: [],
  aleatorio: false,
  repeticion: 'ninguno',
  volumen: 1,
  normalizar: true,
  karaokeDisponible: false,
  karaokeActivo: false,
  dj: null,
  ciego: false
};

class EstadoDelReproductor {
  instantanea = $state<Instantanea>(VACIA);
  /** Los datos de la pista que suena. */
  pista = $state<PistaResumen | null>(null);
  /** Los picos de la forma de onda de la pista que suena (F8.1). */
  picos = $state<number[]>([]);
  /** El último aviso, para mostrarlo y descartarlo. */
  aviso = $state<AvisoReproductor | null>(null);
  /** Segundos desde que llegó la instantánea, mientras suena. */
  #desde = $state(0);
  #recibida = 0;
  #reloj: ReturnType<typeof setInterval> | null = null;
  #arrancado = false;

  readonly sonando = $derived(this.instantanea.estado === 'reproduciendo');

  /** La posición interpolada, acotada a la duración. */
  readonly posicion = $derived(
    Math.min(
      this.instantanea.posicionSeg + (this.sonando ? this.#desde : 0),
      this.instantanea.duracionSeg || Number.POSITIVE_INFINITY
    )
  );

  /** Se llama una vez, desde la carcasa. */
  async arrancar(): Promise<void> {
    if (this.#arrancado) return;
    this.#arrancado = true;
    await alCambiarElReproductor((i) => this.#recibir(i));
    await alAvisarElReproductor((a) => {
      this.aviso = a;
    });
    const inicial = await reproductorEstado().catch(() => null);
    if (inicial) this.#recibir(inicial);
  }

  #recibir(i: Instantanea): void {
    const cambioDePista = i.pistaId !== this.instantanea.pistaId;
    this.instantanea = i;
    this.#recibida = performance.now();
    this.#desde = 0;
    if (cambioDePista) void this.#cargarPista(i.pistaId);
    this.#ajustarReloj();
  }

  async #cargarPista(id: number | null): Promise<void> {
    this.picos = [];
    if (id === null) {
      this.pista = null;
      return;
    }
    const [[p], picos] = await Promise.all([
      pistasResumen([id]).catch(() => []),
      formaDeOnda(id).catch(() => [])
    ]);
    // Si mientras tanto cambió de pista, esta respuesta ya no vale.
    if (this.instantanea.pistaId === id) {
      this.pista = p ?? null;
      this.picos = picos;
    }
  }

  /** El reloj solo corre mientras suena: en reposo no se anima nada (ADR-008). */
  #ajustarReloj(): void {
    if (this.sonando && this.#reloj === null) {
      this.#reloj = setInterval(() => {
        this.#desde = (performance.now() - this.#recibida) / 1000;
      }, 250);
    } else if (!this.sonando && this.#reloj !== null) {
      clearInterval(this.#reloj);
      this.#reloj = null;
    }
  }

  orden(orden: OrdenReproductor): Promise<void> {
    return reproductorOrden(orden).catch((e: unknown) => {
      this.aviso = {
        codigo: e instanceof Error ? e.message : 'INTERNAL',
        pistaId: null
      };
    });
  }

  pausarReanudar = () => this.orden({ tipo: 'pausarReanudar' });
  siguiente = () => this.orden({ tipo: 'siguiente' });
  anterior = () => this.orden({ tipo: 'anterior' });
  buscar = (segundos: number) => this.orden({ tipo: 'buscar', segundos });
  volumen = (valor: number) => this.orden({ tipo: 'volumen', valor });
  alternarAleatorio = () => this.orden({ tipo: 'aleatorio', activo: !this.instantanea.aleatorio });

  /** Ninguno, todo y una, en ese orden, como en la V1. */
  rotarRepeticion = () => {
    const siguiente: Record<string, string> = { ninguno: 'todo', todo: 'uno', uno: 'ninguno' };
    return this.orden({
      tipo: 'repeticion',
      modo: siguiente[this.instantanea.repeticion] ?? 'ninguno'
    });
  };

  alternarKaraoke = () => this.orden({ tipo: 'karaoke', activo: !this.instantanea.karaokeActivo });

  reproducirPistas = (ids: number[], desde = 0) =>
    this.orden({ tipo: 'reproducirPistas', ids, desde });
}

export const reproductor = new EstadoDelReproductor();

/** `m:ss`, o `h:mm:ss` a partir de una hora, como la V1. */
export function formatoTiempo(segundos: number): string {
  if (!Number.isFinite(segundos) || segundos < 0) return '0:00';
  const total = Math.floor(segundos);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const ss = String(s).padStart(2, '0');
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}
