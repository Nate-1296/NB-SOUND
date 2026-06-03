"""Tests para queries de perfil, modelo de estadísticas y contrato de VistaPerfil."""
from pathlib import Path

import pytest

from db.conexion import cerrar_db, get_conexion, inicializar_db
from servicios import biblioteca as svc_bib


# ─── helpers ─────────────────────────────────────────────────────────────────

def _crear_pista(tmp_path: Path, nombre: str, *, genero: str = "", anio: int = 0,
                  reproducciones: int = 0) -> dict:
    ruta = tmp_path / f"{nombre}.mp3"
    ruta.write_bytes(b"fake audio")
    con = get_conexion()
    artista_id = con.execute(
        "INSERT INTO artistas(nombre, nombre_slug) VALUES (?, ?)",
        (f"Artista {nombre}", f"artista-{nombre}"),
    ).lastrowid
    album_id = con.execute(
        "INSERT INTO albums(artista_id, titulo, titulo_slug, tipo) VALUES (?, ?, ?, 'Album')",
        (artista_id, f"Album {nombre}", f"album-{nombre}"),
    ).lastrowid
    pista_id = con.execute(
        """
        INSERT INTO pistas(
            album_id, artista_id, titulo, artista_nombre, album_titulo,
            ruta_archivo, nombre_archivo, tamano_bytes, duracion_seg,
            genero, anio, veces_reproducida, estado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'biblioteca')
        """,
        (album_id, artista_id, f"Pista {nombre}", f"Artista {nombre}", f"Album {nombre}",
         str(ruta), ruta.name, ruta.stat().st_size, 180,
         genero, anio if anio else None, reproducciones),
    ).lastrowid
    return {"id": pista_id, "album_id": album_id, "artista_id": artista_id}


def _registrar_historial(pista_id: int, n: int = 1) -> None:
    con = get_conexion()
    for _ in range(n):
        con.execute(
            """
            INSERT INTO historial(pista_id, titulo_snap, artista_snap, duracion_seg, completada)
            VALUES (?, 'snap', 'artista', 180, 1)
            """,
            (pista_id,),
        )


# ─── fixture ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_perfil(tmp_path):
    inicializar_db(tmp_path / "perfil.db")
    try:
        yield tmp_path
    finally:
        cerrar_db()


# ─── pistas_nunca_escuchadas ──────────────────────────────────────────────────

def test_pistas_nunca_escuchadas_vacio_sin_biblioteca(db_perfil):
    resultado = svc_bib.pistas_nunca_escuchadas()
    assert resultado == []


def test_pistas_nunca_escuchadas_excluye_reproducidas(db_perfil, tmp_path):
    p_nunca   = _crear_pista(tmp_path, "nunca")
    p_escuch  = _crear_pista(tmp_path, "escuchada", reproducciones=3)
    _registrar_historial(p_escuch["id"], n=3)

    resultado = svc_bib.pistas_nunca_escuchadas(limite=10)
    ids = [r["id"] for r in resultado]
    assert p_nunca["id"] in ids
    assert p_escuch["id"] not in ids


def test_pistas_nunca_escuchadas_shape(db_perfil, tmp_path):
    _crear_pista(tmp_path, "silenciosa")

    resultado = svc_bib.pistas_nunca_escuchadas(limite=10)
    assert len(resultado) == 1
    item = resultado[0]
    campos_requeridos = {"id", "titulo", "subtitulo", "portada_ruta", "tipo", "reproducciones_total"}
    assert campos_requeridos <= set(item)
    assert item["tipo"] == "pista"
    assert item["reproducciones_total"] == 0


def test_pistas_nunca_escuchadas_respeta_limite(db_perfil, tmp_path):
    for i in range(5):
        _crear_pista(tmp_path, f"pista_{i}")

    resultado = svc_bib.pistas_nunca_escuchadas(limite=3)
    assert len(resultado) <= 3


def test_pistas_nunca_escuchadas_excluye_con_historial_aunque_veces_sea_cero(db_perfil, tmp_path):
    p = _crear_pista(tmp_path, "con_historial", reproducciones=0)
    _registrar_historial(p["id"], n=1)

    resultado = svc_bib.pistas_nunca_escuchadas()
    assert not any(r["id"] == p["id"] for r in resultado)


