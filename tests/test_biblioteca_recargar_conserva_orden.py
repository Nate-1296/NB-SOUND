# =============================================================================
# tests/test_biblioteca_recargar_conserva_orden.py
#
# Issue: al eliminar una pista (o cualquier refresco global vía recargar()),
# la lista de pistas volvía a "Título A-Z" aunque el usuario tuviera otro
# orden/filtro activo. ModeloBiblioteca.recargar() debe reusar los últimos
# parámetros con los que se listaron las pistas, no los valores por defecto.
# =============================================================================

import pytest

from db.conexion import cerrar_db, inicializar_db

pytest.importorskip("PySide6")
from PySide6.QtGui import QGuiApplication  # noqa: E402

from servicios import biblioteca as svc_bib  # noqa: E402
from ui.modelos_qml import ModeloBiblioteca  # noqa: E402


@pytest.fixture()
def app():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture()
def db(tmp_path):
    inicializar_db(tmp_path / "bib_recargar.sqlite3")
    try:
        yield tmp_path
    finally:
        cerrar_db()


def test_recargar_conserva_orden_y_filtro_de_pistas(app, db, monkeypatch):
    llamadas = []

    def _fake_listar_pistas(filtro_texto="", solo_favoritas=False, orden="titulo", limite=None):
        llamadas.append((filtro_texto, bool(solo_favoritas), orden))
        return []

    monkeypatch.setattr(svc_bib, "listar_pistas", _fake_listar_pistas)

    modelo = ModeloBiblioteca(parent=None)
    # El usuario está viendo favoritas ordenadas por artista, filtrando "rock".
    modelo.cargar_pistas("rock", True, "artista")
    assert llamadas[-1] == ("rock", True, "artista")

    # Un refresco global (p.ej. tras eliminar una pista) NO debe revertir a
    # los valores por defecto: la última carga conserva orden/filtro activos.
    modelo.recargar()
    assert llamadas[-1] == ("rock", True, "artista")
