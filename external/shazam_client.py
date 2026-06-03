# =============================================================================
# external/shazam_client.py
#
# Cliente de identificacion de audio via Shazam usando shazamio.
#
# Rol en el pipeline:
#   Shazamio es la fuente de mayor confianza para titulo y artista cuando
#   los tags locales estan ausentes, son incorrectos o son ambiguos.
#   El ISRC que devuelve (cuando esta disponible) es especialmente valioso:
#   permite localizar la grabacion exacta en MusicBrainz sin ambiguedad.
#
# Shazam es una fuente de alta confianza para identificacion, pero de
# baja confianza para estructura discografica. Por eso solo usamos sus
# datos para enriquecer la busqueda en MusicBrainz, no para reemplazarla.
#
# La API de Shazam no es oficial y puede cambiar o fallar. El modulo
# maneja todos los errores de forma silenciosa: si falla, el pipeline
# continua normalmente con los datos disponibles.
#
# Dependencias opcionales:
#   pip install shazamio
# =============================================================================

import asyncio
from pathlib import Path
from typing import Optional

from config.settings import (
    ENABLE_SHAZAM,
    SHAZAM_TIMEOUT_SEG,
    SHAZAM_MIN_DURACION_SEG,
    CACHE_TTL_NEGATIVE_SECONDS,
)
from domain.models import ResultadoShazam
from external.cache import CacheLocal
from infra.logger import obtener_logger
from utils.text import normalizar_isrc

_log = obtener_logger("shazam_client")

_PREFIJO_CACHE_SHAZAM = "shazam_res"

# Intentar importar shazamio de forma opcional
try:
    from shazamio import Shazam as _ShazamLib
    _SHAZAM_DISPONIBLE = True
except ImportError:
    _SHAZAM_DISPONIBLE = False


# =============================================================================
# CLASE PRINCIPAL
# =============================================================================

