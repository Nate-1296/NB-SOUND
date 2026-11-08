# Pruebas finales en el entorno real

> **Estado:** Vigente desde el 2026-10-30; reescrito el 2026-11-08.
> **Decisión de Nathan (2026-11-08):** quedan solo las pruebas que puede hacer una IA, sin nadie delante. Salen las
> de Windows y macOS (Nathan lo probó en Windows y funciona), la instalación en máquina limpia y todo lo que
> necesita a Nathan: oído, ratón, teléfono físico, claves suyas, contraseñas del sistema o selectores nativos.
> Cada iteración que deja algo sin comprobar lo apunta aquí en el mismo commit, solo si una IA lo puede comprobar.

## Cómo se hace

Todo sobre la aplicación compilada y una **copia** de los datos, nunca los reales: KWin virtual, audio a un sumidero
nulo y la interfaz manejada con JavaScript por el inspector remoto de WebKit (la receta está en la memoria del
proyecto, "Probar la app aislada"). Los trabajos pesados van con `systemd-run` y `MemoryMax`, de uno en uno.

| Lo que antes era a mano | Cómo lo comprueba una IA |
|---|---|
| Oír huecos, clics o saltos de volumen | Grabar el monitor del sumidero nulo (`parec`) y medir: muestras a cero entre pistas, discontinuidades, sonoridad (EBU R128) |
| Pasar el ratón por encima | `CSS.forcePseudoState` (`:hover`) por el inspector y captura de pantalla |
| El teléfono | Un cliente HTTP que habla el [contrato móvil](../adr/decisions/ADR-005-contrato-movil.md), comparado con las respuestas doradas |
| KDE y GNOME (MPRIS) | `busctl --user` sobre `org.mpris.MediaPlayer2.*` |
| Una memoria USB | Una carpeta temporal como destino |
| CPU y memoria | `/proc/<pid>/task/*/stat` y `status` muestreados durante la prueba |

Lo que falle se corrige con su prueba de regresión antes de cerrar.

El arnés de audio vive en `scripts/qa/audio-qa.sh`. Prepara
`~/.cache/nb-sound-qa/pruebas-finales`, enlaza la música sin copiar sus datos y ejecuta las grabaciones y medidas
con `scripts/qa/audio-qa.sh todo`; el propio guion se relanza bajo
`systemd-run --user --scope -p MemoryMax=6G`.

Las pruebas de interfaz y contrato móvil se ejecutan con `scripts/qa/ui-qa.sh todo`. Levanta KWin y Xwayland
virtuales, enruta el audio al mismo sumidero, conecta el inspector de WebKit y compara el DOM, MPRIS, `/proc` y el
manifest con la copia. Igual que el arnés de audio, se relanza bajo `systemd-run` con `MemoryMax=6G`.

La ventana principal nace oculta para no enseñar el tema de fábrica. Si la apariencia guardada falla o tarda más de
1500 ms, se muestra con la que ya estaba en caché; `scripts/qa/ui-qa.sh fallo-apariencia` elimina solo la tabla de
preferencias de la copia y comprueba que la ventana sigue apareciendo.

La Fase 3 se ejecuta con `scripts/qa/ui-qa.sh movil`. [`mobile-qa.mjs`](../../scripts/qa/mobile-qa.mjs) es el
cliente de prueba: habla HTTPS y el WebSocket de control con la huella TLS fijada, descarga el audio en streaming y
compara lo que recibe con la base de la copia, el DOM y el reproductor.

## Fase 2

- [x] Al abrir, la cola, la pista y el segundo en que se quedó la última sesión están ahí, sin sonar hasta pulsar
      reproducir. *(Comprobado por guion el 2026-11-05 sobre la 2.0.9 instalada y la copia de los datos.)*
- [x] Cerrar la ventana mientras suena no deja audio sonando ni procesos vivos. *(Comprobado por guion el 2026-11-05.)*
- [x] Un álbum en MP3 y otro en FLAC, grabados del sumidero: ningún hueco entre pistas. *(Comprobado por guion el
      2026-11-08 sobre el binario compilado y la copia: 10 uniones MP3 y 1 FLAC, con 0 ms añadidos.)*
- [x] Buscar a una posición cae donde se pide; pausar y reanudar no deja discontinuidad en la grabación.
      *(Comprobado por guion el 2026-11-08: 4,000000 s solicitados y observados, 0 discontinuidades.)*
- [x] Las 18 preselecciones del ecualizador, grabadas al volumen máximo: ninguna recorta. *(Comprobado por guion el
      2026-11-08: 0 muestras recortadas; pico máximo -5,94 dBFS.)*
