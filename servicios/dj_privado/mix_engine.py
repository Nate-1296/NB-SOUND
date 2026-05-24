# =============================================================================
# servicios/dj_privado/mix_engine.py
#
# Motor de mezcla real para el DJ Privado.
#
# Filosofía:
#   - El scheduler ya decide QUÉ pistas entran en cada posición.
#   - El mix engine decide CÓMO mezclarlas: técnica concreta, dónde recortar
#     cada pista (mix-in / mix-out points) y cómo modular EQ y volumen
#     durante el overlap.
#   - Todas las decisiones de selección son funciones puras (testeables).
#     El estado de runtime vive en `EjecutorMezcla`, que sostiene las dos
#     instancias `vlc.AudioEqualizer` durante la vida de una transición.
#   - Las técnicas que dependen de Demucs (HARMONIC_MIX) consultan a un
#     `StemsProvider` opcional. Si no hay stems listos para una transición
#     concreta, el motor degrada a otra técnica del mismo nivel sin avisar
#     al usuario.
# =============================================================================

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Protocol

from infra.logger import obtener_logger
from servicios.dj_privado.hardware_profile import (
    PerfilHardware,
    perfil_efectivo,
    tecnicas_habilitadas,
)
from servicios.dj_privado.transiciones import TransicionPlan

logger = obtener_logger(__name__)

try:
    import vlc as _vlc  # type: ignore
    VLC_DISPONIBLE = True
except Exception:
    _vlc = None  # type: ignore
    VLC_DISPONIBLE = False


# =============================================================================
# TÉCNICAS DE MEZCLA
# =============================================================================

class TecnicaMezcla(str, Enum):
    """Técnica concreta seleccionada por el motor para una transición.

    HARD_CUT:      corte seco al beat. Requiere BPM similar (±2 BPM).
    ENERGY_BLEND:  crossfade volumétrico largo (32 beats típicos) para
                   transiciones cinematic / release→cooldown.
    EQ_KILL_BASS:  baja los graves del saliente y los sube en el entrante.
                   Útil para drops, breaks o cambios de carácter rítmico.
    FILTER_SWEEP:  high-pass sweep en el saliente y/o low-pass en el
                   entrante (gradiente de bandas EQ, no cutoff real).
    HARMONIC_MIX:  superposición plena con stem "no_vocals" en una de las
                   dos pistas. Requiere stems Demucs cacheados.
    """
    HARD_CUT     = "hard_cut"
    ENERGY_BLEND = "energy_blend"
    EQ_KILL_BASS = "eq_kill_bass"
    FILTER_SWEEP = "filter_sweep"
    HARMONIC_MIX = "harmonic_mix"


# Etiqueta humana (para que el UI no muestre identificadores técnicos).
ETIQUETAS_HUMANAS: dict[TecnicaMezcla, str] = {
    TecnicaMezcla.HARD_CUT:     "Corte en el beat",
    TecnicaMezcla.ENERGY_BLEND: "Fundido largo",
    TecnicaMezcla.EQ_KILL_BASS: "Mezclando con ecualización",
    TecnicaMezcla.FILTER_SWEEP: "Barrido de filtros",
    TecnicaMezcla.HARMONIC_MIX: "Fundiendo capas",
}


def etiqueta_humana(tecnica: TecnicaMezcla) -> str:
    """Texto visible al usuario para una técnica. No exponer el enum bruto."""
    return ETIQUETAS_HUMANAS.get(tecnica, "Mezclando")


# =============================================================================
# MIX POINTS
# =============================================================================

@dataclass(frozen=True)
class MixPoints:
    """Puntos óptimos de entrada y salida de una pista.

    `mix_in_seg` es el offset desde el inicio: el reproductor hace seek a
    ese punto al cargar la pista. `mix_out_seg` es el momento donde puede
    arrancar el fade hacia la siguiente. Ambos respetan la duración natural.

    `fuente` documenta cómo se calcularon. Útil para debug y telemetría.
    """
    mix_in_seg:  float
    mix_out_seg: float
    duracion_seg: float
    fuente: str  # "bpm" | "rms" | "default"


