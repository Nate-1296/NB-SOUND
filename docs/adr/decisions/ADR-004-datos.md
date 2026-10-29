# ADR-004: Rust es dueño de los datos; la V1 se migra sin pérdida

**Fecha:** 2026-10-29
**Estado:** Aceptado

## Contexto

La base de la V1 (`~/.local/share/nb_sound/biblioteca/nb_sound.sqlite3`) tiene 30 tablas. La instalación real,
medida el 2026-10-29: 2.397 pistas, 1.421 álbumes, 434 artistas, 56 playlists, 3.225 entradas de historial, 323
trabajos de karaoke, 12 dispositivos móviles emparejados y **464 MB**.

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
   documentos aprender; la V1 abre `BEGIN` a secas (`db/conexion.py`, línea 639). Lo vigila `check-transacciones`.
3. **Esquema V2 nuevo**, no una copia del de la V1. Se diseña a partir del inventario de la V1, normalizado y con
   índices medidos.
4. **El análisis se guarda resumido**: embeddings agregados como `BLOB` de `f32` (por ejemplo, 1.280 dimensiones de
   EffNet = 5 KB) y probabilidades por clase. Las salidas crudas no se guardan. Presupuesto: **menos de 16 KB de
   análisis por pista**, vigilado por una prueba.
5. **Identificadores estables.** Los `id` de pista, álbum, artista y playlist de la V1 se conservan tal cual,
   porque NB Sound Mobile los tiene guardados en su base local ([ADR-005](./ADR-005-contrato-movil.md)). Lo mismo
   para `sync_version`, las tumbas (`sync_tombstones`) y los `device_token`.
6. **Importador V1 → V2**, que se ejecuta solo la primera vez que arranca la V2 si encuentra la base de la V1:
   * abre la base V1 en **solo lectura** (`mode=ro`) y nunca la modifica;
   * migra biblioteca, playlists con su orden, historial, favoritos, cola y estado del reproductor, overrides de
     catalogación, dispositivos emparejados, estado de sincronización, sesiones y preferencias del DJ, rutas de stems
     ya separados y rasgos de audio (resumidos según el punto 4);
   * copia el certificado y la clave del servidor móvil (`~/.config/nb_sound/sync/sync_cert.pem` y
     `sync_key.pem`) para que la huella no cambie;
   * deja un informe que cuenta lo migrado por tabla, y una prueba exige que cuadre fila a fila.
   * No migra lo que era operativo de la V1: `archivos_pendientes`, `manifests_index`, colas de trabajos
     terminados, ejecuciones de análisis.

## Alternativas consideradas

* **Reutilizar la base V1 en sitio.** Rechazada: arrastra el esquema, los 441 MB y el riesgo de que una V2 con
  defectos dañe los datos de la V1 que el usuario sigue usando.
* **Exportar e importar por JSON.** Rechazada: pierde tipos y no ofrece una prueba directa de conservación.

## Consecuencias

- **Positivas:** la base de la instalación real baja de 464 MB a unos 25 MB; la V1 sigue funcionando mientras la
  V2 madura; el móvil no nota el cambio.
- **Negativas:** hay que mantener el importador hasta que nadie tenga ya la V1.
- **Riesgos:** perder un dato que nadie inventarió. Se vigila con la prueba de conservación sobre la base real.
