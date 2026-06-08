# =============================================================================
# infra/dependencias.py
#
# Detector central de dependencias externas necesarias por NB Sound.
#
# Diseño
# ------
# La app NB Sound declara dos clases de dependencias:
#
#   * **Requeridas**: VLC, ffmpeg, python-vlc, librosa. Sin alguna de ellas
#     la funcionalidad principal queda degradada (reproducción rota,
#     transcodificación rota, importación sin features básicas).
#
#   * **Opcionales**: torch / torchaudio / demucs (Karaoke), essentia-tensorflow
#     + modelos (.pb) (deep audio intelligence). Su ausencia no impide usar
#     la app, sólo deshabilita las pantallas/acciones que las requieren.
#
# Para evitar el síntoma reportado por el usuario ("falla en silencio")
# este módulo cachea el estado de cada dependencia en `config_ui` y expone
# una API uniforme para que la UI:
#
#   1) muestre un dashboard claro al usuario,
#   2) ofrezca instalación automática (vía `infra.instalador`),
#   3) revalide cada N días.
#
# El módulo NO depende de Qt para que sea testeable y pueda ser invocado
# desde CLI / scripts sin arrancar la UI.
# =============================================================================

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from infra.logger import obtener_logger

_log = obtener_logger("dependencias")


# -----------------------------------------------------------------------------
# Modelo de datos
# -----------------------------------------------------------------------------

class TipoDependencia(str, Enum):
    """Origen del componente, determina cómo se verifica e instala."""
    SISTEMA = "sistema"            # paquete del SO (VLC). Instalación manual.
    BINARIO_PATH = "binario_path"  # ejecutable buscado en PATH / bundle (ffmpeg, fpcalc).
    PIP = "pip"                    # wheel Python instalable vía pip.
    MODELOS = "modelos"            # archivos descargables (modelos .pb).


class EstadoDependencia(str, Enum):
    OK = "ok"
    FALTANTE = "faltante"
    INSTALANDO = "instalando"
    ERROR_INSTALACION = "error_instalacion"
    NO_VERIFICADO = "no_verificado"


@dataclass
class Dependencia:
    """Definición declarativa de una dependencia externa.

    El verificador es una función sin argumentos que devuelve una tupla
    (encontrada, version). Cuando ``encontrada == False`` el estado se
    considera FALTANTE; cuando devuelve True con version vacía se marca OK
    con ``version = "desconocida"``.
    """
    id: str
    nombre: str
    descripcion: str
    tipo: TipoDependencia
    requerida: bool
    funciones_que_habilita: list[str]
    verificador: Callable[[], tuple[bool, str]]
    # Solo para tipo=PIP:
    pip_specifier: Optional[str] = None
    pip_modulo_test: Optional[str] = None
    # Solo para tipo=SISTEMA / tipo=BINARIO_PATH:
    instruccion_manual: str = ""
    # URLs por SO para descargar el componente cuando es de sistema:
    urls_descarga: dict[str, str] = field(default_factory=dict)
    # Para tipo=MODELOS: lista de URLs a descargar (compute en runtime).
    proveedor_descargas: Optional[Callable[[], list[tuple[str, Path]]]] = None


@dataclass
class ReporteDependencia:
    """Snapshot serializable del estado de una dependencia para la UI / BD."""
    id: str
    nombre: str
    descripcion: str
    tipo: str
    requerida: bool
    funciones_que_habilita: list[str]
    estado: str
    version: str
    detalle: str
    instruccion_manual: str
    pip_specifier: str
    verificado_en: str

    def a_dict(self) -> dict:
        return {
            "id": self.id,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "tipo": self.tipo,
            "requerida": self.requerida,
            "funciones_que_habilita": list(self.funciones_que_habilita),
            "estado": self.estado,
            "version": self.version,
            "detalle": self.detalle,
            "instruccion_manual": self.instruccion_manual,
            "pip_specifier": self.pip_specifier,
            "verificado_en": self.verificado_en,
        }


# -----------------------------------------------------------------------------
# Verificadores concretos
# -----------------------------------------------------------------------------

