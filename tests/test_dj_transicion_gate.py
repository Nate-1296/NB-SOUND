# =============================================================================
# tests/test_dj_transicion_gate.py
#
# Adicional — Transición DJ entrecortada. El crossfade NO debe empezar a bajar
# el volumen del deck saliente hasta que el deck entrante produzca audio (VLC
# tarda en abrir/buferear el media). Antes, el fade corría durante ese hueco y
# se oía "bajón → silencio → entra bajo" en cada cambio de pista.
#
# Se prueba la lógica del gate en `_tick_transicion_locked` con decks de prueba
# controlables (sin audio real).
# =============================================================================
from __future__ import annotations

import time

import pytest

from db.conexion import cerrar_db, inicializar_db
from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj, EstadoSesion


@pytest.fixture()
def db(tmp_path):
    inicializar_db(tmp_path / "trans.db")
    try:
        yield tmp_path
    finally:
        cerrar_db()


class _DeckStub:
    def __init__(self, t_ms=-1, playing=None):
        self._t = t_ms
        # Por defecto "suena" si reporta tiempo > 0 (como VLC al arrancar).
        self._playing = playing if playing is not None else (t_ms > 0)
        self.volumen = None
    def get_time(self):
        return self._t
    def is_playing(self):
        return self._playing
    def audio_set_volume(self, v):
        self.volumen = int(v)
    def set_equalizer(self, *_a):
        pass


def _rep_con_transicion(db, *, b_ms=-1, mix_in_b=0.0):
    r = ReproductorSesionDj(permitir_modo_simulado=True)
    # Decks de prueba: A activo (deck "a"), B entrando (deck "b").
    r._deck_a = _DeckStub(t_ms=120000)   # saliente, sonando
    r._deck_b = _DeckStub(t_ms=b_ms)     # entrante (controlable)
    r._deck_activo = "a"
    r._volumen = 80
    r._ejecutor_mezcla = None            # ruta clásica (sin mix engine)
    r._estado = EstadoSesion.TRANSICIONANDO
    r._transicion_activa = {
        "inicio_ts": None,
        "armado_ts": time.monotonic(),
        "overlap": 4.0,
        "tecnica": "crossfade",
        "idx_a": 0,
        "idx_b": 1,
        "mix_in_b": mix_in_b,
    }
    return r


def test_gate_mantiene_A_pleno_mientras_B_no_suena(db):
    r = _rep_con_transicion(db, b_ms=-1)  # B aún no produce audio
    try:
        with r._lock:
            r._tick_transicion_locked(pos_seg=120.0, dur_seg=180.0)
        # El fade NO arrancó: inicio_ts sigue None.
        assert r._transicion_activa["inicio_ts"] is None
        # A se mantiene a volumen pleno; B en silencio.
        assert r._deck_a.volumen == 80
        assert r._deck_b.volumen == 0
    finally:
        r.close()


def test_gate_arranca_fade_cuando_B_suena(db):
    r = _rep_con_transicion(db, b_ms=300)  # B ya produce audio (0.3s)
    try:
        with r._lock:
            r._tick_transicion_locked(pos_seg=120.0, dur_seg=180.0)
        # Detectó B sonando → fija inicio_ts y empieza el fade.
        assert r._transicion_activa["inicio_ts"] is not None
    finally:
        r.close()


def test_gate_espera_al_seek_de_mix_in(db):
    # Con mix_in_b=30s, B "suena" pero en posición 1s: el seek aún no aplicó.
    r = _rep_con_transicion(db, b_ms=1000, mix_in_b=30.0)
    try:
        with r._lock:
            r._tick_transicion_locked(pos_seg=120.0, dur_seg=180.0)
        assert r._transicion_activa["inicio_ts"] is None  # espera al seek
        # Ahora B está en ~30s (seek aplicado) → arranca.
        r._deck_b._t = 30000
        with r._lock:
            r._tick_transicion_locked(pos_seg=120.0, dur_seg=180.0)
        assert r._transicion_activa["inicio_ts"] is not None
    finally:
        r.close()


def test_gate_timeout_de_seguridad_arranca_igual(db):
    r = _rep_con_transicion(db, b_ms=-1)
    try:
        # Simular que pasaron >2.5s buffereando sin éxito.
        r._transicion_activa["armado_ts"] = time.monotonic() - 3.0
        with r._lock:
            r._tick_transicion_locked(pos_seg=120.0, dur_seg=180.0)
        # Timeout: arranca igual para no bloquear la sesión.
        assert r._transicion_activa["inicio_ts"] is not None
    finally:
        r.close()
