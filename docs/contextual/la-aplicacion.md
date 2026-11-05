# NB Sound, de punta a punta

> **Qué es este documento:** la descripción de la aplicación tal como es y como tiene que ser, vista por dentro y
> por fuera: qué hace, qué hay en cada pantalla, qué hace cada botón y qué pasa por debajo. Recoge las decisiones de
> Nathan de la revisión QA-R2 (2026-11-05). Si una pantalla y este documento no coinciden, una de las dos está mal.

## En una frase

NB Sound es el reproductor de tu música: la que tienes en tus archivos, no la de un catálogo ajeno. La ordena sola,
la completa (portadas, letras, datos), la hace sonar como merece y te da cosas que ningún servicio de streaming te
da con tu propia biblioteca: un DJ que mezcla de verdad, karaoke de cualquier canción, un juego para redescubrirla y
un teléfono que se lleva todo sin internet.

## Lo que la hace distinta

* **Tu música, en tu equipo.** Nada sale de él si no lo permites, servicio por servicio. Sin cuentas, sin
  suscripciones, sin anuncios. La biblioteca funciona sin conexión.
* **Nada que instalar aparte.** Lo que pesa (el karaoke, el análisis musical, el entendimiento de frases del DJ) son
  agregados que se descargan con un clic desde la propia aplicación y se quitan igual.
* **Una sola aplicación.** No hay modo "simple" y modo "experto", ni pantallas de diagnóstico. Lo técnico vive en
  el registro; lo que ves está escrito para personas.
* **Nunca hay que reiniciarla.** Cambiar la carpeta de la música, el tema, el tamaño, borrar canciones, instalar un
  agregado: todo se aplica al momento. La única excepción es restaurar una copia de seguridad, que cambia la
  biblioteca entera.
* **Se acuerda de todo.** Al volver a abrirla está como la dejaste: la canción, el segundo exacto (en pausa), la
  cola, el aleatorio, la repetición, el volumen, la vista de cada pantalla (cuadrícula o lista, el orden, los
  filtros) y la pestaña en la que estabas.
* **Rápida.** Las listas largas se dibujan por tramos, las portadas se sirven en el tamaño justo, y volver a una
  pantalla ya visitada la enseña al instante con lo que tenía, mientras se actualiza por detrás.

## La ventana

La ventana tiene cuatro partes fijas y el contenido en el centro.

### La barra lateral

A la izquierda, de arriba abajo:

* **El logo**, que cambia con el tema y lleva a Inicio.
* **Explorar:** Inicio.
* **Tu música:** Biblioteca, Playlists y Tu música.
* **Experiencias:** DJ Privado y A ciegas.
* **Al pie:** Por revisar (solo si hay archivos esperando, con su número) y Ajustes.
* **Contraer barra lateral**, separado por una línea que está exactamente a la altura del borde superior de la
  barra de reproducción: la ventana se lee como un solo marco.

Contraída, la barra se queda en iconos (el nombre aparece al pasar el ratón). En ventanas estrechas se contrae
sola.

### La barra superior

* **La caja de búsqueda**, que busca en títulos, artistas, álbumes y letras. El atajo para llegar a ella es Ctrl+K,
  pero el recordatorio no está pintado en la caja: aparece en su texto de ayuda. Con texto, una equis la borra.
* **Karaoke**, **Dispositivos** y **Añadir música**, que abren cada uno su consola lateral.

### La barra de reproducción

Siempre abajo, siempre visible.

* **A la izquierda**, la portada, el título, el artista y el álbum, con todo el ancho para que se lean enteros.
  La portada y el título abren la reproducción ampliada; el artista y el álbum llevan a sus páginas.
* **En el centro**, aleatorio, anterior, reproducir o pausar, siguiente y repetir (la cola entera o una canción).
  Activos, aleatorio y repetir toman el color de acento y llevan un punto debajo; no se confunden con el botón de
  reproducir. Debajo, la forma de onda de la canción, que es también la barra de progreso, con el tiempo a cada lado.
* **A la derecha**, letras, karaoke (si la canción está lista para cantar), la cola con su número, el volumen,
  pantalla completa y el menú **···**.

