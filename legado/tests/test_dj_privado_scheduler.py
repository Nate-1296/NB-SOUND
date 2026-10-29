"""Tests del scheduler, embeddings y motor de transiciones del DJ Privado."""
from __future__ import annotations

import pytest

from servicios.dj_privado import embeddings, scheduler, transiciones
from servicios.dj_privado.intencion import parsear_intent
from servicios.dj_privado.persistencia import PistaCandidata


def _make(
    id: int, titulo: str, artista: str, genero: str,
    *, bpm=None, key=None, mode=None, energy=None, valence=None,
    danceability=None, calmness=None, melancholy=None, aggressiveness=None,
    brightness=None, darkness=None, focus=None, workout=None, party=None, night=None,
    tags_json="{}", vibe_tags=(),
) -> PistaCandidata:
    return PistaCandidata(
        id=id, titulo=titulo, artista_nombre=artista,
        album_titulo="", artista_id=hash(artista) % 1000,
        album_id=None, genero=genero, duracion_seg=210.0,
        ruta_archivo=f"/m/{id}.mp3", favorita=False, veces_reproducida=0,
        bpm=bpm, key_name=key, mode=mode, energy=energy,
        valence_proxy=valence, danceability_proxy=danceability,
        calmness_proxy=calmness, melancholy_proxy=melancholy,
        aggressiveness_proxy=aggressiveness, brightness=brightness,
        darkness_proxy=darkness, focus_score_proxy=focus,
        workout_score_proxy=workout, party_score_proxy=party,
        night_score_proxy=night, tags_json=tags_json, vibe_tags=tuple(vibe_tags),
    )


# =============================================================================
# EMBEDDINGS
# =============================================================================

class TestEmbeddings:
    def test_provider_deterministico_siempre_disponible(self):
        embeddings.reset_provider()
        p = embeddings.obtener_provider()
        assert p.dim > 0
        assert p.model_id == "dj_deterministic_v1"

    def test_embed_texto_vacio_es_cero(self):
        p = embeddings.obtener_provider()
        vec = p.embed_texto("")
        assert all(v == 0.0 for v in vec)

    def test_similitud_prompts_similares(self):
        p = embeddings.obtener_provider()
        a = p.embed_texto("algo cinematografico con voces femeninas")
        b = p.embed_texto("musica cinematografica con voces femeninas")
        s = embeddings.similitud_coseno(a, b)
        assert s > 0.7

    def test_similitud_prompts_opuestos(self):
        p = embeddings.obtener_provider()
        a = p.embed_texto("algo tranquilo y acustico")
        b = p.embed_texto("rock agresivo para entrenar")
        s = embeddings.similitud_coseno(a, b)
        assert s < 0.3  # baja similitud

    def test_embed_pista_sin_features(self):
        p = embeddings.obtener_provider()
        vec = p.embed_pista({})
        assert len(vec) == p.dim


# =============================================================================
# SCHEDULER - PUNTUACION
# =============================================================================

class TestPuntuacion:
    def test_pista_alineada_supera_pista_desalineada(self):
        intent = parsear_intent("para concentrarme")
        pista_focus = _make(
            1, "Quiet Piano", "Pianist", "ambient",
            energy=0.2, calmness=0.95, focus=0.9, aggressiveness=0.05,
            tags_json='{"tags_msd50":[{"label":"ambient","score":0.9},{"label":"instrumental","score":0.9}]}',
        )
        pista_party = _make(
            2, "Loud Banger", "DJ", "electronic",
            energy=0.95, calmness=0.1, focus=0.1, aggressiveness=0.7, party=0.9,
        )
        s_focus = scheduler.puntuar_pista(pista_focus, intent)
        s_party = scheduler.puntuar_pista(pista_party, intent)
        assert s_focus.score_intent > s_party.score_intent

    def test_exclusion_genero_descarta(self):
        intent = parsear_intent("rock pero sin pop")
        pista_pop = _make(1, "Hit", "Star", "pop", energy=0.7, valence=0.7)
        detalles = [scheduler.puntuar_pista(pista_pop, intent)]
        sobrev = scheduler.aplicar_exclusiones(detalles, intent)
        assert all(d.pista.id != 1 for d in sobrev)

    def test_score_descompone_por_ejes(self):
        intent = parsear_intent("voces femeninas")
        pista = _make(
            1, "Female Anthem", "Singer", "pop",
            energy=0.6, valence=0.7,
            tags_json='{"tags_msd50":[{"label":"female vocalists","score":0.9},{"label":"pop","score":0.85}]}',
        )
        detalle = scheduler.puntuar_pista(pista, intent)
        # Score positivo y al menos una razon menciona eje
        assert detalle.score_intent > 0
        assert any("+" in r or "foco:" in r for r in detalle.razones)


