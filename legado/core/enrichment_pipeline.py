from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from config import settings
from config.settings import ENABLE_EXTERNAL_ENRICHMENT
from core.audio_analysis_runs import AudioRunTracker
from core.audio_analytics import AudioAnalyticsExtractor
from core.audio_feature_store import persist_basic_analysis
from core.audio_features import ANALYZER_VERSION as BASIC_ANALYZER_VERSION, AudioFeatureAnalyzer
from db.conexion import obtener_una_fila
from domain.models import DecisionArchivo
from external.lyrics_client import LyricsClient
from infra.logger import obtener_logger

_log = obtener_logger("enrichment")


class EnrichmentPipeline:
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self._external_enabled = ENABLE_EXTERNAL_ENRICHMENT
        self._local_basic_enabled = settings.ENABLE_AUDIO_FEATURES and settings.AUDIO_FEATURES_ANALYZE_ON_IMPORT
        self._enabled = self._external_enabled or self._local_basic_enabled
        self._base = (base_dir or settings.DEFAULT_ASSETS_DIR) / "enrichment"
        self._base.mkdir(parents=True, exist_ok=True)
        self._lyrics = LyricsClient()
        self._analytics = AudioAnalyticsExtractor()
        self._audio_features = AudioFeatureAnalyzer()
        self._manifest = self._base / "enrichment_manifest.jsonl"

    @property
    def active(self) -> bool:
        return self._enabled

    def procesar(self, decision: DecisionArchivo) -> None:
        if not self._enabled:
            return
        if decision.candidato_elegido is None or decision.ruta_destino is None:
            return

        self._procesar_enriquecimiento_local(decision)
        if not self._external_enabled:
            decision.esquema_explicacion.setdefault(
                "enrichment",
                {
                    "lyrics_status": "disabled",
                    "lyrics_provider": "",
                    "analytics_status": "disabled",
                },
            )
            return

        candidato = decision.candidato_elegido
        lyrics = self._lyrics.fetch(
            artist=candidato.artista_principal,
            title=candidato.titulo_oficial,
            duration=candidato.duracion_seg,
            album=candidato.album_oficial,
        )
        cruda = decision.archivo.metadata_cruda
        lyrics = self._aplicar_fallback_embebido(lyrics, cruda)
        analytics = self._analytics.extract(decision.ruta_destino)
        acoustid = decision.archivo.resultado_acoustid

        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "file": str(decision.ruta_destino),
            "recording_id": candidato.recording_id,
            "release_id": candidato.release_id,
            "release_group_id": candidato.release_group_id,
            "lyrics": {
                "status": lyrics.status,
                "provider": lyrics.provider,
                "plain_lyrics": lyrics.plain_lyrics,
                "synced_lyrics": lyrics.synced_lyrics,
                "language": lyrics.language,
                "instrumental": lyrics.instrumental,
                "is_translation": lyrics.is_translation,
                "confidence": lyrics.confidence,
                "match_method": lyrics.match_method,
                "fetched_at": lyrics.fetched_at,
            },
            "audio_analytics": analytics.to_dict(),
            "embedded": {
                "lyrics_plain": cruda.lyrics_plain if cruda else None,
                "lyrics_synced": cruda.lyrics_synced if cruda else None,
                "disc_number": cruda.disc_number if cruda else None,
                "total_discs": cruda.total_discs if cruda else None,
                "composer": cruda.composer if cruda else None,
                "composer_sort": cruda.composer_sort if cruda else None,
                "lyricist": cruda.lyricist if cruda else None,
                "arranger": cruda.arranger if cruda else None,
                "conductor": cruda.conductor if cruda else None,
                "director": cruda.director if cruda else None,
                "djmixer": cruda.djmixer if cruda else None,
                "engineer": cruda.engineer if cruda else None,
                "mixer": cruda.mixer if cruda else None,
                "producer": cruda.producer if cruda else None,
                "remixer": cruda.remixer if cruda else None,
                "writer": cruda.writer if cruda else None,
                "work": cruda.work if cruda else None,
                "performer_roles": cruda.performer_roles if cruda else {},
                "musicbrainz_ids": cruda.musicbrainz_ids if cruda else {},
                "iswc": (cruda.musicbrainz_ids.get("iswc") if cruda and cruda.musicbrainz_ids else None),
                "acoustid_id": cruda.acoustid_id if cruda else None,
                "acoustid_fingerprint": cruda.acoustid_fingerprint if cruda else None,
            },
            "acoustid": {
                "recording_ids": acoustid.recording_ids if acoustid else [],
                "scores": acoustid.scores if acoustid else [],
                "fingerprint": acoustid.fingerprint if acoustid else "",
            },
        }

        decision.esquema_explicacion.setdefault(
            "enrichment",
            {
                "lyrics_status": lyrics.status,
                "lyrics_provider": lyrics.provider,
                "analytics_status": analytics.status,
            },
        )

        self._manifest.parent.mkdir(parents=True, exist_ok=True)
        with self._manifest.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    @staticmethod
    def _aplicar_fallback_embebido(lyrics, cruda):
        if lyrics.status in {"found", "partial"} and (lyrics.plain_lyrics or lyrics.synced_lyrics):
            return lyrics
        if cruda is None:
            return lyrics
        plain = str(cruda.lyrics_plain or "").strip()
        synced = str(cruda.lyrics_synced or "").strip()
        if not plain and not synced:
            return lyrics
        from external.lyrics_client import LyricsResult

        return LyricsResult(
            status="found" if plain or synced else "not_found",
            provider="embedded_tags",
            plain_lyrics=plain,
            synced_lyrics=synced,
            confidence=0.70 if synced else 0.62,
            match_method=f"embedded_after_{lyrics.provider or lyrics.status}",
            fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    def _procesar_enriquecimiento_local(self, decision: DecisionArchivo) -> None:
        if not decision.ruta_destino or not decision.ruta_destino.exists():
            return
        track_id = self._resolver_track_id(decision)
        file_path = decision.ruta_destino
        if self._local_basic_enabled:
            self._procesar_audio_features_post_import(track_id, file_path)

    def _resolver_track_id(self, decision: DecisionArchivo) -> str:
        ruta = str(decision.ruta_destino or "")
        try:
            fila = obtener_una_fila("SELECT id FROM pistas WHERE ruta_archivo = ?", (ruta,))
            if fila:
                return str(fila["id"])
            try:
                from servicios.indexador import IndexadorBiblioteca

                IndexadorBiblioteca(Path(ruta).parent).indexar_archivo_nuevo(Path(ruta))
                fila = obtener_una_fila("SELECT id FROM pistas WHERE ruta_archivo = ?", (ruta,))
                if fila:
                    return str(fila["id"])
            except Exception as exc:
                _log.warning("No se pudo indexar pista para enrichment local: %s", exc)
        except Exception as exc:
            _log.warning("No se pudo resolver pista para enrichment local: %s", exc)
        return ruta

    def _debe_analizar_basic(self, track_id: str) -> bool:
        row = obtener_una_fila(
            "SELECT analysis_status, analyzer_version FROM track_audio_features WHERE track_id=?",
            (track_id,),
        )
        if not row or row["analysis_status"] != "ready":
            return True
        return bool(
            settings.AUDIO_FEATURES_REANALYZE_ON_VERSION_CHANGE
            and row["analyzer_version"] != BASIC_ANALYZER_VERSION
        )

    def _procesar_audio_features_post_import(self, track_id: str, file_path: Path) -> None:
        try:
            if not self._debe_analizar_basic(track_id):
                return
            mode = "standard" if settings.AUDIO_FEATURES_ANALYZE_FULL_TRACK else settings.AUDIO_FEATURES_MODE
            run = AudioRunTracker("audio_features_basic", {"trigger": "post_import", "track_id": track_id, "analysis_mode": mode})
            run.set_total(1)
            job_id = run.register_job(track_id, "basic", current_file_path=str(file_path), current_stage="audio_features_basic")
            result = self._audio_features.analyze(track_id, file_path, mode=mode)
            persist_basic_analysis(None, settings.DEFAULT_ASSETS_DIR, result)
            run.finish_job(
                job_id,
                "ready" if result.analysis_status == "ready" else "failed",
                result.error_code or "",
                result.error_message or "",
                current_track_id=track_id,
                current_file_path=str(file_path),
                current_stage="audio_features_basic",
            )
            run.finish()
        except Exception as exc:
            _log.warning("No se pudo completar audio features post-import: %s", exc)
            if not settings.AUDIO_FEATURES_FAIL_SILENTLY:
                raise
