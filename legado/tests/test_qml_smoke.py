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


def test_principal_y_vistas_con_menu_playlist_cargan_sin_errores(app, tmp_path, monkeypatch):
    """Carga Principal.qml con el árbol real de modelos y fuerza la activación
    de las vistas que integran el selector "agregar a playlist"
    (MenuAgregarPlaylist). Detecta errores de runtime QML que los linters
    estáticos no ven (TypeError/ReferenceError, slots inexistentes)."""
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QML_DISABLE_DISK_CACHE", "1")

    from PySide6.QtCore import QTimer, QUrl
    from db.conexion import cerrar_db, inicializar_db
    import main_ui as main_ui_mod

    inicializar_db(tmp_path / "smoke.sqlite3")
    try:
        warnings = []
        engine = QQmlApplicationEngine()
        engine.warnings.connect(lambda errs: [warnings.append(e.toString()) for e in errs])
        main_ui_mod.exponer_modelos(engine, main_ui_mod.construir_modelos(app))
        engine.addImportPath(str((_QML_DIR).resolve()))
        engine.addImportPath(str((_QML_DIR / "componentes").resolve()))
        engine.addImportPath(str((_QML_DIR / "vistas").resolve()))
        engine.load(QUrl.fromLocalFile(str(main_ui_mod.ARCHIVO_QML.resolve())))

        roots = engine.rootObjects()
        assert roots, "Principal.qml no cargó"
        root = roots[0]

        # Forzar la activación de las vistas tocadas (MenuAgregarPlaylist,
        # botón guardar DJ, Instalar todo, contador Karaoke).
        for vista in ("busqueda", "biblioteca", "playlists", "dj_privado", "karaoke", "estado_sistema"):
            root.setProperty("vista_activa", vista)
            deadline = QTimer()
            deadline.setSingleShot(True)
            deadline.start(60)
            while deadline.isActive():
                app.processEvents()

        errs = _filtrar_errores_reales(warnings)
        assert errs == [], f"Runtime QML con errores: {errs}"
    finally:
        cerrar_db()
