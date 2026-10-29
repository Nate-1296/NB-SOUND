# =============================================================================
# core/normalizer.py
#
# Capa de normalizacion y fusion de metadatos. Toma la MetadataCruda del
# archivo y los resultados de fuentes externas (Shazam, AcoustID) para
# producir una MetadataNormalizada cohesionada y orientada al matching.
#
# Novedades v3 — fusion de evidencias:
#   - fusionar_con_fuentes_externas(): combina tags locales, Shazamio y
#     AcoustID en una sola MetadataNormalizada con trazabilidad de fuente.
#   - Si Shazamio identifico la cancion y los tags locales estan vacios,
#     los datos de Shazam se usan como fuente principal.
#   - Si Shazam y los tags locales coinciden en artista/titulo, la confianza
#     de la identificacion sube.
#   - El ISRC de Shazam se propaga al campo norm.isrc para la busqueda MB.
#   - _completar_desde_filename() sigue siendo el ultimo recurso.
# =============================================================================

from typing import Optional

from domain.models import (
    ArchivoAudio,
    MetadataCruda,
    MetadataNormalizada,
    ResultadoShazam,
    ResultadoAcoustID,
    FuenteIdentificacion,
    CuarentenaCausa,
)
from infra.logger import obtener_logger
from utils.text import (
    normalizar_titulo,
    normalizar_artista,
    para_comparacion,
    separar_artista_principal,
    extraer_featuring_del_titulo,
    limpiar_numero_pista,
    normalizar_base,
    extraer_anio_del_texto,
    parsear_nombre_archivo,
    limpiar_version_titulo,
    similitud_combinada,
    normalizar_isrc,
)

_log = obtener_logger("normalizer")

_MIN_LONGITUD_ARTISTA = 2
_MIN_LONGITUD_TITULO  = 1

# Umbral de similitud para considerar que dos fuentes "coinciden" en artista/titulo
_SIMILITUD_COINCIDENCIA = 0.75


# =============================================================================
# FUNCION PRINCIPAL
# =============================================================================

def normalizar_metadata(archivo: ArchivoAudio) -> tuple[bool, Optional[CuarentenaCausa]]:
    """
    Construye MetadataNormalizada fusionando todas las fuentes disponibles:
    tags locales, Shazamio y AcoustID. Si todo falla, intenta inferir del
    nombre del archivo.

    Returns:
        (tiene_suficiente_info, causa_cuarentena_o_None)
    """
    cruda = archivo.metadata_cruda
    if cruda is None:
        archivo.agregar_error("No hay metadata cruda disponible para normalizar")
        return False, CuarentenaCausa.METADATA_INSUFICIENTE

    norm = MetadataNormalizada()

    # La duracion siempre viene de los datos tecnicos del audio, no de los tags
    norm.duracion_seg = cruda.duracion_seg

    # --- Paso 1: Normalizar tags locales como base ---
    _poblar_desde_tags_locales(cruda, norm)

    # --- Paso 2: Fusionar con fuentes externas (Shazam / AcoustID) ---
    _fusionar_con_fuentes_externas(
        norm,
        resultado_shazam=archivo.resultado_shazam,
        resultado_acoustid=archivo.resultado_acoustid,
    )

    # --- Paso 3: Verificacion con fallback al nombre de archivo ---
    tiene_artista = len(norm.artista_para_match) >= _MIN_LONGITUD_ARTISTA
    tiene_titulo  = len(norm.titulo_para_match)  >= _MIN_LONGITUD_TITULO

    if not tiene_artista or not tiene_titulo:
        _completar_desde_filename(
            archivo.nombre_archivo, norm, tiene_artista, tiene_titulo,
            resultado_shazam=archivo.resultado_shazam,
        )
        tiene_artista = len(norm.artista_para_match) >= _MIN_LONGITUD_ARTISTA
        tiene_titulo  = len(norm.titulo_para_match)  >= _MIN_LONGITUD_TITULO

    archivo.metadata_norm = norm

    # --- Paso 4: Verificacion final ---
    if not tiene_artista and not tiene_titulo:
        _log.warning(
            f"Metadata insuficiente tras todas las estrategias: "
            f"artista='{norm.artista_principal}' titulo='{norm.titulo}' "
            f"archivo='{archivo.nombre_archivo}'"
        )
        archivo.agregar_advertencia("Metadata insuficiente: sin artista ni titulo usable")
        return False, CuarentenaCausa.METADATA_INSUFICIENTE

    if not tiene_artista:
        archivo.agregar_advertencia("Artista vacio o no normalizable")
    if not tiene_titulo:
        archivo.agregar_advertencia("Titulo vacio o no normalizable")

    _log.debug(
        f"Norm OK [{norm.fuente_artista.value}/{norm.fuente_titulo.value}]: "
        f"'{norm.artista_principal}' - '{norm.titulo}' "
        f"(match: '{norm.artista_para_match}' / '{norm.titulo_para_match}') "
        f"confianza={norm.confianza_identificacion:.2f} "
        f"isrc={norm.isrc or 'N/A'} "
        f"[{archivo.nombre_archivo}]"
    )

    return True, None