- [x] Con la normalización activa, una pista alta y una baja quedan a menos de 2 LU en la grabación. *(Comprobado
      por guion el 2026-11-08: -14,047 y -14,038 LUFS; diferencia 0,008 LU.)*
- [x] La medición de sonoridad sobre la copia de la biblioteca: por debajo de un núcleo y sin vacíos de buffer en lo
      que suena. *(Comprobado por guion el 2026-11-08: 68,68 % de un núcleo, 104 → 100 pistas pendientes y 0 huecos
      durante 4,08 s de reproducción.)*
- [x] La biblioteca (2.397 canciones, 1.421 álbumes): desplazarse por guion sin fotogramas largos, portadas al frenar;
      buscar, filtrar, ordenar y abrir álbum y artista. *(Comprobado por guion el 2026-11-08: 166 fotogramas, máximo
      28 ms, p95 20 ms, 0 fotogramas sobre 50 ms; 15 de 15 portadas cargadas; búsqueda, 51 favoritas, orden Z-A y
      ambos detalles abiertos.)*
- [x] Playlists: categorías, mosaicos y orden; crear, renombrar, ordenar, quitar, borrar y añadir; el cliente del
      contrato recibe los cambios y «Me gusta». *(Comprobado por guion el 2026-11-08 con el manifest HTTPS: orden
      `[2,1]`, nombre, canción quitada, mosaico 1/1, categoría, favorita y tombstone recibidos.)*
- [x] La vista de reproducción toma el color de la portada; la letra sincronizada sigue a la canción y lleva al segundo
      pulsado; la cola reordena con Alt+flechas. *(Comprobado por guion el 2026-11-08: acento `#f5bd6f` frente a
      `#ff2020` del tema, 35 líneas sincronizadas y cola `[1,2,3]` → `[2,1,3]`.)*
- [x] Abre con `sangre_dragon` y Fira Sans sin un fotograma con el tema de fábrica; los 63 temas se pintan.
      *(Comprobado por guion el 2026-11-08: ninguna captura negra desde el primer fotograma; 63/63 temas aplicados y
      0 errores de consola.)*
- [x] Ajustes: tema, tipografía y tamaño se aplican al momento; la normalización entra desde la canción siguiente.
      *(Comprobado por guion el 2026-11-08: `#0e0000`, Fira Sans y 125 % inmediatos; la pista actual cambió 0,069 LU
      al activar y la siguiente quedó a 0,642 LU.)*
- [x] Inicio muestra Retomar, el álbum destacado, las secciones y el saludo por el nombre. *(Comprobado por guion el
      2026-11-08: saludo «Nate», Retomar, álbum destacado y las siete secciones.)*
- [x] MPRIS publica título, artista, portada, duración y posición; sus órdenes controlan la aplicación; aleatorio y
      repetición se reflejan en los dos sentidos. *(Comprobado por guion el 2026-11-08 con `busctl`: metadatos y
      posición correctos, PlayPause/Next/Previous/Seek/SetPosition, Shuffle y LoopStatus bidireccionales.)*
- [x] Los atajos (espacio, flechas, S, R, L, F, K, +/-, Ctrl+Q, Ctrl+M) funcionan y no interfieren al escribir.
      *(Comprobado por guion el 2026-11-08 con `KeyboardEvent`: todos actuaron, se abrió una segunda ventana para
      Ctrl+M y el espacio no cambió el estado con el foco en la búsqueda.)*
- [x] Tu música: cifras del historial de la copia, hora pico en hora local, mood del día, días activos y tops.
      *(Comprobado por guion el 2026-11-08 contra `sqlite3 -readonly`: 3.604 reproducciones, 459 pistas, 146 artistas,
      316 álbumes, hora pico 17:00, 8 días activos y top encabezado por «DEGENERE».)*

## Fase 3

- [x] Con la biblioteca de la copia, el cliente recibe el manifiesto sin volver a descargar todo y las playlists traen
      su mosaico (F3.1.4). *(Comprobado por guion el 2026-11-08: 2.352 pistas, 1.507 álbumes, 492 artistas y 53
      playlists; la segunda sincronización repitió 0 entidades, un cambio trajo solo la playlist nueva y el mosaico
      respondió con 72.099 bytes en 600×600.)*
