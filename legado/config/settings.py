# =============================================================================
# config/settings.py
#
# Parametros operativos, umbrales y rutas de NB SOUND CLI v1.
#
# ORGANIZACION DE ESTE ARCHIVO
# ─────────────────────────────────────────────────────────────────────────────
#   SECCION A — RUTAS OBLIGATORIAS
#     Sin estos valores el programa no puede ejecutarse. Dejalos vacios y
#     el sistema te indicara exactamente que falta al intentar correrlo.
#
#   SECCION B — CONFIGURACION OPCIONAL
#     Modulos extra que mejoran la precision cuando estan configurados.
#     Si se omiten, el sistema funciona correctamente con MusicBrainz solo.
#     Cada parametro tiene un comentario indicando donde obtener la clave.
#
#   SECCION C — PARAMETROS OPERATIVOS (predeterminados optimos)
#     Ajustados para el mejor equilibrio precision/velocidad. Puedes
#     modificarlos si conoces bien el comportamiento del sistema.
#
# REGLA DE ORO: Nada de lo que configures aqui debe apuntar dentro del
# directorio del proyecto. El proyecto es solo codigo; todos los datos van
# fuera de el.
# =============================================================================

from pathlib import Path
from typing import Optional
import os
import sys
import tempfile

# `python-dotenv` se carga de forma opcional. En el bundle frozen está
# disponible, pero los subprocess Python externos (por ejemplo
# `infra.deep_runner`) usan el intérprete del sistema y pueden no
# tenerlo instalado. Sin esta defensa, el subprocess deep fallaba con
# `ModuleNotFoundError: No module named 'dotenv'` al importar
# `config.settings`, lo que dejaba todos los análisis deep en estado
# "analyzer_init_failed".
try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]
except Exception:
    def load_dotenv(*_args, **_kwargs):  # type: ignore[misc]
        return False


def _cargar_env_usuario() -> None:
    """Carga el .env desde las ubicaciones donde el bootstrap lo deposita.

    Orden de precedencia (las primeras sobrescriben las siguientes solo si
    aún no se ha cargado el valor):
      1. ``.env`` en el directorio actual (desarrollo: repo / CWD).
      2. ``.env`` en el directorio de configuración estándar del SO:
           Linux   -> ``$XDG_CONFIG_HOME/nb_sound/.env``
                      (fallback ``~/.config/nb_sound/.env``)
           Windows -> ``%APPDATA%\\NBSound\\.env``
           macOS   -> ``~/Library/Preferences/NBSound/.env``

    Necesario porque en builds empaquetadas (PyInstaller) no existe un
    ``.env`` adyacente al ejecutable; el bootstrap genera uno en la ruta
    de configuración del sistema operativo en el primer arranque, y a
    partir del segundo arranque es desde donde debe leerse.

    La función es defensiva: si python-dotenv falla, si el archivo no
    existe, o si la resolución de rutas levanta excepción, simplemente
    sigue adelante; los defaults internos del módulo continúan vigentes.
    """
    # 1. .env relativo al CWD / proyecto en desarrollo.
    try:
        load_dotenv()
    except Exception:
        pass

    # 2. .env del usuario (estándar por SO). No sobreescribe lo ya cargado.
    try:
        env_usuario = _resolver_env_usuario_path()
    except Exception:
        env_usuario = None
    if env_usuario and env_usuario.is_file():
        try:
            load_dotenv(env_usuario, override=False)
        except Exception:
            pass


def _resolver_env_usuario_path():
    """Resuelve la ruta esperada del .env de usuario según el SO.

    Mantiene su propia lógica (sin importar ``infra.bootstrap``) para
    evitar dependencias circulares: ``config.settings`` es importado por
    casi todo y debe poder cargarse en cualquier contexto, incluido el
    bootstrap mismo. Si las rutas cambian, mantener sincronizado con
    :func:`infra.bootstrap.resolver_rutas_estandar`.
    """
    from pathlib import Path

    plataforma = sys.platform
    home = Path.home()
    if plataforma.startswith("win"):
        roaming = os.environ.get("APPDATA")
        base = Path(roaming) if roaming else home / "AppData" / "Roaming"
        return base / "NBSound" / ".env"
    if plataforma == "darwin":
        return home / "Library" / "Preferences" / "NBSound" / ".env"
    # Linux y otros UNIX: XDG.
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(xdg) if xdg else home / ".config"
    return base / "nb_sound" / ".env"


# El .env se carga aqui para que los _env_* helpers ya vean sus valores al
# importar. En tests, las variables pueden inyectarse antes del import; el
# parámetro ``override=False`` de python-dotenv respeta lo que ya existe.
_cargar_env_usuario()


def _env_str(nombre: str, default: str = "") -> str:
    """Obtiene una variable de entorno como string, con fallback a default."""
    valor = os.getenv(nombre, default)
    if valor is None:
        return default
    return valor.strip()


def _env_bool(nombre: str, default: bool) -> bool:
    """Obtiene una variable de entorno como booleano. Reconoce: 1|true|yes|on|si."""
    valor = os.getenv(nombre)
    if valor is None:
        return default
    return valor.strip().lower() in {"1", "true", "yes", "on", "si"}


