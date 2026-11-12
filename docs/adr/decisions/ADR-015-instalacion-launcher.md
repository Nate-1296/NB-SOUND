# ADR-015: instalación administrada por NB Launcher

**Fecha:** 2026-11-12
**Estado:** Decisión de implementación bajo la continuación y publicación autorizadas por
Nathan desde NB Launcher; en validación. No modifica el contrato móvil ni los datos.

## Contexto

Instalar una copia por usuario requiere resolver sus recursos locales y evitar que el
actualizador propio modifique binarios simultáneamente con el gestor. El tar de Linux
contiene `usr/bin`, `usr/lib/NB Sound`, iconos y licencias, pero no incluye WebKitGTK/GTK.

## Alternativas

- Dos actualizadores para la misma instalación: rechazado por carreras y autoridad ambigua.
- Guardar datos de Sound dentro del Launcher: rechazado por propiedad y desinstalación.
- Usar variables de entorno para decidir la autoridad: insuficiente al abrir el binario
  fuera del Launcher.
- Sustituir siempre `/usr`: requiere privilegios y afecta instalaciones ajenas; diferido.

## Decisión

Una copia Linux administrada tiene estructura `nb.sound/<sha256>/usr/bin/nb-sound` y marca
`.nb-launcher-managed` junto al ejecutable con bytes `nb-launcher-managed-v1` y LF.
Sound comprueba ambas condiciones antes de abrir sus datos. Si la marca existe pero es
inválida, no asume una instalación independiente ni actualiza binarios por su cuenta.

El proceso conserva un bloqueo compartido sobre `nb.sound/running.lock` durante toda su
vida. El gestor crea ese archivo y nunca lo elimina; requiere bloqueo exclusivo para
mutar binarios. Sound resuelve ONNX en `usr/lib/NB Sound` de su misma versión; `fpcalc`
conserva su resolución junto al ejecutable. No necesita secretos ni acceso a configuración
privada del Launcher.

La consulta del actualizador propio devuelve `INSTALLATION_MANAGED` antes de cualquier
petición de red; la interfaz explica «Esta instalación se actualiza desde NB Launcher».
La instalación independiente mantiene su actualizador, consentimiento y comportamiento.
No se añade dependencia de ejecución; marca y bloqueo son un contrato de instalación.

## Consecuencias y validación

Launcher controla sus binarios y Sound conserva rutas de datos, migraciones y dominio.
Quitar una instalación no borra biblioteca ni copias. Una actualización no revierte datos.
Las pruebas verifican estructura, recursos y exclusión mutua; la release y su ejecución
real se comprueban antes de anunciar compatibilidad. No se afirma instalación en máquina
limpia ni soporte de este formato en Windows/macOS.
