# =============================================================================
# utils/text.py
#
# Utilidades de manipulacion y normalizacion de texto para el tagger.
# Todas las funciones son puras y sin efectos secundarios.
#
# Novedades v3:
#   - limpiar_basura_descarga(): elimina marcas de sitios de pirateria del
#     nombre del archivo (spotdown.org, mp3paw, etc.) usando regex robusto.
#   - normalizar_titulo() ahora invoca limpiar_basura_descarga() internamente.
#   - parsear_nombre_archivo() pre-procesa con limpiar_basura_descarga().
#   - similitud_trigrama() mejorada para nombres cortos.
# =============================================================================

import re
import unicodedata
from typing import Optional

from config.settings import (
    FEATURING_VARIANTS,
    PROMO_SUFFIXES,
    SLUG_SEPARATOR,
    SLUG_MAX_LENGTH,
    VERSION_KEYWORDS,
)


# =============================================================================
# NORMALIZACION UNICODE Y LIMPIEZA BASE
# =============================================================================

def eliminar_acentos(texto: str) -> str:
    """
    Convierte caracteres con tilde o diacresis a su equivalente ASCII.
    Ejemplo: 'cafe' -> 'cafe', 'Nono' -> 'Nono'
    """
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def limpiar_espacios(texto: str) -> str:
    """Colapsa espacios multiples y elimina espacios al inicio y fin."""
    return re.sub(r"\s+", " ", texto).strip()


def limpiar_caracteres_control(texto: str) -> str:
    """Elimina caracteres de control y no imprimibles."""
    return "".join(c for c in texto if unicodedata.category(c) != "Cc")


def normalizar_base(texto: str) -> str:
    """
    Limpieza base aplicada a cualquier campo de metadata antes de procesar.
    Elimina caracteres de control y colapsa espacios. Preserva acentos.
    """
    if not texto:
        return ""
    texto = limpiar_caracteres_control(texto)
    texto = limpiar_espacios(texto)
    return texto


# =============================================================================
# LIMPIEZA DE MARCAS DE SITIOS DE DESCARGA
# =============================================================================

# Patron regex que captura cualquier variante de la marca "spotdown.org"
# y otros dominios de descarga conocidos dentro de corchetes, parentesis
# o como texto libre al final del nombre.
_RE_SITIOS_DESCARGA = re.compile(
    r"[\[\(]?"
    r"\s*(?:www\.)?"
    r"(?:"
    r"spotdown\.org"
    r"|mp3paw\.(?:com|cc|io)"
    r"|mp3juice\.(?:cc|se|tel)"
    r"|zippyshare\.com"
    r"|freemusicdownload\.[a-z]+"
    r"|mp3\.pm"
    r"|mp3skull\.[a-z]+"
    r"|mr-jatt\.[a-z]+"
    r"|songspk\.[a-z]+"
    r"|downloadming\.[a-z]+"
    r")"
    r"\s*[\]\)]?",
    re.IGNORECASE,
)

# Cualquier dominio generico entre corchetes que parezca un sitio de descarga
# (patron mas agresivo — solo aplica entre corchetes o parentesis)
_RE_DOMINIO_GENERICO_BRACKETS = re.compile(
    r"[\[\(]\s*(?:www\.)?[\w\-]+\.(?:org|com|cc|io|net|me)\s*[\]\)]",
    re.IGNORECASE,
)


def limpiar_basura_descarga(texto: str) -> str:
    """
    Elimina marcas de sitios de descarga del nombre de un archivo o tag.

    Cubre variantes como:
        'Song [spotdown.org].mp3'
        'Song (spotdown.org)'
        'Song [www.spotdown.org]'
        'Song spotdown.org - Artist'
        'Song [mp3paw.com]'

    No elimina dominios que no esten en la lista de sitios conocidos a menos
    que esten entre corchetes o parentesis (para evitar falsos positivos con
    nombres artisticos tipo "website.band").
    """
    if not texto:
        return texto

    # Primero eliminar dominios conocidos en cualquier posicion
    texto = _RE_SITIOS_DESCARGA.sub(" ", texto)

    # Luego eliminar cualquier dominio generico entre corchetes/parentesis
    texto = _RE_DOMINIO_GENERICO_BRACKETS.sub(" ", texto)

    return limpiar_espacios(texto)


