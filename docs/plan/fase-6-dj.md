# Fase 6: DJ Privado y A ciegas

> **Objetivo:** portar el DJ Privado (`servicios/dj_privado/`, 17 módulos) y el juego A ciegas
> (`servicios/explorador_ciego/`), con la mezcla en el motor de Kira.
>
> **Prerrequisitos:** Fases 2 y 5.

## Estado de la fase

| Iteración | Estado |
|---|---|
| F6.1.1 Ontología, intención y embeddings (con y sin el agregado de texto) | Hecha: `dj/ontologia.rs` (los 81 conceptos y 24 ejes, transcritos de la V1 en su orden), `dj/intencion.rs` (negaciones, amplificadores y contradicciones, con el JSON de la V1 para `dj_sesiones.intencion`) y `dj/embeddings.rs` (el determinista y MiniLM del agregado de texto, con un WordPiece propio en vez de `tokenizers`). 14 frases y dos vectores dorados de la V1 coinciden. Se conservan cinco contradicciones de la V1 que citan conceptos inexistentes y nunca se disparan. MiniLM con el modelo real, a las pruebas finales |
| F6.1.2 Constructor y planificador de sesiones | Hecha: `dj/narrativa.rs` (fases y objetivos), `dj/planificador.rs` (ejes de cada pista, puntuación, exclusiones, elección por el arco y carga de candidatas desde `rasgos`, `analisis_profundo` y `etiquetas_ambiente`), `dj/constructor.rs` (bloques de 8 y 12, resumen de la V1) y `dj/transiciones.rs` (puntuación Camelot, tempo y energía, y el refinado por intercambios que usa el constructor). El azar es el de Python (`dj/azar.rs`): siete sesiones con semilla son iguales bit a bit a las de la V1. Al guardar rasgos y análisis se derivan las etiquetas de ambiente, que faltaban. La paridad sobre la base migrada, a las pruebas finales |
| F6.1.3 Transiciones y motor de mezcla: `energy_blend`, `eq_kill_bass`, `filter_sweep`, `harmonic_mix` | Hecha: `dj/mezcla.rs` (técnica, puntos de entrada y salida, solapamiento y curvas), dos platos en el motor y `dj/ejecutor.rs` (la puerta de la V1 y las curvas con el reloj del audio). Las cinco técnicas, renderizadas fuera de línea, no hacen clic ni saltan de volumen. El perfil de equipo que decide si hay capas llega con F6.1.4; la escucha, a las pruebas finales |
| F6.1.4 Perfil de hardware y degradación de técnicas | Hecha: `dj/equipo.rs` mide el equipo separando diez segundos con el agregado de karaoke y clasifica como la V1; sin medida o sin agregado, perfil bajo y cuatro técnicas. La medida no se guarda (la migración la descarta). La medición con el modelo real, a las pruebas finales |
| F6.1.5 Narrativa, persistencia, historial y preferencias | Hecha: la narrativa en F6.1.2; `dj/sesiones.rs` (sesiones, pistas, eventos, preferencias y sesión en curso) y `dj/servicio.rs` (empezar, continuar, regenerar, descartar, finalizar, guardar como playlist, retomar, historial y borrar), con las pruebas de integración de la V1 |
| F6.1.6 Vistas: pedir sesión, sesión activa, historial | Pendiente |
| F6.2.1 A ciegas: selectores, pistas y servicio | Pendiente |
| F6.2.2 A ciegas: vista del juego | Pendiente |

## Criterios

* Las pruebas de la V1 del DJ (`test_dj_*`) se traducen y pasan, en especial `test_dj_mix_engine.py` y
  `test_dj_transicion_gate.py`.
* Las transiciones suenan sin clics ni saltos de volumen, comprobado con render fuera de línea (pico y LUFS a corto
  plazo durante el solapamiento) y a oído.
* Con el mismo pedido y la misma semilla, la V2 construye la misma sesión que la V1 sobre la base migrada.
* Sin el agregado de análisis, el DJ funciona con los rasgos básicos y lo dice.

**Puerta de empaquetado.**
