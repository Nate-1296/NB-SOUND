# Bitácora de trabajo

> Registro de lo que se hace en cada sesión, en orden: qué se terminó, con qué commit, qué se verificó y qué quedó
> pendiente o decidido por el camino. El estado de cada iteración sigue viviendo **solo** en la tabla de su fase
> ([plan](./README.md), sección 4); esto es el diario que explica cómo se llegó ahí. Cada entrada nueva va al final.

## Cómo se lee

* **Commit**: el identificador corto en la rama de trabajo.
* **Verificado**: lo que pasó antes de subirlo. Salvo que se diga otra cosa, la verificación completa de la
  sección 6 de `CLAUDE.md`: `pnpm verify`, `cargo fmt --check`, `cargo clippy -D warnings` y `cargo test`.
* **Pendiente**: lo que no se pudo comprobar en el entorno de trabajo y se apuntó en
  [pruebas finales](./pruebas-finales.md), o lo que espera una decisión en
  [preguntas abiertas](../contextual/open-questions/README.md).

## 2026-10-30 y 2026-10-31: cierre de la Fase 4

Se retomó desde `3aa802c` (F4.2.2 a medias, subido sin verificar). Todo se trabajó en la rama
`claude/exciting-carson-39m9r0` con el borrador de PR `Nate-1296/NB-SOUND#2`, porque la sesión no podía empujar a
`main`; fusionarlo deja `main` como pide `CLAUDE.md`.

Para compilar en el contenedor hicieron falta las librerías de sistema de Tauri (`libwebkit2gtk-4.1-dev`,
`libgtk-3-dev` y compañía) y `node scripts/fetch-binarios.mjs`, que descarga `fpcalc` y ONNX Runtime fuera del
repositorio.

| Commit | Iteración | Qué se hizo | Pruebas nuevas |
|---|---|---|---|
| `0e80ca2` | F4.2.2 | Carpeta vigilada terminada. Defecto corregido: también se excluye lo que espera en la cola, que dejaba una importación sin terminar. Sin carpeta fijada, espera a la primera importación en vez de exigir reinicio | El vigilante real con `notify` y un álbum copiado en dos tiempos |
| `4993346` | F4.2.7 | Ajustes > Privacidad (interruptor general y por servicio, con lo que envía) e Inteligencia artificial (proveedor, modelo y clave en el llavero, que nunca vuelve al webview). La política se aplica a la puerta en el acto | La política guardada y aplicada; validación del modelo; cuentas del llavero |
| `f624727` | F4.1.7 | `catalogo/ia.rs`: desempate por IA con el prompt y la validación de `external/ia_client.py`; un lanzamiento fuera de la lista cerrada descarta la respuesta | Lista cerrada, revisión manual, confianza acotada, forma de la petición de cada proveedor, la clave fuera del `Debug` |
| `caac72c` | F4.2.8 | "Completar datos" sin cambiar el `id`. La identificación de la canalización pasa a `identificar_y_decidir`, compartida | La letra añadida sin cambiar el `id`; la fila rehecha y los vacíos borrados |
| `e8dec4f` | F4.2.7 | Los textos de lo que se carga aparte salen del arranque (`es-aparte.ts`): de 248,1 a 246 KB | `check-paquete` |
| `f33c072` | F4.2.5 | Editar pista y álbum sin cambiar `id`; renombrar un álbum conserva su fila y su portada, y solo se junta con otro igual del mismo artista | Renombrar, juntar, cambiar de artista, editar una pista, rechazos |
| `683edb4` | F4.2.5 | Las correcciones: lo editado se recuerda por huella e ISRC y la importación lo aplica antes de ir a la red | Claves, orden huella > ISRC > artista y título, importación de punta a punta sin red |
| `02d169a` | F4.2.6 | Copia de seguridad `.nbsound-backup` con el formato más la versión de esquema; restaurar valida entera y se aplica al reiniciar; copias automáticas. Entra `zip` (ADR-002) | Ida y vuelta completa; rechazo de una copia, una más nueva, una dañada y una con ruta trampa |
| `d35ce3b` | F4.1.12 | `rasgos.rs`: el modo `light`, con el seguidor de pulsos de librosa 0.11 leído en su código y la tonalidad con perfiles de Krumhansl, en el hilo de la sonoridad | Tempo exacto en la rejilla, pulsos cada periodo, tono puro, acordes mayor y menor, preferencias |
| `cba2eef` | Fase 4 | Cierre de lo automático y lo real apuntado en pruebas finales | `check-docs` |
| `6b01e24` | F5.1.1 | P13 registrada: los agregados no están publicados | `check-docs` |

**Decisiones tomadas por el camino.**

* La carpeta vigilada no vigila por su cuenta la carpeta de música del sistema: importaría sin preguntar toda la
  música que ya hubiera en ella.
* "Completar datos" y "Editar datos" ponen las etiquetas en el archivo pero no lo mueven.
* Editar a mano no marca una pista como verificada.
* Restaurar una copia nunca cambia la base con la aplicación abierta.
* Las filas que ya tienen rasgos se respetan; solo se analiza lo que no tiene.
* El recorte de pulsos de librosa 0.11, que quita de más en los extremos, se replica tal cual.

**Avisos.** El arranque quedó en 248,6 KB de 250: lo próximo de interfaz se carga aparte. `cargo-deny` no está en
el contenedor; las licencias nuevas (MIT y Apache-2.0) se revisaron a mano.

## 2026-10-31: Fase 5

Nathan delegó la decisión sobre P13 y pidió seguir con la Fase 5. Se construye la mecánica de agregados con el
catálogo preparado y sus entradas marcadas como no publicadas: en cuanto haya una Release con los archivos, basta con
rellenar URL, tamaño y SHA-256.

| Commit | Iteración | Qué se hizo | Pruebas nuevas |
|---|---|---|---|
| `832a152` | — | Esta bitácora, con todo lo anterior | `check-docs` |
| `2e037ea` | F5.1.1, F5.1.2 | `agregados.rs`: catálogo compilado sin publicar (P13) e instalación reanudable, verificada y atómica; `Red::descargar` a disco con `Range` | Corte y reanudación, `Range` ignorado, hash alterado, ruta trampa, quitar y reinstalar |
| `2ef9687` | F5.1.3 | Ajustes > Agregados con su gestor y progreso. Para dar margen al arranque (249,2 KB de 250), lo del puente que solo usan pantallas diferidas pasa a `$core/ipc/aparte.ts` y Dispositivos se carga aparte: 245,4 KB. Se devuelve a su función un comentario de documentación que una inserción anterior había separado | El gestor con el catálogo sin publicar |
| `410b943` | F5.1.5 | `gpu.rs`: la GPU que aprovecharía ONNX Runtime, sin procesos externos; Ajustes recomienda el agregado de aceleración con su motivo y nunca lo instala solo | El controlador de NVIDIA con y sin tarjeta |
| `cb35203` | F5.2.1 | `karaoke.rs` y `onnx.rs` (carga el ONNX Runtime que viaja dentro). Entra `ort` (ADR-002). P14 registrada sobre el formato del instrumental | Todo voz da silencio, sin voz da la mezcla, cancelación y forma, WAV leído por el reproductor, la cola, ONNX Runtime cargado de verdad |
| `306aee3` | F5.2.2, F5.1.4 | El micrófono prepara mientras suena y ofrece el agregado; el instrumental listo entra en la pista que suena sin desfase. Defecto evitado: pasar el frame por segundos perdía uno por redondeo, de ahí `buscar_frame`. La fila del contrato del reproductor que pedía desactivar el micrófono se rediseña según ADR-007 | El instrumental a mitad de pista en su frame exacto |
| `4fb295f` | F5.2.3, F5.2.4 | Filtro "Listas para cantar" y "Preparar mis favoritas" | El filtro solo da las que tienen instrumental; favoritas en cola sin repetir |
| `9a91d52` | F5.3.1, F5.3.2 | `analisis.rs`: MusiCNN y sus cabezas con la cadena de F0.4.3, en segundo plano y reanudable. Defecto corregido: valencia y activación de DEAM se recortaban a 1. Atribución de los modelos en Acerca de y en los avisos de terceros | Clase positiva de cada cabeza y escala de DEAM, parches de Essentia, lotes de 8, remuestreo lineal, filas que caducan |
| `a1cb5cc` | F5.3.3 | `descubrir.rs` y sus secciones en Buscar. Para dar margen al arranque (249,4 KB), Reproducción y Apariencia de Ajustes pasan a `SeccionesEscucha.svelte`, que se carga aparte: 244,3 KB | La frase, orden y sin repetir, sin intención no hay nada, la activación no cuenta |

