# =============================================================================
# infra/instalador.py
#
# Instalación automática de dependencias post-empaquetado.
#
# Problema
# --------
# Los bundles PyInstaller (`nb_sound.exe`, el .deb, la .app) no incluyen
# wheels pesados como `torch` (~250 MB), `demucs` (~50 MB) o
# `essentia-tensorflow` (~700 MB) porque GitHub Releases tiene un límite
# de 2 GB por archivo. Tampoco incluyen modelos `.pb` de Essentia. La app
# debe poder instalarlos en runtime con consentimiento del usuario.
#
# Diseño
# ------
# 1) Usamos un Python externo del sistema (`python3` / `py` / `python`)
#    para ejecutar `pip install --target <dir>`. El bundle no expone
#    `python -m pip` porque el sys.executable es el bootloader nativo, no
#    un intérprete Python.
#
# 2) El directorio de instalación es:
#       Linux   -> ~/.local/share/nb_sound/python/site-packages
#       Windows -> %LOCALAPPDATA%/NBSound/python/site-packages
#       macOS   -> ~/Library/Application Support/NBSound/python/site-packages
#    Es de usuario (no requiere sudo / UAC).
#
# 3) En runtime, `infra.dependencias.aplicar_runtime_pip_userdir()` agrega
#    ese path a `sys.path` ANTES de cualquier import opcional, así torch /
#    demucs / essentia son importables sin reiniciar.
#
# 4) Para VLC (paquete del sistema, no pip) NO instalamos automáticamente:
#    abrimos la URL oficial y enseñamos el comando para el SO actual.
#    Atender mismo VLC requeriría sudo / UAC y depende del distro.
#
# Threading: las funciones que disparan instalaciones aceptan callbacks
# opcionales para emitir progreso. La UI las llamará desde un QThread.
# =============================================================================

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from infra.logger import obtener_logger

_log = obtener_logger("instalador")


# -----------------------------------------------------------------------------
# Rutas runtime
# -----------------------------------------------------------------------------

def ruta_base_runtime() -> Path:
    """Carpeta donde se instalan deps pip post-bundle.

    Se mantiene en sync con `infra.bootstrap.resolver_rutas_estandar`:
    todo bajo el directorio de datos del SO para que desinstalar la app
    pueda limpiarla sin tocar nada más del sistema.
    """
    try:
        from infra.bootstrap import resolver_rutas_estandar
        rutas = resolver_rutas_estandar()
        # Reusa la carpeta de datos (no la de cache: lo de pip es persistente).
        # Bajo Linux: ~/.local/share/nb_sound/python
        base = rutas.library.parent  # rutas.library = .../nb_sound/biblioteca
        return base / "python"
    except Exception:
        # Fallback minimo.
        return Path.home() / ".nb_sound_runtime"


def ruta_site_packages_runtime() -> Optional[Path]:
    """Site-packages donde pip instala con --target. None si no aplica."""
    base = ruta_base_runtime()
    return base / "site-packages"


def python_para_subprocess() -> tuple[Optional[str], dict]:
    """Devuelve (ejecutable, env) para correr código Python en subprocess.

    Por qué existe
    --------------
    Cuando NB Sound corre como bundle PyInstaller, ``sys.executable`` apunta
    al binario nativo (`/opt/nb-sound/nb_sound`), NO a un intérprete Python.
    Invocar ``subprocess.run([sys.executable, "-c", "import torch"])`` en
    ese contexto hace que el bootloader interprete ``-c`` como argumento
    de la app y termine con error (sin haber importado nada). El detector
    cree que torch está faltante aunque la instalación pip haya sido
    exitosa.

    Solución
    --------
    En modo frozen necesitamos un Python externo real para verificar
    módulos sin tumbar la app por SIGSEGV. La función:

      * En desarrollo (``sys.frozen != True``): devuelve ``sys.executable``
        sin tocar el entorno; el Python actual ya puede importar todo.
      * En bundle: busca Python 3.10+ del sistema con
        ``detectar_python_sistema()`` y le añade el ``site-packages``
        donde el plug & play instala wheels (mismo path al que apuntamos
        ``sys.path`` en runtime). Sin ese PYTHONPATH el Python externo
        no encuentra los módulos que NB Sound instaló con
        ``pip install --target``.

    Si en bundle no hay Python externo disponible, devuelve ``(None, env)``;
    los callers deben tratarlo como "no se puede verificar" en lugar de
    reportar "faltante" (porque podría estar correctamente instalado).
    """
    env = dict(os.environ)
    if not getattr(sys, "frozen", False):
        return sys.executable, env

    py = detectar_python_sistema()
    if not py:
        return None, env

    sp = ruta_site_packages_runtime()
    if sp is not None and sp.is_dir():
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(sp) + (os.pathsep + existing if existing else "")
    return py, env