**El menú ···** de la barra es una ventana flotante como la de la cola, con lo que antes ocupaba sitio junto al
título: **añadir a una playlist**, **poner o quitar de favoritas**, **minirreproductor** y **dispositivos** (en qué
equipo suena, cuando hay un teléfono conectado). Así el título, el artista y el álbum largos se leen.

### El lienzo

El contenido flota en una tarjeta redondeada sobre el fondo de la ventana. Solo él se desplaza; las barras se
quedan quietas.

## Las pantallas

### Inicio

Lo primero que ves, pensado para retomar y para descubrir.

* **El saludo**, de un tamaño moderado y en una línea siempre que quepa, con tu nombre y la hora del día ("Buenas
  noches, Nate…"). A su derecha, el botón **Sorpréndeme**: elige una canción de tu biblioteca que hace tiempo no
  suena, la pone y lo dice. También responde a la tecla D.
* **Retomar reproducción**, con la canción que sonaba (o la última), continuar o pausar, e ir a su álbum.
* **Álbum destacado del día**: uno de los diez discos que más te gustan, con portada, distinto cada día.
* **Vuelve a tu música**: la última que sonó en grande y las anteriores en tarjetas, para volver a cualquiera con un
  clic.
* **Tu top 10**: el podio de los tres primeros, con las portadas grandes y su número de escuchas, y el cuarto puesto
  destacado justo debajo, más grande que el resto; del quinto al décimo, en dos columnas.
* **Tus playlists destacadas**, **Álbumes que vuelven a aparecer**, **Tus 10 álbumes más escuchados**, **Artistas que
  más suenan** y **Últimos añadidos**, en carruseles con flechas.

No hay cifras de la biblioteca (pistas, artistas, álbumes, duración): eso está en Tu música y en Añadir música.

**La primera vez**, con la biblioteca vacía, Inicio es una bienvenida: el logo, cómo te llamamos y tres caminos, cada
uno con su botón. *Tengo una carpeta con mi música* (se importa entera y se vigila lo que copies después), *Quiero
añadir canciones sueltas* y *Vengo de otro equipo* (restaurar una copia de seguridad).

### Biblioteca

Tres pestañas, cada una con su búsqueda, su orden y cuatro tamaños de vista (cuadrícula pequeña, mediana, grande o
lista). Cada pestaña recuerda los suyos.

* **Álbumes**: todos, solo álbumes, o sencillos y EP, como en la V1. Se cargan por páginas al llegar al final.
* **Artistas**: en círculos, con su número de álbumes y canciones.
* **Pistas**: la lista entera, con filtros de favoritas, sin verificar y listas para cantar (y "Preparar mis
  favoritas" cuando ese filtro está puesto). Cada fila: portada, título y artista, álbum, la favorita, la duración y
  las acciones. Sin numeración ni rótulos de columnas: no es un ranking, es tu biblioteca en el orden que elijas.

**Cada canción**, en cualquier lista, al pasar el ratón muestra la favorita, "+" (añadir a una playlist) y **···**:
reproducir a continuación, añadir a la cola, abrir el álbum, abrir el artista, completar datos (si está sin
verificar), editar datos, mostrar en su carpeta y eliminar. Doble clic la reproduce; Enter también.

**Eliminar** pregunta: quitarla solo de la biblioteca, o también mandar su archivo a la papelera del sistema (nunca
se borra del todo). La canción desaparece al momento de todas las listas, de las playlists, de la cola, de Inicio y
del teléfono en la siguiente sincronización, sin recargar nada.

### Álbum

* **La cabecera**, con el color de la portada (si "Color por portada" está activo): la portada grande, el tipo
  (álbum, sencillo, EP), el título, el artista (enlace), el año, el número de canciones y la duración.
* **Las acciones**: reproducir (el botón grande), aleatorio y ··· con añadir a la cola, abrir el artista y editar
  datos.
* **Las canciones**, numeradas y con rótulos de columnas: aquí el orden sí significa algo.
* **Más de este artista**, al final.

### Artista

* La cabecera con su foto en círculo y el color de su música.
* Reproducir y aleatorio.
* **Populares**: sus cinco canciones más escuchadas, ampliables a diez.
* **Álbumes** y **Sencillos y EP**, por separado.
* **Todas sus canciones**.

### Playlists

* **Arriba**: nueva playlist, nueva inteligente y "Crear para mí".
* **Filtros**: búsqueda, categoría (todo, Me gusta, creadas por mí, creadas para ti, This is…, sistema) y orden.
  Cuatro tamaños de vista, como en Biblioteca.
* **Las tarjetas**, con el mosaico de portadas. Las **ancladas** llevan su marca (el icono de anclar sobre el
  mosaico), y se reconocen sin abrirlas.
* **El panel de la derecha** ocupa todo el alto y enseña la elegida: su mosaico, su tipo, su nombre, cuántas canciones
  y cuánto dura, reproducir, abrir, anclar o desanclar, y la lista de sus canciones (sin repetir el número, que ya
  está arriba).

Un clic elige; otro clic, o "Abrir", la abre. En ventanas estrechas el panel no cabe y el primer clic abre.

**Una playlist abierta** tiene la misma cabecera que un álbum, reproducir, aleatorio, **Añadir canciones** (en las
manuales: un buscador dentro de la propia playlist) y ··· con añadir a la cola, anclar, renombrar, editar la regla
(en las inteligentes), duplicar, vaciar y borrar. Sus canciones van numeradas; en las manuales, el ··· de cada una
añade subir, bajar y quitar de la playlist.

**Las inteligentes** se definen con una regla (ánimo, instrumental de karaoke, BPM, energía, reproducciones, años,
última escucha, género, orden y tamaño) y se mantienen solas: cambian al importar, marcar favoritas o escuchar.

**Crear para mí** arma playlists con lo que escuchas: This is… de tus artistas, tops y mezclas.

### Tu música

Tu identidad musical, sacada de tu historial y solo de él.

* **La cabecera**: tu foto (tocarla la cambia), tu nombre (tocarlo lo edita), tus reproducciones, tu año favorito,
  tu hora pico y tus días activos del mes; "Reproducir tu esencia".
* **Tu actividad**: pistas, artistas y álbumes distintos, tiempo escuchado, el ánimo del día y el calendario del mes.
* **Lo que más has querido**: top de canciones, de álbumes y de artistas.
* **Resumen local de escucha**: por mes, por año o de todo el historial, con el radar de ánimos y el mapa de calor
  de días y horas. El mapa responde al periodo elegido: si eliges un mes, enseña las semanas de ese mes; con un año
  o con todo, los días de la semana por hora. Se exporta como tarjeta.

Una escucha cuenta desde los 30 segundos (o la mitad, en las canciones de menos de un minuto), suene entera o no, y
también dentro de una sesión del DJ.

### DJ Privado

Le dices qué te apetece y arma con tu música una sesión mezclada, como la haría un DJ: no una lista, una sesión con
transiciones.

* **El pedido**: un campo de texto ("algo tranquilo para trabajar de noche, sin reguetón"), la duración (30, 60, 90
  o 120 minutos) y fichas para construirlo pulsando: voces, géneros (reguetón, trap, pop, salsa, bachata, cumbia,
  rock…), ánimos, energía y momentos. Cada ficha es una palabra que el motor entiende.
* **La sesión**, arriba en cuanto la pides: su mosaico, lo que entendió en fichas ("reguetón", "fiesta", "pico de
  energía", "sin trap"), sus cifras (canciones, duración, artistas, transiciones limpias), reproducir o pausar, me
  gusta y no me gusta para la que suena, "Otra parecida", "Guardar como playlist" y ··· con descartar. Mientras
  suena, la forma de onda con el punto de entrada y el de salida, y la técnica con la que está mezclando (corte en el
  beat, fundido largo, ecualización, barrido de filtros, capas).
* **Sus canciones**, con su portada y la calidad de la transición que las trae.
* **El historial**, a la derecha y siempre de alto completo: con pocas sesiones se decora (ilustración y una frase
  que invita a pedir la primera); a medida que crece, deja sitio a la lista.

La sesión suena en el mismo reproductor: la cola que tenías espera en pausa y vuelve al terminar.

### A ciegas

Un juego para redescubrir tu música. Ocupa la pantalla entera y crece con ella.

* **Modos**: por la portada, por el sonido (unos segundos sin saber qué suena), redescubrir (las que te gustaron y
  llevan tiempo sin sonar) y la que nunca eliges.
* **Retos por ronda**: 5, 10 o 15.
* **El reto**: la portada grande (o el fragmento), los campos que se van revelando, escribir el título (o "¡La sé!"
  si no se puede escribir), indicios (alfabeto, empieza por, termina en, palabras, letra), ver el artista o el
  álbum, rendirse y pasar.
* **El resumen**: cuántas acertaste, revelaste o pasaste, y la lista de la ronda con su resultado y un botón para
  escuchar cada una. Otra ronda o cambiar de modo.

### Buscar

* **Sin texto**: qué se puede pedir y dieciséis ideas que funcionan ("Algo triste para una noche de lluvia",
  "Música para fiesta"…).
* **Con texto**: si la frase pide algo ("para entrenar", "algo triste"), primero las secciones de lo que pides; luego
  el **mejor resultado** (lo que se llama exactamente así, o lo más cercano al principio de lo escrito) junto a las
  primeras canciones, y después artistas, álbumes y playlists en cuadrícula y todas las canciones.
* El mejor resultado sigue al texto: "beb" lleva antes a lo que empieza por "beb" en su nombre que a un artista
  que solo tiene una canción así.

Escape o la equis de la caja cierran la búsqueda y vuelven a donde estabas.

### La reproducción ampliada

Desde la portada de la barra, o con F. Dos modos:

* **Portada**: la portada grande sobre un fondo del color de la canción, con título, artista, álbum, año y duración.
* **Letras**: la letra sincronizada, centrada, con la línea que suena grande y el resto atenuado, siguiendo la
  canción. Con el karaoke activo, una ficha lo dice.

**Pantalla completa** (F11): si el ratón se queda quieto 3,5 segundos, desaparecen los controles y la barra, y el
color y la letra ocupan toda la pantalla, sin franjas vacías. El desplazamiento de la letra no cuenta como
movimiento. Escape sale de la pantalla completa y luego de la vista.

### La cola

Desde la barra o con Ctrl+Q: una ventana flotante con las canciones que vienen, su duración total, la que suena
marcada, reproducir o quitar cada una, reordenar arrastrando o con el teclado, y vaciarla. La barra de desplazamiento
tiene su propio carril y no tapa nada.

### El minirreproductor

Una ventana pequeña que se queda encima de las demás, con la portada, el título, el artista, los controles, el
progreso, la favorita y cerrar. Responde al instante y se mueve arrastrándola.

## Las consolas laterales

### Karaoke

Para cantar cualquier canción: la voz se separa en tu equipo, sin internet (agregado de karaoke).

* **Ahora suena**: la canción, si está lista y "Cantar ahora" o "Volver a la original"; si no, "Preparar esta
  canción".
* **En preparación**: la canción que se está preparando, con su portada, su título y el porcentaje real, y las que
  esperan detrás, en orden. Se ve siempre, también si la preparación empezó desde otra parte.
* **Tu repertorio**: cuántas canciones están listas, verlas en la biblioteca y preparar tus favoritas.

La preparación sigue sola en segundo plano; si cierras la aplicación, al volver a abrirla continúa donde iba y la
consola lo dice.

### Dispositivos

* **Tus teléfonos**: permitir que se conecten (con la dirección en la red), los conectados con su última conexión y
  quitar, y "Conectar un teléfono" con un código QR y un código para escribir. NB Sound Mobile sincroniza la
  biblioteca, las playlists, las letras y los instrumentales, y controla este equipo como un mando.
* **Copiar a una tarjeta o un USB**: qué copiar (favoritas, una playlist o todo), con qué carpetas, con portada y
  etiquetas, o convertido a WAV para reproductores antiguos.
* **Modo fiesta**: tus invitados escanean un código y sugieren canciones desde su navegador, sin instalar nada; tú
  apruebas, descartas o bloqueas, o las aceptas solas.

### Añadir música

* **Añadir archivos** y **añadir carpeta**, o arrastrar a la ventana en cualquier momento.
* **El estado de la biblioteca**: canciones, álbumes y artistas, y si hay algo en Por revisar.
* **Canciones duplicadas**: las copias que NB Sound apartó, buscar más y limpiarlas.

Mientras importa, una tarjeta discreta abajo a la derecha dice cuántas lleva y cuál va; se puede cancelar sin
perder lo ya añadido. Al terminar: "142 añadidas. 8 por revisar".

## Por revisar

Lo que no entró solo, cada archivo con su motivo en lenguaje llano y un icono que lo distingue: varias versiones
posibles (con el comparador lado a lado y "Elegir esta"), no estamos seguros, no la encontramos, no se pudo guardar,
ya la tienes, parece dañado. Para cada uno: importar tal como está (avisando de lo que le faltará), buscar de nuevo,
descartar (a la papelera) y mostrar en su carpeta; y en lote, importar todas o descartar las seleccionadas.

## Ajustes

* **Biblioteca**: la carpeta de tu música y **Cambiar** (dice cuántas canciones hay en la elegida; si están, solo
  apunta, y si no, las lleva con su avance y deshace todo si algo falla), tu nombre, tu foto y la copia de seguridad
  (crear, restaurar y cada cuánto).
* **Reproducción**: igualar el volumen entre canciones (EBU R128) y el ecualizador de diez bandas con sus
  preselecciones.
* **Apariencia**: 63 temas (oscuros, claros y de alto contraste), cinco tipografías, el **tamaño de la interfaz en
  botones** (no un deslizador) que deja la vista quieta en ese ajuste al cambiarlo, y "Color por portada".
* **Agregados**: karaoke, análisis musical y pedidos al DJ en tus palabras, con su tamaño, instalar y quitar. Lo que
  no está disponible en tu equipo, o todavía no existe, no se muestra.
* **Privacidad y servicios en línea**: un interruptor general y uno por servicio (AcoustID, MusicBrainz, Cover Art
  Archive, Shazam, iTunes, LRCLIB, lyrics.ovh, Deezer, Wikipedia, TheAudioDB, actualizaciones), cada uno diciendo
  qué recibe.
* **Inteligencia artificial**: desempatar con IA cuando dos versiones empatan, con tu propia cuenta (Anthropic u
  OpenAI) y tu clave guardada en el llavero del sistema.
* **Acerca de**: el logo, la versión, buscar actualizaciones e instalarlas, la licencia y los componentes de
  terceros.

## Lo que pasa por debajo

* **Importar.** Cada archivo se valida, se compara con lo que ya tienes (por su huella de contenido y por sus datos),
  se identifica (Shazam, AcoustID, MusicBrainz, iTunes), se le ponen las etiquetas y la portada, se organiza en la
  carpeta de la música (Artista / tipo / Álbum) y se le buscan letra e imagen del artista. Lo dudoso va a Por
  revisar; nada se pierde ni se pisa.
* **La carpeta vigilada.** Lo que copies en la carpeta de la música entra solo cuando termina de copiarse.
* **El sonido.** Un motor de audio propio, sin cortes entre canciones, con la sonoridad medida de cada una para
  igualarlas y su forma de onda.
* **El análisis.** Con el agregado, cada canción recibe su ánimo, su energía, su bailabilidad y su tempo: de ahí salen
  las inteligentes, el DJ, el radar de ánimos y las búsquedas por intención.
* **El teléfono.** Un servidor en tu red, cifrado y con emparejamiento por QR, que sirve la biblioteca, las letras y
  los instrumentales, y recibe órdenes de control.
* **La memoria.** La base de datos guarda la sesión del reproductor (cola, posición, volumen, aleatorio, repetición)
  cada vez que cambia y al cerrar; las preferencias de cada pantalla se guardan al cambiarlas.

## Atajos de teclado

| Tecla | Qué hace |
|---|---|
| Espacio | Reproducir o pausar |
| Flecha izquierda / derecha | Diez segundos atrás o adelante |
| Flecha arriba / abajo | Canción anterior o siguiente |
| S | Aleatorio |
| R | Repetir (la cola, una canción, nada) |
| L | Letras |
| F | Reproducción ampliada |
| K | Karaoke |
| D | Sorpréndeme |
| + y - | Volumen |
| Ctrl+Q | La cola |
| Ctrl+M | Minirreproductor |
| Ctrl+K | Buscar |
| F11 | Pantalla completa |
| Escape | Salir de la pantalla completa, de la reproducción ampliada o de la búsqueda |
