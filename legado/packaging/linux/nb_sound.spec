# PyInstaller spec — Linux build
# Uso: pyinstaller packaging/linux/nb_sound.spec
# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

# Hace que `import _common` funcione cuando PyInstaller carga el spec.
SPEC_DIR = Path(SPECPATH).resolve()
sys.path.insert(0, str(SPEC_DIR.parent))

import _common  # noqa: E402

block_cipher = None

ROOT = _common.project_root(SPECPATH)
LOGO_DIR = ROOT / "ui" / "qml" / "assets" / "logo"

a = _common.build_analysis(ROOT)

# Quita del bundle las librerias del sistema que provocan conflictos ABI con
# las del usuario (libvlc/libvlccore, libstdc++, libgcc, libdbus, libsystemd,
# crypto/compression). Ver _common._LINUX_LIBS_DEL_SISTEMA para el detalle.
a.binaries = _common.filter_linux_system_libs(a.binaries)

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
    icon=str(LOGO_DIR / "logo_256.png"),
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