def _env_int(
    nombre: str, 
    default: int, 
    min_val: Optional[int] = None, 
    max_val: Optional[int] = None
) -> int:
    """
    Obtiene una variable de entorno como int con validación de rango.
    
    Args:
        nombre: Nombre de la variable
        default: Valor por defecto si no existe
        min_val: Valor mínimo permitido (inclusive). None = sin límite inferior
        max_val: Valor máximo permitido (inclusive). None = sin límite superior
    
    Returns:
        El valor si está en rango válido, else default con advertencia.
    """
    valor = os.getenv(nombre)
    if valor is None:
        return default
    try:
        parsed = int(valor)
        # Validar rango
        if min_val is not None and parsed < min_val:
            import sys
            if sys.stderr is not None:
                print(
                    f"[WARN] {nombre}={parsed} por debajo del mínimo ({min_val}), "
                    f"usando default={default}",
                    file=sys.stderr,
                )
            return default
        if max_val is not None and parsed > max_val:
            import sys
            if sys.stderr is not None:
                print(
                    f"[WARN] {nombre}={parsed} por encima del máximo ({max_val}), "
                    f"usando default={default}",
                    file=sys.stderr,
                )
            return default
        return parsed
    except ValueError:
        return default


def _env_float(
    nombre: str, 
    default: float, 
    min_val: Optional[float] = None, 
    max_val: Optional[float] = None
) -> float:
    """
    Obtiene una variable de entorno como float con validación de rango.
    
    Args:
        nombre: Nombre de la variable
        default: Valor por defecto si no existe
        min_val: Valor mínimo permitido (inclusive). None = sin límite inferior
        max_val: Valor máximo permitido (inclusive). None = sin límite superior
    
    Returns:
        El valor si está en rango válido, else default con advertencia.
    """
    valor = os.getenv(nombre)
    if valor is None:
        return default
    try:
        parsed = float(valor)
        # Validar rango
        if min_val is not None and parsed < min_val:
            import sys
            if sys.stderr is not None:
                print(
                    f"[WARN] {nombre}={parsed} por debajo del mínimo ({min_val}), "
                    f"usando default={default}",
                    file=sys.stderr,
                )
            return default
        if max_val is not None and parsed > max_val:
            import sys
            if sys.stderr is not None:
                print(
                    f"[WARN] {nombre}={parsed} por encima del máximo ({max_val}), "
                    f"usando default={default}",
                    file=sys.stderr,
                )
            return default
        return parsed
    except ValueError:
        return default


# =============================================================================
# SECCION A — RUTAS OBLIGATORIAS
# Rellena estas cinco rutas para poder ejecutar el programa sin argumentos.
# Si las dejas vacias, deberas pasarlas por linea de comandos cada vez.
# =============================================================================

USER_INPUT_DIR      = _env_str("USER_INPUT_DIR", "")   # Ejemplo: "/home/usuario/Descargas/musica"
USER_LIBRARY_DIR    = _env_str("USER_LIBRARY_DIR", "")   # Ejemplo: "/home/usuario/Musica/biblioteca"
USER_QUARANTINE_DIR = _env_str("USER_QUARANTINE_DIR", "")   # Ejemplo: "/home/usuario/Musica/cuarentena"
USER_REVIEW_DIR     = _env_str("USER_REVIEW_DIR", "")   # Ejemplo: "/home/usuario/Musica/revision"
USER_LOGS_DIR       = _env_str("USER_LOGS_DIR", "")   # Ejemplo: "/home/usuario/Musica/logs"
USER_PROCESSED_DIR  = _env_str("USER_PROCESSED_DIR", "")   # Ejemplo: "/home/usuario/Musica/procesados"


# =============================================================================
# SECCION B — CONFIGURACION OPCIONAL
#
# B.1 — Rutas opcionales con fallback automatico
# =============================================================================

USER_CACHE_DIR = _env_str("USER_CACHE_DIR", "")   # Predeterminado si se omite: ~/.cache/nb_sound
USER_TEMP_DIR  = _env_str("USER_TEMP_DIR", "")   # Predeterminado si se omite: tempfile.gettempdir()/nb_sound


# =============================================================================
# B.2 — Identificacion acustica con AcoustID
#
# Genera un fingerprint acustico del audio y lo contrasta con la base de datos
# abierta de AcoustID. Proporciona recording IDs de MusicBrainz con alta
# confianza, independientemente de los tags existentes.
#
# Requiere:
#   pip install pyacoustid
#   + binario fpcalc (apt install libchromaprint-tools / brew install chromaprint)
#   + Clave gratuita en: https://acoustid.org/login
# =============================================================================

ACOUSTID_API_KEY = _env_str("ACOUSTID_API_KEY", "")   # Pega aqui tu clave de AcoustID

ENABLE_ACOUSTID = _env_bool("ENABLE_ACOUSTID", True)   # Activa el modulo si pyacoustid y fpcalc estan disponibles


# =============================================================================
# B.3 — Identificacion por Shazam
#
# Consulta la base de datos de Shazam para obtener titulo, artista e ISRC.
# Especialmente util para archivos sin metadata o con tags incorrectos.
# El ISRC resultante permite localizar la grabacion exacta en MusicBrainz.
#
# Requiere:
#   pip install shazamio
# =============================================================================

ENABLE_SHAZAM         = _env_bool("ENABLE_SHAZAM", True)    # Activa el modulo si shazamio esta instalado
SHAZAM_TIMEOUT_SEG    = _env_int("SHAZAM_TIMEOUT_SEG", 12, min_val=1, max_val=300)  # Segundos maximos
SHAZAM_MIN_DURACION_SEG = _env_int("SHAZAM_MIN_DURACION_SEG", 20)    # No enviar a Shazam archivos mas cortos que esto


