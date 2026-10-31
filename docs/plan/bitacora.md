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
| `4993346` | F4.2.7 | Ajustes > Privacidad (interruptor general y por servicio, con lo que envía) e Inteligencia artificial (proveedor, modelo y clave en el llavero, que nunca vuelve al webview). La política se aplica a la puerta en el acto | La política guardada y aplicada; validación del modelo; cuentas del llavero iguales a las del importador de la V1 |
| `f624727` | F4.1.7 | `catalogo/ia.rs`: desempate por IA con el prompt y la validación de `external/ia_client.py`; un lanzamiento fuera de la lista cerrada descarta la respuesta | Lista cerrada, revisión manual, confianza acotada, forma de la petición de cada proveedor, la clave fuera del `Debug` |
| `caac72c` | F4.2.8 | "Completar datos" sin cambiar el `id`. La identificación de la canalización pasa a `identificar_y_decidir`, compartida | La letra añadida sin cambiar el `id`; la fila rehecha y los vacíos borrados |
| `e8dec4f` | F4.2.7 | Los textos de lo que se carga aparte salen del arranque (`es-aparte.ts`): de 248,1 a 246 KB | `check-paquete` |
| `f33c072` | F4.2.5 | Editar pista y álbum sin cambiar `id`; renombrar un álbum conserva su fila y su portada, y solo se junta con otro igual del mismo artista | Renombrar, juntar, cambiar de artista, editar una pista, rechazos |
| `683edb4` | F4.2.5 | Las correcciones (`overrides` de la V1): lo editado se recuerda por huella e ISRC y la importación lo aplica antes de ir a la red, también lo que trajo la V1 | Claves de la V1, orden huella > ISRC > artista y título, importación de punta a punta sin red |
| `02d169a` | F4.2.6 | Copia de seguridad `.nbsound-backup` con el formato de la V1 más la versión de esquema; restaurar valida entera y se aplica al reiniciar; copias automáticas. Entra `zip` (ADR-002) | Ida y vuelta completa; rechazo de una copia de la V1, una más nueva, una dañada y una con ruta trampa |
| `d35ce3b` | F4.1.12 | `rasgos.rs`: el modo `light` de la V1, con el seguidor de pulsos de librosa 0.11 leído en su código y la tonalidad con perfiles de Krumhansl, en el hilo de la sonoridad | Tempo exacto en la rejilla, pulsos cada periodo, tono puro, acordes mayor y menor, preferencias |
| `cba2eef` | Fase 4 | Cierre de lo automático y lo real apuntado en pruebas finales | `check-docs` |
| `6b01e24` | F5.1.1 | P13 registrada: los agregados no están publicados | `check-docs` |

**Decisiones tomadas por el camino.**

* La carpeta vigilada no vigila por su cuenta la carpeta de música del sistema: importaría sin preguntar toda la
  música que ya hubiera en ella.
* "Completar datos" y "Editar datos" ponen las etiquetas en el archivo pero no lo mueven.
* Editar a mano no marca una pista como verificada.
* Restaurar una copia nunca cambia la base con la aplicación abierta.
* Las filas de rasgos que trajo la V1 se respetan; solo se analiza lo que no tiene.
* El recorte de pulsos de librosa 0.11, que quita de más en los extremos, se replica porque es lo que contaba la
  V1.

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
| `cb35203` | F5.2.1 | `karaoke.rs` (separación por segmentos de la V1 con `ort`, cola en segundo plano, instrumental en WAV) y `onnx.rs` (carga el ONNX Runtime que viaja dentro). Entra `ort` (ADR-002). P14 registrada sobre el formato del instrumental | Todo voz da silencio, sin voz da la mezcla, cancelación y forma, WAV leído por el reproductor, la cola, ONNX Runtime cargado de verdad |
| `306aee3` | F5.2.2, F5.1.4 | El micrófono prepara mientras suena y ofrece el agregado; el instrumental listo entra en la pista que suena sin desfase. Defecto evitado: pasar el frame por segundos perdía uno por redondeo, de ahí `buscar_frame`. La fila del contrato del reproductor que pedía desactivar el micrófono se rediseña según ADR-007 | El instrumental a mitad de pista en su frame exacto |
| `4fb295f` | F5.2.3, F5.2.4 | Filtro "Listas para cantar" y "Preparar mis favoritas"; F5.2.4 ya lo cumplía el importador de la V1 | El filtro solo da las que tienen instrumental; favoritas en cola sin repetir |
| `9a91d52` | F5.3.1, F5.3.2 | `analisis.rs`: MusiCNN y sus cabezas con la cadena de F0.4.3, en segundo plano y reanudable. Defecto de la V1 corregido: valencia y activación de DEAM se recortaban a 1. Atribución de los modelos en Acerca de y en los avisos de terceros | Clase positiva de cada cabeza y escala de DEAM, parches de Essentia, lotes de 8, remuestreo lineal, filas de la V1 que caducan |
| `a1cb5cc` | F5.3.3 | `descubrir.rs` y sus secciones en Buscar. Para dar margen al arranque (249,4 KB), Reproducción y Apariencia de Ajustes pasan a `SeccionesEscucha.svelte`, que se carga aparte: 244,3 KB | La frase como en la V1, orden y sin repetir, sin intención no hay nada, la activación de la V1 no cuenta |

