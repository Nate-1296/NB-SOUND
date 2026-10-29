# =============================================================================
# core/writer.py
#
# Escritura segura de metadatos y organizacion final de archivos.
#
# Principio: "tocar poco, comprobar mucho".
#   1. Construir los metadatos finales canonicos a partir del candidato MB.
#   2. Copiar el archivo original a un temporal (nunca tocar el original).
#   3. Escribir los tags ID3 sobre la copia temporal.
#   4. Reabrir y verificar que los tags quedaron correctamente escritos.
#   5. Mover el temporal al destino final de forma atomica.
#   6. Verificar que el archivo movido es legible en su nueva ubicacion.
#
# Si cualquier paso falla: el original no se toca, el temporal se elimina.
#
# Novedades v3:
#   - El tag TXXX:tagger_sources registra las fuentes que participaron
#     en la decision (shazam, acoustid, ia) para auditoria posterior.
#   - El ISRC se escribe en el tag TSRC si estuvo disponible.
#   - construir_ruta_destino() ahora tambien recibe el tipo de release
#     para casos donde el candidato es "Other" y se redirige a "otros/".
# =============================================================================

import shutil
from pathlib import Path
from typing import Optional

try:
    from mutagen.id3 import (
        ID3, ID3NoHeaderError,
        TIT2, TPE1, TALB, TPE2, TRCK, TDRC, TCON, TXXX, TSRC
    )
    from mutagen.mp3 import MP3
    MUTAGEN_DISPONIBLE = True
except ImportError:
    MUTAGEN_DISPONIBLE = False

from config import settings
from config.settings import (
    RELEASE_TYPE_TO_FOLDER,
    TRACK_FILENAME_TEMPLATE,
    PROCESSED_TAG_MARKER,
    PROCESSED_TAG_FIELD,
)
from domain.models import (
    DecisionArchivo,
    DecisionTipo,
    CandidatoMB,
    CuarentenaCausa,
)
from infra.logger import obtener_logger
from core.validator import revalidar_post_escritura
from utils.text import construir_slug, construir_slug_artista, construir_slug_album

_log = obtener_logger("writer")

_SUFIJO_TEMPORAL = ".tagger_tmp"


def _validar_metadata_canonica_obligatoria(candidato: CandidatoMB) -> tuple[bool, str]:
    """
    Garantiza metadatos mínimos para materializar un archivo en biblioteca.
    """
    titulo = (candidato.titulo_oficial or "").strip()
    artista = (candidato.artista_principal or "").strip()

    if not titulo:
        return False, "titulo_oficial ausente en candidato final"
    if not artista:
        return False, "artista_principal ausente en candidato final"
    return True, ""


# =============================================================================
# CONSTRUCCION DE RUTA DESTINO
# =============================================================================

def _clasificar_carpeta_biblioteca(candidato: CandidatoMB) -> tuple[str, Optional[str]]:
    """
    Clasifica el candidato en una carpeta de biblioteca semántica.

    Retorna (tipo_carpeta, slug_subcarpeta_opcional).

    Lógica de tres niveles (v3.2):
      1. tipo_release conocido y aceptado → albumes / singles_y_ep
      2. tipo no formal pero álbum consistente → heurística secundaria
      3. Sin clasificación clara → otros (sin subcarpeta de álbum)

    Nunca crea artista/otros/<album>/ cuando el release es incertidumbre real.
    """
    tipo = candidato.tipo_release or ""
    album = candidato.album_oficial or ""

    # --- Nivel 1: tipo formal presente ---
    if tipo in RELEASE_TYPE_TO_FOLDER:
        tipo_carpeta = RELEASE_TYPE_TO_FOLDER[tipo]
        if tipo_carpeta == "otros":
            # Tipos penalizados/especiales: sí usar subcarpeta de álbum si existe
            slug_sub = construir_slug_album(album) if album else None
            return "otros", slug_sub
        # albumes o singles_y_ep → siempre incluir subcarpeta de álbum/release
        slug_sub = construir_slug_album(album) if album else construir_slug_album("sin_album")
        return tipo_carpeta, slug_sub

    # --- Nivel 2: sin tipo formal pero con álbum/release consistente ---
    if album:
        from utils.text import similitud_combinada, para_comparacion, limpiar_version_titulo
        titulo_track = limpiar_version_titulo(candidato.titulo_oficial or "")
        album_norm   = para_comparacion(limpiar_version_titulo(album))
        titulo_norm  = para_comparacion(titulo_track)

        # Heurística: si el título del release es muy similar al título de la
        # pista, probablemente es un single o EP (la pista da nombre al release).
        # Si son distintos, es un álbum con varias pistas.
        similitud_titulo_album = (
            similitud_combinada(titulo_norm, album_norm)
            if titulo_norm and album_norm else 0.0
        )
        es_probable_single_ep = similitud_titulo_album >= 0.75

        if es_probable_single_ep:
            return "singles_y_ep", construir_slug_album(album)
        else:
            return "albumes", construir_slug_album(album)

    # --- Nivel 3: sin tipo ni álbum → otros sin subcarpeta ---
    return "otros", None