# -----------------------------------------------------------------------------
# Detección de Python del sistema
# -----------------------------------------------------------------------------

@dataclass
class PythonChequeado:
    """Resultado de auditar un intérprete Python.

    ``utilizable`` es True solo si el binario existe, es Python 3.10+ y
    expone ``pip`` y ``venv`` (los dos que necesitamos para instalar
    wheels con ``--target``).
    """
    ruta: str
    version: tuple[int, int]
    pip_presente: bool
    venv_presente: bool
    error: str = ""

    @property
    def utilizable(self) -> bool:
        if not self.ruta:
            return False
        if self.version < (3, 10):
            return False
        return self.pip_presente and self.venv_presente


def _candidatos_python() -> list[str]:
    """Devuelve la lista de comandos Python a probar, en orden de
    preferencia, según el SO."""
    pref = os.environ.get("NB_SOUND_PYTHON", "").strip()
    candidatos: list[str] = []
    if pref:
        candidatos.append(pref)
    # Lanzador `py -3` de Windows expande a la mejor versión instalada.
    if sys.platform.startswith("win"):
        candidatos.extend(["py -3", "python", "python3"])
    else:
        candidatos.extend([
            "python3", "python3.13", "python3.12", "python3.11", "python3.10",
            "python",
        ])
    return candidatos


def _chequear_python(comando: str) -> PythonChequeado:
    """Audita ``comando`` (que puede contener espacios, ej. 'py -3').

    Devuelve un PythonChequeado con el detalle de qué módulos faltan,
    para que el caller pueda repararlo (`reparar_python_linux`, etc.).
    """
    partes = comando.split()
    binario = partes[0]
    args_extra = partes[1:]
    ruta = shutil.which(binario)
    if not ruta:
        return PythonChequeado(ruta="", version=(0, 0), pip_presente=False,
                               venv_presente=False, error="no encontrado")
    rc, out, err = _ejecutar([ruta, *args_extra, "-c",
        "import sys, importlib.util\n"
        "print(sys.executable)\n"
        "print('%d.%d' % sys.version_info[:2])\n"
        "print('pip' if importlib.util.find_spec('pip') else 'no_pip')\n"
        "print('venv' if importlib.util.find_spec('venv') else 'no_venv')\n"
        "print('ensurepip' if importlib.util.find_spec('ensurepip') else 'no_ensurepip')\n"
    ], timeout=8.0)
    if rc != 0:
        return PythonChequeado(ruta=ruta, version=(0, 0), pip_presente=False,
                               venv_presente=False, error=(err or out)[:200])
    lineas = (out or "").strip().splitlines()
    if len(lineas) < 5:
        return PythonChequeado(ruta=ruta, version=(0, 0), pip_presente=False,
                               venv_presente=False, error="salida inesperada")
    ejecutable_real = lineas[0].strip() or ruta
    try:
        major, minor = (int(x) for x in lineas[1].split(".")[:2])
    except Exception:
        major, minor = 0, 0
    pip = (lineas[2].strip() == "pip")
    venv = (lineas[3].strip() == "venv")
    ensurepip = (lineas[4].strip() == "ensurepip")
    # ensurepip + venv juntos son lo que se necesita para `python -m venv`;
    # pip por sí solo basta para `pip install --target` que es lo que usamos.
    return PythonChequeado(
        ruta=ejecutable_real,
        version=(major, minor),
        pip_presente=pip,
        venv_presente=(venv and ensurepip),
    )


def detectar_python_sistema() -> Optional[str]:
    """Devuelve la ruta a un Python 3.10+ con pip+venv, o None si no hay
    ninguno utilizable. Conserva la API original; el detalle por candidato
    queda en :func:`auditar_python_sistema`.
    """
    for comando in _candidatos_python():
        chq = _chequear_python(comando)
        if chq.utilizable:
            return chq.ruta
    return None


