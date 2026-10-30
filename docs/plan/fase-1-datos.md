# Fase 1: Datos

> **Objetivo:** el esquema V2 en Rust y un importador que trae la instalación de la V1 entera, sin pérdida y sin
> tocarla.
>
> **Prerrequisitos:** Fase 0 cerrada. Contrato: [ADR-004](../adr/decisions/ADR-004-datos.md).
>
> **Regla de la fase:** ninguna pérdida. Un dato que la V1 tiene y la V2 no importa es un defecto, salvo que esté
> en la lista de lo que no se migra de ADR-004.

## Estado de la fase

| Iteración | Estado |
|---|---|
| F1.1.1 Capa de base de datos (pool, WAL, `BEGIN IMMEDIATE`, migraciones) | Hecha |
| F1.1.2 Esquema V2: catálogo (artistas, álbumes, pistas con `verificada`, archivos, portadas e imágenes de artista, letras, por revisar) | Pendiente |
| F1.1.3 Esquema V2: uso (playlists, favoritos, historial, cola, estado del reproductor) | Pendiente |
| F1.1.4 Esquema V2: análisis resumido (rasgos, embeddings `f32`, LUFS, paleta) | Pendiente |
| F1.1.5 Esquema V2: sincronización (dispositivos, `sync_version`, tumbas, transferencias) | Pendiente |
| F1.1.6 Esquema V2: karaoke y DJ (stems, sesiones, eventos, preferencias) | Pendiente |
| F1.2.1 Inventario columna a columna de las 30 tablas de la V1 y de lo que guarda fuera de la base | Hecha |
| F1.2.2 Importador de solo lectura | Pendiente |
| F1.2.3 Migración de la identidad del servidor móvil (certificado, clave, tokens) | Pendiente |
| F1.2.4 Migración del `.env` (rutas y claves al llavero) | Pendiente |
| F1.2.5 Informe y prueba de conservación sobre la base real | Pendiente |
| F1.3.1 Búsqueda de texto completo (FTS5) sobre títulos, artistas, álbumes y letras | Pendiente |

## Criterios

* **F1.1.1:** `check-transacciones` pasa; una prueba con 8 escritores concurrentes no produce `SQLITE_BUSY`.
* **F1.1.2 a F1.1.6:** cada tabla tiene su migración, sus índices justificados por una consulta real y su prueba;
  F1.1.4 cumple el presupuesto de menos de 16 KB de análisis por pista.
* **F1.2.1:** `docs/engineering/migracion-v1.md` dice, para cada columna de la V1, a dónde va o por qué no se migra.
* **F1.2.2:** abre la base V1 con `mode=ro`; una prueba demuestra que el archivo de la V1 no cambia (hash antes y
  después). Los `id` se conservan.
* **F1.2.3:** la huella SHA-256 del certificado tras migrar es idéntica a la de la V1; los 12 `device_token` se
  validan contra el servidor de la V2 (cuando exista, en la Fase 3).
* **F1.2.5:** sobre la base real, el informe cuadra fila a fila: 2.397 pistas, 1.421 álbumes, 434 artistas, 56
  playlists con su orden, 3.225 entradas de historial, 12 dispositivos. La base resultante pesa menos de 40 MB.
* **F1.3.1:** una búsqueda sobre 100.000 pistas simuladas responde en menos de 30 ms.

**Puerta de empaquetado** al cerrar: la aplicación instalada encuentra la base de la V1 y la importa.
