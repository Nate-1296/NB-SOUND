from pathlib import Path

import pytest

from db.conexion import cerrar_db, get_conexion, inicializar_db
from servicios import biblioteca as svc_bib


@pytest.fixture()
def db_playlists(tmp_path):
    inicializar_db(tmp_path / "playlists.sqlite3")
    try:
        yield tmp_path
    finally:
        cerrar_db()


def _slug(texto: str) -> str:
    return texto.lower().replace(" ", "-")


def _crear_album(artista: str, album: str, portada: str | None = None) -> tuple[int, int]:
    con = get_conexion()
    cur_artista = con.execute(
        "INSERT OR IGNORE INTO artistas(nombre, nombre_slug) VALUES (?, ?)",
        (artista, _slug(artista)),
    )
    artista_id = cur_artista.lastrowid if cur_artista.rowcount else 0
    if not artista_id:
        artista_id = con.execute("SELECT id FROM artistas WHERE nombre = ?", (artista,)).fetchone()["id"]

    album_slug = f"{_slug(artista)}-{_slug(album)}"
    cur_album = con.execute(
        """
        INSERT OR IGNORE INTO albums(artista_id, titulo, titulo_slug, tipo, portada_ruta)
        VALUES (?, ?, ?, 'Album', ?)
        """,
        (artista_id, album, album_slug, portada or ""),
    )
    album_id = cur_album.lastrowid if cur_album.rowcount else 0
    if not album_id:
        album_id = con.execute(
            "SELECT id FROM albums WHERE artista_id = ? AND titulo_slug = ?",
            (artista_id, album_slug),
        ).fetchone()["id"]
        if portada:
            con.execute("UPDATE albums SET portada_ruta = ? WHERE id = ?", (portada, album_id))
    return artista_id, album_id


def _crear_pista(
    tmp_path: Path,
    titulo: str,
    *,
    artista: str = "Artista",
    album: str = "Album",
    genero: str = "",
    anio: int | None = None,
    favorita: bool = False,
    reproducciones: int = 0,
    portada: str | None = None,
) -> int:
    artista_id, album_id = _crear_album(artista, album, portada)
    ruta = tmp_path / f"{artista}-{album}-{titulo}.mp3"
    ruta.write_bytes(b"audio")
    con = get_conexion()
    pista_id = con.execute(
        """
        INSERT INTO pistas(
            album_id, artista_id, titulo, artista_nombre, album_titulo,
            ruta_archivo, nombre_archivo, tamano_bytes, duracion_seg,
            genero, anio, favorita, veces_reproducida, ultimo_acceso, estado
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 180, ?, ?, ?, ?, datetime('now'), 'biblioteca')
        """,
        (
            album_id,
            artista_id,
            titulo,
            artista,
            album,
            str(ruta),
            ruta.name,
            ruta.stat().st_size,
            genero,
            anio,
            1 if favorita else 0,
            reproducciones,
        ),
    ).lastrowid
    for _ in range(reproducciones):
        con.execute(
            """
            INSERT INTO historial(pista_id, titulo_snap, artista_snap, duracion_seg, completada)
            VALUES (?, ?, ?, 180, 1)
            """,
            (pista_id, titulo, artista),
        )
    return pista_id


def _crear_lote(
    tmp_path: Path,
    total: int,
    *,
    artista: str = "Adele",
    album: str = "25",
    reproducciones: bool = False,
) -> list[int]:
    ids = []
    for i in range(total):
        ids.append(
            _crear_pista(
                tmp_path,
                f"Cancion {i:02d}",
                artista=artista,
                album=album,
                reproducciones=(i % 7) + 1 if reproducciones else 0,
            )
        )
    return ids