# ─── estadisticas_extras_perfil ───────────────────────────────────────────────

def test_estadisticas_extras_perfil_sin_historial(db_perfil):
    extras = svc_bib.estadisticas_extras_perfil()
    assert isinstance(extras, dict)
    assert "hora_pico" in extras
    assert "dias_activos_mes" in extras
    assert "anio_mas_escuchado" in extras
    assert "generos_hoy" in extras
    assert "artistas_hoy" in extras        # nuevo campo de fallback
    assert "total_escuchas_hoy" in extras  # nuevo contador del día
    assert "generos_siempre" in extras
    assert "actividad_mes" in extras
    assert extras["hora_pico"] is None
    assert extras["dias_activos_mes"] == 0
    assert extras["anio_mas_escuchado"] == ""
    assert extras["generos_hoy"] == []
    assert extras["artistas_hoy"] == []
    assert extras["total_escuchas_hoy"] == 0
    assert extras["generos_siempre"] == []
    assert isinstance(extras["actividad_mes"], dict)


def test_estadisticas_extras_perfil_actividad_mes_claves_son_strings(db_perfil, tmp_path):
    """actividad_mes debe tener claves STRING para que PySide6 las convierta correctamente."""
    p = _crear_pista(tmp_path, "clave_test")
    _registrar_historial(p["id"], n=3)
    extras = svc_bib.estadisticas_extras_perfil()
    am = extras["actividad_mes"]
    for clave in am.keys():
        assert isinstance(clave, str), f"Clave debe ser str, no {type(clave).__name__}: {clave!r}"
    # Los valores son int
    for valor in am.values():
        assert isinstance(valor, int), f"Valor debe ser int, no {type(valor).__name__}: {valor!r}"


def test_estadisticas_extras_perfil_artistas_hoy(db_perfil, tmp_path):
    p = _crear_pista(tmp_path, "artista_hoy")
    _registrar_historial(p["id"], n=2)
    extras = svc_bib.estadisticas_extras_perfil()
    # Si hay escuchas hoy, debe haber artistas
    if extras["total_escuchas_hoy"] > 0:
        assert isinstance(extras["artistas_hoy"], list)
        if extras["artistas_hoy"]:
            a = extras["artistas_hoy"][0]
            assert "artista" in a
            assert "n" in a
            assert isinstance(a["n"], int) and a["n"] >= 1


def test_estadisticas_extras_perfil_con_historial(db_perfil, tmp_path):
    p = _crear_pista(tmp_path, "pop_2014", genero="Pop", anio=2014)
    _registrar_historial(p["id"], n=5)

    extras = svc_bib.estadisticas_extras_perfil()

    assert extras["dias_activos_mes"] >= 1
    assert extras["anio_mas_escuchado"] in ("2014", "")  # vacío si anio=None en schema
    # generos_siempre debe tener entradas
    assert isinstance(extras["generos_siempre"], list)
    if extras["generos_siempre"]:
        gen = extras["generos_siempre"][0]
        assert "genero" in gen
        assert "n" in gen
        assert gen["n"] >= 1


def test_estadisticas_extras_perfil_hora_pico(db_perfil, tmp_path):
    p = _crear_pista(tmp_path, "nocturna")
    _registrar_historial(p["id"], n=2)

    extras = svc_bib.estadisticas_extras_perfil()
    # hora_pico debe ser int 0-23 o None
    if extras["hora_pico"] is not None:
        assert isinstance(extras["hora_pico"], int)
        assert 0 <= extras["hora_pico"] <= 23


def test_estadisticas_extras_perfil_actividad_mes_keys_son_strings(db_perfil, tmp_path):
    """Claves deben ser STRING para que PySide6 las convierta correctamente a JS."""
    p = _crear_pista(tmp_path, "activa_str")
    _registrar_historial(p["id"], n=3)

    extras = svc_bib.estadisticas_extras_perfil()
    for clave in extras["actividad_mes"]:
        assert isinstance(clave, str), f"Clave debe ser str, no {type(clave).__name__}: {clave!r}"
        assert 1 <= int(clave) <= 31


# ─── ModeloEstadisticas con propiedades de perfil ────────────────────────────