# =============================================================================
# CURVA DE ENERGIA
# =============================================================================

class TestCurva:
    def test_progressive_sube(self):
        a = scheduler.objetivo_energia_para_posicion("progressive", 0, 10)
        b = scheduler.objetivo_energia_para_posicion("progressive", 9, 10)
        assert b > a

    def test_descending_baja(self):
        a = scheduler.objetivo_energia_para_posicion("descending", 0, 10)
        b = scheduler.objetivo_energia_para_posicion("descending", 9, 10)
        assert a > b

    def test_stable_es_constante(self):
        a = scheduler.objetivo_energia_para_posicion("stable", 0, 10)
        b = scheduler.objetivo_energia_para_posicion("stable", 9, 10)
        assert abs(a - b) < 0.05


# =============================================================================
# PLANIFICACION COMPLETA
# =============================================================================

class TestPlanificacion:
    def test_pool_vacio(self):
        intent = parsear_intent("algo")
        plan = scheduler.planificar_sesion([], intent)
        assert plan == []

    def test_intent_vacio_aun_planifica(self):
        intent = parsear_intent("")
        pool = [_make(i, f"T{i}", f"A{i % 3}", "pop", energy=0.5) for i in range(6)]
        plan = scheduler.planificar_sesion(pool, intent, duracion_objetivo_min=8)
        assert len(plan) > 0

    def test_diversidad_artista(self):
        # 5 pistas del mismo artista, max 2 por artista -> max 2 seleccionadas
        pool = [_make(i, f"T{i}", "MISMO", "pop", energy=0.6) for i in range(1, 6)]
        intent = parsear_intent("pop")
        plan = scheduler.planificar_sesion(pool, intent, max_pistas_por_artista=2, duracion_objetivo_min=30)
        artistas_usados = {p.pista.artista_nombre for p in plan}
        # MISMO solo puede aparecer max 2 veces
        contador = sum(1 for p in plan if p.pista.artista_nombre == "MISMO")
        assert contador <= 2

    def test_curva_progressive_aplica_objetivo(self):
        # Sin un foco intenso (como "entrenar") la curva tiene mas peso.
        # Aqui medimos que el scheduler USA la curva, no que ordena
        # estrictamente las pistas: la asignacion target esta en el codigo.
        # Usamos intent vacio para que score_intent sea 0 y la curva domine.
        from servicios.dj_privado.intencion import IntentMusical
        intent = IntentMusical(
            prompt="(progresivo)", axes={}, curva_energia="progressive",
            vacio=False, duracion_minutos=15,
        )
        pool = [
            _make(1, "Low", "A", "pop", energy=0.20),
            _make(2, "MedLow", "B", "pop", energy=0.40),
            _make(3, "Med", "C", "pop", energy=0.55),
            _make(4, "MedHigh", "D", "pop", energy=0.75),
            _make(5, "High", "E", "pop", energy=0.95),
        ]
        plan = scheduler.planificar_sesion(pool, intent, duracion_objetivo_min=15, semilla=42)
        if len(plan) >= 3:
            primeras = sum(p.pista.energy or 0.5 for p in plan[:2]) / 2
            ultimas = sum(p.pista.energy or 0.5 for p in plan[-2:]) / 2
            assert ultimas > primeras

    def test_workout_eleva_energia_promedio(self):
        # Con intent "entrenar", la sesion debe tener energia promedio alta
        # (no exigimos orden ascendente, el score domina sobre la curva).
        intent = parsear_intent("para entrenar duro")
        pool = [
            _make(1, "Low", "A", "pop", energy=0.20, workout=0.3),
            _make(2, "High1", "B", "pop", energy=0.85, workout=0.85),
            _make(3, "High2", "C", "pop", energy=0.90, workout=0.9),
            _make(4, "Med", "D", "pop", energy=0.50, workout=0.5),
        ]
        plan = scheduler.planificar_sesion(pool, intent, duracion_objetivo_min=14, semilla=7)
        if plan:
            promedio = sum(p.pista.energy or 0.5 for p in plan) / len(plan)
            assert promedio > 0.55  # debe favorecer pistas energeticas

    def test_planificacion_reproducible_con_semilla(self):
        intent = parsear_intent("algo energetico")
        pool = [_make(i, f"T{i}", f"A{i % 5}", "pop", energy=0.5 + (i % 5) * 0.1) for i in range(20)]
        plan1 = scheduler.planificar_sesion(pool, intent, semilla=123, duracion_objetivo_min=20)
        plan2 = scheduler.planificar_sesion(pool, intent, semilla=123, duracion_objetivo_min=20)
        ids1 = [p.pista.id for p in plan1]
        ids2 = [p.pista.id for p in plan2]
        assert ids1 == ids2


