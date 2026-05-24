"""Tests del worker genérico que mantiene la UI libre de freezes.

`_UiQueryWorker` mueve queries SQL pesadas (Biblioteca, Karaoke,
Playlists, Estadísticas, diagnósticos backend) a un QThread. Estos
tests verifican:

* En modo síncrono (variable de entorno ``NB_SOUND_UI_WORKER_SYNC=1``
  forzada por ``conftest.py``) tanto ``func`` como ``applier`` se
  ejecutan en línea — la semántica usada por todos los demás tests
  de la suite.
* Cuando ``func`` lanza, ``applier`` recibe ``None`` y el flujo
  no aborta.
* El modelo de Estadísticas aplica todos los datos consultados
  (regresión: antes ejecutaba ~12 queries SQL en el hilo de la UI
  cuando se abría VistaInicio).
* El modelo de Karaoke aplica el diagnóstico de backend mediante
  el worker (regresión: ``diagnostico()`` lanzaba subprocess
  bloqueando la UI 100-300 ms).
* El modelo de DJ Privado expone el hook de pre-warm que carga
  los servicios en background (zero-freeze al pulsar "Play DJ").
"""

from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.usefixtures("_patch_pipeline_dirs")


def test_ui_worker_sync_flag_activado_en_tests():
    """conftest debe haber forzado el modo síncrono globalmente."""
    assert os.environ.get("NB_SOUND_UI_WORKER_SYNC") == "1"


def test_ui_worker_run_sync_aplica_resultado_inmediato():
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QCoreApplication
    _app = QCoreApplication.instance() or QCoreApplication([])

    from ui.modelos_qml import _UiQueryWorker

    worker = _UiQueryWorker()
    recibido: dict = {}

    def _func():
        return {"datos": [1, 2, 3]}

    def _aplicar(res):
        recibido["valor"] = res

    worker.run(_func, _aplicar)

    assert recibido["valor"] == {"datos": [1, 2, 3]}


def test_ui_worker_run_sync_func_excepcion_no_aborta():
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QCoreApplication
    _app = QCoreApplication.instance() or QCoreApplication([])

    from ui.modelos_qml import _UiQueryWorker

    worker = _UiQueryWorker()
    recibido: dict = {}

    def _func():
        raise RuntimeError("boom")

    def _aplicar(res):
        recibido["valor"] = res

    worker.run(_func, _aplicar)

    assert recibido["valor"] is None


def test_ui_worker_run_sync_applier_excepcion_no_propaga():
    """Si el applier crashea, el worker debe loggear y seguir."""
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QCoreApplication
    _app = QCoreApplication.instance() or QCoreApplication([])

    from ui.modelos_qml import _UiQueryWorker

    worker = _UiQueryWorker()

    def _func():
        return 42

    def _aplicar(_):
        raise RuntimeError("aplicador roto")

    # No debe propagar la excepción al caller.
    worker.run(_func, _aplicar)


def test_modelo_estadisticas_cargar_aplica_via_worker(monkeypatch, tmp_path):
    """ModeloEstadisticas.cargar() ahora corre las queries en _UiQueryWorker.

    Con el modo sync forzado en tests, los datos quedan aplicados
    inmediatamente y la lista debe reflejar el contenido devuelto.
    """
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication
    _app = QGuiApplication.instance() or QGuiApplication([])

    from ui import modelos_qml

    monkeypatch.setattr(modelos_qml.svc_bib, "estadisticas_generales", lambda: {"total_pistas": 99})
    monkeypatch.setattr(modelos_qml.svc_bib, "pistas_recientes",                  lambda *, limite, **_: [{"id": 1, "portada_ruta": ""}])
    monkeypatch.setattr(modelos_qml.svc_bib, "albums_recientes",                  lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "artistas_recientes",                lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "pistas_mas_escuchadas",             lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "albums_mas_escuchados",             lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "artistas_mas_escuchados",           lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "playlists_mas_escuchadas",          lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "pistas_para_volver",                lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "playlists_destacadas",              lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "albums_con_canciones_que_gustan",   lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "recomendaciones_inicio",            lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "pistas_nunca_escuchadas",           lambda *, limite, **_: [], raising=False)
    monkeypatch.setattr(modelos_qml.svc_bib, "pistas_menos_escuchadas",           lambda *, limite, **_: [], raising=False)
    monkeypatch.setattr(modelos_qml.svc_bib, "estadisticas_extras_perfil",        lambda: {"ok": True}, raising=False)

    modelo = modelos_qml.ModeloEstadisticas()
    modelo.cargar()

    assert modelo.resumen.get("total_pistas") == 99
    assert modelo.recientes_canciones.total == 1
    assert modelo.estadisticas_perfil == {"ok": True}


def test_modelo_estadisticas_resiliente_si_perfil_falla(monkeypatch):
    """estadisticas_extras_perfil con error -> perfil vacío, resto OK."""
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication
    _app = QGuiApplication.instance() or QGuiApplication([])

    from ui import modelos_qml

    monkeypatch.setattr(modelos_qml.svc_bib, "estadisticas_generales", lambda: {"total_pistas": 1})
    for nombre in (
        "pistas_recientes", "albums_recientes", "artistas_recientes",
        "pistas_mas_escuchadas", "albums_mas_escuchados", "artistas_mas_escuchados",
        "playlists_mas_escuchadas", "pistas_para_volver", "playlists_destacadas",
        "albums_con_canciones_que_gustan", "recomendaciones_inicio",
        "pistas_nunca_escuchadas", "pistas_menos_escuchadas",
    ):
        monkeypatch.setattr(modelos_qml.svc_bib, nombre, lambda *, limite, **_: [], raising=False)

    def _crash():
        raise RuntimeError("perfil falló")

    monkeypatch.setattr(modelos_qml.svc_bib, "estadisticas_extras_perfil", _crash, raising=False)

    modelo = modelos_qml.ModeloEstadisticas()
    modelo.cargar()

    assert modelo.estadisticas_perfil == {}
    assert modelo.resumen.get("total_pistas") == 1