def _ejecutar_silencioso(cmd: list[str], timeout: float = 4.0) -> tuple[int, str, str]:
    """Ejecuta ``cmd`` capturando stdio. En Windows GUI evita la ventana flash.

    Devuelve (returncode, stdout, stderr). Si el binario no existe o se
    excede el timeout, returncode != 0 y stdout/stderr contienen información
    para diagnóstico.
    """
    kwargs: dict = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "check": False,
    }
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(cmd, **kwargs)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except OSError as exc:
        return 1, "", str(exc)


def _verificar_modulo_python(nombre: str) -> tuple[bool, str]:
    """Devuelve (importable, version). No importa el módulo si pesa mucho."""
    if importlib.util.find_spec(nombre) is None:
        return False, ""
    try:
        # importlib.metadata es estándar y no carga el módulo.
        from importlib.metadata import version, PackageNotFoundError
        try:
            return True, version(nombre)
        except PackageNotFoundError:
            return True, "desconocida"
    except Exception:
        return True, "desconocida"


def _verificar_vlc() -> tuple[bool, str]:
    """python-vlc cargado + libvlc.so disponible + Instance creable."""
    importable, ver = _verificar_modulo_python("vlc")
    if not importable:
        return False, ""
    try:
        import vlc  # type: ignore
        if vlc.dll is None:
            return False, ver
        inst = vlc.Instance("--no-xlib --quiet --vout=dummy --aout=pulse")
        if inst is None:
            inst = vlc.Instance("--quiet")
        if inst is None:
            return False, ver
        return True, ver
    except Exception as exc:
        _log.debug("VLC verificacion fallo: %s", exc)
        return False, ver


def _verificar_libvlc_sistema() -> tuple[bool, str]:
    """Para Windows / macOS: verifica que libvlc del sistema esté."""
    # Reutiliza la lógica de _verificar_vlc; si python-vlc carga es porque
    # libvlc estaba disponible.
    return _verificar_vlc()


def _verificar_binario(nombre: str) -> tuple[bool, str]:
    """Busca el binario primero en `infra.binarios.resolver_bin` (incluye
    embedded) y luego en el PATH. Si lo encuentra ejecuta -version para
    obtener la cadena de versión.
    """
    try:
        from infra.binarios import resolver_bin
        ruta = resolver_bin(nombre)
    except Exception:
        ruta = shutil.which(nombre)
    if not ruta:
        return False, ""
    rc, out, err = _ejecutar_silencioso([ruta, "-version"], timeout=4.0)
    if rc != 0:
        return True, "desconocida"
    primera = (out or err).strip().splitlines()
    return True, (primera[0] if primera else "desconocida")


