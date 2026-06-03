# =============================================================================
# tests/test_reproductor_ecualizador.py
#
# Ecualizador + "Estabilizar volumen" (normvol) del reproductor GLOBAL (ítem 7).
#
# Cubre:
#   - Tabla de presets contrastada contra la libVLC real (no inventada).
#   - Funciones puras de mapeo preset -> bandas / preamp.
#   - Aplicar preset y que mover una banda/preamp pase a "Personalizado".
#   - Round-trip de persistencia en config_ui (sin cambio de esquema).
#   - normvol como opción PER-MEDIA del global (media.add_option), nunca como
#     arg de instancia, y que el DJ Privado no lee la config de EQ/normvol.
#
# Determinista y sin audio salvo el contraste de la tabla (requiere VLC, se
# salta si no está disponible).
# =============================================================================
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from db.conexion import cerrar_db, inicializar_db, obtener_config
import servicios.reproductor as R
from servicios.reproductor import Reproductor


@pytest.fixture()
def db(tmp_path):
    inicializar_db(tmp_path / "eq.sqlite3")
    try:
        yield tmp_path
    finally:
        cerrar_db()


# ── Funciones puras de mapeo preset -> bandas/preamp ──────────────────────────

def test_estructura_tabla_presets():
    assert len(R.EQ_PRESETS) == 18
    assert R.EQ_PRESET_NOMBRES[0] == "Flat"
    assert R.EQ_PRESET_NOMBRES[-1] == "Techno"
    for _, _, bandas in R.EQ_PRESETS:
        assert len(bandas) == R.EQ_NUM_BANDAS == 10
    assert R.EQ_BANDAS_HZ == (31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)


def test_bandas_de_preset_es_pura():
    assert R.bandas_de_preset(0) == [0.0] * 10          # Flat
    assert R.bandas_de_preset(13)[0] == 8.0             # Rock, banda 31 Hz
    assert R.preamp_de_preset(13) == 5.0
    # Devuelve copia: mutarla no afecta la tabla.
    copia = R.bandas_de_preset(2)
    copia[0] = 99.0
    assert R.bandas_de_preset(2)[0] != 99.0
    with pytest.raises(IndexError):
        R.bandas_de_preset(18)


def test_tabla_presets_coincide_con_libvlc():
    """La tabla embebida debe coincidir con la libVLC instalada (no inventada)."""
    vlc = pytest.importorskip("vlc")
    if not hasattr(vlc, "libvlc_audio_equalizer_new_from_preset"):
        pytest.skip("Binding VLC sin API de ecualizador")
    n = vlc.libvlc_audio_equalizer_get_preset_count()
    nb = vlc.libvlc_audio_equalizer_get_band_count()
    assert n == len(R.EQ_PRESETS)
    assert nb == R.EQ_NUM_BANDAS
    for idx, (nombre, preamp, bandas) in enumerate(R.EQ_PRESETS):
        nombre_vlc = vlc.libvlc_audio_equalizer_get_preset_name(idx)
        nombre_vlc = nombre_vlc.decode() if isinstance(nombre_vlc, bytes) else nombre_vlc
        assert nombre_vlc == nombre
        eq = vlc.libvlc_audio_equalizer_new_from_preset(idx)
        try:
            assert vlc.libvlc_audio_equalizer_get_preamp(eq) == pytest.approx(preamp, abs=0.05)
            for b in range(nb):
                amp = vlc.libvlc_audio_equalizer_get_amp_at_index(eq, b)
                assert amp == pytest.approx(bandas[b], abs=0.05), (nombre, b)
        finally:
            vlc.libvlc_audio_equalizer_release(eq)


# ── Estado lógico: preset / personalizado ─────────────────────────────────────