**Estado al cerrar la sesión.** Todas las iteraciones de la Fase 5 tienen sus pruebas automáticas en verde salvo lo
que depende de publicar los agregados: F5.1.1 (las URL, tamaños y SHA-256 del catálogo) y el agregado de
aceleración de F5.1.5 esperan a P13, y su tamaño a P6. Lo que solo se comprueba con los modelos reales (separación,
paridad del análisis, vacíos de buffer, memoria) está en [pruebas finales](./pruebas-finales.md).

**Decisiones tomadas por el camino.**

* El instrumental se guarda como WAV de 16 bits mientras no haya codificador aprobado (P14).
* Pulsar Instalar en un agregado, con el tamaño y el origen a la vista, cuenta como consentimiento del servicio
  de agregados; con la conexión general apagada no se descarga nada.
* Valencia y activación del análisis van en `(v − 1) / 8` y las filas de otra versión se reanalizan: recortarlas a
  `[0, 1]` daba casi siempre 1.
* Las secciones del descubrimiento se titulan desde el diccionario, no desde Rust.

**Aviso.** El arranque se mantuvo dentro de los 250 KB llevando a carga diferida todo lo que solo usan pantallas
secundarias (textos en `es-aparte.ts`, puente en `$core/ipc/aparte.ts`, Dispositivos, Reproducción y Apariencia de
Ajustes); quedó en 244,3 KB.

## 2026-10-31: Fase 6

| Commit | Iteración | Qué se hizo | Pruebas nuevas |
|---|---|---|---|
| `aa43803` | F6.1.1 | Ontología, intención y embeddings del DJ. La tabla de conceptos se generó desde el módulo con un script de un solo uso fuera del repositorio, para no transcribir a mano 800 líneas de datos; las respuestas doradas (`dj/doradas_intencion.json`) salen del mismo módulo. El tokenizador de MiniLM se escribe a mano: `tokenizers` no está en ningún ADR | 14 intenciones y dos embeddings iguales a sus doradas; la tabla y sus cinco referencias muertas; el WordPiece |
| `62d1428` | F6.1.2 | Narrativa, planificador y constructor por bloques, con la puntuación de transiciones y el refinado del orden que el constructor usa en cada bloque (la mezcla audible queda en F6.1.3). Para que la misma semilla dé la misma sesión se escribe el Mersenne Twister de Python (`dj/azar.rs`) y la suma compensada de `sum()` de Python 3.12+. Se cierra un hueco de F4.1.12 y F5.3.1: las etiquetas de ambiente (`derive_vibe_tags` y su versión del modelo) no se guardaban, y el DJ las usa para penalizar lo negado | Siete sesiones con semilla iguales bit a bit a sus doradas (pistas, orden, puntuaciones, razones, transiciones, resumen); la secuencia del azar; las propiedades de `test_dj_privado_scheduler.py`; la carga de candidatas; el ambiente |

**Decisiones de F6.1.2.**

* La intención guarda sus mapas en el orden de inserción, como el `dict` (`ontologia::objeto`): el orden
  decide sumas y el desempate del estilo de transición.
* La similitud del embedding con cada pista se calcula una vez por sesión y no una vez por bloque: el
  resultado es el mismo y con MiniLM ahorra una inferencia por pista y bloque.
* `serde_json` lee los flotantes con `float_roundtrip` solo en las pruebas, para comparar las doradas bit a bit; el
  binario no cambia.
* Las pistas analizadas por NB Sound antes de este commit no tienen etiquetas de ambiente básicas; las llegaron
  con la importación. Nadie usa aún NB Sound con datos propios, así que no se añade una migración de relleno.
| `7c08cfe` | F6.1.3 (1/2) | La decisión de cada mezcla (`dj/mezcla.rs`): puntos de entrada y salida por pulsos, técnica según fase, tempo, tonalidad, perfil e instrumental, solapamiento y las curvas de volumen y bandas. Las capas hacían aparecer la pista entrante al 40 % y cortaban la saliente al 40 %; aquí ambas entran y salen en rampa. No se porta el cálculo por RMS | Las propiedades de `test_dj_mix_engine.py` que no dependen de VLC; ninguna curva salta salvo el corte |
| `fb63d45` | F6.1.3 (2/2) | El motor pasa a dos platos (fuente, alimentador, diez bandas y volumen cada uno) colgados de la pista maestra, que conserva el ecualizador del usuario y el limitador; la reproducción normal sigue siendo idéntica muestra a muestra. `dj/ejecutor.rs` arma la entrante en silencio, abre la puerta cuando suena (o a los 2,5 s), aplica las curvas con el reloj del audio y, al terminar, cambia de plato. El barrido mueve sus bandas de forma continua, no a saltos de 4 dB, y las rampas de volumen se curvan para que el cruce no deje un hueco: Kira interpola en decibelios | La puerta de `test_dj_transicion_gate.py`; las cinco técnicas renderizadas fuera de línea sin clics, sin picos, sin escalones de 1,5 dB en 50 ms ni de 1 LU en la sonoridad a corto plazo |

**Decisiones de F6.1.3.**

* En las capas, la entrante suena con su instrumental del karaoke y recupera la voz en el último cuarto del
  solapamiento: cargar el instrumental en lugar de la pista y dejarlo sonar hasta el final dejaría toda la canción
  sin voz.
* La pista que entra solo se anuncia (`PistaEmpieza`) cuando la mezcla termina y su plato pasa a ser el activo; el
  plato que no lo es no cuenta ni su comienzo ni su final.

| Commit | Iteración | Qué se hizo | Pruebas nuevas |
|---|---|---|---|
| `02844a5` | F6.1.4 | `dj/equipo.rs`: el perfil (bajo, medio, alto), su clasificación por el factor de tiempo real y la medición en un hilo aparte, una a la vez. Se mide separando diez segundos de audio sintético con el modelo del agregado de karaoke (`karaoke::medir`), por el mismo camino que una pista; sin el agregado, el perfil es bajo y el DJ mezcla sin capas. No se guarda: la migración descarta la medida y NB Sound mide en cada arranque, al abrir el DJ por primera vez | Las propiedades de `test_dj_hardware_profile.py` salvo las de persistencia; una medición no se solapa con otra; la separación de prueba son dos segmentos |
| `1963ea5` | F6.1.5 | La capa del DJ sin audio. `dj/sesiones.rs` lee y escribe sesiones, pistas planificadas (cada una con la transición que la trae), eventos, preferencias y la sesión en curso, con los estados y JSON. `dj/servicio.rs` empieza, continúa, regenera (semilla + 17), descarta, finaliza, guarda como playlist ("DJ Privado: Music Session, Vol. N"), retoma una del historial sin repetir lo planificado y filtra el historial sin distinguir tildes. La narrativa ya estaba en F6.1.2. Sin candidatas no hay error: el resultado lo dice y la sesión queda en `error` | `test_dj_privado_integracion.py` sobre una base en memoria con la biblioteca; preferencias, sesión en curso y borrado en cascada |

**Decisiones de F6.1.5.**

* Toda sesión nueva guarda su semilla, aunque no se dé: retomarla la sigue construyendo igual.
* La sesión en curso se recuerda por la posición de la pista en la sesión, que no cambia, en vez del índice del
  reproductor.
