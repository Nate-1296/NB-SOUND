# Fase 5: Agregados, karaoke y análisis musical

> **Objetivo:** el gestor de agregados de un clic, el karaoke como función del reproductor y el análisis musical,
> todo con ONNX Runtime.
>
> **Prerrequisitos:** Fases 2 y 4, F0.4.2 y F0.4.3, F0.1.5. Contratos: [ADR-002](../adr/decisions/ADR-002-sin-python.md),
> [ADR-006](../adr/decisions/ADR-006-agregados.md), [ADR-010](../adr/decisions/ADR-010-licencia.md).

## Estado de la fase

| Iteración | Estado |
|---|---|
| F5.1.1 Catálogo de agregados compilado (URL, tamaño, SHA-256) | Pendiente |
| F5.1.2 Descarga reanudable, verificación e instalación atómica | Pendiente |
| F5.1.3 Ajustes > Agregados: tarjetas con Instalar y Quitar | Pendiente |
| F5.1.4 Ofrecer el agregado donde hace falta | Pendiente |
| F5.1.5 Detección de GPU y agregado de aceleración | Pendiente |
| F5.2.1 Separación con `htdemucs` ONNX en segundo plano, con prioridad baja | Pendiente |
| F5.2.2 Botón de micrófono: conmutar original/instrumental y preparar mientras suena | Pendiente |
| F5.2.3 "Listas para cantar" y "Preparar mis favoritas" | Pendiente |
| F5.2.4 Stems migrados de la V1 reconocidos sin volver a separar | Pendiente |
| F5.3.1 Análisis profundo con los modelos convertidos | Pendiente |
| F5.3.2 Análisis en segundo plano, reanudable, sin afectar al audio | Pendiente |
| F5.3.3 Recomendaciones y descubrimiento (`core/music_discovery_service.py`) | Pendiente |

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
