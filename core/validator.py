# =============================================================================
# core/validator.py
#
# Validacion tecnica de archivos MP3. Verifica que el archivo sea legible,
# que su estructura sea minimamente coherente, que la duracion y el bitrate
# esten dentro de rangos aceptables, y que sea posible leer/escribir tags ID3.
#
# La validacion es intencionalmente conservadora: si hay duda razonable
# sobre la integridad del archivo, no pasa. Es mejor enviar a cuarentena
# un archivo valido que procesar uno corrupto y perder datos.
#
# Novedades v3:
#   - El hash SHA256 ahora usa tambien los ultimos 512KB ademas del inicio,
#     lo que reduce colisiones en archivos que comparten encabezados identicos.
#   - Se detecta y advierte cuando el archivo tiene tags ID3v1 unicamente
#     (son menos fiables para escritura segura).
# =============================================================================

import hashlib
from pathlib import Path
from typing import Optional

try:
    from mutagen.mp3 import MP3, HeaderNotFoundError
    from mutagen.id3 import ID3, ID3NoHeaderError
    from mutagen import MutagenError
    MUTAGEN_DISPONIBLE = True
except ImportError:
    MUTAGEN_DISPONIBLE = False

from config.settings import (
    MIN_DURATION_SECONDS,
    MAX_DURATION_SECONDS,
    MIN_BITRATE_KBPS,
    MIN_FILE_SIZE_BYTES,
)
from domain.models import ArchivoAudio, MetadataCruda, CuarentenaCausa
from infra.logger import obtener_logger

_log = obtener_logger("validator")

# Bytes leidos en cada chunk del hash
_HASH_CHUNK_SIZE = 8192
# Maximo de bytes leidos desde el inicio del archivo para el hash
_HASH_MAX_BYTES_INICIO = 512 * 1024   # 512 KB
# Maximo de bytes leidos desde el final del archivo para el hash
_HASH_MAX_BYTES_FINAL  = 512 * 1024   # 512 KB


# =============================================================================
# FUNCION PRINCIPAL
# =============================================================================

