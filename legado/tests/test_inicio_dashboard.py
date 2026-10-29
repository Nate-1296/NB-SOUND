from pathlib import Path
import re

import pytest

from db.conexion import cerrar_db, get_conexion, inicializar_db
from servicios import biblioteca as svc_bib
from utils import diccionarios


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
    b"\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
    b"\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture()
def db_inicio(tmp_path):
    inicializar_db(tmp_path / "inicio_dashboard.db")
    try:
        yield tmp_path
    finally:
        cerrar_db()


def _crear_pista_inicio(
    tmp_path: Path,
    nombre: str,
    *,
    favorita: bool = False,
    reproducciones: int = 0,
    portada: str | None = None,
) -> dict:
    ruta = tmp_path / f"{nombre}.mp3"
    ruta.write_bytes(b"fake audio")
    portada_final = portada if portada is not None else f"/covers/{nombre}.jpg"

    con = get_conexion()
    artista_id = con.execute(
        "INSERT INTO artistas(nombre, nombre_slug) VALUES (?, ?)",
        (f"Artista {nombre}", f"artista-{nombre}"),
    ).lastrowid
    album_id = con.execute(
        """
        INSERT INTO albums(artista_id, titulo, titulo_slug, tipo, portada_ruta)
        VALUES (?, ?, ?, 'Album', ?)
        """,
        (artista_id, f"Album {nombre}", f"album-{nombre}", portada_final),
    ).lastrowid
    pista_id = con.execute(
        """
        INSERT INTO pistas(
            album_id, artista_id, titulo, artista_nombre, album_titulo,
            ruta_archivo, nombre_archivo, tamano_bytes, duracion_seg,
            favorita, veces_reproducida, ultimo_acceso, estado
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), 'biblioteca')
        """,
        (
            album_id,
            artista_id,
            f"Pista {nombre}",
            f"Artista {nombre}",
            f"Album {nombre}",
            str(ruta),
            ruta.name,
            ruta.stat().st_size,
            180,
            1 if favorita else 0,
            reproducciones,
        ),
    ).lastrowid
    return {
        "id": pista_id,
        "album_id": album_id,
        "artista_id": artista_id,
        "ruta_archivo": str(ruta),
    }


def _registrar_historial(pista_id: int, total: int = 1) -> None:
    con = get_conexion()
    for _ in range(total):
        con.execute(
            """
            INSERT INTO historial(pista_id, titulo_snap, artista_snap, duracion_seg, completada)
            VALUES (?, 'snapshot', 'artist', 180, 1)
            """,
            (pista_id,),
        )


def _crear_playlist(nombre: str, pistas: list[int]) -> int:
    con = get_conexion()
    playlist_id = con.execute(
        "INSERT INTO playlists(nombre, descripcion, tipo) VALUES (?, '', 'manual')",
        (nombre,),
    ).lastrowid
    for posicion, pista_id in enumerate(pistas, start=1):
        con.execute(
            "INSERT INTO pistas_playlist(playlist_id, pista_id, posicion) VALUES (?, ?, ?)",
            (playlist_id, pista_id, posicion),
        )
    return playlist_id


def _forzar_fechas_inicio(pista: dict, fecha: str) -> None:
    con = get_conexion()
    con.execute(
        "UPDATE pistas SET indexado_en = ?, actualizado_en = ? WHERE id = ?",
        (fecha, fecha, pista["id"]),
    )
    con.execute(
        "UPDATE albums SET creado_en = ? WHERE id = ?",
        (fecha, pista["album_id"]),
    )
    con.execute(
        "UPDATE artistas SET creado_en = ? WHERE id = ?",
        (fecha, pista["artista_id"]),
    )


def test_servicios_dashboard_inicio_devuelven_vacio_sin_biblioteca(db_inicio):
    assert svc_bib.pistas_para_volver() == []
    assert svc_bib.playlists_destacadas() == []
    assert svc_bib.albums_con_canciones_que_gustan() == []
    assert svc_bib.recomendaciones_inicio() == []