class ClienteShazam:
    """
    Identifica canciones usando la API de Shazam via shazamio.
    Se instancia una vez por ejecucion del pipeline.
    """

    def __init__(self, cache: Optional[CacheLocal] = None) -> None:
        self._cache = cache or CacheLocal()

        self._activo = ENABLE_SHAZAM and _SHAZAM_DISPONIBLE

        if ENABLE_SHAZAM and not _SHAZAM_DISPONIBLE:
            _log.info(
                "Modulo Shazam desactivado: shazamio no instalado. "
                "(pip install shazamio)"
            )
        elif self._activo:
            _log.info("Cliente Shazam inicializado y activo.")

    # ------------------------------------------------------------------
    # API PUBLICA
    # ------------------------------------------------------------------

    @property
    def activo(self) -> bool:
        """True si el modulo puede ejecutarse."""
        return self._activo

    def identificar(
        self,
        ruta_archivo: Path,
        duracion_seg: Optional[float] = None,
        hash_archivo: Optional[str] = None,
    ) -> ResultadoShazam:
        """
        Identifica una cancion enviandola a Shazam.

        Args:
            ruta_archivo:  Ruta al archivo MP3.
            duracion_seg:  Duracion del audio (para omitir archivos muy cortos).
            hash_archivo:  Hash SHA256 del archivo para clave de cache.

        Returns:
            ResultadoShazam con titulo, artista, ISRC si fue identificado.
        """
        resultado = ResultadoShazam(disponible=self._activo)

        if not self._activo:
            return resultado

        # Omitir archivos demasiado cortos (Shazam no funciona bien con menos de ~20s)
        if duracion_seg is not None and duracion_seg < SHAZAM_MIN_DURACION_SEG:
            _log.debug(
                f"Shazam omitido (duracion {duracion_seg:.1f}s < "
                f"{SHAZAM_MIN_DURACION_SEG}s): {ruta_archivo.name}"
            )
            return resultado

        # Clave de cache basada en el hash del archivo (contenido, no nombre)
        clave_id = hash_archivo or ruta_archivo.name
        clave_cache = CacheLocal.construir_clave(
            _PREFIJO_CACHE_SHAZAM, {"id": clave_id}
        )

        datos_cacheados = self._cache.obtener(clave_cache)
        if datos_cacheados is not None:
            _log.debug(f"Shazam cache hit: {ruta_archivo.name}")
            return self._deserializar_resultado(datos_cacheados)

        # Consultar Shazam
        try:
            resultado = asyncio.run(
                asyncio.wait_for(
                    self._identificar_async(ruta_archivo),
                    timeout=SHAZAM_TIMEOUT_SEG,
                )
            )
        except asyncio.TimeoutError:
            _log.warning(
                f"Shazam timeout ({SHAZAM_TIMEOUT_SEG}s) para: {ruta_archivo.name}"
            )
            resultado.error = "Timeout al consultar Shazam"
            resultado.disponible = True
            self._cache.guardar_con_ttl(
                clave_cache,
                self._serializar_resultado(resultado),
                CACHE_TTL_NEGATIVE_SECONDS,
            )
            return resultado
        except Exception as e:
            _log.warning(f"Error consultando Shazam para {ruta_archivo.name}: {e}")
            resultado.error = str(e)
            resultado.disponible = True
            self._cache.guardar_con_ttl(
                clave_cache,
                self._serializar_resultado(resultado),
                CACHE_TTL_NEGATIVE_SECONDS,
            )
            return resultado

        # Guardar siempre en cache para evitar repetir consultas de archivos
        # no identificables o con error transitorio corto.
        if resultado.identificado:
            self._cache.guardar(clave_cache, self._serializar_resultado(resultado))
            _log.debug(
                f"Shazam identifico: '{resultado.artista}' - '{resultado.titulo}' "
                f"{'[ISRC: ' + resultado.isrc + ']' if resultado.isrc else ''} "
                f"| {ruta_archivo.name}"
            )
        else:
            self._cache.guardar_con_ttl(
                clave_cache,
                self._serializar_resultado(resultado),
                CACHE_TTL_NEGATIVE_SECONDS,
            )
            _log.debug(f"Shazam no identifico: {ruta_archivo.name}")

        return resultado

    # ------------------------------------------------------------------
    # CONSULTA ASYNC
    # ------------------------------------------------------------------

    async def _identificar_async(self, ruta: Path) -> ResultadoShazam:
        """Ejecuta la identificacion de forma asincrona con shazamio."""
        shazam = _ShazamLib()
        resultado = ResultadoShazam(disponible=True)

        try:
            respuesta = await shazam.recognize(str(ruta))
        except Exception as e:
            resultado.error = str(e)
            return resultado

        if not respuesta:
            return resultado

        track = respuesta.get("track")
        if not track:
            return resultado

        resultado.titulo = track.get("title", "").strip()
        resultado.artista = track.get("subtitle", "").strip()

        # ISRC — Shazam lo incluye en el campo "isrc" del track a veces
        isrc_raw = track.get("isrc", "")
        if not isrc_raw:
            # Intentar buscarlo en hub o en metadata interna
            hub = track.get("hub", {})
            for action in hub.get("actions", []):
                if action.get("type") == "applemusicplay":
                    # Apple Music a veces expone el ISRC en la URI
                    pass

        if isrc_raw:
            resultado.isrc = normalizar_isrc(isrc_raw)

        # Album y año desde sections
        for seccion in track.get("sections", []):
            if seccion.get("type") == "SONG":
                for meta in seccion.get("metadata", []):
                    titulo_meta = meta.get("title", "").lower()
                    texto_meta  = meta.get("text", "").strip()
                    if "album" in titulo_meta and texto_meta:
                        resultado.album = texto_meta
                    elif "released" in titulo_meta and texto_meta:
                        try:
                            resultado.anio = int(texto_meta[:4])
                        except (ValueError, TypeError):
                            pass
            elif seccion.get("type") == "LYRICS":
                pass  # No usamos letra

        resultado.identificado = bool(resultado.titulo or resultado.artista)
        return resultado

    # ------------------------------------------------------------------
    # SERIALIZACION PARA CACHE
    # ------------------------------------------------------------------

    @staticmethod
    def _serializar_resultado(r: ResultadoShazam) -> dict:
        return {
            "titulo":      r.titulo,
            "artista":     r.artista,
            "isrc":        r.isrc,
            "album":       r.album,
            "anio":        r.anio,
            "genero":      r.genero,
            "identificado": r.identificado,
        }

    @staticmethod
    def _deserializar_resultado(datos: dict) -> ResultadoShazam:
        return ResultadoShazam(
            titulo       = datos.get("titulo", ""),
            artista      = datos.get("artista", ""),
            isrc         = datos.get("isrc"),
            album        = datos.get("album"),
            anio         = datos.get("anio"),
            genero       = datos.get("genero"),
            identificado = datos.get("identificado", False),
            disponible   = True,
        )