def test_aplicar_preset_y_mover_banda_pasa_a_custom(db):
    r = Reproductor(permitir_modo_simulado=True)
    try:
        assert r.eq_preset_idx == 0          # default Flat
        r.aplicar_ecualizador_preset(13)     # Rock
        assert r.eq_preset_idx == 13
        assert r.eq_bandas == list(R.EQ_PRESETS[13][2])
        assert r.eq_preamp == R.EQ_PRESETS[13][1]
        # Mover una banda => Personalizado
        r.set_ecualizador_banda(0, 1.5)
        assert r.eq_preset_idx == -1
        assert r.eq_bandas[0] == 1.5
        # Volver a un preset re-fija todo
        r.aplicar_ecualizador_preset(2)
        assert r.eq_preset_idx == 2
        # Mover preamp => Personalizado
        r.set_ecualizador_preamp(-3.0)
        assert r.eq_preset_idx == -1
        assert r.eq_preamp == -3.0
    finally:
        r.cerrar()


def test_nombres_presets_es():
    """Nombres de presentación en español, mismo orden/índice que la tabla.
    Los géneros/términos sin traducción natural se conservan."""
    assert len(R.EQ_PRESET_NOMBRES_ES) == len(R.EQ_PRESETS) == 18
    assert R.EQ_PRESET_NOMBRES_ES[0] == "Plano"        # Flat
    assert R.EQ_PRESET_NOMBRES_ES[1] == "Clásica"      # Classical
    assert R.EQ_PRESET_NOMBRES_ES[9] == "En vivo"      # Live
    assert R.EQ_PRESET_NOMBRES_ES[10] == "Fiesta"      # Party
    # Géneros/proper-names conservados (alineados por índice con la tabla EN).
    for idx, nombre in ((11, "Pop"), (13, "Rock"), (12, "Reggae"),
                        (14, "Ska"), (17, "Techno"), (2, "Club"), (3, "Dance")):
        assert R.EQ_PRESET_NOMBRES_ES[idx] == nombre
        assert R.EQ_PRESET_NOMBRES[idx] == nombre  # coincide con el canónico EN


def test_preset_se_aplica_via_new_from_preset(db, monkeypatch):
    """Los preajustes se aplican con libvlc_audio_equalizer_new_from_preset
    (API de la librería); solo 'Personalizado' arma el EQ a mano."""
    import types

    registro = {"preset": [], "manual": 0, "set": 0}

    class _Eq:
        def set_preamp(self, v): pass
        def set_amp_at_index(self, v, i): pass
        def release(self): pass

    class _MP:
        def set_equalizer(self, eq): registro["set"] += 1

    def _new_from_preset(idx):
        registro["preset"].append(idx)
        return _Eq()

    def _audio_eq():
        registro["manual"] += 1
        return _Eq()

    fake = types.SimpleNamespace(
        Instance=lambda *a, **k: None,           # __init__ no crea VLC real
        libvlc_audio_equalizer_new_from_preset=_new_from_preset,
        AudioEqualizer=_audio_eq,
    )
    monkeypatch.setattr(R, "_vlc", fake)
    monkeypatch.setattr(R, "VLC_DISPONIBLE", True)

    r = Reproductor(permitir_modo_simulado=True)
    try:
        r._media_player = _MP()
        r.set_ecualizador_activo(True)        # default Flat (idx 0) vía preset
        assert registro["preset"] == [0]
        assert registro["manual"] == 0
        r.aplicar_ecualizador_preset(2)       # Club vía new_from_preset(2)
        assert registro["preset"] == [0, 2]
        assert registro["manual"] == 0
        # Mover una banda => Personalizado => construcción manual.
        r.set_ecualizador_banda(0, 5.0)
        assert registro["manual"] == 1
        assert registro["preset"] == [0, 2]   # no se volvió a pedir un preset
    finally:
        r.cerrar()