* El reproductor de la sesión (`reproductor_sesion.py`), que decide cuándo mezclar y con qué pista, va con las vistas
  en F6.1.6, integrado en el reproductor único: NB Sound tiene un solo motor y una sola barra.

| Commit | Iteración | Qué se hizo | Pruebas nuevas |
|---|---|---|---|
| `6914ba1` | F6.1.6 (1/2) | La sesión del DJ suena en el reproductor único (`reproductor/dj.rs`), como un modo: la cola del usuario espera en pausa donde estaba, cada pista prepara al empezar la mezcla hacia la siguiente con el perfil del equipo y la fase de la sesión, y al llegar al punto de salida la arma el ejecutor. Saltar apunta la pista como saltada y mezcla ya; pedir otra música deja la sesión; al acabar la última, la sesión queda finalizada y vuelve la cola. La sesión que sonaba vuelve en pausa al abrir (`dj_en_curso`), salvo si se descartó | Una sesión de tres pistas suena entera con sus mezclas; la cola vuelve en pausa y sigue donde estaba; pedir otra música; saltar; volver al abrir y no volver si se descartó |

| `7052890` | F6.1.6 (2/2) | El DJ en su hilo (`dj/director.rs`): atiende las peticiones de una en una y, entre ellas, sigue construyendo la sesión activa y avisa al reproductor y a la vista de cada bloque. Nueve comandos (`dj_pedir`, `dj_sesion`, `dj_reproducir`, `dj_valorar`, `dj_regenerar`, `dj_descartar`, `dj_guardar`, `dj_historial`, `dj_eliminar`) y la vista DJ Privado: pedir con palabras, duración e ideas; la sesión con su resumen, sus cifras, la mezcla en curso y sus canciones con la calidad de cada transición; y el historial con búsqueda. La vista dice cuando no hay análisis musical. Se carga aparte: el arranque sigue en 244,5 KB | Una sesión se completa sola tras el primer bloque y avisa; la vista, comprobada en una captura con el puente simulado |

**Aviso.** Durante esta iteración se llenó el disco de la sesión con 18,7 GB de artefactos de compilación de la propia
caja; `cargo clean -p nb-sound` los quitó sin tocar las dependencias.
| `78aae0f` | F6.2.1 | A ciegas en `a_ciegas/`: los cuatro modos (portada, audio, redescubrir y "nunca la eliges", con su recurso a las menos escuchadas), los indicios sobre el título (alfabeto, primera y última letra, palabras y letras), la comprobación tolerante de lo escrito con los umbrales y el estado de la ronda. La vista solo recibe lo ya revelado: el título no viaja hasta que se revela | `test_explorador_ciego_hints.py`, `_service.py` y `_modelo.py`: universos de cada modo, nada oculto viaja, acierto y fallos, indicios acumulados, pasar y terminar, evitar las ya jugadas, el fragmento |
| (siguiente) | F6.2.2 | El fragmento a ciegas es un modo breve del reproductor (`reproductor/fragmento.rs`): toca unos segundos de la canción del reto con la cola en pausa y publica la instantánea sin la pista (`ciego`), así que ni la barra, ni los controles del sistema, ni el móvil la delatan; al acabar, o al pedir otra cosa, la cola vuelve donde estaba. Seis comandos y la vista: elegir modo y número de retos, el reto con portada o fragmento, los campos que se van revelando, los indicios, escribir el título o "¡La sé!", rendirse, escuchar entera o añadir a la cola, y el resumen. `VistaPendiente` desaparece: los siete destinos ya tienen su vista | El fragmento no deja ver la pista y devuelve la cola; pedir otra música o pausar lo acaban; la vista, comprobada en una captura con el puente simulado |

**Estado al cerrar la Fase 6.** Todas sus iteraciones están hechas. De sus criterios quedan para las pruebas finales los
que necesitan la instalación real: la escucha de las transiciones (el render fuera de línea ya las comprueba). El agregado de karaoke, del que
dependen las capas y la medida del equipo, sigue sin publicar (P13).

## 2026-10-31: Fase 7

| Commit | Iteración | Qué se hizo | Pruebas nuevas |
|---|---|---|---|
| `65b17e2` | F7.2.3 | (Nathan, en local) Tipografías y código portado en los avisos de terceros | — |
| `276424f` | F7.2.2 (a medias) | (Nathan, en local) El actualizador detrás de la puerta de red | Dos en `net.rs` |
| `985d605` | F7.2.2 | Cierre: `cargo test` (548) y `pnpm verify` en verde, avisos regenerados con las dependencias del actualizador, y las enmiendas de ADR-001 (la dependencia) y ADR-009 (la excepción del cliente HTTP propio del plugin y sus límites) | — |
| `d62be50` | F7.2.1 | `publicacion.yml`: al empujar una etiqueta `v*` (o a mano) compila en Ubuntu 22.04 (AppImage, deb y rpm; la glibc más vieja para que el AppImage arranque en más sistemas), Windows (MSI y NSIS) y macOS de Apple Silicon (dmg), con los binarios de `binarios.json` comprobados por SHA-256. Firma con los secretos `TAURI_SIGNING_PRIVATE_KEY*`, sube `latest.json` y deja la publicación en borrador: publicarla sigue siendo decisión de Nathan | No se ha ejecutado: no hay forma de lanzarla desde esta sesión sin crear una etiqueta |
| `cd50bc5` | F7.2.4 | La 2.0.0 queda preparada sin publicar: la versión en los tres manifiestos y `CHANGELOG.md`, que el borrador de la publicación cita. No se crea la etiqueta `v2.0.0`: hacerlo lanzaría la publicación | `pnpm verify` en verde |

**Cierre de la Fase 7.** Lo que falta para publicar está en [pruebas finales](./pruebas-finales.md).

## 2026-10-31: Fase 8

