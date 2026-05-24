from __future__ import annotations

from pathlib import Path

import pytest

from db.conexion import cerrar_db, get_conexion, guardar_config, inicializar_db
from core.audio_intelligence_background import (
    BACKGROUND_MODE,
    AudioIntelligenceBackgroundService,
)
from core.audio_intelligence_deep import ANALYZER_VERSION as DEEP_ANALYZER_VERSION


class FakeDeepAnalyzer:
    model_dir_configured = True

    def __init__(self, model_dir: Path):
        self.model_dir = model_dir

    def backend_available(self):
        return True, ""

    def available_models(self):
        return [{"model_id": "fake", "is_available": True, "enabled": True}]

    def analyze(self, track_id: str, audio_path: str):
        return {
            "track_id": str(track_id),
            "analyzer_version": DEEP_ANALYZER_VERSION,
            "analysis_status": "ready",
            "mood_happy": 0.8,
            "mood_sad": 0.1,
            "mood_relaxed": 0.4,
            "mood_aggressive": 0.2,
            "mood_party": 0.6,
            "danceability_model": 0.7,
            "arousal": 0.5,
            "valence": 0.8,
            "embeddings_path": "",
            "embeddings_dim": 2,
            "tags_json": "{}",
            "model_outputs_json": '{"fake": 1}',
            "raw_output_json": '{"path": "%s"}' % audio_path,
            "model_summary_json": '{"successful_models": ["fake"]}',
            "inference_time_ms": 1,
            "error_code": "",
            "error_message": "",
            "started_at": "2026-01-01T00:00:00Z",
            "analyzed_at": "2026-01-01T00:00:01Z",
        }


def _configure(tmp_path: Path):
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    for key, value in {
        "enable_audio_intelligence_deep": "1",
        "audio_intelligence_background": "1",
        "audio_intelligence_backend": "essentia_tensorflow",
        "audio_intelligence_model_dir": str(model_dir),
        "enable_audio_mood_models": "1",
        "enable_audio_embeddings": "1",
        "enable_audio_tagging_models": "1",
        "audio_intelligence_analyze_after_import_background": "1",
        "audio_intelligence_background_autostart": "0",
        "audio_intelligence_retry_failed": "0",
        "audio_intelligence_max_attempts": "2",
        "audio_intelligence_background_idle_delay_sec": "0",
    }.items():
        guardar_config(key, value)
    return model_dir


def _insert_track(track_id: int, path: str, file_hash: str):
    get_conexion().execute(
        """
        INSERT INTO pistas(id, titulo, artista_nombre, album_titulo, ruta_archivo, nombre_archivo, tamano_bytes, hash_sha256, estado)
        VALUES(?,?,?,?,?,?,?,?, 'biblioteca')
        """,
        (track_id, f"T{track_id}", "A", "B", path, Path(path).name, 10, file_hash),
    )


def _service(tmp_path: Path, model_dir: Path):
    return AudioIntelligenceBackgroundService(
        base_dir=tmp_path,
        analyzer_factory=lambda: FakeDeepAnalyzer(model_dir),
    )


def test_background_enqueue_idempotente_y_no_reencola_ready(tmp_path: Path):
    inicializar_db(tmp_path / "bg.sqlite")
    model_dir = _configure(tmp_path)
    _insert_track(1, "/music/a.mp3", "h1")
    _insert_track(2, "/music/b.mp3", "h2")
    get_conexion().execute(
        """
        INSERT INTO track_deep_audio_features(track_id, file_hash, analyzer_version, analysis_status)
        VALUES('2', ?, ?, 'ready')
        """,
        ("h2", DEEP_ANALYZER_VERSION),
    )

    svc = _service(tmp_path, model_dir)
    first = svc.enqueue_pending_tracks()
    second = svc.enqueue_pending_tracks()

    assert first["created_jobs"] == 1
    assert second["created_jobs"] == 0
    assert get_conexion().execute("SELECT COUNT(*) c FROM audio_analysis_jobs").fetchone()["c"] == 1
    cerrar_db()