def _verificar_modulo_subprocess(nombre: str, atributo_version: str = "__version__") -> tuple[bool, str]:
    """Importa ``nombre`` en un subprocess y devuelve (ok, version).

    Para wheels con extensiones nativas pesadas (torch, essentia,
    tensorflow), `import` puede crashear con SIGABRT/SIGSEGV cuando hay
    incompatibilidad ABI con las libs del bundle. Una excepción Python
    no captura faults nativos, así que el riesgo de tumbar la app es
    real. Aislando el import en subprocess, el peor caso es returncode
    distinto de 0; la app principal nunca se cae.

    En bundle PyInstaller el subprocess corre con un **Python externo**
    (no ``sys.executable``, que apunta al bootloader nativo) y
    PYTHONPATH inyectando el ``site-packages`` donde el plug & play
    instaló los wheels. Ver ``infra.instalador.python_para_subprocess``.
    """
    # find_spec mira sys.path del proceso actual. En bundle, después de
    # `aplicar_runtime_pip_userdir` ya tenemos el site-packages user en
    # sys.path, así que esta llamada es informativa pero NO concluyente
    # cuando devuelve None: el Python externo del subprocess sí puede
    # encontrarlo via PYTHONPATH. Por eso seguimos al subprocess incluso
    # sin find_spec positivo.
    spec_local = importlib.util.find_spec(nombre)

    try:
        from infra.instalador import python_para_subprocess
        ejecutable, env = python_para_subprocess()
    except Exception:
        ejecutable, env = sys.executable, dict(os.environ)

    if ejecutable is None:
        # No hay Python externo disponible y estamos en bundle. Si find_spec
        # encontró el módulo en sys.path actual lo damos como presente
        # (versión desconocida); si no, faltante.
        if spec_local is not None:
            return True, "desconocida"
        return False, ""

    script = (
        f"import json, sys\n"
        f"try:\n"
        f"    import {nombre}\n"
        f"    v = getattr({nombre}, {atributo_version!r}, '')\n"
        f"    if not v:\n"
        f"        try:\n"
        f"            from importlib.metadata import version as _v\n"
        f"            v = _v({nombre!r})\n"
        f"        except Exception:\n"
        f"            v = 'desconocida'\n"
        f"    print(json.dumps({{'ok': True, 'version': str(v)}}))\n"
        f"except Exception as e:\n"
        f"    print(json.dumps({{'ok': False, 'error': str(e)}}))\n"
        f"    sys.exit(1)\n"
    )
    kwargs: dict = {
        # 60s: la PRIMERA importación de un wheel nativo recién instalado
        # (torch ~250MB, demucs) puede tardar bastante en disco lento; un
        # timeout corto daba un falso "faltante" justo tras instalar.
        "capture_output": True, "text": True, "timeout": 60.0, "check": False,
        "env": env,
    }
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run([ejecutable, "-c", script], **kwargs)
    except Exception as exc:
        _log.debug("subprocess import %s fallo: %s", nombre, exc)
        return False, ""
    if proc.returncode != 0:
        # Capturamos stdout TAMBIÉN: el script de verificación imprime el
        # error JSON en stdout cuando el import falla, no en stderr. Sin
        # esto, el log diagnóstico mostraba "stderr=" vacío y no se
        # podía saber por qué torch/demucs/essentia no se importaba.
        _log.debug(
            "subprocess %s returncode=%s stdout=%s stderr=%s",
            nombre, proc.returncode,
            (proc.stdout or "")[-500:], (proc.stderr or "")[-500:],
        )
        return False, ""
    try:
        data = json.loads((proc.stdout or "").strip().splitlines()[-1])
        if not data.get("ok"):
            return False, ""
        return True, str(data.get("version") or "desconocida")
    except Exception:
        return False, ""


def _verificar_torch() -> tuple[bool, str]:
    """torch importable sin SIGSEGV. Usa subprocess para aislar faults nativos."""
    return _verificar_modulo_subprocess("torch")


def _verificar_demucs() -> tuple[bool, str]:
    """demucs importable sin SIGSEGV (depende de torch nativo)."""
    return _verificar_modulo_subprocess("demucs")


def _verificar_librosa() -> tuple[bool, str]:
    return _verificar_modulo_python("librosa")


def _verificar_soundfile() -> tuple[bool, str]:
    return _verificar_modulo_python("soundfile")