def construir_ruta_destino(
    candidato: CandidatoMB,
    directorio_biblioteca: Optional[Path] = None,
) -> tuple[Path, str]:
    """
    Calcula la carpeta de destino y el nombre de archivo final.

    Estructura semántica v3.2:
      biblioteca/<artista>/albumes/<album>/<track>_<titulo>.mp3
      biblioteca/<artista>/singles_y_ep/<release>/<track>_<titulo>.mp3
      biblioteca/<artista>/otros/<track>_<titulo>.mp3
      biblioteca/<artista>/otros/<album>/<track>_<titulo>.mp3   (solo tipos penalizados)
    """
    biblioteca = directorio_biblioteca or settings.DEFAULT_LIBRARY_DIR
    ok_canon, msg = _validar_metadata_canonica_obligatoria(candidato)
    if not ok_canon:
        raise ValueError(f"candidato invalido para ruta destino: {msg}")

    slug_artista = construir_slug_artista(candidato.artista_principal or "desconocido")
    tipo_carpeta, slug_sub = _clasificar_carpeta_biblioteca(candidato)

    if slug_sub:
        carpeta = biblioteca / slug_artista / tipo_carpeta / slug_sub
    else:
        carpeta = biblioteca / slug_artista / tipo_carpeta

    track_num      = candidato.track_number or 0
    titulo_canonico = candidato.titulo_oficial
    slug_titulo    = construir_slug(titulo_canonico)
    nombre_archivo = TRACK_FILENAME_TEMPLATE.format(
        track_num=track_num,
        slug_titulo=slug_titulo,
    )

    return carpeta, nombre_archivo


# =============================================================================
# ESCRITURA SEGURA
# =============================================================================