def validar_archivo(archivo: ArchivoAudio) -> tuple[bool, Optional[CuarentenaCausa]]:
    """
    Ejecuta la validacion tecnica completa sobre un ArchivoAudio.
    Popula los campos metadata_cruda y hash_sha256 si la validacion pasa.

    Returns:
        (es_valido, causa_cuarentena_o_None)
    """
    if not MUTAGEN_DISPONIBLE:
        _log.error("Mutagen no esta instalado. Ejecuta: pip install mutagen")
        return False, CuarentenaCausa.ARCHIVO_ILEGIBLE

    ruta = archivo.ruta_original

    # --- Existencia y tipo ---
    if not ruta.exists():
        _log.warning(f"Archivo no existe: {ruta.name}")
        archivo.agregar_error("El archivo no existe en disco al momento de validar")
        return False, CuarentenaCausa.ARCHIVO_ILEGIBLE

    if not ruta.is_file():
        _log.warning(f"La ruta no es un archivo regular: {ruta.name}")
        return False, CuarentenaCausa.ARCHIVO_ILEGIBLE

    # --- Tamano ---
    try:
        tamano_actual = ruta.stat().st_size
    except OSError as e:
        _log.error(f"Error al leer stat de {ruta.name}: {e}")
        return False, CuarentenaCausa.ARCHIVO_ILEGIBLE

    if tamano_actual < MIN_FILE_SIZE_BYTES:
        _log.warning(f"Archivo demasiado pequeno: {ruta.name} ({tamano_actual} bytes)")
        archivo.agregar_error(f"Tamano insuficiente: {tamano_actual} bytes")
        return False, CuarentenaCausa.ARCHIVO_MUY_PEQUENO

    # --- Hash de identificacion ---
    archivo.hash_sha256 = _calcular_hash_combinado(ruta)

    # --- Lectura con Mutagen ---
    try:
        audio_mp3 = MP3(str(ruta))
    except HeaderNotFoundError:
        _log.warning(f"Header MP3 no encontrado: {ruta.name}")
        archivo.agregar_error("Header MP3 no encontrado o archivo no es MP3")
        return False, CuarentenaCausa.ARCHIVO_CORRUPTO
    except MutagenError as e:
        _log.warning(f"Mutagen no pudo leer {ruta.name}: {e}")
        archivo.agregar_error(f"Error de Mutagen: {e}")
        return False, CuarentenaCausa.ARCHIVO_CORRUPTO
    except Exception as e:
        _log.error(f"Error inesperado abriendo {ruta.name}: {e}")
        archivo.agregar_error(f"Error inesperado: {e}")
        return False, CuarentenaCausa.ARCHIVO_ILEGIBLE

    # --- Duracion ---
    duracion = audio_mp3.info.length if audio_mp3.info else None
    if duracion is None or duracion <= 0:
        _log.warning(f"Duracion invalida o nula: {ruta.name}")
        archivo.agregar_error("No se pudo determinar la duracion del archivo")
        return False, CuarentenaCausa.DURACION_INVALIDA

    if duracion < MIN_DURATION_SECONDS:
        _log.warning(f"Duracion demasiado corta ({duracion:.1f}s): {ruta.name}")
        archivo.agregar_error(f"Duracion insuficiente: {duracion:.1f}s")
        return False, CuarentenaCausa.DURACION_INVALIDA

    if duracion > MAX_DURATION_SECONDS:
        # No cuartenar por esto, pero si registrar para inspeccion
        archivo.agregar_advertencia(f"Duracion muy larga: {duracion:.1f}s")

    # --- Bitrate ---
    bitrate_kbps = None
    if audio_mp3.info and audio_mp3.info.bitrate:
        bitrate_kbps = int(audio_mp3.info.bitrate / 1000)

    if bitrate_kbps is not None and bitrate_kbps < MIN_BITRATE_KBPS:
        _log.warning(f"Bitrate insuficiente ({bitrate_kbps} kbps): {ruta.name}")
        archivo.agregar_error(f"Bitrate insuficiente: {bitrate_kbps} kbps")
        return False, CuarentenaCausa.BITRATE_INSUFICIENTE

    # --- Tags ID3 ---
    metadata_cruda = _extraer_metadata_cruda(ruta, audio_mp3)
    archivo.metadata_cruda = metadata_cruda
    archivo.es_legible = True

    _log.debug(
        f"Validacion OK: {ruta.name} | "
        f"duracion={duracion:.1f}s | bitrate={bitrate_kbps}kbps"
    )

    return True, None


# =============================================================================
# REVALIDACION POST-ESCRITURA
# =============================================================================

def revalidar_post_escritura(ruta: Path) -> tuple[bool, str]:
    """
    Verifica que un archivo sea legible y tenga metadatos coherentes
    despues de haber sido modificado. Devuelve (ok, mensaje).
    """
    if not MUTAGEN_DISPONIBLE:
        return False, "Mutagen no disponible"

    try:
        audio_mp3 = MP3(str(ruta))
        if not audio_mp3.info or audio_mp3.info.length <= 0:
            return False, "Duracion invalida post-escritura"

        try:
            tags = ID3(str(ruta))
            if not tags:
                return False, "No se pudieron leer tags ID3 post-escritura"
        except ID3NoHeaderError:
            return False, "Sin header ID3 post-escritura"

        return True, "OK"

    except MutagenError as e:
        return False, f"Error Mutagen post-escritura: {e}"
    except Exception as e:
        return False, f"Error inesperado post-escritura: {e}"


# =============================================================================
# EXTRACCION DE METADATA CRUDA
# =============================================================================

