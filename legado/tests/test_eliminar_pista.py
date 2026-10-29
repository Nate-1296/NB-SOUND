"""Tests de la eliminación definitiva de una pista (servicios.biblioteca.eliminar_pista).

Cubre el contrato destructivo: borrado de BD (cascada + tablas sin FK + historial
+ override), borrado de archivo de audio, borrado de carátula propia, CONSERVACIÓN
de carátulas compartidas, recomposición de playlist/DJ y limpieza de manifiestos.
"""
import json
from pathlib import Path

import pytest

from db.conexion import cerrar_db, get_conexion, inicializar_db
from servicios import biblioteca as svc_bib


@pytest.fixture()
def db_eliminar(tmp_path, monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "DEFAULT_ASSETS_DIR", tmp_path / "assets")
    monkeypatch.setattr(settings, "DEFAULT_MANIFESTS_DIR", tmp_path / "manifests")
    monkeypatch.setattr(settings, "DEFAULT_PROCESSED_DIR", tmp_path / "procesados")
    (tmp_path / "assets").mkdir()
    inicializar_db(tmp_path / "eliminar.sqlite3")
    try:
        yield tmp_path
    finally:
        cerrar_db()


def _slug(t: str) -> str:
    return t.lower().replace(" ", "-")


def _crear_artista_album(artista: str, album: str, *, portada_album: str) -> tuple[int, int]:
    con = get_conexion()
    con.execute("INSERT OR IGNORE INTO artistas(nombre, nombre_slug) VALUES (?, ?)", (artista, _slug(artista)))
    artista_id = con.execute("SELECT id FROM artistas WHERE nombre = ?", (artista,)).fetchone()["id"]
    album_slug = f"{_slug(artista)}-{_slug(album)}"
    con.execute(
        "INSERT OR IGNORE INTO albums(artista_id, titulo, titulo_slug, tipo, portada_ruta) VALUES (?,?,?,'Album',?)",
        (artista_id, album, album_slug, portada_album),
    )
    album_id = con.execute(
        "SELECT id FROM albums WHERE artista_id = ? AND titulo_slug = ?", (artista_id, album_slug)
    ).fetchone()["id"]
    return artista_id, album_id


def _crear_pista(tmp_path, titulo, artista_id, album_id, artista, album, *, ruta_audio, hash_sha="") -> int:
    con = get_conexion()
    return con.execute(
        """
        INSERT INTO pistas(album_id, artista_id, titulo, artista_nombre, album_titulo,
            ruta_archivo, nombre_archivo, tamano_bytes, duracion_seg, hash_sha256,
            ultimo_acceso, estado)
        VALUES (?,?,?,?,?,?,?,?,180,?,datetime('now'),'biblioteca')
        """,
        (album_id, artista_id, titulo, artista, album, str(ruta_audio), Path(ruta_audio).name,
         Path(ruta_audio).stat().st_size if Path(ruta_audio).exists() else 0, hash_sha),
    ).lastrowid


def _escribir_manifest_assets(tmp_path, entradas: list[dict]) -> None:
    path = tmp_path / "assets" / "assets_manifest.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for e in entradas:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


