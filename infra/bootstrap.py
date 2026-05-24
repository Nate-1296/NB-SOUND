# =============================================================================
# infra/bootstrap.py
#
# Inicializacion idempotente del entorno de NB SOUND en primer arranque.
#
# Resuelve rutas estandar por sistema operativo y garantiza que los
# directorios existan antes de que la aplicacion intente usarlos. Tambien
# genera un archivo .env minimo cuando no existe, para que la primera
# ejecucion tras instalar no requiera configuracion manual.
#
# Reglas:
#   - Idempotente: ejecutar varias veces es seguro y no destructivo.
#   - No sobreescribe configuracion existente del usuario (.env, dirs).
#   - Falla silenciosa: si no puede crear un directorio (permisos,
#     filesystem read-only) reporta pero deja que la app se inicie en
#     modo degradado.
# =============================================================================

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# -----------------------------------------------------------------------------
# Constantes de plataforma
# -----------------------------------------------------------------------------

_SO = platform.system()


@dataclass(frozen=True)
class RutasEstandar:
    """Conjunto de rutas estandar para una instalacion limpia.

    Todas son absolutas. No se crean al construir el objeto: el caller
    decide cuales crear y cuando, lo que permite usarlo en tests sin
    tocar el filesystem.
    """
    home: Path
    library: Path
    input_dir: Path
    quarantine: Path
    review: Path
    logs: Path
    processed: Path
    cache: Path
    temp: Path
    assets: Path
    manifests: Path
    config: Path
    env_file: Path


# -----------------------------------------------------------------------------
# Resolucion de rutas por SO
# -----------------------------------------------------------------------------

def _home() -> Path:
    return Path.home()


def _xdg(nombre_var: str, default: Path) -> Path:
    """Devuelve la ruta XDG (Linux/macOS) o un fallback razonable."""
    valor = os.environ.get(nombre_var, "").strip()
    if valor:
        return Path(valor).expanduser()
    return default


def resolver_rutas_estandar(home: Optional[Path] = None,
                            so: Optional[str] = None) -> RutasEstandar:
    """Resuelve las rutas estandar para el SO actual o el indicado.

    Permite pasar home/so explicitos para tests. Si no se pasan, usa
    los del entorno real.

    Linux:
      datos      -> $XDG_DATA_HOME (~/.local/share/nb_sound)
      cache      -> $XDG_CACHE_HOME (~/.cache/nb_sound)
      config     -> $XDG_CONFIG_HOME (~/.config/nb_sound)
      musica     -> ~/Music (estandar XDG)

    Windows:
      datos      -> %LOCALAPPDATA%/NBSound  (fallback %APPDATA%)
      cache      -> %LOCALAPPDATA%/NBSound/Cache
      config     -> %APPDATA%/NBSound
      musica     -> %USERPROFILE%/Music

    macOS:
      datos      -> ~/Library/Application Support/NBSound
      cache      -> ~/Library/Caches/NBSound
      config     -> ~/Library/Preferences/NBSound
      musica     -> ~/Music
    """
    home = home or _home()
    so = (so or _SO).lower()
    import tempfile

    if so.startswith("win"):
        local = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        roaming = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
        datos = local / "NBSound"
        cache = local / "NBSound" / "Cache"
        config = roaming / "NBSound"
        musica = home / "Music"
    elif so == "darwin" or so == "mac":
        datos = home / "Library" / "Application Support" / "NBSound"
        cache = home / "Library" / "Caches" / "NBSound"
        config = home / "Library" / "Preferences" / "NBSound"
        musica = home / "Music"
    else:
        datos = _xdg("XDG_DATA_HOME", home / ".local" / "share") / "nb_sound"
        cache = _xdg("XDG_CACHE_HOME", home / ".cache") / "nb_sound"
        config = _xdg("XDG_CONFIG_HOME", home / ".config") / "nb_sound"
        musica = _xdg("XDG_MUSIC_DIR", home / "Music")

    return RutasEstandar(
        home=home,
        library=datos / "biblioteca",
        input_dir=musica / "NBSound_Entrada",
        quarantine=datos / "cuarentena",
        review=datos / "revision",
        logs=datos / "logs",
        processed=datos / "procesados",
        cache=cache,
        temp=Path(tempfile.gettempdir()) / "nb_sound",
        assets=datos / "assets",
        manifests=datos / "manifests",
        config=config,
        env_file=config / ".env",
    )


# -----------------------------------------------------------------------------
# Creacion de directorios y archivos iniciales
# -----------------------------------------------------------------------------

@dataclass
class ResultadoBootstrap:
    creados: list[Path]
    existentes: list[Path]
    errores: list[str]
    env_generado: bool

    @property
    def ok(self) -> bool:
        return not self.errores