def test_background_process_persiste_ready_run_id_y_eta(tmp_path: Path):
    inicializar_db(tmp_path / "process.sqlite")
    model_dir = _configure(tmp_path)
    _insert_track(1, "/music/a.mp3", "h1")

    svc = _service(tmp_path, model_dir)
    svc.enqueue_pending_tracks()
    out = svc.process_pending(idle_delay_sec=0)

    assert out["estado"] == "completado"
    assert out["ready"] == 1
    assert out["pendientes"] == 0
    row = get_conexion().execute("SELECT * FROM track_deep_audio_features WHERE track_id='1'").fetchone()
    assert row["analysis_status"] == "ready"
    assert row["last_run_id"] == out["run_id"]
    run = get_conexion().execute("SELECT * FROM audio_analysis_runs WHERE run_id=?", (out["run_id"],)).fetchone()
    assert run["status"] == "completed"
    assert run["eta_human"] == "0s"
    cerrar_db()


def test_background_recover_running_huerfano(tmp_path: Path):
    inicializar_db(tmp_path / "recover.sqlite")
    _configure(tmp_path)
    run_id = "run-dead"
    get_conexion().execute(
        "INSERT INTO audio_analysis_runs(run_id, mode, status, started_at) VALUES(?,?, 'running', datetime('now'))",
        (run_id, BACKGROUND_MODE),
    )
    get_conexion().execute(
        """
        INSERT INTO audio_analysis_jobs(job_id, run_id, track_id, job_type, status, model_version, file_hash)
        VALUES('job-dead', ?, '1', 'deep', 'running', ?, 'h')
        """,
        (run_id, DEEP_ANALYZER_VERSION),
    )

    snapshot = AudioIntelligenceBackgroundService().recover_interrupted_jobs()
    job = get_conexion().execute("SELECT status FROM audio_analysis_jobs WHERE job_id='job-dead'").fetchone()
    run = get_conexion().execute("SELECT status FROM audio_analysis_runs WHERE run_id=?", (run_id,)).fetchone()
    assert snapshot["recovered_jobs"] == 1
    assert job["status"] == "pending"
    assert run["status"] == "pending"
    cerrar_db()


def test_background_pause_resume_cancel_keep(tmp_path: Path):
    inicializar_db(tmp_path / "pause.sqlite")
    model_dir = _configure(tmp_path)
    _insert_track(1, "/music/a.mp3", "h1")
    svc = _service(tmp_path, model_dir)
    snapshot = svc.enqueue_pending_tracks()
    run_id = snapshot["run_id"]

    paused = svc.pause(run_id=run_id)
    assert paused["estado"] == "pausado"
    assert get_conexion().execute("SELECT status FROM audio_analysis_jobs").fetchone()["status"] == "paused"

    resumed = svc.resume(run_id=run_id)
    assert resumed["estado"] == "pendiente"
    assert get_conexion().execute("SELECT status FROM audio_analysis_jobs").fetchone()["status"] == "pending"

    cancelled = svc.cancel_keep(run_id=run_id)
    assert cancelled["estado"] == "cancelado"
    assert get_conexion().execute("SELECT status FROM audio_analysis_jobs").fetchone()["status"] == "cancelled_keep"
    cerrar_db()


def test_background_resume_sin_jobs_no_encola_biblioteca(tmp_path: Path):
    inicializar_db(tmp_path / "resume_empty.sqlite")
    model_dir = _configure(tmp_path)
    _insert_track(1, "/music/a.mp3", "h1")

    svc = _service(tmp_path, model_dir)
    resumed = svc.resume()
    processed = svc.process_pending(enqueue_missing=False, idle_delay_sec=0)

    assert "No hay jobs deep pendientes" in resumed["mensaje"]
    assert "No hay jobs deep pendientes" in processed["mensaje"]
    assert get_conexion().execute("SELECT COUNT(*) c FROM audio_analysis_jobs").fetchone()["c"] == 0
    cerrar_db()


def test_background_cancel_discard_borra_outputs_de_run(tmp_path: Path):
    inicializar_db(tmp_path / "discard.sqlite")
    model_dir = _configure(tmp_path)
    _insert_track(1, "/music/a.mp3", "h1")
    svc = _service(tmp_path, model_dir)
    svc.enqueue_pending_tracks()
    out = svc.process_pending(idle_delay_sec=0)

    discarded = svc.cancel_discard(run_id=out["run_id"])

    assert discarded["estado"] == "cancelado"
    assert get_conexion().execute("SELECT COUNT(*) c FROM track_deep_audio_features").fetchone()["c"] == 0
    assert get_conexion().execute("SELECT status FROM audio_analysis_jobs").fetchone()["status"] == "cancelled_discard"
    cerrar_db()


