# =============================================================================
# infra/modelos_essentia.py
#
# Catálogo de modelos Essentia que NB Sound usa para "Audio Intelligence
# profunda" + lógica de descarga directa desde el repositorio oficial.
#
# Política de descarga
# --------------------
# - NO abrimos una URL en el navegador del usuario: descargamos por
#   HTTP a la carpeta configurada en
#   `settings.AUDIO_INTELLIGENCE_MODEL_DIR`, igual que haría el usuario
#   con `wget` en una terminal.
# - Si un archivo ya está presente y tiene tamaño >0, no se vuelve a bajar.
# - Si falla algún archivo, los demás siguen y al final se reporta cuáles
#   fallaron para reintentar selectivamente.
# - Cada modelo `.pb` viene acompañado por su `.json` de metadata, que
#   Essentia consume para mapear índices a etiquetas; descargamos ambos.
# =============================================================================

from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from infra.logger import obtener_logger

_log = obtener_logger("modelos_essentia")


# URL base oficial. El path de cada modelo se concatena a esta raíz.
_BASE_URL = "https://essentia.upf.edu/models"


@dataclass(frozen=True)
class ModeloEssentia:
    """Un archivo .pb (modelo TF) con su .json de metadata."""
    archivo_pb: str            # nombre final en disco, ej: "msd-musicnn-1.pb"
    archivo_json: str          # nombre final en disco, ej: "msd-musicnn-1.json"
    ruta_remota: str           # path remoto sin extensión, ej: "feature-extractors/musicnn/msd-musicnn-1"
    funcion: str               # descripción humana para el usuario


# Lista canónica. Mantener sincronizada con el subconjunto que el pipeline
# de NB Sound consulta. Si en el futuro se agregan más modelos a la app,
# añadirlos aquí también.
CATALOGO: tuple[ModeloEssentia, ...] = (
    # Feature extractors (necesarios como "embeddings input" de los clasificadores)
    ModeloEssentia(
        archivo_pb="msd-musicnn-1.pb",
        archivo_json="msd-musicnn-1.json",
        ruta_remota="feature-extractors/musicnn/msd-musicnn-1",
        funcion="Embeddings musicnn (input para mood/genre)",
    ),
    ModeloEssentia(
        archivo_pb="discogs-effnet-bs64-1.pb",
        archivo_json="discogs-effnet-bs64-1.json",
        ruta_remota="feature-extractors/discogs-effnet/discogs-effnet-bs64-1",
        funcion="Embeddings effnet (input para genre_discogs400)",
    ),
    ModeloEssentia(
        archivo_pb="audioset-vggish-3.pb",
        archivo_json="audioset-vggish-3.json",
        ruta_remota="feature-extractors/vggish/audioset-vggish-3",
        funcion="Embeddings VGGish (AudioSet)",
    ),
    # Genre / mood classifiers
    ModeloEssentia(
        archivo_pb="genre_discogs400-discogs-effnet-1.pb",
        archivo_json="genre_discogs400-discogs-effnet-1.json",
        ruta_remota="classification-heads/genre_discogs400/genre_discogs400-discogs-effnet-1",
        funcion="Clasificación de género Discogs 400",
    ),
    ModeloEssentia(
        archivo_pb="danceability-msd-musicnn-1.pb",
        archivo_json="danceability-msd-musicnn-1.json",
        ruta_remota="classification-heads/danceability/danceability-msd-musicnn-1",
        funcion="Bailabilidad",
    ),
    ModeloEssentia(
        archivo_pb="deam-msd-musicnn-2.pb",
        archivo_json="deam-msd-musicnn-2.json",
        ruta_remota="classification-heads/deam/deam-msd-musicnn-2",
        funcion="Valencia/arousal (DEAM)",
    ),
    ModeloEssentia(
        archivo_pb="mood_aggressive-msd-musicnn-1.pb",
        archivo_json="mood_aggressive-msd-musicnn-1.json",
        ruta_remota="classification-heads/mood_aggressive/mood_aggressive-msd-musicnn-1",
        funcion="Mood: agresividad",
    ),
    ModeloEssentia(
        archivo_pb="mood_happy-msd-musicnn-1.pb",
        archivo_json="mood_happy-msd-musicnn-1.json",
        ruta_remota="classification-heads/mood_happy/mood_happy-msd-musicnn-1",
        funcion="Mood: alegría",
    ),
    ModeloEssentia(
        archivo_pb="mood_party-msd-musicnn-1.pb",
        archivo_json="mood_party-msd-musicnn-1.json",
        ruta_remota="classification-heads/mood_party/mood_party-msd-musicnn-1",
        funcion="Mood: fiesta",
    ),
    ModeloEssentia(
        archivo_pb="mood_relaxed-msd-musicnn-1.pb",
        archivo_json="mood_relaxed-msd-musicnn-1.json",
        ruta_remota="classification-heads/mood_relaxed/mood_relaxed-msd-musicnn-1",
        funcion="Mood: relajado",
    ),
    ModeloEssentia(
        archivo_pb="mood_sad-msd-musicnn-1.pb",
        archivo_json="mood_sad-msd-musicnn-1.json",
        ruta_remota="classification-heads/mood_sad/mood_sad-msd-musicnn-1",
        funcion="Mood: tristeza",
    ),
)