# =============================================================================
# CONSTRUCCION DE SLUGS
# =============================================================================

_RE_UNDERSCORES_MULTIPLES = re.compile(r"_+")
_RE_ESPACIOS = re.compile(r"\s+")
_CARACTERES_INVALIDOS_RUTA = set('<>:"/\\|?*')


def construir_slug(texto: str, max_longitud: int = SLUG_MAX_LENGTH) -> str:
    """
    Convierte un texto arbitrario en un slug estable para uso en rutas.
    Resultado: minusculas, unicode-safe, filesystem-safe, separado por guion bajo.
    """
    if not texto:
        return "sin_titulo"

    base = unicodedata.normalize("NFKC", str(texto))
    base = _RE_ESPACIOS.sub(" ", base).strip().lower()
    if not base:
        return "sin_titulo"

    slug_chars: list[str] = []
    for c in base:
        categoria = unicodedata.category(c)

        # Mantener letras y numeros de cualquier alfabeto Unicode.
        if categoria[0] in {"L", "N"}:
            slug_chars.append(c)
            continue

        # Mantener marcas combinantes solo si siguen a un caracter util.
        if categoria[0] == "M" and slug_chars and slug_chars[-1] != "_":
            slug_chars.append(c)
            continue

        # Separadores y puntuacion comun se normalizan a "_".
        if c.isspace() or c in {"-", "_", "."}:
            slug_chars.append("_")
            continue

        # Caracteres invalidos para rutas o categorias no imprimibles.
        if c in _CARACTERES_INVALIDOS_RUTA or categoria[0] == "C":
            slug_chars.append("_")
            continue

        # Resto de simbolos/puntuacion: separador neutro.
        if categoria[0] in {"P", "S"}:
            slug_chars.append("_")
            continue

    slug = "".join(slug_chars)
    slug = _RE_UNDERSCORES_MULTIPLES.sub("_", slug).strip("._ ")

    if not slug:
        return "sin_titulo"

    slug = slug[:max_longitud].rstrip("._ ")
    return slug or "sin_titulo"


def construir_slug_artista(nombre: str) -> str:
    return construir_slug(nombre)


def construir_slug_album(nombre: str) -> str:
    return construir_slug(nombre)


# =============================================================================
# NORMALIZACION PARA MATCHING
# =============================================================================

def para_comparacion(texto: str) -> str:
    """
    Prepara un texto para comparacion difusa:
    minusculas, sin acentos, sin simbolos, espacios normalizados.
    """
    if not texto:
        return ""
    texto = texto.lower()
    texto = eliminar_acentos(texto)
    texto = re.sub(r"[^\w\s]", " ", texto)
    texto = limpiar_espacios(texto)
    return texto


# -----------------------------------------------------------------------------
# Normalizacion tolerante para comparacion de titulos/artistas/albumes.
#
# Vive en esta capa hoja (utils) —y no en servicios— porque tanto el pipeline
# de catalogacion (core, p.ej. dedupe observable) como los servicios de la UI
# (explorador ciego, dedupe periodico) necesitan EL MISMO algoritmo. Mantenerlo
# aqui evita invertir la dependencia core->servicios. `hints.py` lo re-exporta
# para conservar su API publica historica; su suite de tests valida el contrato.
# -----------------------------------------------------------------------------

_RE_NORMALIZAR_SPACES = re.compile(r"\s+")
_RE_PUNTUACION = re.compile(r"[^\w\s]", re.UNICODE)

