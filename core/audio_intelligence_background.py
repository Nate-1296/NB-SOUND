"""
audio_intelligence_background.py
---------------------------------
Cola reanudable de análisis profundo (Essentia/TensorFlow) en background.

Responsabilidades:
    - Mantener una cola de jobs de análisis deep en la tabla audio_analysis_jobs.
    - Gestionar el ciclo de vida de corridas (runs) en audio_analysis_runs.
    - Ejecutar el análisis track a track desde un hilo secundario, sin bloquear
      el hilo principal de la UI.
    - Soportar pause/resume/cancel de forma segura entre hilos.
    - Calcular y persistir métricas de progreso (ETA, velocidad, porcentaje).

Modelo de datos (runs y jobs):
    - Una "run" (audio_analysis_runs) agrupa una sesión de análisis deep.
      Estados de run: pending → running → paused | completed | cancelled_*.
    - Un "job" (audio_analysis_jobs) representa el análisis de un track concreto.
      Estados de job: pending → running → ready | failed | skipped | cancelled_*.
    - Los jobs de un run pueden reanudarse en sesiones futuras; la cola es
      persistente en SQLite, no en memoria.

Diseño reanudable:
    - recover_interrupted_jobs() revierte jobs que quedaron en 'running'
      (crash o kill inesperado) a 'pending' para que puedan reintentarse.
    - enqueue_pending_tracks() es idempotente: detecta tracks ya analizados
      y jobs existentes, evitando duplicaciones.
    - El criterio de "ya analizado" combina analysis_status='ready',
      analyzer_version y file_hash para detectar cambios en el archivo.

Threading:
    - _PROCESS_LOCK garantiza que solo un worker deep corra en el proceso.
    - stop_event permite detención cooperativa desde otro hilo.
    - _sleep_interruptible() implementa espera interrumpible entre batches.

Configuración (AudioIntelligenceBackgroundConfig):
    - Se resuelve en cada llamada desde settings + tabla de config en DB,
      permitiendo cambiar parámetros sin reiniciar la aplicación.
    - La config se serializa como snapshot en la run para auditoría.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from config import settings
from core.audio_intelligence_deep import (
    ANALYZER_VERSION as DEEP_ANALYZER_VERSION,
    EssentiaTensorflowAnalyzer,
    persist_deep_analysis,
)
from db.conexion import obtener_filas, obtener_una_fila, ejecutar, ejecutar_muchos, obtener_config
from infra.logger import obtener_logger

_log = obtener_logger("core.audio_intelligence_background")

BACKGROUND_MODE = "audio_intelligence_deep_background"
DEEP_STAGE = "audio_intelligence_deep"

FINAL_JOB_STATUSES = {"ready", "failed", "skipped", "cancelled_keep", "cancelled_discard"}
ACTIVE_RUN_STATUSES = {"pending", "running", "paused"}
NON_TERMINAL_JOB_STATUSES = {"pending", "running", "paused"}

_PROCESS_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def _format_eta(seconds: float | None) -> str:
    if seconds is None:
        return "desconocido"
    total = max(0, int(round(seconds)))
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _bool_text(value: object, default: bool) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "si", "sí"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _int_text(value: object, default: int, *, min_value: int = 0, max_value: int | None = None) -> int:
    try:
        parsed = int(float(str(value).strip()))
    except (TypeError, ValueError):
        parsed = default
    if parsed < min_value:
        parsed = min_value
    if max_value is not None and parsed > max_value:
        parsed = max_value
    return parsed


def _float_text(value: object, default: float, *, min_value: float = 0.0, max_value: float | None = None) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        parsed = default
    if parsed < min_value:
        parsed = min_value
    if max_value is not None and parsed > max_value:
        parsed = max_value
    return parsed


def _setting_text(env_name: str, config_key: str) -> str:
    default = getattr(settings, env_name)
    if isinstance(default, bool):
        default_text = "1" if default else "0"
    else:
        default_text = str(default)
    try:
        value = obtener_config(config_key, default_text)
    except Exception:
        value = default_text
    return str(value).strip()


@dataclass(frozen=True)
class AudioIntelligenceBackgroundConfig:
    """
    Configuración inmutable del worker de análisis deep en background.

    Parámetros operacionales:
        enabled:                    Habilita el subsistema deep en general.
        background_enabled:         Habilita específicamente la ejecución en background.
        analyze_after_import_background: Analiza tracks nuevos en background post-import.
        resume_pending_on_startup:  Reanuda jobs pendientes al arrancar la app.
        autostart:                  Inicia el worker automáticamente al arrancar.
        backend:                    Motor de inferencia ('essentia', 'essentia_tensorflow').
        model_dir:                  Directorio con los archivos .pb y .json de modelos.
        allow_downloads:            Permite descargar modelos faltantes.
        mood_models:                Habilita modelos de mood (happy, sad, etc.).
        embeddings:                 Habilita extracción de embeddings MusiCNN/VGGish.
        tagging_models:             Habilita modelos de auto-tagging (MSD50, Discogs400).
        batch_size:                 Tracks a procesar antes de introducir idle_delay.
        idle_delay_sec:             Pausa entre batches para liberar CPU/I/O (0 = sin pausa).
        max_runtime_min:            Tiempo máximo de ejecución por sesión (0 = ilimitado).
        retry_failed:               Reintenta automáticamente jobs fallidos.
        max_attempts:               Máximo de intentos por job antes de rendirse.
        cancel_discard_outputs:     Al cancelar con discard, elimina resultados parciales.
        reanalyze_on_model_change:  Re-analiza si cambia el analyzer_version o el file_hash.
    """
    enabled: bool
    background_enabled: bool
    analyze_after_import_background: bool
    resume_pending_on_startup: bool
    autostart: bool
    backend: str
    model_dir: str
    allow_downloads: bool
    mood_models: bool
    embeddings: bool
    tagging_models: bool
    batch_size: int
    idle_delay_sec: float
    max_runtime_min: int
    retry_failed: bool
    max_attempts: int
    cancel_discard_outputs: bool
    reanalyze_on_model_change: bool

    @classmethod
    def load(cls) -> "AudioIntelligenceBackgroundConfig":
        return cls(
            enabled=_bool_text(_setting_text("ENABLE_AUDIO_INTELLIGENCE_DEEP", "enable_audio_intelligence_deep"), settings.ENABLE_AUDIO_INTELLIGENCE_DEEP),
            background_enabled=_bool_text(_setting_text("AUDIO_INTELLIGENCE_BACKGROUND", "audio_intelligence_background"), settings.AUDIO_INTELLIGENCE_BACKGROUND),
            analyze_after_import_background=_bool_text(
                _setting_text("AUDIO_INTELLIGENCE_ANALYZE_AFTER_IMPORT_BACKGROUND", "audio_intelligence_analyze_after_import_background"),
                settings.AUDIO_INTELLIGENCE_ANALYZE_AFTER_IMPORT_BACKGROUND,
            ),
            resume_pending_on_startup=_bool_text(
                _setting_text("AUDIO_INTELLIGENCE_RESUME_PENDING_ON_STARTUP", "audio_intelligence_resume_pending_on_startup"),
                settings.AUDIO_INTELLIGENCE_RESUME_PENDING_ON_STARTUP,
            ),
            autostart=_bool_text(
                _setting_text("AUDIO_INTELLIGENCE_BACKGROUND_AUTOSTART", "audio_intelligence_background_autostart"),
                settings.AUDIO_INTELLIGENCE_BACKGROUND_AUTOSTART,
            ),
            backend=_setting_text("AUDIO_INTELLIGENCE_BACKEND", "audio_intelligence_backend").lower(),
            model_dir=_setting_text("AUDIO_INTELLIGENCE_MODEL_DIR", "audio_intelligence_model_dir"),
            allow_downloads=_bool_text(
                _setting_text("AUDIO_INTELLIGENCE_ALLOW_MODEL_DOWNLOADS", "audio_intelligence_allow_model_downloads"),
                settings.AUDIO_INTELLIGENCE_ALLOW_MODEL_DOWNLOADS,
            ),
            mood_models=_bool_text(_setting_text("ENABLE_AUDIO_MOOD_MODELS", "enable_audio_mood_models"), settings.ENABLE_AUDIO_MOOD_MODELS),
            embeddings=_bool_text(_setting_text("ENABLE_AUDIO_EMBEDDINGS", "enable_audio_embeddings"), settings.ENABLE_AUDIO_EMBEDDINGS),
            tagging_models=_bool_text(_setting_text("ENABLE_AUDIO_TAGGING_MODELS", "enable_audio_tagging_models"), settings.ENABLE_AUDIO_TAGGING_MODELS),
            batch_size=_int_text(
                _setting_text("AUDIO_INTELLIGENCE_BACKGROUND_BATCH_SIZE", "audio_intelligence_background_batch_size"),
                settings.AUDIO_INTELLIGENCE_BACKGROUND_BATCH_SIZE,
                min_value=1,
                max_value=50,
            ),
            idle_delay_sec=_float_text(
                _setting_text("AUDIO_INTELLIGENCE_BACKGROUND_IDLE_DELAY_SEC", "audio_intelligence_background_idle_delay_sec"),
                settings.AUDIO_INTELLIGENCE_BACKGROUND_IDLE_DELAY_SEC,
                min_value=0.0,
                max_value=3600.0,
            ),
            max_runtime_min=_int_text(
                _setting_text("AUDIO_INTELLIGENCE_BACKGROUND_MAX_RUNTIME_MIN", "audio_intelligence_background_max_runtime_min"),
                settings.AUDIO_INTELLIGENCE_BACKGROUND_MAX_RUNTIME_MIN,
                min_value=0,
                max_value=1440,
            ),
            retry_failed=_bool_text(_setting_text("AUDIO_INTELLIGENCE_RETRY_FAILED", "audio_intelligence_retry_failed"), settings.AUDIO_INTELLIGENCE_RETRY_FAILED),
            max_attempts=_int_text(
                _setting_text("AUDIO_INTELLIGENCE_MAX_ATTEMPTS", "audio_intelligence_max_attempts"),
                settings.AUDIO_INTELLIGENCE_MAX_ATTEMPTS,
                min_value=1,
                max_value=20,
            ),
            cancel_discard_outputs=_bool_text(
                _setting_text("AUDIO_INTELLIGENCE_CANCEL_DISCARD_OUTPUTS", "audio_intelligence_cancel_discard_outputs"),
                settings.AUDIO_INTELLIGENCE_CANCEL_DISCARD_OUTPUTS,
            ),
            reanalyze_on_model_change=_bool_text(
                _setting_text("AUDIO_INTELLIGENCE_REANALYZE_ON_MODEL_CHANGE", "audio_intelligence_reanalyze_on_model_change"),
                settings.AUDIO_INTELLIGENCE_REANALYZE_ON_MODEL_CHANGE,
            ),
        )


class AudioIntelligenceBackgroundService:
    """
    Servicio de análisis deep en background.

    Lifecycle de una sesión:
        1. enqueue_pending_tracks() → crea jobs para tracks sin análisis ready.
        2. process_pending()       → ejecuta jobs en loop, un track a la vez.
        3. pause() / resume()      → control de flujo sin pérdida de progreso.
        4. cancel_keep() / cancel_discard() → cancelación con/sin limpieza de resultados.
        5. retry_failed()          → reencola jobs fallidos que no alcanzaron max_attempts.

    El método status() puede llamarse en cualquier momento desde cualquier hilo
    y retorna un snapshot consistente del estado actual.
    """

    def __init__(self, *, base_dir: Path | None = None, analyzer_factory: Callable[[], EssentiaTensorflowAnalyzer] | None = None):
        self.base_dir = base_dir if base_dir is not None else settings.DEFAULT_ASSETS_DIR
        self._analyzer_factory = analyzer_factory

    def recover_interrupted_jobs(self) -> dict:
        rows = obtener_filas(
            """
            SELECT j.job_id
            FROM audio_analysis_jobs j
            JOIN audio_analysis_runs r ON r.run_id=j.run_id
            WHERE r.mode=? AND j.status='running'
            """,
            (BACKGROUND_MODE,),
        )
        job_ids = [row["job_id"] for row in rows]
        if job_ids:
            ejecutar_muchos(
                """
                UPDATE audio_analysis_jobs
                SET status='pending', started_at=NULL, updated_at=datetime('now'), finished_at=NULL
                WHERE job_id=?
                """,
                [(job_id,) for job_id in job_ids],
            )
        ejecutar(
            """
            UPDATE audio_analysis_runs
            SET status='pending', current_stage=?, last_update_at=?
            WHERE mode=? AND status='running'
            """,
            (DEEP_STAGE, _utc_now(), BACKGROUND_MODE),
        )
        run_id = self._latest_run_id()
        if run_id:
            self._refresh_run_summary(run_id)
        return {"recovered_jobs": len(job_ids), "run_id": run_id or ""}

    def enqueue_pending_tracks(
        self,
        *,
        run_id: str | None = None,
        include_cancelled: bool = False,
        force_retry_failed: bool = False,
    ) -> dict:
        cfg = AudioIntelligenceBackgroundConfig.load()
        if not cfg.enabled or not cfg.background_enabled:
            return self.status(message="Audio Intelligence deep background esta desactivado.")

        run_id = run_id or self._ensure_run(cfg)
        created = 0
        reactivated = 0
        skipped_ready = 0
        skipped_failed = 0

        for track in self._library_tracks():
            track_id = str(track["id"])
            file_hash = str(track["hash_sha256"] or "")
            deep_row = self._deep_row(track_id)
            if self._deep_ready_for_current_file(deep_row, file_hash, cfg):
                skipped_ready += 1
                continue
            if deep_row and deep_row["analysis_status"] == "failed" and not (cfg.retry_failed or force_retry_failed):
                skipped_failed += 1
                continue

            existing = self._latest_job(track_id, file_hash)
            if existing:
                status = str(existing["status"] or "")
                attempts = int(existing["attempts"] or 0)
                if status in {"pending", "running", "paused"}:
                    continue
                if status == "failed" and not (cfg.retry_failed or force_retry_failed):
                    skipped_failed += 1
                    continue
                if status == "failed" and attempts >= cfg.max_attempts:
                    skipped_failed += 1
                    continue
                if status in {"cancelled_keep", "cancelled_discard"} and not include_cancelled:
                    continue
                self._reactivate_job(existing["job_id"], run_id, cfg.max_attempts)
                reactivated += 1
                continue

            self._insert_job(run_id, track_id, file_hash, cfg.max_attempts)
            created += 1

        self._refresh_run_summary(run_id)
        return {
            **self.status(run_id=run_id),
            "created_jobs": created,
            "reactivated_jobs": reactivated,
            "skipped_ready": skipped_ready,
            "skipped_failed": skipped_failed,
        }

    def process_pending(
        self,
        *,
        run_id: str | None = None,
        reactivate_cancelled: bool = False,
        force_retry_failed: bool = False,
        enqueue_missing: bool = True,
        progress_callback: Callable[[dict], None] | None = None,
        stop_event: threading.Event | None = None,
        idle_delay_sec: float | None = None,
    ) -> dict:
        cfg = AudioIntelligenceBackgroundConfig.load()
        if not cfg.enabled:
            return self.status(message="Audio Intelligence deep esta desactivado.")
        if not cfg.background_enabled:
            return self.status(message="Audio Intelligence background esta desactivado.")

        self.recover_interrupted_jobs()
        run_id = run_id or self._latest_active_run_id() or self._latest_run_with_pending_jobs()
        if not run_id and not enqueue_missing:
            return self.status(message="No hay jobs deep pendientes para procesar.")
        run_id = run_id or self._ensure_run(cfg)
        if self._run_status(run_id) == "paused":
            self.resume(run_id=run_id, reactivate_cancelled=False)
        if enqueue_missing:
            self.enqueue_pending_tracks(
                run_id=run_id,
                include_cancelled=reactivate_cancelled,
                force_retry_failed=force_retry_failed,
            )
        else:
            self._refresh_run_summary(run_id)
        queued = self.status(run_id=run_id)
        if int(queued.get("pendientes") or 0) <= 0:
            self._set_run_status(run_id, "completed", finished=True)
            return self.status(run_id=run_id)

        warning = self._availability_warning(cfg)
        if warning:
            self._set_run_status(run_id, "pending", message=warning)
            return self.status(run_id=run_id, warning=warning)

        if not _PROCESS_LOCK.acquire(blocking=False):
            return self.status(run_id=run_id, warning="Ya hay un worker deep ejecutandose en este proceso.")

        try:
            self._set_run_status(run_id, "running")
            analyzer = self._make_analyzer(cfg)
            started = time.monotonic()
            delay = cfg.idle_delay_sec if idle_delay_sec is None else max(0.0, float(idle_delay_sec))
            max_runtime = cfg.max_runtime_min * 60 if cfg.max_runtime_min > 0 else 0
            processed_in_batch = 0

            while True:
                if stop_event is not None and stop_event.is_set():
                    self.pause(run_id=run_id)
                    break
                run_status = self._run_status(run_id)
                if run_status in {"paused", "cancelled_keep", "cancelled_discard", "failed"}:
                    break
                if max_runtime and time.monotonic() - started >= max_runtime:
                    self._set_run_status(run_id, "pending", message="Max runtime alcanzado; quedan jobs pendientes.")
                    break

                job = self._next_pending_job(run_id)
                if not job:
                    final_status = "completed"
                    summary = self.status(run_id=run_id)
                    if summary.get("failed", 0) > 0:
                        final_status = "completed"
                    self._set_run_status(run_id, final_status, finished=True)
                    break

                self._run_job(run_id, job, analyzer, progress_callback=progress_callback)
                processed_in_batch += 1
                if progress_callback:
                    progress_callback(self.status(run_id=run_id))
                run_status = self._run_status(run_id)
                if run_status in {"paused", "cancelled_keep", "cancelled_discard", "failed"}:
                    break
                if delay > 0 and processed_in_batch >= cfg.batch_size:
                    processed_in_batch = 0
                    self._sleep_interruptible(delay, run_id, stop_event)
        finally:
            _PROCESS_LOCK.release()

        return self.status(run_id=run_id)

    def pause(self, *, run_id: str | None = None) -> dict:
        run_id = run_id or self._latest_active_run_id()
        if not run_id:
            return self.status(message="No hay corrida deep para pausar.")
        now = _utc_now()
        ejecutar(
            """
            UPDATE audio_analysis_runs
            SET status='paused', last_update_at=?, current_stage=?
            WHERE run_id=?
            """,
            (now, DEEP_STAGE, run_id),
        )
        ejecutar(
            """
            UPDATE audio_analysis_jobs
            SET status='paused', updated_at=datetime('now')
            WHERE run_id=? AND status IN ('pending','running')
            """,
            (run_id,),
        )
        self._refresh_run_summary(run_id)
        return self.status(run_id=run_id, message="Audio Intelligence deep pausado.")

    def resume(self, *, run_id: str | None = None, reactivate_cancelled: bool = False) -> dict:
        cfg = AudioIntelligenceBackgroundConfig.load()
        if not cfg.enabled:
            return self.status(message="Audio Intelligence deep esta desactivado.")
        if not cfg.background_enabled:
            return self.status(message="Audio Intelligence background esta desactivado.")
        self.recover_interrupted_jobs()
        run_id = run_id or self._latest_active_run_id() or self._latest_run_with_pending_jobs()
        if not run_id:
            return self.status(message="No hay jobs deep pendientes para reanudar.")
        ejecutar(
            """
            UPDATE audio_analysis_jobs
            SET status='pending', updated_at=datetime('now'), finished_at=NULL
            WHERE run_id=? AND status='paused'
            """,
            (run_id,),
        )
        ejecutar(
            """
            UPDATE audio_analysis_runs
            SET status='pending', last_update_at=?, finished_at=NULL, current_stage=?
            WHERE run_id=?
            """,
            (_utc_now(), DEEP_STAGE, run_id),
        )
        if reactivate_cancelled:
            ejecutar(
                """
                UPDATE audio_analysis_jobs
                SET status='pending', updated_at=datetime('now'), finished_at=NULL
                WHERE run_id=? AND status IN ('cancelled_keep','cancelled_discard') AND attempts < ?
                """,
                (run_id, cfg.max_attempts),
            )
        self._refresh_run_summary(run_id)
        return self.status(run_id=run_id, message="Audio Intelligence deep listo para reanudar.")

    def cancel_keep(self, *, run_id: str | None = None) -> dict:
        return self._cancel(run_id=run_id, policy="cancelled_keep")

    def cancel_discard(self, *, run_id: str | None = None) -> dict:
        run_id = run_id or self._latest_active_run_id()
        if not run_id:
            return self.status(message="No hay corrida deep para cancelar.")

        rows = obtener_filas(
            "SELECT DISTINCT track_id FROM audio_analysis_jobs WHERE run_id=?",
            (run_id,),
        )
        track_ids = [str(row["track_id"]) for row in rows if row["track_id"] is not None]
        if track_ids:
            ejecutar_muchos(
                "DELETE FROM track_deep_audio_features WHERE track_id=? AND last_run_id=?",
                [(track_id, run_id) for track_id in track_ids],
            )
            ejecutar_muchos(
                "DELETE FROM track_vibe_tags WHERE track_id=? AND source='deep_model'",
                [(track_id,) for track_id in track_ids],
            )
        ejecutar(
            """
            UPDATE audio_analysis_jobs
            SET status='cancelled_discard', attempts=0, updated_at=datetime('now'), finished_at=datetime('now')
            WHERE run_id=? AND status IN ('pending','running','paused','ready','skipped')
            """,
            (run_id,),
        )
        return self._cancel(run_id=run_id, policy="cancelled_discard")

    def retry_failed(self, *, run_id: str | None = None) -> dict:
        cfg = AudioIntelligenceBackgroundConfig.load()
        if not cfg.enabled:
            return self.status(message="Audio Intelligence deep esta desactivado.")
        if not cfg.background_enabled:
            return self.status(message="Audio Intelligence background esta desactivado.")
        # Reintento MANUAL (botón del usuario): reintenta TODOS los jobs deep
        # fallidos, incluidos los que ya agotaron sus reintentos automáticos
        # (attempts >= max_attempts). El auto-retry usa otra vía
        # (`force_retry_failed`), así que aquí no hay riesgo de bucle infinito;
        # reseteamos `attempts=0` para que vuelvan a ejecutarse de verdad.
        retryable = obtener_una_fila(
            """
            SELECT COUNT(*) c
            FROM audio_analysis_jobs
            WHERE job_type='deep' AND status='failed'
            """
        )["c"]
        if int(retryable or 0) <= 0:
            return self.status(message="No hay jobs deep fallidos para reintentar.")

        run_id = run_id or self._latest_active_run_id() or self._ensure_run(cfg)
        ejecutar(
            """
            UPDATE audio_analysis_jobs
            SET run_id=?, status='pending', attempts=0, max_attempts=?, updated_at=datetime('now'), finished_at=NULL
            WHERE job_type='deep' AND status='failed'
            """,
            (run_id, cfg.max_attempts),
        )
        self._set_run_status(run_id, "pending")
        return {
            **self.status(run_id=run_id, message="Jobs deep fallidos listos para reintento."),
            "requeued": int(retryable or 0),
        }

    def status(self, *, run_id: str | None = None, message: str = "", warning: str = "") -> dict:
        cfg = AudioIntelligenceBackgroundConfig.load()
        run_id = run_id or self._latest_active_run_id() or self._latest_run_id()
        if run_id:
            self._refresh_run_summary(run_id)
            run = obtener_una_fila("SELECT * FROM audio_analysis_runs WHERE run_id=?", (run_id,))
        else:
            run = None

        total_library = obtener_una_fila("SELECT COUNT(*) c FROM pistas WHERE estado='biblioteca'")["c"]
        deep_ready = obtener_una_fila("SELECT COUNT(*) c FROM track_deep_audio_features WHERE analysis_status='ready'")["c"]
        pending_global = obtener_una_fila(
            "SELECT COUNT(*) c FROM audio_analysis_jobs WHERE job_type='deep' AND status IN ('pending','paused','running')"
        )["c"]
        warning = warning or self._config_warning(cfg)

        if not cfg.enabled:
            estado = "inactivo"
        elif run is None and pending_global == 0:
            estado = "sin_pendientes"
        elif run is not None and run["status"] == "running":
            estado = "procesando"
        elif run is not None and run["status"] == "paused":
            estado = "pausado"
        elif run is not None and str(run["status"] or "").startswith("cancelled"):
            estado = "cancelado"
        elif run is not None and int(run["pending_tracks"] or 0) > 0:
            estado = "pendiente"
        elif run is not None and int(run["failed_tracks"] or 0) > 0:
            estado = "error_parcial"
        elif run is not None and int(run["total_tracks"] or 0) > 0:
            estado = "completado"
        else:
            estado = "sin_pendientes"

        total = int(run["total_tracks"] or 0) if run else 0
        processed = int(run["processed_tracks"] or 0) if run else 0
        ready = int(run["ready_tracks"] or 0) if run else 0
        failed = int(run["failed_tracks"] or 0) if run else 0
        skipped = int(run["skipped_tracks"] or 0) if run else 0
        pending = int(run["pending_tracks"] or pending_global or 0) if run else int(pending_global or 0)
        percentage = (processed / total) if total else 0.0
        speed = float(run["tracks_per_minute"] or 0.0) if run else 0.0
        eta = run["eta_human"] if run and run["eta_human"] else "desconocido"

        return {
            "ok": True,
            "run_id": run_id or "",
            "estado": estado,
            "status": run["status"] if run else "",
            "activo": estado in {"pendiente", "procesando", "pausado"},
            "disponible": cfg.enabled and cfg.background_enabled and not warning,
            "procesando": estado == "procesando",
            "pausado": estado == "pausado",
            "total": total,
            "procesadas": processed,
            "ready": ready,
            "failed": failed,
            "skipped": skipped,
            "pendientes": pending,
            "porcentaje": max(0.0, min(1.0, percentage)),
            "eta_seconds": float(run["eta_seconds"] or -1.0) if run else -1.0,
            "eta": eta,
            "velocidad": speed,
            "pista_actual": run["current_file_path"] if run else "",
            "current_track_id": run["current_track_id"] if run else "",
            "current_stage": run["current_stage"] if run else DEEP_STAGE,
            "mensaje": message,
            "warning": warning,
            "deep_ready": int(deep_ready or 0),
            "library_total": int(total_library or 0),
        }

    def _ensure_run(self, cfg: AudioIntelligenceBackgroundConfig) -> str:
        run_id = self._latest_active_run_id()
        if run_id:
            return run_id
        run_id = str(uuid.uuid4())
        now = _utc_now()
        snapshot = {
            "total": 0,
            "processed": 0,
            "ready": 0,
            "failed": 0,
            "skipped": 0,
            "pending": 0,
            "current_stage": DEEP_STAGE,
        }
        ejecutar(
            """
            INSERT INTO audio_analysis_runs(
                run_id, mode, status, started_at, last_update_at, current_stage,
                config_snapshot_json, summary_json
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                run_id,
                BACKGROUND_MODE,
                "pending",
                now,
                now,
                DEEP_STAGE,
                json.dumps(cfg.__dict__, ensure_ascii=False, sort_keys=True),
                json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
            ),
        )
        return run_id

    def _library_tracks(self) -> Iterable[dict]:
        rows = obtener_filas(
            """
            SELECT id, ruta_archivo, hash_sha256
            FROM pistas
            WHERE estado='biblioteca'
            ORDER BY id
            """
        )
        return [dict(row) for row in rows]

    def _deep_row(self, track_id: str):
        return obtener_una_fila(
            "SELECT analysis_status, analyzer_version, file_hash FROM track_deep_audio_features WHERE track_id=?",
            (track_id,),
        )

    def _deep_ready_for_current_file(self, row, file_hash: str, cfg: AudioIntelligenceBackgroundConfig) -> bool:
        if not row or row["analysis_status"] != "ready":
            return False
        if not cfg.reanalyze_on_model_change:
            return True
        same_version = row["analyzer_version"] == DEEP_ANALYZER_VERSION
        stored_hash = str(row["file_hash"] or "")
        same_hash = not file_hash or not stored_hash or stored_hash == file_hash
        return same_version and same_hash

    def _latest_job(self, track_id: str, file_hash: str):
        return obtener_una_fila(
            """
            SELECT *
            FROM audio_analysis_jobs
            WHERE job_type='deep'
              AND track_id=?
              AND COALESCE(model_version,'')=?
              AND COALESCE(file_hash,'')=?
            ORDER BY created_at DESC, updated_at DESC
            LIMIT 1
            """,
            (track_id, DEEP_ANALYZER_VERSION, file_hash or ""),
        )

    def _insert_job(self, run_id: str, track_id: str, file_hash: str, max_attempts: int) -> None:
        ejecutar(
            """
            INSERT INTO audio_analysis_jobs(
                job_id, run_id, track_id, job_type, status, priority,
                attempts, max_attempts, model_version, file_hash,
                created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))
            """,
            (
                str(uuid.uuid4()),
                run_id,
                track_id,
                "deep",
                "pending",
                5,
                0,
                max_attempts,
                DEEP_ANALYZER_VERSION,
                file_hash or "",
            ),
        )

    def _reactivate_job(self, job_id: str, run_id: str, max_attempts: int) -> None:
        ejecutar(
            """
            UPDATE audio_analysis_jobs
            SET run_id=?, status='pending', max_attempts=?, updated_at=datetime('now'), finished_at=NULL
            WHERE job_id=?
            """,
            (run_id, max_attempts, job_id),
        )

    def _next_pending_job(self, run_id: str):
        return obtener_una_fila(
            """
            SELECT j.*, p.ruta_archivo, p.hash_sha256
            FROM audio_analysis_jobs j
            JOIN pistas p ON CAST(p.id AS TEXT)=j.track_id
            WHERE j.run_id=? AND j.job_type='deep' AND j.status='pending'
            ORDER BY j.priority ASC, j.created_at ASC
            LIMIT 1
            """,
            (run_id,),
        )

    def _run_job(self, run_id: str, job, analyzer: EssentiaTensorflowAnalyzer, *, progress_callback: Callable[[dict], None] | None = None) -> None:
        track_id = str(job["track_id"])
        file_path = str(job["ruta_archivo"] or "")
        attempts = int(job["attempts"] or 0) + 1
        ejecutar(
            """
            UPDATE audio_analysis_jobs
            SET status='running', attempts=?, started_at=COALESCE(started_at, datetime('now')),
                updated_at=datetime('now'), error_code='', error_message=''
            WHERE job_id=?
            """,
            (attempts, job["job_id"]),
        )
        ejecutar(
            """
            UPDATE audio_analysis_runs
            SET status='running', current_track_id=?, current_file_path=?, current_stage=?,
                last_update_at=?
            WHERE run_id=?
            """,
            (track_id, file_path, DEEP_STAGE, _utc_now(), run_id),
        )
        self._refresh_run_summary(run_id)
        if progress_callback:
            progress_callback(self.status(run_id=run_id))

        result = analyzer.analyze(track_id, file_path)
        run_status = self._run_status(run_id)
        if run_status in {"cancelled_keep", "cancelled_discard"}:
            ejecutar(
                """
                UPDATE audio_analysis_jobs
                SET status=?, updated_at=datetime('now'), finished_at=datetime('now')
                WHERE job_id=?
                """,
                (run_status, job["job_id"]),
            )
            self._refresh_run_summary(run_id)
            return

        persist_deep_analysis(
            None,
            self.base_dir,
            result,
            file_hash=str(job["hash_sha256"] or job["file_hash"] or ""),
            run_id=run_id,
        )
        status = result.get("analysis_status") or "failed"
        if status not in {"ready", "failed", "skipped"}:
            status = "failed"
        ejecutar(
            """
            UPDATE audio_analysis_jobs
            SET status=?, error_code=?, error_message=?,
                updated_at=datetime('now'), finished_at=datetime('now')
            WHERE job_id=?
            """,
            (
                status,
                result.get("error_code", ""),
                result.get("error_message", ""),
                job["job_id"],
            ),
        )
        if run_status == "paused":
            ejecutar(
                "UPDATE audio_analysis_runs SET status='paused', last_update_at=? WHERE run_id=?",
                (_utc_now(), run_id),
            )
        self._refresh_run_summary(run_id)

    def _make_analyzer(self, cfg: AudioIntelligenceBackgroundConfig):
        """Construye el analyzer deep adecuado según el contexto.

        Política:
          * Si hay una factory inyectada (tests / overrides), úsala.
          * Si la app corre congelada (PyInstaller bundle) o el usuario
            forzó ``NB_SOUND_DEEP_SUBPROCESS=1``, lanzamos el adaptador
            ``DeepAnalyzerSubprocess`` que delega a un Python externo.
            Eso evita que TensorFlow ahogue el GIL del proceso Qt y
            mantiene la UI 100% responsive durante el análisis.
          * En desarrollo (no frozen) seguimos in-process: tests
            existentes asumen ese modo y arrancar un subprocess por
            cada corrida desperdicia segundos.
        """
        if self._analyzer_factory is not None:
            return self._analyzer_factory()
        import os
        usar_subprocess = (
            bool(getattr(sys, "frozen", False))
            or os.environ.get("NB_SOUND_DEEP_SUBPROCESS", "").strip() in {"1", "true", "yes"}
        )
        if usar_subprocess:
            import traceback
            try:
                from core.audio_intelligence_deep_subprocess import DeepAnalyzerSubprocess
                _log.info(
                    "AudioIntelligence: usando DeepAnalyzerSubprocess "
                    "(frozen=%s, model_dir=%s)",
                    bool(getattr(sys, "frozen", False)), cfg.model_dir,
                )
                return DeepAnalyzerSubprocess(
                    model_dir=str(Path(cfg.model_dir).expanduser()) if cfg.model_dir else "",
                    backend=cfg.backend,
                    enable_mood_models=cfg.mood_models,
                    enable_embeddings=cfg.embeddings,
                    enable_tagging_models=cfg.tagging_models,
                )
            except Exception as exc:
                # Si falla la importación del adaptador, caemos al
                # in-process. Mejor degradar que romper. PERO logueamos
                # bien fuerte porque significa que estamos cargando
                # TensorFlow dentro del proceso de la UI (puede tumbarla).
                _log.error(
                    "AudioIntelligence: DeepAnalyzerSubprocess no se pudo "
                    "instanciar, cayendo a in-process. exc=%s\n%s",
                    exc, traceback.format_exc()[-1500:],
                )
        _log.info("AudioIntelligence: usando EssentiaTensorflowAnalyzer in-process")
        return EssentiaTensorflowAnalyzer(
            model_dir=str(Path(cfg.model_dir).expanduser()) if cfg.model_dir else "",
            backend=cfg.backend,
            enable_mood_models=cfg.mood_models,
            enable_embeddings=cfg.embeddings,
            enable_tagging_models=cfg.tagging_models,
        )

    def _availability_warning(self, cfg: AudioIntelligenceBackgroundConfig) -> str:
        warning = self._config_warning(cfg)
        if warning:
            return warning
        analyzer = self._make_analyzer(cfg)
        ok, error = analyzer.backend_available()
        if not ok:
            return f"Backend deep no disponible: {error}"
        if not analyzer.model_dir_configured or not analyzer.model_dir.exists():
            return "AUDIO_INTELLIGENCE_MODEL_DIR no existe o no esta configurado."
        runnable = [m for m in analyzer.available_models() if m.get("is_available") and m.get("enabled")]
        if not runnable:
            return "No hay modelos deep habilitados y disponibles."
        return ""

    def _config_warning(self, cfg: AudioIntelligenceBackgroundConfig) -> str:
        if not cfg.enabled:
            return "Audio Intelligence deep esta desactivado."
        if not cfg.background_enabled:
            return "Audio Intelligence background esta desactivado."
        if cfg.backend in {"", "none", "disabled"}:
            return "Backend deep configurado como none."
        if not cfg.model_dir:
            return "AUDIO_INTELLIGENCE_MODEL_DIR no esta configurado."
        if cfg.model_dir and not Path(cfg.model_dir).expanduser().exists():
            return "El directorio de modelos deep no existe."
        return ""

    def _cancel(self, *, run_id: str | None, policy: str) -> dict:
        run_id = run_id or self._latest_active_run_id()
        if not run_id:
            return self.status(message="No hay corrida deep para cancelar.")
        ejecutar(
            """
            UPDATE audio_analysis_jobs
            SET status=?, updated_at=datetime('now'), finished_at=datetime('now')
            WHERE run_id=? AND status IN ('pending','running','paused')
            """,
            (policy, run_id),
        )
        ejecutar(
            """
            UPDATE audio_analysis_runs
            SET status=?, cancel_policy=?, last_update_at=?, finished_at=datetime('now')
            WHERE run_id=?
            """,
            (policy, policy, _utc_now(), run_id),
        )
        self._refresh_run_summary(run_id)
        return self.status(run_id=run_id, message="Audio Intelligence deep cancelado.")

    def _set_run_status(self, run_id: str, status: str, *, finished: bool = False, message: str = "") -> None:
        ejecutar(
            """
            UPDATE audio_analysis_runs
            SET status=?, last_update_at=?, finished_at=CASE WHEN ? THEN datetime('now') ELSE finished_at END
            WHERE run_id=?
            """,
            (status, _utc_now(), 1 if finished else 0, run_id),
        )
        if message:
            self._merge_run_summary(run_id, {"message": message})
        self._refresh_run_summary(run_id)

    def _refresh_run_summary(self, run_id: str) -> dict:
        counts = {
            "total_tracks": 0,
            "processed_tracks": 0,
            "ready_tracks": 0,
            "failed_tracks": 0,
            "skipped_tracks": 0,
            "pending_tracks": 0,
        }
        rows = obtener_filas(
            "SELECT status, COUNT(*) c FROM audio_analysis_jobs WHERE run_id=? GROUP BY status",
            (run_id,),
        )
        for row in rows:
            st = str(row["status"] or "")
            count = int(row["c"] or 0)
            counts["total_tracks"] += count
            if st in {"ready", "failed", "skipped"}:
                counts["processed_tracks"] += count
            if st == "ready":
                counts["ready_tracks"] += count
            elif st == "failed":
                counts["failed_tracks"] += count
            elif st == "skipped":
                counts["skipped_tracks"] += count
            elif st in {"pending", "paused", "running"}:
                counts["pending_tracks"] += count

        run = obtener_una_fila("SELECT * FROM audio_analysis_runs WHERE run_id=?", (run_id,))
        if not run:
            return counts

        started_at = _parse_utc(run["started_at"])
        now_dt = datetime.now(timezone.utc)
        elapsed_ms = max(0, int((now_dt - started_at).total_seconds() * 1000))
        processed = counts["processed_tracks"]
        pending = counts["pending_tracks"]

        if processed > 0 and elapsed_ms > 0:
            avg_ms = elapsed_ms / processed
            tracks_per_minute = processed / max(elapsed_ms / 60000.0, 1e-9)
            eta_seconds = (avg_ms * pending) / 1000.0
        else:
            avg_ms = None
            tracks_per_minute = 0.0
            eta_seconds = 0.0 if pending == 0 else None

        eta_human = _format_eta(eta_seconds)
        summary = {
            **counts,
            "total": counts["total_tracks"],
            "processed": counts["processed_tracks"],
            "ready": counts["ready_tracks"],
            "failed": counts["failed_tracks"],
            "skipped": counts["skipped_tracks"],
            "pending": counts["pending_tracks"],
            "elapsed_ms": elapsed_ms,
            "avg_ms_per_track": avg_ms,
            "tracks_per_minute": tracks_per_minute,
            "eta_seconds": eta_seconds,
            "eta_human": eta_human,
            "eta_last_value": eta_human,
        }
        ejecutar(
            """
            UPDATE audio_analysis_runs
            SET total_tracks=?, processed_tracks=?, ready_tracks=?, failed_tracks=?,
                skipped_tracks=?, pending_tracks=?, elapsed_ms=?, avg_ms_per_track=?,
                tracks_per_minute=?, eta_seconds=?, eta_human=?, eta_last_value=?,
                last_update_at=?, summary_json=?
            WHERE run_id=?
            """,
            (
                counts["total_tracks"],
                counts["processed_tracks"],
                counts["ready_tracks"],
                counts["failed_tracks"],
                counts["skipped_tracks"],
                counts["pending_tracks"],
                elapsed_ms,
                avg_ms,
                tracks_per_minute,
                eta_seconds,
                eta_human,
                eta_human,
                _utc_now(),
                json.dumps(summary, ensure_ascii=False, sort_keys=True),
                run_id,
            ),
        )
        return summary

    def _merge_run_summary(self, run_id: str, extra: dict) -> None:
        row = obtener_una_fila("SELECT summary_json FROM audio_analysis_runs WHERE run_id=?", (run_id,))
        try:
            data = json.loads(row["summary_json"] or "{}") if row else {}
        except json.JSONDecodeError:
            data = {}
        data.update(extra)
        ejecutar(
            "UPDATE audio_analysis_runs SET summary_json=?, last_update_at=? WHERE run_id=?",
            (json.dumps(data, ensure_ascii=False, sort_keys=True), _utc_now(), run_id),
        )

    def _run_status(self, run_id: str) -> str:
        row = obtener_una_fila("SELECT status FROM audio_analysis_runs WHERE run_id=?", (run_id,))
        return str(row["status"] or "") if row else ""

    def _latest_active_run_id(self) -> str:
        row = obtener_una_fila(
            """
            SELECT run_id
            FROM audio_analysis_runs
            WHERE mode=? AND status IN ('pending','running','paused')
            ORDER BY started_at DESC, last_update_at DESC
            LIMIT 1
            """,
            (BACKGROUND_MODE,),
        )
        return str(row["run_id"]) if row else ""

    def _latest_run_with_pending_jobs(self) -> str:
        row = obtener_una_fila(
            """
            SELECT r.run_id
            FROM audio_analysis_runs r
            JOIN audio_analysis_jobs j ON j.run_id=r.run_id
            WHERE r.mode=? AND j.job_type='deep' AND j.status IN ('pending','paused','running')
            ORDER BY r.last_update_at DESC, r.started_at DESC
            LIMIT 1
            """,
            (BACKGROUND_MODE,),
        )
        return str(row["run_id"]) if row else ""

    def _latest_run_id(self) -> str:
        row = obtener_una_fila(
            """
            SELECT run_id
            FROM audio_analysis_runs
            WHERE mode=?
            ORDER BY started_at DESC, last_update_at DESC
            LIMIT 1
            """,
            (BACKGROUND_MODE,),
        )
        return str(row["run_id"]) if row else ""

    def _sleep_interruptible(self, seconds: float, run_id: str, stop_event: threading.Event | None) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if stop_event is not None and stop_event.is_set():
                return
            if self._run_status(run_id) in {"paused", "cancelled_keep", "cancelled_discard"}:
                return
            time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))
