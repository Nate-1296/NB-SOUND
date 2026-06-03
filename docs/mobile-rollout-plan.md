# Plan de implementación — lado escritorio (PC)

Plan ejecutable para dejar la **app de escritorio** lista para el ecosistema
móvil. El plan de la **app móvil** vive en `../../nb_sound_mobile/docs/implementation-plan.md`.

Formato por tarea: `[S/M/L/XL]` esfuerzo relativo · **Qué** · **Archivos** ·
**Done when** (criterio verificable) · **Riesgo** + mitigación.

Base ya entregada y validada:
- ✅ Fase 1 — Auditoría y correcciones.
- ✅ Fase 2 — Deduplicación observable (3ª capa).
- ✅ Fase 3 — UI condicional por plataforma (deep en Windows).
- ✅ Fase 4 — Fixes aplicados, suite verde.

---

## BLOQUE 0 — Cierre de gaps cross-platform (Objetivo: bundle confiable en 3 SO antes de exponer red)

### Tarea 0.1 [M] — Validación de bundle por SO
- **Qué**: verificar que el CI empaqueta ffmpeg/fpcalc por SO y que libVLC
  resuelve; añadir test de humo que falle si falta un binario en el bundle.
- **Archivos**: `.github/workflows/*`, `packaging/_common.py`,
  `tests/test_packaging_artifacts.py`.
- **Done when**: en los tres runners, un build produce un bundle donde
  `infra.binarios` resuelve ffmpeg y fpcalc; test verde.
- **Riesgo**: bajo.

### Tarea 0.2 [S] — Auditoría de rutas literales
- **Qué**: grep de separadores `/` literales en construcción de rutas;
  migrar a `pathlib`/`os.pathsep` donde aplique.
- **Archivos**: transversal (core/, servicios/, infra/).
- **Done when**: sin usos de separadores hardcodeados en construcción de
  rutas; suite verde.
- **Riesgo**: bajo.

---

## BLOQUE 1 — Schema de BD para sincronización (Objetivo: base de datos lista, sin romper nada)

### Tarea 1.1 [M] — Tablas y columnas de sync
- **Qué**: añadir `sync_dispositivos`, `sync_tombstones`,
  `sync_stem_transfers`, `sync_estado` (CREATE TABLE IF NOT EXISTS) y columnas
  `sync_version` + `favorita_actualizada_en` vía `_agregar_columna_si_falta`.
- **Archivos**: `db/esquema.py`, `db/conexion.py`.
- **Done when**: BD nueva y BD existente migran sin error; `PRAGMA table_info`
  muestra las columnas; tests de migración verdes.
- **Riesgo**: bajo (solo aditivo). Mitigación: cubrir con test de migración
  sobre BD v1.0.x existente.

### Tarea 1.2 [M] — Incremento de `sync_version`
- **Qué**: lógica de servicio (o triggers) que incrementa `sync_version` desde
  `sync_estado` al modificar pistas/álbumes/artistas/playlists; registrar
  tombstones en borrados.
- **Archivos**: `servicios/biblioteca.py`, `servicios/indexador.py`,
  `db/esquema.py` (triggers opcionales).
- **Done when**: test que modifica una pista y verifica que su `sync_version`
  sube y que un borrado deja tombstone.
- **Riesgo**: medio (toca escrituras de biblioteca). Mitigación: centralizar
  el incremento en un helper único.

---

## BLOQUE 2 — Servidor local + discovery (Objetivo: el PC es alcanzable y emparejable)

### Tarea 2.1 [M] — Dependencias del módulo de sync
- **Qué**: añadir `aiohttp`, `zeroconf`, `qrcode` a `requirements.txt`, al
  catálogo de `infra/dependencias.py` y a `hiddenimports` de los 3 specs.
- **Archivos**: `requirements.txt`, `infra/dependencias.py`,
  `packaging/{linux,windows,macos}/nb_sound.spec`, `packaging/_common.py`.
- **Done when**: `dependencias.detectar()` lista las nuevas; build incluye los
  módulos.
- **Riesgo**: bajo.

