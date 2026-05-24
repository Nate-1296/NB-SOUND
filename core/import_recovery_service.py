from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from config import settings
from core.audio_feature_store import persist_basic_analysis
from core.audio_features import AudioFeatureAnalyzer
from core.audio_intelligence_background import AudioIntelligenceBackgroundService
from core.assets_pipeline import PipelineAssets
from core.enrichment_pipeline import EnrichmentPipeline
from db.conexion import obtener_filas, obtener_una_fila
from domain.models import ArchivoAudio, CandidatoMB, DecisionArchivo, DecisionTipo
from external.cache import CacheLocal
from infra.logger import obtener_logger

_log = obtener_logger("import_recovery")


class ImportRecoveryService:
    """Diagnostico y reintentos post-import sin reingestar la biblioteca."""

    def __init__(self, *, assets_dir: Path | None = None) -> None:
        self.assets_dir = assets_dir or settings.DEFAULT_ASSETS_DIR

    def status(self) -> dict:
        tracks = self._library_tracks()
        assets_by_file = self._assets_manifest_by_file()
        enrichment_by_file = self._enrichment_manifest_by_file()
        total = len(tracks)

        missing_track_covers = 0
        missing_album_covers = 0
        missing_artist_images = 0
        missing_enrichment = 0
        missing_lyrics = 0

        for track in tracks:
            path = str(track.get("ruta_archivo") or "")
            asset_row = assets_by_file.get(path, {})
            if not self._asset_exists(asset_row.get("track_cover")) and not self._asset_exists(asset_row.get("track_cover_hd")):
                missing_track_covers += 1
            if not self._asset_exists(asset_row.get("album_cover")) and not self._asset_exists(asset_row.get("album_cover_hd")):
                missing_album_covers += 1
            if not self._asset_exists(asset_row.get("artist_avatar")) and not self._asset_exists(asset_row.get("artist_avatar_hd")):
                missing_artist_images += 1

            enrichment = enrichment_by_file.get(path)
            if not enrichment:
                missing_enrichment += 1
                missing_lyrics += 1
            else:
                lyrics = enrichment.get("lyrics") if isinstance(enrichment.get("lyrics"), dict) else {}
                has_lyrics = bool(str(lyrics.get("plain_lyrics") or "").strip() or str(lyrics.get("synced_lyrics") or "").strip())
                if not has_lyrics:
                    missing_lyrics += 1

        features_failed = obtener_una_fila(
            "SELECT COUNT(*) c FROM track_audio_features WHERE analysis_status='failed'"
        )["c"]
        features_ready = obtener_una_fila(
            "SELECT COUNT(*) c FROM track_audio_features WHERE analysis_status='ready'"
        )["c"]
        features_missing = max(0, total - int(features_ready or 0))
        deep_failed = obtener_una_fila(
            "SELECT COUNT(*) c FROM audio_analysis_jobs WHERE job_type='deep' AND status='failed'"
        )["c"]
        deep_pending = obtener_una_fila(
            "SELECT COUNT(*) c FROM audio_analysis_jobs WHERE job_type='deep' AND status IN ('pending','paused','running')"
        )["c"]

        return {
            "ok": True,
            "total_tracks": total,
            "missing_track_covers": missing_track_covers,
            "missing_album_covers": missing_album_covers,
            "missing_artist_images": missing_artist_images,
            "missing_visual_assets": len(
                [
                    1
                    for track in tracks
                    if self._track_needs_assets(track, assets_by_file, {"track", "album", "artist"})
                ]
            ),
            "missing_enrichment": missing_enrichment,
            "missing_lyrics": missing_lyrics,
            "audio_features_missing": features_missing,
            "audio_features_failed": int(features_failed or 0),
            "deep_failed": int(deep_failed or 0),
            "deep_pending": int(deep_pending or 0),
        }

    def retry_assets_missing(self, *, kinds: set[str] | None = None, limit: int = 0, clear_negative_cache: bool = True) -> dict:
        kinds = kinds or {"track", "album", "artist"}
        assets_by_file = self._assets_manifest_by_file()
        pipeline = PipelineAssets(self.assets_dir)
        processed = 0
        skipped = 0
        failed = 0
        tracks = self._library_tracks()
        total_tracks = len(tracks)
        print(f"\nIniciando reintento de assets (Tipos: {kinds}) sobre {total_tracks} pistas...")
        
        for i, track in enumerate(tracks, 1):
            if limit and processed >= limit:
                break
                
            if i % 10 == 0 or i == total_tracks:
                print(f"Progreso: {i}/{total_tracks} (Procesados: {processed}, Omitidos: {skipped}, Fallidos: {failed})", end="\r", flush=True)
                
            if not self._track_needs_assets(track, assets_by_file, kinds):
                skipped += 1
                continue
            path = Path(str(track.get("ruta_archivo") or ""))
            if not path.exists():
                skipped += 1
                continue
            try:
                if clear_negative_cache:
                    self._clear_asset_negative_cache(track, kinds)
                pipeline.procesar(self._decision_from_track(track))
                processed += 1
            except Exception as exc:
                failed += 1
                _log.warning("No se pudo reintentar assets para %s: %s", path, exc)
                
        print("\n\n--- Resumen de Reintento de Assets ---")
        print(f"Pistas procesadas (descarga intentada): {processed}")
        print(f"Pistas omitidas (ya completas o no existen): {skipped}")
        print(f"Pistas fallidas: {failed}\n")
        
        return {**self.status(), "processed": processed, "skipped": skipped, "failed": failed, "action": "retry_assets_missing"}

    def retry_enrichment_missing(self, *, lyrics_only: bool = False, limit: int = 0) -> dict:
        enrichment_by_file = self._enrichment_manifest_by_file()
        processed = 0
        skipped = 0
        failed = 0

        pipeline = EnrichmentPipeline(self.assets_dir)
        # Desactivar análisis local de audio en la instancia para evitar
        # mutación de settings globales desde un hilo worker.
        pipeline._local_basic_enabled = False
        pipeline._local_deep_enabled = False

        tracks = self._library_tracks()
        total_tracks = len(tracks)
        print(f"\nIniciando reintento de enriquecimiento (Solo letras: {lyrics_only}) sobre {total_tracks} pistas...")

        for i, track in enumerate(tracks, 1):
            if limit and processed >= limit:
                break

            if i % 10 == 0 or i == total_tracks:
                print(f"Progreso: {i}/{total_tracks} (Procesados: {processed}, Omitidos: {skipped}, Fallidos: {failed})", end="\r", flush=True)

            path_text = str(track.get("ruta_archivo") or "")
            enrichment = enrichment_by_file.get(path_text)
            if lyrics_only:
                if enrichment and self._manifest_has_lyrics(enrichment):
                    skipped += 1
                    continue
            else:
                if enrichment and self._manifest_has_lyrics(enrichment) and self._manifest_has_analysis(enrichment):
                    skipped += 1
                    continue
            path = Path(path_text)
            if not path.exists():
                skipped += 1
                continue
            try:
                pipeline.procesar(self._decision_from_track(track))
                processed += 1
            except Exception as exc:
                failed += 1
                _log.warning("No se pudo reintentar enrichment para %s: %s", path, exc)

        print("\n\n--- Resumen de Reintento de Enriquecimiento ---")
        print(f"Pistas procesadas: {processed}")
        print(f"Pistas omitidas: {skipped}")
        print(f"Pistas fallidas: {failed}\n")

        return {**self.status(), "processed": processed, "skipped": skipped, "failed": failed, "action": "retry_lyrics_missing" if lyrics_only else "retry_enrichment_missing"}

    def retry_audio_features_failed(self, *, include_missing: bool = True, limit: int = 0) -> dict:
        where = ["p.estado='biblioteca'"]
        if include_missing:
            where.append("(taf.track_id IS NULL OR taf.analysis_status='failed')")
        else:
            where.append("taf.analysis_status='failed'")
        rows = obtener_filas(
            f"""
            SELECT p.id, p.ruta_archivo
            FROM pistas p
            LEFT JOIN track_audio_features taf ON taf.track_id=CAST(p.id AS TEXT)
            WHERE {' AND '.join(where)}
            ORDER BY p.id
            """
        )
        analyzer = AudioFeatureAnalyzer()
        processed = 0
        skipped = 0
        failed = 0
        mode = "standard" if settings.AUDIO_FEATURES_ANALYZE_FULL_TRACK else settings.AUDIO_FEATURES_MODE
        for row in rows:
            if limit and processed >= limit:
                break
            path = Path(str(row["ruta_archivo"] or ""))
            if not path.exists():
                skipped += 1
                continue
            result = analyzer.analyze(str(row["id"]), path, mode=mode)
            persist_basic_analysis(None, self.assets_dir, result)
            if result.analysis_status == "ready":
                processed += 1
            else:
                failed += 1
        return {**self.status(), "processed": processed, "skipped": skipped, "failed": failed, "action": "retry_audio_features_failed"}

    def retry_deep_failed(self) -> dict:
        snapshot = AudioIntelligenceBackgroundService(base_dir=self.assets_dir).retry_failed()
        return {**self.status(), "deep_snapshot": snapshot, "action": "retry_deep_failed"}

    def retry_sidecars_failed(self) -> dict:
        assets = self.retry_assets_missing()
        enrichment = self.retry_enrichment_missing()
        return {
            **self.status(),
            "assets": assets,
            "enrichment": enrichment,
            "processed": int(assets.get("processed") or 0) + int(enrichment.get("processed") or 0),
            "failed": int(assets.get("failed") or 0) + int(enrichment.get("failed") or 0),
            "action": "retry_sidecars_failed",
        }

    def _library_tracks(self) -> list[dict]:
        rows = obtener_filas(
            """
            SELECT id, titulo, artista_nombre, album_titulo, duracion_seg, ruta_archivo,
                   nombre_archivo, tamano_bytes, hash_sha256, mb_recording_id, mb_release_id
            FROM pistas
            WHERE estado='biblioteca'
            ORDER BY id
            """
        )
        return [dict(row) for row in rows]

    def _decision_from_track(self, track: dict) -> DecisionArchivo:
        path = Path(str(track.get("ruta_archivo") or ""))
        archivo = ArchivoAudio(
            ruta_original=path,
            tamano_bytes=int(track.get("tamano_bytes") or 0),
            hash_sha256=str(track.get("hash_sha256") or ""),
        )
        candidato = CandidatoMB(
            recording_id=str(track.get("mb_recording_id") or ""),
            release_id=str(track.get("mb_release_id") or ""),
            titulo_oficial=str(track.get("titulo") or path.stem),
            artista_principal=str(track.get("artista_nombre") or ""),
            album_oficial=str(track.get("album_titulo") or ""),
            duracion_seg=track.get("duracion_seg"),
        )
        decision = DecisionArchivo(
            tipo=DecisionTipo.ACEPTADO,
            archivo=archivo,
            candidato_elegido=candidato,
        )
        decision.ruta_destino = path
        return decision

    def _assets_manifest_by_file(self) -> dict[str, dict]:
        return self._manifest_by_file(self.assets_dir / "assets_manifest.jsonl", "archivo")

    def _enrichment_manifest_by_file(self) -> dict[str, dict]:
        return self._manifest_by_file(self.assets_dir / "enrichment" / "enrichment_manifest.jsonl", "file")

    @staticmethod
    def _manifest_by_file(path: Path, key: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        if not path.exists():
            return out
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    file_path = str(row.get(key) or "").strip()
                    if file_path:
                        out[file_path] = row
        except OSError as exc:
            _log.warning("No se pudo leer manifest %s: %s", path, exc)
        return out

    @staticmethod
    def _asset_exists(value) -> bool:
        text = str(value or "").strip()
        return bool(text and Path(text).exists())

    @staticmethod
    def _manifest_has_lyrics(enrichment: dict) -> bool:
        lyrics = enrichment.get("lyrics") if isinstance(enrichment.get("lyrics"), dict) else {}
        return bool(str(lyrics.get("plain_lyrics") or "").strip() or str(lyrics.get("synced_lyrics") or "").strip())

    @staticmethod
    def _manifest_has_analysis(enrichment: dict) -> bool:
        audio_analytics = enrichment.get("audio_analytics")
        if not isinstance(audio_analytics, dict):
            return False
        return audio_analytics.get("status") == "computed"

    def _track_needs_assets(self, track: dict, assets_by_file: dict[str, dict], kinds: Iterable[str]) -> bool:
        row = assets_by_file.get(str(track.get("ruta_archivo") or ""), {})
        kinds_set = set(kinds)
        if "track" in kinds_set and not self._asset_exists(row.get("track_cover")) and not self._asset_exists(row.get("track_cover_hd")):
            return True
        if "album" in kinds_set and not self._asset_exists(row.get("album_cover")) and not self._asset_exists(row.get("album_cover_hd")):
            return True
        if "artist" in kinds_set and not self._asset_exists(row.get("artist_avatar")) and not self._asset_exists(row.get("artist_avatar_hd")):
            return True
        return False

    def _clear_asset_negative_cache(self, track: dict, kinds: Iterable[str]) -> None:
        cache = CacheLocal(directorio=self.assets_dir / "cache")
        kinds_set = set(kinds)
        artist = str(track.get("artista_nombre") or "").strip()
        album = str(track.get("album_titulo") or "").strip()
        if artist and "artist" in kinds_set:
            cache.invalidar(CacheLocal.construir_clave("assets_artist_lookup", {"artist": artist}))
        if artist and album and "album" in kinds_set:
            cache.invalidar(CacheLocal.construir_clave("assets_album_cover_lookup", {"artist": artist, "album": album}))