def test_servicios_dashboard_inicio_shape_y_prioridad_local(db_inicio):
    portada_favorita = db_inicio / "favorita.png"
    portada_favorita.write_bytes(PNG_1X1)
    favorita = _crear_pista_inicio(db_inicio, "favorita", favorita=True, reproducciones=1, portada=str(portada_favorita))
    escuchada = _crear_pista_inicio(db_inicio, "escuchada", reproducciones=5)
    _registrar_historial(favorita["id"], total=1)
    _registrar_historial(escuchada["id"], total=3)
    playlist_id = _crear_playlist("Lista local", [favorita["id"], escuchada["id"]])

    para_volver = svc_bib.pistas_para_volver(limite=5)
    assert para_volver
    assert {item["tipo"] for item in para_volver} == {"pista"}
    assert {"id", "titulo", "subtitulo", "portada_ruta", "album_id", "artista_id", "reproducciones_total"} <= set(para_volver[0])

    albums = svc_bib.albums_con_canciones_que_gustan(limite=5)
    assert albums
    assert albums[0]["favoritas_total"] >= 1
    assert albums[0]["tipo"] == "album"
    assert albums[0]["score_local"] > 0

    playlists = svc_bib.playlists_destacadas(limite=5)
    assert playlists
    playlist = playlists[0]
    assert playlist["auto_key"] == svc_bib.PLAYLIST_FAVORITOS_AUTO_KEY
    assert playlist["tipo_playlist"] == "favoritos"
    assert playlist["tipo"] == "playlist"
    assert playlist["es_anclada"] is True
    assert playlist["num_pistas"] == 1
    assert playlist["portadas"]
    manual = next(item for item in playlists if item["playlist_id"] == playlist_id)
    assert manual["tipo"] == "playlist"
    assert manual["tipo_playlist"] == "usuario"
    assert manual["origen"] == "usuario"
    assert manual["es_anclada"] is False
    assert manual["num_pistas"] == 2

    recomendaciones = svc_bib.recomendaciones_inicio(limite=3)
    assert 0 < len(recomendaciones) <= 3
    assert all("tipo" in item and "origen" in item for item in recomendaciones)
    assert all(item.get("contexto") for item in recomendaciones)


def test_recientes_dashboard_inicio_son_globales_y_ordenados_por_fecha(db_inicio):
    antigua = _crear_pista_inicio(db_inicio, "antigua")
    nueva = _crear_pista_inicio(db_inicio, "nueva")
    _forzar_fechas_inicio(antigua, "2020-01-02 10:00:00")
    _forzar_fechas_inicio(nueva, "2024-03-04 10:00:00")

    pistas = svc_bib.pistas_recientes(limite=5, ventana_dias=1)
    assert [item["id"] for item in pistas[:2]] == [nueva["id"], antigua["id"]]

    albums = svc_bib.albums_recientes(limite=5, ventana_dias=1)
    assert [item["id"] for item in albums[:2]] == [nueva["album_id"], antigua["album_id"]]

    artistas = svc_bib.artistas_recientes(limite=5, ventana_dias=1)
    assert [item["id"] for item in artistas[:2]] == [nueva["artista_id"], antigua["artista_id"]]


def test_modelo_estadisticas_cargar_usa_limites_mayores_a_veinte(monkeypatch):
    pytest.importorskip("PySide6")
    from ui import modelos_qml

    capturados = {}
    kwargs_capturados = {}

    def captura(nombre):
        def _fn(*, limite, **_kwargs):
            capturados[nombre] = limite
            kwargs_capturados[nombre] = dict(_kwargs)
            return []
        return _fn

    monkeypatch.setattr(modelos_qml.svc_bib, "estadisticas_generales", lambda: {"total_pistas": 0})
    monkeypatch.setattr(modelos_qml.svc_bib, "pistas_recientes", captura("recientes_canciones"))
    monkeypatch.setattr(modelos_qml.svc_bib, "albums_recientes", captura("recientes_albums"))
    monkeypatch.setattr(modelos_qml.svc_bib, "artistas_recientes", captura("recientes_artistas"))
    monkeypatch.setattr(modelos_qml.svc_bib, "pistas_mas_escuchadas", captura("mas_escuchadas_canciones"))
    monkeypatch.setattr(modelos_qml.svc_bib, "albums_mas_escuchados", captura("mas_escuchadas_albums"))
    monkeypatch.setattr(modelos_qml.svc_bib, "artistas_mas_escuchados", captura("mas_escuchadas_artistas"))
    monkeypatch.setattr(modelos_qml.svc_bib, "playlists_mas_escuchadas", captura("mas_escuchadas_playlists"))
    monkeypatch.setattr(modelos_qml.svc_bib, "pistas_para_volver", captura("para_volver"))
    monkeypatch.setattr(modelos_qml.svc_bib, "playlists_destacadas", captura("playlists_destacadas"))
    monkeypatch.setattr(modelos_qml.svc_bib, "albums_con_canciones_que_gustan", captura("albums_que_gustan"))
    monkeypatch.setattr(modelos_qml.svc_bib, "recomendaciones_inicio", captura("recomendaciones_inicio"))
    monkeypatch.setattr(modelos_qml.svc_bib, "pistas_nunca_escuchadas",  captura("pistas_nunca_escuchadas"),  raising=False)
    monkeypatch.setattr(modelos_qml.svc_bib, "pistas_menos_escuchadas",  captura("pistas_menos_escuchadas"), raising=False)
    monkeypatch.setattr(modelos_qml.svc_bib, "estadisticas_extras_perfil", lambda: {}, raising=False)

    modelo = modelos_qml.ModeloEstadisticas()
    modelo.cargar()

    assert capturados == {
        "recientes_canciones": 60,
        "recientes_albums": 50,
        "recientes_artistas": 40,
        "mas_escuchadas_canciones": 60,
        "mas_escuchadas_albums": 50,
        "mas_escuchadas_artistas": 40,
        "mas_escuchadas_playlists": 50,
        "para_volver": 60,
        "playlists_destacadas": 50,
        "albums_que_gustan": 40,
        "recomendaciones_inicio": 60,
        "pistas_nunca_escuchadas":  20,
        "pistas_menos_escuchadas":  20,
    }
    assert kwargs_capturados["recientes_canciones"] == {}
    assert kwargs_capturados["recientes_albums"] == {}
    assert kwargs_capturados["recientes_artistas"] == {}
    assert modelo.para_volver.total == 0
    assert modelo.playlists_destacadas.total == 0
    assert modelo.albums_que_gustan.total == 0
    assert modelo.recomendaciones_inicio.total == 0


