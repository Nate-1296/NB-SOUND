# =============================================================================
# servicios/dj_privado/scheduler.py
#
# Scheduler musical del DJ Privado.
#
# Responsabilidades:
#   1. Convertir las features de cada pista candidata en el mismo espacio
#      perceptual que el IntentMusical (ejes 0..1 alineados con ontologia.EJES).
#   2. Puntuar cada pista vs. el intent (score_intent).
#   3. Aplicar exclusiones duras y blandas (filtros).
#   4. Ordenar la sesion respetando una curva de energia objetivo.
#   5. Diversificar (no repetir artistas/albums en exceso) y aleatorizar
#      con semilla para reproducibilidad.
#
# NO se encarga de transiciones (eso es servicios/dj_privado/transiciones.py)
# ni de I/O persistente (eso es persistencia.py).
#
# Filosofia:
#   - El scoring es interpretable: cada pista anota razones.
#   - La curva es una funcion conocida de la posicion, no un proceso ML.
#   - La diversidad se aplica al final, despues del scoring crudo.
# =============================================================================

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from servicios.dj_privado import embeddings, narrativa, ontologia
from servicios.dj_privado.embeddings import similitud_coseno
from servicios.dj_privado.intencion import IntentMusical
from servicios.dj_privado.narrativa import (
    construir_perfil,
    objetivos_para_posicion,
)
from servicios.dj_privado.persistencia import PistaCandidata


# =============================================================================
# EXTRACCION DE EJES POR PISTA
# =============================================================================

@dataclass(frozen=True)
class EjesPista:
    """Vector de ejes 0..1 para una pista (mismo espacio que IntentMusical.axes).

    Cada valor representa "que tan presente esta este eje en la pista".
    Para pistas sin features analizados, los ejes derivables quedan en 0.5
    (neutral), evitando descartarlas pero tampoco favoreciendolas.
    """

    valores: dict[str, float]

    def get(self, eje: str, default: float = 0.5) -> float:
        return float(self.valores.get(eje, default))


_NEUTRAL = 0.5  # valor cuando no hay informacion


def _clip01(value) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _NEUTRAL
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _safe_or_neutral(value) -> float:
    if value is None:
        return _NEUTRAL
    return _clip01(value)


