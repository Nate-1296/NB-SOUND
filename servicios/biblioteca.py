# =============================================================================
# servicios/biblioteca.py
#
# Servicio de consulta de biblioteca.
#
# Toda operacion de lectura que la UI necesita sobre la coleccion musical
# pasa por este modulo. No hay logica de negocio aqui: solo construccion de
# consultas SQL y transformacion de resultados en dicts listos para QML.
#
# Convencion de retorno: todos los metodos devuelven listas de dict o un
# dict simple. Las claves coinciden con las propiedades que el modelo
# QML espera, para evitar transformaciones en la capa de presentacion.
# =============================================================================

import json
import hashlib
import queue
import random
import re
import sqlite3
import stat as stat_mod
import tempfile
import threading
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from config import settings as _settings
from db.conexion import obtener_filas, obtener_una_fila, ejecutar, ejecutar_y_obtener_id, transaccion
from infra.logger import obtener_logger
from utils.text import para_comparacion

logger = obtener_logger(__name__)

_GRUPOS_ALBUMS = (
    ("albums", "Álbumes"),
    ("singles_y_ep", "Singles/EP"),
    ("otros", "Otros"),
)

PLAYLIST_FAVORITOS_AUTO_KEY = "system:favoritos"
PLAYLIST_AUTO_MAX_PISTAS = 50
PLAYLIST_AUTO_TARGET_PISTAS = 30
PLAYLIST_AUTO_MIN_PISTAS = 12
PLAYLIST_AUTO_STRONG_MIN_PISTAS = 30
# "This is <artista>": tamaño objetivo 25-80. El mínimo deja de ser 50 para que
# se generen también para artistas con catálogo mediano; el tope (80) es un
# override por-spec que NO toca el cap global `PLAYLIST_AUTO_MAX_PISTAS` (50) del
# resto de playlists automáticas. `ARTISTA_MIN` es cuántas pistas propias debe
# tener un artista para habilitar su "This is" (si quedan por debajo de
# MIN_PISTAS se completa con temas similares).
PLAYLIST_AUTO_THIS_IS_MIN_PISTAS = 25
PLAYLIST_AUTO_THIS_IS_MAX_PISTAS = 80
PLAYLIST_AUTO_THIS_IS_ARTISTA_MIN = 20
PLAYLIST_AUTO_FEATURE_MIN_PISTAS = 30
PLAYLIST_AUTO_DESCUBRIR_MIN_PISTAS = 20
PLAYLIST_AUTO_TOP_MIN_REPRODUCCIONES = 60
PLAYLIST_SYNC_COOLDOWN_SEG = 20 * 60
PLAYLIST_COVER_ALGO_VERSION = "v2-visual-dedupe"


_FTS_TOKEN_RE = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)
_BUSQUEDA_STOPWORDS = {
    "a",
    "al",
    "algo",
    "by",
    "cancion",
    "canciones",
    "con",
    "de",
    "del",
    "el",
    "en",
    "la",
    "las",
    "los",
    "musica",
    "pista",
    "pon",
    "song",
    "tema",
    "the",
    "track",
    "un",
    "una",
}


def _consulta_fts_prefijo(termino: str) -> str:
    tokens = [
        token.strip("_")
        for token in _FTS_TOKEN_RE.findall(str(termino or ""))
        if token.strip("_")
    ]
    return " ".join(f"{token}*" for token in tokens)


def _tokens_busqueda(termino: str) -> list[str]:
    return [token for token in para_comparacion(termino).split() if token]


def _tokens_utiles_busqueda(termino: str) -> list[str]:
    return [token for token in _tokens_busqueda(termino) if token not in _BUSQUEDA_STOPWORDS]


def _like_seguro(valor: str) -> str:
    texto = str(valor or "")
    texto = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{texto}%"


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _cobertura_tokens(tokens: list[str], texto: str) -> float:
    if not tokens or not texto:
        return 0.0
    encontrados = 0
    texto_tokens = texto.split()
    for token in tokens:
        if token in texto:
            encontrados += 1
            continue
        if len(token) >= 4 and any(_ratio(token, candidato) >= 0.82 for candidato in texto_tokens):
            encontrados += 1
    return encontrados / max(1, len(tokens))


def _score_texto_busqueda(
    consulta_norm: str,
    tokens: list[str],
    principal_norm: str,
    secundarios_norm: list[str],
    *,
    permitir_fuzzy: bool,
) -> float:
    if not consulta_norm:
        return 0.0

    score = 0.0
    if principal_norm == consulta_norm:
        score = max(score, 10000.0)
    elif principal_norm.startswith(consulta_norm):
        score = max(score, 9000.0)
    elif consulta_norm in principal_norm:
        score = max(score, 8000.0)

    for secundario in secundarios_norm:
        if secundario == consulta_norm:
            score = max(score, 7600.0)
        elif secundario.startswith(consulta_norm):
            score = max(score, 7000.0)
        elif consulta_norm in secundario:
            score = max(score, 6400.0)

    texto_completo = " ".join([principal_norm, *secundarios_norm]).strip()
    cobertura_principal = _cobertura_tokens(tokens, principal_norm)
    cobertura_total = _cobertura_tokens(tokens, texto_completo)
    if cobertura_principal >= 0.999:
        score = max(score, 7800.0)
    elif cobertura_total >= 0.999:
        score = max(score, 7200.0)
    elif cobertura_total >= 0.67 and len(tokens) >= 2:
        score = max(score, 5600.0 + cobertura_total * 600.0)
    elif cobertura_principal > 0 and len(tokens) >= 2:
        score = max(score, 3800.0 + cobertura_principal * 500.0)

    if permitir_fuzzy:
        ratio_principal = _ratio(consulta_norm, principal_norm)
        ratio_total = _ratio(consulta_norm, texto_completo)
        ratio_mejor = max(ratio_principal, ratio_total)
        if ratio_mejor >= 0.88:
            score = max(score, 5200.0 + ratio_mejor * 1000.0)
        elif ratio_mejor >= 0.80 and cobertura_total >= 0.5:
            score = max(score, 4300.0 + ratio_mejor * 700.0)

    return score


def _score_pista_busqueda(fila: dict, termino: str) -> float:
    consulta_norm = para_comparacion(termino)
    tokens = _tokens_utiles_busqueda(termino) or _tokens_busqueda(termino)
    if not consulta_norm:
        return 0.0

    titulo_norm = para_comparacion(fila.get("titulo") or fila.get("nombre_archivo") or "")
    artista_norm = para_comparacion(fila.get("artista_nombre") or "")
    album_norm = para_comparacion(fila.get("album_titulo") or "")
    genero_norm = para_comparacion(fila.get("genero") or "")
    anio_norm = para_comparacion(str(fila.get("anio") or ""))
    permitir_fuzzy = len(consulta_norm) >= 4 and not (len(tokens) == 1 and len(tokens[0]) == 1)

    score = _score_texto_busqueda(
        consulta_norm,
        tokens,
        titulo_norm,
        [artista_norm, album_norm, genero_norm, anio_norm],
        permitir_fuzzy=permitir_fuzzy,
    )

    consulta_sin_stop = " ".join(tokens)
    texto_catalogo = " ".join(
        parte
        for parte in (titulo_norm, artista_norm, album_norm, genero_norm, anio_norm)
        if parte
    )
    if tokens and texto_catalogo and all(token in texto_catalogo for token in tokens):
        score = max(score, 6200.0 + min(900.0, len(tokens) * 160.0))
    if titulo_norm and artista_norm and titulo_norm in consulta_norm and artista_norm in consulta_norm:
        score = max(score, 9500.0)
    if titulo_norm and album_norm and titulo_norm in consulta_norm and album_norm in consulta_norm:
        score = max(score, 9000.0)
    if titulo_norm and artista_norm and consulta_sin_stop:
        combinado = f"{titulo_norm} {artista_norm}"
        inverso = f"{artista_norm} {titulo_norm}"
        if combinado.startswith(consulta_sin_stop) or inverso.startswith(consulta_sin_stop):
            score = max(score, 8800.0)

    # Las reproducciones solo desempatan entre pistas que YA coinciden con el
    # término. Aplicarlas como bonus incondicional hacía que cualquier pista muy
    # reproducida (típicamente las favoritas) superara el filtro `score > 0` sin
    # coincidir realmente, devolviendo "toda la biblioteca" en vez de los
    # resultados pertinentes. Sin match textual no hay inclusión.
    if score > 0:
        try:
            score += min(250.0, float(fila.get("veces_reproducida") or 0) * 10.0)
        except (TypeError, ValueError):
            pass
    return score


def _score_album_busqueda(fila: dict, termino: str) -> float:
    consulta_norm = para_comparacion(termino)
    tokens = _tokens_utiles_busqueda(termino) or _tokens_busqueda(termino)
    if not consulta_norm:
        return 0.0
    titulo_norm = para_comparacion(fila.get("titulo") or "")
    artista_norm = para_comparacion(fila.get("artista_nombre") or "")
    score = _score_texto_busqueda(
        consulta_norm,
        tokens,
        titulo_norm,
        [artista_norm],
        permitir_fuzzy=len(consulta_norm) >= 4,
    )
    if titulo_norm and artista_norm and titulo_norm in consulta_norm and artista_norm in consulta_norm:
        score = max(score, 9300.0)
    return score


def _score_artista_busqueda(fila: dict, termino: str) -> float:
    consulta_norm = para_comparacion(termino)
    tokens = _tokens_utiles_busqueda(termino) or _tokens_busqueda(termino)
    if not consulta_norm:
        return 0.0
    return _score_texto_busqueda(
        consulta_norm,
        tokens,
        para_comparacion(fila.get("nombre") or ""),
        [],
        permitir_fuzzy=len(consulta_norm) >= 4,
    )


_CACHE_PORTADAS_ASSETS: dict = {
    "firma": None,
    "mapa_releases": {},
    "mapa_artistas": {},
    "mapa_releases_hd": {},
    "mapa_artistas_hd": {},
}
_CACHE_PORTADAS_LOCK = threading.RLock()
_CACHE_PORTADAS_DISPLAY: dict[tuple[str, int, int, int], str] = {}
_CACHE_PORTADAS_DISPLAY_LOCK = threading.RLock()
_PORTADAS_WARMUP_QUEUE: queue.Queue[tuple[Path, object, int]] = queue.Queue(maxsize=48)
_PORTADAS_WARMUP_ENQUEUED: set[tuple[str, int, int, int]] = set()
_PORTADAS_WARMUP_THREAD: Optional[threading.Thread] = None
_PORTADAS_WARNED: set[str] = set()
_PILLOW_DISPONIBLE: Optional[bool] = None
_PLAYLIST_COVER_HASH_CACHE: dict[tuple[str, int, int], int] = {}
_PORTADA_THUMB_MAX_PX = 512


def _manifest_assets() -> Optional[Path]:
    if _settings.DEFAULT_ASSETS_DIR is None:
        return None
    return _settings.DEFAULT_ASSETS_DIR / "assets_manifest.jsonl"


def _normalizar_artista_clave(nombre: Optional[str]) -> str:
    return (nombre or "").strip().casefold()


def _mapas_assets() -> tuple[dict[str, str], dict[str, str]]:
    mapa_releases, mapa_artistas, _mapa_releases_hd, _mapa_artistas_hd = _mapas_assets_completos()
    return mapa_releases, mapa_artistas