### Tarea 2.2 [XL] — Servidor HTTP/WS + mDNS
- **Qué**: `servicios/servidor_sync.py` con aiohttp en hilo propio + event
  loop; endpoints `ping`/`pair`; anuncio Zeroconf; selección de puerto libre;
  TLS autofirmado + fingerprint; arranque/parada idempotentes.
- **Archivos**: `servicios/servidor_sync.py` (nuevo), `utils/network.py`.
- **Done when**: test de integración que arranca el servidor, hace `pair` con
  token válido (200) e inválido (401), y lo detiene limpio sin hilos colgados.
- **Riesgo**: alto. Mitigación: hilo aislado, sin tocar objetos Qt; teardown
  determinista con timeout; tests que verifican cierre.

### Tarea 2.3 [M] — Integración con ciclo de vida
- **Qué**: `ModeloSincronizacion` registrado en `construir_modelos`/
  `exponer_modelos` y añadido a `_ORDEN_CIERRE`; arranque bajo demanda.
- **Archivos**: `main_ui.py`, `ui/modelos_qml.py`.
- **Done when**: test de lifecycle: abrir/cerrar la app con servidor activo no
  deja hilos ni puertos abiertos.
- **Riesgo**: medio (cierre ordenado). Mitigación: reutilizar patrón de
  `cerrar()` existente.

---

## BLOQUE 3 — Protocolo de sincronización + transferencia (Objetivo: datos y audio viajan, reanudables)

### Tarea 3.1 [L] — Manifest delta
- **Qué**: endpoint `/manifest?since=` que arma el delta (pistas/álbumes/
  artistas/playlists/perfil + tombstones) desde `sync_version`.
- **Archivos**: `servicios/servidor_sync.py`, `servicios/biblioteca.py`.
- **Done when**: test que tras modificar N entidades, `/manifest?since=k`
  devuelve exactamente esas N y los tombstones correspondientes.
- **Riesgo**: medio.

### Tarea 3.2 [L] — Streaming de audio/assets con Range
- **Qué**: endpoints de audio/portada/lyrics con soporte `Range` (206) y
  ETag; validación de `hash_sha256`.
- **Archivos**: `servicios/servidor_sync.py`.
- **Done when**: test que descarga audio en dos tramos (Range) y el archivo
  reensamblado coincide en `hash_sha256`.
- **Riesgo**: medio (consistencia binaria). Mitigación: validar hash siempre.

### Tarea 3.3 [L] — Historial/favoritos (merge) + stems opt-in
- **Qué**: `POST /history` (merge last-write-wins de favoritos por timestamp;
  append de historial); endpoint de stems con estado en
  `sync_stem_transfers`.
- **Archivos**: `servicios/servidor_sync.py`, `servicios/biblioteca.py`.
- **Done when**: test que un favorito marcado en el "celular" (mock) gana por
  timestamp; transferencia de stems reanuda tras corte.
- **Riesgo**: medio (conflictos). Mitigación: regla de merge única y testeada.

### Tarea 3.4 [M] — Control remoto (WebSocket)
- **Qué**: canal WS `/control`: push de estado del reproductor (a partir de
  las señales de `ModeloReproductor`: `estadoCambiado`, `progresoCambiado`,
  `colaCambiada`, `volumenCambiado`, …) y recepción de comandos delegando en
  el servicio reproductor existente. *Bind exacto de métodos a confirmar
  contra `servicios/reproductor.py` en implementación.*
- **Archivos**: `servicios/servidor_sync.py`, `ui/modelos_qml.py`
  (puente señal→WS).
- **Done when**: test que un comando `pause` por WS pausa el reproductor y que
  un cambio de pista emite un frame de estado por WS.
- **Riesgo**: medio (thread-safety Qt↔hilo servidor). Mitigación: marshalling
  de comandos al hilo de Qt vía señales/`QMetaObject.invokeMethod`.

---

## BLOQUE 4 — Vista de sincronización (Objetivo: el usuario controla todo desde la UI, sin reiniciar)