| Commit | Iteración | Qué se hizo | Pruebas nuevas |
|---|---|---|---|
| `44b7f1c` | F8.1 (ficha) | Ficha de la forma de onda en `fase-8-nuevas.md` y tabla de estado de la Fase 8 | — |
| `9369bd0` | F8.1 | La forma de onda sale de la misma decodificación que mide la sonoridad (`audio/sonoridad.rs`), con 1.000 picos de un byte por pista guardados en `sonoridad.picos` (migración V10). Lo medido antes de V10 se vuelve a medir una vez en `medicion.rs`; el silencio queda con picos a cero y los archivos ilegibles con picos vacíos para no reintentarse. `EstadoDj` anuncia desde dónde entró la pista que suena y dónde empezará a irse, y `FormaDeOnda.svelte` dibuja la onda sobre la barra de reproducción y en la sesión activa del DJ | Picos crecientes, hueco de silencio y pistas cortas en `sonoridad.rs`; silencio, ilegible, remedición tras V10 y caducidad en `medicion.rs`; presupuesto de 16 KB con picos en `pruebas_esquema.rs`; puntos de entrada y salida por pista en `reproductor/pruebas.rs` |
| `ebed471` | F8.2 | Ficha de las listas inteligentes vivas y su convergencia con las playlists automáticas (`docs/plan/fase-8-nuevas.md`) | — |
| `547cca5` | F8.2 | Listas inteligentes vivas del usuario (`ReglaInteligente` evaluada en SQLite sobre BPM, energía, ánimo, instrumental listo, favoritas, reproducciones, última escucha, año y género en `playlists/inteligentes.rs`) y regeneración de las playlists automáticas ("Crear para mí": uso, `This is` y ánimo vía `descubrir::candidatos_con_confianza`). Las inteligentes refrescan `playlist_pistas` al listarse o abrirse y solo escriben cuando cambian sus pistas, para no subir `sync_version` en lecturas sin cambios; interfaz en `DialogoInteligente.svelte`, `VistaPlaylists.svelte` y `VistaPlaylistDetalle.svelte` | Evaluación combinada de rasgos, uso e instrumental, actualización viva sin ruido en `sync_version`, edición/borrado y regeneración de automáticas respetando `editada = 1` en `playlists/pruebas.rs` |
| `dce12fe` | F8.3 | Ficha del resumen local de escucha mensual y anual (`docs/plan/fase-8-nuevas.md`) | — |
| `d40e906` | F8.3 | Resumen local de escucha en `perfil.rs` (`resumen_escucha`, `RadarAnimos`, mapa de calor 7×24 en hora local y `tarjeta_svg` / `exportar_tarjeta` de 800×480 con texto escapado en XML), comandos `resumen_escucha` y `exportar_resumen_escucha` con selector nativo de archivo y sección interactiva en `VistaTuMusica.svelte` | Filtrado por `"todo"`, año (`YYYY`) y mes (`YYYY-MM`), radar de ánimos, mapa de calor de 168 celdas y exportación de tarjeta SVG con escape XML en `perfil.rs` |
| `d1d5fad` | F8.4 | Ficha de la copia a dispositivos externos (`docs/plan/fase-8-nuevas.md`, `docs/plan/pruebas-finales.md`) | — |
| `1e530e7` | F8.4 | Copia a dispositivos externos en `copia_dispositivo.rs` (saneado FAT32/exFAT, tres estructuras de carpetas, portada y etiquetas incrustadas en la copia con `lofty` sin modificar los originales, conversión opcional a WAV PCM de 16 bits / 44,1 kHz, omisión incremental y generación de `.m3u8`), comando `copia_dispositivo_ejecutar` con selector nativo de carpeta y bloque en `SeccionDispositivos.svelte` | Saneado FAT32/exFAT, estructuras `ArtistaAlbum` / `Plana`, portada incrustada sobre la copia preservando el original byte a byte, `.m3u8` y omisión incremental en `copia_dispositivo.rs` |
| `c673bb1` | F8.5 (ficha + ADR) | Ficha de F8.5 en `docs/plan/fase-8-nuevas.md` y propuesta de modelo de confianza en `docs/adr/decisions/ADR-012-modo-fiesta.md` (estado `Propuesto`, bloqueada hasta la aprobación de Nathan antes de escribir código) | — |
| `53d0b1d` | F8.5 | Modo fiesta en `fiesta.rs` tras la aprobación de ADR-012 por Nathan: listener HTTP efímero e independiente (`8831..=8899`), token de sesión de 128 bits en `/f/{token}` verificado en tiempo constante, cinco únicas rutas, cuotas por invitado e IP, rotación instantánea del QR, moderación manual o encolado automático al final de la cola, comandos `fiesta_*` y panel `BloqueFiesta.svelte` en Ajustes > Dispositivos. Cierre de la Fase 8 (5/5) | Rechazo sin token (`401`), página e interfaz web, búsqueda, límite de 3 sugerencias pendientes por invitado (`429`), aprobación que encola la pista, bloqueo de invitado/IP (`403`), modo automático y rotación del token en `fiesta.rs` |
| (siguiente) | F5.1.1 / P13 | Publicada la Release `agregados-1` en `Nate-1296/NB-SOUND` con `karaoke-1.zip` (`htdemucs` fp16, 145,7 MB), `analisis-1.zip` (MusiCNN + 7 cabezas, 3,5 MB) y `texto-dj-1.zip` (`all-MiniLM-L6-v2` + `tokenizer.json`, 83,0 MB), y compilados sus URLs, tamaños y SHA-256 en `agregados.rs` | `agregados::tests` |

## 2026-11-01 a 2026-11-03: ronda de observaciones (2.0.1 a 2.0.6)

Hecha con otro asistente a partir de las observaciones de Nathan
([observaciones](./observaciones-2-antes-pruebas-finales.md)).
Sus commits (`2e9e3db` a `c4ba896`) no citan iteración ni van firmados; lo que traían se revisó entero en la entrada
siguiente.

## 2026-11-04: revisión de la ronda de observaciones (QA-R1)