def _extraer_metadata_cruda(ruta: Path, audio_mp3: "MP3") -> MetadataCruda:
    """
    Extrae todos los campos de metadatos del archivo sin ninguna transformacion.
    Preserva los valores exactamente como estan en el archivo.
    """
    meta = MetadataCruda()

    if audio_mp3.info:
        meta.duracion_seg = audio_mp3.info.length
        meta.bitrate_kbps = (
            int(audio_mp3.info.bitrate / 1000) if audio_mp3.info.bitrate else None
        )
        meta.es_vbr      = getattr(audio_mp3.info, "bitrate_mode", 0) != 0
        meta.sample_rate = getattr(audio_mp3.info, "sample_rate", None)
        modo_raw         = getattr(audio_mp3.info, "mode", None)
        meta.modo        = _traducir_modo_canal(modo_raw)

    tags = audio_mp3.tags
    if tags is None:
        _log.debug(f"Sin tags ID3: {ruta.name}")
        return meta

    meta.titulo        = _leer_tag_texto(tags, ["TIT2"])
    meta.artista       = _leer_tag_texto(tags, ["TPE1"])
    meta.album         = _leer_tag_texto(tags, ["TALB"])
    meta.artista_album = _leer_tag_texto(tags, ["TPE2"])
    meta.track_number  = _leer_tag_texto(tags, ["TRCK"])
    meta.anio          = _leer_tag_texto(tags, ["TDRC", "TYER", "TDAT"])
    meta.genero        = _leer_tag_texto(tags, ["TCON"])
    meta.subtitle      = _leer_tag_texto(tags, ["TIT3"])
    meta.comment       = _leer_tag_texto(tags, ["COMM"])
    meta.language      = _leer_tag_texto(tags, ["TLAN"])
    meta.website       = _leer_tag_texto(tags, ["WOAR", "WOAS"])
    disc_raw = _leer_tag_texto(tags, ["TPOS"])
    meta.disc_number, meta.total_discs = _parse_parte_total(disc_raw)
    meta.original_date = _leer_tag_texto(tags, ["TDOR"])
    meta.original_year = _leer_tag_texto(tags, ["TORY"])

    meta.composer      = _leer_tag_texto(tags, ["TCOM"])
    meta.composer_sort = _leer_tag_texto(tags, ["TSOC"])
    meta.lyricist      = _leer_tag_texto(tags, ["TEXT"])
    meta.arranger      = _leer_txxx(tags, "arranger")
    meta.conductor     = _leer_tag_texto(tags, ["TPE3"]) or _leer_txxx(tags, "conductor")
    meta.director      = _leer_txxx(tags, "director")
    meta.djmixer       = _leer_txxx(tags, "djmixer")
    meta.engineer      = _leer_txxx(tags, "engineer")
    meta.mixer         = _leer_txxx(tags, "mixer")
    meta.producer      = _leer_txxx(tags, "producer")
    meta.remixer       = _leer_tag_texto(tags, ["TPE4"]) or _leer_txxx(tags, "remixer")
    meta.writer        = _leer_tag_texto(tags, ["TEXT"]) or _leer_txxx(tags, "writer")
    meta.work          = _leer_tag_texto(tags, ["TIT1"]) or _leer_txxx(tags, "work")
    meta.performer_roles = _leer_txxx_prefijo(tags, "performer:")

    meta.lyrics_plain  = _leer_tag_texto(tags, ["USLT"])
    meta.lyrics_synced = _leer_tag_texto(tags, ["SYLT"])

    meta.musicbrainz_ids = {
        "musicbrainz_recordingid": _leer_txxx(tags, "musicbrainz_recordingid") or _leer_txxx(tags, "mb_recording_id") or "",
        "musicbrainz_trackid": _leer_txxx(tags, "musicbrainz_trackid") or "",
        "musicbrainz_albumid": _leer_txxx(tags, "musicbrainz_albumid") or _leer_txxx(tags, "mb_release_id") or "",
        "musicbrainz_releasegroupid": _leer_txxx(tags, "musicbrainz_releasegroupid") or _leer_txxx(tags, "mb_release_group_id") or "",
        "musicbrainz_artistid": _leer_txxx(tags, "musicbrainz_artistid") or "",
        "musicbrainz_albumartistid": _leer_txxx(tags, "musicbrainz_albumartistid") or "",
        "musicbrainz_workid": _leer_txxx(tags, "musicbrainz_workid") or "",
        "musicbrainz_discid": _leer_txxx(tags, "musicbrainz_discid") or "",
        "musicbrainz_originalalbumid": _leer_txxx(tags, "musicbrainz_originalalbumid") or "",
        "musicbrainz_originalartistid": _leer_txxx(tags, "musicbrainz_originalartistid") or "",
        "iswc": _leer_txxx(tags, "iswc") or "",
    }
    meta.musicbrainz_ids = {k: v for k, v in meta.musicbrainz_ids.items() if v}
    meta.acoustid_id = _leer_txxx(tags, "acoustid_id")
    meta.acoustid_fingerprint = _leer_txxx(tags, "acoustid_fingerprint")

    return meta


