# Fase 8: Capacidades nuevas

> **Objetivo:** lo que el documento de visión proponía y la V1 no tenía. No empieza antes de la paridad
> (Fase 7) salvo lo que ya entró de paso por ser barato: LUFS (Fase 2) y la forma de onda, si sale de la misma
> pasada de decodificación que LUFS.

| Iteración | Qué | Depende de |
|---|---|---|
| F8.1 Forma de onda sobre la barra de progreso, y en el DJ con los puntos de entrada y salida | Picos calculados al importar, en la misma pasada que LUFS | F4.1.12 |
| F8.2 Listas inteligentes vivas | Reglas sobre rasgos (BPM, energía, instrumental, ánimo) y uso (calificación, última escucha), evaluadas en SQLite | F5.3.1 |
| F8.3 Resumen local de escucha | Mensual y anual, radar de ánimos, mapa de calor por hora y día, tarjeta exportable; nada sale del equipo | F2.2.8 |
| F8.4 Copia a dispositivos (microSD, USB, reproductores portátiles) | Estructura de carpetas, portada incrustada, transcodificación opcional | F4.1.9 |
| F8.5 Modo fiesta | Los invitados en la misma red sugieren canciones desde el navegador con un QR | F3, y un ADR de modelo de confianza antes de empezar, porque abre la aplicación a desconocidos |

Cada una exige su ficha completa (objetivo, criterio, dependencias) antes de empezar.

## Estado de la fase

| Iteración | Estado |
|---|---|
| F8.1 Forma de onda | Hecha: 1.000 picos por pista en `sonoridad.picos` (migración V10), calculados en la misma decodificación que los LUFS (`audio/sonoridad.rs`, `medicion.rs`), servidos por `forma_de_onda` y dibujados en `FormaDeOnda.svelte` sobre la barra y en la sesión activa del DJ con los puntos de entrada y salida de `EstadoDj` |
| F8.2 Listas inteligentes vivas | Hecha: `ReglaInteligente` evaluada en SQLite (`playlists/inteligentes.rs`), sincronizada en `playlist_pistas` sin subir `sync_version` cuando no hay cambios, convergencia con `regenerar_automaticas` ("Crear para mí") y diálogo `DialogoInteligente.svelte` |
| F8.3 Resumen local de escucha | Hecha: `resumen_escucha` por mes (`YYYY-MM`), año (`YYYY`) o `"todo"`, radar de seis ánimos (`RadarAnimos`), mapa de calor 7×24 en hora local y tarjeta SVG autónoma exportable (`tarjeta_svg`, `exportar_resumen_escucha`) en `VistaTuMusica.svelte` |
| F8.4 Copia a dispositivos | Hecha: `copia_dispositivo::copiar` con saneado FAT32/exFAT, tres estructuras de carpetas (`ArtistaAlbum`, `Artista`, `Plana`), portada y etiquetas incrustadas en la copia con `lofty` sin tocar los originales, conversión opcional a WAV PCM (16 bits, 44,1 kHz), lista `.m3u8` e interfaz en `SeccionDispositivos.svelte` |
| F8.5 Modo fiesta | Bloqueada: necesita un ADR del modelo de confianza aprobado por Nathan |

## F8.1 Forma de onda

**Objetivo.** La barra de progreso dibuja la forma de onda de la pista que suena, y la sesión del DJ la dibuja con
el punto por el que entró la pista y el punto en el que empezará a irse.

**Depende de.** F2.1.4 (la medida de sonoridad en segundo plano), F4.1.12 (el hilo que la lleva) y F6.1.6 (la sesión
del DJ en el reproductor único).

**Decisiones.**

* Los picos salen de **la misma decodificación** que mide los LUFS (`audio/sonoridad.rs`): no se abre el archivo
  una segunda vez. Por eso se calculan donde se calcula la sonoridad, en el hilo que mide lo importado, y no en la
  importación misma, que la V2 no retrasa con análisis.
* Se guardan **1.000 picos por pista**, un byte cada uno (el máximo absoluto de las dos voces en su tramo, de 0 a
  255), en una columna nueva de `sonoridad` (migración V10). Un número fijo, y no uno por segundo, porque lo que
  se pinta es siempre la pista entera en un ancho dado; 1.000 da para la barra más ancha sin pesar: unos 2,4 MB en
  la biblioteca de 2.400 pistas.
* La medida de una pista sin picos caduca, como la de un archivo que cambió: la biblioteca ya medida se vuelve a
  medir una vez, al ritmo de siempre.
