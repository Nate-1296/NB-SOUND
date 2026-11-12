# Publicación del catálogo de Launcher

Fecha: 2026-11-12. Estado: productor comprobado localmente; primera firma/publicación CI pendiente.
Decisión: [ADR-016](../adr/decisions/ADR-016-catalogo-launcher.md).

## Herramienta editorial

El ejemplo Cargo `publicar_catalogo` verifica los siete formatos firmados existentes de
una release estable. Rechaza entradas ausentes, firmas ajenas, bytes alterados, hashes
duplicados y versiones que todavía no implementan el contrato administrado. Genera un
JSON de esquema 1, con emisión/caducidad y metadatos exactos, sin sobrescribir una salida.
No inicia Sound ni accede a su biblioteca. No es otro binario del instalador.

Se ejecutó localmente sobre los siete paquetes auténticos de Sound 2.1.3; los metadatos
resultantes coincidieron exactamente con el índice revisado de Launcher. Sus seis pruebas
comprobaron inventario, firmas, alteraciones, claves ajenas, versiones y duplicados.
El resultado local todavía no tiene una firma editorial: no se anuncia como catálogo operativo.
`pnpm verify`, formato y Clippy de todos los targets/features pasaron. La suite Rust ejecutó
652 pruebas y omitió 25; la prueba de búsqueda obligatoria se ejecutó y pasó aparte.
Las seis pruebas del productor están incluidas en esa suite, no solo en una ejecución manual.

## Workflow y confianza

`.github/workflows/catalogo-launcher.yml` se activa al publicar una release estable o
mediante `workflow_dispatch` con su tag. Recupera la configuración de ese tag desde Git,
descarga sus artefactos publicados, verifica/genera el JSON, lo firma con el secreto Tauri
existente y verifica otra vez la firma antes de subir únicamente JSON y `.sig`.
No modifica paquetes, `latest.json`, datos ni configuración de la aplicación.

La clave privada aparece solo en el entorno del paso de firma. El staging vive en el
directorio temporal del runner, fuera del cache de Cargo. El consumidor conserva su anclaje
público; no confía en una clave proporcionada por estos archivos. La autoridad se limita
a Sound y su repositorio. La caducidad normal es de 14 días.

La primera ejecución del workflow y el consumo firmado real se registrarán aquí. El
comando previsto para refrescar una release publicada, todavía sin ejecutar en esta
iteración, es `gh workflow run catalogo-launcher.yml --field tag=v2.1.3` dentro del repo.
