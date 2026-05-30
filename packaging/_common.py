# =============================================================================
# packaging/_common.py
#
# Bloques compartidos por los specs de PyInstaller (Linux, Windows, macOS).
# Mantener la logica aqui evita drift entre los 3 specs y facilita los
# cambios de empaquetado.
# =============================================================================

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


def project_root(spec_path: str) -> Path:
    return Path(spec_path).resolve().parent.parent


def base_datas(root: Path) -> list[tuple[str, str]]:
    """Conjunto minimo de DATAS requerido por la UI en cualquier SO.

    Incluye:
      * Carpeta QML completa + assets de iconos y logo.
      * **Archivos fuente `.py` necesarios cuando el bundle invoca un
        Python externo** (subprocess) para hacer análisis deep aislado.
        Los `hiddenimports` por sí solos solo garantizan que el módulo
        sea importable DESDE el bundle (vía el bootloader frozen). Pero
        `core.audio_intelligence_deep_subprocess` lanza
        ``python -m infra.deep_runner`` con el Python del sistema, que
        no tiene el bundle en su PYTHONPATH y, por tanto, necesita ver
        los `.py` reales en ``sys._MEIPASS``. Sin esto, todo análisis
        deep en el bundle frozen termina como "subprocess_unavailable".
    """
    qml_dir = root / "ui" / "qml"
    datas: list[tuple[str, str]] = [
        (str(qml_dir), "ui/qml"),
        (str(qml_dir / "assets" / "icons"), "ui/qml/assets/icons"),
        (str(qml_dir / "assets" / "logo"), "ui/qml/assets/logo"),
    ]
    # Módulos fuente necesarios para el subprocess deep. Empacamos cada
    # uno explícitamente como `(src, destino)` para que PyInstaller los
    # extraiga al MEIPASS con la misma estructura de directorios que
    # el repo. El subprocess hace `python -m infra.deep_runner` y
    # `infra.deep_runner` importa `core.audio_intelligence_deep`.
    # Incluimos los paquetes `infra/`, `config/` y el módulo
    # `core/audio_intelligence_deep.py` ENTEROS como `.py`. Razón: el
    # subprocess externo importa por cadena y cualquier dependencia
    # transitiva que falte rompe el daemon con `ModuleNotFoundError`
    # silencioso (la cola deep queda en "subprocess_unavailable"). En
    # vez de mantener una lista que tendamos a quedarnos cortos al
    # evolucionar `infra`/`config`, declaramos las carpetas como datas
    # completas — son pocos kB.
    paquetes_subprocess = (("infra", "infra"), ("config", "config"))
    for nombre_local, destino in paquetes_subprocess:
        carpeta = root / nombre_local
        if not carpeta.is_dir():
            continue
        for archivo in carpeta.glob("*.py"):
            datas.append((str(archivo), destino))
    # `core` no se empaca entero porque arrastraría módulos pesados
    # (pipeline, enrichment_pipeline, audio_features…) que no son
    # necesarios para el daemon deep y duplicarían MB en el bundle.
    # Sólo el archivo de análisis deep + `__init__` mínimo:
    for archivo in ("core/__init__.py", "core/audio_intelligence_deep.py"):
        src = root / archivo
        if src.exists():
            datas.append((str(src), "core"))
    return datas


# Paquetes Python opcionales cuyos data files se incluyen si estan instalados.
# Si el paquete no esta en el entorno del builder, se omite silenciosamente
# para producir un bundle minimo (sin karaoke/AudioIntelligence).
_OPTIONAL_DATA_PACKAGES = ("librosa", "soundfile", "demucs")

