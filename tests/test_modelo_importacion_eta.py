from unittest.mock import patch

import pytest

from db.conexion import cerrar_db, inicializar_db
from ui.modelos_qml import ModeloImportacion


@pytest.fixture()
def db_tmp(tmp_path):
    ruta = tmp_path / "importacion_test.db"
    inicializar_db(ruta)
    try:
        yield ruta
    finally:
        cerrar_db()


def test_eta_oculta_al_inicio_hasta_tener_muestra_suficiente(db_tmp):
    modelo = ModeloImportacion()
    modelo._en_ejecucion = True
    modelo._inicio_monotonic = 100.0

    with patch("ui.modelos_qml.time.monotonic", return_value=101.0):
        modelo._al_progreso(1, 10, "a.mp3", "procesando")

    assert modelo.eta_seg == -1


def test_eta_suavizada_con_ema_evitar_saltos_absurdos(db_tmp):
    modelo = ModeloImportacion()
    modelo._en_ejecucion = True
    modelo._inicio_monotonic = 100.0

    with patch("ui.modelos_qml.time.monotonic", side_effect=[112.0, 130.0]):
        modelo._al_progreso(4, 10, "b.mp3", "procesando")  # ~18s
        eta_1 = modelo.eta_seg
        modelo._al_progreso(5, 10, "c.mp3", "procesando")  # crudo seria ~30s sin suavizar
        eta_2 = modelo.eta_seg

    assert eta_1 == 18
    assert 15 <= eta_2 <= 25
    assert eta_2 < 30


def test_eta_se_resetea_en_completar_cancelar_y_error(db_tmp):
    modelo = ModeloImportacion()
    modelo._en_ejecucion = True
    modelo._ultimo_eta_seg = 42

    modelo._al_completar({"ok": True})
    assert modelo.eta_seg == 0

    modelo._en_ejecucion = True
    modelo._ultimo_eta_seg = 42
    modelo._al_cancelar({"cancelada": True})
    assert modelo.eta_seg == -1

    modelo._en_ejecucion = True
    modelo._ultimo_eta_seg = 42
    modelo._al_error("boom")
    assert modelo.eta_seg == -1


def test_protege_retroceso_espurio_en_progreso(db_tmp):
    modelo = ModeloImportacion()
    modelo._en_ejecucion = True
    modelo._inicio_monotonic = 100.0
    modelo._procesados = 5
    modelo._total = 10

    with patch("ui.modelos_qml.time.monotonic", return_value=120.0):
        modelo._al_progreso(3, 9, "x.mp3", "procesando")

    assert modelo.procesados == 5
    assert modelo.total == 10


def test_indeterminado_cuando_total_no_es_confiable(db_tmp):
    modelo = ModeloImportacion()
    modelo._en_ejecucion = True
    modelo._total = 0
    assert modelo.progreso_indeterminado is True

    modelo._total = 12
    assert modelo.progreso_indeterminado is False


def test_transiciones_de_estado_clave(db_tmp):
    modelo = ModeloImportacion()
    assert modelo.estado == "idle"

    modelo._en_ejecucion = True
    modelo._estado = "en_ejecucion"
    assert modelo.estado == "en_ejecucion"

    modelo.cancelar_importacion()  # sin worker no cambia, solo validamos que no rompe
    modelo._estado = "cancelando"
    assert modelo.estado == "cancelando"

    modelo._al_cancelar({"cancelada": True})
    assert modelo.estado == "cancelada"

    modelo._en_ejecucion = True
    modelo._al_error("fallo")
    assert modelo.estado == "error"

    modelo._en_ejecucion = True
    modelo._al_completar({"ok": True})
    assert modelo.estado == "completada"
