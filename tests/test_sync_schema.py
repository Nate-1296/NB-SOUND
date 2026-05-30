# =============================================================================
# tests/test_sync_schema.py
#
# Cubre el BLOQUE 1 del plan de ecosistema movil:
#   - 1.1: las tablas y columnas de sync se crean en BD nueva y migran sin
#          error sobre una BD "v1.0.x" preexistente (solo aditivo).
#   - 1.2: el incremento de `sync_version` sube de forma monotonica al
#          modificar una pista, y un borrado deja un tombstone.
# =============================================================================

import sqlite3
from pathlib import Path

import pytest

from db import esquema
from db.conexion import (
    cerrar_db,
    get_conexion,
    inicializar_db,
    marcar_sync_version,
    registrar_tombstone,
    siguiente_sync_version,
    sync_version_actual,
)
from servicios import biblioteca as svc_bib


@pytest.fixture()
def db_sync(tmp_path):
    inicializar_db(tmp_path / "sync.sqlite3")
    try:
        yield tmp_path
    finally:
        cerrar_db()


def _columnas(tabla: str) -> set[str]:
    return {fila["name"] for fila in get_conexion().execute(f"PRAGMA table_info({tabla})").fetchall()}


def _tablas() -> set[str]:
    return {
        fila["name"]
        for fila in get_conexion().execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _crear_pista(titulo: str = "Cancion", ruta: str = "/musica/x.mp3") -> int:
    con = get_conexion()
    cur = con.execute(
        """
        INSERT INTO pistas(titulo, artista_nombre, album_titulo, ruta_archivo, nombre_archivo)
        VALUES (?, 'Artista', 'Album', ?, 'x.mp3')
        """,
        (titulo, ruta),
    )
    return cur.lastrowid


# ── 1.1 — Tablas y columnas ──────────────────────────────────────────────────

def test_tablas_de_sync_existen(db_sync):
    tablas = _tablas()
    for esperada in ("sync_dispositivos", "sync_tombstones", "sync_stem_transfers", "sync_estado"):
        assert esperada in tablas


def test_columnas_sync_version_existen(db_sync):
    assert "sync_version" in _columnas("pistas")
    assert "favorita_actualizada_en" in _columnas("pistas")
    assert "sync_version" in _columnas("albums")
    assert "sync_version" in _columnas("artistas")
    assert "sync_version" in _columnas("playlists")


def test_migracion_sobre_bd_existente_v1(tmp_path):
    """Una BD creada con un esquema 'viejo' (sin columnas de sync) debe migrar
    de forma idempotente al abrirla con inicializar_db, sin perder datos."""
    ruta = tmp_path / "vieja.sqlite3"

    # Construir una BD al estilo v1.0.x: tabla pistas con las columnas que ya
    # existian entonces (album_id, artista_id, estado, hash...) pero SIN las
    # columnas de sync. Asi se valida que la migracion aditiva las agrega.
    con = sqlite3.connect(str(ruta))
    con.execute(
        """
        CREATE TABLE pistas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            album_id INTEGER,
            artista_id INTEGER,
            titulo TEXT NOT NULL,
            artista_nombre TEXT NOT NULL DEFAULT '',
            album_titulo TEXT NOT NULL DEFAULT '',
            ruta_archivo TEXT NOT NULL UNIQUE,
            nombre_archivo TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'biblioteca',
            hash_sha256 TEXT,
            favorita INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    con.execute(
        "INSERT INTO pistas(titulo, ruta_archivo, nombre_archivo) VALUES ('Vieja', '/m/v.mp3', 'v.mp3')"
    )
    con.commit()
    con.close()

    inicializar_db(ruta)
    try:
        cols = _columnas("pistas")
        assert "sync_version" in cols
        assert "favorita_actualizada_en" in cols
        # El dato preexistente sigue ahi.
        fila = get_conexion().execute("SELECT titulo, sync_version FROM pistas").fetchone()
        assert fila["titulo"] == "Vieja"
        assert fila["sync_version"] == 0
        assert "sync_dispositivos" in _tablas()
    finally:
        cerrar_db()


# ── 1.2 — Incremento de sync_version y tombstones ────────────────────────────

def test_siguiente_sync_version_es_monotonica(db_sync):
    v1 = siguiente_sync_version()
    v2 = siguiente_sync_version()
    v3 = siguiente_sync_version()
    assert v1 >= 1
    assert v2 == v1 + 1
    assert v3 == v2 + 1
    assert sync_version_actual() == v3


def test_marcar_sync_version_sube_la_de_la_entidad(db_sync):
    pista_id = _crear_pista()
    antes = get_conexion().execute(
        "SELECT sync_version FROM pistas WHERE id = ?", (pista_id,)
    ).fetchone()["sync_version"]
    nueva = marcar_sync_version("pistas", pista_id)
    despues = get_conexion().execute(
        "SELECT sync_version FROM pistas WHERE id = ?", (pista_id,)
    ).fetchone()["sync_version"]
    assert despues == nueva
    assert despues > antes


def test_marcar_sync_version_rechaza_tabla_no_whitelisted(db_sync):
    with pytest.raises(ValueError):
        marcar_sync_version("config_ui", 1)


def test_toggle_favorita_incrementa_sync_version_y_sella_timestamp(db_sync):
    pista_id = _crear_pista()
    version_inicial = get_conexion().execute(
        "SELECT sync_version FROM pistas WHERE id = ?", (pista_id,)
    ).fetchone()["sync_version"]

    nuevo = svc_bib.toggle_favorita(pista_id)
    assert nuevo is True

    fila = get_conexion().execute(
        "SELECT favorita, sync_version, favorita_actualizada_en FROM pistas WHERE id = ?",
        (pista_id,),
    ).fetchone()
    assert fila["favorita"] == 1
    assert fila["sync_version"] > version_inicial
    assert fila["favorita_actualizada_en"]  # timestamp no vacio


def test_registrar_tombstone_deja_fila(db_sync):
    pista_id = _crear_pista()
    version = registrar_tombstone("pista", pista_id)
    fila = get_conexion().execute(
        "SELECT entidad, entidad_id, sync_version FROM sync_tombstones WHERE entidad_id = ?",
        (pista_id,),
    ).fetchone()
    assert fila["entidad"] == "pista"
    assert fila["entidad_id"] == pista_id
    assert fila["sync_version"] == version


def test_registrar_tombstone_rechaza_entidad_invalida(db_sync):
    with pytest.raises(ValueError):
        registrar_tombstone("config", 1)