# Tiempos por defecto cuando no hay ni BPM ni análisis disponibles.
DEFAULT_INTRO_SEG = 8.0
DEFAULT_OUTRO_SEG = 12.0
# Si la pista es muy corta, no recortamos.
MIN_DURACION_PARA_RECORTE = 60.0


def calcular_mix_points_por_bpm(
    duracion_seg: float,
    bpm: Optional[float],
    *,
    beats_intro: int = 16,
    beats_outro: int = 32,
) -> Optional[MixPoints]:
    """Mix-in/out estimados como múltiplos de beats si hay BPM.

    Devuelve None si no hay BPM o si la duración es demasiado corta para
    recortar (preferimos tocar la pista completa).
    """
    if not bpm or bpm <= 0 or duracion_seg < MIN_DURACION_PARA_RECORTE:
        return None
    seg_por_beat = 60.0 / float(bpm)
    intro = max(0.0, beats_intro * seg_por_beat)
    outro = max(0.0, beats_outro * seg_por_beat)
    # Garantizamos al menos 60% de la pista entre mix-in y mix-out.
    if (duracion_seg - intro - outro) < duracion_seg * 0.5:
        intro = max(0.0, duracion_seg * 0.10)
        outro = max(0.0, duracion_seg * 0.15)
    mix_out = max(intro + 30.0, duracion_seg - outro)
    return MixPoints(
        mix_in_seg=round(intro, 2),
        mix_out_seg=round(mix_out, 2),
        duracion_seg=round(duracion_seg, 2),
        fuente="bpm",
    )


def calcular_mix_points_por_rms(
    ruta_audio: str,
    duracion_seg: float,
    *,
    ventana_seg: float = 1.0,
) -> Optional[MixPoints]:
    """Análisis RMS ligero para detectar los valles de energía a inicio y fin.

    Usa librosa+soundfile (ya disponible en requirements.txt). Si librosa
    no está instalada, el archivo no se puede leer, o la pista resultante
    no tiene al menos 30 s útiles de margen entre mix-in y mix-out,
    devuelve None y el llamador cae al fallback determinista.

    IMPORTANTE: este cálculo BLOQUEA (carga todo el audio con librosa).
    El reproductor no lo invoca en el hilo principal; el motor lo expone
    sólo cuando se llama con `permitir_rms=True` explícito.
    """
    if duracion_seg < MIN_DURACION_PARA_RECORTE:
        return None
    try:
        import librosa  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return None
    try:
        # Descarga rebajada (mono, 22050) — suficiente para detectar valles RMS
        # sin gastar memoria. Para una pista de 4 min son ~5 MB.
        y, sr = librosa.load(ruta_audio, sr=22050, mono=True)
    except Exception as exc:
        logger.info("RMS: no se pudo leer %s: %s", ruta_audio, exc)
        return None
    if y.size < sr * 30:  # menos de 30s útiles
        return None
    hop = max(1, int(sr * ventana_seg / 4))
    frame = int(sr * ventana_seg)
    rms = librosa.feature.rms(y=y, frame_length=frame, hop_length=hop)[0]
    if rms.size == 0:
        return None
    objetivo = float(np.median(rms)) * 0.6
    idxs_sobre_umbral = np.where(rms >= objetivo)[0]
    if idxs_sobre_umbral.size == 0:
        return None
    idx_in = int(idxs_sobre_umbral[0])
    idx_out = int(idxs_sobre_umbral[-1])
    n_frames = rms.size
    seg_por_frame = hop / sr
    mix_in_seg = max(0.0, idx_in * seg_por_frame - 2.0)
    duracion_real = min(duracion_seg, n_frames * seg_por_frame)
    mix_out_seg = min(idx_out * seg_por_frame, duracion_real - 1.0)
    # Garantizar al menos 30 s útiles entre mix-in y mix-out. Si el audio
    # útil es más corto, descartamos: el caller usa otro fallback. Esto
    # evita devolver puntos donde `mix_out <= mix_in` que harían disparar
    # transición inmediata al cargar la pista.
    if mix_out_seg - mix_in_seg < 30.0:
        return None
    return MixPoints(
        mix_in_seg=round(mix_in_seg, 2),
        mix_out_seg=round(mix_out_seg, 2),
        duracion_seg=round(duracion_real, 2),
        fuente="rms",
    )