_REEMPLAZOS_PRENORMAL = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",  # comilla simple
    "ʼ": "'", "`": "'",                      # modifier letter / backtick
    "“": '"', "”": '"', "„": '"', "‟": '"',  # comillas dobles
    "«": '"', "»": '"',                      # << >>
    "–": "-", "—": "-", "−": "-", "‐": "-",  # guiones (en-dash, em-dash, etc.)
    "…": "...",                              # ellipsis
}


def _prenormalizar(texto: str) -> str:
    """Normaliza variantes Unicode antes del strip de puntuacion."""
    out = []
    for ch in str(texto or ""):
        out.append(_REEMPLAZOS_PRENORMAL.get(ch, ch))
    return "".join(out)


def normalizar_para_comparar(texto: str) -> str:
    """Normaliza para comparacion tolerante.

    Pipeline:
      1. Pre-normalizar comillas/guiones curvos a su forma ASCII.
      2. NFD + strip de diacriticos -> "Cancion" == "Cancion".
      3. Strip de puntuacion (cada signo -> espacio).
      4. Colapso de espacios + lowercase.

    Deliberadamente permisivo. Ejemplos (ver tests de explorador ciego):
      "Cancion"      -> "cancion"
      "Don't Stop"   -> "don t stop"
      "   hola  x  " -> "hola x"
    """
    if not texto:
        return ""
    pre = _prenormalizar(texto)
    nfd = unicodedata.normalize("NFD", pre)
    sin_diacriticos = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    sin_puntuacion = _RE_PUNTUACION.sub(" ", sin_diacriticos)
    colapsado = _RE_NORMALIZAR_SPACES.sub(" ", sin_puntuacion).strip().lower()
    return colapsado


def normalizar_titulo(titulo: str) -> str:
    """
    Limpieza completa de un titulo de cancion para prepararlo para matching.
    Elimina marcas de descarga, sufijos promocionales, parentesis vacios
    y texto decorativo.
    """
    if not titulo:
        return ""

    # Primero eliminar marcas de sitios de descarga (spotdown, etc.)
    titulo = limpiar_basura_descarga(titulo)
    titulo = normalizar_base(titulo)
    titulo_lower = titulo.lower()

    for sufijo in PROMO_SUFFIXES:
        if sufijo in titulo_lower:
            idx = titulo_lower.find(sufijo)
            titulo = titulo[:idx].strip()
            titulo_lower = titulo.lower()

    # Eliminar parentesis y corchetes vacios
    titulo = re.sub(r"\(\s*\)", "", titulo)
    titulo = re.sub(r"\[\s*\]", "", titulo)
    titulo = limpiar_espacios(titulo)

    return titulo


def limpiar_version_titulo(titulo: str) -> str:
    """
    Devuelve el titulo base eliminando anotaciones de version entre parentesis
    o corchetes que contengan palabras clave de version.

    Ejemplo:
        'Come Together (2019 Mix)'    -> 'Come Together'
        'Hotel California (Remaster)' -> 'Hotel California'
        'Something (feat. Ringo)'     -> 'Something (feat. Ringo)'  # no toca feat
    """
    if not titulo:
        return titulo

    patron_version = re.compile(
        r"\s*[\(\[]\s*(?:" +
        "|".join(re.escape(kw) for kw in sorted(VERSION_KEYWORDS, key=len, reverse=True)) +
        r")[^\)\]]*[\)\]]",
        re.IGNORECASE,
    )
    resultado = patron_version.sub("", titulo).strip()
    return resultado if resultado else titulo


def normalizar_artista(artista: str) -> str:
    """
    Limpieza de nombre de artista: elimina featuring embebido y decoraciones.
    """
    if not artista:
        return ""

    artista = normalizar_base(artista)
    artista = separar_artista_principal(artista)[0]
    artista = limpiar_espacios(artista)

    return artista


# =============================================================================
# MANEJO DE FEATURING
# =============================================================================

_RE_FEAT_SPLIT = re.compile(
    r"\s*[\(\[]?\s*(?:featuring|feat\.?|ft\.?|with|w/)\s+",
    re.IGNORECASE
)