# =============================================================================
# B.4 — Desempate inteligente con IA
#
# Cuando el scoring determinista produce un empate o ambiguedad entre candidatos,
# un modelo de lenguaje economico elige entre los candidatos disponibles.
# La IA NO inventa datos: solo puede elegir de la lista proporcionada o
# devolver "revision_manual".
#
# Puedes dejar configuradas las claves de ambos proveedores y seleccionar
# cual usar con el campo IA_PROVEEDOR.
#
# Proveedores disponibles: "Anthropic" | "OpenAI"
#
# Para Anthropic:
#   pip install anthropic
#   + Clave en: https://console.anthropic.com
#
# Para OpenAI:
#   pip install openai
#   + Clave en: https://platform.openai.com/api-keys
# =============================================================================

# --- Seleccion de proveedor ---
# Cambia este valor para elegir que IA usar. Opciones: "Anthropic" | "OpenAI" | "No"
# Usa "No" para desactivar la capa de IA completamente sin necesidad de
# configurar ningun proveedor externo (equivale a ENABLE_IA_TIEBREAK = False).
IA_PROVEEDOR = _env_str("IA_PROVEEDOR", "No")

# --- Claves de API (puedes dejar las dos escritas) ---
ANTHROPIC_API_KEY = _env_str("ANTHROPIC_API_KEY", "")   # Pega aqui tu clave de Anthropic
OPENAI_API_KEY    = _env_str("OPENAI_API_KEY", "")   # Pega aqui tu clave de OpenAI

# --- Modelos a usar por proveedor ---
IA_TIEBREAK_MODEL_ANTHROPIC = "claude-haiku-4-5-20251001"  # Modelo economico de Anthropic
IA_TIEBREAK_MODEL_OPENAI    = "gpt-4o-mini"                # Modelo economico de OpenAI

# --- Parametros comunes ---
ENABLE_IA_TIEBREAK    = _env_bool("ENABLE_IA_TIEBREAK", True)    # Activa el modulo de desempate por IA
# v3.3: umbral ampliado de 0.08 → 0.12 para que la IA intervenga en mas
# casos de ambiguedad leve, especialmente en variantes con score cercano.
IA_TIEBREAK_MIN_GAP   = _env_float("IA_TIEBREAK_MIN_GAP", 0.12, min_val=0.01, max_val=0.99)
IA_MAX_TOKENS         = _env_int("IA_MAX_TOKENS", 512, min_val=64, max_val=4096)     # Tokens maximos para la respuesta de la IA
IA_TIMEOUT_SEG        = _env_int("IA_TIMEOUT_SEG", 20, min_val=5, max_val=300)      # Segundos maximos de espera

# Resolucion del modelo activo segun el proveedor seleccionado.
# Si IA_PROVEEDOR es "No" (u otro valor no reconocido), no se resuelve ningun modelo;
# el cliente IA lo interpretara como capa desactivada sin intentar validar claves.
IA_TIEBREAK_MODEL = (
    IA_TIEBREAK_MODEL_OPENAI     if IA_PROVEEDOR == "OpenAI"
    else IA_TIEBREAK_MODEL_ANTHROPIC if IA_PROVEEDOR == "Anthropic"
    else ""
)


# =============================================================================
# SECCION C — PARAMETROS OPERATIVOS
# Valores predeterminados cuidadosamente ajustados. Modificalos solo si
# entiendes el impacto en el pipeline.
# =============================================================================

# --- Formatos y tamanos de archivo ---
SUPPORTED_EXTENSIONS     = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".aac"}
MIN_FILE_SIZE_BYTES      = 10_240        # 10 KB — proteccion contra archivos truncados
MAX_FILE_SIZE_BYTES      = 200 * 1024 * 1024  # 200 MB

# --- Validacion tecnica de audio ---
MIN_DURATION_SECONDS     = 15
MAX_DURATION_SECONDS     = 3600          # 1 hora
MIN_BITRATE_KBPS         = 64

# --- Normalizacion de texto ---

# Variantes de "featuring" que se unifican durante la normalizacion
FEATURING_VARIANTS = [
    " featuring ", " feat. ", " feat ", " ft. ", " ft ",
    " with ", " w/ ", " vs. ", " vs ",
    "(feat.", "(ft.", "(featuring", "(with ",
    " x ",
]

# Sufijos promocionales/decorativos a eliminar de titulos antes del matching
PROMO_SUFFIXES = [
    # Videos y audios
    "(official video)", "(official audio)", "(official music video)",
    "(lyrics)", "(lyric video)", "(visualizer)", "(audio)",
    "(hd)", "(hq)", "(4k)", "(explicit)", "(clean)",
    "[official video]", "[official audio]", "[lyrics]",
    "[explicit]", "[clean]", "[hd]",
    "(official)", "(video oficial)", "(audio oficial)",
    # Marcas de sitios de descarga — spotdown y similares
    "[spotdown.org]", "(spotdown.org)", "spotdown.org",
    "[_spotdown.org]", "[www.spotdown.org]",
    "[mp3paw.com]", "[mp3juice.cc]", "[zippyshare.com]",
    "[freemusicdownload]", "(freemusicdownload)",
    # Versiones y ediciones
    "(remastered)", "(remaster)", "(remastered version)",
    "(2011 remaster)", "(2012 remaster)", "(2013 remaster)",
    "(2014 remaster)", "(2015 remaster)", "(2016 remaster)",
    "(2017 remaster)", "(2018 remaster)", "(2019 remaster)",
    "(2020 remaster)", "(2021 remaster)", "(2022 remaster)",
    "(2023 remaster)", "(2024 remaster)", "(2025 remaster)",
    "[remastered]", "[remaster]",
    "(deluxe edition)", "(deluxe version)", "(deluxe)",
    "[deluxe edition]", "[deluxe]",
    "(extended version)", "(extended edition)", "(extended)",
    "[extended]",
    "(album version)", "(single version)", "(radio edit)",
    "(radio version)", "(original mix)", "(original version)",
    "(bonus track)", "(bonus)",
    "(instrumental)", "[instrumental]",
    "(mono)", "(mono version)", "(stereo)", "(stereo version)",
    "(acoustic)", "(acoustic version)", "[acoustic]",
    "(live)", "[live]",
    "(demo)", "(demo version)", "[demo]",
    "(anniversary edition)", "(special edition)",
    "(super deluxe)", "(super deluxe edition)",
    "(anniversary)", "(20th anniversary)", "(25th anniversary)",
    "(30th anniversary)", "(40th anniversary)", "(50th anniversary)",
]