**Estado al cerrar la sesión.** Todas las iteraciones de la Fase 5 tienen sus pruebas automáticas en verde salvo lo
que depende de publicar los agregados: F5.1.1 (las URL, tamaños y SHA-256 del catálogo) y el agregado de
aceleración de F5.1.5 esperan a P13, y su tamaño a P6. Lo que solo se comprueba con los modelos reales (separación,
paridad del análisis, vacíos de buffer, memoria) está en [pruebas finales](./pruebas-finales.md).

**Decisiones tomadas por el camino.**

* El instrumental se guarda como WAV de 16 bits mientras no haya codificador aprobado (P14).
* Pulsar Instalar en un agregado, con el tamaño y el origen a la vista, cuenta como consentimiento del servicio
  de agregados; con la conexión general apagada no se descarga nada.
* Valencia y activación del análisis van en `(v − 1) / 8` y las filas de la V1 se reanalizan, porque la V1 las
  recortaba a 1.
* Las secciones del descubrimiento se titulan desde el diccionario, no desde Rust.

**Aviso.** El arranque se mantuvo dentro de los 250 KB llevando a carga diferida todo lo que solo usan pantallas
secundarias (textos en `es-aparte.ts`, puente en `$core/ipc/aparte.ts`, Dispositivos, Reproducción y Apariencia de
Ajustes); quedó en 244,3 KB.

## 2026-10-31: Fase 6

| Commit | Iteración | Qué se hizo | Pruebas nuevas |
|---|---|---|---|
| `aa43803` | F6.1.1 | Ontología, intención y embeddings del DJ. La tabla de conceptos se generó desde el módulo de la V1 con un script de un solo uso fuera del repositorio, para no transcribir a mano 800 líneas de datos; las respuestas doradas (`dj/doradas_intencion.json`) salen del mismo módulo. El tokenizador de MiniLM se escribe a mano: `tokenizers` no está en ningún ADR | 14 intenciones y dos embeddings iguales a la V1; la tabla y sus cinco referencias muertas; el WordPiece |
| `62d1428` | F6.1.2 | Narrativa, planificador y constructor por bloques, con la puntuación de transiciones y el refinado del orden que el constructor de la V1 usa en cada bloque (la mezcla audible queda en F6.1.3). Para que la misma semilla dé la misma sesión se escribe el Mersenne Twister de Python (`dj/azar.rs`) y la suma compensada de `sum()` de Python 3.12+. Se cierra un hueco de F4.1.12 y F5.3.1: las etiquetas de ambiente (`derive_vibe_tags` y su versión del modelo) no se guardaban, y el DJ las usa para penalizar lo negado | Siete sesiones con semilla iguales bit a bit a la V1 (pistas, orden, puntuaciones, razones, transiciones, resumen); la secuencia del azar; las propiedades de `test_dj_privado_scheduler.py`; la carga de candidatas; el ambiente |

**Decisiones de F6.1.2.**

* La intención guarda sus mapas en el orden de inserción, como el `dict` de la V1 (`ontologia::objeto`): el orden
  decide sumas y el desempate del estilo de transición.
* La similitud del embedding con cada pista se calcula una vez por sesión y no una vez por bloque como en la V1: el
  resultado es el mismo y con MiniLM ahorra una inferencia por pista y bloque.
* `serde_json` lee los flotantes con `float_roundtrip` solo en las pruebas, para comparar las doradas bit a bit; el
  binario no cambia.
* Las pistas analizadas por la V2 antes de este commit no tienen etiquetas de ambiente básicas; las de la V1 llegaron
  con la importación. Nadie usa aún la V2 con datos propios, así que no se añade una migración de relleno.
| `7c08cfe` | F6.1.3 (1/2) | La decisión de cada mezcla (`dj/mezcla.rs`): puntos de entrada y salida por pulsos, técnica según fase, tempo, tonalidad, perfil e instrumental, solapamiento y las curvas de volumen y bandas. Las capas de la V1 hacían aparecer la pista entrante al 40 % y cortaban la saliente al 40 %; aquí ambas entran y salen en rampa. No se porta el cálculo por RMS, que la V1 nunca activaba | Las propiedades de `test_dj_mix_engine.py` que no dependen de VLC; ninguna curva salta salvo el corte |
| `fb63d45` | F6.1.3 (2/2) | El motor pasa a dos platos (fuente, alimentador, diez bandas y volumen cada uno) colgados de la pista maestra, que conserva el ecualizador del usuario y el limitador; la reproducción normal sigue siendo idéntica muestra a muestra. `dj/ejecutor.rs` arma la entrante en silencio, abre la puerta cuando suena (o a los 2,5 s), aplica las curvas con el reloj del audio y, al terminar, cambia de plato. El barrido mueve sus bandas de forma continua, no a saltos de 4 dB, y las rampas de volumen se curvan para que el cruce no deje un hueco: Kira interpola en decibelios | La puerta de `test_dj_transicion_gate.py`; las cinco técnicas renderizadas fuera de línea sin clics, sin picos, sin escalones de 1,5 dB en 50 ms ni de 1 LU en la sonoridad a corto plazo |