def separar_artista_principal(texto: str) -> tuple[str, Optional[str]]:
    """
    Separa el artista principal del featuring embebido.

    Ejemplos:
        'Drake feat. Future'  -> ('Drake', 'Future')
        'Jay-Z ft. Kanye'     -> ('Jay-Z', 'Kanye')
        'Radiohead'           -> ('Radiohead', None)
    """
    if not texto:
        return ("", None)

    partes = _RE_FEAT_SPLIT.split(texto, maxsplit=1)
    if len(partes) == 2:
        principal     = partes[0].strip().rstrip("([ ")
        colaboradores = partes[1].strip().rstrip("])")
        return (principal, colaboradores)

    return (texto.strip(), None)


def extraer_featuring_del_titulo(titulo: str) -> tuple[str, Optional[str]]:
    """
    Extrae informacion de featuring embebida en el titulo.

    Ejemplos:
        'Umbrella (feat. Jay-Z)'  -> ('Umbrella', 'Jay-Z')
        'Title [ft. Artist]'      -> ('Title', 'Artist')
    """
    if not titulo:
        return ("", None)

    patron = re.compile(
        r"[\(\[]\s*(?:featuring|feat\.?|ft\.?|with)\s+([^\)\]]+)[\)\]]",
        re.IGNORECASE
    )
    match = patron.search(titulo)
    if match:
        featuring     = match.group(1).strip()
        titulo_limpio = patron.sub("", titulo).strip()
        titulo_limpio = limpiar_espacios(titulo_limpio)
        return (titulo_limpio, featuring)

    return (titulo.strip(), None)


# =============================================================================
# PARSEO DE NOMBRE DE ARCHIVO
# =============================================================================

_PATRON_ARTISTA_TITULO   = re.compile(r"^(.+?)\s*-\s*(.+)$")
_PATRON_NUM_TITULO       = re.compile(r"^(\d{1,3})[.\-\s_]+(.+)$")
_PATRON_ARTISTA_NUM_TITU = re.compile(r"^(.+?)\s*-\s*(\d{2})\s*[-_.]\s*(.+)$")
_RE_EXTENSION            = re.compile(r"\.[a-zA-Z0-9]{2,5}$")


def parsear_nombre_archivo(nombre: str) -> dict[str, Optional[str]]:
    """
    Intenta inferir artista, titulo y numero de pista desde el nombre del archivo.
    Util como fallback cuando los tags ID3 estan vacios o son incorrectos.

    Pre-procesa el nombre eliminando marcas de sitios de descarga (spotdown, etc.)
    antes de aplicar los patrones de parseo.

    Retorna dict con claves: 'artista', 'titulo', 'track_number'.
    Los valores no encontrados seran None.

    Patrones soportados:
        'Artist - Title.mp3'
        'Artist - 01 - Title.mp3'
        '01. Title.mp3'
        '01_Title.mp3'
        'Artist_Title.mp3'   (guion bajo como separador)
    """
    resultado: dict[str, Optional[str]] = {
        "artista":      None,
        "titulo":       None,
        "track_number": None,
    }

    if not nombre:
        return resultado

    # Eliminar extension y normalizar el nombre base
    base = _RE_EXTENSION.sub("", nombre)
    base = base.replace("_", " ").strip()

    # Limpiar marcas de sitios de descarga antes de parsear
    base = limpiar_basura_descarga(base)

    # Eliminar corchetes con contenido generico residual
    base = re.sub(r"\s*\[.*?\]\s*", " ", base)
    base = limpiar_espacios(base)

    # Patron: "Artist - 01 - Title"  o  "Artist - 01. Title"
    m = _PATRON_ARTISTA_NUM_TITU.match(base)
    if m:
        resultado["artista"]      = limpiar_espacios(m.group(1))
        resultado["track_number"] = m.group(2)
        resultado["titulo"]       = limpiar_espacios(m.group(3))
        return _limpiar_resultado_filename(resultado)

    # Patron: "Artist - Title"
    m = _PATRON_ARTISTA_TITULO.match(base)
    if m:
        posible_artista = limpiar_espacios(m.group(1))
        posible_titulo  = limpiar_espacios(m.group(2))
        if not re.match(r"^\d+$", posible_artista):
            resultado["artista"] = posible_artista
            resultado["titulo"]  = posible_titulo
            return _limpiar_resultado_filename(resultado)

    # Patron: "01. Title"  o  "01 - Title"  o  "01_Title"
    m = _PATRON_NUM_TITULO.match(base)
    if m:
        numero = m.group(1)
        if 1 <= int(numero) <= 99:
            resultado["track_number"] = numero
            resultado["titulo"]       = limpiar_espacios(m.group(2))
            return _limpiar_resultado_filename(resultado)

    # Sin patron reconocido: usar todo como titulo
    resultado["titulo"] = base
    return _limpiar_resultado_filename(resultado)