# Modulos Python que PyInstaller debe forzar a empaquetar aunque no aparezcan
# en el analisis estatico. Los modulos QML (ui.modelos_qml) se cargan desde
# QML, por lo que PyInstaller no los detecta.
_HIDDEN_IMPORTS_BASE = [
    # Submódulos de stdlib que PyInstaller no incluye por defecto pero
    # paquetes opcionales SÍ requieren en runtime.
    #
    # Histórico de los que hemos visto fallar:
    #   * `logging.config` — `submitit.core.logger` (vía demucs→dora).
    #   * `pickletools` — `torch.package.package_exporter`.
    #
    # Mantenemos una lista amplia preventiva para que el usuario no
    # vea un ciclo de "ahora falta X, ahora Y" cada vez que un wheel
    # actualiza dependencias.
    "logging.config",
    "logging.handlers",
    "pickletools",
    "pickle",
    # torch.serialization llama estos en algunos paths:
    "lzma",
    "bz2",
    # torch/numpy paths que pueden usar:
    "pdb",
    "doctest",
    "ssl",
    "_ssl",
    # urllib3 / requests usados por dora/torchhub para descargas:
    "http.cookies",
    "http.cookiejar",
    "xml.etree.ElementTree",
    "xml.parsers.expat",
    # email/mimetypes que urllib usa al armar requests HTTP:
    "email.mime",
    "email.mime.multipart",
    "email.mime.text",
    "mimetypes",
    # encodings esenciales (algunos wheels los importan tarde):
    "encodings.idna",
    "encodings.ascii",
    "encodings.utf_8",
    # ctypes utilities que torch.utils.cpp_extension carga lazily:
    "ctypes.util",
    "ctypes.macholib",
    # tomllib se usa por algunos parsers de config en wheels recientes:
    "tomllib",
    # multiprocessing helpers que torch puede usar:
    "multiprocessing.spawn",
    "multiprocessing.pool",
    "multiprocessing.synchronize",
    "multiprocessing.queues",
    # concurrent.futures.process es importado tarde por torch.distributed:
    "concurrent.futures.process",
    "concurrent.futures.thread",
    # PySide6 / Qt — módulos que PyInstaller no detecta automáticamente porque
    # se usan desde QML, no desde código Python importado estáticamente.
    # QtSvg: requerido por libqsvg.so (imageformats plugin). Sin él el plugin
    # carga pero falla al intentar usar libQt6Svg.so.6 → todos los SVGs
    # del UI quedan en blanco sin ningún error visible.
    "PySide6.QtSvg",
    # QtXml: requerido internamente por QtSvg para parsear SVG files.
    "PySide6.QtXml",
    # UI bridge: instanciado desde QML.
    "ui.modelos_qml",
    # Servicios de aplicacion.
    "servicios.reproductor",
    "servicios.biblioteca",
    "servicios.importacion",
    "servicios.indexador",
    # Ecosistema movil: servidor de sincronizacion local + repositorio de sync.
    # Se importan lazy desde el modelo Qt, por lo que PyInstaller no los
    # detecta por analisis estatico. Sin esto, abrir la Vista de
    # Sincronizacion en un bundle falla con "No module named ...".
    "servicios.servidor_sync",
    "servicios.sync_repositorio",
    "servicios.backup",
    "infra.tls_local",
    "servicios.karaoke",
    "servicios.karaoke.backend",
    "servicios.karaoke.modelo",
    "servicios.karaoke.separador",
    "servicios.dj_privado",
    "servicios.dj_privado.mix_engine",
    "servicios.dj_privado.reproductor_sesion",
    "servicios.dj_privado.embeddings",
    "servicios.explorador_ciego",
    # Workers Qt.
    "workers.workers_qt",
    # Infraestructura.
    "infra.bootstrap",
    "infra.execution_control",
    "infra.logger",
    "infra.version",
    "infra.processed",
    "infra.progress",
    "infra.quarantine",
    "infra.reports",
    # Pipeline.
    "core.pipeline",
    "core.audio_intelligence_background",
    "core.audio_intelligence_deep",
    "core.audio_intelligence_deep_subprocess",
    "core.music_discovery_service",
    "core.import_recovery_service",
    # Daemon de subprocess para análisis deep aislado de la UI.
    # Empacarlo como hidden import garantiza que `python -m infra.deep_runner`
    # encuentre el módulo cuando el bundle lo ejecuta con el Python externo
    # del sistema apuntando al PYTHONPATH del bundle.
    "infra.deep_runner",
    # Persistencia.
    "config.settings",
    "db.conexion",
    "db.esquema",
    "domain.models",
]

