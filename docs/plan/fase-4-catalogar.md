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
| F4.1.4 MusicBrainz, discografía y Cover Art Archive | Hecha: el cliente de MusicBrainz con las seis estrategias de la V1 (`catalogo/musicbrainz.rs`, API JSON); la organización por discografía (`catalogo/organizacion.rs`) da las mismas rutas que la V1 en las 2.240 pistas de la biblioteca real; Cover Art Archive va con las portadas (F4.1.10) |
| F4.1.5 Shazam (`shazamio-core`) e iTunes | Hecha: la firma portada de `songrec` (`catalogo/shazam.rs`, con la ventana de 10 s de la V1; en un MP3 real, los picos por banda difieren menos de un 5 % de los de `shazamio_core`) e iTunes (`catalogo/etapas.rs`). La consulta real a Shazam va a las pruebas finales |
| F4.1.6 Puntuación y emparejamiento: primera, segunda y tercera etapa | Hecha: primera etapa (`catalogo/emparejador.rs`) y `normalizer.py` (`catalogo/normalizacion.rs`), con la misma decisión, causa, puntuación y candidato que la V1 en 400 casos grabados; segunda y tercera (`catalogo/etapas.rs`) como funciones puras con sus umbrales |
| F4.1.7 Desempate por IA opcional | Hecha: `catalogo/ia.rs`, con el prompt y la validación de la V1 (un lanzamiento fuera de la lista cerrada descarta la respuesta); Anthropic u OpenAI por `net.rs`, solo con el servicio consentido y una clave en el llavero. Sin respuesta válida, la ambigüedad queda en revisión. La reorganización de discografía por IA de la V1 (`organizar_discografia`) no se porta: no la pide ninguna iteración |
| F4.1.8 Duplicados exactos y semánticos, con su política | Hecha: los tres ejes de la V1 (`catalogo/duplicados.rs`), con la huella de 512 KB al principio y al final que comprueba el teléfono; precargados con la biblioteca |
| F4.1.9 Escritura: organizar en la carpeta de música, transcodificar con `ffmpeg` | Hecha: `catalogo/canalizacion.rs` encadena validación, duplicados, identificación, las tres etapas, organización, etiquetas, portadas, letras y alta; lo que no entra va a Por revisar con su causa. Sin transcodificar (enmienda de ADR-006). Sin permiso para MusicBrainz, lo que trae título y artista entra sin verificar |
| F4.1.10 Portadas e imágenes de artista (las seis fuentes de la V1) | Hecha: `catalogo/portadas_red.rs`: etiquetas, Cover Art Archive, iTunes, TheAudioDB, Deezer y Wikipedia con la puntuación de la V1; una sola copia por contenido, la HD si existe (P11) |
| F4.1.11 Letras (LRCLIB y lyrics.ovh) | Hecha: `catalogo/letras_red.rs`, con el orden, la puntuación de filas y el trato del 429 de la V1 |
| F4.1.12 Rasgos básicos y LUFS al importar | Hecha: `rasgos.rs` porta el modo `light` de la V1 (tempo y pulsos del `beat_track` de librosa 0.11 leído en su código, RMS, centroide, ancho de banda, caída espectral, cruces por cero, ataques y las aproximaciones con sus fórmulas) y la tonalidad nueva con perfiles de Krumhansl sobre el croma. Se analiza lo que no tiene rasgos en el hilo de la sonoridad, que ya medía los LUFS de lo importado (F2.1.4); las filas de la V1 se respetan y se obedecen sus preferencias de análisis. La comparación con la V1 de los rasgos nuevos y la tonalidad a oído en 30 pistas van a las pruebas finales |
| F4.1.13 Recuperación tras un cierre a medias (`core/import_recovery_service.py`) | Hecha: cada archivo se apunta en `pendientes_importacion` (V9) antes de empezar y se borra al terminar; al arrancar se sigue por donde iba (`catalogo/importacion.rs`) |
| F4.2.1 Arrastrar y soltar en toda la ventana; "Añadir música" | Hecha: el evento de la ventana llega a Rust y el selector nativo se abre desde Rust; ninguna ruta cruza el puente |
| F4.2.2 Carpeta de música vigilada | Hecha: al arrancar se recoge lo que llegó con la aplicación cerrada y, mientras está abierta, `notify` avisa de lo nuevo; cada archivo se importa tras 3 s sin cambiar de tamaño y si no está ya en la biblioteca ni en la cola. Sin carpeta fijada, espera a que la fije la primera importación |
| F4.2.3 Progreso discreto y resumen | Hecha: la tarjeta "Catalogando N canciones" y el resumen con enlace a Por revisar |
| F4.2.4 Por revisar: lista con el motivo en lenguaje llano, comparador lado a lado y acciones | Hecha: motivos de la enmienda de ADR-007, candidatos al lado del archivo, importar tal como está avisando de lo que faltará, buscar de nuevo, descartar a la papelera y acciones en lote. Una prueba recorre todas las causas internas |
| F4.2.5 Editar metadatos de una pista o un álbum | Hecha: `catalogo/edicion.rs` y su diálogo, que se carga aparte. Los `id` no cambian: renombrar un álbum actualiza su fila con su portada, y solo se junta con otro si ya existe uno igual del mismo artista; lo que se queda vacío se borra. Las etiquetas van al archivo si se puede; editar no marca la pista como verificada. Lo editado se guarda como corrección (`catalogo/correcciones.rs`, los `overrides` de la V1) por huella e ISRC, y la importación la aplica por huella, ISRC y artista con título antes de consultar la red, también las que trajo la V1 |
| F4.2.6 Copia de seguridad y restauración (`servicios/backup.py`) | Hecha: `copia_seguridad.rs`, con el `.nbsound-backup` de la V1 (base por `VACUUM INTO`, portadas y manifiesto con sha256) más la versión de esquema. Restaurar valida la copia entera (sumas, `integrity_check`, esquema no más nuevo, rutas que no salen de su carpeta), la deja preparada y la aplica al reiniciar, antes de abrir la base; la de antes se aparta. Copias automáticas con la frecuencia y la carpeta de la V1. Una copia de la V1 se rechaza con su motivo hasta que se cierre P12 |
| F4.2.7 Ajustes > Privacidad y servicios en línea; Inteligencia artificial | Hecha: `privacidad.rs`; el interruptor general y uno por servicio con lo que envía, aplicados a la puerta en el acto; proveedor (Anthropic u OpenAI) y modelo como preferencias, la clave en el llavero sin volver nunca a la interfaz. Las dos secciones se cargan aparte del arranque |
| F4.2.8 Importar tal como está: pistas sin verificar, su filtro y "Completar datos" | Hecha: la insignia, el filtro "Sin verificar", el aviso al confirmar (F4.2.4) y el campo `verificada` del manifiesto (F3.1.4) ya estaban. "Completar datos" (`catalogo/completar_datos.rs`) identifica de nuevo con la misma función que la canalización y busca portada y letra sin cambiar el `id`; si se identifica, la fila se rehace en su sitio, el archivo recibe las etiquetas pero no se mueve, y el álbum y el artista vacíos se borran. La prueba con el teléfono real va a las pruebas finales |

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