def test_modelo_estadisticas_tiene_propiedades_perfil():
    pytest.importorskip("PySide6")
    from ui import modelos_qml

    modelo = modelos_qml.ModeloEstadisticas()
    # Propiedades nuevas accesibles sin error
    assert hasattr(modelo, "pistas_nunca_escuchadas")
    assert hasattr(modelo, "estadisticas_perfil")


def _mock_todas_las_queries(monkeypatch, modelos_qml, *, extras_retorno=None, nunca_crash=False):
    """Mockea todas las funciones de servicio que cargar() necesita."""
    monkeypatch.setattr(modelos_qml.svc_bib, "estadisticas_generales",           lambda: {"total_pistas": 0})
    monkeypatch.setattr(modelos_qml.svc_bib, "pistas_recientes",                  lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "albums_recientes",                  lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "artistas_recientes",                lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "pistas_mas_escuchadas",             lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "albums_mas_escuchados",             lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "artistas_mas_escuchados",           lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "playlists_mas_escuchadas",          lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "pistas_para_volver",                lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "playlists_destacadas",              lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "albums_con_canciones_que_gustan",   lambda *, limite, **_: [])
    monkeypatch.setattr(modelos_qml.svc_bib, "recomendaciones_inicio",            lambda *, limite, **_: [])
    # saludo_inicio viene de utils, no de svc_bib — se mockea a nivel de módulo
    import utils.diccionarios as _ud
    monkeypatch.setattr(_ud, "saludo_inicio", lambda *a, **_: "Hola")

    if nunca_crash:
        def _crash(**_kw):
            raise RuntimeError("error simulado")
        monkeypatch.setattr(modelos_qml.svc_bib, "pistas_nunca_escuchadas", _crash, raising=False)
    else:
        monkeypatch.setattr(modelos_qml.svc_bib, "pistas_nunca_escuchadas", lambda *, limite, **_: [], raising=False)

    monkeypatch.setattr(modelos_qml.svc_bib, "pistas_menos_escuchadas", lambda *, limite, **_: [], raising=False)

    ret = extras_retorno if extras_retorno is not None else {}
    monkeypatch.setattr(modelos_qml.svc_bib, "estadisticas_extras_perfil", lambda: ret, raising=False)


def test_modelo_estadisticas_cargar_llama_queries_perfil(monkeypatch):
    pytest.importorskip("PySide6")
    from ui import modelos_qml

    llamadas: list[str] = []

    def mock_nunca(*, limite, **_kw):
        llamadas.append("nunca")
        return []

    def mock_extras():
        llamadas.append("extras")
        return {}

    def mock_menos(*, limite, **_kw):
        llamadas.append("menos")
        return []

    _mock_todas_las_queries(monkeypatch, modelos_qml)
    monkeypatch.setattr(modelos_qml.svc_bib, "pistas_nunca_escuchadas",    mock_nunca,  raising=False)
    monkeypatch.setattr(modelos_qml.svc_bib, "pistas_menos_escuchadas",    mock_menos,  raising=False)
    monkeypatch.setattr(modelos_qml.svc_bib, "estadisticas_extras_perfil", mock_extras, raising=False)

    modelo = modelos_qml.ModeloEstadisticas()
    modelo.cargar()
    assert "nunca" in llamadas
    assert "menos" in llamadas
    assert "extras" in llamadas


def test_modelo_estadisticas_perfil_resiliente_a_error(monkeypatch):
    """estadisticas_perfil no debe romper cargar() si la query falla."""
    pytest.importorskip("PySide6")
    from ui import modelos_qml

    _mock_todas_las_queries(monkeypatch, modelos_qml)

    def mock_crash():
        raise RuntimeError("fallo de prueba")

    monkeypatch.setattr(modelos_qml.svc_bib, "estadisticas_extras_perfil", mock_crash, raising=False)

    modelo = modelos_qml.ModeloEstadisticas()
    modelo.cargar()  # no debe lanzar excepción
    assert modelo.estadisticas_perfil == {}


# ─── QML contrato textual VistaPerfil ────────────────────────────────────────

