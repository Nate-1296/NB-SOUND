from pathlib import Path

import pytest

from db.conexion import cerrar_db, get_conexion, inicializar_db
from servicios.biblioteca import buscar


@pytest.fixture()
def db_busqueda(tmp_path):
    inicializar_db(tmp_path / "busqueda.sqlite")
    try:
        yield tmp_path
    finally:
        cerrar_db()


def _crear_pista(
    tmp_path: Path,
    titulo: str,
    *,
    artista: str = "Artista",
    album: str = "Album",
    favorita: bool = False,
) -> int:
    con = get_conexion()
    artista_id = con.execute(
        "INSERT OR IGNORE INTO artistas(nombre, nombre_slug) VALUES (?, ?)",
        (artista, artista.lower().replace(" ", "-")),
    ).lastrowid
    if not artista_id:
        artista_id = con.execute("SELECT id FROM artistas WHERE nombre = ?", (artista,)).fetchone()["id"]

    album_slug = f"{artista}-{album}".lower().replace(" ", "-")
    album_id = con.execute(
        """
        INSERT OR IGNORE INTO albums(artista_id, titulo, titulo_slug, tipo)
        VALUES (?, ?, ?, 'Album')
        """,
        (artista_id, album, album_slug),
    ).lastrowid
    if not album_id:
        album_id = con.execute(
            "SELECT id FROM albums WHERE artista_id = ? AND titulo_slug = ?",
            (artista_id, album_slug),
        ).fetchone()["id"]

    ruta = tmp_path / f"{artista}-{album}-{titulo}.mp3"
    ruta.write_bytes(b"audio")
    return con.execute(
        """
        INSERT INTO pistas(
            album_id, artista_id, titulo, artista_nombre, album_titulo,
            ruta_archivo, nombre_archivo, tamano_bytes, duracion_seg, favorita, estado
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 180, ?, 'biblioteca')
        """,
        (
            album_id, artista_id, titulo, artista, album, str(ruta), ruta.name,
            ruta.stat().st_size, 1 if favorita else 0,
        ),
    ).lastrowid


def test_busqueda_un_caracter_encuentra_pista_x(db_busqueda):
    _crear_pista(db_busqueda, "X", artista="System")

    out = buscar("X")

    assert [p["titulo"] for p in out["pistas"]] == ["X"]


def test_busqueda_sin_acentos_encuentra_titulo_con_tilde(db_busqueda):
    _crear_pista(db_busqueda, "Estás en mi cabeza", artista="Shakira")

    out = buscar("estas en mi cabeza")

    assert out["pistas"][0]["titulo"] == "Estás en mi cabeza"


def test_busqueda_fuzzy_ligera_encuentra_typo_razonable(db_busqueda):
    _crear_pista(db_busqueda, "Estás en mi cabeza", artista="Shakira")

    out = buscar("estás en mi cabesa")

    assert out["pistas"][0]["titulo"] == "Estás en mi cabeza"


def test_busqueda_titulo_artista_prioriza_artista_embebido(db_busqueda):
    _crear_pista(db_busqueda, "Hello", artista="Lionel Richie", album="Hello")
    _crear_pista(db_busqueda, "Hello", artista="Adele", album="25")

    out = buscar("Hello Adele")
    out_con_conector = buscar("Hello de Adele")

    assert out["pistas"][0]["artista_nombre"] == "Adele"
    assert out_con_conector["pistas"][0]["artista_nombre"] == "Adele"


def test_busqueda_album_result_incluye_id_navegable(db_busqueda):
    _crear_pista(db_busqueda, "Hello", artista="Adele", album="25")

    out = buscar("Adele")

    assert out["albums"]
    assert isinstance(out["albums"][0]["id"], int)
    assert out["albums"][0]["titulo"] == "25"


def test_busqueda_pista_favorita_queda_identificable(db_busqueda):
    _crear_pista(db_busqueda, "Hello", artista="Adele", album="25", favorita=True)
    _crear_pista(db_busqueda, "Hello Again", artista="Adele", album="25")

    out = buscar("Hello")
    favoritas = [p for p in out["pistas"] if p["favorita"] == 1]

    assert [p["titulo"] for p in favoritas] == ["Hello"]


def test_busqueda_inputs_raros_no_lanzan(db_busqueda):
    _crear_pista(db_busqueda, "Hello", artista="Adele", album="25")

    for termino in (":", "::", "¿?", "hello:", "adele - hello"):
        out = buscar(termino)
        assert set(out) == {"pistas", "albums", "artistas"}

    assert buscar("hello:")["pistas"][0]["titulo"] == "Hello"
