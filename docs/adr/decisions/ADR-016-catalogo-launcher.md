# ADR-016: metadatos de distribución para NB Launcher

**Fecha:** 2026-11-12
**Estado:** Decisión de implementación bajo la continuación autorizada de Launcher;
productor y publicación de metadatos todavía en validación.

## Contexto

Launcher verifica los paquetes de Sound, pero su índice incorporado no permite descubrir
una release posterior sin actualizar el hub. El `latest.json` existente no firma todos sus
campos. Se necesita autenticar propietario, versión, plataforma, tamaño, hash y contrato.

## Alternativas consideradas

- Confiar solo en HTTPS o el manifiesto actual: no autentica todos los metadatos.
- Entregar la clave privada al Launcher: innecesario y rechazado.
- Una clave nueva para el mismo propietario: duplica distribución/rotación sin aportar
  separación de autoridad; se conserva la clave editorial que ya firma los paquetes.
- Añadir otro ejecutable al producto: innecesario; el productor es un ejemplo de Cargo
  de desarrollo, fuera de los binarios que Tauri instala y del puente de la aplicación.

## Decisión

Sound publica `launcher-catalog.json` y su firma Tauri/minisign en su propia release.
El esquema 1 identifica solo `nb.sound`, su repositorio, una versión estable, emisión,
caducidad y sus siete artefactos conocidos. El tar compatible declara `sound_linux_v1`.
La clave no autoriza otras apps. Rotarla requiere actualizar los anclajes del consumidor.

El productor comprueba las siete firmas y tamaños sobre los bytes reales antes de generar
metadatos. Reutiliza versiones ya resueltas: declara `base64` 0.22.1 como dependencia
solo de desarrollo (MIT/Apache-2.0), sin añadir dependencias al runtime. CI firma el resultado con su secreto
editorial y verifica la firma antes de subirlo. La herramienta no contiene secretos ni
accede a datos personales. La caducidad normal es de 14 días; refrescarla no modifica los
paquetes ni reescribe la aplicación. El consumidor debe protegerse contra rollback.

## Consecuencias y validación

No cambia el ejecutable publicado, su actualizador, sus salidas de red ni el contrato móvil.
La herramienta y el workflow son de publicación: usan archivos descargados por CI y la
configuración del tag de la release. No se incluye otro programa dentro del instalador.
Las pruebas deben rechazar paquetes alterados, firmas ajenas, inventarios incompletos y
configuración/versiones inválidas. La verificación de Sound y una publicación de metadatos
firmados con consumo real en Launcher preceden a anunciar esta integración como operativa.