def mix_points_default(duracion_seg: float) -> MixPoints:
    """Fallback determinista para pistas sin BPM ni análisis posible."""
    if duracion_seg < MIN_DURACION_PARA_RECORTE:
        return MixPoints(
            mix_in_seg=0.0,
            mix_out_seg=round(duracion_seg, 2),
            duracion_seg=round(duracion_seg, 2),
            fuente="default",
        )
    return MixPoints(
        mix_in_seg=DEFAULT_INTRO_SEG,
        mix_out_seg=round(max(0.0, duracion_seg - DEFAULT_OUTRO_SEG), 2),
        duracion_seg=round(duracion_seg, 2),
        fuente="default",
    )


# =============================================================================
# PROVIDER DE STEMS (HARMONIC_MIX)
# =============================================================================

class StemsProvider(Protocol):
    """Contrato para obtener stems pre-renderizados.

    El motor sólo activa HARMONIC_MIX si el provider responde con una ruta
    legible para la pista. El llamador (servicio DJ) implementa este
    contrato envolviendo el subsistema karaoke u otra fuente.
    """

    def ruta_no_vocals(self, pista_id: int, ruta_audio: str) -> Optional[Path]:
        """Devuelve la ruta del stem 'sin voz' si está listo. None si no."""


# =============================================================================
# PLAN DE MEZCLA RESULTANTE
# =============================================================================

@dataclass(frozen=True)
class PlanMezcla:
    """Decisión completa del motor para una transición concreta.

    El reproductor usa este plan para:
      - Saber CUÁNDO iniciar la transición (`overlap_seg` antes del mix_out).
      - Saber QUÉ MEDIA cargar en el deck entrante (puede ser un stem).
      - Saber DÓNDE arrancar el deck entrante (`mix_in_b_seg`).
      - Saber CÓMO modular volumen y EQ en cada tick.
    """
    tecnica:       TecnicaMezcla
    overlap_seg:   float
    mix_out_a_seg: float       # absoluto sobre la pista A
    mix_in_b_seg:  float       # absoluto sobre la pista B
    ruta_audio_b_override: Optional[str]   # stem "no_vocals" si aplica
    usa_eq:        bool
    razones:       tuple[str, ...]
    etiqueta_ui:   str         # texto para mostrar al usuario


# =============================================================================
# SELECCIÓN DE TÉCNICA
# =============================================================================

def _bpm_compatibles_para_hard_cut(bpm_a: Optional[float], bpm_b: Optional[float]) -> bool:
    if bpm_a is None or bpm_b is None:
        return False
    if bpm_a <= 0 or bpm_b <= 0:
        return False
    return abs(bpm_a - bpm_b) <= 2.0