def auditar_python_sistema() -> PythonChequeado:
    """Audita todos los candidatos y devuelve el "más útil":

    * Prioriza ``utilizable=True`` (3.10+ con pip y venv).
    * Si todos están degradados, devuelve el de mayor versión con la mayor
      cantidad de módulos presentes, para que la UI sepa exactamente qué
      reparar (``apt install python3-venv`` es distinto a ``apt install
      python3-pip``).
    """
    candidatos = [_chequear_python(c) for c in _candidatos_python()]
    candidatos = [c for c in candidatos if c.ruta]
    if not candidatos:
        return PythonChequeado(ruta="", version=(0, 0), pip_presente=False,
                               venv_presente=False, error="no se encontró ningún Python en PATH")
    utilizables = [c for c in candidatos if c.utilizable]
    if utilizables:
        # Preferir la versión más alta entre los utilizables.
        return max(utilizables, key=lambda c: c.version)
    # Ninguno utilizable: devolver el menos roto (mayor versión + más módulos).
    return max(candidatos, key=lambda c: (c.version, int(c.pip_presente), int(c.venv_presente)))


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _ejecutar(cmd: list[str], timeout: Optional[float] = None,
              en_callback: Optional[Callable[[str], None]] = None) -> tuple[int, str, str]:
    """Ejecuta ``cmd`` capturando stdio. Si ``en_callback`` se pasa, emite
    cada línea a la UI en streaming (para mostrar el progreso de pip).
    """
    kwargs: dict = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if en_callback is None:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout, check=False, **kwargs)
            return proc.returncode, proc.stdout or "", proc.stderr or ""
        except FileNotFoundError as exc:
            return 127, "", str(exc)
        except subprocess.TimeoutExpired:
            return 124, "", "timeout"
        except OSError as exc:
            return 1, "", str(exc)

    # Modo streaming: lanzar Popen y leer línea por línea.
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            **kwargs,
        )
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except OSError as exc:
        return 1, "", str(exc)

    salida: list[str] = []
    assert proc.stdout is not None
    for linea in proc.stdout:
        salida.append(linea)
        try:
            en_callback(linea.rstrip("\n"))
        except Exception:
            pass
    proc.wait(timeout=timeout)
    return proc.returncode, "".join(salida), ""


# -----------------------------------------------------------------------------
# Reparación de Python en Linux (instalación de python3-venv / python3-pip)
# -----------------------------------------------------------------------------

def _detectar_gestor_paquetes_linux() -> Optional[tuple[str, list[str]]]:
    """Detecta el gestor de paquetes nativo del distro y devuelve el comando
    base para instalar paquetes (``[gestor, *args, paquete...]``).

    Cubre apt (Debian/Ubuntu/Pop/Mint), dnf (Fedora/RHEL), pacman
    (Arch/Manjaro), zypper (openSUSE). Si no encuentra ninguno devuelve
    None y el caller debe pedir instalación manual.
    """
    if shutil.which("apt-get"):
        return "apt", ["apt-get", "install", "-y", "--no-install-recommends"]
    if shutil.which("dnf"):
        return "dnf", ["dnf", "install", "-y"]
    if shutil.which("pacman"):
        return "pacman", ["pacman", "-S", "--noconfirm"]
    if shutil.which("zypper"):
        return "zypper", ["zypper", "install", "-y"]
    return None


def _paquetes_python_por_gestor(version: tuple[int, int]) -> dict[str, list[str]]:
    """Nombres de paquetes según el gestor.

    apt suele tener `python3-venv` separado de `python3-pip`. dnf/pacman/zypper
    lo integran en el paquete `python3` base. Si la versión es 0 (Python no
    instalado) instalamos el paquete `python3` también.
    """
    base_extra = ["python3", "python3-pip", "python3-venv"] if version == (0, 0) else ["python3-pip", "python3-venv"]
    return {
        "apt":    base_extra,
        "dnf":    ["python3", "python3-pip"] if version == (0, 0) else ["python3-pip"],
        "pacman": ["python", "python-pip"]   if version == (0, 0) else ["python-pip"],
        "zypper": ["python3", "python3-pip"] if version == (0, 0) else ["python3-pip"],
    }


def comando_reparacion_linux(chq: PythonChequeado) -> Optional[list[str]]:
    """Construye el comando ``pkexec ...`` necesario para reparar el
    Python del sistema, según lo que falte en ``chq``. Devuelve None si
    no se puede reparar automáticamente (sin pkexec o sin gestor conocido).
    """
    if not sys.platform.startswith("linux"):
        return None
    gestor = _detectar_gestor_paquetes_linux()
    if gestor is None:
        return None
    nombre, base_cmd = gestor
    paquetes = _paquetes_python_por_gestor(chq.version).get(nombre, [])
    if not paquetes:
        return None
    # apt-get update primero en distros basadas en Debian: si los índices
    # están viejos, install -y puede fallar con "Unable to locate package".
    if nombre == "apt":
        prefijo = ["sh", "-c", "apt-get update && " + " ".join(base_cmd + paquetes)]
    else:
        prefijo = base_cmd + paquetes
    # pkexec eleva sin pedir password en gráficos (polkit). Como fallback,
    # si no hay pkexec, usar `sudo -A` (con SUDO_ASKPASS).
    if shutil.which("pkexec"):
        return ["pkexec"] + prefijo
    if shutil.which("sudo"):
        return ["sudo"] + prefijo
    return None


