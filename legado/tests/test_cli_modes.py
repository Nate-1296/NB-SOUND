from pathlib import Path
import subprocess
import sys

import pytest
from tempfile import TemporaryDirectory

import main
from db.conexion import cerrar_db


def _monkeypatch_all_dirs(monkeypatch, tmp_path):
    """Monkeypatch all directory settings to tmp_path to avoid FS errors."""
    for attr in (
        "DEFAULT_INPUT_DIR", "DEFAULT_LIBRARY_DIR", "DEFAULT_QUARANTINE_DIR",
        "DEFAULT_REVIEW_DIR", "DEFAULT_LOGS_DIR", "DEFAULT_PROCESSED_DIR",
        "DEFAULT_CACHE_DIR", "DEFAULT_TEMP_DIR", "DEFAULT_ASSETS_DIR",
        "DEFAULT_MANIFESTS_DIR",
    ):
        monkeypatch.setattr(main.settings, attr, tmp_path)


@pytest.mark.parametrize(
    "argv",
    [
        ["main.py", "--audit", "--repair"],
        ["main.py", "--audio-features-status", "--audit"],
        ["main.py", "--music-discovery", "rock energético", "--repair"],
        ["main.py", "--audio-intelligence-deep-status", "--import-recovery-status"],
        ["main.py", "--assets-retry-missing", "--metadata-only"],
        ["main.py", "--audio-intelligence-deep-cancel-discard", "--audio-intelligence-deep-pause"],
    ],
)
def test_cli_rejects_multiple_action_modes(monkeypatch, tmp_path, argv):
    _monkeypatch_all_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr("sys.argv", argv)

    rc = main.main()

    assert rc == 1


def test_cli_explain_without_db_returns_zero(monkeypatch, tmp_path):
    _monkeypatch_all_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr("sys.argv", ["main.py", "--explain", "foo"])
    rc = main.main()
    assert rc == 0


def test_cli_audit_without_db_returns_zero(monkeypatch, tmp_path):
    _monkeypatch_all_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr("sys.argv", ["main.py", "--audit"])
    rc = main.main()
    assert rc == 0


def test_cli_help_refleja_audio_multiformato_y_modo_discografia():
    parser = main.construir_parser()
    help_text = parser.format_help()
    assert "audio soportados" in help_text
    assert "--discography-organize" in help_text
    assert "--audio-intelligence-deep-status" in help_text
    assert "--import-recovery-status" in help_text
    assert "--assets-retry-missing" in help_text
    assert "--sidecars-retry-failed" in help_text


def test_cli_help_muestra_todos_los_comandos_deep_background():
    """Validates all deep background CLI commands appear in --help."""
    parser = main.construir_parser()
    help_text = parser.format_help()
    for cmd in (
        "--audio-intelligence-deep-status",
        "--audio-intelligence-deep-resume",
        "--audio-intelligence-deep-pause",
        "--audio-intelligence-deep-cancel-keep",
        "--audio-intelligence-deep-cancel-discard",
        "--audio-intelligence-deep-retry-failed",
        "--audio-features-analyze",
        "--audio-features-status",
        "--audio-features-reanalyze",
        "--music-discovery",
    ):
        assert cmd in help_text, f"Falta {cmd} en --help"


def test_cli_help_no_carga_backends_pesados():
    repo = Path(__file__).resolve().parents[1]
    script = (
        "import sys; "
        "before = set(sys.modules); "
        "import main; "
        "main.construir_parser().format_help(); "
        "loaded = set(sys.modules) - before; "
        "pesados = sorted(m for m in ("
        "'core.audio_features', "
        "'core.audio_intelligence_deep', "
        "'core.music_discovery_service', "
        "'essentia', "
        "'tensorflow', "
        "'librosa', "
        "'numpy'"
        ") if m in loaded); "
        "print(','.join(pesados))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    assert proc.stdout.strip() == ""


def test_cli_audio_intelligence_deep_status_sin_biblioteca_crashea_no(monkeypatch, tmp_path):
    monkeypatch.setattr(main.settings, "DEFAULT_LIBRARY_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["main.py", "--audio-intelligence-deep-status"])
    rc = main.main()
    assert rc == 0


def test_cli_audio_features_status_db_vacia(monkeypatch, tmp_path, capsys):
    """--audio-features-status con DB vacía no crashea y muestra info."""
    monkeypatch.setattr(main.settings, "DEFAULT_LIBRARY_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["main.py", "--audio-features-status"])
    rc = main.main()
    salida = capsys.readouterr().out
    assert rc == 0
    assert "audio_features_status" in salida
    assert "biblioteca: 0" in salida


def test_cli_deep_resume_sin_pendientes(monkeypatch, tmp_path, capsys):
    """--audio-intelligence-deep-resume sin pendientes no crashea."""
    monkeypatch.setattr(main.settings, "DEFAULT_LIBRARY_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["main.py", "--audio-intelligence-deep-resume"])
    rc = main.main()
    assert rc == 0


def test_cli_deep_pause_sin_run(monkeypatch, tmp_path, capsys):
    """--audio-intelligence-deep-pause sin run activo responde controlado."""
    monkeypatch.setattr(main.settings, "DEFAULT_LIBRARY_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["main.py", "--audio-intelligence-deep-pause"])
    rc = main.main()
    assert rc == 0


def test_cli_deep_cancel_keep_sin_run(monkeypatch, tmp_path, capsys):
    """--audio-intelligence-deep-cancel-keep sin run responde controlado."""
    monkeypatch.setattr(main.settings, "DEFAULT_LIBRARY_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["main.py", "--audio-intelligence-deep-cancel-keep"])
    rc = main.main()
    assert rc == 0


def test_cli_deep_retry_failed_sin_jobs(monkeypatch, tmp_path, capsys):
    """--audio-intelligence-deep-retry-failed sin jobs fallidos responde controlado."""
    monkeypatch.setattr(main.settings, "DEFAULT_LIBRARY_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["main.py", "--audio-intelligence-deep-retry-failed"])
    rc = main.main()
    salida = capsys.readouterr().out
    assert rc == 0
    assert "audio_intelligence_deep_background" in salida


def test_cli_import_recovery_status_db_vacia(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(main.settings, "DEFAULT_LIBRARY_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["main.py", "--import-recovery-status"])
    rc = main.main()
    salida = capsys.readouterr().out
    assert rc == 0
    assert "Estado de Diagnóstico y Recuperación Post-Import" in salida
    assert "Pistas en biblioteca: 0" in salida

def test_cli_deep_cancel_discard_sin_run(monkeypatch, tmp_path):
    monkeypatch.setattr(main.settings, "DEFAULT_LIBRARY_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["main.py", "--audio-intelligence-deep-cancel-discard"])

    rc = main.main()

    assert rc == 0


@pytest.mark.parametrize(
    "flag",
    [
        "--assets-retry-missing",
        "--assets-retry-covers-only",
        "--assets-retry-artists-only",
        "--enrichment-retry-missing",
        "--lyrics-retry-missing",
        "--sidecars-retry-failed",
        "--audio-features-retry-failed",
    ],
)
def test_cli_import_recovery_actions_db_vacia(monkeypatch, tmp_path, capsys, flag):
    _monkeypatch_all_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr("sys.argv", ["main.py", flag])

    rc = main.main()
    salida = capsys.readouterr().out

    assert rc == 0
    assert "Diagnóstico" in salida or "Reintento" in salida or "Audio Features" in salida