def _limpiar_resultado_filename(
    resultado: dict[str, Optional[str]],
) -> dict[str, Optional[str]]:
    """Aplica limpieza final a los campos extraidos del nombre de archivo."""
    for campo in ("artista", "titulo"):
        valor = resultado.get(campo)
        if valor:
            valor = normalizar_titulo(valor)
            resultado[campo] = valor if valor else None
    return resultado


# =============================================================================
# SIMILITUD DE CADENAS
# =============================================================================

def similitud_tokens(a: str, b: str) -> float:
    """
    Similitud basada en tokens compartidos (Jaccard).
    Util para titulos con palabras en distinto orden.
    """
    if not a or not b:
        return 0.0

    tokens_a = set(para_comparacion(a).split())
    tokens_b = set(para_comparacion(b).split())

    if not tokens_a or not tokens_b:
        return 0.0

    interseccion = tokens_a & tokens_b
    union        = tokens_a | tokens_b

    return len(interseccion) / len(union)


def similitud_secuencial(a: str, b: str) -> float:
    """
    Similitud de edicion via SequenceMatcher.
    Util para nombres con variaciones menores.
    """
    from difflib import SequenceMatcher

    if not a or not b:
        return 0.0

    a_norm = para_comparacion(a)
    b_norm = para_comparacion(b)

    return SequenceMatcher(None, a_norm, b_norm).ratio()


def similitud_trigrama(a: str, b: str) -> float:
    """
    Similitud basada en trigramas de caracteres.
    Especialmente buena para detectar errores de tipeo y variaciones ortograficas.
    Para cadenas muy cortas (menos de 3 caracteres normalizados) recurre
    a similitud_secuencial para evitar resultados erroneos.
    """
    if not a or not b:
        return 0.0

    a_norm = para_comparacion(a)
    b_norm = para_comparacion(b)

    if len(a_norm) < 3 or len(b_norm) < 3:
        return similitud_secuencial(a, b)

    def trigramas(s: str) -> set[str]:
        return {s[i:i+3] for i in range(len(s) - 2)}

    tg_a = trigramas(a_norm)
    tg_b = trigramas(b_norm)

    if not tg_a or not tg_b:
        return 0.0

    interseccion = tg_a & tg_b
    union        = tg_a | tg_b
    return len(interseccion) / len(union)


def similitud_combinada(a: str, b: str) -> float:
    """
    Combina tres metricas de similitud para mayor robustez frente a
    variaciones de formato, typos y palabras reordenadas.

    Ponderacion:
      - Secuencial (50%): buena para nombres exactos con pequenas variaciones
      - Tokens     (35%): buena para titulos con palabras en distinto orden
      - Trigrama   (15%): buena para typos y variaciones ortograficas
    """
    if not a or not b:
        return 0.0

    tokens     = similitud_tokens(a, b)
    secuencial = similitud_secuencial(a, b)
    trigrama   = similitud_trigrama(a, b)

    return round(
        (secuencial * 0.50) + (tokens * 0.35) + (trigrama * 0.15),
        4,
    )


