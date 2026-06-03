# PyInstaller spec — macOS build (.app bundle)
# Uso: pyinstaller packaging/macos/nb_sound.spec
# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()
sys.path.insert(0, str(SPEC_DIR.parent))

import _common  # noqa: E402

block_cipher = None

ROOT = _common.project_root(SPECPATH)
LOGO_DIR = ROOT / "ui" / "qml" / "assets" / "logo"

# Leer version dinamicamente desde infra.version para que el .app no se
# desincronice del codigo cuando se publique una nueva release.
sys.path.insert(0, str(ROOT))
from infra.version import APP_VERSION, APP_IDENTIFIER  # noqa: E402

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
    icon=str(LOGO_DIR / "logo.icns"),
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

app = BUNDLE(
    coll,
    name="NB Sound.app",
    icon=str(LOGO_DIR / "logo.icns"),
    bundle_identifier=APP_IDENTIFIER,
    info_plist={
        "CFBundleName": "NB Sound",
        "CFBundleDisplayName": "NB Sound",
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "10.15",
        "LSApplicationCategoryType": "public.app-category.music",
        # macOS exige declarar uso de microfono incluso para apps que NO lo usan.
        # Se documenta explicitamente que NB Sound no captura audio del usuario.
        "NSMicrophoneUsageDescription":
            "NB Sound no usa el microfono; este es un valor por defecto requerido "
            "por los frameworks de audio del sistema.",
    },
)
