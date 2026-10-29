# =============================================================================
# tests/test_modelos_essentia.py
#
# Verifica el catálogo y la lógica de verificación de
# `infra.modelos_essentia`. La descarga real no se ejerce: usa servidor
# remoto y haría tests lentos / dependientes de red.
# =============================================================================

from __future__ import annotations

from pathlib import Path

import pytest


def test_catalogo_tiene_11_modelos():
    """El catálogo expone los 11 modelos que NB Sound consume realmente.

    Si en el futuro se agrega o quita un modelo, este test debe actualizarse
    explícitamente — sirve como recordatorio de mantener el catálogo en
    sincronía con el pipeline.
    """
    from infra.modelos_essentia import CATALOGO
    assert len(CATALOGO) == 11
    ids = {m.archivo_pb for m in CATALOGO}
    esperados = {
        "msd-musicnn-1.pb",
        "discogs-effnet-bs64-1.pb",
        "audioset-vggish-3.pb",
        "genre_discogs400-discogs-effnet-1.pb",
        "danceability-msd-musicnn-1.pb",
        "deam-msd-musicnn-2.pb",
        "mood_aggressive-msd-musicnn-1.pb",
        "mood_happy-msd-musicnn-1.pb",
        "mood_party-msd-musicnn-1.pb",
        "mood_relaxed-msd-musicnn-1.pb",
        "mood_sad-msd-musicnn-1.pb",
    }
    assert ids == esperados


def test_cada_modelo_tiene_metadata_json():
    """Cada `.pb` debe declarar su `.json` de metadata: Essentia requiere
    el JSON para mapear índices de salida a etiquetas.
    """
    from infra.modelos_essentia import CATALOGO
    for m in CATALOGO:
        assert m.archivo_json.endswith(".json")
        assert m.archivo_pb.replace(".pb", ".json") == m.archivo_json


def test_verificar_carpeta_inexistente_devuelve_todo_faltante(tmp_path):
    """Si la carpeta no existe, `verificar` reporta TODO el catálogo como
    faltante (no None, no excepción). La UI lee este resultado para mostrar
    el botón "Descargar modelos"."""
    from infra import modelos_essentia as _me
    estado = _me.verificar(tmp_path / "no_existe")
    assert estado.completo is False
    assert len(estado.faltantes) == _me.verificar.__globals__["CATALOGO"].__len__()  # tipo: ignore


def test_verificar_carpeta_completa(tmp_path):
    """Si todos los .pb están en disco, estado.completo es True."""
    from infra.modelos_essentia import CATALOGO, verificar
    for modelo in CATALOGO:
        (tmp_path / modelo.archivo_pb).write_bytes(b"\x00\x01\x02")
    estado = verificar(tmp_path)
    assert estado.completo is True
    assert estado.faltantes == []
    assert set(estado.presentes) == {m.archivo_pb for m in CATALOGO}


def test_verificar_descarta_archivos_vacios(tmp_path):
    """Un .pb de 0 bytes NO debe contar como presente (descarga interrumpida)."""
    from infra.modelos_essentia import CATALOGO, verificar
    for modelo in CATALOGO:
        (tmp_path / modelo.archivo_pb).touch()  # tamaño 0
    estado = verificar(tmp_path)
    assert estado.completo is False
    assert len(estado.faltantes) == len(CATALOGO)


def test_carpeta_actual_lee_settings(tmp_path, monkeypatch):
    """`carpeta_actual()` debe respetar settings.AUDIO_INTELLIGENCE_MODEL_DIR
    cuando se establece (igual a lo que pasa al guardar Configuración).
    """
    from config import settings as _settings
    from infra.modelos_essentia import carpeta_actual
    monkeypatch.setattr(_settings, "AUDIO_INTELLIGENCE_MODEL_DIR", str(tmp_path))
    assert carpeta_actual() == tmp_path.resolve()


def test_carpeta_actual_fallback_a_assets(tmp_path, monkeypatch):
    """Si el usuario no configuró model_dir, fallback a
    `<DEFAULT_ASSETS_DIR>/modelos_essentia`. Sirve para que la UI ofrezca
    un destino sensato incluso en una instalación recién hecha.
    """
    from config import settings as _settings
    from infra.modelos_essentia import carpeta_actual
    monkeypatch.setattr(_settings, "AUDIO_INTELLIGENCE_MODEL_DIR", "")
    monkeypatch.setattr(_settings, "DEFAULT_ASSETS_DIR", tmp_path)
    assert carpeta_actual() == (tmp_path / "modelos_essentia").resolve()