def escribir_y_mover(
    decision: DecisionArchivo,
    directorio_biblioteca: Optional[Path] = None,
    directorio_temp: Optional[Path] = None,
) -> tuple[bool, Optional[CuarentenaCausa], str]:
    """
    Ejecuta el proceso completo de escritura de tags y movimiento del archivo.

    Args:
        decision:              Decision ACEPTADO con candidato elegido.
        directorio_biblioteca: Destino final de la biblioteca organizada.
        directorio_temp:       Directorio para temporales (externo al proyecto).

    Returns:
        (exito, causa_cuarentena_si_fallo, mensaje)
    """
    if not MUTAGEN_DISPONIBLE:
        return False, CuarentenaCausa.ESCRITURA_FALLIDA, "Mutagen no disponible"

    _tipos_escribibles = {DecisionTipo.ACEPTADO, DecisionTipo.ACEPTADO_PROVISIONAL}
    if decision.tipo not in _tipos_escribibles or decision.candidato_elegido is None:
        return False, CuarentenaCausa.ERROR_INESPERADO, (
            f"Decision no escribible: {decision.tipo.value}"
        )

    candidato     = decision.candidato_elegido
    ruta_original = decision.archivo.ruta_original
    dir_temp      = directorio_temp or settings.DEFAULT_TEMP_DIR

    ok_canon, msg_canon = _validar_metadata_canonica_obligatoria(candidato)
    if not ok_canon:
        return (
            False,
            CuarentenaCausa.METADATA_FINAL_INVALIDA,
            f"Metadata final invalida: {msg_canon}",
        )

    # --- Calcular ruta destino ---
    carpeta_destino, nombre_destino = construir_ruta_destino(
        candidato, directorio_biblioteca
    )
    ruta_destino = carpeta_destino / nombre_destino

    decision.ruta_destino   = ruta_destino
    decision.nombre_destino = nombre_destino

    if settings.DRY_RUN:
        _log.info(f"[DRY_RUN] {ruta_original.name} -> {ruta_destino}")
        return True, None, f"DRY_RUN: destino={ruta_destino}"

    # --- Crear directorio temporal ---
    try:
        dir_temp.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return False, CuarentenaCausa.ESCRITURA_FALLIDA, f"No se pudo crear dir temp: {e}"

    ruta_temporal = dir_temp / (ruta_original.name + _SUFIJO_TEMPORAL)
    if ruta_temporal.exists():
        _eliminar_temporal(ruta_temporal)

    try:
        # Paso 1: Copiar a temporal
        shutil.copy2(str(ruta_original), str(ruta_temporal))
        _log.debug(f"Copia temporal: {ruta_temporal}")

        # Paso 2: Escribir tags sobre el temporal
        exito_tags, msg_tags = _escribir_tags(ruta_temporal, decision)
        if not exito_tags:
            _eliminar_temporal(ruta_temporal)
            return False, CuarentenaCausa.ESCRITURA_FALLIDA, msg_tags

        # Paso 3: Revalidar post-escritura
        ok_rev, msg_rev = revalidar_post_escritura(ruta_temporal)
        if not ok_rev:
            _eliminar_temporal(ruta_temporal)
            return False, CuarentenaCausa.VALIDACION_POST_ESCRITURA, msg_rev

        # Paso 4: Crear carpeta destino y resolver conflictos de nombre
        carpeta_destino.mkdir(parents=True, exist_ok=True)

        if ruta_destino.exists():
            ruta_destino = _resolver_conflicto_nombre(ruta_destino)
            decision.ruta_destino   = ruta_destino
            decision.nombre_destino = ruta_destino.name
            _log.warning(f"Conflicto de nombre resuelto: {decision.nombre_destino}")

        shutil.move(str(ruta_temporal), str(ruta_destino))
        _log.debug(f"Archivo movido a: {ruta_destino}")

        # Paso 5: Verificar en destino final
        ok_final, msg_final = revalidar_post_escritura(ruta_destino)
        if not ok_final:
            # Intentar revertir
            try:
                shutil.move(str(ruta_destino), str(ruta_original))
            except Exception as _exc:
                _log.debug("Excepcion ignorada en %s: %s", "writer.py", _exc)
            return False, CuarentenaCausa.VALIDACION_POST_ESCRITURA, msg_final

        _log.info(f"Guardado: {ruta_destino}")
        return True, None, f"OK: {ruta_destino}"

    except PermissionError as e:
        _eliminar_temporal(ruta_temporal)
        return False, CuarentenaCausa.ESCRITURA_FALLIDA, f"Sin permiso: {e}"
    except OSError as e:
        _eliminar_temporal(ruta_temporal)
        return False, CuarentenaCausa.ESCRITURA_FALLIDA, f"Error de OS: {e}"
    except Exception as e:
        _eliminar_temporal(ruta_temporal)
        _log.error(f"Error inesperado en escritura de {ruta_original.name}: {e}")
        return False, CuarentenaCausa.ERROR_INESPERADO, f"Error inesperado: {e}"


# =============================================================================
# ESCRITURA DE TAGS ID3
# =============================================================================