def _mapas_assets_completos() -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    """
    Retorna mapas:
      - release_id -> portada (album_cover preferido)
      - artista(normalizado) -> avatar de artista
      - release_id -> portada HD
      - artista(normalizado) -> avatar HD
    Se cachea en memoria y se invalida por cambios de mtime/tamano del manifest.
    """
    manifest = _manifest_assets()
    if manifest is None or not manifest.exists():
        with _CACHE_PORTADAS_LOCK:
            _CACHE_PORTADAS_ASSETS["firma"] = None
            _CACHE_PORTADAS_ASSETS["mapa_releases"] = {}
            _CACHE_PORTADAS_ASSETS["mapa_artistas"] = {}
            _CACHE_PORTADAS_ASSETS["mapa_releases_hd"] = {}
            _CACHE_PORTADAS_ASSETS["mapa_artistas_hd"] = {}
            return {}, {}, {}, {}

    stat = manifest.stat()
    firma = (stat.st_mtime_ns, stat.st_size)
    with _CACHE_PORTADAS_LOCK:
        if _CACHE_PORTADAS_ASSETS["firma"] == firma:
            return (
                _CACHE_PORTADAS_ASSETS["mapa_releases"],
                _CACHE_PORTADAS_ASSETS["mapa_artistas"],
                _CACHE_PORTADAS_ASSETS.get("mapa_releases_hd", {}),
                _CACHE_PORTADAS_ASSETS.get("mapa_artistas_hd", {}),
            )

    mapa_releases: dict[str, str] = {}
    mapa_artistas: dict[str, str] = {}
    mapa_releases_hd: dict[str, str] = {}
    mapa_artistas_hd: dict[str, str] = {}
    with manifest.open("r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                row = json.loads(linea)
            except json.JSONDecodeError as e:
                logger.warning(f"Línea JSON inválida en manifest de assets (ignorada): {e}")
                continue

            release_id = str(row.get("release_id") or "").strip()
            if not release_id:
                continue

            album_cover = str(row.get("album_cover") or "").strip()
            track_cover = str(row.get("track_cover") or "").strip()
            artist_avatar = str(row.get("artist_avatar") or "").strip()
            album_cover_hd = str(row.get("album_cover_hd") or "").strip()
            track_cover_hd = str(row.get("track_cover_hd") or "").strip()
            artist_avatar_hd = str(row.get("artist_avatar_hd") or "").strip()
            artista = _normalizar_artista_clave(row.get("artista"))

            if album_cover:
                mapa_releases[release_id] = album_cover
            elif track_cover and release_id not in mapa_releases:
                mapa_releases[release_id] = track_cover

            if album_cover_hd:
                mapa_releases_hd[release_id] = album_cover_hd
            elif track_cover_hd and release_id not in mapa_releases_hd:
                mapa_releases_hd[release_id] = track_cover_hd

            if artist_avatar and artista and artista not in mapa_artistas:
                mapa_artistas[artista] = artist_avatar
            if artist_avatar_hd and artista and artista not in mapa_artistas_hd:
                mapa_artistas_hd[artista] = artist_avatar_hd

    with _CACHE_PORTADAS_LOCK:
        _CACHE_PORTADAS_ASSETS["firma"] = firma
        _CACHE_PORTADAS_ASSETS["mapa_releases"] = mapa_releases
        _CACHE_PORTADAS_ASSETS["mapa_artistas"] = mapa_artistas
        _CACHE_PORTADAS_ASSETS["mapa_releases_hd"] = mapa_releases_hd
        _CACHE_PORTADAS_ASSETS["mapa_artistas_hd"] = mapa_artistas_hd
        return mapa_releases, mapa_artistas, mapa_releases_hd, mapa_artistas_hd


def _resolver_portada_fila(
    portada_actual: Optional[str],
    mb_release_id: Optional[str],
) -> Optional[str]:
    portada = (portada_actual or "").strip()
    if portada:
        return portada

    release_id = (mb_release_id or "").strip()
    if not release_id:
        return None

    mapa_releases, _ = _mapas_assets()
    return mapa_releases.get(release_id)


def _resolver_portada_hd_fila(
    portada_hd_actual: Optional[str],
    mb_release_id: Optional[str],
) -> Optional[str]:
    portada = (portada_hd_actual or "").strip()
    if portada:
        return portada

    release_id = (mb_release_id or "").strip()
    if not release_id:
        return None

    _mapa_releases, _mapa_artistas, mapa_releases_hd, _mapa_artistas_hd = _mapas_assets_completos()
    return mapa_releases_hd.get(release_id)


def _resolver_avatar_artista(
    portada_actual: Optional[str],
    nombre_artista: Optional[str],
) -> Optional[str]:
    portada = (portada_actual or "").strip()
    if portada:
        return portada

    artista_key = _normalizar_artista_clave(nombre_artista)
    if not artista_key:
        return None

    _, mapa_artistas = _mapas_assets()
    return mapa_artistas.get(artista_key)


def _resolver_avatar_hd_artista(
    portada_hd_actual: Optional[str],
    nombre_artista: Optional[str],
) -> Optional[str]:
    portada = (portada_hd_actual or "").strip()
    if portada:
        return portada

    artista_key = _normalizar_artista_clave(nombre_artista)
    if not artista_key:
        return None

    _mapa_releases, _mapa_artistas, _mapa_releases_hd, mapa_artistas_hd = _mapas_assets_completos()
    return mapa_artistas_hd.get(artista_key)


def _warn_portada_once(clave: str, mensaje: str, *args) -> None:
    with _CACHE_PORTADAS_DISPLAY_LOCK:
        if clave in _PORTADAS_WARNED:
            return
        _PORTADAS_WARNED.add(clave)
    logger.warning(mensaje, *args)


def _pillow_disponible() -> bool:
    global _PILLOW_DISPONIBLE
    if _PILLOW_DISPONIBLE is not None:
        return _PILLOW_DISPONIBLE
    try:
        import PIL  # noqa: F401
    except ImportError:
        _PILLOW_DISPONIBLE = False
        _warn_portada_once(
            "pillow-no-disponible",
            "No se pudo sanitizar portadas de Biblioteca: Pillow no está instalado.",
        )
    else:
        _PILLOW_DISPONIBLE = True
    return _PILLOW_DISPONIBLE


def _ruta_local_portada(ruta: Optional[str]) -> Optional[Path]:
    texto = str(ruta or "").strip()
    if not texto:
        return None
    if "://" in texto:
        parsed = urlparse(texto)
        if parsed.scheme != "file":
            return None
        texto = unquote(parsed.path)
    return Path(texto).expanduser()


def _directorio_cache_portadas() -> Path:
    base = _settings.DEFAULT_CACHE_DIR or Path(tempfile.gettempdir()) / "nb_sound"
    return base / "biblioteca" / "portadas"


def _clave_cache_portada(path: Path, stat, max_px: int) -> tuple[str, int, int, int]:
    return (str(path.absolute()), int(stat.st_mtime_ns), int(stat.st_size), int(max_px))


def _ruta_cache_portada(path: Path, stat, max_px: int) -> Path:
    digest = hashlib.sha256(
        f"{path.absolute()}\0{stat.st_mtime_ns}\0{stat.st_size}\0{max_px}".encode("utf-8")
    ).hexdigest()[:28]
    return _directorio_cache_portadas() / f"{digest}_{max_px}.png"


def _crear_thumb_portada(path: Path, salida: Path, max_px: int) -> Optional[str]:
    if not _pillow_disponible():
        return str(path)

    try:
        from PIL import Image, ImageOps

        salida.parent.mkdir(parents=True, exist_ok=True)
        tmp = salida.with_name(f".{salida.name}.tmp")
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            tiene_alpha = img.mode in {"RGBA", "LA"} or (
                img.mode == "P" and "transparency" in img.info
            )
            img = img.convert("RGBA" if tiene_alpha else "RGB")
            img.info.pop("icc_profile", None)
            img.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
            img.save(tmp, format="PNG", optimize=True)
        tmp.replace(salida)
        return str(salida)
    except Exception as exc:
        try:
            if "tmp" in locals() and tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        _warn_portada_once(
            f"portada-cache:{path}",
            "No se pudo preparar portada sanitizada para Biblioteca (%s): %s",
            path,
            exc,
        )
        return ""


def _worker_warmup_portadas() -> None:
    while True:
        path, stat, max_px = _PORTADAS_WARMUP_QUEUE.get()
        clave = _clave_cache_portada(path, stat, max_px)
        try:
            salida = _ruta_cache_portada(path, stat, max_px)
            if salida.exists() and salida.stat().st_size > 0:
                display = str(salida)
            else:
                display = _crear_thumb_portada(path, salida, max_px)
            if display:
                with _CACHE_PORTADAS_DISPLAY_LOCK:
                    _CACHE_PORTADAS_DISPLAY[clave] = display
        except Exception as exc:
            _warn_portada_once(
                f"portada-warmup:{path}",
                "No se pudo precalentar portada de Biblioteca (%s): %s",
                path,
                exc,
            )
        finally:
            with _CACHE_PORTADAS_DISPLAY_LOCK:
                _PORTADAS_WARMUP_ENQUEUED.discard(clave)
            _PORTADAS_WARMUP_QUEUE.task_done()
            time.sleep(0.08)


def _asegurar_worker_warmup_portadas() -> None:
    global _PORTADAS_WARMUP_THREAD
    with _CACHE_PORTADAS_DISPLAY_LOCK:
        if _PORTADAS_WARMUP_THREAD and _PORTADAS_WARMUP_THREAD.is_alive():
            return
        _PORTADAS_WARMUP_THREAD = threading.Thread(
            target=_worker_warmup_portadas,
            name="nb-sound-cover-warmup",
            daemon=True,
        )
        _PORTADAS_WARMUP_THREAD.start()


def _programar_thumb_portada(path: Path, stat, max_px: int) -> bool:
    clave = _clave_cache_portada(path, stat, max_px)
    with _CACHE_PORTADAS_DISPLAY_LOCK:
        if clave in _CACHE_PORTADAS_DISPLAY or clave in _PORTADAS_WARMUP_ENQUEUED:
            return True
        _PORTADAS_WARMUP_ENQUEUED.add(clave)
    try:
        _PORTADAS_WARMUP_QUEUE.put_nowait((path, stat, max_px))
    except queue.Full:
        with _CACHE_PORTADAS_DISPLAY_LOCK:
            _PORTADAS_WARMUP_ENQUEUED.discard(clave)
        return False
    _asegurar_worker_warmup_portadas()
    return True


def _resolver_portada_display(
    portada_actual: Optional[str],
    max_px: int = _PORTADA_THUMB_MAX_PX,
    generar_si_falta: bool = False,
) -> str:
    texto = str(portada_actual or "").strip()
    if not texto:
        return ""

    path = _ruta_local_portada(texto)
    if path is None:
        return texto

    try:
        stat = path.stat()
    except OSError:
        return ""
    if not stat_mod.S_ISREG(stat.st_mode):
        return ""

    clave = _clave_cache_portada(path, stat, max_px)
    with _CACHE_PORTADAS_DISPLAY_LOCK:
        cached = _CACHE_PORTADAS_DISPLAY.get(clave)
        if cached is not None:
            return cached

    salida = _ruta_cache_portada(path, stat, max_px)
    programada = False
    if salida.exists() and salida.stat().st_size > 0:
        display = str(salida)
    elif generar_si_falta:
        display = _crear_thumb_portada(path, salida, max_px)
    else:
        programada = _programar_thumb_portada(path, stat, max_px)
        display = texto

    if display != texto or generar_si_falta or salida.exists() or programada:
        with _CACHE_PORTADAS_DISPLAY_LOCK:
            _CACHE_PORTADAS_DISPLAY[clave] = display
    return display


def _agregar_portada_display(item: dict, clave_portada: str = "portada_ruta") -> dict:
    portada = item.get(clave_portada)
    display = _resolver_portada_display(portada)
    item["portada_display_ruta"] = display
    item["portada_thumb_ruta"] = display if display and display != str(portada or "").strip() else ""
    return item


def _grupo_album_sql() -> str:
    return (
        "CASE "
        "WHEN lower(al.tipo) = 'album' THEN 'albums' "
        "WHEN lower(al.tipo) IN ('single', 'ep') THEN 'singles_y_ep' "
        "ELSE 'otros' END"
    )


def _normalizar_grupo_album(grupo: Optional[str]) -> Optional[str]:
    valor = (grupo or "").strip()
    return valor if valor in {clave for clave, _label in _GRUPOS_ALBUMS} else None


def _agregar_condicion_grupo_album(condiciones: list[str], params: list, grupo: Optional[str]) -> None:
    grupo_normalizado = _normalizar_grupo_album(grupo)
    if grupo_normalizado == "albums":
        condiciones.append("lower(al.tipo) = ?")
        params.append("album")
    elif grupo_normalizado == "singles_y_ep":
        condiciones.append("lower(al.tipo) IN (?, ?)")
        params.extend(["single", "ep"])
    elif grupo_normalizado == "otros":
        condiciones.append("lower(al.tipo) NOT IN (?, ?, ?)")
        params.extend(["album", "single", "ep"])


def _normalizar_pista_fila(fila: dict) -> dict:
    item = dict(fila)
    portada_base = item.get("portada_ruta") or item.get("album_portada_ruta")
    release_id = item.get("album_mb_release_id") or item.get("mb_release_id")
    item["portada_ruta"] = _resolver_portada_fila(portada_base, release_id)
    item["portada_hd_ruta"] = _resolver_portada_hd_fila(
        item.get("portada_hd_ruta") or item.get("album_portada_hd_ruta"),
        release_id,
    )
    return _agregar_portada_display(item)


def _limite_dashboard(limite: int, predeterminado: int = 50, maximo: int = 100) -> int:
    try:
        valor = int(limite)
    except (TypeError, ValueError):
        valor = predeterminado
    return max(0, min(valor, maximo))


def _columnas_tabla(tabla: str) -> set[str]:
    try:
        return {str(fila["name"]) for fila in obtener_filas(f"PRAGMA table_info({tabla})")}
    except sqlite3.Error as exc:
        logger.warning("No se pudieron leer columnas de %s: %s", tabla, exc)
        return set()


def _subtitulo_pista(item: dict) -> str:
    partes = []
    artista = str(item.get("artista_nombre") or item.get("artista") or "").strip()
    album = str(item.get("album_titulo") or item.get("album") or "").strip()
    if artista:
        partes.append(artista)
    if album and album != artista:
        partes.append(album)
    return " · ".join(partes)


def _item_dashboard_pista(fila: dict, origen: str) -> dict:
    item = _normalizar_pista_fila(fila)
    item["tipo"] = "pista"
    item["subtitulo"] = _subtitulo_pista(item)
    item["origen"] = origen
    item["album_id"] = item.get("album_id") or 0
    item["artista_id"] = item.get("artista_id") or 0
    item["reproducciones_total"] = int(item.get("reproducciones_total") or item.get("veces_reproducida") or 0)
    return item


def _item_dashboard_album(fila: dict, origen: str) -> dict:
    item = dict(fila)
    item["tipo"] = "album"
    item["portada_ruta"] = _resolver_portada_fila(
        item.get("portada_ruta"),
        item.get("mb_release_id"),
    )
    _agregar_portada_display(item)
    artista = str(item.get("artista_nombre") or "").strip()
    pistas = int(item.get("num_pistas") or 0)
    partes = []
    if artista:
        partes.append(artista)
    if pistas:
        partes.append(f"{pistas} pista" + ("" if pistas == 1 else "s"))
    item["subtitulo"] = " · ".join(partes)
    item["origen"] = origen
    item["album_id"] = item.get("id") or item.get("album_id") or 0
    item["artista_id"] = item.get("artista_id") or 0
    item["reproducciones_total"] = int(item.get("reproducciones_total") or 0)
    item["num_pistas"] = pistas
    return item


def _item_dashboard_artista(fila: dict, origen: str) -> dict:
    item = dict(fila)
    item["tipo"] = "artista"
    item["portada_ruta"] = _resolver_avatar_artista(
        item.get("portada_ruta"),
        item.get("nombre"),
    )
    _agregar_portada_display(item)
    albums = int(item.get("num_albums") or 0)
    pistas = int(item.get("num_pistas") or 0)
    partes = []
    if albums:
        partes.append(f"{albums} album" + ("" if albums == 1 else "es"))
    if pistas:
        partes.append(f"{pistas} pista" + ("" if pistas == 1 else "s"))
    item["subtitulo"] = " · ".join(partes)
    item["origen"] = origen
    item["artista_id"] = item.get("id") or item.get("artista_id") or 0
    item["reproducciones_total"] = int(item.get("reproducciones_total") or 0)
    item["num_albums"] = albums
    item["num_pistas"] = pistas
    return item


def _item_dashboard_playlist(fila: dict, origen: str) -> dict:
    item = _normalizar_playlist_fila(dict(fila))
    playlist_id = int(item.get("playlist_id") or 0)
    tipo_db = item.get("tipo") or "manual"
    subtipo = item.get("tipo_playlist") or _subtipo_playlist(item)
    num_pistas = int(item.get("num_pistas") or 0)
    reproducciones = int(item.get("reproducciones_total") or 0)
    tipo_legible = item.get("etiqueta_tipo") or _etiqueta_playlist(subtipo, tipo_db, item.get("origen"))
    item["id"] = playlist_id
    item["playlist_id"] = playlist_id
    item["tipo_db"] = tipo_db
    item["tipo"] = "playlist"
    item["tipo_playlist"] = subtipo
    item["origen_bloque"] = origen
    item["es_anclada"] = bool(item.get("es_anclada") or item.get("anclada") or item.get("fijada") or False)
    item["num_pistas"] = num_pistas
    item["reproducciones_total"] = reproducciones
    item["subtitulo"] = (
        ("Anclada · " if item["es_anclada"] else "")
        + tipo_legible
        + (f" · {num_pistas} pista" + ("" if num_pistas == 1 else "s") if num_pistas else "")
    )
    if reproducciones > 0:
        item["contexto"] = f"Escuchada {reproducciones} vez" + ("" if reproducciones == 1 else "es")
    elif num_pistas > 0:
        item["contexto"] = f"Incluye {num_pistas} cancion" + ("" if num_pistas == 1 else "es")
    item["portadas"] = item.get("portadas") or _portadas_playlist(playlist_id)
    _agregar_portada_display(item)
    return item


# =============================================================================
# ARTISTAS
# =============================================================================

def listar_artistas(filtro_texto: str = "", orden: str = "nombre") -> list[dict]:
    """
    Retorna todos los artistas con numero de albums y pistas.
    orden: 'nombre' | 'nombre_desc' | 'num_pistas' | 'num_pistas_asc' |
           'num_albums' | 'num_albums_asc' | 'duracion' | 'duracion_asc'
    """
    ordenes_validos = {
        "nombre", "nombre_desc", "num_pistas", "num_pistas_asc",
        "num_albums", "num_albums_asc", "duracion", "duracion_asc",
    }
    if orden == "nombre" and filtro_texto in ordenes_validos:
        orden = filtro_texto
        filtro_texto = ""

    columna_orden = {
        "nombre":         "nb_sortkey(a.nombre)",
        "nombre_desc":    "nb_sortkey(a.nombre) DESC",
        "num_pistas":     "num_pistas DESC, nb_sortkey(a.nombre)",
        "num_pistas_asc": "num_pistas ASC, nb_sortkey(a.nombre)",
        "num_albums":     "num_albums DESC, nb_sortkey(a.nombre)",
        "num_albums_asc": "num_albums ASC, nb_sortkey(a.nombre)",
        "duracion":       "duracion_total_seg DESC, nb_sortkey(a.nombre)",
        "duracion_asc":   "duracion_total_seg ASC, nb_sortkey(a.nombre)",
    }.get(orden, "nb_sortkey(a.nombre)")

    condiciones = [
        """
        EXISTS (
            SELECT 1 FROM pistas pp WHERE pp.artista_id = a.id AND pp.estado = 'biblioteca'
        )
        """
    ]
    params: list = []
    filtro = (filtro_texto or "").strip()
    if filtro:
        like = f"%{filtro}%"
        condiciones.append(
            """
            (
                a.nombre LIKE ? COLLATE NOCASE OR
                EXISTS (
                    SELECT 1
                    FROM pistas px
                    WHERE px.artista_id = a.id
                      AND px.estado = 'biblioteca'
                      AND (
                          px.titulo LIKE ? COLLATE NOCASE OR
                          px.artista_nombre LIKE ? COLLATE NOCASE OR
                          px.album_titulo LIKE ? COLLATE NOCASE OR
                          px.genero LIKE ? COLLATE NOCASE
                      )
                )
            )
            """
        )
        params.extend([like, like, like, like, like])

    where = "WHERE " + " AND ".join(condiciones)

    filas = obtener_filas(
        f"""
        SELECT
            a.id,
            a.nombre,
            a.nombre_slug,
            a.mb_artist_id,
            COUNT(DISTINCT CASE WHEN p.id IS NOT NULL THEN al.id END) AS num_albums,
            COUNT(DISTINCT p.id)  AS num_pistas,
            COALESCE(SUM(p.duracion_seg), 0) AS duracion_total_seg
        FROM artistas a
        LEFT JOIN albums al ON al.artista_id = a.id
        LEFT JOIN pistas p  ON p.artista_id  = a.id AND p.estado = 'biblioteca'
        {where}
        GROUP BY a.id
        ORDER BY {columna_orden}
        """,
        params,
    )
    out = []
    for fila in filas:
        item = dict(fila)
        item["portada_ruta"] = _resolver_avatar_artista(
            None,
            item.get("nombre"),
        )
        item["portada_hd_ruta"] = _resolver_avatar_hd_artista(
            None,
            item.get("nombre"),
        )
        _agregar_portada_display(item)
        out.append(item)
    return out


# =============================================================================
# ALBUMS
# =============================================================================

def grupos_albums_disponibles() -> list[dict]:
    """Retorna solo las subcategorias de album que tienen contenido."""
    filas = obtener_filas(
        f"""
        SELECT {_grupo_album_sql()} AS grupo, COUNT(DISTINCT al.id) AS total
        FROM albums al
        JOIN pistas p ON p.album_id = al.id AND p.estado = 'biblioteca'
        GROUP BY grupo
        """
    )
    conteos = {fila["grupo"]: int(fila["total"] or 0) for fila in filas}
    return [
        {"clave": clave, "label": label, "total": conteos.get(clave, 0)}
        for clave, label in _GRUPOS_ALBUMS
        if conteos.get(clave, 0) > 0
    ]


def listar_albums(
    artista_id: Optional[int] = None,
    tipo: Optional[str] = None,
    orden: str = "artista",
    grupo: Optional[str] = None,
    filtro_texto: str = "",
) -> list[dict]:
    """
    Lista albums con portada, artista y conteo de pistas.
    Si artista_id se especifica, filtra por ese artista.
    tipo: 'Album' | 'Single' | 'EP' | None (todos)
    grupo: 'albums' | 'singles_y_ep' | 'otros' | None
    orden: 'artista' | 'artista_desc' | 'titulo' | 'titulo_desc' | 'anio' |
           'anio_asc' | 'duracion' | 'duracion_asc' | 'pistas' | 'pistas_asc'
    """
    condiciones = ["p.estado = 'biblioteca'"]
    params: list = []

    if artista_id is not None:
        condiciones.append("al.artista_id = ?")
        params.append(artista_id)

    if tipo:
        condiciones.append("al.tipo = ?")
        params.append(tipo)
    elif grupo:
        _agregar_condicion_grupo_album(condiciones, params, grupo)

    filtro = (filtro_texto or "").strip()
    if filtro:
        like = f"%{filtro}%"
        condiciones.append(
            """
            (
                al.titulo LIKE ? COLLATE NOCASE OR
                art.nombre LIKE ? COLLATE NOCASE OR
                EXISTS (
                    SELECT 1
                    FROM pistas px
                    WHERE px.album_id = al.id
                      AND px.estado = 'biblioteca'
                      AND (
                          px.titulo LIKE ? COLLATE NOCASE OR
                          px.artista_nombre LIKE ? COLLATE NOCASE OR
                          px.album_titulo LIKE ? COLLATE NOCASE OR
                          px.genero LIKE ? COLLATE NOCASE
                      )
                )
            )
            """
        )
        params.extend([like, like, like, like, like, like])

    where = "WHERE " + " AND ".join(condiciones)

    columna_orden = {
        "artista":      "nb_sortkey(art.nombre), COALESCE(al.anio, 0), nb_sortkey(al.titulo)",
        "artista_desc": "nb_sortkey(art.nombre) DESC, COALESCE(al.anio, 0) DESC, nb_sortkey(al.titulo)",
        "titulo":       "nb_sortkey(al.titulo)",
        "titulo_desc":  "nb_sortkey(al.titulo) DESC",
        "anio":         "COALESCE(al.anio, 0) DESC, nb_sortkey(al.titulo)",
        "anio_asc":     "COALESCE(al.anio, 0) ASC, nb_sortkey(al.titulo)",
        "duracion":     "duracion_total_seg DESC, nb_sortkey(al.titulo)",
        "duracion_asc": "duracion_total_seg ASC, nb_sortkey(al.titulo)",
        "pistas":       "num_pistas DESC, nb_sortkey(al.titulo)",
        "pistas_asc":   "num_pistas ASC, nb_sortkey(al.titulo)",
    }.get(orden, "nb_sortkey(art.nombre), al.anio")

    filas = obtener_filas(
        f"""
        SELECT
            al.id,
            al.titulo,
            al.titulo_slug,
            al.tipo,
            al.anio,
            al.mb_release_id,
            al.portada_ruta,
            al.ruta_carpeta,
            art.id   AS artista_id,
            art.nombre AS artista_nombre,
            COUNT(p.id) AS num_pistas,
            SUM(p.duracion_seg) AS duracion_total_seg
        FROM albums al
        JOIN artistas art ON art.id = al.artista_id
        JOIN pistas p ON p.album_id = al.id
        {where}
        GROUP BY al.id
        ORDER BY {columna_orden}
        """,
        params,
    )
    out = []
    for fila in filas:
        item = dict(fila)
        item["portada_ruta"] = _resolver_portada_fila(
            item.get("portada_ruta"),
            item.get("mb_release_id"),
        )
        item["portada_hd_ruta"] = _resolver_portada_hd_fila(
            item.get("portada_hd_ruta"),
            item.get("mb_release_id"),
        )
        item["grupo"] = _normalizar_grupo_album(
            "albums" if (item.get("tipo") or "").lower() == "album"
            else "singles_y_ep" if (item.get("tipo") or "").lower() in {"single", "ep"}
            else "otros"
        ) or "otros"
        _agregar_portada_display(item)
        out.append(item)
    return out


def detalle_album(album_id: int) -> Optional[dict]:
    """Retorna el detalle completo de un album con sus pistas ordenadas."""
    fila = obtener_una_fila(
        """
        SELECT al.*, art.nombre AS artista_nombre
        FROM albums al
        JOIN artistas art ON art.id = al.artista_id
        WHERE al.id = ?
        """,
        (album_id,),
    )
    if not fila:
        return None

    resultado = dict(fila)
    pistas = listar_pistas_de_album(album_id)
    resultado["pistas"] = pistas
    resultado["num_pistas"] = len(pistas)
    resultado["duracion_total_seg"] = sum(int(p.get("duracion_seg") or 0) for p in pistas)
    resultado["portada_ruta"] = _resolver_portada_fila(
        resultado.get("portada_ruta"),
        resultado.get("mb_release_id"),
    )
    resultado["portada_hd_ruta"] = _resolver_portada_hd_fila(
        resultado.get("portada_hd_ruta"),
        resultado.get("mb_release_id"),
    )
    _agregar_portada_display(resultado)
    return resultado


# =============================================================================
# PISTAS
# =============================================================================

def listar_pistas_de_album(album_id: int) -> list[dict]:
    """Lista las pistas de un album ordenadas por track_number."""
    filas = obtener_filas(
        """
        SELECT
            p.*,
            art.nombre AS artista_nombre_rel,
            al.portada_ruta AS album_portada_ruta,
            al.mb_release_id AS album_mb_release_id
        FROM pistas p
        LEFT JOIN artistas art ON art.id = p.artista_id
        LEFT JOIN albums al ON al.id = p.album_id
        WHERE p.album_id = ? AND p.estado = 'biblioteca'
        ORDER BY COALESCE(p.track_number, 9999), p.titulo COLLATE NOCASE
        """,
        (album_id,),
    )
    return [_normalizar_pista_fila(dict(f)) for f in filas]


def listar_pistas(
    artista_id: Optional[int] = None,
    album_id: Optional[int] = None,
    solo_favoritas: bool = False,
    orden: str = "titulo",
    limite: Optional[int] = None,
    offset: int = 0,
    filtro_texto: str = "",
) -> list[dict]:
    """Lista pistas con filtros opcionales."""
    condiciones = ["p.estado = 'biblioteca'"]
    params: list = []

    if artista_id is not None:
        condiciones.append("p.artista_id = ?")
        params.append(artista_id)
    if album_id is not None:
        condiciones.append("p.album_id = ?")
        params.append(album_id)
    if solo_favoritas:
        condiciones.append("p.favorita = 1")
    filtro = (filtro_texto or "").strip()
    if filtro:
        condiciones.append(
            "("
            "p.titulo LIKE ? COLLATE NOCASE OR "
            "p.artista_nombre LIKE ? COLLATE NOCASE OR "
            "p.album_titulo LIKE ? COLLATE NOCASE OR "
            "p.genero LIKE ? COLLATE NOCASE"
            ")"
        )
        like = f"%{filtro}%"
        params.extend([like, like, like, like])

    where = "WHERE " + " AND ".join(condiciones)

    columna_orden = {
        "titulo":          "nb_sortkey(p.titulo), nb_sortkey(p.artista_nombre)",
        "titulo_desc":     "nb_sortkey(p.titulo) DESC, nb_sortkey(p.artista_nombre)",
        "artista":         "nb_sortkey(p.artista_nombre), nb_sortkey(p.album_titulo), COALESCE(p.track_number, 9999)",
        "artista_desc":    "nb_sortkey(p.artista_nombre) DESC, nb_sortkey(p.album_titulo), COALESCE(p.track_number, 9999)",
        "album":           "nb_sortkey(p.album_titulo), COALESCE(p.track_number, 9999), nb_sortkey(p.titulo)",
        "album_desc":      "nb_sortkey(p.album_titulo) DESC, COALESCE(p.track_number, 9999), nb_sortkey(p.titulo)",
        "anio":            "COALESCE(p.anio, 0) DESC, nb_sortkey(p.titulo)",
        "anio_asc":        "COALESCE(p.anio, 0) ASC, nb_sortkey(p.titulo)",
        "duracion":        "COALESCE(p.duracion_seg, 0) DESC, nb_sortkey(p.titulo)",
        "duracion_asc":    "COALESCE(p.duracion_seg, 0) ASC, nb_sortkey(p.titulo)",
        "reproducida":     "p.veces_reproducida DESC, nb_sortkey(p.titulo)",
        "reproducida_asc": "p.veces_reproducida ASC, nb_sortkey(p.titulo)",
        "reciente":        "p.ultimo_acceso DESC NULLS LAST, p.actualizado_en DESC",
        "reciente_asc":    "p.ultimo_acceso ASC NULLS FIRST, p.actualizado_en ASC",
    }.get(orden, "nb_sortkey(p.titulo)")

    limite_sql = ""
    if limite is not None:
        try:
            limite_int = int(limite)
        except (TypeError, ValueError):
            limite_int = 500
        limite_int = max(0, limite_int)
        offset_int = max(0, int(offset or 0))
        limite_sql = "LIMIT ? OFFSET ?"
        params.extend([limite_int, offset_int])

    filas = obtener_filas(
        f"""
        SELECT
            p.*,
            al.portada_ruta AS album_portada_ruta,
            al.mb_release_id AS album_mb_release_id
        FROM pistas p
        LEFT JOIN albums al ON al.id = p.album_id
        {where}
        ORDER BY {columna_orden}
        {limite_sql}
        """,
        params,
    )
    return [_normalizar_pista_fila(dict(f)) for f in filas]


def obtener_pista(pista_id: int) -> Optional[dict]:
    """Retorna el detalle completo de una pista por ID."""
    fila = obtener_una_fila(
        "SELECT * FROM pistas WHERE id = ?", (pista_id,)
    )
    return dict(fila) if fila else None


def obtener_pista_por_ruta(ruta: str) -> Optional[dict]:
    """Busca una pista por su ruta de archivo."""
    fila = obtener_una_fila(
        "SELECT * FROM pistas WHERE ruta_archivo = ?", (ruta,)
    )
    return dict(fila) if fila else None


def toggle_favorita(pista_id: int) -> bool:
    """Alterna el estado de favorita de una pista. Retorna el nuevo valor.

    Sella `favorita_actualizada_en` (UTC) e incrementa `sync_version` para que
    el ecosistema movil resuelva el favorito por last-write-wins y detecte el
    cambio en el siguiente delta. Ver docs/mobile-ecosystem.md (seccion B).
    """
    fila = obtener_una_fila("SELECT favorita FROM pistas WHERE id = ?", (pista_id,))
    if not fila:
        return False
    nuevo_valor = 0 if fila["favorita"] else 1
    ejecutar(
        "UPDATE pistas SET favorita = ?, favorita_actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), "
        "actualizado_en = datetime('now') WHERE id = ?",
        (nuevo_valor, pista_id),
    )
    try:
        from db.conexion import marcar_sync_version
        marcar_sync_version("pistas", pista_id)
    except Exception as exc:
        logger.warning("No se pudo incrementar sync_version de la pista %s: %s", pista_id, exc)
    try:
        _sincronizar_playlist_favoritos()
    except Exception as exc:
        logger.warning("No se pudo sincronizar Me gusta tras cambiar favorito %s: %s", pista_id, exc)
    return bool(nuevo_valor)


# =============================================================================
# BUSQUEDA UNIVERSAL
# =============================================================================

def _buscar_pistas(termino_limpio: str, limite: int) -> list[dict]:
    """Núcleo de búsqueda de pistas (FTS + LIKE + comparación + scoring).

    Aislado de :func:`buscar` para que consumidores que solo necesitan pistas
    —el selector "+Agregar" de playlists— no paguen el costo de los agregados
    de álbumes y artistas (GROUP BY sobre toda la biblioteca) que descartan.
    """
    termino_fts = _consulta_fts_prefijo(termino_limpio)
    like_amplio = _like_seguro(termino_limpio)

    filas_por_id: dict[int, dict] = {}

    if termino_fts:
        try:
            for fila in obtener_filas(
                """
                SELECT
                    p.*,
                    al.portada_ruta AS album_portada_ruta,
                    al.mb_release_id AS album_mb_release_id,
                    bm25(pistas_fts, 4.0, 2.2, 1.6, 0.4) AS score_fts
                FROM pistas p
                JOIN pistas_fts f ON p.id = f.rowid
                LEFT JOIN albums al ON al.id = p.album_id
                WHERE pistas_fts MATCH ? AND p.estado = 'biblioteca'
                ORDER BY score_fts ASC, p.veces_reproducida DESC
                LIMIT ?
                """,
                (termino_fts, max(limite * 4, 80)),
            ):
                item = dict(fila)
                item["_search_bonus"] = 500.0
                filas_por_id[int(item["id"])] = item
        except sqlite3.Error as exc:
            logger.warning("Busqueda FTS ignorada para %r: %s", termino_limpio, exc)

    for fila in obtener_filas(
        """
        SELECT
            p.*,
            al.portada_ruta AS album_portada_ruta,
            al.mb_release_id AS album_mb_release_id
        FROM pistas p
        LEFT JOIN albums al ON al.id = p.album_id
        WHERE p.estado = 'biblioteca'
          AND (
              p.titulo COLLATE NOCASE LIKE ? ESCAPE '\\' OR
              p.artista_nombre COLLATE NOCASE LIKE ? ESCAPE '\\' OR
              p.album_titulo COLLATE NOCASE LIKE ? ESCAPE '\\' OR
              p.genero COLLATE NOCASE LIKE ? ESCAPE '\\'
          )
        ORDER BY p.veces_reproducida DESC, p.titulo COLLATE NOCASE
        LIMIT ?
        """,
        (like_amplio, like_amplio, like_amplio, like_amplio, max(limite * 4, 80)),
    ):
        item = dict(fila)
        existente = filas_por_id.get(int(item["id"]))
        item["_search_bonus"] = max(float((existente or {}).get("_search_bonus") or 0), 250.0)
        filas_por_id[int(item["id"])] = item

    if para_comparacion(termino_limpio):
        for fila in obtener_filas(
            """
            SELECT
                p.*,
                al.portada_ruta AS album_portada_ruta,
                al.mb_release_id AS album_mb_release_id
            FROM pistas p
            LEFT JOIN albums al ON al.id = p.album_id
            WHERE p.estado = 'biblioteca'
            ORDER BY p.veces_reproducida DESC, p.titulo COLLATE NOCASE
            """
        ):
            item = dict(fila)
            filas_por_id.setdefault(int(item["id"]), item)

    pistas_out = []
    for fila in filas_por_id.values():
        item = dict(fila)
        item["_score_busqueda"] = _score_pista_busqueda(item, termino_limpio) + float(item.get("_search_bonus") or 0.0)
        if item["_score_busqueda"] <= 0:
            continue
        item = _normalizar_pista_fila(item)
        pistas_out.append(item)
    pistas_out.sort(
        key=lambda item: (
            -float(item.get("_score_busqueda") or 0.0),
            str(item.get("titulo") or "").casefold(),
        )
    )
    pistas_out = pistas_out[:limite]
    for item in pistas_out:
        item.pop("_search_bonus", None)
        item.pop("_score_busqueda", None)
        item.pop("score_fts", None)
    return pistas_out


def buscar(termino: str, limite: int = 50) -> dict:
    """
    Busqueda full-text sobre pistas (titulo, artista, album).
    Retorna dict con claves: pistas, albums, artistas.
    """
    termino_limpio = str(termino or "").strip()
    if not termino_limpio:
        return {"pistas": [], "albums": [], "artistas": []}

    limite = max(1, int(limite or 50))

    pistas_out = _buscar_pistas(termino_limpio, limite)

    albums_filas = obtener_filas(
        """
        SELECT al.*, art.nombre AS artista_nombre, COUNT(p.id) AS num_pistas
        FROM albums al
        JOIN artistas art ON art.id = al.artista_id
        JOIN pistas p ON p.album_id = al.id AND p.estado = 'biblioteca'
        GROUP BY al.id
        """,
    )

    artistas_filas = obtener_filas(
        """
        SELECT a.*,
               COUNT(DISTINCT p.id) AS num_pistas,
               COUNT(DISTINCT al.id) AS num_albums
        FROM artistas a
        LEFT JOIN pistas p ON p.artista_id = a.id AND p.estado = 'biblioteca'
        LEFT JOIN albums al ON al.artista_id = a.id
        GROUP BY a.id
        HAVING num_pistas > 0
        """,
    )

    albums_out = []
    for fila in albums_filas:
        item = dict(fila)
        item["_score_busqueda"] = _score_album_busqueda(item, termino_limpio)
        if item["_score_busqueda"] <= 0:
            continue
        item["portada_ruta"] = _resolver_portada_fila(
            item.get("portada_ruta"),
            item.get("mb_release_id"),
        )
        _agregar_portada_display(item)
        albums_out.append(item)
    albums_out.sort(
        key=lambda item: (
            -float(item.get("_score_busqueda") or 0.0),
            str(item.get("titulo") or "").casefold(),
        )
    )
    albums_out = albums_out[:10]
    for item in albums_out:
        item.pop("_score_busqueda", None)

    artistas_out = []
    for fila in artistas_filas:
        item = dict(fila)
        item["_score_busqueda"] = _score_artista_busqueda(item, termino_limpio)
        if item["_score_busqueda"] <= 0:
            continue
        item["portada_ruta"] = _resolver_avatar_artista(
            None,
            item.get("nombre"),
        )
        _agregar_portada_display(item)
        artistas_out.append(item)
    artistas_out.sort(
        key=lambda item: (
            -float(item.get("_score_busqueda") or 0.0),
            str(item.get("nombre") or "").casefold(),
        )
    )
    artistas_out = artistas_out[:10]
    for item in artistas_out:
        item.pop("_score_busqueda", None)

    return {
        "pistas": pistas_out,
        "albums": albums_out,
        "artistas": artistas_out,
    }


# =============================================================================
# REVISION Y CUARENTENA
# =============================================================================

def listar_pendientes(tipo: Optional[str] = None, solo_sin_resolver: bool = True) -> list[dict]:
    """
    Lista archivos en revision o cuarentena.
    tipo: 'revision' | 'cuarentena' | None (ambos)
    """
    condiciones = []
    params: list = []

    if tipo:
        condiciones.append("tipo = ?")
        params.append(tipo)
    if solo_sin_resolver:
        condiciones.append("resuelto = 0")

    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    filas = obtener_filas(
        f"SELECT * FROM archivos_pendientes {where} ORDER BY registrado_en DESC",
        params,
    )
    return [dict(f) for f in filas]


def contar_pendientes() -> dict:
    """Retorna conteo de archivos pendientes: {revision: N, cuarentena: N}."""
    revision   = obtener_una_fila(
        "SELECT COUNT(*) AS n FROM archivos_pendientes WHERE tipo='revision'   AND resuelto=0"
    )["n"]
    cuarentena = obtener_una_fila(
        "SELECT COUNT(*) AS n FROM archivos_pendientes WHERE tipo='cuarentena' AND resuelto=0"
    )["n"]
    return {"revision": revision, "cuarentena": cuarentena}


def marcar_pendiente_resuelto(pendiente_id: int) -> None:
    ejecutar(
        "UPDATE archivos_pendientes SET resuelto=1, resuelto_en=datetime('now') WHERE id=?",
        (pendiente_id,),
    )


# =============================================================================
# ESTADISTICAS
# =============================================================================

def estadisticas_generales() -> dict:
    """Resumen rapido de la coleccion para el dashboard de inicio."""
    total_pistas = obtener_una_fila(
        "SELECT COUNT(*) AS n FROM pistas WHERE estado='biblioteca'"
    )["n"]
    total_artistas = obtener_una_fila(
        "SELECT COUNT(DISTINCT artista_id) AS n FROM pistas WHERE estado='biblioteca'"
    )["n"]
    total_albums = obtener_una_fila(
        "SELECT COUNT(DISTINCT album_id) AS n FROM pistas WHERE estado='biblioteca'"
    )["n"]
    duracion_total = obtener_una_fila(
        "SELECT SUM(duracion_seg) AS s FROM pistas WHERE estado='biblioteca'"
    )["s"] or 0
    total_reproducidas = obtener_una_fila(
        "SELECT COUNT(*) AS n FROM historial"
    )["n"]

    pendientes = contar_pendientes()

    return {
        "total_pistas":       total_pistas,
        "total_artistas":     total_artistas,
        "total_albums":       total_albums,
        "duracion_total_seg": duracion_total,
        "total_reproducidas": total_reproducidas,
        "pendientes_revision":    pendientes["revision"],
        "pendientes_cuarentena":  pendientes["cuarentena"],
    }


def pistas_recientes(limite: int = 10, ventana_dias: int = 5) -> list[dict]:
    """Ultimas pistas agregadas a biblioteca, sin limitar por sesion o ventana."""
    filas = obtener_filas(
        """
        SELECT
            p.*,
            al.portada_ruta AS album_portada_ruta,
            al.mb_release_id AS album_mb_release_id
        FROM pistas p
        LEFT JOIN albums al ON al.id = p.album_id
        WHERE p.estado = 'biblioteca'
        ORDER BY datetime(COALESCE(p.indexado_en, p.actualizado_en)) DESC,
                 p.titulo COLLATE NOCASE
        LIMIT ?
        """,
        (limite,),
    )
    return [_normalizar_pista_fila(dict(fila)) for fila in filas]


def albums_recientes(limite: int = 10, ventana_dias: int = 5) -> list[dict]:
    """Ultimos albums agregados a biblioteca, sin limitar por sesion."""
    filas = obtener_filas(
        """
        SELECT
            al.id,
            al.titulo,
            al.anio,
            al.tipo,
            al.mb_release_id,
            al.portada_ruta,
            al.creado_en,
            art.nombre AS artista_nombre,
            COUNT(p.id) AS num_pistas,
            MAX(datetime(COALESCE(p.indexado_en, p.actualizado_en))) AS ultimo_indexado
        FROM albums al
        JOIN artistas art ON art.id = al.artista_id
        JOIN pistas p ON p.album_id = al.id AND p.estado = 'biblioteca'
        GROUP BY al.id
        ORDER BY datetime(COALESCE(ultimo_indexado, al.creado_en)) DESC,
                 al.titulo COLLATE NOCASE
        LIMIT ?
        """,
        (limite,),
    )
    out = []
    for fila in filas:
        item = dict(fila)
        item["portada_ruta"] = _resolver_portada_fila(
            item.get("portada_ruta"),
            item.get("mb_release_id"),
        )
        _agregar_portada_display(item)
        out.append(item)
    return out


def artistas_recientes(limite: int = 10, ventana_dias: int = 5) -> list[dict]:
    """Ultimos artistas agregados a biblioteca, sin limitar por sesion."""
    filas = obtener_filas(
        """
        SELECT
            a.id,
            a.nombre,
            a.creado_en,
            COUNT(DISTINCT al.id) AS num_albums,
            COUNT(DISTINCT p.id) AS num_pistas,
            (
                SELECT al2.portada_ruta
                FROM pistas p2
                JOIN albums al2 ON al2.id = p2.album_id
                WHERE p2.artista_id = a.id
                  AND p2.estado = 'biblioteca'
                  AND al2.portada_ruta IS NOT NULL
                  AND al2.portada_ruta <> ''
                ORDER BY datetime(COALESCE(p2.indexado_en, p2.actualizado_en)) DESC
                LIMIT 1
            ) AS portada_ruta,
            MAX(datetime(COALESCE(p.indexado_en, p.actualizado_en))) AS ultimo_indexado
        FROM artistas a
        LEFT JOIN albums al ON al.artista_id = a.id
        LEFT JOIN pistas p ON p.artista_id = a.id AND p.estado = 'biblioteca'
        GROUP BY a.id
        HAVING num_pistas > 0
        ORDER BY datetime(COALESCE(ultimo_indexado, a.creado_en)) DESC,
                 a.nombre COLLATE NOCASE
        LIMIT ?
        """,
        (limite,),
    )
    out = []
    for fila in filas:
        item = dict(fila)
        item["portada_ruta"] = _resolver_avatar_artista(
            item.get("portada_ruta"),
            item.get("nombre"),
        )
        _agregar_portada_display(item)
        out.append(item)
    return out


def pistas_mas_escuchadas(limite: int = 10) -> list[dict]:
    """Las pistas con mayor numero de reproducciones."""
    filas = obtener_filas(
        """
        SELECT
            p.*,
            al.portada_ruta,
            COALESCE(h.reproducciones, p.veces_reproducida, 0) AS reproducciones_total
        FROM pistas p
        LEFT JOIN albums al ON al.id = p.album_id
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca' AND COALESCE(h.reproducciones, p.veces_reproducida, 0) > 0
        ORDER BY reproducciones_total DESC, p.ultimo_acceso DESC
        LIMIT ?
        """,
        (limite,),
    )
    out = []
    for fila in filas:
        item = dict(fila)
        item["portada_ruta"] = _resolver_portada_fila(
            item.get("portada_ruta"),
            item.get("mb_release_id"),
        )
        _agregar_portada_display(item)
        out.append(item)
    return out


def albums_mas_escuchados(limite: int = 10) -> list[dict]:
    """Albums con mas reproducciones historicas."""
    filas = obtener_filas(
        """
        SELECT
            al.id,
            al.titulo,
            al.mb_release_id,
            al.portada_ruta,
            art.nombre AS artista_nombre,
            COUNT(h.id) AS reproducciones_total,
            MAX(h.reproducido_en) AS ultima_reproduccion
        FROM historial h
        JOIN pistas p ON p.id = h.pista_id
        JOIN albums al ON al.id = p.album_id
        JOIN artistas art ON art.id = al.artista_id
        GROUP BY al.id
        HAVING reproducciones_total > 0
        ORDER BY reproducciones_total DESC, ultima_reproduccion DESC
        LIMIT ?
        """,
        (limite,),
    )
    out = []
    for fila in filas:
        item = dict(fila)
        item["portada_ruta"] = _resolver_portada_fila(
            item.get("portada_ruta"),
            item.get("mb_release_id"),
        )
        _agregar_portada_display(item)
        out.append(item)
    return out


def artistas_mas_escuchados(limite: int = 10) -> list[dict]:
    """Artistas con mas reproducciones historicas."""
    filas = obtener_filas(
        """
        SELECT
            art.id,
            art.nombre,
            (
                SELECT al2.portada_ruta
                FROM pistas p2
                JOIN albums al2 ON al2.id = p2.album_id
                WHERE p2.artista_id = art.id
                  AND p2.estado = 'biblioteca'
                  AND al2.portada_ruta IS NOT NULL
                  AND al2.portada_ruta <> ''
                ORDER BY RANDOM()
                LIMIT 1
            ) AS portada_ruta,
            COUNT(h.id) AS reproducciones_total,
            MAX(h.reproducido_en) AS ultima_reproduccion
        FROM historial h
        JOIN pistas p ON p.id = h.pista_id
        JOIN artistas art ON art.id = p.artista_id
        GROUP BY art.id
        HAVING reproducciones_total > 0
        ORDER BY reproducciones_total DESC, ultima_reproduccion DESC
        LIMIT ?
        """,
        (limite,),
    )
    out = []
    for fila in filas:
        item = dict(fila)
        item["portada_ruta"] = _resolver_avatar_artista(
            item.get("portada_ruta"),
            item.get("nombre"),
        )
        _agregar_portada_display(item)
        out.append(item)
    return out


def playlists_mas_escuchadas(limite: int = 10) -> list[dict]:
    """
    Estimacion de playlists mas escuchadas.
    Se contabiliza una reproduccion si la pista reproducida pertenece a la playlist.
    """
    limite = _limite_dashboard(limite, predeterminado=10, maximo=100)
    filas = obtener_filas(
        """
        SELECT
            pl.id,
            pl.nombre,
            pl.descripcion,
            pl.tipo,
            pl.subtipo,
            pl.origen,
            pl.regla_json,
            pl.es_anclada,
            pl.visible,
            pl.portada_ruta,
            pl.creado_en,
            pl.actualizado_en,
            pl.ultima_generacion_en,
            pl.auto_key,
            pl.auto_actualizable,
            pl.editada_por_usuario,
            COUNT(DISTINCT pp.pista_id) AS num_pistas,
            SUM(COALESCE(p.duracion_seg, 0)) AS duracion_total_seg,
            SUM(COALESCE(h.reproducciones, 0)) AS reproducciones_total,
            MAX(h.ultima_reproduccion) AS ultima_reproduccion
        FROM playlists pl
        JOIN pistas_playlist pp ON pp.playlist_id = pl.id
        JOIN pistas p ON p.id = pp.pista_id AND p.estado = 'biblioteca'
        JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones, MAX(reproducido_en) AS ultima_reproduccion
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = pp.pista_id
        WHERE COALESCE(pl.visible, 1) = 1
        GROUP BY pl.id
        HAVING reproducciones_total > 0
        ORDER BY reproducciones_total DESC, ultima_reproduccion DESC
        LIMIT ?
        """,
        (limite,),
    )
    return [_item_dashboard_playlist(dict(f), "mas_escuchadas") for f in filas]


def pistas_para_volver(limite: int = 60) -> list[dict]:
    """Pistas reproducidas recientemente o con historial suficiente para retomar."""
    limite = _limite_dashboard(limite, predeterminado=60, maximo=100)
    filas = obtener_filas(
        """
        SELECT
            p.*,
            al.portada_ruta AS album_portada_ruta,
            al.mb_release_id AS album_mb_release_id,
            COUNT(h.id) AS reproducciones_total,
            MAX(h.reproducido_en) AS ultima_reproduccion
        FROM pistas p
        LEFT JOIN albums al ON al.id = p.album_id
        LEFT JOIN historial h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca'
          AND (
              h.id IS NOT NULL
              OR p.ultimo_acceso IS NOT NULL
              OR COALESCE(p.veces_reproducida, 0) > 0
          )
        GROUP BY p.id
        ORDER BY
            datetime(COALESCE(MAX(h.reproducido_en), p.ultimo_acceso, p.actualizado_en, p.indexado_en)) DESC,
            reproducciones_total DESC,
            p.titulo COLLATE NOCASE
        LIMIT ?
        """,
        (limite,),
    )
    return [_item_dashboard_pista(dict(fila), "volver") for fila in filas]


def playlists_destacadas(limite: int = 50) -> list[dict]:
    """Playlists listas para Inicio con contrato estable para ancladas/tipos."""
    limite = _limite_dashboard(limite, predeterminado=50, maximo=100)
    try:
        sincronizar_playlists_sistema(limite_creacion=0)
    except Exception as exc:  # pragma: no cover - proteccion defensiva de dashboard
        logger.warning("No se pudieron sincronizar playlists de sistema para Inicio: %s", exc)
    filas = obtener_filas(
        """
        WITH stats AS (
            SELECT
                pp.playlist_id,
                COUNT(DISTINCT pp.pista_id) AS num_pistas,
                SUM(COALESCE(p.duracion_seg, 0)) AS duracion_total_seg,
                SUM(COALESCE(hist.reproducciones, p.veces_reproducida, 0)) AS reproducciones_total,
                MAX(COALESCE(hist.ultima_reproduccion, p.ultimo_acceso, p.actualizado_en, p.indexado_en)) AS ultima_actividad
            FROM pistas_playlist pp
            JOIN pistas p ON p.id = pp.pista_id AND p.estado = 'biblioteca'
            LEFT JOIN (
                SELECT pista_id, COUNT(*) AS reproducciones, MAX(reproducido_en) AS ultima_reproduccion
                FROM historial
                GROUP BY pista_id
            ) hist ON hist.pista_id = p.id
            GROUP BY pp.playlist_id
        )
        SELECT
            pl.id,
            pl.nombre,
            pl.descripcion,
            pl.tipo,
            pl.subtipo,
            pl.origen,
            pl.regla_json,
            COALESCE(pl.es_anclada, 0) AS es_anclada,
            COALESCE(pl.visible, 1) AS visible,
            pl.portada_ruta,
            pl.creado_en,
            pl.actualizado_en,
            pl.ultima_generacion_en,
            pl.auto_key,
            COALESCE(pl.auto_actualizable, 0) AS auto_actualizable,
            COALESCE(pl.editada_por_usuario, 0) AS editada_por_usuario,
            COALESCE(stats.num_pistas, 0) AS num_pistas,
            COALESCE(stats.duracion_total_seg, 0) AS duracion_total_seg,
            COALESCE(stats.reproducciones_total, 0) AS reproducciones_total,
            stats.ultima_actividad,
            CASE
                WHEN pl.auto_key = ? THEN 0
                WHEN COALESCE(pl.es_anclada, 0) = 1 THEN 1
                WHEN pl.tipo = 'manual' THEN 2
                WHEN pl.origen = 'generado'
                  AND COALESCE(pl.subtipo, '') NOT IN ('this_is', 'mood', 'descubrimiento_local', 'top_canciones', 'top_artistas', 'top_albumes', 'artist_mix', 'album_mix') THEN 3
                WHEN pl.subtipo = 'this_is' THEN 4
                WHEN pl.subtipo IN ('mood', 'descubrimiento_local') THEN 5
                WHEN pl.subtipo IN ('top_canciones', 'top_artistas', 'top_albumes', 'artist_mix', 'album_mix') THEN 6
                ELSE 7
            END AS prioridad_inicio
        FROM playlists pl
        LEFT JOIN stats ON stats.playlist_id = pl.id
        WHERE COALESCE(pl.visible, 1) = 1
          AND COALESCE(stats.num_pistas, 0) > 0
        ORDER BY
            prioridad_inicio ASC,
            reproducciones_total DESC,
            datetime(COALESCE(stats.ultima_actividad, pl.ultima_generacion_en, pl.actualizado_en, pl.creado_en)) DESC,
            pl.nombre COLLATE NOCASE
        LIMIT ?
        """,
        (PLAYLIST_FAVORITOS_AUTO_KEY, limite),
    )
    return [_item_dashboard_playlist(dict(fila), "destacada") for fila in filas]


def albums_con_canciones_que_gustan(limite: int = 40) -> list[dict]:
    """Albums donde existen favoritas o reproducciones locales relevantes."""
    limite = _limite_dashboard(limite, predeterminado=40, maximo=100)
    filas = obtener_filas(
        """
        SELECT
            al.id,
            al.titulo,
            al.anio,
            al.tipo AS tipo_album,
            al.mb_release_id,
            al.portada_ruta,
            art.id AS artista_id,
            art.nombre AS artista_nombre,
            COUNT(DISTINCT p.id) AS num_pistas,
            SUM(CASE WHEN COALESCE(p.favorita, 0) = 1 THEN 1 ELSE 0 END) AS favoritas_total,
            SUM(COALESCE(h.reproducciones, p.veces_reproducida, 0)) AS reproducciones_total,
            MAX(COALESCE(h.ultima_reproduccion, p.ultimo_acceso, p.actualizado_en)) AS ultima_actividad,
            (
                SUM(CASE WHEN COALESCE(p.favorita, 0) = 1 THEN 1 ELSE 0 END) * 100
                + SUM(COALESCE(h.reproducciones, p.veces_reproducida, 0)) * 4
            ) AS score_local
        FROM albums al
        JOIN artistas art ON art.id = al.artista_id
        JOIN pistas p ON p.album_id = al.id AND p.estado = 'biblioteca'
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones, MAX(reproducido_en) AS ultima_reproduccion
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        GROUP BY al.id
        HAVING favoritas_total > 0 OR reproducciones_total > 0
        ORDER BY score_local DESC, datetime(ultima_actividad) DESC, al.titulo COLLATE NOCASE
        LIMIT ?
        """,
        (limite,),
    )
    out = []
    for fila in filas:
        item = _item_dashboard_album(dict(fila), "gustos")
        favoritas = int(item.get("favoritas_total") or 0)
        reproducciones = int(item.get("reproducciones_total") or 0)
        item["score_local"] = float(item.get("score_local") or 0)
        item["subtitulo"] = (
            f"{item.get('artista_nombre') or 'Artista'} · "
            + (f"{favoritas} favorita" + ("" if favoritas == 1 else "s") if favoritas else f"{reproducciones} reproducciones")
        )
        if favoritas:
            item["contexto"] = "Tiene canciones marcadas como favoritas"
        elif reproducciones:
            item["contexto"] = f"Lo escuchaste {reproducciones} vez" + ("" if reproducciones == 1 else "es")
        out.append(item)
    return out


def recomendaciones_inicio(limite: int = 60) -> list[dict]:
    """Sugerencias locales con contexto basado en datos reales."""
    limite = _limite_dashboard(limite, predeterminado=60, maximo=100)
    if limite == 0:
        return []

    candidatos: list[dict] = []
    vistos: set[tuple[str, int]] = set()

    def agregar(items: list[dict], tipo: str, origen: str, contexto: str = "") -> None:
        for base in items:
            item = dict(base)
            item["tipo"] = tipo
            item["origen"] = item.get("origen") or origen
            if not item.get("contexto"):
                if int(item.get("favorita") or 0):
                    item["contexto"] = "Favorita"
                elif origen == "reciente":
                    item["contexto"] = contexto or "Añadida hace poco"
                elif origen == "escucha" and int(item.get("reproducciones_total") or 0) > 0:
                    item["contexto"] = "Muy repetida"
                elif contexto:
                    item["contexto"] = contexto
            item_id = int(item.get("id") or 0)
            clave = (tipo, item_id)
            if item_id <= 0 or clave in vistos:
                continue
            vistos.add(clave)
            candidatos.append(item)

    agregar([_item_dashboard_pista(f, "reciente") for f in pistas_recientes(limite=min(limite, 36))], "pista", "reciente", "Añadida hace poco")
    agregar(albums_con_canciones_que_gustan(limite=min(limite, 24)), "album", "gustos")
    agregar([_item_dashboard_artista(f, "reciente") for f in artistas_recientes(limite=min(limite, 24))], "artista", "reciente", "Reciente en tu biblioteca")
    agregar([_item_dashboard_pista(f, "escucha") for f in pistas_mas_escuchadas(limite=min(limite, 30))], "pista", "escucha")

    if not candidatos:
        return []

    favoritos = [item for item in candidatos if item.get("origen") in {"gustos", "escucha"}]
    exploracion = [item for item in candidatos if item.get("origen") not in {"gustos", "escucha"}]

    # Barajamos antes de mezclar para que cada carga ofrezca sugerencias
    # frescas. Sin esto, "Lo que podrías probar" mostraba siempre las mismas
    # canciones en el mismo orden (pistas_recientes / mas_escuchadas son
    # determinísticas por diseño, así que la única fuente de variedad real
    # es introducir aleatoriedad aquí).
    random.shuffle(favoritos)
    random.shuffle(exploracion)

    mezcla: list[dict] = []
    while favoritos or exploracion:
        if favoritos:
            mezcla.append(favoritos.pop(0))
        if exploracion:
            mezcla.append(exploracion.pop(0))
        if exploracion:
            mezcla.append(exploracion.pop(0))
        if len(mezcla) >= limite:
            break

    return mezcla[:limite]


def detalle_artista(artista_id: int) -> Optional[dict]:
    """Retorna detalle de artista con albums y pistas principales."""
    artista = obtener_una_fila(
        """
        SELECT a.id, a.nombre, a.mb_artist_id,
               COUNT(DISTINCT CASE WHEN p.id IS NOT NULL THEN al.id END) AS num_albums,
               COUNT(DISTINCT p.id) AS num_pistas,
               COALESCE(SUM(p.duracion_seg), 0) AS duracion_total_seg
        FROM artistas a
        LEFT JOIN albums al ON al.artista_id = a.id
        LEFT JOIN pistas p ON p.artista_id = a.id AND p.estado='biblioteca'
        WHERE a.id = ?
        GROUP BY a.id
        """,
        (artista_id,),
    )
    if not artista:
        return None
    resultado = dict(artista)
    resultado["portada_ruta"] = _resolver_avatar_artista(None, resultado.get("nombre"))
    resultado["portada_hd_ruta"] = _resolver_avatar_hd_artista(None, resultado.get("nombre"))
    _agregar_portada_display(resultado)
    resultado["albums"] = listar_albums(artista_id=artista_id, orden="anio")
    resultado["pistas"] = listar_pistas(artista_id=artista_id, orden="album", limite=None)
    resultado["pistas_destacadas"] = listar_pistas(artista_id=artista_id, orden="reproducida", limite=10)
    resultado["duracion_total_seg"] = sum(int(p.get("duracion_seg") or 0) for p in resultado["pistas"])
    return resultado


def listar_sesiones_import(limite: int = 30) -> list[dict]:
    """Historial de corridas de importación."""
    filas = obtener_filas(
        """
        SELECT *
        FROM sesiones_import
        ORDER BY iniciado_en DESC, id DESC
        LIMIT ?
        """,
        (limite,),
    )
    return [dict(f) for f in filas]


def historial_reciente(limite: int = 20) -> list[dict]:
    """El historial de reproducciones mas reciente."""
    filas = obtener_filas(
        """
        SELECT h.*, p.ruta_archivo, p.artista_nombre, p.album_titulo
        FROM historial h
        LEFT JOIN pistas p ON p.id = h.pista_id
        ORDER BY h.reproducido_en DESC
        LIMIT ?
        """,
        (limite,),
    )
    return [dict(f) for f in filas]


def pistas_nunca_escuchadas(limite: int = 10) -> list[dict]:
    """Pistas de biblioteca que nunca han sido reproducidas ni tienen historial."""
    limite = _limite_dashboard(limite, predeterminado=10, maximo=50)
    filas = obtener_filas(
        """
        SELECT
            p.*,
            al.portada_ruta AS album_portada_ruta,
            al.mb_release_id AS album_mb_release_id,
            0 AS reproducciones_total
        FROM pistas p
        LEFT JOIN albums al ON al.id = p.album_id
        LEFT JOIN historial h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca'
          AND h.id IS NULL
          AND COALESCE(p.veces_reproducida, 0) = 0
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (limite,),
    )
    return [_item_dashboard_pista(_normalizar_pista_fila(dict(fila)), "olvidada") for fila in filas]


def pistas_menos_escuchadas(limite: int = 10) -> list[dict]:
    """Pistas de biblioteca que han sido reproducidas pero pocas veces (fallback para hábitos)."""
    limite = _limite_dashboard(limite, predeterminado=10, maximo=50)
    filas = obtener_filas(
        """
        SELECT
            p.*,
            al.portada_ruta AS album_portada_ruta,
            al.mb_release_id AS album_mb_release_id,
            COUNT(h.id) AS reproducciones_total
        FROM pistas p
        LEFT JOIN albums al ON al.id = p.album_id
        LEFT JOIN historial h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca'
        GROUP BY p.id
        HAVING COUNT(h.id) > 0
        ORDER BY COUNT(h.id) ASC, RANDOM()
        LIMIT ?
        """,
        (limite,),
    )
    return [_item_dashboard_pista(_normalizar_pista_fila(dict(fila)), "poco_escuchada") for fila in filas]


def estadisticas_extras_perfil() -> dict:
    """Estadísticas adicionales para la vista de perfil."""
    hora_pico_fila = obtener_una_fila(
        """
        SELECT CAST(strftime('%H', reproducido_en, 'localtime') AS INTEGER) AS hora, COUNT(*) AS n
        FROM historial
        GROUP BY hora ORDER BY n DESC LIMIT 1
        """
    )
    hora_pico = int(hora_pico_fila["hora"]) if hora_pico_fila else None

    # Días activos del MES CALENDARIO en curso (no una ventana móvil de 30
    # días): la UI lo rotula "este mes", así que el cálculo debe coincidir con
    # el mes actual y reiniciarse en cada cambio de mes. 'localtime' alinea el
    # corte con `actividad_mes` (evita contar como del mes una escucha de fin
    # de mes que en UTC cae en el mes siguiente).
    dias_activos_fila = obtener_una_fila(
        """
        SELECT COUNT(DISTINCT date(reproducido_en, 'localtime')) AS dias
        FROM historial
        WHERE strftime('%Y-%m', reproducido_en, 'localtime') = strftime('%Y-%m', 'now', 'localtime')
        """
    )
    dias_activos = int(dias_activos_fila["dias"]) if dias_activos_fila else 0

    anio_fila = obtener_una_fila(
        """
        SELECT CAST(p.anio AS TEXT) AS anio, COUNT(h.id) AS n
        FROM historial h
        JOIN pistas p ON p.id = h.pista_id
        WHERE p.anio IS NOT NULL AND CAST(COALESCE(p.anio, 0) AS INTEGER) > 1900
        GROUP BY p.anio ORDER BY n DESC LIMIT 1
        """
    )
    anio_mas_escuchado = str(anio_fila["anio"]) if anio_fila else ""

    # Géneros reales de hoy — ambas fechas comparadas en localtime (evita desfase UTC)
    generos_hoy_filas = obtener_filas(
        """
        SELECT TRIM(COALESCE(p.genero, '')) AS genero, COUNT(h.id) AS n
        FROM historial h
        JOIN pistas p ON p.id = h.pista_id
        WHERE date(h.reproducido_en, 'localtime') = date('now', 'localtime')
          AND TRIM(COALESCE(p.genero, '')) != ''
        GROUP BY genero ORDER BY n DESC LIMIT 6
        """
    )

    # Artistas escuchados hoy (fallback cuando no hay géneros disponibles)
    artistas_hoy_filas = obtener_filas(
        """
        SELECT COALESCE(TRIM(p.artista_nombre), '') AS artista, COUNT(h.id) AS n
        FROM historial h
        JOIN pistas p ON p.id = h.pista_id
        WHERE date(h.reproducido_en, 'localtime') = date('now', 'localtime')
          AND COALESCE(TRIM(p.artista_nombre), '') != ''
        GROUP BY artista ORDER BY n DESC LIMIT 3
        """
    )

    # Total de escuchas hoy (para mood)
    escuchas_hoy_fila = obtener_una_fila(
        """
        SELECT COUNT(*) AS n
        FROM historial
        WHERE date(reproducido_en, 'localtime') = date('now', 'localtime')
        """
    )
    total_escuchas_hoy = int(dict(escuchas_hoy_fila).get("n") or 0) if escuchas_hoy_fila else 0

    generos_siempre_filas = obtener_filas(
        """
        SELECT TRIM(COALESCE(p.genero, '')) AS genero, COUNT(h.id) AS n
        FROM historial h
        JOIN pistas p ON p.id = h.pista_id
        WHERE TRIM(COALESCE(p.genero, '')) != ''
        GROUP BY genero ORDER BY n DESC LIMIT 6
        """
    )

    actividad_mes_filas = obtener_filas(
        """
        SELECT CAST(strftime('%d', reproducido_en, 'localtime') AS INTEGER) AS dia,
               COUNT(*) AS reproducciones
        FROM historial
        WHERE strftime('%Y-%m', reproducido_en, 'localtime') = strftime('%Y-%m', 'now', 'localtime')
        GROUP BY dia
        """
    )
    # IMPORTANTE: claves como STRING para que PySide6 las convierta a JS objeto accesible
    # (PySide6 no convierte correctamente claves enteras en dicts anidados de QVariant)
    actividad_mes: dict[str, int] = {str(int(f["dia"])): int(f["reproducciones"]) for f in actividad_mes_filas}

    # Estadísticas de lo que ha escuchado (no de la biblioteca)
    escuchas_fila = obtener_una_fila(
        """
        SELECT
            COUNT(*) AS total_escuchas,
            COUNT(DISTINCT h.pista_id) AS pistas_distintas,
            COUNT(DISTINCT COALESCE(p.artista_id, 0)) AS artistas_distintos,
            COUNT(DISTINCT COALESCE(p.album_id, 0)) AS albums_distintos,
            COALESCE(SUM(CASE WHEN h.duracion_seg > 0 THEN h.duracion_seg ELSE 0 END), 0.0) AS tiempo_seg
        FROM historial h
        LEFT JOIN pistas p ON p.id = h.pista_id
        """
    )
    if escuchas_fila:
        total_escuchas = int(escuchas_fila["total_escuchas"] or 0)
        pistas_distintas = int(escuchas_fila["pistas_distintas"] or 0)
        artistas_distintos = max(0, int(escuchas_fila["artistas_distintos"] or 0) - 1)  # resta el artista_id=0
        albums_distintos = max(0, int(escuchas_fila["albums_distintos"] or 0) - 1)
        tiempo_escuchado_seg = float(escuchas_fila["tiempo_seg"] or 0.0)
    else:
        total_escuchas = pistas_distintas = artistas_distintos = albums_distintos = 0
        tiempo_escuchado_seg = 0.0

    # Artistas y álbumes distintos: recalcular sin el id=0
    artistas_reales_fila = obtener_una_fila(
        """
        SELECT COUNT(DISTINCT p.artista_id) AS n
        FROM historial h
        JOIN pistas p ON p.id = h.pista_id
        WHERE p.artista_id IS NOT NULL AND p.artista_id > 0
        """
    )
    artistas_distintos = int(dict(artistas_reales_fila).get("n") or 0) if artistas_reales_fila else 0

    albums_reales_fila = obtener_una_fila(
        """
        SELECT COUNT(DISTINCT p.album_id) AS n
        FROM historial h
        JOIN pistas p ON p.id = h.pista_id
        WHERE p.album_id IS NOT NULL AND p.album_id > 0
        """
    )
    albums_distintos = int(dict(albums_reales_fila).get("n") or 0) if albums_reales_fila else 0

    return {
        "hora_pico": hora_pico,
        "dias_activos_mes": dias_activos,
        "anio_mas_escuchado": anio_mas_escuchado,
        "generos_hoy": [{"genero": r["genero"], "n": int(r["n"])} for r in generos_hoy_filas],
        "artistas_hoy": [{"artista": r["artista"], "n": int(r["n"])} for r in artistas_hoy_filas],
        "total_escuchas_hoy": total_escuchas_hoy,
        "generos_siempre": [{"genero": r["genero"], "n": int(r["n"])} for r in generos_siempre_filas],
        "actividad_mes": actividad_mes,
        # Escuchas reales del historial
        "total_escuchas": total_escuchas,
        "pistas_distintas_escuchadas": pistas_distintas,
        "artistas_distintos_escuchados": artistas_distintos,
        "albums_distintos_escuchados": albums_distintos,
        "tiempo_escuchado_seg": tiempo_escuchado_seg,
    }


# =============================================================================
# PLAYLISTS
# =============================================================================

def _ahora_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalizar_nombre_playlist(nombre: str) -> str:
    return re.sub(r"\s+", " ", str(nombre or "").strip())


def _json_compacto(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _playlist_error(mensaje: str) -> ValueError:
    return ValueError(mensaje)


def _obtener_playlist(playlist_id: int) -> Optional[dict]:
    fila = obtener_una_fila("SELECT * FROM playlists WHERE id = ?", (int(playlist_id or 0),))
    return dict(fila) if fila else None


def _obtener_playlist_por_auto_key(auto_key: str) -> Optional[dict]:
    fila = obtener_una_fila(
        "SELECT * FROM playlists WHERE auto_key = ? ORDER BY id LIMIT 1",
        (str(auto_key or "").strip(),),
    )
    return dict(fila) if fila else None


def playlist_existe(playlist_id: int) -> bool:
    """True si la playlist existe y es visible (chequeo ligero, sin cargar pistas).

    Pensada para que la UI sepa si una sesión DJ sigue vinculada a una playlist
    real: si el usuario la borró, el botón "Guardar como playlist" debe volver a
    estar disponible.
    """
    pid = int(playlist_id or 0)
    if pid <= 0:
        return False
    fila = obtener_una_fila(
        "SELECT 1 FROM playlists WHERE id = ? AND COALESCE(visible, 1) = 1",
        (pid,),
    )
    return fila is not None


def _es_playlist_favoritos(playlist: Optional[dict]) -> bool:
    return bool(playlist and playlist.get("auto_key") == PLAYLIST_FAVORITOS_AUTO_KEY)


def _subtipo_playlist(playlist: dict) -> str:
    subtipo = str(playlist.get("subtipo") or "").strip()
    if subtipo:
        return subtipo
    tipo = str(playlist.get("tipo") or "manual").strip()
    if tipo == "manual":
        return "usuario"
    if tipo == "sistema":
        return "sistema"
    return tipo or "usuario"


def _origen_playlist(playlist: dict) -> str:
    origen = str(playlist.get("origen") or "").strip()
    if origen:
        return origen
    tipo = str(playlist.get("tipo") or "manual").strip()
    return "usuario" if tipo == "manual" else "generado"


def _etiqueta_playlist(subtipo: str, tipo: str, origen: str) -> str:
    etiquetas = {
        "favoritos": "Me gusta",
        "usuario": "Manual",
        "this_is": "This is...",
        "mood": "Inteligente",
        "top_canciones": "Top",
        "top_artistas": "Mix",
        "top_albumes": "Mix",
        "album_mix": "Mix",
        "artist_mix": "Mix",
        "recientes": "Para ti",
        "descubrimiento_local": "Para ti",
    }
    if subtipo in etiquetas:
        return etiquetas[subtipo]
    if tipo == "automatica" or origen == "generado":
        return "Para ti"
    if tipo == "sistema":
        return "Sistema"
    return "Manual"


def _validar_nombre_playlist(nombre: str, *, excluir_id: Optional[int] = None) -> str:
    limpio = _normalizar_nombre_playlist(nombre)
    if not limpio:
        raise _playlist_error("El nombre de la playlist es obligatorio.")
    if len(limpio) > 120:
        raise _playlist_error("El nombre de la playlist es demasiado largo.")

    params: list = [limpio]
    condicion_exclusion = ""
    if excluir_id:
        condicion_exclusion = "AND id <> ?"
        params.append(int(excluir_id))
    duplicada = obtener_una_fila(
        f"""
        SELECT id
        FROM playlists
        WHERE visible = 1
          AND lower(nombre) = lower(?)
          {condicion_exclusion}
        LIMIT 1
        """,
        tuple(params),
    )
    if duplicada:
        raise _playlist_error("Ya existe una playlist con ese nombre.")
    return limpio


def _estadisticas_playlist(playlist_id: int) -> dict:
    fila = obtener_una_fila(
        """
        SELECT
            COUNT(pp.pista_id) AS num_pistas,
            COALESCE(SUM(COALESCE(p.duracion_seg, 0)), 0) AS duracion_total_seg,
            COALESCE(SUM(COALESCE(h.reproducciones, p.veces_reproducida, 0)), 0) AS reproducciones_total
        FROM pistas_playlist pp
        JOIN pistas p ON p.id = pp.pista_id
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        WHERE pp.playlist_id = ?
        """,
        (playlist_id,),
    )
    return dict(fila) if fila else {"num_pistas": 0, "duracion_total_seg": 0, "reproducciones_total": 0}


def _permisos_playlist(playlist: dict) -> dict:
    es_favoritos = _es_playlist_favoritos(playlist)
    tipo = str(playlist.get("tipo") or "manual")
    editable = not es_favoritos
    manual = tipo == "manual"
    return {
        "es_favoritos": es_favoritos,
        "puede_renombrar": editable,
        "puede_editar_descripcion": editable,
        "puede_agregar": editable,
        "puede_reordenar": editable,
        "puede_quitar": True,
        "puede_vaciar": editable and not es_favoritos,
        "puede_eliminar": not es_favoritos,
        "puede_duplicar": not es_favoritos,
        "puede_anclar": not es_favoritos,
        "puede_regenerar": tipo == "automatica" and not es_favoritos,
        "es_manual": manual,
        "es_automatica": tipo == "automatica",
    }


def _normalizar_playlist_fila(fila: dict) -> dict:
    item = dict(fila)
    playlist_id = int(item.get("id") or item.get("playlist_id") or 0)
    tipo = str(item.get("tipo") or "manual").strip() or "manual"
    subtipo = _subtipo_playlist(item)
    origen = _origen_playlist(item)
    item["id"] = playlist_id
    item["playlist_id"] = playlist_id
    item["tipo"] = tipo
    item["subtipo"] = subtipo
    item["tipo_playlist"] = subtipo
    item["origen"] = origen
    item["es_anclada"] = bool(item.get("es_anclada") or 0)
    item["anclada_en"] = str(item.get("anclada_en") or "")
    item["visible"] = bool(item.get("visible") if item.get("visible") is not None else 1)
    item["auto_actualizable"] = bool(item.get("auto_actualizable") or 0)
    item["editada_por_usuario"] = bool(item.get("editada_por_usuario") or 0)
    item["num_pistas"] = int(item.get("num_pistas") or 0)
    item["duracion_total_seg"] = float(item.get("duracion_total_seg") or 0)
    item["reproducciones_total"] = int(item.get("reproducciones_total") or 0)
    item["portadas"] = item.get("portadas") or _portadas_playlist(playlist_id)
    if not item.get("portada_ruta"):
        item["portada_ruta"] = item["portadas"][0] if item["portadas"] else ""
    _agregar_portada_display(item)
    item["etiqueta_tipo"] = _etiqueta_playlist(subtipo, tipo, origen)
    item.update(_permisos_playlist(item))
    return item


def _ids_playlist(playlist_id: int) -> list[int]:
    filas = obtener_filas(
        "SELECT pista_id FROM pistas_playlist WHERE playlist_id = ? ORDER BY posicion",
        (playlist_id,),
    )
    return [int(f["pista_id"]) for f in filas]


def _recomponer_posiciones_playlist(conexion, playlist_id: int) -> None:
    filas = conexion.execute(
        """
        SELECT pista_id
        FROM pistas_playlist
        WHERE playlist_id = ?
        ORDER BY posicion, agregado_en, pista_id
        """,
        (playlist_id,),
    ).fetchall()
    for posicion, fila in enumerate(filas, start=1):
        conexion.execute(
            "UPDATE pistas_playlist SET posicion = ? WHERE playlist_id = ? AND pista_id = ?",
            (posicion, playlist_id, fila["pista_id"]),
        )


def _reemplazar_pistas_playlist(
    conexion,
    playlist_id: int,
    pista_ids: list[int],
    *,
    tope: Optional[int] = PLAYLIST_AUTO_MAX_PISTAS,
) -> None:
    """Reescribe las pistas de una playlist (dedupe + posiciones 1..N).

    `tope` limita cuántas pistas se materializan: las playlists automáticas
    pasan su tope (50 global, 80 para "This is"); las operaciones sobre listas
    ya acotadas (favoritos, reordenar, duplicar) pasan ``None`` para no
    truncar el conjunto.
    """
    vistos: set[int] = set()
    ids_limpios: list[int] = []
    for pista_id in pista_ids:
        try:
            pid = int(pista_id)
        except (TypeError, ValueError):
            continue
        if pid <= 0 or pid in vistos:
            continue
        vistos.add(pid)
        ids_limpios.append(pid)
        if tope is not None and len(ids_limpios) >= tope:
            break

    conexion.execute("DELETE FROM pistas_playlist WHERE playlist_id = ?", (playlist_id,))
    for posicion, pista_id in enumerate(ids_limpios, start=1):
        conexion.execute(
            """
            INSERT INTO pistas_playlist(playlist_id, pista_id, posicion, agregado_en)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (playlist_id, pista_id, posicion),
        )
    conexion.execute(
        "UPDATE playlists SET actualizado_en = datetime('now') WHERE id = ?",
        (playlist_id,),
    )


def _marcar_editada_si_corresponde(conexion, playlist: dict) -> None:
    if playlist.get("tipo") == "manual" or _es_playlist_favoritos(playlist):
        return
    conexion.execute(
        """
        UPDATE playlists
        SET editada_por_usuario = 1,
            auto_actualizable = 0,
            actualizado_en = datetime('now')
        WHERE id = ?
        """,
        (int(playlist["id"]),),
    )


def _pista_existe(pista_id: int) -> bool:
    fila = obtener_una_fila(
        "SELECT id FROM pistas WHERE id = ? AND estado = 'biblioteca'",
        (int(pista_id or 0),),
    )
    return fila is not None


def _directorio_portadas_playlist() -> Path:
    base = _settings.DEFAULT_CACHE_DIR or Path(tempfile.gettempdir()) / "nb_sound"
    return base / "playlist_covers"


def _portadas_playlist_con_ids(playlist_id: int, limite: int = 4) -> list[dict]:
    filas = obtener_filas(
        """
        SELECT
            p.id AS pista_id,
            al.portada_ruta AS album_portada_ruta,
            al.mb_release_id AS album_mb_release_id
        FROM pistas_playlist pp
        JOIN pistas p ON p.id = pp.pista_id
        LEFT JOIN albums al ON al.id = p.album_id
        WHERE pp.playlist_id = ? AND p.estado = 'biblioteca'
        ORDER BY pp.posicion
        LIMIT 80
        """,
        (playlist_id,),
    )
    out: list[dict] = []
    rutas_vistas: set[str] = set()
    hashes_visuales: list[int] = []
    limite_seguro = max(1, int(limite or 4))
    for fila in filas:
        portada = _resolver_portada_fila(fila["album_portada_ruta"], fila["album_mb_release_id"])
        if not portada:
            continue
        path_local = _ruta_local_portada(portada)
        if path_local is not None and not path_local.exists():
            continue
        clave_ruta = _clave_portada_playlist(portada)
        if clave_ruta in rutas_vistas:
            continue
        hash_visual = _hash_visual_portada_playlist(portada)
        if hash_visual is not None and any(_distancia_hamming(hash_visual, previo) <= 6 for previo in hashes_visuales):
            continue
        rutas_vistas.add(clave_ruta)
        if hash_visual is not None:
            hashes_visuales.append(hash_visual)
        out.append({"pista_id": int(fila["pista_id"]), "portada_ruta": portada})
        if len(out) >= limite_seguro:
            break
    return out


def _firma_rapida_playlist(playlist_id: int, limite: int = 4) -> str:
    """Firma barata (sin decodificar imagenes) de las entradas que alimentan la
    caratula de la playlist: id de pista + ruta de portada + (mtime, size) del
    archivo. Cambia cuando cambian las pistas, su orden, la portada de su album
    o el contenido del archivo de portada.

    Permite a `generar_portada_playlist` decidir si la caratula sigue vigente
    SIN abrir ni decodificar ninguna imagen (el hash perceptual de
    `_portadas_playlist_con_ids` es lo caro). Espeja la consulta de candidatos
    de `_portadas_playlist_con_ids`; manten ambas consistentes.
    """
    filas = obtener_filas(
        """
        SELECT
            p.id AS pista_id,
            al.portada_ruta AS album_portada_ruta,
            al.mb_release_id AS album_mb_release_id
        FROM pistas_playlist pp
        JOIN pistas p ON p.id = pp.pista_id
        LEFT JOIN albums al ON al.id = p.album_id
        WHERE pp.playlist_id = ? AND p.estado = 'biblioteca'
        ORDER BY pp.posicion
        LIMIT 80
        """,
        (int(playlist_id),),
    )
    piezas = [PLAYLIST_COVER_ALGO_VERSION, str(int(playlist_id)), str(max(1, int(limite or 4)))]
    for fila in filas:
        portada = _resolver_portada_fila(fila["album_portada_ruta"], fila["album_mb_release_id"])
        if not portada:
            continue
        marca = ""
        path_local = _ruta_local_portada(portada)
        if path_local is not None:
            try:
                st = path_local.stat()
            except OSError:
                # No existe / inaccesible: igual que en la seleccion, no aporta.
                continue
            marca = f"{st.st_mtime_ns}:{st.st_size}"
        piezas.append(f"{int(fila['pista_id'])}:{portada}:{marca}")
    return hashlib.sha256("|".join(piezas).encode("utf-8")).hexdigest()[:24]


def _clave_portada_playlist(ruta: str) -> str:
    path = _ruta_local_portada(ruta)
    if path is not None:
        try:
            return str(path.resolve())
        except OSError:
            return str(path.absolute())
    return str(ruta or "").strip()


def _hash_visual_portada_playlist(ruta: str) -> Optional[int]:
    path = _ruta_local_portada(ruta)
    if path is None or not path.exists() or not _pillow_disponible():
        return None
    try:
        stat = path.stat()
        clave = (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))
        if clave in _PLAYLIST_COVER_HASH_CACHE:
            return _PLAYLIST_COVER_HASH_CACHE[clave]
        from PIL import Image, ImageOps

        with Image.open(path) as img:
            base = ImageOps.exif_transpose(img).convert("RGB")
            color = base.resize((1, 1), Image.Resampling.LANCZOS).getpixel((0, 0))
            gris = base.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
            valores = list(gris.tobytes())
        promedio = sum(valores) / max(1, len(valores))
        digest = 0
        for valor in valores:
            digest = (digest << 1) | (1 if valor >= promedio else 0)
        color_digest = ((color[0] // 16) << 8) | ((color[1] // 16) << 4) | (color[2] // 16)
        digest = (digest << 12) | color_digest
        _PLAYLIST_COVER_HASH_CACHE[clave] = digest
        return digest
    except Exception as exc:
        _warn_portada_once(
            f"playlist-cover-hash:{ruta}",
            "No se pudo calcular hash visual de portada de playlist (%s): %s",
            ruta,
            exc,
        )
        return None


def _distancia_hamming(a: int, b: int) -> int:
    return int(a ^ b).bit_count()


def _firma_portada_playlist(playlist_id: int, entradas: list[dict]) -> str:
    piezas = [PLAYLIST_COVER_ALGO_VERSION, str(playlist_id)]
    for entrada in entradas[:4]:
        piezas.append(f"{entrada.get('pista_id')}:{entrada.get('portada_ruta') or ''}")
    return hashlib.sha256("|".join(piezas).encode("utf-8")).hexdigest()[:24]


def _color_desde_digest(digest: str, offset: int = 0) -> tuple[int, int, int]:
    base = digest[offset:offset + 6].ljust(6, "0")
    r = int(base[0:2], 16)
    g = int(base[2:4], 16)
    b = int(base[4:6], 16)
    return (max(24, min(210, r)), max(28, min(210, g)), max(36, min(220, b)))


def _crear_lienzo_playlist(size: int, digest: str):
    from PIL import Image, ImageDraw

    color_a = _color_desde_digest(digest, 0)
    color_b = _color_desde_digest(digest, 8)
    img = Image.new("RGB", (size, size), color_a)
    draw = ImageDraw.Draw(img)
    for y in range(size):
        ratio = y / max(1, size - 1)
        color = tuple(int(color_a[i] * (1 - ratio) + color_b[i] * ratio) for i in range(3))
        draw.line((0, y, size, y), fill=color)
    draw.rectangle((0, size * 0.62, size, size), fill=tuple(max(0, c - 36) for c in color_b))
    draw.line((0, size * 0.62, size, size * 0.42), fill=tuple(min(255, c + 34) for c in color_a), width=max(2, size // 80))
    return img


def _pegar_portada_en_slot(base, ruta: str, slot: tuple[int, int, int, int], digest: str, offset: int) -> bool:
    from PIL import Image, ImageOps

    path = _ruta_local_portada(ruta)
    if path is None or not path.exists():
        return False
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            ancho = max(1, slot[2] - slot[0])
            alto = max(1, slot[3] - slot[1])
            thumb = ImageOps.contain(img, (ancho, alto), method=Image.Resampling.LANCZOS)
            x = slot[0] + max(0, (ancho - thumb.width) // 2)
            y = slot[1] + max(0, (alto - thumb.height) // 2)
            base.paste(thumb, (x, y))
        return True
    except Exception as exc:
        _warn_portada_once(
            f"playlist-cover-source:{ruta}",
            "No se pudo usar portada de playlist (%s): %s",
            ruta,
            exc,
        )
        return False


def obtener_portadas_playlist(playlist_id: int, limite: int = 4) -> list[str]:
    covers: list[str] = []
    for entrada in _portadas_playlist_con_ids(int(playlist_id or 0), limite=max(limite * 3, 4)):
        portada = str(entrada.get("portada_ruta") or "").strip()
        if portada and portada not in covers:
            covers.append(portada)
        if len(covers) >= limite:
            break
    return covers


def _portadas_playlist(playlist_id: int, limite: int = 4) -> list[str]:
    return obtener_portadas_playlist(playlist_id, limite=limite)


def generar_portada_playlist(playlist_id: int) -> Optional[str]:
    playlist = _obtener_playlist(int(playlist_id or 0))
    if not playlist:
        return None
    if not _pillow_disponible():
        return str(playlist.get("portada_ruta") or "") or None

    try:
        from PIL import ImageDraw

        size = 512
        # Firma barata (sin decodificar imagenes) de las entradas de la
        # caratula. Nombra el archivo y habilita el early-return de abajo sin
        # abrir una sola imagen cuando la playlist no cambio: asi la red de
        # seguridad de arranque (`asegurar_portadas_playlists`) no
        # re-decodifica miles de portadas en cada inicio.
        fastsig = _firma_rapida_playlist(int(playlist_id), limite=4)
        destino = _directorio_portadas_playlist() / f"playlist_{int(playlist_id)}_{fastsig}.png"
        destino.parent.mkdir(parents=True, exist_ok=True)

        actual = str(playlist.get("portada_ruta") or "").strip()
        if actual == str(destino) and destino.exists() and destino.stat().st_size > 0:
            return str(destino)

        # Regeneracion real: recien aqui seleccionamos las portadas con dedupe
        # visual (esto si decodifica) y construimos el mosaico.
        entradas = _portadas_playlist_con_ids(int(playlist_id), limite=4)
        digest = _firma_portada_playlist(int(playlist_id), entradas)
        base = _crear_lienzo_playlist(size, digest)
        total = len(entradas)
        if total == 1:
            slots = [(0, 0, size, size)]
        elif total == 2:
            slots = [(0, 0, size // 2, size), (size // 2, 0, size, size)]
        elif total == 3:
            slots = [(0, 0, size // 2, size), (size // 2, 0, size, size // 2), (size // 2, size // 2, size, size)]
        else:
            slots = [
                (0, 0, size // 2, size // 2),
                (size // 2, 0, size, size // 2),
                (0, size // 2, size // 2, size),
                (size // 2, size // 2, size, size),
            ]

        usadas = 0
        for idx, entrada in enumerate(entradas[:4]):
            ruta = str(entrada.get("portada_ruta") or "")
            if ruta and _pegar_portada_en_slot(base, ruta, slots[idx], digest, idx * 6):
                usadas += 1
        if usadas == 0:
            draw = ImageDraw.Draw(base)
            color = tuple(min(255, c + 42) for c in _color_desde_digest(digest, 12))
            margen = size // 5
            draw.rounded_rectangle(
                (margen, margen, size - margen, size - margen),
                radius=size // 16,
                outline=color,
                width=max(4, size // 48),
            )

        tmp = destino.with_name(f".{destino.name}.tmp")
        base.save(tmp, format="PNG", optimize=True)
        tmp.replace(destino)
        return str(destino)
    except Exception as exc:
        logger.warning("No se pudo generar portada de playlist %s: %s", playlist_id, exc, exc_info=True)
        try:
            if "tmp" in locals() and tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return str(playlist.get("portada_ruta") or "") or None


def actualizar_portada_playlist_si_cambio(playlist_id: int) -> Optional[str]:
    nueva = generar_portada_playlist(int(playlist_id or 0))
    if not nueva:
        return None
    ejecutar(
        """
        UPDATE playlists
        SET portada_ruta = ?, actualizado_en = datetime('now')
        WHERE id = ? AND COALESCE(portada_ruta, '') <> ?
        """,
        (nueva, int(playlist_id), nueva),
    )
    return nueva


def asegurar_portadas_playlists() -> list[int]:
    """Garantiza que cada playlist visible tenga su carátula "hecha".

    Red de seguridad: barre todas las playlists visibles y regenera la carátula
    (mosaico con las portadas de sus canciones) en las que falte o esté
    obsoleta. Cubre casos que las regeneraciones puntuales no atrapan: playlists
    creadas sin canciones con portada, o cuyas canciones cambiaron por una vía
    que no actualizó la carátula (p. ej. altas más allá de las 4 primeras).

    Es idempotente y barata cuando ya están al día: `generar_portada_playlist`
    hace early-return (sin reescribir el PNG) si el digest de las portadas
    coincide con la carátula vigente. Devuelve los IDs realmente actualizados,
    para que la UI refresque solo si hubo cambios.
    """
    actualizadas: list[int] = []
    try:
        filas = obtener_filas(
            "SELECT id, portada_ruta FROM playlists WHERE COALESCE(visible, 1) = 1"
        )
    except Exception as exc:
        logger.warning("No se pudieron listar playlists para asegurar portadas: %s", exc)
        return actualizadas

    for fila in filas:
        try:
            playlist_id = int(fila["id"])
        except (TypeError, ValueError, KeyError):
            continue
        if playlist_id <= 0:
            continue
        anterior = str(fila["portada_ruta"] or "").strip()
        try:
            nueva = actualizar_portada_playlist_si_cambio(playlist_id)
        except Exception as exc:
            logger.warning("No se pudo asegurar la portada de la playlist %s: %s", playlist_id, exc)
            continue
        if nueva and str(nueva).strip() != anterior:
            actualizadas.append(playlist_id)
    return actualizadas


def _sincronizar_playlist_favoritos() -> int:
    existente = _obtener_playlist_por_auto_key(PLAYLIST_FAVORITOS_AUTO_KEY)
    with transaccion() as conexion:
        if existente:
            playlist_id = int(existente["id"])
            conexion.execute(
                """
                UPDATE playlists
                SET nombre = 'Me gusta',
                    descripcion = 'Canciones marcadas como favoritas.',
                    tipo = 'sistema',
                    subtipo = 'favoritos',
                    origen = 'sistema',
                    visible = 1,
                    auto_actualizable = 1,
                    editada_por_usuario = 0,
                    actualizado_en = datetime('now')
                WHERE id = ?
                """,
                (playlist_id,),
            )
        else:
            playlist_id = conexion.execute(
                """
                INSERT INTO playlists(
                    nombre, descripcion, tipo, subtipo, origen, regla_json, auto_key,
                    es_anclada, visible, auto_actualizable, editada_por_usuario
                )
                VALUES (
                    'Me gusta', 'Canciones marcadas como favoritas.', 'sistema',
                    'favoritos', 'sistema', ?, ?, 1, 1, 1, 0
                )
                """,
                (_json_compacto({"tipo": "favoritos"}), PLAYLIST_FAVORITOS_AUTO_KEY),
            ).lastrowid

        filas = conexion.execute(
            """
            SELECT id
            FROM pistas
            WHERE estado = 'biblioteca' AND COALESCE(favorita, 0) = 1
            ORDER BY COALESCE(ultimo_acceso, actualizado_en, indexado_en) DESC, titulo COLLATE NOCASE
            """
        ).fetchall()
        # "Me gusta" refleja TODAS las favoritas, sin tope.
        _reemplazar_pistas_playlist(conexion, playlist_id, [int(f["id"]) for f in filas], tope=None)
    actualizar_portada_playlist_si_cambio(playlist_id)
    return playlist_id


def _candidatos_favoritas_sonando() -> list[int]:
    filas = obtener_filas(
        """
        SELECT p.id, COALESCE(h.reproducciones, p.veces_reproducida, 0) AS reproducciones_total
        FROM pistas p
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca'
          AND COALESCE(p.favorita, 0) = 1
          AND COALESCE(h.reproducciones, p.veces_reproducida, 0) > 0
        ORDER BY reproducciones_total DESC, COALESCE(p.ultimo_acceso, p.actualizado_en, p.indexado_en) DESC
        LIMIT ?
        """,
        (PLAYLIST_AUTO_MAX_PISTAS,),
    )
    return [int(f["id"]) for f in filas]


def _candidatos_redescubrir() -> list[int]:
    filas = obtener_filas(
        """
        SELECT p.id, COALESCE(h.reproducciones, p.veces_reproducida, 0) AS reproducciones_total
        FROM pistas p
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca'
          AND (COALESCE(p.favorita, 0) = 1 OR COALESCE(h.reproducciones, p.veces_reproducida, 0) > 0)
        ORDER BY COALESCE(p.ultimo_acceso, p.indexado_en, p.actualizado_en) ASC,
                 reproducciones_total DESC,
                 p.titulo COLLATE NOCASE
        LIMIT ?
        """,
        (PLAYLIST_AUTO_MAX_PISTAS,),
    )
    return [int(f["id"]) for f in filas]


def _candidatos_recientes() -> list[int]:
    filas = obtener_filas(
        """
        SELECT id
        FROM pistas
        WHERE estado = 'biblioteca'
        ORDER BY datetime(COALESCE(indexado_en, actualizado_en)) DESC, titulo COLLATE NOCASE
        LIMIT ?
        """,
        (PLAYLIST_AUTO_MAX_PISTAS,),
    )
    return [int(f["id"]) for f in filas]


def _candidatos_canciones_por_descubrir() -> list[int]:
    filas = obtener_filas(
        """
        SELECT p.id, COALESCE(h.reproducciones, p.veces_reproducida, 0) AS reproducciones_total
        FROM pistas p
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca'
          AND COALESCE(h.reproducciones, p.veces_reproducida, 0) < 10
        ORDER BY
            COALESCE(h.reproducciones, p.veces_reproducida, 0) ASC,
            datetime(COALESCE(p.indexado_en, p.actualizado_en)) DESC,
            p.titulo COLLATE NOCASE
        LIMIT ?
        """,
        (PLAYLIST_AUTO_MAX_PISTAS,),
    )
    return [int(f["id"]) for f in filas]


def _candidatos_recientes_sin_escuchar() -> list[int]:
    filas = obtener_filas(
        """
        SELECT p.id
        FROM pistas p
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca'
          AND COALESCE(h.reproducciones, p.veces_reproducida, 0) = 0
        ORDER BY datetime(COALESCE(p.indexado_en, p.actualizado_en)) DESC, p.titulo COLLATE NOCASE
        LIMIT ?
        """,
        (PLAYLIST_AUTO_MAX_PISTAS,),
    )
    return [int(f["id"]) for f in filas]


def _candidatos_favoritas_olvidadas() -> list[int]:
    filas = obtener_filas(
        """
        SELECT p.id
        FROM pistas p
        LEFT JOIN (
            SELECT pista_id, MAX(reproducido_en) AS ultima_reproduccion
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca'
          AND COALESCE(p.favorita, 0) = 1
          AND (
              COALESCE(h.ultima_reproduccion, p.ultimo_acceso) IS NULL
              OR datetime(COALESCE(h.ultima_reproduccion, p.ultimo_acceso)) <= datetime('now', '-60 days')
          )
        ORDER BY
            datetime(COALESCE(h.ultima_reproduccion, p.ultimo_acceso, p.indexado_en, p.actualizado_en)) ASC,
            p.titulo COLLATE NOCASE
        LIMIT ?
        """,
        (PLAYLIST_AUTO_MAX_PISTAS,),
    )
    return [int(f["id"]) for f in filas]


def _candidatos_top_canciones() -> list[int]:
    filas = obtener_filas(
        """
        SELECT p.id, COALESCE(h.reproducciones, p.veces_reproducida, 0) AS reproducciones_total
        FROM pistas p
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones, MAX(reproducido_en) AS ultima_reproduccion
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca'
          AND COALESCE(h.reproducciones, p.veces_reproducida, 0) > 0
        ORDER BY reproducciones_total DESC, datetime(COALESCE(h.ultima_reproduccion, p.ultimo_acceso, p.actualizado_en)) DESC
        LIMIT ?
        """,
        (PLAYLIST_AUTO_MAX_PISTAS,),
    )
    if sum(int(f["reproducciones_total"] or 0) for f in filas) < PLAYLIST_AUTO_TOP_MIN_REPRODUCCIONES:
        return []
    return [int(f["id"]) for f in filas]


def _candidatos_artistas_frecuentes() -> list[int]:
    artistas = obtener_filas(
        """
        SELECT p.artista_id, SUM(COALESCE(h.reproducciones, p.veces_reproducida, 0)) AS score
        FROM pistas p
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca' AND p.artista_id IS NOT NULL
        GROUP BY p.artista_id
        HAVING score > 0
        ORDER BY score DESC
        LIMIT 10
        """
    )
    ids: list[int] = []
    usados: set[int] = set()
    for artista in artistas:
        filas = obtener_filas(
            """
            SELECT p.id, COALESCE(h.reproducciones, p.veces_reproducida, 0) AS reproducciones_total
            FROM pistas p
            LEFT JOIN (
                SELECT pista_id, COUNT(*) AS reproducciones
                FROM historial
                GROUP BY pista_id
            ) h ON h.pista_id = p.id
            WHERE p.estado = 'biblioteca' AND p.artista_id = ?
            ORDER BY reproducciones_total DESC, COALESCE(p.favorita, 0) DESC, p.titulo COLLATE NOCASE
            LIMIT 5
            """,
            (artista["artista_id"],),
        )
        for fila in filas:
            pid = int(fila["id"])
            if pid not in usados:
                usados.add(pid)
                ids.append(pid)
        if len(ids) >= PLAYLIST_AUTO_MAX_PISTAS:
            break
    return ids[:PLAYLIST_AUTO_MAX_PISTAS]


def _candidatos_albumes_frecuentes() -> list[int]:
    albums = obtener_filas(
        """
        SELECT p.album_id, SUM(COALESCE(h.reproducciones, p.veces_reproducida, 0)) AS score
        FROM pistas p
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca' AND p.album_id IS NOT NULL
        GROUP BY p.album_id
        HAVING score > 0
        ORDER BY score DESC
        LIMIT 10
        """
    )
    ids: list[int] = []
    usados: set[int] = set()
    for album in albums:
        filas = obtener_filas(
            """
            SELECT p.id, COALESCE(h.reproducciones, p.veces_reproducida, 0) AS reproducciones_total
            FROM pistas p
            LEFT JOIN (
                SELECT pista_id, COUNT(*) AS reproducciones
                FROM historial
                GROUP BY pista_id
            ) h ON h.pista_id = p.id
            WHERE p.estado = 'biblioteca' AND p.album_id = ?
            ORDER BY reproducciones_total DESC, COALESCE(p.track_number, 9999), p.titulo COLLATE NOCASE
            LIMIT 4
            """,
            (album["album_id"],),
        )
        for fila in filas:
            pid = int(fila["id"])
            if pid not in usados:
                usados.add(pid)
                ids.append(pid)
        if len(ids) >= PLAYLIST_AUTO_MAX_PISTAS:
            break
    return ids[:PLAYLIST_AUTO_MAX_PISTAS]


def _candidatos_albumes_para_volver() -> list[int]:
    albums = obtener_filas(
        """
        SELECT
            p.album_id,
            COUNT(DISTINCT p.id) AS num_pistas,
            SUM(COALESCE(h.reproducciones, p.veces_reproducida, 0)) AS reproducciones_total,
            SUM(COALESCE(p.favorita, 0)) AS favoritas_total,
            MAX(COALESCE(h.ultima_reproduccion, p.ultimo_acceso, p.actualizado_en, p.indexado_en)) AS ultima_actividad
        FROM pistas p
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones, MAX(reproducido_en) AS ultima_reproduccion
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca' AND p.album_id IS NOT NULL
        GROUP BY p.album_id
        HAVING num_pistas >= 6 AND (reproducciones_total >= 6 OR favoritas_total >= 2)
        ORDER BY
            (favoritas_total * 12 + reproducciones_total) DESC,
            datetime(ultima_actividad) ASC
        LIMIT 10
        """
    )
    ids: list[int] = []
    usados: set[int] = set()
    for album in albums:
        filas = obtener_filas(
            """
            SELECT p.id, COALESCE(h.reproducciones, p.veces_reproducida, 0) AS reproducciones_total
            FROM pistas p
            LEFT JOIN (
                SELECT pista_id, COUNT(*) AS reproducciones
                FROM historial
                GROUP BY pista_id
            ) h ON h.pista_id = p.id
            WHERE p.estado = 'biblioteca' AND p.album_id = ?
            ORDER BY COALESCE(p.favorita, 0) DESC,
                     reproducciones_total DESC,
                     COALESCE(p.track_number, 9999),
                     p.titulo COLLATE NOCASE
            LIMIT 6
            """,
            (album["album_id"],),
        )
        for fila in filas:
            pid = int(fila["id"])
            if pid not in usados:
                usados.add(pid)
                ids.append(pid)
        if len(ids) >= PLAYLIST_AUTO_MAX_PISTAS:
            break
    return ids[:PLAYLIST_AUTO_MAX_PISTAS]


def _candidatos_similares_a_artista(artista_id: int, *, excluir: set[int], limite: int) -> list[int]:
    """Relleno de 'similares' para completar una playlist 'This is'.

    Devuelve pistas de OTROS artistas que comparten alguno de los géneros del
    artista objetivo, priorizando popularidad local (favoritas y más
    escuchadas). Aplica un tope blando por artista para que el relleno no quede
    dominado por un único nombre. Si el artista no tiene género asociado,
    devuelve lista vacía (no se rellena: mejor una playlist corta que una
    incoherente).
    """
    if limite <= 0:
        return []
    generos = obtener_filas(
        """
        SELECT DISTINCT lower(trim(genero)) AS g
        FROM pistas
        WHERE artista_id = ? AND estado = 'biblioteca' AND COALESCE(genero, '') <> ''
        """,
        (artista_id,),
    )
    lista_generos = [g["g"] for g in generos if g["g"]]
    if not lista_generos:
        return []
    placeholders = ",".join(["?"] * len(lista_generos))
    filas = obtener_filas(
        f"""
        SELECT
            p.id,
            p.artista_id,
            COALESCE(h.reproducciones, p.veces_reproducida, 0) AS reproducciones_total
        FROM pistas p
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca'
          AND p.artista_id <> ?
          AND lower(trim(COALESCE(p.genero, ''))) IN ({placeholders})
        ORDER BY COALESCE(p.favorita, 0) DESC,
                 reproducciones_total DESC,
                 datetime(COALESCE(p.ultimo_acceso, p.actualizado_en, p.indexado_en)) DESC,
                 p.titulo COLLATE NOCASE
        LIMIT ?
        """,
        (artista_id, *lista_generos, limite * 4),
    )
    ids: list[int] = []
    por_artista: dict[int, int] = {}
    for fila in filas:
        pid = int(fila["id"])
        if pid in excluir or pid in ids:
            continue
        otro = int(fila["artista_id"] or 0)
        usados = por_artista.get(otro, 0)
        if usados >= 4:
            continue
        ids.append(pid)
        por_artista[otro] = usados + 1
        if len(ids) >= limite:
            break
    return ids


def _candidatos_this_is(artista_id: int, limite: int = PLAYLIST_AUTO_THIS_IS_MAX_PISTAS) -> list[int]:
    """Pistas para una playlist 'This is <artista>' (rango objetivo 25-80).

    Prioriza el catálogo propio del artista (favoritas y más escuchadas
    primero, con tope blando de 8 por álbum para dar variedad). Si el artista
    tiene pocas pistas propias, completa con temas similares —de artistas que
    comparten género, por popularidad local— hasta alcanzar el mínimo viable,
    sin pasar de `limite`.
    """
    filas = obtener_filas(
        """
        SELECT
            p.id,
            p.album_id,
            COALESCE(h.reproducciones, p.veces_reproducida, 0) AS reproducciones_total
        FROM pistas p
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca' AND p.artista_id = ?
        ORDER BY COALESCE(p.favorita, 0) DESC,
                 reproducciones_total DESC,
                 datetime(COALESCE(p.ultimo_acceso, p.actualizado_en, p.indexado_en)) DESC,
                 COALESCE(p.album_id, 0),
                 COALESCE(p.track_number, 9999),
                 p.titulo COLLATE NOCASE
        LIMIT ?
        """,
        (artista_id, limite * 4),
    )
    ids: list[int] = []
    diferidos: list[int] = []
    albumes: dict[int, int] = {}
    for fila in filas:
        pid = int(fila["id"])
        album_id = int(fila["album_id"] or 0)
        usados_album = albumes.get(album_id, 0)
        if album_id and usados_album >= 8:
            diferidos.append(pid)
            continue
        ids.append(pid)
        albumes[album_id] = usados_album + 1
        if len(ids) >= limite:
            return ids[:limite]
    for pid in diferidos:
        if len(ids) >= limite:
            break
        if pid not in ids:
            ids.append(pid)

    # Relleno con similares solo si el catálogo propio no alcanza el mínimo.
    if len(ids) < PLAYLIST_AUTO_THIS_IS_MIN_PISTAS:
        similares = _candidatos_similares_a_artista(
            artista_id,
            excluir=set(ids),
            limite=limite - len(ids),
        )
        for pid in similares:
            if len(ids) >= limite:
                break
            if pid not in ids:
                ids.append(pid)
    return ids[:limite]


def conteos_artistas_para_playlists() -> list[dict]:
    filas = obtener_filas(
        """
        SELECT
            a.id AS artista_id,
            a.nombre AS nombre,
            COUNT(p.id) AS total_pistas,
            SUM(COALESCE(p.favorita, 0)) AS total_favoritas,
            SUM(COALESCE(h.reproducciones, p.veces_reproducida, 0)) AS reproducciones_total,
            MAX(COALESCE(p.actualizado_en, p.indexado_en)) AS ultima_actualizacion
        FROM artistas a
        JOIN pistas p ON p.artista_id = a.id AND p.estado = 'biblioteca'
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        GROUP BY a.id
        ORDER BY total_pistas DESC, (total_favoritas * 20 + reproducciones_total * 3) DESC, a.nombre COLLATE NOCASE
        """
    )
    return [
        {
            "artista_id": int(f["artista_id"]),
            "nombre": str(f["nombre"] or ""),
            "total_pistas": int(f["total_pistas"] or 0),
            "total_favoritas": int(f["total_favoritas"] or 0),
            "reproducciones_total": int(f["reproducciones_total"] or 0),
            "ultima_actualizacion": f["ultima_actualizacion"] or "",
        }
        for f in filas
    ]


def _candidatos_discovery(query: str) -> list[int]:
    try:
        from core.music_discovery_service import MusicDiscoveryService

        salida = MusicDiscoveryService(None, min_confidence=0.45).discover(query, limit=PLAYLIST_AUTO_MAX_PISTAS)
    except Exception as exc:
        logger.warning("No se pudo generar candidatos discovery para %r: %s", query, exc)
        return []
    ids: list[int] = []
    for item in salida.get("results") or []:
        try:
            pid = int(item.get("id") or item.get("track_id") or 0)
        except (TypeError, ValueError):
            continue
        if pid > 0 and pid not in ids:
            ids.append(pid)
    return ids[:PLAYLIST_AUTO_MAX_PISTAS]


def _specs_playlists_automaticas() -> list[dict]:
    specs = [
        {
            "auto_key": "auto:favoritas_sonando",
            "nombre": "Favoritas que siguen sonando",
            "descripcion": "Favoritas que también tienen historial de escucha local.",
            "tipo": "automatica",
            "subtipo": "descubrimiento_local",
            "origen": "generado",
            "min_pistas": 5,
            "candidatos": _candidatos_favoritas_sonando,
            "regla": {"tipo": "favoritas_sonando"},
        },
        {
            "auto_key": "auto:redescubrir",
            "nombre": "Para redescubrir",
            "descripcion": "Canciones de tu biblioteca con señales locales para volver.",
            "tipo": "automatica",
            "subtipo": "descubrimiento_local",
            "origen": "generado",
            "min_pistas": PLAYLIST_AUTO_STRONG_MIN_PISTAS,
            "candidatos": _candidatos_redescubrir,
            "regla": {"tipo": "redescubrir"},
        },
        {
            "auto_key": "auto:recientes_biblioteca",
            "nombre": "Recientes de tu biblioteca",
            "descripcion": "Últimas canciones añadidas a tu biblioteca local.",
            "tipo": "automatica",
            "subtipo": "recientes",
            "origen": "generado",
            "min_pistas": PLAYLIST_AUTO_DESCUBRIR_MIN_PISTAS,
            "candidatos": _candidatos_recientes,
            "regla": {"tipo": "recientes"},
        },
        {
            "auto_key": "auto:descubrir:canciones",
            "nombre": "Canciones por descubrir",
            "descripcion": "Canciones de tu biblioteca que todavía casi no han sonado.",
            "tipo": "automatica",
            "subtipo": "descubrimiento_local",
            "origen": "generado",
            "min_pistas": PLAYLIST_AUTO_DESCUBRIR_MIN_PISTAS,
            "candidatos": _candidatos_canciones_por_descubrir,
            "regla": {"tipo": "canciones_por_descubrir", "max_reproducciones": 9},
        },
        {
            "auto_key": "auto:recientes_sin_escuchar",
            "nombre": "Recientes sin escuchar",
            "descripcion": "Últimas canciones añadidas que aún no tienen reproducciones.",
            "tipo": "automatica",
            "subtipo": "recientes",
            "origen": "generado",
            "min_pistas": 15,
            "candidatos": _candidatos_recientes_sin_escuchar,
            "regla": {"tipo": "recientes_sin_escuchar"},
        },
        {
            "auto_key": "auto:favoritas_olvidadas",
            "nombre": "Favoritas que no escuchas hace rato",
            "descripcion": "Favoritas que llevan tiempo sin sonar en esta biblioteca.",
            "tipo": "automatica",
            "subtipo": "descubrimiento_local",
            "origen": "generado",
            "min_pistas": 5,
            "candidatos": _candidatos_favoritas_olvidadas,
            "regla": {"tipo": "favoritas_olvidadas"},
        },
        {
            "auto_key": "auto:top_canciones",
            "nombre": "Tu top canciones",
            "descripcion": "Canciones con más reproducciones registradas localmente.",
            "tipo": "automatica",
            "subtipo": "top_canciones",
            "origen": "generado",
            "min_pistas": PLAYLIST_AUTO_STRONG_MIN_PISTAS,
            "candidatos": _candidatos_top_canciones,
            "regla": {"tipo": "top_canciones"},
        },
        {
            "auto_key": "auto:artist_mix_frecuentes",
            "nombre": "Mix de tus artistas frecuentes",
            "descripcion": "Canciones combinadas de los artistas que más suenan en tu biblioteca.",
            "tipo": "automatica",
            "subtipo": "artist_mix",
            "origen": "generado",
            "min_pistas": PLAYLIST_AUTO_STRONG_MIN_PISTAS,
            "candidatos": _candidatos_artistas_frecuentes,
            "regla": {"tipo": "artist_mix"},
        },
        {
            "auto_key": "auto:album_mix_frecuentes",
            "nombre": "Mix de álbumes frecuentes",
            "descripcion": "Canciones de álbumes con más actividad local.",
            "tipo": "automatica",
            "subtipo": "album_mix",
            "origen": "generado",
            "min_pistas": PLAYLIST_AUTO_STRONG_MIN_PISTAS,
            "candidatos": _candidatos_albumes_frecuentes,
            "regla": {"tipo": "album_mix"},
        },
        {
            "auto_key": "auto:albumes_para_volver",
            "nombre": "Vuelve a esos álbumes",
            "descripcion": "Canciones de álbumes con actividad suficiente para retomarlos.",
            "tipo": "automatica",
            "subtipo": "album_mix",
            "origen": "generado",
            "min_pistas": PLAYLIST_AUTO_STRONG_MIN_PISTAS,
            "candidatos": _candidatos_albumes_para_volver,
            "regla": {"tipo": "albumes_para_volver"},
        },
    ]

    artistas = [
        artista for artista in conteos_artistas_para_playlists()
        if int(artista.get("total_pistas") or 0) >= PLAYLIST_AUTO_THIS_IS_ARTISTA_MIN
    ]
    for artista in artistas:
        artista_id = int(artista["artista_id"])
        nombre = str(artista["nombre"] or "").strip()
        if not nombre:
            continue
        specs.append({
            "auto_key": f"auto:this_is:{artista_id}",
            "nombre": f"This is {nombre}",
            "descripcion": f"Canciones de {nombre} en tu biblioteca local.",
            "tipo": "automatica",
            "subtipo": "this_is",
            "origen": "generado",
            "min_pistas": PLAYLIST_AUTO_THIS_IS_MIN_PISTAS,
            "max_pistas": PLAYLIST_AUTO_THIS_IS_MAX_PISTAS,
            "candidatos": lambda artista_id=artista_id: _candidatos_this_is(artista_id),
            "regla": {"tipo": "this_is", "artista_id": artista_id, "artista_nombre": nombre},
        })

    for auto_key, nombre, query in [
        ("auto:mood:workout", "Para entrenar", "para entrenar"),
        ("auto:mood:party", "Para fiesta", "para fiesta"),
        ("auto:mood:focus", "Para concentrarme", "para concentrarme"),
        ("auto:mood:chill", "Algo tranquilo", "algo tranquilo"),
        ("auto:mood:night", "Algo de noche", "algo de noche"),
        ("auto:mood:fast", "Rápidas", "rápido"),
        ("auto:mood:sad_energy", "Tristes pero con energía", "algo triste pero con energía"),
    ]:
        specs.append({
            "auto_key": auto_key,
            "nombre": nombre,
            "descripcion": "Selección local creada con audio features disponibles.",
            "tipo": "automatica",
            "subtipo": "mood",
            "origen": "generado",
            "min_pistas": PLAYLIST_AUTO_FEATURE_MIN_PISTAS,
            "candidatos": lambda query=query: _candidatos_discovery(query),
            "regla": {"tipo": "mood", "query": query},
        })
    return specs


def _spec_por_auto_key(auto_key: str) -> Optional[dict]:
    for spec in _specs_playlists_automaticas():
        if spec["auto_key"] == auto_key:
            return spec
    return None


def _debe_regenerar_playlist(playlist: dict, *, respetar_cooldown: bool) -> bool:
    if not playlist.get("visible", 1):
        return False
    if int(playlist.get("editada_por_usuario") or 0):
        return False
    if not int(playlist.get("auto_actualizable") or 0):
        return False
    if not respetar_cooldown:
        return True
    ultima = str(playlist.get("ultima_generacion_en") or "").strip()
    if not ultima:
        return True
    try:
        normalizada = ultima.replace("Z", "+00:00")
        fecha = datetime.fromisoformat(normalizada)
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    edad = datetime.now(timezone.utc) - fecha.astimezone(timezone.utc)
    return edad.total_seconds() >= PLAYLIST_SYNC_COOLDOWN_SEG


def _aplicar_spec_playlist_automatica(spec: dict, *, forzar: bool = False, respetar_cooldown: bool = True) -> dict:
    auto_key = str(spec["auto_key"])
    existente = _obtener_playlist_por_auto_key(auto_key)
    if (
        existente
        and not int(existente.get("visible", 1))
        and not forzar
        and (int(existente.get("editada_por_usuario") or 0) or not int(existente.get("auto_actualizable") or 0))
    ):
        return {"ok": False, "creada": False, "actualizada": False, "motivo": "oculta"}
    if existente and not forzar and int(existente.get("visible", 1)) and not _debe_regenerar_playlist(existente, respetar_cooldown=respetar_cooldown):
        return {"ok": True, "creada": False, "actualizada": False, "motivo": "sin_cambios"}

    candidatos = list(spec["candidatos"]())
    min_pistas = int(spec.get("min_pistas") or PLAYLIST_AUTO_MIN_PISTAS)
    if len(candidatos) < min_pistas:
        if (
            existente
            and not forzar
            and int(existente.get("visible", 1))
            and not int(existente.get("editada_por_usuario") or 0)
            and int(existente.get("auto_actualizable") or 0)
        ):
            ejecutar(
                """
                UPDATE playlists
                SET visible = 0,
                    actualizado_en = datetime('now')
                WHERE id = ?
                """,
                (int(existente["id"]),),
            )
            return {
                "ok": False,
                "creada": False,
                "actualizada": False,
                "ocultada": True,
                "motivo": "calidad_insuficiente",
                "candidatos": len(candidatos),
            }
        return {"ok": False, "creada": False, "actualizada": False, "motivo": "insuficientes", "candidatos": len(candidatos)}

    # Tope por-spec: "This is" usa 80; el resto el cap global (50). Así un
    # único override no afecta al tamaño del resto de playlists automáticas.
    tope_pistas = int(spec.get("max_pistas") or PLAYLIST_AUTO_MAX_PISTAS)
    candidatos = candidatos[:tope_pistas]
    ahora = _ahora_iso()
    with transaccion() as conexion:
        if existente:
            playlist_id = int(existente["id"])
            nombre_sql = "nombre" if int(existente.get("editada_por_usuario") or 0) else "?"
            descripcion_sql = "descripcion" if int(existente.get("editada_por_usuario") or 0) else "?"
            params: list = []
            if nombre_sql == "?":
                params.append(spec["nombre"])
            if descripcion_sql == "?":
                params.append(spec["descripcion"])
            params.extend([
                spec["tipo"],
                spec["subtipo"],
                spec["origen"],
                _json_compacto(spec.get("regla") or {}),
                ahora,
                playlist_id,
            ])
            conexion.execute(
                f"""
                UPDATE playlists
                SET nombre = {nombre_sql},
                    descripcion = {descripcion_sql},
                    tipo = ?,
                    subtipo = ?,
                    origen = ?,
                    regla_json = ?,
                    visible = 1,
                    auto_actualizable = 1,
                    ultima_generacion_en = ?,
                    actualizado_en = datetime('now')
                WHERE id = ?
                """,
                tuple(params),
            )
            creada = False
        else:
            playlist_id = conexion.execute(
                """
                INSERT INTO playlists(
                    nombre, descripcion, tipo, subtipo, origen, regla_json, auto_key,
                    visible, auto_actualizable, editada_por_usuario, ultima_generacion_en
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, 0, ?)
                """,
                (
                    spec["nombre"],
                    spec["descripcion"],
                    spec["tipo"],
                    spec["subtipo"],
                    spec["origen"],
                    _json_compacto(spec.get("regla") or {}),
                    auto_key,
                    ahora,
                ),
            ).lastrowid
            creada = True
        _reemplazar_pistas_playlist(conexion, playlist_id, candidatos, tope=tope_pistas)
    actualizar_portada_playlist_si_cambio(playlist_id)
    return {"ok": True, "playlist_id": playlist_id, "creada": creada, "actualizada": not creada, "num_pistas": len(candidatos)}


def obtener_candidatos_playlist(regla) -> list[int]:
    if isinstance(regla, str):
        try:
            regla_dict = json.loads(regla)
        except json.JSONDecodeError:
            regla_dict = {"auto_key": regla}
    elif isinstance(regla, dict):
        regla_dict = dict(regla)
    else:
        regla_dict = {}

    auto_key = str(regla_dict.get("auto_key") or "").strip()
    if auto_key:
        spec = _spec_por_auto_key(auto_key)
        return list(spec["candidatos"]()) if spec else []
    tipo = str(regla_dict.get("tipo") or "").strip()
    for spec in _specs_playlists_automaticas():
        if (spec.get("regla") or {}).get("tipo") == tipo:
            return list(spec["candidatos"]())
    return []


def generar_playlists_inteligentes(limite_creacion: int = 4) -> dict:
    limite_creacion = max(0, min(5, int(limite_creacion or 0)))
    creadas = 0
    actualizadas = 0
    ocultadas = 0
    omitidas = 0
    detalles: list[dict] = []
    for spec in _specs_playlists_automaticas():
        existente = _obtener_playlist_por_auto_key(spec["auto_key"])
        es_this_is = str(spec.get("subtipo") or "") == "this_is"
        if not existente and creadas >= limite_creacion and not es_this_is:
            omitidas += 1
            continue
        resultado = _aplicar_spec_playlist_automatica(spec, respetar_cooldown=True)
        detalles.append({"auto_key": spec["auto_key"], **resultado})
        if resultado.get("creada"):
            creadas += 1
        elif resultado.get("actualizada"):
            actualizadas += 1
        elif resultado.get("ocultada"):
            ocultadas += 1
        elif not resultado.get("ok"):
            omitidas += 1
    if creadas:
        mensaje = "Se creó 1 playlist nueva." if creadas == 1 else f"Se crearon {creadas} playlists nuevas."
    elif actualizadas:
        mensaje = "Playlists inteligentes actualizadas."
    else:
        # Sin novedades: mensaje general en lugar de uno atado a "This is".
        # El anterior confundía (hablaba de un tipo concreto de playlist
        # aunque no hubiera artistas elegibles); este cubre cualquier criterio
        # —artistas, géneros, hábitos de escucha— de forma neutra.
        mensaje = "Cuando escuches más canciones o haya más datos musicales, vuelve a intentarlo."
    return {
        "ok": True,
        "creadas": creadas,
        "actualizadas": actualizadas,
        "ocultadas": ocultadas,
        "omitidas": omitidas,
        "detalles": detalles,
        "mensaje": mensaje,
    }


def regenerar_playlist_automatica(playlist_id: int) -> dict:
    playlist = _obtener_playlist(int(playlist_id or 0))
    if not playlist:
        return {"ok": False, "mensaje": "No encontré esa playlist."}
    if _es_playlist_favoritos(playlist):
        _sincronizar_playlist_favoritos()
        return {"ok": True, "mensaje": "Me gusta está sincronizada.", "playlist_id": int(playlist["id"])}
    auto_key = str(playlist.get("auto_key") or "").strip()
    if not auto_key:
        return {"ok": False, "mensaje": "Esta playlist no tiene una regla automática."}
    spec = _spec_por_auto_key(auto_key)
    if not spec:
        return {"ok": False, "mensaje": "No encontré la regla para regenerar esta playlist."}
    resultado = _aplicar_spec_playlist_automatica(spec, forzar=True, respetar_cooldown=False)
    if resultado.get("ok"):
        ejecutar(
            "UPDATE playlists SET editada_por_usuario = 0, auto_actualizable = 1 WHERE id = ?",
            (int(playlist_id),),
        )
        resultado["mensaje"] = "Playlist regenerada."
    else:
        resultado["mensaje"] = "No hay suficientes canciones para regenerar esta playlist."
    return resultado


def sincronizar_playlists_sistema(limite_creacion: int = 3) -> dict:
    favoritos_id = _sincronizar_playlist_favoritos()
    generadas = generar_playlists_inteligentes(limite_creacion=limite_creacion)
    return {"ok": True, "favoritos_id": favoritos_id, **generadas}


def listar_playlists() -> list[dict]:
    """Lista playlists visibles con metadatos, permisos y conteos estables."""
    _sincronizar_playlist_favoritos()
    filas = obtener_filas(
        """
        SELECT
            pl.*,
            COUNT(pp.pista_id) AS num_pistas,
            COALESCE(SUM(COALESCE(p.duracion_seg, 0)), 0) AS duracion_total_seg,
            COALESCE(SUM(COALESCE(h.reproducciones, p.veces_reproducida, 0)), 0) AS reproducciones_total
        FROM playlists pl
        LEFT JOIN pistas_playlist pp ON pp.playlist_id = pl.id
        LEFT JOIN pistas p ON p.id = pp.pista_id
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        WHERE COALESCE(pl.visible, 1) = 1
        GROUP BY pl.id
        ORDER BY
            COALESCE(pl.es_anclada, 0) DESC,
            datetime(COALESCE(pl.anclada_en, '2000-01-01')) DESC,
            CASE COALESCE(pl.subtipo, '')
                WHEN 'favoritos' THEN 0
                WHEN 'usuario' THEN 1
                WHEN 'this_is' THEN 2
                WHEN 'mood' THEN 3
                WHEN 'top_canciones' THEN 4
                WHEN 'artist_mix' THEN 5
                WHEN 'album_mix' THEN 6
                ELSE 7
            END,
            datetime(COALESCE(pl.actualizado_en, pl.creado_en)) DESC,
            pl.nombre COLLATE NOCASE
        """
    )
    return [_normalizar_playlist_fila(dict(fila)) for fila in filas]


def playlists_editables_para_pista(pista_id: int) -> list[dict]:
    """Playlists manuales del usuario, marcando si ya contienen la pista.

    Pensada para el selector "agregar a playlist" (estilo Spotify): solo
    incluye playlists **manuales** (las que el usuario creó), nunca las
    automáticas/sistema ni "Me gusta". Agregar a una automática se perdería
    al regenerarla, y los favoritos se gestionan con su propio corazón.

    Cada item trae ``contiene`` (bool) para pre-marcar el estado actual y
    ``num_pistas`` para mostrar el conteo. Una sola query agrupada: el número
    de playlists manuales es pequeño, así que es barata aun en bibliotecas
    grandes.
    """
    pid = int(pista_id or 0)
    filas = obtener_filas(
        """
        SELECT
            pl.id                                          AS playlist_id,
            pl.nombre                                      AS nombre,
            COUNT(pp.pista_id)                             AS num_pistas,
            MAX(CASE WHEN pp.pista_id = ? THEN 1 ELSE 0 END) AS contiene
        FROM playlists pl
        LEFT JOIN pistas_playlist pp ON pp.playlist_id = pl.id
        WHERE COALESCE(pl.visible, 1) = 1
          AND pl.tipo = 'manual'
          AND COALESCE(pl.subtipo, '') <> 'favoritos'
        GROUP BY pl.id
        ORDER BY
            COALESCE(pl.es_anclada, 0) DESC,
            datetime(COALESCE(pl.actualizado_en, pl.creado_en)) DESC,
            nb_sortkey(pl.nombre)
        """,
        (pid,),
    )
    return [
        {
            "playlist_id": int(fila["playlist_id"]),
            "nombre": str(fila["nombre"] or ""),
            "num_pistas": int(fila["num_pistas"] or 0),
            "contiene": bool(fila["contiene"]),
        }
        for fila in filas
    ]


def pistas_de_playlist(playlist_id: int) -> list[dict]:
    """Retorna las pistas de una playlist en orden."""
    playlist = _obtener_playlist(int(playlist_id or 0))
    if _es_playlist_favoritos(playlist):
        _sincronizar_playlist_favoritos()
    filas = obtener_filas(
        """
        SELECT
            p.*,
            pp.posicion,
            al.portada_ruta AS album_portada_ruta,
            al.mb_release_id AS album_mb_release_id
        FROM pistas_playlist pp
        JOIN pistas p ON p.id = pp.pista_id
        LEFT JOIN albums al ON al.id = p.album_id
        WHERE pp.playlist_id = ?
        ORDER BY pp.posicion
        """,
        (playlist_id,),
    )
    return [_normalizar_pista_fila(dict(f)) for f in filas]


def detalle_playlist(playlist_id: int) -> Optional[dict]:
    playlist = _obtener_playlist(int(playlist_id or 0))
    if not playlist or not int(playlist.get("visible", 1)):
        return None
    if _es_playlist_favoritos(playlist):
        _sincronizar_playlist_favoritos()
        playlist = _obtener_playlist(int(playlist_id))
        if not playlist:
            return None
    stats = _estadisticas_playlist(int(playlist_id))
    playlist.update(stats)
    item = _normalizar_playlist_fila(playlist)
    item["pistas"] = pistas_de_playlist(int(playlist_id))
    item["num_pistas"] = len(item["pistas"])
    item["duracion_total_seg"] = sum(float(p.get("duracion_seg") or 0) for p in item["pistas"])
    return item


def crear_playlist(nombre: str, descripcion: str = "") -> int:
    """Crea una playlist manual. Retorna el ID creado."""
    nombre_limpio = _validar_nombre_playlist(nombre)
    descripcion_limpia = str(descripcion or "").strip()[:500]
    playlist_id = ejecutar_y_obtener_id(
        """
        INSERT INTO playlists(
            nombre, descripcion, tipo, subtipo, origen, regla_json,
            visible, auto_actualizable, editada_por_usuario
        )
        VALUES (?, ?, 'manual', 'usuario', 'usuario', NULL, 1, 0, 0)
        """,
        (nombre_limpio, descripcion_limpia),
    )
    actualizar_portada_playlist_si_cambio(playlist_id)
    return int(playlist_id)


def renombrar_playlist(playlist_id: int, nombre: str) -> dict:
    playlist = _obtener_playlist(int(playlist_id or 0))
    if not playlist:
        return {"ok": False, "mensaje": "No encontré esa playlist."}
    if _es_playlist_favoritos(playlist):
        return {"ok": False, "mensaje": "Me gusta no se puede renombrar."}
    nombre_limpio = _validar_nombre_playlist(nombre, excluir_id=int(playlist_id))
    with transaccion() as conexion:
        conexion.execute(
            "UPDATE playlists SET nombre = ?, actualizado_en = datetime('now') WHERE id = ?",
            (nombre_limpio, int(playlist_id)),
        )
        _marcar_editada_si_corresponde(conexion, playlist)
    return {"ok": True, "mensaje": "Playlist renombrada.", "playlist_id": int(playlist_id), "nombre": nombre_limpio}


def editar_descripcion_playlist(playlist_id: int, descripcion: str) -> dict:
    playlist = _obtener_playlist(int(playlist_id or 0))
    if not playlist:
        return {"ok": False, "mensaje": "No encontré esa playlist."}
    if _es_playlist_favoritos(playlist):
        return {"ok": False, "mensaje": "Me gusta no permite editar descripción."}
    descripcion_limpia = str(descripcion or "").strip()[:500]
    with transaccion() as conexion:
        conexion.execute(
            "UPDATE playlists SET descripcion = ?, actualizado_en = datetime('now') WHERE id = ?",
            (descripcion_limpia, int(playlist_id)),
        )
        _marcar_editada_si_corresponde(conexion, playlist)
    return {"ok": True, "mensaje": "Descripción actualizada.", "playlist_id": int(playlist_id)}


def agregar_a_playlist(playlist_id: int, pista_id: int) -> dict:
    """Agrega una pista a una playlist en la ultima posicion."""
    playlist = _obtener_playlist(int(playlist_id or 0))
    if not playlist:
        return {"ok": False, "mensaje": "No encontré esa playlist."}
    if not _pista_existe(int(pista_id or 0)):
        return {"ok": False, "mensaje": "No encontré esa canción en la biblioteca."}
    if _es_playlist_favoritos(playlist):
        ejecutar("UPDATE pistas SET favorita = 1, actualizado_en = datetime('now') WHERE id = ?", (int(pista_id),))
        _sincronizar_playlist_favoritos()
        return {"ok": True, "mensaje": "Canción marcada como favorita.", "playlist_id": int(playlist_id), "pista_id": int(pista_id)}

    existente = obtener_una_fila(
        "SELECT 1 FROM pistas_playlist WHERE playlist_id = ? AND pista_id = ?",
        (int(playlist_id), int(pista_id)),
    )
    if existente:
        return {"ok": False, "mensaje": "Ya estaba en la playlist.", "duplicada": True}
    with transaccion() as conexion:
        fila = conexion.execute(
            "SELECT COALESCE(MAX(posicion), 0) + 1 AS pos FROM pistas_playlist WHERE playlist_id = ?",
            (int(playlist_id),),
        ).fetchone()
        posicion = int(fila["pos"] if fila else 1)
        conexion.execute(
            """
            INSERT INTO pistas_playlist(playlist_id, pista_id, posicion, agregado_en)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (int(playlist_id), int(pista_id), posicion),
        )
        conexion.execute(
            "UPDATE playlists SET actualizado_en = datetime('now') WHERE id = ?",
            (int(playlist_id),),
        )
        _marcar_editada_si_corresponde(conexion, playlist)
    if posicion <= 4:
        actualizar_portada_playlist_si_cambio(int(playlist_id))
    return {"ok": True, "mensaje": "Canción añadida.", "playlist_id": int(playlist_id), "pista_id": int(pista_id)}


def eliminar_playlist(playlist_id: int) -> dict:
    playlist = _obtener_playlist(int(playlist_id or 0))
    if not playlist:
        return {"ok": False, "mensaje": "No encontré esa playlist."}
    if _es_playlist_favoritos(playlist):
        return {"ok": False, "mensaje": "Me gusta no se puede eliminar."}
    if str(playlist.get("tipo") or "manual") == "manual" and not playlist.get("auto_key"):
        try:
            from db.conexion import registrar_tombstone
            registrar_tombstone("playlist", int(playlist_id))
        except Exception as exc:
            logger.debug("No se pudo registrar tombstone de playlist %s: %s", playlist_id, exc)
        ejecutar("DELETE FROM playlists WHERE id = ?", (int(playlist_id),))
        return {"ok": True, "mensaje": "Playlist eliminada.", "eliminada": True}
    ejecutar(
        """
        UPDATE playlists
        SET visible = 0,
            auto_actualizable = 0,
            editada_por_usuario = 1,
            actualizado_en = datetime('now')
        WHERE id = ?
        """,
        (int(playlist_id),),
    )
    return {"ok": True, "mensaje": "Playlist ocultada.", "oculta": True}


def quitar_de_playlist(playlist_id: int, pista_id: int) -> dict:
    """Elimina una pista concreta de una playlist y recompone posiciones."""
    playlist = _obtener_playlist(int(playlist_id or 0))
    if not playlist:
        return {"ok": False, "mensaje": "No encontré esa playlist."}
    if _es_playlist_favoritos(playlist):
        ejecutar("UPDATE pistas SET favorita = 0, actualizado_en = datetime('now') WHERE id = ?", (int(pista_id),))
        _sincronizar_playlist_favoritos()
        return {"ok": True, "mensaje": "Canción quitada de Me gusta.", "playlist_id": int(playlist_id), "pista_id": int(pista_id)}
    posicion_previa = obtener_una_fila(
        "SELECT posicion FROM pistas_playlist WHERE playlist_id = ? AND pista_id = ?",
        (int(playlist_id), int(pista_id)),
    )
    with transaccion() as conexion:
        conexion.execute(
            "DELETE FROM pistas_playlist WHERE playlist_id = ? AND pista_id = ?",
            (int(playlist_id), int(pista_id)),
        )
        _recomponer_posiciones_playlist(conexion, int(playlist_id))
        conexion.execute(
            "UPDATE playlists SET actualizado_en = datetime('now') WHERE id = ?",
            (int(playlist_id),),
        )
        _marcar_editada_si_corresponde(conexion, playlist)
    posicion_valor = int(posicion_previa["posicion"] if posicion_previa else 9999)
    if posicion_valor <= 4:
        actualizar_portada_playlist_si_cambio(int(playlist_id))
    return {"ok": True, "mensaje": "Canción quitada de esta playlist.", "playlist_id": int(playlist_id), "pista_id": int(pista_id)}


# =============================================================================
# ELIMINACIÓN DEFINITIVA DE UNA PISTA (destructivo e irreversible)
# =============================================================================

def _sha256_archivo(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _borrar_archivo_seguro(ruta: str) -> None:
    if not ruta:
        return
    try:
        Path(ruta).unlink(missing_ok=True)
    except OSError as exc:
        logger.debug("No se pudo borrar archivo %s: %s", ruta, exc)


def _recomponer_posiciones_sesion_dj(conexion, sesion_id: int) -> None:
    """Renumera 1..N las pistas de una sesión DJ tras quitar una.

    La PK de dj_pistas_sesion es (sesion_id, posicion); se desplazan primero las
    posiciones a un rango alto para evitar colisiones de PK durante el renumerado.
    """
    filas = conexion.execute(
        "SELECT pista_id FROM dj_pistas_sesion WHERE sesion_id = ? ORDER BY posicion, agregado_en",
        (sesion_id,),
    ).fetchall()
    conexion.execute("UPDATE dj_sesiones SET actualizado_en = datetime('now') WHERE id = ?", (sesion_id,))
    if not filas:
        return
    desplazamiento = 1_000_000
    for fila in filas:
        conexion.execute(
            "UPDATE dj_pistas_sesion SET posicion = posicion + ? WHERE sesion_id = ? AND pista_id = ?",
            (desplazamiento, sesion_id, fila["pista_id"]),
        )
    for nueva, fila in enumerate(filas, start=1):
        conexion.execute(
            "UPDATE dj_pistas_sesion SET posicion = ? WHERE sesion_id = ? AND pista_id = ?",
            (nueva, sesion_id, fila["pista_id"]),
        )


def _leer_entrada_assets(ruta_archivo: str) -> dict:
    """Devuelve la entrada del assets_manifest para un archivo, o {}."""
    path = _manifest_assets()
    if not path or not ruta_archivo or not Path(path).exists():
        return {}
    objetivo = str(ruta_archivo)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for linea in fh:
                texto = linea.strip()
                if not texto:
                    continue
                try:
                    row = json.loads(texto)
                except json.JSONDecodeError:
                    continue
                if str(row.get("archivo") or "") == objetivo:
                    return row
    except OSError:
        return {}
    return {}


_CLAVES_COVER_MANIFEST = (
    "track_cover", "track_cover_hd", "album_cover", "album_cover_hd",
    "artist_avatar", "artist_avatar_hd",
)


def _covers_referenciadas(path) -> set:
    """Conjunto de TODAS las rutas de carátula referenciadas en el manifiesto."""
    refs: set[str] = set()
    if not path or not Path(path).exists():
        return refs
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for linea in fh:
                texto = linea.strip()
                if not texto:
                    continue
                try:
                    row = json.loads(texto)
                except json.JSONDecodeError:
                    continue
                for k in _CLAVES_COVER_MANIFEST:
                    v = str(row.get(k) or "").strip()
                    if v:
                        refs.add(v)
    except OSError:
        pass
    return refs


def _reescribir_manifest_sin(path, clave: str, valor: str) -> None:
    """Reescribe un manifiesto JSONL omitiendo las líneas con row[clave]==valor."""
    if not path or not valor or not Path(path).exists():
        return
    objetivo = str(valor)
    conservadas: list[str] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for linea in fh:
                texto = linea.rstrip("\n")
                if not texto.strip():
                    continue
                try:
                    row = json.loads(texto)
                except json.JSONDecodeError:
                    conservadas.append(texto)  # no romper líneas no parseables
                    continue
                if str(row.get(clave) or "") == objetivo:
                    continue
                conservadas.append(texto)
    except OSError:
        return
    tmp = Path(str(path) + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            for texto in conservadas:
                fh.write(texto + "\n")
        tmp.replace(path)
    except OSError as exc:
        logger.debug("No se pudo reescribir manifiesto %s: %s", path, exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _borrar_manifests_track(ruta_archivo: str, hash_sha: str) -> None:
    """Borra tracks/<id>.json cuyo ruta_actual/hash coincida + su fila de índice."""
    base = _settings.DEFAULT_MANIFESTS_DIR
    if base is None:
        return
    carpeta = Path(base) / "tracks"
    if not carpeta.exists():
        return
    objetivo_ruta = str(ruta_archivo or "")
    objetivo_hash = str(hash_sha or "")
    for json_path in carpeta.glob("*.json"):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        coincide = (
            (objetivo_ruta and str(data.get("ruta_actual") or "") == objetivo_ruta)
            or (objetivo_hash and str(data.get("hash") or "") == objetivo_hash)
        )
        if not coincide:
            continue
        key = str(data.get("track_id") or "")
        _borrar_archivo_seguro(str(json_path))
        if key:
            try:
                ejecutar(
                    "DELETE FROM manifests_index WHERE entity_type = 'track' AND entity_key = ?",
                    (key,),
                )
            except Exception as exc:
                logger.debug("No se pudo limpiar manifests_index de %s: %s", key, exc)


def _borrar_procesado_por_hash(nombre_archivo: str, hash_sha: str) -> None:
    """Borra la copia archivada en `procesados` SOLO si su SHA-256 coincide.

    La copia archivada conserva el nombre ORIGINAL del archivo importado, que
    puede diferir del de la biblioteca; por eso se busca por nombre (incluidas
    variantes con sufijo `_N`) pero solo se borra si el contenido (hash) es el
    mismo, garantizando que nunca se borre un archivo equivocado.
    """
    base = _settings.DEFAULT_PROCESSED_DIR
    if base is None or not hash_sha:
        return
    raiz = Path(base)
    if not raiz.exists():
        return
    nombre = str(nombre_archivo or "")
    if not nombre:
        return
    tallo = Path(nombre).stem
    ext = Path(nombre).suffix
    for sub in raiz.iterdir():
        if not sub.is_dir():
            continue
        for candidato in sub.glob(f"{tallo}*{ext}"):
            try:
                if candidato.is_file() and _sha256_archivo(candidato) == hash_sha:
                    _borrar_archivo_seguro(str(candidato))
            except OSError:
                continue


def eliminar_pista(pista_id: int) -> dict:
    """Elimina una pista de raíz: BD, archivo, copias, carátulas y manifiestos.

    Operación DESTRUCTIVA e IRREVERSIBLE. Borra:
      - La fila de `pistas` (cascada FK: pistas_playlist, cola, karaoke_jobs,
        dj_pistas_sesion, dj_track_emb, sync_stem_transfers; el índice FTS se
        limpia por trigger), las tablas con `track_id` TEXT sin FK
        (features/deep/vibe/jobs), el historial y el override de catalogación.
      - El archivo de audio y su copia archivada en `procesados` (validada por
        hash, para nunca borrar un archivo equivocado).
      - Carátulas/portadas y entradas de manifiesto, **conservando** las que
        otras pistas sigan compartiendo (foto de artista, portada de álbum…).
      - El álbum/artista si quedaran sin ninguna pista.
    Recompone las posiciones de las playlists y sesiones DJ afectadas y registra
    tombstones para la sincronización móvil. Devuelve un resumen para la UI.
    """
    pid = int(pista_id or 0)
    pista = obtener_una_fila(
        "SELECT id, titulo, ruta_archivo, nombre_archivo, hash_sha256, album_id, artista_id "
        "FROM pistas WHERE id = ?",
        (pid,),
    )
    if not pista:
        return {"ok": False, "mensaje": "No encontré esa pista."}

    ruta_archivo = str(pista["ruta_archivo"] or "")
    nombre_archivo = str(pista["nombre_archivo"] or "")
    hash_sha = str(pista["hash_sha256"] or "")
    album_id = pista["album_id"]
    artista_id = pista["artista_id"]
    track_txt = str(pid)
    titulo = str(pista["titulo"] or nombre_archivo or "la pista")

    # Carátulas declaradas para ESTA pista (se leen antes de tocar el manifiesto).
    entrada_assets = _leer_entrada_assets(ruta_archivo)
    covers_pista = [
        str(entrada_assets.get(k) or "").strip() for k in _CLAVES_COVER_MANIFEST
    ]
    covers_pista = [c for c in covers_pista if c]

    # Playlists / sesiones DJ afectadas (capturadas ANTES de la cascada FK).
    playlists_afectadas = [
        int(f["playlist_id"]) for f in obtener_filas(
            "SELECT DISTINCT playlist_id FROM pistas_playlist WHERE pista_id = ?", (pid,))
    ]
    sesiones_dj_afectadas = [
        int(f["sesion_id"]) for f in obtener_filas(
            "SELECT DISTINCT sesion_id FROM dj_pistas_sesion WHERE pista_id = ?", (pid,))
    ]

    album_huerfano = False
    artista_huerfano = False
    with transaccion() as cx:
        # Tablas con track_id TEXT (sin FK → borrado manual).
        cx.execute("DELETE FROM track_audio_features WHERE track_id = ?", (track_txt,))
        cx.execute("DELETE FROM track_deep_audio_features WHERE track_id = ?", (track_txt,))
        cx.execute("DELETE FROM track_vibe_tags WHERE track_id = ?", (track_txt,))
        cx.execute("DELETE FROM audio_analysis_jobs WHERE track_id = ?", (track_txt,))
        # Historial y override de catalogación (sin rastro).
        cx.execute("DELETE FROM historial WHERE pista_id = ?", (pid,))
        if hash_sha:
            cx.execute(
                "DELETE FROM overrides_catalogacion WHERE match_type = 'hash' AND match_value = ?",
                (hash_sha,),
            )
        # La pista → dispara cascada FK + trigger FTS.
        cx.execute("DELETE FROM pistas WHERE id = ?", (pid,))
        # Recomponer posiciones de las playlists y sesiones DJ afectadas.
        for plid in playlists_afectadas:
            _recomponer_posiciones_playlist(cx, plid)
            cx.execute("UPDATE playlists SET actualizado_en = datetime('now') WHERE id = ?", (plid,))
        for sid in sesiones_dj_afectadas:
            _recomponer_posiciones_sesion_dj(cx, sid)
        # Álbum / artista huérfanos (sin más pistas).
        if album_id is not None:
            album_huerfano = cx.execute(
                "SELECT 1 FROM pistas WHERE album_id = ? LIMIT 1", (album_id,)).fetchone() is None
            if album_huerfano:
                cx.execute("DELETE FROM albums WHERE id = ?", (album_id,))
        if artista_id is not None:
            artista_huerfano = cx.execute(
                "SELECT 1 FROM pistas WHERE artista_id = ? LIMIT 1", (artista_id,)).fetchone() is None
            if artista_huerfano:
                cx.execute("DELETE FROM artistas WHERE id = ?", (artista_id,))

    # Tombstones para la sincronización móvil (fuera de la transacción; lock propio).
    try:
        from db.conexion import registrar_tombstone
        registrar_tombstone("pista", pid)
        if album_huerfano and album_id is not None:
            registrar_tombstone("album", int(album_id))
        if artista_huerfano and artista_id is not None:
            registrar_tombstone("artista", int(artista_id))
    except Exception as exc:
        logger.debug("No se pudo registrar tombstone al eliminar pista %s: %s", pid, exc)

    # --- Archivos y manifiestos (best-effort, ya fuera de la BD) ---
    # Quitar la línea de la pista de los manifiestos JSONL (match por ruta).
    _reescribir_manifest_sin(_manifest_assets(), "archivo", ruta_archivo)
    _reescribir_manifest_sin(_ruta_manifest_letras(), "file", ruta_archivo)
    # Borrar el manifiesto JSON por-pista (tracks/<id>.json) + su índice.
    _borrar_manifests_track(ruta_archivo, hash_sha)

    # Carátulas: borrar SOLO las que ninguna otra pista siga referenciando.
    covers_supervivientes = _covers_referenciadas(_manifest_assets())
    for cover in covers_pista:
        if cover and cover not in covers_supervivientes:
            _borrar_archivo_seguro(cover)

    # Audio de la biblioteca + copia archivada en procesados (validada por hash).
    _borrar_archivo_seguro(ruta_archivo)
    _borrar_procesado_por_hash(nombre_archivo, hash_sha)

    logger.info("Pista %s eliminada de raíz: %s", pid, ruta_archivo)
    return {
        "ok": True,
        "mensaje": f"«{titulo}» se eliminó por completo.",
        "pista_id": pid,
        "album_eliminado": bool(album_huerfano),
        "artista_eliminado": bool(artista_huerfano),
        "playlists_afectadas": playlists_afectadas,
        "sesiones_dj_afectadas": sesiones_dj_afectadas,
    }


def vaciar_playlist(playlist_id: int) -> dict:
    """Elimina todas las pistas de una playlist."""
    playlist = _obtener_playlist(int(playlist_id or 0))
    if not playlist:
        return {"ok": False, "mensaje": "No encontré esa playlist."}
    if _es_playlist_favoritos(playlist):
        return {"ok": False, "mensaje": "Me gusta no se puede vaciar desde Playlists."}
    with transaccion() as conexion:
        conexion.execute("DELETE FROM pistas_playlist WHERE playlist_id = ?", (int(playlist_id),))
        conexion.execute(
            "UPDATE playlists SET actualizado_en = datetime('now') WHERE id = ?",
            (int(playlist_id),),
        )
        _marcar_editada_si_corresponde(conexion, playlist)
    actualizar_portada_playlist_si_cambio(int(playlist_id))
    return {"ok": True, "mensaje": "Playlist vaciada.", "playlist_id": int(playlist_id)}


def reordenar_playlist(playlist_id: int, pista_id: int, nueva_posicion: int) -> dict:
    playlist = _obtener_playlist(int(playlist_id or 0))
    if not playlist:
        return {"ok": False, "mensaje": "No encontré esa playlist."}
    if _es_playlist_favoritos(playlist):
        return {"ok": False, "mensaje": "Me gusta se ordena desde tus favoritas."}
    ids = _ids_playlist(int(playlist_id))
    try:
        pista_id = int(pista_id)
    except (TypeError, ValueError):
        return {"ok": False, "mensaje": "Canción inválida."}
    if pista_id not in ids:
        return {"ok": False, "mensaje": "Esa canción no está en la playlist."}
    ids.remove(pista_id)
    try:
        posicion_solicitada = int(nueva_posicion or 1)
    except (TypeError, ValueError):
        posicion_solicitada = 1
    posicion = max(0, min(posicion_solicitada - 1, len(ids)))
    ids.insert(posicion, pista_id)
    with transaccion() as conexion:
        _reemplazar_pistas_playlist(conexion, int(playlist_id), ids, tope=None)
        _marcar_editada_si_corresponde(conexion, playlist)
    return {"ok": True, "mensaje": "Orden actualizado.", "playlist_id": int(playlist_id)}


def reordenar_playlist_completa(playlist_id: int, lista_ids: list[int]) -> dict:
    playlist = _obtener_playlist(int(playlist_id or 0))
    if not playlist:
        return {"ok": False, "mensaje": "No encontré esa playlist."}
    if _es_playlist_favoritos(playlist):
        return {"ok": False, "mensaje": "Me gusta se ordena desde tus favoritas."}
    actuales = _ids_playlist(int(playlist_id))
    nuevos = [int(pid) for pid in lista_ids]
    if sorted(actuales) != sorted(nuevos):
        return {"ok": False, "mensaje": "El nuevo orden no coincide con las canciones de la playlist."}
    with transaccion() as conexion:
        _reemplazar_pistas_playlist(conexion, int(playlist_id), nuevos, tope=None)
        _marcar_editada_si_corresponde(conexion, playlist)
    return {"ok": True, "mensaje": "Orden actualizado.", "playlist_id": int(playlist_id)}


def duplicar_playlist(playlist_id: int, nombre: str = "") -> dict:
    playlist = detalle_playlist(int(playlist_id or 0))
    if not playlist:
        return {"ok": False, "mensaje": "No encontré esa playlist."}
    base = _normalizar_nombre_playlist(nombre) or f"{playlist.get('nombre') or 'Playlist'} (copia)"
    candidato = base
    sufijo = 2
    while True:
        try:
            candidato = _validar_nombre_playlist(candidato)
            break
        except ValueError:
            candidato = f"{base} {sufijo}"
            sufijo += 1
    nuevo_id = crear_playlist(candidato, str(playlist.get("descripcion") or ""))
    ids = [int(p["id"]) for p in playlist.get("pistas") or []]
    with transaccion() as conexion:
        _reemplazar_pistas_playlist(conexion, nuevo_id, ids, tope=None)
    actualizar_portada_playlist_si_cambio(nuevo_id)
    return {"ok": True, "mensaje": "Playlist duplicada.", "playlist_id": nuevo_id}


def anclar_playlist(playlist_id: int, anclada: bool) -> dict:
    playlist = _obtener_playlist(int(playlist_id or 0))
    if not playlist:
        return {"ok": False, "mensaje": "No encontré esa playlist."}
    if _es_playlist_favoritos(playlist):
        return {"ok": True, "mensaje": "Me gusta ya queda priorizada.", "playlist_id": int(playlist_id)}
    ejecutar(
        "UPDATE playlists SET es_anclada = ?, anclada_en = ?, actualizado_en = datetime('now') WHERE id = ?",
        (1 if anclada else 0, _ahora_iso() if anclada else None, int(playlist_id)),
    )
    return {"ok": True, "mensaje": "Playlist anclada." if anclada else "Playlist desanclada.", "playlist_id": int(playlist_id)}


def buscar_pistas_para_playlist(query: str, playlist_id: Optional[int] = None, limite: int = 100) -> list[dict]:
    termino = str(query or "").strip()
    limite = max(1, min(200, int(limite or 100)))
    presentes = set(_ids_playlist(int(playlist_id))) if playlist_id else set()
    if termino:
        # Ruta solo-pistas: evita los agregados de álbumes/artistas de `buscar`
        # (no se usan aquí) y sin sobre-fetch (los resultados ya vienen sin
        # duplicados), lo que hace este buscador tan ágil como el de "Buscar".
        resultados = _buscar_pistas(termino, limite)
    else:
        resultados = listar_pistas(orden="reciente", limite=limite)

    out: list[dict] = []
    vistos: set[int] = set()
    for pista in resultados:
        item = dict(pista)
        pid = int(item.get("id") or 0)
        if pid <= 0 or pid in vistos:
            continue
        vistos.add(pid)
        item["ya_en_playlist"] = pid in presentes
        item["accion_agregar"] = "Ya está" if item["ya_en_playlist"] else "Añadir"
        out.append(item)
        if len(out) >= limite:
            break
    return out


def explicar_entidad(target: str) -> dict:
    fila = obtener_una_fila(
        "SELECT manifest_path FROM manifests_index WHERE entity_key = ? ORDER BY updated_at DESC LIMIT 1",
        (target,),
    )
    if not fila and Path(target).exists():
        key = hashlib.sha1(str(Path(target).resolve()).encode("utf-8")).hexdigest()
        fila = obtener_una_fila(
            "SELECT manifest_path FROM manifests_index WHERE entity_key = ? ORDER BY updated_at DESC LIMIT 1",
            (key,),
        )
    if not fila:
        return {}
    ruta = Path(fila["manifest_path"])
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.warning(f"Manifiesto JSON inválido en {ruta}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error inesperado leyendo manifiesto {ruta}: {e}", exc_info=True)
        return {}


# =============================================================================
# KARAOKE
# =============================================================================

_ESTADOS_KARAOKE_VALIDOS = frozenset({
    "no_procesada", "en_cola", "procesando", "lista", "fallida", "no_aplica"
})

# Grupos de filtro por pestaña de la UI.
# "sin_preparar" = SOLO no_procesada (jamás tocadas).
# "en_cola" = en_cola + procesando (esperando o siendo procesadas ahora).
_GRUPOS_KARAOKE: dict[str, tuple[str, ...]] = {
    "sin_preparar": ("no_procesada",),
    "en_cola":      ("en_cola", "procesando"),
    "lista":        ("lista",),
    "fallida":      ("fallida",),
    "no_aplica":    ("no_aplica",),
}

_KARAOKE_SELECT = """
    SELECT
        p.id,
        p.titulo,
        p.artista_nombre,
        p.album_titulo,
        p.duracion_seg,
        p.ruta_archivo,
        p.karaoke_estado,
        p.karaoke_ruta_instrumental,
        p.karaoke_actualizado_en,
        p.karaoke_error_codigo,
        p.karaoke_error_mensaje,
        al.portada_ruta AS album_portada_ruta,
        (
            SELECT j.progreso FROM karaoke_jobs j
            WHERE j.pista_id = p.id
              AND j.estado IN ('preparando','procesando','generando')
            ORDER BY j.id DESC LIMIT 1
        ) AS karaoke_progreso,
        (
            SELECT j.intento FROM karaoke_jobs j
            WHERE j.pista_id = p.id
            ORDER BY j.id DESC LIMIT 1
        ) AS karaoke_intento
    FROM pistas p
    LEFT JOIN albums al ON al.id = p.album_id
"""

_KARAOKE_ORDER = """
    ORDER BY
        p.artista_nombre COLLATE NOCASE,
        p.album_titulo COLLATE NOCASE,
        p.titulo COLLATE NOCASE
"""


def _karaoke_where_params(
    filtro_estado: Optional[str],
    filtro_texto: str,
) -> tuple[str, list]:
    """Genera cláusula WHERE y lista de parámetros para queries karaoke."""
    condiciones = ["p.estado = 'biblioteca'"]
    params: list = []

    grupo = filtro_estado or ""
    if grupo and grupo not in ("todos", ""):
        estados_grupo = _GRUPOS_KARAOKE.get(grupo)
        if estados_grupo:
            placeholders = ",".join("?" * len(estados_grupo))
            condiciones.append(f"p.karaoke_estado IN ({placeholders})")
            params.extend(estados_grupo)
        elif grupo in _ESTADOS_KARAOKE_VALIDOS:
            condiciones.append("p.karaoke_estado = ?")
            params.append(grupo)

    filtro = (filtro_texto or "").strip()
    if filtro:
        condiciones.append(
            "(p.titulo LIKE ? COLLATE NOCASE OR "
            "p.artista_nombre LIKE ? COLLATE NOCASE OR "
            "p.album_titulo LIKE ? COLLATE NOCASE)"
        )
        like = f"%{filtro}%"
        params.extend([like, like, like])

    return "WHERE " + " AND ".join(condiciones), params


def contar_pistas_karaoke(
    filtro_estado: Optional[str] = None,
    filtro_texto: str = "",
) -> int:
    """Cuenta pistas karaoke sin paginación (para controles de páginas)."""
    where, params = _karaoke_where_params(filtro_estado, filtro_texto)
    fila = obtener_una_fila(
        f"SELECT COUNT(*) AS n FROM pistas p {where}",
        params,
    )
    return int(fila["n"]) if fila else 0


def listar_pistas_karaoke(
    filtro_estado: Optional[str] = None,
    filtro_texto: str = "",
    limite: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Lista pistas de la biblioteca con su estado karaoke, con paginación."""
    where, params = _karaoke_where_params(filtro_estado, filtro_texto)
    params = list(params) + [max(1, int(limite)), max(0, int(offset))]
    filas = obtener_filas(
        f"{_KARAOKE_SELECT} {where} {_KARAOKE_ORDER} LIMIT ? OFFSET ?",
        params,
    )
    return [dict(f) for f in filas]


def resumen_karaoke() -> dict:
    """Devuelve conteo de pistas por estado karaoke (solo biblioteca)."""
    filas = obtener_filas(
        """
        SELECT karaoke_estado, COUNT(*) AS total
        FROM pistas
        WHERE estado = 'biblioteca'
        GROUP BY karaoke_estado
        """,
        [],
    )
    resultado: dict = {
        "no_procesada": 0,
        "en_cola": 0,
        "procesando": 0,
        "lista": 0,
        "fallida": 0,
        "no_aplica": 0,
        "total": 0,
        "sin_preparar": 0,
    }
    for fila in filas:
        estado = fila["karaoke_estado"] or "no_procesada"
        # Normalizar estados desconocidos/legacy a 'no_procesada' para que el
        # "Total" sea SIEMPRE igual a la suma de las pestañas. Sin esto, una
        # pista con un karaoke_estado inesperado se sumaba al total pero no a
        # ningún estado visible, inflando el contador general ("cuenta
        # canciones que no aparecen en ninguna pestaña").
        if estado not in _ESTADOS_KARAOKE_VALIDOS:
            estado = "no_procesada"
        resultado[estado] += fila["total"]
        resultado["total"] += fila["total"]
    # "sin_preparar" = solo no_procesada (nunca tocadas ni encoladas).
    # La pestaña "En cola" muestra en_cola + procesando por separado.
    resultado["sin_preparar"] = resultado["no_procesada"]
    return resultado


def actualizar_karaoke_pista(
    pista_id: int,
    estado: str,
    ruta_instrumental: Optional[str] = None,
) -> bool:
    """Actualiza el estado karaoke de una pista. Retorna True si tuvo éxito."""
    if estado not in _ESTADOS_KARAOKE_VALIDOS:
        return False
    try:
        ejecutar(
            """
            UPDATE pistas
            SET karaoke_estado = ?,
                karaoke_ruta_instrumental = ?,
                karaoke_actualizado_en = datetime('now')
            WHERE id = ? AND estado = 'biblioteca'
            """,
            [estado, ruta_instrumental, pista_id],
        )
        return True
    except Exception:
        return False


def pista_karaoke_por_id(pista_id: int) -> dict:
    """Devuelve el registro karaoke de una pista específica."""
    fila = obtener_una_fila(
        f"{_KARAOKE_SELECT} WHERE p.id = ? AND p.estado = 'biblioteca'",
        [pista_id],
    )
    return dict(fila) if fila else {}


# =============================================================================
# RESOLUCION PARA EL ECOSISTEMA MOVIL (lyrics / imagen de artista)
#
# Funciones standalone (sin depender del Reproductor Qt) que el servidor de
# sincronizacion usa para servir letras e imagenes de artista por sus endpoints.
# =============================================================================

# Cache del indice de letras (manifest de enrichment) por mtime, para no
# releer el archivo en cada peticion del movil.
_indice_lyrics_cache: dict[str, dict[str, str]] = {}
_indice_lyrics_mtime: float = -1.0
_indice_lyrics_ruta: Optional[Path] = None


def _ruta_manifest_letras() -> Optional[Path]:
    if _settings.DEFAULT_ASSETS_DIR is None:
        return None
    return Path(_settings.DEFAULT_ASSETS_DIR) / "enrichment" / "enrichment_manifest.jsonl"


def _recargar_indice_lyrics_si_necesario() -> None:
    """Reconstruye el indice de letras si el manifest cambio (compara mtime)."""
    global _indice_lyrics_cache, _indice_lyrics_mtime, _indice_lyrics_ruta
    manifest = _ruta_manifest_letras()
    if manifest is None or not manifest.exists():
        _indice_lyrics_cache = {}
        _indice_lyrics_mtime = -1.0
        _indice_lyrics_ruta = manifest
        return
    try:
        mtime = manifest.stat().st_mtime
    except OSError:
        return
    if manifest == _indice_lyrics_ruta and mtime == _indice_lyrics_mtime:
        return
    indice: dict[str, dict[str, str]] = {}
    try:
        with manifest.open("r", encoding="utf-8") as fh:
            for linea in fh:
                texto = linea.strip()
                if not texto:
                    continue
                try:
                    fila = json.loads(texto)
                except json.JSONDecodeError:
                    continue
                ruta = str(fila.get("file") or "").strip()
                if not ruta:
                    continue
                lyrics = fila.get("lyrics") or {}
                if not isinstance(lyrics, dict):
                    continue
                synced = str(lyrics.get("synced_lyrics") or "").strip()
                plain = str(lyrics.get("plain_lyrics") or "").strip()
                if not synced and not plain:
                    continue
                entry = {"synced_lyrics": synced, "plain_lyrics": plain}
                indice[ruta] = entry
                try:
                    indice[str(Path(ruta).expanduser().resolve())] = entry
                except Exception:
                    pass
    except OSError as exc:
        logger.warning("No se pudo leer manifest de enrichment para lyrics: %s", exc)
        return
    _indice_lyrics_cache = indice
    _indice_lyrics_mtime = mtime
    _indice_lyrics_ruta = manifest


def obtener_lyrics_por_ruta(ruta_archivo: Optional[str]) -> dict[str, str]:
    """Devuelve {'synced_lyrics','plain_lyrics'} para una pista por su ruta.

    Lee el manifest de enrichment (cacheado por mtime). Si no hay letra,
    devuelve cadenas vacias. Standalone: no depende del Reproductor.
    """
    ruta = str(ruta_archivo or "").strip()
    if not ruta:
        return {"synced_lyrics": "", "plain_lyrics": ""}
    _recargar_indice_lyrics_si_necesario()
    entry = _indice_lyrics_cache.get(ruta)
    if entry is None:
        try:
            entry = _indice_lyrics_cache.get(str(Path(ruta).expanduser().resolve()))
        except Exception:
            entry = None
    return dict(entry) if entry else {"synced_lyrics": "", "plain_lyrics": ""}


def obtener_lyrics_pista(pista_id: int) -> dict[str, str]:
    """Resuelve las letras de una pista por id (vía su ruta de archivo)."""
    fila = obtener_una_fila("SELECT ruta_archivo FROM pistas WHERE id = ?", (int(pista_id),))
    if not fila or not fila["ruta_archivo"]:
        return {"synced_lyrics": "", "plain_lyrics": ""}
    return obtener_lyrics_por_ruta(fila["ruta_archivo"])


def ruta_imagen_artista(artista_id: int) -> Optional[str]:
    """Ruta local del avatar/imagen de un artista por id, o None si no hay.

    Resuelve primero por el mapa de assets (avatar enriquecido); el servidor de
    sincronizacion la usa para servir `/api/v1/asset/artist/{id}`.
    """
    fila = obtener_una_fila("SELECT nombre FROM artistas WHERE id = ?", (int(artista_id),))
    if not fila:
        return None
    avatar = _resolver_avatar_artista(None, fila["nombre"])
    if not avatar:
        return None
    ruta = _ruta_local_portada(avatar)
    if ruta is None:
        return None
    return str(ruta) if ruta.is_file() else None
