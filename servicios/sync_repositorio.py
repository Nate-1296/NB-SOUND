# =============================================================================
# servicios/sync_repositorio.py
#
# Capa de datos del ecosistema movil (lado PC). Sin dependencias de Qt ni de
# red: solo SQLite. El servidor (`servicios/servidor_sync.py`) y el modelo Qt
# (`ui/modelos_qml.ModeloSincronizacion`) la consumen.
#
# Responsabilidades:
#   - Dispositivos emparejados: alta (pair), listado, revocacion, tokens.
#   - Manifest delta: arma el conjunto de cambios desde una `sync_version`.
#   - Merge de historial/favoritos provenientes del celular (last-write-wins).
#   - Estado de transferencia de stems (reanudable).
#   - Resolucion de rutas de audio/portada para los endpoints binarios.
#
# Reglas de merge (ver docs/mobile-ecosystem.md, seccion B):
#   - PC gana en metadata enriquecida (read-only para el celular).
#   - Celular gana en su historial; el favorito es bidireccional y se resuelve
#     por `favorita_actualizada_en` (timestamp ISO-8601 UTC).
# =============================================================================

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from db.conexion import (
    ejecutar,
    marcar_sync_version,
    obtener_filas,
    obtener_una_fila,
    sync_version_actual,
    transaccion,
)
from infra.logger import obtener_logger

_log = obtener_logger("sync_repositorio")

# Version del protocolo de sincronizacion. El cliente la compara en /ping.
PROTOCOLO_VERSION = 1

_PLATAFORMAS_VALIDAS = {"android", "ios", "ipados", "tablet", "desconocida"}


# -----------------------------------------------------------------------------
# Utilidades
# -----------------------------------------------------------------------------