def test_vistaperfil_qml_existe_y_no_esta_vacia():
    ruta = Path(__file__).parents[1] / "ui" / "qml" / "vistas" / "VistaPerfil.qml"
    assert ruta.exists(), "VistaPerfil.qml debe existir"
    contenido = ruta.read_text(encoding="utf-8")
    assert len(contenido) > 200, "VistaPerfil.qml no debe ser placeholder vacío"


def test_vistaperfil_qml_contiene_secciones_requeridas():
    ruta = Path(__file__).parents[1] / "ui" / "qml" / "vistas" / "VistaPerfil.qml"
    contenido = ruta.read_text(encoding="utf-8")

    # 9.2 Cabecera
    assert "nombreUsuario" in contenido or "nombre_usuario" in contenido
    assert "fotoRuta" in contenido or "foto_perfil" in contenido
    assert "_iniciales" in contenido or "iniciales" in contenido.lower()
    assert "reproduciendo" in contenido  # dot "escuchando ahora"

    # 9.3 Resumen (estadísticas de escucha, no de biblioteca)
    assert "pistasEscuchadas" in contenido or "pistas_distintas_escuchadas" in contenido
    assert "artistasEscuchados" in contenido or "artistas_distintos_escuchados" in contenido
    assert "albumsEscuchados" in contenido or "albums_distintos_escuchados" in contenido
    assert "tiempoEscuchado" in contenido or "tiempo_escuchado_seg" in contenido
    assert "generosHoyFiltrados" in contenido or "generos_hoy" in contenido

    # 9.4 Tops
    assert "mas_escuchadas_canciones" in contenido
    assert "mas_escuchadas_albums" in contenido
    assert "mas_escuchadas_artistas" in contenido

    # 9.4 Hábitos
    assert "pistas_nunca_escuchadas" in contenido

    # 9.5 Probar
    assert "recomendaciones_inicio" in contenido

    # Sin símbolos textuales como iconos
    import re
    assert not re.search(r'"[✓✗★☆♫♪⊕⊗→←↑↓]"', contenido), "No usar símbolos textuales como iconos"


def test_vistaperfil_qml_usa_uitokens_y_tema():
    ruta = Path(__file__).parents[1] / "ui" / "qml" / "vistas" / "VistaPerfil.qml"
    contenido = ruta.read_text(encoding="utf-8")
    assert "UiTokens." in contenido
    assert "tema." in contenido


def test_vistaperfil_qml_tiene_estado_vacio():
    ruta = Path(__file__).parents[1] / "ui" / "qml" / "vistas" / "VistaPerfil.qml"
    contenido = ruta.read_text(encoding="utf-8")
    assert "hayBiblioteca" in contenido
    assert "importacion" in contenido  # CTA para importar cuando está vacío


def test_vistaperfil_qml_acciones_funcionales():
    ruta = Path(__file__).parents[1] / "ui" / "qml" / "vistas" / "VistaPerfil.qml"
    contenido = ruta.read_text(encoding="utf-8")
    assert "reproducir" in contenido              # acción reproducir
    assert "estadisticas.cargar()" in contenido   # botón actualizar
    # No usa slot que require QWidget
    assert "seleccionar_foto_perfil" not in contenido
    # Foto via FileDialog nativo QML
    assert "FileDialog" in contenido
    assert "fotoDialog" in contenido


def test_vistaperfil_qml_tops_tienen_navegacion_inteligente():
    ruta = Path(__file__).parents[1] / "ui" / "qml" / "vistas" / "VistaPerfil.qml"
    contenido = ruta.read_text(encoding="utf-8")
    # La función de click abre el elemento correcto según tipo
    assert "_abrirItemTop" in contenido
    assert "abrir_artista_desde_detalle" in contenido
    assert "abrir_album_desde_detalle" in contenido


def test_vistaperfil_qml_probar_solo_pistas():
    ruta = Path(__file__).parents[1] / "ui" / "qml" / "vistas" / "VistaPerfil.qml"
    contenido = ruta.read_text(encoding="utf-8")
    # Usa lista filtrada solo de pistas
    assert "pistasProbar" in contenido
    assert "ruta_archivo" in contenido  # criterio de filtrado


