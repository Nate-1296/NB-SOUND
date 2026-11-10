# ADR-002: Ningún intérprete de Python en tiempo de ejecución

**Fecha:** 2026-10-29
**Estado:** Aceptado. Confirmado entero el 2026-10-29 por los prototipos de karaoke (F0.4.2), análisis (F0.4.3) y rasgos (F0.4.4)

## Contexto

Mantener un demonio de Python para la catalogación y la inteligencia se descartó por cuatro hechos:

1. **Essentia no publica wheels para Windows.** La última versión en PyPI (2.1b6.dev1438, mayo de 2026) solo
   trae `manylinux2014_x86_64` y `macosx_15_0` (arm64 y x86_64). Con Python, el análisis profundo nunca llega a
   Windows.
2. **Essentia se usa solo como envoltorio de inferencia.** En `core/audio_intelligence_deep.py` las únicas
   llamadas son `MonoLoader` y `TensorflowPredict*` sobre 12 modelos `.pb`. No hay algoritmos de Essentia que
   portar: hay que portar el preprocesado de los espectrogramas y ejecutar los modelos.
3. **Demucs v4 existe exportado a ONNX con paridad verificada.** `htdemucs` en ONNX (opset 17, 316 MB en fp32 y
   166 MB en fp16) difiere de PyTorch en menos de 7·10⁻⁴, con la STFT dentro del grafo, y tarda unos 1,6 s por
   segmento de 7,8 s en CPU (RTF 0,20 en un M4 Pro). Mixxx hizo la misma conversión en su GSoC 2025.
4. **librosa se usa para rasgos simples.** `core/audio_features.py` calcula tempo, RMS, centroide, ancho de
   banda, rolloff, ZCR, onset y croma; la tonalidad es un `argmax` del croma sin modo mayor o menor. Todo es DSP
   estándar, portable a Rust y mejorable de paso.

Además, `shazamio-core` ya está escrito en Rust (MIT), los clientes de MusicBrainz, AcoustID, iTunes, LRCLIB y Cover
Art Archive son HTTP con JSON, y las etiquetas se escriben mejor con `lofty` que con `mutagen`.

## Alternativas consideradas

1. **Python del sistema**. Rechazada por la Constitución, regla 1.
2. **Python embebido** (`python-build-standalone` + `uv`) como agregado descargable. Rechazada como plan principal:
   no resuelve Essentia en Windows, añade un segundo runtime con varios GB (torch), un canal de IPC con contratos en
   tres lenguajes y una segunda superficie de empaquetado. **Queda como plan de contingencia** si F0.4.2 o F0.4.3
   fallan.
3. **Todo en Rust, la inferencia con ONNX Runtime a través de `ort`.** Aceptada.

## Decisión

* NB Sound no ejecuta Python. La catalogación, la inteligencia y la sincronización están escritas en Rust.
* La inferencia (karaoke, análisis, embeddings del DJ) corre en ONNX Runtime vía `ort`. El runtime de CPU viaja en
  el instalador; los modelos y la aceleración por GPU son agregados ([ADR-006](./ADR-006-agregados.md)).
* Los modelos `.pb` de Essentia se convierten a ONNX una sola vez, fuera de la aplicación, con `tf2onnx`, y se
  publican como agregado con su hash. La licencia de los modelos (CC BY-NC) permite el cambio de formato; ver
  [ADR-010](./ADR-010-licencia.md).
* El texto del DJ corre por la misma vía.

## Criterios que confirman o derriban este ADR

| Prototipo | Pasa si |
|---|---|
| F0.4.2 Karaoke ONNX | Instrumental equivalente al de referencia (diferencia de SDR < 0,1 dB en 20 pistas del corpus) y tiempo por pista aceptable en esta máquina |
| F0.4.3 Análisis ONNX | Las 12 salidas de modelo coinciden con las de referencia en 407 pistas (diferencia absoluta < 0,01 por clase) |
| F0.4.4 Rasgos básicos | Tempo dentro de ±2 % (o múltiplo 2× / 0,5×) del de referencia en ≥ 95 % de 2.397 pistas |

Si alguno falla, se escribe un ADR que supera a este y adopta la alternativa 2 para esa función concreta.

## Consecuencias

- **Positivas:** un solo runtime y un solo lenguaje en el núcleo; el análisis llega a Windows; el karaoke no
  necesita PyTorch (de varios GB a 166 MB); los tipos son de extremo a extremo.
- **Negativas:** escribir en Rust toda la lógica de catalogación e inteligencia. Se mitiga por fases y con
  resultados medidos contra referencias.
- **Riesgos:** que la paridad del preprocesado mel de MusiCNN/VGGish/EffNet sea difícil. Se vigila con F0.4.3
  antes de construir encima.

## Enmienda del 2026-10-30: dependencias de la catalogación

Para la canalización de catalogación (Fase 4), con la aprobación de Nathan:

| Crate | Para qué |
|---|---|
| `lofty` | Leer y escribir etiquetas (ya prevista arriba) |
| `unicode-normalization` | NFKC, NFD y quitar diacríticos al comparar nombres |
| `regex` | Las reglas de normalización de texto; ya estaba en el árbol |
| `notify` | Vigilar la carpeta de música |
| `trash` | Descartar desde Por revisar a la papelera del sistema |
| `zip` | Leer y escribir el `.nbsound-backup`, que es un ZIP |
| `rustfft` y `rubato` | Los rasgos básicos de F0.4.4 y la firma de Shazam, portada de `songrec` |

Cada una entra en el commit de la iteración que la usa.

## Enmienda del 2026-11-05: prioridad del trabajo de fondo

Medido en la 2.0.8 instalada, preparar el karaoke ocupaba la mitad de los núcleos a prioridad normal y competía con
la interfaz. Con la aprobación de Nathan entra `libc` (MIT o Apache-2.0; ya estaba en el árbol por `alsa`, `gtk` y
otras), solo en Unix, para bajar la prioridad de los hilos de fondo (`prioridad.rs`): en Linux, `setpriority` del
hilo a 19; en macOS, la clase de calidad de servicio `UTILITY`. Los hilos de ONNX Runtime heredan la del hilo que
crea la sesión. En Windows no se baja todavía: haría falta `windows-sys`, que no está aprobada.

## Enmienda del 2026-11-09: prioridad en Windows y del disco

Con la aprobación de Nathan (P16) entra `windows-sys` (MIT o Apache-2.0; ya llegaba por Tauri), solo en Windows y
solo con `Win32_System_Threading`: el hilo de fondo pasa a `THREAD_MODE_BACKGROUND_BEGIN`, que baja a la vez la
prioridad del procesador y la del disco. En Linux, los mismos hilos bajan también la del disco a la clase ociosa
(`ioprio_set` por `libc`), y se suman a ellos la copia automática, la auditoría, los vectores del DJ y lo que se
completa en segundo plano.
