# Fase 6: DJ Privado y A ciegas

> **Objetivo:** portar el DJ Privado (`servicios/dj_privado/`, 17 módulos) y el juego A ciegas
> (`servicios/explorador_ciego/`), con la mezcla en el motor de Kira.
>
> **Prerrequisitos:** Fases 2 y 5.

## Estado de la fase

| Iteración | Estado |
|---|---|
| F6.1.1 Ontología, intención y embeddings (con y sin el agregado de texto) | Pendiente |
| F6.1.2 Constructor y planificador de sesiones | Pendiente |
| F6.1.3 Transiciones y motor de mezcla: `energy_blend`, `eq_kill_bass`, `filter_sweep`, `harmonic_mix` | Pendiente |
| F6.1.4 Perfil de hardware y degradación de técnicas | Pendiente |
| F6.1.5 Narrativa, persistencia, historial y preferencias | Pendiente |
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
