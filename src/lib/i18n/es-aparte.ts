/**
 * Textos de las pantallas que se cargan aparte del arranque (`check-paquete`).
 *
 * `es.ts` entra entero en el arranque, así que un texto que solo usa un diálogo o
 * una sección diferida lo pagaría cada apertura de la aplicación. Aquí van esos:
 * solo los importan módulos que ya se cargan a demanda, y con ellos se cargan.
 */
export const esAparte = {
  edicion: {
    tituloPista: 'Editar datos de la canción',
    tituloAlbum: 'Editar datos del álbum',
    ayuda:
      'Se guardan en tu biblioteca y, si se puede, en el archivo. Las playlists y el teléfono la siguen reconociendo.',
    titulo: 'Título',
    artista: 'Artista',
    album: 'Álbum',
    albumAyuda: 'Vacío si no es de ningún álbum.',
    numero: 'Número de pista',
    anio: 'Año',
    genero: 'Género',
    guardar: 'Guardar',
    cancelar: 'Cancelar',
    invalido:
      'Revisa los datos: el título y el artista no pueden quedar vacíos y el año va de 1000 a 9999.',
    sinArchivo: 'No se encuentra el archivo de esta canción.',
    fallo: 'No se pudo guardar. Vuelve a intentarlo.'
  },
  privacidad: {
    privacidadAyuda:
      'NB Sound funciona sin conexión. Cada servicio solo se usa si lo activas, y solo recibe lo que se indica.',
    conexion: 'Usar servicios en línea',
    conexionAyuda: 'Apagado, nada sale de este equipo, sea cual sea el ajuste de cada servicio.',
    servicios: {
      acoustId: {
        nombre: 'AcoustID',
        envia: 'La huella acústica de cada canción y su duración, para reconocerla. Nunca el audio.'
      },
      musicBrainz: {
        nombre: 'MusicBrainz',
        envia:
          'Título, artista y álbum, o el identificador que dio AcoustID, para completar los datos.'
      },
      coverArtArchive: {
        nombre: 'Cover Art Archive',
        envia: 'El identificador del álbum en MusicBrainz, para descargar su portada.'
      },
      shazam: {
        nombre: 'Shazam',
        envia:
          'Una firma de unos segundos de la canción, no el audio. Es un servicio no oficial y puede dejar de funcionar; sin él se reconoce con AcoustID.'
      },
      itunes: {
        nombre: 'iTunes',
        envia: 'Título y artista, para confirmar la canción y buscar portadas.'
      },
      lrclib: {
        nombre: 'LRCLIB',
        envia: 'Título, artista, álbum y duración, para buscar la letra sincronizada.'
      },
      lyricsOvh: {
        nombre: 'lyrics.ovh',
        envia: 'Título y artista, para buscar la letra si LRCLIB no la tiene.'
      },
      deezer: {
        nombre: 'Deezer',
        envia: 'El nombre del artista o del álbum, para buscar imágenes.'
      },
      wikipedia: {
        nombre: 'Wikipedia',
        envia: 'El nombre del artista, para buscar su foto.'
      },
      theAudioDb: {
        nombre: 'TheAudioDB',
        envia: 'El nombre del artista y del álbum, para buscar portadas e imágenes de artista.'
      }
    },
    iaAyuda:
      'Opcional. Cuando dos versiones de una canción empatan, un modelo de lenguaje elige entre ellas con tu propia cuenta. Solo recibe los datos de la canción y de los candidatos, nunca el audio.',
    iaActiva: 'Desempatar con IA',
    iaSinConexion: 'Activa antes los servicios en línea.',
    proveedor: 'Proveedor',
    proveedores: { anthropic: 'Anthropic (Claude)', openai: 'OpenAI' },
    modelo: 'Modelo',
    modeloAyuda: 'Déjalo vacío para usar el de fábrica.',
    clave: 'Clave de API',
    claveGuardada: 'Guardada en el llavero del sistema.',
    claveNueva: 'Pega aquí tu clave',
    guardarClave: 'Guardar clave',
    olvidarClave: 'Olvidar clave',
    sinLlavero:
      'Este sistema no tiene llavero de contraseñas, así que no se puede guardar ninguna clave. NB Sound nunca la guarda en un archivo.',
    noGuardado: 'No se pudo guardar. Vuelve a intentarlo.'
  }
};

export type TextosAparte = typeof esAparte;
