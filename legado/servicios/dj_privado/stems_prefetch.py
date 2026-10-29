# =============================================================================
# servicios/dj_privado/stems_prefetch.py
#
# Pre-fetch agresivo de stems "sin voz" para que HARMONIC_MIX tenga material
# disponible antes de que llegue el momento de la transición.
#
# Estrategia:
#   - Cuando se carga una sesión, las primeras N pistas se encolan en el
#     subsistema karaoke (que ya tiene worker, cola persistente y retry).
#   - El encolar es BARATO (un INSERT en SQLite por pista). El procesamiento
#     real ocurre en el worker karaoke; aquí no bloqueamos.
#   - Si una pista ya tiene karaoke procesado o ya está en cola, se ignora
#     (idempotente, sin spamear jobs).
#   - El motor consulta el StemsProvider cuando va a iniciar la transición
#     y degrada a otra técnica si el stem aún no está listo.
#
# Esta capa NO espera resultados ni reporta progreso al reproductor: el
# objetivo es maximizar la probabilidad de que el stem ESTÉ listo cuando se
# necesita, sin acoplar el reproductor al ciclo de vida de Demucs.
# =============================================================================

from __future__ import annotations

import threading
from typing import Iterable, Optional

from infra.logger import obtener_logger
from servicios.dj_privado.hardware_profile import (
    PerfilHardware,
    perfil_efectivo,
)

logger = obtener_logger(__name__)

# Cuántas pistas pre-encolamos al cargar la sesión. Más de eso satura la
# cola karaoke y compite con jobs del usuario. 3-5 es suficiente porque la
# transición ocurre cada ~3-5 min y el worker procesa una pista en ~30-90s.
PISTAS_INICIALES_PRE_FETCH = 5


def pre_fetch_inicial(
    pista_ids: Iterable[int],
    *,
    n_pistas: int = PISTAS_INICIALES_PRE_FETCH,
    perfil: Optional[PerfilHardware] = None,
) -> int:
    """Encola las primeras `n_pistas` para procesamiento de stems en background.

    Devuelve cuántos jobs nuevos se crearon (puede ser 0 si todas ya tenían
    stems listos o jobs en cola).

    Se ejecuta de forma síncrona pero ligera (solo INSERTs en SQLite); no
    bloquea la reproducción. Si quieres más aislamiento, llámalo dentro de
    un threading.Thread daemon.

    Si el perfil hardware es LOW, no se pre-fetcha nada: en LOW el motor
    nunca selecciona HARMONIC_MIX, así que generar stems sería desperdicio.
    """
    perfil_actual = perfil or perfil_efectivo()
    if perfil_actual == PerfilHardware.LOW:
        logger.info("pre_fetch_inicial: perfil LOW, no se encola nada")
        return 0
    seleccion: list[int] = []
    for pid in pista_ids:
        if pid is None:
            continue
        try:
            seleccion.append(int(pid))
        except (TypeError, ValueError):
            continue
        if len(seleccion) >= n_pistas:
            break
    if not seleccion:
        return 0
    try:
        from servicios.karaoke import jobs_repo as karaoke_jobs
    except Exception as exc:
        logger.info("pre_fetch_inicial: karaoke no disponible (%s)", exc)
        return 0
    try:
        creados = karaoke_jobs.encolar_muchas(seleccion)
    except Exception:
        logger.exception("pre_fetch_inicial: encolar_muchas falló")
        return 0
    if creados > 0:
        logger.info(
            "pre_fetch_inicial: encoladas %d pistas (de %d candidatas) para stems",
            creados, len(seleccion),
        )
    return creados


def pre_fetch_inicial_async(
    pista_ids: Iterable[int],
    *,
    n_pistas: int = PISTAS_INICIALES_PRE_FETCH,
    perfil: Optional[PerfilHardware] = None,
) -> threading.Thread:
    """Variante en hilo daemon. Devuelve el thread (por si quieres .join()).

    Es la forma recomendada de llamarlo desde el reproductor: aunque
    `pre_fetch_inicial` es barato, el aislamiento en thread evita cualquier
    latencia perceptible al abrir la sesión.
    """
    ids = list(pista_ids)

    def _run() -> None:
        try:
            pre_fetch_inicial(ids, n_pistas=n_pistas, perfil=perfil)
        except Exception:
            logger.exception("pre_fetch_inicial_async falló")

    t = threading.Thread(target=_run, daemon=True, name="dj_stems_prefetch")
    t.start()
    return t