def reparar_python_linux(
    chq: PythonChequeado,
    *,
    en_progreso: Optional[Callable[[str], None]] = None,
) -> "ResultadoInstalacion":
    """Ejecuta el comando devuelto por ``comando_reparacion_linux``
    transmitiendo la salida a ``en_progreso``. Pensado para correrse en un
    QThread desde la UI.
    """
    cmd = comando_reparacion_linux(chq)
    if cmd is None:
        return ResultadoInstalacion(
            ok=False,
            mensaje=(
                "No se pudo reparar Python automáticamente. "
                "Instala python3-venv y python3-pip manualmente con el "
                "gestor de paquetes de tu distro."
            ),
        )
    _log.info("Reparando Python: %s", " ".join(cmd))
    rc, salida, _ = _ejecutar(cmd, timeout=None, en_callback=en_progreso)
    if rc != 0:
        return ResultadoInstalacion(
            ok=False,
            mensaje=f"La reparación de Python terminó con código {rc}.",
            detalle=(salida or "").strip()[-2000:],
        )
    return ResultadoInstalacion(
        ok=True,
        mensaje="Python reparado. python3-venv y python3-pip ya están disponibles.",
        detalle=(salida or "").strip()[-2000:],
    )


# -----------------------------------------------------------------------------
# Instalación de paquetes pip
# -----------------------------------------------------------------------------

@dataclass
class ResultadoInstalacion:
    ok: bool
    mensaje: str
    detalle: str = ""


def instalar_pip(
    pip_specifier: str,
    *,
    extra_index_url: str = "",
    en_progreso: Optional[Callable[[str], None]] = None,
) -> ResultadoInstalacion:
    """Instala (o repara) ``pip_specifier`` en el directorio runtime de NB Sound.

    Siempre fuerza una reinstalación limpia (``--upgrade --force-reinstall``):
    el botón de instalar opera sobre dependencias que no están OK, y una
    instalación previa interrumpida puede haber dejado el paquete a medias.

    El paquete queda accesible vía ``sys.path`` luego de que
    ``infra.dependencias.aplicar_runtime_pip_userdir()`` se ejecute (cosa
    que hace ``main_ui`` al arrancar).

    Si el Python del sistema existe pero le falta ``pip``/``venv`` (caso
    típico en Debian/Ubuntu sin ``python3-venv``), intenta repararlo
    automáticamente con pkexec antes de continuar. Solo se rinde si la
    reparación también falla.
    """
    python = detectar_python_sistema()
    if python is None:
        # Intento extra: ¿hay un Python instalado pero con módulos rotos?
        chq = auditar_python_sistema()
        if chq.ruta and chq.version >= (3, 10) and sys.platform.startswith("linux"):
            if en_progreso:
                en_progreso(f"Python {chq.version[0]}.{chq.version[1]} detectado pero le faltan módulos. "
                            "Intentando reparar (puede pedir contraseña)...")
            rep = reparar_python_linux(chq, en_progreso=en_progreso)
            if rep.ok:
                python = detectar_python_sistema()
        if python is None:
            return ResultadoInstalacion(
                ok=False,
                mensaje="No se encontró Python 3.10+ funcional en el sistema.",
                detalle=(
                    "NB Sound necesita un Python del sistema con pip y venv para "
                    "instalar componentes opcionales (torch, demucs, essentia). "
                    "En Linux: instala los paquetes `python3-pip python3-venv` "
                    "con tu gestor (apt/dnf/pacman/zypper). "
                    "En Windows/macOS: descarga Python 3.12+ desde python.org / brew."
                ),
            )
    sp = ruta_site_packages_runtime()
    if sp is None:
        return ResultadoInstalacion(
            ok=False,
            mensaje="No se pudo resolver el directorio de instalación.",
        )
    try:
        sp.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return ResultadoInstalacion(
            ok=False,
            mensaje=f"No se pudo crear {sp}: {exc}",
        )

    # `--upgrade --force-reinstall`: el botón de instalar es siempre una acción
    # de REPARACIÓN sobre una dependencia que no está OK. Una instalación previa
    # interrumpida (cierre de la app, corte de red) deja el `--target` con un
    # paquete a medias; con `pip install --target` SIN estas banderas pip
    # considera el paquete "ya presente" y NO lo reemplaza, devolviendo código 0
    # ("instalado correctamente") mientras los archivos siguen corruptos y la
    # app nunca lo reconoce. Forzar la reinstalación garantiza un árbol limpio.
    # El coste es bajo: pip reusa el wheel de su caché HTTP (no re-descarga), así
    # que solo re-extrae a disco.
    # `--retries`/`--timeout`: resiliencia ante redes intermitentes (mismo
    # criterio que la descarga de binarios del pipeline de release).
    cmd = [python, "-m", "pip", "install", "--no-input", "--disable-pip-version-check",
           "--retries", "5", "--timeout", "30",
           "--upgrade", "--force-reinstall", "--target", str(sp)]
    if extra_index_url:
        cmd.extend(["--extra-index-url", extra_index_url])
    cmd.append(pip_specifier)

    _log.info("Instalando %s en %s", pip_specifier, sp)
    rc, salida, err = _ejecutar(cmd, timeout=None, en_callback=en_progreso)
    if rc != 0:
        detalle = (err or salida).strip()[-2000:]
        return ResultadoInstalacion(
            ok=False,
            mensaje=f"pip install {pip_specifier} terminó con código {rc}.",
            detalle=detalle,
        )
    return ResultadoInstalacion(
        ok=True,
        mensaje=f"{pip_specifier} instalado correctamente.",
        detalle=(salida or "").strip()[-2000:],
    )


