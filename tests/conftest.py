# =============================================================================
# tests/conftest.py
#
# Shared fixtures for the test suite.
#
# The autouse fixture ``_patch_pipeline_dirs`` ensures that any test
# instantiating PipelineCatalogacion does not attempt to create directories
# on the real filesystem (which may be read-only in CI/sandbox).
# =============================================================================

import os
import pytest


# Fijar QT_QPA_PLATFORM=offscreen globalmente para toda la suite,
# ANTES de que cualquier test cree una QApplication. Esto evita
# segfaults por inicialización inconsistente del backend de Qt cuando
# tests que crean QObjects corren en distinto orden.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QML_DISABLE_DISK_CACHE", "1")
# Forzar el modo síncrono del `_UiQueryWorker` durante tests.
# En producción el worker corre queries pesadas en un QThread separado
# para que la UI no se congele. En tests no podemos depender del orden
# de la cola de eventos de Qt: ejecutamos `func` y `applier` en el hilo
# actual para que los assert que siguen a `modelo.cargar()` vean el
# estado ya aplicado.
os.environ.setdefault("NB_SOUND_UI_WORKER_SYNC", "1")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: tests que descargan modelos o hacen procesamiento real "
        "(se ejecutan con NB_SOUND_RUN_SLOW_TESTS=1)",
    )


def pytest_collection_modifyitems(items):
    """Reordena la suite para que los tests con motores QML pesados se ejecuten
    ANTES de los tests de servicio/modelo que dejan estado en la cola Qt.

    test_reproductor_ui_contract.py y test_ui_configuracion_runtime.py llaman a
    app.exec() y son sensibles a eventos pendientes de workers de otros tests.
    Ejecutarlos primero (mientras la cola de eventos Qt está limpia) evita los
    segfaults que ocurren cuando corren después de karaoke + playlists.
    """
    _SUFIJOS_PRIMERO = (
        "test_reproductor_ui_contract.py",
        "test_ui_configuracion_runtime.py",
    )
    primeros = [i for i in items if     any(s in str(i.fspath) for s in _SUFIJOS_PRIMERO)]
    resto    = [i for i in items if not any(s in str(i.fspath) for s in _SUFIJOS_PRIMERO)]
    items[:] = primeros + resto


@pytest.fixture(autouse=True)
def _patch_pipeline_dirs(tmp_path, monkeypatch):
    """Redirect module-level directory constants used by the pipeline.

    ``core.pipeline`` and ``core.enrichment_pipeline`` do
    ``from config.settings import DEFAULT_ASSETS_DIR`` at import time.
    Monkeypatching ``config.settings`` alone is insufficient because
    the reference is already copied at import time. We must patch the
    module-level symbols in every module that re-exports them.
    """
    import importlib

    modules_to_patch = []
    for mod_name in ("core.pipeline", "core.enrichment_pipeline"):
        try:
            mod = importlib.import_module(mod_name)
            modules_to_patch.append(mod)
        except Exception:
            pass

    for mod in modules_to_patch:
        for attr in ("DEFAULT_ASSETS_DIR", "DEFAULT_MANIFESTS_DIR"):
            if hasattr(mod, attr):
                monkeypatch.setattr(mod, attr, tmp_path)
