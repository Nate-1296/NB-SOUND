# =============================================================================
# servicios/dj_privado/hardware_profile.py
#
# Detecta la capacidad real del hardware para decidir qué técnicas de mezcla
# habilitar en el motor del DJ Privado. El resultado se cachea entre sesiones.
#
# Filosofía:
#   - LOW no es "modo degradado": es un modo plenamente funcional que usa
#     técnicas DJ válidas (EQ kill, sweep de bandas, cortes) sin requerir
#     separación de stems.
#   - HIGH/MID habilitan técnicas que dependen de Demucs en tiempo casi-real
#     o pre-cacheado.
#   - El benchmark se ejecuta UNA sola vez y nunca bloquea el primer uso:
#     siempre se dispara en background y, si aún no terminó, se asume LOW.
# =============================================================================

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from infra.logger import obtener_logger

logger = obtener_logger(__name__)


# =============================================================================
# PERFILES
# =============================================================================

class PerfilHardware(str, Enum):
    """Categorización de la capacidad de mezcla disponible.

    El motor de mezcla mapea perfil → técnicas habilitadas en `tecnicas_habilitadas`.
    """
    HIGH = "high"
    MID  = "mid"
    LOW  = "low"


# Umbrales de clasificación (factor sobre tiempo real al separar 10s de audio).
# Si Demucs procesa 10s en menos de 15s -> HIGH. Hasta 50s -> MID. Más -> LOW.
UMBRAL_HIGH_FACTOR  = 1.5
UMBRAL_MID_FACTOR   = 5.0

# Si el benchmark tarda más que este límite, se aborta y se reporta LOW
# (la pista pierde sentido como uso real si separar 10s toma >2 minutos).
BENCHMARK_TIMEOUT_SEG = 120.0

# Clave en la tabla config_ui donde se persiste el perfil calculado.
CLAVE_CONFIG = "dj_privado_perfil_hardware"


# =============================================================================
# RESULTADO
# =============================================================================

@dataclass(frozen=True)
class ResultadoBenchmark:
    """Resumen del benchmark con todos los datos necesarios para auditar."""

    perfil:             PerfilHardware
    seg_para_10s:       float        # tiempo real medido (segundos)
    factor_tiempo_real: float        # seg_para_10s / 10.0
    device:             str          # "cpu" | "cuda" | "mps" | "n/a"
    demucs_disponible:  bool
    error:              Optional[str]  # mensaje breve si el benchmark falló
    benchmark_en:       str          # ISO timestamp

    def a_dict(self) -> dict:
        data = asdict(self)
        data["perfil"] = self.perfil.value
        return data

    @staticmethod
    def desde_dict(data: dict) -> "ResultadoBenchmark":
        return ResultadoBenchmark(
            perfil=PerfilHardware(str(data.get("perfil") or "low")),
            seg_para_10s=float(data.get("seg_para_10s") or 0.0),
            factor_tiempo_real=float(data.get("factor_tiempo_real") or 0.0),
            device=str(data.get("device") or "n/a"),
            demucs_disponible=bool(data.get("demucs_disponible") or False),
            error=data.get("error"),
            benchmark_en=str(data.get("benchmark_en") or ""),
        )


# =============================================================================
# TÉCNICAS HABILITADAS POR PERFIL
# =============================================================================

# Identificadores de técnica del mix engine. Se duplican aquí como literales
# para evitar import circular con mix_engine.
_TECNICAS_BASE  = ("hard_cut", "energy_blend", "eq_kill_bass", "filter_sweep")
_TECNICAS_STEMS = ("harmonic_mix",)


def tecnicas_habilitadas(perfil: PerfilHardware) -> tuple[str, ...]:
    """Conjunto de técnicas que el mix engine puede seleccionar.

    - LOW: solo técnicas que viven dentro de libVLC (EQ y filtros por banda).
    - MID: lo anterior + harmonic_mix solo si los stems están pre-cacheados.
    - HIGH: todo.
    """
    if perfil == PerfilHardware.HIGH:
        return _TECNICAS_BASE + _TECNICAS_STEMS
    if perfil == PerfilHardware.MID:
        return _TECNICAS_BASE + _TECNICAS_STEMS
    return _TECNICAS_BASE


# =============================================================================
# PERSISTENCIA
# =============================================================================

def _cargar_desde_db() -> Optional[ResultadoBenchmark]:
    """Lee el resultado guardado desde la tabla config_ui.

    Devuelve None si nunca se ha hecho benchmark, si el valor está corrupto
    o si la BD aún no está inicializada (caso de tests aislados).
    """
    try:
        from db.conexion import obtener_config
    except Exception:
        return None
    try:
        raw = obtener_config(CLAVE_CONFIG, "")
    except Exception:
        return None
    if not raw:
        return None
    try:
        return ResultadoBenchmark.desde_dict(json.loads(raw))
    except Exception:
        logger.warning("perfil de hardware guardado corrupto; será regenerado")
        return None


