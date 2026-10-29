# =============================================================================
# infra/logger.py
#
# Infraestructura de logging del tagger. Configura dos canales paralelos:
# uno hacia terminal (legible, con colores ANSI) y otro hacia disco
# (detallado para auditoria). Adicionalmente mantiene un canal de eventos
# estructurados en formato JSONL para analisis programatico posterior.
#
# El logging es transversal a todo el sistema. Este modulo se inicializa
# una sola vez al arranque; luego cada modulo obtiene su logger por nombre.
# =============================================================================

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _eprint(*args, **kwargs) -> None:
    """print seguro a stderr; no-op cuando sys.stderr es None (Windows GUI)."""
    if sys.stderr is not None:
        print(*args, file=sys.stderr, **kwargs)

from config.settings import (
    LOG_LEVEL_CONSOLE,
    LOG_LEVEL_FILE,
    LOG_FILE_NAME,
    LOG_EVENTS_FILE_NAME,
)

# =============================================================================
# AJUSTES INTERNOS
# =============================================================================

_FORMATO_CONSOLA = "%(levelname)-8s %(message)s"
_FORMATO_ARCHIVO = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
_FECHA_ARCHIVO   = "%Y-%m-%d %H:%M:%S"

LOGGER_RAIZ = "nb_sound"

_eventos_fh: Optional[object] = None


# =============================================================================
# COLORES ANSI
# =============================================================================

class _Color:
    RESET   = "\033[0m"
    ROJO    = "\033[91m"
    VERDE   = "\033[92m"
    AMARILLO= "\033[93m"
    AZUL    = "\033[94m"
    CIAN    = "\033[96m"
    GRIS    = "\033[90m"
    NEGRITA = "\033[1m"


class _FormatterColor(logging.Formatter):
    """Formatter que agrega color ANSI segun nivel para salida en terminal."""

    _COLORES = {
        logging.DEBUG:    _Color.GRIS,
        logging.INFO:     _Color.AZUL,
        logging.WARNING:  _Color.AMARILLO,
        logging.ERROR:    _Color.ROJO,
        logging.CRITICAL: _Color.ROJO + _Color.NEGRITA,
    }

    def format(self, record: logging.LogRecord) -> str:
        mensaje = super().format(record)
        if os.getenv("NO_COLOR") is not None:
            return mensaje
        color = getattr(record, "terminal_color", None) or self._COLORES.get(record.levelno, _Color.RESET)
        return f"{color}{mensaje}{_Color.RESET}"


# =============================================================================
# INICIALIZACION
# =============================================================================

