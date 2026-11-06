# Fase 3: El móvil sigue funcionando

> **Objetivo:** el servidor de sincronización y control remoto en Rust, compatible byte a byte con el protocolo
> `1`, de modo que los teléfonos ya emparejados se reconectan sin hacer nada.
>
> **Prerrequisitos:** Fases 1 y 2, y F0.4.5. Contrato: [ADR-005](../adr/decisions/ADR-005-contrato-movil.md) y
> `NB_Sound_Mobile/docs/pc-contract.md`.
>
> **Regla de la fase:** NB Sound Mobile no se modifica.

## Estado de la fase

| Iteración | Estado |
|---|---|
| F3.1.1 Servidor HTTPS con su identidad (`axum` + `rustls`) | Hecha: `movil/`, en su hilo y su runtime; crea una identidad que no vence y la conserva. Teléfono real: en las pruebas finales |
| F3.1.2 Anuncio mDNS `_nbsound._tcp.local.` (`mdns-sd`) | Hecha: mismo nombre, host y TXT que espera el teléfono |
| F3.1.3 Emparejamiento: QR, token efímero, `device_token` | Hecha: token y código corto de un solo uso con 300 s; el `device_token` mide lo y se guarda como hash |
| F3.1.4 `manifest` delta paginado, tumbas y `sync_version` | Hecha: respuestas doradas con `content-length` exacto |
| F3.1.5 `seleccion`, `history`, `lyrics`, `asset` | Hecha; el mosaico de las playlists se compone al pedirlo |
| F3.1.6 `audio` y `stems` con `Range` y registro de transferencias | Hecha: a trozos, sin cargar el archivo |
| F3.2.1 WebSocket `/api/v1/control`: estado, comandos y frame de cola | Hecha: todas las acciones de `pc-contract.md` con sus alias; latido de 30 s |
| F3.3.1 Ajustes > Dispositivos: conectar un teléfono, lista y quitar | Hecha |
| F3.3.2 Selector de destino en la barra de reproducción (este equipo / teléfono) | Hecha: muestra dónde suena y qué teléfono lo controla. El protocolo 1 no tiene orden del equipo al teléfono, así que el traspaso al teléfono se hace desde el teléfono |

## Criterios

* **Todas:** el arnés de respuestas doradas de F0.4.5 pasa contra NB Sound, sin más diferencias que campos añadidos.
* **F3.1.1:** un teléfono emparejado se reconecta sin volver a escanear el QR.
* **F3.1.4:** el manifiesto que recibe el teléfono es el de las respuestas doradas.
* **F3.2.1:** desde el teléfono real se reproduce, pausa, salta, cambia volumen, aleatorio, repetición y karaoke, y
  la cola persiste al cambiar de destino, como describe `NB_Sound_Mobile/docs/remote-control.md`.
* **F3.3.1:** emparejar un teléfono nuevo desde Ajustes, sin más pantallas que la del QR.

**Al cerrar la fase** NB Sound se usa para escuchar y sincronizar. **Puerta de empaquetado.**
