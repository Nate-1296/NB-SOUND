<!--
Plantilla de Pull Request para NB SOUND.
Borra las secciones que no apliquen a tu cambio.
-->

## Resumen

<!-- En 1 a 3 frases: qué hace este PR y por qué. -->

## Tipo de cambio

<!-- Marca con [x] el que corresponda. Debe coincidir con el prefijo del commit. -->

- [ ] `feat`: nueva funcionalidad
- [ ] `fix`: corrección de bug
- [ ] `refactor`: refactor sin cambio funcional
- [ ] `docs`: solo documentación
- [ ] `test`: tests nuevos o ajustados
- [ ] `chore`: mantenimiento (build, CI, dependencias)

## Issue relacionado

<!-- Para cerrar automáticamente al mergear, usa `Closes #N`. Si no hay issue, deja en blanco. -->

Closes #

## Cambios principales

<!-- Lista breve. No expandas archivo por archivo; resalta lo conceptual. -->

-
-

## Plan de pruebas

<!-- Cómo verificaste que el cambio funciona y no rompe nada. -->

- [ ] `pytest -q` pasa localmente
- [ ] Probé manualmente en (marca lo aplicable): Linux / macOS / Windows
- [ ] Smoke test de QML pasa, si tocaste la UI

## Capturas o evidencia

<!-- Para cambios visibles en UI o resultados notables, agrega capturas o snippets. -->

## Checklist

- [ ] Sigo las convenciones de [`CONTRIBUTING.md`](../blob/main/CONTRIBUTING.md)
- [ ] El commit usa prefijo *conventional commits* (`feat:`, `fix:`, etc.)
- [ ] Añadí tests para servicios o capas de datos modificadas
- [ ] No introduje lógica de negocio en QML ni acceso directo a SQLite desde la UI
- [ ] No expongo claves de API, paths privados ni datos personales en el código o en los logs
- [ ] Acepto distribuir esta contribución bajo **GPL-3.0-or-later**
