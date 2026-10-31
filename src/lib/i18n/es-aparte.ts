/**
 * Textos de las pantallas que se cargan aparte del arranque (`check-paquete`).
 *
 * `es.ts` entra entero en el arranque, así que un texto que solo usa un diálogo o
 * una sección diferida lo pagaría cada apertura de la aplicación. Aquí van esos:
 * solo los importan módulos que ya se cargan a demanda, y con ellos se cargan.
 */
export const esAparte = {
  descubrir: {
    titulo: (que: string) => `Para lo que pides: ${que}`,
    sinAnalisis:
      'Todavía no hay canciones analizadas. Se analizan solas en segundo plano después de importarlas.',
    nada: 'Ninguna canción encaja lo bastante con lo que pides.',
    intenciones: {
      triste: 'triste',
      alegre: 'alegre',
      fiesta: 'para fiesta',
      entrenar: 'para entrenar',
      concentrarse: 'para concentrarte',
      tranquila: 'tranquila',
      nocturna: 'nocturna',
      intensa: 'intensa',
      suave: 'suave',
      rapida: 'rápida',
      lenta: 'lenta'
    },
    secciones: {
      masFiesteras: 'Más fiesteras',
      masBailables: 'Más bailables',
      masRapidas: 'Más rápidas',
      energiaAlta: 'Energía alta',
      masMelancolicas: 'Más melancólicas',
      tristesSuaves: 'Tristes pero suaves',
      tristesConEnergia: 'Tristes con más energía',
      masIntensas: 'Más intensas',
      ritmoAlto: 'Ritmo alto',
      energiaParaMoverse: 'Energía para moverse',
      masEnfocadas: 'Más enfocadas',
      tranquilasParaTrabajar: 'Tranquilas para trabajar',
      bajaDistraccion: 'Baja distracción',
      masNocturnas: 'Más nocturnas',
      oscurasYCalmadas: 'Oscuras y calmadas',
      suavesDeNoche: 'Suaves de noche',
      masTranquilas: 'Más tranquilas',
      suavesParaBajarRitmo: 'Suaves para bajar ritmo',
      paraLevantarAnimo: 'Para levantar ánimo',
      alegresYLigeras: 'Alegres y ligeras',
      masSuaves: 'Más suaves',
      bajaEnergia: 'Baja energía',
      masLentas: 'Más lentas',
      bajaVelocidad: 'Baja velocidad',
      seleccionSugerida: 'Selección sugerida'
    } as Record<string, string>
  },
  agregados: {
    ayuda:
      'Funciones grandes y opcionales. Se descargan de las publicaciones de NB Sound en GitHub con un clic, y quitarlas libera su espacio en el acto.',
    nombres: {
      karaoke: 'Karaoke',
      analisis: 'Análisis musical',
      textoDj: 'Pedidos al DJ en tus palabras',
      aceleracion: 'Aceleración por GPU'
    },
    descripciones: {
      karaoke:
        'Separa la voz de cualquier canción para cantarla, y prepara los instrumentales para el teléfono y el DJ.',
      analisis:
        'Reconoce el ánimo, la bailabilidad y el estilo de cada canción para las listas inteligentes y el DJ.',
      textoDj: 'Entiende lo que le pides al DJ con tus propias palabras.',
      aceleracion: 'Hace el karaoke y el análisis varias veces más rápidos con la tarjeta gráfica.'
    },
    tamano: (megas: number) => `${megas} MB`,
    instalar: (megas: number) => `Instalar (${megas} MB)`,
    descargando: (porcentaje: number) => `Descargando ${porcentaje} %`,
    instalado: 'Instalado',
    actualizar: 'Actualizar',
    quitar: 'Quitar',
    noDisponible: 'Todavía no disponible',
    ofertaNecesita: (megas: number) =>
      `Necesita un agregado de ${megas} MB. Se descarga una vez y puedes seguir escuchando mientras.`,
    ofertaSigue: 'puedes seguir escuchando',
    ofertaLista: 'Instalado. Pulsa el micrófono para preparar esta canción.',
    cerrar: 'Cerrar',
    recomendado: (gpu: string) => `Recomendado: tu equipo tiene ${gpu}.`,
    gpus: {
      cuda: 'una tarjeta NVIDIA',
      directMl: 'una tarjeta gráfica compatible con DirectML',
      coreMl: 'un procesador Apple con Neural Engine'
    },
    sinConexion: 'Activa los servicios en línea en Privacidad para descargarlo.',
    errores: {
      NETWORK_FAILURE: 'La descarga se cortó. Al volver a pulsar Instalar sigue donde se quedó.',
      INTEGRITY_MISMATCH:
        'El archivo descargado no es el esperado y se ha descartado. Vuelve a intentarlo.',
      STORAGE_FAILURE: 'No hay espacio o no se pudo escribir en el disco.',
      NETWORK_DISABLED: 'Activa los servicios en línea en Privacidad para descargarlo.'
    } as Record<string, string>,
    error: 'No se pudo instalar. Vuelve a intentarlo.'
  },
  actualizacion: {
    buscar: 'Buscar actualizaciones',
    buscando: 'Buscando',
    alDia: 'Tienes la versión más reciente.',
    disponible: (v: string) => `NB Sound ${v} está disponible.`,
    instalar: 'Instalar y reiniciar',
    instalando: 'Descargando e instalando. NB Sound se reiniciará solo.',
    sinConexion: 'Activa los servicios en línea en Privacidad para buscar actualizaciones.',
    noDisponible:
      'Esta instalación se actualiza con el gestor de paquetes del sistema o descargando la nueva versión.',
    firma: 'La descarga no lleva la firma de NB Sound, así que no se ha instalado.',
    error: 'No se pudo conectar. Vuelve a intentarlo más tarde.'
  },
  copia: {
    titulo: 'Copia de seguridad',
    ayuda:
      'Guarda tu biblioteca, playlists, historial y portadas en un solo archivo. No incluye la música ni tus claves.',
    crear: 'Crear una copia ahora',
    creando: 'Creando la copia',
    creada: (megas: string, portadas: number) =>
      `Copia guardada: ${megas} MB, con ${portadas === 1 ? '1 portada' : `${portadas} portadas`}.`,
    restaurar: 'Restaurar una copia',
    confirmarTitulo: '¿Restaurar una copia?',
    confirmarTexto:
      'Tu biblioteca actual se sustituirá por la de la copia al reiniciar NB Sound. La de ahora se aparta, por si hay que volver atrás. Tu música no se toca.',
    elegirCopia: 'Elegir la copia',
    cancelar: 'Cancelar',
    pendiente: 'La copia está lista. Se aplicará al reiniciar NB Sound.',
    reiniciar: 'Reiniciar ahora',
    errorFormato:
      'Este archivo no es una copia de esta versión de NB Sound. Las copias de la versión anterior todavía no se pueden abrir aquí.',
    errorNueva:
      'La copia es de una versión más nueva de NB Sound. Actualiza la aplicación para restaurarla.',
    errorDanada: 'La copia está dañada o incompleta.',
    error: 'No se pudo completar. Vuelve a intentarlo.',
    automaticas: 'Copias automáticas',
    frecuencias: { 0: 'Nunca', 1: 'Cada día', 7: 'Cada semana', 30: 'Cada mes' } as Record<
      number,
      string
    >,
    carpeta: 'Carpeta de las copias',
    sinCarpeta: 'Elige una carpeta para que se hagan.',
    elegirCarpeta: 'Elegir carpeta',
    ultima: (fecha: string) => `Última copia: ${fecha}`,
    ninguna: 'Todavía no se ha hecho ninguna copia.'
  },
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
      },
      actualizaciones: {
        nombre: 'Actualizaciones de NB Sound',
        envia:
          'La versión instalada y el sistema, a GitHub, solo cuando buscas una versión nueva desde Acerca de.'
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
  },
  inteligentes: {
    nueva: 'Nueva inteligente',
    editar: 'Editar regla',
    crearParaMi: 'Crear para mí',
    creandoParaMi: 'Preparando listas',
    ayuda:
      'Se actualiza sola cada vez que importas música, marcas favoritas o escuchas canciones que cumplen estas condiciones.',
    animo: 'Ánimo',
    cualquierAnimo: 'Cualquiera',
    animos: {
      energetica: 'Enérgica',
      tranquila: 'Tranquila',
      bailable: 'Bailable',
      triste: 'Triste',
      nocturna: 'Nocturna',
      entrenamiento: 'Para entrenar',
      concentracion: 'Para concentrarse',
      fiesta: 'Para fiesta',
      feliz: 'Alegre',
      relajada: 'Relajada',
      intensa: 'Intensa'
    } as Record<string, string>,
    bpmMin: 'BPM mínimo',
    bpmMax: 'BPM máximo',
    energiaMin: 'Energía mínima (0 a 100 %)',
    energiaMax: 'Energía máxima (0 a 100 %)',
    instrumental: 'Instrumental de karaoke',
    instrumentalOpciones: {
      cualquiera: 'Cualquiera',
      con: 'Solo con instrumental listo',
      sin: 'Solo sin instrumental'
    },
    soloFavoritas: 'Solo canciones favoritas',
    reproduccionesMin: 'Mínimo de reproducciones',
    reproduccionesMax: 'Máximo de reproducciones',
    frecuencia: 'Última escucha',
    frecuenciaOpciones: {
      cualquiera: 'En cualquier momento',
      reciente: 'Escuchadas en los últimos días',
      olvidada: 'Sin escuchar desde hace días'
    },
    dias: 'Días',
    anioMin: 'Año desde',
    anioMax: 'Año hasta',
    genero: 'Género contiene',
    orden: 'Ordenar por',
    ordenes: {
      recientes: 'Añadidas más recientes',
      masEscuchadas: 'Más escuchadas',
      menosEscuchadas: 'Menos escuchadas',
      ultimaEscuchaAsc: 'Más tiempo sin sonar',
      bpmAsc: 'BPM de menor a mayor',
      bpmDesc: 'BPM de mayor a menor',
      energiaDesc: 'Mayor energía',
      tituloAsc: 'Título (A a Z)'
    },
    limite: 'Máximo de canciones',
    invalida: 'Revisa los rangos: el mínimo no puede superar al máximo.'
  },

  resumenEscucha: {
    titulo: 'Resumen local de escucha',
    sub: 'Tu actividad por mes, por año o en todo tu historial, sin salir del equipo.',
    todo: 'Todo el historial',
    exportar: 'Exportar tarjeta SVG',
    exportando: 'Exportando…',
    exportada: 'Tarjeta guardada.',
    radarTitulo: 'Radar de ánimos',
    radarSub: 'Promedio de las canciones escuchadas en el periodo.',
    ejes: {
      energia: 'Energía',
      bailable: 'Bailable',
      alegre: 'Alegre',
      calma: 'Calma',
      nocturna: 'Nocturna',
      melancolica: 'Melancólica'
    },
    mapaTitulo: 'Mapa de calor por día y hora',
    mapaSub: 'A qué horas escuchas más música en tu hora local.',
    diasSemana: ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'] as const,
    celdaMapa: (dia: string, hora: number, escuchas: number) =>
      `${dia} ${String(hora).padStart(2, '0')}:00 · ${escuchas} ${escuchas === 1 ? 'escucha' : 'escuchas'}`,
    reproduccionesPeriodo: (n: number) =>
      `${n.toLocaleString('es')} ${n === 1 ? 'reproducción' : 'reproducciones'}`,
    meses: {
      '01': 'Ene',
      '02': 'Feb',
      '03': 'Mar',
      '04': 'Abr',
      '05': 'May',
      '06': 'Jun',
      '07': 'Jul',
      '08': 'Ago',
      '09': 'Sep',
      '10': 'Oct',
      '11': 'Nov',
      '12': 'Dic'
    } as Record<string, string>
  },

  copiaDispositivo: {
    titulo: 'Copiar a tarjeta microSD, USB o reproductor portátil',
    ayuda:
      'Exporta tu música con nombres válidos para FAT32/exFAT, portada incrustada y archivo de lista .m3u8.',
    origen: 'Qué copiar',
    origenes: {
      biblioteca: 'Toda la biblioteca',
      favoritas: 'Mis canciones favoritas',
      playlist: 'Una playlist'
    },
    playlist: 'Playlist a copiar',
    sinPlaylists: 'Aún no hay playlists creadas.',
    estructura: 'Estructura de carpetas',
    estructuras: {
      artistaAlbum: 'Artista / Álbum / 01 - Canción',
      artista: 'Artista / 01 - Canción',
      plana: 'Todo en una carpeta (Artista - Canción)'
    },
    incrustarPortada: 'Incrustar portada y etiquetas en las copias',
    convertirWav: 'Convertir a WAV PCM (16 bits, 44,1 kHz) para máxima compatibilidad',
    botonCopiar: 'Elegir carpeta y copiar',
    copiando: 'Copiando al dispositivo…',
    resumen: (copiadas: number, omitidas: number, mb: string, m3u: string | null) =>
      `${copiadas.toLocaleString('es')} ${copiadas === 1 ? 'pista copiada' : 'pistas copiadas'}${omitidas > 0 ? `, ${omitidas.toLocaleString('es')} ya existentes` : ''} (${mb} MB)${m3u ? ` · ${m3u}` : ''}.`,
    error: 'No se pudo completar la copia al dispositivo.'
  },

  modoFiesta: {
    titulo: 'Modo fiesta (QR en red local)',
    ayuda:
      'Abre una página temporal en tu red Wi-Fi para que los invitados busquen canciones y las sugieran desde el navegador sin instalar nada.',
    interruptor: 'Activar Modo fiesta',
    interruptorAyuda:
      'Solo funciona mientras está encendido. Al apagarlo se cierra el puerto y se borran las sesiones.',
    qrEtiqueta: 'Código QR para unirse al Modo fiesta',
    urlEtiqueta: 'Enlace para invitados en la misma red:',
    regenerarQr: 'Rotar QR',
    automatico: 'Encolar sugerencias automáticamente',
    automaticoAyuda:
      'Si está apagado, tú apruebas o descartas cada sugerencia antes de que pase a la cola.',
    sugerenciasTitulo: 'Sugerencias de los invitados',
    sinSugerencias: 'Todavía no han enviado sugerencias.',
    porInvitado: (alias: string) => `Sugerida por ${alias}`,
    enCola: 'En la cola',
    aceptar: 'Aceptar',
    descartar: 'Descartar',
    bloquear: 'Bloquear invitado',
    bloqueados: (n: number) =>
      `${n} ${n === 1 ? 'invitado bloqueado' : 'invitados bloqueados'} en esta sesión`
  }
};

export type TextosAparte = typeof esAparte;
