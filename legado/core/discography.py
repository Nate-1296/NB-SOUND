from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from config.settings import (
    DISCOGRAPHY_IA_MIN_CONFIDENCE,
    ENABLE_IA_DISCOGRAPHY,
    RELEASE_TYPE_TO_FOLDER,
)
from infra.logger import obtener_logger
from utils.text import construir_slug_album, construir_slug_artista

_log = obtener_logger("discography")

_ALLOWED_BUCKETS = {"albumes", "singles_y_ep", "otros"}


class OrganizadorDiscografias:
    """Reorganiza biblioteca en base a manifiestos + sugerencia IA controlada."""

    def __init__(self, manifests_dir: Path, biblioteca_dir: Path, ia_client=None) -> None:
        self._tracks_dir = manifests_dir / "tracks"
        self._albums_dir = manifests_dir / "albums"
        self._biblioteca = biblioteca_dir
        self._ia = ia_client

    def ejecutar(self, dry_run: bool = False) -> dict:
        tracks = self._cargar_jsons(self._tracks_dir)
        albums = self._cargar_jsons(self._albums_dir)
        if not tracks or not albums:
            return {"artists": 0, "moves": 0, "note": "sin_manifests"}

        albums_by_id = {a.get("release_mbid") or a.get("album_id"): a for a in albums}
        artist_groups: dict[str, list[dict]] = {}
        for track in tracks:
            artist = (track.get("canonical_artist") or "").strip()
            if not artist:
                continue
            artist_groups.setdefault(artist, []).append(track)

        total_moves = 0
        artists_done = 0

        for artist, artist_tracks in artist_groups.items():
            plan = self._construir_plan_artist(artist, artist_tracks, albums_by_id)
            if ENABLE_IA_DISCOGRAPHY and self._ia and self._ia.activo:
                plan = self._aplicar_plan_ia(artist, plan)
            moves = self._aplicar_plan(plan, dry_run=dry_run)
            total_moves += moves
            artists_done += 1

        return {"artists": artists_done, "moves": total_moves, "dry_run": dry_run}

    def _construir_plan_artist(self, artist: str, tracks: list[dict], albums_by_id: dict) -> list[dict]:
        plan = []
        artist_slug = construir_slug_artista(artist)
        for tr in tracks:
            current = Path(tr.get("ruta_actual") or "")
            if not current.exists():
                continue
            rel_id = tr.get("release_mbid")
            album_data = albums_by_id.get(rel_id) or {}
            release_type = str(album_data.get("release_type") or "")
            target_bucket = RELEASE_TYPE_TO_FOLDER.get(release_type, "otros")
            album_name = tr.get("album") or album_data.get("canonical_title") or "sin_album"
            target_dir = self._biblioteca / artist_slug / target_bucket / construir_slug_album(str(album_name))
            target_path = target_dir / current.name
            plan.append({
                "track_id": tr.get("track_id"),
                "release_id": rel_id,
                "artist": artist,
                "release_type": release_type,
                "current_path": str(current),
                "target_bucket": target_bucket,
                "target_path": str(target_path),
                "confidence": 1.0 if release_type else 0.75,
            })
        return plan

    def _aplicar_plan_ia(self, artist: str, plan: list[dict]) -> list[dict]:
        if not plan:
            return plan
        releases = {}
        for row in plan:
            rid = row.get("release_id") or row.get("track_id")
            releases.setdefault(rid, {
                "release_id": rid,
                "release_type": row.get("release_type"),
                "current_bucket": row.get("target_bucket"),
                "track_count": 0,
            })
            releases[rid]["track_count"] += 1

        suggestion = self._ia.organizar_discografia(artist=artist, releases=list(releases.values()))
        if not suggestion:
            return plan

        valid_map = {
            item["release_id"]: item
            for item in suggestion
            if item.get("release_id") in releases
            and item.get("bucket") in _ALLOWED_BUCKETS
            and isinstance(item.get("confidence"), (float, int))
        }

        updated = []
        for row in plan:
            sid = valid_map.get(row.get("release_id") or row.get("track_id"))
            if not sid or float(sid.get("confidence", 0.0)) < DISCOGRAPHY_IA_MIN_CONFIDENCE:
                updated.append(row)
                continue
            row = dict(row)
            row["target_bucket"] = sid["bucket"]
            current = Path(row["current_path"])
            artist_slug = construir_slug_artista(row["artist"])
            row["target_path"] = str(
                self._biblioteca / artist_slug / sid["bucket"] / current.parent.name / current.name
            )
            row["confidence"] = float(sid["confidence"])
            updated.append(row)
        return updated

    def _aplicar_plan(self, plan: list[dict], dry_run: bool) -> int:
        moves = 0
        for row in plan:
            src = Path(row["current_path"])
            dst = Path(row["target_path"])
            if src == dst:
                continue
            if not src.exists():
                continue
            if dry_run:
                moves += 1
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst = self._resolver_conflicto(dst)
            shutil.move(str(src), str(dst))
            self._actualizar_manifest_track(row.get("track_id"), dst)
            moves += 1
        return moves

    def _actualizar_manifest_track(self, track_id: Optional[str], new_path: Path) -> None:
        if not track_id:
            return
        manifest = self._tracks_dir / f"{track_id}.json"
        if not manifest.exists():
            return
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["ruta_actual"] = str(new_path)
        manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _resolver_conflicto(path: Path) -> Path:
        if not path.exists():
            return path
        n = 2
        candidate = path.parent / f"{path.stem}_{n}{path.suffix}"
        while candidate.exists() and n < 10_000:
            n += 1
            candidate = path.parent / f"{path.stem}_{n}{path.suffix}"
        return candidate

    @staticmethod
    def _cargar_jsons(folder: Path) -> list[dict]:
        out = []
        for p in folder.glob("*.json"):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                _log.debug(f"Manifest inválido: {p}")
        return out
