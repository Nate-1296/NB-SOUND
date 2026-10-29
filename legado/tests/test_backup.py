# =============================================================================
# tests/test_backup.py
#
# BLOQUE 5 del plan: backup automático.
#   5.1 — crear_backup genera un ZIP con db.sqlite3 + manifest + checksums.
#   5.2 — restaurar_backup sobre una BD distinta deja la biblioteca igual a
#         la del origen (incluye validación de integridad y checksums).
# =============================================================================

import json
import zipfile
from pathlib import Path

import pytest

from db.conexion import cerrar_db, get_conexion, inicializar_db
from servicios import backup as svc_backup


def _crear_pista(titulo, ruta):
    con = get_conexion()
    return con.execute(
        """
        INSERT INTO pistas(titulo, artista_nombre, album_titulo, ruta_archivo, nombre_archivo)
        VALUES (?, 'Artista', 'Album', ?, ?)
        """,
        (titulo, ruta, Path(ruta).name),
    ).lastrowid


# ── 5.1 — Exportacion ────────────────────────────────────────────────────────

def test_crear_backup_contiene_db_y_manifest(tmp_path, monkeypatch):
    inicializar_db(tmp_path / "origen.sqlite3")
    try:
        _crear_pista("Cancion 1", "/musica/1.mp3")
        _crear_pista("Cancion 2", "/musica/2.mp3")

        # Assets de ejemplo.
        assets = tmp_path / "assets"
        assets.mkdir()
        (assets / "portada.jpg").write_bytes(b"IMG-DATA")
        from config import settings
        monkeypatch.setattr(settings, "DEFAULT_ASSETS_DIR", assets, raising=False)

        destino = tmp_path / "respaldo.nbsound-backup"
        res = svc_backup.crear_backup(destino)
        assert res["ok"] is True
        assert Path(res["ruta"]).is_file()
        assert res["total_assets"] == 1

        with zipfile.ZipFile(destino, "r") as zf:
            nombres = set(zf.namelist())
            assert "db.sqlite3" in nombres
            assert "manifest.json" in nombres
            assert "assets/portada.jpg" in nombres
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            assert manifest["formato"] == "nbsound-backup"
            assert "db.sqlite3" in manifest["checksums"]
            assert "assets/portada.jpg" in manifest["checksums"]
    finally:
        cerrar_db()


def test_validar_backup_detecta_corrupcion(tmp_path):
    inicializar_db(tmp_path / "origen2.sqlite3")
    try:
        _crear_pista("Cancion", "/m/x.mp3")
        destino = tmp_path / "b.nbsound-backup"
        svc_backup.crear_backup(destino, incluir_assets=False)
    finally:
        cerrar_db()

    assert svc_backup.validar_backup(destino)["ok"] is True

    # Corromper el ZIP: reescribir la db con bytes distintos manteniendo manifest.
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(destino, "r") as zf:
        manifest = zf.read("manifest.json")
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("db.sqlite3", b"corrupto")
        zf.writestr("manifest.json", manifest)
    destino.write_bytes(buffer.getvalue())

    res = svc_backup.validar_backup(destino)
    assert res["ok"] is False
    assert "checksum" in res["error"]


# ── 5.2 — Restauracion ───────────────────────────────────────────────────────

def test_restaurar_sobre_bd_distinta_coincide(tmp_path, monkeypatch):
    # BD origen con dos pistas concretas.
    origen = tmp_path / "origen.sqlite3"
    inicializar_db(origen)
    try:
        _crear_pista("Origen A", "/m/a.mp3")
        _crear_pista("Origen B", "/m/b.mp3")
        titulos_origen = sorted(
            r["titulo"] for r in get_conexion().execute("SELECT titulo FROM pistas").fetchall()
        )
        destino_backup = tmp_path / "full.nbsound-backup"
        svc_backup.crear_backup(destino_backup, incluir_assets=False)
    finally:
        cerrar_db()

    # BD destino DISTINTA, con contenido diferente.
    destino_db = tmp_path / "destino.sqlite3"
    inicializar_db(destino_db)
    try:
        _crear_pista("Otra cosa", "/m/z.mp3")
    finally:
        cerrar_db()

    # Restaurar el backup del origen sobre la BD destino.
    res = svc_backup.restaurar_backup(destino_backup, destino_db, restaurar_assets=False)
    assert res["ok"] is True

    # La biblioteca resultante coincide con la del origen.
    inicializar_db(destino_db)
    try:
        titulos_restaurados = sorted(
            r["titulo"] for r in get_conexion().execute("SELECT titulo FROM pistas").fetchall()
        )
        assert titulos_restaurados == titulos_origen
        assert "Otra cosa" not in titulos_restaurados
    finally:
        cerrar_db()


def test_restaurar_backup_invalido_no_toca_bd(tmp_path):
    destino_db = tmp_path / "viva.sqlite3"
    inicializar_db(destino_db)
    try:
        _crear_pista("Intacta", "/m/i.mp3")
    finally:
        cerrar_db()

    falso = tmp_path / "falso.nbsound-backup"
    falso.write_bytes(b"esto no es un zip")

    res = svc_backup.restaurar_backup(falso, destino_db)
    assert res["ok"] is False

    # La BD viva sigue intacta.
    inicializar_db(destino_db)
    try:
        fila = get_conexion().execute("SELECT titulo FROM pistas").fetchone()
        assert fila["titulo"] == "Intacta"
    finally:
        cerrar_db()
