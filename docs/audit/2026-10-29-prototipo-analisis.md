# Prototipo F0.4.3: análisis musical en Rust y ONNX (2026-10-29)

> Decide la parte de análisis de [ADR-002](../adr/decisions/ADR-002-sin-python.md). Código en
> `scripts/prototipos/analisis/` (`convertir.py`, `referencia.py` y el prototipo de Rust en `rust/`).

## Resultado

**En las 407 pistas que la V1 analizó, la cadena entera en Rust da las mismas salidas que guardó la V1: la peor
diferencia es 0,0041 y ninguna pasa de 0,01**, que era el criterio.

| Salida | Peor diferencia en 407 pistas |
|---|---|
| Bailabilidad | 0,00075 |
| Alegría | 0,0028 |
| Tristeza | 0,0037 |
| Relajado | 0,0041 |
| Agresividad | 0,0037 |
| Fiesta | 0,0019 |
| Valencia y activación (DEAM, sobre su escala de 1 a 9 llevada a 0–1) | 0,00087 |

La cadena medida es la de producción: Symphonia decodifica, se remuestrea a 16 kHz, se calculan las bandas mel de
MusiCNN, se cortan los parches y ONNX Runtime 1.31.1 (el del instalador) ejecuta los modelos convertidos. 407 pistas
en 36 minutos con prioridad baja, unos 5 s por pista.

## Cómo se llegó, paso a paso

1. **Conversión de los modelos** con `tf2onnx`: MusiCNN y sus siete cabezas difieren del original de TensorFlow
   entre 10⁻⁷ y 3·10⁻⁵ sobre la misma entrada.
2. **Preprocesado:** las bandas mel de `TensorflowInputMusiCNN` portadas desde el código de Essentia (`FrameCutter`
   de streaming, ventana de Hann simétrica, filtros de Slaney normalizados por área, `log10(1 + 10000·x)`) difieren
   de las de Essentia como mucho 5,6·10⁻⁴, y las salidas de los modelos, 10⁻⁶.
3. **Decodificación:** Symphonia y el decodificador de Essentia (FFmpeg) dan la misma señal: −80,7 dB de
   diferencia, misma longitud.
4. **Remuestreo, lo que costó encontrar:** con un remuestreador de calidad las salidas se desviaban hasta 0,1. La
   V1 usaba `resampleQuality = 4`, el conversor **lineal** de libsamplerate, y Essentia le pasa la razón calculada en
   `float32`; con la razón en `float64` cada muestra se desplaza un poco y la diferencia acumulada llega a −36 dB.
   Replicando las dos cosas, la señal coincide con la de Essentia a −82 dB.

## Decisiones que salen de aquí

* **VGGish y EffNet se retiran.** La V1 calculaba los embeddings de VGGish (y tenía preparado EffNet con el género
  Discogs400, desactivado) pero **ningún código los leía**: se guardaban y nada más. VGGish además no se puede
  convertir dentro de 9 GB de memoria (son 288 MB de grafo). Sin ellos, **el agregado de análisis pasa de más de
  300 MB a unos 4 MB**: MusiCNN (3,2 MB) y sus siete cabezas.
* **El remuestreo del análisis es el lineal de la V1**, no uno de calidad, por paridad: los modelos ya se evaluaron
  así en la biblioteca real. Cambiarlo cambiaría los resultados de todas las pistas ya analizadas.
* **Los parches se procesan en lotes de 8**, no de 64 como Essentia: con 64, las activaciones de una sola pista
  llevan el proceso a 3,6 GB; con 8, a 445 MB, a la misma velocidad.

La parte de análisis de ADR-002 queda **confirmada**.
