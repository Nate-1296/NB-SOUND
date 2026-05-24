from pathlib import Path
import json
import threading

import pytest

from db.conexion import cerrar_db, get_conexion, inicializar_db
from servicios import biblioteca as svc_bib
from servicios import reproductor as reproductor_mod
from config import settings as _settings
from servicios.reproductor import EstadoReproductor, Reproductor


_ORIGINAL_INICIALIZAR_VLC = reproductor_mod.Reproductor._inicializar_vlc


@pytest.fixture()
def db_reproductor(tmp_path, monkeypatch):
    monkeypatch.setattr(reproductor_mod.Reproductor, "_inicializar_vlc", lambda self: None)
    monkeypatch.setattr(reproductor_mod.Reproductor, "_iniciar_hilo_progreso", lambda self: None)

    inicializar_db(tmp_path / "reproductor_test.db")
    try:
        yield tmp_path
    finally:
        cerrar_db()


def _crear_reproductor() -> Reproductor:
    return Reproductor(permitir_modo_simulado=True)


def _crear_pista(
    tmp_path: Path,
    nombre: str,
    *,
    portada: str = "/covers/album.jpg",
    release_id: str | None = None,
    duracion_seg: float = 120,
    album_tipo: str = "Album",
    genero: str | None = None,
    anio: int | None = None,
    favorita: bool = False,
) -> dict:
    ruta = tmp_path / f"{nombre}.mp3"
    ruta.write_bytes(b"fake audio")
    mb_release_id = release_id or f"rel-{nombre}"

    con = get_conexion()
    cursor = con.execute(
        "INSERT INTO artistas(nombre, nombre_slug) VALUES (?, ?)",
        (f"Artista {nombre}", f"artista-{nombre}"),
    )
    artista_id = cursor.lastrowid
    cursor = con.execute(
        """
        INSERT INTO albums(artista_id, titulo, titulo_slug, tipo, portada_ruta)
        VALUES (?, ?, ?, ?, ?)
        """,
        (artista_id, f"Album {nombre}", f"album-{nombre}", album_tipo, portada),
    )
    album_id = cursor.lastrowid
    con.execute(
        "UPDATE albums SET mb_release_id = ? WHERE id = ?",
        (mb_release_id, album_id),
    )
    cursor = con.execute(
        """
        INSERT INTO pistas(
            album_id, artista_id, titulo, artista_nombre, album_titulo,
            mb_release_id, ruta_archivo, nombre_archivo, tamano_bytes, duracion_seg,
            genero, anio, favorita, estado
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'biblioteca')
        """,
        (
            album_id,
            artista_id,
            f"Pista {nombre}",
            f"Artista {nombre}",
            f"Album {nombre}",
            mb_release_id,
            str(ruta),
            ruta.name,
            ruta.stat().st_size,
            duracion_seg,
            genero,
            anio,
            1 if favorita else 0,
        ),
    )
    pista_id = cursor.lastrowid
    return {
        "id": pista_id,
        "titulo": f"Pista {nombre}",
        "artista_nombre": f"Artista {nombre}",
        "album_titulo": f"Album {nombre}",
        "album_id": album_id,
        "mb_release_id": mb_release_id,
        "ruta_archivo": str(ruta),
        "duracion_seg": duracion_seg,
        "genero": genero,
        "anio": anio,
        "favorita": 1 if favorita else 0,
    }


def test_reproductor_resuelve_portada_de_album_en_pista_activa(db_reproductor):
    datos = _crear_pista(db_reproductor, "uno", portada="/covers/uno.jpg")
    rep = _crear_reproductor()
    datos_sin_portada = {
        k: v for k, v in datos.items() if k not in {"portada_ruta", "album_id"}
    }

    rep.reproducir_pista(datos_sin_portada)

    assert rep.pista_activa is not None
    assert rep.pista_activa.portada_ruta == "/covers/uno.jpg"