def extraer_ejes(pista: PistaCandidata) -> EjesPista:
    """Mapea features de la BD a los ejes perceptuales del DJ.

    Jerarquia de fuentes por eje (primera disponible gana):
      - Modelos deep (mood_happy, danceability_model...) tienen preferencia
        sobre proxies (valence_proxy, danceability_proxy...) cuando ambos
        existen, porque los modelos deep son mas precisos.
      - Los proxies son suficientes para funcionar sin analisis deep activado.

    Reglas notables:
      - vocal_focus se aproxima por mood_party / valence / brightness y por
        tags MSD que mencionan vocals. Sin tags ni mood, valor neutral.
      - vocal_female/vocal_male se infieren EXCLUSIVAMENTE de tags MSD
        ('female vocalists', 'male vocalists'). Sin tags, NEUTRAL (no
        sesgamos al azar).
      - club_energy: mood_party preferido (modelo deep), fallback a
        party_score_proxy (heuristica de pipeline).
      - bass_weight: estimacion por combinacion de danceability_proxy y
        darkness_proxy, porque ningun feature captura graves directamente.
    """

    f = pista
    tags_json = f.tags_json or "{}"

    # Detectar etiquetas en tags_msd50 / genre_discogs400 (deep models)
    tags_msd = _extraer_tags_deep(tags_json, "tags_msd50")
    tags_discogs = _extraer_tags_deep(tags_json, "genre_discogs400")

    def tag_score(*keywords: str) -> float:
        """Devuelve el max score de cualquier tag deep que coincida (lowercase)."""
        mejor = 0.0
        for label, score in tags_msd + tags_discogs:
            low = label.lower()
            for keyword in keywords:
                if keyword.lower() in low:
                    if score > mejor:
                        mejor = float(score)
                    break
        return mejor

    valores: dict[str, float] = {}

    # ---- Ejes directos ----
    valores["energy"] = _safe_or_neutral(f.energy if f.energy is not None else f.arousal_proxy)
    valores["danceability"] = _safe_or_neutral(
        f.danceability_model if f.danceability_model is not None else f.danceability_proxy
    )
    valores["calmness"] = _safe_or_neutral(
        f.mood_relaxed if f.mood_relaxed is not None else f.calmness_proxy
    )
    valores["melancholy"] = _safe_or_neutral(
        f.mood_sad if f.mood_sad is not None else f.melancholy_proxy
    )
    valores["euphoria"] = _safe_or_neutral(
        f.mood_happy if f.mood_happy is not None else f.valence_proxy
    )
    valores["aggressiveness"] = _safe_or_neutral(
        f.mood_aggressive if f.mood_aggressive is not None else f.aggressiveness_proxy
    )
    valores["brightness"] = _safe_or_neutral(f.brightness)
    valores["darkness"] = _safe_or_neutral(f.darkness_proxy)
    valores["tension"] = _safe_or_neutral(
        f.aggressiveness_proxy if f.aggressiveness_proxy is not None else None
    )
    valores["focus_score"] = _safe_or_neutral(f.focus_score_proxy)
    valores["workout_score"] = _safe_or_neutral(f.workout_score_proxy)
    valores["night_score"] = _safe_or_neutral(f.night_score_proxy)
    valores["rhythmic_density"] = _safe_or_neutral(f.danceability_proxy)

    # ---- Club energy ----
    valores["club_energy"] = _safe_or_neutral(
        f.mood_party if f.mood_party is not None else f.party_score_proxy
    )

    # ---- Bass weight (heuristica: combinacion de loudness/darkness/danceability) ----
    if f.danceability_proxy is not None and f.darkness_proxy is not None:
        bass_estim = (_clip01(f.danceability_proxy) + _clip01(f.darkness_proxy)) / 2.0
        valores["bass_weight"] = bass_estim
    else:
        valores["bass_weight"] = _NEUTRAL

    # ---- Vocales ----
    # Inferencias desde tags MSD (mas confiable que mood):
    female_score = tag_score("female vocal")
    male_score = tag_score("male vocal")
    instrumental_score = tag_score("instrumental")
    if female_score > 0 or male_score > 0 or instrumental_score > 0:
        # Si hay senal alguna, calibrar respecto al maximo
        vocal_presence = max(female_score, male_score)
        if instrumental_score > 0 and vocal_presence == 0:
            valores["vocal_focus"] = max(0.0, 0.4 - instrumental_score * 0.4)
            valores["instrumental_focus"] = _clip01(instrumental_score)
        else:
            valores["vocal_focus"] = _clip01(vocal_presence)
            valores["instrumental_focus"] = max(0.0, 1.0 - vocal_presence)
        valores["vocal_female"] = _clip01(female_score)
        valores["vocal_male"] = _clip01(male_score)
    else:
        valores["vocal_focus"] = _NEUTRAL
        valores["instrumental_focus"] = _NEUTRAL
        valores["vocal_female"] = _NEUTRAL
        valores["vocal_male"] = _NEUTRAL

    # ---- Orquestal / electronico / acustico ----
    cinematic_score = tag_score("classic", "soundtrack", "ambient")
    valores["cinematic_level"] = _clip01(cinematic_score) if cinematic_score else _NEUTRAL
    orchestral_score = tag_score("classical")
    valores["orchestral_weight"] = _clip01(orchestral_score) if orchestral_score else _NEUTRAL
    electronic_score = tag_score("electronic", "electro", "house", "techno", "edm", "dance")
    valores["electronic_weight"] = _clip01(electronic_score) if electronic_score else _NEUTRAL
    acoustic_score = tag_score("acoustic", "folk")
    valores["acoustic_weight"] = _clip01(acoustic_score) if acoustic_score else _NEUTRAL

    # ---- Storytelling (heuristica) ----
    valores["storytelling"] = _NEUTRAL

    return EjesPista(valores=valores)


