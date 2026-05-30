# =============================================================================
# tests/test_deep_analytics_windows.py
#
# Fase 3 — UI condicional por plataforma.
#
# En Windows `essentia-tensorflow` no tiene wheel funcional, por lo que toda
# la UI de análisis profundo (deep) debe ocultarse. La condición se evalúa
# una sola vez desde `sys.platform` y se expone:
#   * como helper puro `infra.dependencias.deep_analytics_disponible()`,
#   * como propiedad `ModeloDependencias.deepAnalyticsDisponible`,
#   * (en runtime) como context property global homónima en main_ui.
#
# Estos tests NO requieren la plataforma real: fuerzan `sys.platform` con
# monkeypatch para validar el comportamiento determinista en cada SO.
# =============================================================================

from __future__ import annotations

import sys

import pytest


# -----------------------------------------------------------------------------
# Helper puro de plataforma (sin Qt ni BD)
# -----------------------------------------------------------------------------

def test_helper_false_en_windows(monkeypatch):
    """En Windows el análisis deep no está disponible."""
    from infra import dependencias as deps
    monkeypatch.setattr(sys, "platform", "win32")
    assert deps.deep_analytics_disponible() is False


def test_helper_true_en_linux_y_macos(monkeypatch):
    """En Linux y macOS el comportamiento no cambia: deep disponible."""
    from infra import dependencias as deps
    monkeypatch.setattr(sys, "platform", "linux")
    assert deps.deep_analytics_disponible() is True
    monkeypatch.setattr(sys, "platform", "darwin")
    assert deps.deep_analytics_disponible() is True


def test_ids_deep_son_essentia_y_modelos():
    """Los IDs filtrables en Windows son exactamente las dos deps deep."""
    from infra.dependencias import IDS_DEPENDENCIAS_DEEP
    assert set(IDS_DEPENDENCIAS_DEEP) == {"essentia_tensorflow", "modelos_essentia"}


# -----------------------------------------------------------------------------
# ModeloDependencias: filtrado + propiedad (requiere Qt + BD aislada)
# -----------------------------------------------------------------------------

@pytest.fixture
def _aislar_db(tmp_path):
    """BD de config_ui aislada en sqlite temporal (mismo patrón que la suite)."""
    from db import conexion
    db_path = tmp_path / "config.sqlite3"
    conexion.inicializar_db(db_path)
    yield
    try:
        conexion.cerrar_db()
    except Exception:
        pass


def _catalogo_fake(deps):
    """Catálogo mínimo con una requerida OK, una opcional OK y las dos deep."""
    return [
        deps.Dependencia(
            id="vlc", nombre="VLC", descripcion="", tipo=deps.TipoDependencia.SISTEMA,
            requerida=True, funciones_que_habilita=[], verificador=lambda: (True, "3.0"),
        ),
        deps.Dependencia(
            id="torch", nombre="PyTorch", descripcion="", tipo=deps.TipoDependencia.PIP,
            requerida=False, funciones_que_habilita=[], verificador=lambda: (True, "2.0"),
        ),
        deps.Dependencia(
            id="essentia_tensorflow", nombre="essentia-tensorflow", descripcion="",
            tipo=deps.TipoDependencia.PIP, requerida=False, funciones_que_habilita=[],
            verificador=lambda: (False, ""),
        ),
        deps.Dependencia(
            id="modelos_essentia", nombre="Modelos Essentia (.pb)", descripcion="",
            tipo=deps.TipoDependencia.MODELOS, requerida=False, funciones_que_habilita=[],
            verificador=lambda: (False, ""),
        ),
    ]


def test_modelo_oculta_deps_deep_en_windows(_aislar_db, monkeypatch):
    """En Windows, ModeloDependencias no expone essentia ni modelos, su
    propiedad deepAnalyticsDisponible es False y `faltanOpcionales` no se
    dispara por las deps deep faltantes (estado global puede ser "todo OK").
    """
    pytest.importorskip("PySide6.QtCore")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication
    QGuiApplication.instance() or QGuiApplication([])

    from infra import dependencias as deps
    monkeypatch.setattr(deps, "construir_catalogo", lambda: _catalogo_fake(deps))
    # Parcheamos directamente la fuente de verdad (el helper) en vez de
    # `sys.platform`: forzar "win32" en un host Linux rompe `shutil.which`
    # (CPython lo enruta a `_winapi`, inexistente fuera de Windows) en ramas
    # ajenas a lo que probamos. La conducta por plataforma del helper ya está
    # cubierta por `test_helper_false_en_windows`.
    monkeypatch.setattr(deps, "deep_analytics_disponible", lambda: False)

    from ui.modelos_qml import ModeloDependencias
    modelo = ModeloDependencias()

    ids = {r.get("id") for r in modelo.estado}
    assert "essentia_tensorflow" not in ids
    assert "modelos_essentia" not in ids
    assert "vlc" in ids and "torch" in ids  # el resto del catálogo intacto

    assert modelo.deepAnalyticsDisponible is False
    # torch (opcional) está OK; essentia/modelos (las únicas faltantes) se
    # filtraron -> no quedan opcionales faltantes.
    assert modelo.faltanOpcionales is False
    assert modelo.faltanRequeridas is False


def test_modelo_muestra_deps_deep_en_linux(_aislar_db, monkeypatch):
    """En Linux el comportamiento no cambia: las deps deep siguen visibles."""
    pytest.importorskip("PySide6.QtCore")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication
    QGuiApplication.instance() or QGuiApplication([])

    from infra import dependencias as deps
    monkeypatch.setattr(deps, "construir_catalogo", lambda: _catalogo_fake(deps))
    monkeypatch.setattr(deps, "deep_analytics_disponible", lambda: True)

    from ui.modelos_qml import ModeloDependencias
    modelo = ModeloDependencias()

    ids = {r.get("id") for r in modelo.estado}
    assert "essentia_tensorflow" in ids
    assert "modelos_essentia" in ids
    assert modelo.deepAnalyticsDisponible is True
    # essentia y modelos están FALTANTE en este catálogo fake -> sí faltan opcionales.
    assert modelo.faltanOpcionales is True
