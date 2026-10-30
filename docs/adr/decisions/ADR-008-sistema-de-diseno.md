# ADR-008: Material 3 compartido con NB Books y color por portada

**Fecha:** 2026-10-29
**Estado:** Aceptado
**Enmendado:** 2026-10-29, por Nathan: la V2 se parece a la V1, no a NB Books. Ver [la enmienda](#enmienda-del-2026-10-29-la-v2-se-parece-a-la-v1)

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
  **colores semilla** para el acento fijo. Los 60 PNG del logo, uno por paleta, desaparecen: queda un solo
  logo, el de la V1 (`logo_512.png`), que es una ilustración y no admite teñirse sin redibujarla.
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

## Enmienda del 2026-10-29: la V2 se parece a la V1

**Decidido por Nathan:** "No estamos copiando NB Books. Estamos reescribiendo NB Sound y por ello se debe parecer a
lo que teníamos antes; esto aplica para cualquier vista". NB Books aporta método, estructura, guardianes y la
técnica de Material 3; **la apariencia y el comportamiento de cada pantalla salen de la V1** (capturas en
`legado/assets/screens/`, QML en `legado/ui/qml/vistas/`). Las únicas excepciones son los rediseños pedidos
explícitamente en ADR-007 (Importar, Preparar Karaoke, Ajustes, Estado del Sistema y el modo Pro/Simple).

En consecuencia, lo de arriba cambia en cuatro puntos:

* **Los 63 temas de la V1 vuelven a ser temas completos**, no solo acentos: cada uno traduce sus colores (`fondo`,
  `superficie`, `texto`, `acento`…) a los tokens `--m3c-*`, de modo que la V2 se ve con el mismo tema que el
  usuario tenía. El importador trae el tema elegido (en la instalación real, `sangre_dragon`). El color por portada
  sigue siendo una opción, no la norma.
* **La tipografía la elige el usuario, como en la V1** (`ui_font_family`; en la instalación real, Fira Sans; de
  fábrica, Inter). Para no depender de las fuentes del sistema, las familias que se ofrecen viajan dentro de la
  aplicación con su licencia.
* **Las listas son continuas, como en la V1**, no páginas como en NB Books. F0.4.7 midió una ventana virtual de alto
  fijo con bloques alineados sin un solo fotograma largo con 100.000 filas (P9, cerrada).
* La carcasa de la Fase 0 (clara, con acento cian) es provisional: F2.2.1 la ajusta a la disposición de la V1.