def test_modelo_estadisticas_normaliza_portadas_y_no_revienta_vacio(db_inicio):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloEstadisticas

    modelo = ModeloEstadisticas()
    modelo.cargar()

    assert modelo.resumen["total_pistas"] == 0
    assert modelo.para_volver.total == 0
    assert modelo.playlists_destacadas.total == 0
    assert modelo.albums_que_gustan.total == 0
    assert modelo.recomendaciones_inicio.total == 0

    portada = db_inicio / "cover.jpg"
    portada.write_bytes(b"fake cover")
    normalizados = modelo._normalizar_portadas([
        {
            "id": 1,
            "tipo": "playlist",
            "nombre": "Lista",
            "portada_ruta": str(portada),
            "portadas": [str(portada)],
        }
    ])

    assert normalizados[0]["portada_ruta"].startswith("file://")
    assert normalizados[0]["portadas"][0].startswith("file://")


def test_saludo_inicio_con_y_sin_nombre_no_usa_emojis(monkeypatch):
    monkeypatch.setattr(diccionarios.random, "choice", lambda secuencia: secuencia[0])

    sin_nombre = diccionarios.saludo_inicio("")
    con_nombre = diccionarios.saludo_inicio("Jonathan")

    assert sin_nombre
    assert con_nombre
    assert "Jonathan" in con_nombre

    emoji_re = re.compile("[\U0001F300-\U0001FAFF]")
    saludos = (
        diccionarios.SALUDOS_MANANA
        + diccionarios.SALUDOS_TARDE
        + diccionarios.SALUDOS_NOCHE
        + diccionarios.SALUDOS_SIN_NOMBRE
    )
    assert all(not emoji_re.search(saludo) for saludo in saludos)


def test_albums_mas_escuchados_no_incluye_num_pistas_en_query(db_inicio):
    """albums_mas_escuchados does not have num_pistas in the SQL; the UI must
    handle num_pistas=0 gracefully (not display '0 pistas')."""
    pista = _crear_pista_inicio(db_inicio, "album_test", reproducciones=2)
    _registrar_historial(pista["id"], total=2)

    albums = svc_bib.albums_mas_escuchados(limite=5)
    assert albums, "should return albums when there is history"
    album = albums[0]
    # Fields guaranteed to exist
    assert "id" in album
    assert "titulo" in album
    assert "artista_nombre" in album
    assert "reproducciones_total" in album
    assert album["reproducciones_total"] >= 1
    # num_pistas is NOT in the query — must default to 0 (the UI hides it when 0)
    assert album.get("num_pistas", 0) == 0, \
        "num_pistas is absent from albums_mas_escuchados; UI shows only artist name when 0"


def test_playlists_destacadas_tienen_playlist_id_y_num_pistas(db_inicio):
    """DashboardCard clickable playlist navigation requires playlist_id and num_pistas."""
    p1 = _crear_pista_inicio(db_inicio, "nav1", reproducciones=1)
    p2 = _crear_pista_inicio(db_inicio, "nav2", reproducciones=1)
    _registrar_historial(p1["id"], total=1)
    playlist_id = _crear_playlist("NavTest", [p1["id"], p2["id"]])

    playlists = svc_bib.playlists_destacadas(limite=10)
    manual = next((pl for pl in playlists if pl.get("playlist_id") == playlist_id), None)
    assert manual is not None, "created playlist must appear in playlists_destacadas"
    # playlist_id is required by abrirItem to navigate to the specific playlist
    assert manual["playlist_id"] > 0, "playlist_id must be a positive int for navigation"
    # num_pistas must be > 0 so subtituloItem shows it
    assert manual["num_pistas"] == 2, "num_pistas must reflect actual track count"
    # tipo is required for the DashboardCard to dispatch correctly
    assert manual["tipo"] == "playlist"


def test_recomendaciones_inicio_tipo_y_origen(db_inicio):
    """recomendaciones_inicio must return items with tipo and origen fields."""
    p = _crear_pista_inicio(db_inicio, "recom1", reproducciones=3)
    _registrar_historial(p["id"], total=3)

    recomendaciones = svc_bib.recomendaciones_inicio(limite=60)
    assert recomendaciones, "must return items when library has history"
    assert all("tipo" in item and "origen" in item for item in recomendaciones)
