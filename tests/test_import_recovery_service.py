from __future__ import annotations

import json
from pathlib import Path

import pytest

from db.conexion import cerrar_db, get_conexion, inicializar_db


def _insert_track(path: Path) -> int:
    cur = get_conexion().execute(
        """
        INSERT INTO pistas(titulo, artista_nombre, album_titulo, ruta_archivo, nombre_archivo, tamano_bytes, hash_sha256, estado)
        VALUES('Tema', 'Artista', 'Album', ?, ?, 10, 'hash-1', 'biblioteca')
        """,
        (str(path), path.name),
    )
    return cur.lastrowid


def test_import_recovery_status_reporta_faltantes_controlados(tmp_path: Path):
    inicializar_db(tmp_path / "recovery_status.sqlite")
    try:
        audio = tmp_path / "tema.mp3"
        audio.write_bytes(b"fake")
        _insert_track(audio)

        from core.import_recovery_service import ImportRecoveryService

        status = ImportRecoveryService(assets_dir=tmp_path / "assets").status()

        assert status["total_tracks"] == 1
        assert status["missing_visual_assets"] == 1
        assert status["missing_lyrics"] == 1
        assert status["audio_features_missing"] == 1
    finally:
        cerrar_db()


def test_import_recovery_reintenta_assets_e_invalida_cache_negativa(tmp_path: Path, monkeypatch):
    inicializar_db(tmp_path / "recovery_assets.sqlite")
    try:
        audio = tmp_path / "tema.mp3"
        audio.write_bytes(b"fake")
        _insert_track(audio)

        from core.assets_pipeline import PipelineAssets
        from core.import_recovery_service import ImportRecoveryService
        from external.cache import CacheLocal

        assets_dir = tmp_path / "assets"
        cache = CacheLocal(directorio=assets_dir / "cache")
        key = CacheLocal.construir_clave("assets_artist_lookup", {"artist": "Artista"})
        cache.guardar_con_ttl(key, "__NO_ASSET__", 999)
        assert cache.obtener(key) == "__NO_ASSET__"

        def fake_procesar(self, decision):
            cover = assets_dir / "cover.jpg"
            artist = assets_dir / "artist.jpg"
            cover.parent.mkdir(parents=True, exist_ok=True)
            cover.write_bytes(b"img")
            artist.write_bytes(b"img")
            self._manifest.parent.mkdir(parents=True, exist_ok=True)
            with self._manifest.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "archivo": str(decision.ruta_destino),
                    "track_cover": str(cover),
                    "album_cover": str(cover),
                    "artist_avatar": str(artist),
                }) + "\n")

        monkeypatch.setattr(PipelineAssets, "procesar", fake_procesar)

        out = ImportRecoveryService(assets_dir=assets_dir).retry_assets_missing()

        assert out["processed"] == 1
        assert out["missing_visual_assets"] == 0
        assert cache.obtener(key) is None
    finally:
        cerrar_db()


# ---------------------------------------------------------------------------
# Tests para persist_basic_analysis(None, ...) — bug conn=None corregido
# ---------------------------------------------------------------------------

def test_retry_audio_features_failed_no_crashea_con_conn_none(tmp_path, monkeypatch):
    """retry_audio_features_failed debe funcionar sin NoneType error tras el fix en audio_feature_store."""
    inicializar_db(tmp_path / "feat_retry.sqlite")
    try:
        audio = tmp_path / "tema.mp3"
        audio.write_bytes(b"\x00" * 64)
        track_id = _insert_track(audio)

        from core.audio_features import AudioFeatureAnalyzer, AudioFeatureResult
        from core.import_recovery_service import ImportRecoveryService

        def fake_analyze(self, tid, path, mode="light"):
            return AudioFeatureResult(
                track_id=tid, file_path=str(path), file_hash="h",
                analysis_status="ready", energy=0.6, danceability_proxy=0.6,
                melancholy_proxy=0.3, calmness_proxy=0.4,
                workout_score_proxy=0.5, party_score_proxy=0.5,
                focus_score_proxy=0.4, night_score_proxy=0.3,
            )

        monkeypatch.setattr(AudioFeatureAnalyzer, "analyze", fake_analyze)

        out = ImportRecoveryService(assets_dir=tmp_path / "assets").retry_audio_features_failed(include_missing=True)

        assert out["processed"] >= 1
        assert out["failed"] == 0
        assert out["action"] == "retry_audio_features_failed"
        row = get_conexion().execute(
            "SELECT analysis_status FROM track_audio_features WHERE track_id=?",
            (str(track_id),),
        ).fetchone()
        assert row is not None
        assert row["analysis_status"] == "ready"
    finally:
        cerrar_db()


