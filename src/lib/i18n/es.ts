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
    atajo: 'Ctrl+K'
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
  ajustes: {
    acercaDe: 'Acerca de',
    version: (v: string) => `NB Sound ${v}`
  },
  vistas: {
    proximamente: 'Esta sección llega en una fase próxima del plan.'
  }
} as const;

export type Textos = typeof es;