# =============================================================================
# NORMALIZACION DESDE TAGS LOCALES
# =============================================================================

def _poblar_desde_tags_locales(cruda: MetadataCruda, norm: MetadataNormalizada) -> None:
    """Rellena la metadata normalizada a partir de los tags ID3 del archivo."""

    # --- Titulo ---
    titulo_raw = normalizar_base(cruda.titulo or "")
    titulo_sin_feat, featuring_del_titulo = extraer_featuring_del_titulo(titulo_raw)
    titulo_limpio = normalizar_titulo(titulo_sin_feat)
    norm.titulo = titulo_limpio

    titulo_sin_version = limpiar_version_titulo(titulo_limpio)
    norm.titulo_para_match = para_comparacion(titulo_sin_version)

    # --- Artista ---
    artista_raw = normalizar_base(cruda.artista or "")
    artista_principal_raw, featuring_del_artista = separar_artista_principal(artista_raw)
    artista_principal = normalizar_artista(artista_principal_raw)
    norm.artista_principal  = artista_principal
    norm.artista_para_match = para_comparacion(artista_principal)
    norm.featuring = featuring_del_titulo or featuring_del_artista

    # --- Album ---
    album_raw = normalizar_base(cruda.album or "")
    norm.album           = album_raw
    norm.album_para_match = para_comparacion(album_raw)

    # --- Campos adicionales ---
    norm.track_number = limpiar_numero_pista(cruda.track_number or "")
    norm.anio         = extraer_anio_del_texto(cruda.anio or "")

    # Confianza base: baja si no hay titulo ni artista
    tiene_titulo  = len(norm.titulo_para_match)  >= _MIN_LONGITUD_TITULO
    tiene_artista = len(norm.artista_para_match) >= _MIN_LONGITUD_ARTISTA
    if tiene_titulo and tiene_artista:
        norm.confianza_identificacion = 0.40
    elif tiene_titulo or tiene_artista:
        norm.confianza_identificacion = 0.20
    else:
        norm.confianza_identificacion = 0.0


# =============================================================================
# FUSION CON FUENTES EXTERNAS
# =============================================================================