# Paquetes con submodulos cargados dinamicamente que `Analysis` no detecta.
_DYNAMIC_SUBMODULES = (
    "librosa",
    "demucs",
    # `demucs.pretrained` carga `dora.log` que a su vez importa
    # `submitit.core.logger`. Ese módulo hace `import logging.config`.
    # Sin recoger los submódulos transitivos, PyInstaller pierde
    # algunos por analisis estatico y la primera carga del modelo
    # falla con "No module named 'logging.config'" o similar.
    "dora",
    "submitit",
    # Ecosistema movil: aiohttp/zeroconf cargan submodulos dinamicamente
    # (routers, protocolos, async_) que el analisis estatico pierde.
    "aiohttp",
    "zeroconf",
    "qrcode",
    "cryptography",
)


def collect_extra_datas() -> list[tuple[str, str]]:
    extras: list[tuple[str, str]] = []
    for paquete in _OPTIONAL_DATA_PACKAGES:
        try:
            extras.extend(collect_data_files(paquete))
        except Exception:
            # paquete opcional ausente en el builder
            pass
    return extras


def hidden_imports() -> list[str]:
    imports = list(_HIDDEN_IMPORTS_BASE)
    for paquete in _DYNAMIC_SUBMODULES:
        try:
            imports.extend(collect_submodules(paquete))
        except Exception:
            pass
    return imports


# Modulos pesados que JAMAS deben entrar al bundle aunque PyInstaller los
# detecte como dependencia indirecta (vienen de librerias de tests, examples,
# o gui alternativos que no usamos).
#
# NO incluir `unittest` ni `test` aquí: aunque parezcan solo de tests,
# librosa, soundfile y otras libs científicas hacen `import unittest` o
# `import unittest.mock` para asserts internos y patching dinámico. Si
# se excluyen, `import librosa` funciona pero `librosa.load(...)` falla
# con `ModuleNotFoundError: No module named 'unittest'`, dejando todos
# los análisis de audio features en estado `failed` (síntoma observado
# en logs reales: 1984 archivos importados, 0 features generados).
EXCLUDES = [
    "tkinter",
    "matplotlib",
    "PySide6.QtWebEngine",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.Qt3D",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtTest",
]


# Librerías de bajo nivel que PyInstaller copia automáticamente al bundle Linux
# pero que provocan corrupción ABI cuando el sistema del usuario es más reciente
# que el del builder (Ubuntu 22.04 en CI vs distros derivadas de Ubuntu 24+):
#
#   - libvlc.so.5 / libvlccore.so.9
#     Si están bundled, libvlc del sistema termina cargando libvlccore del
#     bundle (incompatible) -> vlc.Instance() devuelve None.
#     La app declara `Depends: vlc` en .deb/.rpm, así que VLC siempre estará
#     en el sistema; no necesitamos empaquetarlo.
#
#   - libstdc++.so.6 / libgcc_s.so.1
#     Son la runtime de C++/GCC. El bundle suele traer una versión más vieja
#     (Ubuntu 22.04 -> GLIBCXX_3.4.30) que la del sistema del usuario
#     (Ubuntu 24.04+ -> GLIBCXX_3.4.33). Cuando libEGL/Mesa del sistema se
#     enlaza contra la versión vieja del bundle faltan símbolos, lo que
#     hace que Qt reporte "EGL not available" y la GUI no arranque.
#
#   - libdbus-1.so.3 / libsystemd.so.0
#     Servicios del sistema. Mezclar bundled vs system rompe la integración
#     d-bus de Qt y la inicialización de libvlc.
#
#   - libgcrypt.so.20 / libgpg-error.so.0 / libidn.so.12 / libcap.so.2 /
#     libcrypto.so.3 / liblz4.so.1 / liblzma.so.5 / libzstd.so.1
#     Son arrastradas por libvlc y libsystemd. Mantenerlas bundled deja
#     mezclas ABI; quitarlas asegura que el dynamic linker resuelva todo
#     desde /usr/lib/x86_64-linux-gnu de forma consistente.
#
# Todas estas librerías son parte del baseline de cualquier distro Linux con
# escritorio: están instaladas por el propio sistema operativo y no por la app.
# Excluirlas del bundle es la solución estándar para apps PyInstaller en Linux.
_LINUX_LIBS_DEL_SISTEMA = frozenset({
    "libvlc.so.5",
    "libvlccore.so.9",
    "libstdc++.so.6",
    "libgcc_s.so.1",
    "libdbus-1.so.3",
    "libsystemd.so.0",
    "libgcrypt.so.20",
    "libgpg-error.so.0",
    "libidn.so.12",
    "libidn2.so.0",
    "libcap.so.2",
    "libcrypto.so.3",
    "libssl.so.3",
    "liblz4.so.1",
    "liblzma.so.5",
    "libzstd.so.1",
    "libapparmor.so.1",
})