def seleccionar_tecnica(
    *,
    plan_transicion: TransicionPlan,
    perfil: PerfilHardware,
    fase_narrativa: str,
    bpm_a: Optional[float],
    bpm_b: Optional[float],
    stems_listos: bool,
) -> tuple[TecnicaMezcla, tuple[str, ...]]:
    """Decide la técnica concreta para una transición.

    Reglas en orden de prioridad:
      1. Si la fase es PEAK y los BPM son casi iguales: HARD_CUT.
      2. Si fase release→cooldown: ENERGY_BLEND (fundido largo).
      3. Si perfil habilita HARMONIC_MIX y los stems están listos
         y el score armónico de la transición es bueno: HARMONIC_MIX.
      4. Si score de BPM es alto pero el de energía es ruidoso: EQ_KILL_BASS.
      5. Default: FILTER_SWEEP (siempre disponible vía libVLC).

    Devuelve la técnica + razones legibles (para auditar la decisión).
    """
    habilitadas = set(tecnicas_habilitadas(perfil))
    razones: list[str] = []
    fase = (fase_narrativa or "").lower()

    if fase == "peak" and _bpm_compatibles_para_hard_cut(bpm_a, bpm_b):
        razones.append("peak con BPM casi iguales -> corte seco")
        if "hard_cut" in habilitadas:
            return TecnicaMezcla.HARD_CUT, tuple(razones)

    if fase in ("release", "cooldown"):
        razones.append("fase de descenso -> fundido largo")
        if "energy_blend" in habilitadas:
            return TecnicaMezcla.ENERGY_BLEND, tuple(razones)

    quiere_harmonic = (
        stems_listos
        and "harmonic_mix" in habilitadas
        and plan_transicion.factor_key >= 0.6
        and plan_transicion.factor_bpm >= 0.6
    )
    if quiere_harmonic:
        razones.append("tonalidades compatibles y stems listos -> mezcla con capas")
        return TecnicaMezcla.HARMONIC_MIX, tuple(razones)

    # Si los BPM son cercanos pero la energía cambia, EQ kill funciona muy bien
    # porque la pista entrante "entra por arriba" hasta que se le sueltan bajos.
    if plan_transicion.factor_bpm >= 0.75 and "eq_kill_bass" in habilitadas:
        razones.append("BPM cercano -> EQ kill bass")
        return TecnicaMezcla.EQ_KILL_BASS, tuple(razones)

    razones.append("transición neutra -> barrido de filtros")
    return TecnicaMezcla.FILTER_SWEEP, tuple(razones)


def overlap_recomendado(tecnica: TecnicaMezcla, overlap_base: float) -> float:
    """Ajusta el overlap base de la transición según la técnica.

    HARD_CUT: muy corto. ENERGY_BLEND: prolongado. El resto: cerca del overlap
    sugerido por el scoring de transición original.
    """
    if tecnica == TecnicaMezcla.HARD_CUT:
        return 0.4
    if tecnica == TecnicaMezcla.ENERGY_BLEND:
        return max(overlap_base, 10.0)
    if tecnica == TecnicaMezcla.HARMONIC_MIX:
        return max(overlap_base, 8.0)
    if tecnica == TecnicaMezcla.FILTER_SWEEP:
        return max(overlap_base, 6.0)
    return overlap_base


# =============================================================================
# CURVAS DE VOLUMEN Y EQ
# =============================================================================

def curva_volumen(tecnica: TecnicaMezcla, progreso: float) -> tuple[float, float]:
    """Devuelve (vol_a, vol_b) en rango [0,1] según el avance de la mezcla.

    `progreso` está clampeado por el llamador.
    """
    p = max(0.0, min(1.0, progreso))
    if tecnica == TecnicaMezcla.HARD_CUT:
        # Saliente cae a 0 en p>=0.5; entrante entra plena en p>=0.5.
        return (1.0 if p < 0.5 else 0.0, 0.0 if p < 0.5 else 1.0)
    if tecnica == TecnicaMezcla.ENERGY_BLEND:
        # Curva equal-power suave: mantiene la energía percibida.
        return ((1.0 - p) ** 0.5, p ** 0.5)
    if tecnica == TecnicaMezcla.HARMONIC_MIX:
        # Las dos pistas suenan plenas en el centro de la mezcla.
        return (max(0.0, 1.0 - p * 0.6), min(1.0, 0.4 + p * 0.6))
    if tecnica == TecnicaMezcla.FILTER_SWEEP:
        # Volumen lineal estándar; la "magia" la hace el filtro.
        return (1.0 - p, p)
    if tecnica == TecnicaMezcla.EQ_KILL_BASS:
        # Volumen lineal estándar; el EQ es lo que crea la sensación DJ.
        return (1.0 - p, p)
    return (1.0 - p, p)


