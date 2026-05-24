"""Tests del módulo de perfilado de hardware para el DJ Privado.

Cobertura:
  - Clasificación de perfiles a partir del factor de tiempo real.
  - Persistencia en config_ui (round-trip).
  - Idempotencia del benchmark en background.
  - Técnicas habilitadas por cada perfil.

NO ejecuta Demucs real: el benchmark se mockea o se confía en su rama de
fallback (sin Demucs disponible -> LOW). El objetivo es validar la lógica
de selección, no la performance del modelo de separación.
"""
from __future__ import annotations

import json
import threading
import time

import pytest

from db.conexion import cerrar_db, get_conexion, guardar_config, inicializar_db
from servicios.dj_privado import hardware_profile as hp


@pytest.fixture()
def db_temp(tmp_path):
    inicializar_db(tmp_path / "hw.db")
    # Limpia estado en memoria previo entre tests para asegurar aislamiento.
    hp.resetear_perfil()
    try:
        yield tmp_path
    finally:
        try:
            cerrar_db()
        except Exception:
            pass
        hp.resetear_perfil()


# =============================================================================
# Clasificación
# =============================================================================


def test_clasificar_high_si_factor_bajo():
    assert hp.clasificar(0.5, demucs_ok=True) == hp.PerfilHardware.HIGH
    assert hp.clasificar(1.5, demucs_ok=True) == hp.PerfilHardware.HIGH


def test_clasificar_mid_si_factor_medio():
    assert hp.clasificar(3.0, demucs_ok=True) == hp.PerfilHardware.MID
    assert hp.clasificar(5.0, demucs_ok=True) == hp.PerfilHardware.MID


def test_clasificar_low_si_factor_alto():
    assert hp.clasificar(8.0, demucs_ok=True) == hp.PerfilHardware.LOW
    assert hp.clasificar(100.0, demucs_ok=True) == hp.PerfilHardware.LOW


def test_clasificar_sin_demucs_siempre_low():
    """Sin Demucs no se puede hacer HARMONIC_MIX -> siempre LOW."""
    assert hp.clasificar(0.1, demucs_ok=False) == hp.PerfilHardware.LOW
    assert hp.clasificar(1.0, demucs_ok=False) == hp.PerfilHardware.LOW


def test_clasificar_factor_cero_o_negativo_es_low():
    assert hp.clasificar(0.0, demucs_ok=True) == hp.PerfilHardware.LOW
    assert hp.clasificar(-1.0, demucs_ok=True) == hp.PerfilHardware.LOW


# =============================================================================
# Técnicas habilitadas
# =============================================================================


def test_tecnicas_low_no_incluyen_harmonic_mix():
    tecnicas = hp.tecnicas_habilitadas(hp.PerfilHardware.LOW)
    assert "harmonic_mix" not in tecnicas
    assert "eq_kill_bass" in tecnicas
    assert "filter_sweep" in tecnicas


def test_tecnicas_mid_incluyen_harmonic_mix():
    tecnicas = hp.tecnicas_habilitadas(hp.PerfilHardware.MID)
    assert "harmonic_mix" in tecnicas


def test_tecnicas_high_incluyen_todas():
    tecnicas = hp.tecnicas_habilitadas(hp.PerfilHardware.HIGH)
    assert set(tecnicas) >= {
        "hard_cut", "energy_blend", "eq_kill_bass",
        "filter_sweep", "harmonic_mix",
    }


# =============================================================================
# Serialización round-trip
# =============================================================================


def test_resultado_round_trip():
    original = hp.ResultadoBenchmark(
        perfil=hp.PerfilHardware.MID,
        seg_para_10s=24.5,
        factor_tiempo_real=2.45,
        device="cpu",
        demucs_disponible=True,
        error=None,
        benchmark_en="2026-05-16T10:00:00+00:00",
    )
    data = original.a_dict()
    rehydrado = hp.ResultadoBenchmark.desde_dict(data)
    assert rehydrado == original