def test_modelo_reproductor_expone_snapshot_de_pista_activa_para_qml(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    datos = _crear_pista(db_reproductor, "dos", portada="/covers/dos.jpg")
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    rep.reproducir_pista(datos)

    assert modelo.pista_activa["titulo"] == "Pista dos"
    assert modelo.pista_activa["portada_ruta"] == "/covers/dos.jpg"


def test_modelo_reproductor_expone_pista_visual_de_cola_persistida_sin_activar(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    datos = _crear_pista(db_reproductor, "continuar", portada="/covers/continuar.jpg")
    rep = _crear_reproductor()
    rep.agregar_a_cola(datos)

    assert rep.pista_activa is None
    assert rep.indice_cola == -1

    cerrar_db()
    inicializar_db(db_reproductor / "reproductor_test.db")

    rep_restaurado = _crear_reproductor()
    modelo = ModeloReproductor(rep_restaurado)

    assert rep_restaurado.pista_activa is None
    assert rep_restaurado.indice_cola == -1
    assert modelo.pista_activa == {}
    assert modelo.cola.total == 1
    assert modelo.pista_visual["titulo"] == "Pista continuar"
    assert modelo.pista_visual["portada_ruta"] == "/covers/continuar.jpg"


def test_modelo_reproductor_pista_visual_usa_cola_cacheada_sin_consultar_backend(db_reproductor, monkeypatch):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    datos = _crear_pista(db_reproductor, "cache", portada="/covers/cache.jpg")
    rep = _crear_reproductor()
    rep.agregar_a_cola(datos)
    modelo = ModeloReproductor(rep)

    def obtener_cola_bloqueada():
        raise AssertionError("pista_visual no debe consultar la cola del backend")

    monkeypatch.setattr(rep, "obtener_cola", obtener_cola_bloqueada)

    assert modelo.pista_visual["titulo"] == "Pista cache"
    assert modelo.pista_visual["portada_ruta"] == "/covers/cache.jpg"


def test_reanudar_cola_persistida_no_bloquea_al_leer_pista_visual(db_reproductor):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import Qt
    from ui.modelos_qml import ModeloReproductor

    datos = _crear_pista(db_reproductor, "reanudar", portada="/covers/reanudar.jpg")
    rep = _crear_reproductor()
    rep.agregar_a_cola(datos)

    cerrar_db()
    inicializar_db(db_reproductor / "reproductor_test.db")

    rep_restaurado = _crear_reproductor()
    modelo = ModeloReproductor(rep_restaurado)
    lecturas_visual = []
    errores = []

    def leer_pista_visual():
        lecturas_visual.append(modelo.pista_visual.get("titulo"))

    modelo.pistaVisualCambiada.connect(leer_pista_visual, Qt.DirectConnection)

    def reanudar():
        try:
            modelo.pausar_reanudar()
        except Exception as exc:
            errores.append(exc)

    hilo = threading.Thread(target=reanudar, daemon=True)
    hilo.start()
    hilo.join(timeout=1.5)

    assert not hilo.is_alive()
    assert not errores
    assert rep_restaurado.estado == EstadoReproductor.REPRODUCIENDO
    assert "Pista reanudar" in lecturas_visual


def test_reproductor_resuelve_portada_desde_assets_manifest(db_reproductor, monkeypatch):
    assets_dir = db_reproductor / "assets"
    assets_dir.mkdir()
    manifest = assets_dir / "assets_manifest.jsonl"
    manifest.write_text(
        json.dumps({"release_id": "rel-assets", "album_cover": "/covers/assets.jpg"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(_settings, "DEFAULT_ASSETS_DIR", assets_dir)
    svc_bib._CACHE_PORTADAS_ASSETS["firma"] = None

    datos = _crear_pista(
        db_reproductor,
        "assets",
        portada="",
        release_id="rel-assets",
    )
    rep = _crear_reproductor()

    rep.reproducir_pista({k: v for k, v in datos.items() if k != "portada_ruta"})

    assert rep.pista_activa is not None
    assert rep.pista_activa.portada_ruta == "/covers/assets.jpg"


def test_reproductor_expone_portada_hd_desde_assets_manifest(db_reproductor, monkeypatch):
    assets_dir = db_reproductor / "assets"
    assets_dir.mkdir()
    manifest = assets_dir / "assets_manifest.jsonl"
    manifest.write_text(
        json.dumps({
            "release_id": "rel-assets-hd",
            "album_cover": "/covers/assets.jpg",
            "album_cover_hd": "/covers/assets-hd.jpg",
        }) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(_settings, "DEFAULT_ASSETS_DIR", assets_dir)
    svc_bib._CACHE_PORTADAS_ASSETS["firma"] = None

    datos = _crear_pista(
        db_reproductor,
        "assets-hd",
        portada="",
        release_id="rel-assets-hd",
    )
    rep = _crear_reproductor()

    rep.reproducir_pista({k: v for k, v in datos.items() if k != "portada_ruta"})

    assert rep.pista_activa is not None
    assert rep.pista_activa.portada_ruta == "/covers/assets.jpg"
    assert rep.pista_activa.portada_hd_ruta == "/covers/assets-hd.jpg"


def test_modelo_reproductor_expone_portada_hd_para_qml(db_reproductor, monkeypatch):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    assets_dir = db_reproductor / "assets-qml"
    assets_dir.mkdir()
    (assets_dir / "assets_manifest.jsonl").write_text(
        json.dumps({"release_id": "rel-qml-hd", "album_cover_hd": "/covers/qml-hd.jpg"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(_settings, "DEFAULT_ASSETS_DIR", assets_dir)
    svc_bib._CACHE_PORTADAS_ASSETS["firma"] = None

    datos = _crear_pista(db_reproductor, "qml-hd", portada="/covers/qml.jpg", release_id="rel-qml-hd")
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    rep.reproducir_pista(datos)

    assert modelo.pista_activa["portada_ruta"] == "/covers/qml.jpg"
    assert modelo.pista_activa["portada_hd_ruta"] == "/covers/qml-hd.jpg"


def test_modelo_biblioteca_abre_album_desde_id_directo(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloBiblioteca

    pista = _crear_pista(db_reproductor, "album-id")
    modelo = ModeloBiblioteca()

    resultado = modelo.abrir_album_desde_pista({"album_id": pista["album_id"]})

    assert resultado["ok"] is True
    assert resultado["fallback"] is False
    assert modelo.album_detalle["titulo"] == pista["album_titulo"]


def test_modelo_biblioteca_abre_album_por_metadata_sin_id(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloBiblioteca

    pista = _crear_pista(db_reproductor, "album-fallback")
    modelo = ModeloBiblioteca()

    resultado = modelo.abrir_album_desde_pista({
        "album_titulo": pista["album_titulo"],
        "artista_nombre": pista["artista_nombre"],
    })

    assert resultado["ok"] is True
    assert resultado["fallback"] is True
    assert modelo.album_detalle["titulo"] == pista["album_titulo"]


def test_modelo_biblioteca_abre_artista_por_metadata_sin_id(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloBiblioteca

    pista = _crear_pista(db_reproductor, "artist-fallback")
    modelo = ModeloBiblioteca()

    resultado = modelo.abrir_artista_desde_pista({
        "artista_nombre": pista["artista_nombre"],
    })

    assert resultado["ok"] is True
    assert resultado["fallback"] is True
    assert modelo.artista_detalle["nombre"] == pista["artista_nombre"]


def test_modelo_biblioteca_no_abre_metadata_ambigua(db_reproductor, monkeypatch):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloBiblioteca

    modelo = ModeloBiblioteca()
    monkeypatch.setattr(
        svc_bib,
        "buscar",
        lambda termino, limite=20: {
            "pistas": [],
            "albums": [
                {"id": 1, "titulo": "Mismo Album", "artista_nombre": "Mismo Artista"},
                {"id": 2, "titulo": "Mismo Album", "artista_nombre": "Mismo Artista"},
            ],
            "artistas": [],
        },
    )

    resultado = modelo.abrir_album_desde_pista({
        "album_titulo": "Mismo Album",
        "artista_nombre": "Mismo Artista",
    })

    assert resultado["ok"] is False
    assert modelo.album_detalle == {}


def test_biblioteca_grupos_albums_disponibles_oculta_vacios_y_clasifica_otros(db_reproductor):
    _crear_pista(db_reproductor, "grupo-album", album_tipo="Album")
    _crear_pista(db_reproductor, "grupo-single", album_tipo="Single")
    _crear_pista(db_reproductor, "grupo-ep", album_tipo="EP")
    _crear_pista(db_reproductor, "grupo-otro", album_tipo="Compilation")

    grupos = svc_bib.grupos_albums_disponibles()

    assert [g["clave"] for g in grupos] == ["albums", "singles_y_ep", "otros"]
    assert {g["clave"]: g["total"] for g in grupos} == {
        "albums": 1,
        "singles_y_ep": 2,
        "otros": 1,
    }
    assert [a["tipo"] for a in svc_bib.listar_albums(grupo="otros")] == ["Compilation"]


def test_listar_pistas_sin_limite_de_500_y_con_filtros_reales(db_reproductor):
    total = 505
    for i in range(total):
        _crear_pista(
            db_reproductor,
            f"bulk-{i:03d}",
            duracion_seg=60 + i,
            genero="electro-pop" if i == 37 else "rock",
            anio=2000 + (i % 20),
            favorita=i == 37,
        )

    todas = svc_bib.listar_pistas(limite=None)
    filtradas = svc_bib.listar_pistas(filtro_texto="bulk-037", limite=None)
    favoritas = svc_bib.listar_pistas(solo_favoritas=True, limite=None)
    por_genero = svc_bib.listar_pistas(filtro_texto="electro-pop", limite=None)
    mayor_duracion = svc_bib.listar_pistas(orden="duracion", limite=1)
    orden_invalido = svc_bib.listar_pistas(orden="no_existe", limite=1)

    assert len(todas) == total
    assert len(filtradas) == 1
    assert filtradas[0]["titulo"] == "Pista bulk-037"
    assert [p["titulo"] for p in favoritas] == ["Pista bulk-037"]
    assert [p["titulo"] for p in por_genero] == ["Pista bulk-037"]
    assert mayor_duracion[0]["titulo"] == "Pista bulk-504"
    assert orden_invalido[0]["titulo"] == "Pista bulk-000"


def test_biblioteca_busqueda_albumes_artistas_por_metadata_cruzada_con_conteos_completos(db_reproductor):
    con = get_conexion()
    artista_id = con.execute(
        "INSERT INTO artistas(nombre, nombre_slug) VALUES (?, ?)",
        ("Bad Bunny", "bad-bunny"),
    ).lastrowid
    album_id = con.execute(
        """
        INSERT INTO albums(artista_id, titulo, titulo_slug, tipo, anio, portada_ruta)
        VALUES (?, ?, ?, 'Album', 2020, ?)
        """,
        (artista_id, "YHLQMDLG", "yhlqmdlg", "/covers/yhlqmdlg.jpg"),
    ).lastrowid
    con.execute(
        "INSERT INTO artistas(nombre, nombre_slug) VALUES (?, ?)",
        ("Artista Ajeno", "artista-ajeno"),
    )

    for indice, (titulo, genero) in enumerate(
        [("Yo perreo sola", "reggaeton"), ("Safaera", "urbano")],
        start=1,
    ):
        ruta = db_reproductor / f"bad-bunny-{indice}.mp3"
        ruta.write_bytes(b"fake audio")
        con.execute(
            """
            INSERT INTO pistas(
                album_id, artista_id, titulo, artista_nombre, album_titulo,
                track_number, ruta_archivo, nombre_archivo, tamano_bytes,
                duracion_seg, genero, estado
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'biblioteca')
            """,
            (
                album_id,
                artista_id,
                titulo,
                "Bad Bunny",
                "YHLQMDLG",
                indice,
                str(ruta),
                ruta.name,
                ruta.stat().st_size,
                180 + indice,
                genero,
            ),
        )

    albumes_por_cancion = svc_bib.listar_albums(filtro_texto="Yo perreo sola")
    albumes_por_genero = svc_bib.listar_albums(filtro_texto="urbano")
    artistas_por_cancion = svc_bib.listar_artistas(filtro_texto="Yo perreo sola")
    artistas_por_album = svc_bib.listar_artistas(filtro_texto="YHLQMDLG")

    assert [a["titulo"] for a in albumes_por_cancion] == ["YHLQMDLG"]
    assert albumes_por_cancion[0]["num_pistas"] == 2
    assert [a["titulo"] for a in albumes_por_genero] == ["YHLQMDLG"]
    assert [a["nombre"] for a in artistas_por_cancion] == ["Bad Bunny"]
    assert artistas_por_cancion[0]["num_pistas"] == 2
    assert [a["nombre"] for a in artistas_por_album] == ["Bad Bunny"]


def test_biblioteca_ordenes_directos_e_inversos(db_reproductor):
    _crear_pista(db_reproductor, "orden-a", duracion_seg=100, anio=2010)
    _crear_pista(db_reproductor, "orden-b", duracion_seg=220, anio=2020)
    _crear_pista(db_reproductor, "orden-c", duracion_seg=40, anio=2000)

    assert svc_bib.listar_pistas(orden="titulo", limite=1)[0]["titulo"] == "Pista orden-a"
    assert svc_bib.listar_pistas(orden="titulo_desc", limite=1)[0]["titulo"] == "Pista orden-c"
    assert svc_bib.listar_pistas(orden="duracion", limite=1)[0]["titulo"] == "Pista orden-b"
    assert svc_bib.listar_pistas(orden="duracion_asc", limite=1)[0]["titulo"] == "Pista orden-c"
    assert svc_bib.listar_pistas(orden="anio", limite=1)[0]["titulo"] == "Pista orden-b"
    assert svc_bib.listar_pistas(orden="anio_asc", limite=1)[0]["titulo"] == "Pista orden-c"

    assert svc_bib.listar_albums(orden="titulo")[0]["titulo"] == "Album orden-a"
    assert svc_bib.listar_albums(orden="titulo_desc")[0]["titulo"] == "Album orden-c"
    assert svc_bib.listar_albums(orden="duracion")[0]["titulo"] == "Album orden-b"
    assert svc_bib.listar_albums(orden="duracion_asc")[0]["titulo"] == "Album orden-c"

    assert svc_bib.listar_artistas(orden="nombre")[0]["nombre"] == "Artista orden-a"
    assert svc_bib.listar_artistas(orden="nombre_desc")[0]["nombre"] == "Artista orden-c"
    assert svc_bib.listar_artistas(orden="duracion")[0]["nombre"] == "Artista orden-b"
    assert svc_bib.listar_artistas(orden="duracion_asc")[0]["nombre"] == "Artista orden-c"


def test_detalle_artista_expone_todas_las_pistas_y_destacadas(db_reproductor):
    con = get_conexion()
    artista_id = con.execute(
        "INSERT INTO artistas(nombre, nombre_slug) VALUES (?, ?)",
        ("Artista Completo", "artista-completo"),
    ).lastrowid
    album_id = con.execute(
        """
        INSERT INTO albums(artista_id, titulo, titulo_slug, tipo, portada_ruta)
        VALUES (?, ?, ?, 'Album', ?)
        """,
        (artista_id, "Album Completo", "album-completo", "/covers/completo.jpg"),
    ).lastrowid
    duracion_total = 0
    for i in range(12):
        ruta = db_reproductor / f"artist-full-{i}.mp3"
        ruta.write_bytes(b"fake audio")
        duracion = 100 + i
        duracion_total += duracion
        con.execute(
            """
            INSERT INTO pistas(
                album_id, artista_id, titulo, artista_nombre, album_titulo,
                track_number, ruta_archivo, nombre_archivo, tamano_bytes,
                duracion_seg, veces_reproducida, estado
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'biblioteca')
            """,
            (
                album_id,
                artista_id,
                f"Pista completa {i:02d}",
                "Artista Completo",
                "Album Completo",
                i + 1,
                str(ruta),
                ruta.name,
                ruta.stat().st_size,
                duracion,
                i,
            ),
        )

    detalle = svc_bib.detalle_artista(artista_id)

    assert detalle is not None
    assert len(detalle["pistas"]) == 12
    assert len(detalle["pistas_destacadas"]) == 10
    assert detalle["duracion_total_seg"] == duracion_total
    assert detalle["pistas_destacadas"][0]["titulo"] == "Pista completa 11"


def test_modelo_biblioteca_persiste_estado_y_carga_pistas_filtradas(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloBiblioteca

    _crear_pista(db_reproductor, "estado-visible", genero="ambient")
    _crear_pista(db_reproductor, "estado-oculta", genero="metal")
    modelo = ModeloBiblioteca()

    modelo.guardar_estado_vista({
        "seccion": "pistas",
        "grupo_albums": "singles_y_ep",
        "filtro_albums": "estado-visible",
        "filtro_artistas": "estado-visible",
        "filtro_pistas": "ambient",
        "solo_favoritas": False,
        "orden_pistas": "anio_asc",
        "orden_albums": "pistas_asc",
        "orden_artistas": "nombre_desc",
        "scroll_pistas": 42,
    })
    estado = ModeloBiblioteca().estado_vista()
    modelo.cargar_pistas("ambient", False, "titulo")
    modelo.cargar_albums_por_grupo("albums", "titulo_desc", "estado-visible")
    album_filtrado = modelo.albums.obtener(0)
    modelo.cargar_artistas("estado-visible", "nombre_desc")
    artista_filtrado = modelo.artistas.obtener(0)

    assert estado["seccion"] == "pistas"
    assert estado["grupo_albums"] == "singles_y_ep"
    assert estado["filtro_albums"] == "estado-visible"
    assert estado["filtro_artistas"] == "estado-visible"
    assert estado["filtro_pistas"] == "ambient"
    assert estado["orden_pistas"] == "anio_asc"
    assert estado["orden_albums"] == "pistas_asc"
    assert estado["orden_artistas"] == "nombre_desc"
    assert estado["scroll_pistas"] == 42
    modelo.cargar_pistas("ambient", False, "titulo")
    assert modelo.pistas.total == 1
    assert modelo.pistas.obtener(0)["titulo"] == "Pista estado-visible"
    assert album_filtrado["titulo"] == "Album estado-visible"
    assert artista_filtrado["nombre"] == "Artista estado-visible"


def test_modelo_biblioteca_toggle_favorita_y_filtro_reflejan_estado(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloBiblioteca

    _crear_pista(db_reproductor, "favorita-off-a")
    pista = _crear_pista(db_reproductor, "favorita-toggle")
    modelo = ModeloBiblioteca()

    modelo.cargar_pistas("", True, "titulo")
    assert modelo.pistas.total == 0

    assert modelo.toggle_favorita(pista["id"]) is True
    modelo.cargar_pistas("", True, "titulo")

    assert modelo.pistas.total == 1
    assert modelo.pistas.obtener(0)["titulo"] == "Pista favorita-toggle"
    assert modelo.pistas.obtener(0)["favorita"] == 1

    assert modelo.toggle_favorita(pista["id"]) is False
    modelo.cargar_pistas("", True, "titulo")

    assert modelo.pistas.total == 0


def test_modelo_biblioteca_favorita_refleja_lista_album_y_artista(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloBiblioteca

    pista = _crear_pista(db_reproductor, "favorita-contextos")
    artista_id = get_conexion().execute(
        "SELECT artista_id FROM pistas WHERE id = ?",
        (pista["id"],),
    ).fetchone()["artista_id"]
    modelo = ModeloBiblioteca()

    assert modelo.toggle_favorita(pista["id"]) is True

    modelo.cargar_pistas("", False, "titulo")
    modelo.abrir_album(pista["album_id"])
    modelo.abrir_artista(artista_id)

    assert modelo.pistas.obtener(0)["favorita"] == 1
    assert modelo.album_detalle["pistas"][0]["favorita"] == 1
    assert modelo.artista_detalle["pistas"][0]["favorita"] == 1
    assert modelo.artista_detalle["pistas_destacadas"][0]["favorita"] == 1


def test_siguiente_sin_cola_detiene_y_play_reanuda_pista_activa(db_reproductor):
    datos = _crear_pista(db_reproductor, "tres")
    rep = _crear_reproductor()

    rep.reproducir_pista(datos)
    rep.siguiente()

    assert rep.estado == EstadoReproductor.DETENIDO

    rep.pausar_reanudar()

    assert rep.estado == EstadoReproductor.REPRODUCIENDO
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == "Pista tres"


def test_anterior_en_repetir_todo_envuelve_al_final_de_la_cola(db_reproductor):
    pista_uno = _crear_pista(db_reproductor, "cuatro")
    pista_dos = _crear_pista(db_reproductor, "cinco")
    rep = _crear_reproductor()

    rep.reproducir_cola([pista_uno, pista_dos], desde_indice=0)
    rep.set_modo_repeticion("todo")
    rep.anterior()

    assert rep.indice_cola == 1
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == "Pista cinco"


def test_aleatorio_reordena_cola_visible_y_siguiente_respeta_ese_orden(db_reproductor, monkeypatch):
    monkeypatch.setattr(reproductor_mod.random, "shuffle", lambda items: items.reverse())
    pistas = [
        _crear_pista(db_reproductor, "seis"),
        _crear_pista(db_reproductor, "siete"),
        _crear_pista(db_reproductor, "ocho"),
        _crear_pista(db_reproductor, "nueve"),
    ]
    rep = _crear_reproductor()

    rep.reproducir_cola(pistas, desde_indice=1)
    rep.set_aleatorio(True)

    titulos_cola = [p["titulo"] for p in rep.obtener_cola()]
    assert titulos_cola == ["Pista siete", "Pista nueve", "Pista ocho", "Pista seis"]
    assert rep.indice_cola == 0

    rep.siguiente()

    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == "Pista nueve"


def test_desactivar_aleatorio_restaura_orden_original_restante(db_reproductor, monkeypatch):
    monkeypatch.setattr(reproductor_mod.random, "shuffle", lambda items: items.reverse())
    pistas = [
        _crear_pista(db_reproductor, "shuffle-off-a"),
        _crear_pista(db_reproductor, "shuffle-off-b"),
        _crear_pista(db_reproductor, "shuffle-off-c"),
        _crear_pista(db_reproductor, "shuffle-off-d"),
    ]
    rep = _crear_reproductor()

    rep.reproducir_cola(pistas, desde_indice=1)
    rep.set_aleatorio(True)
    rep.set_aleatorio(False)

    assert [p["titulo"] for p in rep.obtener_cola()] == [
        pista["titulo"] for pista in pistas
    ]
    assert rep.indice_cola == 1
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pistas[1]["titulo"]


def test_desactivar_aleatorio_no_revive_pistas_consumidas(db_reproductor, monkeypatch):
    monkeypatch.setattr(reproductor_mod.random, "shuffle", lambda items: items.reverse())
    pistas = [
        _crear_pista(db_reproductor, "shuffle-consume-a"),
        _crear_pista(db_reproductor, "shuffle-consume-b"),
        _crear_pista(db_reproductor, "shuffle-consume-c"),
        _crear_pista(db_reproductor, "shuffle-consume-d"),
    ]
    rep = _crear_reproductor()

    rep.reproducir_cola(pistas, desde_indice=1)
    rep.set_aleatorio(True)
    rep._avanzar_tras_fin_pista()
    rep.set_aleatorio(False)

    assert [p["titulo"] for p in rep.obtener_cola()] == [
        pistas[0]["titulo"],
        pistas[2]["titulo"],
        pistas[3]["titulo"],
    ]
    assert rep.indice_cola == 2
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pistas[3]["titulo"]


def test_modelo_buscar_posicion_actualiza_progreso_inmediato(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    datos = _crear_pista(db_reproductor, "seek")
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    rep.reproducir_pista(datos)
    modelo.buscar_posicion(30)

    assert modelo.posicion_seg == 30
    assert modelo.duracion_seg == 120
    assert modelo.progreso_ratio == pytest.approx(0.25)


def test_modelo_buscar_posicion_clampa_fuera_de_rango(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    datos = _crear_pista(db_reproductor, "seek-clamp")
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    rep.reproducir_pista(datos)

    modelo.buscar_posicion(-25)
    assert modelo.posicion_seg == 0
    assert modelo.progreso_ratio == 0

    modelo.buscar_posicion(999)
    assert modelo.posicion_seg == 120
    assert modelo.progreso_ratio == 1


def test_modelo_buscar_posicion_con_duracion_desconocida_no_avanza(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    datos = _crear_pista(db_reproductor, "seek-no-duration", duracion_seg=0)
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    rep.reproducir_pista(datos)
    modelo.buscar_posicion(45)

    assert modelo.posicion_seg == 0
    assert modelo.duracion_seg == 0
    assert modelo.progreso_ratio == 0


def test_modelo_progreso_ratio_no_lanza_con_estado_corrupto(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)
    modelo._pos_seg = float("nan")
    modelo._dur_seg = "no-numero"

    assert modelo.posicion_seg == 0
    assert modelo.duracion_seg == 0
    assert modelo.progreso_ratio == 0


def test_modelo_set_volumen_clampa_rango(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    modelo.set_volumen(-25)
    assert rep.volumen == 0
    assert modelo.volumen == 0

    modelo.set_volumen(140)
    assert rep.volumen == 100
    assert modelo.volumen == 100


def test_modelo_progreso_reportado_no_supera_duracion_real(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    datos = _crear_pista(db_reproductor, "progress-clamp", duracion_seg=299)
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    rep.reproducir_pista(datos)
    modelo._al_progreso(300, 299)

    assert modelo.posicion_seg == 299
    assert modelo.duracion_seg == 299
    assert modelo.progreso_ratio == 1
    assert modelo.formatear_tiempo(modelo.posicion_seg) == "4:59"


def test_modelo_formatea_tiempos_con_duracion_canonica(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    assert modelo.formatear_tiempo(180) == "3:00"
    assert modelo.formatear_tiempo(179.6) == "3:00"
    assert modelo.formatear_tiempo(174) == "2:54"
    assert modelo.formatear_tiempo(299) == "4:59"


def test_modelo_lyrics_mood_fallback_estable_y_en_rango(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    datos = _crear_pista(db_reproductor, "mood-fallback", portada="")
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    rep.reproducir_pista(datos)

    mood_uno = modelo.lyrics_mood
    mood_dos = modelo.lyrics_mood

    assert mood_uno == mood_dos
    assert 0 <= mood_uno["h"] <= 1
    assert 0 <= mood_uno["s"] <= 1
    assert 0 <= mood_uno["l"] <= 1


def test_modelo_lyrics_mood_usa_color_dominante_de_portada(db_reproductor):
    qtgui = pytest.importorskip("PySide6.QtGui")
    from ui.modelos_qml import ModeloReproductor

    portada = db_reproductor / "portada-roja.png"
    imagen = qtgui.QImage(32, 32, qtgui.QImage.Format_RGB32)
    imagen.fill(qtgui.QColor("#e3312c"))
    assert imagen.save(str(portada))

    datos = _crear_pista(db_reproductor, "mood-portada", portada=str(portada))
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    rep.reproducir_pista(datos)

    mood = modelo.lyrics_mood
    assert mood["h"] < 0.08 or mood["h"] > 0.92
    assert 0.34 <= mood["s"] <= 0.70
    assert 0.16 <= mood["l"] <= 0.31


def test_modelo_mood_visual_es_alias_compatible_de_lyrics_mood(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    assert modelo.mood_visual == modelo.lyrics_mood


def test_modelo_lyrics_normaliza_synced_y_elimina_traduccion(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    lyrics = modelo._normalizar_lyrics_para_ui({
        "synced_lyrics": "[00:01.00]Hola mundo ^ Hello world\n[00:02]Siguiente verso",
        "plain_lyrics": "fallback",
    })

    assert lyrics == {
        "synced_lyrics": "[00:01.00]Hola mundo\n[00:02]Siguiente verso",
        "plain_lyrics": "",
    }


def test_modelo_lyrics_malformada_oculta_plain_fallback(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    lyrics = modelo._normalizar_lyrics_para_ui({
        "synced_lyrics": "[00:01.00]Linea valida\nLinea sin timestamp",
        "plain_lyrics": "Esta no debe mostrarse",
    })

    assert lyrics == {"synced_lyrics": "", "plain_lyrics": ""}


def test_modelo_lyrics_ignora_metadata_lrc_sin_invalidar(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    lyrics = modelo._normalizar_lyrics_para_ui({
        "synced_lyrics": "[ar:Artista]\n[ti:Tema]\n[offset:0]\n[00:03.500]Verso",
        "plain_lyrics": "",
    })

    assert lyrics["synced_lyrics"] == "[00:03.500]Verso"
    assert lyrics["plain_lyrics"] == ""


def test_modelo_lyrics_plain_sin_synced_se_sanitiza(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    lyrics = modelo._normalizar_lyrics_para_ui({
        "synced_lyrics": "",
        "plain_lyrics": "[ar:Artista]\nPrimera linea ^ Translation\n[00:02.00]Segunda linea",
    })

    assert lyrics == {
        "synced_lyrics": "",
        "plain_lyrics": "Primera linea\nSegunda linea",
    }


def test_modelo_lyrics_plain_tipo_documento_se_oculta(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)
    bloque = (
        "Esta letra viene como un documento pegado en un solo parrafo, con muchas frases, "
        "puntuacion, explicaciones, texto extendido y una estructura que no sirve como lyric "
        "normal para una vista sincronizada."
    )

    lyrics = modelo._normalizar_lyrics_para_ui({
        "synced_lyrics": "",
        "plain_lyrics": bloque,
    })

    assert lyrics == {"synced_lyrics": "", "plain_lyrics": ""}


def test_modelo_reproductor_expone_y_alterna_karaoke_lista(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    datos = _crear_pista(db_reproductor, "karaoke")
    instrumental = db_reproductor / "karaoke.instrumental.mp3"
    instrumental.write_bytes(b"fake instrumental")
    con = get_conexion()
    con.execute(
        """
        UPDATE pistas
        SET karaoke_estado = 'lista',
            karaoke_ruta_instrumental = ?
        WHERE id = ?
        """,
        (str(instrumental), datos["id"]),
    )

    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    rep.reproducir_pista(datos)

    assert modelo.karaoke_estado == "lista"
    assert modelo.karaoke_disponible is True
    assert modelo.karaoke_activo is False
    assert [p["titulo"] for p in rep.obtener_cola()] == [datos["titulo"]]
    assert rep.indice_cola == 0

    # Contrato CORRECTO del modo karaoke:
    #   - `ruta_archivo` es SIEMPRE la ruta logica original (la pista no cambia).
    #   - `ruta_audio_actual` indica que esta sirviendo VLC (None = original).
    #   - `karaoke_activo` refleja el estado funcional.
    # La pista logica es invariante para que lyrics/metadata sigan vigentes.
    assert modelo.alternar_karaoke() is True
    assert rep.pista_activa is not None
    assert rep.pista_activa.ruta_archivo == datos["ruta_archivo"]
    assert rep.pista_activa.ruta_audio_actual == str(instrumental)
    assert rep.pista_activa.fuente_audio_efectiva() == str(instrumental)
    assert modelo.karaoke_activo is True
    assert [p["titulo"] for p in rep.obtener_cola()] == [datos["titulo"]]
    assert rep.indice_cola == 0

    assert modelo.alternar_karaoke() is True
    assert rep.pista_activa is not None
    assert rep.pista_activa.ruta_archivo == datos["ruta_archivo"]
    assert rep.pista_activa.ruta_audio_actual is None
    assert rep.pista_activa.fuente_audio_efectiva() == datos["ruta_archivo"]
    assert modelo.karaoke_activo is False
    assert [p["titulo"] for p in rep.obtener_cola()] == [datos["titulo"]]
    assert rep.indice_cola == 0


def test_alternar_karaoke_preserva_lyrics_y_estado(db_reproductor, tmp_path, monkeypatch):
    """Al alternar karaoke la pista logica NO cambia y las lyrics asociadas
    a la ruta original siguen siendo recuperables."""
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor
    import json

    datos = _crear_pista(db_reproductor, "karaoke_lyrics")
    instrumental = db_reproductor / "karaoke_lyrics.instrumental.mp3"
    instrumental.write_bytes(b"fake instrumental")
    con = get_conexion()
    con.execute(
        "UPDATE pistas SET karaoke_estado='lista', karaoke_ruta_instrumental=? WHERE id=?",
        (str(instrumental), datos["id"]),
    )

    # Construir un manifest de enrichment con lyrics asociadas a la ruta ORIGINAL.
    manifest_dir = tmp_path / "enrichment"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = manifest_dir / "enrichment_manifest.jsonl"
    manifest.write_text(json.dumps({
        "file": str(datos["ruta_archivo"]),
        "lyrics": {
            "synced_lyrics": "[00:01.00] linea 1\n[00:02.00] linea 2",
            "plain_lyrics": "linea 1\nlinea 2",
        },
    }) + "\n", encoding="utf-8")

    rep = _crear_reproductor()
    # Apuntar el manifest del reproductor al de prueba.
    monkeypatch.setattr(rep, "_manifest_letras_ruta", manifest)
    rep._manifest_letras_mtime = -1.0
    rep._cache_letras = {}

    modelo = ModeloReproductor(rep)
    rep.reproducir_pista(datos)

    letra_original = rep.obtener_letra_pista_activa()
    assert "linea 1" in letra_original

    # Alternar karaoke: lyrics deben seguir disponibles.
    assert modelo.alternar_karaoke() is True
    assert modelo.karaoke_activo is True
    letra_kar = rep.obtener_letra_pista_activa()
    assert letra_kar == letra_original, "Las lyrics deben preservarse en modo karaoke"

    # Volver a original: lyrics siguen.
    assert modelo.alternar_karaoke() is True
    assert modelo.karaoke_activo is False
    assert rep.obtener_letra_pista_activa() == letra_original


def test_modelo_reproductor_oculta_karaoke_si_no_esta_lista(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    datos = _crear_pista(db_reproductor, "karaoke-no-lista")
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    rep.reproducir_pista(datos)

    assert modelo.karaoke_estado == "no_procesada"
    assert modelo.karaoke_disponible is False
    assert modelo.alternar_karaoke() is False


def test_sorprenderme_devuelve_true_y_reproduce_sin_pista_activa(db_reproductor, monkeypatch):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    pista = _crear_pista(db_reproductor, "sorp-sin-activa")
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    monkeypatch.setattr(svc_bib, "listar_pistas", lambda **kwargs: [pista])
    import ui.modelos_qml as modelos_qml
    monkeypatch.setattr(modelos_qml.random, "choice", lambda items: items[0])
    monkeypatch.setattr(modelos_qml.random, "random", lambda: 0.1)

    assert modelo.sorprenderme() is True
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista["titulo"]
    assert [p["titulo"] for p in rep.obtener_cola()] == [pista["titulo"]]
    assert rep.indice_cola == 0
    assert modelo.sorpresa_activa is True


def test_sorprenderme_reproduce_inmediato_aun_con_reproduccion_activa(db_reproductor, monkeypatch):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    pista_a = _crear_pista(db_reproductor, "sorp-a")
    pista_b = _crear_pista(db_reproductor, "sorp-b")

    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    rep.reproducir_pista(pista_a)

    monkeypatch.setattr(svc_bib, "listar_pistas", lambda **kwargs: [pista_a, pista_b])
    import ui.modelos_qml as modelos_qml
    monkeypatch.setattr(modelos_qml.random, "choice", lambda items: items[-1])
    monkeypatch.setattr(modelos_qml.random, "random", lambda: 0.1)

    assert modelo.sorprenderme() is True

    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_b["titulo"]
    assert [p["titulo"] for p in rep.obtener_cola()] == [pista_b["titulo"]]
    assert rep.indice_cola == 0
    assert modelo.sorpresa_activa is True


def test_sorprenderme_devuelve_false_sin_candidatas_validas(db_reproductor, monkeypatch):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    pista_invalida = {
        "id": 999,
        "titulo": "Invalida",
        "artista_nombre": "Nadie",
        "album_titulo": "Nada",
        "ruta_archivo": str(db_reproductor / "no-existe.mp3"),
        "duracion_seg": 120,
    }
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    monkeypatch.setattr(svc_bib, "listar_pistas", lambda **kwargs: [pista_invalida])

    assert modelo.sorprenderme() is False
    assert rep.pista_activa is None
    assert modelo.sorpresa_activa is False


def test_sorpresa_activa_se_limpia_al_finalizar_o_reproducir_normal(db_reproductor, monkeypatch):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    pista_sorpresa = _crear_pista(db_reproductor, "sorp-activa")
    pista_normal = _crear_pista(db_reproductor, "normal-limpia")
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    monkeypatch.setattr(svc_bib, "listar_pistas", lambda **kwargs: [pista_sorpresa, pista_normal])
    import ui.modelos_qml as modelos_qml
    monkeypatch.setattr(modelos_qml.random, "random", lambda: 0.0)

    assert modelo.sorprenderme() is True
    assert modelo.sorpresa_activa is True

    rep._avanzar_tras_fin_pista()

    assert modelo.sorpresa_activa is False

    assert modelo.sorprenderme() is True
    assert modelo.sorpresa_activa is True

    modelo.reproducir(pista_normal)

    assert rep.pista_activa is not None
    assert rep.pista_activa.id == pista_normal["id"]
    assert modelo.sorpresa_activa is False


def test_sorpresa_activa_se_mantiene_en_sorpresas_consecutivas(db_reproductor, monkeypatch):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    pistas = [
        _crear_pista(db_reproductor, "sorp-consecutiva-a"),
        _crear_pista(db_reproductor, "sorp-consecutiva-b"),
        _crear_pista(db_reproductor, "sorp-consecutiva-c"),
    ]
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    monkeypatch.setattr(svc_bib, "listar_pistas", lambda **kwargs: pistas)
    import ui.modelos_qml as modelos_qml
    monkeypatch.setattr(modelos_qml.random, "random", lambda: 0.0)

    assert modelo.sorprenderme() is True
    primera = rep.pista_activa.id
    assert modelo.sorpresa_activa is True

    assert modelo.sorprenderme() is True

    assert rep.pista_activa is not None
    assert rep.pista_activa.id != primera
    assert modelo.sorpresa_activa is True
    assert modelo.cola.total == 1
    assert modelo.cola.obtener(0)["id"] == rep.pista_activa.id


def test_sorprenderme_diversifica_artistas_y_albums_con_alternativas(db_reproductor, monkeypatch):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    actual = _crear_pista(db_reproductor, "sorp-actual")
    mala_a = _crear_pista(db_reproductor, "sorp-bad-a")
    mala_b = _crear_pista(db_reproductor, "sorp-bad-b")
    alt_a = _crear_pista(db_reproductor, "sorp-alt-a")
    alt_b = _crear_pista(db_reproductor, "sorp-alt-b")

    for pista in (actual, mala_a, mala_b):
        pista["artista_nombre"] = "Bad Bunny"
        pista["album_titulo"] = "Album repetido"
    alt_a["artista_nombre"] = "Artista Alternativa A"
    alt_a["album_titulo"] = "Album Alternativo A"
    alt_b["artista_nombre"] = "Artista Alternativa B"
    alt_b["album_titulo"] = "Album Alternativo B"

    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)
    rep.reproducir_pista(actual)

    monkeypatch.setattr(
        svc_bib,
        "listar_pistas",
        lambda **kwargs: [actual, mala_a, mala_b, alt_a, alt_b],
    )
    import ui.modelos_qml as modelos_qml
    monkeypatch.setattr(modelos_qml.random, "random", lambda: 0.0)

    assert modelo.sorprenderme() is True
    primera = rep.pista_activa
    assert primera is not None
    assert primera.artista == "Artista Alternativa A"

    assert modelo.sorprenderme() is True
    segunda = rep.pista_activa
    assert segunda is not None
    assert segunda.artista == "Artista Alternativa B"


def test_sorprenderme_funciona_si_toda_la_biblioteca_es_del_mismo_artista(db_reproductor, monkeypatch):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    pista_a = _crear_pista(db_reproductor, "sorp-same-a")
    pista_b = _crear_pista(db_reproductor, "sorp-same-b")
    for pista in (pista_a, pista_b):
        pista["artista_nombre"] = "Mismo Artista"
        pista["album_titulo"] = "Mismo Album"

    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    monkeypatch.setattr(svc_bib, "listar_pistas", lambda **kwargs: [pista_a, pista_b])
    import ui.modelos_qml as modelos_qml
    monkeypatch.setattr(modelos_qml.random, "random", lambda: 0.0)

    assert modelo.sorprenderme() is True
    primera_id = rep.pista_activa.id
    assert modelo.sorprenderme() is True
    assert rep.pista_activa is not None
    assert rep.pista_activa.id != primera_id


def test_sorprenderme_no_repite_pistas_en_biblioteca_amplia(db_reproductor, monkeypatch):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    pistas = [_crear_pista(db_reproductor, f"sorp-wide-{indice}") for indice in range(60)]
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    monkeypatch.setattr(svc_bib, "listar_pistas", lambda **kwargs: pistas)
    import ui.modelos_qml as modelos_qml
    monkeypatch.setattr(modelos_qml.random, "random", lambda: 0.0)

    seleccionadas = []
    for _ in range(25):
        assert modelo.sorprenderme() is True
        assert rep.pista_activa is not None
        seleccionadas.append(rep.pista_activa.id)
        assert modelo.cola.total == 1
        assert modelo.cola.obtener(0)["id"] == rep.pista_activa.id

    assert len(seleccionadas) == len(set(seleccionadas))


def test_sorprenderme_evita_repetir_artista_si_hay_alternativas(db_reproductor, monkeypatch):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    pistas = []
    for indice in range(8):
        pista = _crear_pista(db_reproductor, f"sorp-artista-{indice}")
        pista["artista_nombre"] = f"Artista Alternativa {indice}"
        pista["album_titulo"] = f"Album Alternativo {indice}"
        pistas.append(pista)

    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    monkeypatch.setattr(svc_bib, "listar_pistas", lambda **kwargs: pistas)
    import ui.modelos_qml as modelos_qml
    monkeypatch.setattr(modelos_qml.random, "random", lambda: 0.0)

    artistas = []
    for _ in range(6):
        assert modelo.sorprenderme() is True
        assert rep.pista_activa is not None
        artistas.append(rep.pista_activa.artista)

    assert len(artistas) == len(set(artistas))


def test_modelo_reproductor_expone_duracion_total_de_cola(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    pista_a = _crear_pista(db_reproductor, "cola-dur-a", duracion_seg=90)
    pista_b = _crear_pista(db_reproductor, "cola-dur-b", duracion_seg=150)
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    rep.reproducir_cola([pista_a, pista_b], desde_indice=0)
    modelo.recargar_cola()

    assert modelo.duracion_cola_seg == 240


def test_modelo_duracion_cola_no_reentra_lock_del_reproductor(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor
    import threading

    pista_a = _crear_pista(db_reproductor, "cola-lock-a", duracion_seg=90)
    pista_b = _crear_pista(db_reproductor, "cola-lock-b", duracion_seg=150)
    rep = _crear_reproductor()

    rep.reproducir_cola([pista_a, pista_b], desde_indice=0)
    modelo = ModeloReproductor(rep)

    resultado = []
    errores = []

    def leer_duracion():
        try:
            resultado.append(modelo.duracion_cola_seg)
        except Exception as exc:  # pragma: no cover - evidencia de regresion
            errores.append(exc)

    rep._lock.acquire()
    try:
        hilo = threading.Thread(target=leer_duracion)
        hilo.start()
        hilo.join(0.25)
        bloqueo_detectado = hilo.is_alive()
    finally:
        rep._lock.release()

    hilo.join(1.0)

    assert not bloqueo_detectado
    assert errores == []
    assert resultado == [240]


def test_modelo_estadisticas_formatear_duracion_detallada():
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloEstadisticas

    modelo = ModeloEstadisticas()
    assert modelo.formatear_duracion_detallada(86400 + 3661) == "1d 1h 1m 1s"
    assert modelo.formatear_duracion_detallada(86400) == "1d"
    assert modelo.formatear_duracion_detallada(3661) == "1h 1m 1s"
    assert modelo.formatear_duracion_detallada(3600) == "1h"
    assert modelo.formatear_duracion_detallada(125) == "2m 5s"
    assert modelo.formatear_duracion_detallada(5) == "5s"
    assert modelo.formatear_duracion_detallada(0) == "0s"
    assert modelo.formatear_duracion_detallada(None) == "0s"


def test_modelo_reproductor_formatea_duracion_larga_para_cola(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    assert modelo.formatear_duracion_larga(3725) == "1h 2m 5s"
    assert modelo.formatear_duracion_larga(3600) == "1h 0m 0s"
    assert modelo.formatear_duracion_larga(65) == "1m 5s"
    assert modelo.formatear_duracion_larga(5) == "5s"
    assert modelo.formatear_duracion_larga(0) == "0s"
    assert modelo.formatear_duracion_larga(-12) == "0s"
    assert modelo.formatear_duracion_larga(None) == "0s"


def test_limpiar_cola_vacia_lista_sin_detener_pista_activa(db_reproductor):
    pista_a = _crear_pista(db_reproductor, "cola-clear-a")
    pista_b = _crear_pista(db_reproductor, "cola-clear-b")
    rep = _crear_reproductor()

    rep.reproducir_cola([pista_a, pista_b], desde_indice=0)
    rep.limpiar_cola()

    assert rep.obtener_cola() == []
    assert rep.estado == EstadoReproductor.REPRODUCIENDO
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_a["titulo"]


def test_vaciar_cola_mantener_actual_conserva_solo_fila_activa(db_reproductor):
    pista_a = _crear_pista(db_reproductor, "queue-clear-keep-a")
    pista_b = _crear_pista(db_reproductor, "queue-clear-keep-b")
    pista_c = _crear_pista(db_reproductor, "queue-clear-keep-c")
    rep = _crear_reproductor()

    rep.reproducir_cola([pista_a, pista_b, pista_c], desde_indice=1)
    rep.vaciar_cola_mantener_actual()

    assert [p["titulo"] for p in rep.obtener_cola()] == [pista_b["titulo"]]
    assert rep.indice_cola == 0
    assert rep.estado == EstadoReproductor.REPRODUCIENDO
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_b["titulo"]


def test_vaciar_cola_mantener_actual_vacia_si_no_hay_fila_activa(db_reproductor):
    pista_a = _crear_pista(db_reproductor, "queue-clear-idle-a")
    pista_b = _crear_pista(db_reproductor, "queue-clear-idle-b")
    rep = _crear_reproductor()

    rep.agregar_a_cola(pista_a)
    rep.agregar_a_cola(pista_b)
    rep.vaciar_cola_mantener_actual()

    assert rep.obtener_cola() == []
    assert rep.indice_cola == -1
    assert rep.pista_activa is None
    assert rep.estado == EstadoReproductor.DETENIDO


def test_quitar_unica_pista_activa_resetea_reproductor(db_reproductor):
    pista = _crear_pista(db_reproductor, "queue-remove-active-single")
    rep = _crear_reproductor()

    rep.reproducir_pista(pista)
    rep.quitar_de_cola(0)

    assert rep.obtener_cola() == []
    assert rep.pista_activa is None
    assert rep.indice_cola == -1
    assert rep.estado == EstadoReproductor.DETENIDO


def test_quitar_unica_pista_activa_pausada_resetea_reproductor(db_reproductor):
    pista = _crear_pista(db_reproductor, "queue-remove-paused-single")
    rep = _crear_reproductor()

    rep.reproducir_pista(pista)
    rep.pausar_reanudar()
    assert rep.estado == EstadoReproductor.PAUSADO

    rep.quitar_de_cola(0)

    assert rep.obtener_cola() == []
    assert rep.pista_activa is None
    assert rep.indice_cola == -1
    assert rep.estado == EstadoReproductor.DETENIDO


def test_quitar_pista_activa_con_mas_cola_reproduce_siguiente(db_reproductor):
    pista_a = _crear_pista(db_reproductor, "queue-remove-next-a")
    pista_b = _crear_pista(db_reproductor, "queue-remove-next-b")
    pista_c = _crear_pista(db_reproductor, "queue-remove-next-c")
    rep = _crear_reproductor()

    rep.reproducir_cola([pista_a, pista_b, pista_c], desde_indice=1)
    rep.quitar_de_cola(1)

    assert [p["titulo"] for p in rep.obtener_cola()] == [
        pista_a["titulo"],
        pista_c["titulo"],
    ]
    assert rep.indice_cola == 1
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_c["titulo"]
    assert rep.estado == EstadoReproductor.REPRODUCIENDO


def test_quitar_ultima_pista_activa_con_mas_cola_reproduce_anterior(db_reproductor):
    pista_a = _crear_pista(db_reproductor, "queue-remove-prev-a")
    pista_b = _crear_pista(db_reproductor, "queue-remove-prev-b")
    rep = _crear_reproductor()

    rep.reproducir_cola([pista_a, pista_b], desde_indice=1)
    rep.quitar_de_cola(1)

    assert [p["titulo"] for p in rep.obtener_cola()] == [pista_a["titulo"]]
    assert rep.indice_cola == 0
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_a["titulo"]
    assert rep.estado == EstadoReproductor.REPRODUCIENDO


def test_modelo_quitar_unica_pista_activa_limpia_barra_visual(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    pista = _crear_pista(db_reproductor, "queue-remove-model-active")
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    modelo.reproducir(pista)
    assert modelo.pista_activa["titulo"] == pista["titulo"]
    assert modelo.pista_visual["titulo"] == pista["titulo"]

    modelo.quitar_de_cola(0)

    assert modelo.cola.total == 0
    assert modelo.pista_activa == {}
    assert modelo.pista_visual == {}
    assert modelo.titulo_activo == ""
    assert modelo.artista_activo == ""
    assert modelo.album_activo == ""
    assert modelo.posicion_seg == 0
    assert modelo.progreso_ratio == 0


def test_modelo_vaciar_cola_mantener_actual_sincroniza_cola_visible(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    pista_a = _crear_pista(db_reproductor, "queue-clear-model-a")
    pista_b = _crear_pista(db_reproductor, "queue-clear-model-b")
    pista_c = _crear_pista(db_reproductor, "queue-clear-model-c")
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    modelo.reproducir_cola_desde_pistas([pista_a, pista_b, pista_c], 1)
    modelo.vaciar_cola_mantener_actual()

    assert modelo.cola.total == 1
    assert modelo.indice_cola == 0
    assert modelo.cola.obtener(0)["titulo"] == pista_b["titulo"]
    assert modelo.pista_activa["titulo"] == pista_b["titulo"]
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_b["titulo"]


def test_modelo_reproductor_agrega_varias_a_cola_en_una_operacion(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    pista_a = _crear_pista(db_reproductor, "queue-bulk-model-a")
    pista_b = _crear_pista(db_reproductor, "queue-bulk-model-b")
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    modelo.agregar_varias_a_cola([pista_a, pista_b])

    assert modelo.cola.total == 2
    assert modelo.cola.obtener(0)["titulo"] == pista_a["titulo"]
    assert modelo.cola.obtener(1)["titulo"] == pista_b["titulo"]


def test_modelo_quitar_unica_pista_sin_iniciar_limpia_pista_visual(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    pista = _crear_pista(db_reproductor, "queue-remove-model-idle")
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    modelo.agregar_a_cola(pista)
    assert rep.pista_activa is None
    assert modelo.pista_visual["titulo"] == pista["titulo"]

    modelo.quitar_de_cola(0)

    assert modelo.cola.total == 0
    assert modelo.pista_activa == {}
    assert modelo.pista_visual == {}


def test_controles_sin_pista_y_cola_vacia_no_rompen_estado(db_reproductor):
    rep = _crear_reproductor()

    rep.pausar_reanudar()
    rep.siguiente()
    rep.anterior()
    rep.limpiar_cola()
    rep.quitar_de_cola(0)
    rep.set_aleatorio(True)
    rep.set_modo_repeticion("todo")
    rep.siguiente()

    assert rep.estado == EstadoReproductor.DETENIDO
    assert rep.pista_activa is None
    assert rep.obtener_cola() == []
    assert rep.es_aleatorio is True
    assert rep.modo_repeticion == "todo"


def test_reproductor_pista_inexistente_emite_warning_y_estado_error(db_reproductor):
    rep = _crear_reproductor()
    avisos = []
    rep.on_aviso(avisos.append)
    pista = {
        "id": 9999,
        "titulo": "No existe",
        "artista_nombre": "Nadie",
        "album_titulo": "Ninguno",
        "ruta_archivo": str(db_reproductor / "missing.mp3"),
        "duracion_seg": 180,
    }

    rep.reproducir_pista(pista)

    assert rep.estado == EstadoReproductor.ERROR
    assert rep.pista_activa is None
    assert rep.obtener_cola() == []
    assert rep.indice_cola == -1
    assert avisos[-1]["nivel"] == "warning"
    assert avisos[-1]["codigo"] == "pista_no_encontrada"


def test_reproductor_error_de_backend_audio_no_bloquea_ui(db_reproductor):
    class FakeInstancia:
        def media_new(self, ruta):
            return {"ruta": ruta}

    class FakeMediaPlayer:
        def set_media(self, media):
            self.media = media

        def audio_set_volume(self, volumen):
            self.volumen = volumen

        def play(self):
            raise RuntimeError("audio corrupto")

    pista = _crear_pista(db_reproductor, "audio-corrupto")
    rep = _crear_reproductor()
    rep._instancia_vlc = FakeInstancia()
    rep._media_player = FakeMediaPlayer()

    rep.reproducir_pista(pista)

    assert rep.estado == EstadoReproductor.ERROR
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista["titulo"]
    assert [p["titulo"] for p in rep.obtener_cola()] == [pista["titulo"]]
    assert rep.indice_cola == 0


def test_reproductor_error_backend_emite_warning(db_reproductor):
    class FakeInstancia:
        def media_new(self, ruta):
            return {"ruta": ruta}

    class FakeMediaPlayer:
        def set_media(self, media):
            self.media = media

        def audio_set_volume(self, volumen):
            self.volumen = volumen

        def play(self):
            raise RuntimeError("audio corrupto")

    pista = _crear_pista(db_reproductor, "audio-warning")
    rep = _crear_reproductor()
    rep._instancia_vlc = FakeInstancia()
    rep._media_player = FakeMediaPlayer()
    avisos = []
    rep.on_aviso(avisos.append)

    rep.reproducir_pista(pista)

    assert rep.estado == EstadoReproductor.ERROR
    assert avisos[-1]["nivel"] == "warning"
    assert avisos[-1]["codigo"] == "playback_fallido"


def test_reproductor_sin_vlc_real_emite_error_critico_retenido(db_reproductor, monkeypatch):
    monkeypatch.setattr(reproductor_mod, "VLC_DISPONIBLE", False)
    monkeypatch.setattr(
        reproductor_mod.Reproductor,
        "_inicializar_vlc",
        _ORIGINAL_INICIALIZAR_VLC,
    )
    rep = Reproductor(permitir_modo_simulado=False)
    avisos = []

    rep.on_aviso(avisos.append)

    assert avisos
    assert avisos[-1]["nivel"] == "critical"
    assert avisos[-1]["codigo"] == "vlc_no_disponible"
    assert avisos[-1]["soluciones"]


def test_repetir_uno_no_consume_cola_al_finalizar(db_reproductor):
    pista_a = _crear_pista(db_reproductor, "repeat-one-a")
    pista_b = _crear_pista(db_reproductor, "repeat-one-b")
    rep = _crear_reproductor()

    rep.reproducir_cola([pista_a, pista_b], desde_indice=0)
    rep.set_modo_repeticion("uno")
    rep._avanzar_tras_fin_pista()

    assert [p["titulo"] for p in rep.obtener_cola()] == [
        pista_a["titulo"],
        pista_b["titulo"],
    ]
    assert rep.indice_cola == 0
    assert rep.estado == EstadoReproductor.REPRODUCIENDO
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_a["titulo"]


def test_repetir_todo_reconstruye_contexto_al_consumir_ultima_pista(db_reproductor):
    pista_a = _crear_pista(db_reproductor, "repeat-all-a")
    pista_b = _crear_pista(db_reproductor, "repeat-all-b")
    rep = _crear_reproductor()

    rep.reproducir_cola([pista_a, pista_b], desde_indice=0)
    rep.set_modo_repeticion("todo")
    rep._avanzar_tras_fin_pista()
    rep._avanzar_tras_fin_pista()

    assert [p["titulo"] for p in rep.obtener_cola()] == [
        pista_a["titulo"],
        pista_b["titulo"],
    ]
    assert rep.indice_cola == 0
    assert rep.estado == EstadoReproductor.REPRODUCIENDO
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_a["titulo"]


def test_repetir_todo_no_revive_contexto_tras_limpiar_cola(db_reproductor):
    pista_a = _crear_pista(db_reproductor, "repeat-clear-a")
    pista_b = _crear_pista(db_reproductor, "repeat-clear-b")
    rep = _crear_reproductor()

    rep.reproducir_cola([pista_a, pista_b], desde_indice=0)
    rep.set_modo_repeticion("todo")
    rep.limpiar_cola()
    rep._avanzar_tras_fin_pista()

    assert rep.obtener_cola() == []
    assert rep.indice_cola == -1
    assert rep.pista_activa is None
    assert rep.estado == EstadoReproductor.FINALIZADA


def test_repetir_todo_contexto_respeta_reorden_manual(db_reproductor):
    pista_a = _crear_pista(db_reproductor, "repeat-move-a")
    pista_b = _crear_pista(db_reproductor, "repeat-move-b")
    pista_c = _crear_pista(db_reproductor, "repeat-move-c")
    rep = _crear_reproductor()

    rep.reproducir_cola([pista_a, pista_b, pista_c], desde_indice=1)
    rep.mover_en_cola(2, 0)
    rep.set_modo_repeticion("todo")
    rep._avanzar_tras_fin_pista()
    rep._avanzar_tras_fin_pista()
    rep._avanzar_tras_fin_pista()

    assert [p["titulo"] for p in rep.obtener_cola()] == [
        pista_c["titulo"],
        pista_a["titulo"],
        pista_b["titulo"],
    ]
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_c["titulo"]


def test_repetir_todo_no_reintroduce_pista_quitada(db_reproductor):
    pista_a = _crear_pista(db_reproductor, "repeat-remove-a")
    pista_b = _crear_pista(db_reproductor, "repeat-remove-b")
    pista_c = _crear_pista(db_reproductor, "repeat-remove-c")
    rep = _crear_reproductor()

    rep.reproducir_cola([pista_a, pista_b, pista_c], desde_indice=0)
    rep.quitar_de_cola(1)
    rep.set_modo_repeticion("todo")
    rep._avanzar_tras_fin_pista()
    rep._avanzar_tras_fin_pista()

    assert [p["titulo"] for p in rep.obtener_cola()] == [
        pista_a["titulo"],
        pista_c["titulo"],
    ]
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_a["titulo"]


def test_reproducir_pista_individual_reemplaza_cola_previa(db_reproductor):
    pista_a = _crear_pista(db_reproductor, "individual-a")
    pista_b = _crear_pista(db_reproductor, "individual-b")
    pista_c = _crear_pista(db_reproductor, "individual-c")
    rep = _crear_reproductor()

    rep.agregar_a_cola(pista_b)
    rep.agregar_a_cola(pista_c)
    rep.reproducir_pista(pista_a)

    assert [p["titulo"] for p in rep.obtener_cola()] == [pista_a["titulo"]]
    assert rep.indice_cola == 0
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_a["titulo"]


def test_modelo_reproducir_pista_individual_actualiza_cola_visible(db_reproductor):
    pytest.importorskip("PySide6")
    from ui.modelos_qml import ModeloReproductor

    pista = _crear_pista(db_reproductor, "modelo-individual")
    rep = _crear_reproductor()
    modelo = ModeloReproductor(rep)

    modelo.reproducir(pista)

    assert modelo.cola.total == 1
    assert modelo.indice_cola == 0
    assert modelo.cola.obtener(0)["titulo"] == pista["titulo"]


def test_reproducir_pista_existente_en_cola_reemplaza_sin_duplicar(db_reproductor):
    pista_a = _crear_pista(db_reproductor, "individual-existing-a")
    pista_b = _crear_pista(db_reproductor, "individual-existing-b")
    pista_c = _crear_pista(db_reproductor, "individual-existing-c")
    rep = _crear_reproductor()

    rep.agregar_a_cola(pista_a)
    rep.agregar_a_cola(pista_b)
    rep.agregar_a_cola(pista_c)
    rep.reproducir_pista(pista_b)

    assert [p["titulo"] for p in rep.obtener_cola()] == [pista_b["titulo"]]
    assert rep.indice_cola == 0
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_b["titulo"]


def test_reproducir_cola_conserva_contexto_completo(db_reproductor):
    pista_a = _crear_pista(db_reproductor, "context-a")
    pista_b = _crear_pista(db_reproductor, "context-b")
    pista_c = _crear_pista(db_reproductor, "context-c")
    rep = _crear_reproductor()

    rep.reproducir_cola([pista_a, pista_b, pista_c], desde_indice=1)

    assert [p["titulo"] for p in rep.obtener_cola()] == [
        pista_a["titulo"],
        pista_b["titulo"],
        pista_c["titulo"],
    ]
    assert rep.indice_cola == 1
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_b["titulo"]


def test_reproductor_consume_pista_de_cola_al_finalizar_y_avanza(db_reproductor):
    pista_a = _crear_pista(db_reproductor, "cola-finish-a")
    pista_b = _crear_pista(db_reproductor, "cola-finish-b")
    rep = _crear_reproductor()

    rep.reproducir_cola([pista_a, pista_b], desde_indice=0)
    rep._avanzar_tras_fin_pista()

    assert [p["titulo"] for p in rep.obtener_cola()] == [pista_b["titulo"]]
    assert rep.indice_cola == 0
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_b["titulo"]


def test_reproductor_consume_pista_individual_y_limpia_cola(db_reproductor):
    individual = _crear_pista(db_reproductor, "single-finish")
    pista_a = _crear_pista(db_reproductor, "single-prev-a")
    pista_b = _crear_pista(db_reproductor, "single-prev-b")
    rep = _crear_reproductor()

    rep.agregar_a_cola(pista_a)
    rep.agregar_a_cola(pista_b)
    rep.reproducir_pista(individual)
    rep._avanzar_tras_fin_pista()

    assert rep.obtener_cola() == []
    assert rep.indice_cola == -1
    assert rep.pista_activa is None
    assert rep.estado == EstadoReproductor.FINALIZADA


def test_reproductor_activa_primera_cola_al_terminar_pista_individual(db_reproductor):
    individual = _crear_pista(db_reproductor, "cola-after-individual")
    pista_a = _crear_pista(db_reproductor, "cola-next-a")
    pista_b = _crear_pista(db_reproductor, "cola-next-b")
    rep = _crear_reproductor()

    rep.reproducir_pista(individual)
    rep.agregar_a_cola(pista_a)
    rep.agregar_a_cola(pista_b)
    rep._avanzar_tras_fin_pista()

    assert [p["titulo"] for p in rep.obtener_cola()] == [
        pista_a["titulo"],
        pista_b["titulo"],
    ]
    assert rep.indice_cola == 0
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_a["titulo"]


def test_reproducir_indice_cola_reproduce_sin_reconstruir_orden(db_reproductor):
    pista_a = _crear_pista(db_reproductor, "cola-play-a")
    pista_b = _crear_pista(db_reproductor, "cola-play-b")
    pista_c = _crear_pista(db_reproductor, "cola-play-c")
    rep = _crear_reproductor()

    rep.reproducir_cola([pista_a, pista_b, pista_c], desde_indice=0)

    assert rep.reproducir_indice_cola(2) is True
    assert [p["titulo"] for p in rep.obtener_cola()] == [
        pista_a["titulo"],
        pista_b["titulo"],
        pista_c["titulo"],
    ]
    assert rep.indice_cola == 2
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_c["titulo"]


def test_reproducir_indice_cola_invalido_no_cambia_estado(db_reproductor):
    pista_a = _crear_pista(db_reproductor, "cola-invalid-a")
    pista_b = _crear_pista(db_reproductor, "cola-invalid-b")
    rep = _crear_reproductor()

    rep.reproducir_cola([pista_a, pista_b], desde_indice=1)

    assert rep.reproducir_indice_cola(-1) is False
    assert rep.reproducir_indice_cola(9) is False
    assert [p["titulo"] for p in rep.obtener_cola()] == [
        pista_a["titulo"],
        pista_b["titulo"],
    ]
    assert rep.indice_cola == 1
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_b["titulo"]


def test_mover_en_cola_reordena_y_preserva_indice_activo(db_reproductor):
    pista_a = _crear_pista(db_reproductor, "cola-move-a")
    pista_b = _crear_pista(db_reproductor, "cola-move-b")
    pista_c = _crear_pista(db_reproductor, "cola-move-c")
    rep = _crear_reproductor()

    rep.reproducir_cola([pista_a, pista_b, pista_c], desde_indice=1)
    rep.mover_en_cola(2, 0)

    assert [p["titulo"] for p in rep.obtener_cola()] == [
        pista_c["titulo"],
        pista_a["titulo"],
        pista_b["titulo"],
    ]
    assert rep.indice_cola == 2
    assert rep.pista_activa is not None
    assert rep.pista_activa.titulo == pista_b["titulo"]


def test_reproductor_permite_desregistrar_callbacks_de_progreso_y_estado(db_reproductor):
    rep = _crear_reproductor()

    cb_progreso = lambda pos, dur: None
    cb_estado = lambda estado, pista: None
    cb_aviso = lambda aviso: None

    rep.on_progreso(cb_progreso)
    rep.on_estado(cb_estado)
    rep.on_aviso(cb_aviso)

    assert cb_progreso in rep._cb_progreso
    assert cb_estado in rep._cb_estado
    assert cb_aviso in rep._cb_aviso

    rep.off_progreso(cb_progreso)
    rep.off_estado(cb_estado)
    rep.off_aviso(cb_aviso)

    assert cb_progreso not in rep._cb_progreso
    assert cb_estado not in rep._cb_estado
    assert cb_aviso not in rep._cb_aviso


def test_qml_no_declara_tooltips_visibles():
    qml_dir = Path("ui/qml")
    usos = [
        str(ruta)
        for ruta in qml_dir.rglob("*.qml")
        if "ToolTip" in ruta.read_text(encoding="utf-8")
    ]

    assert usos == []


def test_qml_barra_no_muestra_toast_exito_sorpresa():
    barra = Path("ui/qml/componentes/BarraReproduccion.qml").read_text(encoding="utf-8")

    assert "Sorpresa lista" not in barra


def test_qml_lyrics_overlay_no_reacomoda_con_barra_y_sync_es_fijo():
    principal = Path("ui/qml/Principal.qml").read_text(encoding="utf-8")
    lyrics = Path("ui/qml/vistas/VistaLyrics.qml").read_text(encoding="utf-8")
    barra = Path("ui/qml/componentes/BarraReproduccion.qml").read_text(encoding="utf-8")

    assert "anchors.bottomMargin: barra_lyrics.opacity * barra_lyrics.height" not in principal
    assert "anchors.bottomMargin: 0" in principal
    assert "id: barra_lyrics_cortina" in principal
    assert "id: barra_lyrics_wrapper" in principal
    assert "id: barra_lyrics_fade_izquierdo" in principal
    assert "id: barra_lyrics_fade_derecho" in principal
    assert "anchors.horizontalCenter: parent.horizontalCenter" in principal
    assert "property real barra_reveal_width" in principal
    assert "readonly property string overlay_reproductor_modo" in principal
    assert "readonly property bool overlay_en_fullscreen" in principal
    assert "readonly property real ancho_barra_objetivo: width" in principal
    assert "readonly property real barra_offset_y" in principal
    assert "function alternar_lyrics_en_fullscreen()" in principal
    assert "function cerrar_colas_reproductor()" in principal
    assert "barra_principal.cerrar_cola()" in principal
    assert "barra_lyrics.cerrar_cola()" in principal
    assert "function _actualizar_barra_overlay_por_modo(forzarReveal)" in principal
    assert "function _entrar_overlay_normal_con_reveal()" in principal
    assert "function _entrar_o_cambiar_fullscreen_sin_reveal(mostrarBarra)" in principal
    assert "function _conservar_barra_visible_temporalmente()" in principal
    assert "function _salir_overlay()" in principal
    assert "_fijar_barra_overlay_sin_reveal" not in principal
    assert "onOverlay_modoChanged:" in principal
    assert "ventana_principal.cerrar_colas_reproductor()" in principal
    assert "_entrar_o_cambiar_fullscreen_sin_reveal(false)" in principal
    assert "_entrar_o_cambiar_fullscreen_sin_reveal(true)" in principal
    assert "_conservar_barra_visible_temporalmente()" in principal
    assert "barra_visible = true" in principal
    assert "y: overlay_lyrics.barra_base_y + overlay_lyrics.barra_offset_y" in principal
    assert "ancho_barra_revelada" not in principal
    assert "Behavior on x" not in principal
    assert "function cerrar_cola()" in barra
    assert "shell.alternar_lyrics_en_fullscreen()" in barra
    assert "positionViewAtIndex(indice_activo, ListView.Center)" in lyrics
    assert "property bool modo_fullscreen" in lyrics
    assert "property bool seguimiento_activo" in lyrics
    assert "property bool usuario_desplazo_letra" in lyrics
    assert "property bool sync_forzado" in lyrics
    assert "function _activar_sync_forzado()" in lyrics
    assert "id: liberar_sync_forzado" in lyrics
    assert "id: ventana_sync_usuario" in lyrics
    assert "readonly property int transicion_verso_ms: 280" in lyrics
    assert "readonly property int transicion_scroll_verso_ms: 360" in lyrics
    assert "mapToItem(ventana_sync_usuario" in lyrics
    assert "ventana_visible_inicio_ratio" in lyrics
    assert "currentIndex: -1" in lyrics
    assert "currentIndex: raiz.indice_activo" not in lyrics
    assert "highlightFollowsCurrentItem: false" in lyrics
    assert "highlightRangeMode: ListView.NoHighlightRange" in lyrics
    assert lyrics.count("positionViewAtIndex(") == 2
    assert "duration: raiz.transicion_scroll_verso_ms" in lyrics
    assert "realce_transicion" not in lyrics
    assert "? 1.15" in lyrics
    assert "font.weight: esActual ? Font.Bold : Font.DemiBold" in lyrics
    assert "Font.ExtraBold" not in lyrics
    assert lyrics.count("duration: raiz.transicion_verso_ms") >= 2
    assert "if (!forzado && usuario_desplazo_letra)" in lyrics
    assert "if (!raiz.sync_forzado)" in lyrics
    assert "seguimiento_activo && !usuario_desplazo_letra" not in lyrics
    assert "_verso_activo_en_ventana_usuario(8) && !lista_sync.moving" not in lyrics
    assert "reproductor.buscar_posicion(modelData.t)" in lyrics
    assert "reproductor.letra_plain_activa" not in lyrics
    assert "raiz.letra_plain" not in lyrics
    assert "visible: !modo_fullscreen" in lyrics
    assert "Layout.preferredWidth: visible ? 40 : 0" in lyrics
    assert "shell.cerrar_vista_lyrics()" in lyrics
    assert "raiz.sync_forzado = false" not in lyrics.replace("onTriggered: raiz.sync_forzado = false", "")
    assert "altura_barra_reproduccion" in lyrics
    assert "../assets/icons/sync.svg" in lyrics


def test_qml_fullscreen_info_usa_mood_visual_y_salida_limpia():
    principal = Path("ui/qml/Principal.qml").read_text(encoding="utf-8")
    fullscreen = Path("ui/qml/vistas/VistaReproduccionExpandida.qml").read_text(encoding="utf-8")

    assert "function salir_fullscreen_reproductor(conservarLyrics)" in principal
    assert "ventana_principal.salir_fullscreen_reproductor(ventana_principal.lyrics_visible)" in principal
    assert "salir_fullscreen_reproductor(true)" in principal
    assert "showMaximized()" in principal
    assert "requestActivate()" in principal
    assert "Screen.width" in principal
    assert "reproductor.mood_visual" in fullscreen
    assert "pista.portada_hd_ruta" in fullscreen
    assert "sourceSize.width" in fullscreen
    assert "asynchronous: true" in fullscreen
    assert "smooth: true" in fullscreen
    assert "altura_barra_reproduccion" in fullscreen
    assert "boton_volver_fullscreen" not in fullscreen
    assert "back.svg" not in fullscreen
    assert "Reproduciendo ahora" not in fullscreen
    assert "barras_equalizer" not in fullscreen
    assert "glows_equalizer" not in fullscreen
    assert "figuras_fondo" in fullscreen
    assert "figuras_pulso" in fullscreen
    assert "SequentialAnimation on pulso" in fullscreen
    assert "desplazamiento_con_barra" in fullscreen
    assert "barra_overlay_visible" in fullscreen
    assert "id: escenario_central" in fullscreen
    assert "id: contenido_centrado" in fullscreen
    assert "Repeater" in fullscreen


def test_qml_mini_reproductor_es_ventana_flotante_con_controles_svg():
    principal = Path("ui/qml/Principal.qml").read_text(encoding="utf-8")
    barra = Path("ui/qml/componentes/BarraReproduccion.qml").read_text(encoding="utf-8")
    slider = Path("ui/qml/componentes/SliderLine.qml").read_text(encoding="utf-8")
    qmldir = Path("ui/qml/componentes/qmldir").read_text(encoding="utf-8")
    mini = principal.split("id: mini_window", 1)[1]

    assert "Window {\n        id: mini_window" in principal
    assert "transientParent: null" in mini
    assert "Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint" in mini
    assert "readonly property int ancho_fijo_mini" in mini
    assert "readonly property int alto_fijo_mini" in mini
    assert "minimumWidth: ancho_fijo_mini" in mini
    assert "maximumWidth: ancho_fijo_mini" in mini
    assert "minimumHeight: alto_fijo_mini" in mini
    assert "maximumHeight: alto_fijo_mini" in mini
    assert "function abrir_mini_reproductor()" in principal
    assert "function cerrar_mini_reproductor()" in principal
    assert "if (reproduccion_expandida_visible)\n            return" in principal
    assert "cerrar_mini_reproductor()" in principal
    assert "preparar_apertura()" in mini
    assert "_posicionar_inferior_derecha()" in mini
    assert "_limitar_mini_a_pantalla()" in mini
    assert "Screen.desktopAvailableWidth" in mini
    assert "Screen.virtualX" in mini
    assert 'typeof mini_window.startSystemMove === "function"' in mini
    assert "mini_window.startSystemMove()" in mini
    assert "function _preparar_arrastre_manual_mini()" in mini
    assert "function _finalizar_arrastre_mini()" in mini
    assert "property bool arrastre_manual_mini" in mini
    assert "HoverHandler" in mini
    assert "drag.target: drag_proxy_mini" in mini
    assert "drag.smoothed: false" in mini
    assert "opacity: 0" in mini
    assert "onReleased: mini_window._finalizar_arrastre_mini()" in mini
    assert "assets/icons/drag-handle.svg" in mini
    assert "readonly property bool controles_visibles" in mini
    assert "opacity: mini_window.controles_visibles ? 1 : 0" in mini
    assert "readonly property int ancho_lateral_controles_mini: 92" in mini
    assert "readonly property int ancho_slider_volumen_mini: 42" in mini
    assert "Layout.preferredWidth: mini_window.ancho_lateral_controles_mini" in mini
    assert "width: mini_window.ancho_slider_volumen_mini" in mini
    assert "anchors.right: parent.right" in mini
    assert "enabled: mini_window.controles_visibles" in mini
    assert "Layout.alignment: Qt.AlignVCenter" in mini
    assert "property real tam_portada_mini" in mini
    assert "Layout.preferredHeight: mini_window.alto_controles_mini" in mini
    assert "assets/icons/prev.svg" in mini
    assert "assets/icons/play.svg" in mini
    assert "assets/icons/pause.svg" in mini
    assert "assets/icons/next.svg" in mini
    assert "assets/icons/surprise.svg" in mini
    assert "assets/icons/volume.svg" in mini
    assert "assets/icons/close.svg" in mini
    assert "iconSource: mini_window.iconoPlayMini" in mini
    assert "buttonSize: 32" in mini
    assert "iconSize: 15" in mini
    assert "activo: reproductor.sorpresa_activa" in mini
    assert "Componentes.SliderLine" in mini
    assert "SliderLine 1.0 SliderLine.qml" in qmldir
    assert "signal committed(real ratio)" in slider
    assert "signal moved(real ratio)" in slider
    assert "component SliderLine" not in barra
    assert "asynchronous: true" in mini
    assert "sourceSize.width: 256" in mini
    assert "status === Image.Ready" in mini
    assert "ToolTip" not in mini
    assert "BtnMini" not in mini
    assert 'text: "Mini"' not in mini
    assert 'text: "NB SOUND"' not in mini
    assert "Reproduciendo" not in mini
    assert "En pausa" not in mini
    assert "◀" not in mini
    assert "▶" not in mini
    assert "❚❚" not in mini
    assert "×" not in mini


def test_qml_queue_panel_usa_iconos_svg_para_acciones_de_fila():
    queue = Path("ui/qml/componentes/QueuePanel.qml").read_text(encoding="utf-8")

    assert "../assets/icons/drag.svg" in queue
    assert "../assets/icons/queue-play.svg" in queue
    assert "../assets/icons/close.svg" in queue
    assert "../assets/icons/pause.svg" in queue
    assert "property string iconSource" in queue
    assert "source: botonFila.iconSource" in queue
    assert 'text: "⋮⋮"' not in queue
    assert 'text: "▶"' not in queue
    assert 'text: "×"' not in queue
    assert Path("ui/qml/assets/icons/drag.svg").exists()
    assert Path("ui/qml/assets/icons/queue-play.svg").exists()


def test_qml_queue_panel_vaciar_usa_slot_especifico_para_conservar_actual():
    queue = Path("ui/qml/componentes/QueuePanel.qml").read_text(encoding="utf-8")

    assert "onClicked: reproductor.vaciar_cola_mantener_actual()" in queue
    assert "onClicked: reproductor.limpiar_cola()" not in queue


def test_qml_queue_panel_auto_scroll_durante_drag():
    queue = Path("ui/qml/componentes/QueuePanel.qml").read_text(encoding="utf-8")

    assert "property int autoScrollDireccion" in queue
    assert "readonly property int autoScrollMargen" in queue
    assert "function _actualizarAutoScroll(yEnLista)" in queue
    assert "id: auto_scroll_drag_timer" in queue
    assert "lista_cola.contentY = panel._limitarContentY" in queue
    assert "dragHandle.mapToItem(lista_cola" in queue


def test_qml_queue_panel_distingue_sonando_y_pausada_y_oculta_0s_en_vacio():
    queue = Path("ui/qml/componentes/QueuePanel.qml").read_text(encoding="utf-8")

    assert "property bool esSonando: esActual && reproductor.reproduciendo" in queue
    assert "property bool esPausada: esActual && reproductor.pausado" in queue
    assert 'text: fila.esSonando ? "Sonando" : "En pausa"' in queue
    assert "visible: panel.hayContenido" in queue


def test_qml_popup_cola_es_responsive_y_limitado_al_viewport():
    barra = Path("ui/qml/componentes/BarraReproduccion.qml").read_text(encoding="utf-8")

    assert "parent: Overlay.overlay" in barra
    assert "readonly property real popupMargen" in barra
    assert "readonly property real popupSeparacion: raiz.layout_compacto ? UiTokens.spacing12 : (UiTokens.spacing24 + UiTokens.spacing6)" in barra
    assert "readonly property real popupAnchoObjetivo" in barra
    assert "readonly property real popupAltoObjetivo" in barra
    assert "readonly property real popupViewportHeight" in barra
    assert "margins: popupMargen" in barra
    assert "popupViewportWidth - width - popupMargen" in barra
    assert "popupBotonTopY - height - popupSeparacion" in barra
    assert "function sincronizar_geometria()" in barra
    assert "var referencia = shell.contentItem ? shell.contentItem : raiz" in barra
    assert "var centro = boton_cola.mapToItem(referencia, boton_cola.width / 2, 0)" in barra
    assert "var origen = boton_cola.mapToItem(referencia, 0, 0)" in barra
    assert "onAboutToShow: Qt.callLater(sincronizar_geometria)" in barra
    assert "Qt.callLater(sincronizar_geometria)" in barra
    assert "modal: true" in barra
    assert "dim: false" in barra
    assert "closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside" in barra
    assert "CloseOnPressOutsideParent" not in barra
    assert "height: 328" not in barra


def test_qml_popup_cola_vacia_abre_con_altura_positiva(db_reproductor, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("QML_DISABLE_DISK_CACHE", "1")

    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    import main_ui as main_ui_mod

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    main_ui_mod.exponer_modelos(engine, main_ui_mod.construir_modelos(app))
    engine.addImportPath(str((Path("ui") / "qml").resolve()))
    engine.addImportPath(str((Path("ui") / "qml" / "componentes").resolve()))
    engine.addImportPath(str((Path("ui") / "qml" / "vistas").resolve()))
    engine.load(QUrl.fromLocalFile(str(main_ui_mod.ARCHIVO_QML.resolve())))

    root = engine.rootObjects()[0]

    def prop_names(obj):
        meta = obj.metaObject()
        return [meta.property(i).name() for i in range(meta.propertyCount())]

    def walk(obj):
        yield obj
        for child in obj.children():
            yield from walk(child)

    barra = next(obj for obj in walk(root) if "cola_visible" in prop_names(obj))
    assert barra.metaObject().invokeMethod(barra, "alternar_cola")

    QTimer.singleShot(120, app.quit)
    app.exec()

    popup = next(
        obj for obj in walk(root)
        if "opened" in prop_names(obj)
        and "popupMargen" in prop_names(obj)
        and obj.property("opened")
    )

    assert popup.property("height") > 0
    assert popup.property("visible") is True


def test_qml_popup_cola_cierra_con_click_fuera(db_reproductor, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("QML_DISABLE_DISK_CACHE", "1")

    from PySide6.QtCore import QPoint, QTimer, QUrl, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtTest import QTest
    import main_ui as main_ui_mod

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    main_ui_mod.exponer_modelos(engine, main_ui_mod.construir_modelos(app))
    engine.addImportPath(str((Path("ui") / "qml").resolve()))
    engine.addImportPath(str((Path("ui") / "qml" / "componentes").resolve()))
    engine.addImportPath(str((Path("ui") / "qml" / "vistas").resolve()))
    engine.load(QUrl.fromLocalFile(str(main_ui_mod.ARCHIVO_QML.resolve())))

    root = engine.rootObjects()[0]

    def prop_names(obj):
        meta = obj.metaObject()
        return [meta.property(i).name() for i in range(meta.propertyCount())]

    def walk(obj):
        yield obj
        for child in obj.children():
            yield from walk(child)

    barra = next(obj for obj in walk(root) if "cola_visible" in prop_names(obj))
    assert barra.metaObject().invokeMethod(barra, "alternar_cola")

    def click_fuera():
        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, QPoint(12, 12))
        QTimer.singleShot(120, app.quit)

    QTimer.singleShot(150, click_fuera)
    app.exec()

    popup = next(
        obj for obj in walk(root)
        if "opened" in prop_names(obj)
        and "popupMargen" in prop_names(obj)
    )

    assert popup.property("opened") is False
    assert popup.property("visible") is False


def test_qml_popup_cola_tocar_boton_playlist_abierto_lo_cierra(db_reproductor, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("QML_DISABLE_DISK_CACHE", "1")

    from PySide6.QtCore import QTimer, QUrl, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtTest import QTest
    import main_ui as main_ui_mod

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    main_ui_mod.exponer_modelos(engine, main_ui_mod.construir_modelos(app))
    engine.addImportPath(str((Path("ui") / "qml").resolve()))
    engine.addImportPath(str((Path("ui") / "qml" / "componentes").resolve()))
    engine.addImportPath(str((Path("ui") / "qml" / "vistas").resolve()))
    engine.load(QUrl.fromLocalFile(str(main_ui_mod.ARCHIVO_QML.resolve())))

    root = engine.rootObjects()[0]

    def prop_names(obj):
        meta = obj.metaObject()
        return [meta.property(i).name() for i in range(meta.propertyCount())]

    def walk(obj):
        yield obj
        for child in obj.children():
            yield from walk(child)

    barra = next(obj for obj in walk(root) if "cola_visible" in prop_names(obj))
    assert barra.metaObject().invokeMethod(barra, "alternar_cola")

    def click_boton_playlist():
        boton = next(
            obj for obj in walk(root)
            if "iconSource" in prop_names(obj)
            and "visible" in prop_names(obj)
            and obj.property("visible") is True
            and "playlist.svg" in str(obj.property("iconSource") or "")
        )
        centro_global = boton.mapToGlobal(boton.property("width") / 2, boton.property("height") / 2)
        centro_local = root.mapFromGlobal(centro_global.toPoint())
        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, centro_local)
        QTimer.singleShot(150, app.quit)

    QTimer.singleShot(150, click_boton_playlist)
    app.exec()

    popup = next(
        obj for obj in walk(root)
        if "opened" in prop_names(obj)
        and "popupMargen" in prop_names(obj)
    )

    assert popup.property("opened") is False
    assert popup.property("visible") is False


def test_qml_principal_escucha_avisos_y_usa_toast_o_dialog():
    principal = Path("ui/qml/Principal.qml").read_text(encoding="utf-8")

    assert "property var alerta_reproductor_critica" in principal
    assert "function manejar_aviso_reproductor(aviso)" in principal
    assert "function onAvisoReproductor(aviso)" in principal
    assert "reproductor.reenviar_avisos_retenidos()" in principal
    assert "dialog_error_reproductor.open()" in principal
    assert "Dialog {\n        id: dialog_error_reproductor" in principal
    assert "mostrar_toast_global(mensaje, nivel === \"warning\" ? \"warning\" : \"info\")" in principal
    assert "def reenviar_avisos_retenidos(self) -> None:" in Path("ui/modelos_qml.py").read_text(encoding="utf-8")


def test_qml_metadata_activa_usa_fallback_de_biblioteca():
    principal = Path("ui/qml/Principal.qml").read_text(encoding="utf-8")
    barra = Path("ui/qml/componentes/BarraReproduccion.qml").read_text(encoding="utf-8")
    modelo = Path("ui/modelos_qml.py").read_text(encoding="utf-8")

    assert "biblioteca.abrir_album_desde_pista(pista)" in principal
    assert "function abrir_artista_activo_en_biblioteca()" in principal
    assert "biblioteca.abrir_artista_desde_pista(pista)" in principal
    assert "shell.abrir_artista_activo_en_biblioteca()" in barra
    assert "abrir_album_desde_pista" in modelo
    assert "abrir_artista_desde_pista" in modelo


def test_qml_barra_y_mini_usan_pista_visual_sin_habilitar_overlays():
    principal = Path("ui/qml/Principal.qml").read_text(encoding="utf-8")
    barra = Path("ui/qml/componentes/BarraReproduccion.qml").read_text(encoding="utf-8")
    modelo = Path("ui/modelos_qml.py").read_text(encoding="utf-8")

    assert "pistaVisualCambiada" in modelo
    assert '@Property("QVariant", notify=pistaVisualCambiada)' in modelo
    assert "def pista_visual(self) -> dict:" in modelo
    assert "return self._snapshot_pista_para_continuar()" in modelo

    assert "readonly property var pista_visual: reproductor.pista_visual || ({})" in barra
    assert "readonly property bool hay_pista_visual" in barra
    assert "titulo_seguro: hay_pista_visual" in barra
    assert "portada_activa: pista_visual.portada_ruta" in barra
    assert "enabled: hay_pista_activa" in barra

    assert "readonly property var pistaMini: reproductor.pista_visual || ({})" in principal
    assert "readonly property bool hayPistaActivaMini" in principal
    assert "duracionMiniConocida: hayPistaActivaMini" in principal


def test_qml_nav_lateral_compacta_vertical_y_usa_animacion_compartida():
    nav = Path("ui/qml/componentes/NavLateral.qml").read_text(encoding="utf-8")
    barra = Path("ui/qml/componentes/BarraReproduccion.qml").read_text(encoding="utf-8")
    principal = Path("ui/qml/Principal.qml").read_text(encoding="utf-8")
    qmldir = Path("ui/qml/componentes/qmldir").read_text(encoding="utf-8")
    fondo = Path("ui/qml/componentes/AnimatedPlaybackBackground.qml").read_text(encoding="utf-8")

    assert "AnimatedPlaybackBackground 1.0 AnimatedPlaybackBackground.qml" in qmldir
    assert "property real animacion_reproductor_fase" in principal
    assert "animacion_fase: ventana_principal.animacion_reproductor_fase" in principal
    assert "animacion_origen_x: nav_lateral.width" in principal

    assert "readonly property bool compacto_vertical" in nav
    assert "height < 980" in nav
    assert "readonly property bool estrecho_vertical" in nav
    assert "height < 760" in nav
    assert "readonly property bool minimo_vertical" in nav
    assert "height < 640" in nav
    assert "alto_item_nav" in nav
    assert "alto_separador_nav" in nav
    assert "font_marca_nav" in nav
    assert "alto_marca_nav: minimo_vertical ? 24" in nav
    # NavLateral usa AppScrollBar unificado con patrón parent/anchors
    # explícitos al ScrollView; sin esto el thumb queda en (0,0) como
    # un punto perdido en la esquina superior izquierda.
    assert "ScrollBar.vertical: AppScrollBar" in nav
    assert "parent: nav_scroll" in nav
    assert "nav_scroll.contentHeight > nav_scroll.height + 2 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff" in nav
    assert "AnimatedPlaybackBackground" in nav
    assert "running: reproductor.reproduciendo" in nav
    assert "activeFocusOnTab: true" in nav
    assert "property bool focoTecladoVisible: false" in nav
    assert "Keys.priority: Keys.BeforeItem" in nav
    assert "Qt.Key_Backtab" in nav
    assert "(event.modifiers & Qt.ShiftModifier)" in nav
    assert "event.key === Qt.Key_Tab && (event.modifiers & Qt.ControlModifier)" in nav
    assert "function activar()" in nav
    assert "focoTecladoVisible = false" in nav
    assert "border.width: elemento_nav.focoTecladoVisible && elemento_nav.activeFocus ? 2 : 0" in nav
    assert "border.color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, raiz.temaClaro ? 0.78 : 0.92)" in nav
    assert "onClicked: elemento_nav.activar()" in nav
    assert "onClicked: toggle_modo.activar()" in nav
    assert "KeyNavigation.tab" not in nav
    assert "KeyNavigation.backtab" not in nav

    assert "AnimatedPlaybackBackground" in barra
    assert "Canvas {" not in barra
    assert "id: fondo_sobrio" not in barra
    assert "property real originX" in fondo
    assert "property real worldWidth" in fondo
    assert "Canvas {" not in fondo
    assert "Repeater" in fondo


def test_qml_reproduccion_individual_y_playlist_usa_cola_con_indice():
    album = Path("ui/qml/vistas/VistaDetalleAlbum.qml").read_text(encoding="utf-8")
    biblioteca = Path("ui/qml/vistas/VistaBiblioteca.qml").read_text(encoding="utf-8")
    playlists = Path("ui/qml/vistas/VistaPlaylists.qml").read_text(encoding="utf-8")
    modelo = Path("ui/modelos_qml.py").read_text(encoding="utf-8")

    assert "reproductor.reproducir_cola_desde_pistas(pistas, index)" not in album
    assert "reproductor.reproducir(modelData)" in album
    assert "reproductor.reproducir_cola_desde_pistas(artista_activo.pistas, index)" not in biblioteca
    assert "reproductor.reproducir(filaPista.pista)" in biblioteca
    assert "reproductor.reproducir_cola_desde_pistas(datos, inicio)" in playlists
    assert "reproductor.agregar_varias_a_cola(datos)" in playlists
    assert "onClicked: reproducirPlaylistDesde(index)" in playlists
    assert "reproductor.reproducir(playlists.pistas_activas.obtener(index))" not in playlists
    assert "def _valor_qml_a_python" in modelo
    assert "datos_pistas = self._valor_qml_a_python(datos_pistas)" in modelo


def test_qml_playlists_fase8_contrato_visual_y_acciones():
    playlists = Path("ui/qml/vistas/VistaPlaylists.qml").read_text(encoding="utf-8")
    toast = Path("ui/qml/componentes/ToastMessage.qml").read_text(encoding="utf-8")

    assert "onDoubleClicked: abrirDetallePlaylist" in playlists
    detalle_pistas = playlists.split("id: filaTrack", 1)[1]
    assert "onDoubleClicked" not in detalle_pistas
    for simbolo in ("←", "♫", "▶", "✕", "✎", "🔍"):
        assert simbolo not in playlists

    for icono in (
        "play.svg",
        "playlist.svg",
        "favorite.svg",
        "search.svg",
        "close.svg",
        "drag-handle.svg",
        "plus.svg",
        "edit.svg",
        "trash.svg",
        "grid-small.svg",
        "grid-medium.svg",
        "grid-large.svg",
        "list.svg",
        "pin.svg",
    ):
        assert icono in playlists

    for texto in (
        "Me gusta",
        "Creadas por mí",
        "Creadas para ti",
        "Inteligentes",
        "This is...",
        "Tops",
        "Mixes",
        "Últimas creadas para ti",
        "Nueva playlist",
        "Editar playlist",
        "Agregar canciones",
        "Busca por canción, artista, álbum, género o año",
        "Ya está",
        "Abrir playlist",
        "Volver",
    ):
        assert texto in playlists

    assert "ComboBox" not in playlists
    assert "OrdenChip" in playlists
    assert "ToolbarLabel { texto: \"Orden\" }" in playlists
    assert '"lista"' in playlists
    assert '"grid-sm"' in playlists
    assert '"grid-md"' in playlists
    assert '"grid-lg"' in playlists
    assert "configuracion.guardar(\"playlists_modo_vista\", modo)" in playlists
    assert "configuracion.guardar(\"playlists_orden\", orden_actual)" in playlists
    assert "configuracion.guardar(\"playlists_categoria\", categoria_actual)" in playlists
    assert "Drag.active" in playlists
    assert "DropArea" in playlists
    assert "playlists.reordenar_playlist" in playlists
    assert "playlists.buscar_pistas_para_playlist" in playlists
    assert "busquedaAgregarTimer" in playlists
    assert "playlists.renombrar_playlist" in playlists
    assert "playlists.editar_descripcion_playlist" in playlists
    # `sincronizar_inteligentes_async(0)` en `Component.onCompleted`
    # corre en un QThread vía _UiQueryWorker para no congelar la UI.
    # `sincronizar_inteligentes(3)` (versión síncrona con retorno dict)
    # se mantiene para el botón "Actualizar" que necesita el resumen
    # en el toast (`raiz.ejecutar(...)` consume el QVariantMap).
    assert "playlists.sincronizar_inteligentes_async(0)" in playlists
    assert "playlists.sincronizar_inteligentes(3)" in playlists
    assert "id: previewComponent" in playlists
    preview = playlists.split("id: previewComponent", 1)[1].split("id: detalleCompletoComponent", 1)[0]
    for accion_destructiva in ("Editar", "Eliminar", "Vaciar", "Regenerar", "Duplicar"):
        assert accion_destructiva not in preview
    assert "Flickable {" in preview
    assert "ListView {" in preview
    assert "Image.PreserveAspectFit" in preview
    assert "ModalPopup" in playlists
    assert "Overlay.modal" in playlists
    assert "CloseOnPressOutside" in playlists
    assert "Dialog {" not in playlists
    assert "accionConfirmada" in playlists
    assert "typeof accion === \"function\"" in playlists
    detalle_delegate = playlists.split("id: filaTrack", 1)[1].split("ModalPopup", 1)[0]
    assert "ejecutar(" not in detalle_delegate.replace("detalle._raiz.ejecutar(", "").replace("r.ejecutar(", "").replace("raiz.ejecutar(", "")
    assert "Flow {" in playlists
    assert "SearchBox {" in playlists
    assert "mostrar_toast_global" in playlists
    assert 'if (limpio === "")' in toast
    assert "root.message = limpio" in toast
    assert "score" not in playlists
    assert "confidence" not in playlists
    assert "basic" not in playlists
    assert "deep" not in playlists


def test_qml_biblioteca_fase5_estado_filtros_y_reset_nav():
    principal = Path("ui/qml/Principal.qml").read_text(encoding="utf-8")
    biblioteca = Path("ui/qml/vistas/VistaBiblioteca.qml").read_text(encoding="utf-8")
    modelo = Path("ui/modelos_qml.py").read_text(encoding="utf-8")

    assert "function navegar_a_vista(vista)" in principal
    assert "loader_biblioteca.item.ir_a_inicio_biblioteca()" in principal
    assert "function ir_a_inicio_biblioteca()" in biblioteca
    assert "biblioteca.guardar_estado_vista(_estado_actual())" in biblioteca
    assert "biblioteca.cargar_pistas(filtro_pistas, solo_favoritas, orden_pistas)" in biblioteca
    assert "biblioteca.cargar_albums_por_grupo(grupo_albums, orden_albums, filtro_albums)" in biblioteca
    assert "biblioteca.cargar_artistas(filtro_artistas, orden_artistas)" in biblioteca
    assert "model: biblioteca.grupos_albums" in biblioteca
    assert "Layout.preferredHeight: Math.max(96, toolbarContenido.implicitHeight + UiTokens.spacing24)" in biblioteca
    assert "Flow {" in biblioteca
    assert "Layout.fillWidth: true" in biblioteca
    assert 'ToolbarLabel { texto: "Orden" }' in biblioteca
    assert "id: filtroAlbumsInput" in biblioteca
    assert "id: filtroArtistasInput" in biblioteca
    assert '"Título Z-A"' in biblioteca
    assert '"Título A-Z"' in biblioteca
    assert '"Año reciente"' in biblioteca
    assert '"Año antiguo"' in biblioteca
    assert '"Menor duración"' in biblioteca
    assert "sort-asc.svg" in biblioteca
    assert "sort-desc.svg" in biblioteca
    assert "cursorShape: Qt.IBeamCursor" in biblioteca
    assert "TapHandler {" in biblioteca
    assert "_tapDentroDeBuscador(point.position)" in biblioteca
    assert "contienePuntoRaiz(posicion)" in biblioteca
    assert "property int modoTarjeta" in biblioteca
    assert "cellHeight: modoTarjeta === 0" in biblioteca
    assert "Layout.preferredWidth: albumGrid.portadaSize" in biblioteca
    assert "visible: albumGrid.modoTarjeta >= 1" in biblioteca
    assert "visible: albumGrid.modoTarjeta >= 2" in biblioteca
    assert "vista_biblioteca_estado" in modelo
    assert '"filtro_albums": self._texto_seguro(estado.get("filtro_albums"))' in modelo
    assert '"orden_artistas": orden_artistas' in modelo
    assert "limite=None" in modelo

    albums_toolbar = biblioteca[
        biblioteca.index("id: filtroAlbumsInput"):
        biblioteca.index("id: filtroArtistasInput")
    ]
    pistas_toolbar = biblioteca[
        biblioteca.index("id: filtroPistasInput"):
        biblioteca.index("VistaDetalleAlbum {")
    ]
    assert albums_toolbar.index("model: biblioteca.grupos_albums") < albums_toolbar.index('ToolbarLabel { texto: "Orden" }')
    assert pistas_toolbar.index('texto: "Favoritas"') < pistas_toolbar.index('ToolbarLabel { texto: "Orden" }')


def test_qml_biblioteca_fase5_ux_acciones_claras_sin_deprecated():
    biblioteca = Path("ui/qml/vistas/VistaBiblioteca.qml").read_text(encoding="utf-8")
    album = Path("ui/qml/vistas/VistaDetalleAlbum.qml").read_text(encoding="utf-8")

    assert "ComboBox" not in biblioteca
    assert "TextField" not in biblioteca
    assert "onActivated: cambiar_orden_albums(index)" not in biblioteca
    assert "onActivated: cambiar_orden_pistas(index)" not in biblioteca
    assert "onDoubleClicked" not in biblioteca
    assert "onDoubleClicked" not in album

    assert "component PillButton" in biblioteca
    assert "component LibrarySearchField" in biblioteca
    assert "component LibraryHeaderRow" in biblioteca
    assert "component LibraryActionButton" in biblioteca
    assert "component BackButton" in biblioteca

    assert "property var historial_biblioteca" in biblioteca
    assert "function volver_biblioteca()" in biblioteca
    assert "_push_historial()" in biblioteca
    assert "abrir_album_id(estado.album_id, false)" in biblioteca
    assert "historial_biblioteca = []" in biblioteca

    assert 'texto: "Reproducir todas las pistas del artista"' in biblioteca
    assert 'texto: "Añadir todas las canciones a la cola"' in biblioteca
    assert "mostrarBotonArtista: false" in biblioteca
    assert 'texto: "Artista"' not in biblioteca

    album_grid = biblioteca[
        biblioteca.index("id: albumGrid"):
        biblioteca.index("id: artistGrid")
    ]
    assert 'texto: "Abrir"' not in album_grid
    assert 'texto: "Abrir álbum"' not in album_grid
    assert 'iconSource: "../assets/icons/play.svg"' not in album_grid
    assert 'iconSource: "../assets/icons/queue-play.svg"' not in album_grid

    discografia_artista = biblioteca[
        biblioteca.index('text: "Discografía"'):
        biblioteca.index('title: "Sin discografía visible"')
    ]
    assert 'texto: "Abrir álbum"' not in discografia_artista
    assert 'texto: "Reproducir álbum"' not in discografia_artista
    assert 'texto: "Añadir álbum a cola"' not in discografia_artista

    assert 'texto: "Abrir álbum"' in biblioteca
    assert 'texto: "Abrir artista"' in biblioteca

    assert "biblioteca.toggle_favorita(pista.id)" in biblioteca
    assert "refrescar_pistas_conservando_scroll()" in biblioteca
    assert "favorite.svg" in biblioteca
    assert "favorite-filled.svg" in biblioteca
    assert "favorite-filled.svg" in album
    assert "component FavoriteButton" in biblioteca
    assert "mostrarFavorito: true" in biblioteca
    assert "signal favoritaToggled(var pista)" in album
    assert "component AlbumFavoriteButton" in album
    assert "onFavoritaToggled: function(pista)" in biblioteca

    assert "import QtQuick.Effects" in biblioteca
    assert "import QtQuick.Effects" in album
    assert "component ThemedIcon" in biblioteca
    assert "component ThemedIcon" in album
    assert "MultiEffect" in biblioteca
    assert "MultiEffect" in album
    assert "colorizationColor" in biblioteca
    assert "colorizationColor" in album
    assert "component CoverPlaceholder" in biblioteca
    assert "component AlbumCoverPlaceholder" in album
    assert "Image.PreserveAspectFit" in biblioteca
    assert "Image.PreserveAspectFit" in album
    assert "ScrollBar.vertical: LibraryScrollBar" in biblioteca
    assert "ScrollBar.vertical: AlbumScrollBar" in album
    assert "ScrollBar.horizontal" not in biblioteca
    assert "ScrollBar.horizontal" not in album
    track_list = biblioteca[
        biblioteca.index("id: trackList"):
        biblioteca.index("header: LibraryHeaderRow", biblioteca.index("id: trackList"))
    ]
    assert "LibraryScrollBar {" in track_list
    assert "ScrollBar.vertical" not in track_list
    assert "flickable: trackList" in track_list
    assert "readonly property real _trackRange" in biblioteca
    assert "position / _trackRange" in biblioteca
    assert "ratio * _maxContentY" in biblioteca
    assert "scrollGestureEnabled: false" in biblioteca
    assert "scrollGestureEnabled: false" in album
    assert "parent: albumGrid.parent" in biblioteca
    assert "parent: artistGrid.parent" in biblioteca
    assert "parent: trackList.parent" in biblioteca
    assert "parent: artistaDetalleScroll.parent" in biblioteca
    assert "parent: detalleAlbumScroll.parent" in album
    assert "color: tema.acentoFuerte" in biblioteca
    assert "color: tema.acentoFuerte" in album
    assert "color: scrollBar.pressed" not in biblioteca
    assert "color: scrollBar.pressed" not in album
    assert 'color: albumCover.visible ? "transparent" : tema.superficieAlt' in biblioteca
    assert 'border.width: albumCover.visible ? 0 : 1' in biblioteca
    assert 'color: albumCover.visible ? "transparent" : tema.superficieAlt' in album
    assert 'border.width: albumCover.visible ? 0 : 1' in album
    assert "portada_display_ruta" in biblioteca
    assert "portada_thumb_ruta" in biblioteca
    assert "portada_display_ruta" in album
    assert "cache: true" in biblioteca
    assert "cache: true" in album
    assert 'iconSource: "../assets/icons/library.svg"' in biblioteca
    assert 'iconSource: "../assets/icons/artist.svg"' in biblioteca

    assert '"DUR."' not in album
    assert 'text: "Duración"' in album
    assert 'text: "Acciones"' in album
    assert 'text: "Título"; font.pixelSize: UiTokens.fontSizeSm; font.weight: Font.DemiBold; color: tema.textoMuted; Layout.fillWidth: true; horizontalAlignment: Text.AlignLeft' in album
    assert 'text: "Pista"' in biblioteca
    assert "horizontalAlignment: Text.AlignLeft" in biblioteca
    assert "Layout.preferredWidth: 304" in album
    assert "horizontalAlignment: Text.AlignHCenter" in album
    assert 'texto: "Reproducir álbum completo"' in album
    assert 'texto: "Añadir álbum a la cola"' in album
    assert 'text: etiquetaTipoAlbum(datos_album.tipo) || "Álbum"' in album
    assert 'text: datos_album.tipo || "Album"' not in album

    favorita_fn = biblioteca[
        biblioteca.index("function alternar_favorita_pista"):
        biblioteca.index("function abrir_album_id")
    ]
    assert "mostrar_toast(" not in favorita_fn
    assert 'texto: "Reproducir"' in album
    assert 'texto: "Añadir a cola"' in album

    for icono in ("sort-asc.svg", "sort-desc.svg", "artist.svg"):
        ruta_icono = Path("ui/qml/assets/icons") / icono
        assert ruta_icono.exists()
        assert "<svg" in ruta_icono.read_text(encoding="utf-8")


def test_qml_vista_busqueda_fase6_contrato_visual_y_acciones():
    busqueda = Path("ui/qml/vistas/VistaBusqueda.qml").read_text(encoding="utf-8")
    principal = Path("ui/qml/Principal.qml").read_text(encoding="utf-8")

    assert "onDoubleClicked" not in busqueda
    assert "length >= 2" not in busqueda
    assert "length < 2" not in busqueda
    assert 'text: ">"' not in busqueda
    assert 'text: "→"' not in busqueda
    assert "chevron-right.svg" in busqueda
    assert Path("ui/qml/assets/icons/chevron-right.svg").exists()

    for texto_debug in (
        "Biblioteca analizada",
        "score ",
        "conf ",
        "confidence",
        "basic",
        "basic + deep",
        "feature_summary",
        "ranking_weights",
        "filters",
    ):
        assert texto_debug not in busqueda

    assert "component SearchTrackRow" in busqueda
    assert "readonly property bool mostrarResultadosClasicos: !modoNatural && queryBusquedaClasica.trim().length > 0" in busqueda
    assert "readonly property bool mostrarResultadosNaturales: modoNatural && queryBusquedaNatural.trim().length > 0" in busqueda
    # Las secciones clásicas se renderizan vía Repeater APLANADO
    # (_filasPlanas) sobre _ordenSeccionesBusqueda. Cada fila (header o
    # item) es un Loader leaf en el padre, sin sub-ColumnLayout intermedio.
    assert "_ordenSeccionesBusqueda" in busqueda
    assert "model: raiz._filasPlanas" in busqueda
    assert "id: _compHeader" in busqueda
    assert "id: _compFilaPistaFav" in busqueda
    assert "id: _compFilaPista" in busqueda
    assert "id: _compFilaArtista" in busqueda
    assert "id: _compFilaAlbum" in busqueda
    assert "busqueda.favoritos.obtener" in busqueda
    assert "busqueda.pistas.obtener" in busqueda
    assert "busqueda.artistas.obtener" in busqueda
    assert "busqueda.albums.obtener" in busqueda
    assert "model: mostrarResultadosNaturales ? busqueda.seccionesNatural : 0" in busqueda
    assert "visible: !modoNatural && queryBusquedaClasica.trim().length === 0" in busqueda
    assert "visible: modoNatural && busqueda.hayBibliotecaMusical && busqueda.hayFeaturesDisponibles &&\n                             queryBusquedaNatural.trim().length === 0" in busqueda
    assert "visible: mostrarResultadosClasicos && !esta_buscando &&" in busqueda
    assert "busqueda.favoritos.total === 0 && busqueda.pistas.total === 0" in busqueda
    assert "visible: modoNatural && busqueda.hayBibliotecaMusical && busqueda.hayFeaturesDisponibles &&\n                             mostrarResultadosNaturales && !esta_buscando && busqueda.seccionesNatural.total === 0" in busqueda
    # En el modelo aplanado, los singulares se derivan dinámicamente desde
    # modelData.seccion en _compHeader. Verificamos las cadenas literales
    # presentes en esa derivación.
    assert '"Artista"' in busqueda
    assert '"Álbum"' in busqueda
    assert '"Pista"' in busqueda
    assert '"Favorito"' in busqueda
    assert 'texto: "Añadir a cola"' in busqueda

    assert "../assets/icons/queue-play.svg" in busqueda
    assert "../assets/icons/favorite.svg" in busqueda
    assert "../assets/icons/favorite-filled.svg" in busqueda
    assert "biblioteca.toggle_favorita(pista.id)" in busqueda
    assert "reproductor.agregar_a_cola(pista)" in busqueda
    assert "reproductor.reproducir(pista)" in busqueda
    assert "onPlay: function(pista)" in busqueda
    assert "onAddToQueue: function(pista)" in busqueda
    assert "onToggleFavorite: function(pista)" in busqueda
    assert "onPlay: reproducirPista(pista)" not in busqueda
    assert "onAddToQueue: agregarPistaACola(pista)" not in busqueda
    assert "onToggleFavorite: alternarFavorita(pista)" not in busqueda

    assert "property string queryBusquedaClasica" in busqueda
    assert "property string queryBusquedaNatural" in busqueda
    assert "function resetScrollBusqueda()" in busqueda
    assert "resultadosScroll.contentItem.contentY = 0" in busqueda

    assert "function abrir_album_desde_detalle(album_id)" in principal
    assert "loader_biblioteca.item.abrir_album_id(album_id)" in principal
    assert "shell.abrir_album_desde_detalle(_data.id)" in busqueda

    natural_delegate = busqueda[busqueda.index("model: mostrarResultadosNaturales ? busqueda.seccionesNatural : 0"):]
    assert "abrir_album" not in natural_delegate
    assert "abrir_artista" not in natural_delegate


def test_qml_vista_inicio_fase7_dashboard_vivo_sin_accesos_rapidos():
    inicio = Path("ui/qml/vistas/VistaInicio.qml").read_text(encoding="utf-8")

    assert "Accesos rápidos" not in inicio
    assert "BotonQuick" not in inicio
    assert "Haz que esta sesión suene increíble" not in inicio
    assert "Tu próxima gran biblioteca empieza hoy" not in inicio

    for simbolo in ("♪", "♬", "⊞", "⏱", "⚡", "◀", "▶"):
        assert simbolo not in inicio

    # Core components that must exist
    assert "component SeccionCarrusel" in inicio
    assert "component InicioEcualizadorBarras" in inicio
    assert "component StatChip" in inicio
    assert "component GridRetornarAsimetrico" in inicio
    assert "component HeroSeccion" in inicio
    assert "component CarouselButton" in inicio
    assert "component DashboardCard" in inicio
    assert "component CoverArt" in inicio
    assert "chevron-left.svg" in inicio
    assert "chevron-right.svg" in inicio
    assert "track.svg" in inicio
    assert "album.svg" in inicio
    assert "clock.svg" in inicio
    assert "MultiEffect" in inicio

    assert "(estadisticas.resumen.total_pistas || 0) === 0" in inicio
    assert 'texto: "Importar música"' in inicio
    assert "estadoVacio" in inicio
    assert "barContainer" in inicio   # equalizer inner container
    assert "barRow" in inicio         # equalizer row

    # All section titles must be present
    for seccion in (
        "Vuelve a tu música",
        "Tus playlists destacadas",
        "Álbumes que vuelven a aparecer",
        "Tu top 10 canciones",
        "Últimos añadidos",
        "Artistas que más suenan",
        "Tus 10 álbumes más escuchados",
    ):
        assert seccion in inicio
    # Mix personal was removed by user request
    assert "Para redescubrir" not in inicio
    assert "MIX PERSONAL" not in inicio

    assert "Creado para ti" not in inicio
    assert "Mezcla local" not in inicio
    assert "escuchas fuertes" not in inicio
    assert 'titulo: "Vuelve a tu música"' in inicio
    assert "GridRetornarAsimetrico" in inicio
    assert "readonly property int maxVolver: 12" in inicio
    assert "readonly property int maxTop: 10" in inicio
    assert "maxItems:" in inicio and "raiz.maxTop" in inicio
    assert 'model: seccion.totalVisible' in inicio
    assert "estadisticas.para_volver" in inicio
    assert "estadisticas.playlists_destacadas" in inicio
    assert "estadisticas.albums_que_gustan" in inicio
    # recomendaciones_inicio was used only by the removed Mix Personal banner
    assert "recomendaciones_inicio" not in inicio
    assert "reuseItems: true" in inicio
    assert "cacheBuffer" in inicio
    # Scrollbar uses the same InicioScrollBar component pattern as LibraryScrollBar
    assert "component InicioScrollBar" in inicio
    assert "scrollbarTrack" in inicio
    assert "flickable: inicioScroll" in inicio
    assert "tema.acentoFuerte" in inicio   # scrollbar handle color matches accent
    assert "Flickable" in inicio
    assert "shell.abrir_album_desde_detalle" in inicio
    # Playlist navigation must use specific ID (not just generic view)
    assert "abrir_playlist_desde_inicio" in inicio
    assert "shell.abrir_artista_desde_detalle" in inicio
    assert 'shell.vista_activa = "playlists"' in inicio

    for icono in ("chevron-left.svg", "album.svg", "track.svg", "clock.svg"):
        ruta_icono = Path("ui/qml/assets/icons") / icono
        assert ruta_icono.exists()
        assert "<svg" in ruta_icono.read_text(encoding="utf-8")

    assert 'color: "transparent"' in inicio
    assert "formatear_duracion_detallada" in inicio
    assert "sinRecortePortada" in inicio
    assert "modoFooter" in inicio
    assert "espacioCarrusel" in inicio
    assert "tema.modoBoxFondo" in inicio
    assert "tema.modoBoxBorde" in inicio
    assert "tema.seleccion" in inicio
    assert "tema.hover" in inicio
    assert "inicioContenido" in inicio
    assert "readonly property bool playlist:" not in inicio
    assert "playlistCard" not in inicio
    assert "compacto" not in inicio
