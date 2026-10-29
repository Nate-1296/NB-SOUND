# ADR-008: Material 3 compartido con NB Books y color por portada

**Fecha:** 2026-10-29
**Estado:** Aceptado

## Contexto

La V1 tiene su propio sistema de temas: unas 60 paletas con nombre (`acero_azul`, `aurora_boreal`, `lava`…) y **un
PNG del logo por cada paleta** en `ui/qml/assets/logo/`. NB Books adoptó Material 3 con `m3-svelte` (su ADR-014),
tokens `--m3c-*` generados por `scripts/generar-paletas.mjs` y Material Color Utilities.

## Decisión

* NB Sound usa el mismo sistema que NB Books: `m3-svelte`, los mismos tokens, el mismo generador de paletas y las
  mismas reglas de interfaz (sin colores literales, sin desenfoques en cromo permanente, sin `will-change`, nada que
  se anime en reposo, ningún `:hover` que desplace la caja, iconos SVG y nunca emojis).
* **Color por portada:** al cambiar de álbum, Rust extrae el color semilla de la portada con `material-colors`
  (port en Rust de Material Color Utilities, MIT/Apache-2.0), genera el esquema claro y oscuro, y lo guarda en la
  base por álbum. Se calcula una vez por portada, nunca en el webview. La interfaz cambia de esquema con una sola
  transición corta; en reposo no se anima nada. El sistema tonal de Material 3 garantiza el contraste.
* Se puede desactivar ("color por portada") y elegir un acento fijo. Las 60 paletas de la V1 pasan a ser
  **colores semilla** para el acento fijo; los 60 PNG desaparecen y el logo es un SVG teñido por los tokens.
* La barra de progreso interpola la posición con `requestAnimationFrame` a partir de los eventos de estado del
  motor (reproducir, pausar, seek, duración), solo mientras suena y la ventana es visible. El puente no lleva
  eventos de posición a 30 o 60 Hz.
* Las listas largas se virtualizan con la solución que NB Books ya midió con 152.080 elementos, no con una librería
  nueva.

## Consecuencias

- **Positivas:** las dos aplicaciones se ven y se comportan como una familia; NB Sound gana los guardianes de
  interfaz de NB Books desde el primer día.
- **Negativas:** se pierden las paletas de la V1 como temas completos; quedan como acentos.
- **Riesgos:** una portada con colores apagados da un esquema gris. `material-colors` puntúa los colores por croma,
  y si ninguno supera el umbral se usa el acento elegido.