def test_resultado_desde_dict_tolera_datos_corruptos():
    rehydrado = hp.ResultadoBenchmark.desde_dict({})
    assert rehydrado.perfil == hp.PerfilHardware.LOW
    assert rehydrado.demucs_disponible is False


# =============================================================================
# Persistencia
# =============================================================================


def test_perfil_guardado_es_none_si_nunca_se_corrio(db_temp):
    assert hp.perfil_guardado() is None
    assert hp.perfil_efectivo() == hp.PerfilHardware.LOW


def test_perfil_guardado_round_trip_via_config(db_temp):
    """Si se persiste manualmente un perfil en config_ui, perfil_guardado
    debe leerlo correctamente."""
    resultado = hp.ResultadoBenchmark(
        perfil=hp.PerfilHardware.HIGH,
        seg_para_10s=8.0,
        factor_tiempo_real=0.8,
        device="cuda",
        demucs_disponible=True,
        error=None,
        benchmark_en="2026-05-16T00:00:00+00:00",
    )
    guardar_config(hp.CLAVE_CONFIG, json.dumps(resultado.a_dict()))
    leido = hp.perfil_guardado()
    assert leido is not None
    assert leido.perfil == hp.PerfilHardware.HIGH
    assert hp.perfil_efectivo() == hp.PerfilHardware.HIGH


def test_perfil_corrupto_se_ignora_silenciosamente(db_temp):
    """Si config_ui contiene basura, perfil_guardado devuelve None
    sin lanzar excepción (para no romper el motor)."""
    guardar_config(hp.CLAVE_CONFIG, "no es json {{{")
    assert hp.perfil_guardado() is None
    assert hp.perfil_efectivo() == hp.PerfilHardware.LOW


def test_resetear_perfil_borra_persistido(db_temp):
    resultado = hp.ResultadoBenchmark(
        perfil=hp.PerfilHardware.MID,
        seg_para_10s=30.0,
        factor_tiempo_real=3.0,
        device="cpu",
        demucs_disponible=True,
        error=None,
        benchmark_en="2026-05-16T00:00:00+00:00",
    )
    guardar_config(hp.CLAVE_CONFIG, json.dumps(resultado.a_dict()))
    assert hp.perfil_guardado() is not None
    hp.resetear_perfil()
    assert hp.perfil_guardado() is None


# =============================================================================
# Idempotencia del benchmark en background
# =============================================================================


def test_lanzar_benchmark_no_corre_si_ya_hay_perfil(db_temp, monkeypatch):
    """Si ya hay un perfil persistido y no se fuerza, no se lanza otro."""
    resultado = hp.ResultadoBenchmark(
        perfil=hp.PerfilHardware.HIGH,
        seg_para_10s=10.0,
        factor_tiempo_real=1.0,
        device="cpu",
        demucs_disponible=True,
        error=None,
        benchmark_en="2026-05-16T00:00:00+00:00",
    )
    guardar_config(hp.CLAVE_CONFIG, json.dumps(resultado.a_dict()))
    # Reseteamos solo el cache en memoria para que perfil_guardado vuelva a leer de BD.
    hp._estado_benchmark["ultimo"] = None  # type: ignore[index]

    invocaciones = []

    def fake_benchmark(modelo_nombre: str = "htdemucs"):
        invocaciones.append(modelo_nombre)
        return resultado

    monkeypatch.setattr(hp, "_ejecutar_benchmark", fake_benchmark)
    lanzado = hp.lanzar_benchmark_si_falta()
    # Esperar a que un hilo eventual termine.
    time.sleep(0.2)
    assert lanzado is False
    assert invocaciones == []


