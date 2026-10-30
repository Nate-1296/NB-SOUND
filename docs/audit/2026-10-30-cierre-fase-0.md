# Cierre de la Fase 0: fundaciones y prototipos (2026-10-30)

> Evaluación de la [Fase 0](../plan/fase-0-fundaciones.md) contra su criterio de cierre: todas las iteraciones
> hechas o parciales con lo que falta escrito, la puerta de empaquetado cruzada en Linux y ADR-002 y ADR-003
> confirmados o superados.

## Resultado

**La Fase 0 se cierra.** Las 23 iteraciones están hechas. ADR-002 y ADR-003 quedan confirmados por medición. La
puerta de empaquetado se cruzó en Linux con prueba en máquina limpia.

## Lo que construyó

* **Repositorio:** la V1 en `legado/`, la V2 en la raíz con la pila de NB Books (Tauri 2, SvelteKit 2, Svelte 5,
  Rust), público desde el 2026-10-29.
* **Fundación del runtime:** errores con código canónico, tipos del puente generados, registro con redacción, rutas
  propias separadas de las de la V1 y una sola puerta de red que de fábrica no deja salir nada.
* **Verificación:** 16 guardianes en `pnpm verify` y en el gancho de pre-commit, `cargo-deny` y CI en Linux, Windows
  y macOS, en verde.
* **Empaquetado:** `.deb` y AppImage compilados en Ubuntu 22.04, con `fpcalc` y ONNX Runtime dentro, probados en
  Ubuntu 24.04, Ubuntu 22.04 y Debian 12 limpios.

## Lo que decidieron los prototipos

| Prototipo | Resultado | Informe |
|---|---|---|
| Motor de audio | Confirma Symphonia + Kira con una fuente propia, margen antes de la salida y EQ corregido | [motor](2026-10-29-prototipo-motor-audio.md) |
| Karaoke | `htdemucs` en ONNX = PyTorch (74–95 dB por debajo), misma velocidad; riesgo de 9 GB de memoria (P8) | [karaoke](2026-10-29-prototipo-karaoke.md) |
| Análisis | 407 de 407 pistas iguales a la V1; VGGish y EffNet retirados, agregado de ~4 MB | [análisis](2026-10-29-prototipo-analisis.md) |
| Rasgos | Tempo igual que la V1 en el 99,7 % de 2.397 pistas | [rasgos](2026-10-29-prototipo-rasgos.md) |
| Contrato móvil | 36 respuestas doradas de la V1, reproducibles byte a byte | [contrato](../engineering/contrato-movil.md) |
| Huella | Se queda `fpcalc` | [plan](../plan/fase-0-fundaciones.md) |
| Lista | Ventana virtual sin fotogramas largos con 100.000 filas | [lista](2026-10-29-prototipo-lista.md) |

## Lo que cambió del plan por el camino

* **`ffmpeg` sale del instalador** y la V2 deja cada archivo en su formato: la V1 convertía FLAC a MP3 (enmienda de
  ADR-006).
* **La V2 se parece a la V1**, no a NB Books: temas completos de la V1, tipografía elegible y listas continuas
  (enmienda de ADR-008, decidida por Nathan).
* **El repositorio es público** (decisión de Nathan), lo que además desbloqueó el CI y resolvió dónde publicar los
  agregados.

## Lo que queda abierto y a quién le toca

| Asunto | Dónde se resuelve |
|---|---|
| P3, licencia de los modelos de Essentia si el producto fuera comercial | Nathan, solo si cambia el modelo de negocio |
| P6, tamaño del agregado de aceleración con CUDA | F5.1.5 |
| P7, que el móvil reproduzca FLAC y M4A | F3.1.6, con el teléfono real |
| P8, bajar la memoria del karaoke por debajo de 3 GB | F5.2.1 |
| `fpcalc` en `/usr/bin` puede chocar con el paquete `chromaprint` | F7.2.1 |
| Instaladores de Windows y macOS sin probar en máquina real | Puerta de cada fase, con el CI |
| Mac con Intel sin soporte (ONNX Runtime 1.31 no lo publica) | Registrado; no hay acción |

## Una lección de la propia fase

Dos veces el editor de Nathan se cerró porque los prototipos pesados agotaron la memoria y `systemd-oomd` mató el
grupo de procesos entero. Desde entonces, todo trabajo pesado corre en su propia unidad de systemd con tope de
memoria, de uno en uno. El karaoke de la Fase 5 tiene que caber en 3 GB por la misma razón.