# Palabras clave que identifican versiones alternativas del titulo
# Se usan para normalizar antes de comparar, sin borrar el titulo completo
VERSION_KEYWORDS = frozenset({
    "remastered", "remaster", "deluxe", "extended",
    "album version", "radio edit", "single version",
    "acoustic", "instrumental", "demo", "live", "bonus",
    "anniversary", "special edition", "anniversary edition",
})

# --- Matching y puntuacion ---

# Pesos de cada criterio en el scoring de candidatos MusicBrainz (deben sumar 1.0).
# El peso de "isrc" solo tiene efecto cuando hay ISRC disponible en la fuente
# externa; en caso contrario ese peso se redistribuye proporcionalmente.
SCORE_WEIGHTS = {
    "titulo":        0.28,
    "artista":       0.23,
    "duracion":      0.18,
    "album":         0.10,
    "track_number":  0.07,
    "tipo_release":  0.07,
    "isrc":          0.07,   # Solo aplica cuando hay ISRC disponible
}

# Umbral de aceptacion automatica: puntaje >= este valor -> DecisionTipo.ACEPTADO.
# Umbral de revision: score entre REVIEW y ACCEPT -> DecisionTipo.REVISION.
# Score < REVIEW -> DecisionTipo.CUARENTENA.
SCORE_THRESHOLD_ACCEPT = 0.82    # >= acepta automaticamente
SCORE_THRESHOLD_REVIEW = 0.55    # >= envia a revision manual

DURATION_TOLERANCE_PERFECT = 3   # segundos — puntaje perfecto de duracion
DURATION_TOLERANCE_PARTIAL  = 10  # segundos — puntaje parcial de duracion

MAX_CANDIDATES_PER_FILE     = 8

# Penalizaciones aplicadas al puntaje total del candidato.
# PENALTY_AMBIGUITY_GAP: se aplica cuando el gap entre el primero y el segundo
# candidato es menor que MIN_SCORE_GAP, indicando ambiguedad entre ellos.
PENALTY_COMPILATION         = 0.25
PENALTY_LIVE_REMIX          = 0.20
PENALTY_AMBIGUITY_GAP       = 0.15
MIN_SCORE_GAP               = 0.10

# Bonus cuando el año del release coincide con el año en la metadata local
BONUS_YEAR_MATCH            = 0.04

# Bonus cuando el ISRC de la fuente externa coincide con el del candidato MB
BONUS_ISRC_EXACTO           = 0.22

# Resultados minimos antes de intentar estrategia de fallback
MIN_RESULTS_PER_STRATEGY    = 3

# --- Tipos de release (MusicBrainz release-group primary types) ---

ACCEPTED_RELEASE_TYPES = {"Album", "Single", "EP"}

RELEASE_TYPE_TO_FOLDER = {
    # Tipos principales → carpetas semánticas en español
    "Album":             "albumes",
    "Single":            "singles_y_ep",
    "EP":                "singles_y_ep",
    # Tipos secundarios y especiales → siempre a otros
    "Compilation":       "otros",
    "Live":              "otros",
    "Remix":             "otros",
    "DJ-mix":            "otros",
    "Mixtape/Street":    "otros",
    "Soundtrack":        "otros",
    "Audiobook":         "otros",
    "Interview":         "otros",
    "Spoken Word":       "otros",
    "Other":             "otros",
}

PENALIZED_RELEASE_TYPES = {
    "Compilation", "Live", "Remix", "DJ-mix", "Mixtape/Street",
    "Soundtrack", "Broadcast", "Audiobook", "Interview", "Spoken Word",
}

# Prioridad para seleccionar el mejor release de una grabacion (mayor = mejor)
# Prioridad para elegir el release canonico cuando una grabacion aparece en
# multiples releases de MusicBrainz. Mayor valor = mejor candidato.
# Se usa para seleccionar el release mas representativo antes del scoring final.
RELEASE_TYPE_PRIORITY = {
    "Album":          50,
    "EP":             40,
    "Single":         35,
    "Compilation":    20,
    "Soundtrack":     15,
    "Live":           12,
    "Remix":          10,
    "DJ-mix":          8,
    "Mixtape/Street":  8,
    "Broadcast":       5,
    "Other":           5,
    "Audiobook":       3,
    "Interview":       3,
    "Spoken Word":     3,
    "":                2,
}

# --- Consulta externa — MusicBrainz ---

MB_USER_AGENT_APP     = "NBSoundLocal"
MB_USER_AGENT_VERSION = "2.0.0"
MB_USER_AGENT_CONTACT = "local-tagger@localhost"

MB_SEARCH_LIMIT              = 10
MB_REQUEST_TIMEOUT           = 15
MB_RATE_LIMIT_SECONDS        = 1.1
MB_MAX_RETRIES               = 3
MB_BACKOFF_FACTOR            = 2.0
MB_BACKOFF_BASE              = 2.0
MB_MAX_RELEASES_PER_RECORDING = 15