def test_eliminar_pista_borra_todo_y_conserva_compartido(db_eliminar):
    tmp = db_eliminar
    con = get_conexion()

    # Dos pistas del MISMO artista; pista A en su propio álbum, pista B en otro.
    art_id, alb_a = _crear_artista_album("Artista X", "Álbum A", portada_album=str(tmp / "assets" / "albA.jpg"))
    _, alb_b = _crear_artista_album("Artista X", "Álbum B", portada_album=str(tmp / "assets" / "albB.jpg"))

    audio_a = tmp / "A.mp3"; audio_a.write_bytes(b"aaaa")
    audio_b = tmp / "B.mp3"; audio_b.write_bytes(b"bbbb")
    cover_a = tmp / "assets" / "coverA.jpg"; cover_a.write_bytes(b"ca")
    cover_b = tmp / "assets" / "coverB.jpg"; cover_b.write_bytes(b"cb")
    avatar = tmp / "assets" / "artistX.jpg"; avatar.write_bytes(b"av")  # COMPARTIDO

    pid_a = _crear_pista(tmp, "Canción A", art_id, alb_a, "Artista X", "Álbum A", ruta_audio=audio_a, hash_sha="hA")
    pid_b = _crear_pista(tmp, "Canción B", art_id, alb_b, "Artista X", "Álbum B", ruta_audio=audio_b, hash_sha="hB")

    # Manifiesto: A y B comparten artist_avatar; cada una su track_cover.
    _escribir_manifest_assets(tmp, [
        {"archivo": str(audio_a), "track_cover": str(cover_a), "artist_avatar": str(avatar)},
        {"archivo": str(audio_b), "track_cover": str(cover_b), "artist_avatar": str(avatar)},
    ])

    # Datos colaterales de A: features, vibe tags, historial, playlist, sesión DJ.
    con.execute("INSERT INTO track_audio_features(track_id, analysis_status, analyzer_version, analysis_mode) VALUES (?, 'ready', 'v1', 'light')", (str(pid_a),))
    con.execute("INSERT INTO track_vibe_tags(track_id, tag, source) VALUES (?, 'energetica', 'basic')", (str(pid_a),))
    con.execute("INSERT INTO historial(pista_id, titulo_snap, artista_snap, duracion_seg, completada) VALUES (?,?,?,180,1)",
                (pid_a, "Canción A", "Artista X"))
    con.execute("INSERT INTO overrides_catalogacion(match_type, match_value, payload_json, source) VALUES ('hash','hA','{}','manual')")

    pl_id = con.execute("INSERT INTO playlists(nombre) VALUES ('Mix')").lastrowid
    con.execute("INSERT INTO pistas_playlist(playlist_id, pista_id, posicion) VALUES (?,?,1)", (pl_id, pid_a))
    con.execute("INSERT INTO pistas_playlist(playlist_id, pista_id, posicion) VALUES (?,?,2)", (pl_id, pid_b))

    ses_id = con.execute("INSERT INTO dj_sesiones(prompt_original) VALUES ('algo')").lastrowid
    con.execute("INSERT INTO dj_pistas_sesion(sesion_id, posicion, pista_id) VALUES (?,1,?)", (ses_id, pid_a))
    con.execute("INSERT INTO dj_pistas_sesion(sesion_id, posicion, pista_id) VALUES (?,2,?)", (ses_id, pid_b))

    # --- ACCIÓN ---
    res = svc_bib.eliminar_pista(pid_a)
    assert res["ok"] is True
    assert res["album_eliminado"] is True   # Álbum A queda sin pistas
    assert res["artista_eliminado"] is False  # Artista X aún tiene la pista B

    # BD: la pista A y todo su rastro desaparecieron.
    assert con.execute("SELECT 1 FROM pistas WHERE id=?", (pid_a,)).fetchone() is None
    assert con.execute("SELECT 1 FROM track_audio_features WHERE track_id=?", (str(pid_a),)).fetchone() is None
    assert con.execute("SELECT 1 FROM track_vibe_tags WHERE track_id=?", (str(pid_a),)).fetchone() is None
    assert con.execute("SELECT 1 FROM historial WHERE pista_id=?", (pid_a,)).fetchone() is None
    assert con.execute("SELECT 1 FROM overrides_catalogacion WHERE match_value='hA'").fetchone() is None
    assert con.execute("SELECT 1 FROM pistas_playlist WHERE pista_id=?", (pid_a,)).fetchone() is None
    assert con.execute("SELECT 1 FROM dj_pistas_sesion WHERE pista_id=?", (pid_a,)).fetchone() is None
    assert con.execute("SELECT 1 FROM albums WHERE id=?", (alb_a,)).fetchone() is None

    # Archivos: audio y carátula propia borrados; AVATAR compartido conservado.
    assert not audio_a.exists()
    assert not cover_a.exists()
    assert avatar.exists(), "El avatar de artista compartido NO debe borrarse"

    # La pista B y su mundo permanecen intactos.
    assert con.execute("SELECT 1 FROM pistas WHERE id=?", (pid_b,)).fetchone() is not None
    assert audio_b.exists() and cover_b.exists()
    assert con.execute("SELECT 1 FROM albums WHERE id=?", (alb_b,)).fetchone() is not None
    assert con.execute("SELECT 1 FROM artistas WHERE id=?", (art_id,)).fetchone() is not None

    # Playlist recompuesta: B ahora en posición 1.
    fila = con.execute("SELECT posicion FROM pistas_playlist WHERE playlist_id=? AND pista_id=?", (pl_id, pid_b)).fetchone()
    assert fila["posicion"] == 1
    # Sesión DJ recompuesta: B en posición 1.
    fila = con.execute("SELECT posicion FROM dj_pistas_sesion WHERE sesion_id=? AND pista_id=?", (ses_id, pid_b)).fetchone()
    assert fila["posicion"] == 1

    # Manifiesto: ya no contiene la línea de A; sí la de B.
    lineas = (tmp / "assets" / "assets_manifest.jsonl").read_text(encoding="utf-8").splitlines()
    archivos = [json.loads(l)["archivo"] for l in lineas if l.strip()]
    assert str(audio_a) not in archivos
    assert str(audio_b) in archivos

    # Tombstones de sync registrados (pista + álbum huérfano).
    tomb = {r["entidad"] for r in con.execute("SELECT entidad FROM sync_tombstones").fetchall()}
    assert "pista" in tomb and "album" in tomb


def test_eliminar_pista_borra_artista_y_avatar_si_queda_huerfano(db_eliminar):
    tmp = db_eliminar
    con = get_conexion()
    art_id, alb = _crear_artista_album("Solo", "Único", portada_album=str(tmp / "assets" / "alb.jpg"))
    audio = tmp / "U.mp3"; audio.write_bytes(b"u")
    cover = tmp / "assets" / "cov.jpg"; cover.write_bytes(b"c")
    avatar = tmp / "assets" / "solo.jpg"; avatar.write_bytes(b"a")
    pid = _crear_pista(tmp, "Única", art_id, alb, "Solo", "Único", ruta_audio=audio, hash_sha="h1")
    _escribir_manifest_assets(tmp, [
        {"archivo": str(audio), "track_cover": str(cover), "artist_avatar": str(avatar)},
    ])

    res = svc_bib.eliminar_pista(pid)
    assert res["ok"] and res["album_eliminado"] and res["artista_eliminado"]
    # Sin más pistas: artista y su avatar (no compartido) se borran.
    assert con.execute("SELECT 1 FROM artistas WHERE id=?", (art_id,)).fetchone() is None
    assert not avatar.exists()
    assert not cover.exists()
    assert not audio.exists()


def test_eliminar_pista_inexistente(db_eliminar):
    res = svc_bib.eliminar_pista(99999)
    assert res["ok"] is False
