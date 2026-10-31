# Fase 5: Agregados, karaoke y análisis musical

> **Objetivo:** el gestor de agregados de un clic, el karaoke como función del reproductor y el análisis musical,
> todo con ONNX Runtime.
>
> **Prerrequisitos:** Fases 2 y 4, F0.4.2 y F0.4.3, F0.1.5. Contratos: [ADR-002](../adr/decisions/ADR-002-sin-python.md),
> [ADR-006](../adr/decisions/ADR-006-agregados.md), [ADR-010](../adr/decisions/ADR-010-licencia.md).

## Estado de la fase

| Iteración | Estado |
|---|---|
| F5.1.1 Catálogo de agregados compilado (URL, tamaño, SHA-256) | Hecha: `agregados.rs` compila las entradas publicadas en la Release `agregados-1` (`karaoke-1.zip`, `analisis-1.zip` y `texto-dj-1.zip`) con su URL, tamaño exacto y hash SHA-256 verificados (P13 cerrada; `Aceleracion` permanece opcional hasta medir P6) |
| F5.1.2 Descarga reanudable, verificación e instalación atómica | Hecha: `Red::descargar` escribe a disco con `Range` y sin el tope global de 30 s; el ZIP parcial sobrevive a un cierre, se verifica el SHA-256 antes de abrirlo y se extrae a una carpeta temporal que se cambia de nombre al final. Probado con un servidor de mentira: corte y reanudación, servidor que ignora el `Range`, hash alterado y ruta trampa. La prueba contra la Release real va a las pruebas finales |
| F5.1.3 Ajustes > Agregados: tarjetas con Instalar y Quitar | Hecha: una tarjeta por agregado con qué hace, cuánto ocupa y un botón; el progreso llega por `agregados:cambio` y se sigue usando la aplicación. Pulsar Instalar consiente el servicio de agregados; con la conexión general apagada no se descarga. Sin Release publicada (P13) se ven como "Todavía no disponible"; el clic hasta el micrófono funcionando va a las pruebas finales |
| F5.1.4 Ofrecer el agregado donde hace falta | Hecha: pulsar el micrófono sin el agregado de karaoke lo ofrece ahí mismo con su tamaño (`OfertaAgregado.svelte`, que se carga aparte), y se sigue escuchando mientras se instala |
| F5.1.5 Detección de GPU y agregado de aceleración | Parcial: `gpu.rs` detecta lo que aprovecharía ONNX Runtime (NVIDIA con su controlador en Linux, DirectML en Windows, CoreML en Apple Silicon) y Ajustes recomienda el agregado con su motivo, sin instalarlo. El agregado en sí espera a P13 y a medir su tamaño (P6) |
| F5.2.1 Separación con `htdemucs` ONNX en segundo plano, con prioridad baja | Hecha: `karaoke.rs` con el algoritmo por segmentos de la V1 (solo acumula la voz), la sesión sin *arena* ni patrón de memoria y con la mitad de los núcleos (P8), una cola en su hilo que retoma lo cortado y reintenta lo fallido al pedirlo, y el instrumental en WAV (P14). `onnx.rs` carga el ONNX Runtime que viaja dentro. Sin el modelo en el entorno, el algoritmo se prueba con modelos de mentira; el vacío de buffer y el pico de memoria con el modelo real van a las pruebas finales |
| F5.2.2 Botón de micrófono: conmutar original/instrumental y preparar mientras suena | Hecha: con instrumental alterna; sin él, pone la pista en la cola y el micrófono enseña el avance real; al terminar, el reproductor añade el instrumental a la pista que suena, en el mismo frame que el original (`Decodificador::buscar_frame`), sin cortar. Con el modelo real, a las pruebas finales |
| F5.2.3 "Listas para cantar" y "Preparar mis favoritas" | Hecha: la ficha de Biblioteca filtra las que tienen instrumental listo (`ConsultaPistas.paraCantar`, opcional para no cambiar las demás consultas) y, con ella activa, "Preparar mis favoritas" pone en cola las que faltan y reintenta las fallidas; sin el agregado, lo ofrece |
| F5.2.4 Stems migrados de la V1 reconocidos sin volver a separar | Hecha: el importador de la V1 (F1.2) ya copia cada instrumental y lo da por `lista`, y deja como `pendiente` lo que estaba en cola (`importador_v1::pruebas::los_instrumentales_se_copian_y_la_cola_queda_pendiente`); con F5.2.3 aparecen en "Listas para cantar". Los 115 reales, a las pruebas finales |
| F5.3.1 Análisis profundo con los modelos convertidos | Hecha: `analisis.rs` porta la cadena de F0.4.3 (remuestreo lineal de libsamplerate con la razón en `f32`, bandas de `TensorflowInputMusiCNN`, parches de Essentia, MusiCNN en lotes de 8 y sus siete cabezas). Se corrige un defecto de la V1: DEAM (de 1 a 9) se lleva a `(v − 1) / 8` en vez de recortarse a 1, y por eso las filas de la V1 se reanalizan. Acerca de y `THIRD_PARTY_LICENSES.md` atribuyen los modelos. La paridad con el modelo real va a las pruebas finales |
| F5.3.2 Análisis en segundo plano, reanudable, sin afectar al audio | Hecha: un hilo propio con un cuarto de los núcleos y pausa entre pistas; lo pendiente es lo que no tiene fila de esta versión o cuyo archivo cambió, así que se reanuda solo; obedece `analisis_activado` y `analisis_en_segundo_plano` de la V1 |
| F5.3.3 Recomendaciones y descubrimiento (`core/music_discovery_service.py`) | Hecha: `descubrir.rs` porta la interpretación de la frase, la puntuación por intención y las secciones de la V1, con sus pesos y su umbral de 0,35; Buscar muestra las secciones cuando la búsqueda expresa una intención. Los títulos viajan como identificadores y salen del diccionario. "Sorpréndeme" de Inicio y el resumen anual de Tu música no usaban este servicio en la V1 (`sorprenderme` es del reproductor) y siguen pendientes en su fase |

## Criterios

* **F5.1.2:** cortar la red a mitad de una descarga y reanudarla produce el archivo correcto; un hash alterado se
  rechaza y no deja nada instalado.
* **F5.1.3:** de "no tengo karaoke" a "el micrófono funciona" en un clic, sin terminal y sin reiniciar.
* **F5.2.1:** separar con todos los núcleos ocupados no produce ningún vacío de buffer en la reproducción (la misma
  prueba de F0.4.1), y el pico de memoria del proceso separando queda por debajo de 3 GB (F0.4.2 midió 9 GB con
  la configuración por defecto de ONNX Runtime; ver P8).
* **F5.2.4:** las 115 pistas con instrumental de la V1 aparecen como "listas para cantar" tras migrar, sin volver a
  separarlas. De los 323 trabajos de la V1 solo 117 terminaron; 149 se cancelaron y 57 siguen en cola, y estos
  entran como pendientes.
* **F5.3.1:** se mantiene la paridad de F0.4.3; el almacenamiento cumple el presupuesto de ADR-004.
* Ajustes > Acerca de atribuye los modelos con su licencia.

**Puerta de empaquetado**, incluida la instalación de cada agregado en la máquina limpia.