def _agregar_features(pista_ids: list[int], *, party: bool = True) -> None:
    con = get_conexion()
    for pista_id in pista_ids:
        con.execute(
            """
            INSERT INTO track_audio_features(
                track_id, file_hash, file_path, analyzer_version, analysis_mode,
                analysis_status, duration_sec, bpm, energy, danceability_proxy,
                workout_score_proxy, party_score_proxy, calmness_proxy,
                focus_score_proxy, night_score_proxy, melancholy_proxy,
                valence_proxy, arousal_proxy, darkness_proxy, brightness
            )
            VALUES (?, ?, ?, 'test', 'basic', 'ready', 180, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(pista_id),
                f"hash-{pista_id}",
                f"/tmp/{pista_id}.mp3",
                132 if party else 92,
                0.92 if party else 0.22,
                0.88 if party else 0.18,
                0.91 if party else 0.12,
                0.90 if party else 0.10,
                0.10 if party else 0.93,
                0.18 if party else 0.90,
                0.20 if party else 0.88,
                0.10,
                0.82 if party else 0.38,
                0.88 if party else 0.30,
                0.12 if party else 0.52,
                0.80 if party else 0.35,
            ),
        )


def test_migraciones_playlists_agregan_contrato_e_indices(db_playlists):
    con = get_conexion()
    columnas = {row["name"] for row in con.execute("PRAGMA table_info(playlists)").fetchall()}
    assert {
        "subtipo",
        "origen",
        "auto_key",
        "es_anclada",
        "visible",
        "portada_ruta",
        "ultima_generacion_en",
        "auto_actualizable",
        "editada_por_usuario",
    } <= columnas

    indices = {row["name"] for row in con.execute("PRAGMA index_list(playlists)").fetchall()}
    assert {"idx_playlists_tipo", "idx_playlists_subtipo", "idx_playlists_auto_key", "idx_playlists_visible"} <= indices


def test_crud_manual_agregar_quitar_vaciar_reordenar_y_duplicar(db_playlists):
    ids = _crear_lote(db_playlists, 4, artista="Rosalia", album="Motomami")

    playlist_id = svc_bib.crear_playlist("Mi lista", "Inicial")
    assert playlist_id > 0
    with pytest.raises(ValueError):
        svc_bib.crear_playlist("   ")
    with pytest.raises(ValueError):
        svc_bib.crear_playlist("mi lista")

    assert svc_bib.renombrar_playlist(playlist_id, "Mi lista nueva")["ok"]
    assert svc_bib.editar_descripcion_playlist(playlist_id, "Descripcion corta")["ok"]
    assert svc_bib.agregar_a_playlist(playlist_id, ids[0])["ok"]
    duplicada = svc_bib.agregar_a_playlist(playlist_id, ids[0])
    assert duplicada["ok"] is False
    assert duplicada["duplicada"] is True
    svc_bib.agregar_a_playlist(playlist_id, ids[1])
    svc_bib.agregar_a_playlist(playlist_id, ids[2])

    assert [p["id"] for p in svc_bib.pistas_de_playlist(playlist_id)] == ids[:3]
    svc_bib.reordenar_playlist(playlist_id, ids[2], 1)
    assert [p["id"] for p in svc_bib.pistas_de_playlist(playlist_id)] == [ids[2], ids[0], ids[1]]

    svc_bib.quitar_de_playlist(playlist_id, ids[0])
    pistas = svc_bib.pistas_de_playlist(playlist_id)
    assert [p["posicion"] for p in pistas] == [1, 2]
    assert {p["id"] for p in pistas} == {ids[2], ids[1]}

    duplicada = svc_bib.duplicar_playlist(playlist_id)
    assert duplicada["ok"]
    duplicada_id = duplicada["playlist_id"]
    assert duplicada_id != playlist_id
    assert [p["id"] for p in svc_bib.pistas_de_playlist(duplicada_id)] == [ids[2], ids[1]]

    svc_bib.vaciar_playlist(playlist_id)
    assert svc_bib.pistas_de_playlist(playlist_id) == []
    assert svc_bib.eliminar_playlist(playlist_id)["ok"]
    assert all(pl["playlist_id"] != playlist_id for pl in svc_bib.listar_playlists())


def test_me_gusta_refleja_favoritas_y_no_se_elimina(db_playlists):
    pista_id = _crear_pista(db_playlists, "Favorita", artista="Adele", album="30")

    svc_bib.sincronizar_playlists_sistema(0)
    favoritos = next(pl for pl in svc_bib.listar_playlists() if pl["tipo_playlist"] == "favoritos")
    assert favoritos["nombre"] == "Me gusta"
    assert svc_bib.pistas_de_playlist(favoritos["playlist_id"]) == []

    assert svc_bib.toggle_favorita(pista_id) is True
    assert [p["id"] for p in svc_bib.pistas_de_playlist(favoritos["playlist_id"])] == [pista_id]
    assert svc_bib.eliminar_playlist(favoritos["playlist_id"])["ok"] is False
    assert svc_bib.vaciar_playlist(favoritos["playlist_id"])["ok"] is False
    assert svc_bib.toggle_favorita(pista_id) is False
    assert svc_bib.pistas_de_playlist(favoritos["playlist_id"]) == []


def test_buscar_pistas_para_playlist_cruza_album_artista_titulo_y_acentos(db_playlists):
    pista_album = _crear_pista(db_playlists, "Estrella", artista="Bomba Estereo", album="Deja", genero="Tropical", anio=2021)
    pista_tilde = _crear_pista(db_playlists, "Estas en mi cabeza", artista="Shakira", album="Pies descalzos")
    playlist_id = svc_bib.crear_playlist("Busqueda")
    svc_bib.agregar_a_playlist(playlist_id, pista_album)

    por_album = svc_bib.buscar_pistas_para_playlist("deja", playlist_id)
    assert por_album[0]["id"] == pista_album
    assert por_album[0]["ya_en_playlist"] is True

    assert svc_bib.buscar_pistas_para_playlist("bomba estrella", playlist_id)[0]["id"] == pista_album
    assert svc_bib.buscar_pistas_para_playlist("tropical 2021", playlist_id)[0]["id"] == pista_album
    assert svc_bib.buscar_pistas_para_playlist("estas cabeza", playlist_id)[0]["id"] == pista_tilde


def test_generacion_automatica_respeta_minimos_maximo_auto_key_y_tombstone(db_playlists):
    _crear_lote(db_playlists, 3, artista="Pequeno", album="EP", reproducciones=True)
    svc_bib.sincronizar_playlists_sistema(5)
    assert [pl for pl in svc_bib.listar_playlists() if pl["tipo"] == "automatica"] == []

    _crear_lote(db_playlists, 70, artista="Adele", album="25", reproducciones=True)
    resultado = svc_bib.sincronizar_playlists_sistema(5)
    assert resultado["creadas"] <= 5
    auto_keys = [pl["auto_key"] for pl in svc_bib.listar_playlists() if pl["auto_key"]]
    assert len(auto_keys) == len(set(auto_keys))

    top = next(pl for pl in svc_bib.listar_playlists() if pl["auto_key"] == "auto:top_canciones")
    assert top["num_pistas"] <= 50
    auto = next(pl for pl in svc_bib.listar_playlists() if pl["tipo"] == "automatica")
    assert svc_bib.eliminar_playlist(auto["playlist_id"])["ok"]
    svc_bib.sincronizar_playlists_sistema(5)
    con = get_conexion()
    rows = con.execute("SELECT id, visible FROM playlists WHERE auto_key = ?", (auto["auto_key"],)).fetchall()
    assert len(rows) == 1
    assert rows[0]["visible"] == 0


def test_automatica_editada_no_se_sobrescribe_y_regenerar_es_explicito(db_playlists):
    _crear_lote(db_playlists, 35, artista="Bad Bunny", album="Un verano", reproducciones=True)
    svc_bib.sincronizar_playlists_sistema(5)
    auto = next(pl for pl in svc_bib.listar_playlists() if pl["auto_key"] == "auto:redescubrir")

    svc_bib.renombrar_playlist(auto["playlist_id"], "No tocar")
    svc_bib.generar_playlists_inteligentes(5)
    protegida = next(pl for pl in svc_bib.listar_playlists() if pl["playlist_id"] == auto["playlist_id"])
    assert protegida["nombre"] == "No tocar"
    assert protegida["editada_por_usuario"] is True
    assert protegida["auto_actualizable"] is False

    assert svc_bib.regenerar_playlist_automatica(auto["playlist_id"])["ok"]
    regenerada = next(pl for pl in svc_bib.listar_playlists() if pl["playlist_id"] == auto["playlist_id"])
    assert regenerada["editada_por_usuario"] is False
    assert regenerada["auto_actualizable"] is True


def test_genera_this_is_y_moods_solo_con_datos_suficientes(db_playlists, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "MUSIC_DISCOVERY_USE_AUDIO_FEATURES", True)
    monkeypatch.setattr(settings, "MUSIC_DISCOVERY_USE_DEEP_FEATURES", False)
    ids = _crear_lote(db_playlists, 49, artista="Adele", album="Live", reproducciones=False)
    svc_bib.sincronizar_playlists_sistema(5)
    assert not any(pl["tipo_playlist"] == "this_is" and pl["nombre"] == "This is Adele" for pl in svc_bib.listar_playlists())
    assert not any(pl["tipo_playlist"] == "mood" for pl in svc_bib.listar_playlists())

    ids.append(_crear_pista(db_playlists, "Cancion 49", artista="Adele", album="Live"))
    svc_bib.sincronizar_playlists_sistema(5)
    assert any(pl["tipo_playlist"] == "this_is" and pl["nombre"] == "This is Adele" for pl in svc_bib.listar_playlists())

    _agregar_features(ids[:29], party=True)
    svc_bib.generar_playlists_inteligentes(5)
    assert not any(pl["tipo_playlist"] == "mood" for pl in svc_bib.listar_playlists())

    _agregar_features(ids[29:30], party=True)
    svc_bib.generar_playlists_inteligentes(5)
    assert any(pl["tipo_playlist"] == "mood" for pl in svc_bib.listar_playlists())


def test_this_is_crea_con_50_no_con_49_y_expone_conteos(db_playlists):
    _crear_lote(db_playlists, 49, artista="Artista 49", album="Directos")
    svc_bib.sincronizar_playlists_sistema(5)
    assert not any(pl["auto_key"] for pl in svc_bib.listar_playlists() if pl["auto_key"] == "auto:this_is:1")

    _crear_pista(db_playlists, "Cancion 49", artista="Artista 49", album="Directos")
    svc_bib.sincronizar_playlists_sistema(0)

    conteo = next(item for item in svc_bib.conteos_artistas_para_playlists() if item["nombre"] == "Artista 49")
    assert conteo["total_pistas"] == 50
    assert {"artista_id", "nombre", "total_pistas", "total_favoritas", "reproducciones_total", "ultima_actualizacion"} <= set(conteo)
    assert any(pl["tipo_playlist"] == "this_is" and pl["nombre"] == "This is Artista 49" for pl in svc_bib.listar_playlists())


def test_this_is_no_duplica_no_recrea_oculta_y_no_sobrescribe_editada(db_playlists):
    _crear_lote(db_playlists, 50, artista="No Duplicar", album="Catalogo")
    svc_bib.sincronizar_playlists_sistema(0)
    this_is = next(pl for pl in svc_bib.listar_playlists() if pl["nombre"] == "This is No Duplicar")

    svc_bib.sincronizar_playlists_sistema(0)
    con = get_conexion()
    assert con.execute("SELECT COUNT(*) AS total FROM playlists WHERE auto_key = ?", (this_is["auto_key"],)).fetchone()["total"] == 1

    assert svc_bib.eliminar_playlist(this_is["playlist_id"])["ok"]
    svc_bib.sincronizar_playlists_sistema(0)
    oculta = con.execute("SELECT visible FROM playlists WHERE auto_key = ?", (this_is["auto_key"],)).fetchone()
    assert oculta["visible"] == 0

    _crear_lote(db_playlists, 50, artista="Editada", album="Catalogo")
    svc_bib.sincronizar_playlists_sistema(0)
    editada = next(pl for pl in svc_bib.listar_playlists() if pl["nombre"] == "This is Editada")
    svc_bib.renombrar_playlist(editada["playlist_id"], "Mi artista protegido")
    svc_bib.sincronizar_playlists_sistema(0)
    protegida = svc_bib.detalle_playlist(editada["playlist_id"])
    assert protegida["nombre"] == "Mi artista protegido"
    assert protegida["editada_por_usuario"] is True


def test_generacion_no_crea_mixes_pobres_y_descubrir_excluye_muy_reproducidas(db_playlists):
    ids_pobres = []
    for album_idx in range(4):
        ids_pobres.extend(
            _crear_lote(
                db_playlists,
                4,
                artista=f"Artista {album_idx}",
                album=f"Album {album_idx}",
                reproducciones=True,
            )
        )
    svc_bib.sincronizar_playlists_sistema(5)
    auto_keys = {pl["auto_key"] for pl in svc_bib.listar_playlists() if pl["auto_key"]}
    assert "auto:album_mix_frecuentes" not in auto_keys
    assert "auto:artist_mix_frecuentes" not in auto_keys

    for idx in range(24):
        _crear_pista(db_playlists, f"Pendiente {idx:02d}", artista="Explorar", album="Locales", reproducciones=0)
    muy_reproducida = _crear_pista(db_playlists, "Quemada", artista="Explorar", album="Locales", reproducciones=10)

    svc_bib.generar_playlists_inteligentes(5)
    descubrir = next(pl for pl in svc_bib.listar_playlists() if pl["auto_key"] == "auto:descubrir:canciones")
    descubrir_ids = {p["id"] for p in svc_bib.pistas_de_playlist(descubrir["playlist_id"])}
    assert muy_reproducida not in descubrir_ids
    assert any(pid in descubrir_ids for pid in ids_pobres)


def test_automatica_pobre_heredada_se_oculta_sin_tocar_manual(db_playlists):
    ids = _crear_lote(db_playlists, 16, artista="Albumero", album="Frecuente", reproducciones=True)
    manual = svc_bib.crear_playlist("Manual intacta")
    svc_bib.agregar_a_playlist(manual, ids[0])
    con = get_conexion()
    auto_id = con.execute(
        """
        INSERT INTO playlists(nombre, descripcion, tipo, subtipo, origen, auto_key, visible, auto_actualizable, editada_por_usuario)
        VALUES ('Mix de álbumes frecuentes', '', 'automatica', 'album_mix', 'generado', 'auto:album_mix_frecuentes', 1, 1, 0)
        """
    ).lastrowid
    for pos, pista_id in enumerate(ids, start=1):
        con.execute(
            "INSERT INTO pistas_playlist(playlist_id, pista_id, posicion) VALUES (?, ?, ?)",
            (auto_id, pista_id, pos),
        )

    svc_bib.sincronizar_playlists_sistema(5)
    auto = con.execute("SELECT visible, editada_por_usuario FROM playlists WHERE id = ?", (auto_id,)).fetchone()
    assert auto["visible"] == 0
    assert auto["editada_por_usuario"] == 0
    assert svc_bib.detalle_playlist(manual)["num_pistas"] == 1


def test_crear_para_mi_devuelve_mensaje_humano_si_no_crea(db_playlists):
    _crear_lote(db_playlists, 3, artista="Poco Material", album="EP")
    resultado = svc_bib.generar_playlists_inteligentes(3)
    assert resultado["creadas"] == 0
    assert "score" not in resultado["mensaje"].lower()
    assert "features" not in resultado["mensaje"].lower()
    assert "playlist" in resultado["mensaje"] or "canciones" in resultado["mensaje"]


def test_portadas_collage_fallback_y_actualizacion_fuera_del_proyecto(db_playlists, tmp_path, monkeypatch):
    Image = pytest.importorskip("PIL.Image")
    from config import settings as _settings
    monkeypatch.setattr(_settings, "DEFAULT_CACHE_DIR", tmp_path / "cache")
    covers = []
    for idx, color in enumerate(("red", "green", "blue", "yellow", "purple")):
        path = tmp_path / f"cover-{idx}.png"
        Image.new("RGB", (40, 40), color=color).save(path)
        covers.append(path)

    ids = [
        _crear_pista(db_playlists, f"Con portada {i}", artista="Artista", album=f"Album {i}", portada=str(covers[i]))
        for i in range(5)
    ]
    playlist_id = svc_bib.crear_playlist("Collage")
    for pista_id in ids[:4]:
        svc_bib.agregar_a_playlist(playlist_id, pista_id)

    portada = Path(svc_bib.actualizar_portada_playlist_si_cambio(playlist_id))
    assert portada.exists()
    assert (tmp_path / "cache" / "playlist_covers") in portada.parents
    assert Path.cwd().resolve() not in portada.resolve().parents

    svc_bib.agregar_a_playlist(playlist_id, ids[4])
    svc_bib.reordenar_playlist(playlist_id, ids[4], 1)
    nueva_portada = Path(svc_bib.actualizar_portada_playlist_si_cambio(playlist_id))
    assert nueva_portada.exists()
    assert nueva_portada != portada

    sin_portada = svc_bib.crear_playlist("Sin portada")
    sin_portada_track = _crear_pista(db_playlists, "Sin cover", artista="Otro", album="Sin cover")
    svc_bib.agregar_a_playlist(sin_portada, sin_portada_track)
    fallback = Path(svc_bib.actualizar_portada_playlist_si_cambio(sin_portada))
    assert fallback.exists()


def test_collage_deduplica_portadas_visualmente_iguales_y_tolera_faltantes(db_playlists, tmp_path, monkeypatch):
    Image = pytest.importorskip("PIL.Image")
    from config import settings as _settings
    monkeypatch.setattr(_settings, "DEFAULT_CACHE_DIR", tmp_path / "cache")

    repetidas = []
    for idx in range(4):
        path = tmp_path / f"misma-{idx}.png"
        Image.new("RGB", (40, 40), color="red").save(path)
        repetidas.append(path)
    distinta = tmp_path / "distinta.png"
    Image.new("RGB", (40, 40), color="blue").save(distinta)

    ids = [
        _crear_pista(db_playlists, f"Repetida {idx}", artista="Visual", album=f"R{idx}", portada=str(path))
        for idx, path in enumerate(repetidas)
    ]
    ids.append(_crear_pista(db_playlists, "Distinta", artista="Visual", album="D", portada=str(distinta)))
    ids.append(_crear_pista(db_playlists, "Faltante", artista="Visual", album="F", portada=str(tmp_path / "no-existe.png")))

    playlist_id = svc_bib.crear_playlist("Visual")
    for pista_id in ids:
        svc_bib.agregar_a_playlist(playlist_id, pista_id)

    portadas = svc_bib.obtener_portadas_playlist(playlist_id, limite=4)
    assert len(portadas) == 2
    assert str(distinta) in portadas
    assert Path(svc_bib.actualizar_portada_playlist_si_cambio(playlist_id)).exists()


def test_reordenar_no_regenera_portada_sin_pedirlo(db_playlists, monkeypatch):
    ids = _crear_lote(db_playlists, 5, artista="Orden", album="Lista")
    playlist_id = svc_bib.crear_playlist("Orden ligero")
    for pista_id in ids:
        svc_bib.agregar_a_playlist(playlist_id, pista_id)

    llamadas = []
    monkeypatch.setattr(svc_bib, "actualizar_portada_playlist_si_cambio", lambda playlist_id: llamadas.append(playlist_id))
    assert svc_bib.reordenar_playlist(playlist_id, ids[-1], 1)["ok"]
    assert llamadas == []


def test_playlists_destacadas_shape_y_prioridad(db_playlists):
    favorita = _crear_pista(db_playlists, "Favorita", artista="Adele", album="30", favorita=True, reproducciones=2)
    manual = svc_bib.crear_playlist("Manual")
    svc_bib.agregar_a_playlist(manual, favorita)

    destacadas = svc_bib.playlists_destacadas(5)
    assert destacadas
    primero = destacadas[0]
    assert primero["auto_key"] == svc_bib.PLAYLIST_FAVORITOS_AUTO_KEY
    assert {
        "id",
        "playlist_id",
        "nombre",
        "subtitulo",
        "tipo_playlist",
        "origen",
        "es_anclada",
        "num_pistas",
        "reproducciones_total",
        "portada_ruta",
        "portadas",
    } <= set(primero)
    assert any(item["playlist_id"] == manual for item in destacadas)


def test_modelo_playlists_carga_abre_y_expone_errores_humanos(db_playlists):
    pytest.importorskip("PySide6")
    from PySide6.QtTest import QSignalSpy
    from ui.modelos_qml import ModeloPlaylists

    pista_id = _crear_pista(db_playlists, "Modelo", artista="Tester", album="Suite")
    modelo = ModeloPlaylists()
    spy = QSignalSpy(modelo.playlistsCambiadas)
    modelo.cargar()
    assert spy.count() >= 1
    assert modelo.playlists.total >= 1

    resultado = modelo.crear_playlist("Desde modelo", "")
    assert resultado["ok"] is True
    playlist_id = resultado["playlist_id"]
    modelo.abrir_playlist(playlist_id)
    assert modelo.playlist_activa["nombre"] == "Desde modelo"
    assert modelo.agregar_pista(playlist_id, pista_id)["ok"] is True
    assert modelo.pistas_activas.total == 1
    spy_busqueda = QSignalSpy(modelo.resultadosAgregarCambiados)
    modelo.buscar_pistas_para_playlist("Suite", playlist_id)
    if modelo.resultados_agregar.total == 0:
        # WorkerBusquedaPlaylist es un QThread; su señal `resultados` viaja
        # cross-thread via QueuedConnection. En la suite completa con
        # plataforma "offscreen", QSignalSpy.wait() es flaky en PySide6
        # con queued connections (no siempre dispara el local event loop
        # que entrega la señal al main thread). El fallback robusto es
        # bombear eventos manualmente con QCoreApplication.processEvents()
        # hasta que la señal llegue o se agote un timeout total fijo.
        import time as _time
        from PySide6.QtCore import QCoreApplication
        _deadline = _time.monotonic() + 10.0
        while modelo.resultados_agregar.total == 0 and _time.monotonic() < _deadline:
            QCoreApplication.processEvents()
            _time.sleep(0.02)
    assert modelo.resultados_agregar.total >= 1
    fallo = modelo.crear_playlist("   ", "")
    assert fallo["ok"] is False
    assert fallo["mensaje"]