def _extraer_tags_deep(tags_json: str, modelo: str) -> list[tuple[str, float]]:
    """Lee la lista de tags top_tags de un modelo deep desde tags_json.

    tags_json tiene shape {modelo: [{"label": str, "score": float}, ...]}.
    Si no esta presente, retorna []. Defensivo ante JSON malformado.
    """
    if not tags_json or tags_json == "{}":
        return []
    try:
        import json
        data = json.loads(tags_json)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    bloque = data.get(modelo, [])
    if not isinstance(bloque, list):
        return []
    salida: list[tuple[str, float]] = []
    for item in bloque:
        if isinstance(item, dict):
            label = str(item.get("label") or "")
            try:
                score = float(item.get("score") or 0.0)
            except (TypeError, ValueError):
                continue
            if label:
                salida.append((label, score))
    return salida


# =============================================================================
# SCORING INTENT vs PISTA
# =============================================================================

@dataclass
class ScoreDetalle:
    """Resultado de puntuar una pista contra un intent."""

    pista: PistaCandidata
    score_intent: float
    score_embedding: float
    score_total: float
    razones: list[str] = field(default_factory=list)
    descartada: bool = False
    motivo_descarte: str = ""


def _suma_axes(axes_intent: dict[str, float]) -> float:
    """Suma de valores absolutos del intent; usado para normalizar el ajuste."""
    return sum(abs(v) for v in axes_intent.values()) or 1.0


def puntuar_pista(
    pista: PistaCandidata,
    intent: IntentMusical,
    *,
    provider: Optional[embeddings.EmbeddingProvider] = None,
    peso_embedding: float = 0.25,
) -> ScoreDetalle:
    """Calcula score_intent + score_embedding para una pista vs. un intent.

    score_intent:
        Producto interno normalizado entre axes_intent (vector del prompt en
        espacio perceptual) y los ejes de la pista. Los ejes de la pista se
        reescalan de [0,1] a [-1,+1] para que el punto neutro (0.5) contribuya
        cero al producto, y no favorezca ni perjudique pistas sin informacion.

    score_embedding:
        Similitud coseno entre el embedding del prompt y el embedding de la pista.
        Solo activo si se pasa un `provider`. Con el provider deterministico es
        coherente con score_intent pero anadiendole contexto semantico (sinonimos,
        agrupaciones de concepto). Con ONNX real, captura matices linguisticos.

    bonus_focos:
        Si el intent tiene focos perceptuales (priority-role), se suma un bonus
        proporcional a cuanto exhibe la pista cada foco. El bonus se acota a
        0.15 por foco para no dominar sobre el score_intent.

    score_total:
        (1 - peso_embedding) * (score_intent + bonus_focos)
        + peso_embedding * score_embedding.
        Con peso_embedding=0 el embedding no participa en absoluto.
    """
    ejes_pista = extraer_ejes(pista)
    intent_axes = intent.axes or {}

    norm = _suma_axes(intent_axes)
    score_intent = 0.0
    razones: list[str] = []

    if intent_axes:
        # Producto escalado: (eje_pista - 0.5) * 2 -> rango [-1, +1].
        # Asi un eje neutral aporta 0; uno presente al maximo aporta +1.
        for eje, delta in intent_axes.items():
            valor_pista = ejes_pista.get(eje, _NEUTRAL)
            ajustado = (valor_pista - 0.5) * 2.0
            contribucion = ajustado * delta
            score_intent += contribucion
            if abs(contribucion) >= 0.20:
                signo = "+" if contribucion > 0 else "-"
                razones.append(f"{signo}{eje}({contribucion:+.2f})")
        score_intent /= norm
    else:
        # Sin axes => intent vacio o muy debil; score_intent neutral.
        score_intent = 0.0

    # ---- Score embedding (similitud semantica) ----
    score_emb = 0.0
    if provider is not None and peso_embedding > 0:
        vec_pista = provider.embed_pista(pista.to_features_dict())
        vec_prompt = provider.embed_texto(intent.prompt)
        score_emb = similitud_coseno(vec_prompt, vec_pista)

    # ---- Ajustes por focos perceptuales ----
    # Si el intent tiene focos (priority), reforzar pistas que los exhiban
    # claramente sumando un bonus moderado.
    bonus_focos = 0.0
    for nombre_foco in intent.focos:
        concepto = ontologia.obtener_concepto(nombre_foco)
        if concepto is None:
            continue
        # Como medimos "exhibe el foco"? Calculamos la alineacion del axes
        # del concepto con los ejes de la pista (mismo metodo que arriba).
        alignment = 0.0
        for eje, delta in concepto.axes.items():
            ajustado = (ejes_pista.get(eje) - 0.5) * 2.0
            alignment += ajustado * delta
        if alignment > 0:
            bonus_focos += min(0.15, alignment / max(1, len(concepto.axes)))
            razones.append(f"foco:{concepto.name}(+{min(0.15, alignment / max(1, len(concepto.axes))):.2f})")

    score_total = (
        (1.0 - peso_embedding) * (score_intent + bonus_focos)
        + peso_embedding * score_emb
    )

    return ScoreDetalle(
        pista=pista,
        score_intent=score_intent + bonus_focos,
        score_embedding=score_emb,
        score_total=score_total,
        razones=razones,
    )


