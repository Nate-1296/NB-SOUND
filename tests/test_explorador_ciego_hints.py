"""Tests del modulo de hints/validacion del Explorador Ciego.

Cubre:
  - Normalizacion tolerante (NFD, puntuacion, espacios).
  - Validacion de intentos (acierto exacto, acierto cercano, "muy cerca", lejos).
  - Generadores de hints (empieza_con, termina_con, cantidad_*).
  - Deteccion de alfabeto (latino, cirilico, chino, etc.).
  - Regla `requiere_escritura` (solo latino -> True).

Estos tests son 100% puros (no tocan BD ni Qt).
"""
from __future__ import annotations

import pytest

from servicios.explorador_ciego import (
    detectar_alfabeto,
    generar_hints,
    normalizar_para_comparar,
    requiere_escritura,
    validar_intento,
)
from servicios.explorador_ciego.hints import (
    UMBRAL_ACIERTO,
    UMBRAL_CERCA,
    hint_cantidad_letras,
    hint_cantidad_palabras,
    hint_empieza_con,
    hint_termina_con,
)


# ── Normalizacion ────────────────────────────────────────────────────────

def test_normalizar_quita_diacriticos():
    assert normalizar_para_comparar("Canción") == "cancion"
    assert normalizar_para_comparar("café") == "cafe"
    assert normalizar_para_comparar("Niño") == "nino"


def test_normalizar_quita_puntuacion():
    assert normalizar_para_comparar("Don't Stop") == "don t stop"
    assert normalizar_para_comparar("(I Can't Get No) Satisfaction") == "i can t get no satisfaction"


def test_normalizar_colapsa_espacios():
    assert normalizar_para_comparar("   hola    mundo  ") == "hola mundo"


def test_normalizar_vacio_es_vacio():
    assert normalizar_para_comparar("") == ""
    assert normalizar_para_comparar(None) == ""


# ── Validacion de intentos ───────────────────────────────────────────────

def test_validar_acierto_exacto():
    r = validar_intento("Yesterday", "Yesterday")
    assert r["acierto"] is True
    assert r["ratio"] == 1.0


def test_validar_acierto_case_insensitive():
    r = validar_intento("Yesterday", "yesterday")
    assert r["acierto"] is True


def test_validar_acierto_con_acentos():
    r = validar_intento("Canción del Mar", "cancion del mar")
    assert r["acierto"] is True


def test_validar_acierto_con_puntuacion():
    r = validar_intento("Don't Stop Believin'", "dont stop believin")
    assert r["acierto"] is True


def test_validar_acierto_apostrofes_curvos_vs_ascii():
    """Apostrofe curvo 'right' (U+2019) debe igualar al apostrofe ASCII."""
    r = validar_intento("Don’t Stop", "Don't Stop")
    assert r["acierto"] is True


def test_validar_acierto_comillas_dobles_distintas():
    r = validar_intento("“Hello” World", '"Hello" World')
    assert r["acierto"] is True


def test_validar_acierto_guiones_distintos():
    """Em-dash (U+2014) y en-dash (U+2013) se igualan al guion ASCII."""
    r = validar_intento("Rock—Roll Symphony", "Rock-Roll Symphony")
    assert r["acierto"] is True


def test_validar_acierto_sin_apostrofe_vs_con():
    """El usuario que olvida el apostrofe debe acertar igual."""
    r = validar_intento("We Are Never Ever Getting Back Together",
                        "we are never ever getting back together")
    assert r["acierto"] is True


def test_validar_cercano_es_acierto():
    """Una letra mal es aceptable: el juego es tolerante."""
    r = validar_intento("Bohemian Rhapsody", "Bohemia Rapsody")
    assert r["acierto"] is True


def test_validar_lejano_no_es_acierto():
    r = validar_intento("Bohemian Rhapsody", "Imagine")
    assert r["acierto"] is False
    assert r["cerca"] is False


def test_validar_intermedio_es_cerca():
    """Un titulo parcial debe activar la franja `cerca` (entre umbrales)."""
    real = "Stairway to Heaven"
    # "Stairway Heaven" omite la preposicion: cerca pero no acierto.
    r = validar_intento(real, "Stairway Heaven")
    assert (r["cerca"] and not r["acierto"]) or r["acierto"]


def test_validar_vacio_no_es_acierto():
    r = validar_intento("Yesterday", "")
    assert r["acierto"] is False
    assert r["ratio"] == 0.0


def test_validar_titulo_vacio_no_es_acierto():
    r = validar_intento("", "algo")
    assert r["acierto"] is False


def test_umbrales_son_consistentes():
    """Documenta los umbrales y verifica que `cerca` < `acierto`."""
    assert UMBRAL_CERCA < UMBRAL_ACIERTO
    assert 0.0 < UMBRAL_CERCA < 1.0
    assert 0.0 < UMBRAL_ACIERTO < 1.0


# ── Hint: empieza_con / termina_con ──────────────────────────────────────

def test_empieza_con_letra_normal():
    assert hint_empieza_con("Yesterday") == "Y"


def test_empieza_con_ignora_puntuacion():
    assert hint_empieza_con("(I Can't Get No) Satisfaction") == "I"


