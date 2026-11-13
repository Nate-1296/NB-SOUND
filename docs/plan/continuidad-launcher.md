# Pausa y limpieza del trabajo de integración con Launcher

Fecha: 2026-11-13. Estado: pausa solicitada por Nathan, sin cambios nuevos de runtime.

## Código guardado

Sound conserva la release publicada 2.1.3 y sus contratos actuales. Los últimos cambios
del trabajo anterior ya estaban subidos: `6262a6c` corrigió la sincronización del ensayo
de cola; `0478c77` registró su CI completa en Linux, Windows y macOS. La evidencia está en
[validación de Launcher](../engineering/validacion-launcher-2.1.3.md).

Antes de esta limpieza, el árbol de trabajo estaba limpio y sincronizado con `origin/main`.
No había implementación pendiente de guardar. Esta actualización añade únicamente la
nota de pausa y su referencia en la bitácora; no exige otra release de la aplicación.

## Limpieza comprobada

El checkout ocupaba aproximadamente 13 GB. Casi todo estaba en `src-tauri/target`,
especialmente objetos y dependencias de compilación. Se retiraron solo directorios
generados e ignorados por Git, comprobando previamente que no contenían archivos versionados:

- `src-tauri/target`: compilaciones, dependencias e incrementales de Cargo.
- `node_modules`: dependencias y caché local del frontend.
- `build` y `.svelte-kit`: salidas generadas del frontend.
- `src-tauri/binarios`: descargas nativas reproducibles con los hashes del manifiesto.
- `src-tauri/gen`: esquemas y metadatos generados por Tauri.

El checkout quedó en aproximadamente 66 MiB. Se conservan fuentes, lockfiles, recursos
versionados, historial Git y la exportación sellada `src-tauri/vendor/nb-shared`.
No se borraron archivos versionados ni se modificaron la instalación personal, la biblioteca,
las bases de datos, preferencias, respaldos o cachés externas de la aplicación.
No había procesos de Sound ni compilaciones activas de este trabajo al limpiar.

Después de retirar los resultados pasaron `node scripts/check-docs.mjs`,
`node scripts/check-shared.mjs` y `cargo fmt --manifest-path src-tauri/Cargo.toml --all -- --check`.
No se reconstruyó ni se repitió la suite de runtime porque no cambió código y el objetivo
era retirar las compilaciones. Los resultados completos anteriores conservan sus límites.

## Dónde retomar

La integración vigente sigue usando `--nb-launcher` y el bootstrap privado de arranque.
No hay adhesión a una instancia independiente ni autorización persistente implementadas
en Sound. El propietario sigue conservando frecuencia, revisiones, datos y validación.
NB Sound Mobile no se modifica.

Nathan eligió que la autorización futura se recuerde entre sesiones y se pueda revocar
persistentemente desde Sound. Launcher dejó un núcleo experimental de identidad y desafíos,
con sus pruebas locales, en el checkpoint `21a926f`; no se incorporó a este proyecto.
El [punto de continuidad de Launcher](../../../NB%20Launcher/docs/continuidad.md) describe
esa decisión y los pendientes exactos.

Al reanudar, definir primero el contrato y ADR propios de Sound para el canal de adhesión,
consentimiento, registro transaccional de concesiones y cierre de sesiones revocadas.
Después adaptar el propietario, regenerar la exportación compartida desde su fuente
canónica y comprobar dos procesos reales y sus interfaces antes de anunciar la función.
No editar manualmente el vendor actual ni sustituirlo solo porque haya fuentes nuevas.
La nueva implementación requerirá sus verificaciones y release correspondientes.

Para volver a compilar este checkout será necesario reinstalar dependencias con
`pnpm install --frozen-lockfile`, recuperar los binarios mediante `pnpm binarios` y
seguir la verificación documentada. Esos comandos reconstruyen lo retirado; no se han
ejecutado de nuevo durante esta limpieza. La pausa sigue vigente.
