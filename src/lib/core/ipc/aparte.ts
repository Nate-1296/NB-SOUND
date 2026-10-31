/**
 * La parte del puente que solo usan pantallas que se cargan aparte del arranque:
 * agregados, copia de seguridad, edición, privacidad e IA. Vive aquí, y no en
 * `index.ts`, porque `index.ts` entra entero en el arranque (`check-paquete`); este
 * módulo solo lo importan módulos diferidos y se carga con ellos.
 */

import type { UnlistenFn } from '@tauri-apps/api/event';
import type {
  Actualizacion,
  AjustesIa,
  DatosAlbum,
  DatosPista,
  Descubrimiento,
  EstadoAgregado,
  EstadoCopia,
  Gpu,
  IdAgregado,
  PoliticaDeRed,
  ProveedorIa,
  ResumenCopia
} from '$lib/bindings';

import { call, escuchar } from './index';

// --- Descubrir --------------------------------------------------------------------

/** Lo que se pide en palabras: secciones de pistas, o `entendida: false`. */
export function descubrir(consulta: string, limite: number): Promise<Descubrimiento> {
  return call<Descubrimiento>('descubrir', { consulta, limite });
}

// --- Agregados -------------------------------------------------------------------

/** La GPU que aprovecharía el agregado de aceleración, o `null`. */
export function gpuDetectada(): Promise<Gpu | null> {
  return call<Gpu | null>('gpu_detectada');
}

export function agregadosEstado(): Promise<EstadoAgregado[]> {
  return call<EstadoAgregado[]>('agregados_estado');
}

// --- Actualizaciones de la aplicación ------------------------------------------------

/** La versión publicada más nueva que la instalada; buscarla es consentir el servicio. */
export function actualizacionBuscar(): Promise<Actualizacion | null> {
  return call<Actualizacion | null>('actualizacion_buscar');
}

/** Instala la versión más nueva; la aplicación se reinicia con ella. */
export function actualizacionInstalar(): Promise<void> {
  return call<void>('actualizacion_instalar');
}

/** Empieza a instalarlo en segundo plano; el progreso llega con `alCambiarLosAgregados`. */
export function agregadoInstalar(id: IdAgregado): Promise<void> {
  return call<void>('agregado_instalar', { id });
}

export function agregadoQuitar(id: IdAgregado): Promise<EstadoAgregado[]> {
  return call<EstadoAgregado[]>('agregado_quitar', { id });
}

/** Cada avance de una instalación, su fin o su fallo: se vuelve a pedir el estado. */
export function alCambiarLosAgregados(cada: () => void): Promise<UnlistenFn> {
  return escuchar<null>('agregados:cambio', () => cada());
}

// --- Copia de seguridad ----------------------------------------------------------

export function copiaEstado(): Promise<EstadoCopia> {
  return call<EstadoCopia>('copia_estado');
}

/** Abre el selector nativo para guardar; `null` si se canceló. */
export function copiaCrear(): Promise<ResumenCopia | null> {
  return call<ResumenCopia | null>('copia_crear');
}

/** Abre el selector nativo, valida la copia y la deja lista para el próximo arranque. */
export function copiaRestaurar(): Promise<boolean> {
  return call<boolean>('copia_restaurar');
}

/** 0, 1, 7 o 30 días. */
export function copiaFrecuencia(dias: number): Promise<EstadoCopia> {
  return call<EstadoCopia>('copia_frecuencia', { dias });
}

export function copiaElegirCarpeta(): Promise<EstadoCopia> {
  return call<EstadoCopia>('copia_elegir_carpeta');
}

/** Reinicia la aplicación, con el mismo cierre ordenado que al salir. */
export function reiniciar(): Promise<void> {
  return call<void>('reiniciar');
}

// --- Editar metadatos --------------------------------------------------------------

export function datosPista(pista: number): Promise<DatosPista> {
  return call<DatosPista>('datos_pista', { pista });
}

/** Guarda en la base y, si se puede, en el archivo. La pista conserva su id. */
export function editarPista(pista: number, datos: DatosPista): Promise<void> {
  return call<void>('editar_pista', { pista, datos });
}

export function datosAlbum(album: number): Promise<DatosAlbum> {
  return call<DatosAlbum>('datos_album', { album });
}

/** Devuelve el id del álbum resultante: otro solo si se juntó con uno que ya existía. */
export function editarAlbum(album: number, datos: DatosAlbum): Promise<number> {
  return call<number>('editar_album', { album, datos });
}

// --- Privacidad e inteligencia artificial ---------------------------------------

/** Lo que la puerta de red deja salir ahora mismo. */
export function politicaRed(): Promise<PoliticaDeRed> {
  return call<PoliticaDeRed>('politica_red');
}

export function cambiarPoliticaRed(politica: PoliticaDeRed): Promise<void> {
  return call<void>('cambiar_politica_red', { politica });
}

export function ajustesIa(): Promise<AjustesIa> {
  return call<AjustesIa>('ajustes_ia');
}

/** Un modelo vacío vuelve al de fábrica del proveedor. */
export function guardarAjustesIa(proveedor: ProveedorIa, modelo: string): Promise<AjustesIa> {
  return call<AjustesIa>('guardar_ajustes_ia', { proveedor, modelo });
}

/** La clave va al llavero del sistema y no vuelve: la respuesta solo dice si hay una. */
export function guardarClaveIa(clave: string): Promise<AjustesIa> {
  return call<AjustesIa>('guardar_clave_ia', { clave });
}

export function borrarClaveIa(): Promise<AjustesIa> {
  return call<AjustesIa>('borrar_clave_ia');
}
