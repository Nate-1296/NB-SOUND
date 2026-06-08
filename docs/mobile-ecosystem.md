# Ecosistema móvil — lado escritorio (PC)

El lado escritorio del ecosistema móvil. Describe **lo que la app de escritorio
expone** para integrarse con la app móvil (Flutter, Android/iOS/tablets). El
código del lado PC vive en este repositorio; el del teléfono vive en el
proyecto [NB Sound Mobile](https://github.com/Nate-1296/NB-SOUND-MOBILE).

> El servidor local, el protocolo de sync, el schema de BD, la vista de
> sincronización y el backup descritos aquí están **implementados** en el
> escritorio (`servicios/servidor_sync.py`, `servicios/sync_repositorio.py`,
> `ui/modelos_qml.py::ModeloSincronizacion`, `ui/qml/vistas/VistaSincronizacion.qml`,
> `servicios/backup.py`). El **contrato del protocolo** (endpoints, JSON de
> cada entidad, WS de control, selección, merge) es la fuente de verdad para el
> cliente móvil. Este documento recoge ese contrato y las decisiones de
> producto.

## Decisión de producto (contexto)

- El **PC es la fuente de verdad** para metadata enriquecida (catálogo,
  portadas, lyrics, audio features, stems de karaoke).
- El **celular es fuente de verdad** para su historial y favoritos locales.
- Sincronización **local por WiFi**, iniciada por **QR**.
- El audio puede **transferirse** al celular para escucha offline.
- Con ambos conectados: **control remoto bidireccional** del reproductor
  (estilo Spotify Connect).

---

## A) Servidor local

### Protocolo

- **HTTP REST** para operaciones request/response: handshake, exportación de
  datos (catálogo, playlists, perfil), descarga de assets y audio.
- **WebSocket** para tiempo real bidireccional: estado del reproductor y
  comandos de control (Spotify Connect). Un solo canal WS por dispositivo.
- **mDNS / DNS-SD (Zeroconf)** para descubrimiento: el PC anuncia
  `_nbsound._tcp.local`. El QR es el camino primario (lleva IP+puerto+token);
  mDNS es el fallback/reconexión cuando el dispositivo ya está emparejado.

> Decisión de stack: servidor HTTP+WS en proceso, sobre `aiohttp` (async,
> HTTP y WS en un solo framework liviano) corriendo en su propio hilo con su
> event loop, para no acoplarse al event loop de Qt. Alternativa evaluada:
> `Flask`+`flask-sock` (más simple pero WSGI síncrono, peor para streaming de
> audio). **Recomendado: `aiohttp`.** QR con `qrcode` (sobre `Pillow`, ya
> presente). Descubrimiento con `zeroconf`.

### ¿Cuándo arranca?

**Bajo demanda**, no al iniciar la app. El servidor se enciende cuando el
usuario abre la Vista de Sincronización (o si "recordar dispositivos" está
activo y hay dispositivos emparejados, puede auto-encenderse al iniciar).
Razón: minimizar superficie de red y consumo cuando no se usa.

### Endpoints mínimos

| Método | Ruta | Propósito |
| --- | --- | --- |
| `GET` | `/api/v1/ping` | Liveness + versión de protocolo |
| `POST` | `/api/v1/pair` | Handshake: valida token del QR, registra dispositivo, devuelve `device_token` de larga vida |
| `GET` | `/api/v1/manifest?since=<sync_version>` | Delta de cambios desde la última sync (pistas/álbumes/artistas/playlists/perfil) |
| `GET` | `/api/v1/track/{id}/audio` | Stream/descarga del audio (soporta `Range` para reanudar) |
| `GET` | `/api/v1/asset/{tipo}/{id}` | Portada de álbum (`cover`/`album`), imagen de artista (`artist`) o carátula de playlist (`playlist`) |
| `GET` | `/api/v1/track/{id}/stems` | Stems de karaoke (opt-in, ver protocolo) |
| `POST` | `/api/v1/history` | Recibe historial/favoritos locales del celular (merge) |
| `WS` | `/api/v1/control` | Estado del reproductor (push) + comandos (play/pause/next/prev/seek/volume/queue) |

### Seguridad en red local

- **Emparejamiento por QR**: el QR contiene `host`, `puerto`, y un
  **token de emparejamiento efímero** (TTL corto, un solo uso). Tras el
  handshake `/pair`, el PC emite un `device_token` persistente por dispositivo.
- **Todo el tráfico autenticado** con `device_token` (header `Authorization`).
- **TLS**: certificado autofirmado generado al vuelo; el QR incluye el
  fingerprint para que el cliente lo fije (TOFU). Alternativa mínima v1: sin
  TLS pero solo en LAN + token (documentar el trade-off).
- **Binding a interfaces LAN**, nunca `0.0.0.0` en interfaces públicas;
  preferir la IP de la subred del WiFi.
- **Revocación**: el usuario puede revocar un dispositivo desde la Vista de
  Sincronización (borra su `device_token`).

### Integración con el ciclo de vida

- Arranque/parada gobernados por un **servicio Python** nuevo
  (`servicios/servidor_sync.py`) y un **modelo QML** (`ModeloSincronizacion`).
- **Cierre limpio**: registrar el teardown del servidor en el `_ORDEN_CIERRE`
  de `main_ui.construir_modelos` (junto a los demás modelos con `cerrar()`),
  para que el hilo del servidor y su event loop se detengan antes de que Qt
  destruya los QObject.
- **Puerto**: elegir uno libre en un rango (p. ej. 8731–8799); si está
  ocupado, probar el siguiente. El puerto efectivo va en el QR.
- **Ciclo "nunca bloquea"**: el servidor corre en su propio hilo; la UI solo
  recibe señales (dispositivo conectado, progreso de transferencia).

### Cambios en `main_ui.py` / bootstrap

- Registrar `ModeloSincronizacion` en `construir_modelos()` y exponerlo en
  `exponer_modelos()`.
- Añadirlo al `_ORDEN_CIERRE` para teardown ordenado.
- **No** arrancar el servidor en `inicializar_aplicacion()` (es bajo demanda).
- `aiohttp`, `zeroconf` y `qrcode` están en `requirements.txt`, en el catálogo
  de `infra/dependencias.py` (como requeridas del módulo de sync) y en los
  `hiddenimports` de los tres specs de PyInstaller.

El servidor corre en su propio hilo con event loop aislado del de Qt; no se
comparten objetos Qt entre hilos, la comunicación es por señales.

---

## B) Protocolo de sincronización

### Datos que viajan (schema del payload)

Todo se serializa en JSON salvo binarios (audio/imágenes), que se descargan
por sus endpoints. Campos basados en columnas reales de la BD del PC.

- **Pistas** (`/manifest`): `id`, `titulo`, `artista_nombre`, `album_titulo`,
  `album_id`, `artista_id`, `track_number`, `duracion_seg`, `anio`, `genero`,
  `isrc`, `mb_recording_id`, `favorita`, `hash_sha256` (para validar audio),
  `audio_url`, `cover_url`; audio features básicas resumidas (bpm, energy,
  key) desde `track_audio_features`; `lyrics_url` si hay LRC.
- **Álbumes**: `id`, `titulo`, `artista_id`, `tipo`, `anio`, `cover_url`
  (desde `albums.portada_ruta`).
- **Artistas**: `id`, `nombre`, `imagen_url`.
- **Playlists**: `id`, `nombre`, `descripcion`, `tipo`
  (manual/automática/sistema), `subtipo`, `origen`, `auto_key`, `es_anclada`,
  `num_pistas`, lista ordenada de `pista_id` (desde `pistas_playlist`) y
  `cover_url` (carátula en uso, desde `playlists.portada_ruta`, igual que los
  álbumes). Para que el celular agrupe igual que el PC se incluye `categoria`
  (`me_gusta` | `creada` | `inteligente` | `this_is` | `sistema`), su `etiqueta`
  legible y `es_favoritos`. Incluye "Me gusta" como lista canónica de
  favoritos (todas las favoritas, sin tope).
  Nota de implementación: cada mutación de playlist (crear/editar/membresía/
  portada/anclar) bumpea `playlists.sync_version`; un backfill único etiqueta
  las preexistentes. Sin esto el delta (`sync_version > since`) nunca las
  enviaba.
- **Historial de reproducción**: viaja **del celular al PC** (el celular es
  su fuente de verdad); el PC lo agrega a `historial`.
- **Perfil**: nombre, foto, estadísticas agregadas (solo lectura hacia el
  celular).
- **Stems de karaoke**: **opt-in por pista** (el usuario marca qué llevar).
  Tamaño estimado: ~2–4× el tamaño del audio original (varias pistas WAV/FLAC
  por separación). Por eso nunca viajan por defecto.
- **Sesiones DJ**: por defecto **solo metadata** de sesión (timeline,
  decisiones), no las pistas (ya viajan por el catálogo si el usuario las
  sincronizó).
- **Temas y preferencias UI**: opcional, opt-in (el celular tiene su propio
  sistema de temas; se puede importar la paleta activa).

### Qué NO viaja por defecto y por qué

- **Stems de karaoke** (tamaño) — opt-in por pista.
- **Audio de toda la biblioteca** (tamaño) — el usuario elige qué transferir
  para offline; sin transferir, el celular usa streaming cuando hay conexión.
- **Pistas de sesiones DJ** (redundante con el catálogo).
- **Claves de API / `.env` / configuración sensible** (seguridad).
- **Tablas de control interno** (`audio_analysis_jobs/runs`, sidecars).

### Selección del usuario

Granularidad: **todo / nada / por playlist / por artista**. La selección se
persiste por dispositivo (qué incluir en cada sync). La transferencia de
audio para offline es una segunda capa de selección (qué descargar al
teléfono), independiente de qué metadata se sincroniza.

### Reglas de merge

- **PC gana** en metadata enriquecida (título, artista, álbum, portada,
  lyrics, features). El celular las trata como read-only.
- **Celular gana** en su historial y favoritos locales. El favorito es el
  caso especial: es bidireccional — se resuelve por **última escritura gana**
  con timestamp (`favorita` + `favorita_actualizada_en`), de modo que marcar
  favorito en cualquier lado se propaga.

### Detección de cambios (delta)

- **Versión de sync monotónica** por entidad: una columna `sync_version`
  (entero incremental) en las tablas sincronizables, actualizada en cada
  cambio. El cliente pide `/manifest?since=<última_sync_version_conocida>` y
  recibe solo lo modificado.
- Complemento: `actualizado_en` (ya existe en varias tablas) para auditoría;
  `hash_sha256` para validar que el audio descargado coincide.
- **Tombstones**: tabla `sync_tombstones` para propagar borrados (id + tipo +
  `sync_version`), ya que un DELETE no se detecta por `sync_version`.

### Transferencia interrumpida

- **Audio/assets**: descargas con soporte `Range` (HTTP 206) — el celular
  reanuda desde el byte recibido; valida `hash_sha256` al completar.
- **Sync de metadata**: idempotente y reanudable por `sync_version` — si se
  corta, el cliente reintenta `since=` el último aplicado con éxito.
- **Stems**: estado de transferencia por pista/dispositivo en
  `sync_stem_transfers` (pending/in_progress/done/failed), reanudable.

---

## C) Base de datos — cambios de schema

Coherente con el mecanismo existente: **migraciones aditivas idempotentes**
vía `db/conexion._agregar_columna_si_falta` y `CREATE TABLE IF NOT EXISTS` en
`db/esquema.py` (el proyecto **no** usa `PRAGMA user_version`; las migraciones
solo agregan columnas/tablas, nunca eliminan).

### Tablas nuevas

```sql
-- Dispositivos móviles emparejados
CREATE TABLE IF NOT EXISTS sync_dispositivos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_token    TEXT    NOT NULL UNIQUE,   -- credencial persistente
    nombre          TEXT    NOT NULL,          -- "Pixel de Jonathan"
    plataforma      TEXT,                       -- android | ios
    ultima_conexion TEXT,
    ultima_sync_version INTEGER NOT NULL DEFAULT 0,
    seleccion_json  TEXT,                       -- qué sincroniza este device
    creado_en       TEXT    NOT NULL DEFAULT (datetime('now')),
    revocado        INTEGER NOT NULL DEFAULT 0
);

-- Borrados a propagar (no detectables por sync_version)
CREATE TABLE IF NOT EXISTS sync_tombstones (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    entidad       TEXT    NOT NULL,   -- pista | album | artista | playlist
    entidad_id    INTEGER NOT NULL,
    sync_version  INTEGER NOT NULL,
    creado_en     TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Estado de transferencia de stems por dispositivo
CREATE TABLE IF NOT EXISTS sync_stem_transfers (
    dispositivo_id INTEGER NOT NULL REFERENCES sync_dispositivos(id) ON DELETE CASCADE,
    pista_id       INTEGER NOT NULL REFERENCES pistas(id) ON DELETE CASCADE,
    estado         TEXT    NOT NULL DEFAULT 'pending', -- pending|in_progress|done|failed
    bytes_enviados INTEGER NOT NULL DEFAULT 0,
    actualizado_en TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (dispositivo_id, pista_id)
);

-- Contador global de versión de sync (monotónico)
CREATE TABLE IF NOT EXISTS sync_estado (
    clave TEXT PRIMARY KEY,   -- p.ej. 'sync_version_actual'
    valor TEXT NOT NULL
);
```

### Columnas nuevas (aditivas, vía `_agregar_columna_si_falta`)

- `pistas.sync_version INTEGER NOT NULL DEFAULT 0`
- `pistas.favorita_actualizada_en TEXT` (para merge last-write-wins de favoritos)
- `albums.sync_version INTEGER NOT NULL DEFAULT 0`
- `artistas.sync_version INTEGER NOT NULL DEFAULT 0`
- `playlists.sync_version INTEGER NOT NULL DEFAULT 0`

La lógica de servicio incrementa `sync_version` (desde un contador en
`sync_estado`) en cada modificación de las entidades sincronizables.

### Versionado de migraciones

Las columnas se añaden en `_aplicar_migraciones_ligeras` y las tablas nuevas en
`CREAR_TABLAS_SQL`, siguiendo el patrón aditivo idempotente del proyecto (sin
`PRAGMA user_version`, ya que todas las migraciones son aditivas).

---

## D) Vista de sincronización en la UI de PC

### Qué muestra

- **Dispositivos**: emparejados (nombre, plataforma, última conexión, botón
  revocar) y el actualmente conectado.
- **Estado del servidor**: encendido/apagado, IP:puerto, indicador WiFi.
- **QR** grande para emparejar uno nuevo.
- **Progreso de transferencia**: barra por transferencia activa (audio/stems),
  con cancelar/pausar.
- **Historial de syncs**: últimas N (fecha, dispositivo, cambios aplicados).

### QR

Generado en Python con `qrcode` (sobre `Pillow`, ya presente). Contenido:
JSON con `host`, `puerto`, `token_efímero`, `tls_fingerprint`, `version`.
Se entrega a QML como imagen (data URI o archivo temporal) vía una propiedad
del modelo. Se regenera al encender el servidor o al expirar el token.

### Acciones expuestas

Encender/apagar servidor; generar/regenerar QR; revocar dispositivo; elegir
selección de sync por dispositivo; iniciar transferencia de audio/stems para
offline; cancelar transferencia.

### Modelo QML y servicio Python

- `servicios/servidor_sync.py` — servidor HTTP/WS + mDNS + lógica de sync
  (sin Qt; testeable).
- `ui/modelos_qml.py::ModeloSincronizacion` — bridge Qt: propiedades
  (servidor activo, lista de dispositivos, QR, progreso) y slots
  (encender/apagar, revocar, transferir). Worker Qt para no bloquear.
- Vista `ui/qml/vistas/VistaSincronizacion.qml` + entrada en `NavLateral` y
  `Principal.qml` (lazy loading, igual que las demás vistas).

---

## E) Backup automático

### Qué incluye

- **SQLite** completo (catálogo, playlists, historial, perfil, config_ui).
- **Assets**: portadas e imágenes de artista (carpeta de assets del usuario).
- **Opcional/opt-in**: lyrics/sidecars, stems de karaoke (tamaño).
- **Excluye**: audio original (es la biblioteca del usuario, no un "backup"
  de la app), `.env`/claves.

### Formato

Archivo `.nbsound-backup` = **ZIP** con: `db.sqlite3` (copiado con
`VACUUM INTO` para consistencia sin bloquear), `assets/`, y un `manifest.json`
(versión de app, fecha, contenido, checksums). ZIP por portabilidad y por
soportar restauración parcial.

### Frecuencia y destino

- **Manual** + **programado** (diario/semanal, configurable), corriendo en
  worker Qt al cierre o en idle.
- Destino: carpeta configurable (por defecto `USER_*`/backups); rotación de
  los últimos N.

### Restauración

Desde la Vista de Sincronización (o Configuración): seleccionar un
`.nbsound-backup`, validar `manifest.json`/checksums, restaurar a una BD
temporal, validar integridad, y reemplazar atómicamente. **Reutiliza** la
lógica de recuperación de BD corrupta ya existente en `db/conexion.py`.

---

← [architecture.md](architecture.md) · [cross-platform.md](cross-platform.md) ·
App móvil: [NB Sound Mobile](https://github.com/Nate-1296/NB-SOUND-MOBILE)