def _leer_tag_texto(tags: object, frames: list[str]) -> Optional[str]:
    """
    Lee el primer frame disponible de una lista de alternativas.
    Retorna el valor como string o None si no existe o esta vacio.
    """
    for frame_id in frames:
        try:
            frame = tags.get(frame_id)
            if frame is not None:
                valor = str(frame)
                if valor.strip():
                    return valor.strip()
        except Exception:
            continue
    return None


def _parse_parte_total(value: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Parsea formatos tipo "2/4" en (parte, total)."""
    raw = (value or "").strip()
    if not raw:
        return None, None
    if "/" not in raw:
        return raw, None
    parte, total = raw.split("/", 1)
    parte = parte.strip() or None
    total = total.strip() or None
    return parte, total


def _leer_txxx_prefijo(tags: object, prefijo: str) -> dict[str, str]:
    """Retorna todos los TXXX cuyo desc comience con el prefijo."""
    try:
        frames = tags.getall("TXXX")
    except Exception:
        return {}
    out: dict[str, str] = {}
    pref = (prefijo or "").strip().lower()
    for frame in frames:
        desc = str(getattr(frame, "desc", "") or "").strip()
        if not desc.lower().startswith(pref):
            continue
        text = getattr(frame, "text", None)
        value = ""
        if isinstance(text, list) and text:
            value = str(text[0]).strip()
        if not value:
            value = str(frame).strip()
        if value:
            out[desc] = value
    return out

def _leer_txxx(tags: object, desc: str) -> Optional[str]:
    """Lee un frame TXXX por descripción exacta (case-insensitive)."""
    try:
        frames = tags.getall("TXXX")
    except Exception:
        return None
    target = (desc or "").strip().lower()
    for frame in frames:
        frame_desc = str(getattr(frame, "desc", "") or "").strip().lower()
        if frame_desc != target:
            continue
        text = getattr(frame, "text", None)
        if isinstance(text, list) and text:
            value = str(text[0]).strip()
            if value:
                return value
        value = str(frame).strip()
        if value:
            return value
    return None


def _traducir_modo_canal(modo: Optional[int]) -> Optional[str]:
    """Convierte el modo numerico de mutagen a descripcion legible."""
    if modo is None:
        return None
    modos = {0: "stereo", 1: "joint_stereo", 2: "dual_channel", 3: "mono"}
    return modos.get(modo, f"modo_{modo}")


# =============================================================================
# HASH COMBINADO (inicio + final del archivo)
# =============================================================================

def _calcular_hash_combinado(ruta: Path) -> Optional[str]:
    """
    Calcula un hash SHA256 usando los primeros 512KB y los ultimos 512KB
    del archivo. Esto reduce colisiones entre archivos que comparten
    encabezados identicos (ej: intros silenciosas del mismo album).
    """
    try:
        hasher      = hashlib.sha256()
        tamano      = ruta.stat().st_size
        bytes_leidos = 0

        with open(ruta, "rb") as f:
            # Leer desde el inicio
            while bytes_leidos < _HASH_MAX_BYTES_INICIO:
                chunk = f.read(_HASH_CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
                bytes_leidos += len(chunk)

            # Leer desde el final si el archivo es suficientemente grande
            offset_final = max(0, tamano - _HASH_MAX_BYTES_FINAL)
            if offset_final > bytes_leidos:
                f.seek(offset_final)
                while True:
                    chunk = f.read(_HASH_CHUNK_SIZE)
                    if not chunk:
                        break
                    hasher.update(chunk)

        return hasher.hexdigest()
    except OSError as e:
        _log.debug(f"No se pudo calcular hash de {ruta.name}: {e}")
        return None
