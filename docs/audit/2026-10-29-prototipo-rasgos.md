# Prototipo F0.4.4: rasgos básicos de la V1 en Rust (2026-10-29)

> Decide la parte de rasgos de [ADR-002](../adr/decisions/ADR-002-sin-python.md). Código en
> `scripts/prototipos/rasgos/`.

## Qué se portó

Lo que calculaba `legado/core/audio_features.py` con librosa en modo `light`: los primeros 90 s, en mono a
22.050 Hz, y de ahí tempo, RMS, centroide espectral y tasa de cruces por cero. El tempo replica el estimador que
usa `librosa.beat.beat_track`: espectrograma mel de Slaney, envolvente de onsets, tempograma por autocorrelación con
ventana de 8 s y la preferencia logarítmica centrada en 120 BPM. Como el resultado cae en una rejilla discreta
(`60 · 22050 / (512 · lag)`), una réplica exacta da exactamente los mismos valores.

## Resultado

En las 2.397 pistas de la biblioteca real con análisis de la V1 (otras 37 filas apuntan a archivos que ya no
existen):

| Rasgo | Resultado |
|---|---|
| Tempo | **2.389 iguales dentro de ±2 % (99,7 %)**, 2 en el doble o la mitad; dentro del criterio de ADR-002 (≥ 95 %), el **99,7 %** |
| RMS | correlación 0,9999 |
| Centroide espectral | correlación 0,9995 |
| Cruces por cero | correlación 0,9997 |

39 minutos para las 2.397 pistas en un solo hilo con prioridad baja, menos de 1 s por pista.

Las 6 pistas restantes caen en relaciones de 3:2 o 4:3 (por ejemplo 92 frente a 172 BPM), que es donde el máximo
del tempograma está casi empatado y una diferencia mínima del decodificador lo inclina.

## Lo que costó encontrar

El primer intento coincidía solo en el 83 %. `beat_track` no usa la envolvente de onsets de
`onset_strength` por defecto (la media entre bandas mel), sino **la mediana**. Con la mediana, 60 de 60 primero y
99,7 % en todo el corpus.

## Lo que queda

* **La tonalidad nueva** (mayor o menor con perfiles de Krumhansl, en lugar del `argmax` del croma de la V1, que
  además decidía el modo por si la nota tenía sostenido) no se puede comparar con la V1 porque es distinta a
  propósito. Se implementa en F4.1.12 y se valida a oído en 30 pistas.
* Los demás rasgos de la V1 (ancho de banda, rolloff, onset rate y los "proxies" de energía, valencia y demás) son
  combinaciones de estos y se portan en F4.1.12 con la misma comparación.

La parte de rasgos de ADR-002 queda **confirmada**, y con ella todo el ADR: la V2 no necesita Python.
