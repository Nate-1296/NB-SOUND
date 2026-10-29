# =============================================================================
# external/acoustid_client.py
#
# Cliente de identificacion acustica via AcoustID y Chromaprint.
#
# Funcionamiento:
#   1. fpcalc (binario de Chromaprint) genera un fingerprint del audio.
#   2. pyacoustid envia el fingerprint a la API de AcoustID.
#   3. AcoustID devuelve recording IDs de MusicBrainz con sus scores.
#
# Los recording IDs resultantes se usan como Strategy 0 en el cliente MB:
# en lugar de buscar por texto, buscamos directamente la grabacion por ID,
# lo que elimina casi toda la ambiguedad de titulos con variantes.
#
# El fingerprint se cachea por hash SHA256 del archivo para no recalcularlo
# en ejecuciones futuras (TTL separado y mayor que el de busquedas).
#
# Dependencias opcionales (el modulo degrada graciosamente si no estan):
#   pip install pyacoustid
#   apt install libchromaprint-tools   (o brew install chromaprint)
# =============================================================================

import os
import time
from pathlib import Path
from typing import Optional

from config.settings import (
    ACOUSTID_API_KEY_RESOLVED,
    ENABLE_ACOUSTID,
    CACHE_TTL_FINGERPRINT_SECONDS,
    ACOUSTID_MAX_RETRIES,
    ACOUSTID_BACKOFF_BASE,
    ACOUSTID_BACKOFF_FACTOR,
)
from domain.models import ResultadoAcoustID
from external.cache import CacheLocal
from infra.binarios import resolver_bin
from infra.logger import obtener_logger

_log = obtener_logger("acoustid_client")

# Prefijos de cache para separar fingerprints de resultados de busqueda
_PREFIJO_CACHE_FINGERPRINT = "acoustid_fp"
_PREFIJO_CACHE_RESULTADO   = "acoustid_res"

# Score minimo de AcoustID para considerar un resultado valido
_SCORE_MINIMO = 0.60

# Intentar importar pyacoustid de forma opcional
try:
    import acoustid
    _ACOUSTID_DISPONIBLE = True
except ImportError:
    _ACOUSTID_DISPONIBLE = False


def _fpcalc_disponible() -> bool:
    """Verifica si fpcalc esta disponible (embebido o en PATH del sistema).

    Cuando el binario esta embebido en el bundle, exporta su ruta absoluta
    via la variable de entorno ``FPCALC``, que ``pyacoustid`` consulta
    durante ``fingerprint_file(force_fpcalc=True)``.
    """
    ruta = resolver_bin("fpcalc")
    if not ruta:
        return False
    os.environ.setdefault("FPCALC", ruta)
    return True


# =============================================================================
# CLASE PRINCIPAL
# =============================================================================

