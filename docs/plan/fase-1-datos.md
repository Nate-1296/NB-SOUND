# Fase 1: Datos

> **Objetivo:** el esquema en Rust y la búsqueda de texto completo.
>
> **Prerrequisitos:** Fase 0 cerrada. Contrato: [ADR-004](../adr/decisions/ADR-004-datos.md).

## Estado de la fase

| Iteración | Estado |
|---|---|
| F1.1.1 Capa de base de datos (pool, WAL, `BEGIN IMMEDIATE`, migraciones) | Hecha |
| F1.1.2 Esquema: catálogo (artistas, álbumes, pistas con su archivo y `verificada`, portadas e imágenes de artista, letras, por revisar) | Hecha |
| F1.1.3 Esquema: uso (playlists, favoritos, historial, cola, estado del reproductor) | Hecha |
| F1.1.4 Esquema: análisis resumido (rasgos, embeddings `f32`, LUFS, paleta) | Hecha |
| F1.1.5 Esquema: sincronización (dispositivos, `sync_version`, tumbas, transferencias) | Hecha |
| F1.1.6 Esquema: karaoke y DJ (stems, sesiones, eventos, preferencias) | Hecha |
| F1.3.1 Búsqueda de texto completo (FTS5) sobre títulos, artistas, álbumes y letras | Hecha |

## Criterios

* **F1.1.1:** `check-transacciones` pasa; una prueba con 8 escritores concurrentes no produce `SQLITE_BUSY`.
* **F1.1.2 a F1.1.6:** cada tabla tiene su migración, sus índices justificados por una consulta real y su prueba;
  F1.1.4 cumple el presupuesto de menos de 16 KB de análisis por pista.
* **F1.3.1:** una búsqueda sobre 100.000 pistas simuladas responde en menos de 30 ms.

La medición se ejecuta con `pnpm test:rendimiento`, incluida en `pnpm verify` y en un
paso separado de CI. Se conserva el límite de 30 ms; no se comparte el proceso de prueba
con los ensayos intensivos de DSP ni se reintenta una medición que falla.