def inicializar_logging(directorio_logs: Path) -> None:
    """
    Configura el sistema de logging global.

    Comportamiento:
      * Si NO hay handlers todavía → los crea.
      * Si HAY handlers y apuntan al mismo directorio → no hace nada.
      * Si HAY handlers pero apuntan a OTRO directorio → cierra los
        actuales y abre nuevos en ``directorio_logs``. Esto evita el
        caso real en runtime UI: el ``PipelineCatalogacion`` cierra el
        logging al terminar una importación; cuando el usuario hace
        una operación posterior (karaoke, deep, configurar otra ruta)
        no quedaba forma de re-escribir a disco y los errores se
        perdían.

    Idempotente para tests: dos llamadas con el mismo dir no duplican
    handlers.
    """
    global _eventos_fh

    directorio_logs.mkdir(parents=True, exist_ok=True)

    logger_raiz = logging.getLogger(LOGGER_RAIZ)
    logger_raiz.setLevel(logging.DEBUG)

    ruta_log_objetivo = (directorio_logs / LOG_FILE_NAME).resolve()
    if logger_raiz.handlers:
        # Detectar si el handler actual apunta al mismo archivo. Si sí,
        # no tocamos nada (idempotente). Si no, cerramos los handlers
        # actuales para que abajo abramos en el dir correcto.
        for h in logger_raiz.handlers:
            stream = getattr(h, "_nb_sound_stream", None) or getattr(h, "stream", None)
            ruta_actual = getattr(stream, "name", None)
            if ruta_actual:
                try:
                    if Path(str(ruta_actual)).resolve() == ruta_log_objetivo:
                        return
                except Exception:
                    pass
        # Apunta a otro directorio → cerrar para re-inicializar limpio.
        cerrar_logging()

    # Handler de consola — colorizado, nivel configurable.
    # sys.stdout es None en bundles Windows con console=False; en ese caso
    # se omite el handler de consola (los logs siguen yendo a disco).
    if sys.stdout is not None:
        handler_consola = logging.StreamHandler(sys.stdout)
        handler_consola.setLevel(getattr(logging, LOG_LEVEL_CONSOLE))
        handler_consola.setFormatter(_FormatterColor(_FORMATO_CONSOLA))
        logger_raiz.addHandler(handler_consola)

    # Handler de archivo — detallado para auditoria.
    # IMPORTANTE: el FileHandler de stdlib usa buffering por defecto. Si
    # la app crashea o se cierra abruptamente, las últimas líneas no
    # llegan a disco. Para diagnóstico realista (caso típico: el usuario
    # reporta "se cerró sin razón y los logs están vacíos") abrimos el
    # archivo en modo line-buffered: cada `\n` flushea al SO. Adjuntamos
    # el stream al handler para que `cerrar_logging` lo cierre.
    ruta_log = directorio_logs / LOG_FILE_NAME
    _archivo_stream = open(ruta_log, "a", encoding="utf-8", buffering=1)
    handler_archivo = logging.StreamHandler(_archivo_stream)
    handler_archivo.setLevel(getattr(logging, LOG_LEVEL_FILE))
    handler_archivo.setFormatter(
        logging.Formatter(_FORMATO_ARCHIVO, datefmt=_FECHA_ARCHIVO)
    )
    handler_archivo._nb_sound_stream = _archivo_stream  # type: ignore[attr-defined]
    logger_raiz.addHandler(handler_archivo)

    # Canal de eventos estructurados (JSONL) — para analisis posterior
    ruta_eventos = directorio_logs / LOG_EVENTS_FILE_NAME
    _eventos_fh  = open(ruta_eventos, "a", encoding="utf-8", buffering=1)

    logger_raiz.info(
        f"Logging v3 inicializado. "
        f"Log: {ruta_log} | Eventos: {ruta_eventos}"
    )


def cerrar_logging() -> None:
    """Cierra los handlers abiertos. Llamar al finalizar el programa."""
    global _eventos_fh, _logger_sistema
    if _eventos_fh is not None:
        try:
            _eventos_fh.close()
        except (OSError, IOError) as e:
            # El logging nunca debe colapsar el programa, pero sí registramos el error
            import sys
            _eprint(f"[WARN] Error cerrando archivo de eventos: {e}")
        except Exception as e:
            # Captura inesperada — log pero no falla
            import sys
            _eprint(f"[WARN] Error inesperado cerrando eventos: {type(e).__name__}: {e}")
        finally:
            _eventos_fh = None

    logger_raiz = logging.getLogger(LOGGER_RAIZ)
    for handler in list(logger_raiz.handlers):
        try:
            handler.flush()
            handler.close()
        except (OSError, IOError) as e:
            import sys
            _eprint(f"[WARN] Error flushing handler {handler}: {e}")
        except Exception as e:
            import sys
            _eprint(f"[WARN] Error inesperado en handler {handler}: {type(e).__name__}: {e}")
        finally:
            try:
                logger_raiz.removeHandler(handler)
            except Exception as e:
                import sys
                _eprint(f"[WARN] No se pudo remover handler {handler}: {type(e).__name__}: {e}")

    _logger_sistema = None


# =============================================================================
# OBTENCION DE LOGGERS POR MODULO
# =============================================================================

def obtener_logger(nombre_modulo: str) -> logging.Logger:
    """
    Retorna un logger hijo del logger raiz del proyecto.
    Convencion: 'nb_sound.<nombre_modulo>'
    """
    return logging.getLogger(f"{LOGGER_RAIZ}.{nombre_modulo}")


