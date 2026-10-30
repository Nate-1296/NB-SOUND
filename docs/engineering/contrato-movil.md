# Contrato con NB Sound Mobile

> **Estado:** Vigente desde el 2026-10-29. Gobierna la Fase 3. Decisión: [ADR-005](../adr/decisions/ADR-005-contrato-movil.md).

## La fuente de verdad

1. **Lo que respondía la V1**, grabado en `src-tauri/tests/contrato_movil/respuestas.json` (F0.4.5). Manda sobre
   cualquier documento.
2. `NB_Sound_Mobile/docs/pc-contract.md`, que describe lo mismo con palabras y es lo que lee quien programa el
   móvil.

Si los dos discrepan, gana la grabación: es lo que el móvil recibió de verdad durante su desarrollo.

## Cómo se comprueba

* El escenario (`escenario.json`) son datos inventados: dos artistas, dos álbumes, cuatro pistas (una con
  instrumental y letras, una borrada), dos playlists (una oculta), un perfil y el estado de un reproductor.
* `scripts/prototipos/contrato-movil/grabar.py` lo siembra en la V1, arranca su servidor real y graba 36 respuestas.
  Con `--comprobar` vuelve a grabar y exige el mismo archivo byte a byte: es el arnés contra la V1.
* En la Fase 3, una prueba de `cargo test` siembra el mismo escenario en la base de la V2, arranca el servidor de la
  V2 y hace las mismas peticiones. Reglas de comparación:
  * mismo código de estado;
  * mismas cabeceras de las cinco que se graban (`content-type`, `content-length`, `content-range`,
    `accept-ranges`, `x-nb-sound-hash`);
  * mismo cuerpo, con dos tolerancias: los marcadores `<...>` aceptan cualquier valor del mismo tipo, y un campo
    que la V2 **añade** se admite (el móvil ignora los desconocidos). Un campo que falta, que cambia de tipo o de
    valor, rompe la prueba;
  * en el WebSocket, la misma secuencia de frames; el orden entre el ack de `queue` y el frame `cola` no cuenta.

## Lo que la grabación destapó y el documento del móvil no dice

* **Playlists:** además de `id`, `nombre`, `tipo`, `auto_key`, `sync_version` y `pista_ids`, la V1 envía
  `descripcion`, `subtipo`, `origen`, `categoria`, `etiqueta`, `es_favoritos`, `es_anclada`, `num_pistas` y
  `cover_url`. La V2 los envía todos.
* **Errores:** sin autenticación, `401 {"error": "no_autorizado"}`. Una ruta de pista con id no numérico da
  `404 {"error": "no_encontrado"}` (no un 400). Un tipo de asset desconocido, también 404 `no_encontrado`.
* **Ack de los comandos:** `resultado` es `{"ok": true, "encolado": true}` incluso para una acción desconocida; el
  frame de error solo aparece con JSON inválido (`{"tipo": "error", "detalle": "json_invalido"}`).

## Campos que añade la V2

Ninguno todavía. Cada uno que se añada se apunta aquí con su motivo y una nota para el móvil, que no tiene
obligación de usarlo. Previstos: `verificada` en las pistas importadas tal como están (enmienda de ADR-007).
