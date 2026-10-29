# =============================================================================
# infra/binarios.py
#
# Resolucion de binarios externos (ffmpeg, fpcalc) con prioridad al binario
# embebido en el bundle distribuido. Permite que las builds oficiales
# funcionen sin que el usuario instale dependencias del sistema para los
# componentes basicos (transcodificacion y fingerprinting acustico).
#
# Orden de resolucion:
#   1. Binario embebido dentro de PyInstaller (`sys._MEIPASS/bin/<nombre>`).
#   2. Binario adyacente al ejecutable congelado (`sys.executable/bin/<nombre>`).
#   3. Binario disponible en el PATH del sistema (`shutil.which`).
#
# El sufijo ".exe" se aplica automaticamente en Windows. El llamador siempre
# pasa el nombre desnudo ("ffmpeg", "fpcalc"); la conversion la hace este
# modulo.
# =============================================================================

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Optional


def _con_sufijo_windows(nombre: str) -> str:
    """Agrega ".exe" en Windows, deja el nombre intacto en POSIX."""
    if sys.platform.startswith("win") and not nombre.lower().endswith(".exe"):
        return f"{nombre}.exe"
    return nombre


def _candidato_meipass(nombre_archivo: str) -> Optional[Path]:
    """Ruta dentro del temp dir extraido por PyInstaller en modo onefile."""
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return None
    return Path(meipass) / "bin" / nombre_archivo


def _candidato_adyacente(nombre_archivo: str) -> Optional[Path]:
    """Ruta junto al ejecutable congelado en modo onedir/app bundle."""
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve().parent / "bin" / nombre_archivo


def _asegurar_ejecutable(ruta: Path) -> None:
    """Garantiza que el archivo tiene permiso de ejecucion en sistemas POSIX.

    PyInstaller incluye los ejecutables externos como datas y puede perder
    el bit +x en algunos entornos. Se establece solo si hace falta; en
    Windows es un no-op (los permisos de ejecucion no se manejan igual).
    """
    if sys.platform.startswith("win"):
        return
    try:
        modo = os.stat(ruta).st_mode
        if not (modo & stat.S_IXUSR):
            os.chmod(ruta, modo | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass


def resolver_bin(nombre: str) -> Optional[str]:
    """Resuelve la ruta absoluta a un binario externo.

    Devuelve la ruta como string si encuentra el binario, o None si no
    esta disponible ni en el bundle ni en el PATH del sistema. El llamador
    es responsable de manejar el caso None (mostrar mensaje al usuario,
    degradar graciosamente, etc.).

    Args:
        nombre: nombre canonico del binario sin extension ("ffmpeg", "fpcalc").

    Returns:
        Ruta absoluta como string, o None.
    """
    nombre_archivo = _con_sufijo_windows(nombre)

    for candidato in (_candidato_meipass(nombre_archivo),
                      _candidato_adyacente(nombre_archivo)):
        if candidato is not None and candidato.exists():
            _asegurar_ejecutable(candidato)
            return str(candidato)

    return shutil.which(nombre)


def disponible(nombre: str) -> bool:
    """Booleano de conveniencia: ``True`` si ``resolver_bin`` encuentra algo."""
    return resolver_bin(nombre) is not None
