/**
 * Los textos de la interfaz, en español.
 *
 * Ningún texto visible se escribe en el marcado: sale de aquí. NB Sound empieza en
 * español, pero con los textos fuera del código otro idioma es un archivo más y no
 * una búsqueda por todo el proyecto (es la regla de NB Books, F1.7.1).
 */
export const es = {
  app: {
    nombre: 'NB Sound'
  },
  comun: {
    cerrar: 'Cerrar'
  },
  avisos: {
    region: 'Avisos',
    regionFallos: 'Fallos',
    cerrar: 'Cerrar el aviso',
    veces: (n: number) => `${n} veces`
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
    colapsarLateral: 'Contraer barra lateral',
    expandirLateral: 'Expandir barra lateral',
    secciones: {
      explorar: 'Explorar',
      tuMusica: 'Tu música',
      experiencias: 'Experiencias'
    }
  },
  busqueda: {
    etiqueta: 'Buscar en tu música',
    marcador: 'Canciones, álbumes, artistas o letras',
    ayudaAtajo: 'Buscar en tu música (Ctrl+K)',
    borrar: 'Borrar búsqueda',
    titulo: 'Buscar',
    subtitulo: 'Encuentra artistas, álbumes, pistas y letras en toda tu biblioteca.',
    artistas: 'Artistas',
    albumes: 'Álbumes',
    pistas: 'Pistas',
    playlists: 'Playlists',
    sinResultados: (q: string) => `Nada en tu biblioteca coincide con «${q}».`,
    sinResultadosSub: 'Prueba con menos palabras, otra grafía o una frase de la letra.',
    resultados: (q: string) => `Resultados de «${q}»`,
    mejor: 'Mejor resultado',
    canciones: 'Canciones',
    todas: 'Todas las canciones',
    tipoArtista: 'Artista',
    tipoAlbum: 'Álbum',
    tipoCancion: 'Canción',
    escribe: 'Escribe arriba para buscar.',
    cerrarBusqueda: 'Cerrar búsqueda'
  },
  reproductor: {
    region: 'Reproductor',
    nadaSonando: 'Nada sonando',
    aCiegas: 'A ciegas',
    adivina: '¿Sabes cuál es?',
    eligeAlgo: 'Elige una canción para empezar',
    anterior: 'Anterior',
    siguiente: 'Siguiente',
    reproducir: 'Reproducir',
    pausar: 'Pausar',
    aleatorio: 'Aleatorio',
    repetir: 'Repetir',
    marcarFavorita: 'Añadir a favoritas',
    quitarFavorita: 'Quitar de favoritas',
    karaoke: 'Modo karaoke',
    karaokePreparar: 'Preparar el karaoke de esta canción',
    letras: 'Letras',
    cola: 'Cola',
    colaCon: (n: number) => (n === 1 ? 'Cola, 1 canción' : `Cola, ${n} canciones`),
    volumen: 'Volumen',
    silenciar: 'Silenciar',
    quitarSilencio: 'Quitar silencio',
    expandir: 'Reproducción ampliada',
    pantallaCompleta: 'Pantalla completa (F11)',
    salirPantallaCompleta: 'Salir de pantalla completa (F11)',
    mini: 'Minirreproductor',
    cerrarMini: 'Cerrar el minirreproductor',
    volverDeMini: 'Volver a la ventana de NB Sound',
    progreso: 'Progreso de la canción',
    repeticion: {
      ninguno: 'Repetir',
      todo: 'Repetir la cola',
      uno: 'Repetir esta canción'
    },
    destino: 'Dónde suena',
    esteEquipo: 'Este equipo',
    sonandoAqui: 'Sonando aquí',
    controlandoDesde: (nombre: string) => `${nombre} lo está controlando`,
    escucharEnElTelefono: 'Para escuchar en el teléfono, elígelo desde NB Sound Mobile.',
    conectarTelefono: 'Conectar un teléfono',
    masOpciones: 'Más opciones',
    anadirAPlaylist: 'Añadir a una playlist',
    sorprendeme: 'Sorpréndeme'
  },
  biblioteca: {
    titulo: 'Biblioteca',
    vistas: { albumes: 'Álbumes', artistas: 'Artistas', pistas: 'Pistas' },
    cuentaPistas: (n: number) => (n === 1 ? '1 pista' : `${n.toLocaleString('es')} pistas`),
    cuentaAlbumes: (n: number) => (n === 1 ? '1 álbum' : `${n.toLocaleString('es')} álbumes`),
    cuentaArtistas: (n: number) => (n === 1 ? '1 artista' : `${n.toLocaleString('es')} artistas`),
    densidad: {
      gridSm: 'Cuadrícula pequeña',
      gridMd: 'Cuadrícula mediana',
      gridLg: 'Cuadrícula grande',
      lista: 'Lista'
    },
    buscar: 'Buscar por pista, artista, álbum o letra',
    favoritas: 'Favoritas',
    sinVerificar: 'Sin verificar',
    paraCantar: 'Listas para cantar',
    grupos: { todos: 'Todos', albumes: 'Álbumes', sencillos: 'Sencillos y EP' },
    favoritasEnCola: (n: number) =>
      n === 0
        ? 'Tus favoritas ya están listas o en camino.'
        : `${n === 1 ? '1 favorita' : `${n} favoritas`} en preparación. Puedes seguir escuchando.`,
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
    anadirACola: 'Añadir a la cola',
    reproducirDespues: 'Reproducir a continuación',
    anadidasACola: (n: number) =>
      n === 1 ? 'Añadida a la cola' : `${n.toLocaleString('es')} canciones añadidas a la cola`,
    sonaraDespues: (n: number) =>
      n === 1
        ? 'Sonará a continuación'
        : `${n.toLocaleString('es')} canciones sonarán a continuación`,
    colaFallo: 'No se pudo cambiar la cola.',
    favoritaFallo: 'No se pudo guardar la favorita.',
    explorarFallo: 'El archivo de esta canción ya no está en el disco.',
    abrirAlbum: 'Abrir álbum',
    abrirArtista: 'Abrir artista',
    marcarFavorita: 'Marcar como favorita',
    quitarFavorita: 'Quitar de favoritas',
    masAcciones: 'Más acciones',
    sinVerificarInsignia: 'Sin verificar',
    completarDatos: 'Completar datos',
    editarDatos: 'Editar datos',
    mostrarEnExplorador: 'Mostrar en su carpeta',
    borrarCancion: 'Eliminar canción',
    confirmarBorrarTitulo: '¿Eliminar canción?',
    confirmarBorrarDetalle: (titulo: string) =>
      `«${titulo}» saldrá de la biblioteca, de tus playlists y del móvil. Su archivo puede quedarse donde está o ir a la papelera, desde donde se recupera.`,
    borrarSoloBiblioteca: 'Quitar de la biblioteca',
    borrarTambienArchivo: 'Quitar y mover el archivo a la papelera',
    borrada: (titulo: string) => `«${titulo}» ya no está en la biblioteca`,
    borrarFallo: 'No se pudo quitar la canción. Su archivo no se tocó.',
    cancelar: 'Cancelar',
    sonando: 'Reproduciéndose actualmente',
    completando: 'Buscando sus datos',
    completado: (r: { identificada: boolean; portada: boolean; letra: boolean }) => {
      const nuevas = [r.portada && 'la portada', r.letra && 'la letra'].filter(Boolean);
      const anadidas =
        nuevas.length === 0
          ? ''
          : `${nuevas.length === 1 ? 'Se añadió' : 'Se añadieron'} ${nuevas.join(' y ')}.`;
      if (r.identificada) return `Identificada. ${anadidas}`.trim();
      return anadidas || 'No se encontró nada nuevo.';
    },
    completarSinArchivo: 'No se encuentra el archivo de esta canción.',
    completarFallo: 'No se pudo completar. Vuelve a intentarlo.',
    lista: 'Canciones',
    columnas: { titulo: 'Título', album: 'Álbum', duracion: 'Duración' },
    vacia: 'No hay canciones que coincidan.',
    vaciaBiblioteca: 'Tu biblioteca está vacía.',
    vaciaTexto: 'Añade canciones o una carpeta entera: aparecerán aquí con sus portadas y letras.',
    sinCoincidencias: 'Nada coincide con lo que buscas.',
    sinCoincidenciasTexto: 'Prueba con menos palabras o quita algún filtro.',
    cargando: 'Cargando',
    // `albumes.tipo` guarda lo que trajo MusicBrainz, en inglés.
    tipos: { Album: 'Álbum', Single: 'Sencillo', EP: 'EP', Compilation: 'Recopilatorio' },
    album: {
      volver: 'Volver a la biblioteca',
      pistas: (n: number, duracion: string) =>
        `${n === 1 ? '1 pista' : `${n} pistas`} · ${duracion}`,
      aleatorio: 'Aleatorio',
      noEncontrado: 'Este álbum ya no está en la biblioteca.',
      masDe: (artista: string) => `Más de ${artista}`
    },
    artista: {
      tipo: 'Artista',
      populares: 'Populares',
      mostrarMas: 'Mostrar más',
      mostrarMenos: 'Mostrar menos',
      albumes: 'Álbumes',
      sencillos: 'Sencillos y EP',
      canciones: 'Todas sus canciones',
      aleatorio: 'Aleatorio',
      resumen: (albumes: number, pistas: number) =>
        `${albumes === 1 ? '1 álbum' : `${albumes} álbumes`} · ${pistas === 1 ? '1 pista' : `${pistas} pistas`}`,
      noEncontrado: 'Este artista ya no está en la biblioteca.'
    }
  },
  inicio: {
    // Los saludos, uno al azar por visita.
    saludosMadrugada: [
      (nombre: string) => `Buenas noches, ${nombre}. La música acompaña la calma de estas horas.`,
      (nombre: string) =>
        `Madrugada tranquila, ${nombre}. Una buena selección para escuchar sin prisa.`,
      (nombre: string) => `Buenas noches, ${nombre}. Tu biblioteca sigue despierta contigo.`,
      (nombre: string) => `${nombre}, escucha con calma en este tramo de la noche.`,
      (nombre: string) => `Buenas noches, ${nombre}. El mejor momento para una escucha atenta.`
    ],
    saludosManana: [
      (nombre: string) => `Buenos días, ${nombre}. Tu música ya está lista.`,
      (nombre: string) => `Arranca el día con una buena selección, ${nombre}.`,
      (nombre: string) => `Buenos días, ${nombre}. Tu biblioteca te estaba esperando.`,
      (nombre: string) => `Hoy puede empezar con algo que ya conoces, ${nombre}.`,
      (nombre: string) => `Buen día, ${nombre}. Hay música pendiente por retomar.`,
      (nombre: string) => `${nombre}, empieza por una canción que marque el ritmo.`,
      (nombre: string) => `La mañana suena mejor cuando eliges bien, ${nombre}.`,
      (nombre: string) => `Tu biblioteca tiene buen material para hoy, ${nombre}.`,
      (nombre: string) => `${nombre}, vuelve a lo que estabas escuchando.`,
      (nombre: string) => `Buenos días, ${nombre}. Elige el primer tono del día.`,
      (nombre: string) => `Hay una sesión esperando por ti, ${nombre}.`,
      (nombre: string) => `${nombre}, tienes favoritos listos para volver a sonar.`,
      (nombre: string) => `Buen día, ${nombre}. Tu biblioteca está en orden.`,
      (nombre: string) => `${nombre}, abre la mañana con algo tuyo.`,
      (nombre: string) => `La primera canción puede cambiar el ritmo, ${nombre}.`,
      (nombre: string) => `Buenos días, ${nombre}. Revisa qué suena mejor ahora.`
    ],
    saludosTarde: [
      (nombre: string) => `Buenas tardes, ${nombre}. Tu próxima escucha está cerca.`,
      (nombre: string) => `Pausa musical, ${nombre}. Hay mucho por retomar.`,
      (nombre: string) => `Buenas tardes, ${nombre}. Dale play a algo que te mueva.`,
      (nombre: string) => `Tu tarde puede seguir con buena música, ${nombre}.`,
      (nombre: string) => `Que no decaiga el ritmo, ${nombre}.`,
      (nombre: string) => `${nombre}, una buena playlist ordena cualquier tarde.`,
      (nombre: string) => `Tu biblioteca tiene opciones para esta hora, ${nombre}.`,
      (nombre: string) => `Hora perfecta para redescubrir favoritos, ${nombre}.`,
      (nombre: string) => `Buenas tardes, ${nombre}. Dale espacio a una canción distinta.`,
      (nombre: string) => `${nombre}, esta tarde puede sonar con más intención.`,
      (nombre: string) => `${nombre}, vuelve a esas canciones que dejaste a medias.`,
      (nombre: string) => `Tu biblioteca tiene justo lo que necesitas ahora, ${nombre}.`,
      (nombre: string) => `Buenas tardes, ${nombre}. Hay álbumes que merecen otra vuelta.`,
      (nombre: string) => `${nombre}, elige algo familiar o prueba otra ruta.`,
      (nombre: string) => `La tarde está lista para una sesión corta, ${nombre}.`,
      (nombre: string) => `${nombre}, tus artistas frecuentes están esperando.`
    ],
    saludosNoche: [
      (nombre: string) => `Buenas noches, ${nombre}. Hora de escuchar sin prisa.`,
      (nombre: string) => `Buenas noches, ${nombre}. Tu música puede bajar el ritmo.`,
      (nombre: string) => `Cierra el día con la canción correcta, ${nombre}.`,
      (nombre: string) => `Que suene algo bien elegido esta noche, ${nombre}.`,
      (nombre: string) => `Baja el ritmo, ${nombre}, y deja que suene tu biblioteca.`,
      (nombre: string) => `${nombre}, esta noche merece una selección fina.`,
      (nombre: string) => `Modo nocturno, ${nombre}. Mejor con una selección tranquila.`,
      (nombre: string) => `Buenas noches, ${nombre}. El mejor cierre del día empieza con play.`,
      (nombre: string) => `${nombre}, deja que una buena canción haga el resto.`,
      (nombre: string) => `Es tu momento, ${nombre}: calma, ritmo y buena música.`,
      (nombre: string) => `Que la noche encuentre una canción precisa, ${nombre}.`,
      (nombre: string) => `${nombre}, ponle música a este tramo del día.`,
      (nombre: string) => `Buenas noches, ${nombre}. Hay álbumes para escuchar con calma.`,
      (nombre: string) => `${nombre}, vuelve a tus canciones de confianza.`,
      (nombre: string) => `La noche pide una escucha más cuidada, ${nombre}.`,
      (nombre: string) => `Buenas noches, ${nombre}. Tu biblioteca sigue despierta.`
    ],
    saludosSinNombre: [
      '¿Qué quieres escuchar hoy?',
      'Dale play a algo que acompañe este momento.',
      'Tu próxima canción favorita puede empezar ahora.',
      'Hoy es un gran día para descubrir nueva música.',
      'Tu biblioteca está lista: solo falta que elijas.',
      'Haz que este momento suene mejor.',
      'Explora algo nuevo: una canción puede sorprenderte.',
      'Elige un ritmo y deja que todo encaje.',
      '¿Listo para una sesión que valga la pena?',
      'Pulsa play: aquí empiezan los buenos descubrimientos.',
      'Tu soundtrack de hoy te está esperando.',
      'Una buena canción siempre llega a tiempo.',
      'Dale una oportunidad a ese tema que aún no has escuchado.',
      'Prueba una selección distinta sin salir de tu biblioteca.',
      'Hoy también puede sonar increíble.',
      'Abre la sesión: hay música para cada momento.',
      'Vuelve a lo que estabas escuchando.',
      'Hay favoritos listos para sonar de nuevo.',
      'Tu biblioteca tiene algo para esta hora.',
      'Elige una canción y deja que la sesión avance.',
      'Redescubre un álbum que no escuchas hace rato.',
      'Hay artistas esperando otra vuelta.',
      'Tu música local tiene mucho por mostrar.'
    ],
    sorprendemeAyuda: 'Pon una canción tuya que hace tiempo no suena (D)',
    pistas: 'Pistas',
    artistas: 'Artistas',
    albumes: 'Álbumes',
    retomar: 'Retomar reproducción',
    continuar: 'Continuar',
    destacado: 'Álbum destacado del día',
    verAlbum: 'Ver álbum',
    reproducir: 'Reproducir',
    vuelve: 'Vuelve a tu música',
    vuelveSub: 'Retoma canciones, álbumes y playlists de tu biblioteca.',
    ultima: 'Última reproducción',
    reproducciones: (n: number) => (n === 1 ? '1 reproducción' : `${n} reproducciones`),
    top: 'Tu top 10 canciones',
    topSub: 'Las que más has repetido en tu biblioteca.',
    podio: {
      lugar1: '1.º lugar',
      lugar2: '2.º lugar',
      lugar3: '3.º lugar'
    },
    playlists: 'Tus playlists destacadas',
    playlistsSub: 'Listas que has creado o escuchado más.',
    queGustan: 'Álbumes que vuelven a aparecer',
    queGustanSub: 'Discos con canciones favoritas o escuchas frecuentes.',
    artistas10: 'Artistas que más suenan',
    artistasSub: 'Los nombres que más aparecen en tu historial.',
    anadidos: 'Últimos añadidos',
    anadidosSub: 'Lo más reciente que entró a tu biblioteca.',
    anterior: 'Anterior',
    siguiente: 'Siguiente',
    masEscuchados: 'Tus 10 álbumes más escuchados',
    masEscuchadosSub: 'Los discos que más han pasado por reproducción.',
    sorprendeme: (titulo: string, artista: string) => `Sorpréndeme: «${titulo}» de ${artista}`
  },
  tuMusica: {
    fotoInvalida: 'Esa imagen no se pudo usar. Elige un PNG o un JPG.',
    identidad: 'Tu identidad musical',
    anonimo: 'Tu música',
    cambiarNombre: 'Cambiar tu nombre',
    nombreMarcador: 'Cómo quieres que te llame',
    resumen: (r: number, d: number, b: number) =>
      `${r.toLocaleString('es')} reproducciones · ${d.toLocaleString('es')} pistas distintas de ${b.toLocaleString('es')} en biblioteca.`,
    anioFavorito: (a: number) => `Año favorito: ${a}`,
    horaPico: (h: string) => `Hora pico: ${h}`,
    diasActivos: (n: number) => (n === 1 ? '1 día activo este mes' : `${n} días activos este mes`),
    esencia: 'Reproducir tu esencia',
    actualizar: 'Actualizar',
    actividad: 'Tu actividad',
    actividadSub: 'Lo que tu historial local dice de ti.',
    escuchadas: 'Pistas escuchadas',
    artistas: 'Artistas distintos',
    albumes: 'Álbumes distintos',
    tiempo: 'Tiempo escuchado',
    animo: 'Mood del día',
    sinEscuchasHoy: 'Todavía no has escuchado nada hoy.',
    escuchasHoy: (n: number) =>
      n === 1 ? '1 pista reproducida hoy.' : `${n} pistas reproducidas hoy.`,
    mes: 'Actividad del mes',
    leyenda: { nada: 'Sin escuchas', poco: '1–5', medio: '6–15', mucho: '16+' },
    dia: (d: number, n: number) => `Día ${d}: ${n === 1 ? '1 escucha' : `${n} escuchas`}`,
    querido: 'Lo que más has querido',
    queridoSub: 'Tus tops según el historial. Álbum o artista llevan a su vista en la biblioteca.',
    topCanciones: 'Top canciones',
    topAlbumes: 'Top álbumes',
    topArtistas: 'Top artistas',
    vacio: 'Escucha música y aquí aparecerá lo que tu historial dice de ti.'
  },
  cola: {
    titulo: 'Cola de reproducción',
    vaciar: 'Vaciar',
    vacia: 'La cola está vacía. Reproduce algo o añádelo desde tu biblioteca.',
    sonando: 'Sonando',
    pausada: 'Pausada',
    reproducir: (t: string) => `Reproducir ${t}`,
    quitar: (t: string) => `Quitar ${t} de la cola`,
    moverConTeclado: 'Alt+Arriba y Alt+Abajo para mover'
  },
  reproduciendo: {
    titulo: 'Reproduciendo',
    volver: 'Volver',
    karaoke: 'Karaoke: canta tú',
    album: (a: string) => `Álbum · ${a}`,
    anio: (a: number) => `Año · ${a}`,
    duracion: (d: string) => `Duración · ${d}`,
    letras: 'Letras',
    sinLetra: 'Esta canción no tiene letra guardada.',
    nadaSonando: 'No suena nada. Elige una canción en tu biblioteca.',
    irA: (t: string) => `Ir a ${t}`,
    verLetras: 'Ver letras',
    verPortada: 'Ver portada'
  },
  playlists: {
    titulo: 'Playlists',
    subtitulo: 'Listas manuales, favoritas y mezclas locales preparadas con tu biblioteca.',
    vaciasTitulo: 'Aún no hay playlists',
    vaciasTexto:
      'Crea la tuya, o pulsa «Crear para mí» cuando tengas música y NB Sound armará unas cuantas con lo que escuchas.',
    nueva: 'Nueva playlist',
    densidad: {
      gridSm: 'Cuadrícula pequeña',
      gridMd: 'Cuadrícula mediana',
      gridLg: 'Cuadrícula grande',
      lista: 'Lista'
    },
    buscar: 'Buscar por nombre o tipo',
    cuenta: (n: number) => (n === 1 ? '1 playlist' : `${n} playlists`),
    categoria: 'Categoría',
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
    anclada: 'Anclada',
    reproducir: 'Reproducir',
    aleatorio: 'Aleatorio',
    renombrar: 'Renombrar',
    borrar: 'Borrar',
    encolar: 'Añadir a la cola',
    duplicar: 'Duplicar',
    duplicada: (nombre: string) => `Copia creada: «${nombre}»`,
    vaciar: 'Vaciar',
    confirmarVaciarTitulo: '¿Vaciar la playlist?',
    confirmarVaciar: (nombre: string) =>
      `Se quitarán todas las canciones de «${nombre}». Las canciones siguen en tu biblioteca.`,
    vaciada: 'Playlist vaciada',
    anadirCanciones: 'Añadir canciones',
    buscarParaAnadir: 'Busca en tu biblioteca para añadir',
    yaEnLista: 'Ya está en la playlist',
    confirmarBorrar: (nombre: string) =>
      `¿Borrar «${nombre}»? Las canciones siguen en tu biblioteca.`,
    quitar: 'Quitar de la playlist',
    subir: 'Subir',
    bajar: 'Bajar',
    vacia: 'Esta playlist todavía no tiene canciones.',
    verMasCanciones: (n: number) => `Ver ${n.toLocaleString('es')} canciones más...`,
    noEncontrada: 'Esta playlist ya no existe.',
    volver: 'Volver a Playlists',
    nombre: 'Nombre',
    descripcion: 'Descripción (opcional)',
    crear: 'Crear',
    guardar: 'Guardar',
    cancelar: 'Cancelar',
    anadirA: 'Añadir a playlist',
    anadida: (nombre: string) => `Añadida a «${nombre}»`,
    quitada: (nombre: string) => `Eliminada de «${nombre}»`,
    yaEstaba: (nombre: string) => `Ya estaba en «${nombre}»`,
    errores: {
      INVALID_INPUT: 'El nombre no puede estar vacío ni pasar de 120 caracteres.',
      NAME_TAKEN: 'Ya tienes una playlist con ese nombre.'
    } as Record<string, string>
  },
  ajustes: {
    titulo: 'Ajustes',
    secciones: 'Secciones de Ajustes',
    biblioteca: 'Biblioteca',
    reproduccion: 'Reproducción',
    apariencia: 'Apariencia',
    acercaDe: 'Acerca de',
    producto: 'NB Sound',
    dispositivos: 'Dispositivos',
    dispositivosSub: 'Tu música en el teléfono, en una tarjeta o en la fiesta.',
    telefonos: 'Tus teléfonos',
    permitirTelefonos: 'Permitir que tus teléfonos se conecten',
    permitirAyuda:
      'NB Sound Mobile sincroniza tu música y controla este equipo desde la misma red Wi-Fi.',
    escuchandoEn: (d: string) => `Disponible en ${d}`,
    conectarTelefono: 'Conectar un teléfono',
    sinTelefonos: 'Todavía no has conectado ningún teléfono.',
    conectadoAhora: 'Conectado ahora',
    controlando: 'Controlando este equipo',
    ultimaConexion: (fecha: string) => `Última conexión: ${fecha}`,
    sinConexiones: 'Aún no se ha conectado',
    quitar: 'Quitar',
    quitarTelefono: (nombre: string) => `Quitar ${nombre}`,
    quitarAyuda: (nombre: string) =>
      `${nombre} dejará de sincronizar y de controlar este equipo. Para volver a usarlo tendrás que conectarlo de nuevo.`,
    cancelar: 'Cancelar',
    tituloQr: 'Conectar un teléfono',
    instruccionesQr:
      'Abre NB Sound Mobile y escanea este código. El teléfono tiene que estar en la misma red Wi-Fi que este equipo.',
    codigoManual: 'Si no puedes escanearlo, escribe este código:',
    caduca: (s: number) => `Caduca en ${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`,
    caducado: 'El código caducó.',
    otroCodigo: 'Generar otro código',
    cerrar: 'Cerrar',
    qr: 'Código QR para conectar un teléfono',
    emparejado: (nombre: string) => `${nombre} ya está conectado.`,
    sinServidor:
      'No se pudo abrir la conexión con los teléfonos. Comprueba que este equipo está conectado a una red.',
    carpeta: 'Carpeta de tu música',
    sinCarpeta: 'Todavía no hay carpeta. La eliges al importar música.',
    nombre: 'Tu nombre',
    nombreAyuda: 'Lo usa Inicio para saludarte.',
    fotoPerfil: 'Foto de perfil',
    fotoPerfilAyuda: 'Imagen visible en tu perfil y estadísticas personales.',
    cambiarFoto: 'Cambiar imagen',
    normalizar: 'Igualar el volumen entre canciones',
    normalizarAyuda:
      'Lleva todas las canciones al mismo nivel (EBU R128). Se aplica desde la siguiente.',
    ecualizador: 'Ecualizador',
    ecualizadorActivo: 'Ecualizador activo',
    preseleccion: 'Preselección',
    personalizado: 'Personalizado',
    preamp: 'Preamplificación',
    banda: (hz: string) => `Banda de ${hz}`,
    tema: 'Tema',
    temasOscuros: 'Temas oscuros',
    temasClaros: 'Temas claros',
    temasEspeciales: 'Alto contraste y OLED',
    tipografia: 'Tipografía',
    escala: 'Tamaño de la interfaz',
    porcentaje: (n: number) => `${n} %`,
    colorPortada:
      'La reproducción, los álbumes, los artistas y las playlists toman el color de su portada',
    muestra: 'NB Sound, tu música',
    version: (v: string) => `NB Sound ${v}`,
    licencia: 'Software libre bajo la licencia GPL-3.0-or-later.',
    terceros: 'Incluye componentes de terceros con sus licencias (THIRD_PARTY_LICENSES.md).',
    modelos:
      'Los agregados usan htdemucs de Meta (MIT) para el karaoke, los modelos de Essentia del MTG de la Universitat Pompeu Fabra (CC BY-NC, uso no comercial) para el análisis y all-MiniLM-L6-v2 (Apache-2.0) para los pedidos al DJ.',
    agregados: 'Agregados',
    privacidad: 'Privacidad y servicios en línea',
    ia: 'Inteligencia artificial'
  },
  importacion: {
    cancelar: 'Cancelar la importación: lo ya añadido se queda',
    soltar: 'Suelta para añadir a tu biblioteca',
    soltarAyuda:
      'Canciones o carpetas enteras. Lo que no se pueda identificar queda en Por revisar.',
    anadir: 'Añadir música',
    anadirArchivos: 'Añadir archivos',
    anadirCarpeta: 'Añadir carpeta',
    catalogando: (n: number) => (n === 1 ? 'Catalogando 1 canción' : `Catalogando ${n} canciones`),
    deTotal: (hechos: number, total: number) => `${hechos} de ${total}`,
    deTotalCon: (hechos: number, total: number, archivo: string) =>
      `${hechos} de ${total} · ${archivo}`,
    resumen: (anadidas: number, revisar: number) =>
      revisar > 0
        ? `${anadidas === 1 ? '1 añadida' : `${anadidas} añadidas`}. ${revisar} por revisar`
        : anadidas === 1
          ? '1 añadida'
          : `${anadidas} añadidas`,
    sinVerificar: (n: number) => (n === 1 ? '1 sin verificar' : `${n} sin verificar`),
    verPorRevisar: 'Ver Por revisar',
    cerrar: 'Cerrar',
    subtitulo: 'Importa pistas individuales o carpetas a tu biblioteca local',
    archivosDesc: 'Selecciona pistas de audio (.mp3, .flac, .m4a, .wav)',
    carpetaDesc: 'Escanea un directorio entero con sus subcarpetas y carátulas',
    arrastrarTitulo: 'Arrastrar y soltar',
    arrastrarDesc: 'Puedes arrastrar archivos o carpetas a la ventana en cualquier momento',
    arrastrarActivo: 'Suelta los archivos aquí para comenzar a importar',
    estadoBiblioteca: 'Estado de la biblioteca',
    archivosPorRevisar: (n: number) =>
      n === 1 ? '1 archivo pendiente por revisar' : `${n} archivos pendientes por revisar`,
    sinPendientes: 'Todo el contenido catalogado sin incidencias'
  },
  porRevisar: {
    titulo: 'Por revisar',
    vacio: 'No hay nada pendiente. Todo lo que importaste está en tu biblioteca.',
    cuenta: (n: number) => (n === 1 ? '1 archivo no importado' : `${n} archivos no importados`),
    causas: {
      candidatos_ambiguos: 'Encontramos varias versiones posibles de esta canción',
      puntaje_intermedio: 'No estamos seguros de que sea esta canción',
      duracion_marginal: 'No estamos seguros de que sea esta canción',
      release_type_dudoso: 'No sabemos si es de un álbum o de un sencillo',
      sin_candidatos: 'No encontramos esta canción en ninguna fuente',
      metadata_insuficiente: 'No encontramos esta canción en ninguna fuente',
      puntaje_bajo: 'No encontramos esta canción en ninguna fuente',
      escritura_fallida: 'No pudimos guardar los datos en el archivo',
      validacion_post_escritura: 'No pudimos guardar los datos en el archivo',
      duplicado: 'Ya tienes esta canción',
      duracion_invalida: 'El archivo parece dañado o incompleto',
      audio_ilegible: 'El archivo parece dañado o incompleto'
    } as Record<string, string>,
    importarTalCual: 'Importar tal como está',
    importarTodas: 'Importar todas tal como están',
    elegir: 'Elegir esta',
    buscarDeNuevo: 'Buscar de nuevo',
    descartar: 'Descartar',
    descartarSeleccionadas: 'Descartar las seleccionadas',
    seleccionar: (nombre: string) => `Seleccionar ${nombre}`,
    candidatos: 'Posibles coincidencias',
    tuArchivo: 'Tu archivo',
    sinEtiquetas: 'El archivo no trae etiquetas: ni título, ni artista, ni álbum.',
    campos: { titulo: 'Título', artista: 'Artista', album: 'Álbum' },
    faltara: 'Entrará sin verificar. Le faltará:',
    falta: { portada: 'portada', letra: 'letra', album: 'álbum', anio: 'año' } as Record<
      string,
      string
    >,
    nadaFalta: 'Entrará sin verificar, con los datos que trae el archivo.',
    confirmar: 'Importar',
    cancelar: 'Cancelar',
    papelera: 'Los archivos descartados van a la papelera del sistema.',
    error: 'No se pudo completar. Vuelve a intentarlo.'
  },
  permisos: {
    titulo: 'Permisos',
    ayuda:
      'Lo que NB Sound necesita del sistema. Se comprueba solo, y si algo falta se pide desde aquí con la ventana de tu sistema.',
    servicios: { telefono: 'Tu teléfono', fiesta: 'El Modo fiesta' },
    para: {
      telefono: 'Que NB Sound Mobile encuentre este equipo y se conecte en tu red.',
      fiesta: 'Que tus invitados abran la página de la fiesta desde su móvil.'
    },
    estados: {
      abierto: 'Permitido',
      bloqueado: 'Bloqueado por el cortafuegos',
      sinCortafuegos: 'Permitido',
      desconocido: 'No se puede comprobar'
    },
    comprobando: 'Comprobando',
    permitir: 'Permitir',
    pidiendo: 'Esperando al sistema',
    cortafuegos: (nombre: string) =>
      `Cortafuegos del sistema: ${({ ufw: 'ufw', firewalld: 'firewalld', windows: 'Firewall de Windows', macos: 'cortafuegos de macOS' } as Record<string, string>)[nombre] ?? nombre}.`,
    nadaMas:
      'NB Sound no usa el micrófono, la cámara ni tu ubicación, y solo lee la carpeta de música que eliges.',
    bloqueadoTitulo: 'El cortafuegos lo está bloqueando',
    avisoAlAbrir: 'Tu teléfono no puede conectarse. Permítelo en Ajustes > Permisos.',
    bloqueadoTelefono:
      'Tu teléfono no puede llegar a este equipo. Permítelo y el sistema te pedirá confirmarlo.',
    bloqueadoFiesta:
      'Los móviles de tus invitados no pueden abrir la página. Permítelo y el sistema te pedirá confirmarlo.'
  },
  karaokeConsola: {
    titulo: 'Karaoke',
    subtitulo:
      'Canta cualquier canción de tu biblioteca. La voz se separa en este equipo, sin internet.',
    abrir: 'Abrir la consola de karaoke',
    motorNoInstalado: 'Falta el agregado de karaoke',
    motorExplicacion:
      'Es lo que quita la voz de las canciones. Se descarga una vez y funciona sin conexión.',
    instalar: 'Instalar el agregado',
    ahora: 'Ahora suena',
    nadaSonando: 'Pon una canción para cantarla.',
    lista: 'Lista para cantar',
    noLista: 'Sin preparar',
    preparandoEsta: (pct: number) => `Preparándose · ${pct} %`,
    cantar: 'Cantar ahora',
    dejarDeCantar: 'Volver a la original',
    prepararPistaActual: 'Preparar esta canción',
    enPreparacion: 'En preparación',
    enEspera: 'En espera',
    fallidas: (n: number) =>
      n === 1
        ? '1 canción no se pudo preparar. "Preparar mis favoritas" lo vuelve a intentar si es favorita.'
        : `${n} canciones no se pudieron preparar. "Preparar mis favoritas" lo vuelve a intentar con las favoritas.`,
    yMas: (n: number) => (n === 1 ? 'Y 1 más después.' : `Y ${n} más después.`),
    siguePorSuCuenta:
      'Se preparan una detrás de otra mientras escuchas. Si cierras NB Sound, sigue donde lo dejó al volver a abrirlo.',
    sinPendientes: 'Nada en preparación. Puedes seguir escuchando mientras se preparan.',
    repertorio: 'Tu repertorio',
    listas: (n: number) =>
      n === 1
        ? '1 canción lista para cantar'
        : `${n.toLocaleString('es')} canciones listas para cantar`,
    verListas: 'Verlas en la biblioteca',
    prepararFavoritas: 'Preparar mis favoritas'
  }
} as const;

export type Textos = typeof es;