# --- Reintentos AcoustID (fallos transitorios de red / DNS) ---
# v3.4: AcoustID opera sobre red externa y puede fallar transitoriamente.
# Se reintenta con backoff exponencial antes de degradar a 0 resultados.
ACOUSTID_MAX_RETRIES   = 3     # Número de reintentos ante WebServiceError
ACOUSTID_BACKOFF_BASE  = 2.0   # Segundos de pausa inicial
ACOUSTID_BACKOFF_FACTOR = 2.0  # Multiplicador por cada intento adicional

# --- Cache local ---

# TTLs del cache local en disco (archivos .json por clave de busqueda).
# Los fingerprints tienen TTL mas largo porque el audio no cambia; los
# resultados negativos se cachean menos tiempo para reintentar antes.
CACHE_TTL_SECONDS             = 86_400    # 24 horas para resultados de busqueda
CACHE_TTL_FINGERPRINT_SECONDS = 604_800   # 7 dias para fingerprints acusticos
CACHE_TTL_NEGATIVE_SECONDS    = 21_600    # 6 horas para resultados negativos permanentes
CACHE_FILE_EXTENSION          = ".json"

# --- Logs y reportes ---

LOG_LEVEL_CONSOLE        = "INFO"
LOG_LEVEL_FILE           = "DEBUG"
LOG_FILE_NAME            = "tagger_run.log"
LOG_EVENTS_FILE_NAME     = "tagger_events.jsonl"
REPORT_SUMMARY_FILE_NAME = "tagger_summary.json"
NB_SOUND_PROGRESS_MODE   = _env_str("NB_SOUND_PROGRESS_MODE", "auto")
NB_SOUND_PROGRESS_INTERVAL_SEC = _env_float("NB_SOUND_PROGRESS_INTERVAL_SEC", 2.0, min_val=0.25, max_val=60.0)

# --- Nomenclatura de archivos y carpetas ---

SLUG_SEPARATOR          = "_"
TRACK_FILENAME_TEMPLATE = "{track_num:02d}_{slug_titulo}.mp3"
SLUG_MAX_LENGTH         = 80

# --- Comportamiento general del pipeline ---

DRY_RUN                = False
INIT_COMPONENT_MAX_RETRIES = _env_int("INIT_COMPONENT_MAX_RETRIES", 2)
INIT_COMPONENT_RETRY_BACKOFF_SEG = _env_float("INIT_COMPONENT_RETRY_BACKOFF_SEG", 0.7)
# Si un MP3 vuelve manualmente a "entrada", se re-procesa para reconstruir
# biblioteca/procesados/assets en corridas de recuperación ("hot run").
# Puedes activar el comportamiento antiguo exportando SKIP_ALREADY_PROCESSED=true.
SKIP_ALREADY_PROCESSED = _env_bool("SKIP_ALREADY_PROCESSED", False)
# Marca ID3 escrita en cada archivo procesado exitosamente. El campo TXXX
# es un tag libre de ID3v2; su presencia permite detectar archivos ya
# procesados en corridas posteriores sin consultar la BD.
PROCESSED_TAG_MARKER   = "TAGGER_V3"
PROCESSED_TAG_FIELD    = "TXXX:tagger_status"

# --- Deteccion de duplicados ---
ENABLE_DEDUPLICATION          = _env_bool("ENABLE_DEDUPLICATION", True)
ENABLE_SEMANTIC_DEDUPLICATION = _env_bool("ENABLE_SEMANTIC_DEDUPLICATION", True)
# Politica de duplicados: "replace_if_better" reemplaza el archivo existente
# solo si el nuevo candidato supera el score del actual por al menos
# DUPLICATE_BETTER_MIN_DELTA. Valores menores son mas agresivos en el reemplazo.
DUPLICATE_POLICY              = _env_str("DUPLICATE_POLICY", "replace_if_better")
DUPLICATE_BETTER_MIN_DELTA    = _env_float("DUPLICATE_BETTER_MIN_DELTA", 0.08)
# Eje observable (3a capa de dedupe): dos pistas son duplicado obvio si
# comparten titulo/artista/album normalizados + portada (hash de contenido) y
# su duracion difiere a lo sumo esta tolerancia, en segundos. Es un parametro
# de afinacion interno del algoritmo (la regla de producto es fija: +-3 s), no
# una preferencia de usuario expuesta en la pantalla de Configuracion; por eso
# es una constante literal y no una variable `_env_*` (que ademas exigiria
# mapearla en el contrato de ModeloConfiguracion).
DUPLICATE_OBSERVABLE_TOLERANCIA_SEG = 3.0