### Tarea 4.1 [M] — Modelo + QR
- **Qué**: propiedades (servidor activo, dispositivos, QR, progreso) y slots
  (encender/apagar, revocar, transferir) en `ModeloSincronizacion`; QR con
  `qrcode`.
- **Archivos**: `ui/modelos_qml.py`.
- **Done when**: test que enciende el servidor desde el modelo y expone un QR
  no vacío con host/puerto/token.
- **Riesgo**: bajo.

### Tarea 4.2 [M] — Vista QML
- **Qué**: `VistaSincronizacion.qml` (dispositivos, estado, QR, progreso,
  historial de syncs) + entrada en `NavLateral`/`Principal.qml` (lazy).
- **Archivos**: `ui/qml/vistas/VistaSincronizacion.qml`, `ui/qml/Principal.qml`,
  `ui/qml/componentes/NavLateral.qml`.
- **Done when**: smoke test QML carga la vista sin `ReferenceError`; objetos
  con `objectName` presentes.
- **Riesgo**: bajo.

---

## BLOQUE 5 — Backup automático (Objetivo: respaldo/restauración fiable) — paralelizable

### Tarea 5.1 [M] — Exportación
- **Qué**: `servicios/backup.py` que genera `.nbsound-backup` (ZIP con
  `db.sqlite3` vía `VACUUM INTO`, assets, `manifest.json`+checksums); worker
  Qt; manual + programado.
- **Archivos**: `servicios/backup.py` (nuevo), `ui/modelos_qml.py`.
- **Done when**: test que crea un backup y valida que el ZIP contiene la BD y
  el manifest con checksums correctos.
- **Riesgo**: bajo.

### Tarea 5.2 [M] — Restauración
- **Qué**: validar manifest/checksums, restaurar a BD temporal, validar
  integridad, reemplazo atómico; reutilizar recuperación de
  `db/conexion.py`.
- **Archivos**: `servicios/backup.py`, `db/conexion.py`.
- **Done when**: test que restaura un backup sobre una BD distinta y la
  biblioteca resultante coincide.
- **Riesgo**: medio (reemplazo de BD viva). Mitigación: restaurar a temporal +
  swap atómico + validación previa.

---

## BLOQUE 6 — Tests de integración del ecosistema (Objetivo: extremo a extremo del lado PC)

### Tarea 6.1 [L] — E2E PC con cliente simulado
- **Qué**: test que simula un cliente móvil (mock HTTP/WS): pair → manifest →
  descarga audio (Range) → push historial → control por WS → revocar.
- **Archivos**: `tests/test_sync_e2e.py` (nuevo).
- **Done when**: el flujo completo pasa de forma determinista y reanudable.
- **Riesgo**: medio.

---

## BLOQUE 7 — Validación final cross-platform (Objetivo: lo nuevo funciona en los 3 SO)

### Tarea 7.1 [M] — Matriz CI
- **Qué**: ejecutar la suite (incluida la de sync) en Linux/Windows/macOS;
  validar bundle con el módulo de sync incluido.
- **Archivos**: `.github/workflows/*`, `docs/cross-platform.md` (actualizar
  tabla con el componente "Servidor local" resuelto).
- **Done when**: CI verde en los tres SO; tabla cross-platform sin gaps
  abiertos para el servidor.
- **Riesgo**: bajo.

---

## Secuencia global

```
BLOQUE 0 (gaps) ─┐
BLOQUE 1 (schema)─┼─► BLOQUE 2 (servidor) ─► BLOQUE 3 (protocolo) ─► BLOQUE 4 (vista) ─► BLOQUE 6 (E2E) ─► BLOQUE 7 (CI 3 SO)
BLOQUE 5 (backup) ── paralelo ───────────────────────────────────────────────────────┘
```

Cada bloque deja la suite verde antes de pasar al siguiente (regla del
proyecto). La app nunca requiere reinicio para aplicar cambios de estado.

---

← [architecture.md](architecture.md) · [mobile-ecosystem.md](mobile-ecosystem.md) ·
[cross-platform.md](cross-platform.md)
