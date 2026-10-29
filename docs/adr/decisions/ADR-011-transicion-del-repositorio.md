# ADR-011: Transición del repositorio: la V1 congelada en `legado/`, la V2 en la raíz

**Fecha:** 2026-10-29
**Estado:** Aceptado

## Contexto

El repositorio `Nate-1296/NB-SOUND` tiene una sola rama, `main`, y debe seguir así. La V1 está etiquetada hasta
`v1.1.16` y es la aplicación que se usa a diario. La V2 necesita la raíz con la estructura de NB Books
(`package.json`, `src/`, `src-tauri/`, `scripts/`, `e2e/`), y la V1 ocupa la raíz con `main.py`, `tests/` y sus
paquetes.

## Alternativas consideradas

1. **Repositorio nuevo para la V2.** Rechazada: pierde la historia y separa las respuestas doradas, que se graban
   de la V1, del código que las usa.
2. **Rama `v2`.** Rechazada: solo debe existir `main`.
3. **Convivir en la raíz.** Rechazada: `tests/`, `README.md` y `.github/` chocarían, y no quedaría claro qué es
   cada cosa.
4. **Mover la V1 a `legado/` y construir la V2 en la raíz.** Aceptada.

## Decisión

* La V1 se congela en `v1.1.16`. **No hay más versiones de la V1**: la instalación actual sigue funcionando, y su
  código se puede recuperar desde la etiqueta.
* En F0.1.3 todo el código de la V1 pasa a `legado/` con un solo `git mv`, y sus pruebas siguen ejecutándose
  desde allí. Sirve para tres cosas: consultar la lógica mientras se porta, grabar las respuestas doradas del
  servidor móvil y medir la paridad.
* Los flujos de GitHub Actions de la V1 se retiran; los de la V2 se escriben en la Fase 0.
* `docs/v1/` conserva la documentación de la V1, solo para consultarla.
* En la Fase 7 (retiro) se borran `legado/` y `docs/v1/`.

## Consecuencias

- **Positivas:** una sola rama, una sola historia, sin ambigüedad sobre qué está vivo.
- **Negativas:** durante la transición el repositorio carga con las dos versiones.
- **Riesgos:** que un defecto grave de la V1 necesite corregirse antes de que la V2 la sustituya. Si pasa, se
  corrige en `legado/` y se publica una `v1.1.17` desde `main`, sin abrir ramas.
