# Bibliotecas NB compartidas

Exportación reproducible de nb-protocol y nb-capability desde NB Launcher.
Fuente canónica: nb-launcher-workspace. Licencia: Apache 2.0, incluida en LICENSE.

No editar estos archivos manualmente. Regenerar desde scripts/shared-export.mjs
del proyecto canónico y revisar el cambio del bundle_id.

Verificar desde cualquier carpeta con node <ruta-del-bundle>/verify.mjs.
No requiere el checkout de Launcher para verificar o compilar sus dependencias.
La aplicación consumidora fija sus versiones resueltas en su propio Cargo.lock.
Cargo.lock y target locales son salidas de desarrollo excluidas del sello.

El manifiesto detecta deriva y corrupción; no es una firma ni prueba de procedencia.
