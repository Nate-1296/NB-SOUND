/**
 * Textos del DJ Privado (F6.1.6). Van aparte del arranque, como `es-aparte.ts`:
 * solo los importa la vista del DJ, que se carga a demanda.
 */
import type { Tecnica } from '$lib/bindings';

export const esDj = {
  titulo: 'DJ Privado',
  subtitulo: 'Dile qué te apetece y arma con tu música una sesión mezclada como la haría un DJ.',
  pedir: {
    etiqueta: '¿Qué quieres escuchar?',
    ejemplo: 'Por ejemplo: algo tranquilo para trabajar de noche, sin reguetón',
    duracion: 'Duración',
    minutos: (n: number) => `${n} min`,
    crear: 'Crear sesión',
    creando: 'Preparando la sesión…',
    error: 'No se pudo generar la sesión. Inténtalo de nuevo.',
    vacia: 'Escribe lo que quieres escuchar.',
    sinCandidatas:
      'Ninguna canción de tu biblioteca encaja con eso. Prueba con otras palabras o con menos exclusiones.',
    ideas: 'Ideas',
    sugerencias: [
      'Subida progresiva para entrenar',
      'Algo cinematográfico con voces femeninas',
      'Tranquilo para concentrarme',
      'Fiesta electrónica con mucha energía',
      'Melancólico para una noche de lluvia'
    ]
  },
  sesion: {
    sonando: 'Sonando',
    enPausa: 'En pausa',
    construyendo: 'Preparando más canciones mientras suena…',
    resumen: (pistas: number, duracion: string, artistas: number) =>
      `${pistas} canciones · ${duracion} · ${artistas} artistas`,
    transiciones: (buenas: number, total: number) =>
      `${buenas} de ${total} transiciones muy limpias`,
    sinAnalisis:
      'Sin el análisis musical, el DJ elige con los rasgos básicos de cada canción. Con el agregado de análisis, en Ajustes, afina más.',
    escuchar: 'Escuchar',
    regenerar: 'Otra parecida',
    guardar: 'Guardar como playlist',
    guardada: 'Guardada en Playlists.',
    descartar: 'Descartar',
    meGusta: 'Me gusta',
    noMeGusta: 'No me gusta',
    valorada: 'Lo tendré en cuenta.',
    pistas: 'Canciones de la sesión',
    tocarDesde: (titulo: string) => `Escuchar desde ${titulo}`,
    entrada: (tiempo: string) => `Entrada ${tiempo}`,
    salida: (tiempo: string) => `Salida ${tiempo}`,
    mezclando: (tecnica: string, progreso: number) =>
      `${tecnica} · ${Math.round(progreso * 100)} %`,
    tecnicas: {
      hard_cut: 'Corte en el beat',
      energy_blend: 'Fundido largo',
      eq_kill_bass: 'Mezclando con ecualización',
      filter_sweep: 'Barrido de filtros',
      harmonic_mix: 'Fundiendo capas'
    } satisfies Record<Tecnica, string>,
    transicion: {
      limpia: 'Transición limpia',
      aceptable: 'Transición aceptable',
      forzada: 'Transición forzada'
    }
  },
  historial: {
    titulo: 'Historial',
    buscar: 'Buscar en el historial',
    vacio: 'Aún no has pedido ninguna sesión.',
    nada: 'Ninguna sesión coincide.',
    estados: {
      construyendo: 'Preparándose',
      lista: 'Lista',
      finalizada: 'Escuchada',
      descartada: 'Descartada',
      error: 'Sin canciones'
    } as Record<string, string>,
    resumen: (pistas: number, duracion: string) => `${pistas} canciones · ${duracion}`,
    ver: 'Ver',
    eliminar: 'Eliminar',
    eliminarSesion: (peticion: string) => `Eliminar la sesión «${peticion}»`
  }
} as const;

export type TextosDj = typeof esDj;
