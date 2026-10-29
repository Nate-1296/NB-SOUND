"""
Tests para tokens semánticos de tema: textoSobreAcento, textoSobrePeligro,
textoInmersivo, y la lógica de contraste WCAG.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QGuiApplication

from db.conexion import inicializar_db, cerrar_db
from ui.modelos_qml import ModeloTema, ModeloConfiguracion


@pytest.fixture(scope="module")
def app():
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app


@pytest.fixture()
def tema_inicializado(tmp_path, app):
    db = tmp_path / "tema_test.db"
    inicializar_db(db)
    cfg = ModeloConfiguracion()
    tema = ModeloTema(cfg)
    try:
        yield tema
    finally:
        cerrar_db()


def test_luminancia_negro_es_cero(tema_inicializado):
    assert ModeloTema._luminancia_relativa("#000000") == 0.0


def test_luminancia_blanco_es_uno(tema_inicializado):
    assert ModeloTema._luminancia_relativa("#ffffff") == pytest.approx(1.0, abs=0.01)


def test_luminancia_color_invalido_devuelve_default(tema_inicializado):
    # Default = 1.0 → texto negro por defecto
    assert ModeloTema._luminancia_relativa("nohex") == 1.0
    assert ModeloTema._luminancia_relativa("") == 1.0
    assert ModeloTema._luminancia_relativa(None) == 1.0


def test_texto_sobre_acento_en_tema_oscuro(tema_inicializado):
    # negro_puro: acento #00e5ff (cian brillante) — luminancia alta → texto negro
    tema_inicializado.aplicar_tema("negro_puro")
    assert tema_inicializado.textoSobreAcento == "#000000"


def test_texto_sobre_acento_en_tema_claro(tema_inicializado):
    # menta_fresh: acento #1abc9c (verde oscuro) — luminancia baja → texto blanco
    tema_inicializado.aplicar_tema("menta_fresh")
    assert tema_inicializado.textoSobreAcento == "#ffffff"


def test_texto_inmersivo_siempre_es_blanco(tema_inicializado):
    """textoInmersivo debe ser blanco en cualquier tema porque
    las superficies inmersivas (lyrics, reproducción expandida) imponen
    fondo dinámico oscuro."""
    for tema_id in ["negro_puro", "menta_fresh", "glacial", "nieve"]:
        tema_inicializado.aplicar_tema(tema_id)
        assert tema_inicializado.textoInmersivo == "#ffffff", (
            f"Tema {tema_id}: textoInmersivo debería ser blanco"
        )


def test_texto_sobre_peligro_es_consistente(tema_inicializado):
    """textoSobrePeligro debe ser negro o blanco según luminancia del color peligro."""
    tema_inicializado.aplicar_tema("negro_puro")
    resultado = tema_inicializado.textoSobrePeligro
    assert resultado in ("#000000", "#ffffff")


def test_texto_sobre_exito_es_consistente(tema_inicializado):
    """textoSobreExito existe y devuelve negro o blanco segun luminancia."""
    tema_inicializado.aplicar_tema("negro_puro")
    resultado = tema_inicializado.textoSobreExito
    assert resultado in ("#000000", "#ffffff")


def test_texto_sobre_advertencia_es_consistente(tema_inicializado):
    """textoSobreAdvertencia existe y devuelve negro o blanco segun luminancia."""
    tema_inicializado.aplicar_tema("negro_puro")
    resultado = tema_inicializado.textoSobreAdvertencia
    assert resultado in ("#000000", "#ffffff")


def test_tokens_texto_sobre_color_funcionan_en_todos_los_temas(tema_inicializado):
    """Todos los tokens textoSobreX deben devolver valores validos en todos los temas."""
    temas_ids = [t["id"] for t in tema_inicializado.temas_disponibles]
    assert len(temas_ids) >= 10  # garantiza que recorremos varios

    for tema_id in temas_ids:
        tema_inicializado.aplicar_tema(tema_id)
        for atributo in (
            "textoSobreAcento",
            "textoSobrePeligro",
            "textoSobreExito",
            "textoSobreAdvertencia",
        ):
            valor = getattr(tema_inicializado, atributo)
            assert valor in ("#000000", "#ffffff"), (
                f"Tema {tema_id} produce {atributo}={valor} (no normalizado)"
            )


def test_todos_los_temas_definen_acento_valido(tema_inicializado):
    """Cada tema declarado debe tener un acento que produzca textoSobreAcento válido."""
    for tema_id in ModeloTema._TEMAS.keys():
        tema_inicializado.aplicar_tema(tema_id)
        resultado = tema_inicializado.textoSobreAcento
        assert resultado in ("#000000", "#ffffff"), (
            f"Tema {tema_id}: textoSobreAcento inválido: {resultado}"
        )


def test_cambio_tema_emite_temacambiado(tema_inicializado, app):
    """Verifica que aplicar_tema emite la señal temaCambiado."""
    eventos = []
    tema_inicializado.temaCambiado.connect(lambda: eventos.append(1))
    tema_inicializado.aplicar_tema("aurora_boreal")
    assert len(eventos) >= 1