# =============================================================================
# UTILES VARIOS
# =============================================================================

_PATRON_ANIO = re.compile(r"\b(19[0-9]{2}|20[0-2][0-9])\b")


def extraer_anio_del_texto(valor: str) -> Optional[int]:
    """
    Extrae un año de 4 digitos de un campo de texto.
    Maneja: '2003', '2003-01-15', 'ID3v2.4: 2003', etc.
    """
    if not valor:
        return None
    match = _PATRON_ANIO.search(str(valor))
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def limpiar_numero_pista(valor: str) -> Optional[int]:
    """
    Extrae el numero de pista de un campo '3/12' o '3'.
    Retorna None si no es parseable.
    """
    if not valor:
        return None
    partes = str(valor).split("/")
    try:
        numero = int(partes[0].strip())
        return numero if 1 <= numero <= 999 else None
    except (ValueError, TypeError):
        return None


def formatear_duracion(segundos: float) -> str:
    """Convierte segundos a formato legible mm:ss."""
    minutos = int(segundos) // 60
    segs    = int(segundos) % 60
    return f"{minutos}:{segs:02d}"


def es_cadena_vacia_o_nula(valor: Optional[str]) -> bool:
    """Verifica si un valor de tag es efectivamente vacio."""
    if valor is None:
        return True
    return len(valor.strip()) == 0


