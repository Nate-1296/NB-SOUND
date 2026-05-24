# =============================================================================
# external/musicbrainz_client.py
#
# Cliente para la API de MusicBrainz con estrategias de busqueda inteligente.
#
# Novedades v3 — integracion de fuentes externas:
#   - Strategy 0a: Busqueda por ISRC (cuando Shazam lo proporciona).
#     El ISRC identifica univocamente una grabacion. Si existe, saltamos
#     directamente al recording y evitamos toda la logica de texto.
#   - Strategy 0b: Busqueda por recording_id de AcoustID.
#     AcoustID ya nos da el recording_id de MusicBrainz. Solo necesitamos
#     obtener sus releases y seleccionar el mejor.
#   - Si estrategias 0a/0b producen resultados de alta calidad, las
#     estrategias de texto pueden omitirse para ahorrar consultas.
#   - Deduplicacion mejorada: un candidato encontrado por ISRC o AcoustID
#     tiene marcador de procedencia para que el matcher le asigne bonus.
# =============================================================================

import time
from typing import Optional

try:
    import musicbrainzngs as mb
    MB_DISPONIBLE = True
except ImportError:
    MB_DISPONIBLE = False

from config.settings import (
    MB_USER_AGENT_APP,
    MB_USER_AGENT_VERSION,
    MB_USER_AGENT_CONTACT,
    MB_SEARCH_LIMIT,
    MB_RATE_LIMIT_SECONDS,
    MB_MAX_RETRIES,
    MB_BACKOFF_FACTOR,
    MB_BACKOFF_BASE,
    MB_REQUEST_TIMEOUT,
    ACCEPTED_RELEASE_TYPES,
    PENALIZED_RELEASE_TYPES,
    RELEASE_TYPE_PRIORITY,
    MB_MAX_RELEASES_PER_RECORDING,
    MIN_RESULTS_PER_STRATEGY,
    MAX_CANDIDATES_PER_FILE,
    CACHE_TTL_NEGATIVE_SECONDS,
)
from domain.models import CandidatoMB, MetadataNormalizada
from external.cache import CacheLocal
from infra.logger import obtener_logger
from utils.text import limpiar_version_titulo, separar_artista_principal, para_comparacion

_log = obtener_logger("mb_client")

_PREFIJO_CACHE_RECORDING = "mb_rec"
_PREFIJO_CACHE_RELEASE   = "mb_rel"
_PREFIJO_CACHE_ISRC      = "mb_isrc"

_TIPOS_SECUNDARIOS_PENALIZADOS = {
    "Live", "Remix", "Compilation", "DJ-mix",
    "Mixtape/Street", "Demo", "Interview",
}

# Numero minimo de candidatos de calidad antes de omitir estrategias de texto
_UMBRAL_CANDIDATOS_SUFICIENTES = 3


def _extraer_status_http(error: Exception) -> Optional[int]:
    for attr in ("status", "status_code", "code"):
        valor = getattr(error, attr, None)
        if isinstance(valor, int):
            return valor
        if isinstance(valor, str) and valor.isdigit():
            return int(valor)
    causa = getattr(error, "cause", None)
    for attr in ("code", "status", "status_code"):
        valor = getattr(causa, attr, None)
        if isinstance(valor, int):
            return valor
        if isinstance(valor, str) and valor.isdigit():
            return int(valor)
    texto = str(error)
    for token in ("404", "429", "500", "502", "503", "504"):
        if token in texto:
            return int(token)
    return None


def _clasificar_error_mb(error: Exception) -> tuple[bool, bool, str]:
    """
    Retorna (reintentar, cachear_negativo, categoria).
    """
    status = _extraer_status_http(error)
    mensaje = str(error).lower()

    if status == 404:
        return False, True, "not_found"
    if status == 429:
        return True, False, "rate_limited"
    if status is not None and 500 <= status <= 599:
        return True, False, "server_error"
    if "timeout" in mensaje or "timed out" in mensaje:
        return True, False, "timeout"
    if any(k in mensaje for k in ("connection", "dns", "temporar", "network")):
        return True, False, "network_error"
    return False, False, "unknown_error"


def _normalizar_tipos_secundarios_mb(raw_list: list) -> list[str]:
    """
    MusicBrainz puede devolver secondary-type-list como:
      - lista de strings (formato más común), o
      - lista de dicts (variantes antiguas/normalizadas por wrappers).
    Esta función unifica ambos formatos.
    """
    tipos: list[str] = []
    for item in raw_list or []:
        if isinstance(item, str):
            valor = item.strip()
        elif isinstance(item, dict):
            valor = str(item.get("secondary-type", "")).strip()
        else:
            valor = ""
        if valor:
            tipos.append(valor)
    return tipos