| Commit | Iteración | Qué se hizo | Pruebas nuevas |
|---|---|---|---|
| `e3aeb98` | QA-R1 | Lo que podía perder música: "Limpiar duplicados" adivinaba copias por título y duración y borraba sus archivos (23 grupos de canciones distintas en la biblioteca real); borrar una canción no usaba la papelera ni limpiaba álbum, artista, instrumental y cola. La actualización del `.tar.gz` de Linux no podía funcionar (sin firma en la CI, clave mal decodificada) y abría una carrera para escalar privilegios en `/tmp`. Foto de perfil validada y por huella; "Sorpréndeme" en Rust; el avisador de NB Books; favorita y cola en un solo módulo; logos de 36 MB a 2,6 MB; imports `#lib` de SvelteKit 3 | `catalogo/borrado.rs` (8), `explorador.rs` (2), `sorpresa.rs` (5), foto en `perfil.rs`, firma y URL en `net.rs`, la cola de avisos de NB Books |
| `e9b22a6` | QA-R1 | Un solo cajón lateral (`Cajon.svelte`, un `<dialog>` modal) para las tres consolas de la barra superior; el botón de plegar la barra lateral fuera de las ventanas estrechas; fuera textos, exports y un oyente sin uso | — |
| `f7fd8ad` | QA-R1 | Lo que faltaba: cancelar la importación, duplicar y vaciar playlists, mandarlas a la cola, añadir canciones desde la propia playlist, el álbum a la cola, "Reproducir a continuación", abrir la carpeta de un pendiente de Por revisar, Escape para salir de la reproducción ampliada y el barrido de duplicados observables sobre la biblioteca | Cancelación en `importacion.rs`, duplicar y vaciar en `playlists/pruebas.rs`, barrido en `duplicados.rs`, Escape en `atajos.test.ts` |
| `bd318ea` | QA-R1 | "Añadir a playlist" pedía hasta 500 canciones de cada playlist para saber cuáles ya tenían la canción, y ofrecía las inteligentes, que no admiten añadir: ahora una consulta y solo las manuales. A ciegas enseñaba "registros" inventados (8 aciertos y una racha de 5 fijos): fuera. Avisos de fallo en la foto de perfil, en "Crear para mí" y al añadir a una playlist | `con_pista` en `playlists/pruebas.rs` |
| `bb5f620` | QA-R2 | Primera pasada de interfaz con la aplicación en marcha (datos copiados aparte, nunca los reales). Las filas de canciones llevan número, favorita a la vista y rótulos de columna (`CabeceraPistas`); el menú ··· es un componente (`MenuAcciones`) y las cabeceras de álbum, artista y playlist comparten su fila de acciones (`AccionesColeccion`), con el color de la portada (`ambiente.ts`). El artista separa populares, álbumes y sencillos; Inicio recupera el saludo grande y las cifras, y el destacado del día cambia cada día entre los que tienen portada. Buscar: mejor resultado, rejillas, Escape ya no vuelve atrás dos veces, y las ideas son frases que se entienden. Las fichas del DJ que el motor no entendía ("Mucha energía", "Para viajar") y "reguetón" con la grafía de la RAE. Consola de karaoke con "Cantar ahora" y el repertorio; Dispositivos en tres tarjetas. Aleatorio y repetición activos ya no se confunden con reproducir | Fichas del DJ e ideas de Buscar contra sus motores (`intencion.rs`, `descubrir.rs`), destacado del día (`inicio.rs`) |
| `c4b6040` | QA-R2 | A 1.100 px los extras de la barra de reproducción desbordaban sobre los controles del centro (el micrófono quedaba encima de "repetir"): ahora van a su ancho y, por debajo de 75 rem, se esconden el álbum, el "+" y la barra del volumen. El mejor resultado de Buscar prefiere la canción al álbum que se llama igual. Las fichas del DJ con muchas opciones se metían bajo su rótulo, y la sesión pedida aparecía debajo del formulario: ahora va arriba | — |
| `bd791b4` | QA-R2 | Los grupos en Biblioteca > Álbumes: todos, álbumes o sencillos y EP (`ConsultaAlbumes.sencillos`, opcional para no romper a quien no lo dice). En "Nueva inteligente", mínimo y máximo van por parejas; la sombra de las tarjetas de Inicio era un borrón en los temas claros | Álbumes y sencillos por separado en `biblioteca.rs` |
| `60d1660` | QA-R2 | Playlists por debajo de 70 rem: la regla de dos columnas de `.con-panel` ganaba a la de la ventana estrecha y la rejilla ocupaba media vista; y con el panel escondido, el primer clic en una playlist no hacía nada visible. Ahora la abre | — |
| `85e4773` | QA-R2 | La carpeta de tu música se puede cambiar desde Ajustes (`catalogo/carpeta.rs`): se dice cuántas canciones hay ya en la elegida; si están, solo se apunta, y si no, NB Sound las lleva a su misma ruta con avance y, si algo falla, todo vuelve a su sitio. La vigilancia pasa a la carpeta nueva sin reiniciar. El nombre se cambia tocándolo en Tu música, y la foto se ve en Ajustes. El DJ explicaba el pedido con las frases internas ("Voy a priorizar: club party. Curva: pico de energia"): ahora fichas en español (`intencion::lectura` y el diccionario de conceptos) | `catalogo/carpeta.rs` (3), lectura y nombres de los conceptos en `intencion.rs` (2) |
| `748b81a` | QA-R2 | El historial solo apuntaba las canciones que sonaban hasta el final, y nada de lo que sonaba en una sesión del DJ: pasar de canción a los tres minutos o escuchar una sesión entera no dejaba rastro en Tu música ni en los tops. Ahora cuenta lo escuchado 30 s o más (la mitad en las de menos de un minuto), con `completada` diciendo si sonó entera, y las canciones de una sesión al mezclarse, al acabar o al dejarla | Escucha parcial en `reproductor/pruebas.rs`; la sesión del DJ apunta sus tres canciones |
| `fa0814c` | QA-R2 | La primera pantalla de una instalación nueva decía "Tu biblioteca empieza al importar música" sin ningún botón: ahora es una bienvenida con el nombre y tres caminos (elegir la carpeta de la música, que se importa y se vigila; añadir canciones; restaurar una copia de otro equipo). Biblioteca, Playlists y A ciegas vacías se quedaban en blanco: `EstadoVacio` dice qué pasa y ofrece "Añadir música". La sesión del DJ con su mosaico, reproducir/pausar grande, valorar con iconos, descartar en el menú y las canciones con su portada y la transición en la misma fila | — |
| `a98d265` | QA-R2 | Las playlists ancladas, en la barra lateral (`PlaylistsAncladas`): anclar solo ordenaba la vista de Playlists. Por revisar: un icono por clase de motivo en vez de "No importado" en rojo en cada fila, "Tu archivo" con sus campos o "no trae etiquetas" en vez de tres "Sin datos", el tipo del candidato en español y el botón de la carpeta con el icono al lado. Acerca de con el logo y la versión; "color por portada" dice que ya tiñe álbumes, artistas y playlists | — |
| `77178b3` | QA-R2 | En Buscar, pulsar una canción hacía sonar otra: la lista va por relevancia (el `rank` de FTS5) y la cola se armaba por título, así que el índice pulsado apuntaba a otra canción. Las dos usan ahora el mismo `ORDER BY` (`orden_de`) | La cola por relevancia sigue el orden de la lista, en `biblioteca.rs` |
| `16043b3` | QA-R2 | El resumen de A ciegas lista las canciones de la ronda con su resultado y un botón para escucharlas (antes, solo "0 acertadas · 5 reveladas"); los plurales de A ciegas, del DJ y de los duplicados ("1 pasadas"); el año del reto separado de su título. En la reproducción ampliada, una ficha dice que el karaoke está activo | — |
| `411690f` | QA-R2 | Las huellas de contenido (`pistas.sha256`, la `x-nb-sound-hash` del móvil) guardadas no eran las de sus archivos: se habían calculado antes de escribir las etiquetas, y solo coincidían 2 de cada 300. Por eso un archivo que ya estaba en la biblioteca llegaba a Por revisar como si fuera nuevo y el teléfono marcaba cada descarga como "sin verificar". La auditoría las corrige una vez, y pasa a la huella nueva la medición, el análisis y los instrumentales hechos con la vieja (el audio no cambió). La tarjeta de importación separaba mal el archivo que procesa | Huellas viejas corregidas una vez, arrastrando sus mediciones, en `auditoria.rs` |
| `aa24942` | QA-R2 | "Buscar de nuevo" en Por revisar volvía a apuntar el archivo con el nombre con que se guarda dentro (su huella, "a0666ccf….mp3") en vez del nombre con que llegó | Buscar de nuevo conserva el nombre, en `canalizacion.rs` |
| `6f693b0` | QA-R2 | Lo de la revisión de Nathan del 2026-11-05, primera tanda. Nunca reiniciar: las vistas abiertas se refrescan solas cuando cambia la biblioteca (`cambios.svelte.ts`, desde el propio puente), y la lista de pistas lo hace sin perder dónde estaba. Recordarlo todo: la vista de cada pestaña, sus órdenes y filtros, la playlist elegida y la pantalla en la que se estaba vuelven al abrir; y abrir y cerrar sin pulsar reproducir ya no pierde el segundo de la canción. La barra de reproducción deja a la pista todo su ancho: la favorita, "+", el minirreproductor y dónde suena pasan al menú ···, con Sorpréndeme. La barra lateral pierde las ancladas y su raya del pie queda a la altura de la de la barra de reproducción | Abrir y cerrar sin tocar nada conserva el segundo, en `reproductor/pruebas.rs` |

