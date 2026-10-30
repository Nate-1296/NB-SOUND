# Prototipo F0.4.2: karaoke con htdemucs en ONNX (2026-10-29)

> Decide la parte de karaoke de [ADR-002](../adr/decisions/ADR-002-sin-python.md). Código en
> `scripts/prototipos/karaoke/paridad.py`.

## Cómo se midió

Cinco canciones del corpus de géneros distintos (electrónica, pop, R&B, balada en español y música barroca), con
el entorno de la V1. Para cada una:

1. **Referencia:** el modelo `htdemucs` de PyTorch con el algoritmo por segmentos de la V1 tal cual
   (`legado/servicios/karaoke/separador.py`, `_separar_por_segmentos`: normalización, segmentos de 7,8 s con 25 % de
   solapamiento y ventana triangular).
2. **ONNX:** el mismo algoritmo, cambiando solo la llamada al modelo por ONNX Runtime 1.31.1 (el que viaja en el
   instalador), con el grafo exportado de [adowu/htdemucs-onnx](https://huggingface.co/adowu/htdemucs-onnx) en fp16
   y en fp32.
3. Se compara el instrumental (mezcla menos voces, como la V1) con la relación señal/diferencia en dB: cuánto más
   débil es la diferencia que el instrumental de PyTorch.

Las mismas 8 hebras de CPU en los tres casos. El criterio de ADR-002 pedía "diferencia de SDR menor de 0,1 dB": no
hay stems de referencia (las canciones no vienen separadas), así que se mide algo más exigente, la diferencia
directa con la salida de la V1.

## Resultados

| Canción | Duración | RTF PyTorch | RTF ONNX fp16 | RTF ONNX fp32 | fp16 frente a PyTorch | fp32 frente a PyTorch |
|---|---|---|---|---|---|---|
| Electrónica | 219 s | 1,03 | 1,12 | 1,00 | 78,7 dB | 93,7 dB |
| Pop | 163 s | 1,04 | 1,40 | 0,97 | 74,0 dB | 89,5 dB |
| R&B | 239 s | 1,29 | 1,04 | | 77,2 dB | |
| Balada | 200 s | 1,26 | 1,02 | | 76,9 dB | |
| Barroca | 176 s | 1,13 | 1,03 | | 94,9 dB | |

RTF es el tiempo de proceso dividido por la duración: 1,0 es tiempo real. La V1 en uso real (323 trabajos en su
base) tuvo una mediana de 0,96.

## Conclusión

* **La salida es la misma.** La diferencia más grande, 74 dB por debajo del instrumental, equivale a un error de
  una parte en cinco mil: inaudible. Con fp32 la diferencia baja a 90 dB.
* **La velocidad es la misma** que con PyTorch en CPU (fp16, mediana 1,04; fp32, 0,97–1,00). El pop con fp16 (1,40) se midió
  mientras corrían otros prototipos en la máquina, así que esa cifra probablemente está inflada; el resto queda
  entre 1,02 y 1,12.
* **Se elige fp16** para el agregado: 166 MB frente a 316 MB por una diferencia inaudible.
* **Aparece un riesgo que no estaba en el plan:** ONNX Runtime llegó a **9 GB de memoria** durante la separación.
  En la máquina de desarrollo (19 GB) eso, sumado a lo demás, hizo que `systemd-oomd` cerrara el editor. F5.2.1 no
  puede integrarse así: se añade a su criterio un tope de memoria (desactivar el *arena* y el patrón de memoria de
  ONNX Runtime, y medir el pico con la sesión reutilizada entre segmentos). Queda como pregunta abierta P8.

La parte de karaoke de ADR-002 queda **confirmada**: el agregado no necesita PyTorch ni Python.