def _fusionar_con_fuentes_externas(
    norm: MetadataNormalizada,
    resultado_shazam: Optional[ResultadoShazam],
    resultado_acoustid: Optional[ResultadoAcoustID],
) -> None:
    """
    Enriquece la metadata normalizada con los resultados de Shazam y AcoustID.

    Logica de fusion:
      1. Si Shazam identifico la cancion y los tags locales estan vacios:
         se usan los datos de Shazam como fuente principal.
      2. Si Shazam y los tags locales coinciden (>= 0.75 de similitud):
         se eleva la confianza de identificacion.
      3. Si Shazam proporciona ISRC: se propaga siempre (es muy valioso).
      4. AcoustID no proporciona titulo/artista directamente (solo recording_ids),
         pero su presencia con score alto eleva la confianza.
    """
    tiene_artista_local = len(norm.artista_para_match) >= _MIN_LONGITUD_ARTISTA
    tiene_titulo_local  = len(norm.titulo_para_match)  >= _MIN_LONGITUD_TITULO

    # --- Fusion con Shazam ---
    if resultado_shazam and resultado_shazam.identificado:
        shazam_titulo  = para_comparacion(normalizar_titulo(resultado_shazam.titulo or ""))
        shazam_artista = para_comparacion(normalizar_artista(resultado_shazam.artista or ""))

        # Propagar ISRC siempre (es el dato mas valioso de Shazam)
        if resultado_shazam.isrc:
            isrc_limpio = normalizar_isrc(resultado_shazam.isrc)
            if isrc_limpio:
                norm.isrc = isrc_limpio
                _log.debug(f"ISRC de Shazam: {isrc_limpio}")

        # Completar campos vacios con datos de Shazam
        if not tiene_titulo_local and shazam_titulo:
            titulo_shazam_limpio = normalizar_titulo(resultado_shazam.titulo)
            norm.titulo           = titulo_shazam_limpio
            norm.titulo_para_match = para_comparacion(
                limpiar_version_titulo(titulo_shazam_limpio)
            )
            norm.fuente_titulo = FuenteIdentificacion.SHAZAM
            _log.debug(f"Titulo de Shazam: '{titulo_shazam_limpio}'")

        if not tiene_artista_local and shazam_artista:
            artista_shazam_limpio = normalizar_artista(resultado_shazam.artista)
            norm.artista_principal  = artista_shazam_limpio
            norm.artista_para_match = para_comparacion(artista_shazam_limpio)
            norm.fuente_artista = FuenteIdentificacion.SHAZAM
            _log.debug(f"Artista de Shazam: '{artista_shazam_limpio}'")

        # Enriquecer album y año si no los tenemos
        if not norm.album and resultado_shazam.album:
            norm.album           = resultado_shazam.album
            norm.album_para_match = para_comparacion(resultado_shazam.album)

        if not norm.anio and resultado_shazam.anio:
            norm.anio = resultado_shazam.anio

        # Calcular bonus de confianza segun coincidencia de fuentes
        confianza_shazam = _calcular_bonus_confianza_shazam(
            norm_titulo=norm.titulo_para_match,
            norm_artista=norm.artista_para_match,
            shazam_titulo=shazam_titulo,
            shazam_artista=shazam_artista,
            tiene_isrc=bool(norm.isrc),
        )
        norm.confianza_identificacion = min(
            1.0, norm.confianza_identificacion + confianza_shazam
        )

    # --- Fusion con AcoustID ---
    if resultado_acoustid and resultado_acoustid.recording_ids:
        mejor_score = resultado_acoustid.mejor_score
        # AcoustID con score alto es una señal fuerte de que la cancion existe en MB
        if mejor_score >= 0.90:
            bonus_acoustid = 0.25
        elif mejor_score >= 0.75:
            bonus_acoustid = 0.15
        else:
            bonus_acoustid = 0.05

        norm.confianza_identificacion = min(
            1.0, norm.confianza_identificacion + bonus_acoustid
        )


def _calcular_bonus_confianza_shazam(
    norm_titulo:   str,
    norm_artista:  str,
    shazam_titulo: str,
    shazam_artista: str,
    tiene_isrc:    bool,
) -> float:
    """
    Calcula el bonus de confianza que aporta Shazam en funcion de cuanto
    coinciden sus datos con los tags locales.
    """
    bonus = 0.0

    # ISRC es la señal mas fuerte: identifica univocamente la grabacion
    if tiene_isrc:
        bonus += 0.30
        return min(0.45, bonus)  # Con ISRC, el techo de bonus es alto

    # Coincidencia de titulo
    if norm_titulo and shazam_titulo:
        sim_titulo = similitud_combinada(norm_titulo, shazam_titulo)
        if sim_titulo >= _SIMILITUD_COINCIDENCIA:
            bonus += 0.15

    # Coincidencia de artista
    if norm_artista and shazam_artista:
        sim_artista = similitud_combinada(norm_artista, shazam_artista)
        if sim_artista >= _SIMILITUD_COINCIDENCIA:
            bonus += 0.15

    # Shazam identifico aunque no tengamos tags: tambien suma
    if not norm_titulo and shazam_titulo:
        bonus += 0.10
    if not norm_artista and shazam_artista:
        bonus += 0.10

    return min(0.35, bonus)


# =============================================================================
# FALLBACK: COMPLETAR DESDE NOMBRE DE ARCHIVO
# =============================================================================

# Titulos demasiado genericos para hacer matching fiable sin artista confirmado
_TITULOS_GENERICOS = frozenset({
    "track", "audio", "music", "song", "untitled", "sin titulo", "unknown",
    "pista", "tema", "cancion", "new recording", "recording", "new track",
    "vocal", "instrumental", "demo", "draft", "test", "sample",
})

# Longitud minima del artista inferido para considerarlo util
_MIN_ARTISTA_FILENAME = 3


