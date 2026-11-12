# Publicación del catálogo de Launcher

Fecha: 2026-11-12. Estado: catálogo firmado publicado y consumido por Launcher; renovación semanal en validación.
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
El resultado local inicial no tenía firma editorial; la publicación autenticada posterior se registra abajo.
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
directorio de trabajo editorial del runner, fuera del cache de Cargo. El consumidor conserva su anclaje
público; no confía en una clave proporcionada por estos archivos. La autoridad se limita
a Sound y su repositorio. La caducidad normal es de 14 días.

La primera ejecución del workflow y el consumo firmado real se registran abajo. Se ejecutó
`gh workflow run catalogo-launcher.yml --field tag=v2.1.3` contra el repo; omitir el tag
selecciona la release estable más reciente, igual que la renovación programada.

## Validación de la definición CI

La primera definición (`316d0a2`) no se ejecutó: `runner.temp` no está disponible en
el entorno de un job. Actionlint 1.7.12 reprodujo exactamente esa restricción. El staging
usa ahora una ruta editorial propia fuera del cache de Cargo. Windows detectó además
un `mut` usado únicamente bajo Unix en el arnés; se corrigió sin tocar código de la app.
Actionlint comprobó localmente todas las definiciones y se añade a CI con versión y
SHA-256 fijados. La CI corregida comprobó ambas correcciones en los tres sistemas, según el registro siguiente.

## Publicación y consumo reales

La CI corregida `43313486799` pasó íntegra en los tres sistemas, incluido actionlint.
El workflow editorial `43315321548` terminó correctamente y publicó los dos archivos
en Sound 2.1.3. El catálogo emitido en Unix `1794520710` tiene SHA-256
`4dd9bcfdf600d734dd5ffae5b25af0c522af56954b01dfb3e037f154f04ab0c9`.
Launcher verificó su firma real, descargó JSON/firma por HTTPS y aceptó/releyó su índice
privado con una oferta vigente 2.1.3. No se modificaron los siete paquetes ni `latest.json`.

Se define una renovación semanal de la release estable más reciente para evitar caducidad
sin publicar binarios nuevos. Usa el mismo productor y anclaje, con tag validado y salida
de firma limitada al paso correspondiente. La primera ejecución de esta variante está
pendiente; no se presenta el cron futuro como ejecución observada. GitHub puede desactivar
workflows programados en repositorios inactivos: la aplicación conserva sus instalaciones
y declara que no pudo comprobar novedades si no obtiene metadatos vigentes.