# Ecualizador ISO de libVLC: bandas centrales en Hz.
EQ_BANDAS_HZ: tuple[float, ...] = (
    31.25, 62.5, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0,
)
NUM_BANDAS_EQ = len(EQ_BANDAS_HZ)
# Ganancia mínima útil (libVLC clampa a ~-20 dB).
GANANCIA_KILL_DB = -16.0


def curva_eq(tecnica: TecnicaMezcla, progreso: float) -> tuple[list[float], list[float]]:
    """Devuelve (ganancias_a, ganancias_b) — listas de 10 valores en dB.

    Cada lista mapea 1:1 con `EQ_BANDAS_HZ`. Ganancias 0.0 = pasa-todo.
    """
    p = max(0.0, min(1.0, progreso))
    a = [0.0] * NUM_BANDAS_EQ
    b = [0.0] * NUM_BANDAS_EQ

    if tecnica == TecnicaMezcla.EQ_KILL_BASS:
        # En A bajamos bandas 0, 1, 2 progresivamente (graves).
        kill_a = GANANCIA_KILL_DB * p
        a[0] = kill_a
        a[1] = kill_a
        a[2] = kill_a * 0.5
        # En B subimos esos mismos graves al entrar (compensa con +3 dB max).
        bump_b = 3.0 * p
        b[0] = bump_b
        b[1] = bump_b
        return a, b

    if tecnica == TecnicaMezcla.FILTER_SWEEP:
        # High-pass progresivo en A: bandas bajas caen primero.
        # Modelamos un cutoff que sube de banda 0 a banda 5 según p.
        cutoff_band_a = int(round(p * 5))
        for i in range(NUM_BANDAS_EQ):
            if i < cutoff_band_a:
                # Distancia al cutoff actual: kill total cerca del cutoff,
                # rampa más suave al alejarse.
                dist = cutoff_band_a - i
                a[i] = max(GANANCIA_KILL_DB, -4.0 * dist)
        # Low-pass de B al entrar: bandas altas atenuadas, suben con p.
        cutoff_band_b = int(round((1.0 - p) * 5))
        for i in range(NUM_BANDAS_EQ):
            if i > (NUM_BANDAS_EQ - 1 - cutoff_band_b):
                dist = i - (NUM_BANDAS_EQ - 1 - cutoff_band_b)
                b[i] = max(GANANCIA_KILL_DB, -4.0 * dist)
        return a, b

    # HARD_CUT, ENERGY_BLEND, HARMONIC_MIX no tocan EQ.
    return a, b


# =============================================================================
# MIX ENGINE
# =============================================================================