def test_modelo_karaoke_detectar_backend_async(monkeypatch):
    """detectar_backend usa _UiQueryWorker → no bloquea la UI."""
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication
    _app = QGuiApplication.instance() or QGuiApplication([])

    from ui import modelos_qml

    diag_falso = {
        "demucs_disponible": True, "demucs_version": "4.0.0",
        "torch_disponible": True, "torch_version": "2.0.0",
        "ffmpeg_disponible": True, "ffmpeg_version": "6.0",
        "device_disponible": "cpu", "devices_soportados": ["cpu"],
        "backend_listo": True, "mensaje": "ok", "instrucciones": "",
    }

    import servicios.karaoke as karaoke_mod
    monkeypatch.setattr(karaoke_mod, "diagnostico", lambda: dict(diag_falso))

    m = modelos_qml.ModeloKaraoke()
    m.detectar_backend()

    assert m.backend_diag.get("backend_listo") is True
    assert m.backend_diag.get("mensaje") == "ok"


def test_modelo_karaoke_iniciar_procesamiento_no_arranca_si_backend_no_listo(monkeypatch):
    """iniciar_procesamiento encadena detectar_backend→worker. Si el
    backend no está listo, no debe arrancar el WorkerKaraokeCola.
    """
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication
    _app = QGuiApplication.instance() or QGuiApplication([])

    from ui import modelos_qml

    diag_no_listo = {
        "demucs_disponible": False, "demucs_version": "",
        "torch_disponible": False, "torch_version": "",
        "ffmpeg_disponible": True, "ffmpeg_version": "6.0",
        "device_disponible": "cpu", "devices_soportados": ["cpu"],
        "backend_listo": False, "mensaje": "Falta torch", "instrucciones": "pip install torch",
    }
    import servicios.karaoke as karaoke_mod
    monkeypatch.setattr(karaoke_mod, "diagnostico", lambda: dict(diag_no_listo))

    m = modelos_qml.ModeloKaraoke()
    m.iniciar_procesamiento()

    # Snap debe quedar en estado de error.
    assert m.estado_proceso == "error"
    assert m.snap_proceso.get("error_codigo") == "backend_no_disponible"
    assert m._worker is None


def test_modelo_dj_expone_prewarm_hook():
    """ModeloDjPrivado debe exponer el método de pre-warm de imports."""
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication
    _app = QGuiApplication.instance() or QGuiApplication([])

    from ui.modelos_qml import ModeloDjPrivado
    from servicios.reproductor import Reproductor

    rep = Reproductor()
    try:
        modelo = ModeloDjPrivado(rep)
        assert hasattr(modelo, "_prewarm_dj_imports"), \
            "ModeloDjPrivado debe exponer _prewarm_dj_imports"
        # El init debió disparar QTimer.singleShot(1500, ...). El hilo aún no
        # se construyó porque el timer no ha disparado.
        # Lo llamamos manualmente y verificamos que arranca un QThread.
        modelo._prewarm_dj_imports()
        assert modelo._prewarm_thread is not None
        # Esperamos que termine para no dejar threads colgados en la suite.
        modelo._prewarm_thread.wait(5000)
    finally:
        try:
            rep.cerrar()
        except Exception:
            pass


def test_modelo_dj_prewarm_solo_lanza_una_vez():
    """Llamar _prewarm_dj_imports dos veces no debe duplicar el hilo."""
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication
    _app = QGuiApplication.instance() or QGuiApplication([])

    from ui.modelos_qml import ModeloDjPrivado
    from servicios.reproductor import Reproductor

    rep = Reproductor()
    try:
        modelo = ModeloDjPrivado(rep)
        modelo._prewarm_dj_imports()
        hilo_a = modelo._prewarm_thread
        modelo._prewarm_dj_imports()
        hilo_b = modelo._prewarm_thread
        assert hilo_a is hilo_b
        if hilo_a is not None:
            hilo_a.wait(5000)
    finally:
        try:
            rep.cerrar()
        except Exception:
            pass


def test_modelo_playlists_sincronizar_async(monkeypatch):
    """sincronizar_inteligentes_async ejecuta vía _UiQueryWorker y refresca."""
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication
    _app = QGuiApplication.instance() or QGuiApplication([])

    from ui import modelos_qml

    llamadas: list[str] = []

    monkeypatch.setattr(
        modelos_qml.svc_bib, "sincronizar_playlists_sistema",
        lambda lim: llamadas.append(f"sync({lim})") or {"creadas": 0, "actualizadas": 0},
    )
    monkeypatch.setattr(
        modelos_qml.svc_bib, "listar_playlists",
        lambda *a, **k: llamadas.append("listar") or [],
    )

    modelo = modelos_qml.ModeloPlaylists()
    modelo.sincronizar_inteligentes_async(0)

    assert any(c.startswith("sync(") for c in llamadas), \
        "sincronizar_playlists_sistema debe invocarse vía worker"