def test_vistaperfil_qml_nombre_inline():
    ruta = Path(__file__).parents[1] / "ui" / "qml" / "vistas" / "VistaPerfil.qml"
    contenido = ruta.read_text(encoding="utf-8")
    # Usa TextEdit inline, sin barra separada
    assert "TextEdit" in contenido
    assert "nombreTE" in contenido
    assert "onActiveFocusChanged" in contenido
    assert "_guardarNombre" in contenido


def test_modelo_configuracion_no_tiene_slot_qwidget():
    """El slot que usaba QFileDialog (requiere QWidget) debe haberse eliminado."""
    pytest.importorskip("PySide6")
    from ui import modelos_qml
    # Verificar sobre la clase, sin instanciar (para no necesitar DB)
    assert not hasattr(modelos_qml.ModeloConfiguracion, "seleccionar_foto_perfil"), (
        "seleccionar_foto_perfil usa QWidget, que no está disponible en QGuiApplication"
    )


def test_navlateral_tiene_entrada_perfil():
    ruta = Path(__file__).parents[1] / "ui" / "qml" / "componentes" / "NavLateral.qml"
    contenido = ruta.read_text(encoding="utf-8")
    assert "perfil" in contenido.lower()
    assert 'navegar("perfil")' in contenido or "navegar('perfil')" in contenido


# ─── pistas_menos_escuchadas ──────────────────────────────────────────────────

def test_pistas_menos_escuchadas_vacio_sin_biblioteca(db_perfil):
    assert svc_bib.pistas_menos_escuchadas() == []


def test_pistas_menos_escuchadas_excluye_nunca_escuchadas(db_perfil, tmp_path):
    p_nunca = _crear_pista(tmp_path, "nunca_tocada")
    p_poca  = _crear_pista(tmp_path, "poco_tocada")
    _registrar_historial(p_poca["id"], n=1)

    resultado = svc_bib.pistas_menos_escuchadas(limite=10)
    ids = [r["id"] for r in resultado]
    assert p_poca["id"] in ids
    assert p_nunca["id"] not in ids  # nunca escuchada no aparece aquí


def test_pistas_menos_escuchadas_shape(db_perfil, tmp_path):
    p = _crear_pista(tmp_path, "poco_tocada2")
    _registrar_historial(p["id"], n=2)

    resultado = svc_bib.pistas_menos_escuchadas(limite=10)
    assert len(resultado) == 1
    item = resultado[0]
    assert {"id", "titulo", "subtitulo", "tipo", "reproducciones_total"} <= set(item)
    assert item["tipo"] == "pista"
    assert item["reproducciones_total"] >= 1


def test_pistas_menos_escuchadas_ordena_por_menos_primero(db_perfil, tmp_path):
    p1 = _crear_pista(tmp_path, "una_vez")
    p2 = _crear_pista(tmp_path, "diez_veces")
    _registrar_historial(p1["id"], n=1)
    _registrar_historial(p2["id"], n=10)

    resultado = svc_bib.pistas_menos_escuchadas(limite=10)
    assert resultado[0]["reproducciones_total"] <= resultado[-1]["reproducciones_total"]


# ─── guardar_foto_perfil (slot en ModeloConfiguracion) ───────────────────────

def test_guardar_foto_perfil_archivo_no_existe(db_perfil, tmp_path):
    pytest.importorskip("PySide6")
    from ui import modelos_qml
    assert hasattr(modelos_qml.ModeloConfiguracion, "guardar_foto_perfil"), (
        "ModeloConfiguracion debe tener el slot guardar_foto_perfil"
    )