def _crear_directorio(ruta: Path) -> tuple[bool, bool, Optional[str]]:
    """Crea ``ruta`` si no existe. Devuelve (creado, ya_existia, error)."""
    if ruta.exists():
        if not ruta.is_dir():
            return (False, True, f"{ruta} existe pero no es directorio")
        return (False, True, None)
    try:
        ruta.mkdir(parents=True, exist_ok=True)
        return (True, False, None)
    except OSError as exc:
        return (False, False, f"{ruta}: {exc}")


_PLANTILLA_ENV_INICIAL = """\
# NB Sound — archivo generado automaticamente en el primer arranque.
# Las rutas apuntan a directorios estandar del sistema operativo.
# Puedes editar este archivo libremente o usar la pantalla Configuracion
# de la UI para ajustarlas; ambas rutas se mantienen sincronizadas.

USER_INPUT_DIR={input_dir}
USER_LIBRARY_DIR={library}
USER_QUARANTINE_DIR={quarantine}
USER_REVIEW_DIR={review}
USER_LOGS_DIR={logs}
USER_PROCESSED_DIR={processed}
USER_CACHE_DIR={cache}
USER_TEMP_DIR={temp}
USER_ASSETS_DIR={assets}
USER_MANIFESTS_DIR={manifests}
"""


def _generar_env_si_falta(rutas: RutasEstandar,
                          env_destino: Path) -> tuple[bool, Optional[str]]:
    """Genera un .env minimo solo si no existe ya en el destino indicado."""
    if env_destino.exists():
        return (False, None)
    try:
        env_destino.parent.mkdir(parents=True, exist_ok=True)
        contenido = _PLANTILLA_ENV_INICIAL.format(
            input_dir=rutas.input_dir,
            library=rutas.library,
            quarantine=rutas.quarantine,
            review=rutas.review,
            logs=rutas.logs,
            processed=rutas.processed,
            cache=rutas.cache,
            temp=rutas.temp,
            assets=rutas.assets,
            manifests=rutas.manifests,
        )
        env_destino.write_text(contenido, encoding="utf-8")
        return (True, None)
    except OSError as exc:
        return (False, f"No se pudo escribir {env_destino}: {exc}")


def asegurar_entorno(rutas: Optional[RutasEstandar] = None,
                     *,
                     generar_env: bool = False,
                     env_destino: Optional[Path] = None) -> ResultadoBootstrap:
    """Crea los directorios estandar si no existen y, opcionalmente, .env.

    El flag ``generar_env`` es opt-in porque la mayoria de usuarios ya
    tendran configuracion previa: en CI o en instalaciones empaquetadas
    se llama explicitamente cuando el caller detecta que no hay .env.
    """
    rutas = rutas or resolver_rutas_estandar()
    creados: list[Path] = []
    existentes: list[Path] = []
    errores: list[str] = []

    for directorio in (
        rutas.library,
        rutas.input_dir,
        rutas.quarantine,
        rutas.review,
        rutas.logs,
        rutas.processed,
        rutas.cache,
        rutas.temp,
        rutas.assets,
        rutas.manifests,
        rutas.config,
    ):
        creado, ya_existia, error = _crear_directorio(directorio)
        if error:
            errores.append(error)
            continue
        if creado:
            creados.append(directorio)
        elif ya_existia:
            existentes.append(directorio)

    env_generado = False
    if generar_env:
        destino = env_destino or rutas.env_file
        env_generado, env_error = _generar_env_si_falta(rutas, destino)
        if env_error:
            errores.append(env_error)

    return ResultadoBootstrap(
        creados=creados,
        existentes=existentes,
        errores=errores,
        env_generado=env_generado,
    )


# -----------------------------------------------------------------------------
# Helper: lo invoca main_ui en primer arranque cuando faltan rutas claves.
# -----------------------------------------------------------------------------

def primer_arranque_necesario(env_existe: bool,
                              library_resuelta: Optional[Path]) -> bool:
    """Heuristica para decidir si conviene generar configuracion inicial.

    Activa el bootstrap solo cuando la app esta partiendo de cero:
      - no hay .env en el directorio del proyecto, y
      - settings no logro resolver USER_LIBRARY_DIR (config['DEFAULT_LIBRARY_DIR']).

    En cualquier otro caso se asume que el usuario ya tiene su entorno
    configurado y no se interviene.
    """
    if env_existe:
        return False
    if library_resuelta is not None:
        return False
    return True


def emitir_resumen(resultado: ResultadoBootstrap, stream=None) -> None:
    """Imprime un resumen compacto del bootstrap. Util en CLI/primer arranque."""
    stream = stream or sys.stderr
    if resultado.creados:
        print(
            f"[nb_sound] Inicializadas {len(resultado.creados)} carpetas de datos.",
            file=stream,
        )
    if resultado.env_generado:
        print(
            "[nb_sound] Generado archivo de configuracion inicial.",
            file=stream,
        )
    for err in resultado.errores:
        print(f"[nb_sound] AVISO: {err}", file=stream)