- [x] Desde el cliente: reproducir, pausar, saltar, buscar, volumen, aleatorio, repetición y karaoke; la cola espejada
      se mantiene al cambiar de destino (F3.2.1). *(Comprobado por guion el 2026-11-08 con WSS: PlayPause, Next y
      Previous, Seek a 18,45 s, volumen 37, aleatorio, repetición «uno» y karaoke; la cola
      `[1150,1253,172]` → `[1253,1150,172]` del móvil → `[1150,172,1253]` del equipo coincidió en ambos lados.)*
- [x] Emparejar con el código corto y quitar el dispositivo lo desconecta al momento (F3.3.1). *(Comprobado por guion
      el 2026-11-08 con un código de 8 caracteres: el WSS se cerró, el manifest siguiente respondió 401 y el
      dispositivo desapareció de la lista.)*
- [x] "Dónde suena" dice qué cliente controla el equipo mientras lo hace (F3.3.2). *(Comprobado por guion el
      2026-11-08: `QA IA Fase 3`, conectado y `controlando: true`; el menú mostró «QA IA Fase 3 lo está
      controlando».)*
- [x] Una descarga completa de la biblioteca: sin vacíos de buffer y la ventana sin fotogramas largos. *(Comprobado
      por guion el 2026-11-08: 2.352 audios y 14.001.578.045 bytes en 35,20 s; 2.188 fotogramas, máximo 47 ms, p95
      17 ms y 0 sobre 50 ms; WAV de 35,22 s sin huecos ni discontinuidades. El servidor escuchó solo en
      `192.168.18.119:8731` y todas sus conexiones establecidas quedaron en bucle local o red privada.)*

## Fase 4

- [ ] AcoustID y MusicBrainz responden con la clave que ya está en el llavero, con el consentimiento de la copia.
- [ ] Importar una carpeta por la orden del puente: tarjeta de progreso y resumen.
- [ ] Matar el proceso a mitad de una importación y volver a abrir: sigue sin duplicar nada.
- [ ] Por revisar: cada motivo con su texto, elegir candidato, importar tal como está, buscar de nuevo y descartar;
      el archivo descartado está en `~/.local/share/Trash` (con un archivo sintético, no del corpus).
- [ ] Con la red desactivada, importar canciones con etiquetas: entran sin verificar.
- [x] Copiar un álbum en la carpeta vigilada lo importa al terminar de copiarse; con la aplicación cerrada, al abrirla.
      *(Comprobado por guion el 2026-11-05 en la 2.0.7 con un archivo sintético.)*
- [ ] Privacidad: apagar un servicio corta su siguiente petición sin reiniciar; con la conexión general apagada no
      sale nada (contando conexiones con `ss`) (F4.2.7).
- [ ] "Completar datos" sobre una pista sin verificar le pone portada y letra; el cliente la vuelve a descargar con los
      datos nuevos (F4.2.8).
- [ ] Editar una canción y un álbum (sobre una copia del archivo, no un enlace duro): el cliente recibe el cambio, el
      archivo lleva las etiquetas, renombrar conserva la portada y reimportar respeta lo editado (F4.2.5).
- [ ] Copia de seguridad, cambiar la biblioteca, restaurar y reiniciar: vuelve a estar como en la copia (F4.2.6).

## Fase 5

- [ ] Instalar cada agregado de la Release `agregados-1`, cortar la red a mitad y reanudar; la suma coincide con el
      catálogo (F5.1.2).
- [ ] Separar con el modelo real (`karaoke::tests::con_el_modelo_real_separa_una_pista`) y en la aplicación: sin vacíos
      de buffer con todos los núcleos ocupados y el pico de memoria por debajo de 3 GB (F5.2.1, P8).
- [ ] Preparar una canción para karaoke desde la orden del puente: avance en el botón, lo que suena no se corta y al
      terminar se pasa al instrumental sin hueco (F5.2.2); sin el agregado, se ofrece con su tamaño (F5.1.4).
- [ ] "Cooler Than Me" (48 kHz) se prepara para karaoke y aparece su micrófono.

## Fase 6

- [ ] El tokenizador propio da los mismos ids que `tokenizer.json` de MiniLM en 50 frases del DJ, y los embeddings
      coinciden (F6.1.1).
- [ ] Una sesión de una hora con las cinco técnicas, grabada: ninguna discontinuidad, hundimiento ni subida brusca de
      sonoridad en las transiciones (F6.1.3).