def _ahora_iso() -> str:
    """Timestamp UTC ISO-8601 con milisegundos y sufijo Z (orden lexicografico)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def generar_token() -> str:
    """Token opaco URL-safe para credenciales de dispositivo (256 bits)."""
    return secrets.token_urlsafe(32)


def _normalizar_plataforma(valor: Optional[str]) -> str:
    v = (valor or "").strip().lower()
    return v if v in _PLATAFORMAS_VALIDAS else "desconocida"


# -----------------------------------------------------------------------------
# Dispositivos emparejados
# -----------------------------------------------------------------------------

def registrar_dispositivo(nombre: str, plataforma: Optional[str] = None) -> dict:
    """Empareja un dispositivo nuevo y devuelve su registro (incluye token).

    Emite un `device_token` persistente de larga vida que el cliente usa para
    autenticar todas las llamadas siguientes (header Authorization).
    """
    nombre_limpio = (nombre or "").strip() or "Dispositivo móvil"
    token = generar_token()
    plataforma_norm = _normalizar_plataforma(plataforma)
    with transaccion() as con:
        cur = con.execute(
            """
            INSERT INTO sync_dispositivos(device_token, nombre, plataforma, ultima_conexion)
            VALUES (?, ?, ?, ?)
            """,
            (token, nombre_limpio, plataforma_norm, _ahora_iso()),
        )
        dispositivo_id = cur.lastrowid
    return obtener_dispositivo(dispositivo_id) or {}


def _fila_dispositivo(fila) -> dict:
    d = dict(fila)
    d["revocado"] = bool(d.get("revocado"))
    try:
        d["seleccion"] = json.loads(d.get("seleccion_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        d["seleccion"] = {}
    return d


def obtener_dispositivo(dispositivo_id: int) -> Optional[dict]:
    fila = obtener_una_fila(
        "SELECT * FROM sync_dispositivos WHERE id = ?", (int(dispositivo_id),)
    )
    return _fila_dispositivo(fila) if fila else None


def obtener_dispositivo_por_token(device_token: str) -> Optional[dict]:
    """Devuelve el dispositivo activo (no revocado) dueño del token, o None."""
    if not device_token:
        return None
    fila = obtener_una_fila(
        "SELECT * FROM sync_dispositivos WHERE device_token = ? AND revocado = 0",
        (device_token,),
    )
    return _fila_dispositivo(fila) if fila else None


def listar_dispositivos(incluir_revocados: bool = False) -> list[dict]:
    sql = "SELECT * FROM sync_dispositivos"
    if not incluir_revocados:
        sql += " WHERE revocado = 0"
    sql += " ORDER BY (ultima_conexion IS NULL), ultima_conexion DESC, id DESC"
    return [_fila_dispositivo(f) for f in obtener_filas(sql)]


def revocar_dispositivo(dispositivo_id: int) -> bool:
    """Revoca un dispositivo: invalida su token para futuras peticiones."""
    cur = ejecutar(
        "UPDATE sync_dispositivos SET revocado = 1 WHERE id = ? AND revocado = 0",
        (int(dispositivo_id),),
    )
    return cur.rowcount > 0


def tocar_dispositivo(dispositivo_id: int) -> None:
    """Actualiza `ultima_conexion` al instante actual (best-effort)."""
    ejecutar(
        "UPDATE sync_dispositivos SET ultima_conexion = ? WHERE id = ?",
        (_ahora_iso(), int(dispositivo_id)),
    )


def guardar_ultima_sync_version(dispositivo_id: int, version: int) -> None:
    ejecutar(
        "UPDATE sync_dispositivos SET ultima_sync_version = ? WHERE id = ?",
        (int(version), int(dispositivo_id)),
    )


def guardar_seleccion(dispositivo_id: int, seleccion: dict) -> None:
    """Persiste qué sincroniza este device (todo/nada/por playlist/artista)."""
    ejecutar(
        "UPDATE sync_dispositivos SET seleccion_json = ? WHERE id = ?",
        (json.dumps(seleccion or {}, ensure_ascii=False), int(dispositivo_id)),
    )


# -----------------------------------------------------------------------------
# Manifest delta
# -----------------------------------------------------------------------------

def _pistas_desde(since: int) -> list[dict]:
    filas = obtener_filas(
        """
        SELECT
            p.id, p.titulo, p.artista_nombre, p.album_titulo, p.album_id,
            p.artista_id, p.track_number, p.duracion_seg, p.anio, p.genero,
            p.isrc, p.mb_recording_id, p.favorita, p.favorita_actualizada_en,
            p.hash_sha256, p.sync_version,
            taf.bpm AS bpm, taf.energy AS energy, taf.key_name AS key_name
        FROM pistas p
        LEFT JOIN track_audio_features taf ON taf.track_id = CAST(p.id AS TEXT)
        WHERE p.sync_version > ?
        ORDER BY p.sync_version ASC
        """,
        (int(since),),
    )
    pistas = []
    for fila in filas:
        d = dict(fila)
        pid = d["id"]
        pistas.append(
            {
                "id": pid,
                "titulo": d.get("titulo"),
                "artista_nombre": d.get("artista_nombre"),
                "album_titulo": d.get("album_titulo"),
                "album_id": d.get("album_id"),
                "artista_id": d.get("artista_id"),
                "track_number": d.get("track_number"),
                "duracion_seg": d.get("duracion_seg"),
                "anio": d.get("anio"),
                "genero": d.get("genero"),
                "isrc": d.get("isrc"),
                "mb_recording_id": d.get("mb_recording_id"),
                "favorita": bool(d.get("favorita")),
                "favorita_actualizada_en": d.get("favorita_actualizada_en"),
                "hash_sha256": d.get("hash_sha256"),
                "sync_version": d.get("sync_version"),
                # Audio features básicas en plano (coincide con el esquema Drift
                # del móvil: bpm?/energy?/key?). Ver nb_sound_mobile/docs/local-data.md.
                "bpm": d.get("bpm"),
                "energy": d.get("energy"),
                "key": d.get("key_name"),
                "audio_url": f"/api/v1/track/{pid}/audio",
                "cover_url": f"/api/v1/asset/cover/{d.get('album_id')}" if d.get("album_id") else None,
                "lyrics_url": f"/api/v1/track/{pid}/lyrics",
            }
        )
    return pistas


def _albums_desde(since: int) -> list[dict]:
    filas = obtener_filas(
        """
        SELECT id, titulo, artista_id, tipo, anio, sync_version
        FROM albums WHERE sync_version > ? ORDER BY sync_version ASC
        """,
        (int(since),),
    )
    return [
        {
            "id": f["id"],
            "titulo": f["titulo"],
            "artista_id": f["artista_id"],
            "tipo": f["tipo"],
            "anio": f["anio"],
            "sync_version": f["sync_version"],
            "cover_url": f"/api/v1/asset/cover/{f['id']}",
        }
        for f in obtener_filas_a_dicts(filas)
    ]


def _artistas_desde(since: int) -> list[dict]:
    filas = obtener_filas(
        """
        SELECT id, nombre, sync_version FROM artistas
        WHERE sync_version > ? ORDER BY sync_version ASC
        """,
        (int(since),),
    )
    return [
        {
            "id": f["id"],
            "nombre": f["nombre"],
            "sync_version": f["sync_version"],
            "imagen_url": f"/api/v1/asset/artist/{f['id']}",
        }
        for f in obtener_filas_a_dicts(filas)
    ]


def _playlists_desde(since: int) -> list[dict]:
    filas = obtener_filas(
        """
        SELECT id, nombre, tipo, auto_key, sync_version
        FROM playlists
        WHERE sync_version > ? AND visible = 1
        ORDER BY sync_version ASC
        """,
        (int(since),),
    )
    playlists = []
    for f in obtener_filas_a_dicts(filas):
        pistas_ids = [
            r["pista_id"]
            for r in obtener_filas(
                "SELECT pista_id FROM pistas_playlist WHERE playlist_id = ? ORDER BY posicion ASC",
                (f["id"],),
            )
        ]
        playlists.append(
            {
                "id": f["id"],
                "nombre": f["nombre"],
                "tipo": f["tipo"],
                "auto_key": f["auto_key"],
                "sync_version": f["sync_version"],
                "pista_ids": pistas_ids,
            }
        )
    return playlists


def obtener_filas_a_dicts(filas) -> list[dict]:
    """Convierte filas sqlite3.Row a dicts (helper de legibilidad)."""
    return [dict(f) for f in filas]


def _tombstones_desde(since: int) -> list[dict]:
    return [
        {"entidad": f["entidad"], "entidad_id": f["entidad_id"], "sync_version": f["sync_version"]}
        for f in obtener_filas(
            "SELECT entidad, entidad_id, sync_version FROM sync_tombstones WHERE sync_version > ? ORDER BY sync_version ASC",
            (int(since),),
        )
    ]


def _perfil_resumen() -> dict:
    """Perfil + estadisticas agregadas (solo lectura hacia el celular)."""
    total_pistas = (obtener_una_fila("SELECT COUNT(*) c FROM pistas") or {"c": 0})["c"]
    total_favoritas = (
        obtener_una_fila("SELECT COUNT(*) c FROM pistas WHERE favorita = 1") or {"c": 0}
    )["c"]
    nombre = ""
    foto = ""
    try:
        fila_n = obtener_una_fila("SELECT valor FROM config_ui WHERE clave = 'nombre_usuario'")
        fila_f = obtener_una_fila("SELECT valor FROM config_ui WHERE clave = 'foto_perfil'")
        nombre = fila_n["valor"] if fila_n else ""
        foto = fila_f["valor"] if fila_f else ""
    except Exception:
        pass
    return {
        "nombre": nombre,
        "foto": foto,
        "estadisticas": {"total_pistas": total_pistas, "total_favoritas": total_favoritas},
    }


def _ids_playlists_a_pistas(playlist_ids: list[int]) -> set[int]:
    if not playlist_ids:
        return set()
    marcadores = ",".join("?" for _ in playlist_ids)
    filas = obtener_filas(
        f"SELECT DISTINCT pista_id FROM pistas_playlist WHERE playlist_id IN ({marcadores})",
        tuple(int(p) for p in playlist_ids),
    )
    return {f["pista_id"] for f in filas}


def _aplicar_seleccion(manifest: dict, seleccion: Optional[dict]) -> dict:
    """Filtra el delta segun la seleccion del dispositivo.

    Modos (seleccion["modo"]): 'todo' (default), 'nada', 'artistas', 'playlists'.
      - todo  : sin filtrar.
      - nada  : sin entidades (se conservan tombstones y la version).
      - artistas: solo pistas/albums/artistas de `artista_ids`; sin playlists.
      - playlists: solo `playlist_ids` y las pistas que contienen (+ sus albums
        y artistas); el resto de playlists se omite.
    Los tombstones y la version SIEMPRE viajan (para propagar borrados).
    """
    if not seleccion:
        return manifest
    modo = str(seleccion.get("modo") or "todo").lower()
    if modo == "todo":
        return manifest
    if modo == "nada":
        manifest["pistas"] = []
        manifest["albums"] = []
        manifest["artistas"] = []
        manifest["playlists"] = []
        return manifest
    if modo == "artistas":
        permitidos = {int(a) for a in (seleccion.get("artista_ids") or [])}
        manifest["pistas"] = [p for p in manifest["pistas"] if p.get("artista_id") in permitidos]
        manifest["albums"] = [a for a in manifest["albums"] if a.get("artista_id") in permitidos]
        manifest["artistas"] = [a for a in manifest["artistas"] if a.get("id") in permitidos]
        manifest["playlists"] = []
        return manifest
    if modo == "playlists":
        playlist_ids = {int(p) for p in (seleccion.get("playlist_ids") or [])}
        pistas_permitidas = _ids_playlists_a_pistas(list(playlist_ids))
        manifest["pistas"] = [p for p in manifest["pistas"] if p.get("id") in pistas_permitidas]
        albums_ok = {p.get("album_id") for p in manifest["pistas"] if p.get("album_id")}
        artistas_ok = {p.get("artista_id") for p in manifest["pistas"] if p.get("artista_id")}
        manifest["albums"] = [a for a in manifest["albums"] if a.get("id") in albums_ok]
        manifest["artistas"] = [a for a in manifest["artistas"] if a.get("id") in artistas_ok]
        manifest["playlists"] = [pl for pl in manifest["playlists"] if pl.get("id") in playlist_ids]
        return manifest
    return manifest


def construir_manifest(
    since: int = 0, *, seleccion: Optional[dict] = None, incluir_perfil: bool = True
) -> dict:
    """Arma el delta de cambios desde `since` (exclusivo).

    Devuelve solo entidades con `sync_version > since` y los tombstones del
    mismo rango, opcionalmente filtrado por la `seleccion` del dispositivo
    (todo/nada/artistas/playlists). `sync_version_actual` en la raiz es el
    high-water mark que el cliente debe guardar para pedir el siguiente delta
    (`sync_version` se mantiene como alias por compatibilidad).
    """
    since = max(0, int(since or 0))
    version = sync_version_actual()
    manifest = {
        "protocolo": PROTOCOLO_VERSION,
        "since": since,
        "sync_version_actual": version,
        "sync_version": version,  # alias compatible
        "generado_en": _ahora_iso(),
        "pistas": _pistas_desde(since),
        "albums": _albums_desde(since),
        "artistas": _artistas_desde(since),
        "playlists": _playlists_desde(since),
        "tombstones": _tombstones_desde(since),
    }
    manifest = _aplicar_seleccion(manifest, seleccion)
    if incluir_perfil:
        manifest["perfil"] = _perfil_resumen()
    return manifest


# -----------------------------------------------------------------------------
# Merge de historial / favoritos (celular -> PC)
# -----------------------------------------------------------------------------

def aplicar_historial_remoto(payload: dict) -> dict:
    """Aplica historial y favoritos provenientes del celular.

    payload = {
        "historial": [ {pista_id, reproducido_en, duracion_seg?, completada?}, ... ],
        "favoritos": [ {pista_id, favorita: bool, actualizada_en: ISO8601}, ... ],
    }

    Favoritos: last-write-wins por `actualizada_en`. Solo se sobrescribe el
    valor del PC si el timestamp remoto es estrictamente mas reciente que el
    `favorita_actualizada_en` local (None local = el remoto siempre gana).
    Historial: append idempotente best-effort (se inserta una fila por evento).
    """
    historial = payload.get("historial") or []
    favoritos = payload.get("favoritos") or []
    insertados = 0
    favoritos_aplicados = 0
    favoritos_ignorados = 0
    ids_favoritos_aplicados: list[int] = []

    with transaccion() as con:
        for ev in historial:
            try:
                pista_id = int(ev.get("pista_id"))
            except (TypeError, ValueError):
                continue
            fila = con.execute(
                "SELECT titulo, artista_nombre FROM pistas WHERE id = ?", (pista_id,)
            ).fetchone()
            titulo_snap = fila["titulo"] if fila else None
            artista_snap = fila["artista_nombre"] if fila else None
            con.execute(
                """
                INSERT INTO historial(pista_id, titulo_snap, artista_snap, reproducido_en, duracion_seg, completada)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    pista_id,
                    titulo_snap,
                    artista_snap,
                    str(ev.get("reproducido_en") or _ahora_iso()),
                    ev.get("duracion_seg"),
                    1 if ev.get("completada", True) else 0,
                ),
            )
            insertados += 1

        for fav in favoritos:
            try:
                pista_id = int(fav.get("pista_id"))
            except (TypeError, ValueError):
                continue
            ts_remoto = str(fav.get("actualizada_en") or "").strip()
            nuevo_valor = 1 if fav.get("favorita") else 0
            fila = con.execute(
                "SELECT favorita, favorita_actualizada_en FROM pistas WHERE id = ?",
                (pista_id,),
            ).fetchone()
            if not fila:
                continue
            ts_local = (fila["favorita_actualizada_en"] or "").strip()
            # Last-write-wins: el remoto gana si su timestamp es mas reciente
            # (los timestamps son ISO-8601 UTC con sufijo Z => orden lexico).
            if ts_local and ts_remoto and ts_remoto <= ts_local:
                favoritos_ignorados += 1
                continue
            if not ts_remoto:
                # Sin timestamp remoto no podemos comparar: no pisamos el PC.
                favoritos_ignorados += 1
                continue
            con.execute(
                "UPDATE pistas SET favorita = ?, favorita_actualizada_en = ?, actualizado_en = datetime('now') WHERE id = ?",
                (nuevo_valor, ts_remoto, pista_id),
            )
            favoritos_aplicados += 1
            ids_favoritos_aplicados.append(pista_id)

    # El bump de sync_version se hace fuera de la transaccion de merge para no
    # anidar locks de escritura, y solo sobre los favoritos efectivamente
    # aplicados (los ignorados no cambiaron, no deben re-aparecer en el delta).
    for pista_id in ids_favoritos_aplicados:
        try:
            marcar_sync_version("pistas", pista_id)
        except Exception:
            pass

    return {
        "historial_insertado": insertados,
        "favoritos_aplicados": favoritos_aplicados,
        "favoritos_ignorados": favoritos_ignorados,
    }