def test_empieza_con_minuscula_devuelve_mayuscula():
    assert hint_empieza_con("yesterday") == "Y"


def test_empieza_con_numero():
    assert hint_empieza_con("99 Luftballons") == "9"


def test_empieza_con_vacio_es_none():
    assert hint_empieza_con("") is None
    assert hint_empieza_con("...") is None


def test_termina_con_letra_normal():
    assert hint_termina_con("Yesterday") == "Y"
    assert hint_termina_con("Imagine") == "E"


def test_termina_con_ignora_puntuacion_final():
    assert hint_termina_con("Hello!") == "O"
    assert hint_termina_con("Question?") == "N"


# ── Hint: cantidad_palabras / cantidad_letras ───────────────────────────

def test_cantidad_palabras_simple():
    assert hint_cantidad_palabras("Yesterday") == 1
    assert hint_cantidad_palabras("Bohemian Rhapsody") == 2
    assert hint_cantidad_palabras("Stairway to Heaven") == 3


def test_cantidad_palabras_vacio():
    assert hint_cantidad_palabras("") == 0


def test_cantidad_letras_sin_espacios_por_defecto():
    # "Hello World" -> 10 letras (sin contar espacio).
    assert hint_cantidad_letras("Hello World") == 10


def test_cantidad_letras_incluye_numeros():
    assert hint_cantidad_letras("99 Luftballons") == 13  # 2 + 11


def test_cantidad_letras_total_incluye_espacios():
    assert hint_cantidad_letras("Hello World", contar_espacios=True) == 11


def test_cantidad_letras_ignora_puntuacion():
    # ! y ? no son alfanumericos.
    assert hint_cantidad_letras("Hello!") == 5
    assert hint_cantidad_letras("Don't!") == 4


# ── Detector de alfabeto ─────────────────────────────────────────────────

def test_alfabeto_latino_default():
    assert detectar_alfabeto("Yesterday") == "latino"
    assert detectar_alfabeto("Niño") == "latino"


def test_alfabeto_cirilico():
    assert detectar_alfabeto("Привет") == "cirilico"
    assert detectar_alfabeto("Калинка") == "cirilico"


def test_alfabeto_griego():
    assert detectar_alfabeto("Αθήνα") == "griego"


def test_alfabeto_chino():
    assert detectar_alfabeto("你好") == "chino"


def test_alfabeto_japones():
    assert detectar_alfabeto("ありがとう") == "japones"


def test_alfabeto_arabe():
    assert detectar_alfabeto("مرحبا") == "arabe"


def test_alfabeto_vacio_es_latino():
    assert detectar_alfabeto("") == "latino"


def test_alfabeto_dominante_decide_en_mixto():
    """Cuando un titulo mezcla alfabetos, gana el dominante."""
    # Mayoria cirilico con una palabra latina pequena.
    assert detectar_alfabeto("Калинка ok") == "cirilico"


# ── requiere_escritura ──────────────────────────────────────────────────

def test_requiere_escritura_latino():
    assert requiere_escritura("Yesterday") is True
    assert requiere_escritura("Canción") is True


def test_no_requiere_escritura_no_latino():
    assert requiere_escritura("Привет") is False
    assert requiere_escritura("你好") is False
    assert requiere_escritura("ありがとう") is False


def test_no_requiere_escritura_mixto_con_un_caracter_no_latino():
    """Si UN solo caracter es no latino, no debe requerir escritura.

    Esto cubre titulos como "caracter (FLOWER)" donde un simbolo
    coreano/chino aparece entre texto latino: pedirle al usuario que
    teclee ese caracter rompe la experiencia.
    """
    assert requiere_escritura("Song 花 Title") is False
    assert requiere_escritura("Hello Привет World") is False
    assert requiere_escritura("Я vi a ti") is False


def test_requiere_escritura_ignora_numeros_y_puntuacion():
    """Numeros y puntuacion no son alfabeticos: no descalifican."""
    assert requiere_escritura("99 Luftballons") is True
    assert requiere_escritura("Don't Stop!") is True
    assert requiere_escritura("(I Can't Get No) Satisfaction") is True


# ── generar_hints ───────────────────────────────────────────────────────

def test_generar_hints_titulo_normal():
    hints = generar_hints("Bohemian Rhapsody")
    assert hints["alfabeto"] == "latino"
    assert hints["requiere_escritura"] is True
    assert hints["empieza_con"] == "B"
    assert hints["termina_con"] == "Y"
    assert hints["cantidad_palabras"] == 2
    assert hints["cantidad_letras"] == 16  # "Bohemian" (8) + "Rhapsody" (8)


def test_generar_hints_titulo_vacio():
    hints = generar_hints("")
    assert hints["empieza_con"] == ""
    assert hints["termina_con"] == ""
    assert hints["cantidad_palabras"] == 0
    assert hints["cantidad_letras"] == 0


def test_generar_hints_titulo_no_latino():
    hints = generar_hints("Калинка")
    assert hints["alfabeto"] == "cirilico"
    assert hints["requiere_escritura"] is False
    # Las hints siguen funcionando (no son responsabilidad de "latino").
    assert hints["cantidad_palabras"] == 1
    assert hints["cantidad_letras"] > 0