class ClienteAcoustID:
    """
    Genera fingerprints acusticos y los consulta en AcoustID.

    Flujo de operacion:
      1. Verifica que todas las dependencias esten disponibles (pyacoustid,
         fpcalc, ACOUSTID_API_KEY). Si falta cualquiera, el modulo se
         desactiva y el pipeline continua sin identificacion acustica.
      2. Para cada archivo, intenta recuperar el resultado de cache antes
         de generar el fingerprint o contactar la API.
      3. El fingerprint (operacion costosa sobre el audio) se cachea con
         un TTL extendido separado del TTL de resultados de busqueda.
      4. Los recording IDs resultantes se pasan al ClienteMusicBrainz como
         Strategy 0b, que los usa para localizar el release correcto sin
         necesidad de busqueda por texto.

    Se instancia una vez por ejecucion del pipeline.
    """

    def __init__(self, cache: Optional[CacheLocal] = None) -> None:
        self._cache = cache or CacheLocal()

        # El modulo solo es funcional si TODAS las condiciones se cumplen:
        # libreria instalada, binario fpcalc en PATH y API key configurada.
        self._activo = (
            ENABLE_ACOUSTID
            and _ACOUSTID_DISPONIBLE
            and _fpcalc_disponible()
            and bool(ACOUSTID_API_KEY_RESOLVED)
        )

        if ENABLE_ACOUSTID and not self._activo:
            razones = []
            if not _ACOUSTID_DISPONIBLE:
                razones.append("pyacoustid no instalado (pip install pyacoustid)")
            if not _fpcalc_disponible():
                razones.append("fpcalc no encontrado (instala chromaprint)")
            if not ACOUSTID_API_KEY_RESOLVED:
                razones.append("ACOUSTID_API_KEY no configurada")
            _log.info(
                "Modulo AcoustID desactivado. "
                f"Razones: {'; '.join(razones)}"
            )
        elif self._activo:
            _log.info("Cliente AcoustID inicializado y activo.")

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
        hash_archivo: Optional[str] = None,
    ) -> ResultadoAcoustID:
        """
        Identifica una cancion por su fingerprint acustico.

        Primero consulta cache de resultados (TTL estandar). Si no hay hit,
        genera o recupera el fingerprint (TTL extendido) y lo envia a la API
        de AcoustID. El resultado, incluyendo listas vacias, se guarda en
        cache para no repetir consultas sobre archivos no identificables.

        Args:
            ruta_archivo:  Ruta al archivo MP3.
            hash_archivo:  Hash SHA256 del archivo para clave de cache.
                           Preferir sobre el nombre del archivo porque es
                           estable ante renombrados. Si es None, se usa
                           el nombre del archivo como fallback.

        Returns:
            ResultadoAcoustID con los recording IDs de MusicBrainz y sus
            scores de confianza. Si el modulo esta inactivo o hay error,
            retorna un resultado con listas vacias y disponible=False.
        """
        resultado = ResultadoAcoustID(disponible=self._activo)

        if not self._activo:
            return resultado

        clave_identificador = hash_archivo or ruta_archivo.name

        # Intentar cache de resultados primero (TTL normal de busqueda)
        clave_resultado = CacheLocal.construir_clave(
            _PREFIJO_CACHE_RESULTADO, {"id": clave_identificador}
        )
        datos_cacheados = self._cache.obtener(clave_resultado)
        if datos_cacheados is not None:
            _log.debug(f"AcoustID cache hit: {ruta_archivo.name}")
            return self._deserializar_resultado(datos_cacheados)

        # Generar o recuperar fingerprint
        fingerprint, duracion = self._obtener_fingerprint(
            ruta_archivo, clave_identificador
        )
        if not fingerprint:
            resultado.error = "No se pudo generar el fingerprint"
            return resultado

        resultado.fingerprint  = fingerprint
        resultado.duracion_seg = duracion

        # Consultar AcoustID
        recording_ids, scores = self._consultar_acoustid(fingerprint, duracion)
        resultado.recording_ids = recording_ids
        resultado.scores        = scores

        # Guardar resultado en cache
        self._cache.guardar(clave_resultado, self._serializar_resultado(resultado))

        _log.debug(
            f"AcoustID: {len(recording_ids)} resultados para {ruta_archivo.name} "
            f"(mejor score: {max(scores, default=0):.3f})"
        )

        return resultado

    # ------------------------------------------------------------------
    # FINGERPRINT
    # ------------------------------------------------------------------

    def _obtener_fingerprint(
        self,
        ruta: Path,
        clave_cache: str,
    ) -> tuple[str, Optional[float]]:
        """
        Obtiene el fingerprint Chromaprint del archivo.

        Usa cache con TTL extendido (CACHE_TTL_FINGERPRINT_SECONDS, tipicamente
        7 dias) para evitar recalcular el fingerprint en cada ejecucion del
        pipeline, ya que fpcalc puede tardar varios segundos sobre archivos
        grandes o en hardware lento.

        Side-effect: escribe el fingerprint en cache bajo _PREFIJO_CACHE_FINGERPRINT
        si se genero exitosamente.

        Returns:
            Tupla (fingerprint_string, duracion_en_segundos). Retorna ("", None)
            ante cualquier error, incluyendo archivos corruptos o formatos no
            soportados por la version de chromaprint instalada.
        """
        clave_fp = CacheLocal.construir_clave(
            _PREFIJO_CACHE_FINGERPRINT, {"id": clave_cache}
        )

        # Intentar cache de fingerprint (TTL extendido: 7 dias)
        datos_fp = self._cache.obtener_con_ttl(clave_fp, CACHE_TTL_FINGERPRINT_SECONDS)
        if datos_fp is not None and datos_fp.get("fingerprint"):
            _log.debug(f"Fingerprint desde cache: {ruta.name}")
            return datos_fp["fingerprint"], datos_fp.get("duracion")

        # Generar fingerprint con fpcalc via pyacoustid
        try:
            # v3.3: forzar force_fpcalc=True para evitar que pyacoustid intente
            # usar libchromaprint directamente (mas compatible entre plataformas)
            raw = acoustid.fingerprint_file(str(ruta), force_fpcalc=True)

            # acoustid.fingerprint_file puede retornar (duracion, fingerprint)
            # o solo fingerprint segun la version
            if isinstance(raw, tuple) and len(raw) == 2:
                duracion_fp, fingerprint = raw[0], raw[1]
            else:
                _log.warning(
                    f"Formato inesperado de fingerprint_file para {ruta.name}: {type(raw)}"
                )
                return "", None

            # acoustid puede retornar bytes o str segun version
            if isinstance(fingerprint, bytes):
                fingerprint = fingerprint.decode("ascii", errors="ignore")

            if not fingerprint:
                _log.warning(
                    f"fpcalc devolvio fingerprint vacio para {ruta.name}. "
                    "Verifica que el archivo MP3 no este corrupto o truncado."
                )
                return "", None

            self._cache.guardar_con_ttl(
                clave_fp,
                {"fingerprint": fingerprint, "duracion": duracion_fp},
                CACHE_TTL_FINGERPRINT_SECONDS,
            )
            return fingerprint, duracion_fp

        except acoustid.FingerprintGenerationError as e:
            # fpcalc no pudo decodificar el audio — archivo corrupto,
            # formato no soportado, o fpcalc incorrecto para la plataforma.
            _log.warning(
                f"No se pudo generar fingerprint para {ruta.name}: {e}. "
                "Posibles causas: archivo corrupto/truncado, codec no soportado "
                "por la version instalada de chromaprint, o fpcalc incorrecto "
                "para la arquitectura del sistema."
            )
            return "", None
        except acoustid.WebServiceError as e:
            _log.warning(f"Error de red AcoustID para {ruta.name}: {e}")
            return "", None
        except Exception as e:
            _log.warning(
                f"Error inesperado generando fingerprint de {ruta.name}: "
                f"{type(e).__name__}: {e}"
            )
            return "", None

    # ------------------------------------------------------------------
    # CONSULTA A ACOUSTID
    # ------------------------------------------------------------------

    def _consultar_acoustid(
        self,
        fingerprint: str,
        duracion: Optional[float],
    ) -> tuple[list[str], list[float]]:
        """
        Envia el fingerprint a la API de AcoustID y retorna recording IDs
        de MusicBrainz con sus scores de confianza.

        Estrategia de retry y fallback:
        - Intenta primero con meta='recordings', que permite usar
          parse_lookup_result() (camino recomendado por pyacoustid).
        - Si ese meta falla por razones de formato (no de red), reintenta
          con meta='recordingids' como alternativa.
        - Los errores de red (WebServiceError) se reintentan con backoff
          exponencial (ACOUSTID_BACKOFF_BASE * factor^intento).
        - Un fallo de red persistente cancela ambos metas para no bloquear
          el pipeline en situaciones de red caida.

        Filtra resultados con score menor a _SCORE_MINIMO (0.60) para
        evitar falsos positivos de baja confianza.

        Returns:
            Tupla (lista_recording_ids, lista_scores) — paralelas, mismo orden.
            Ambas listas estan vacias si no hay resultados por encima del umbral.
        """
        if not fingerprint or duracion is None:
            return [], []

        recording_ids: list[str] = []
        scores: list[float]       = []

        for meta_value in ("recordings", "recordingids"):
            # Reintentos ante WebServiceError (errores de red / DNS)
            for intento in range(ACOUSTID_MAX_RETRIES + 1):
                try:
                    resultados = acoustid.lookup(
                        ACOUSTID_API_KEY_RESOLVED,
                        fingerprint,
                        int(duracion),
                        meta=meta_value,
                    )

                    nuevos_ids, nuevos_scores = self._extraer_resultados_lookup(
                        resultados,
                        meta_value=meta_value,
                    )
                    for rid, score_float in zip(nuevos_ids, nuevos_scores):
                        if score_float < _SCORE_MINIMO:
                            continue
                        if rid and rid not in recording_ids:
                            recording_ids.append(rid)
                            scores.append(score_float)

                    break  # lookup completado (con o sin resultados) — salir del retry

                except acoustid.WebServiceError as e:
                    # Error de red / DNS — potencialmente transitorio
                    if intento < ACOUSTID_MAX_RETRIES:
                        pausa = ACOUSTID_BACKOFF_BASE * (ACOUSTID_BACKOFF_FACTOR ** intento)
                        _log.warning(
                            f"AcoustID error de red (meta={meta_value}, "
                            f"intento {intento + 1}/{ACOUSTID_MAX_RETRIES + 1}): {e}. "
                            f"Reintentando en {pausa:.1f}s..."
                        )
                        time.sleep(pausa)
                    else:
                        _log.warning(
                            f"AcoustID: fallo de red tras {ACOUSTID_MAX_RETRIES} reintentos "
                            f"(meta={meta_value}): {e}"
                        )
                        # Error de red persistente — no tiene sentido intentar otro meta
                        return recording_ids, scores

                except Exception as e:
                    # Error no relacionado con red (formato, versión de pyacoustid…)
                    _log.debug(
                        f"AcoustID lookup fallido con meta={meta_value}: "
                        f"{type(e).__name__}: {e}"
                    )
                    break  # Probar con el otro meta value

            if recording_ids:
                break  # Éxito con este meta — no probar el alternativo

        return recording_ids, scores

    @staticmethod
    def _extraer_resultados_lookup(
        resultados: object,
        meta_value: str,
    ) -> tuple[list[str], list[float]]:
        """
        Extrae (recording_ids, scores) desde la respuesta de acoustid.lookup.

        Maneja tres formatos posibles segun la version de pyacoustid y el
        meta solicitado:
          1. dict + meta='recordings': usa parse_lookup_result() (recomendado).
          2. dict + meta='recordingids': parseo manual del campo 'results'.
          3. list/tuple: formato legacy de versiones antiguas de pyacoustid.

        El fallback defensivo al formato legacy evita romper la integracion
        si se instala una version antigua de la libreria.

        Returns:
            Tupla (ids, scores) paralelas. Pueden estar vacias si la respuesta
            no contiene grabaciones reconocibles.
        """
        ids: list[str] = []
        scores: list[float] = []

        # Camino recomendado por pyacoustid para meta=recordings
        if isinstance(resultados, dict) and meta_value == "recordings":
            try:
                for item in acoustid.parse_lookup_result(resultados):
                    if not isinstance(item, (tuple, list)) or len(item) < 2:
                        continue
                    score = float(item[0])
                    rid = str(item[1]) if item[1] else ""
                    if rid:
                        ids.append(rid)
                        scores.append(score)
            except Exception:
                pass
            return ids, scores

        # Fallback JSON para meta=recordingids
        if isinstance(resultados, dict):
            for result in resultados.get("results", []) or []:
                score_raw = result.get("score")
                try:
                    score = float(score_raw) if score_raw is not None else 0.0
                except (TypeError, ValueError):
                    score = 0.0
                for rec in result.get("recordings", []) or []:
                    rid = str(rec.get("id", "")).strip()
                    if rid:
                        ids.append(rid)
                        scores.append(score)
            return ids, scores

        # Compatibilidad defensiva con formatos tuple/list legacy
        if isinstance(resultados, (list, tuple)):
            for item in resultados:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                try:
                    score = float(item[0])
                except (TypeError, ValueError):
                    continue
                rid = str(item[1]) if item[1] else ""
                if rid:
                    ids.append(rid)
                    scores.append(score)

        return ids, scores

    # ------------------------------------------------------------------
    # SERIALIZACION PARA CACHE
    # ------------------------------------------------------------------
    # El resultado se serializa a dict plano para almacenarse como JSON en
    # CacheLocal. La deserializacion reconstruye el dataclass sin pasar por
    # la logica de identificacion, marcando disponible=True siempre que
    # haya datos validos en cache.

    @staticmethod
    def _serializar_resultado(r: ResultadoAcoustID) -> dict:
        return {
            "recording_ids": r.recording_ids,
            "scores":        r.scores,
            "fingerprint":   r.fingerprint,
            "duracion_seg":  r.duracion_seg,
        }

    @staticmethod
    def _deserializar_resultado(datos: dict) -> ResultadoAcoustID:
        return ResultadoAcoustID(
            recording_ids = datos.get("recording_ids", []),
            scores        = datos.get("scores", []),
            fingerprint   = datos.get("fingerprint", ""),
            duracion_seg  = datos.get("duracion_seg"),
            disponible    = True,
        )