* El silencio tiene picos (a cero) aunque no tenga sonoridad. Un archivo que no se puede leer se apunta con picos
  vacíos para no reintentarlo en cada arranque, igual que su sonoridad.
* La forma de onda se pinta en SVG con las variables del tema; lo reproducido, en el color primario. Solo cambia
  cuando cambia la posición, así que en pausa no se anima nada (ADR-008).

**Criterio de aceptación.**

1. `sonoridad::medir` devuelve la sonoridad y los picos de una sola pasada; una prueba lo comprueba sobre un
   archivo que sube de volumen (los picos crecen) y otro con un silencio en medio (sus picos son cero en ese tramo).
2. La biblioteca medida antes de V10 se vuelve a medir una sola vez; el silencio queda con picos a cero y sin
   sonoridad; un archivo ilegible queda con picos vacíos y no se reintenta. Pruebas en `medicion.rs`.
3. La prueba de presupuesto del esquema sigue por debajo de 16 KB por pista con los picos dentro.
4. El comando asíncrono `forma_de_onda` devuelve los picos de una pista, o una lista vacía sin medida. La barra
   dibuja la forma de onda con lo reproducido resaltado; sin picos, la barra de siempre.
5. En el DJ, la instantánea dice desde dónde entró la pista que suena y dónde empieza a irse (`EstadoDj`), y la
   vista de la sesión y la barra marcan los dos puntos sobre la forma de onda. Una prueba del reproductor comprueba
   que la salida es la del plan de la mezcla y que la entrada de la pista siguiente es la del plan que la trajo.
6. En el fragmento de A ciegas la instantánea no lleva pista, así que no se pide ni se dibuja su forma de onda.

**A las pruebas finales.** Que la forma de onda se corresponda a la vista con lo que suena en diez pistas del
corpus, y que la nueva medida de la biblioteca entera no se note en el equipo.

## F8.2 Listas inteligentes vivas

**Objetivo.** El usuario puede crear y editar listas inteligentes cuyas reglas sobre rasgos (BPM, energía,
instrumental listo, ánimo) y uso (favoritas, reproducciones, última escucha, año, género) se evalúan en SQLite y se
mantienen vivas al cambiar la biblioteca o el historial, convergiendo en el mismo mecanismo con las playlists
automáticas de la V1 ("Crear para mí").

**Depende de.** F2.2.4 (playlists manuales y clasificación móvil), F5.2.1 (instrumentales del karaoke), F5.3.1
(rasgos, análisis profundo y etiquetas de ambiente) y F5.3.3 (`descubrir.rs`).

**Decisiones.**

* **Un solo modelo en `playlists`:** no se añade otra tabla. Una lista inteligente del usuario es una fila de
  `playlists` con `tipo = 'automatica'`, `subtipo = 'inteligente'`, `origen = 'usuario'`, `auto_actualizable = 1` y
  su `ReglaInteligente` en JSON dentro de `regla`. `clasificar` la agrupa en `Categoria::Inteligente` con etiqueta
  `"Inteligente"`, de modo que NB Sound Mobile la recibe como cualquier playlist sin tocar su contrato (ADR-005).
* **Evaluación en SQLite y sincronización sin ruido:** la regla se traduce a una consulta parametrizada sobre
  `pistas`, `rasgos`, `analisis_profundo`, `etiquetas_ambiente` (umbral ≥ 0,5) y `stems` (`estado = 'lista'`).
  Al listar, abrir o reproducir una lista inteligente viva se evalúa su regla y solo se reescribe `playlist_pistas`
  cuando la lista de `id` resultante cambió: así la lista está siempre al día y `sync_version` solo sube cuando de
  verdad entraron, salieron o cambiaron de orden sus canciones.
* **Convergencia con las automáticas de la V1 (F7.1.1):** el mismo módulo regenera las playlists automáticas que la
  V1 creaba en `servicios/biblioteca.py` (`auto:favoritas_sonando`, `auto:redescubrir`, `auto:recientes_biblioteca`,
  `auto:descubrir:canciones`, `auto:recientes_sin_escuchar`, `auto:favoritas_olvidadas`, `auto:top_canciones`,
  `auto:artist_mix_frecuentes`, `auto:album_mix_frecuentes`, `auto:albumes_para_volver`, `auto:this_is:<artista_id>`
  y las siete `auto:mood:*` apoyadas en `descubrir`), respetando `editada = 1` y `visible = 0`.
