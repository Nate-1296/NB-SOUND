# =============================================================================
# servicios/dj_privado/__init__.py
#
# API publica del subsistema DJ Privado.
#
# Punto de entrada principal: DjPrivadoService. La UI/modelos QML solo
# deberian importar de aqui o, a lo sumo, de errores/intencion (dataclasses
# inmutables seguras de exponer).
# =============================================================================

from servicios.dj_privado.errores import (
    ConfiguracionInvalidaError,
    DjPrivadoError,
    IntentInvalidoError,
    PoolVacioError,
    SesionNoEncontradaError,
)
from servicios.dj_privado.intencion import IntentMusical, parsear_intent
from servicios.dj_privado.ontologia import (
    CURVAS_ENERGIA,
    EJES,
    ESTILOS_TRANSICION,
    buscar_conceptos,
    todos_los_conceptos,
)
from servicios.dj_privado.persistencia import (
    PistaCandidata,
    SesionDjRow,
    sesiones_recientes,
)
from servicios.dj_privado.constructor import (
    BloqueConstruido,
    OpcionesConstructor,
)
from servicios.dj_privado.scheduler import PistaSesionPlanificada
from servicios.dj_privado.transiciones import TransicionPlan
from servicios.dj_privado.servicio import (
    DjPrivadoService,
    MOTOR_VERSION,
    SesionActiva,
)

__all__ = [
    # Servicio principal
    "DjPrivadoService",
    "SesionActiva",
    "MOTOR_VERSION",
    # Intent / ontologia
    "IntentMusical",
    "parsear_intent",
    "buscar_conceptos",
    "todos_los_conceptos",
    "EJES",
    "CURVAS_ENERGIA",
    "ESTILOS_TRANSICION",
    # Estructuras
    "PistaCandidata",
    "PistaSesionPlanificada",
    "BloqueConstruido",
    "OpcionesConstructor",
    "TransicionPlan",
    "SesionDjRow",
    "sesiones_recientes",
    # Errores
    "DjPrivadoError",
    "PoolVacioError",
    "SesionNoEncontradaError",
    "IntentInvalidoError",
    "ConfiguracionInvalidaError",
]
