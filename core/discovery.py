# =============================================================================
# core/discovery.py
#
# Descubrimiento de archivos de audio soportados. Recorre recursivamente la carpeta de entrada
# y construye la lista de candidatos a procesar. Aplica filtros de extension,
# tamano minimo y tamano maximo antes de entregar archivos al pipeline.
# No modifica ningun archivo durante su operacion.
# =============================================================================

from pathlib import Path
from typing import Generator

from config.settings import (
    SUPPORTED_EXTENSIONS,
    MIN_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_BYTES,
)
from domain.models import ArchivoAudio
from infra.logger import obtener_logger
from utils.text import validar_path_seguro

_log = obtener_logger("discovery")

# Carpetas que se excluyen automaticamente del recorrido para evitar que
# el programa procese sus propios archivos de salida si la entrada apunta
# a un directorio padre de la biblioteca.
_CARPETAS_EXCLUIDAS = {
    ".tmp", ".cache",
    "quarantine", "cuarentena",
    "review", "revision",
    "library", "biblioteca",
    "processed", "procesados",
    "logs",
}


# =============================================================================
# DESCUBRIMIENTO
# =============================================================================

def descubrir_archivos(directorio: Path) -> list[ArchivoAudio]:
    """
    Recorre el directorio recursivamente y retorna lista de ArchivoAudio
    candidatos listos para validacion tecnica.

    Args:
        directorio: Ruta raiz desde donde iniciar el recorrido.

    Returns:
        Lista ordenada alfabeticamente de ArchivoAudio.

    Raises:
        FileNotFoundError: Si el directorio no existe.
        NotADirectoryError: Si la ruta no es un directorio.
    """
    if not directorio.exists():
        raise FileNotFoundError(
            f"Directorio de entrada no encontrado: {directorio}"
        )

    if not directorio.is_dir():
        raise NotADirectoryError(
            f"La ruta indicada no es un directorio: {directorio}"
        )

    # Validar que la ruta no contiene path traversal (..) o symlinks peligrosos
    es_valida, msg_error = validar_path_seguro(str(directorio))
    if not es_valida:
        raise ValueError(
            f"Ruta de entrada contiene referencias potencialmente peligrosas: {msg_error}"
        )

    _log.info(f"Iniciando descubrimiento en: {directorio}")

    candidatos:          list[ArchivoAudio] = []
    total_inspeccionados = 0
    rechazados_extension = 0
    rechazados_tamano    = 0

    for ruta in _recorrer_recursivo(directorio):
        total_inspeccionados += 1

        # Validar que la ruta no contiene path traversal (..) o symlinks peligrosos
        es_valida, msg_error = validar_path_seguro(str(ruta), base_permitida=str(directorio))
        if not es_valida:
            _log.warning(f"Ruta rechazada por validacion de seguridad ({msg_error}): {ruta.name}")
            rechazados_tamano += 1
            continue

        if ruta.suffix.lower() not in SUPPORTED_EXTENSIONS:
            rechazados_extension += 1
            _log.debug(f"Extension no soportada: {ruta.name}")
            continue

        try:
            tamano = ruta.stat().st_size
        except OSError as e:
            _log.warning(f"No se pudo obtener tamano de {ruta.name}: {e}")
            rechazados_tamano += 1
            continue

        if tamano < MIN_FILE_SIZE_BYTES:
            _log.warning(
                f"Archivo demasiado pequeno ({tamano} bytes), posible truncado: {ruta.name}"
            )
            rechazados_tamano += 1
            continue

        if tamano > MAX_FILE_SIZE_BYTES:
            _log.warning(
                f"Archivo excede tamano maximo ({tamano} bytes): {ruta.name}"
            )
            rechazados_tamano += 1
            continue

        candidatos.append(ArchivoAudio(ruta_original=ruta, tamano_bytes=tamano))
        _log.debug(f"Candidato: {ruta.name} ({tamano:,} bytes)")

    # Ordenar de forma determinista para que el pipeline sea reproducible
    candidatos.sort(key=lambda a: str(a.ruta_original).lower())

    _log.info(
        f"Descubrimiento: {len(candidatos)} candidatos de "
        f"{total_inspeccionados} inspeccionados "
        f"(excluidos por extension: {rechazados_extension}, "
        f"por tamano: {rechazados_tamano})"
    )

    return candidatos


def _recorrer_recursivo(directorio: Path) -> Generator[Path, None, None]:
    """
    Generador que recorre el arbol de directorios omitiendo carpetas del sistema
    y carpetas de salida del propio tagger.
    """
    try:
        for entrada in sorted(directorio.iterdir()):
            if entrada.is_dir():
                if (entrada.name.startswith(".")
                        or entrada.name.lower() in _CARPETAS_EXCLUIDAS):
                    _log.debug(f"Carpeta excluida: {entrada.name}")
                    continue
                yield from _recorrer_recursivo(entrada)
            elif entrada.is_file():
                yield entrada
    except PermissionError as e:
        _log.warning(f"Sin permiso para leer directorio: {directorio} — {e}")
    except OSError as e:
        _log.warning(f"Error al recorrer directorio: {directorio} — {e}")
