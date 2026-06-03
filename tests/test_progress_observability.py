import json
import logging
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

import pytest

from core.pipeline import PipelineCatalogacion
from db.conexion import cerrar_db, get_conexion, inicializar_db
from domain.models import ArchivoAudio, DecisionArchivo, DecisionTipo
from infra.execution_control import ControlEjecucion
from infra.progress import BarraProgreso
from servicios.importacion import marcar_sesiones_importacion_huerfanas, _BarraProgresoBridge


def test_barra_progreso_log_mode_muestra_fase_eta_y_sidecars(monkeypatch, capsys):
    monkeypatch.setenv("NB_SOUND_PROGRESS_MODE", "log")
    monkeypatch.setenv("NB_SOUND_PROGRESS_INTERVAL_SEC", "0.25")

    barra = BarraProgreso(total_archivos=2)
    barra.iniciar()
    barra.establecer_fase("phase_2", "Fase 2 - resolucion dirigida", total=2, current=0)
    barra.actualizar_archivo("tema.mp3", "validando")
    barra.registrar_tarea_extra("assets", "tema.mp3", "imagenes: tema.mp3")
    barra.finalizar_tarea_extra("assets", "tema.mp3", ok=True, duracion_seg=0.2)
    barra.registrar_resultado("aceptado", duracion_archivo_seg=1.0)
    barra.finalizar()

    salida = capsys.readouterr().out
    assert "[progreso]" in salida
    assert "Fase 2 - resolucion dirigida" in salida
    assert "imagenes:1/1" in salida
    assert "ETA fase:" in salida
    assert "\r" not in salida


def test_control_ejecucion_persiste_fase_y_sidecars(tmp_path: Path):
    ruta = tmp_path / "logs" / "run_state.json"
    control = ControlEjecucion(ruta)

    control.fase("sidecars", "Finalizando assets", total=4, current=1, current_item="a.mp3")
    control.registrar_tarea_extra("assets", "a.mp3", "scheduled", "imagenes")
    control.registrar_tarea_extra("assets", "a.mp3", "timeout", "timeout tras 5s")
    control.progreso_fase(current=2, total=4, current_task="sidecar_timeout:assets")

    data = json.loads(ruta.read_text(encoding="utf-8"))
    assert data["phase_id"] == "sidecars"
    assert data["phase_label"] == "Finalizando assets"
    assert data["phase_current"] == 2
    assert data["extras"]["assets"]["scheduled"] == 1
    assert data["extras"]["assets"]["timeout"] == 1
    assert data["extras"]["assets"]["pending"] == 0
    assert data["last_event"].startswith("assets:timeout")


def test_bridge_ui_propaga_fases_y_sidecars():
    eventos = []
    bridge = _BarraProgresoBridge(
        callback=lambda p, t, n, e: eventos.append((p, t, n, e)),
        cancelar_evento=threading.Event(),
    )

    bridge.set_total_archivos(3)
    bridge.establecer_fase("sidecars", "Finalizando assets, letras y manifiestos", total=2)
    bridge.registrar_tarea_extra("assets", "tema.mp3", "imagenes: tema.mp3")
    bridge.finalizar_tarea_extra("assets", "tema.mp3", ok=False, detalle="timeout")

    etapas = [e[3] for e in eventos]
    assert any("Finalizando assets" in etapa for etapa in etapas)
    assert any("assets" in etapa and "timeout" in etapa for etapa in etapas)
    assert eventos[-1][0] == 0
    assert eventos[-1][1] == 3