def _verificar_essentia_tensorflow() -> tuple[bool, str]:
    """essentia + algoritmos *Tensorflow* expuestos.

    Aislado en subprocess (Python externo + PYTHONPATH al site-packages
    runtime cuando NB Sound corre como bundle). essentia-tensorflow carga
    libtensorflow.so, que puede crashear el proceso si las libs del
    bundle / del sistema no son ABI-compatibles. La app no puede
    sobrevivir a SIGSEGV vía try/except, por eso usamos subprocess.
    """
    spec_local = importlib.util.find_spec("essentia")

    try:
        from infra.instalador import python_para_subprocess
        ejecutable, env = python_para_subprocess()
    except Exception:
        ejecutable, env = sys.executable, dict(os.environ)

    if ejecutable is None:
        if spec_local is not None:
            # En bundle sin python externo no podemos validar TF, pero al
            # menos sabemos que essentia base se importa.
            return True, "desconocida"
        return False, ""

    script = (
        "import json, sys\n"
        "try:\n"
        "    import essentia.standard as es\n"
        "    from importlib.metadata import version, PackageNotFoundError\n"
        "    try:\n"
        "        v = version('essentia-tensorflow')\n"
        "    except PackageNotFoundError:\n"
        "        try:\n"
        "            v = version('essentia')\n"
        "        except PackageNotFoundError:\n"
        "            v = 'desconocida'\n"
        "    tiene_tf = any(hasattr(es, n) for n in ('TensorflowPredictMusiCNN', 'TensorflowPredict2D'))\n"
        "    print(json.dumps({'ok': True, 'tf': bool(tiene_tf), 'version': str(v)}))\n"
        "except Exception as e:\n"
        "    print(json.dumps({'ok': False, 'error': str(e)}))\n"
        "    sys.exit(1)\n"
    )
    kwargs: dict = {
        # 60s: importar essentia + cargar libtensorflow.so la primera vez tras
        # instalar puede ser lento; evita falsos "faltante" por timeout.
        "capture_output": True, "text": True, "timeout": 60.0, "check": False,
        "env": env,
    }
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run([ejecutable, "-c", script], **kwargs)
    except Exception as exc:
        _log.debug("subprocess essentia fallo: %s", exc)
        return False, ""
    if proc.returncode != 0:
        _log.debug("essentia subprocess rc=%s stderr=%s",
                   proc.returncode, (proc.stderr or "")[-300:])
        return False, ""
    try:
        data = json.loads((proc.stdout or "").strip().splitlines()[-1])
        if not data.get("ok") or not data.get("tf"):
            return False, str(data.get("version", ""))
        return True, str(data.get("version") or "desconocida")
    except Exception:
        return False, ""


def _verificar_modelos_essentia() -> tuple[bool, str]:
    """Compara el contenido de la carpeta del usuario contra el catálogo
    canónico de NB Sound (`infra.modelos_essentia.CATALOGO`).

    Si TODOS los modelos esperados están presentes, devuelve OK.
    Si faltan algunos, marca como FALTANTE con detalle de cuántos hay vs.
    cuántos faltan, así la UI puede mostrar "8/11" en vez de un binario.
    """
    try:
        from infra import modelos_essentia as _me
        estado = _me.verificar()
    except Exception as exc:
        _log.debug("verificar modelos_essentia fallo: %s", exc)
        return False, ""
    if estado.completo:
        return True, f"{len(estado.presentes)}/{estado.total} OK"
    if estado.presentes:
        return False, f"{len(estado.presentes)}/{estado.total} presentes"
    return False, ""


# -----------------------------------------------------------------------------
# Catalogo
# -----------------------------------------------------------------------------

