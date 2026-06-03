"""PyInstaller runtime hook — Linux library path & VLC bootstrap.

Executed by the PyInstaller bootloader before any Python import.

Why this exists
---------------
The PyInstaller bootloader prepends ``sys._MEIPASS`` (the bundle's ``_internal``
directory) to ``LD_LIBRARY_PATH`` so that bundled ``.so`` files are loaded
before system ones. That is correct for libraries the bundle owns
(``libQt6*.so``, ``libpython*.so``, NumPy/SciPy native code, …) but is
**fatal** for low-level system libraries that the app does not own:

  * ``libvlc.so.5`` / ``libvlccore.so.9`` — if the bundle ships these (eg.
    because PyInstaller's analysis pulled them in via ``python-vlc``), the
    dynamic linker will load *system* libvlc with *bundled* libvlccore (or
    vice-versa). The two come from different distros / different ABIs, and
    the symptom is ``vlc.Instance(...)`` returning ``None`` — followed by
    ``AttributeError: 'NoneType' object has no attribute 'media_player_new'``.

  * ``libstdc++.so.6`` / ``libgcc_s.so.1`` — the bundle ships the version
    from the CI builder (Ubuntu 22.04 → ``GLIBCXX_3.4.30``). Pop!_OS,
    Ubuntu 24.04, Fedora 40+ ship newer ones (``GLIBCXX_3.4.33``). When
    system ``libEGL`` / Mesa is compiled against the newer ``libstdc++``
    and gets paired with the older bundled copy, EGL initialization fails
    silently and Qt reports ``qt.qpa.wayland: EGL not available``, falling
    back to the software renderer (which cannot composite ColorOverlay /
    MultiEffect — every themed SVG icon ends up invisible).

  * ``libdbus-1.so.3`` / ``libsystemd.so.0`` — same problem, propagated to
    VLC and Qt D-Bus integration.

The build pipeline (``packaging/_common.filter_linux_system_libs``) already
strips these libraries from the bundle, so the dynamic linker can never find
them under ``_MEIPASS``. This hook is the runtime counterpart: it ensures
that the *system* paths are searchable and points ``python-vlc`` explicitly
at the system ``libvlc.so.5``.

Defensive measures (order matters)
----------------------------------
1. **Pre-load system Mesa** ``libGL.so.1`` / ``libEGL.so.1`` with
   ``RTLD_GLOBAL`` so their symbols are already resolved by the time Qt's
   ``xcb`` / ``wayland`` platform plugins are dlopen-ed. This works even if
   ``LD_LIBRARY_PATH`` ordering is unfavourable, because the dynamic linker
   reuses already-loaded libraries by ``DT_SONAME``.

2. **Append system library directories** to ``LD_LIBRARY_PATH`` *after* the
   bundle path. Anything not in the bundle (because we filtered it out) is
   then found in ``/usr/lib`` / ``/lib`` automatically.

3. **Point python-vlc** to the absolute path of the system libvlc via
   ``PYTHON_VLC_LIB_PATH``. The python-vlc binding reads this before
   anything else, so even if ``ctypes`` would otherwise pick a bundled
   ``libvlc.so.5`` (defence in depth — should never happen after filtering)
   it would still go to the system copy.

4. **Set ``VLC_PLUGIN_PATH``** if libvlc cannot discover its plugin folder
   from its install prefix. On most Debian/Ubuntu/Fedora installations the
   plugins live under ``/usr/lib/<arch>/vlc/plugins``.
"""

import ctypes as _ctypes
import os as _os
import sys as _sys


def _existe_archivo(ruta):
    try:
        return _os.path.isfile(ruta)
    except OSError:
        return False


def _existe_dir(ruta):
    try:
        return _os.path.isdir(ruta)
    except OSError:
        return False


