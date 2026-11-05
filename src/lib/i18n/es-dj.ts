/**
 * Textos del DJ Privado (F6.1.6). Van aparte del arranque, como `es-aparte.ts`:
 * solo los importa la vista del DJ, que se carga a demanda.
 */
import type { Tecnica } from '#lib/bindings/index.ts';

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
    // Cada ficha es una palabra que el motor entiende: lo comprueba
    // `dj::ontologia::pruebas::las_fichas_de_la_vista_las_entiende_el_motor`.
    categoriasSugeridas: [
      {
        nombre: 'Voces',
        chips: ['Voces femeninas', 'Voces masculinas', 'Instrumental', 'Acústico']
      },
      {
        nombre: 'Géneros',
        chips: [
          'Reguetón',
          'Trap',
          'Pop',
          'Salsa',
          'Bachata',
          'Cumbia',
          'Rock',
          'Electrónica',
          'Hip hop',
          'R&B',
          'Indie',
          'Jazz',
          'Clásica'
        ]
      },
      {
        nombre: 'Ánimos',
        chips: [
          'Alegre',
          'Romántico',
          'Melancólico',
          'Nostálgico',
          'Nocturno',
          'Cinematográfico',
          'Tranquilo'
        ]
      },
      {
        nombre: 'Energía',
        chips: ['Energético', 'Que pegue', 'Suave', 'Relajante', 'Subida progresiva']
      },
      {
        nombre: 'Momentos',
        chips: ['Fiesta', 'Para entrenar', 'Para concentrarme', 'Para cocinar', 'Noche de lluvia']
      }
    ],
    sugerencias: [
      'Subida progresiva para entrenar',
      'Algo cinematográfico con voces femeninas',
      'Tranquilo para concentrarme',
      'Fiesta electrónica con mucha energía',
      'Melancólico para una noche de lluvia'
    ]
  },
  sesion: {
    entendi: 'Entendí',
    evitare: 'Sin',
    // Los conceptos de la ontología (`dj/ontologia_datos.rs`) por su nombre, para
    // decir cómo se entendió el pedido. Lo comprueba
    // `dj::intencion::tests::cada_concepto_tiene_su_nombre_en_la_vista`.
    conceptos: {
      pop: 'pop',
      rock: 'rock',
      indie: 'indie',
      electronica: 'electrónica',
      edm_agresivo: 'EDM agresivo',
      house: 'house',
      techno: 'techno',
      hip_hop: 'hip hop',
      reggaeton: 'reguetón',
      reggae: 'reggae',
      salsa: 'salsa',
      bachata: 'bachata',
      merengue: 'merengue',
      cumbia: 'cumbia',
      trap: 'trap',
      rnb: 'R&B',
      jazz: 'jazz',
      clasica: 'clásica',
      ambient: 'ambient',
      folk: 'folk',
      metal: 'metal',
      blues: 'blues',
      funk: 'funk',
      cinematografico: 'cinematográfica',
      orquestal: 'orquestal',
      narrativo: 'que cuente una historia',
      sonador: 'soñadora',
      nocturno: 'nocturna',
      elegante: 'elegante',
      minimalista: 'minimalista',
      triste: 'triste',
      feliz: 'alegre',
      esperanzador: 'esperanzadora',
      tranquilo: 'tranquila',
      agresivo: 'agresiva',
      energetico: 'con energía',
      etereo_calido: 'cálida',
      voces_femeninas: 'voces femeninas',
      voces_masculinas: 'voces masculinas',
      instrumental: 'instrumental',
      que_resalten_voces: 'voces al frente',
      bajos_fuertes: 'bajos fuertes',
      acustico: 'acústica',
      electronico_modifier: 'electrónica',
      oscuro: 'oscura',
      brillante: 'brillante',
      transiciones_suaves: 'transiciones suaves',
      transiciones_agresivas: 'transiciones bruscas',
      transicion_progresiva: 'transición progresiva',
      entrenar: 'para entrenar',
      concentrarse: 'para concentrarse',
      club_party: 'fiesta',
      cocinar: 'para cocinar',
      lluvioso: 'de lluvia',
      lo_fi: 'lo-fi',
      romantico: 'romántica',
      sin_edm_agresivo: 'sin EDM agresivo',
      emocionante: 'emocionante',
      sentimental: 'sentimental',
      melancolico_profundo: 'melancólica',
      nostalgico: 'nostálgica',
      dramatico: 'dramática',
      epico: 'épica',
      que_pegue: 'que pegue',
      suave: 'suave',
      relajante: 'relajante',
      atmosferico: 'atmosférica',
      etereo: 'etérea',
      espacial: 'espacial',
      futurista: 'futurista',
      synthwave: 'synthwave',
      underground: 'underground',
      pesado: 'pesada',
      minimal_textural: 'minimal',
      bajos_profundos: 'bajos profundos',
      percusion_fuerte: 'percusión fuerte',
      vocal_dominante: 'la voz como protagonista',
      voz_femenina_suave: 'voz femenina suave',
      voz_masculina_grave: 'voz masculina grave'
    } as Record<string, string>,
    curvas: {
      progressive: 'subida progresiva',
      wave: 'energía en olas',
      descending: 'energía que baja',
      peak: 'pico de energía'
    } as Record<string, string>,
    general: 'No reconocí nada concreto: es una selección general de tu música.',
    sonando: 'Sonando',
    enPausa: 'En pausa',
    construyendo: 'Preparando más canciones mientras suena…',
    resumen: (pistas: number, duracion: string, artistas: number) =>
      `${pistas === 1 ? '1 canción' : `${pistas} canciones`} · ${duracion} · ${artistas === 1 ? '1 artista' : `${artistas} artistas`}`,
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
    pocas: 'Tus sesiones se quedan aquí.',
    adornoTexto:
      'Vuelve a cualquiera para escucharla otra vez, ver sus canciones o guardarla como playlist.',
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