| `f1daf09` | QA-R2 | Inicio sin cifras ni subtítulo: el saludo, a la mitad, comparte fila con Sorpréndeme; el podio del top 10 tiene pedestales y el cuarto puesto una tarjeta propia. Biblioteca > Pistas, Buscar y las canciones de un artista vuelven a la lista sin cabecera ni números; la numeración queda en álbumes y playlists | — |
| `d821056` | QA-R2 | Segunda tanda de la revisión de Nathan. Playlists: sin "Pistas x" en el panel y las ancladas con su distintivo. Buscar: un solo marco en la caja con el foco, sin "Ctrl+K" a la vista, el mejor resultado por parecido (exacto, empieza así, una palabra empieza así) y las canciones cuyo título empieza así antes que las que solo lo dicen en la letra. Pantalla completa sin franja vacía, sin que la letra que avanza cuente como ratón, y el icono de salir dentro de su lienzo. La cola con carril para la barra. Ajustes: tamaño en botones que no se van de la vista y sin agregados aún no publicados. DJ: el historial a toda altura con un adorno que se encoge al llenarse. A ciegas grande, con la portada a la izquierda. La consola de karaoke dice qué canción se prepara y cuáles esperan. El minirreproductor rehecho y que se esconde en vez de cerrarse. Tu música: un mes elegido se ve como calendario. Las vistas recuerdan su última respuesta y se pintan al instante al volver; las rejillas no pintan lo que no se ve | Escalones de título en la relevancia (`biblioteca.rs`, `db/busqueda.rs`) y días del mes en el resumen (`perfil.rs`) |
| `2271af0` | QA-R2 | Tercera tanda de la revisión de Nathan. El karaoke no preparaba una canción cuyo audio mide un número exacto de trozos del remuestreador ("Cooler Than Me", 48 kHz): fallaba con INTERNAL, salía de la cola y parecía lista; ahora se prepara, y la consola cuenta las que fallaron. La cola solo pinta las filas a la vista: con la biblioteca entera (2.243) abrirla congelaba la aplicación. Las barras de desplazamiento las dibuja la página: las nativas de WebKitGTK quedaban encima de cajones, menús y la cola; la de la letra no se ve. El menú ··· enseña dónde suena en su sitio en vez de abrir la consola de dispositivos (que, con la letra abierta, dejaba la aplicación bloqueada). La barra de reproducción ya no cambia de forma: el botón de karaoke está siempre y la cuenta de la cola tiene ancho fijo. Tu música: un año o todo el historial se ve mes a mes y el calendario del mes tiene siempre seis semanas. Biblioteca sin "Preparar mis favoritas" | Remuestreo con trozos justos (`karaoke.rs`) y meses del resumen (`perfil.rs`) |
| `54ab526` | QA-R2 | La aplicación se repara sola. El karaoke vuelve a intentar un fallo pasajero hasta tres veces y, al arrancar, lo que falló por no tener el modelo; la importación reintenta un archivo hasta tres veces antes de contarlo como error. Al estrenar una versión, todo lo que había quedado fallido (karaoke y lo que llegó a Por revisar por un fallo al escribir) se intenta otra vez solo, una vez | Una versión se estrena una sola vez, solo vuelve lo que falló al escribir y las fallidas vuelven desde cero (`autorreparacion.rs`) |
| `9ebcaac` | QA-R2 | Probando la 2.0.7 instalada (no la de desarrollo): el karaoke arranca antes de que se fije dónde está ONNX Runtime y, con trabajo pendiente, pedía el entorno primero; el fallo quedaba guardado y en toda la sesión ni el karaoke ni el análisis podían usar modelos (todo lo pendiente fallaba en un segundo). El entorno ya no guarda el fallo, el karaoke espera a la ruta y un componente ausente para la cola en vez de quemar sus intentos. Y la instalada abre en `tauri://localhost`, con la ruta vacía: no volvía a la pantalla guardada, guardaba una vacía e Inicio no se marcaba | Sin componente la cola se para y vuelve al despertar (`karaoke.rs`); la raíz con ruta vacía (`navegacion.test.ts`) |
| `b2d2915` | QA-R2 | Medido por hilo en la 2.0.8 instalada: la ventana al 7 % y el audio bien, pero el karaoke con cuatro núcleos al 97 % de ocho y a prioridad normal, compitiendo con la interfaz. Ahora el karaoke usa un cuarto de los núcleos y el análisis un octavo, y ONNX Runtime ya no deja sus hilos girando en vacío: dos núcleos en vez de cuatro | Al menos un hilo y nunca la mayor parte del equipo (`onnx.rs`) |
| `0edb70e` | QA-R2 | Con la aprobación de Nathan entra `libc` (enmienda de ADR-002): el karaoke, el análisis y la sonoridad bajan su hilo a prioridad 19 en Linux (clase `UTILITY` en macOS) y los hilos de ONNX Runtime la heredan; medido, los dos del karaoke a 19 y la ventana y el audio a 0. Solo usan lo que el equipo no está usando | El hilo de fondo y los que crea quedan a 19 y el resto no cambia (`prioridad.rs`) |
| `02ad88d` | QA-R2 | Revisión de producto punto por punto sobre la 2.0.9, comparada con Spotify, Apple Music, Plexamp, MusicBee, foobar2000 y Symfonium: lo que ya está a la altura, lo que falta (A1–A8, M1–M7, B1–B5) y en qué orden. Al día el documento de la aplicación, la Fase 7 (publicada de la 2.0.0 a la 2.0.9 sin la puerta de máquina limpia), las pruebas finales (cuatro cerradas por guion; tres desfasadas, corregidas) y las preguntas P15–P17 | — |
| `99e3ca7` | QA-R2 | Los cajones de Karaoke, Dispositivos y Añadir música aparecían en mitad de la ventana y saltaban a la derecha. Solo con la GPU (como los abre Nathan): WebKitGTK pinta mal la animación de `transform` de un hijo del `<dialog>` modal. Reproducido en su escritorio con la 2.0.9 instalada, la animación ralentizada a 3 s y capturas; el panel entra ahora animando su borde derecho, comprobado igual antes de tocar el código | — (se ve solo con la GPU; anotado en pruebas finales) |
| `52c046c`…`28df860` | QA-R2 | Teléfono: "Conectado ahora" ya no se queda fijo al cerrar la app del móvil (margen de 40 s y la lista se vuelve a pedir mientras haya alguno conectado). Permisos de red: `cortafuegos.rs` comprueba si el cortafuegos del sistema (`ufw`, firewalld, el de Windows o el de macOS) deja pasar al teléfono y al Modo fiesta, y lo pide con la ventana de administrador del sistema; Ajustes > Permisos lo mide mientras está a la vista, Dispositivos avisa con un botón para pedirlo de nuevo y, al abrir, se avisa si el teléfono está bloqueado. Además, NB Sound sin la versión anterior: fuera el importador, sus rutas y sus pruebas, y la documentación, los comentarios y los nombres sin ella | Un perfil de `ufw` que abre el teléfono y no la fiesta, rangos unidos, guion y codificación de PowerShell (`cortafuegos.rs`); el teléfono que dejó de hablar (`movil/repositorio.rs`); la clave privada sin lectura ajena (`identidad_movil.rs`) |
| `5ccc4e6` | QA-R2 | La 2.0.11 publicada con los 16 artefactos; el `.tar.gz` firmado se instala en el equipo de Nathan. Probada instalada sobre la copia de los datos: Acerca de dice 2.0.11, Ajustes > Permisos muestra el teléfono y la fiesta permitidos con `ufw`, y con el Modo fiesta encendido su página responde por la red local | CI y publicación en verde; firma comprobada |

## 2026-11-06: tercera revisión (QA-R3)

Lo que pidió Nathan: Por revisar más sencilla, que la música se encuentre sola si cambia de sitio, `~/Música` limpia
de lo que no usa NB Sound y las barras sin pisarse a ningún tamaño. Después, la prueba de punta a punta.

| Commit | Iteración | Qué se hizo | Pruebas nuevas |
|---|---|---|---|
| — | QA-R3 | `~/Música` queda en `biblioteca/`, `copia_seguridad/` y `revision/`. Los 112 MP3 de revisión y cuarentena, sueltos en `revision/` (sin pisar nombres repetidos); a la papelera las carpetas de la versión anterior (`assets`, `cache`, `procesados`, `manifests`, `logs`, `modelos_essentia`, `entrada`, `tmp`), su base suelta en la biblioteca y su copia de seguridad, que esta versión rechaza. Fuera también 11 carpetas de álbum vacías | — |
| `f752fe1` | QA-R3 | Las barras deciden por su propio ancho (`anchos.ts`): la de reproducción en tres tramos, con lo que no cabe en una fila del menú ···; la superior con nombres solo si la búsqueda tiene sitio, y siempre separada de sus botones | Umbrales de la barra (`anchos.test.ts`) |
| `3f0edaf` | QA-R3 | Dónde vive tu música (`catalogo/ubicacion.rs`): al arrancar se comprueba una muestra y, si la carpeta ya no la tiene, se busca bajo la carpeta personal de ahora y en la de música del sistema; si no aparece, se pregunta. Ajustes con Comprobar y Cambiar. Las copias automáticas: la frecuencia guardada como `1.0` se leía como "nunca" (la base real llevaba días sin copias), se guardan las tres últimas, las portadas no se recomprimen y se comprueba cada seis horas. Borrar una canción poda su carpeta vacía | Otro usuario, una copia de Windows, una carpeta que solo coincide en el nombre, la que sigue en su sitio y la de copias (`ubicacion.rs`); frecuencia decimal y poda de copias (`copia_seguridad.rs`); poda de carpetas (`carpeta.rs`) |
| `43f6e67` | QA-R3 | Por revisar rediseñada: grupos por decisión, la canción con su portada (`portada://localhost/pendiente/{id}`), una acción a la vista, candidatas ordenadas por parecido y acciones por grupo. Probándola con los 112 archivos reales: lo descartado llega a la papelera con su nombre, la tarjeta de importación dice el nombre real y una copia de algo que ya esperaba no le roba el motivo ni se recataloga en cada arranque | Nombre en la papelera (`por_revisar.rs`); copia de un pendiente (`canalizacion.rs`) |
| `ad5e551` | QA-R3 | La 2.0.12 publicada | CI y publicación en verde |
| `ae149b4` | QA-R3 | Soltar la barra de progreso en su extremo dejaba la pista "ilegible" y el reproductor en "0:00" sin pasar a la siguiente (Symphonia rechaza buscar en el final de un MP3) | Barra al final (`reproductor/pruebas.rs`) y MP3 real con `NS_MP3` (`audio/pruebas.rs`) |
| `1c8e68d` | QA-R3 | Inteligentes con rangos que no se podían crear, "0 listas hechas", la ficha encendida con "sin reguetón", Buscar en blanco con un texto largo, el bloque de copiar a USB sin flecha y el resumen de importación que no se iba | — |
| `ff4f278` | QA-R3 | La foto de perfil viaja en la copia de seguridad | Foto que vuelve al restaurar (`copia_seguridad.rs`) |
| `e8faf94` | QA-R3 | En una instalación nueva Biblioteca acababa en "500": el efecto de la rejilla se disparaba a sí mismo con la lista vacía. "Dónde vive tu música" sin carpeta ofrece "Elegir" | — (comprobado con datos vacíos en la aplicación) |
| `2ddf260` | QA-R3 | Mover la barra en pausa no movía la posición hasta reanudar | La posición en pausa (`reproductor/pruebas.rs`) |
| `342884c` | QA-R3 | Un número de pista negativo decía "No se pudo guardar" | — |
| `2fd7742` | QA-R3 | Un lote de Por revisar cuenta por dónde va y quita cada canción al entrar (88 tardaron dos minutos sin que la vista cambiara) | — |
| `688ff6b` | QA-R3 | La 2.0.13 | CI y publicación |
| `e1e976d` | QA-R3 | Un solo aviso al encontrar la música desde la pregunta del arranque | — |
| — | QA-R3 | La 2.0.13 publicada e instalada. Prueba con los datos reales de Nathan: copia automática hecha por la 2.0.13 (3,4 GB, 23 s, con la foto), desinstalación, datos apartados como en un equipo nuevo, reinstalación (abre en la bienvenida), restauración de la copia y arranque: 2.243 canciones, 1.426 álbumes, 438 artistas, 56 playlists con las mismas canciones cada una y 35 favoritas, idénticos a antes; tema, nombre, foto, sesión y carpeta de la música en su sitio, y suena. El agregado de análisis se instala con un clic. Después se devolvieron los instrumentales del karaoke, los agregados y la identidad del teléfono, que la copia no lleva | Recuentos de la base y lista de archivos de la biblioteca comparados antes y después |


