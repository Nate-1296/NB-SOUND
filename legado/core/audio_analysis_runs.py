from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from db.conexion import ejecutar


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_eta(seconds: float | int | None) -> str:
    if seconds is None:
        return "desconocido"
    try:
        total = max(0, int(round(float(seconds))))
    except (TypeError, ValueError):
        return "desconocido"
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def compute_eta_metrics(
    *,
    total_tracks: int,
    processed_tracks: int,
    started_monotonic: float,
    now_monotonic: float | None = None,
) -> dict[str, Any]:
    now = time.monotonic() if now_monotonic is None else now_monotonic
    elapsed_ms = max(0, int((now - started_monotonic) * 1000))
    total = max(0, int(total_tracks or 0))
    processed = max(0, int(processed_tracks or 0))
    remaining = max(0, total - processed)

    if processed <= 0 or elapsed_ms <= 0:
        avg_ms_per_track = None
        tracks_per_minute = 0.0
        eta_seconds = None if remaining else 0.0
    else:
        avg_ms_per_track = elapsed_ms / processed
        tracks_per_minute = processed / max(elapsed_ms / 60000.0, 1e-9)
        eta_seconds = (avg_ms_per_track * remaining) / 1000.0

    eta_human = format_eta(eta_seconds)
    return {
        "elapsed_ms": elapsed_ms,
        "avg_ms_per_track": avg_ms_per_track,
        "tracks_per_minute": tracks_per_minute,
        "eta_seconds": eta_seconds,
        "eta_human": eta_human,
        "eta_last_value": eta_human,
    }