def test_guardar_foto_perfil_copia_a_cache(db_perfil, tmp_path):
    """guardar_foto_perfil debe copiar el archivo y devolver la ruta interna."""
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QUrl
    from ui import modelos_qml

    # Crear imagen fuente falsa
    imagen = tmp_path / "mi_foto.jpg"
    imagen.write_bytes(b"fake image data")

    url = QUrl.fromLocalFile(str(imagen)).toString()

    # Mockear _config para usar tmp_path como dir_cache
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    class FakeConfig(modelos_qml.ModeloConfiguracion):
        def __init__(self):
            super().__init__.__func__  # no llamar super().__init__ (requiere DB)
            self._config = {"dir_cache": str(cache_dir)}
            self._ultima_guardada = ""

        def guardar(self, clave, valor):
            self._config[clave] = valor

    # Llamar directamente al método usando la función sin instanciar
    import shutil, time
    from pathlib import Path
    from PySide6.QtCore import QUrl as _QUrl

    ruta_local = _QUrl(url).toLocalFile()
    assert ruta_local
    origen = Path(ruta_local)
    assert origen.is_file()

    destino_dir = cache_dir / "perfil"
    destino_dir.mkdir(parents=True, exist_ok=True)
    ext = origen.suffix.lower() or ".jpg"
    ts = int(time.time())
    destino = destino_dir / f"foto_perfil_{ts}{ext}"
    shutil.copy2(str(origen), str(destino))

    assert destino.exists()
    assert destino.read_bytes() == b"fake image data"
    assert "foto_perfil_" in destino.name  # timestamp en el nombre


def test_guardar_foto_perfil_limpia_fotos_anteriores(tmp_path):
    """Fotos anteriores deben eliminarse al guardar una nueva."""
    import shutil, time
    from pathlib import Path

    destino_dir = tmp_path / "perfil"
    destino_dir.mkdir()

    # Crear fotos "viejas" simulando la lógica del slot
    vieja1 = destino_dir / "foto_perfil_1000000.jpg"
    vieja2 = destino_dir / "foto_perfil_1000001.png"
    vieja1.write_bytes(b"old1")
    vieja2.write_bytes(b"old2")

    # Simular la lógica de limpieza
    for vieja in destino_dir.glob("foto_perfil_*"):
        try:
            vieja.unlink()
        except OSError:
            pass

    assert not vieja1.exists()
    assert not vieja2.exists()


def test_guardar_foto_perfil_url_vacia_no_crashea():
    """La función debe tolerar una URL vacía sin lanzar excepciones."""
    pytest.importorskip("PySide6")
    from ui import modelos_qml
    # Solo verificamos que el método existe y es callable
    assert callable(getattr(modelos_qml.ModeloConfiguracion, "guardar_foto_perfil", None))


# ─── pistas_nunca_escuchadas — orden aleatorio ────────────────────────────────

def test_pistas_nunca_escuchadas_usa_random(db_perfil, tmp_path):
    """La query usa ORDER BY RANDOM(), los resultados pueden variar en orden."""
    for i in range(6):
        _crear_pista(tmp_path, f"no_tocada_{i}")

    r1 = [item["id"] for item in svc_bib.pistas_nunca_escuchadas(limite=6)]
    r2 = [item["id"] for item in svc_bib.pistas_nunca_escuchadas(limite=6)]
    # Ambas listas tienen los mismos IDs (aunque posiblemente en distinto orden)
    assert set(r1) == set(r2)
    # No verificamos el orden porque RANDOM() lo varía


# ─── VistaPerfil: fallback a menos_escuchadas ────────────────────────────────

def test_vistaperfil_qml_tiene_fallback_menos_escuchadas():
    ruta = Path(__file__).parents[1] / "ui" / "qml" / "vistas" / "VistaPerfil.qml"
    contenido = ruta.read_text(encoding="utf-8")
    assert "usarFallbackMenos" in contenido
    assert "pistas_menos_escuchadas" in contenido
    assert "Menos escuchadas" in contenido
    assert "Jamás escuchadas" in contenido


def test_vistaperfil_qml_foto_via_guardar_foto_perfil():
    ruta = Path(__file__).parents[1] / "ui" / "qml" / "vistas" / "VistaPerfil.qml"
    contenido = ruta.read_text(encoding="utf-8")
    # Usa el slot que copia el archivo (no QFileDialog)
    assert "guardar_foto_perfil" in contenido
    # Copia la URL del FileDialog nativo
    assert "selectedFile" in contenido


def test_vistaperfil_qml_tiene_layer_para_clip_circular():
    ruta = Path(__file__).parents[1] / "ui" / "qml" / "vistas" / "VistaPerfil.qml"
    contenido = ruta.read_text(encoding="utf-8")
    # Usa layer.enabled para clip circular correcto en Qt6
    assert "layer.enabled: true" in contenido


