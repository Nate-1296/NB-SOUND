# =============================================================================
# tests/test_rutas_lazy_settings.py
#
# Verifica que el refactor de A.1 / A.1.3 sea correcto:
#
#   * Los servicios consumen `settings.DEFAULT_*_DIR` en runtime (no
#     copia local al importar). Sobrescribir el atributo del módulo se
#     ve reflejado en la siguiente llamada.
#   * `_aplicar_rutas_persistidas_a_settings()` toma los valores de
#     `config_ui` y los vuelca a `config.settings.DEFAULT_*_DIR`.
# =============================================================================

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _aislar_db(tmp_path):
    from db import conexion
    conexion._conexion = None
    conexion.inicializar_db(tmp_path / "config.sqlite3")
    yield
    try:
        conexion.cerrar_db()
    except Exception:
        pass


def test_backend_audit_lee_assets_dir_dinamico(tmp_path):
    """`DoctorBiblioteca` debe leer settings.DEFAULT_ASSETS_DIR cada vez que
    se instancia, no quedarse con el valor que tenía el módulo al importarse.
    """
    from config import settings
    from core.audit import DoctorBiblioteca

    nuevo_assets = tmp_path / "assets_test"
    nuevo_assets.mkdir()
    original = settings.DEFAULT_ASSETS_DIR
    try:
        settings.DEFAULT_ASSETS_DIR = nuevo_assets
        doc = DoctorBiblioteca(library_dir=tmp_path / "lib",
                                processed_dir=tmp_path / "proc")
        assert doc._assets == nuevo_assets
    finally:
        settings.DEFAULT_ASSETS_DIR = original


def test_backend_manifests_lee_manifests_dir_dinamico(tmp_path):
    """Idem para GestorManifests con DEFAULT_MANIFESTS_DIR."""
    from config import settings
    from core.manifests import GestorManifests

    nuevo = tmp_path / "manifests_test"
    original = settings.DEFAULT_MANIFESTS_DIR
    try:
        settings.DEFAULT_MANIFESTS_DIR = nuevo
        g = GestorManifests()
        assert g._base == nuevo
        assert (nuevo / "tracks").is_dir()
    finally:
        settings.DEFAULT_MANIFESTS_DIR = original


def test_aplicar_rutas_persistidas_vuelca_a_settings(tmp_path):
    """Tras `_aplicar_rutas_persistidas_a_settings`, las claves dir_* de
    config_ui deben aparecer en `config.settings`.
    """
    from db.conexion import guardar_config
    from config import settings
    from main_ui import _aplicar_rutas_persistidas_a_settings

    dir_assets = tmp_path / "mis_assets"
    dir_cache = tmp_path / "mi_cache"
    guardar_config("dir_assets", str(dir_assets))
    guardar_config("dir_cache", str(dir_cache))

    original_assets = settings.DEFAULT_ASSETS_DIR
    original_cache = settings.DEFAULT_CACHE_DIR
    try:
        _aplicar_rutas_persistidas_a_settings()
        assert settings.DEFAULT_ASSETS_DIR == dir_assets.resolve()
        assert settings.DEFAULT_CACHE_DIR == dir_cache.resolve()
    finally:
        settings.DEFAULT_ASSETS_DIR = original_assets
        settings.DEFAULT_CACHE_DIR = original_cache


def test_aplicar_rutas_ignora_claves_vacias(tmp_path):
    """Si una clave dir_* está vacía o no existe en BD, el atributo
    correspondiente NO debe pisarse con None."""
    from db.conexion import guardar_config
    from config import settings
    from main_ui import _aplicar_rutas_persistidas_a_settings

    guardar_config("dir_assets", "")  # vacío
    valor_previo = settings.DEFAULT_ASSETS_DIR
    _aplicar_rutas_persistidas_a_settings()
    assert settings.DEFAULT_ASSETS_DIR == valor_previo