def _completar_desde_filename(
    nombre_archivo: str,
    norm: MetadataNormalizada,
    tiene_artista: bool,
    tiene_titulo: bool,
    resultado_shazam=None,
) -> None:
    """
    Ultimo recurso: infiere artista y titulo del nombre del archivo.
    Solo modifica los campos que siguen vacios.

    Mejoras v3.1:
    - Si Shazam identifico la cancion y el artista inferido del filename
      diverge del artista de Shazam, NO se usa el artista del filename
      (evita introducir ruido semantico en el matching).
    - Si el titulo inferido es un titulo generico (track, audio, untitled...)
      y no hay artista confirmado por Shazam, se descarta para no inducir
      falsos positivos en MB.
    """
    inferido = parsear_nombre_archivo(nombre_archivo)

    # --- Titulo ---
    if not tiene_titulo and inferido.get("titulo"):
        titulo_inf = normalizar_titulo(inferido["titulo"])
        titulo_norm = para_comparacion(titulo_inf)

        # Detectar titulo generico: si no hay artista externo confirmado,
        # un titulo generico sin artista produce matches de baja calidad
        es_generico = titulo_norm in _TITULOS_GENERICOS or len(titulo_norm) <= 2
        tiene_artista_externo = (
            resultado_shazam is not None
            and resultado_shazam.identificado
            and bool(resultado_shazam.artista)
        )

        if es_generico and not tiene_artista_externo:
            _log.debug(
                f"Titulo generico descartado del filename: '{titulo_inf}' "
                f"(sin fuente externa de artista)"
            )
        else:
            titulo_sin_version = limpiar_version_titulo(titulo_inf)
            norm.titulo           = titulo_inf
            norm.titulo_para_match = para_comparacion(titulo_sin_version)
            norm.fuente_titulo     = FuenteIdentificacion.NOMBRE_ARCHIVO
            _log.debug(f"Titulo inferido del nombre: '{titulo_inf}'")

    # --- Artista ---
    if not tiene_artista and inferido.get("artista"):
        artista_inf = normalizar_artista(inferido["artista"])
        artista_norm = para_comparacion(artista_inf)

        # Descartar artistas demasiado cortos
        if len(artista_norm) < _MIN_ARTISTA_FILENAME:
            _log.debug(f"Artista inferido demasiado corto, descartado: '{artista_inf}'")

        # Si Shazam identifico con artista propio, verificar coherencia
        elif (resultado_shazam is not None
              and resultado_shazam.identificado
              and resultado_shazam.artista):
            shazam_artista_norm = para_comparacion(
                normalizar_artista(resultado_shazam.artista)
            )
            sim = similitud_combinada(artista_norm, shazam_artista_norm)
            if sim < _SIMILITUD_COINCIDENCIA:
                # Divergencia: Shazam conoce el artista real, el filename miente
                # → priorizar Shazam (ya fue aplicado en fusion), no sobreescribir
                _log.debug(
                    f"Artista filename '{artista_inf}' diverge de Shazam "
                    f"'{resultado_shazam.artista}' (sim={sim:.2f}) — descartado"
                )
            else:
                norm.artista_principal  = artista_inf
                norm.artista_para_match = artista_norm
                norm.fuente_artista     = FuenteIdentificacion.NOMBRE_ARCHIVO
                _log.debug(f"Artista inferido del nombre: '{artista_inf}'")
        else:
            norm.artista_principal  = artista_inf
            norm.artista_para_match = artista_norm
            norm.fuente_artista     = FuenteIdentificacion.NOMBRE_ARCHIVO
            _log.debug(f"Artista inferido del nombre: '{artista_inf}'")

    if norm.track_number is None and inferido.get("track_number"):
        try:
            norm.track_number = int(inferido["track_number"])
        except (ValueError, TypeError):
            pass


# =============================================================================
# CONSTRUCCION DE QUERY DE BUSQUEDA
# =============================================================================

def construir_query_busqueda(norm: MetadataNormalizada) -> dict[str, str]:
    """
    Construye los parametros de busqueda a enviar al cliente externo.
    """
    query: dict[str, str] = {}

    if norm.artista_principal:
        query["artista"] = norm.artista_principal
    if norm.titulo:
        query["titulo"] = norm.titulo
    if norm.album:
        query["album"] = norm.album
    if norm.track_number is not None:
        query["track_number"] = str(norm.track_number)
    if norm.duracion_seg is not None:
        query["duracion_seg"] = str(int(norm.duracion_seg))
    if norm.isrc:
        query["isrc"] = norm.isrc

    return query