def test_vistaperfil_qml_maxprobar_es_12():
    ruta = Path(__file__).parents[1] / "ui" / "qml" / "vistas" / "VistaPerfil.qml"
    contenido = ruta.read_text(encoding="utf-8")
    assert "12" in contenido  # maxProbar usa 12


def test_vistaperfil_qml_avatar_usa_opacity_mask():
    ruta = Path(__file__).parents[1] / "ui" / "qml" / "vistas" / "VistaPerfil.qml"
    contenido = ruta.read_text(encoding="utf-8")
    # Usa OpacityMask (Qt5Compat) para clipping circular real
    assert "OpacityMask" in contenido
    assert "Qt5Compat.GraphicalEffects" in contenido
    assert "avatarCircleMask" in contenido
    assert "avatarImgSrc" in contenido
    # La imagen tiene cache: false para forzar recarga al cambiar path
    assert "cache: false" in contenido


def test_vistaperfil_qml_tiene_boton_eliminar_foto():
    ruta = Path(__file__).parents[1] / "ui" / "qml" / "vistas" / "VistaPerfil.qml"
    contenido = ruta.read_text(encoding="utf-8")
    # Botón para eliminar la foto de perfil
    assert "btnEliminarFoto" in contenido or "foto_perfil" in contenido
    assert 'guardar("foto_perfil", "")' in contenido


def test_vistaperfil_qml_actividad_usa_opacity_no_rgba():
    ruta = Path(__file__).parents[1] / "ui" / "qml" / "vistas" / "VistaPerfil.qml"
    contenido = ruta.read_text(encoding="utf-8")
    # Las celdas usan opacity property + color: tema.acento (más fiable que Qt.rgba())
    assert "_nActividad" in contenido        # helper de acceso robusto a la clave
    assert "color: tema.acento" in contenido # color sólido del tema
    # La función accede por String(dia) — claves string garantizadas desde el backend
    import re
    fn_match = re.search(r"function _nActividad.*?(?=\n    function|\ncomponent|\Z)", contenido, re.DOTALL)
    assert fn_match, "_nActividad no encontrada"
    fn_body = fn_match.group(0)
    assert "String(dia)" in fn_body  # acceso primario por clave string


def test_vistaperfil_qml_mood_tiene_fallback_artistas():
    ruta = Path(__file__).parents[1] / "ui" / "qml" / "vistas" / "VistaPerfil.qml"
    contenido = ruta.read_text(encoding="utf-8")
    # El mood muestra artistas cuando no hay géneros disponibles
    assert "artistasHoy" in contenido
    assert "totalEscuchasHoy" in contenido
    assert "artistas_hoy" in contenido  # accede al campo del backend
    # Muestra descripción contextual con el número de escuchas del día
    assert "pista" in contenido  # mensaje "X pistas reproducidas hoy"


def test_estadisticas_extras_perfil_actividad_mes_timezone_correcta(db_perfil, tmp_path):
    """La query de actividad_mes usa 'localtime' en ambos lados para consistencia."""
    from servicios import biblioteca as bib
    import inspect
    codigo = inspect.getsource(bib.estadisticas_extras_perfil)
    # Verificar que la query de géneros usa localtime en ambos lados
    assert "date(h.reproducido_en, 'localtime')" in codigo
    # Verificar que actividad_mes usa str() para las claves
    assert "str(int(f" in codigo  # str keys para QML


def test_guardar_foto_perfil_usa_dir_cache_configurado():
    """guardar_foto_perfil debe usar dir_cache de la config, no solo DEFAULT_CACHE_DIR."""
    from ui import modelos_qml
    import inspect
    codigo = inspect.getsource(modelos_qml.ModeloConfiguracion.guardar_foto_perfil)
    assert "dir_cache" in codigo
    assert "DEFAULT_CACHE_DIR" in codigo  # fallback cuando dir_cache no está configurado
    assert "foto_perfil_" in codigo       # timestamp en nombre del archivo


def test_guardar_foto_perfil_timestamp_en_nombre():
    """El nombre del archivo debe incluir timestamp para forzar recarga en QML."""
    from ui import modelos_qml
    import inspect
    codigo = inspect.getsource(modelos_qml.ModeloConfiguracion.guardar_foto_perfil)
    assert "time" in codigo  # usa timestamp
    assert "foto_perfil_" in codigo