def test_valores_invalidos_se_acotan_o_ignoran(db):
    r = Reproductor(permitir_modo_simulado=True)
    try:
        r.set_ecualizador_activo(True)
        # Banda fuera de rango de índice: ignorada.
        r.aplicar_ecualizador_preset(2)
        r.set_ecualizador_banda(99, 5.0)
        assert r.eq_preset_idx == 2  # no cambió
        # dB fuera de rango: se acota a [EQ_AMP_MIN, EQ_AMP_MAX].
        r.set_ecualizador_banda(0, 999.0)
        assert r.eq_bandas[0] == R.EQ_AMP_MAX
        r.set_ecualizador_preamp(-999.0)
        assert r.eq_preamp == R.EQ_PREAMP_MIN
        # Preset fuera de rango: ignorado.
        antes = r.eq_preset_idx
        r.aplicar_ecualizador_preset(50)
        assert r.eq_preset_idx == antes
    finally:
        r.cerrar()


# ── Persistencia round-trip en config_ui ──────────────────────────────────────

def test_persistencia_roundtrip_config_ui(db):
    r = Reproductor(permitir_modo_simulado=True)
    r.set_ecualizador_activo(True)
    r.aplicar_ecualizador_preset(13)     # Rock
    r.set_ecualizador_banda(0, 3.5)      # -> custom
    r.set_ecualizador_preamp(-4.0)
    r.set_normalizar_volumen(True)
    r.cerrar()

    # Claves esperadas en config_ui (sin cambio de esquema).
    assert obtener_config("eq_activo") == "1"
    assert obtener_config("eq_preset") == "custom"
    assert obtener_config("audio_normalizar") == "1"
    assert obtener_config("eq_bandas") != ""

    # Una instancia nueva restaura el estado completo.
    r2 = Reproductor(permitir_modo_simulado=True)
    try:
        assert r2.eq_activo is True
        assert r2.eq_preset_idx == -1
        assert r2.eq_bandas[0] == pytest.approx(3.5)
        assert r2.eq_preamp == pytest.approx(-4.0)
        assert r2.audio_normalizar is True
    finally:
        r2.cerrar()


def test_bandas_corruptas_caen_a_preset(db):
    from db.conexion import guardar_config
    guardar_config("eq_activo", "1")
    guardar_config("eq_preset", "13")       # Rock
    guardar_config("eq_bandas", "no-es-json")
    r = Reproductor(permitir_modo_simulado=True)
    try:
        # Bandas inválidas: se derivan del preset, sin reventar.
        assert r.eq_preset_idx == 13
        assert r.eq_bandas == list(R.EQ_PRESETS[13][2])
    finally:
        r.cerrar()


# ── normvol per-media (global) ────────────────────────────────────────────────

class _FakeMedia:
    def __init__(self):
        self.opts: list[str] = []

    def add_option(self, opcion):
        self.opts.append(opcion)


class _FakeInstancia:
    def media_new(self, ruta):
        return _FakeMedia()


def test_normvol_es_opcion_per_media_no_de_instancia(db):
    r = Reproductor(permitir_modo_simulado=True)
    try:
        r._instancia_vlc = _FakeInstancia()
        # Apagado: el media no lleva opciones de normvol.
        r._audio_normalizar = False
        assert r._crear_media("/x.mp3").opts == []
        # Encendido: normvol se inyecta PER-MEDIA (no recrea instancia).
        r._audio_normalizar = True
        opts = r._crear_media("/x.mp3").opts
        assert any(o.startswith(":audio-filter=normvol") for o in opts)
        assert any(o.startswith(":norm-max-level=") for o in opts)
        assert any(o.startswith(":norm-buff-size=") for o in opts)
    finally:
        r.cerrar()


# ── El DJ Privado no se ve afectado ───────────────────────────────────────────

def test_dj_privado_no_lee_config_eq_ni_normvol():
    """Garantía de aislamiento: el código del DJ Privado no consulta las claves
    de config del ecualizador/normalización del reproductor global."""
    from servicios.dj_privado import reproductor_sesion, mix_engine

    claves = ("eq_activo", "eq_preset", "eq_bandas", "eq_preamp", "audio_normalizar")
    for modulo in (reproductor_sesion, mix_engine):
        fuente = inspect.getsource(modulo)
        for clave in claves:
            assert clave not in fuente, f"{modulo.__name__} referencia '{clave}'"