**Decisiones de F6.1.3.**

* En las capas, la entrante suena con su instrumental del karaoke y recupera la voz en el último cuarto del
  solapamiento. La V1 cargaba el instrumental en lugar de la pista y lo dejaba sonar hasta el final: toda la canción
  sin voz.
* La pista que entra solo se anuncia (`PistaEmpieza`) cuando la mezcla termina y su plato pasa a ser el activo; el
  plato que no lo es no cuenta ni su comienzo ni su final.

| Commit | Iteración | Qué se hizo | Pruebas nuevas |
|---|---|---|---|
| `02844a5` | F6.1.4 | `dj/equipo.rs`: el perfil (bajo, medio, alto), su clasificación por el factor de tiempo real y la medición en un hilo aparte, una a la vez. Se mide separando diez segundos de audio sintético con el modelo del agregado de karaoke (`karaoke::medir`), por el mismo camino que una pista; sin el agregado, el perfil es bajo y el DJ mezcla sin capas. No se guarda: la migración descarta la medida de la V1 y la V2 mide en cada arranque, al abrir el DJ por primera vez, como la V1 | Las propiedades de `test_dj_hardware_profile.py` salvo las de persistencia; una medición no se solapa con otra; la separación de prueba son dos segmentos |
| `1963ea5` | F6.1.5 | La capa del DJ sin audio. `dj/sesiones.rs` lee y escribe sesiones, pistas planificadas (cada una con la transición que la trae), eventos, preferencias y la sesión en curso, con los estados y JSON de la V1. `dj/servicio.rs` empieza, continúa, regenera (semilla + 17), descarta, finaliza, guarda como playlist ("DJ Privado: Music Session, Vol. N"), retoma una del historial sin repetir lo planificado y filtra el historial sin distinguir tildes. La narrativa ya estaba en F6.1.2. Sin candidatas no hay error: el resultado lo dice y la sesión queda en `error`, como en la V1 | `test_dj_privado_integracion.py` sobre una base en memoria con la biblioteca de la V1; preferencias, sesión en curso y borrado en cascada |

**Decisiones de F6.1.5.**

* Toda sesión nueva guarda su semilla, aunque no se dé: retomarla la sigue construyendo igual. La V1 solo guardaba la
  que le daban.
* La sesión en curso se recuerda por la posición de la pista en la sesión, que no cambia, en vez del índice del
  reproductor; por eso `dj_en_curso` no necesita el id de pista que guardaba la V1.
* El reproductor de la sesión (`reproductor_sesion.py`), que decide cuándo mezclar y con qué pista, va con las vistas
  en F6.1.6, integrado en el reproductor único: la V2 tiene un solo motor y una sola barra.

| Commit | Iteración | Qué se hizo | Pruebas nuevas |
|---|---|---|---|
| `6914ba1` | F6.1.6 (1/2) | La sesión del DJ suena en el reproductor único (`reproductor/dj.rs`), como un modo: la cola del usuario espera en pausa donde estaba, cada pista prepara al empezar la mezcla hacia la siguiente con el perfil del equipo y la fase de la sesión, y al llegar al punto de salida la arma el ejecutor. Saltar apunta la pista como saltada y mezcla ya; pedir otra música deja la sesión; al acabar la última, la sesión queda finalizada y vuelve la cola. La sesión que sonaba vuelve en pausa al abrir (`dj_en_curso`), salvo si se descartó | Una sesión de tres pistas suena entera con sus mezclas; la cola vuelve en pausa y sigue donde estaba; pedir otra música; saltar; volver al abrir y no volver si se descartó |

| (siguiente) | F6.1.6 (2/2) | El DJ en su hilo (`dj/director.rs`): atiende las peticiones de una en una y, entre ellas, sigue construyendo la sesión activa y avisa al reproductor y a la vista de cada bloque. Nueve comandos (`dj_pedir`, `dj_sesion`, `dj_reproducir`, `dj_valorar`, `dj_regenerar`, `dj_descartar`, `dj_guardar`, `dj_historial`, `dj_eliminar`) y la vista DJ Privado: pedir con palabras, duración e ideas; la sesión con su resumen, sus cifras, la mezcla en curso y sus canciones con la calidad de cada transición; y el historial con búsqueda. La vista dice cuando no hay análisis musical. Se carga aparte: el arranque sigue en 244,5 KB | Una sesión se completa sola tras el primer bloque y avisa; la vista, comprobada en una captura con el puente simulado |

**Aviso.** Durante esta iteración se llenó el disco de la sesión con 18,7 GB de artefactos de compilación de la propia
caja; `cargo clean -p nb-sound` los quitó sin tocar las dependencias.