# -----------------------------------------------------------------------------
# Transferencia de stems (reanudable)
# -----------------------------------------------------------------------------

def estado_stem(dispositivo_id: int, pista_id: int) -> Optional[dict]:
    fila = obtener_una_fila(
        "SELECT * FROM sync_stem_transfers WHERE dispositivo_id = ? AND pista_id = ?",
        (int(dispositivo_id), int(pista_id)),
    )
    return dict(fila) if fila else None


def registrar_progreso_stem(
    dispositivo_id: int, pista_id: int, estado: str, bytes_enviados: int = 0
) -> None:
    """Upsert del estado de transferencia de stems (pending/in_progress/done/failed)."""
    ejecutar(
        """
        INSERT INTO sync_stem_transfers(dispositivo_id, pista_id, estado, bytes_enviados, actualizado_en)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(dispositivo_id, pista_id) DO UPDATE SET
            estado = excluded.estado,
            bytes_enviados = excluded.bytes_enviados,
            actualizado_en = excluded.actualizado_en
        """,
        (int(dispositivo_id), int(pista_id), str(estado), int(bytes_enviados)),
    )


# -----------------------------------------------------------------------------
# Resolucion de rutas binarias (para los endpoints de audio/portada/stems)
# -----------------------------------------------------------------------------

