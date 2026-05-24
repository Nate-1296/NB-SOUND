import importlib
import sys
import types
from pathlib import Path

import pytest


class _FakeApp:
    def __init__(self, *_args, **_kwargs):
        pass

    @staticmethod
    def setAttribute(_attr):
        return None

    def setApplicationName(self, _name):
        return None

    def setApplicationVersion(self, _version):
        return None

    def setOrganizationName(self, _name):
        return None

    def setWindowIcon(self, _icon):
        return None

    def exec(self):
        return 0


class _FakeEngine:
    def __init__(self):
        self.import_paths = []

    def addImportPath(self, ruta):
        self.import_paths.append(ruta)

    def rootContext(self):
        class _Ctx:
            def setContextProperty(self, *_args, **_kwargs):
                return None

        return _Ctx()

    def load(self, _url):
        return None

    def rootObjects(self):
        return [object()]


def _cargar_main_ui_con_qt_fake(monkeypatch):
    qtcore = types.ModuleType("PySide6.QtCore")
    qtcore.QUrl = types.SimpleNamespace(fromLocalFile=lambda ruta: ruta)
    qtcore.Qt = types.SimpleNamespace(AA_ShareOpenGLContexts=1)
    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QGuiApplication = _FakeApp
    qtgui.QIcon = lambda *_args, **_kwargs: None
    qtqml = types.ModuleType("PySide6.QtQml")
    qtqml.QQmlApplicationEngine = _FakeEngine
    pyside6 = types.ModuleType("PySide6")

    monkeypatch.setitem(sys.modules, "PySide6", pyside6)
    monkeypatch.setitem(sys.modules, "PySide6.QtCore", qtcore)
    monkeypatch.setitem(sys.modules, "PySide6.QtGui", qtgui)
    monkeypatch.setitem(sys.modules, "PySide6.QtQml", qtqml)

    sys.modules.pop("main_ui", None)
    return importlib.import_module("main_ui")


def _setup_qt_fakes(monkeypatch, main_ui_mod):
    monkeypatch.setattr(main_ui_mod, "QGuiApplication", _FakeApp)
    monkeypatch.setattr(main_ui_mod, "QQmlApplicationEngine", _FakeEngine)


def test_cierra_db_si_falta_qml(monkeypatch):
    main_ui_mod = _cargar_main_ui_con_qt_fake(monkeypatch)
    _setup_qt_fakes(monkeypatch, main_ui_mod)

    cerrado = {"valor": False}
    monkeypatch.setattr(main_ui_mod, "inicializar_aplicacion", lambda _ruta: None)
    monkeypatch.setattr(main_ui_mod, "construir_modelos", lambda _app: {})
    monkeypatch.setattr(main_ui_mod, "ARCHIVO_QML", Path("/tmp/no_existe.qml"))
    monkeypatch.setattr("db.conexion.cerrar_db", lambda: cerrado.__setitem__("valor", True))
    monkeypatch.setattr(main_ui_mod.sys, "argv", ["main_ui.py"])

    codigo = main_ui_mod.main()

    assert codigo == 1
    assert cerrado["valor"] is True


def test_cierra_db_si_falla_construccion_modelos(monkeypatch):
    main_ui_mod = _cargar_main_ui_con_qt_fake(monkeypatch)
    _setup_qt_fakes(monkeypatch, main_ui_mod)

    cerrado = {"valor": False}
    monkeypatch.setattr(main_ui_mod, "inicializar_aplicacion", lambda _ruta: None)
    monkeypatch.setattr(main_ui_mod, "construir_modelos", lambda _app: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(main_ui_mod, "ARCHIVO_QML", Path("/tmp/no_existe.qml"))
    monkeypatch.setattr("db.conexion.cerrar_db", lambda: cerrado.__setitem__("valor", True))
    monkeypatch.setattr(main_ui_mod.sys, "argv", ["main_ui.py"])

    with pytest.raises(RuntimeError, match="boom"):
        main_ui_mod.main()

    assert cerrado["valor"] is True
