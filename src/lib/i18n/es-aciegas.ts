/**
 * Textos de A ciegas (F6.2.2). Van aparte del arranque: solo los importa la vista
 * del juego, que se carga a demanda.
 */
import type { Indicio, Modo } from '$lib/bindings';

export const esACiegas = {
  titulo: 'A ciegas',
  subtitulo:
    'Redescubre tu música: adivina canciones por su portada o por unos segundos de sonido.',
  modos: {
    portada: {
      nombre: 'Por la portada',
      detalle: 'Ves la portada y adivinas la canción.'
    },
    audio: {
      nombre: 'Por el sonido',
      detalle: 'Escuchas unos segundos sin saber qué suena.'
    },
    redescubrimiento: {
      nombre: 'Redescubrir',
      detalle: 'Canciones que te gustaron y hace tiempo que no suenan.'
    },
    nunca_eliges: {
      nombre: 'La que nunca eliges',
      detalle: 'Canciones de tu biblioteca que casi nunca pones.'
    }
  } satisfies Record<Modo, { nombre: string; detalle: string }>,
  canciones: (n: number) => (n === 1 ? '1 canción' : `${n.toLocaleString('es')} canciones`),
  retos: 'Retos por ronda',
  empezar: 'Empezar',
  sinCanciones: 'Aún no hay canciones para este modo.',
  reto: (n: number, total: number) => `Reto ${n} de ${total}`,
  marcador: (acertados: number) => `${acertados} acertadas`,
  oculto: '???',
  campos: { titulo: 'Título', artista: 'Artista', album: 'Álbum' },
  escuchar: 'Escuchar el fragmento',
  segundos: (s: number) => `${s} s`,
  duracionFragmento: 'Duración del fragmento',
  escribir: '¿Cómo se llama?',
  comprobar: 'Comprobar',
  laSe: '¡La sé!',
  noSeEscribe: 'Este título no se escribe con letras latinas: si la reconoces, dilo.',
  acierto: '¡Correcto!',
  cerca: 'Casi…',
  fallo: 'No es esa.',
  fallos: (n: number) => (n === 1 ? '1 intento fallido' : `${n} intentos fallidos`),
  verArtista: 'Ver el artista',
  verAlbum: 'Ver el álbum',
  rendirse: 'Rendirme',
  siguiente: 'Siguiente',
  anterior: 'Anterior',
  terminar: 'Ver el resumen',
  indicios: 'Indicios',
  nombresIndicio: {
    alfabeto: 'Alfabeto',
    empiezaCon: 'Empieza por',
    terminaCon: 'Termina en',
    cantidadPalabras: 'Palabras',
    cantidadLetras: 'Letras'
  } satisfies Record<Indicio, string>,
  alfabetos: {
    latino: 'latino',
    griego: 'griego',
    cirilico: 'cirílico',
    hebreo: 'hebreo',
    arabe: 'árabe',
    devanagari: 'devanagari',
    japones: 'japonés',
    chino: 'chino',
    coreano: 'coreano',
    otro: 'otro'
  } as Record<string, string>,
  escucharEntera: 'Escuchar entera',
  aLaCola: 'Añadir a la cola',
  enCola: 'En la cola.',
  resumen: {
    titulo: 'Fin de la ronda',
    cifras: (acertados: number, revelados: number, pasados: number) =>
      `${acertados} acertadas · ${revelados} reveladas · ${pasados} pasadas`,
    otra: 'Otra ronda',
    cambiar: 'Cambiar de modo'
  }
} as const;

export type TextosACiegas = typeof esACiegas;
