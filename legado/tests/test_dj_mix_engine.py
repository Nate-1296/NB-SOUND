"""Tests unitarios del motor de mezcla del DJ Privado.

Cobertura:
  - Cálculo de mix points por BPM (intro/outro como múltiplos de beats).
  - Cálculo de mix points por RMS con audio sintético.
  - Fallback determinista cuando no hay datos.
  - Selección de técnica según fase narrativa y perfil hardware.
  - Curvas de volumen para cada técnica.
  - Curvas de EQ para EQ_KILL_BASS y FILTER_SWEEP.
  - Plan de mezcla completo (overlap, override de ruta para harmonic_mix).
  - Degradación cuando los stems no están listos.

No prueba comportamiento de audio real (libVLC equalizer): eso requeriría
salida acústica reproducible. Sí valida que los amps se calculan en el
rango esperado y que el ejecutor encadena las llamadas correctas a VLC
(mockeado).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
import soundfile as sf

from servicios.dj_privado.hardware_profile import PerfilHardware
from servicios.dj_privado.mix_engine import (
    EQ_BANDAS_HZ,
    GANANCIA_KILL_DB,
    NUM_BANDAS_EQ,
    EjecutorMezcla,
    MixEngine,
    MixPoints,
    PlanMezcla,
    StemsProvider,
    TecnicaMezcla,
    calcular_mix_points_por_bpm,
    calcular_mix_points_por_rms,
    curva_eq,
    curva_volumen,
    etiqueta_humana,
    mix_points_default,
    overlap_recomendado,
    seleccionar_tecnica,
)
from servicios.dj_privado.transiciones import TransicionPlan


# =============================================================================
# Helpers
# =============================================================================


def _plan_transicion(
    *,
    factor_bpm: float = 0.8,
    factor_key: float = 0.8,
    factor_energia: float = 0.7,
    score: float = 0.8,
    overlap_seg: float = 5.0,
) -> TransicionPlan:
    return TransicionPlan(
        score=score,
        factor_bpm=factor_bpm,
        factor_key=factor_key,
        factor_energia=factor_energia,
        delta_bpm=0.0,
        delta_camelot=0,
        delta_energia=0.0,
        razones=[],
        tecnica_sugerida="crossfade",
        overlap_seg=overlap_seg,
        estilo_aplicado="smooth",
    )


# =============================================================================
# Mix points por BPM
# =============================================================================


def test_mix_points_por_bpm_120():
    """BPM 120 sobre 240s: intro=16 beats=8s, outro=32 beats=16s -> mix_out=224s."""
    mp = calcular_mix_points_por_bpm(240.0, 120.0)
    assert mp is not None
    assert mp.fuente == "bpm"
    assert mp.mix_in_seg == pytest.approx(8.0, abs=0.01)
    assert mp.mix_out_seg == pytest.approx(224.0, abs=0.01)
    assert mp.duracion_seg == pytest.approx(240.0)


def test_mix_points_por_bpm_bpm_alto_ajusta():
    """Con BPM muy alto la regla de '60% de la pista' debe activarse."""
    # 200 BPM: 16 beats = 4.8s, 32 beats = 9.6s. Sobre 30s la regla no
    # se activa porque 30s < MIN_DURACION_PARA_RECORTE -> None.
    assert calcular_mix_points_por_bpm(30.0, 200.0) is None
    # Sobre 90s: intro=4.8s, outro=9.6s, suma=14.4s -> ok (deja >60% de pista)
    mp = calcular_mix_points_por_bpm(90.0, 200.0)
    assert mp is not None
    assert mp.mix_in_seg < 10.0
    assert mp.mix_out_seg > 60.0


def test_mix_points_por_bpm_sin_bpm():
    assert calcular_mix_points_por_bpm(240.0, None) is None
    assert calcular_mix_points_por_bpm(240.0, 0.0) is None
    assert calcular_mix_points_por_bpm(240.0, -1.0) is None


def test_mix_points_por_bpm_pista_corta():
    """Pistas más cortas que MIN_DURACION_PARA_RECORTE no se recortan."""
    assert calcular_mix_points_por_bpm(45.0, 120.0) is None


# =============================================================================
# Mix points por RMS
# =============================================================================


def test_mix_points_por_rms_audio_sintetico(tmp_path):
    """Genera 90s con 5s de silencio al inicio y 8s al final; verifica detección."""
    sr = 22050
    duracion = 90.0
    n = int(duracion * sr)
    audio = np.random.default_rng(0).standard_normal(n).astype(np.float32) * 0.5
    audio[: 5 * sr] = 0.0          # silencio inicial 5s
    audio[-8 * sr:] = 0.0          # silencio final 8s
    ruta = tmp_path / "test.wav"
    sf.write(str(ruta), audio, sr)

    mp = calcular_mix_points_por_rms(str(ruta), duracion)
    assert mp is not None
    assert mp.fuente == "rms"
    # Debe detectar mix_in al menos cercano al fin del silencio inicial.
    assert mp.mix_in_seg >= 2.0
    assert mp.mix_in_seg <= 8.0
    # Mix-out debe estar antes del silencio final pero respetar margen mínimo.
    assert mp.mix_out_seg <= duracion - 5.0
    assert mp.mix_out_seg > mp.mix_in_seg + 30.0


def test_mix_points_por_rms_archivo_invalido():
    assert calcular_mix_points_por_rms("/tmp/__no_existe__.wav", 240.0) is None


def test_mix_points_por_rms_pista_corta():
    """Pistas cortas no aplican RMS (devuelven None aunque exista archivo)."""
    assert calcular_mix_points_por_rms("/any/path.wav", 30.0) is None


# =============================================================================
# Mix points default
# =============================================================================


def test_mix_points_default_pista_corta_no_recorta():
    mp = mix_points_default(30.0)
    assert mp.mix_in_seg == 0.0
    assert mp.mix_out_seg == pytest.approx(30.0)
    assert mp.fuente == "default"


def test_mix_points_default_pista_normal():
    mp = mix_points_default(240.0)
    assert mp.mix_in_seg > 0.0
    assert mp.mix_out_seg < 240.0
    assert mp.duracion_seg == pytest.approx(240.0)


# =============================================================================
# Selección de técnica
# =============================================================================


def test_seleccion_fase_peak_con_bpm_iguales_da_hard_cut():
    plan = _plan_transicion()
    tecnica, razones = seleccionar_tecnica(
        plan_transicion=plan, perfil=PerfilHardware.HIGH,
        fase_narrativa="peak", bpm_a=128.0, bpm_b=128.5,
        stems_listos=True,
    )
    assert tecnica == TecnicaMezcla.HARD_CUT
    assert any("peak" in r for r in razones)


def test_seleccion_fase_peak_bpm_distantes_no_es_hard_cut():
    plan = _plan_transicion()
    tecnica, _ = seleccionar_tecnica(
        plan_transicion=plan, perfil=PerfilHardware.HIGH,
        fase_narrativa="peak", bpm_a=120.0, bpm_b=140.0,
        stems_listos=False,
    )
    assert tecnica != TecnicaMezcla.HARD_CUT


@pytest.mark.parametrize("fase", ["release", "cooldown"])
def test_seleccion_descenso_da_energy_blend(fase):
    plan = _plan_transicion()
    tecnica, _ = seleccionar_tecnica(
        plan_transicion=plan, perfil=PerfilHardware.MID,
        fase_narrativa=fase, bpm_a=120, bpm_b=120,
        stems_listos=False,
    )
    assert tecnica == TecnicaMezcla.ENERGY_BLEND


def test_seleccion_harmonic_mix_cuando_stems_listos_y_armonia():
    plan = _plan_transicion(factor_bpm=0.9, factor_key=0.9)
    tecnica, razones = seleccionar_tecnica(
        plan_transicion=plan, perfil=PerfilHardware.HIGH,
        fase_narrativa="groove", bpm_a=120, bpm_b=121,
        stems_listos=True,
    )
    assert tecnica == TecnicaMezcla.HARMONIC_MIX


def test_seleccion_low_nunca_da_harmonic_mix():
    """En perfil LOW no se permite HARMONIC_MIX aunque haya stems."""
    plan = _plan_transicion(factor_bpm=0.9, factor_key=0.9)
    tecnica, _ = seleccionar_tecnica(
        plan_transicion=plan, perfil=PerfilHardware.LOW,
        fase_narrativa="groove", bpm_a=120, bpm_b=121,
        stems_listos=True,
    )
    assert tecnica != TecnicaMezcla.HARMONIC_MIX


def test_seleccion_bpm_cercano_da_eq_kill_bass():
    """Con BPM cercano pero sin stems ni armonía perfecta -> EQ kill bass."""
    plan = _plan_transicion(factor_bpm=0.85, factor_key=0.4)
    tecnica, _ = seleccionar_tecnica(
        plan_transicion=plan, perfil=PerfilHardware.LOW,
        fase_narrativa="groove", bpm_a=124, bpm_b=125,
        stems_listos=False,
    )
    assert tecnica == TecnicaMezcla.EQ_KILL_BASS


def test_seleccion_default_filter_sweep():
    """Sin condiciones específicas, fallback a barrido de filtros."""
    plan = _plan_transicion(factor_bpm=0.5, factor_key=0.3, factor_energia=0.5)
    tecnica, _ = seleccionar_tecnica(
        plan_transicion=plan, perfil=PerfilHardware.LOW,
        fase_narrativa="warmup", bpm_a=100, bpm_b=130,
        stems_listos=False,
    )
    assert tecnica == TecnicaMezcla.FILTER_SWEEP


# =============================================================================
# Overlap recomendado
# =============================================================================


def test_overlap_hard_cut_es_minimo():
    assert overlap_recomendado(TecnicaMezcla.HARD_CUT, 8.0) < 1.0


def test_overlap_energy_blend_es_largo():
    assert overlap_recomendado(TecnicaMezcla.ENERGY_BLEND, 4.0) >= 10.0


def test_overlap_filter_sweep_respeta_minimo():
    assert overlap_recomendado(TecnicaMezcla.FILTER_SWEEP, 3.0) >= 6.0


# =============================================================================
# Curvas de volumen
# =============================================================================


def test_curva_volumen_endpoints():
    """En p=0 la pista saliente está plena; en p=1 la entrante."""
    for tecnica in TecnicaMezcla:
        v_a0, v_b0 = curva_volumen(tecnica, 0.0)
        v_a1, v_b1 = curva_volumen(tecnica, 1.0)
        assert v_a0 == pytest.approx(1.0, abs=1e-3) or tecnica == TecnicaMezcla.HARMONIC_MIX
        assert v_b1 == pytest.approx(1.0, abs=1e-3)


def test_curva_volumen_hard_cut_es_seca():
    """HARD_CUT mantiene A plena hasta p<0.5 y luego salta a B."""
    v_a, v_b = curva_volumen(TecnicaMezcla.HARD_CUT, 0.3)
    assert v_a == 1.0 and v_b == 0.0
    v_a, v_b = curva_volumen(TecnicaMezcla.HARD_CUT, 0.7)
    assert v_a == 0.0 and v_b == 1.0


def test_curva_volumen_energy_blend_equal_power():
    """En el centro, vol_a y vol_b deben ser iguales (~0.707)."""
    v_a, v_b = curva_volumen(TecnicaMezcla.ENERGY_BLEND, 0.5)
    assert v_a == pytest.approx(v_b, abs=1e-3)
    # Suma de cuadrados ~ constante (equal-power).
    assert (v_a ** 2 + v_b ** 2) == pytest.approx(1.0, abs=1e-3)


def test_curva_volumen_clamping():
    """Progresos fuera de [0,1] se clampan."""
    assert curva_volumen(TecnicaMezcla.FILTER_SWEEP, -0.5) == curva_volumen(TecnicaMezcla.FILTER_SWEEP, 0.0)
    assert curva_volumen(TecnicaMezcla.FILTER_SWEEP, 1.5) == curva_volumen(TecnicaMezcla.FILTER_SWEEP, 1.0)


# =============================================================================
# Curvas de EQ
# =============================================================================


def test_curva_eq_inicio_no_modifica_bandas():
    """En p=0 ninguna banda debe estar atenuada."""
    amps_a, amps_b = curva_eq(TecnicaMezcla.EQ_KILL_BASS, 0.0)
    assert amps_a == [0.0] * NUM_BANDAS_EQ
    assert amps_b == [0.0] * NUM_BANDAS_EQ


def test_curva_eq_kill_bass_final():
    """En p=1 los graves de A están killeados; los de B levemente reforzados."""
    amps_a, amps_b = curva_eq(TecnicaMezcla.EQ_KILL_BASS, 1.0)
    # Bandas 0, 1 (31Hz, 62Hz) -> kill total.
    assert amps_a[0] == pytest.approx(GANANCIA_KILL_DB)
    assert amps_a[1] == pytest.approx(GANANCIA_KILL_DB)
    # Banda 2 (125 Hz): kill parcial.
    assert -10.0 < amps_a[2] < 0.0
    # Bandas medias/agudas no se tocan.
    for i in range(3, NUM_BANDAS_EQ):
        assert amps_a[i] == 0.0
    # B sube bajos en bandas 0 y 1.
    assert amps_b[0] > 0.0
    assert amps_b[1] > 0.0


def test_curva_eq_filter_sweep_convergente():
    """En FILTER_SWEEP, A pierde graves y B pierde agudos progresivamente."""
    amps_a, amps_b = curva_eq(TecnicaMezcla.FILTER_SWEEP, 0.5)
    # A: las bandas bajas están atenuadas.
    assert amps_a[0] < 0.0
    # B: las bandas altas están atenuadas.
    assert amps_b[-1] < 0.0


def test_curva_eq_no_aplica_a_hard_cut():
    """HARD_CUT no toca EQ: todas las bandas a 0."""
    amps_a, amps_b = curva_eq(TecnicaMezcla.HARD_CUT, 0.5)
    assert amps_a == [0.0] * NUM_BANDAS_EQ
    assert amps_b == [0.0] * NUM_BANDAS_EQ


def test_curva_eq_bandas_estan_definidas():
    assert len(EQ_BANDAS_HZ) == NUM_BANDAS_EQ
    assert EQ_BANDAS_HZ[0] < EQ_BANDAS_HZ[-1]


# =============================================================================
# MixEngine: caché de mix points
# =============================================================================


def test_mix_engine_cachea_mix_points():
    engine = MixEngine(perfil=PerfilHardware.LOW)
    mp1 = engine.calcular_mix_points(1, "/x.mp3", 240.0, 120.0)
    mp2 = engine.calcular_mix_points(1, "/x.mp3", 240.0, 120.0)
    assert mp1 is mp2


def test_mix_engine_invalida_cache():
    engine = MixEngine(perfil=PerfilHardware.LOW)
    mp1 = engine.calcular_mix_points(1, "/x.mp3", 240.0, 120.0)
    engine.invalidar_cache(1)
    mp2 = engine.calcular_mix_points(1, "/x.mp3", 240.0, 120.0)
    # Otro objeto pero mismo contenido.
    assert mp1 is not mp2
    assert mp1 == mp2


# =============================================================================
# MixEngine: preparar_transicion completo
# =============================================================================


class _FakeStemsProvider:
    """StemsProvider que devuelve una ruta válida si el archivo existe."""

    def __init__(self, rutas: dict[int, Path]) -> None:
        self._rutas = rutas

    def ruta_no_vocals(self, pista_id, ruta_audio):
        return self._rutas.get(int(pista_id))


def test_preparar_transicion_low_no_usa_stems_aunque_esten(tmp_path):
    stem_path = tmp_path / "no_vocals.mp3"
    stem_path.write_bytes(b"fake")
    engine = MixEngine(
        perfil=PerfilHardware.LOW,
        stems_provider=_FakeStemsProvider({2: stem_path}),
    )
    plan = engine.preparar_transicion(
        plan_transicion=_plan_transicion(factor_bpm=0.9, factor_key=0.9),
        pista_a_id=1, pista_b_id=2,
        pista_a_ruta="/a.mp3", pista_b_ruta="/b.mp3",
        pista_a_duracion=200.0, pista_b_duracion=200.0,
        pista_a_bpm=120.0, pista_b_bpm=121.0,
        fase_narrativa="groove",
    )
    assert plan.tecnica != TecnicaMezcla.HARMONIC_MIX
    assert plan.ruta_audio_b_override is None


def test_preparar_transicion_high_con_stems_da_harmonic(tmp_path):
    stem_path = tmp_path / "no_vocals.mp3"
    stem_path.write_bytes(b"fake")
    engine = MixEngine(
        perfil=PerfilHardware.HIGH,
        stems_provider=_FakeStemsProvider({2: stem_path}),
    )
    plan = engine.preparar_transicion(
        plan_transicion=_plan_transicion(factor_bpm=0.9, factor_key=0.9),
        pista_a_id=1, pista_b_id=2,
        pista_a_ruta="/a.mp3", pista_b_ruta="/b.mp3",
        pista_a_duracion=200.0, pista_b_duracion=200.0,
        pista_a_bpm=120.0, pista_b_bpm=121.0,
        fase_narrativa="groove",
    )
    assert plan.tecnica == TecnicaMezcla.HARMONIC_MIX
    assert plan.ruta_audio_b_override == str(stem_path)


def test_preparar_transicion_stems_listos_pero_archivo_no_existe_degrada(tmp_path):
    """Si el provider reporta un path inexistente, el motor lo trata como no listo."""
    no_existe = tmp_path / "no_existe.mp3"
    engine = MixEngine(
        perfil=PerfilHardware.HIGH,
        stems_provider=_FakeStemsProvider({2: no_existe}),
    )
    plan = engine.preparar_transicion(
        plan_transicion=_plan_transicion(factor_bpm=0.9, factor_key=0.9),
        pista_a_id=1, pista_b_id=2,
        pista_a_ruta="/a.mp3", pista_b_ruta="/b.mp3",
        pista_a_duracion=200.0, pista_b_duracion=200.0,
        pista_a_bpm=120.0, pista_b_bpm=121.0,
        fase_narrativa="groove",
    )
    assert plan.tecnica != TecnicaMezcla.HARMONIC_MIX
    assert plan.ruta_audio_b_override is None


def test_preparar_transicion_release_da_blend_largo():
    engine = MixEngine(perfil=PerfilHardware.LOW)
    plan = engine.preparar_transicion(
        plan_transicion=_plan_transicion(overlap_seg=4.0),
        pista_a_id=1, pista_b_id=2,
        pista_a_ruta="/a.mp3", pista_b_ruta="/b.mp3",
        pista_a_duracion=200.0, pista_b_duracion=200.0,
        pista_a_bpm=120.0, pista_b_bpm=120.0,
        fase_narrativa="release",
    )
    assert plan.tecnica == TecnicaMezcla.ENERGY_BLEND
    assert plan.overlap_seg >= 10.0


def test_preparar_transicion_actualiza_perfil_en_runtime():
    """Cambiar el perfil entre llamadas debe afectar la siguiente decisión."""
    engine = MixEngine(perfil=PerfilHardware.LOW)
    p1 = engine.preparar_transicion(
        plan_transicion=_plan_transicion(factor_bpm=0.85),
        pista_a_id=1, pista_b_id=2,
        pista_a_ruta="/a.mp3", pista_b_ruta="/b.mp3",
        pista_a_duracion=200.0, pista_b_duracion=200.0,
        pista_a_bpm=120, pista_b_bpm=120.5,
        fase_narrativa="peak",
    )
    # En LOW, peak con BPM iguales: hard_cut.
    assert p1.tecnica == TecnicaMezcla.HARD_CUT
    engine.actualizar_perfil(PerfilHardware.HIGH)
    p2 = engine.preparar_transicion(
        plan_transicion=_plan_transicion(factor_bpm=0.85),
        pista_a_id=1, pista_b_id=3,
        pista_a_ruta="/a.mp3", pista_b_ruta="/c.mp3",
        pista_a_duracion=200.0, pista_b_duracion=200.0,
        pista_a_bpm=120, pista_b_bpm=120.5,
        fase_narrativa="peak",
    )
    # En HIGH también es hard_cut (regla 1).
    assert p2.tecnica == TecnicaMezcla.HARD_CUT


# =============================================================================
# Etiqueta humana
# =============================================================================


def test_etiqueta_humana_no_expone_codigo():
    """Las etiquetas para UI no deben contener guiones bajos ni mayúsculas tipo enum."""
    for tecnica in TecnicaMezcla:
        etiqueta = etiqueta_humana(tecnica)
        assert etiqueta
        assert "_" not in etiqueta
        assert etiqueta != tecnica.value


# =============================================================================
# EjecutorMezcla
# =============================================================================


def _plan_mezcla(tecnica: TecnicaMezcla, usa_eq: bool) -> PlanMezcla:
    return PlanMezcla(
        tecnica=tecnica,
        overlap_seg=5.0,
        mix_out_a_seg=180.0,
        mix_in_b_seg=8.0,
        ruta_audio_b_override=None,
        usa_eq=usa_eq,
        razones=(),
        etiqueta_ui=etiqueta_humana(tecnica),
    )


def test_ejecutor_aplica_volumen_a_ambos_decks():
    deck_a = MagicMock()
    deck_b = MagicMock()
    ejecutor = EjecutorMezcla(
        _plan_mezcla(TecnicaMezcla.ENERGY_BLEND, usa_eq=False),
        deck_a=deck_a, deck_b=deck_b, volumen_objetivo=80,
    )
    ejecutor.aplicar_tick(0.5)
    deck_a.audio_set_volume.assert_called()
    deck_b.audio_set_volume.assert_called()
    # En equal-power p=0.5 ambos a ~0.707 * 80 ~= 57.
    args_a = deck_a.audio_set_volume.call_args[0][0]
    args_b = deck_b.audio_set_volume.call_args[0][0]
    assert 50 <= args_a <= 65
    assert 50 <= args_b <= 65


def test_ejecutor_libera_eq_al_terminar():
    """liberar() debe desconectar el EQ de los dos decks (set_equalizer(None))."""
    deck_a = MagicMock()
    deck_b = MagicMock()
    ejecutor = EjecutorMezcla(
        _plan_mezcla(TecnicaMezcla.EQ_KILL_BASS, usa_eq=True),
        deck_a=deck_a, deck_b=deck_b, volumen_objetivo=80,
    )
    ejecutor.liberar()
    deck_a.set_equalizer.assert_any_call(None)
    deck_b.set_equalizer.assert_any_call(None)


def test_ejecutor_sin_eq_no_intenta_aplicar_amps():
    """Si usa_eq=False, no debe intentar configurar bandas EQ."""
    deck_a = MagicMock()
    deck_b = MagicMock()
    ejecutor = EjecutorMezcla(
        _plan_mezcla(TecnicaMezcla.ENERGY_BLEND, usa_eq=False),
        deck_a=deck_a, deck_b=deck_b, volumen_objetivo=80,
    )
    ejecutor.aplicar_tick(0.3)
    # No se llamó a set_equalizer salvo en liberar() si se llamase.
    # En aplicar_tick con usa_eq=False, no debe haber llamadas a set_equalizer.
    deck_a.set_equalizer.assert_not_called()
    deck_b.set_equalizer.assert_not_called()


def test_ejecutor_volumen_fuera_de_rango_no_crashea():
    """El ejecutor debe tolerar volúmenes fuera del rango canónico."""
    deck_a = MagicMock()
    deck_b = MagicMock()
    EjecutorMezcla(
        _plan_mezcla(TecnicaMezcla.HARD_CUT, usa_eq=False),
        deck_a=deck_a, deck_b=deck_b, volumen_objetivo=500,  # se clampa
    ).aplicar_tick(1.0)
    # No exception is enough.


# =============================================================================
# Protocolo StemsProvider
# =============================================================================


def test_stems_provider_es_protocolo_estructural():
    """Una clase que implementa ruta_no_vocals satisface el protocolo."""

    class Provider:
        def ruta_no_vocals(self, pista_id, ruta_audio):
            return None

    # No debería levantar isinstance check (Protocol estructural).
    p: StemsProvider = Provider()  # type: ignore[assignment]
    assert p.ruta_no_vocals(1, "/x.mp3") is None
