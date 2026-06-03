# PyInstaller spec — Windows build
# Uso: pyinstaller packaging\windows\nb_sound.spec
# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()
sys.path.insert(0, str(SPEC_DIR.parent))

import _common  # noqa: E402

block_cipher = None

ROOT = _common.project_root(SPECPATH)
LOGO_DIR = ROOT / "ui" / "qml" / "assets" / "logo"

a = _common.build_analysis(ROOT)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="nb_sound",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    # Sin firma valida, SmartScreen mostrara advertencia la primera vez.
    icon=str(LOGO_DIR / "logo.ico"),
    # Version info embebida en el .exe: Explorer, Administrador de tareas y el
    # dialogo UAC muestran "NB Sound" / "Nathan" en vez de quedar en blanco
    # (el "editor desconocido"). Se genera desde infra.version.
    version=_common.write_windows_version_file(ROOT),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="nb_sound",
)