def test_background_no_reintenta_failed_si_config_false(tmp_path: Path):
    inicializar_db(tmp_path / "failed.sqlite")
    model_dir = _configure(tmp_path)
    _insert_track(1, "/music/a.mp3", "h1")
    run_id = "run-failed"
    get_conexion().execute(
        "INSERT INTO audio_analysis_runs(run_id, mode, status, started_at) VALUES(?,?, 'completed', datetime('now'))",
        (run_id, BACKGROUND_MODE),
    )
    get_conexion().execute(
        """
        INSERT INTO audio_analysis_jobs(job_id, run_id, track_id, job_type, status, attempts, max_attempts, model_version, file_hash)
        VALUES('job-failed', ?, '1', 'deep', 'failed', 1, 2, ?, 'h1')
        """,
        (run_id, DEEP_ANALYZER_VERSION),
    )

    out = _service(tmp_path, model_dir).enqueue_pending_tracks()

    assert out["skipped_failed"] == 1
    assert get_conexion().execute("SELECT status FROM audio_analysis_jobs").fetchone()["status"] == "failed"
    cerrar_db()


def test_background_retry_failed_no_encola_tracks_sin_failed(tmp_path: Path):
    inicializar_db(tmp_path / "retry_empty.sqlite")
    model_dir = _configure(tmp_path)
    _insert_track(1, "/music/a.mp3", "h1")

    out = _service(tmp_path, model_dir).retry_failed()

    assert "No hay jobs deep fallidos" in out["mensaje"]
    assert get_conexion().execute("SELECT COUNT(*) c FROM audio_analysis_jobs").fetchone()["c"] == 0
    cerrar_db()


def test_background_retry_failed_solo_reactiva_failed(tmp_path: Path):
    inicializar_db(tmp_path / "retry_only_failed.sqlite")
    model_dir = _configure(tmp_path)
    _insert_track(1, "/music/a.mp3", "h1")
    _insert_track(2, "/music/b.mp3", "h2")
    get_conexion().execute(
        "INSERT INTO audio_analysis_runs(run_id, mode, status, started_at) VALUES(?,?, 'completed', datetime('now'))",
        ("run-old", BACKGROUND_MODE),
    )
    get_conexion().execute(
        """
        INSERT INTO audio_analysis_jobs(job_id, run_id, track_id, job_type, status, attempts, max_attempts, model_version, file_hash)
        VALUES('job-failed', 'run-old', '1', 'deep', 'failed', 1, 2, ?, 'h1')
        """,
        (DEEP_ANALYZER_VERSION,),
    )

    svc = _service(tmp_path, model_dir)
    retry = svc.retry_failed()
    out = svc.process_pending(enqueue_missing=False, force_retry_failed=True, idle_delay_sec=0)

    assert retry["pendientes"] == 1
    assert out["ready"] == 1
    assert get_conexion().execute("SELECT COUNT(*) c FROM audio_analysis_jobs").fetchone()["c"] == 1
    assert get_conexion().execute("SELECT COUNT(*) c FROM track_deep_audio_features").fetchone()["c"] == 1
    cerrar_db()


def test_importacion_programa_deep_post_import_sin_autostart(tmp_path: Path):
    inicializar_db(tmp_path / "post_import.sqlite")
    _configure(tmp_path)
    _insert_track(1, "/music/a.mp3", "h1")

    from servicios.importacion import ServicioImportacion

    ServicioImportacion()._programar_audio_deep_post_import()

    row = get_conexion().execute("SELECT status FROM audio_analysis_jobs WHERE track_id='1'").fetchone()
    assert row["status"] == "pending"
    cerrar_db()


