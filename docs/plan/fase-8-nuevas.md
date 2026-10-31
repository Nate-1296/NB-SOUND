# Fase 8: Capacidades nuevas

> **Objetivo:** lo que el documento de visión proponía y la V1 no tenía. No empieza antes de la paridad
> (Fase 7) salvo lo que ya entró de paso por ser barato: LUFS (Fase 2) y la forma de onda, si sale de la misma
> pasada de decodificación que LUFS.

| Iteración | Qué | Depende de |
|---|---|---|
| F8.1 Forma de onda sobre la barra de progreso, y en el DJ con los puntos de entrada y salida | Picos calculados al importar, en la misma pasada que LUFS | F4.1.12 |
| F8.2 Listas inteligentes vivas | Reglas sobre rasgos (BPM, energía, instrumental, ánimo) y uso (calificación, última escucha), evaluadas en SQLite | F5.3.1 |
| F8.3 Resumen local de escucha | Mensual y anual, radar de ánimos, mapa de calor por hora y día, tarjeta exportable; nada sale del equipo | F2.2.8 |
| F8.4 Copia a dispositivos (microSD, USB, reproductores portátiles) | Estructura de carpetas, portada incrustada, transcodificación opcional | F4.1.9 |
| F8.5 Modo fiesta | Los invitados en la misma red sugieren canciones desde el navegador con un QR | F3, y un ADR de modelo de confianza antes de empezar, porque abre la aplicación a desconocidos |

Cada una exige su ficha completa (objetivo, criterio, dependencias) antes de empezar.

## Estado de la fase

| Iteración | Estado |
|---|---|
| F8.1 Forma de onda | Hecha: 1.000 picos por pista en `sonoridad.picos` (migración V10), calculados en la misma decodificación que los LUFS (`audio/sonoridad.rs`, `medicion.rs`), servidos por `forma_de_onda` y dibujados en `FormaDeOnda.svelte` sobre la barra y en la sesión activa del DJ con los puntos de entrada y salida de `EstadoDj` |
| F8.2 Listas inteligentes vivas | Pendiente: sin ficha |
| F8.3 Resumen local de escucha | Pendiente: sin ficha |
| F8.4 Copia a dispositivos | Pendiente: sin ficha |
| F8.5 Modo fiesta | Bloqueada: necesita un ADR del modelo de confianza aprobado por Nathan |

## F8.1 Forma de onda

**Objetivo.** La barra de progreso dibuja la forma de onda de la pista que suena, y la sesión del DJ la dibuja con
el punto por el que entró la pista y el punto en el que empezará a irse.

**Depende de.** F2.1.4 (la medida de sonoridad en segundo plano), F4.1.12 (el hilo que la lleva) y F6.1.6 (la sesión
del DJ en el reproductor único).

**Decisiones.**

* Los picos salen de **la misma decodificación** que mide los LUFS (`audio/sonoridad.rs`): no se abre el archivo
  una segunda vez. Por eso se calculan donde se calcula la sonoridad, en el hilo que mide lo importado, y no en la
  importación misma, que la V2 no retrasa con análisis.
* Se guardan **1.000 picos por pista**, un byte cada uno (el máximo absoluto de las dos voces en su tramo, de 0 a
  255), en una columna nueva de `sonoridad` (migración V10). Un número fijo, y no uno por segundo, porque lo que
  se pinta es siempre la pista entera en un ancho dado; 1.000 da para la barra más ancha sin pesar: unos 2,4 MB en
  la biblioteca de 2.400 pistas.
* La medida de una pista sin picos caduca, como la de un archivo que cambió: la biblioteca ya medida se vuelve a
  medir una vez, al ritmo de siempre.
* El silencio tiene picos (a cero) aunque no tenga sonoridad. Un archivo que no se puede leer se apunta con picos
  vacíos para no reintentarlo en cada arranque, igual que su sonoridad.
* La forma de onda se pinta en SVG con las variables del tema; lo reproducido, en el color primario. Solo cambia
  cuando cambia la posición, así que en pausa no se anima nada (ADR-008).

**Criterio de aceptación.**

1. `sonoridad::medir` devuelve la sonoridad y los picos de una sola pasada; una prueba lo comprueba sobre un
   archivo que sube de volumen (los picos crecen) y otro con un silencio en medio (sus picos son cero en ese tramo).
2. La biblioteca medida antes de V10 se vuelve a medir una sola vez; el silencio queda con picos a cero y sin
   sonoridad; un archivo ilegible queda con picos vacíos y no se reintenta. Pruebas en `medicion.rs`.
3. La prueba de presupuesto del esquema sigue por debajo de 16 KB por pista con los picos dentro.
4. El comando asíncrono `forma_de_onda` devuelve los picos de una pista, o una lista vacía sin medida. La barra
   dibuja la forma de onda con lo reproducido resaltado; sin picos, la barra de siempre.
5. En el DJ, la instantánea dice desde dónde entró la pista que suena y dónde empieza a irse (`EstadoDj`), y la
   vista de la sesión y la barra marcan los dos puntos sobre la forma de onda. Una prueba del reproductor comprueba
   que la salida es la del plan de la mezcla y que la entrada de la pista siguiente es la del plan que la trajo.
6. En el fragmento de A ciegas la instantánea no lleva pista, así que no se pide ni se dibuja su forma de onda.

**A las pruebas finales.** Que la forma de onda se corresponda a la vista con lo que suena en diez pistas del
corpus, y que la nueva medida de la biblioteca entera no se note en el equipo.