# --- Pipeline de assets multimedia (caratulas / imagenes de artista) ---
ENABLE_ASSETS_PIPELINE        = _env_bool("ENABLE_ASSETS_PIPELINE", True)
ENABLE_COVER_ART_ARCHIVE      = _env_bool("ENABLE_COVER_ART_ARCHIVE", True)
ENABLE_THEAUDIODB_ARTIST_IMAGES = _env_bool("ENABLE_THEAUDIODB_ARTIST_IMAGES", True)
ENABLE_ITUNES_COVER_FALLBACK  = _env_bool("ENABLE_ITUNES_COVER_FALLBACK", True)
ENABLE_DEEZER_ARTIST_IMAGES   = _env_bool("ENABLE_DEEZER_ARTIST_IMAGES", True)
ENABLE_WIKIPEDIA_ARTIST_IMAGES = _env_bool("ENABLE_WIKIPEDIA_ARTIST_IMAGES", True)
ENABLE_ITUNES_ARTIST_IMAGES    = _env_bool("ENABLE_ITUNES_ARTIST_IMAGES", True)
THEAUDIODB_API_KEY            = _env_str("THEAUDIODB_API_KEY", "123")
ASSETS_TIMEOUT_SEG            = _env_int("ASSETS_TIMEOUT_SEG", 10)
ASSETS_MAX_RETRIES            = _env_int("ASSETS_MAX_RETRIES", 2)
ASSETS_RETRY_BACKOFF_SEG      = _env_float("ASSETS_RETRY_BACKOFF_SEG", 0.8)
ASSETS_CACHE_TTL_SEG          = _env_int("ASSETS_CACHE_TTL_SEG", 259200)
ASSETS_NEGATIVE_CACHE_TTL_SEG = _env_int("ASSETS_NEGATIVE_CACHE_TTL_SEG", 21600)
# Resolucion minima aceptable para portadas en pixels (ancho o alto).
# ASSETS_HD_MAX_IMAGE_BYTES: limite de descarga para evitar imagenes gigantes
# que bloqueen el hilo de I/O durante el pipeline de assets.
ASSETS_MIN_RESOLUTION         = _env_int("ASSETS_MIN_RESOLUTION", 250)
ASSETS_HD_MAX_IMAGE_BYTES     = _env_int("ASSETS_HD_MAX_IMAGE_BYTES", 25_000_000, min_val=1_000_000, max_val=100_000_000)

# --- Enriquecimiento externo (letras + analítica ligera) ---
ENABLE_EXTERNAL_ENRICHMENT    = _env_bool("ENABLE_EXTERNAL_ENRICHMENT", True)
ENABLE_LYRICS_ENRICHMENT      = _env_bool("ENABLE_LYRICS_ENRICHMENT", True)
ENABLE_LRCLIB                 = _env_bool("ENABLE_LRCLIB", True)
ENABLE_LYRICS_OVH             = _env_bool("ENABLE_LYRICS_OVH", True)
LYRICS_TIMEOUT_SEG            = _env_int("LYRICS_TIMEOUT_SEG", 8)
LYRICS_MAX_RETRIES            = _env_int("LYRICS_MAX_RETRIES", 1)
LYRICS_RETRY_BACKOFF_SEG      = _env_float("LYRICS_RETRY_BACKOFF_SEG", 0.8)
LYRICS_SUGGEST_LIMIT          = _env_int("LYRICS_SUGGEST_LIMIT", 3, min_val=0, max_val=10)
# Timeout total para esperar que el sidecar de enriquecimiento (letras,
# analisis de audio) complete su trabajo en background. El heartbeat
# controla con que frecuencia se verifica si el future ya termino.
SIDECAR_FUTURE_TIMEOUT_SEG    = _env_float("SIDECAR_FUTURE_TIMEOUT_SEG", 90.0, min_val=5.0, max_val=3600.0)
SIDECAR_WAIT_HEARTBEAT_SEG    = _env_float("SIDECAR_WAIT_HEARTBEAT_SEG", 2.0, min_val=0.25, max_val=60.0)

USER_ASSETS_DIR = _env_str("USER_ASSETS_DIR", "")

# --- Segunda fase dirigida (post-clasificacion) ---
ENABLE_SECOND_STAGE_RESOLUTION = _env_bool("ENABLE_SECOND_STAGE_RESOLUTION", True)
SECOND_STAGE_MAX_CANDIDATES    = _env_int("SECOND_STAGE_MAX_CANDIDATES", 5)
SECOND_STAGE_MIN_EVIDENCE      = _env_float("SECOND_STAGE_MIN_EVIDENCE", 0.86)
SECOND_STAGE_MIN_GAP           = _env_float("SECOND_STAGE_MIN_GAP", 0.12)
SECOND_STAGE_CAUSE_ENABLED     = _env_bool("SECOND_STAGE_CAUSE_ENABLED", True)

# --- Tercera fase conservadora (post-segunda-fase) ---
ENABLE_THIRD_STAGE_RESOLUTION  = _env_bool("ENABLE_THIRD_STAGE_RESOLUTION", True)
THIRD_STAGE_MIN_EVIDENCE       = _env_float("THIRD_STAGE_MIN_EVIDENCE", 0.90)
THIRD_STAGE_MIN_GAP            = _env_float("THIRD_STAGE_MIN_GAP", 0.14)

# --- Organización discográfica asistida ---
ENABLE_IA_DISCOGRAPHY          = _env_bool("ENABLE_IA_DISCOGRAPHY", True)
DISCOGRAPHY_IA_MIN_CONFIDENCE  = _env_float("DISCOGRAPHY_IA_MIN_CONFIDENCE", 0.90)

# --- Manifiestos canónicos y overrides ---
MANIFEST_SCHEMA_VERSION        = _env_int("MANIFEST_SCHEMA_VERSION", 1)
USER_MANIFESTS_DIR             = _env_str("USER_MANIFESTS_DIR", "")
ENABLE_OVERRIDES               = _env_bool("ENABLE_OVERRIDES", True)


# =============================================================================
# RESOLUCION DE RUTAS (no modificar)
# =============================================================================

def resolver_ruta(
    valor_usuario: str,
    fallback_sistema: Optional[str] = None,
) -> Optional[Path]:
    """
    Resuelve una ruta de usuario expandiendo ~ y rutas relativas.
    Retorna None si no hay valor ni fallback configurado.

    No crea el directorio — eso es responsabilidad del componente que lo usa.
    Se llama al cargar el modulo para que las rutas ya esten resueltas en runtime.
    """
    valor = (valor_usuario or "").strip()
    if valor:
        return Path(valor).expanduser().resolve()
    if fallback_sistema:
        return Path(fallback_sistema).expanduser().resolve()
    return None


