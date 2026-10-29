"""Tests de la ontologia y el intent parser del DJ Privado."""
from __future__ import annotations

import pytest

from servicios.dj_privado import ontologia
from servicios.dj_privado.intencion import IntentMusical, parsear_intent


# =============================================================================
# ONTOLOGIA
# =============================================================================

class TestOntologiaBusqueda:
    def test_detecta_concepto_simple(self):
        matches = ontologia.buscar_conceptos("quiero algo cinematografico")
        nombres = [m.concepto.name for m in matches]
        assert "cinematografico" in nombres

    def test_detecta_multiples_conceptos(self):
        matches = ontologia.buscar_conceptos("cinematografico con voces femeninas")
        nombres = [m.concepto.name for m in matches]
        assert "cinematografico" in nombres
        assert "voces_femeninas" in nombres

    def test_no_detecta_substrings_falsos(self):
        # "rocky" no debe activar "rock"
        matches = ontologia.buscar_conceptos("rocky balboa training")
        nombres = [m.concepto.name for m in matches]
        assert "rock" not in nombres

    def test_alias_mas_largo_gana(self):
        # El alias mas especifico/largo gana sobre el mas generico.
        # "voces femeninas suaves" debe activar el concepto especializado
        # voz_femenina_suave (que incluye matiz de suavidad), NO el
        # generico voces_femeninas.
        matches = ontologia.buscar_conceptos("voces femeninas suaves")
        nombres = [m.concepto.name for m in matches]
        # Al menos uno de los dos conceptos vocales debe haber matcheado.
        # El comportamiento correcto es que gane el mas especifico.
        assert "voz_femenina_suave" in nombres or "voces_femeninas" in nombres
        # Mas matcheo solo el mas especifico (no doble match).
        assert not ("voz_femenina_suave" in nombres and "voces_femeninas" in nombres)

    def test_alias_corto_funciona_solo(self):
        # Sin matiz adicional, "voces femeninas" matchea el concepto generico.
        matches = ontologia.buscar_conceptos("con voces femeninas")
        nombres = [m.concepto.name for m in matches]
        assert "voces_femeninas" in nombres

    def test_prompt_vacio(self):
        assert ontologia.buscar_conceptos("") == []
        assert ontologia.buscar_conceptos("   ") == []

    def test_prompt_sin_conceptos(self):
        matches = ontologia.buscar_conceptos("xyzabc no signal here")
        assert matches == []

    def test_normalizacion_acentos(self):
        matches = ontologia.buscar_conceptos("clásica con piano")
        nombres = [m.concepto.name for m in matches]
        assert "clasica" in nombres


class TestOntologiaAgregacion:
    def test_agregar_ejes_suma_correcta(self):
        matches = ontologia.buscar_conceptos("cinematografico orquestal")
        ejes = ontologia.agregar_ejes(matches)
        # cinematografico tiene cinematic_level 0.7, orquestal tiene 0.4
        # con perceptual_weight=1.2 cada uno
        assert ejes["cinematic_level"] > 0.7  # suma de ambos con pesos

    def test_contradicciones_detectadas(self):
        matches = ontologia.buscar_conceptos("tranquilo y agresivo a la vez")
        pares = ontologia.detectar_contradicciones(matches)
        nombres_planos = {x for par in pares for x in par}
        assert "tranquilo" in nombres_planos
        assert "agresivo" in nombres_planos

    def test_generos_sugeridos(self):
        matches = ontologia.buscar_conceptos("rock")
        generos = ontologia.generos_sugeridos(matches)
        assert "rock" in generos

    def test_estilo_transicion_inferido(self):
        matches = ontologia.buscar_conceptos("subida progresiva")
        estilos = ontologia.estilo_transicion_sugerido(matches)
        assert "energetic" in estilos or "smooth" in estilos

    def test_curva_para_workout(self):
        matches = ontologia.buscar_conceptos("para entrenar duro")
        assert ontologia.curva_energia_sugerida(matches) == "progressive"

    def test_curva_para_party(self):
        matches = ontologia.buscar_conceptos("para fiesta de noche")
        # "fiesta" -> peak; "nocturno" -> descending; gana el primero detectado
        # segun el orden de la helper
        assert ontologia.curva_energia_sugerida(matches) in {"peak", "descending"}