@dataclass
class EstadoModelos:
    """Snapshot del estado de la carpeta de modelos."""
    carpeta: Path
    presentes: list[str]   # nombres .pb presentes en carpeta
    faltantes: list[str]   # nombres .pb del catalogo que faltan
    total: int

    @property
    def completo(self) -> bool:
        return not self.faltantes

    def a_dict(self) -> dict:
        return {
            "carpeta": str(self.carpeta),
            "presentes": list(self.presentes),
            "faltantes": list(self.faltantes),
            "total": self.total,
            "completo": self.completo,
        }


# -----------------------------------------------------------------------------
# Verificación
# -----------------------------------------------------------------------------

def carpeta_actual() -> Optional[Path]:
    """Carpeta donde el usuario quiere los modelos.

    Lee del módulo settings (sincronizado con `audio_intelligence_model_dir`
    de la UI). Si está vacío, cae a `<DEFAULT_ASSETS_DIR>/modelos_essentia`.
    Devuelve None solo si tampoco se puede resolver assets (instalación rota).
    """
    try:
        from config import settings
    except Exception:
        return None
    raw = (getattr(settings, "AUDIO_INTELLIGENCE_MODEL_DIR", "") or "").strip()
    if raw:
        try:
            return Path(raw).expanduser().resolve()
        except Exception:
            return None
    base = getattr(settings, "DEFAULT_ASSETS_DIR", None)
    if base is None:
        return None
    try:
        return Path(base).expanduser().resolve() / "modelos_essentia"
    except Exception:
        return None


def verificar(carpeta: Optional[Path] = None) -> EstadoModelos:
    """Inspecciona ``carpeta`` (default: la configurada) y reporta qué
    modelos del catálogo están presentes vs. faltantes.

    No descarga nada. Es seguro llamar repetidamente: la única IO es
    `Path.exists()` por archivo.
    """
    base = carpeta or carpeta_actual()
    presentes: list[str] = []
    faltantes: list[str] = []
    if base is None or not base.is_dir():
        # Carpeta inexistente: TODO el catálogo es faltante.
        return EstadoModelos(
            carpeta=base or Path(""),
            presentes=[],
            faltantes=[m.archivo_pb for m in CATALOGO],
            total=len(CATALOGO),
        )
    for modelo in CATALOGO:
        ruta_pb = base / modelo.archivo_pb
        if ruta_pb.is_file() and ruta_pb.stat().st_size > 0:
            presentes.append(modelo.archivo_pb)
        else:
            faltantes.append(modelo.archivo_pb)
    return EstadoModelos(
        carpeta=base,
        presentes=presentes,
        faltantes=faltantes,
        total=len(CATALOGO),
    )


# -----------------------------------------------------------------------------
# Descarga
# -----------------------------------------------------------------------------