# Fallbacks cross-platform delegados a infra.bootstrap:
#   Linux   -> XDG (~/.local/share, ~/.cache, ~/.config)
#   Windows -> %LOCALAPPDATA%, %APPDATA%
#   macOS   -> ~/Library/Application Support, ~/Library/Caches, ~/Library/Preferences
# El bloque except cubre el caso de que el paquete `infra` no esté
# disponible durante el import (por ejemplo, en una instalación rota); en
# ese caso se usa el temp del sistema, que existe en todas las plataformas.
try:
    from infra.bootstrap import resolver_rutas_estandar as _resolver_rutas_estandar
    _RUTAS_SO = _resolver_rutas_estandar()
    _FALLBACK_PROCESSED  = str(_RUTAS_SO.processed)
    _FALLBACK_CACHE      = str(_RUTAS_SO.cache)
    _FALLBACK_ASSETS     = str(_RUTAS_SO.assets)
    _FALLBACK_MANIFESTS  = str(_RUTAS_SO.manifests)
    _FALLBACK_TEMP       = str(_RUTAS_SO.temp)
except Exception:  # pragma: no cover
    _tmp_root = Path(tempfile.gettempdir()) / "nb_sound"
    _FALLBACK_PROCESSED  = str(_tmp_root / "procesados")
    _FALLBACK_CACHE      = str(_tmp_root / "cache")
    _FALLBACK_ASSETS     = str(_tmp_root / "assets")
    _FALLBACK_MANIFESTS  = str(_tmp_root / "manifests")
    _FALLBACK_TEMP       = str(_tmp_root)


# Rutas resueltas al cargar el modulo. Cache, temp, assets, manifests y
# processed siempre tienen valor (fallback de sistema). Las demas son
# Optional[Path] y pueden ser None si el usuario no las define.
DEFAULT_INPUT_DIR      = resolver_ruta(USER_INPUT_DIR)
DEFAULT_LIBRARY_DIR    = resolver_ruta(USER_LIBRARY_DIR)
DEFAULT_QUARANTINE_DIR = resolver_ruta(USER_QUARANTINE_DIR)
DEFAULT_REVIEW_DIR     = resolver_ruta(USER_REVIEW_DIR)
DEFAULT_LOGS_DIR       = resolver_ruta(USER_LOGS_DIR)
DEFAULT_PROCESSED_DIR  = resolver_ruta(USER_PROCESSED_DIR, _FALLBACK_PROCESSED)
DEFAULT_CACHE_DIR      = resolver_ruta(USER_CACHE_DIR, _FALLBACK_CACHE)
DEFAULT_TEMP_DIR       = resolver_ruta(USER_TEMP_DIR, _FALLBACK_TEMP)
DEFAULT_ASSETS_DIR     = resolver_ruta(USER_ASSETS_DIR, _FALLBACK_ASSETS)
DEFAULT_MANIFESTS_DIR  = resolver_ruta(USER_MANIFESTS_DIR, _FALLBACK_MANIFESTS)

def _leer_clave_api(nombre_var: str, _modulo_globals: dict) -> str:
    """Lee una clave de API del settings o, como fallback, del entorno.

    Permite que un .env establezca la clave directamente en la variable del
    modulo (via _env_str) o que se pase como variable de entorno pura (util
    en CI/CD donde no hay .env). La variable del modulo tiene prioridad.

    NOTA: locals() dentro de una funcion solo ve su propio scope local,
    nunca las variables del modulo. Por eso se recibe globals() como parametro.
    """
    valor_settings = _modulo_globals.get(nombre_var, "")
    if valor_settings:
        return str(valor_settings).strip()
    return os.environ.get(nombre_var, "").strip()

ACOUSTID_API_KEY_RESOLVED  = _leer_clave_api("ACOUSTID_API_KEY",  globals())
ANTHROPIC_API_KEY_RESOLVED = _leer_clave_api("ANTHROPIC_API_KEY", globals())
OPENAI_API_KEY_RESOLVED    = _leer_clave_api("OPENAI_API_KEY",    globals())


# Audio Features / Intelligence / Music Discovery
ENABLE_AUDIO_FEATURES = _env_bool("ENABLE_AUDIO_FEATURES", True)
# "light" usa librosa (CPU, rapido). "standard" activa analisis adicionales.
# Valores no reconocidos caen a "light" para no bloquear el arranque.
AUDIO_FEATURES_MODE = _env_str("AUDIO_FEATURES_MODE", "light") if _env_str("AUDIO_FEATURES_MODE", "light") in {"light","standard"} else "light"
AUDIO_FEATURES_ANALYZE_ON_IMPORT = _env_bool("AUDIO_FEATURES_ANALYZE_ON_IMPORT", True)
AUDIO_FEATURES_BACKGROUND = _env_bool("AUDIO_FEATURES_BACKGROUND", True)
AUDIO_FEATURES_MAX_WORKERS = _env_int("AUDIO_FEATURES_MAX_WORKERS", 1, min_val=1, max_val=4)
AUDIO_FEATURES_ANALYZE_FULL_TRACK = _env_bool("AUDIO_FEATURES_ANALYZE_FULL_TRACK", False)
AUDIO_FEATURES_SAMPLE_STRATEGY = _env_str("AUDIO_FEATURES_SAMPLE_STRATEGY", "smart_segments")
AUDIO_FEATURES_SEGMENT_SECONDS = _env_int("AUDIO_FEATURES_SEGMENT_SECONDS", 90, min_val=15, max_val=600)
AUDIO_FEATURES_REANALYZE_ON_VERSION_CHANGE = _env_bool("AUDIO_FEATURES_REANALYZE_ON_VERSION_CHANGE", True)
AUDIO_FEATURES_FAIL_SILENTLY = _env_bool("AUDIO_FEATURES_FAIL_SILENTLY", True)