def _pre_cargar_libreria(rutas_candidatas):
    """Carga la primera librería existente con RTLD_GLOBAL. Silencioso si falla.

    El objetivo no es exponer la lib al código Python sino que sus símbolos
    queden disponibles cuando Qt o libvlc se enlacen dinámicamente. Si la
    librería no existe (sistema sin Mesa, contenedor minimalista, etc.) se
    omite sin propagar excepción.
    """
    for ruta in rutas_candidatas:
        if not _existe_archivo(ruta):
            continue
        try:
            _ctypes.CDLL(ruta, mode=_ctypes.RTLD_GLOBAL)
            return ruta
        except OSError:
            # La lib existe pero no se pudo cargar — siguiente candidato.
            continue
    return None


def _bootstrap_linux():
    # ------------------------------------------------------------------
    # 1. Pre-cargar Mesa GL/EGL del sistema con RTLD_GLOBAL.
    # ------------------------------------------------------------------
    _pre_cargar_libreria([
        "/usr/lib/x86_64-linux-gnu/libGL.so.1",
        "/usr/lib64/libGL.so.1",
        "/usr/lib/aarch64-linux-gnu/libGL.so.1",
        "/lib/x86_64-linux-gnu/libGL.so.1",
        "/usr/lib/x86_64-linux-gnu/libGL.so",
    ])
    _pre_cargar_libreria([
        "/usr/lib/x86_64-linux-gnu/libEGL.so.1",
        "/usr/lib64/libEGL.so.1",
        "/usr/lib/aarch64-linux-gnu/libEGL.so.1",
        "/lib/x86_64-linux-gnu/libEGL.so.1",
        "/usr/lib/x86_64-linux-gnu/libEGL.so",
    ])

    # ------------------------------------------------------------------
    # 2. Asegurar que las rutas de sistema están en LD_LIBRARY_PATH.
    #    Se agregan al FINAL para no desplazar las del bundle (que sigue
    #    requiriendo cargar su propio Qt / Python / NumPy).
    # ------------------------------------------------------------------
    actual = _os.environ.get("LD_LIBRARY_PATH", "")
    existentes = actual.split(":") if actual else []

    candidatos_sistema = [
        "/lib/x86_64-linux-gnu",
        "/usr/lib/x86_64-linux-gnu",
        "/lib/aarch64-linux-gnu",
        "/usr/lib/aarch64-linux-gnu",
        "/lib64",
        "/usr/lib64",
        "/lib",
        "/usr/lib",
    ]
    a_agregar = [d for d in candidatos_sistema
                 if d not in existentes and _existe_dir(d)]
    if a_agregar:
        _os.environ["LD_LIBRARY_PATH"] = ":".join(existentes + a_agregar)

    # ------------------------------------------------------------------
    # 3. Dirigir python-vlc al libvlc del sistema (absoluto).
    # ------------------------------------------------------------------
    if not _os.environ.get("PYTHON_VLC_LIB_PATH"):
        for candidato in (
            "/usr/lib/x86_64-linux-gnu/libvlc.so.5",
            "/usr/lib64/libvlc.so.5",
            "/lib/x86_64-linux-gnu/libvlc.so.5",
            "/usr/lib/aarch64-linux-gnu/libvlc.so.5",
            "/lib/aarch64-linux-gnu/libvlc.so.5",
        ):
            if _existe_archivo(candidato):
                _os.environ["PYTHON_VLC_LIB_PATH"] = candidato
                break

    # ------------------------------------------------------------------
    # 4. Localizar el directorio de plugins de VLC si no está configurado.
    # ------------------------------------------------------------------
    if not _os.environ.get("VLC_PLUGIN_PATH"):
        for plugins_dir in (
            "/usr/lib/x86_64-linux-gnu/vlc/plugins",
            "/usr/lib64/vlc/plugins",
            "/usr/lib/aarch64-linux-gnu/vlc/plugins",
            "/usr/lib/vlc/plugins",
        ):
            if _existe_dir(plugins_dir):
                _os.environ["VLC_PLUGIN_PATH"] = plugins_dir
                break


if _sys.platform.startswith("linux"):
    _bootstrap_linux()