# =============================================================================
# TRANSICIONES
# =============================================================================

class TestTransiciones:
    def test_camelot_mayor(self):
        assert transiciones.codigo_camelot("C", "major") == "8B"

    def test_camelot_menor(self):
        assert transiciones.codigo_camelot("A", "minor") == "8A"

    def test_distancia_camelot_vecino(self):
        assert transiciones.distancia_camelot("8B", "9B") == 1
        assert transiciones.distancia_camelot("8B", "8A") == 1

    def test_distancia_camelot_lejos(self):
        assert transiciones.distancia_camelot("8B", "2A") >= 2

    def test_factor_bpm_cercano(self):
        assert transiciones.factor_bpm(120, 122) > 0.9
        assert transiciones.factor_bpm(120, 180) < 0.5

    def test_factor_bpm_doble_es_alto(self):
        # 70 vs 140 BPM se considera "doble" -> alta compat
        assert transiciones.factor_bpm(70, 140) > 0.8

    def test_factor_energia_smooth_penaliza_saltos(self):
        # smooth requiere energia cercana
        suave = transiciones.factor_energia(0.5, 0.55, estilo="smooth")
        salto = transiciones.factor_energia(0.5, 0.95, estilo="smooth")
        assert suave > salto

    def test_factor_energia_aggressive_favorece_saltos(self):
        suave = transiciones.factor_energia(0.5, 0.55, estilo="aggressive")
        salto = transiciones.factor_energia(0.5, 0.95, estilo="aggressive")
        assert salto >= suave

    def test_planificar_transicion_excelente(self):
        a = _make(1, "A", "X", "", bpm=120, key="C", mode="major", energy=0.6)
        b = _make(2, "B", "Y", "", bpm=121, key="G", mode="major", energy=0.65)
        plan = transiciones.planificar_transicion(a, b, estilo="smooth")
        assert plan.score > 0.85

    def test_planificar_transicion_mala(self):
        a = _make(1, "A", "X", "", bpm=80, key="C", mode="major", energy=0.3)
        b = _make(2, "B", "Y", "", bpm=180, key="F#", mode="minor", energy=0.95)
        plan = transiciones.planificar_transicion(a, b, estilo="smooth")
        assert plan.score < 0.4

    def test_refinamiento_mejora_total(self):
        pistas = [
            _make(1, "A", "1", "", bpm=120, key="C", mode="major", energy=0.5),
            _make(2, "B", "2", "", bpm=180, key="F#", mode="minor", energy=0.9),  # outlier
            _make(3, "C", "3", "", bpm=122, key="G", mode="major", energy=0.55),
            _make(4, "D", "4", "", bpm=124, key="D", mode="major", energy=0.6),
        ]
        refinadas, transiciones_calc = transiciones.refinar_orden_para_transiciones(pistas, estilo="smooth")
        total = sum(t.score for t in transiciones_calc)
        # Comparar contra el orden original
        orig_trans = [
            transiciones.planificar_transicion(pistas[i], pistas[i+1], estilo="smooth")
            for i in range(len(pistas)-1)
        ]
        orig_total = sum(t.score for t in orig_trans)
        assert total >= orig_total  # refinamiento no empeora

    def test_resolver_estilo_intent_vacio(self):
        assert transiciones.resolver_estilo_intent({}) == "smooth"

    def test_resolver_estilo_intent_dominante(self):
        assert transiciones.resolver_estilo_intent({"smooth": 0.3, "aggressive": 0.7}) == "aggressive"