# =============================================================================
# FILTROS DUROS Y BLANDOS
# =============================================================================

def aplicar_exclusiones(
    detalles: list[ScoreDetalle],
    intent: IntentMusical,
) -> list[ScoreDetalle]:
    """Aplica filtros de exclusion del intent.

    Hard filters (descartan completamente):
      - generos_excluidos: si el genero crudo de la pista esta en la lista.
      - exclusiones tipo "sin_X" donde X es un concepto con genres declarados
        que coinciden con el genero de la pista.

    Soft filters (penalizan score):
      - exclusiones que no eliminan pero reducen el score_total a la mitad.
    """
    excluidos_lower = {g.lower() for g in intent.generos_excluidos}

    # Mapa de conceptos negados a sus generos asociados
    generos_indirectos: set[str] = set()
    for nombre in intent.exclusiones:
        concepto = ontologia.obtener_concepto(nombre)
        if concepto and concepto.genres:
            for g in concepto.genres:
                generos_indirectos.add(g.lower())

    for detalle in detalles:
        genero_pista = (detalle.pista.genero or "").lower()
        if genero_pista and (genero_pista in excluidos_lower or genero_pista in generos_indirectos):
            detalle.descartada = True
            detalle.motivo_descarte = f"genero_excluido:{genero_pista}"
            continue

        # Penalizacion suave: si el intent niega un concepto y la pista
        # tiene un tag que matchea el concepto, reducir score.
        for nombre in intent.exclusiones:
            concepto = ontologia.obtener_concepto(nombre)
            if concepto is None:
                continue
            # Detectar alias del concepto entre los tags de la pista
            tags_pista_norm = {t.lower() for t in detalle.pista.vibe_tags}
            for alias in concepto.aliases:
                if alias.lower() in tags_pista_norm:
                    detalle.score_total *= 0.5
                    detalle.razones.append(f"penalizado:{concepto.name}")
                    break

    return [d for d in detalles if not d.descartada]


# =============================================================================
# CURVA DE ENERGIA
# =============================================================================