* **Edición y borrado:** las listas inteligentes creadas por el usuario (`subtipo = 'inteligente'` y
  `origen = 'usuario'`) se pueden editar (nombre, descripción y regla) y borrar; sus canciones las decide la regla,
  no se añaden ni mueven a mano.

**Criterio de aceptación.**

1. `ReglaInteligente` permite filtrar combinando rango de BPM (`rasgos.bpm`), rango de energía
   (`coalesce(analisis_profundo.activacion, rasgos.energia)`), ánimo (`etiquetas_ambiente`), instrumental listo para
   cantar (`stems`), solo favoritas, mínimo y máximo de reproducciones, escuchadas en los últimos $N$ días
   o sin escuchar desde hace al menos $N$ días (incluidas las nunca escuchadas), rango de año y género, con orden y
   límite (1 a 200).
2. Una lista inteligente es **viva**: si una pista pasa a cumplir la regla (por ejemplo, se marca como favorita, se
   reproduce, recibe sus rasgos o su instrumental), al abrir o listar la playlist la pista aparece en ella y
   `playlist_pistas` se actualiza; si el resultado no cambia, `sync_version` no sube.
3. `regenerar_automaticas` crea o actualiza las playlists automáticas de la V1 que alcanzan su mínimo de pistas,
   respeta las que el usuario editó (`editada = 1`) y actualiza las inteligentes vivas.
4. En la vista de Playlists, el usuario puede crear y editar una lista inteligente con su diálogo de reglas, borrarla
   y pulsar "Crear para mí" para regenerar las automáticas.

**A las pruebas finales.** Crear en la instalación real una lista inteligente por BPM + ánimo + favoritas y comprobar
que el teléfono la sincroniza y que al marcar una nueva favorita entra sola; pulsar "Crear para mí" sobre la
biblioteca migrada de la V1 y verificar las listas generadas.

## F8.3 Resumen local de escucha

**Objetivo.** En **Tu música**, el usuario puede explorar su resumen local de escucha por mes, por año o de todo el
historial, con el radar de seis ánimos, el mapa de calor por día de la semana y hora, los más escuchados del periodo y
una tarjeta exportable a archivo desde el propio equipo sin que ningún dato salga por la red.

**Depende de.** F2.2.8 (`perfil.rs` y `VistaTuMusica.svelte`) y F5.3.1 (`rasgos` y `analisis_profundo`).

**Decisiones.**

* **Periodos desde el historial local:** `resumen_escucha` lista los años (`YYYY`) y meses (`YYYY-MM`) con escuchas en
  la hora local del equipo (`'localtime'`), además de `"todo"`, y calcula las cifras, los más escuchados, el radar y el
  mapa de calor filtrados al periodo elegido.
* **Radar de seis ejes:** cada escucha del periodo aporta los seis rasgos de su pista (`energía`, `bailable`, `alegre`,
  `calma`, `nocturna`, `melancólica`), prefiriendo `analisis_profundo` de la versión actual sobre las aproximaciones de
  `rasgos`. El promedio de las escuchas con análisis da los seis valores en `[0, 1]` que se pintan como polígono en SVG.
* **Mapa de calor 7 × 24:** 168 celdas ordenadas de lunes (fila 0) a domingo (fila 6) y de las 00:00 a las 23:00 en la
  hora local, para ver de un vistazo qué días y a qué horas suena más la música.
* **Tarjeta exportable 100 % local:** `exportar_resumen_escucha` genera en Rust (`perfil::tarjeta_svg`) una tarjeta SVG
  autónoma con las cifras del periodo, el radar de ánimos, el artista y la canción principales y el nombre del perfil,
  y la guarda mediante el selector nativo de archivos sin usar la red.

**Criterio de aceptación.**

1. `resumen_escucha` devuelve los años y meses disponibles en `historial` y filtra cifras, tops, radar y mapa de calor
   por `"todo"`, por año (`YYYY`) o por mes (`YYYY-MM`).
2. El radar calcula los seis ejes promediando las escuchas del periodo con `analisis_profundo` o `rasgos`, y el mapa de
   calor asigna cada escucha a su celda `(lunes..domingo) × (0..23)` en hora local.
3. `tarjeta_svg` produce un documento SVG válido y autónomo con los datos del periodo y escapando cualquier carácter
   especial en nombres de usuario, artistas o canciones; `exportar_resumen_escucha` lo escribe en la ruta elegida.
