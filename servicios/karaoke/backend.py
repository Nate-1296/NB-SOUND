# =============================================================================
# servicios/karaoke/backend.py
#
# Deteccion y validacion del backend de separacion (Demucs) y de sus
# dependencias del sistema (ffmpeg). Tambien resuelve el `device` optimo
# (CUDA / MPS / CPU) sin depender del fabricante de GPU.
#
# Diseno:
#   - `diagnostico()` produce un dict con todo el estado del backend.
#     La UI lo usa para mostrar banners de configuracion al usuario.
#   - `seleccionar_device()` toma una preferencia y devuelve el mejor device
#     soportado en runtime. Nunca falla: cae a "cpu" si no hay alternativa.
#
# Todas las funciones de deteccion son baratas: no cargan modelos ni pesos,
# solo comprueban importaciones y ejecutan binarios con -version. Son seguras
# para llamar desde el hilo principal de Qt sin riesgo de bloqueo.
# =============================================================================

from __future__ import annotations

import importlib.util
import subprocess
import sys
from typing import Literal, Optional, TypedDict

from infra.binarios import resolver_bin
from infra.logger import obtener_logger


def _flags_subprocess_silencioso() -> dict:
    """``CREATE_NO_WINDOW`` en Windows; vacio en POSIX."""
    if sys.platform.startswith("win"):
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}

_log = obtener_logger("servicios.karaoke.backend")

DevicePref = Literal["auto", "cpu", "cuda", "mps"]


class DiagnosticoBackend(TypedDict):
    """Snapshot completo del estado del backend karaoke.

    Todos los campos son seguros para serializar a JSON y exponer a QML.
    `backend_listo` es el unico campo que la UI necesita para decidir si
    puede iniciar procesamiento; el resto son informativos para el panel
    de configuracion.
    """
    demucs_disponible: bool
    demucs_version: str
    torch_disponible: bool
    torch_version: str
    ffmpeg_disponible: bool
    ffmpeg_version: str
    device_disponible: str          # "cuda" | "mps" | "cpu"
    devices_soportados: list[str]
    backend_listo: bool
    mensaje: str
    instrucciones: str


def _detectar_ffmpeg() -> tuple[bool, str]:
    """Comprueba si ffmpeg esta disponible y extrae su version de la primera linea.

    La resolucion prioriza el binario embebido en el bundle; si no existe,
    cae al PATH del sistema. Si el binario existe pero ``-version`` falla,
    devuelve True con version "desconocida" — es suficiente para el diagnostico.
    """
    binario = resolver_bin("ffmpeg")
    if not binario:
        return False, ""
    try:
        salida = subprocess.run(
            [binario, "-version"], capture_output=True, text=True, timeout=4,
            **_flags_subprocess_silencioso(),
        )
        primera_linea = (salida.stdout or salida.stderr).splitlines()[:1]
        return True, (primera_linea[0] if primera_linea else "ffmpeg")
    except Exception as exc:
        _log.warning("ffmpeg -version fallo: %s", exc)
        return True, "ffmpeg (version desconocida)"


def _detectar_demucs() -> tuple[bool, str]:
    """Verifica si el paquete demucs esta instalado y extrae su version.

    Demucs 4.x no expone `__version__` directamente; se consulta a
    importlib.metadata como fallback. No importa torch ni carga pesos.
    """
    if importlib.util.find_spec("demucs") is None:
        return False, ""
    try:
        import demucs  # type: ignore
        version = getattr(demucs, "__version__", "")
        if not version:
            # demucs 4.x no expone __version__; pedirselo a importlib.metadata
            try:
                from importlib.metadata import version as _v
                version = _v("demucs")
            except Exception:
                version = "instalado"
        return True, str(version)
    except Exception as exc:
        _log.warning("demucs import fallo: %s", exc)
        return False, ""


