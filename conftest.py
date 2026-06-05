# =============================================================================
# conftest.py (raíz del proyecto)
#
# Activa el aislamiento por proceso de los tests (pytest-forked) al correr el
# suite COMPLETO en POSIX. Las fixtures de la suite están en tests/conftest.py.
# =============================================================================

import os
import sys


def _debe_forkear(config) -> bool:
    """¿Conviene ejecutar cada test en su propio proceso?

    Acumular librerías nativas pesadas (torch, essentia, cuda…) junto con Qt en
    un único proceso de pytest provoca un fallo de segmentación a mitad del
    suite (problema pre-existente; reordenar los tests lo mitiga pero no lo
    resuelve). Forkear cada test da un proceso limpio por test y lo elimina.

    Solo se activa cuando:
      * Estamos en POSIX (en Windows no hay `os.fork`; allí pytest-forked no
        aplica y, además, essentia no tiene wheel, así que el crash no se da).
      * Se ejecuta el suite COMPLETO (sin seleccionar archivos/tests concretos),
        para no estorbar la depuración puntual con `-s`/pdb.
      * No está el escape `NB_SOUND_TEST_NO_FORK=1`.
    """
    if sys.platform == "win32":
        return False
    if os.environ.get("NB_SOUND_TEST_NO_FORK"):
        return False
    try:
        crudos = list(getattr(config.invocation_params, "args", ()) or ())
    except Exception:
        crudos = []

    def _es_target(a: str) -> bool:
        if a.startswith("-"):
            return False
        return "::" in a or a.endswith(".py") or os.path.exists(a)

    if any(_es_target(a) for a in crudos):
        return False
    try:
        import pytest_forked  # noqa: F401
    except Exception:
        return False
    return True


def pytest_configure(config):
    if not _debe_forkear(config):
        return
    # pytest-forked ejecuta cada test en un fork cuando `--forked` está activo.
    # Fijamos su opción programáticamente (equivale a pasar `--forked`).
    try:
        if not config.getoption("forked", default=False):
            config.option.forked = True
    except Exception:
        pass