def construir_catalogo() -> list[Dependencia]:
    """Lista declarativa de TODAS las dependencias que NB Sound conoce.

    Orden = orden de presentación en la UI (de las más críticas a las más
    opcionales). El catálogo es estable: la UI lo consume directamente.
    """
    instr_vlc = {
        "linux": "sudo apt install vlc  # o dnf install vlc / pacman -S vlc",
        "win32": "winget install --id VideoLAN.VLC",
        "darwin": "brew install --cask vlc",
    }
    return [
        Dependencia(
            id="vlc",
            nombre="VLC media player",
            descripcion="Backend de reproducción de audio. Sin VLC la app abre pero no reproduce.",
            tipo=TipoDependencia.SISTEMA,
            requerida=True,
            funciones_que_habilita=["Reproducción", "Karaoke", "DJ Privado", "Explorador Ciego"],
            verificador=_verificar_libvlc_sistema,
            instruccion_manual=instr_vlc.get(sys.platform if sys.platform != "linux" else "linux", instr_vlc["linux"]),
            urls_descarga={
                "linux": "https://www.videolan.org/vlc/#download",
                "win32": "https://www.videolan.org/vlc/download-windows.html",
                "darwin": "https://www.videolan.org/vlc/download-macosx.html",
            },
        ),
        Dependencia(
            id="ffmpeg",
            nombre="FFmpeg",
            descripcion="Transcodificación y análisis de audio. Las builds oficiales lo embeben; si no se detecta se busca en PATH.",
            tipo=TipoDependencia.BINARIO_PATH,
            requerida=True,
            funciones_que_habilita=["Importación", "Transcodificación", "Karaoke"],
            verificador=lambda: _verificar_binario("ffmpeg"),
            instruccion_manual="sudo apt install ffmpeg  # o equivalente para tu SO",
            urls_descarga={
                "linux": "https://ffmpeg.org/download.html",
                "win32": "https://ffmpeg.org/download.html#build-windows",
                "darwin": "https://ffmpeg.org/download.html#build-mac",
            },
        ),
        Dependencia(
            id="fpcalc",
            nombre="Chromaprint (fpcalc)",
            descripcion="Fingerprinting acústico para AcoustID. Las builds oficiales lo embeben.",
            tipo=TipoDependencia.BINARIO_PATH,
            requerida=False,
            funciones_que_habilita=["AcoustID"],
            verificador=lambda: _verificar_binario("fpcalc"),
            instruccion_manual="Descargar Chromaprint desde https://acoustid.org/chromaprint",
            urls_descarga={
                "linux": "https://acoustid.org/chromaprint",
                "win32": "https://acoustid.org/chromaprint",
                "darwin": "https://acoustid.org/chromaprint",
            },
        ),
        Dependencia(
            id="librosa",
            nombre="librosa",
            descripcion="Extracción de audio features básicas (tempo, key, energy, …).",
            tipo=TipoDependencia.PIP,
            requerida=True,
            funciones_que_habilita=["Audio features", "Recomendaciones", "DJ Privado"],
            verificador=_verificar_librosa,
            pip_specifier="librosa>=0.11.0",
            pip_modulo_test="librosa",
        ),
        Dependencia(
            id="soundfile",
            nombre="soundfile",
            descripcion="Lectura/escritura de audio para librosa y demucs.",
            tipo=TipoDependencia.PIP,
            requerida=True,
            funciones_que_habilita=["Audio features", "Karaoke"],
            verificador=_verificar_soundfile,
            pip_specifier="soundfile>=0.12.0",
            pip_modulo_test="soundfile",
        ),
        Dependencia(
            id="aiohttp",
            nombre="aiohttp",
            descripcion="Servidor HTTP + WebSocket en proceso para sincronizar con la app móvil por WiFi.",
            tipo=TipoDependencia.PIP,
            requerida=False,
            funciones_que_habilita=["Sincronización móvil"],
            verificador=lambda: _verificar_modulo_python("aiohttp"),
            pip_specifier="aiohttp>=3.9.0",
            pip_modulo_test="aiohttp",
        ),
        Dependencia(
            id="zeroconf",
            nombre="Zeroconf (mDNS)",
            descripcion="Descubrimiento del PC en la red local (DNS-SD). Reconexión sin reescanear el QR.",
            tipo=TipoDependencia.PIP,
            requerida=False,
            funciones_que_habilita=["Sincronización móvil"],
            verificador=lambda: _verificar_modulo_python("zeroconf"),
            pip_specifier="zeroconf>=0.131.0",
            pip_modulo_test="zeroconf",
        ),
        Dependencia(
            id="qrcode",
            nombre="qrcode",
            descripcion="Generación del código QR de emparejamiento (sobre Pillow).",
            tipo=TipoDependencia.PIP,
            requerida=False,
            funciones_que_habilita=["Sincronización móvil"],
            verificador=lambda: _verificar_modulo_python("qrcode"),
            pip_specifier="qrcode>=7.4.2",
            pip_modulo_test="qrcode",
        ),
        Dependencia(
            id="cryptography",
            nombre="cryptography",
            descripcion="TLS del servidor de sincronización (certificado autofirmado + huella TOFU). Sin ella, la sync usa HTTP plano en la LAN.",
            tipo=TipoDependencia.PIP,
            requerida=False,
            funciones_que_habilita=["Sincronización móvil"],
            verificador=lambda: _verificar_modulo_python("cryptography"),
            pip_specifier="cryptography>=42.0.0",
            pip_modulo_test="cryptography",
        ),
        Dependencia(
            id="torch",
            nombre="PyTorch",
            descripcion="Backend de separación voz/instrumental para Karaoke. ~250MB en CPU.",
            tipo=TipoDependencia.PIP,
            requerida=False,
            funciones_que_habilita=["Karaoke"],
            verificador=_verificar_torch,
            pip_specifier="torch>=2.0.0",
            pip_modulo_test="torch",
        ),
        Dependencia(
            id="torchaudio",
            nombre="torchaudio",
            descripcion="Audio I/O para PyTorch (requerido por Demucs).",
            tipo=TipoDependencia.PIP,
            requerida=False,
            funciones_que_habilita=["Karaoke"],
            verificador=lambda: _verificar_modulo_python("torchaudio"),
            pip_specifier="torchaudio>=2.0.0",
            pip_modulo_test="torchaudio",
        ),
        Dependencia(
            id="demucs",
            nombre="Demucs",
            descripcion="Modelo de separación voz/instrumental (htdemucs). Necesita PyTorch.",
            tipo=TipoDependencia.PIP,
            requerida=False,
            funciones_que_habilita=["Karaoke"],
            verificador=_verificar_demucs,
            pip_specifier="demucs>=4.0.1",
            pip_modulo_test="demucs",
        ),
        Dependencia(
            id="essentia_tensorflow",
            nombre="essentia-tensorflow",
            descripcion="Backend de análisis profundo (moods, géneros Discogs400, embeddings). Necesita modelos .pb.",
            tipo=TipoDependencia.PIP,
            requerida=False,
            funciones_que_habilita=["Audio Intelligence deep"],
            verificador=_verificar_essentia_tensorflow,
            pip_specifier="essentia-tensorflow",
            pip_modulo_test="essentia",
        ),
        Dependencia(
            id="modelos_essentia",
            nombre="Modelos Essentia (.pb)",
            descripcion="Archivos de modelos pre-entrenados para deep audio intelligence.",
            tipo=TipoDependencia.MODELOS,
            requerida=False,
            funciones_que_habilita=["Audio Intelligence deep"],
            verificador=_verificar_modelos_essentia,
            instruccion_manual=(
                "Descargar los .pb desde https://essentia.upf.edu/models/ "
                "y colocarlos en el directorio configurado en Configuración "
                "→ Avanzada → AUDIO_INTELLIGENCE_MODEL_DIR."
            ),
            urls_descarga={
                "linux": "https://essentia.upf.edu/models/",
                "win32": "https://essentia.upf.edu/models/",
                "darwin": "https://essentia.upf.edu/models/",
            },
        ),
    ]