class MixEngine:
    """Decide mix points y plan de transición por solicitud, con caché.

    No mantiene estado de runtime de los decks (eso lo hace `EjecutorMezcla`).
    Es seguro instanciar uno por sesión.
    """

    def __init__(
        self,
        *,
        perfil: Optional[PerfilHardware] = None,
        stems_provider: Optional[StemsProvider] = None,
    ) -> None:
        self._perfil = perfil or perfil_efectivo()
        self._stems_provider = stems_provider
        self._mix_points_cache: dict[int, MixPoints] = {}
        self._lock = threading.RLock()

    @property
    def perfil(self) -> PerfilHardware:
        return self._perfil

    def actualizar_perfil(self, perfil: PerfilHardware) -> None:
        with self._lock:
            self._perfil = perfil

    def configurar_stems_provider(self, provider: Optional[StemsProvider]) -> None:
        with self._lock:
            self._stems_provider = provider

    # ------------------------------------------------------------------
    # MIX POINTS
    # ------------------------------------------------------------------

    def calcular_mix_points(
        self,
        pista_id: int,
        ruta_audio: str,
        duracion_seg: float,
        bpm: Optional[float],
        *,
        permitir_rms: bool = False,
    ) -> MixPoints:
        """Mix-in/out óptimos para una pista. Cachea en memoria por pista.

        Estrategia:
            1. BPM (rápido, determinista).
            2. RMS con librosa (sólo si `permitir_rms=True`: BLOQUEA por
               varios segundos cargando el audio entero).
            3. Default (cuando no hay BPM ni se quiere analizar audio).

        Por defecto el análisis RMS está DESHABILITADO: el reproductor
        llama esta función al cargar la sesión y no puede permitirse un
        bloqueo. Cualquier llamada que sí quiera análisis tiene que
        habilitarlo explícitamente y correrlo fuera del hilo principal.
        """
        with self._lock:
            cacheado = self._mix_points_cache.get(int(pista_id))
            if cacheado is not None:
                return cacheado

        resultado = calcular_mix_points_por_bpm(duracion_seg, bpm)
        if resultado is None and permitir_rms and ruta_audio:
            resultado = calcular_mix_points_por_rms(ruta_audio, duracion_seg)
        if resultado is None:
            resultado = mix_points_default(duracion_seg)

        with self._lock:
            self._mix_points_cache[int(pista_id)] = resultado
        return resultado

    def invalidar_cache(self, pista_id: Optional[int] = None) -> None:
        with self._lock:
            if pista_id is None:
                self._mix_points_cache.clear()
            else:
                self._mix_points_cache.pop(int(pista_id), None)

    # ------------------------------------------------------------------
    # PLAN DE MEZCLA
    # ------------------------------------------------------------------

    def preparar_transicion(
        self,
        *,
        plan_transicion: TransicionPlan,
        pista_a_id: int,
        pista_b_id: int,
        pista_a_ruta: str,
        pista_b_ruta: str,
        pista_a_duracion: float,
        pista_b_duracion: float,
        pista_a_bpm: Optional[float],
        pista_b_bpm: Optional[float],
        fase_narrativa: str,
    ) -> PlanMezcla:
        """Construye un PlanMezcla a partir de los datos disponibles.

        Si HARMONIC_MIX se selecciona pero los stems no están listos, hace
        fallback transparente a otra técnica del mismo nivel.
        """
        with self._lock:
            perfil = self._perfil
            stems_provider = self._stems_provider

        # Determinar disponibilidad de stems para esta transición. En
        # HIGH y MID requerimos que el stem esté ya en disco (no esperamos
        # al pre-fetch en runtime: arriesgaría la transición). En LOW la
        # técnica no está habilitada y ni siquiera consultamos al provider.
        stems_listos = False
        ruta_override: Optional[str] = None
        if stems_provider is not None and "harmonic_mix" in tecnicas_habilitadas(perfil):
            ruta_stem = stems_provider.ruta_no_vocals(pista_b_id, pista_b_ruta)
            if ruta_stem is not None and Path(ruta_stem).exists():
                stems_listos = True
                ruta_override = str(ruta_stem)

        tecnica, razones = seleccionar_tecnica(
            plan_transicion=plan_transicion,
            perfil=perfil,
            fase_narrativa=fase_narrativa,
            bpm_a=pista_a_bpm,
            bpm_b=pista_b_bpm,
            stems_listos=stems_listos,
        )

        if tecnica != TecnicaMezcla.HARMONIC_MIX:
            # Si caímos en otra técnica, el override de stems no aplica.
            ruta_override = None

        overlap = overlap_recomendado(tecnica, plan_transicion.overlap_seg)

        # Mix points: respetan duración natural pero no obligamos al
        # reproductor a hacer seek si el mix-in es 0. mix_out_a es el momento
        # en que arrancamos la transición; el reproductor llama a este motor
        # cuando faltan `overlap` segundos para mix_out_a.
        mp_a = self.calcular_mix_points(
            pista_a_id, pista_a_ruta, pista_a_duracion, pista_a_bpm,
            permitir_rms=False,
        )
        mp_b = self.calcular_mix_points(
            pista_b_id, pista_b_ruta, pista_b_duracion, pista_b_bpm,
            permitir_rms=False,
        )

        # El mix-out efectivo de A nunca debe pasar la duración real menos overlap.
        mix_out_a = min(mp_a.mix_out_seg, max(0.0, pista_a_duracion - overlap))
        mix_in_b = max(0.0, mp_b.mix_in_seg)

        usa_eq = tecnica in (TecnicaMezcla.EQ_KILL_BASS, TecnicaMezcla.FILTER_SWEEP)

        return PlanMezcla(
            tecnica=tecnica,
            overlap_seg=round(overlap, 2),
            mix_out_a_seg=round(mix_out_a, 2),
            mix_in_b_seg=round(mix_in_b, 2),
            ruta_audio_b_override=ruta_override,
            usa_eq=usa_eq,
            razones=razones,
            etiqueta_ui=etiqueta_humana(tecnica),
        )


