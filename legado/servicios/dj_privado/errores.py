# =============================================================================
# servicios/dj_privado/errores.py
#
# Jerarquia de excepciones del subsistema DJ Privado.
#
# Todas derivan de DjPrivadoError para que el caller pueda atrapar el
# subsistema completo con un solo `except DjPrivadoError`. Las subclases
# permiten distinguir condiciones de negocio (pool vacio, sesion inexistente)
# de errores de programacion (configuracion invalida).
#
# Contrato:
#   - Ninguna excepcion de este modulo contiene logica; son data classes de
#     error con un mensaje descriptivo como primer argumento.
#   - Los componentes internos (scheduler, constructor, persistencia) las
#     lanzan; el servicio (servicio.py) es quien las propaga a la UI/worker.
#   - La UI/worker nunca deberia ver excepciones Python nativas del DJ:
#     todas deben convertirse en estas antes de cruzar el boundary.
# =============================================================================

from __future__ import annotations


class DjPrivadoError(Exception):
    """Error base del subsistema DJ Privado.

    Capturar esta clase atrapa cualquier fallo originado en el subsistema.
    """


class SesionNoEncontradaError(DjPrivadoError):
    """Se referencio una sesion que no existe en la BD.

    Lanzada por `persistencia.obtener_sesion` y por `servicio.cargar_sesion`.
    El caller debe verificar que el id proviene de una fuente confiable antes
    de llamar; en la UI esto implica que la sesion fue eliminada externamente.
    """


class PoolVacioError(DjPrivadoError):
    """No hay pistas candidatas para construir la sesion.

    Causas tipicas:
      - Biblioteca vacia (ningun archivo en estado 'biblioteca').
      - Filtros del intent eliminan todas las candidatas (exclusiones agresivas
        sobre una biblioteca pequena).
      - Pool con features pero todos con status de error en audio_features.

    El servicio marca la sesion como 'error' en BD antes de lanzar esta excepcion
    para que no quede en estado 'construyendo' indefinidamente.
    """


class IntentInvalidoError(DjPrivadoError):
    """El intent es semanticamente inviable.

    Se reserva para casos donde los ejes del intent se anulan mutuamente de forma
    total (ej. `energy=+1.0` y `energy=-1.0` con exclusiones que eliminan todo
    el rango intermedio). En la practica, el parser de intent resuelve
    contradicciones antes de llegar aqui; esta excepcion es una guarda de ultimo
    recurso para el scheduler.
    """


class ConfiguracionInvalidaError(DjPrivadoError):
    """Parametros del constructor o servicio fuera de rango aceptable.

    Ejemplos: duracion_minutos=0, duracion_minutos=9999, semilla invalida.
    El servicio valida estos parametros en la entrada publica (`iniciar_sesion`)
    para que el error sea claro antes de escribir nada en BD.
    """