# -----------------------------------------------------------------------------
# Descarga de archivos (modelos Essentia, instaladores de sistema, …)
# -----------------------------------------------------------------------------

def descargar_archivo(
    url: str,
    destino: Path,
    *,
    en_progreso: Optional[Callable[[int, int], None]] = None,
    timeout: float = 60.0,
) -> ResultadoInstalacion:
    """Descarga ``url`` a ``destino`` con barra de progreso opcional.

    ``en_progreso`` recibe (bytes_descargados, bytes_totales). Si el
    servidor no envía Content-Length, ``bytes_totales`` será 0 y el caller
    puede mostrar un indicador indeterminado.
    """
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return ResultadoInstalacion(ok=False, mensaje=f"No se pudo crear {destino.parent}: {exc}")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NB-Sound/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(destino, "wb") as fh:
            total = int(resp.headers.get("Content-Length") or 0)
            leido = 0
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                leido += len(chunk)
                if en_progreso is not None:
                    try:
                        en_progreso(leido, total)
                    except Exception:
                        pass
    except Exception as exc:
        return ResultadoInstalacion(ok=False, mensaje=f"Descarga falló: {exc}")
    return ResultadoInstalacion(ok=True, mensaje=f"Descargado en {destino}.")


# -----------------------------------------------------------------------------
# Diagnóstico / sanity check
# -----------------------------------------------------------------------------

def directorio_modelos_karaoke() -> Optional[Path]:
    """Carpeta donde Demucs guarda los pesos del modelo (TORCH_HOME).

    Debe coincidir EXACTAMENTE con el path que
    ``servicios.karaoke.rutas.directorio_modelos`` calcula a partir de
    ``settings.DEFAULT_CACHE_DIR``, porque ese es el que
    ``WorkerKaraokeCola`` pasa a ``cargar_modelo``. Si el plug & play
    descarga los pesos en otro sitio (cache XDG por defecto), el caller
    no los encuentra y dispara una nueva descarga — sin red, esto cae
    con "Verifica conexión a internet…".

    Prioridad:
      1. ``settings.DEFAULT_CACHE_DIR / "karaoke" / "models"`` — la ruta
         configurada por el usuario (puede vivir en ``~/Música/cache``,
         por ejemplo).
      2. Fallback XDG (``rutas.cache``) sólo si ``settings`` aún no
         está poblado (caso raro en runtime; settings siempre resuelve
         a un fallback de SO).
    """
    try:
        from config import settings as _s
        if _s.DEFAULT_CACHE_DIR is not None:
            d = Path(_s.DEFAULT_CACHE_DIR) / "karaoke" / "models"
            d.mkdir(parents=True, exist_ok=True)
            return d
    except Exception:
        pass
    try:
        from infra.bootstrap import resolver_rutas_estandar
        rutas = resolver_rutas_estandar()
        d = rutas.cache / "karaoke" / "models"
        d.mkdir(parents=True, exist_ok=True)
        return d
    except Exception:
        return None