# =============================================================================
# EVENTOS ESTRUCTURADOS (JSONL)
# =============================================================================

def registrar_evento(
    tipo: str,
    archivo: Optional[str] = None,
    datos: Optional[dict] = None,
) -> None:
    """
    Escribe un evento estructurado en el archivo JSONL de auditoria.

    Args:
        tipo:    Identificador del tipo de evento (ej: 'archivo_aceptado')
        archivo: Nombre del archivo involucrado (opcional)
        datos:   Diccionario con informacion adicional del evento

    Nota: El logging nunca debe colapsar el programa principal. Se intenta escribir
    el evento pero si falla, se registra un stderr y continúa normalmente.
    """
    if _eventos_fh is None:
        return

    evento: dict = {
        "ts":   datetime.now(timezone.utc).isoformat(),
        "tipo": tipo,
    }
    if archivo:
        evento["archivo"] = archivo
    if datos:
        evento.update(datos)

    try:
        _eventos_fh.write(json.dumps(evento, ensure_ascii=False) + "\n")
        # Intentar flush para asegurar que se escriba (pero no crítico si falla)
        try:
            _eventos_fh.flush()
        except (OSError, IOError):
            pass  # El flush es best-effort; el buffer se vacía al cerrar
    except (OSError, IOError) as e:
        # El archivo de eventos no está disponible — registrar y continuar
        import sys
        _eprint(f"[WARN] No se pudo escribir evento JSONL (tipo={tipo}): {e}")
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        # Error en serialización JSON — evento inválido
        import sys
        _eprint(f"[WARN] Evento no serializable a JSON (tipo={tipo}): {e}")
    except Exception as e:
        # Captura defensiva de errores inesperados
        import sys
        _eprint(f"[WARN] Error inesperado en registrar_evento: {type(e).__name__}: {e}")


# =============================================================================
# HELPERS DE LOGGING COMUNES
# =============================================================================

_logger_sistema: Optional[logging.Logger] = None


def _obtener_logger_sistema() -> logging.Logger:
    global _logger_sistema
    if _logger_sistema is None:
        _logger_sistema = obtener_logger("sistema")
    return _logger_sistema


def log_inicio_archivo(nombre: str) -> None:
    _obtener_logger_sistema().debug(f"[>] Iniciando: {nombre}")
    registrar_evento("inicio_archivo", archivo=nombre)


def log_decision(
    nombre: str, decision: str, puntaje: float, mensaje: str
) -> None:
    niveles = {
        "aceptado": logging.INFO,
        "aceptado_provisional": logging.INFO,
        "revision": logging.WARNING,
        "cuarentena": logging.ERROR,
        "error": logging.ERROR,
        "duplicado_exacto": logging.INFO,
        "duplicado_semantico": logging.INFO,
        "duplicado_mejorable": logging.INFO,
        "omitido": logging.INFO,
    }
    colores = {
        "aceptado": _Color.VERDE,
        "aceptado_provisional": _Color.CIAN,
        "revision": _Color.AMARILLO,
        "cuarentena": _Color.ROJO,
        "error": _Color.ROJO,
        "duplicado_exacto": _Color.CIAN,
        "duplicado_semantico": _Color.CIAN,
        "duplicado_mejorable": _Color.CIAN,
        "omitido": _Color.GRIS,
    }
    logger = _obtener_logger_sistema()
    logger.log(
        niveles.get(decision, logging.INFO),
        f"[{decision.upper():22}] {nombre} | score={puntaje:.3f} | {mensaje}",
        extra={"terminal_color": colores.get(decision, _Color.AZUL)},
    )
    registrar_evento(
        f"decision_{decision}",
        archivo=nombre,
        datos={"puntaje": puntaje, "mensaje": mensaje},
    )


def log_error_archivo(nombre: str, etapa: str, error: str) -> None:
    _obtener_logger_sistema().error(
        f"[ERROR] {nombre} | etapa={etapa} | {error}"
    )
    registrar_evento(
        "error_archivo",
        archivo=nombre,
        datos={"etapa": etapa, "error": error},
    )
