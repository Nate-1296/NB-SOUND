# ADR-010: Licencia del código y de los modelos

**Fecha:** 2026-10-29
**Estado:** Aceptado

## Contexto

* NB Sound se publica bajo **GPL-3.0** (`LICENSE`); NB Books, bajo Apache-2.0.
* **Essentia**, la librería, es AGPL-3.0 para uso no comercial. Con [ADR-002](./ADR-002-sin-python.md) la V2 ya no
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
  `THIRD_PARTY_LICENSES.md` y en Ajustes > Acerca de. Mientras NB Sound sea gratuito y no comercial, es conforme.
* **Si algún día NB Sound fuera comercial**, el agregado de análisis exige licencia del MTG o sustituir los modelos.
  Queda registrado en [preguntas abiertas](../../contextual/open-questions/README.md), P3.
* `cargo-deny` rechaza dependencias con licencias fuera de la política, igual que en NB Books.

## Consecuencias

- **Positivas:** sin cambios legales; la restricción de los modelos queda aislada en un agregado opcional.
- **Negativas:** el análisis profundo no puede formar parte de un producto comercial sin negociar.
- **Riesgos:** que el MTG cambie los términos. Afecta a un agregado, no a la aplicación.