def precargar_modelo_demucs(
    nombre_modelo: str = "htdemucs",
    *,
    en_progreso: Optional[Callable[[str], None]] = None,
) -> ResultadoInstalacion:
    """Descarga los pesos del modelo Demucs ``nombre_modelo`` al disco
    sin lanzar la app principal.

    Se usa justo después de ``pip install demucs`` desde el plug & play:
    el wheel pip NO incluye los pesos (.th), torch.hub los descarga la
    primera vez que se llama ``get_model``. Si la descarga ocurre dentro
    de la app Karaoke puede fallar por SSL/cert del bundle PyInstaller,
    proxy o simple latencia, y el usuario ve "Verifica conexión a
    internet" aunque la conexión funcione.

    Pre-descarga = un subprocess Python externo con PYTHONPATH al
    site-packages runtime + TORCH_HOME apuntando a la carpeta cache de
    NB Sound. Si funciona, ``cargar_modelo`` posterior solo lee del
    disco sin tocar la red.
    """
    ejecutable, env = python_para_subprocess()
    if ejecutable is None:
        return ResultadoInstalacion(
            ok=False,
            mensaje="No hay Python externo disponible para pre-descargar el modelo.",
        )
    cache = directorio_modelos_karaoke()
    if cache is None:
        return ResultadoInstalacion(
            ok=False,
            mensaje="No se pudo resolver la carpeta de cache para los modelos.",
        )
    env = dict(env)
    env["TORCH_HOME"] = str(cache.resolve())

    if en_progreso:
        try:
            en_progreso(f"TORCH_HOME = {env['TORCH_HOME']}")
            en_progreso(f"Descargando modelo {nombre_modelo} (puede tardar ~1 min)...")
        except Exception:
            pass

    script = (
        "import json, os, sys\n"
        "try:\n"
        f"    from demucs.pretrained import get_model\n"
        f"    m = get_model({nombre_modelo!r})\n"
        "    sources = list(getattr(m, 'sources', []))\n"
        "    print(json.dumps({'ok': True, 'sources': sources}))\n"
        "except Exception as e:\n"
        "    print(json.dumps({'ok': False, 'error': str(e)}))\n"
        "    sys.exit(1)\n"
    )
    kwargs: dict = {
        "capture_output": True, "text": True, "timeout": 600.0, "check": False,
        "env": env,
    }
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run([ejecutable, "-c", script], **kwargs)
    except Exception as exc:
        return ResultadoInstalacion(
            ok=False,
            mensaje=f"No se pudo lanzar la pre-descarga: {exc}",
        )
    if proc.returncode != 0:
        detalle = (proc.stderr or proc.stdout or "").strip()[-2000:]
        return ResultadoInstalacion(
            ok=False,
            mensaje=f"La pre-descarga del modelo {nombre_modelo} falló.",
            detalle=detalle,
        )
    return ResultadoInstalacion(
        ok=True,
        mensaje=f"Modelo {nombre_modelo} listo en {cache}.",
        detalle=(proc.stdout or "").strip()[-300:],
    )


def diagnostico_entorno() -> dict:
    """Snapshot del entorno relevante para la UI de plug & play.

    Incluye versión de Python detectada, qué módulos le faltan, ruta del
    site-packages runtime, si NB Sound corre frozen, y si la reparación
    automática es posible en este SO.
    """
    chq = auditar_python_sistema()
    sp = ruta_site_packages_runtime()
    cmd_reparar = comando_reparacion_linux(chq) if sys.platform.startswith("linux") else None
    return {
        "python_sistema": chq.ruta if chq.utilizable else "",
        "python_detectado": chq.ruta,
        "python_version": f"{chq.version[0]}.{chq.version[1]}" if chq.version != (0, 0) else "",
        "python_utilizable": chq.utilizable,
        "python_falta_pip": (not chq.pip_presente),
        "python_falta_venv": (not chq.venv_presente),
        "python_error": chq.error,
        "site_packages_runtime": str(sp) if sp else "",
        "frozen": bool(getattr(sys, "frozen", False)),
        "ejecutable": sys.executable,
        "plataforma": sys.platform,
        "reparacion_disponible": bool(cmd_reparar),
        "reparacion_comando": " ".join(cmd_reparar) if cmd_reparar else "",
    }
