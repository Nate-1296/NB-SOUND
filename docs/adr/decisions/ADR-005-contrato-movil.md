# ADR-005: El contrato con NB Sound Mobile queda congelado

**Fecha:** 2026-10-29
**Estado:** Aceptado

## Contexto

NB Sound Mobile (Flutter, v0.1.2) está terminado. Su fuente de verdad sobre el PC es
`NB_Sound_Mobile/docs/pc-contract.md`, que describe lo que implementan hoy `servicios/servidor_sync.py` (869
líneas) y `servicios/sync_repositorio.py` (827):

* HTTPS y WSS con certificado autofirmado persistido; el móvil fija su huella SHA-256 en el primer
  emparejamiento (TOFU).
* Anuncio mDNS `_nbsound._tcp.local.`; QR con token efímero de un solo uso (TTL de 300 s).
* `POST /api/v1/pair` emite un `device_token` persistente; el resto usa `Authorization: Bearer`.
* Endpoints: `ping`, `pair`, `manifest` (delta paginado por `sync_version`, con tumbas), `seleccion` (GET/POST),
  `track/{id}/audio` y `track/{id}/stems` con `Range`, `track/{id}/lyrics`, `asset/{tipo}/{id}`, `history`.
* WebSocket `/api/v1/control`: estado del reproductor, comandos y frame de cola.
* `version_protocolo = 1`. El cliente ignora campos desconocidos, así que solo se admiten cambios aditivos.

Hay 12 dispositivos emparejados en la instalación real.

## Decisión

1. El servidor está escrito en Rust (`axum`, `rustls`, `mdns-sd`), **compatible byte a byte** con el protocolo
   `1`: mismas rutas, códigos, nombres de campo, paginación, semántica de `sync_version` y reglas de autoridad del
   merge.
2. **Una identidad que no cambia**: el certificado y la clave se crean una vez y se guardan, así que la huella no
   cambia y los teléfonos emparejados se reconectan sin volver a escanear el QR. Se guardan también los
   `device_token`, la selección por dispositivo y la última versión sincronizada.
3. **Respuestas doradas**: cada endpoint y cada frame del WebSocket tiene su respuesta grabada, con los datos
   sensibles redactados. Un arnés las reproduce contra el servidor de NB Sound en cada verificación. Una diferencia
   que no sea un campo añadido rompe la verificación.
4. Cualquier campo nuevo que necesite NB Sound (por ejemplo, LUFS, la paleta del álbum o `verificada` para las
   pistas importadas tal como están) es aditivo y se documenta en
   `docs/engineering/contrato-movil.md` con una nota para el móvil, que no tiene obligación de usarlo.
5. **La app móvil no se modifica.** Si una mejora del escritorio exigiera romper el protocolo, se escribe un ADR
   que lo justifique y se sube a `version_protocolo = 2`, manteniendo el 1 mientras exista un cliente que lo use.

## Consecuencias

- **Positivas:** el móvil funciona sin cambios.
- **Negativas:** NB Sound hereda nombres de campo en español y en inglés mezclados, que no se pueden cambiar.
- **Riesgos:** comportamiento implícito (cabeceras, formato de errores, cierre del WebSocket) que no esté en el
  contrato. Las respuestas doradas lo capturan porque se grabaron de un servidor real, no del documento.

## Enmienda del 2026-10-30: dependencias del servidor

Además de `axum`, `rustls` y `mdns-sd`, el servidor usa, con la aprobación de Nathan:

* **`tokio-rustls`**: une rustls con el servidor. Con la pila criptográfica `ring`, la que ya trae `ureq`; sin
  `aws-lc-rs`.
* **`rcgen`**: crea el certificado autofirmado la primera vez. ECDSA P-256 y con una validez que no vence: el
  teléfono fija la huella, y regenerar el certificado lo obligaría a emparejarse de nuevo.
* **`qrcode`**, sin las features de imagen: solo la matriz de módulos; la interfaz la dibuja.

`tokio` y `futures-util` ya estaban en el árbol por Tauri y axum; se nombran en `Cargo.toml` porque el servidor los
usa directamente. `tokio-tungstenite` solo entra como dependencia de desarrollo, para que el arnés hable con el
WebSocket como el teléfono.