def test_modelo_audio_deep_expone_estado_y_slots(monkeypatch):
    pytest.importorskip("PySide6")

    class FakeService:
        def __init__(self):
            self.paused = False
            self.cancelled = False

        def status(self):
            return {"estado": "pendiente", "pendientes": 2, "total": 3, "procesadas": 1}

        def pause(self):
            self.paused = True
            return {"estado": "pausado", "pausado": True, "pendientes": 2}

        def cancel_keep(self):
            self.cancelled = True
            return {"estado": "cancelado", "pendientes": 0}

    fake = FakeService()
    from ui.modelos_qml import ModeloAudioIntelligenceBackground

    monkeypatch.setattr(ModeloAudioIntelligenceBackground, "_service", lambda self: fake)
    modelo = ModeloAudioIntelligenceBackground()

    assert modelo.audioDeepEstado == "pendiente"
    assert modelo.audioDeepPendientes == 2
    modelo.pausarAudioDeepBackground()
    assert fake.paused is True
    assert modelo.audioDeepEstado == "pausado"
    modelo.cancelarAudioDeepConservar()
    assert fake.cancelled is True
    assert modelo.audioDeepEstado == "cancelado"
    modelo.deleteLater()


def test_background_max_attempts_respetado(tmp_path: Path):
    """Jobs at max_attempts should not be retried even with retry_failed=True."""
    inicializar_db(tmp_path / "max.sqlite")
    model_dir = _configure(tmp_path)
    # Set max_attempts=2
    guardar_config("audio_intelligence_max_attempts", "2")
    _insert_track(1, "/music/a.mp3", "h1")
    run_id = "run-maxed"
    get_conexion().execute(
        "INSERT INTO audio_analysis_runs(run_id, mode, status, started_at) VALUES(?,?, 'completed', datetime('now'))",
        (run_id, BACKGROUND_MODE),
    )
    # Job has already been attempted 2 times (== max_attempts)
    get_conexion().execute(
        """
        INSERT INTO audio_analysis_jobs(job_id, run_id, track_id, job_type, status, attempts, max_attempts, model_version, file_hash)
        VALUES('job-maxed', ?, '1', 'deep', 'failed', 2, 2, ?, 'h1')
        """,
        (run_id, DEEP_ANALYZER_VERSION),
    )

    svc = _service(tmp_path, model_dir)
    out = svc.enqueue_pending_tracks(force_retry_failed=True)

    # Should skip because attempts >= max_attempts
    assert out["skipped_failed"] == 1
    assert get_conexion().execute("SELECT status FROM audio_analysis_jobs WHERE job_id='job-maxed'").fetchone()["status"] == "failed"
    cerrar_db()


def test_background_config_desactivado_retorna_controlado(tmp_path: Path):
    """When deep is disabled, enqueue should return a controlled response."""
    inicializar_db(tmp_path / "disabled.sqlite")
    _configure(tmp_path)
    guardar_config("enable_audio_intelligence_deep", "0")
    _insert_track(1, "/music/a.mp3", "h1")

    svc = _service(tmp_path, tmp_path / "models")
    out = svc.enqueue_pending_tracks()

    assert "desactivado" in out.get("mensaje", "").lower() or out.get("estado") == "inactivo"
    cerrar_db()


def test_background_process_con_stop_event(tmp_path: Path):
    """stop_event should pause the run."""
    import threading
    inicializar_db(tmp_path / "stop.sqlite")
    model_dir = _configure(tmp_path)
    _insert_track(1, "/music/a.mp3", "h1")
    _insert_track(2, "/music/b.mp3", "h2")

    stop = threading.Event()
    stop.set()  # Pre-set: should stop immediately

    svc = _service(tmp_path, model_dir)
    svc.enqueue_pending_tracks()
    out = svc.process_pending(stop_event=stop, idle_delay_sec=0)

    # Run should be paused, not completed
    assert out["estado"] in ("pausado", "pendiente")
    cerrar_db()


def test_background_status_sin_corridas(tmp_path: Path):
    """status() without any runs should not crash."""
    inicializar_db(tmp_path / "empty_status.sqlite")
    _configure(tmp_path)

    svc = _service(tmp_path, tmp_path / "models")
    out = svc.status()

    assert out["ok"] is True
    assert out["run_id"] == ""
    assert out["estado"] in ("inactivo", "sin_pendientes")
    cerrar_db()