# Analisis profundo con modelos Essentia/TensorFlow. Desactivado por defecto
# porque requiere dependencias pesadas (essentia-tensorflow) y GPU opcional.
# AUDIO_INTELLIGENCE_BACKEND: "essentia" | "none".
ENABLE_AUDIO_INTELLIGENCE_DEEP = _env_bool("ENABLE_AUDIO_INTELLIGENCE_DEEP", False)
AUDIO_INTELLIGENCE_BACKEND = _env_str("AUDIO_INTELLIGENCE_BACKEND", "none")
ENABLE_AUDIO_MOOD_MODELS = _env_bool("ENABLE_AUDIO_MOOD_MODELS", False)
ENABLE_AUDIO_EMBEDDINGS = _env_bool("ENABLE_AUDIO_EMBEDDINGS", False)
ENABLE_AUDIO_TAGGING_MODELS = _env_bool("ENABLE_AUDIO_TAGGING_MODELS", False)
AUDIO_INTELLIGENCE_ANALYZE_AFTER_IMPORT_BACKGROUND = _env_bool("AUDIO_INTELLIGENCE_ANALYZE_AFTER_IMPORT_BACKGROUND", True)
AUDIO_INTELLIGENCE_RESUME_PENDING_ON_STARTUP = _env_bool("AUDIO_INTELLIGENCE_RESUME_PENDING_ON_STARTUP", True)
AUDIO_INTELLIGENCE_BACKGROUND_AUTOSTART = _env_bool("AUDIO_INTELLIGENCE_BACKGROUND_AUTOSTART", True)
AUDIO_INTELLIGENCE_BACKGROUND = _env_bool("AUDIO_INTELLIGENCE_BACKGROUND", True)
AUDIO_INTELLIGENCE_MAX_WORKERS = _env_int("AUDIO_INTELLIGENCE_MAX_WORKERS", 1, min_val=1, max_val=2)
AUDIO_INTELLIGENCE_BACKGROUND_BATCH_SIZE = _env_int("AUDIO_INTELLIGENCE_BACKGROUND_BATCH_SIZE", 1, min_val=1, max_val=50)
AUDIO_INTELLIGENCE_BACKGROUND_IDLE_DELAY_SEC = _env_float("AUDIO_INTELLIGENCE_BACKGROUND_IDLE_DELAY_SEC", 2.0, min_val=0.0, max_val=3600.0)
# Tiempo maximo de ejecucion del worker de analisis profundo en minutos.
# 0 significa sin limite. Util para entornos con recursos limitados.
AUDIO_INTELLIGENCE_BACKGROUND_MAX_RUNTIME_MIN = _env_int("AUDIO_INTELLIGENCE_BACKGROUND_MAX_RUNTIME_MIN", 0, min_val=0, max_val=1440)
# Directorio donde residen los modelos Essentia. Si esta vacio, el backend
# buscara los modelos en las rutas por defecto de la libreria.
AUDIO_INTELLIGENCE_MODEL_DIR = _env_str("AUDIO_INTELLIGENCE_MODEL_DIR", "")
AUDIO_INTELLIGENCE_ALLOW_MODEL_DOWNLOADS = _env_bool("AUDIO_INTELLIGENCE_ALLOW_MODEL_DOWNLOADS", False)
AUDIO_INTELLIGENCE_SAMPLE_STRATEGY = _env_str("AUDIO_INTELLIGENCE_SAMPLE_STRATEGY", "smart_segments")
AUDIO_INTELLIGENCE_SEGMENT_SECONDS = _env_int("AUDIO_INTELLIGENCE_SEGMENT_SECONDS", 120, min_val=15, max_val=1200)
AUDIO_INTELLIGENCE_REANALYZE_ON_MODEL_CHANGE = _env_bool("AUDIO_INTELLIGENCE_REANALYZE_ON_MODEL_CHANGE", True)
AUDIO_INTELLIGENCE_RETRY_FAILED = _env_bool("AUDIO_INTELLIGENCE_RETRY_FAILED", False)
AUDIO_INTELLIGENCE_MAX_ATTEMPTS = _env_int("AUDIO_INTELLIGENCE_MAX_ATTEMPTS", 1, min_val=1, max_val=20)
AUDIO_INTELLIGENCE_CANCEL_DISCARD_OUTPUTS = _env_bool("AUDIO_INTELLIGENCE_CANCEL_DISCARD_OUTPUTS", False)
AUDIO_INTELLIGENCE_FAIL_SILENTLY = _env_bool("AUDIO_INTELLIGENCE_FAIL_SILENTLY", True)

ENABLE_MUSIC_DISCOVERY = _env_bool("ENABLE_MUSIC_DISCOVERY", True)
MUSIC_DISCOVERY_USE_AUDIO_FEATURES = _env_bool("MUSIC_DISCOVERY_USE_AUDIO_FEATURES", True)
MUSIC_DISCOVERY_USE_DEEP_FEATURES = _env_bool("MUSIC_DISCOVERY_USE_DEEP_FEATURES", True)
MUSIC_DISCOVERY_MIN_CONFIDENCE = _env_float("MUSIC_DISCOVERY_MIN_CONFIDENCE", 0.35, min_val=0.0, max_val=1.0)
MUSIC_DISCOVERY_DEFAULT_LIMIT = _env_int("MUSIC_DISCOVERY_DEFAULT_LIMIT", 25, min_val=1, max_val=200)
MUSIC_DISCOVERY_EXPLAIN_RESULTS = _env_bool("MUSIC_DISCOVERY_EXPLAIN_RESULTS", True)
