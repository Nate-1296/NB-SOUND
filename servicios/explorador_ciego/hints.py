# =============================================================================
# servicios/explorador_ciego/hints.py
#
# Sistema de pistas (hints) y validacion de intentos del Explorador Ciego.
#
# Hints disponibles (en orden de revelacion sugerido):
#   - empieza_con      : "Empieza con la letra X"
#   - termina_con      : "Termina con la letra X"
#   - cantidad_letras  : "Tiene N letras (sin contar espacios)"
#   - cantidad_palabras: "El nombre son N palabras"
#   - alfabeto         : "Esta en alfabeto latino / cirilico / chino / arabe / griego / japones"
#
# Validacion:
#   - Normalizamos ambos lados (NFD + strip de diacriticos + lowercase + colapso
#     de espacios) y comparamos por igualdad estricta + ratio de similitud.
#   - Para idiomas con alfabeto no latino, la comparacion sigue funcionando
#     porque NFD aplica igual; sin embargo, exponemos `requiere_escritura` que
#     vale False para esos titulos: la UI puede ocultar el input.
# =============================================================================

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Optional


# Resultado de un intento de adivinanza.
# - acierto: True si la respuesta es correcta (ratio >= UMBRAL_ACIERTO).
# - cerca:   True si se acerca pero no llega al umbral de acierto (entre
#            UMBRAL_CERCA y UMBRAL_ACIERTO). Util para feedback "muy cerca".
# - ratio:   numero entre 0 y 1, util para tests/depuracion.
UMBRAL_ACIERTO = 0.84
UMBRAL_CERCA = 0.62


# Mapeo de codepoint -> nombre de alfabeto. Solo necesitamos saber si un
# titulo es predominantemente NO latino para ofrecer la salida alternativa
# (botones "La se" / "Me rindo") y evitar pedir que el usuario teclee algo
# que su layout no le permita.
def _alfabeto_codepoint(cp: int) -> str:
    if cp < 0x0080:
        return "latino"
    if 0x0080 <= cp <= 0x024F:
        return "latino"  # extendidos latinos
    if 0x0370 <= cp <= 0x03FF:
        return "griego"
    if 0x0400 <= cp <= 0x04FF:
        return "cirilico"
    if 0x0590 <= cp <= 0x05FF:
        return "hebreo"
    if 0x0600 <= cp <= 0x06FF:
        return "arabe"
    if 0x0900 <= cp <= 0x097F:
        return "devanagari"
    if 0x3040 <= cp <= 0x309F or 0x30A0 <= cp <= 0x30FF:
        return "japones"
    if 0x4E00 <= cp <= 0x9FFF:
        return "chino"
    if 0xAC00 <= cp <= 0xD7AF:
        return "coreano"
    return "otro"


# `normalizar_para_comparar` (y sus ayudantes) viven ahora en la capa hoja
# `utils.text`, para que el pipeline de catalogacion (core, p.ej. dedupe
# observable) y los servicios compartan EXACTAMENTE el mismo algoritmo sin
# invertir dependencias (core no debe importar de servicios). Se re-exporta
# aqui para conservar la API publica historica de este modulo.
from utils.text import normalizar_para_comparar  # noqa: E402,F401


def detectar_alfabeto(texto: str) -> str:
    """Devuelve el alfabeto dominante en el texto.

    "Dominante": el que tiene mas codepoints alfabeticos. Numeros y
    puntuacion se ignoran. Si no hay caracteres alfabeticos, devolvemos
    "latino" por defecto (compatible con la UI por defecto).
    """
    if not texto:
        return "latino"
    contador: dict[str, int] = {}
    for ch in str(texto):
        if not ch.isalpha():
            continue
        nombre = _alfabeto_codepoint(ord(ch))
        contador[nombre] = contador.get(nombre, 0) + 1
    if not contador:
        return "latino"
    return max(contador.items(), key=lambda kv: kv[1])[0]


