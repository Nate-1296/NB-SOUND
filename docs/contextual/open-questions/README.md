# Preguntas abiertas

> Toda duda que bloquee o condicione trabajo se registra aquí con su fecha, a quién le toca y qué la cierra.
> Cerrada una pregunta, se deja la fila con la respuesta y el enlace al documento que la recoge.

| Id | Fecha | Pregunta | Qué la cierra | Estado |
|---|---|---|---|---|
| P1 | 2026-10-29 | ¿Kira da la precisión de muestra que piden el karaoke y la cola sin cortes, o hace falta un motor propio sobre `cpal`? | F0.4.1 | Cerrada: sí, con una fuente propia para la cola y el karaoke ([informe](../../audit/2026-10-29-prototipo-motor-audio.md)) |
| P2 | 2026-10-29 | ¿Se alcanza paridad del preprocesado mel de MusiCNN, VGGish y EffNet en Rust? | F0.4.3 | Cerrada: sí, en las 407 pistas, replicando el remuestreo lineal de la V1 ([informe](../../audit/2026-10-29-prototipo-analisis.md)) |
| P3 | 2026-10-29 | Si NB Sound llegara a ser comercial, ¿se licencian los modelos del MTG o se sustituyen? La propia web del MTG dice CC BY-NC-SA en una página y CC BY-NC-ND en otra | Decisión de Nathan, solo si cambia el modelo de negocio | Abierta, no bloquea |
| P4 | 2026-10-29 | ¿Repositorio público de distribución en GitHub o Hugging Face para los agregados? | F0.1.5 | Cerrada: Nathan hizo público el repositorio `Nate-1296/NB-SOUND`; los agregados se publican en sus Releases |
| P5 | 2026-10-29 | ¿`rusty-chromaprint` produce la huella comprimida idéntica a la de `fpcalc`? | F0.4.6 | Cerrada: no; 0 de 66 idénticas. Se empaqueta `fpcalc` |
| P6 | 2026-10-29 | ¿El agregado de aceleración en Linux con NVIDIA cabe en un tamaño razonable, dado que el proveedor CUDA de ONNX Runtime arrastra las librerías de CUDA? | F5.1.5, midiendo | Abierta, no bloquea |
| P7 | 2026-10-29 | La V2 deja cada archivo en su formato. ¿NB Sound Mobile reproduce bien un FLAC o un M4A recibido por `track/{id}/audio`? La biblioteca real hoy es toda MP3, así que nunca se probó | F3.1.6, con el teléfono real | Abierta |
| P8 | 2026-10-29 | ONNX Runtime llegó a 9 GB de memoria separando con `htdemucs`. ¿Cuánto baja sin *arena* ni patrón de memoria y con la sesión reutilizada? Sin bajarlo, el karaoke no cabe en un equipo de 8 GB | F5.2.1, con un tope de memoria en su criterio | Abierta |
| P9 | 2026-10-29 | ¿Se acepta enmendar ADR-008 para que la biblioteca use una ventana virtual de alto fijo con bloques alineados (medida en F0.4.7) en lugar de las páginas de NB Books? | Decisión de Nathan | Cerrada: sí, porque la V1 ya tenía listas continuas; la V2 se parece a la V1 (enmienda de ADR-008) |
| P10 | 2026-10-30 | GitHub avisa de 7 vulnerabilidades sin arreglo dentro de la pila actual: `glib` < 0.20 (moderada; la arrastra Tauri por GTK 3, no se puede subir sin que Tauri pase a GTK 4) y seis bajas de `@sveltejs/kit` < 3, `cookie` y `deepmerge`, que afectan a cookies y al servidor de SvelteKit, inexistentes con `adapter-static`. ¿Se sube a SvelteKit 3 cuando sea estable para el ecosistema? | Revisión en la puerta de cada fase; F7 como tope | Abierta, no bloquea |
| P11 | 2026-10-30 | Las portadas de la V1 ocupan 3,5 GB, 3,4 GB de ellos en las variantes HD de álbum, que la V1 usa en la vista de reproducción. ¿El importador las copia todas a la carpeta de la V2, o copia solo la versión HD de cada portada (la original) y la V2 deriva de ella el resto? Recomendación: lo segundo, que conserva todo lo que se ve sin duplicar tamaños | F1.2.2 | Cerrada: se copia una portada por álbum, la HD si existe, y la V2 deriva los tamaños pequeños (decisión de Nathan) |