def _guardar_en_db(resultado: ResultadoBenchmark) -> None:
    """Persiste el resultado en config_ui. Silencioso si la BD no está lista."""
    try:
        from db.conexion import guardar_config
    except Exception:
        return
    try:
        guardar_config(CLAVE_CONFIG, json.dumps(resultado.a_dict(), ensure_ascii=False))
    except Exception:
        logger.warning("no se pudo persistir el perfil de hardware", exc_info=True)


# =============================================================================
# CLASIFICACIÓN
# =============================================================================

def clasificar(factor_tiempo_real: float, demucs_ok: bool) -> PerfilHardware:
    """Convierte el factor medido en uno de los tres perfiles.

    Si Demucs no está disponible, siempre devuelve LOW (no podemos hacer
    HARMONIC_MIX sin separación) y el motor cae en técnicas vía libVLC.
    """
    if not demucs_ok:
        return PerfilHardware.LOW
    if factor_tiempo_real <= 0.0:
        return PerfilHardware.LOW
    if factor_tiempo_real <= UMBRAL_HIGH_FACTOR:
        return PerfilHardware.HIGH
    if factor_tiempo_real <= UMBRAL_MID_FACTOR:
        return PerfilHardware.MID
    return PerfilHardware.LOW


# =============================================================================
# BENCHMARK
# =============================================================================

def _generar_audio_sintetico(duracion_seg: float = 10.0, samplerate: int = 44100):
    """Construye un buffer de audio sintético con contenido amplio.

    Mezcla de tres senoides (bajo, medio, agudo) modulado en amplitud y con
    pequeño ruido blanco. Densidad espectral suficiente para que Demucs no
    optimice la separación de un silencio.
    """
    import numpy as np  # type: ignore

    n = int(duracion_seg * samplerate)
    t = np.arange(n, dtype=np.float32) / samplerate
    base = (
        0.30 * np.sin(2 * np.pi *  80.0 * t)   # grave
        + 0.25 * np.sin(2 * np.pi * 440.0 * t)   # medio (A4)
        + 0.20 * np.sin(2 * np.pi * 3000.0 * t)  # agudo
    )
    modulacion = 0.5 + 0.5 * np.sin(2 * np.pi * 0.5 * t)
    ruido = (np.random.default_rng(42).standard_normal(n).astype(np.float32) * 0.02)
    canal = (base * modulacion + ruido).astype(np.float32)
    # Estéreo: replica el mismo canal con pequeño desfase para que no sea mono perfecto.
    stereo = np.stack([canal, np.roll(canal, 30)], axis=0)
    return stereo


def _device_disponible() -> str:
    """Detecta el mejor dispositivo de inferencia disponible para Demucs."""
    try:
        import torch  # type: ignore
    except Exception:
        return "cpu"
    try:
        if torch.cuda.is_available():
            return "cuda"
    except Exception as _exc:
        logger.debug("Excepcion ignorada en %s: %s", "hardware_profile.py", _exc)
    try:
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception as _exc:
        logger.debug("Excepcion ignorada en %s: %s", "hardware_profile.py", _exc)
    return "cpu"


def _ejecutar_benchmark(*, modelo_nombre: str = "htdemucs") -> ResultadoBenchmark:
    """Corre el benchmark medible una sola vez. No lanza excepciones.

    El cálculo del factor de tiempo real excluye el load del modelo (es un
    coste de una sola vez por proceso). Si Demucs no se puede importar o el
    forward falla, devuelve un resultado LOW con `error` poblado.
    """
    iso_now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    device = _device_disponible()

    try:
        import torch  # type: ignore
        from demucs.apply import apply_model  # type: ignore

        from servicios.karaoke.modelo import cargar_modelo  # tarda ~1s en frío
        from servicios.karaoke.rutas import directorio_modelos
        from config import settings  # type: ignore
    except Exception as exc:
        logger.info("Demucs no disponible para benchmark: %s", exc)
        return ResultadoBenchmark(
            perfil=PerfilHardware.LOW,
            seg_para_10s=0.0,
            factor_tiempo_real=0.0,
            device="n/a",
            demucs_disponible=False,
            error=f"import_error: {exc}",
            benchmark_en=iso_now,
        )

    try:
        cache_base = Path(settings.DEFAULT_CACHE_DIR or Path.home() / ".cache" / "nb_sound")
        modelo = cargar_modelo(directorio_modelos(cache_base), modelo_nombre)
    except Exception as exc:
        logger.warning("benchmark: carga de modelo Demucs falló: %s", exc)
        return ResultadoBenchmark(
            perfil=PerfilHardware.LOW,
            seg_para_10s=0.0,
            factor_tiempo_real=0.0,
            device=device,
            demucs_disponible=False,
            error=f"model_load: {exc}",
            benchmark_en=iso_now,
        )

    try:
        audio = _generar_audio_sintetico(10.0, samplerate=getattr(modelo, "samplerate", 44100))
        mix = torch.from_numpy(audio).unsqueeze(0)  # (1, 2, n)

        # Una pasada de warm-up (no medida) para amortizar JIT/caches del backend.
        with torch.no_grad():
            apply_model(modelo, mix[..., :8192].to(device),
                        shifts=0, split=False, overlap=0.0,
                        progress=False, device=device, num_workers=0)

        t0 = time.monotonic()
        with torch.no_grad():
            apply_model(modelo, mix.to(device),
                        shifts=0, split=True, overlap=0.25,
                        progress=False, device=device, num_workers=0)
        seg = time.monotonic() - t0
    except Exception as exc:
        logger.warning("benchmark: forward de Demucs falló: %s", exc)
        return ResultadoBenchmark(
            perfil=PerfilHardware.LOW,
            seg_para_10s=0.0,
            factor_tiempo_real=0.0,
            device=device,
            demucs_disponible=True,
            error=f"forward: {exc}",
            benchmark_en=iso_now,
        )

    if seg <= 0:
        seg = float("inf")
    factor = seg / 10.0
    perfil = clasificar(factor, demucs_ok=True)
    logger.info("benchmark hardware DJ: %.2fs (factor %.2fx, device %s) -> %s",
                seg, factor, device, perfil.value)
    return ResultadoBenchmark(
        perfil=perfil,
        seg_para_10s=round(seg, 3),
        factor_tiempo_real=round(factor, 3),
        device=device,
        demucs_disponible=True,
        error=None,
        benchmark_en=iso_now,
    )


