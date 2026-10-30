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
* `src-tauri/tests/contrato_movil.rs` (desde F3.1) siembra el mismo escenario en la base de la V2, arranca el
  servidor de la V2 y hace las mismas peticiones, con un cliente que confía en el certificado por su huella como el
  teléfono. Reglas de comparación:
  * mismo código de estado;
  * mismas cabeceras de las cinco que se graban (`content-type`, `content-length`, `content-range`,
    `accept-ranges`, `x-nb-sound-hash`);
  * mismo cuerpo, con dos tolerancias: los marcadores `<...>` aceptan cualquier valor del mismo tipo, y un campo
    que la V2 **añade** se admite (el móvil ignora los desconocidos). Un campo que falta, que cambia de tipo o de
    valor, rompe la prueba;
  * en el WebSocket, la misma secuencia de frames; el orden entre el ack de `queue` y el frame `cola` no cuenta;
  * el `content-length` de la V1 tiene que salir **exacto** al quitar del cuerpo de la V2 lo añadido y devolver las
    diferencias deliberadas a su valor. Es lo que prueba que el JSON se escribe como `json.dumps` (separadores,
    `\uXXXX` para lo que no es ASCII, reales como `repr`), y que las fechas y los tokens miden lo mismo.

Una segunda prueba cubre lo que la grabación no recorre: el estado y la cola que el equipo empuja cuando cambian, y
que quitar un teléfono cierra su control remoto y deja su token sin valor.

## Lo que la grabación destapó y el documento del móvil no dice

* **Playlists:** además de `id`, `nombre`, `tipo`, `auto_key`, `sync_version` y `pista_ids`, la V1 envía
  `descripcion`, `subtipo`, `origen`, `categoria`, `etiqueta`, `es_favoritos`, `es_anclada`, `num_pistas` y
  `cover_url`. La V2 los envía todos.
* **Errores:** sin autenticación, `401 {"error": "no_autorizado"}`. Una ruta de pista con id no numérico da
  `404 {"error": "no_encontrado"}` (no un 400). Un tipo de asset desconocido, también 404 `no_encontrado`.
* **Ack de los comandos:** `resultado` es `{"ok": true, "encolado": true}` incluso para una acción desconocida; el
  frame de error solo aparece con JSON inválido (`{"tipo": "error", "detalle": "json_invalido"}`).

## Campos que añade la V2

Cada uno con su motivo y una nota para el móvil, que no tiene obligación de usarlo.

| Campo | Dónde | Motivo y nota para el móvil |
|---|---|---|
| `verificada` | cada pista del manifiesto | `false` si se importó tal como estaba desde Por revisar (enmienda de ADR-007). El móvil podría marcarla como el escritorio; cambiarla sube la versión de la pista (V8) |

## Diferencias deliberadas con la V1

Están en `DIFERENCIAS` del arnés, que las tolera solo en esa ruta.

| Qué | V1 | V2 | Por qué |
|---|---|---|---|
| `cover_url` de las playlists | Solo si la playlist tenía un mosaico generado | Siempre que alguna de sus pistas tiene portada; `/api/v1/asset/playlist/{id}` compone el mosaico al pedirlo y lo guarda en la caché | En la instalación real lo tenían todas las visibles; el escenario de la grabación no generaba mosaicos |
| `indice` del frame `cola` | `-1` cuando el índice era 0 (`int(x or -1)`) | El índice | Defecto de la V1 |

Diferencias que la grabación no ve, todas en el mismo sentido (no guardar ni enviar lo que no sirve):

* `perfil.foto` va siempre vacío: la V1 enviaba la ruta de la foto en el PC, que el teléfono no puede abrir ni usa.
* `POST /history`: una escucha de una pista que el equipo no tiene no se apunta ni se cuenta (la V1 la apuntaba sin
  título), y una escucha completa suma una reproducción, como las del equipo. Un favorito aplicado mantiene "Me
  gusta" si existe; si no existe, no se crea desde el teléfono, y cuando se cree nacerá con todas las favoritas.
* `queue` responde con la cola solo a quien la pidió: los demás ya la reciben en cada cambio.
* `stop` pausa: la V2 no tiene un "detener" aparte que vacíe nada.
* Quitar un teléfono desde Ajustes cierra al momento su control remoto; en la V1 seguía abierto hasta reconectar.
* El `device_token` no se guarda: solo su SHA-256 (V5).
