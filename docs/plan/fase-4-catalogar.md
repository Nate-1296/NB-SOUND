# Fase 4: Importar y catalogar

> **Objetivo:** portar la canalización de catalogación de la V1 (`core/pipeline.py` y sus etapas, `external/`) a
> Rust, con la experiencia de [ADR-007](../adr/decisions/ADR-007-arquitectura-de-informacion.md): arrastrar y
> soltar en cualquier parte, carpeta vigilada y **Por revisar**.
>
> **Prerrequisitos:** Fases 1 y 2, y F0.4.4 y F0.4.6. Contratos: ADR-002, ADR-007, ADR-009.
>
> **Regla de la fase:** paridad de decisiones medida contra la V1 antes de rediseñar nada del algoritmo.

## Estado de la fase

| Iteración | Estado |
|---|---|
| F4.1.1 Lectura y escritura de etiquetas con `lofty` (ID3v2, Vorbis, MP4) | Hecha: `catalogo/etiquetas.rs`; en 400 MP3 del corpus real lee los siete campos de la V1 igual que `mutagen` y la duración con menos de 0,1 s de diferencia. Escribe sobre una copia y la coloca al terminar |
| F4.1.2 Normalización de texto y nombres (`core/normalizer.py`, `utils/text.py`, `utils/diccionarios.py`) | Parcial: `utils/text.py` portado (`catalogo/texto.rs`), idéntico a la V1 en las 5.531 frases del corpus real; `normalizer.py` portado en `catalogo/normalizacion.rs` (ver F4.1.6). `diccionarios.py` son los saludos de Inicio, ya portados en F2.2.2 |
| F4.1.3 Huella y AcoustID | Hecha: `catalogo/acoustid.rs`, con el `fpcalc` empaquetado y el umbral y los reintentos de la V1; la caché de consultas va con la canalización |
| F4.1.4 MusicBrainz, discografía y Cover Art Archive | Parcial: el cliente de MusicBrainz con las seis estrategias de la V1 (`catalogo/musicbrainz.rs`, API JSON); la organización por discografía (`catalogo/organizacion.rs`) da las mismas rutas que la V1 en las 2.240 pistas de la biblioteca real; falta Cover Art Archive, que va con las portadas (F4.1.10) |
| F4.1.5 Shazam (`shazamio-core`) e iTunes | Parcial: iTunes (`catalogo/etapas.rs`); falta Shazam |
| F4.1.6 Puntuación y emparejamiento: primera, segunda y tercera etapa | Hecha: primera etapa (`catalogo/emparejador.rs`) y `normalizer.py` (`catalogo/normalizacion.rs`), con la misma decisión, causa, puntuación y candidato que la V1 en 400 casos grabados; segunda y tercera (`catalogo/etapas.rs`) como funciones puras con sus umbrales |
| F4.1.7 Desempate por IA opcional | Pendiente |
| F4.1.8 Duplicados exactos y semánticos, con su política | Pendiente |
| F4.1.9 Escritura: organizar en la carpeta de música, transcodificar con `ffmpeg` | Pendiente |
| F4.1.10 Portadas e imágenes de artista (las seis fuentes de la V1) | Pendiente |
| F4.1.11 Letras (LRCLIB y lyrics.ovh) | Pendiente |
| F4.1.12 Rasgos básicos y LUFS al importar | Pendiente |
| F4.1.13 Recuperación tras un cierre a medias (`core/import_recovery_service.py`) | Pendiente |
| F4.2.1 Arrastrar y soltar en toda la ventana; "Añadir música" | Pendiente |
| F4.2.2 Carpeta de música vigilada | Pendiente |
| F4.2.3 Progreso discreto y resumen | Pendiente |
| F4.2.4 Por revisar: lista con el motivo en lenguaje llano, comparador lado a lado y acciones | Pendiente |
| F4.2.5 Editar metadatos de una pista o un álbum | Pendiente |
| F4.2.6 Copia de seguridad y restauración (`servicios/backup.py`) | Pendiente |
| F4.2.7 Ajustes > Privacidad y servicios en línea; Inteligencia artificial | Pendiente |
| F4.2.8 Importar tal como está: pistas sin verificar, su filtro y "Completar datos" | Pendiente |

## Criterios

* **F4.1.x:** las pruebas de la V1 de cada módulo se traducen y pasan.
* **Paridad global:** un conjunto fijo de al menos 300 archivos sin etiquetar (copias de pistas del corpus con
  las etiquetas borradas, fuera de la carpeta real) se importa con la V1 y con la V2; las decisiones (álbum,
  artista, título, número de pista, ¿revisión?) coinciden en ≥ 98 %, y cada diferencia queda explicada en el
  informe.
* **F4.2.4:** cada causa interna de la V1 tiene su mensaje y sus acciones según la tabla de la
  [enmienda de ADR-007](../adr/decisions/ADR-007-arquitectura-de-informacion.md#enmienda-del-2026-10-29-por-revisar);
  una prueba recorre todas las causas y falla si alguna llega a la interfaz sin traducir. La entrada de la barra
  lateral solo existe con algo pendiente. Descartar manda a la papelera del sistema.
* **F4.2.8:** una pista importada tal como está se reproduce, entra en playlists y en el DJ, aparece en el filtro
  "Sin verificar", y antes de confirmar se advierte lo que le falta. Con un teléfono conectado, el manifiesto la
  incluye y el teléfono real la descarga sin cambios en NB Sound Mobile (arnés de respuestas doradas en verde).
  "Completar datos" le añade portada y letra sin cambiar su `id`.
* **F4.2.2:** copiar un álbum en la carpeta de música lo añade sin abrir nada.
* Las salidas de red pasan por `net.rs`; con todo desactivado, la importación funciona solo con las etiquetas.

**Puerta de empaquetado.**
