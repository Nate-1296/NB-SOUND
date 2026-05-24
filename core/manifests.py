from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings
from config.settings import MANIFEST_SCHEMA_VERSION
from db.conexion import obtener_filas, obtener_una_fila, ejecutar
from domain.models import DecisionArchivo
from infra.logger import obtener_logger
from utils.text import para_comparacion

_log = obtener_logger("manifests")


class GestorManifests:
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self._base = base_dir or settings.DEFAULT_MANIFESTS_DIR
        self._tracks = self._base / "tracks"
        self._albums = self._base / "albums"
        self._artists = self._base / "artists"
        for d in (self._tracks, self._albums, self._artists):
            d.mkdir(parents=True, exist_ok=True)

    def escribir_decision(self, decision: DecisionArchivo) -> None:
        if decision.candidato_elegido is None:
            return
        track_data = self._track_manifest(decision)
        track_key = track_data["track_id"]
        track_path = self._tracks / f"{track_key}.json"
        self._write_json(track_path, track_data)
        self._index("track", track_key, track_path)

        album_data = self._album_manifest(decision, track_data)
        album_key = album_data["album_id"]
        album_path = self._albums / f"{album_key}.json"
        self._merge_album(album_path, album_data)
        self._index("album", album_key, album_path)

        artist_data = self._artist_manifest(decision, track_data)
        artist_key = artist_data["artist_id"]
        artist_path = self._artists / f"{artist_key}.json"
        self._merge_artist(artist_path, artist_data)
        self._index("artist", artist_key, artist_path)

    def explicar(self, target: str) -> Optional[dict]:
        ruta = Path(target)
        if ruta.exists() and ruta.suffix.lower() == ".mp3":
            key = self._stable_id(str(ruta.resolve()))
            data = self._buscar_por_indice("track", key)
            if data:
                return data

        for entity in ("track", "album", "artist"):
            data = self._buscar_por_indice(entity, target)
            if data:
                return data

        # Fallback operativo cuando DB no está inicializada:
        # buscar directamente por nombre de archivo de manifiesto.
        for folder in (self._tracks, self._albums, self._artists):
            candidate = folder / f"{target}.json"
            data = self._load_json(candidate)
            if data:
                return data
        return None

    def rebuild(self) -> dict:
        rebuilt = 0
        try:
            filas = obtener_filas(
                "SELECT ruta_archivo, titulo, artista_nombre, album_titulo, isrc, mb_recording_id, mb_release_id, hash_sha256 FROM pistas"
            )
        except RuntimeError:
            return {"tracks_rebuilt": 0, "note": "db_not_initialized"}
        for row in filas:
            key = self._canonical_track_id(
                recording_mbid=row["mb_recording_id"],
                isrc=row["isrc"],
                release_mbid=row["mb_release_id"],
                release_group_mbid=None,
                fingerprint=None,
                audio_hash=row["hash_sha256"],
                path=row["ruta_archivo"],
            )
            legacy = self._stable_id(row["ruta_archivo"])
            data = {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "track_id": key,
                "track_id_legacy": legacy,
                "ruta_actual": row["ruta_archivo"],
                "filename": Path(row["ruta_archivo"]).name,
                "canonical_artist": row["artista_nombre"],
                "canonical_title": row["titulo"],
                "album": row["album_titulo"],
                "recording_mbid": row["mb_recording_id"],
                "release_mbid": row["mb_release_id"],
                "isrcs": [row["isrc"]] if row["isrc"] else [],
                "decision": "biblioteca",
                "decision_reason": "rebuild",
                "score_final": None,
                "score_breakdown": {},
                "sources": ["db_rebuild"],
                "timestamps": {"updated_at": datetime.now(timezone.utc).isoformat()},
            }
            path = self._tracks / f"{key}.json"
            self._write_json(path, data)
            self._index("track", key, path)
            rebuilt += 1
        return {"tracks_rebuilt": rebuilt}

    def _track_manifest(self, decision: DecisionArchivo) -> dict:
        c = decision.candidato_elegido
        archivo = decision.archivo
        path = str((decision.ruta_destino or archivo.ruta_original).resolve())
        key = self._canonical_track_id(
            recording_mbid=c.recording_id,
            isrc=(archivo.isrc_disponible or c.isrc),
            release_mbid=c.release_id,
            release_group_mbid=c.release_group_id,
            fingerprint=(archivo.resultado_acoustid.fingerprint if archivo.resultado_acoustid else None),
            audio_hash=archivo.hash_sha256,
            path=path,
        )
        legacy_key = self._stable_id(path)
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "track_id": key,
            "track_id_legacy": legacy_key,
            "ruta_actual": path,
            "filename": Path(path).name,
            "canonical_artist": c.artista_principal,
            "canonical_title": c.titulo_oficial,
            "artist_mbids": [],
            "recording_mbid": c.recording_id,
            "release_mbid": c.release_id,
            "release_group_mbid": c.release_group_id,
            "isrcs": [x for x in [archivo.isrc_disponible, c.isrc] if x],
            "decision": decision.tipo.value,
            "decision_reason": decision.mensaje_decision,
            "score_final": decision.puntaje_maximo,
            "score_breakdown": c.puntaje_detalle,
            "sources": [f.value for f in decision.fuentes_usadas],
            "timestamps": {"written_at": datetime.now(timezone.utc).isoformat()},
            "fingerprint": (archivo.resultado_acoustid.fingerprint if archivo.resultado_acoustid else None),
            "hash": archivo.hash_sha256,
            "duplicate": decision.info_duplicado,
            "override": decision.override_aplicado,
            "assets": decision.esquema_explicacion.get("asset_selection", {}),
            "provisional": decision.tipo.value == "aceptado_provisional",
            "explain": decision.esquema_explicacion,
        }

    def _album_manifest(self, decision: DecisionArchivo, track_data: dict) -> dict:
        c = decision.candidato_elegido
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "album_id": c.release_id or para_comparacion(f"{c.artista_principal}-{c.album_oficial}"),
            "canonical_title": c.album_oficial,
            "artists": [c.artista_principal],
            "release_mbid": c.release_id,
            "release_group_mbid": c.release_group_id,
            "release_type": c.tipo_release,
            "year": c.anio_release,
            "canonical_folder": str((decision.ruta_destino.parent if decision.ruta_destino else Path(""))),
            "tracks": [{"track_id": track_data["track_id"], "title": track_data["canonical_title"]}],
            "assets": decision.esquema_explicacion.get("asset_selection", {}).get("album", {}),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _artist_manifest(self, decision: DecisionArchivo, track_data: dict) -> dict:
        c = decision.candidato_elegido
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "artist_id": para_comparacion(c.artista_principal),
            "canonical_name": c.artista_principal,
            "aliases": [],
            "artist_mbid": "",
            "canonical_folder": str((decision.ruta_destino.parent.parent if decision.ruta_destino else Path(""))),
            "assets": decision.esquema_explicacion.get("asset_selection", {}).get("artist", {}),
            "links": {},
            "overrides": [decision.override_aplicado] if decision.override_aplicado else [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "tracks": [track_data["track_id"]],
        }

    def _merge_album(self, path: Path, data: dict) -> None:
        old = self._load_json(path) or {}
        tracks = {t["track_id"]: t for t in old.get("tracks", [])}
        for t in data.get("tracks", []):
            tracks[t["track_id"]] = t
        data["tracks"] = list(tracks.values())
        self._write_json(path, {**old, **data})

    def _merge_artist(self, path: Path, data: dict) -> None:
        old = self._load_json(path) or {}
        tracks = set(old.get("tracks", [])) | set(data.get("tracks", []))
        overrides = [x for x in (old.get("overrides", []) + data.get("overrides", [])) if x]
        data["tracks"] = sorted(tracks)
        data["overrides"] = overrides
        self._write_json(path, {**old, **data})

    def _index(self, entity_type: str, entity_key: str, path: Path) -> None:
        ejecutar(
            """
            INSERT INTO manifests_index(entity_type, entity_key, manifest_path, schema_version, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(entity_type, entity_key) DO UPDATE SET
                manifest_path=excluded.manifest_path,
                schema_version=excluded.schema_version,
                updated_at=excluded.updated_at
            """,
            (entity_type, entity_key, str(path), MANIFEST_SCHEMA_VERSION),
        )
        if entity_type == "track":
            # compat backward: también indexar por id legado basado en ruta
            data = self._load_json(path) or {}
            legacy = data.get("track_id_legacy")
            if legacy and legacy != entity_key:
                ejecutar(
                    """
                    INSERT INTO manifests_index(entity_type, entity_key, manifest_path, schema_version, updated_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(entity_type, entity_key) DO UPDATE SET
                        manifest_path=excluded.manifest_path,
                        schema_version=excluded.schema_version,
                        updated_at=excluded.updated_at
                    """,
                    ("track", legacy, str(path), MANIFEST_SCHEMA_VERSION),
                )

    def _buscar_por_indice(self, entity_type: str, entity_key: str) -> Optional[dict]:
        try:
            row = obtener_una_fila(
                "SELECT manifest_path FROM manifests_index WHERE entity_type=? AND entity_key=?",
                (entity_type, entity_key),
            )
        except RuntimeError:
            return None
        if not row:
            return None
        return self._load_json(Path(row["manifest_path"]))

    @staticmethod
    def _load_json(path: Path) -> Optional[dict]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _stable_id(raw: str) -> str:
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _canonical_track_id(
        *,
        recording_mbid: Optional[str],
        isrc: Optional[str],
        release_mbid: Optional[str],
        release_group_mbid: Optional[str],
        fingerprint: Optional[str],
        audio_hash: Optional[str],
        path: str,
    ) -> str:
        rec = (recording_mbid or "").strip()
        if rec:
            return f"rec:{rec}"
        isrc_norm = (isrc or "").strip().upper()
        if isrc_norm:
            if release_mbid:
                return f"isrc:{isrc_norm}|rel:{release_mbid}"
            if release_group_mbid:
                return f"isrc:{isrc_norm}|rg:{release_group_mbid}"
            return f"isrc:{isrc_norm}"
        fp = (fingerprint or "").strip()
        if fp:
            return f"fp:{hashlib.sha1(fp.encode('utf-8')).hexdigest()}"
        if audio_hash:
            return f"sha256:{audio_hash}"
        return f"pathsha1:{hashlib.sha1(path.encode('utf-8')).hexdigest()}"
