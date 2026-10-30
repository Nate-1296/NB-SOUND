# ADR-006: Agregados que se instalan con un clic

**Fecha:** 2026-10-29
**Estado:** Aceptado
**Enmendado:** 2026-10-29, en F0.3.3: `ffmpeg` no viaja dentro. Ver [la enmienda](#enmienda-del-2026-10-29-ffmpeg-no-viaja-dentro)

## Contexto

La V1 tiene una vista entera, **Estado del Sistema** (`VistaEstadoSistema.qml`, 587 líneas), que enseña "Python del
sistema", "Site-packages runtime", la versión de cada librería y comandos de reparación para `apt` o `dnf`.
`infra/dependencias.py` clasifica dependencias como `SISTEMA` ("instalación manual"), `PIP` y `MODELOS`, e
`infra/instalador.py` (676 líneas) busca un Python utilizable en el sistema y ejecuta `pip`. Es la consecuencia
directa de una aplicación diseñada para usar el entorno al que llega.

## Decisión

**Qué viaja dentro del instalador** (nunca es un agregado): el motor de audio, `ffmpeg` y `ffprobe`, la huella
acústica (`fpcalc` o `rusty-chromaprint`, según F0.4.6), ONNX Runtime para CPU, el servidor móvil, las fuentes y los
iconos. Con eso, la aplicación reproduce, importa, identifica, etiqueta, descarga portadas y letras, y sincroniza
con el móvil.

**Qué es un agregado** (grande y opcional):

| Agregado | Contenido | Habilita |
|---|---|---|
| Karaoke | `htdemucs` en ONNX (166 MB en fp16) | Modo karaoke en el reproductor, stems para el móvil, mezcla armónica del DJ |
| Análisis musical | Los 12 modelos de Essentia convertidos a ONNX | Estados de ánimo, género, bailabilidad, listas inteligentes, DJ semántico |
| Comprensión de texto del DJ | `all-MiniLM-L6-v2` en ONNX | Pedidos al DJ en lenguaje natural |
| Aceleración por GPU | Proveedor de ejecución de ONNX Runtime para la GPU detectada (CUDA, DirectML o CoreML) | Karaoke y análisis varias veces más rápidos |

**Cómo se comporta:**

* Viven en **Ajustes, sección Agregados**: una tarjeta por agregado con qué hace, cuánto ocupa y un solo botón
  (Instalar, Quitar). Mientras se descarga se ve el progreso; se puede seguir usando la aplicación.
* Además se ofrecen **en el sitio donde hacen falta**: pulsar el micrófono del reproductor sin el agregado de
  karaoke ofrece instalarlo ahí mismo, con su tamaño.
* El catálogo de agregados se compila dentro del binario: URL, tamaño y SHA-256 fijados. Se descarga a un temporal,
  se verifica el hash antes de moverlo a su sitio y la instalación es atómica. Una descarga interrumpida se reanuda.
* Se guardan en el directorio de datos de la aplicación, nunca en el sistema; desinstalar la aplicación los borra
  con ella, y quitar uno libera su espacio en el acto.
* La descarga pasa por la puerta de red con su consentimiento ([ADR-009](./ADR-009-configuracion-y-red.md)).
* Si el equipo tiene una GPU compatible, Ajustes lo dice y recomienda el agregado de aceleración con su motivo,
  sin instalarlo solo (recomendar no es obligar, principio heredado de NB Books).

**Qué desaparece:** la vista Estado del Sistema, `infra/dependencias.py`, `infra/instalador.py`, la búsqueda de un
Python del sistema, los comandos de reparación y cualquier texto que nombre una librería.

## Consecuencias

- **Positivas:** instalar el karaoke pasa de "Python + pip + torch + demucs + modelo" a un clic de 166 MB.
- **Negativas:** hay que alojar los modelos convertidos en un sitio **público** con enlace estable. El
  repositorio `Nate-1296/NB-SOUND` es privado, así que sus Releases no sirven sin credenciales. Se usará un
  repositorio público de distribución, como en el ADR-011 de NB Books, decidido en F0.1.5.
- **Riesgos:** la licencia de los modelos de Essentia ([ADR-010](./ADR-010-licencia.md)).

## Enmienda del 2026-10-29: ffmpeg no viaja dentro

Al fijar los binarios en F0.3.3 se midió lo que costaba `ffmpeg`: la compilación estática completa (BtbN, 8.1.3)
son 165 MB por ejecutable en Windows, y hacen falta dos (`ffmpeg` y `ffprobe`). Y al revisar para qué lo usaba la
V1 apareció que su uso principal era un defecto: `core/pipeline.py` **convertía a MP3 todo lo que no lo fuera**
(`external/transcoder.py`), así que un FLAC importado perdía calidad para siempre.

La V2 no hace eso. Symphonia reproduce MP3, FLAC, AAC-LC, ALAC, Vorbis y WAV ([ADR-003](./ADR-003-motor-de-audio.md)),
`lofty` escribe las etiquetas de todos ellos, y `fpcalc` 1.6.2 trae su propio decodificador para la huella. Cada
archivo se queda en su formato.

Por tanto:

* **`ffmpeg` sale del instalador.** Lo que queda dentro: `fpcalc` (5 MB) y ONNX Runtime para CPU (29 MB en Linux).
* Lo único que seguiría necesitándolo es decodificar lo que Symphonia no cubre (HE-AAC, Opus, WMA, APE) y copiar a
  dispositivos con conversión (F8.4). Cuando se aborde, será una compilación **propia y solo de audio** (unos
  pocos MB), no la general. Mientras tanto, un archivo en esos formatos llega a Por revisar con el motivo "formato
  no compatible todavía".
* La importación **nunca** transcodifica. Lo vigila una prueba de F4.1.9.
