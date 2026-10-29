# =============================================================================
# infra/processed.py
#
# Gestion del archivado de archivos de entrada ya procesados.
#
# Objetivo: evitar que la carpeta de entrada vuelva a importar archivos que ya
# pasaron por el pipeline en ejecuciones anteriores.
# =============================================================================

import shutil
from pathlib import Path
from typing import Optional

from config import settings
from domain.models import DecisionTipo
from infra.logger import obtener_logger

_log = obtener_logger("processed")


class GestorProcesados:
    """
    Mueve archivos fuente procesados fuera de la carpeta de entrada.

    Cada archivo se mueve a un subdirectorio con el nombre del valor del
    Enum DecisionTipo (p.ej. "aceptado", "cuarentena"). Esto evita que
    en la siguiente ejecución del pipeline el mismo archivo sea re-descubierto
    y procesado de nuevo.

    Uso:
        gestor = GestorProcesados(dir_procesados)
        gestor.archivar(ruta_mp3, DecisionTipo.ACEPTADO)

    Contratos:
        - directorio_procesados debe ser un path absoluto ya verificado.
        - No hace nada (retorna None) en modo DRY_RUN.
        - No lanza excepciones: los errores de sistema de archivos se loguean
          y retornan None para que el pipeline continúe.
        - Thread-safety: no tiene estado mutable compartido, cada llamada
          opera en su propio Path.
    """

    def __init__(self, directorio_procesados: Optional[Path]) -> None:
        if directorio_procesados is None:
            raise ValueError(
                "GestorProcesados requiere directorio_procesados. "
                "Configura USER_PROCESSED_DIR en settings.py o usa --processed."
            )
        self._dir_procesados = directorio_procesados

    def archivar(self, ruta_origen: Path, tipo_decision: DecisionTipo) -> Optional[Path]:
        """
        Archiva el archivo original en la subcarpeta correspondiente al tipo de decisión.

        La subcarpeta se crea si no existe. Si ya hay un archivo con el mismo
        nombre, se resuelve el conflicto añadiendo un sufijo numérico (_2, _3...).

        Retorna la ruta final cuando el movimiento se completa.
        Retorna None en DRY_RUN, si el origen ya no existe, o si ocurre un error.
        """
        if settings.DRY_RUN:
            _log.info(f"[DRY_RUN] Procesados ({tipo_decision.value}): {ruta_origen.name}")
            return None

        if not ruta_origen.exists():
            _log.debug(f"No se archiva porque el origen ya no existe: {ruta_origen}")
            return None

        carpeta_destino = self._dir_procesados / tipo_decision.value
        carpeta_destino.mkdir(parents=True, exist_ok=True)

        ruta_destino = self._resolver_conflicto(carpeta_destino / ruta_origen.name)

        try:
            shutil.move(str(ruta_origen), str(ruta_destino))
            _log.debug(f"Archivado en procesados: {ruta_origen.name} -> {ruta_destino}")
            return ruta_destino
        except OSError as e:
            _log.error(f"No se pudo archivar {ruta_origen.name} en procesados: {e}")
            return None

    @staticmethod
    def _resolver_conflicto(ruta_base: Path) -> Path:
        """
        Retorna ruta_base si no existe, o un nombre alternativo con sufijo
        numérico (_2, _3, ...) hasta un máximo de 9999 para evitar loops infinitos.
        """
        if not ruta_base.exists():
            return ruta_base

        carpeta = ruta_base.parent
        stem = ruta_base.stem
        suffix = ruta_base.suffix

        contador = 2
        ruta = carpeta / f"{stem}_{contador}{suffix}"
        while ruta.exists() and contador < 10_000:
            contador += 1
            ruta = carpeta / f"{stem}_{contador}{suffix}"
        return ruta