def test_sidecar_timeout_no_bloquea_y_marca_retryable(tmp_path: Path):
    pipeline = PipelineCatalogacion(
        directorio_entrada=tmp_path / "input",
        directorio_biblioteca=tmp_path / "library",
        directorio_quarantine=tmp_path / "quarantine",
        directorio_revision=tmp_path / "review",
        directorio_logs=tmp_path / "logs",
        directorio_procesados=tmp_path / "processed",
        directorio_cache=tmp_path / "cache",
        directorio_temp=tmp_path / "temp",
    )
    decision = DecisionArchivo(
        tipo=DecisionTipo.ACEPTADO,
        archivo=ArchivoAudio(ruta_original=tmp_path / "input" / "tema.mp3"),
    )
    future = Future()
    setattr(future, "_nb_sound_started_at", time.monotonic() - 10)
    key = pipeline._sidecar_key("assets", decision, "tema.mp3")
    pipeline._assets_futures = [
        {
            "kind": "assets",
            "nombre": "tema.mp3",
            "decision": decision,
            "future": future,
            "submitted_at": time.monotonic() - 10,
            "key": key,
        }
    ]

    inicio = time.monotonic()
    with (
        patch("core.pipeline.SIDECAR_FUTURE_TIMEOUT_SEG", 0.01),
        patch("core.pipeline.SIDECAR_WAIT_HEARTBEAT_SEG", 0.01),
    ):
        pipeline._esperar_assets_pendientes()

    assert time.monotonic() - inicio < 1.0
    assert pipeline._assets_futures == []
    estado = decision.esquema_explicacion["sidecars"]["assets"]
    assert estado["status"] == "timeout"
    assert estado["retryable"] is True


def test_sidecar_timeout_no_cuenta_tiempo_en_cola(tmp_path: Path):
    pipeline = PipelineCatalogacion(
        directorio_entrada=tmp_path / "input",
        directorio_biblioteca=tmp_path / "library",
        directorio_quarantine=tmp_path / "quarantine",
        directorio_revision=tmp_path / "review",
        directorio_logs=tmp_path / "logs",
        directorio_procesados=tmp_path / "processed",
        directorio_cache=tmp_path / "cache",
        directorio_temp=tmp_path / "temp",
    )
    decision = DecisionArchivo(
        tipo=DecisionTipo.ACEPTADO,
        archivo=ArchivoAudio(ruta_original=tmp_path / "input" / "cola.mp3"),
    )
    future = Future()
    key = pipeline._sidecar_key("assets", decision, "cola.mp3")
    pipeline._assets_futures = [
        {
            "kind": "assets",
            "nombre": "cola.mp3",
            "decision": decision,
            "future": future,
            "submitted_at": time.monotonic() - 10,
            "key": key,
        }
    ]

    def terminar_future():
        time.sleep(0.05)
        future.set_result(None)

    hilo = threading.Thread(target=terminar_future)
    hilo.start()
    with (
        patch("core.pipeline.SIDECAR_FUTURE_TIMEOUT_SEG", 0.01),
        patch("core.pipeline.SIDECAR_WAIT_HEARTBEAT_SEG", 0.01),
    ):
        pipeline._esperar_assets_pendientes()
    hilo.join(timeout=1.0)

    assert "assets" not in decision.esquema_explicacion.get("sidecars", {})


def test_sidecar_assets_tardio_guarda_resultado_util(tmp_path: Path):
    pipeline = PipelineCatalogacion(
        directorio_entrada=tmp_path / "input",
        directorio_biblioteca=tmp_path / "library",
        directorio_quarantine=tmp_path / "quarantine",
        directorio_revision=tmp_path / "review",
        directorio_logs=tmp_path / "logs",
        directorio_procesados=tmp_path / "processed",
        directorio_cache=tmp_path / "cache",
        directorio_temp=tmp_path / "temp",
    )
    decision = DecisionArchivo(
        tipo=DecisionTipo.ACEPTADO,
        archivo=ArchivoAudio(ruta_original=tmp_path / "input" / "tarde.mp3"),
    )
    key = pipeline._sidecar_key("assets", decision, "tarde.mp3")
    with pipeline._sidecar_lock:
        pipeline._sidecars_timeout.add(key)

    class FakeAssets:
        def procesar(self, decision):
            decision.esquema_explicacion["asset_selection"] = {
                "track": {"selected": str(tmp_path / "cover.jpg")},
                "album": {"selected": None},
                "artist": {"selected": None},
            }

    pipeline._assets = FakeAssets()
    pipeline._ejecutar_assets_safe(decision, "tarde.mp3", key)

    estado = decision.esquema_explicacion["sidecars"]["assets"]
    assert estado["status"] == "late_saved"
    assert estado["retryable"] is False
    assert estado["selected"]["track"].endswith("cover.jpg")


