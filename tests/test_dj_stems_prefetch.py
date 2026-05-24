"""Tests del módulo de pre-fetch de stems para el DJ Privado.

Cobertura:
  - LOW no encola nada (no se usa HARMONIC_MIX en ese perfil).
  - MID/HIGH encolan hasta N pistas.
  - Resiliencia: si karaoke no está disponible, devuelve 0 sin levantar.
  - Versión async devuelve un thread daemon y no bloquea.
"""
from __future__ import annotations

import threading

import pytest

from servicios.dj_privado.hardware_profile import PerfilHardware
from servicios.dj_privado import stems_prefetch


@pytest.fixture
def mock_karaoke(monkeypatch):
    """Parcha karaoke.jobs_repo.encolar_muchas con un spy.

    Retorna una lista mutable a la que se appendean las invocaciones.
    """
    # Asegurar que el módulo está cargado para poder parchar su atributo.
    from servicios.karaoke import jobs_repo

    invocaciones: list[list[int]] = []

    def fake_encolar(ids):
        ids_list = list(ids)
        invocaciones.append(ids_list)
        return len(ids_list)

    monkeypatch.setattr(jobs_repo, "encolar_muchas", fake_encolar)
    return invocaciones


def test_low_no_encola(mock_karaoke):
    """En perfil LOW no se llama a karaoke en absoluto."""
    creados = stems_prefetch.pre_fetch_inicial(
        [1, 2, 3], n_pistas=3, perfil=PerfilHardware.LOW,
    )
    assert creados == 0
    assert mock_karaoke == []


def test_mid_encola_n_pistas(mock_karaoke):
    """En MID encolamos hasta n_pistas (los primeros ids de la iteración)."""
    creados = stems_prefetch.pre_fetch_inicial(
        [10, 20, 30, 40, 50], n_pistas=3, perfil=PerfilHardware.MID,
    )
    assert creados == 3
    assert mock_karaoke == [[10, 20, 30]]


def test_high_encola_default(mock_karaoke):
    creados = stems_prefetch.pre_fetch_inicial(
        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        perfil=PerfilHardware.HIGH,
    )
    assert creados == stems_prefetch.PISTAS_INICIALES_PRE_FETCH
    assert len(mock_karaoke[0]) == stems_prefetch.PISTAS_INICIALES_PRE_FETCH


def test_pre_fetch_sin_pistas_devuelve_cero(mock_karaoke):
    creados = stems_prefetch.pre_fetch_inicial([], perfil=PerfilHardware.HIGH)
    assert creados == 0
    assert mock_karaoke == []


def test_pre_fetch_filtra_ids_invalidos(mock_karaoke):
    """None y strings inválidos se ignoran sin crashear."""
    stems_prefetch.pre_fetch_inicial(
        [None, 1, "no-soy-int", 2, 3.5],
        n_pistas=5, perfil=PerfilHardware.HIGH,
    )
    assert mock_karaoke == [[1, 2, 3]]


def test_pre_fetch_sin_karaoke_no_levanta(monkeypatch):
    """Si encolar_muchas levanta, devuelve 0 silenciosamente (no propaga)."""
    from servicios.karaoke import jobs_repo

    def encolar_que_falla(ids):
        raise RuntimeError("simulación de fallo")

    monkeypatch.setattr(jobs_repo, "encolar_muchas", encolar_que_falla)
    creados = stems_prefetch.pre_fetch_inicial([1, 2], perfil=PerfilHardware.HIGH)
    assert creados == 0


def test_pre_fetch_async_devuelve_thread_daemon(monkeypatch):
    listo = threading.Event()
    from servicios.karaoke import jobs_repo

    invocaciones: list[list[int]] = []

    def fake_encolar(ids):
        ids_list = list(ids)
        invocaciones.append(ids_list)
        listo.set()
        return len(ids_list)

    monkeypatch.setattr(jobs_repo, "encolar_muchas", fake_encolar)
    t = stems_prefetch.pre_fetch_inicial_async(
        [1, 2, 3], perfil=PerfilHardware.MID,
    )
    assert isinstance(t, threading.Thread)
    assert t.daemon is True
    assert listo.wait(timeout=2.0), "el hilo no completó en tiempo"
    assert invocaciones == [[1, 2, 3]]


def test_pre_fetch_async_low_perfil_no_invoca(mock_karaoke):
    t = stems_prefetch.pre_fetch_inicial_async(
        [1, 2, 3], perfil=PerfilHardware.LOW,
    )
    t.join(timeout=2.0)
    assert mock_karaoke == []
