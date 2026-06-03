"""
Tests para los 3 fixes finales:
  1) Búsqueda: spacing: 0 en sub-ColumnLayout de cada sección (evita gap
     visual entre Favoritos y la siguiente sección).
  2) Tema: properties de color devuelven QColor (no string) para que
     `tema.X.r .g .b` funcione directo y `Qt.rgba(...)` no pinte negro.
  3) Favoritos: ModeloBiblioteca emite señal `favoritaCambiada` y
     ModeloPlaylists la escucha para refrescar la playlist "Me gusta".
"""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtGui import QColor, QGuiApplication

from db.conexion import inicializar_db, cerrar_db
from ui.modelos_qml import ModeloBiblioteca, ModeloPlaylists, ModeloTema, ModeloConfiguracion


QML_DIR = Path(__file__).resolve().parent.parent / "ui" / "qml"


@pytest.fixture(scope="module")
def app():
    yield QGuiApplication.instance() or QGuiApplication([])


# ─── Fix 1: spacing en búsqueda ──────────────────────────────────────────────

def test_busqueda_usa_filas_planas():
    """Las secciones se renderizan APLANADAS (sin sub-ColumnLayouts) para
    evitar gap residual al final de cada sección con >1 item."""
    contenido = (QML_DIR / "vistas" / "VistaBusqueda.qml").read_text(encoding="utf-8")
    assert "_filasPlanas" in contenido
    assert "model: raiz._filasPlanas" in contenido
    # Cada tipo de fila tiene su propio Component leaf (no envuelto en ColumnLayout)
    for comp in ("_compHeader", "_compFilaPistaFav", "_compFilaPista",
                 "_compFilaArtista", "_compFilaAlbum"):
        assert f"id: {comp}" in contenido, f"Falta Component {comp}"


# ─── Fix 2: tema QColor ──────────────────────────────────────────────────────

def test_tema_properties_devuelven_qcolor(app, tmp_path):
    """Las properties de color del tema deben ser QColor (no str) para que
    `tema.X.r .g .b` funcione directamente en QML."""
    db = tmp_path / "tema_qcolor.db"
    inicializar_db(db)
    try:
        cfg = ModeloConfiguracion()
        tema = ModeloTema(cfg)
        # Tipo retornado debe ser QColor
        for nombre in ("fondo", "fondoElevado", "superficie", "superficieAlt",
                       "borde", "texto", "textoSec", "textoMuted",
                       "acento", "acentoFuerte", "hover", "seleccion",
                       "exito", "peligro", "advertencia"):
            valor = getattr(tema, nombre)
            assert isinstance(valor, QColor), (
                f"tema.{nombre} debe ser QColor (es {type(valor).__name__})"
            )
            assert valor.isValid(), f"tema.{nombre} produjo QColor inválido"
    finally:
        cerrar_db()


def test_tema_qcolor_tiene_componentes_rgb_validos(app, tmp_path):
    """El QColor del tema debe exponer .red() .green() .blue() válidos."""
    db = tmp_path / "tema_rgb.db"
    inicializar_db(db)
    try:
        cfg = ModeloConfiguracion()
        tema = ModeloTema(cfg)
        tema.aplicar_tema("negro_puro")
        acento = tema.acento
        assert isinstance(acento, QColor)
        # negro_puro acento = "#00e5ff"
        assert acento.red() == 0
        assert acento.green() == 0xe5
        assert acento.blue() == 0xff
    finally:
        cerrar_db()


# ─── Fix 3: favoritaCambiada propaga a playlists ─────────────────────────────

def test_biblioteca_emite_favorita_cambiada(app, tmp_path):
    """ModeloBiblioteca debe emitir `favoritaCambiada(pista_id, nueva)` al
    toggle_favorita."""
    db = tmp_path / "fav_signal.db"
    inicializar_db(db)
    try:
        from db.conexion import ejecutar, ejecutar_y_obtener_id
        # Insertar pista mínima necesaria
        artista_id = ejecutar_y_obtener_id(
            "INSERT INTO artistas (nombre, nombre_slug) VALUES (?, ?)", ("ArtistTest", "artisttest"))
        album_id = ejecutar_y_obtener_id(
            "INSERT INTO albums (titulo, titulo_slug, artista_id) VALUES (?, ?, ?)",
            ("AlbumTest", "albumtest", artista_id),
        )
        pista_id = ejecutar_y_obtener_id(
            "INSERT INTO pistas (titulo, artista_id, album_id, ruta_archivo, nombre_archivo, estado, favorita) VALUES (?, ?, ?, ?, ?, 'biblioteca', 0)",
            ("PistaTest", artista_id, album_id, "/tmp/pista_test.mp3", "pista_test.mp3"),
        )

        bib = ModeloBiblioteca()
        eventos = []
        bib.favoritaCambiada.connect(lambda pid, nueva: eventos.append((pid, nueva)))

        # Toggle 1: 0 → 1
        bib.toggle_favorita(int(pista_id))
        # Toggle 2: 1 → 0
        bib.toggle_favorita(int(pista_id))

        assert len(eventos) == 2
        assert eventos[0] == (int(pista_id), True)
        assert eventos[1] == (int(pista_id), False)
    finally:
        cerrar_db()


def test_playlists_conecta_biblioteca_y_refresca(app, tmp_path):
    """ModeloPlaylists.conectar_biblioteca enlaza la señal y refresca la lista
    cuando se toggle un favorito."""
    db = tmp_path / "playlists_refresh.db"
    inicializar_db(db)
    try:
        from db.conexion import ejecutar_y_obtener_id
        artista_id = ejecutar_y_obtener_id(
            "INSERT INTO artistas (nombre, nombre_slug) VALUES (?, ?)", ("A", "a"))
        album_id = ejecutar_y_obtener_id(
            "INSERT INTO albums (titulo, titulo_slug, artista_id) VALUES (?, ?, ?)", ("Al", "al", artista_id))
        pista_id = ejecutar_y_obtener_id(
            "INSERT INTO pistas (titulo, artista_id, album_id, ruta_archivo, nombre_archivo, estado, favorita) VALUES (?, ?, ?, ?, ?, 'biblioteca', 0)",
            ("P", artista_id, album_id, "/tmp/p.mp3", "p.mp3"))

        bib = ModeloBiblioteca()
        playlists = ModeloPlaylists()
        playlists.conectar_biblioteca(bib)

        refrescos = []
        playlists.playlistsCambiadas.connect(lambda: refrescos.append(1))

        bib.toggle_favorita(int(pista_id))
        # Procesa el event loop una vez para que la señal se propague
        app.processEvents()

        assert len(refrescos) >= 1, "playlists.cargar debió llamarse tras toggle"
    finally:
        cerrar_db()