# -----------------------------------------------------------------------------
# Cache en config_ui
# -----------------------------------------------------------------------------

_CLAVE_CACHE = "dependencias_cache"
_CLAVE_TIMESTAMP = "dependencias_verificadas_en"
_CLAVE_APERTURAS = "dependencias_aperturas_desde_revalidacion"

# Política de revalidación: se ejecuta detección completa si:
#   * el cache no existe, o
#   * pasaron más de N días desde la última verificación, o
#   * la app se abrió más de M veces desde la última.
DIAS_HASTA_REVALIDAR = 14
APERTURAS_HASTA_REVALIDAR = 20


def _leer_cache() -> dict:
    try:
        from db.conexion import obtener_config
        raw = obtener_config(_CLAVE_CACHE, "")
        if not raw:
            return {}
        return json.loads(raw)
    except Exception:
        return {}


def _guardar_cache(estado: dict, timestamp: Optional[str] = None) -> None:
    try:
        from db.conexion import guardar_config
        guardar_config(_CLAVE_CACHE, json.dumps(estado, ensure_ascii=False))
        guardar_config(_CLAVE_TIMESTAMP, timestamp or datetime.now(timezone.utc).isoformat())
        guardar_config(_CLAVE_APERTURAS, "0")
    except Exception as exc:
        _log.debug("No se pudo guardar cache de dependencias: %s", exc)


