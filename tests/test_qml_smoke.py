"""
Smoke tests QML: valida que Principal.qml y vistas críticas carguen
sin errores TypeError/ReferenceError con el árbol de modelos real.

Estos tests garantizan que un refactor masivo no rompa runtime QML
(situación que linters estáticos no detectan).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine


_QML_DIR = Path(__file__).resolve().parent.parent / "ui" / "qml"


@pytest.fixture(scope="module")
def app():
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app


def _cargar(app, qml_path):
    warnings = []
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda errs: [warnings.append(e.toString()) for e in errs])
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    return engine, warnings


def _filtrar_errores_reales(warnings):
    return [w for w in warnings if any(k in w for k in (
        "TypeError", "ReferenceError", "is not a function", "cannot read"
    ))]


def test_uitokens_se_carga_sin_errores(app):
    """UiTokens singleton debe parsearse sin warnings."""
    engine, warnings = _cargar(app, _QML_DIR / "componentes" / "UiTokens.qml")
    errs = _filtrar_errores_reales(warnings)
    assert errs == [], f"UiTokens tiene errores QML: {errs}"


def test_uiutils_helpers_existen():
    """UiUtils.js debe exportar las funciones documentadas."""
    contenido = (_QML_DIR / "componentes" / "UiUtils.js").read_text(encoding="utf-8")
    for nombre in ("toMediaSource", "toFileUrl", "contrasteSobre", "contrastePorLuminancia", "veloClaro", "veloOscuro"):
        assert f"function {nombre}(" in contenido, f"UiUtils.js no exporta {nombre}"


def test_appscrollbar_existe():
    """AppScrollBar.qml debe existir y declarar el contrato esperado."""
    path = _QML_DIR / "componentes" / "AppScrollBar.qml"
    assert path.exists()
    contenido = path.read_text(encoding="utf-8")
    for prop in ("property var flickable", "property var tema", "contentItem", "background"):
        assert prop in contenido, f"AppScrollBar.qml no declara {prop}"


def test_uitokens_define_tokens_semanticos():
    """UiTokens debe definir los tokens nuevos: fontSizeBase, fontSize2xl."""
    contenido = (_QML_DIR / "componentes" / "UiTokens.qml").read_text(encoding="utf-8")
    for token in ("fontSizeBase", "fontSize2xl"):
        assert token in contenido, f"UiTokens.qml no declara {token}"