def requiere_escritura(titulo: str) -> bool:
    """True si la UI puede ofrecer un input para escribir el titulo.

    Solo recomendamos input cuando TODOS los caracteres alfabeticos son
    latinos. Si aunque sea uno es de otro alfabeto (cirilico, chino,
    coreano, etc.) el usuario tipico no podra teclearlo facilmente y la
    experiencia se rompe — preferimos el boton "¡La se!" como salida.

    Caracteres no alfabeticos (espacios, numeros, puntuacion, simbolos)
    no afectan: solo miramos `isalpha()`.
    """
    if not titulo:
        return True  # vacio: sin restriccion, dejamos el flujo normal
    for ch in str(titulo):
        if not ch.isalpha():
            continue
        if _alfabeto_codepoint(ord(ch)) != "latino":
            return False
    return True


def validar_intento(titulo_real: str, intento: str) -> dict:
    """Compara un intento del usuario contra el titulo real.

    Retorna:
      {"acierto": bool, "cerca": bool, "ratio": float}

    Es deliberadamente tolerante: el juego deberia premiar la cercania, no
    pedir transcripcion exacta. Recuerda que normalizamos ambos lados antes
    de comparar.
    """
    norm_real = normalizar_para_comparar(titulo_real)
    norm_intento = normalizar_para_comparar(intento)
    if not norm_real or not norm_intento:
        return {"acierto": False, "cerca": False, "ratio": 0.0}
    if norm_real == norm_intento:
        return {"acierto": True, "cerca": False, "ratio": 1.0}
    # SequenceMatcher es O(n*m). Truncamos a 200 chars para no degradarse
    # con titulos absurdamente largos (raros en musica pero existen).
    ratio = difflib.SequenceMatcher(None, norm_real[:200], norm_intento[:200]).ratio()
    return {
        "acierto": ratio >= UMBRAL_ACIERTO,
        "cerca": UMBRAL_CERCA <= ratio < UMBRAL_ACIERTO,
        "ratio": float(round(ratio, 4)),
    }


# ── Hints sobre el titulo ─────────────────────────────────────────────────


def _primera_letra_significativa(texto: str) -> Optional[str]:
    """Primera letra/digito que aparece, ignorando puntuacion y espacios.

    "(I Can't Get No) Satisfaction" -> "I"
    """
    for ch in (texto or ""):
        if ch.isalnum():
            return ch
    return None


def _ultima_letra_significativa(texto: str) -> Optional[str]:
    for ch in reversed(texto or ""):
        if ch.isalnum():
            return ch
    return None


def hint_empieza_con(titulo: str) -> Optional[str]:
    letra = _primera_letra_significativa(titulo)
    if not letra:
        return None
    return letra.upper()


def hint_termina_con(titulo: str) -> Optional[str]:
    letra = _ultima_letra_significativa(titulo)
    if not letra:
        return None
    return letra.upper()


def hint_cantidad_palabras(titulo: str) -> int:
    if not titulo:
        return 0
    return len([p for p in titulo.split() if p.strip()])


def hint_cantidad_letras(titulo: str, *, contar_espacios: bool = False) -> int:
    """Cuenta caracteres alfanumericos del titulo.

    Por defecto NO cuenta espacios ni puntuacion: el numero es mas util
    para el jugador (representa "longitud del nombre").
    """
    if not titulo:
        return 0
    if contar_espacios:
        return len(titulo)
    return sum(1 for c in titulo if c.isalnum())


def generar_hints(titulo: str) -> dict:
    """Empaqueta todas las hints disponibles para un titulo.

    Las hints son acumulativas: la UI muestra solo las que el usuario va
    desbloqueando. El servicio no decide el orden — solo entrega el catalogo.
    """
    return {
        "alfabeto": detectar_alfabeto(titulo),
        "requiere_escritura": requiere_escritura(titulo),
        "empieza_con": hint_empieza_con(titulo) or "",
        "termina_con": hint_termina_con(titulo) or "",
        "cantidad_palabras": int(hint_cantidad_palabras(titulo)),
        "cantidad_letras": int(hint_cantidad_letras(titulo)),
        "cantidad_letras_total": int(hint_cantidad_letras(titulo, contar_espacios=True)),
    }
