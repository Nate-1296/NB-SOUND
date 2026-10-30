# ADR-002: Ningún intérprete de Python en tiempo de ejecución

**Fecha:** 2026-10-29
**Estado:** Aceptado. Confirmado entero el 2026-10-29: karaoke por F0.4.2 ([informe](../../audit/2026-10-29-prototipo-karaoke.md)), análisis por F0.4.3 ([informe](../../audit/2026-10-29-prototipo-analisis.md)) y rasgos por F0.4.4 ([informe](../../audit/2026-10-29-prototipo-rasgos.md))

## Contexto

El documento de visión original ([vision-v2-original.md](../../contextual/vision-v2-original.md)) mantenía un
demonio de Python para la catalogación y la inteligencia. Al investigarlo aparecieron cuatro hechos que lo
invalidan (detalle y fuentes en la [investigación del 2026-10-29](../../audit/2026-10-29-investigacion-v2.md)):

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

1. **Python del sistema** (la V1). Rechazada por la Constitución, regla 1.
2. **Python embebido** (`python-build-standalone` + `uv`) como agregado descargable. Rechazada como plan principal:
   no resuelve Essentia en Windows, añade un segundo runtime con varios GB (torch), un canal de IPC con contratos en
   tres lenguajes y una segunda superficie de empaquetado. **Queda como plan de contingencia** si F0.4.2 o F0.4.3
   fallan.
3. **Todo en Rust, la inferencia con ONNX Runtime a través de `ort`.** Aceptada.

## Decisión

* La V2 no ejecuta Python. La lógica de `core/`, `servicios/` y `external/` se porta a Rust, usando las pruebas de
  la V1 como especificación.
* La inferencia (karaoke, análisis, embeddings del DJ) corre en ONNX Runtime vía `ort`. El runtime de CPU viaja en
  el instalador; los modelos y la aceleración por GPU son agregados ([ADR-006](./ADR-006-agregados.md)).
* Los modelos `.pb` de Essentia se convierten a ONNX una sola vez, fuera de la aplicación, con `tf2onnx`, y se
  publican como agregado con su hash. La licencia de los modelos (CC BY-NC) permite el cambio de formato; ver
  [ADR-010](./ADR-010-licencia.md).
* El texto del DJ (`all-MiniLM-L6-v2`, que la V1 ya intentaba usar vía `onnxruntime`) corre por la misma vía.

## Criterios que confirman o derriban este ADR

| Prototipo | Pasa si |
|---|---|
| F0.4.2 Karaoke ONNX | Instrumental equivalente al de la V1 (diferencia de SDR < 0,1 dB en 20 pistas del corpus) y tiempo por pista no peor que el de la V1 en esta máquina |
| F0.4.3 Análisis ONNX | Las 12 salidas de modelo coinciden con las de la V1 en las 407 pistas ya analizadas (diferencia absoluta < 0,01 por clase) |
| F0.4.4 Rasgos básicos | Tempo dentro de ±2 % (o múltiplo 2× / 0,5×) del de la V1 en ≥ 95 % de las 2.397 pistas |

Si alguno falla, se escribe un ADR que supera a este y adopta la alternativa 2 para esa función concreta.

## Consecuencias

- **Positivas:** un solo runtime y un solo lenguaje en el núcleo; el análisis llega a Windows; el karaoke no
  necesita PyTorch (de varios GB a 166 MB); los tipos son de extremo a extremo.
- **Negativas:** portar unas 34.000 líneas de lógica. Se mitiga portando por fases y con paridad medida contra la V1.
- **Riesgos:** que la paridad del preprocesado mel de MusiCNN/VGGish/EffNet sea difícil. Se vigila con F0.4.3
  antes de construir encima.
