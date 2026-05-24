# =============================================================================
# servicios/explorador_ciego
#
# Modulo del "Explorador Ciego" (Fase 12).
#
# Filosofia: experiencia ludica de redescubrimiento sobre la biblioteca local.
# NO depende de internet, APIs externas ni telemetria. Todo se resuelve con
# pistas, historial, metadatos y portadas que ya viven en la BD del usuario.
#
# Estructura:
#   - modelos.py      : dataclasses + enums (Modo, EstadoReto, Reto)
#   - selectores.py   : reglas de seleccion de pistas por modo
#   - servicio.py     : orquestador (iniciar ronda, revelar, resolver, etc.)
# =============================================================================

from .modelos import (
    ModoExplorador,
    EstadoReto,
    NivelRevelacion,
    Reto,
    ResumenRonda,
)
from .servicio import ExploradorCiegoService
from .hints import (
    detectar_alfabeto,
    generar_hints,
    normalizar_para_comparar,
    requiere_escritura,
    validar_intento,
)

__all__ = [
    "ModoExplorador",
    "EstadoReto",
    "NivelRevelacion",
    "Reto",
    "ResumenRonda",
    "ExploradorCiegoService",
    "detectar_alfabeto",
    "generar_hints",
    "normalizar_para_comparar",
    "requiere_escritura",
    "validar_intento",
]
