# Fase 6: DJ Privado y A ciegas

> **Objetivo:** portar el DJ Privado (`servicios/dj_privado/`, 17 módulos) y el juego A ciegas
> (`servicios/explorador_ciego/`), con la mezcla en el motor de Kira.
>
> **Prerrequisitos:** Fases 2 y 5.

## Estado de la fase

| Iteración | Estado |
|---|---|
| F6.1.1 Ontología, intención y embeddings (con y sin el agregado de texto) | Hecha: `dj/ontologia.rs`, `dj/intencion.rs` y `dj/embeddings.rs` (el determinista y MiniLM del agregado de texto, con un WordPiece propio en vez de `tokenizers`). 14 frases y dos vectores dorados coinciden. Se conservan cinco contradicciones que citan conceptos inexistentes y nunca se disparan. MiniLM con el modelo real, a las pruebas finales |
| F6.1.2 Constructor y planificador de sesiones | Hecha: `dj/narrativa.rs` (fases y objetivos), `dj/planificador.rs` (ejes de cada pista, puntuación, exclusiones, elección por el arco y carga de candidatas desde `rasgos`, `analisis_profundo` y `etiquetas_ambiente`), `dj/constructor.rs` y `dj/transiciones.rs` (puntuación Camelot, tempo y energía, y el refinado por intercambios que usa el constructor). El azar es el de Python (`dj/azar.rs`): siete sesiones con semilla son iguales bit a bit a sus doradas. Al guardar rasgos y análisis se derivan las etiquetas de ambiente, que faltaban. |
| F6.1.3 Transiciones y motor de mezcla: `energy_blend`, `eq_kill_bass`, `filter_sweep`, `harmonic_mix` | Hecha: `dj/mezcla.rs` (técnica, puntos de entrada y salida, solapamiento y curvas), dos platos en el motor y `dj/ejecutor.rs`. Las cinco técnicas, renderizadas fuera de línea, no hacen clic ni saltan de volumen. El perfil de equipo que decide si hay capas llega con F6.1.4; la escucha, a las pruebas finales |
| F6.1.4 Perfil de hardware y degradación de técnicas | Hecha: `dj/equipo.rs` mide el equipo separando diez segundos con el agregado de karaoke y clasifica; sin medida o sin agregado, perfil bajo y cuatro técnicas. La medida no se guarda (la migración la descarta). La medición con el modelo real, a las pruebas finales |
| F6.1.5 Narrativa, persistencia, historial y preferencias | Hecha: la narrativa en F6.1.2; `dj/sesiones.rs` (sesiones, pistas, eventos, preferencias y sesión en curso) y `dj/servicio.rs` (empezar, continuar, regenerar, descartar, finalizar, guardar como playlist, retomar, historial y borrar), con las pruebas de integración |
| F6.1.6 Vistas: pedir sesión, sesión activa, historial | Hecha: la sesión suena en el reproductor único (`reproductor/dj.rs`) con la cola del usuario en pausa; `dj/director.rs` la sigue construyendo mientras suena; nueve comandos y la vista con pedir, sesión y historial, que avisa cuando no hay análisis. El uso real, a las pruebas finales |
| F6.2.1 A ciegas: selectores, pistas y servicio | Hecha: `a_ciegas/selectores.rs` (los cuatro modos y sus cuentas), `a_ciegas/indicios.rs` (los indicios y la comprobación tolerante con `SequenceMatcher`) y `a_ciegas/mod.rs` (la ronda, que solo entrega lo revelado). Las pruebas, traducidas |
| F6.2.2 A ciegas: vista del juego | Hecha: el fragmento suena a ciegas por el reproductor (`reproductor/fragmento.rs`), sin que la barra, los controles del sistema ni el móvil digan qué es, y la vista juega la ronda entera. La partida real, a las pruebas finales |

## Criterios

* Las pruebas del DJ (`test_dj_*`) se traducen y pasan, en especial `test_dj_mix_engine.py` y
  `test_dj_transicion_gate.py`.
* Las transiciones suenan sin clics ni saltos de volumen, comprobado con render fuera de línea (pico y LUFS a corto
  plazo durante el solapamiento) y a oído.
* Con el mismo pedido y la misma semilla, NB Sound construye siempre la misma sesión.
* Sin el agregado de análisis, el DJ funciona con los rasgos básicos y lo dice.

**Puerta de empaquetado.**