# =============================================================================
# API PÚBLICA
# =============================================================================

_lock_benchmark = threading.RLock()
_estado_benchmark: dict = {"corriendo": False, "ultimo": None}


def perfil_guardado() -> Optional[ResultadoBenchmark]:
    """Devuelve el último benchmark persistido o None si nunca se hizo."""
    if _estado_benchmark["ultimo"] is not None:
        return _estado_benchmark["ultimo"]  # type: ignore[return-value]
    cargado = _cargar_desde_db()
    if cargado is not None:
        _estado_benchmark["ultimo"] = cargado
    return cargado


def perfil_efectivo() -> PerfilHardware:
    """Perfil a usar AHORA, sin disparar nada en background.

    Si no hay benchmark previo: LOW. El motor de mezcla siempre puede
    funcionar en LOW; cuando termine el benchmark se reevalúa.
    """
    guardado = perfil_guardado()
    return guardado.perfil if guardado else PerfilHardware.LOW


def benchmark_corriendo() -> bool:
    """True si hay un benchmark en background en este proceso."""
    with _lock_benchmark:
        return bool(_estado_benchmark["corriendo"])


def lanzar_benchmark_si_falta(
    *,
    on_completado: Optional[Callable[[ResultadoBenchmark], None]] = None,
    forzar: bool = False,
) -> bool:
    """Si no hay perfil guardado (o `forzar=True`), corre el benchmark en
    un hilo daemon. Nunca bloquea al llamador. Idempotente: si ya hay uno
    corriendo, devuelve False sin lanzar otro.

    Devuelve True si se programó una corrida nueva, False si ya había una o
    si ya existe un perfil guardado y `forzar=False`.
    """
    with _lock_benchmark:
        if _estado_benchmark["corriendo"]:
            return False
        if not forzar and perfil_guardado() is not None:
            return False
        _estado_benchmark["corriendo"] = True

    def _correr() -> None:
        try:
            t0 = time.monotonic()
            resultado = _ejecutar_benchmark()
            if time.monotonic() - t0 > BENCHMARK_TIMEOUT_SEG:
                # En la práctica el benchmark no debería tardar tanto; si
                # ocurre, fuerza perfil LOW para no engañar al usuario.
                logger.warning("benchmark tardó >%.0fs; forzando LOW", BENCHMARK_TIMEOUT_SEG)
                resultado = ResultadoBenchmark(
                    perfil=PerfilHardware.LOW,
                    seg_para_10s=resultado.seg_para_10s,
                    factor_tiempo_real=resultado.factor_tiempo_real,
                    device=resultado.device,
                    demucs_disponible=resultado.demucs_disponible,
                    error="timeout",
                    benchmark_en=resultado.benchmark_en,
                )
            _guardar_en_db(resultado)
            with _lock_benchmark:
                _estado_benchmark["ultimo"] = resultado
            if on_completado is not None:
                try:
                    on_completado(resultado)
                except Exception:
                    logger.exception("callback on_completado falló")
        finally:
            with _lock_benchmark:
                _estado_benchmark["corriendo"] = False

    threading.Thread(target=_correr, daemon=True, name="dj_hw_benchmark").start()
    return True


def resetear_perfil() -> None:
    """Borra el perfil guardado. Útil para tests y para forzar un re-benchmark."""
    with _lock_benchmark:
        _estado_benchmark["ultimo"] = None
    try:
        from db.conexion import guardar_config
        guardar_config(CLAVE_CONFIG, "")
    except Exception as _exc:
        logger.debug("Excepcion ignorada en %s: %s", "hardware_profile.py", _exc)