def objetivo_energia_para_posicion(curva: str, posicion: int, total: int) -> float:
    """Objetivo de energia para la posicion `posicion` de `total` pistas.

    Devuelve un valor en [0,1] que el ordenamiento intentara aproximar.
    Las curvas estan en ontologia.CURVAS_ENERGIA.
    """
    if total <= 1:
        return 0.5
    t = posicion / max(1, total - 1)  # 0..1 a lo largo de la sesion
    if curva == "progressive":
        return 0.35 + 0.55 * t  # 0.35 -> 0.90
    if curva == "wave":
        # senoidal: pico al 50%, baja al final
        return 0.4 + 0.4 * math.sin(math.pi * t)
    if curva == "descending":
        return 0.85 - 0.55 * t  # 0.85 -> 0.30
    if curva == "peak":
        # rampa hasta el 60%, plateau, desciende suavemente
        if t < 0.4:
            return 0.4 + 1.25 * t  # 0.4 -> 0.9
        if t < 0.7:
            return 0.9
        return 0.9 - 1.3 * (t - 0.7)  # 0.9 -> 0.51
    # stable
    return 0.55


# =============================================================================
# CONSTRUCCION DE LA SESION
# =============================================================================

@dataclass
class PistaSesionPlanificada:
    """Pista seleccionada y posicionada en una sesión."""

    pista: PistaCandidata
    posicion: int
    score_total: float
    score_intent: float
    score_curva: float
    razones: list[str]


