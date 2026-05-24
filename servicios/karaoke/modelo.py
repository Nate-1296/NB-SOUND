# =============================================================================
# servicios/karaoke/modelo.py
#
# Carga del modelo Demucs. El modelo `htdemucs` (4-stems, ~80 MB) es la
# eleccion por defecto: estado del arte, CPU-friendly, MIT-compatible.
#
# La primera descarga se hace contra el repositorio oficial de torch hub.
# Configuramos TORCH_HOME apuntando al cache del proyecto para que los
# pesos queden bajo control de la app y no en ~/.cache/torch.
# =============================================================================

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

from infra.logger import obtener_logger

from .errores import ModeloFaltanteError

_log = obtener_logger("servicios.karaoke.modelo")

# Modelo por defecto. Si en el futuro queremos cambiarlo, basta con esta cte.
MODELO_DEFAULT = "htdemucs"

_lock = threading.Lock()
_cache_modelos: dict[str, object] = {}


def _configurar_torch_home(directorio_modelos: Path) -> None:
    """Apunta TORCH_HOME al cache del proyecto. Idempotente."""
    actual = os.environ.get("TORCH_HOME", "")
    deseado = str(directorio_modelos.resolve())
    if actual != deseado:
        os.environ["TORCH_HOME"] = deseado
        _log.info("TORCH_HOME=%s", deseado)


def cargar_modelo(directorio_modelos: Path, nombre: str = MODELO_DEFAULT):
    """Devuelve el modelo Demucs cargado. Cachea en memoria por proceso.

    La primera invocacion puede descargar pesos (~80 MB para htdemucs).
    Raises:
        ModeloFaltanteError: si el modelo no se puede cargar (sin red, hash
            corrupto, nombre desconocido, etc.).
    """
    import traceback
    with _lock:
        if nombre in _cache_modelos:
            return _cache_modelos[nombre]

        _configurar_torch_home(directorio_modelos)
        _log.info(
            "cargar_modelo: nombre=%s TORCH_HOME=%s checkpoints=%s",
            nombre, os.environ.get("TORCH_HOME"),
            sorted(
                p.name for p in (directorio_modelos / "hub" / "checkpoints").iterdir()
            ) if (directorio_modelos / "hub" / "checkpoints").is_dir() else [],
        )
        # Etapa 1: import demucs. Si hay ABI clash con torch del bundle,
        # SIGSEGV puede tumbar el proceso (no Python exception). El log
        # previo nos deja saber al menos por dónde íbamos.
        try:
            from demucs.pretrained import get_model  # type: ignore
        except Exception as exc:
            _log.error(
                "cargar_modelo: import demucs falló: %s\n%s",
                exc, traceback.format_exc()[-1500:],
            )
            raise ModeloFaltanteError(
                "Demucs no se pudo importar (¿instalacion incompleta?).",
                detalle=f"{exc}\n{traceback.format_exc()[-800:]}",
            ) from exc
        _log.info("cargar_modelo: demucs importado OK")

        # Etapa 2: cargar pesos. Aquí puede fallar por sha mismatch,
        # ausencia de yaml de configuración, o torch.load incompatible.
        try:
            modelo = get_model(nombre)
        except Exception as exc:
            _log.error(
                "cargar_modelo: get_model(%r) falló: %s\n%s",
                nombre, exc, traceback.format_exc()[-1500:],
            )
            raise ModeloFaltanteError(
                f"No se pudo cargar el modelo '{nombre}'.",
                detalle=f"{exc}\n{traceback.format_exc()[-800:]}",
            ) from exc

        modelo.eval()
        _cache_modelos[nombre] = modelo
        _log.info("cargar_modelo: modelo %s cargado y en modo eval", nombre)
        return modelo


def descargar_cache() -> None:
    """Libera referencias a modelos cargados (para pruebas o cierre limpio)."""
    with _lock:
        _cache_modelos.clear()


def modelo_disponible_en_disco(directorio_modelos: Path, nombre: str = MODELO_DEFAULT) -> bool:
    """Heuristica barata: comprueba si hay archivos .th/.zip en hub/checkpoints.

    No descarga ni instancia el modelo. Util para diagnostico/UI.
    """
    base = Path(directorio_modelos) / "hub" / "checkpoints"
    if not base.exists():
        return False
    # Demucs guarda con prefijo. htdemucs => htdemucs-XXXX.th
    patron = nombre.split(":", 1)[0]
    return any(p.name.startswith(patron) for p in base.iterdir() if p.is_file())


def fuentes_modelo(modelo) -> Optional[list[str]]:
    """Devuelve la lista de stems que produce el modelo (drums/bass/other/vocals)."""
    try:
        return list(getattr(modelo, "sources", []) or [])
    except Exception:
        return None