# =============================================================================
# EJECUTOR DE TICK (estado de runtime)
# =============================================================================

class EjecutorMezcla:
    """Aplica volúmenes y EQ a dos decks de VLC durante una transición.

    Vive solo mientras la transición está activa. Se crea al iniciar y se
    descarta al completar. Encapsula la creación y vida de las dos
    instancias `vlc.AudioEqualizer`, que deben permanecer asignadas hasta
    el final del crossfade.
    """

    def __init__(
        self,
        plan: PlanMezcla,
        *,
        deck_a: Optional[object],
        deck_b: Optional[object],
        volumen_objetivo: int,
    ) -> None:
        self._plan = plan
        self._deck_a = deck_a
        self._deck_b = deck_b
        self._vol_objetivo = max(0, min(100, int(volumen_objetivo)))
        self._eq_a = None
        self._eq_b = None
        if plan.usa_eq and VLC_DISPONIBLE:
            try:
                self._eq_a = _vlc.AudioEqualizer()
                self._eq_b = _vlc.AudioEqualizer()
                if self._deck_a is not None:
                    self._deck_a.set_equalizer(self._eq_a)
                if self._deck_b is not None:
                    self._deck_b.set_equalizer(self._eq_b)
            except Exception as exc:
                logger.warning("no se pudo activar EQ para transición: %s", exc)
                self._eq_a = None
                self._eq_b = None

    @property
    def plan(self) -> PlanMezcla:
        return self._plan

    def aplicar_tick(self, progreso: float) -> None:
        """Avanza un tick: volúmenes y EQ se recalculan en cada llamada."""
        p = max(0.0, min(1.0, progreso))
        v_a, v_b = curva_volumen(self._plan.tecnica, p)
        if self._deck_a is not None:
            try:
                self._deck_a.audio_set_volume(int(round(v_a * self._vol_objetivo)))
            except Exception as _exc:
                logger.debug("Excepcion ignorada en %s: %s", "mix_engine.py", _exc)
        if self._deck_b is not None:
            try:
                self._deck_b.audio_set_volume(int(round(v_b * self._vol_objetivo)))
            except Exception as _exc:
                logger.debug("Excepcion ignorada en %s: %s", "mix_engine.py", _exc)
        if self._plan.usa_eq and self._eq_a is not None and self._eq_b is not None:
            amps_a, amps_b = curva_eq(self._plan.tecnica, p)
            for idx in range(NUM_BANDAS_EQ):
                try:
                    self._eq_a.set_amp_at_index(float(amps_a[idx]), idx)
                    self._eq_b.set_amp_at_index(float(amps_b[idx]), idx)
                except Exception:
                    break
            try:
                if self._deck_a is not None:
                    self._deck_a.set_equalizer(self._eq_a)
                if self._deck_b is not None:
                    self._deck_b.set_equalizer(self._eq_b)
            except Exception as _exc:
                logger.debug("Excepcion ignorada en %s: %s", "mix_engine.py", _exc)

    def liberar(self) -> None:
        """Desconecta el EQ de los decks. Llamar al terminar la transición."""
        if VLC_DISPONIBLE:
            try:
                if self._deck_a is not None:
                    self._deck_a.set_equalizer(None)
                if self._deck_b is not None:
                    self._deck_b.set_equalizer(None)
            except Exception as _exc:
                logger.debug("Excepcion ignorada en %s: %s", "mix_engine.py", _exc)
        self._eq_a = None
        self._eq_b = None