def planificar_sesion(
    candidatas: list[PistaCandidata],
    intent: IntentMusical,
    *,
    duracion_objetivo_min: int = 60,
    provider: Optional[embeddings.EmbeddingProvider] = None,
    peso_embedding: float = 0.25,
    max_pistas_por_artista: int = 2,
    semilla: Optional[int] = None,
    pool_top_k: int = 200,
) -> list[PistaSesionPlanificada]:
    """Construye la lista ordenada de pistas para una sesion DJ.

    Algoritmo greedy orientado a perfil narrativo:
      1. Puntuar cada candidata (score_intent + score_embedding).
      2. Aplicar exclusiones duras/blandas del intent (generos excluidos,
         negaciones de conceptos).
      3. Reducir el pool al top_k por score_total (acota el coste del paso 4).
      4. Para cada slot temporal, calcular los objetivos del perfil narrativo
         (warmup/groove/peak/release/cooldown) usando la fraccion de tiempo
         acumulada (t normalizado), NO la posicion en lista. Esto da un perfil
         temporal correcto aunque las pistas tengan duraciones muy distintas.
      5. Seleccionar la pista con mejor combinacion de score_total (65%) y
         adherencia al perfil (35%). El jitter de 1 milis rompe empates sin
         alterar la semilla de forma sensible.
      6. Acumular duracion y parar cuando se supera el objetivo + margen.

    `semilla` garantiza reproducibilidad: dos llamadas con mismos parametros y
    misma semilla producen la misma lista (util para tests y para que el usuario
    pueda compartir/reproducir una sesion especifica).
    """
    if not candidatas:
        return []

    rng = random.Random(semilla)

    # Paso 1: scoring
    detalles: list[ScoreDetalle] = []
    for cand in candidatas:
        detalle = puntuar_pista(cand, intent, provider=provider, peso_embedding=peso_embedding)
        detalles.append(detalle)

    # Paso 2: exclusiones
    sobrevivientes = aplicar_exclusiones(detalles, intent)
    if not sobrevivientes:
        return []

    # Paso 3: limitar pool al top_k por score_total para acotar costo
    sobrevivientes.sort(key=lambda d: -d.score_total)
    sobrevivientes = sobrevivientes[:max(pool_top_k, 10)]

    # Cuenta de artistas usados para diversidad
    uso_artista: dict[int, int] = {}

    # Paso 4: ordenamiento por perfil narrativo (warmup/groove/peak/release/cooldown)
    #
    # Se calcula `t` como fraccion del objetivo de duracion (no del total
    # de pistas), porque el perfil narrativo es temporal, no posicional.
    # Asi pistas de distinta duracion se acomodan correctamente.
    perfil = construir_perfil(intent)

    seleccionados: list[PistaSesionPlanificada] = []
    duracion_acum = 0.0
    objetivo_seg = duracion_objetivo_min * 60.0
    # Margen pequeno para dar al ultimo slot algo de cushion antes del trim.
    margen_corte = objetivo_seg * 0.05
    tolerancia = objetivo_seg + margen_corte

    posicion = 0
    while sobrevivientes:
        # Tiempo normalizado al inicio de esta pista (0..1)
        t_inicio = min(1.0, duracion_acum / max(1.0, objetivo_seg))
        objetivos = objetivos_para_posicion(perfil, t_inicio)

        # Si ya alcanzamos el objetivo, parar (la duracion efectiva se ajusta
        # luego con overlaps y trim si hace falta).
        if duracion_acum >= tolerancia:
            break

        mejor: Optional[ScoreDetalle] = None
        mejor_puntaje = -math.inf
        mejor_distancia = 1.0
        for cand_detalle in sobrevivientes:
            art_id = cand_detalle.pista.artista_id
            if art_id is not None and uso_artista.get(art_id, 0) >= max_pistas_por_artista:
                continue
            ejes = extraer_ejes(cand_detalle.pista)
            # Distancia compuesta a los objetivos multi-eje del perfil
            d_energy     = abs(ejes.get("energy",            _NEUTRAL) - objetivos["energy"])
            d_tension    = abs(ejes.get("tension",           _NEUTRAL) - objetivos["tension"])
            d_density    = abs(ejes.get("rhythmic_density",  _NEUTRAL) - objetivos["density"])
            d_brightness = abs(ejes.get("brightness",        _NEUTRAL) - objetivos["brightness"])
            d_calmness   = abs(ejes.get("calmness",          _NEUTRAL) - objetivos["calmness"])
            distancia = (d_energy * 0.40 + d_tension * 0.20 +
                         d_density * 0.15 + d_brightness * 0.10 + d_calmness * 0.15)

            # Combinacion: 65% score_total (intent + embedding) + 35% adherencia perfil
            puntaje_curva = (1.0 - distancia)
            puntaje_total = 0.65 * cand_detalle.score_total + 0.35 * puntaje_curva
            puntaje_total += rng.uniform(-0.001, 0.001)
            if puntaje_total > mejor_puntaje:
                mejor_puntaje = puntaje_total
                mejor = cand_detalle
                mejor_distancia = distancia
        if mejor is None:
            break
        sobrevivientes.remove(mejor)
        art_id = mejor.pista.artista_id
        if art_id is not None:
            uso_artista[art_id] = uso_artista.get(art_id, 0) + 1
        score_curva_val = max(0.0, 1.0 - mejor_distancia)
        fase_actual = narrativa.fase_en_t(perfil, t_inicio)
        razones_finales = list(mejor.razones) + [
            f"fase:{fase_actual.name}", f"d_perfil={mejor_distancia:.2f}",
        ]
        seleccionados.append(PistaSesionPlanificada(
            pista=mejor.pista,
            posicion=posicion,
            score_total=mejor.score_total,
            score_intent=mejor.score_intent,
            score_curva=score_curva_val,
            razones=razones_finales,
        ))
        duracion_acum += mejor.pista.duracion_seg or 0.0
        posicion += 1
        if posicion >= 200:
            break

    return seleccionados


def _estimar_total(duracion_min: int) -> int:
    """Estimacion conservadora de cuantas pistas caben en N minutos.

    Asume duracion promedio de 3.5 min/pista. Solo se usa para evaluar la
    curva de energia (no es un limite duro).
    """
    return max(8, int(round(duracion_min / 3.5)))