@pytest.fixture()
def db_tmp(tmp_path):
    ruta = tmp_path / "ui.db"
    inicializar_db(ruta)
    try:
        yield ruta
    finally:
        cerrar_db()


def test_servicio_importacion_marca_sesiones_huerfanas(db_tmp):
    con = get_conexion()
    cur = con.execute(
        """
        INSERT INTO sesiones_import(directorio_entrada, estado)
        VALUES (?, 'en_progreso')
        """,
        ("/tmp/entrada",),
    )
    sesion_id = cur.lastrowid

    marcar_sesiones_importacion_huerfanas()

    row = con.execute("SELECT estado, finalizado_en, reporte_json FROM sesiones_import WHERE id=?", (sesion_id,)).fetchone()
    assert row["estado"] == "interrumpido"
    assert row["finalizado_en"]
    assert "interrumpido" in row["reporte_json"]


def test_modelo_importacion_loguea_fallo_al_marcar_sesiones_huerfanas(db_tmp, monkeypatch, caplog):
    pytest.importorskip("PySide6")
    import servicios.importacion as importacion_mod
    from ui.modelos_qml import ModeloImportacion

    def falla_marcado():
        raise RuntimeError("fallo controlado")

    monkeypatch.setattr(importacion_mod, "marcar_sesiones_importacion_huerfanas", falla_marcado)

    with caplog.at_level(logging.WARNING, logger="nb_sound.ui.modelos_qml"):
        ModeloImportacion()

    assert "No se pudieron marcar sesiones de importacion huerfanas" in caplog.text
    assert "fallo controlado" in caplog.text


def test_cli_no_tty_emite_snapshots_y_crea_estado(tmp_path: Path):
    input_dir = tmp_path / "input"
    dirs = {
        "library": tmp_path / "library",
        "quarantine": tmp_path / "quarantine",
        "review": tmp_path / "review",
        "logs": tmp_path / "logs",
        "processed": tmp_path / "processed",
        "cache": tmp_path / "cache",
        "temp": tmp_path / "temp",
    }
    input_dir.mkdir()
    for ruta in dirs.values():
        ruta.mkdir()
    (input_dir / "bad.mp3").write_bytes(b"\x00" * 12_000)

    env = {
        **os.environ,
        "PYTHONPATH": ".",
        "NB_SOUND_PROGRESS_MODE": "log",
        "ENABLE_ASSETS_PIPELINE": "false",
        "ENABLE_EXTERNAL_ENRICHMENT": "false",
        "ENABLE_SECOND_STAGE_RESOLUTION": "false",
        "ENABLE_THIRD_STAGE_RESOLUTION": "false",
        "ENABLE_DEDUPLICATION": "false",
        "ENABLE_SHAZAM": "false",
        "ENABLE_ACOUSTID": "false",
        "NO_COLOR": "1",
        "USER_ASSETS_DIR": str(tmp_path / "assets"),
        "USER_MANIFESTS_DIR": str(tmp_path / "manifests"),
    }
    cmd = [
        sys.executable,
        "main.py",
        "--input", str(input_dir),
        "--library", str(dirs["library"]),
        "--quarantine", str(dirs["quarantine"]),
        "--review", str(dirs["review"]),
        "--logs", str(dirs["logs"]),
        "--processed", str(dirs["processed"]),
        "--cache", str(dirs["cache"]),
        "--temp", str(dirs["temp"]),
        "--no-hotkeys",
    ]

    proc = subprocess.run(
        cmd,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        capture_output=True,
        timeout=25,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "\x1b" not in proc.stdout
    assert "[progreso]" in proc.stdout
    assert "Fase:" in proc.stdout
    assert "RESUMEN FINAL" in proc.stdout
    assert (dirs["logs"] / "run_state.json").exists()
    assert (dirs["logs"] / "tagger_run.log").exists()