def _ts_cache() -> Optional[datetime]:
    try:
        from db.conexion import obtener_config
        raw = obtener_config(_CLAVE_TIMESTAMP, "")
        if not raw:
            return None
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def _incrementar_aperturas() -> int:
    """Incrementa contador de aperturas; devuelve valor nuevo. Best-effort."""
    try:
        from db.conexion import obtener_config, guardar_config
        actual = int(obtener_config(_CLAVE_APERTURAS, "0") or "0")
        nuevo = actual + 1
        guardar_config(_CLAVE_APERTURAS, str(nuevo))
        return nuevo
    except Exception:
        return 0


def cache_obsoleto() -> bool:
    """True si conviene re-verificar todas las dependencias.

    Devuelve True cuando no hay cache, o el cache es viejo en tiempo o en
    número de aperturas. Permite que `infra.dependencias.detectar` decida
    automáticamente cuándo refrescar sin saturar al usuario.
    """
    ts = _ts_cache()
    if ts is None:
        return True
    edad = datetime.now(timezone.utc) - ts.astimezone(timezone.utc)
    if edad > timedelta(days=DIAS_HASTA_REVALIDAR):
        return True
    try:
        from db.conexion import obtener_config
        aperturas = int(obtener_config(_CLAVE_APERTURAS, "0") or "0")
    except Exception:
        aperturas = 0
    return aperturas >= APERTURAS_HASTA_REVALIDAR


# -----------------------------------------------------------------------------
# API publica
# -----------------------------------------------------------------------------

def detectar(force_refresh: bool = False) -> list[ReporteDependencia]:
    """Devuelve el estado actual de cada dependencia del catálogo.

    Si ``force_refresh`` es False (default) y el cache es reciente, se
    devuelve directamente lo cacheado. En caso contrario corre cada
    verificador y persiste el resultado en BD para la próxima llamada.
    """
    if not force_refresh and not cache_obsoleto():
        cacheados = _leer_cache()
        if cacheados:
            return [_reporte_desde_dict(d) for d in cacheados.values()]

    catalogo = construir_catalogo()
    ahora = datetime.now(timezone.utc).isoformat()
    reportes: list[ReporteDependencia] = []
    serializado: dict[str, dict] = {}
    for dep in catalogo:
        rep = _verificar_uno(dep, ahora)
        reportes.append(rep)
        serializado[dep.id] = rep.a_dict()
    _guardar_cache(serializado, ahora)
    return reportes


def reportes_cacheados() -> list[ReporteDependencia]:
    """Devuelve los reportes guardados en cache SIN ejecutar verificadores.

    Para un arranque NO bloqueante: los verificadores pueden lanzar subprocesos
    (torch/essentia) y crear instancias VLC, lo que congelaba el inicio cuando
    el cache estaba vencido. La UI pinta esto al instante y revalida en segundo
    plano. Devuelve lista vacía si no hay nada cacheado todavía.
    """
    cacheados = _leer_cache()
    if not cacheados:
        return []
    return [_reporte_desde_dict(d) for d in cacheados.values()]


def detectar_uno(dep_id: str) -> Optional[ReporteDependencia]:
    """Verifica una sola dependencia y actualiza su entrada en cache."""
    catalogo = construir_catalogo()
    dep = next((d for d in catalogo if d.id == dep_id), None)
    if dep is None:
        return None
    ahora = datetime.now(timezone.utc).isoformat()
    rep = _verificar_uno(dep, ahora)
    cache = _leer_cache()
    cache[dep_id] = rep.a_dict()
    _guardar_cache(cache, ahora)
    return rep


def _verificar_uno(dep: Dependencia, timestamp: str) -> ReporteDependencia:
    detalle = ""
    estado = EstadoDependencia.NO_VERIFICADO
    version = ""
    try:
        ok, version = dep.verificador()
        estado = EstadoDependencia.OK if ok else EstadoDependencia.FALTANTE
    except Exception as exc:
        detalle = f"Excepción durante verificación: {exc}"
        estado = EstadoDependencia.FALTANTE
    return ReporteDependencia(
        id=dep.id,
        nombre=dep.nombre,
        descripcion=dep.descripcion,
        tipo=dep.tipo.value,
        requerida=dep.requerida,
        funciones_que_habilita=list(dep.funciones_que_habilita),
        estado=estado.value,
        version=version or "",
        detalle=detalle,
        instruccion_manual=dep.instruccion_manual,
        pip_specifier=dep.pip_specifier or "",
        verificado_en=timestamp,
    )