## 2026-11-08 y 2026-11-09: pruebas finales hechas por IA (QA-IA)

Decisión de Nathan: las pruebas finales son solo las que puede hacer una IA, sin Windows, macOS ni máquina limpia
(la Constitución pasa a comprobar la regla 1 en la CI de Linux). DeepSeek V4.1 Flash, orquestado desde Claude,
hizo las Fases 2 a 4; Claude, el resto. Todo sobre la aplicación compilada y una copia de los datos.

| Commit | Iteración | Qué se hizo | Pruebas nuevas |
|---|---|---|---|
| `0e82231`…`674bda2` | QA-IA | Arnés de audio e interfaz; Fase 2 entera. La ventana nacía con dos fotogramas del tema de fábrica | Arranque sin tema de fábrica |
| `4a50297`, `2b6f33c` | QA-IA | La ventana oculta hasta tener la apariencia, con red de seguridad en Rust a los 4 s | Fallo de JS inducido |
| `12ffda8`…`c8bfc55` | QA-IA | Fase 3 con un cliente que habla el contrato móvil | — |
| `0f721b5` | QA-IA | Matar NB Sound a mitad de un lote dejaba falsos duplicados; el vigilante tomaba lo recién importado por nuevo; Completar datos no tenía la clave de AcoustID | Una por defecto |
| `1c3065c`, `5a47d3e` | QA-IA | Fase 4, con AcoustID y MusicBrainz reales | — |
| `07bc09d` | P8 | El karaoke llegaba a 6,7 GB; sin optimizar el grafo, 1,4 GB y el mismo instrumental | Pico por debajo de 3 GB con el modelo real |
| `bc7f946` | QA-IA | Fase 5: agregados reanudados tras cerrar a mitad, karaoke con los ocho núcleos ocupados | — |
| `33feeb3` | — | RUSTSEC-2026-0459 ignorado hasta que `r2d2_sqlite` admita rusqlite 0.41 | — |
| `7df2f12` | QA-IA | Lo importado en una instalación nueva no sonaba hasta reiniciar; salir del DJ adelantaba la cola | Una por defecto |
| `8b26f9e` | QA-IA | El DJ tardaba 73 s en sonar (ahora menos de 2: vectores guardados); mezclas de igual potencia; A ciegas perdona una letra en títulos cortos | Memoria de vectores, igual potencia, una letra |
| `30a82ce` | QA-IA | Copia automática diferida y con prioridad de disco ociosa: causa probable del audio entrecortado de la primera apertura | Arranque cargado |
| `f6755ac` | A9 | Completar en segundo plano lo que le falta a la biblioteca (V11) | Qué se vuelve a intentar |
| `4e2e43f` | QA-IA | Las claves de AcoustID y TheAudioDB se ponen en Ajustes > Privacidad | Cuentas del llavero |
| `d8d172d` | QA-IA | Arneses de las Fases 6 y 8 y del arranque cargado | — |
| `59d535e` | QA-IA | TheAudioDB con su clave pública; en Ajustes solo la de AcoustID | Clave pública por defecto |
| `2b3ab1d`, `3f97e3a` | QA-IA | Las 19 casillas de QA-R1 a QA-R3 por guion (puntero real con xdotool; lo del selector nativo, por su función) | — |
| `f9b53a8` | QA-IA | Por revisar centrada, con cabecera, resumen por grupo y tarjetas | Diseño medido en la app |
| `364f540` | — | La 2.0.14 publicada | CI y publicación |
| — | P20 | El motor gastaba el 4,3 % de un núcleo por las 30 campanas de Kira siempre activas; un banco que se las salta en plano lo deja en el 0,5 % | Coste del motor en `--release` y banco plano bit a bit |
| — | P16 | `windows-sys`: el trabajo de fondo con prioridad baja también en Windows | — |
| — | P6 | Agregado de aceleración para Linux con NVIDIA (2 GB), publicado en `agregados-1` sin probar en una NVIDIA | — |
| — | — | Decisiones de Nathan: P10, P15, P19 cerradas; F4.1.2 hecha; P3 y P7 pendientes de su respuesta | — |

## 2026-11-10: cierre de P7 en el teléfono real

| Commit | Iteración | Qué se hizo | Pruebas nuevas |
|---|---|---|---|
| (este) | P7 / F3.1.6 | Comprobada por depuración inalámbrica (ADB) en el TCL 50 Pro NXTPAPER (`T803E`) con NB Sound Mobile 0.1.2 la sincronización, verificación de `x-nb-sound-hash` y reproducción continua de pistas FLAC (`audio/flac`, 48 kHz / 16 bits) y M4A (`audio/mp4`, AAC-LC 192 kbps) servidas por `GET /api/v1/track/{id}/audio` desde la copia aislada; limpiadas las pistas de prueba del teléfono mediante tumbas al terminar | — |

## 2026-11-11: cierre de P3 y comprobación de la Release

| Commit | Iteración | Qué se hizo | Pruebas nuevas |
|---|---|---|---|
| (este) | P3 / ADR-010 | Nathan decide mantener GPL-3.0-or-later, `songrec` y los modelos actuales, sin edición institucional en esta etapa. Enmendado ADR-010 y cerrado P3 en preguntas abiertas y pruebas finales; actualizada la revisión de producto | — (cambio documental) |