def _detectar_torch_devices() -> tuple[bool, str, list[str]]:
    """Detecta PyTorch y construye la lista de devices disponibles.

    Cuando torch se instala vía el plug & play sobre el bundle congelado
    (PyInstaller), ``import torch`` puede provocar **SIGABRT / SIGSEGV**
    si las libs nativas del wheel (libtorch_cpu.so, libgomp.so, …) chocan
    con las del bundle. Una excepción capturada con try/except no protege
    contra un fault nativo: el proceso entero muere.

    Para que esto no tumbe la app cuando el usuario abre "Preparar
    Karaoke", la detección corre en un subprocess con un Python externo
    (no ``sys.executable``: en un bundle PyInstaller eso apunta al
    bootloader nativo, no a un intérprete Python — invocarlo con ``-c``
    no ejecuta Python). El path al site-packages donde el plug & play
    instaló torch se inyecta vía PYTHONPATH.

    Si no se puede resolver un Python externo (raro: el plug & play lo
    requiere para haber instalado torch en primer lugar), caemos a
    ``importlib.util.find_spec`` como heurística "está pero no
    verificable".
    """
    spec_local = importlib.util.find_spec("torch")

    try:
        from infra.instalador import python_para_subprocess
        ejecutable, env = python_para_subprocess()
    except Exception:
        ejecutable, env = sys.executable, None

    if ejecutable is None:
        # Bundle sin Python externo: heurística mínima.
        if spec_local is not None:
            return True, "desconocida", ["cpu"]
        return False, "", ["cpu"]

    # Script de detección: imprime una línea JSON con (version, devices).
    # Si torch no carga limpiamente, el subprocess termina con error y
    # el padre interpreta torch como faltante (lo cual es correcto:
    # un torch que crashea al importarse es funcionalmente inservible).
    script = (
        "import json, sys\n"
        "try:\n"
        "    import torch\n"
        "    dev = ['cpu']\n"
        "    try:\n"
        "        if torch.cuda.is_available(): dev.append('cuda')\n"
        "    except Exception:\n"
        "        pass\n"
        "    try:\n"
        "        backends_mps = getattr(torch.backends, 'mps', None)\n"
        "        if backends_mps is not None and backends_mps.is_available():\n"
        "            dev.append('mps')\n"
        "    except Exception:\n"
        "        pass\n"
        "    print(json.dumps({'ok': True, 'version': str(torch.__version__), 'devices': dev}))\n"
        "except Exception as e:\n"
        "    print(json.dumps({'ok': False, 'error': str(e)}))\n"
        "    sys.exit(1)\n"
    )
    kwargs: dict = {
        "capture_output": True, "text": True, "timeout": 20.0, "check": False,
        **_flags_subprocess_silencioso(),
    }
    if env is not None:
        kwargs["env"] = env
    try:
        proc = subprocess.run([ejecutable, "-c", script], **kwargs)
    except Exception as exc:
        _log.warning("torch subprocess detect fallo: %s", exc)
        return False, "", ["cpu"]

    if proc.returncode != 0:
        _log.info("torch no carga en subprocess (rc=%s): %s",
                  proc.returncode, (proc.stderr or "")[-300:])
        return False, "", ["cpu"]
    try:
        import json as _json
        data = _json.loads((proc.stdout or "").strip().splitlines()[-1])
        if not data.get("ok"):
            return False, "", ["cpu"]
        return True, str(data.get("version", "")), list(data.get("devices") or ["cpu"])
    except Exception as exc:
        _log.warning("torch detect parse fallo: %s", exc)
        return False, "", ["cpu"]


def seleccionar_device(preferencia: DevicePref = "auto") -> str:
    """Resuelve el device a usar en runtime.

    `auto` prioriza GPU si esta disponible; nunca falla.
    """
    _, _, soportados = _detectar_torch_devices()
    if preferencia == "auto":
        for candidato in ("cuda", "mps", "cpu"):
            if candidato in soportados:
                return candidato
        return "cpu"
    if preferencia in soportados:
        return preferencia
    _log.info("Device %r no disponible; cayendo a cpu", preferencia)
    return "cpu"


def diagnostico() -> DiagnosticoBackend:
    """Genera un snapshot completo del estado del backend.

    Pensado para la UI: si `backend_listo` es False, `mensaje` e
    `instrucciones` describen al usuario exactamente que falta y como
    instalarlo. La detection es barata: no carga pesos ni inicializa nada.
    """
    demucs_ok, demucs_version = _detectar_demucs()
    torch_ok, torch_version, devices = _detectar_torch_devices()
    ffmpeg_ok, ffmpeg_version = _detectar_ffmpeg()

    device_default = seleccionar_device("auto")
    listo = demucs_ok and torch_ok and ffmpeg_ok

    if not torch_ok:
        mensaje = "PyTorch no esta instalado."
        instrucciones = "pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu"
    elif not demucs_ok:
        mensaje = "Demucs no esta instalado."
        instrucciones = 'pip install "demucs>=4.0.1"'
    elif not ffmpeg_ok:
        mensaje = "ffmpeg no esta disponible en el PATH."
        instrucciones = (
            "Instala ffmpeg para tu plataforma: "
            "Linux (apt/dnf/pacman install ffmpeg), "
            "macOS (brew install ffmpeg), "
            "Windows (winget install Gyan.FFmpeg o choco install ffmpeg)."
        )
    else:
        partes = [f"demucs {demucs_version}", f"torch {torch_version}", f"device {device_default}"]
        mensaje = " · ".join(partes)
        instrucciones = ""

    return DiagnosticoBackend(
        demucs_disponible=demucs_ok,
        demucs_version=demucs_version,
        torch_disponible=torch_ok,
        torch_version=torch_version,
        ffmpeg_disponible=ffmpeg_ok,
        ffmpeg_version=ffmpeg_version,
        device_disponible=device_default,
        devices_soportados=devices,
        backend_listo=listo,
        mensaje=mensaje,
        instrucciones=instrucciones,
    )


def validar_listo() -> Optional[str]:
    """Comprobacion rapida de disponibilidad del backend.

    Devuelve None si el backend esta listo para procesar, o un codigo de error
    de tipo str si falta alguna dependencia critica.

    Codigos posibles: "backend_no_disponible" | "ffmpeg_faltante".

    Usa esta funcion en rutas de codigo que necesitan una respuesta booleana
    rapida sin construir el diagnostico completo.
    """
    diag = diagnostico()
    if not diag["demucs_disponible"] or not diag["torch_disponible"]:
        return "backend_no_disponible"
    if not diag["ffmpeg_disponible"]:
        return "ffmpeg_faltante"
    return None
