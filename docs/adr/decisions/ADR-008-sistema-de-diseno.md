# ADR-008: Material 3 compartido con NB Books y color por portada

**Fecha:** 2026-10-29
**Estado:** Aceptado
**Enmendado:** 2026-10-29, por Nathan: NB Sound tiene su propia apariencia. Ver [la enmienda](#enmienda-del-2026-10-29-la-apariencia-de-nb-sound)

## Contexto

NB Sound tiene su propio sistema de temas: 63 paletas con nombre (`acero_azul`, `aurora_boreal`, `lava`…) y **un
logo por cada una**. NB Books adoptó Material 3 con `m3-svelte` (su ADR-014), tokens `--m3c-*` generados por
`scripts/generar-paletas.mjs` y Material Color Utilities.

## Decisión

* NB Sound usa el mismo sistema que NB Books: `m3-svelte`, los mismos tokens, el mismo generador de paletas y las
  mismas reglas de interfaz (sin colores literales, sin desenfoques en cromo permanente, sin `will-change`, nada que
  se anime en reposo, ningún `:hover` que desplace la caja, iconos SVG y nunca emojis).
* **Color por portada:** al cambiar de álbum, Rust extrae el color semilla de la portada con `material-colors`
  (port en Rust de Material Color Utilities, MIT/Apache-2.0), genera el esquema claro y oscuro, y lo guarda en la
  base por álbum. Se calcula una vez por portada, nunca en el webview. La interfaz cambia de esquema con una sola
  transición corta; en reposo no se anima nada. El sistema tonal de Material 3 garantiza el contraste.
* Se puede desactivar ("color por portada") y elegir un acento fijo.
* La barra de progreso interpola la posición con `requestAnimationFrame` a partir de los eventos de estado del
  motor (reproducir, pausar, seek, duración), solo mientras suena y la ventana es visible. El puente no lleva
  eventos de posición a 30 o 60 Hz.
* Las listas largas se virtualizan con la solución que NB Books ya midió con 152.080 elementos, no con una librería
  nueva.

## Consecuencias

- **Positivas:** las dos aplicaciones comparten técnica y guardianes; NB Sound gana los guardianes de interfaz de
  NB Books desde el primer día.
- **Negativas:** traducir cada tema a los tokens de Material obliga a completar los que el tema no define.
- **Riesgos:** una portada con colores apagados da un esquema gris. `material-colors` puntúa los colores por croma,
  y si ninguno supera el umbral se usa el acento elegido.

## Enmienda del 2026-10-29: la apariencia de NB Sound

**Decidido por Nathan:** "No estamos copiando NB Books". NB Books aporta método, estructura, guardianes y la
técnica de Material 3; **la apariencia y el comportamiento de cada pantalla son los de NB Sound**.

En consecuencia, lo de arriba cambia en cuatro puntos:

* **Los 63 temas son temas completos**, no solo acentos: cada uno traduce sus colores (`fondo`, `superficie`,
  `texto`, `acento`…) a los tokens `--m3c-*`. El color por portada es una opción, no la norma.
* **La tipografía la elige el usuario** (`ui_font_family`; de fábrica, Inter). Para no depender de las fuentes del
  sistema, las cinco que se ofrecen viajan dentro de la aplicación con su licencia.
* **Las listas son continuas**, no páginas como en NB Books. F0.4.7 midió una ventana virtual de alto
  fijo con bloques alineados sin un solo fotograma largo con 100.000 filas (P9, cerrada).
* **Enmienda del 2026-11-01 (Nathan, DIS-02): un logo por tema.** Sin ellos, la marca naranja quedaba en los 62
  temas que no lo son. Los 63 viven en `static/logos/logo_<tema>.png`, a 208 px (el doble de lo que se pintan); la
  barra lateral elige el del tema y, si falta, usa `static/logo.png`.