def test_retry_audio_features_failed_no_doble_cuenta_fallidos(tmp_path, monkeypatch):
    """processed y failed no deben solaparse: un análisis fallido suma en failed, no en processed."""
    inicializar_db(tmp_path / "feat_fail_count.sqlite")
    try:
        audio = tmp_path / "tema.mp3"
        audio.write_bytes(b"\x00" * 64)
        _insert_track(audio)

        from core.audio_features import AudioFeatureAnalyzer, AudioFeatureResult
        from core.import_recovery_service import ImportRecoveryService

        def fake_analyze_failed(self, tid, path, mode="light"):
            return AudioFeatureResult(
                track_id=tid, file_path=str(path), file_hash="h",
                analysis_status="failed", error_code="test_error",
            )

        monkeypatch.setattr(AudioFeatureAnalyzer, "analyze", fake_analyze_failed)

        out = ImportRecoveryService(assets_dir=tmp_path / "assets").retry_audio_features_failed(include_missing=True)

        assert out["processed"] == 0
        assert out["failed"] == 1
        assert out["processed"] + out["failed"] + out["skipped"] <= 1
    finally:
        cerrar_db()


def test_retry_enrichment_no_muta_settings_globales(tmp_path, monkeypatch):
    """retry_enrichment_missing no debe mutar settings.AUDIO_FEATURES_ANALYZE_ON_IMPORT globalmente."""
    inicializar_db(tmp_path / "enrichment_settings.sqlite")
    try:
        import config.settings as settings
        from core.enrichment_pipeline import EnrichmentPipeline
        from core.import_recovery_service import ImportRecoveryService

        valor_original = settings.AUDIO_FEATURES_ANALYZE_ON_IMPORT

        monkeypatch.setattr(EnrichmentPipeline, "procesar", lambda self, d: None)

        ImportRecoveryService(assets_dir=tmp_path / "assets").retry_enrichment_missing(lyrics_only=True)

        assert settings.AUDIO_FEATURES_ANALYZE_ON_IMPORT == valor_original, (
            "retry_enrichment_missing mutó settings.AUDIO_FEATURES_ANALYZE_ON_IMPORT globalmente"
        )
    finally:
        cerrar_db()


# ---------------------------------------------------------------------------
# Tests para _manifest_has_analysis — método nuevo añadido
# ---------------------------------------------------------------------------

def test_manifest_has_analysis_detecta_computed():
    from core.import_recovery_service import ImportRecoveryService

    svc = ImportRecoveryService.__new__(ImportRecoveryService)
    assert svc._manifest_has_analysis({"audio_analytics": {"status": "computed"}}) is True
    assert svc._manifest_has_analysis({"audio_analytics": {"status": "not_computed"}}) is False
    assert svc._manifest_has_analysis({"audio_analytics": {"status": "error"}}) is False
    assert svc._manifest_has_analysis({}) is False
    assert svc._manifest_has_analysis({"audio_analytics": None}) is False
    assert svc._manifest_has_analysis({"audio_analytics": "computed"}) is False


def test_retry_enrichment_no_crashea_con_manifest_has_analysis(tmp_path, monkeypatch):
    """retry_enrichment_missing(lyrics_only=False) no debe crash al llamar _manifest_has_analysis."""
    inicializar_db(tmp_path / "enrichment_retry.sqlite")
    try:
        audio = tmp_path / "tema.mp3"
        audio.write_bytes(b"\x00" * 64)
        _insert_track(audio)

        assets_dir = tmp_path / "assets"
        enrichment_dir = assets_dir / "enrichment"
        enrichment_dir.mkdir(parents=True)
        manifest = enrichment_dir / "enrichment_manifest.jsonl"
        manifest.write_text(
            json.dumps({
                "file": str(audio),
                "lyrics": {"plain_lyrics": "letra", "synced_lyrics": ""},
                "audio_analytics": {"status": "computed"},
            }) + "\n",
            encoding="utf-8",
        )

        from core.enrichment_pipeline import EnrichmentPipeline
        from core.import_recovery_service import ImportRecoveryService

        monkeypatch.setattr(EnrichmentPipeline, "procesar", lambda self, d: None)

        out = ImportRecoveryService(assets_dir=assets_dir).retry_enrichment_missing(lyrics_only=False)

        assert out["skipped"] >= 1
        assert out["action"] == "retry_enrichment_missing"
    finally:
        cerrar_db()


def test_retry_enrichment_lyrics_only_omite_tracks_con_letra(tmp_path, monkeypatch):
    """retry_enrichment_missing(lyrics_only=True) debe saltarse tracks con letras ya presentes."""
    inicializar_db(tmp_path / "enrichment_lyrics.sqlite")
    try:
        audio = tmp_path / "tema.mp3"
        audio.write_bytes(b"\x00" * 64)
        _insert_track(audio)

        assets_dir = tmp_path / "assets"
        enrichment_dir = assets_dir / "enrichment"
        enrichment_dir.mkdir(parents=True)
        manifest = enrichment_dir / "enrichment_manifest.jsonl"
        manifest.write_text(
            json.dumps({
                "file": str(audio),
                "lyrics": {"plain_lyrics": "letra completa", "synced_lyrics": ""},
                "audio_analytics": {"status": "not_computed"},
            }) + "\n",
            encoding="utf-8",
        )

        from core.enrichment_pipeline import EnrichmentPipeline
        from core.import_recovery_service import ImportRecoveryService

        monkeypatch.setattr(EnrichmentPipeline, "procesar", lambda self, d: None)

        out = ImportRecoveryService(assets_dir=assets_dir).retry_enrichment_missing(lyrics_only=True)

        assert out["skipped"] >= 1
        assert out["processed"] == 0
    finally:
        cerrar_db()
