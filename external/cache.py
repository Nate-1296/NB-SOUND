# =============================================================================
# external/cache.py
#
# Cache local para respuestas de consultas externas. Almacena resultados
# de busquedas en MusicBrainz, fingerprints y resultados de Shazam como
# archivos JSON individuales para evitar peticiones repetidas.
#
# La clave de cache es un hash determinista de los parametros de la query.
# Las entradas expiran segun el TTL configurado en settings.
#
# Novedades v3:
#   - obtener_con_ttl() / guardar_con_ttl(): permiten especificar un TTL
#     diferente al predeterminado, usado para fingerprints (TTL extendido).
#   - Subcarpeta separada por tipo de dato para mejor organizacion.
# =============================================================================

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Optional

from config import settings as _settings
from config.settings import CACHE_TTL_SECONDS, CACHE_FILE_EXTENSION
from infra.logger import obtener_logger

_log = obtener_logger("cache")

_SUBCARPETA_MB        = "musicbrainz"
_SUBCARPETA_SHAZAM    = "shazam"
_SUBCARPETA_ACOUSTID  = "acoustid"
_SUBCARPETA_GENERAL   = "general"


# =============================================================================
# CLASE PRINCIPAL
# =============================================================================

class CacheLocal:
    """
    Cache de archivos JSON para respuestas de APIs externas.

    Cada entrada se escribe como un archivo JSON independiente bajo una
    subcarpeta determinada por el prefijo logico de la clave (musicbrainz/,
    shazam/, acoustid/, general/). La clave de cada archivo es un hash MD5
    del prefijo y los parametros de la query, construido con construir_clave().

    Cada entrada almacena ademas el timestamp de escritura (_ts) y su TTL
    propio (_ttl), lo que permite convivir entradas con vidas utiles distintas
    (resultados de busqueda vs. fingerprints de audio).

    Escrituras atomicas: se usa un archivo temporal + rename para evitar
    dejar entradas parciales en caso de interrupcion del proceso.

    Thread-safe en lecturas via _io_lock. Las escrituras concurrentes no se
    garantizan pero tampoco ocurren en la practica porque el pipeline es
    secuencial por diseno.

    Side-effects sobre el sistema de archivos:
      - Crea directorios de subcarpeta al inicializar y al escribir.
      - Elimina entradas expiradas en limpiar_expiradas() e invalidar().
      - Las escrituras generan archivos .tmp transitorios que se renombran.
    """

    def __init__(self, directorio: Optional[Path] = None) -> None:
        self._directorio_base = (directorio or _settings.DEFAULT_CACHE_DIR)
        self._io_lock = threading.Lock()
        # Mantener compatibilidad: la subcarpeta MB siempre existe
        subcarpeta_mb = self._directorio_base / _SUBCARPETA_MB
        subcarpeta_mb.mkdir(parents=True, exist_ok=True)
        self._hits   = 0
        self._misses = 0
        _log.debug(f"Cache inicializada en: {self._directorio_base}")

    # ------------------------------------------------------------------
    # API PUBLICA — ACCESO CON TTL PREDETERMINADO
    # ------------------------------------------------------------------

    def obtener(self, clave: str) -> Optional[Any]:
        """
        Recupera un valor de cache si existe y no ha expirado.

        Returns:
            El valor deserializado, o None si no existe o expiro.
        """
        return self._leer_con_ttl(clave, CACHE_TTL_SECONDS)

    def guardar(self, clave: str, valor: Any) -> None:
        """Almacena un valor en cache con el TTL predeterminado."""
        self._escribir(clave, valor)

    # ------------------------------------------------------------------
    # API PUBLICA — ACCESO CON TTL PERSONALIZADO (ej: fingerprints)
    # ------------------------------------------------------------------

    def obtener_con_ttl(self, clave: str, ttl: int) -> Optional[Any]:
        """
        Recupera un valor de cache respetando un TTL personalizado.
        Util para entradas con vida util mas larga (fingerprints, etc.).
        """
        return self._leer_con_ttl(clave, ttl)

    def guardar_con_ttl(self, clave: str, valor: Any, ttl: int) -> None:
        """
        Almacena un valor en cache con un TTL personalizado.
        La entrada sera valida durante 'ttl' segundos desde ahora.
        """
        self._escribir(clave, valor, ttl_override=ttl)

    # ------------------------------------------------------------------
    # API PUBLICA — UTILIDADES
    # ------------------------------------------------------------------

    def invalidar(self, clave: str) -> None:
        """Elimina una entrada especifica de la cache."""
        ruta = self._ruta_para_clave(clave)
        with self._io_lock:
            ruta.unlink(missing_ok=True)

    def limpiar_expiradas(self) -> int:
        """
        Recorre todas las subcarpetas de cache y elimina entradas expiradas.

        Usa el TTL almacenado en la propia entrada (_ttl) para respetar TTLs
        personalizados (ej: fingerprints con TTL extendido). Las entradas con
        JSON corrupto o ilegibles se ignoran silenciosamente.

        Side-effect: elimina archivos del sistema de archivos.

        Returns:
            Numero de entradas eliminadas.
        """
        eliminadas = 0
        ahora = time.time()

        for subcarpeta in self._directorio_base.iterdir():
            if not subcarpeta.is_dir():
                continue
            for archivo in subcarpeta.glob(f"*{CACHE_FILE_EXTENSION}"):
                try:
                    with self._io_lock:
                        with open(archivo, "r", encoding="utf-8") as f:
                            entrada = json.load(f)
                    timestamp = entrada.get("_ts", 0)
                    ttl_entry = entrada.get("_ttl", CACHE_TTL_SECONDS)
                    if ahora - timestamp > ttl_entry:
                        with self._io_lock:
                            archivo.unlink()
                        eliminadas += 1
                except Exception:
                    continue

        if eliminadas > 0:
            _log.info(f"Cache: {eliminadas} entradas expiradas eliminadas")
        return eliminadas

    @property
    def estadisticas(self) -> dict:
        """Retorna metricas de uso de la cache."""
        total = self._hits + self._misses
        tasa  = (self._hits / total * 100) if total > 0 else 0.0
        return {
            "hits":         self._hits,
            "misses":       self._misses,
            "total":        total,
            "tasa_hit_pct": round(tasa, 1),
        }

    # ------------------------------------------------------------------
    # CONSTRUCCION DE CLAVE CANONICA
    # ------------------------------------------------------------------

    @staticmethod
    def construir_clave(prefijo: str, params: dict) -> str:
        """
        Construye una clave de cache determinista a partir de un prefijo
        y un diccionario de parametros.

        El prefijo queda embebido como parte legible de la clave resultante
        (formato: "{prefijo}__{md5}"), lo que permite a _resolver_subcarpeta()
        seleccionar la carpeta correcta sin mapas adicionales en memoria.

        El orden de las claves del dict no afecta el resultado (sorted).
        Los valores falsy (None, "") se excluyen para evitar colisiones
        entre queries con parametros opcionales ausentes.

        Returns:
            String con formato "{prefijo}__{md5_hex}" listo para usarse
            como nombre de archivo de cache.
        """
        payload = prefijo + "|" + "|".join(
            f"{k}={v}" for k, v in sorted(params.items()) if v
        )
        digest = hashlib.md5(payload.encode("utf-8")).hexdigest()
        return f"{prefijo}__{digest}"

    # ------------------------------------------------------------------
    # OPERACIONES INTERNAS
    # ------------------------------------------------------------------

    def _leer_con_ttl(self, clave: str, ttl: int) -> Optional[Any]:
        """
        Lee una entrada de cache validando contra el TTL especificado.

        Respeta el TTL almacenado en la propia entrada (_ttl) si existe,
        ignorando el parametro ttl en ese caso. Esto garantiza que una entrada
        guardada con TTL extendido (fingerprints) no expire prematuramente si
        se lee a traves de obtener() con el TTL predeterminado.

        Si la entrada esta expirada, la elimina del disco antes de retornar None.
        """
        ruta = self._ruta_para_clave(clave)

        if not ruta.exists():
            self._misses += 1
            return None

        try:
            with self._io_lock:
                with open(ruta, "r", encoding="utf-8") as f:
                    entrada = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            _log.debug(f"Error al leer cache {ruta.name}: {e}")
            self._misses += 1
            return None

        timestamp = entrada.get("_ts", 0)
        ttl_real  = entrada.get("_ttl", ttl)  # Respetar TTL almacenado si existe

        if time.time() - timestamp > ttl_real:
            _log.debug(f"Cache expirada: {clave[:16]}...")
            with self._io_lock:
                ruta.unlink(missing_ok=True)
            self._misses += 1
            return None

        self._hits += 1
        _log.debug(f"Cache HIT: {clave[:16]}...")
        return entrada.get("data")

    def _escribir(self, clave: str, valor: Any, ttl_override: Optional[int] = None) -> None:
        """
        Escribe una entrada en cache de forma atomica.

        Usa escritura en archivo temporal + rename para garantizar que nunca
        quede una entrada parcialmente escrita si el proceso se interrumpe
        durante la escritura (garantia de atomicidad en sistemas Unix/POSIX).

        El TTL se almacena dentro de la entrada para que _leer_con_ttl() pueda
        validarlo correctamente incluso si se lee con un TTL diferente al original.

        Si valor es None, no escribe nada (evitar cachear ausencia de datos
        cuando la query aun no se ha ejecutado).
        """
        if valor is None:
            return

        ruta = self._ruta_para_clave(clave)
        entrada = {
            "_ts":   time.time(),
            "_clave": clave,
            "_ttl":  ttl_override or CACHE_TTL_SECONDS,
            "data":  valor,
        }

        try:
            ruta_temp = ruta.with_suffix(".tmp")
            with self._io_lock:
                with open(ruta_temp, "w", encoding="utf-8") as f:
                    json.dump(entrada, f, ensure_ascii=False, indent=None)
                ruta_temp.replace(ruta)  # Operacion atomica en sistemas Unix
            _log.debug(f"Cache guardada: {clave[:16]}...")
        except OSError as e:
            _log.warning(f"No se pudo escribir cache para {clave[:16]}...: {e}")

    def _ruta_para_clave(self, clave: str) -> Path:
        subcarpeta = self._resolver_subcarpeta(clave)
        subcarpeta.mkdir(parents=True, exist_ok=True)
        return subcarpeta / f"{clave}{CACHE_FILE_EXTENSION}"

    def _resolver_subcarpeta(self, clave: str) -> Path:
        """
        Selecciona la subcarpeta segun el prefijo logico embebido en la clave.

        La clave tiene formato "{prefijo}__{md5}", por lo que el prefijo es
        recuperable sin necesidad de un mapa externo. Las claves legacy
        (sin "__") se asignan a la subcarpeta de MusicBrainz por compatibilidad
        con entradas generadas antes de la introduccion del esquema de prefijos.
        """
        # Compatibilidad con claves antiguas (solo hash): se guardan en MB.
        prefijo = clave.split("__", 1)[0] if "__" in clave else ""
        if prefijo.startswith("shazam_"):
            return self._directorio_base / _SUBCARPETA_SHAZAM
        if prefijo.startswith("acoustid_"):
            return self._directorio_base / _SUBCARPETA_ACOUSTID
        if prefijo.startswith("mb_"):
            return self._directorio_base / _SUBCARPETA_MB
        return self._directorio_base / _SUBCARPETA_GENERAL