def _reporte_desde_dict(d: dict) -> ReporteDependencia:
    return ReporteDependencia(
        id=d.get("id", ""),
        nombre=d.get("nombre", ""),
        descripcion=d.get("descripcion", ""),
        tipo=d.get("tipo", ""),
        requerida=bool(d.get("requerida", False)),
        funciones_que_habilita=list(d.get("funciones_que_habilita", [])),
        estado=d.get("estado", EstadoDependencia.NO_VERIFICADO.value),
        version=d.get("version", ""),
        detalle=d.get("detalle", ""),
        instruccion_manual=d.get("instruccion_manual", ""),
        pip_specifier=d.get("pip_specifier", ""),
        verificado_en=d.get("verificado_en", ""),
    )


def aplicar_runtime_pip_userdir() -> None:
    """Si existe un site-packages de usuario instalado por nuestro instalador
    (``~/.local/share/nb_sound/python/site-packages`` u homólogo por SO),
    lo agrega a ``sys.path`` para que módulos instalados post-instalación
    (torch, demucs, essentia) se importen sin reiniciar.

    Es idempotente: si el directorio no existe simplemente no hace nada.
    """
    try:
        from infra.instalador import ruta_site_packages_runtime
    except Exception:
        return
    try:
        ruta = ruta_site_packages_runtime()
    except Exception:
        return
    if ruta is None:
        return
    sp = str(ruta)
    if not Path(sp).is_dir():
        return
    if sp not in sys.path:
        sys.path.insert(0, sp)
        _log.debug("site-packages runtime agregado a sys.path: %s", sp)
    # Tras una instalación en runtime, los finders de importlib pueden conservar
    # en caché que el módulo NO existía (negative cache) o el listado del
    # directorio previo a la escritura de los wheels. Sin invalidar, una
    # verificación in-process (find_spec) seguiría devolviendo "faltante" aunque
    # pip lo acabe de instalar: el usuario veía "instalado correctamente" pero la
    # app nunca lo reconocía. invalidate_caches() lo resuelve sin reiniciar y es
    # idempotente (barato si no había nada que invalidar).
    importlib.invalidate_caches()


def registrar_apertura() -> None:
    """A llamarse una sola vez al arrancar la app. Incrementa el contador
    que dispara revalidaciones automáticas."""
    _incrementar_aperturas()


# -----------------------------------------------------------------------------
# Disponibilidad de Audio Intelligence profundo (deep) por plataforma
# -----------------------------------------------------------------------------

# IDs del catálogo que solo tienen sentido cuando el análisis deep está
# disponible. Se usan para filtrar la pantalla "Estado del sistema" en las
# plataformas donde deep no puede funcionar (ver `deep_analytics_disponible`).
IDS_DEPENDENCIAS_DEEP = frozenset({"essentia_tensorflow", "modelos_essentia"})


def deep_analytics_disponible() -> bool:
    """Indica si el análisis profundo (Essentia/TensorFlow) puede operar.

    ``essentia-tensorflow`` no publica un wheel funcional para Windows, por
    lo que toda la cadena de Audio Intelligence deep (modelos de mood,
    embeddings, tagging) es inalcanzable en esa plataforma. La lógica Python
    subyacente se conserva intacta para builds futuras y modo desarrollo;
    esta función es la única fuente de verdad para decidir si la UI debe
    exponer o no los controles deep.

    Se evalúa desde ``sys.platform`` y es estable durante toda la vida del
    proceso, de modo que la UI puede cachear el valor (context property
    evaluada una vez al iniciar).

    Returns:
        ``False`` en Windows (``win32``); ``True`` en Linux y macOS.
    """
    return not sys.platform.startswith("win")