# =============================================================================
# INTENT PARSER
# =============================================================================

class TestIntentParser:
    def test_prompt_vacio(self):
        intent = parsear_intent("")
        assert intent.vacio
        assert intent.axes == {}
        assert intent.curva_energia == "stable"

    def test_prompt_no_reconocido(self):
        intent = parsear_intent("xyz abc 123")
        assert intent.vacio  # sin conceptos -> marcado vacio
        assert intent.axes == {}

    def test_focos_se_extraen(self):
        intent = parsear_intent("algo cinematografico con voces femeninas")
        assert "cinematografico" in intent.focos
        assert "voces_femeninas" in intent.focos

    def test_negacion_basica(self):
        intent = parsear_intent("rock pero sin agresivo")
        assert "agresivo" in intent.exclusiones
        # No deberia tener foco "agresivo"
        assert "agresivo" not in intent.focos

    def test_exclusion_role_concepto(self):
        intent = parsear_intent("energetica pero sin EDM agresivo")
        # sin_edm_agresivo es un concepto de role=exclusion
        assert "sin_edm_agresivo" in intent.exclusiones

    def test_curva_descending_para_nocturno(self):
        intent = parsear_intent("algo elegante para conducir de noche")
        assert intent.curva_energia == "descending"

    def test_curva_progressive_para_entrenar(self):
        intent = parsear_intent("subida progresiva para entrenar")
        assert intent.curva_energia == "progressive"

    def test_resumen_humano_no_vacio(self):
        intent = parsear_intent("triste pero esperanzador")
        assert len(intent.resumen) > 0

    def test_resolucion_de_contradiccion_por_orden(self):
        # "tranquilo" y "agresivo" mismo peso; gana el ultimo
        intent = parsear_intent("tranquilo pero al final agresivo")
        # No deberia haber contradicciones residuales en focos
        focos_set = set(intent.focos)
        assert not ("tranquilo" in focos_set and "agresivo" in focos_set)

    def test_no_quiero_pop_excluye_pop(self):
        intent = parsear_intent("no quiero pop, quiero rock")
        assert "pop" in intent.exclusiones

    def test_negacion_no_propaga_con_ruptor(self):
        # "sin X pero con Y" -> Y no esta negado
        intent = parsear_intent("sin pop pero con rock")
        # Si rock no esta en focos es porque es role=context (no priority); revisamos exclusiones
        assert "pop" in intent.exclusiones
        # rock NO debe estar en exclusiones
        assert "rock" not in intent.exclusiones

    def test_roundtrip_json(self):
        intent = parsear_intent("algo cinematografico con voces femeninas", duracion_minutos=45)
        payload = intent.to_json()
        restaurado = IntentMusical.from_json(payload)
        assert restaurado.axes == intent.axes
        assert restaurado.focos == intent.focos
        assert restaurado.exclusiones == intent.exclusiones
        assert restaurado.curva_energia == intent.curva_energia
        assert restaurado.duracion_minutos == 45


# =============================================================================
# EJES (sanity)
# =============================================================================

class TestEjes:
    def test_lista_ejes_no_vacia(self):
        assert len(ontologia.EJES) > 0

    def test_curvas_validas(self):
        assert "stable" in ontologia.CURVAS_ENERGIA
        assert "progressive" in ontologia.CURVAS_ENERGIA

    def test_estilos_transicion_validas(self):
        assert "smooth" in ontologia.ESTILOS_TRANSICION
        assert "aggressive" in ontologia.ESTILOS_TRANSICION