# =============================================================================
# CLASE PRINCIPAL
# =============================================================================

class ClienteMusicBrainz:
    """
    Cliente de MusicBrainz con multi-estrategia, seleccion inteligente de
    release y cache. Una instancia por ejecucion del pipeline es suficiente.
    """

    def __init__(self, cache: Optional[CacheLocal] = None) -> None:
        self._cache = cache or CacheLocal()
        self._ultimo_request_ts: float = 0.0
        self._total_consultas:   int   = 0
        self._total_reintentos:  int   = 0

        if not MB_DISPONIBLE:
            _log.error(
                "musicbrainzngs no esta instalado. "
                "Instalar con: pip install musicbrainzngs"
            )
            return

        mb.set_useragent(
            MB_USER_AGENT_APP,
            MB_USER_AGENT_VERSION,
            MB_USER_AGENT_CONTACT,
        )
        mb.set_rate_limit(limit_or_interval=MB_RATE_LIMIT_SECONDS, new_requests=1)
        _log.info("Cliente MusicBrainz inicializado (v3: multi-estrategia + ISRC + AcoustID).")

    # ------------------------------------------------------------------
    # API PUBLICA
    # ------------------------------------------------------------------

    def buscar_candidatos(
        self,
        norm: MetadataNormalizada,
        recording_ids_acoustid: Optional[list[str]] = None,
    ) -> list[CandidatoMB]:
        """
        Busca grabaciones en MusicBrainz usando multiples estrategias.

        Orden de estrategias:
          0a. ISRC exacto (si norm.isrc disponible) — maxima precision
          0b. recording_ids de AcoustID (si disponibles) — muy alta precision
          1.  Artista + titulo completo
          2.  Artista + titulo sin anotaciones de version
          3.  Artista sin featuring + titulo
          4.  Solo titulo como ultimo recurso

        Retorna lista deduplicada de candidatos con el mejor release seleccionado.
        """
        if not MB_DISPONIBLE:
            return []

        if not norm.artista_principal and not norm.titulo and not norm.isrc:
            _log.debug("Sin datos para buscar en MB")
            return []

        # Clave de cache: incluye ISRC si existe
        clave_cache = CacheLocal.construir_clave(_PREFIJO_CACHE_RECORDING, {
            "artista": norm.artista_para_match,
            "titulo":  norm.titulo_para_match,
            "isrc":    norm.isrc or "",
        })

        datos_cacheados = self._cache.obtener(clave_cache)
        if datos_cacheados is not None:
            _log.debug(
                f"Cache hit MB: '{norm.artista_principal}' - '{norm.titulo}'"
            )
            return self._deserializar_candidatos(datos_cacheados)

        candidatos = self._buscar_multiestrategia(
            norm, recording_ids_acoustid or []
        )

        self._cache.guardar(clave_cache, self._serializar_candidatos(candidatos))
        self._total_consultas += 1

        _log.debug(
            f"MB: {len(candidatos)} candidatos para "
            f"'{norm.artista_principal}' - '{norm.titulo}'"
        )
        return candidatos

    def obtener_detalle_release(self, release_id: str) -> Optional[dict]:
        """Obtiene el detalle completo de un release por ID (con cache)."""
        if not MB_DISPONIBLE or not release_id:
            return None

        clave_cache = CacheLocal.construir_clave(
            _PREFIJO_CACHE_RELEASE, {"id": release_id}
        )
        datos_cacheados = self._cache.obtener(clave_cache)
        if datos_cacheados is not None:
            return datos_cacheados

        self._respetar_rate_limit()
        try:
            resultado = mb.get_release_by_id(
                release_id,
                includes=["artists", "recordings", "release-groups", "media"]
            )
            detalle = resultado.get("release", {})
            self._cache.guardar(clave_cache, detalle)
            self._total_consultas += 1
            return detalle
        except Exception as e:
            _log.warning(f"Error al obtener detalle de release {release_id}: {e}")
            return None

    @property
    def estadisticas(self) -> dict:
        return {
            "total_consultas":  self._total_consultas,
            "total_reintentos": self._total_reintentos,
            **self._cache.estadisticas,
        }

    # ------------------------------------------------------------------
    # MULTI-ESTRATEGIA
    # ------------------------------------------------------------------

    def _buscar_multiestrategia(
        self,
        norm: MetadataNormalizada,
        recording_ids_acoustid: list[str],
    ) -> list[CandidatoMB]:
        """
        Ejecuta hasta 6 estrategias de busqueda, deteniendose cuando
        acumula suficientes candidatos de calidad.
        """
        pool: dict[str, CandidatoMB] = {}  # keyed by recording_id
        consultas_texto_realizadas: set[tuple[str, str]] = set()

        # --- Strategy 0a: ISRC exacto ---
        if norm.isrc:
            candidatos_isrc = self._buscar_por_isrc(norm.isrc)
            self._merge_pool(pool, candidatos_isrc, marca_acoustid=False)
            _log.debug(f"Strategy 0a (ISRC {norm.isrc}): {len(candidatos_isrc)} resultados")

        # --- Strategy 0b: Recording IDs de AcoustID ---
        if recording_ids_acoustid and len(pool) < _UMBRAL_CANDIDATOS_SUFICIENTES:
            for rid in recording_ids_acoustid[:3]:
                candidatos_rid = self._buscar_por_recording_id(rid)
                self._merge_pool(pool, candidatos_rid, marca_acoustid=True)
            _log.debug(
                f"Strategy 0b (AcoustID recording_ids): {len(pool)} en pool"
            )

        # Si ya tenemos suficientes candidatos de calidad desde fuentes directas,
        # podemos saltarnos las busquedas de texto (ahorra consultas a MB).
        if len(pool) >= _UMBRAL_CANDIDATOS_SUFICIENTES:
            _log.debug(
                f"Suficientes candidatos desde fuentes directas ({len(pool)}), "
                "omitiendo estrategias de texto."
            )
            candidatos = list(pool.values())
            candidatos.sort(key=lambda c: c.puntaje_total, reverse=True)
            return candidatos[:MAX_CANDIDATES_PER_FILE]

        artista       = norm.artista_principal or ""
        titulo        = norm.titulo or ""
        titulo_limpio = limpiar_version_titulo(titulo)
        artista_sin_feat = separar_artista_principal(artista)[0] if norm.featuring else artista

        # v3.3: detectar si el titulo indica una variante para afinar estrategias
        from utils.text import detectar_tipo_variante, parsear_variante_titulo
        variante_local = detectar_tipo_variante(titulo)
        titulo_base_sin_variante, _ = parsear_variante_titulo(titulo_limpio or titulo)

        # --- Strategy 1: artista + titulo completo ---
        if artista and titulo:
            resultados = self._ejecutar_busqueda(
                artista=artista, titulo=titulo, consultas_realizadas=consultas_texto_realizadas
            )
            self._merge_pool(pool, resultados)
            _log.debug(f"Strategy 1 (artista+titulo): {len(resultados)} resultados")

        # --- Strategy 2: artista + titulo sin version ---
        if (titulo_limpio and titulo_limpio != titulo
                and len(pool) < MIN_RESULTS_PER_STRATEGY):
            resultados = self._ejecutar_busqueda(
                artista=artista,
                titulo=titulo_limpio,
                consultas_realizadas=consultas_texto_realizadas,
            )
            self._merge_pool(pool, resultados)
            _log.debug(f"Strategy 2 (sin version): {len(resultados)} resultados")

        # --- Strategy 3: artista sin feat + titulo ---
        if (norm.featuring
                and artista_sin_feat != artista
                and len(pool) < MIN_RESULTS_PER_STRATEGY):
            resultados = self._ejecutar_busqueda(
                artista=artista_sin_feat,
                titulo=titulo_limpio or titulo,
                consultas_realizadas=consultas_texto_realizadas,
            )
            self._merge_pool(pool, resultados)
            _log.debug(f"Strategy 3 (sin feat): {len(resultados)} resultados")

        # --- Strategy 4 (v3.3): artista + titulo base sin variante ---
        # Para tracks como "Song (Remix)" buscar "Song" sin el sufijo de variante
        # ya que MB puede tener el recording como "Song" con release type "Remix"
        if (variante_local is not None
                and titulo_base_sin_variante
                and titulo_base_sin_variante != titulo_limpio
                and len(pool) < MIN_RESULTS_PER_STRATEGY):
            resultados = self._ejecutar_busqueda(
                artista=artista_sin_feat or artista,
                titulo=titulo_base_sin_variante,
                consultas_realizadas=consultas_texto_realizadas,
            )
            self._merge_pool(pool, resultados)
            _log.debug(
                f"Strategy 4 (titulo base sin variante '{variante_local}'): "
                f"{len(resultados)} resultados"
            )

        # --- Strategy 5: solo titulo como ultimo recurso ---
        if titulo and len(pool) == 0:
            resultados = self._ejecutar_busqueda(
                titulo=titulo_limpio or titulo,
                consultas_realizadas=consultas_texto_realizadas,
            )
            self._merge_pool(pool, resultados)
            _log.debug(f"Strategy 5 (solo titulo): {len(resultados)} resultados")

        candidatos = list(pool.values())

        # v3.3: re-ranking por duracion cuando hay candidatos con duracion conocida
        # y la metadata local tiene duracion. Esto mejora la seleccion cuando
        # hay multiples versiones de la misma grabacion con distinta duracion.
        if norm.duracion_seg and len(candidatos) > 1:
            candidatos = self._reordenar_por_duracion(candidatos, norm.duracion_seg)
        else:
            candidatos.sort(key=lambda c: c.puntaje_total, reverse=True)

        return candidatos[:MAX_CANDIDATES_PER_FILE]

    def _reordenar_por_duracion(
        self,
        candidatos: list[CandidatoMB],
        duracion_local: float,
    ) -> list[CandidatoMB]:
        """
        v3.3: Re-ordena candidatos usando la duracion como factor de desempate
        secundario cuando el puntaje_total de los top candidatos es similar.
        Solo modifica el orden cuando la diferencia de puntaje es menor que
        un umbral, evitando que la duracion supere a evidencias mas fuertes.
        """
        if not candidatos:
            return candidatos

        UMBRAL_DURACION_DESEMPATE = 0.05  # Solo aplica si scores muy cercanos

        def score_con_duracion(c: CandidatoMB) -> tuple[float, float]:
            puntaje = c.puntaje_total
            if c.duracion_seg is not None:
                diff = abs(c.duracion_seg - duracion_local)
                # Bonus de duracion: maxima precision hasta 3s, decae hasta 30s
                if diff <= 3:
                    bonus_dur = 0.001   # Minimo para desempatar
                elif diff <= 10:
                    bonus_dur = 0.001 * max(0, 1 - (diff - 3) / 7)
                else:
                    bonus_dur = 0.0
            else:
                bonus_dur = 0.0
            return (round(puntaje, 3), bonus_dur)

        top_puntaje = candidatos[0].puntaje_total if candidatos else 0.0
        # Solo aplicar re-ranking si hay candidatos dentro del umbral de desempate
        hay_empate = any(
            abs(c.puntaje_total - top_puntaje) <= UMBRAL_DURACION_DESEMPATE
            for c in candidatos[1:]
        )

        if hay_empate:
            candidatos.sort(key=lambda c: score_con_duracion(c), reverse=True)
        else:
            candidatos.sort(key=lambda c: c.puntaje_total, reverse=True)

        return candidatos

    # ------------------------------------------------------------------
    # BUSQUEDA POR ISRC
    # ------------------------------------------------------------------

    def _buscar_por_isrc(self, isrc: str) -> list[CandidatoMB]:
        """
        Busca grabaciones en MB por codigo ISRC.
        El ISRC identifica univocamente una grabacion, por lo que el resultado
        tiene maxima precision. Un candidato encontrado por ISRC recibe
        el bonus BONUS_ISRC_EXACTO en el matcher.
        """
        clave_cache = CacheLocal.construir_clave(_PREFIJO_CACHE_ISRC, {"isrc": isrc})
        datos_cacheados = self._cache.obtener(clave_cache)
        if datos_cacheados is not None:
            return self._deserializar_candidatos(datos_cacheados)

        # Reintentos con clasificacion de error: 404 no reintenta.
        resultado = None
        for intento in range(MB_MAX_RETRIES + 1):
            self._respetar_rate_limit()
            try:
                resultado = mb.get_recordings_by_isrc(
                    isrc,
                    includes=["artists", "releases", "isrcs"],
                )
                break  # éxito
            except Exception as e:
                reintentar, cachear_negativo, categoria = _clasificar_error_mb(e)
                if cachear_negativo:
                    _log.info(
                        f"ISRC {isrc}: no existe en MusicBrainz ({categoria}); "
                        "se guarda cache negativo sin reintentos."
                    )
                    self._cache.guardar_con_ttl(
                        clave_cache, self._serializar_candidatos([]), CACHE_TTL_NEGATIVE_SECONDS
                    )
                    return []
                if reintentar and intento < MB_MAX_RETRIES:
                    _log.warning(
                        f"Error buscando ISRC {isrc} "
                        f"(intento {intento + 1}/{MB_MAX_RETRIES + 1}, {categoria}): {e}"
                    )
                    pausa = MB_BACKOFF_BASE * (MB_BACKOFF_FACTOR ** intento)
                    _log.debug(f"Pausa {pausa:.1f}s antes de reintento ISRC lookup...")
                    time.sleep(pausa)
                    self._total_reintentos += 1
                else:
                    _log.error(f"ISRC {isrc}: fallo no recuperable ({categoria}): {e}")
                    return []

        if resultado is None:
            return []

        grabaciones = resultado.get("isrc", {}).get("recording-list", [])
        candidatos: list[CandidatoMB] = []

        for grabacion in grabaciones[:MB_SEARCH_LIMIT]:
            try:
                candidato = self._grabacion_a_candidato(grabacion)
                if candidato:
                    # Marcar que vino de ISRC exacto para el bonus en el matcher
                    candidato.isrc = isrc
                    candidatos.append(candidato)
            except Exception as e:
                _log.debug(f"Error procesando grabacion ISRC: {e}")

        if candidatos:
            self._cache.guardar(clave_cache, self._serializar_candidatos(candidatos))
        else:
            self._cache.guardar_con_ttl(
                clave_cache, self._serializar_candidatos([]), CACHE_TTL_NEGATIVE_SECONDS
            )
        self._total_consultas += 1
        return candidatos

    # ------------------------------------------------------------------
    # BUSQUEDA POR RECORDING ID (AcoustID)
    # ------------------------------------------------------------------

    def _buscar_por_recording_id(self, recording_id: str) -> list[CandidatoMB]:
        """
        Obtiene los datos completos de una grabacion directamente por su ID.
        Usado cuando AcoustID ya nos proporciono el recording_id de MB.
        """
        clave_cache = CacheLocal.construir_clave(
            _PREFIJO_CACHE_RECORDING, {"rid": recording_id}
        )
        datos_cacheados = self._cache.obtener(clave_cache)
        if datos_cacheados is not None:
            return self._deserializar_candidatos(datos_cacheados)

        # NOTA v3.4: "release-groups" NO es un include válido para
        # get_recording_by_id (genera "Bad includes" en la API). Los datos de
        # release-group vienen embebidos dentro de cada release al solicitar
        # "releases". Sólo se usan: artists, releases, isrcs.
        resultado = None
        for intento in range(MB_MAX_RETRIES + 1):
            self._respetar_rate_limit()
            try:
                resultado = mb.get_recording_by_id(
                    recording_id,
                    includes=["artists", "releases", "isrcs"],
                )
                break  # éxito
            except Exception as e:
                reintentar, cachear_negativo, categoria = _clasificar_error_mb(e)
                if cachear_negativo:
                    _log.info(
                        f"Recording {recording_id}: no existe en MusicBrainz ({categoria}); "
                        "se guarda cache negativo sin reintentos."
                    )
                    self._cache.guardar_con_ttl(
                        clave_cache, self._serializar_candidatos([]), CACHE_TTL_NEGATIVE_SECONDS
                    )
                    return []
                if reintentar and intento < MB_MAX_RETRIES:
                    _log.warning(
                        f"Error obteniendo recording {recording_id} "
                        f"(intento {intento + 1}/{MB_MAX_RETRIES + 1}, {categoria}): {e}"
                    )
                    pausa = MB_BACKOFF_BASE * (MB_BACKOFF_FACTOR ** intento)
                    _log.debug(f"Pausa {pausa:.1f}s antes de reintento recording lookup...")
                    time.sleep(pausa)
                    self._total_reintentos += 1
                else:
                    _log.error(f"Recording {recording_id}: fallo no recuperable ({categoria}): {e}")
                    return []

        if resultado is None:
            return []

        grabacion = resultado.get("recording", {})
        if not grabacion:
            return []

        try:
            candidato = self._grabacion_a_candidato(grabacion)
            if candidato:
                candidato.procedencia_acoustid = True
                candidatos = [candidato]
            else:
                candidatos = []
        except Exception as e:
            _log.debug(f"Error procesando recording {recording_id}: {e}")
            candidatos = []

        if candidatos:
            self._cache.guardar(clave_cache, self._serializar_candidatos(candidatos))
        else:
            self._cache.guardar_con_ttl(
                clave_cache, self._serializar_candidatos([]), CACHE_TTL_NEGATIVE_SECONDS
            )
        self._total_consultas += 1
        return candidatos

    # ------------------------------------------------------------------
    # CONSTRUCCION DE QUERY Y BUSQUEDA DE TEXTO
    # ------------------------------------------------------------------

    def _ejecutar_busqueda(
        self,
        artista: str = "",
        titulo:  str = "",
        consultas_realizadas: Optional[set[tuple[str, str]]] = None,
    ) -> list[CandidatoMB]:
        """Construye la query de texto y la ejecuta con reintentos."""
        artista_key = para_comparacion(artista)
        titulo_key = para_comparacion(titulo)
        if consultas_realizadas is not None:
            firma = (artista_key, titulo_key)
            if firma in consultas_realizadas:
                _log.debug(
                    f"Evitando consulta MB duplicada: artista='{artista_key}' titulo='{titulo_key}'"
                )
                return []
            consultas_realizadas.add(firma)

        partes = []
        if artista:
            partes.append(f'artist:"{self._escapar_lucene(artista)}"')
        if titulo:
            partes.append(f'recording:"{self._escapar_lucene(titulo)}"')

        if not partes:
            return []

        query = " AND ".join(partes)
        resultados_brutos = self._buscar_con_reintentos(query)
        if resultados_brutos is None:
            return []

        return self._procesar_resultados(resultados_brutos)

    def _merge_pool(
        self,
        pool: dict[str, CandidatoMB],
        nuevos: list[CandidatoMB],
        marca_acoustid: bool = False,
    ) -> None:
        """
        Agrega candidatos al pool deduplicando por recording_id.
        Si ya existe, conserva el que tiene mejor release.
        """
        for candidato in nuevos:
            if not candidato.recording_id:
                continue
            if marca_acoustid:
                candidato.procedencia_acoustid = True
            rid = candidato.recording_id
            if rid not in pool:
                pool[rid] = candidato
            else:
                existente = pool[rid]
                # Comparar candidatos por puntaje_total (ambos son CandidatoMB,
                # no dicts; _score_release_quality espera un dict de release).
                if candidato.puntaje_total > existente.puntaje_total:
                    # Preservar flags de procedencia
                    candidato.procedencia_acoustid = (
                        candidato.procedencia_acoustid
                        or existente.procedencia_acoustid
                    )
                    pool[rid] = candidato

    @staticmethod
    def _escapar_lucene(texto: str) -> str:
        """Escapa caracteres especiales de Lucene para queries MB."""
        caracteres_especiales = r'+-&|!(){}[]^"~*?:\/'
        return "".join(
            f"\\{c}" if c in caracteres_especiales else c
            for c in texto
        )

    # ------------------------------------------------------------------
    # CONSULTA CON REINTENTOS
    # ------------------------------------------------------------------

    def _buscar_con_reintentos(self, query: str) -> Optional[dict]:
        for intento in range(MB_MAX_RETRIES + 1):
            try:
                self._respetar_rate_limit()
                resultado = mb.search_recordings(
                    query=query,
                    limit=MB_SEARCH_LIMIT,
                )
                return resultado
            except Exception as e:
                reintentar, _, categoria = _clasificar_error_mb(e)
                if reintentar and intento < MB_MAX_RETRIES:
                    _log.warning(
                        f"Error MB (intento {intento + 1}/{MB_MAX_RETRIES + 1}, {categoria}): {e}"
                    )
                else:
                    _log.warning(f"Error MB no recuperable ({categoria}): {e}")
            if reintentar and intento < MB_MAX_RETRIES:
                pausa = MB_BACKOFF_BASE * (MB_BACKOFF_FACTOR ** intento)
                _log.debug(f"Pausa de {pausa:.1f}s antes de reintento...")
                time.sleep(pausa)
                self._total_reintentos += 1
            elif not reintentar:
                break

        _log.error("Busqueda MB fallida (error permanente o limite de reintentos)")
        return None

    def _respetar_rate_limit(self) -> None:
        ahora = time.time()
        transcurrido = ahora - self._ultimo_request_ts
        if transcurrido < MB_RATE_LIMIT_SECONDS:
            time.sleep(MB_RATE_LIMIT_SECONDS - transcurrido)
        self._ultimo_request_ts = time.time()

    # ------------------------------------------------------------------
    # PROCESAMIENTO DE RESULTADOS
    # ------------------------------------------------------------------

    def _procesar_resultados(self, resultados: dict) -> list[CandidatoMB]:
        grabaciones = resultados.get("recording-list", [])
        candidatos: list[CandidatoMB] = []

        for grabacion in grabaciones[:MB_SEARCH_LIMIT]:
            try:
                candidato = self._grabacion_a_candidato(grabacion)
                if candidato is not None:
                    candidatos.append(candidato)
            except Exception as e:
                _log.debug(f"Error procesando grabacion MB: {e}")
                continue

        return candidatos

    def _grabacion_a_candidato(self, grabacion: dict) -> Optional[CandidatoMB]:
        """
        Convierte un resultado de grabacion de MB en un CandidatoMB,
        seleccionando el MEJOR release disponible.
        """
        candidato = CandidatoMB()
        candidato.recording_id   = grabacion.get("id", "")
        candidato.titulo_oficial = grabacion.get("title", "")

        # Duracion en milisegundos -> segundos
        duracion_ms = grabacion.get("length")
        if duracion_ms:
            try:
                candidato.duracion_seg = int(duracion_ms) / 1000.0
            except (ValueError, TypeError):
                pass

        # ISRC de la grabacion (si MB lo tiene)
        isrc_list = grabacion.get("isrc-list", [])
        if isrc_list:
            candidato.isrc = isrc_list[0]

        # Artistas
        artistas = grabacion.get("artist-credit", [])
        if artistas:
            candidato.artista_principal = self._extraer_artista_credito(artistas)
            candidato.artistas_credito  = self._extraer_todos_artistas(artistas)

        # Seleccionar el MEJOR release
        releases = grabacion.get("release-list", [])
        if not releases:
            return None

        mejor_release = self._seleccionar_mejor_release(releases)
        if mejor_release is None:
            return None

        self._poblar_desde_release(candidato, mejor_release)
        return candidato

    def _seleccionar_mejor_release(self, releases: list[dict]) -> Optional[dict]:
        """
        Evalua todos los releases disponibles y devuelve el mas adecuado:
          1. Preferir releases con status "Official"
          2. Tipo: Album > EP > Single > Other
          3. Sin tipos secundarios penalizados (Compilation, Live, Remix)
          4. Release mas antiguo (el original, no una reedicion)
        """
        if not releases:
            return None

        releases_evaluados = releases[:MB_MAX_RELEASES_PER_RECORDING]
        mejor_score   = -1
        mejor_release = None

        for release in releases_evaluados:
            score = self._score_release_quality(release)
            if score > mejor_score:
                mejor_score   = score
                mejor_release = release

        return mejor_release

    def _score_release_quality(self, release: dict) -> int:
        """Calcula un score de calidad para un release. Mayor = mejor."""
        score = 0

        # Criterio 1: Status oficial
        status = release.get("status", "")
        if status == "Official":
            score += 1000
        elif status == "Promotion":
            score += 100

        # Criterio 2: Tipo de release-group
        rg_raw = release.get("release-group", {})
        # MB a veces devuelve el release-group como str (solo el ID) en vez de dict
        rg = rg_raw if isinstance(rg_raw, dict) else {}
        tipo_primario_raw = rg.get("primary-type", "") or ""
        # Normalizar antes del lookup para no perder puntuación por variantes de case
        _ALIASES_SCORE = {
            "album": "Album", "single": "Single", "ep": "EP",
            "other": "Other", "broadcast": "Other",
        }
        tipo_primario = _ALIASES_SCORE.get(tipo_primario_raw.lower(), tipo_primario_raw)
        score += RELEASE_TYPE_PRIORITY.get(tipo_primario, 5)

        # Criterio 3: Penalizacion por tipos secundarios
        secundarios = _normalizar_tipos_secundarios_mb(
            rg.get("secondary-type-list", [])
        )
        for tipo_sec in secundarios:
            if tipo_sec in _TIPOS_SECUNDARIOS_PENALIZADOS:
                score -= 200

        # Criterio 4: Año (mas antiguo = posiblemente original)
        fecha = release.get("date", "") or rg.get("first-release-date", "")
        if fecha:
            try:
                anio = int(str(fecha)[:4])
                score += max(0, (2030 - anio))
            except (ValueError, TypeError):
                pass

        return score

    def _poblar_desde_release(self, candidato: CandidatoMB, release: dict) -> None:
        """Rellena los campos del candidato con los datos del release elegido."""
        candidato.release_id     = release.get("id", "")
        candidato.album_oficial  = release.get("title", "")
        candidato.status_release = release.get("status", "")
        candidato.es_oficial     = candidato.status_release == "Official"

        # Track number
        medium_list = release.get("medium-list", [])
        if medium_list:
            track_info = self._extraer_track_info(medium_list, candidato.recording_id)
            if track_info:
                candidato.track_number = track_info[0]
                candidato.track_total  = track_info[1]

        # Tipo y tipos secundarios del release-group
        rg_raw = release.get("release-group", {})
        # MB a veces devuelve release-group como str (solo el ID) — proteger
        rg = rg_raw if isinstance(rg_raw, dict) else {}
        candidato.release_group_id = rg.get("id", "")

        # primary-type: MB puede enviarlo como campo directo del rg o ausente
        tipo_primario = rg.get("primary-type", "") or rg.get("type", "") or ""
        # Normalizar aliases conocidos que MB devuelve inconsistentemente.
        # Se aplica siempre (no solo para tipos desconocidos) para cubrir
        # variantes en minúsculas/mayúsculas que MB envía a veces.
        _ALIASES_TIPO = {
            "album":           "Album",
            "single":          "Single",
            "ep":              "EP",
            "other":           "Other",
            "broadcast":       "Other",   # Broadcast → Other (penalizado)
            "compilation":     "Compilation",
            "live":            "Live",
            "remix":           "Remix",
            "dj-mix":          "DJ-mix",
            "mixtape/street":  "Mixtape/Street",
            "soundtrack":      "Soundtrack",
            "audiobook":       "Audiobook",
            "interview":       "Interview",
            "spoken word":     "Spoken Word",
        }
        if tipo_primario:
            tipo_primario = _ALIASES_TIPO.get(tipo_primario.lower(), tipo_primario)

        tipos_secundarios = _normalizar_tipos_secundarios_mb(
            rg.get("secondary-type-list", [])
        )

        candidato.tipo_release    = tipo_primario
        candidato.tipos_secundarios = tipos_secundarios
        candidato.es_compilacion  = "Compilation" in tipos_secundarios

        for tipo_sec in tipos_secundarios:
            if tipo_sec in _TIPOS_SECUNDARIOS_PENALIZADOS:
                candidato.penalizaciones.append(f"tipo_secundario:{tipo_sec}")

        # Año del release
        fecha = release.get("date", "") or rg.get("first-release-date", "")
        if fecha:
            try:
                candidato.anio_release = int(str(fecha)[:4])
            except (ValueError, TypeError):
                pass

    # ------------------------------------------------------------------
    # EXTRACCION DE DATOS
    # ------------------------------------------------------------------

    @staticmethod
    def _extraer_artista_credito(artistas: list) -> str:
        for item in artistas:
            if isinstance(item, dict) and "artist" in item:
                return item["artist"].get("name", "")
        return ""

    @staticmethod
    def _extraer_todos_artistas(artistas: list) -> list[str]:
        nombres = []
        for item in artistas:
            if isinstance(item, dict) and "artist" in item:
                nombre = item["artist"].get("name", "")
                if nombre:
                    nombres.append(nombre)
        return nombres

    @staticmethod
    def _extraer_track_info(
        medium_list: list, recording_id: str
    ) -> Optional[tuple[int, int]]:
        for medio in medium_list:
            track_list = medio.get("track-list", [])
            total = int(medio.get("track-count", len(track_list)))
            for track in track_list:
                rec = track.get("recording", {})
                if rec.get("id") == recording_id:
                    try:
                        numero = int(track.get("number", track.get("position", 0)))
                        return (numero, total)
                    except (ValueError, TypeError):
                        pass
        return None

    # ------------------------------------------------------------------
    # SERIALIZACION PARA CACHE
    # ------------------------------------------------------------------

    @staticmethod
    def _serializar_candidatos(candidatos: list[CandidatoMB]) -> list[dict]:
        from dataclasses import asdict
        return [asdict(c) for c in candidatos]

    @staticmethod
    def _deserializar_candidatos(datos: list[dict]) -> list[CandidatoMB]:
        candidatos = []
        for d in datos:
            try:
                c = CandidatoMB(**d)
                candidatos.append(c)
            except Exception:
                continue
        return candidatos
