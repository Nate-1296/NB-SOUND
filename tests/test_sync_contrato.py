# =============================================================================
# tests/test_sync_contrato.py
#
# Cierre de gaps 1-3 y alineación del contrato (gap 4) con nb_sound_mobile:
#   - manifest expone sync_version_actual + bpm/energy/key planos.
#   - filtrado del manifest por selección (todo/nada/artistas/playlists).
#   - resolver de lyrics por ruta (enrichment manifest).
#   - resolver de imagen de artista por id.
# =============================================================================

import json
from pathlib import Path

import pytest

from db.conexion import cerrar_db, get_conexion, inicializar_db, marcar_sync_version
from servicios import biblioteca as svc_bib
from servicios import sync_repositorio


@pytest.fixture()
def db(tmp_path):
    inicializar_db(tmp_path / "contrato.sqlite3")
    try:
        yield tmp_path
    finally:
        cerrar_db()


def _artista(nombre):
    return get_conexion().execute(
        "INSERT INTO artistas(nombre, nombre_slug) VALUES (?, ?)", (nombre, nombre.lower())
    ).lastrowid


def _album(artista_id, titulo):
    return get_conexion().execute(
        "INSERT INTO albums(artista_id, titulo, titulo_slug) VALUES (?, ?, ?)",
        (artista_id, titulo, titulo.lower()),
    ).lastrowid


def _pista(album_id, artista_id, titulo, ruta="/m/x.mp3"):
    pid = get_conexion().execute(
        """
        INSERT INTO pistas(album_id, artista_id, titulo, artista_nombre, album_titulo,
                           ruta_archivo, nombre_archivo)
        VALUES (?, ?, ?, 'A', 'B', ?, ?)
        """,
        (album_id, artista_id, titulo, ruta, Path(ruta).name),
    ).lastrowid
    marcar_sync_version("pistas", pid)
    marcar_sync_version("albums", album_id)
    marcar_sync_version("artistas", artista_id)
    return pid


# ── Contrato (gap 4) ─────────────────────────────────────────────────────────

def test_manifest_expone_sync_version_actual_y_features_planas(db):
    art = _artista("Artista")
    alb = _album(art, "Album")
    pid = _pista(alb, art, "Tema")
    # Audio features básicas para la pista.
    get_conexion().execute(
        "INSERT INTO track_audio_features(track_id, analyzer_version, analysis_mode, analysis_status, bpm, energy, key_name) "
        "VALUES (?, 'v1', 'basic', 'ready', 120.0, 0.8, 'C')",
        (str(pid),),
    )
    m = sync_repositorio.construir_manifest(0)
    assert "sync_version_actual" in m
    assert m["sync_version_actual"] == m["sync_version"]  # alias compatible
    pista = next(p for p in m["pistas"] if p["id"] == pid)
    assert pista["bpm"] == 120.0
    assert pista["energy"] == 0.8
    assert pista["key"] == "C"
    assert "audio_features" not in pista  # ya no anidado
    assert pista["audio_url"] == f"/api/v1/track/{pid}/audio"
    assert pista["lyrics_url"] == f"/api/v1/track/{pid}/lyrics"


# ── Selección del manifest (gap 3) ───────────────────────────────────────────

def test_manifest_seleccion_artistas(db):
    a1 = _artista("Uno")
    a2 = _artista("Dos")
    alb1 = _album(a1, "Alb1")
    alb2 = _album(a2, "Alb2")
    p1 = _pista(alb1, a1, "T1", "/m/1.mp3")
    p2 = _pista(alb2, a2, "T2", "/m/2.mp3")

    m = sync_repositorio.construir_manifest(0, seleccion={"modo": "artistas", "artista_ids": [a1]})
    ids = {p["id"] for p in m["pistas"]}
    assert p1 in ids and p2 not in ids
    assert all(a["id"] == a1 for a in m["artistas"])
    assert m["playlists"] == []


def test_manifest_seleccion_nada(db):
    a = _artista("Uno")
    alb = _album(a, "Alb")
    _pista(alb, a, "T1")
    m = sync_repositorio.construir_manifest(0, seleccion={"modo": "nada"})
    assert m["pistas"] == []
    assert m["albums"] == []
    assert m["artistas"] == []
    assert m["playlists"] == []
    # La versión sigue presente para que el cliente avance el high-water mark.
    assert m["sync_version_actual"] >= 1


def test_manifest_seleccion_playlists(db):
    a = _artista("Uno")
    alb = _album(a, "Alb")
    p1 = _pista(alb, a, "T1", "/m/1.mp3")
    p2 = _pista(alb, a, "T2", "/m/2.mp3")
    pl = get_conexion().execute(
        "INSERT INTO playlists(nombre, tipo, visible) VALUES ('Mix', 'manual', 1)"
    ).lastrowid
    marcar_sync_version("playlists", pl)
    get_conexion().execute(
        "INSERT INTO pistas_playlist(playlist_id, pista_id, posicion) VALUES (?, ?, 0)", (pl, p1)
    )

    m = sync_repositorio.construir_manifest(0, seleccion={"modo": "playlists", "playlist_ids": [pl]})
    ids = {p["id"] for p in m["pistas"]}
    assert ids == {p1}  # solo la pista incluida en la playlist
    assert [pl_["id"] for pl_ in m["playlists"]] == [pl]


# ── Lyrics (gap 1) ───────────────────────────────────────────────────────────

def test_obtener_lyrics_por_ruta_lee_enrichment(db, tmp_path, monkeypatch):
    from config import settings

    assets = tmp_path / "assets"
    (assets / "enrichment").mkdir(parents=True)
    ruta_audio = "/musica/cancion.mp3"
    manifest = assets / "enrichment" / "enrichment_manifest.jsonl"
    manifest.write_text(
        json.dumps({"file": ruta_audio, "lyrics": {"plain_lyrics": "Hola mundo", "synced_lyrics": "[00:01.00] Hola"}}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "DEFAULT_ASSETS_DIR", assets, raising=False)
    # Invalidar cache de mtime entre tests.
    svc_bib._indice_lyrics_mtime = -1.0

    res = svc_bib.obtener_lyrics_por_ruta(ruta_audio)
    assert res["plain_lyrics"] == "Hola mundo"
    assert res["synced_lyrics"].startswith("[00:01.00]")

    # Sin letra para una ruta desconocida.
    vacio = svc_bib.obtener_lyrics_por_ruta("/no/existe.mp3")
    assert vacio == {"synced_lyrics": "", "plain_lyrics": ""}


# ── Imagen de artista (gap 2) ────────────────────────────────────────────────

def test_ruta_imagen_artista(db, tmp_path, monkeypatch):
    art = _artista("Daft Punk")
    # Sin avatar resoluble -> None.
    monkeypatch.setattr(svc_bib, "_resolver_avatar_artista", lambda portada, nombre: None)
    assert svc_bib.ruta_imagen_artista(art) is None

    # Con avatar que apunta a un archivo real -> devuelve la ruta.
    avatar = tmp_path / "daft.jpg"
    avatar.write_bytes(b"IMG")
    monkeypatch.setattr(svc_bib, "_resolver_avatar_artista", lambda portada, nombre: str(avatar))
    assert svc_bib.ruta_imagen_artista(art) == str(avatar)

    # Artista inexistente -> None.
    assert svc_bib.ruta_imagen_artista(99999) is None