4. `VistaTuMusica.svelte` incorpora el selector de periodo (Todo, años y meses), el radar de ánimos, el mapa de calor
   por día y hora y el botón "Exportar tarjeta".

**A las pruebas finales.** En la instalación real, recorrer en Tu música los resúmenes mensuales y anuales del
historial migrado de la V1, comprobar el radar y el mapa de calor y exportar la tarjeta de un mes y de un año.

## F8.4 Copia a dispositivos

**Objetivo.** El usuario puede copiar toda su biblioteca, sus canciones favoritas o una playlist a una tarjeta microSD,
una memoria USB o un reproductor portátil desde **Ajustes → Dispositivos**, eligiendo la estructura de carpetas, la
incrustación de portada y etiquetas en las copias y la conversión opcional a WAV PCM estándar (16 bits, 44,1 kHz) para
reproductores que no leen formatos modernos, sin tocar jamás los archivos originales de su biblioteca.

**Depende de.** F4.1.1 (`catalogo/etiquetas.rs` con `lofty`), F4.1.9 (`portadas.rs`) y F3.3.1
(`SeccionDispositivos.svelte`).

**Decisiones.**

* **Ninguna ruta cruza el puente IPC:** la carpeta de destino se elige con el selector nativo de carpetas desde Rust
  (`copia_dispositivo_ejecutar`), igual que en `copia_seguridad` y `anadir_musica`, cumpliendo `check-rutas` y ADR-003.
* **Saneado estricto para FAT32 / exFAT:** las tarjetas microSD y memorias USB suelen estar formateadas en FAT32 o
  exFAT, que rechazan `<>:"/\|?*`, caracteres de control y puntos o espacios finales en nombres de carpeta o archivo.
  Cada segmento se sanea de forma determinista y se acota en longitud para que la copia funcione en cualquier sistema
  de archivos portátil.
* **Tres estructuras de carpetas:** `Artista / Álbum / NN - Título.ext` (`artistaAlbum`), `Artista / NN - Título.ext`
  (`artista`) o todos los archivos en la raíz con `Artista - Título.ext` (`plana`), además de escribir un archivo de
  lista `.m3u8` con rutas relativas cuando se exporta una playlist o las favoritas.
* **Etiquetas y portada incrustada sobre la copia:** cuando `incrustar_portada` está activo, `lofty` escribe título,
  artista, álbum, número, año y la imagen de portada (`PictureType::CoverFront`) en el archivo ya copiado en el
  dispositivo, sin abrir en modo escritura el archivo original de la biblioteca.
* **Conversión opcional sin dependencias externas (`convertir_a_wav`):** de acuerdo con la enmienda de ADR-006 (sin
  `ffmpeg` empaquetado), la opción de transcodificación decodifica la pista con `symphonia` (`audio::Decodificador`) y
  escribe WAV PCM de 16 bits a 44,1 kHz estéreo, legible por cualquier reproductor portátil o radio de coche.
* **Copia incremental:** si el archivo de destino ya existe con tamaño positivo y no se pide recodificar ni reescribir
  portada, se reutiliza y se contabiliza como omitido para que actualizar una tarjeta microSD sea rápido.

**Criterio de aceptación.**

1. `copia_dispositivo::copiar` exporta las pistas seleccionadas (toda la biblioteca, solo favoritas o una playlist) a
   una carpeta de destino respetando la estructura elegida (`ArtistaAlbum`, `Artista`, `Plana`) y saneando nombres para
   FAT32/exFAT.
2. Con `incrustar_portada = true`, el archivo copiado en el destino lleva las etiquetas y la portada de la pista o del
   álbum incrustadas con `lofty`, y el archivo original de la biblioteca permanece intacto byte a byte.
3. Con `convertir_a_wav = true`, las pistas se convierten a `.wav` PCM de 16 bits y 44,1 kHz reproducible.
4. Al exportar una playlist o las favoritas se genera además el archivo `.m3u8` con las rutas relativas de las pistas
   copiadas.
5. En **Ajustes → Dispositivos**, el bloque de copia a dispositivos externos permite elegir qué copiar, la estructura de
   carpetas, las opciones de portada y conversión y lanzar la copia mostrando el resumen de pistas copiadas, omitidas y
   bytes escritos.

**A las pruebas finales.** En la instalación real, copiar una playlist y las favoritas a una memoria USB o carpeta de
prueba con portada incrustada y comprobar las etiquetas, la portada, el `.m3u8` y la conversión opcional a WAV.