La última Release publicada es [v2.0.15](https://github.com/Nate-1296/NB-SOUND/releases/tag/v2.0.15),
desde `6be0346`: incluye el ahorro del motor (`2306f92`), la prioridad de fondo en Windows (`02eb339`) y
la aceleración NVIDIA en Linux (`a2ac370`). Desde esa etiqueta solo hay cambios documentales, por lo que no
se necesita otra versión de los instaladores para este cierre. La aceleración sigue sin probar en una NVIDIA real.

La [CI de la versión](https://github.com/Nate-1296/NB-SOUND/actions/runs/42727857378) y la
[publicación de sus instaladores](https://github.com/Nate-1296/NB-SOUND/actions/runs/42731625431)
terminaron correctamente. La Release contiene los instaladores de Linux, Windows y macOS, las firmas del
actualizador y `latest.json`.

La CI del cierre de P3 se atascó dos veces al instalar las dependencias de Linux: los runners de
`ubuntu-latest` (Ubuntu 26.04) registraron fallos DNS hacia los repositorios de Ubuntu antes de ejecutar las
comprobaciones. Se cancelaron ambos intentos y se fijó Ubuntu 22.04 en los trabajos `verify` y `runtime`,
la misma base que usa el flujo de publicación, para mantener coherentes los entornos de validación y empaquetado.
No cambia el código ni los instaladores publicados. La verificación local pasó: `pnpm verify`, formato,
Clippy con todas las características y pruebas de Rust con todas las características.


## 2026-11-11: primer ajuste compartido con NB Launcher (F9.1.1)

Nathan aprobó ADR-013 y la integración de frecuencia de respaldo. Se implementó el
propietario transaccional, V12 y las notificaciones del ajuste abierto. La frecuencia y sus
reglas siguen en Sound. Los comandos nativos y el enlace de desarrollo comparten autoridad;
el reproductor, la ejecución de copias y el contrato móvil mantienen su responsabilidad.

Las bibliotecas Apache se incorporaron como exportación sellada dentro del clon, con
verificador integrado en guardianes y rustfmt propio. Se regeneraron bindings y avisos.
No se depende de la carpeta de Launcher para compilar Sound. La migración conserva un
respaldo V11; el binario anterior rechaza V12 y no hay downgrade directo.

Verificación Linux: `pnpm verify`, fmt, Clippy de todos los targets/features y `cargo test`
correctos (645 pruebas Rust, 24 omitidas; 38 frontend). El contrato móvil pasó. La prueba
entre procesos y ventana en KWin virtual confirmó cambios bidireccionales, conflictos,
respuesta perdida reconciliada, persistencia y autonomía al cerrar el enlace. Todo con
datos temporales; también pasó restaurar un ZIP V11 y migrarlo.

Nathan autorizó publicar la release correspondiente el 2026-11-11. Se prepara 2.1.0 por la nueva capacidad opcional y se registra su resultado al terminar. Pendientes: registro y encaminamiento general
del hub, consentimiento de producto y ejecución nativa Windows/macOS. El estado está en
[fase 9](./fase-9-integracion-suite.md).

### Distribución 2.1.1

El candidato 2.1.0 no se publicó: CI detectó dependencias locales sin versión explícita y
metadatos incompatibles de zbus restaurados del cache (E0463). Se fijaron las versiones
locales, sin relajar cargo-deny, y se renovó el prefijo de cache. La comprobación limpia
de zbus 5/6 con Rust oficial 1.98 pasó; no se cambió el stack ni se parchearon dependencias.
La release definitiva se prepara como 2.1.1 para conservar inmutables las etiquetas creadas.

### Publicación y validación final de 2.1.1

Publicada [2.1.1](https://github.com/Nate-1296/NB-SOUND/releases/tag/v2.1.1), con CI de
aplicación y generación de instaladores correctas en las tres plataformas. Se comprobaron
los nueve destinos del manifiesto, la correspondencia de artefactos y las firmas. El tar.gz
Linux se verificó con la clave pública de Sound y su ejecutable distribuido pasó el
recorrido de frecuencia, conflicto, entrada inválida, persistencia y cierre del enlace.

Launcher ya dispone de registro privado, permisos por recurso, consentimiento y una UI
nativa que refleja cambios bidireccionales en Linux. Books sigue independiente y no se
modificó. La ejecución de ese recorrido de Launcher en Windows/macOS sigue pendiente.

Se cerraron los procesos y entornos de QA y se retiraron las compilaciones temporales de
Sound creadas durante el trabajo. Sound y Books conservan sus datos e instalaciones.
Esta actualización documental posterior a la publicación no cambia el ejecutable 2.1.1.

### 2026-11-12: continuación del catálogo y estabilización del ensayo de cola

Catálogo editorial de Sound 2.1.3 consumido desde Launcher en Linux, con consulta explícita,
persistencia y reinicio comprobados. Se corrige la sincronización del ensayo de cola
fuera de línea que falló en macOS; se mantienen historial y transiciones visibles.
`pnpm verify`, formato, Clippy y la suite Rust pasaron localmente. La corrección solo toca
pruebas y documentación; los paquetes publicados 2.1.3 permanecen inmutables.
Evidencia y límites en [validación](../engineering/validacion-launcher-2.1.3.md).

### 2026-11-13: pausa y limpieza del checkout de integración

Nathan pidió guardar el estado y retirar los resultados generados. El código ya estaba
limpio y subido. Se eliminaron compilaciones Rust, dependencias frontend, salidas Svelte/Tauri
y binarios descargados reproducibles: el checkout pasó de unos 13 GB a 66 MiB.
Fuentes, lockfiles, vendor sellado e historial permanecen. No se modificaron datos ni
instalaciones personales. Documentación, sello compartido y formato Rust comprobaron
correctamente después de limpiar. [Continuidad y próximos pasos](./continuidad-launcher.md).


### 2026-11-13: autorización persistente y candidato 2.1.4

Se reanuda por instrucción de Nathan. ADR-017 añade el registro independiente de
biblioteca, concesiones transaccionales, generación de revocación, instancia única
y descubrimiento Linux. El primer permiso persistente bloquea el enlace heredado.
Launcher conserva su identidad en el llavero; Sound conserva dominio y consentimiento.

Pasaron `pnpm verify` con un worker (38 pruebas, guardianes y búsqueda aislada),
formato, Clippy completo y 667 pruebas Rust (25 omitidas). Arranque: 249,8 KB de 250.
El recorrido real de las dos ventanas pasó rechazo, permiso recordado, cambios en
ambos sentidos, reinicios, revocación persistente, permiso nuevo, cancelación, segunda
apertura y arranque desde Launcher. Las claves QA propias se retiraron del llavero.
Se prepara 2.1.4; CI, artefactos firmados, publicación e instalación siguen pendientes.
No se atribuye el nuevo protocolo a la release 2.1.3 ni a Windows/macOS.

La CI inicial de 2.1.4 detectó código exclusivo de Linux no delimitado en Clippy
de macOS/Windows. Se corrige con condiciones de plataforma, sin silenciar warnings.
El bloqueo nuevo de instancia se limita también a Linux para no introducir una
segunda apertura sin activación en otras plataformas. Se añaden dos regresiones
para CI nativa. El frontend público pasó; no se creó etiqueta ni release fallida.


### 2026-11-13: publicación, instalación y cierre de 2.1.4

`fbaede2` pasó la CI `43518196348` completa con Rust 1.98; la etiqueta `v2.1.4`
generó instaladores nativos correctos en `43518959506`. Se comprobaron siete firmas
y el recorrido completo con los paquetes Linux antes de publicar. Catálogo editorial
`43523206333` verificado por el `nbctl` instalado, con oferta 2.1.4 persistida.
La renovación de adhesión también pasó más de 960 segundos sin sondeo web.
Los archivos instalados son idénticos al tar firmado; ambas apps quedaron abiertas.

Se retiraron cinco identidades QA propias y los perfiles/procesos temporales. El
checkout quedó en unos 67 MB tras retirar generados sin uso, conservando código e
historial. Datos personales intactos. El cierre y los límites están en
[validación 2.1.4](../engineering/validacion-launcher-2.1.4.md). La distribución firmada
de Launcher continúa pendiente por el bloqueo de Actions de su repositorio privado.
