# ADR-010: Licencia del código y de los modelos

**Fecha:** 2026-10-29
**Estado:** Aceptado

## Contexto

* NB Sound se publica bajo **GPL-3.0** (`LICENSE`); NB Books, bajo Apache-2.0.
* **Essentia**, la librería, es AGPL-3.0 para uso no comercial. Con [ADR-002](./ADR-002-sin-python.md) NB Sound ya no
  la incluye.
* **Los modelos de Essentia** se licencian aparte, para uso no comercial: la página de modelos dice CC BY-NC-SA 4.0
  y la de licencias dice CC BY-NC-ND 4.0. Hay licencia propietaria a petición del MTG (UPF). CC 4.0 (sección 2.a.4)
  permite las modificaciones técnicas necesarias para usar la obra en otros formatos, y aclara que no producen
  material adaptado, así que convertirlos a ONNX está permitido en las dos variantes.
* `htdemucs` es MIT; las dependencias de Rust previstas son MIT, Apache-2.0 o MPL-2.0 (Symphonia y mpris-server); el
  `ffmpeg` empaquetado puede ser LGPL o GPL; `songrec` es GPL-3.0 y `shazamio-core`, MIT.

## Decisión

* **El código de NB Sound sigue siendo GPL-3.0-or-later.** Es compatible con todo lo anterior. No hay un plan
  comercial que pida cambiarla, y cambiarla no aporta nada al ecosistema, que se unifica por el producto y no por
  la licencia.
* **El agregado de Análisis musical se distribuye con su licencia propia (CC BY-NC)**, con atribución al MTG en
  `THIRD_PARTY_LICENSES.md` y en Ajustes > Acerca de. Su uso debe cumplir los términos de cada modelo;
  que la aplicación sea gratuita no basta para determinar que un uso sea no comercial.
* **Si algún día NB Sound fuera comercial**, el agregado de análisis exige licencia del MTG o sustituir los modelos.
  La decisión actual queda registrada en [preguntas abiertas](../../contextual/open-questions/README.md), P3.
* `cargo-deny` rechaza dependencias con licencias fuera de la política, igual que en NB Books.

## Consecuencias

- **Positivas:** sin cambios legales; la restricción de los modelos queda aislada en un agregado opcional.
- **Negativas:** el análisis profundo no puede formar parte de un producto comercial sin negociar.
- **Riesgos:** que el MTG cambie los términos. Afecta a un agregado, no a la aplicación.

## Enmienda aceptada: mantener el modelo actual (2026-11-11, P3)

Nathan decide mantener la licencia, los componentes y la distribución actuales. No se migra a Apache-2.0,
no se reescribe el código portado de `songrec` y no se crea una edición institucional en esta etapa.

* El código sigue bajo **GPL-3.0-or-later**, también para su uso en instituciones. La GPL permite cobrar por
  distribución y servicios, pero no añadir una obligación de pago por el mero uso institucional ni retirar
  los derechos que concede la licencia.
* Si se ofrece soporte, despliegue, mantenimiento o formación de pago, sus contratos regularán esos servicios
  respetando la GPL. Esta decisión no pone en marcha una oferta comercial.
* Los modelos del MTG conservan sus condiciones no comerciales. Antes de incluirlos en una oferta comercial,
  se debe obtener una autorización del MTG que cubra el uso y la distribución previstos, o sustituirlos por
  modelos con permisos adecuados y validar sus resultados. Ser una institución educativa o distribuir el
  agregado por separado no elimina esas condiciones.
* Antes de cambiar el modelo de negocio, se revisarán las licencias exactas de los modelos y los derechos de
  los componentes y contribuciones afectados, mediante una nueva decisión documentada.

**P3 queda cerrada por decisión de alcance**, sin cambios en el código, los modelos ni sus licencias.

Referencias: [FAQ de GNU sobre cobro y GPL](https://www.gnu.org/licenses/gpl-faq.html#DoesTheGPLAllowMoney),
[licencias de los modelos del MTG](https://essentia.upf.edu/licensing_information.html) y
[criterio NonCommercial de Creative Commons](https://creativecommons.org/faq/#does-my-use-violate-the-noncommercial-clause-of-the-licenses).
