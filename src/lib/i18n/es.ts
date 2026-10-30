/**
 * Los textos de la interfaz, en español.
 *
 * Ningún texto visible se escribe en el marcado: sale de aquí. La interfaz de la
 * V1 solo existía en español, y la V2 también empieza así, pero con los textos
 * fuera del código otro idioma es un archivo más y no una búsqueda por todo el
 * proyecto (es la regla de NB Books, F1.7.1).
 */
export const es = {
  app: {
    nombre: 'NB Sound'
  },
  nav: {
    principal: 'Navegación principal',
    inicio: 'Inicio',
    biblioteca: 'Biblioteca',
    playlists: 'Playlists',
    dj: 'DJ Privado',
    aCiegas: 'A ciegas',
    tuMusica: 'Tu música',
    ajustes: 'Ajustes',
    porRevisar: 'Por revisar',
    pendientes: (n: number) => (n === 1 ? '1 pendiente' : `${n} pendientes`),
    secciones: {
      explorar: 'Explorar',
      tuMusica: 'Tu música',
      experiencias: 'Experiencias'
    }
  },
  busqueda: {
    etiqueta: 'Buscar en tu música',
    marcador: 'Canciones, álbumes, artistas o letras',
    atajo: 'Ctrl+K',
    titulo: 'Buscar',
    subtitulo: 'Encuentra artistas, álbumes, pistas y letras en toda tu biblioteca.',
    artistas: 'Artistas',
    albumes: 'Álbumes',
    pistas: 'Pistas',
    playlists: 'Playlists',
    sinResultados: (q: string) => `Nada en tu biblioteca coincide con «${q}».`,
    escribe: 'Escribe arriba para buscar.',
    verTodas: (n: number) => `Ver las ${n.toLocaleString('es')} pistas`
  },
  reproductor: {
    region: 'Reproductor',
    nadaSonando: 'Nada sonando',
    eligeAlgo: 'Elige una canción para empezar',
    anterior: 'Anterior',
    siguiente: 'Siguiente',
    reproducir: 'Reproducir',
    pausar: 'Pausar',
    aleatorio: 'Aleatorio',
    repetir: 'Repetir',
    karaoke: 'Modo karaoke',
    karaokeNoListo: 'Esta canción aún no está lista para cantar',
    letras: 'Letras',
    cola: 'Cola',
    colaCon: (n: number) => (n === 1 ? 'Cola, 1 canción' : `Cola, ${n} canciones`),
    volumen: 'Volumen',
    silenciar: 'Silenciar',
    quitarSilencio: 'Quitar silencio',
    expandir: 'Reproducción a pantalla completa',
    progreso: 'Progreso de la canción',
    repeticion: {
      ninguno: 'Repetir',
      todo: 'Repetir la cola',
      uno: 'Repetir esta canción'
    }
  },
  biblioteca: {
    titulo: 'Biblioteca',
    vistas: { albumes: 'Álbumes', artistas: 'Artistas', pistas: 'Pistas' },
    cuentaPistas: (n: number) => (n === 1 ? '1 pista' : `${n.toLocaleString('es')} pistas`),
    cuentaAlbumes: (n: number) => (n === 1 ? '1 álbum' : `${n.toLocaleString('es')} álbumes`),
    cuentaArtistas: (n: number) => (n === 1 ? '1 artista' : `${n.toLocaleString('es')} artistas`),
    buscar: 'Buscar por pista, artista, álbum o letra',
    favoritas: 'Favoritas',
    sinVerificar: 'Sin verificar',
    orden: 'Orden',
    ordenes: {
      tituloAsc: 'Título A-Z',
      tituloDesc: 'Título Z-A',
      artistaAsc: 'Artista A-Z',
      artistaDesc: 'Artista Z-A',
      albumAsc: 'Álbum A-Z',
      albumDesc: 'Álbum Z-A',
      anioDesc: 'Año reciente',
      anioAsc: 'Año antiguo',
      duracionDesc: 'Mayor duración',
      duracionAsc: 'Menor duración',
      recientes: 'Recientes',
      antiguas: 'Antiguas',
      masReproducidas: 'Más reproducidas',
      menosReproducidas: 'Menos reproducidas',
      relevancia: 'Relevancia',
      nombreAsc: 'Nombre A-Z',
      nombreDesc: 'Nombre Z-A',
      masPistas: 'Más pistas'
    },
    reproducir: 'Reproducir',
    anadirACola: 'Añadir a cola',
    abrirAlbum: 'Abrir álbum',
    abrirArtista: 'Abrir artista',
    marcarFavorita: 'Marcar como favorita',
    quitarFavorita: 'Quitar de favoritas',
    masAcciones: 'Más acciones',
    sinVerificarInsignia: 'Sin verificar',
    lista: 'Canciones',
    vacia: 'No hay canciones que coincidan.',
    vaciaBiblioteca: 'Tu biblioteca está vacía.',
    cargando: 'Cargando',
    album: {
      volver: 'Volver a la biblioteca',
      pistas: (n: number, duracion: string) =>
        `${n === 1 ? '1 pista' : `${n} pistas`} · ${duracion}`,
      aleatorio: 'Aleatorio',
      noEncontrado: 'Este álbum ya no está en la biblioteca.'
    },
    artista: {
      albumes: 'Álbumes',
      canciones: 'Canciones',
      resumen: (albumes: number, pistas: number) =>
        `${albumes === 1 ? '1 álbum' : `${albumes} álbumes`} · ${pistas === 1 ? '1 pista' : `${pistas} pistas`}`,
      noEncontrado: 'Este artista ya no está en la biblioteca.'
    }
  },
  playlists: {
    titulo: 'Playlists',
    subtitulo: 'Listas manuales, favoritas y mezclas locales preparadas con tu biblioteca.',
    nueva: 'Nueva playlist',
    buscar: 'Buscar por nombre o tipo',
    cuenta: (n: number) => (n === 1 ? '1 playlist' : `${n} playlists`),
    categorias: {
      todo: 'Todo',
      meGusta: 'Me gusta',
      creada: 'Creadas por mí',
      inteligente: 'Creadas para ti',
      thisIs: 'This is...',
      sistema: 'Sistema'
    },
    ordenes: {
      recientes: 'Recientes',
      antiguas: 'Antiguas',
      nombreAsc: 'A → Z',
      nombreDesc: 'Z → A',
      masCanciones: 'Canciones ↓',
      menosCanciones: 'Canciones ↑'
    },
    resumen: (n: number, duracion: string) =>
      `${n === 1 ? '1 pista' : `${n} pistas`} · ${duracion}`,
    abrir: 'Abrir',
    anclar: 'Anclar',
    desanclar: 'Desanclar',
    reproducir: 'Reproducir',
    renombrar: 'Renombrar',
    borrar: 'Borrar',
    confirmarBorrar: (nombre: string) =>
      `¿Borrar «${nombre}»? Las canciones siguen en tu biblioteca.`,
    quitar: 'Quitar de la playlist',
    subir: 'Subir',
    bajar: 'Bajar',
    vacia: 'Esta playlist todavía no tiene canciones.',
    noEncontrada: 'Esta playlist ya no existe.',
    volver: 'Volver a Playlists',
    nombre: 'Nombre',
    descripcion: 'Descripción (opcional)',
    crear: 'Crear',
    guardar: 'Guardar',
    cancelar: 'Cancelar',
    anadirA: 'Añadir a playlist',
    anadida: (nombre: string) => `Añadida a «${nombre}»`,
    yaEstaba: (nombre: string) => `Ya estaba en «${nombre}»`,
    errores: {
      INVALID_INPUT: 'El nombre no puede estar vacío ni pasar de 120 caracteres.',
      NAME_TAKEN: 'Ya tienes una playlist con ese nombre.'
    } as Record<string, string>
  },
  ajustes: {
    acercaDe: 'Acerca de',
    version: (v: string) => `NB Sound ${v}`
  },
  vistas: {
    proximamente: 'Esta sección llega en una fase próxima del plan.'
  }
} as const;

export type Textos = typeof es;