def filter_linux_system_libs(binaries):
    """Elimina del bundle Linux las libs que deben venir del sistema del usuario.

    Recorre la lista ``binaries`` de PyInstaller y descarta las entradas cuyo
    nombre base coincide con :data:`_LINUX_LIBS_DEL_SISTEMA`. PyInstaller
    expone ``binaries`` como lista de tuplas ``(dest, src, type)`` ó
    ``(dest, src)`` según versión; en ambos casos basta inspeccionar el
    primer elemento.

    Es seguro llamar a esta función en plataformas no-Linux (no filtra nada
    porque las libs son específicas de Linux).
    """
    resultado = []
    for entrada in binaries:
        if not entrada:
            continue
        dest = entrada[0]
        nombre = Path(dest).name
        if nombre in _LINUX_LIBS_DEL_SISTEMA:
            continue
        resultado.append(entrada)
    return resultado


def collect_external_tools(root: Path) -> list[tuple[str, str]]:
    """Localiza ejecutables externos preparados por el CI bajo `external_bin/`.

    El CI descarga `ffmpeg` y `fpcalc` para cada SO en `<root>/external_bin/`
    antes de invocar PyInstaller. Se incluyen como **datas** (no como binaries)
    con destino ``bin/`` para que ``infra.binarios.resolver_bin`` los encuentre
    en ``sys._MEIPASS/bin/``.

    Por que datas y no binaries:
      PyInstaller procesa `binaries` como librerias compartidas (.so/.dylib/.dll)
      y puede relocalizarlos o no incluirlos si no detecta dependencias. Los
      ejecutables standalone (ffmpeg, fpcalc) deben ir como `datas` para que
      PyInstaller los copie sin modificacion en la ruta destino declarada.

    Si la carpeta no existe (build de desarrollo), devuelve lista vacia y la
    app usa las herramientas del PATH del sistema.
    """
    fuente = root / "external_bin"
    if not fuente.is_dir():
        return []
    return [(str(archivo), "bin") for archivo in fuente.iterdir()
            if archivo.is_file()]


def _runtime_hooks(root: Path) -> list[str]:
    """Runtime hooks que el bootloader ejecuta antes de cualquier import."""
    hooks = []
    # Windows: redirige sys.stdout/stderr a os.devnull en apps GUI (console=False).
    # Sin esto, cualquier codigo que llame sys.stdout.isatty() al importar un modulo
    # falla con AttributeError: 'NoneType' object has no attribute 'isatty'.
    win_stdio_hook = root / "packaging" / "pyi_rth_windows_stdio.py"
    if win_stdio_hook.exists():
        hooks.append(str(win_stdio_hook))
    # Linux: corrige LD_LIBRARY_PATH para que libvlc encuentre sus dependencias
    # del sistema sin que las librerias del bundle (numba/scipy/llvmlite) interfieran.
    linux_vlc_hook = root / "packaging" / "pyi_rth_linux_vlc.py"
    if linux_vlc_hook.exists():
        hooks.append(str(linux_vlc_hook))
    return hooks


def build_analysis(root: Path, extra_datas: list[tuple[str, str]] | None = None,
                  extra_hidden: list[str] | None = None,
                  extra_excludes: list[str] | None = None):
    """Crea un Analysis listo para usar en cualquiera de los specs."""
    from PyInstaller.building.build_main import Analysis  # type: ignore
    datas = base_datas(root) + collect_extra_datas() + collect_external_tools(root)
    if extra_datas:
        datas.extend(extra_datas)
    hi = hidden_imports()
    if extra_hidden:
        hi.extend(extra_hidden)
    excludes = list(EXCLUDES)
    if extra_excludes:
        excludes.extend(extra_excludes)
    return Analysis(
        [str(root / "main_ui.py")],
        pathex=[str(root)],
        binaries=[],
        datas=datas,
        hiddenimports=hi,
        hookspath=[],
        runtime_hooks=_runtime_hooks(root),
        excludes=excludes,
        noarchive=False,
    )


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return sys.platform.startswith("linux")
