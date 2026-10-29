# =============================================================================
# servicios/karaoke/rutas.py
#
# Resolucion centralizada de rutas para el subsistema karaoke.
#
# Layout:
#   <cache_dir>/karaoke/
#     models/        # checkpoints de demucs (TORCH_HOME)
#     stems_tmp/     # temporales por job (se limpian siempre)
#     instrumentales/  # salidas finales MP3
# =============================================================================

from __future__ import annotations

import hashlib
from pathlib import Path


def directorio_karaoke(cache_base: Path) -> Path:
    raiz = Path(cache_base) / "karaoke"
    raiz.mkdir(parents=True, exist_ok=True)
    return raiz


def directorio_modelos(cache_base: Path) -> Path:
    d = directorio_karaoke(cache_base) / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def directorio_temporales(cache_base: Path) -> Path:
    d = directorio_karaoke(cache_base) / "stems_tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def directorio_instrumentales(cache_base: Path) -> Path:
    d = directorio_karaoke(cache_base) / "instrumentales"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ruta_instrumental_para_pista(cache_base: Path, pista_id: int, ruta_audio: str) -> Path:
    """Genera una ruta estable para el instrumental de una pista.

    El hash de la ruta de origen sirve para que dos pistas distintas que
    apunten al mismo archivo (caso raro) compartan caja, y para invalidar
    automaticamente el cache si la ruta cambia.
    """
    hasher = hashlib.sha1(str(ruta_audio).encode("utf-8")).hexdigest()[:12]
    return directorio_instrumentales(cache_base) / f"kar_{int(pista_id)}_{hasher}.mp3"


def directorio_temporal_para_job(cache_base: Path, job_id: int) -> Path:
    """Carpeta exclusiva para los temporales de un job (WAV intermedios)."""
    d = directorio_temporales(cache_base) / f"job_{int(job_id)}"
    d.mkdir(parents=True, exist_ok=True)
    return d
