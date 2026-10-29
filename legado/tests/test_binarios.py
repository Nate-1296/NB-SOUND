# =============================================================================
# tests/test_binarios.py
#
# Verifica el helper `infra.binarios.resolver_bin`, que selecciona el binario
# embebido en el bundle PyInstaller sobre el del PATH y soporta el sufijo
# ".exe" automatico en Windows.
# =============================================================================

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from infra import binarios


def _crear_binario(directorio: Path, nombre: str) -> Path:
    """Crea un archivo ejecutable vacio para que `Path.exists()` lo detecte."""
    directorio.mkdir(parents=True, exist_ok=True)
    ruta = directorio / nombre
    ruta.write_text("#!/bin/sh\nexit 0\n")
    ruta.chmod(ruta.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return ruta


# -----------------------------------------------------------------------------
# Sufijo Windows
# -----------------------------------------------------------------------------

class TestSufijoWindows:

    def test_posix_no_agrega_sufijo(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert binarios._con_sufijo_windows("ffmpeg") == "ffmpeg"

    def test_windows_agrega_exe(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        assert binarios._con_sufijo_windows("ffmpeg") == "ffmpeg.exe"

    def test_windows_respeta_exe_ya_presente(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        assert binarios._con_sufijo_windows("ffmpeg.exe") == "ffmpeg.exe"

    def test_windows_respeta_exe_mayusculas(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        assert binarios._con_sufijo_windows("FFmpeg.EXE") == "FFmpeg.EXE"


# -----------------------------------------------------------------------------
# Prioridad: bundled gana sobre PATH
# -----------------------------------------------------------------------------

class TestPrioridadBundled:

    def test_meipass_gana_sobre_path(self, tmp_path, monkeypatch):
        bundled_bin = _crear_binario(tmp_path / "bundle" / "bin", "ffmpeg")

        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(binarios.shutil, "which", lambda _: "/usr/bin/ffmpeg")

        resuelto = binarios.resolver_bin("ffmpeg")
        assert resuelto == str(bundled_bin)

    def test_adyacente_gana_sobre_path(self, tmp_path, monkeypatch):
        exe_dir = tmp_path / "app"
        bundled_bin = _crear_binario(exe_dir / "bin", "ffmpeg")

        falso_exe = exe_dir / "nb_sound"
        falso_exe.write_text("")
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(falso_exe))
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(binarios.shutil, "which", lambda _: "/usr/bin/ffmpeg")

        resuelto = binarios.resolver_bin("ffmpeg")
        assert resuelto == str(bundled_bin)

    def test_path_es_ultimo_recurso(self, monkeypatch):
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(binarios.shutil, "which", lambda _: "/usr/bin/ffmpeg")

        assert binarios.resolver_bin("ffmpeg") == "/usr/bin/ffmpeg"

    def test_none_si_no_existe_en_ningun_lado(self, monkeypatch):
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        monkeypatch.setattr(binarios.shutil, "which", lambda _: None)

        assert binarios.resolver_bin("herramienta_inexistente") is None


# -----------------------------------------------------------------------------
# Comportamiento Windows-especifico
# -----------------------------------------------------------------------------

class TestComportamientoWindows:

    def test_meipass_busca_con_extension_exe(self, tmp_path, monkeypatch):
        bundled = _crear_binario(tmp_path / "bundle" / "bin", "ffmpeg.exe")

        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(binarios.shutil, "which", lambda _: None)

        resuelto = binarios.resolver_bin("ffmpeg")
        assert resuelto == str(bundled)


# -----------------------------------------------------------------------------
# Funcion helper `disponible`
# -----------------------------------------------------------------------------

class TestDisponible:

    def test_disponible_true_cuando_resolver_devuelve_path(self, monkeypatch):
        monkeypatch.setattr(binarios, "resolver_bin", lambda _: "/usr/bin/ffmpeg")
        assert binarios.disponible("ffmpeg") is True

    def test_disponible_false_cuando_resolver_devuelve_none(self, monkeypatch):
        monkeypatch.setattr(binarios, "resolver_bin", lambda _: None)
        assert binarios.disponible("inexistente") is False
