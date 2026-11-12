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
| [001](./decisions/ADR-001-pila-tecnologica.md) | Pila tecnológica de NB Sound, la misma que NB Books | Aceptado |
| [002](./decisions/ADR-002-sin-python.md) | Ningún intérprete de Python en tiempo de ejecución | Aceptado, confirmado por F0.4.2–F0.4.4 |
| [003](./decisions/ADR-003-motor-de-audio.md) | Motor de audio embebido en Rust: Symphonia y Kira | Aceptado, confirmado por F0.4.1 |
| [004](./decisions/ADR-004-datos.md) | Rust es dueño de los datos | Aceptado |
| [005](./decisions/ADR-005-contrato-movil.md) | El contrato con NB Sound Mobile queda congelado | Aceptado |
| [006](./decisions/ADR-006-agregados.md) | Agregados que se instalan con un clic | Aceptado |
| [007](./decisions/ADR-007-arquitectura-de-informacion.md) | Arquitectura de información: destinos, Por revisar y lo que deja de existir | Aceptado, enmendado el 2026-10-29 y el 2026-11-04 |
| [008](./decisions/ADR-008-sistema-de-diseno.md) | Material 3 con los 63 temas de NB Sound | Aceptado, enmendado el 2026-10-29 y el 2026-11-04 |
| [009](./decisions/ADR-009-configuracion-y-red.md) | Configuración mínima, secretos en el llavero y una sola puerta de red | Aceptado |
| [010](./decisions/ADR-010-licencia.md) | Licencia del código y de los modelos | Aceptado |
| [012](./decisions/ADR-012-modo-fiesta.md) | Modelo de confianza y aislamiento del modo fiesta | Aceptado |
| [013](./decisions/ADR-013-launcher-frecuencia.md) | Frecuencia de respaldo como capacidad compartida | Aceptado el 2026-11-11; integración en construcción |
| [014](./decisions/ADR-014-renovacion-launcher.md) | Renovación privada del enlace de Launcher | Implementado y comprobado en Linux bajo la continuación autorizada |
| [015](./decisions/ADR-015-instalacion-launcher.md) | Instalación administrada por NB Launcher | Tar Linux 2.1.3 publicado y validado; otros formatos/plataformas pendientes |
| [016](./decisions/ADR-016-catalogo-launcher.md) | Catálogo firmado para Launcher | Productor/editorial en validación; sin cambios del runtime |

Plantilla: [ADR-000-template.md](./ADR-000-template.md).
