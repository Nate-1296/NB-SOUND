# Registro de decisiones arquitectónicas (ADR)

Un ADR documenta una decisión estructural: contexto, alternativas, decisión y consecuencias. Su valor está en
conservar **por qué** se tomó.

## Reglas

* Los ADR son **inmutables**. Una decisión que cambia no se edita: se escribe un ADR nuevo que supera al anterior,
  y el anterior se marca como superado con un enlace al nuevo.
* Un ADR sin alternativas rechazadas es un comunicado, no una decisión.
* "Aceptado, sujeto a verificación" autoriza a construir el prototipo que lo verifica, no lo que va encima.
* Si una decisión será difícil de revertir dentro de seis meses, necesita un ADR.

## Índice

| ADR | Título | Estado |
|---|---|---|
| [001](./decisions/ADR-001-pila-tecnologica.md) | Pila tecnológica de la V2, la misma que NB Books | Aceptado |
| [002](./decisions/ADR-002-sin-python.md) | Ningún intérprete de Python en tiempo de ejecución | Aceptado, confirmado por F0.4.2–F0.4.4 |
| [003](./decisions/ADR-003-motor-de-audio.md) | Motor de audio embebido en Rust: Symphonia y Kira | Aceptado, confirmado por F0.4.1 |
| [004](./decisions/ADR-004-datos.md) | Rust es dueño de los datos; la V1 se migra sin pérdida | Aceptado |
| [005](./decisions/ADR-005-contrato-movil.md) | El contrato con NB Sound Mobile queda congelado | Aceptado |
| [006](./decisions/ADR-006-agregados.md) | Agregados que se instalan con un clic | Aceptado |
| [007](./decisions/ADR-007-arquitectura-de-informacion.md) | Arquitectura de información: destinos, Por revisar y lo que deja de existir | Aceptado, enmendado el 2026-10-29 |
| [008](./decisions/ADR-008-sistema-de-diseno.md) | Material 3 compartido con NB Books y color por portada | Aceptado |
| [009](./decisions/ADR-009-configuracion-y-red.md) | Configuración mínima, secretos en el llavero y una sola puerta de red | Aceptado |
| [010](./decisions/ADR-010-licencia.md) | Licencia del código y de los modelos | Aceptado |
| [011](./decisions/ADR-011-transicion-del-repositorio.md) | Transición del repositorio: V1 en `legado/`, V2 en la raíz | Aceptado |

Plantilla: [ADR-000-template.md](./ADR-000-template.md).