class AudioRunTracker:
    def __init__(self, mode: str, config: dict | None = None):
        self.run_id = str(uuid.uuid4())
        self.mode = mode
        self.t0 = time.monotonic()
        self.started_at = _utc_now()
        self.config_snapshot = dict(config or {})
        self.stats = {
            "total_tracks": 0,
            "processed_tracks": 0,
            "ready_tracks": 0,
            "failed_tracks": 0,
            "skipped_tracks": 0,
        }
        self.current_track_id = ""
        self.current_file_path = ""
        self.current_stage = mode
        ejecutar(
            """
            INSERT INTO audio_analysis_runs(
                run_id, mode, status, started_at, last_update_at, current_stage,
                config_snapshot_json, summary_json
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                self.run_id,
                mode,
                "running",
                self.started_at,
                self.started_at,
                self.current_stage,
                json.dumps(self.config_snapshot, ensure_ascii=False, sort_keys=True),
                json.dumps(self.summary_snapshot(), ensure_ascii=False, sort_keys=True),
            ),
        )

    def set_total(self, total: int) -> dict:
        self.stats["total_tracks"] = max(0, int(total or 0))
        return self.update_progress(current_stage=self.current_stage)

    def register_job(
        self,
        track_id: str,
        job_type: str,
        *,
        current_file_path: str = "",
        current_stage: str | None = None,
    ) -> str:
        jid = str(uuid.uuid4())
        stage = current_stage or job_type or self.mode
        now = _utc_now()
        ejecutar(
            """
            INSERT INTO audio_analysis_jobs(
                job_id, run_id, track_id, job_type, status, created_at, started_at, updated_at
            ) VALUES(?,?,?,?,?,datetime('now'),datetime('now'),datetime('now'))
            """,
            (jid, self.run_id, str(track_id), job_type, "running"),
        )
        self.current_track_id = str(track_id)
        self.current_file_path = str(current_file_path or "")
        self.current_stage = stage
        self._persist(now=now)
        return jid

    def finish_job(
        self,
        job_id: str,
        status: str,
        error_code: str = "",
        error_message: str = "",
        *,
        current_track_id: str | None = None,
        current_file_path: str | None = None,
        current_stage: str | None = None,
    ) -> dict:
        normalized = status if status in {"ready", "failed", "skipped"} else "failed"
        ejecutar(
            """
            UPDATE audio_analysis_jobs
            SET status=?, error_code=?, error_message=?, updated_at=datetime('now'), finished_at=datetime('now')
            WHERE job_id=?
            """,
            (normalized, error_code, error_message, job_id),
        )
        self.stats["processed_tracks"] += 1
        if normalized == "ready":
            self.stats["ready_tracks"] += 1
        elif normalized == "failed":
            self.stats["failed_tracks"] += 1
        else:
            self.stats["skipped_tracks"] += 1
        return self.update_progress(
            current_track_id=current_track_id,
            current_file_path=current_file_path,
            current_stage=current_stage,
        )

    def update_progress(
        self,
        *,
        current_track_id: str | None = None,
        current_file_path: str | None = None,
        current_stage: str | None = None,
    ) -> dict:
        if current_track_id is not None:
            self.current_track_id = str(current_track_id)
        if current_file_path is not None:
            self.current_file_path = str(current_file_path)
        if current_stage is not None:
            self.current_stage = str(current_stage)
        return self._persist(now=_utc_now())

    def finish(self) -> dict:
        snapshot = self._persist(now=_utc_now(), finished=True)
        return snapshot

    def summary_snapshot(self, metrics: dict | None = None) -> dict:
        data = {
            **self.stats,
            "total": self.stats["total_tracks"],
            "processed": self.stats["processed_tracks"],
            "ready": self.stats["ready_tracks"],
            "failed": self.stats["failed_tracks"],
            "skipped": self.stats["skipped_tracks"],
            "pending": max(0, self.stats["total_tracks"] - self.stats["processed_tracks"]),
            "current_track_id": self.current_track_id,
            "current_file_path": self.current_file_path,
            "current_stage": self.current_stage,
            "started_at": self.started_at,
            "last_update_at": "",
            "elapsed_ms": 0,
            "avg_ms_per_track": None,
            "tracks_per_minute": 0.0,
            "eta_seconds": None,
            "eta_human": "desconocido",
            "eta_last_value": "desconocido",
        }
        if metrics:
            data.update(metrics)
        return data

    def _persist(self, *, now: str, finished: bool = False) -> dict:
        metrics = compute_eta_metrics(
            total_tracks=self.stats["total_tracks"],
            processed_tracks=self.stats["processed_tracks"],
            started_monotonic=self.t0,
        )
        if finished:
            metrics["eta_seconds"] = 0.0
            metrics["eta_human"] = "0s"
            metrics["eta_last_value"] = "0s"
        metrics["last_update_at"] = now
        snapshot = self.summary_snapshot(metrics)
        ejecutar(
            """
            UPDATE audio_analysis_runs
            SET total_tracks=?,
                processed_tracks=?,
                ready_tracks=?,
                failed_tracks=?,
                skipped_tracks=?,
                pending_tracks=?,
                current_track_id=?,
                current_file_path=?,
                current_stage=?,
                status=CASE WHEN ? THEN 'completed' ELSE status END,
                last_update_at=?,
                finished_at=CASE WHEN ? THEN datetime('now') ELSE finished_at END,
                elapsed_ms=?,
                avg_ms_per_track=?,
                tracks_per_minute=?,
                eta_seconds=?,
                eta_human=?,
                eta_last_value=?,
                config_snapshot_json=?,
                summary_json=?
            WHERE run_id=?
            """,
            (
                self.stats["total_tracks"],
                self.stats["processed_tracks"],
                self.stats["ready_tracks"],
                self.stats["failed_tracks"],
                self.stats["skipped_tracks"],
                max(0, self.stats["total_tracks"] - self.stats["processed_tracks"]),
                self.current_track_id,
                self.current_file_path,
                self.current_stage,
                1 if finished else 0,
                now,
                1 if finished else 0,
                int(metrics["elapsed_ms"]),
                metrics["avg_ms_per_track"],
                metrics["tracks_per_minute"],
                metrics["eta_seconds"],
                metrics["eta_human"],
                metrics["eta_last_value"],
                json.dumps(self.config_snapshot, ensure_ascii=False, sort_keys=True),
                json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
                self.run_id,
            ),
        )
        return snapshot