- [ ] Reproducción normal por debajo del 2 % de un núcleo y una mezcla en curso por debajo del 4 % (F6.1.3).
- [ ] La medida del equipo termina en menos de dos minutos con un perfil coherente (F6.1.4).
- [ ] Una sesión del DJ suena en menos de 3 s, muestra cómo se entendió, crece hasta la duración, la barra la
      controla, "Otra parecida" y "Descartar" devuelven la cola, y al cerrar y abrir vuelve en pausa (F6.1.6).
- [ ] Una ronda de cada modo de A ciegas: el fragmento empieza en el 30 %, ni la barra ni MPRIS ni el cliente dicen la
      canción, un error de una letra acierta y la cola vuelve donde estaba (F6.2.2).

## Fase 8

- [ ] Diez pistas: la forma de onda coincide con la envolvente de la grabación; en el DJ marca entrada y salida; medir
      la biblioteca entera no se nota (F8.1).
- [ ] Una lista inteligente por BPM, ánimo y favoritas llega al cliente y una favorita nueva entra sola; "Crear para
      mí" genera las listas automáticas (F8.2).
- [ ] Tu música: resumen por año y mes, radar de ánimos, mapa 7×24 y una tarjeta SVG exportada y válida (F8.3).
- [ ] Copiar una playlist y las favoritas a una carpeta temporal: estructura, portada incrustada, `.m3u8` y la
      conversión a WAV (F8.4).
- [ ] Modo fiesta con un cliente HTTP: buscar, sugerir, aprobar, descartar, modo automático y rotar el QR deja sin
      efecto el enlace anterior (F8.5).

## Revisiones QA-R1, QA-R2 y QA-R3

- [ ] Quitar una canción "y mover el archivo a la papelera": está en la papelera y se puede restaurar; sale de sus
      playlists, de la cola y del cliente (archivo sintético).
- [ ] Cancelar una importación grande a la mitad: lo importado se queda, el resto no vuelve al reabrir.
- [ ] "Buscar duplicados" sobre la copia no aparta nada que no sea una copia real.
- [ ] Cambiar la foto de perfil por un PNG y un JPG grandes desde la orden del puente: se ve al momento.
- [ ] Con `:hover` forzado y con Tab: en una fila el número se cambia por reproducir y aparecen favorita, "+" y ···;
      tarjetas de Inicio, flechas de carruseles, el botón grande y las filas del DJ.
- [ ] El menú ··· de fila, álbum y playlist se abre junto al botón, se recorre con flechas, se cierra con Escape y
      cerca del borde inferior se abre hacia arriba.
- [ ] La cabecera de álbum, artista y playlist toma el color de la portada; con "Color por portada" apagado, el del tema.
- [ ] Consola de karaoke: "Cantar ahora" pasa a "Volver a la original"; "Verlas en la biblioteca" abre Pistas filtrado;
      con varias pedidas, la primera con porcentaje y las demás "En espera", y sigue con la misma tras reiniciar.
- [ ] Cambiar la carpeta de la música por la orden del puente a otra carpeta temporal: con copia hecha solo apunta;
      vacía, "Llevar mi música" mueve con avance y no deja carpetas vacías; lo nuevo se importa solo.
- [ ] Tu música: editar el nombre, Enter guarda, Escape cancela, y Ajustes e Inicio lo ven.
- [ ] Las ancladas llevan su distintivo en las cuatro densidades de Playlists.
- [ ] Pantalla completa: sin eventos de ratón 3,5 s los controles se esconden sin dejar franja vacía.
- [ ] Ctrl+M abre y cierra el minirreproductor al momento; volver trae delante la ventana grande.
- [ ] En la cola larga la barra de desplazamiento no tapa la duración ni quitar; con un cajón, la cola o un menú
      abiertos, la de debajo no se ve encima.
- [x] Karaoke, Dispositivos y Añadir música entran deslizándose desde la derecha. *(Comprobado el 2026-11-06.)*
- [x] Reproducir la biblioteca entera y abrir la cola: abre al momento y Vaciar responde. *(Comprobado el 2026-11-05.)*
- [ ] Desplazarse rápido por Biblioteca y Playlists sin fotogramas largos; volver a una vista la muestra al momento.
- [ ] Una instalación con datos vacíos abre en la bienvenida; elegir la carpeta por la orden del puente la importa y
      la vigila.
- [ ] Por revisar: "Otras 3 versiones" despliega y repliega; las filas se apagan al importar y vuelven si algo falla.
- [ ] "¿Dónde está tu música?" con la carpeta buena dice que están todas y suena sin reiniciar; con una vacía, ofrece
      otra.
- [ ] La barra a 720 px: la fila de controles del menú ··· responde y se cierra al elegir letras o pantalla completa.