def ruta_audio_pista(pista_id: int) -> Optional[Path]:
    fila = obtener_una_fila("SELECT ruta_archivo FROM pistas WHERE id = ?", (int(pista_id),))
    if not fila or not fila["ruta_archivo"]:
        return None
    ruta = Path(fila["ruta_archivo"])
    return ruta if ruta.is_file() else None


def ruta_stem_pista(pista_id: int) -> Optional[Path]:
    """Ruta del instrumental de karaoke si la pista lo tiene generado."""
    fila = obtener_una_fila(
        "SELECT karaoke_ruta_instrumental, karaoke_estado FROM pistas WHERE id = ?",
        (int(pista_id),),
    )
    if not fila or not fila["karaoke_ruta_instrumental"]:
        return None
    ruta = Path(fila["karaoke_ruta_instrumental"])
    return ruta if ruta.is_file() else None


def ruta_portada_album(album_id: int) -> Optional[Path]:
    fila = obtener_una_fila("SELECT portada_ruta FROM albums WHERE id = ?", (int(album_id),))
    if not fila or not fila["portada_ruta"]:
        return None
    ruta = Path(fila["portada_ruta"])
    return ruta if ruta.is_file() else None


def ruta_hash_pista(pista_id: int) -> Optional[str]:
    fila = obtener_una_fila("SELECT hash_sha256 FROM pistas WHERE id = ?", (int(pista_id),))
    return fila["hash_sha256"] if fila and fila["hash_sha256"] else None
