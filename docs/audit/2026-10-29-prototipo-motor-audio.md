# Prototipo F0.4.1: motor de audio (2026-10-29)

> Decide [ADR-003](../adr/decisions/ADR-003-motor-de-audio.md). Código desechable en
> `scripts/prototipos/motor-audio/`; lo que sobrevive es este informe y el diseño de la fuente propia.

## Cómo se midió

Symphonia 0.6.1 y Kira 0.12.6, en esta máquina (Linux, 8 hilos), con archivos del corpus real abiertos en solo
lectura. Para comparar muestra a muestra sin tarjeta de sonido se escribió un backend de Kira que renderiza fuera
de línea y entrega la salida (el `MockBackend` de Kira procesa pero no deja leerla). El punto 6 usa el dispositivo
real con `cpal`.

Archivos: dos pistas consecutivas de un álbum (MP3, 44,1 kHz) y una pista de 10 minutos (MP3 VBR) para seek,
karaoke y carga.

## Resultados frente a los criterios

| Criterio de ADR-003 | Resultado | ¿Pasa? |
|---|---|---|
| Sin cortes entre pistas | Symphonia recorta retardo y relleno: los frames decodificados coinciden con los que declara el contenedor (6.132.160 y 9.305.536). Con la fuente propia, la salida es A seguida de B **bit a bit** en todas las muestras por debajo de 0 dBFS | Sí, con la fuente propia |
| Seek < 10 ms en MP3 VBR | Peor desvío en 12 posiciones: **1 frame (0,02 ms)** | Sí |
| Karaoke: deriva 0 en 5 min | Original e invertido arrancados en el mismo instante: **residuo 0** en 300 s. Con la fuente propia, alineados por construcción | Sí |
| Conmutar sin clic (≥ 20 ms) | Salto máximo entre muestras en la conmutación 0,0093, frente a 0,0468 de la propia música | Sí |
| Ecualizador ±0,5 dB de la tabla de la V1 | Diez campanas con las ganancias de la tabla tal cual: hasta **±7,2 dB** de error, porque las bandas vecinas se suman. Con ganancias corregidas por iteración: **±0,00 dB** en los 18 presets | Sí, con corrección |
| Cero vacíos de buffer con la CPU al 100 % | **300 s en el dispositivo real con los 8 hilos ocupados: 0 errores de flujo**, uso máximo del hilo de audio 51,7 % (con la suite de la V1 corriendo a la vez) | Sí |
| Menos del 2 % de un núcleo | Reproducción con los 10 filtros: **1,94 %** de un núcleo; 3,5 % con la máquina saturada | Sí, justo |

## Tres hallazgos que cambian el diseño

1. **Programar pistas con el reloj de Kira no es exacto.** Una pista arrancada con `StartTime::ClockTime` sale
   con pequeñas desviaciones y, encadenando dos, la salida se separa de A seguida de B a los 8,4 s. Una sola pista
   arrancada de inmediato sí es exacta. **Decisión:** la cola no son sonidos de Kira programados en un reloj, sino
   **una fuente propia** (`Sound` de Kira) que entrega los frames de una pista y, en el mismo bloque, los de la
   siguiente. El karaoke son dos lecturas del mismo índice dentro de esa fuente. Kira se queda con lo que hace
   bien: pistas de mezcla, efectos, transiciones y la salida por `cpal`.
2. **Kira recorta la salida a ±1,0** (`backend/renderer.rs`, `clamp(-1.0, 1.0)`). Los MP3 del corpus tienen picos
   de hasta 1,104 tras decodificar, así que hoy esas muestras se recortan en seco. Las 14.745 muestras distintas de
   la prueba de cola son exactamente las que pasaban de 0 dBFS. **Decisión:** el motor deja margen antes de Kira
   (la normalización por LUFS de F2.1.4 ya baja el nivel) y un limitador suave de pico como último efecto de la
   pista maestra, para que el recorte de Kira no actúe nunca.
3. **El ecualizador no puede usar la tabla de la V1 tal cual.** libVLC aplicaba sus propias curvas; diez campanas
   de una octava con esas ganancias se desvían hasta 7,2 dB porque se solapan. **Decisión:** las ganancias que se
   envían a los filtros se calculan una vez por preset (y al mover un deslizador) para que la respuesta en cada
   centro sea la de la tabla. Se mide con amplitud baja: a amplitud alta el propio recorte de Kira falsea la
   medida, que fue el primer error de este prototipo.

## Conclusión

ADR-003 se confirma con los tres ajustes de arriba: Symphonia para decodificar, Kira para mezclar, efectos y
salida, y una fuente propia para la cola y el karaoke. No hace falta el motor propio sobre `cpal`.

Lo que no se midió aquí y queda para F2.1: AAC-LC dentro de M4A (Symphonia lo marca sin reproducción sin cortes)
y FLAC de 24 bits; el corpus real no tiene ninguno.