def test_lanzar_benchmark_forzar_si_corre(db_temp, monkeypatch):
    """Con forzar=True se ejecuta aunque exista un perfil guardado."""
    resultado_existente = hp.ResultadoBenchmark(
        perfil=hp.PerfilHardware.LOW,
        seg_para_10s=0.0,
        factor_tiempo_real=0.0,
        device="cpu",
        demucs_disponible=False,
        error=None,
        benchmark_en="2026-05-16T00:00:00+00:00",
    )
    guardar_config(hp.CLAVE_CONFIG, json.dumps(resultado_existente.a_dict()))
    hp._estado_benchmark["ultimo"] = None  # type: ignore[index]

    nuevo = hp.ResultadoBenchmark(
        perfil=hp.PerfilHardware.HIGH,
        seg_para_10s=8.0,
        factor_tiempo_real=0.8,
        device="cuda",
        demucs_disponible=True,
        error=None,
        benchmark_en="2026-05-16T01:00:00+00:00",
    )
    completado = threading.Event()

    def fake_benchmark(modelo_nombre: str = "htdemucs"):
        return nuevo

    monkeypatch.setattr(hp, "_ejecutar_benchmark", fake_benchmark)

    def on_completado(res):
        completado.set()

    assert hp.lanzar_benchmark_si_falta(on_completado=on_completado, forzar=True) is True
    assert completado.wait(timeout=2.0), "el benchmark no completó en tiempo"
    leido = hp.perfil_guardado()
    assert leido is not None
    assert leido.perfil == hp.PerfilHardware.HIGH


def test_lanzar_benchmark_no_re_entrante(db_temp, monkeypatch):
    """Si hay uno corriendo, otra llamada retorna False sin lanzarlo de nuevo."""
    listo = threading.Event()
    siguiente = threading.Event()

    def fake_benchmark_lento(modelo_nombre: str = "htdemucs"):
        listo.set()
        # bloquea hasta que el test diga "puedes terminar"
        siguiente.wait(timeout=2.0)
        return hp.ResultadoBenchmark(
            perfil=hp.PerfilHardware.MID,
            seg_para_10s=20.0,
            factor_tiempo_real=2.0,
            device="cpu",
            demucs_disponible=True,
            error=None,
            benchmark_en="2026-05-16T00:00:00+00:00",
        )

    monkeypatch.setattr(hp, "_ejecutar_benchmark", fake_benchmark_lento)
    primero = hp.lanzar_benchmark_si_falta()
    assert primero is True
    assert listo.wait(timeout=1.0)
    # Mientras el primero está bloqueado, el segundo debe rechazar.
    segundo = hp.lanzar_benchmark_si_falta()
    assert segundo is False
    siguiente.set()
    # Permitir que el primer hilo termine y persista el resultado.
    for _ in range(20):
        if hp.perfil_guardado() is not None:
            break
        time.sleep(0.05)
    assert hp.perfil_guardado() is not None


# =============================================================================
# Resultado escrito al disco contiene info auditable
# =============================================================================


def test_benchmark_persiste_todos_los_campos(db_temp, monkeypatch):
    resultado = hp.ResultadoBenchmark(
        perfil=hp.PerfilHardware.MID,
        seg_para_10s=28.4,
        factor_tiempo_real=2.84,
        device="cpu",
        demucs_disponible=True,
        error=None,
        benchmark_en="2026-05-16T12:00:00+00:00",
    )
    monkeypatch.setattr(hp, "_ejecutar_benchmark", lambda modelo_nombre="x": resultado)
    completado = threading.Event()
    hp.lanzar_benchmark_si_falta(on_completado=lambda _r: completado.set(), forzar=True)
    assert completado.wait(timeout=2.0)
    crudo = get_conexion().execute(
        "SELECT valor FROM config_ui WHERE clave = ?", (hp.CLAVE_CONFIG,)
    ).fetchone()
    assert crudo is not None
    data = json.loads(crudo["valor"])
    for clave in (
        "perfil", "seg_para_10s", "factor_tiempo_real",
        "device", "demucs_disponible", "benchmark_en",
    ):
        assert clave in data