def _escribir_tags(ruta: Path, decision: DecisionArchivo) -> tuple[bool, str]:
    """
    Escribe los tags ID3v2.3 canonicos sobre el archivo indicado.
    Incluye marcadores de trazabilidad para auditoria posterior.
    """
    candidato = decision.candidato_elegido
    if candidato is None:
        return False, "Sin candidato para escribir tags"

    try:
        try:
            tags = ID3(str(ruta))
        except ID3NoHeaderError:
            tags = ID3()

        # Preservar frames no gestionados por el pipeline (evita perder metadata útil)
        for frame in ("TIT2", "TPE1", "TPE2", "TALB", "TRCK", "TDRC", "TSRC"):
            tags.delall(frame)
        for desc in (
            PROCESSED_TAG_FIELD.split(":", 1)[-1],
            "mb_recording_id",
            "mb_release_id",
            "mb_release_group_id",
            "mb_release_type",
            "tagger_sources",
            "tagger_ia_model",
        ):
            tags.delall("TXXX:" + desc)

        if candidato.titulo_oficial:
            tags.add(TIT2(encoding=3, text=candidato.titulo_oficial))

        if candidato.artista_principal:
            tags.add(TPE1(encoding=3, text=candidato.artista_principal))
            tags.add(TPE2(encoding=3, text=candidato.artista_principal))

        if candidato.album_oficial:
            tags.add(TALB(encoding=3, text=candidato.album_oficial))

        if candidato.track_number is not None:
            track_str = str(candidato.track_number)
            if candidato.track_total:
                track_str = f"{candidato.track_number}/{candidato.track_total}"
            tags.add(TRCK(encoding=3, text=track_str))

        if candidato.anio_release:
            tags.add(TDRC(encoding=3, text=str(candidato.anio_release)))

        # ISRC en tag estandar TSRC
        isrc_a_escribir = (
            candidato.isrc
            or (decision.archivo.isrc_disponible)
        )
        if isrc_a_escribir:
            tags.add(TSRC(encoding=3, text=isrc_a_escribir))

        # Marcadores de trazabilidad v3
        tags.add(TXXX(encoding=3, desc=PROCESSED_TAG_FIELD.split(":", 1)[-1],
                      text=PROCESSED_TAG_MARKER))
        tags.add(TXXX(encoding=3, desc="mb_recording_id",
                      text=candidato.recording_id or ""))
        tags.add(TXXX(encoding=3, desc="mb_release_id",
                      text=candidato.release_id or ""))
        tags.add(TXXX(encoding=3, desc="mb_release_group_id",
                      text=candidato.release_group_id or ""))
        tags.add(TXXX(encoding=3, desc="mb_release_type",
                      text=candidato.tipo_release or ""))

        # Fuentes que contribuyeron a la decision
        fuentes_str = ",".join(f.value for f in decision.fuentes_usadas)
        if fuentes_str:
            tags.add(TXXX(encoding=3, desc="tagger_sources", text=fuentes_str))

        # Si la IA intervino, dejarlo registrado
        if decision.decision_ia and decision.decision_ia.valida:
            tags.add(TXXX(encoding=3, desc="tagger_ia_model",
                          text=decision.decision_ia.modelo_usado or ""))

        tags.save(str(ruta), v2_version=3)
        return True, "OK"

    except Exception as e:
        return False, f"Error escribiendo tags: {e}"


# =============================================================================
# UTILIDADES INTERNAS
# =============================================================================

def _eliminar_temporal(ruta: Path) -> None:
    try:
        ruta.unlink(missing_ok=True)
    except Exception as _exc:
        _log.debug("Excepcion ignorada en %s: %s", "writer.py", _exc)


def _resolver_conflicto_nombre(ruta: Path) -> Path:
    """Agrega un sufijo numerico incremental hasta encontrar un nombre libre."""
    contador = 2
    while True:
        nuevo_nombre = f"{ruta.stem}_{contador}{ruta.suffix}"
        nueva_ruta   = ruta.parent / nuevo_nombre
        if not nueva_ruta.exists():
            return nueva_ruta
        contador += 1
        if contador > 99:
            raise OSError(f"Demasiados conflictos de nombre en: {ruta.parent}")
        