def normalizar_isrc(isrc: str) -> Optional[str]:
    """
    Normaliza un codigo ISRC eliminando espacios y guiones, y convirtiendo
    a mayusculas. Retorna None si el formato no es valido.
    Formato valido: CC-XXX-YY-NNNNN (o sin separadores: 12 caracteres alfanumericos)
    """
    if not isrc:
        return None

    limpio = re.sub(r"[\s\-]", "", isrc).upper()
    # Un ISRC valido tiene exactamente 12 caracteres alfanumericos
    if re.match(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$", limpio):
        return limpio
    return None


# =============================================================================
# DETECCION DE VARIANTES EN TITULOS (v3.3)
# =============================================================================

# Mapeo: tipo_variante -> patron regex que lo detecta dentro del titulo
_VARIANTE_PATRONES: dict[str, re.Pattern] = {
    "Remix": re.compile(
        r"[\(\[]\s*(?:[^\)\]]*\s+)?(?:remix|rmx|rework|bootleg|flip|dub mix|club mix|radio mix|extended mix|[a-z]+ mix)"
        r"(?:\s[^\)\]]*)?[\)\]]"
        r"|\b(?:remix|rmx)\b",
        re.IGNORECASE,
    ),
    "Live": re.compile(
        r"[\(\[]\s*(?:live|en vivo|ao vivo|en directo|concert|concierto|tour)(?:[^\)\]]*)?[\)\]]"
        r"|\blive\b",
        re.IGNORECASE,
    ),
    "Acoustic": re.compile(
        r"[\(\[]\s*acoustic(?:\s+[^\)\]]*)?[\)\]]"
        r"|\bacoustic(?:\s+version)?\b",
        re.IGNORECASE,
    ),
    "Instrumental": re.compile(
        r"[\(\[]\s*instrumental(?:\s+[^\)\]]*)?[\)\]]"
        r"|\binstrumental\b",
        re.IGNORECASE,
    ),
    "Demo": re.compile(
        r"[\(\[]\s*demo(?:\s+[^\)\]]*)?[\)\]]"
        r"|\bdemo\b",
        re.IGNORECASE,
    ),
}

# Patron para extraer el bloque de variante del titulo
_RE_VARIANTE_BLOQUE = re.compile(
    r"\s*[\(\[]\s*(?:"
    r"(?:[^\)\]]*\s+)?(?:remix|rmx|rework|bootleg|flip|[a-z]+ mix)"
    r"|live(?:\s+[^\)\]]*)?"
    r"|en vivo(?:\s+[^\)\]])?"
    r"|acoustic(?:\s+version)?"
    r"|instrumental"
    r"|demo(?:\s+version)?"
    r")\s*[\)\]]",
    re.IGNORECASE,
)


def detectar_tipo_variante(titulo: str) -> Optional[str]:
    """
    Detecta si un titulo contiene una anotacion de variante conocida.

    Retorna el tipo de variante normalizado (ej. 'Remix', 'Live', 'Acoustic')
    o None si el titulo no contiene ninguna variante reconocida.

    Ejemplos:
        'Song (Remix)'             -> 'Remix'
        'Song (Live at Wembley)'   -> 'Live'
        'Song (Acoustic Version)'  -> 'Acoustic'
        'Song'                     -> None
    """
    if not titulo:
        return None
    for tipo, patron in _VARIANTE_PATRONES.items():
        if patron.search(titulo):
            return tipo
    return None


def parsear_variante_titulo(titulo: str) -> tuple[str, Optional[str]]:
    """
    Separa el titulo base de su anotacion de variante.

    Retorna (titulo_base, tipo_variante_o_None).

    Ejemplos:
        'Song (Remix)'             -> ('Song', 'Remix')
        'Song (Live at Wembley)'   -> ('Song', 'Live')
        'Song (feat. A) (Remix)'   -> ('Song (feat. A)', 'Remix')
        'Song'                     -> ('Song', None)
    """
    if not titulo:
        return (titulo, None)

    tipo = detectar_tipo_variante(titulo)
    if tipo is None:
        return (titulo, None)

    # Extraer el titulo sin el bloque de variante
    titulo_base = _RE_VARIANTE_BLOQUE.sub("", titulo).strip()
    return (titulo_base or titulo, tipo)


# =============================================================================
# VALIDACION DE PATHS (v3.4)
# =============================================================================

from pathlib import Path
from typing import Optional as _Optional


def validar_path_seguro(
    ruta,
    base_permitida = None,
) -> tuple[bool, str]:
    """
    Valida que una ruta sea "segura" — no contiene traversal o componentes
    problemáticos. Diseñado para rutas que vienen de metadata o entrada de usuario.
    
    Args:
        ruta: La ruta a validar (str o Path, puede ser relativa o absoluta)
        base_permitida: Si se proporciona (str o Path), valida que la ruta esté bajo este directorio
        
    Returns:
        (es_valida, mensaje_error_o_vacio)
        
    Validaciones:
        - No contiene ".." (path traversal)
        - No es ruta vacía
        - Si base_permitida, verifica que ruta.resolve() esté bajo base_permitida.resolve()
    """
    # Convertir a Path si es string
    if isinstance(ruta, str):
        if not ruta or not ruta.strip():
            return False, "Path no puede estar vacío"
        ruta_obj = Path(ruta)
    else:
        ruta_obj = ruta
    
    try:
        # Resolver puntos (./) y enlaces simbólicos
        ruta_abs = ruta_obj.resolve()
    except (OSError, RuntimeError) as e:
        return False, f"No se puede resolver path: {e}"
    
    # Verificar componentes peligrosos ANTES de resolver
    # (para detectar ".." incluso si no existe la ruta)
    if ".." in ruta_obj.parts:
        return False, "Path contiene '..' (path traversal detectado)"
    
    # Validar contra base si se proporciona
    if base_permitida is not None:
        if isinstance(base_permitida, str):
            base_permitida = Path(base_permitida)
        try:
            base_abs = base_permitida.resolve()
            # Verificar que ruta_abs esté bajo base_abs
            ruta_abs.relative_to(base_abs)  # Lanza ValueError si no está bajo base
        except ValueError:
            return False, f"Path '{ruta}' está fuera del directorio permitido: {base_permitida}"
        except (OSError, RuntimeError) as e:
            return False, f"Error validando path contra base: {e}"
    
    return True, ""
