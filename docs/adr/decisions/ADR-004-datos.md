# ADR-004: Rust es dueño de los datos

**Fecha:** 2026-10-29
**Estado:** Aceptado

## Contexto

La base de NB Sound guarda la biblioteca, las playlists, el historial, el karaoke, el DJ, los teléfonos
emparejados y el estado de la sincronización. Una instalación real, medida el 2026-10-29: unas 2.400 pistas, 1.400
álbumes, 430 artistas, 56 playlists, 3.200 entradas de historial y 12 teléfonos emparejados.

**441 MB de esos 464 MB son la columna `raw_output_json` de `track_deep_audio_features`**: 1,1 MB por pista para
407 pistas, porque se guardan las salidas crudas de los modelos, fotograma a fotograma, como texto JSON. Con la
biblioteca analizada entera serían unos 2,6 GB; con 20.000 pistas, más de 20 GB. Es la regla de NB Books de que lo
derivado nunca pesa más que lo que describe, incumplida.

El documento de visión dejaba SQLite en Python. Con [ADR-002](./ADR-002-sin-python.md) ya no hay Python, pero la
pregunta seguiría siendo la misma: listas virtualizadas, cola, listas inteligentes y estadísticas no pueden
atravesar dos procesos.

## Decisión

1. **Rust es el único dueño del esquema y del acceso**: `rusqlite` con `r2d2`, WAL, `busy_timeout`, claves
   foráneas activas y migraciones versionadas en `src-tauri/migrations/`, como NB Books.
2. **Toda transacción de escritura se abre con `BEGIN IMMEDIATE`.** Es la regla que a NB Books le costó 1.207
   documentos aprender. Lo vigila `check-transacciones`.
3. **Un esquema normalizado** y con índices medidos.
4. **El análisis se guarda resumido**: embeddings agregados como `BLOB` de `f32` (por ejemplo, 1.280 dimensiones de
   EffNet = 5 KB) y probabilidades por clase. Las salidas crudas no se guardan. Presupuesto: **menos de 16 KB de
   análisis por pista**, vigilado por una prueba.
5. **Identificadores estables.** Los `id` de pista, álbum, artista y playlist no cambian nunca, porque NB Sound
   Mobile los tiene guardados en su base local ([ADR-005](./ADR-005-contrato-movil.md)). Lo mismo para
   `sync_version`, las tumbas (`sync_tombstones`) y los `device_token`.
6. **Lo operativo no se guarda**: índices de manifiestos, colas de trabajos terminados o ejecuciones de análisis
   se recalculan o se descartan.

## Alternativas consideradas

* **Un ORM o acceso desde el webview.** Rechazada: el dueño de los datos tiene que ser uno solo, y las reglas de
  transacción no se pueden imponer desde la interfaz.
* **Guardar las salidas crudas del análisis.** Rechazada: multiplica la base por veinte sin que nadie las lea.

## Consecuencias

- **Positivas:** una base pequeña (unos 25 MB en la instalación real); escrituras sin `SQLITE_BUSY`; el móvil
  recibe siempre los mismos identificadores.
- **Negativas:** cada cambio de esquema es una migración con su prueba.
- **Riesgos:** una migración mal escrita. Se vigila con las pruebas de esquema y la copia de seguridad.