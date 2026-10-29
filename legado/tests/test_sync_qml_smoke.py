# =============================================================================
# tests/test_sync_qml_smoke.py
#
# BLOQUE 4.2: smoke test de runtime de VistaSincronizacion.qml. Carga la vista
# con modelos reales (Tema + Sincronizacion) y valida que:
#   - se instancia sin TypeError/ReferenceError,
#   - el objectName esperado esta presente,
#   - Principal.qml referencia y enruta la nueva vista.
#
# El load QML real corre en un SUBPROCESO limpio: en la suite completa, tests
# previos cargan librerias nativas pesadas (torch/cuda/essentia) que entran en
# conflicto con el teardown del QQmlApplicationEngine en el mismo proceso
# (segfault). Aislarlo en un interprete fresco lo hace determinista.
# =============================================================================

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_QML_DIR = _ROOT / "ui" / "qml"

pytest.importorskip("aiohttp")


_SCRIPT_CARGA = textwrap.dedent(
    """
    import os, sys, tempfile
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QML_DISABLE_DISK_CACHE"] = "1"
    sys.path.insert(0, {root!r})

    from pathlib import Path
    from db.conexion import inicializar_db
    inicializar_db(Path(tempfile.mkdtemp()) / "sync_qml.sqlite3")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from ui.modelos_qml import ModeloConfiguracion, ModeloSincronizacion, ModeloTema

    app = QGuiApplication.instance() or QGuiApplication([])
    config = ModeloConfiguracion()
    tema = ModeloTema(config)
    sinc = ModeloSincronizacion()

    warnings = []
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda errs: [warnings.append(e.toString()) for e in errs])
    engine.addImportPath({qml!r})
    ctx = engine.rootContext()
    ctx.setContextProperty("temaUi", tema)
    ctx.setContextProperty("sincronizacion", sinc)
    engine.load(QUrl.fromLocalFile(str(Path({qml!r}) / "vistas" / "VistaSincronizacion.qml")))
    app.processEvents()

    roots = engine.rootObjects()
    assert roots, "no instancio objeto raiz"
    assert roots[0].objectName() == "vista_sincronizacion", roots[0].objectName()

    reales = [w for w in warnings if any(k in w for k in (
        "TypeError", "ReferenceError", "is not a function", "Unable to assign", "cannot read"))]
    assert not reales, "errores QML: " + repr(reales)
    print("SMOKE_OK")
    """
).format(root=str(_ROOT), qml=str(_QML_DIR))


def test_vista_sincronizacion_carga_sin_referenceerror():
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT_CARGA],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(_ROOT),
    )
    assert "SMOKE_OK" in proc.stdout, (
        f"Carga QML falló (rc={proc.returncode}).\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


def test_principal_enruta_la_vista_sincronizacion():
    principal = (_QML_DIR / "Principal.qml").read_text(encoding="utf-8")
    assert "comp_vista_sincronizacion" in principal
    assert '"sincronizacion": 11' in principal
    assert "VistaSincronizacion" in principal


def test_navlateral_tiene_entrada_sincronizacion():
    nav = (_QML_DIR / "componentes" / "NavLateral.qml").read_text(encoding="utf-8")
    assert "nav_sincronizacion" in nav
    assert 'navegar("sincronizacion")' in nav
