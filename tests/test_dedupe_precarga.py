# =============================================================================
# tests/test_dedupe_precarga.py
#
# Verifica que `GestorDuplicados` precarga desde la BD al construirse,
# para que una corrida que repite archivos ya en biblioteca los detecte
# como duplicados aunque la corrida anterior haya sido cancelada.
# =============================================================================

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _bd_aislada(tmp_path):
    from db import conexion
    conexion._conexion = None
    conexion.inicializar_db(tmp_path / "config.sqlite3")
    yield
    try:
        conexion.cerrar_db()
    except Exception:
        pass


def _insertar_pista(hash_sha256: str, ruta: str, *, recording_id: str = "", isrc: str = "") -> int:
    """Inserta una fila de pista con hash + metadata mínima."""
    from db.conexion import ejecutar_y_obtener_id
    return ejecutar_y_obtener_id(
        "INSERT INTO pistas (titulo, artista_nombre, album_titulo, "
        "ruta_archivo, nombre_archivo, hash_sha256, mb_recording_id, isrc, estado) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("Test", "TestArtist", "TestAlbum", ruta,
         "test.mp3", hash_sha256, recording_id, isrc, "biblioteca"),
    )


def test_dedupe_precarga_hashes_existentes():
    """Al construir GestorDuplicados, los hashes de la BD deben estar en
    `_por_hash`, para que `registrar_hash` detecte duplicado contra ellos."""
    from core.dedupe import GestorDuplicados
    from domain.models import ArchivoAudio
    from pathlib import Path

    _insertar_pista("h_existing", "/biblio/X.mp3")

    gestor = GestorDuplicados()
    assert "h_existing" in gestor._por_hash

    archivo = ArchivoAudio(
        ruta_original=Path("/entrada/Y.mp3"),
        hash_sha256="h_existing",
    )
    resultado = gestor.registrar_hash(archivo)
    assert resultado is not None
    assert resultado.tipo == "hash_exacto"


def test_dedupe_precarga_recording_id():
    """Identidad semántica via recording_id debe poblarse desde
    pistas_metadata. Un nuevo candidato con el mismo recording_id se
    marca duplicado."""
    from core.dedupe import GestorDuplicados

    _insertar_pista("h1", "/biblio/X.mp3", recording_id="rid-12345")

    gestor = GestorDuplicados()
    assert "rid:rid-12345" in gestor._por_identidad


def test_dedupe_precarga_no_falla_con_tabla_vacia():
    """Primera ejecución (BD recién inicializada, sin pistas): no debe
    levantar excepción ni dejar estado parcial."""
    from core.dedupe import GestorDuplicados
    gestor = GestorDuplicados()
    assert gestor._por_hash == {}
    assert gestor._por_identidad == {}