def _descargar_a(url: str, destino: Path, *,
                 timeout: float = 60.0,
                 reintentos: int = 2,
                 en_progreso: Optional[Callable[[int, int], None]] = None) -> Optional[str]:
    """Descarga ``url`` a ``destino``. Devuelve None en éxito, str con error
    en fallo. Implementa reintentos exponenciales para tolerar fallos de
    red transitorios sin abandonar la sesión completa.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    intento = 0
    ultimo_error = ""
    while intento <= reintentos:
        intento += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NB-Sound/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                leido = 0
                tmp = destino.with_suffix(destino.suffix + ".tmp")
                with open(tmp, "wb") as fh:
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
                tmp.replace(destino)
            return None
        except urllib.error.HTTPError as exc:
            ultimo_error = f"HTTP {exc.code}: {exc.reason}"
            if 400 <= exc.code < 500 and exc.code != 408:
                # 4xx (excepto Request Timeout): no reintentar, no va a cambiar.
                break
        except Exception as exc:
            ultimo_error = str(exc)
        if intento <= reintentos:
            # Backoff exponencial: 1s, 2s.
            time.sleep(min(2 ** (intento - 1), 5))
    return ultimo_error or "error desconocido"


@dataclass
class ResultadoDescarga:
    descargados: list[str]
    fallidos: dict[str, str]   # archivo -> error
    omitidos: list[str]        # ya presentes en disco
    carpeta: Path

    @property
    def ok(self) -> bool:
        return not self.fallidos


def descargar_faltantes(
    *,
    carpeta: Optional[Path] = None,
    en_archivo: Optional[Callable[[str, int, int], None]] = None,
    en_mensaje: Optional[Callable[[str], None]] = None,
) -> ResultadoDescarga:
    """Descarga los modelos del catálogo que falten en ``carpeta``.

    Args:
        carpeta: destino (default: la configurada por el usuario).
        en_archivo: callback (archivo, bytes_leidos, bytes_totales)
                    para reportar progreso en la UI.
        en_mensaje: callback (linea) para mensajes de estado tipo log.

    Returns:
        ResultadoDescarga con la lista de descargados / omitidos /
        fallidos. Si todo va bien `ok == True`. Si falla algo, los
        archivos fallidos quedan en `fallidos` y el usuario puede
        invocar de nuevo para que reintente sólo esos.
    """
    base = (carpeta or carpeta_actual())
    if base is None:
        return ResultadoDescarga(
            descargados=[], fallidos={}, omitidos=[],
            carpeta=Path(""),
        )
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return ResultadoDescarga(
            descargados=[], fallidos={"__carpeta__": str(exc)},
            omitidos=[], carpeta=base,
        )

    descargados: list[str] = []
    fallidos: dict[str, str] = {}
    omitidos: list[str] = []

    def _emit(msg: str) -> None:
        if en_mensaje is not None:
            try:
                en_mensaje(msg)
            except Exception:
                pass
        _log.info(msg)

    _emit(f"Carpeta destino: {base}")

    for modelo in CATALOGO:
        # 1) .pb principal
        ruta_pb = base / modelo.archivo_pb
        ruta_json = base / modelo.archivo_json
        if ruta_pb.is_file() and ruta_pb.stat().st_size > 0:
            omitidos.append(modelo.archivo_pb)
            _emit(f"OK ya existe: {modelo.archivo_pb}")
            # Aún así, intentar bajar el .json si no está (es pequeño).
            if not ruta_json.is_file():
                url_json = f"{_BASE_URL}/{modelo.ruta_remota}.json"
                _emit(f"Descargando metadata: {modelo.archivo_json}")
                err_j = _descargar_a(url_json, ruta_json)
                if err_j:
                    # No tan critico: el .json es opcional; lo registramos pero
                    # no marcamos el modelo como fallido.
                    _emit(f"AVISO {modelo.archivo_json}: {err_j}")
            continue

        url_pb = f"{_BASE_URL}/{modelo.ruta_remota}.pb"
        url_json = f"{_BASE_URL}/{modelo.ruta_remota}.json"
        _emit(f"Descargando: {modelo.archivo_pb}")

        def _cb(leido: int, total: int, _nombre=modelo.archivo_pb) -> None:
            if en_archivo is not None:
                try:
                    en_archivo(_nombre, leido, total)
                except Exception:
                    pass

        err = _descargar_a(url_pb, ruta_pb, en_progreso=_cb)
        if err:
            fallidos[modelo.archivo_pb] = err
            _emit(f"FALLO {modelo.archivo_pb}: {err}")
            continue

        # .json es metadata pequeño; si falla es no-fatal.
        err_j = _descargar_a(url_json, ruta_json)
        if err_j:
            _emit(f"AVISO {modelo.archivo_json}: {err_j}")

        descargados.append(modelo.archivo_pb)
        _emit(f"OK {modelo.archivo_pb}")

    if not fallidos:
        _emit(f"Descarga completa. {len(descargados)} nuevos, {len(omitidos)} ya estaban.")
    else:
        _emit(f"Descarga incompleta. {len(fallidos)} fallidos: " + ", ".join(fallidos.keys()))

    return ResultadoDescarga(
        descargados=descargados,
        fallidos=fallidos,
        omitidos=omitidos,
        carpeta=base,
    )
