# =============================================================================
# servicios/dj_privado/transiciones.py
#
# Motor de transiciones del DJ Privado.
#
# Responsabilidades:
#   1. Calcular un score de compatibilidad de transicion entre dos pistas
#      adyacentes (track A -> track B).
#   2. Considerar BPM, key (rueda de Camelot/circulo de quintas), energia
#      relativa, tiempo y estilo de transicion deseado.
#   3. Dejar arquitectura preparada para "mezcla con stems" (Demucs) sin
#      implementar la mezcla audio real en esta fase. Lo que se expone es
#      la DESCRIPCION DE LA TRANSICION (que tipo recomendar y por que), y
#      un campo opcional para overlap/crossfade que el reproductor puede
#      consumir mas adelante.
#
# Filosofia:
#   - El sistema NO toca audio. Solo PLANIFICA transiciones.
#   - La calidad subjetiva de la transicion se desglosa en bpm/key/energia
#     y se expone como razones. El usuario puede ver "por que es buena".
#   - Las recomendaciones se inclinan por el estilo declarado en el intent
#     ("smooth" prefiere BPM cercano; "aggressive" tolera saltos).
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from servicios.dj_privado.persistencia import PistaCandidata


# =============================================================================
# RUEDA DE CAMELOT
#
# Sistema standard de DJing que asigna a cada tonalidad un par numero+letra.
# Tonalidades adyacentes en la rueda son armonicamente compatibles. El
# circulo de quintas (mayor o menor) determina los vecinos.
#
# Convencion: 'C' major -> '8B', 'A' minor -> '8A', etc.
# =============================================================================

# Mapeo letra_clave + mode -> codigo Camelot
_CAMELOT_MAYOR: dict[str, str] = {
    "C":  "8B", "C#": "3B", "D":  "10B", "D#": "5B",
    "E":  "12B","F":  "7B", "F#": "2B", "G":  "9B",
    "G#": "4B", "A":  "11B","A#": "6B", "B":  "1B",
    "Db": "3B", "Eb": "5B", "Gb": "2B", "Ab": "4B", "Bb": "6B",
}

_CAMELOT_MENOR: dict[str, str] = {
    "A":  "8A", "A#": "3A", "B":  "10A", "C":  "5A",
    "C#": "12A","D":  "7A", "D#": "2A", "E":  "9A",
    "F":  "4A", "F#": "11A","G":  "6A", "G#": "1A",
    "Bb": "3A", "Db": "12A","Eb": "2A", "Gb": "11A", "Ab": "1A",
}


def codigo_camelot(key_name: Optional[str], mode: Optional[str]) -> Optional[str]:
    """Mapea (key_name, mode) -> codigo Camelot. None si no se puede inferir.

    `mode` se interpreta de forma laxa: 'minor', 'minor mode', 'm' -> menor;
    cualquier otro o vacio -> mayor.
    """
    if not key_name:
        return None
    key = key_name.strip()
    es_menor = bool(mode) and "min" in mode.lower()
    fuente = _CAMELOT_MENOR if es_menor else _CAMELOT_MAYOR
    return fuente.get(key)


def _parse_camelot(codigo: str) -> Optional[tuple[int, str]]:
    """Descompone un codigo Camelot en (numero, letra). None si invalido."""
    if not codigo or len(codigo) < 2:
        return None
    letra = codigo[-1]
    if letra not in ("A", "B"):
        return None
    try:
        numero = int(codigo[:-1])
    except ValueError:
        return None
    if not (1 <= numero <= 12):
        return None
    return numero, letra


def distancia_camelot(a: str, b: str) -> int:
    """Distancia armonica entre dos codigos Camelot.

    Reglas DJ standard:
      - Mismo codigo: 0 (mezcla perfecta).
      - Vecino circular (numero +/- 1, misma letra): 1.
      - Cambio de modo (mismo numero, distinta letra A<->B): 1.
      - +2 en numero o cambios mayores: 2 o 3.

    Devuelve un entero que el scorer convierte en factor [0,1].
    99 = no compatibles (fallback para entradas invalidas).
    """
    pa = _parse_camelot(a)
    pb = _parse_camelot(b)
    if not pa or not pb:
        return 99
    num_a, letra_a = pa
    num_b, letra_b = pb
    delta_num = abs(num_a - num_b)
    # Distancia circular en el reloj de 12
    delta_num = min(delta_num, 12 - delta_num)
    cambio_letra = letra_a != letra_b
    if delta_num == 0 and not cambio_letra:
        return 0
    if delta_num == 0 and cambio_letra:
        return 1  # mismo tonal, modo distinto (cambio de "color")
    if delta_num == 1 and not cambio_letra:
        return 1  # quinta arriba/abajo
    if delta_num == 2 and not cambio_letra:
        return 2
    return 3


# =============================================================================
# COMPATIBILIDAD DE BPM
# =============================================================================

def factor_bpm(bpm_a: Optional[float], bpm_b: Optional[float], *, tolerancia: float = 8.0) -> float:
    """Factor 0..1 de compatibilidad por BPM.

    Reglas:
      - Ambos None: 0.5 (sin informacion -> neutral).
      - Diferencia <= tolerancia (8 BPM por defecto): 1.0.
      - Diferencia hasta 2x tolerancia: decae linealmente a 0.5.
      - Mas alla de 2x tolerancia, decae a 0 a los 30 BPM de diferencia.

    Se considera tambien la mezcla armonica por doble/mitad de BPM (140 vs 70).
    Si la pista B duplica/divide A dentro de la tolerancia ajustada, el factor
    se eleva como si fueran cercanos.
    """
    if bpm_a is None or bpm_b is None:
        return 0.5
    if bpm_a <= 0 or bpm_b <= 0:
        return 0.5
    diff = abs(bpm_a - bpm_b)
    # Mezcla por doble/mitad
    diff_doble = abs(bpm_a * 2 - bpm_b)
    diff_mitad = abs(bpm_a / 2 - bpm_b) if bpm_a > 0 else float("inf")
    diff_efectivo = min(diff, diff_doble, diff_mitad)
    if diff_efectivo <= tolerancia:
        return 1.0
    if diff_efectivo <= tolerancia * 2:
        return 1.0 - 0.5 * ((diff_efectivo - tolerancia) / tolerancia)
    if diff_efectivo <= 30.0:
        return 0.5 - 0.5 * ((diff_efectivo - tolerancia * 2) / (30.0 - tolerancia * 2))
    return 0.0


# =============================================================================
# CONTINUIDAD DE ENERGIA
# =============================================================================

def factor_energia(
    energia_a: Optional[float],
    energia_b: Optional[float],
    *,
    estilo: str = "smooth",
) -> float:
    """Factor 0..1 segun la diferencia de energia entre A y B.

    - Sin datos: 0.5.
    - "smooth": penaliza saltos grandes; tolera diferencias <= 0.2.
    - "aggressive": acepta saltos grandes; favorece contraste (>=0.3).
    - "energetic": favorece pequenos incrementos (B ligeramente superior a A).
    - "cinematic": tolera variaciones medias; prefiere narrativa.
    - "harmonic": neutro respecto a energia.
    """
    if energia_a is None or energia_b is None:
        return 0.5
    diff = energia_b - energia_a
    abs_diff = abs(diff)
    if estilo == "smooth":
        if abs_diff <= 0.10:
            return 1.0
        if abs_diff <= 0.25:
            return 1.0 - (abs_diff - 0.10) / 0.30
        return max(0.0, 0.5 - (abs_diff - 0.25) * 2)
    if estilo == "aggressive":
        if abs_diff >= 0.30:
            return 1.0
        return 0.5 + abs_diff
    if estilo == "energetic":
        if 0.0 <= diff <= 0.15:
            return 1.0
        if diff < 0:
            return max(0.0, 0.5 + diff * 2)  # bajar mucho penaliza
        return max(0.3, 1.0 - (diff - 0.15) * 1.5)
    if estilo == "cinematic":
        if abs_diff <= 0.30:
            return 1.0 - abs_diff * 0.5
        return max(0.0, 0.7 - (abs_diff - 0.30))
    # harmonic / default
    return 1.0 - min(1.0, abs_diff)


# =============================================================================
# SCORING DE TRANSICION
# =============================================================================

@dataclass
class TransicionPlan:
    """Descripcion de una transicion entre dos pistas adyacentes.

    Esta estructura se serializa en dj_pistas_sesion.transicion_json y
    sirve para mostrar al usuario "por que es una buena/mala transicion".

    En el futuro, los campos `overlap_seg` y `tecnica` informaran al
    reproductor para hacer crossfades con stems o fades clasicos.
    """

    score: float                           # 0..1, calidad global
    factor_bpm: float
    factor_key: float
    factor_energia: float
    delta_bpm: Optional[float]
    delta_camelot: Optional[int]
    delta_energia: Optional[float]
    razones: list[str] = field(default_factory=list)
    tecnica_sugerida: str = "crossfade"    # crossfade | cut | mix_armonico | drone
    overlap_seg: float = 4.0               # tiempo recomendado de solapamiento
    estilo_aplicado: str = "smooth"


def planificar_transicion(
    a: PistaCandidata,
    b: PistaCandidata,
    *,
    estilo: str = "smooth",
) -> TransicionPlan:
    """Construye un TransicionPlan entre A (saliendo) y B (entrando)."""

    cam_a = codigo_camelot(a.key_name, a.mode)
    cam_b = codigo_camelot(b.key_name, b.mode)
    dist_cam = distancia_camelot(cam_a, cam_b) if (cam_a and cam_b) else 99

    if dist_cam == 99:
        factor_k = 0.5  # sin informacion -> neutral
    else:
        # 0 -> 1.0, 1 -> 0.85, 2 -> 0.6, 3 -> 0.3
        mapping = {0: 1.0, 1: 0.85, 2: 0.6, 3: 0.3}
        factor_k = mapping.get(dist_cam, 0.0)

    factor_b = factor_bpm(a.bpm, b.bpm)
    factor_e = factor_energia(a.energy, b.energy, estilo=estilo)

    # Pesos segun estilo
    pesos = _pesos_para_estilo(estilo)
    score = (
        pesos["bpm"] * factor_b
        + pesos["key"] * factor_k
        + pesos["energia"] * factor_e
    )

    delta_bpm = (b.bpm - a.bpm) if (a.bpm is not None and b.bpm is not None) else None
    delta_e = (b.energy - a.energy) if (a.energy is not None and b.energy is not None) else None

    razones = _razones_transicion(
        factor_b=factor_b, factor_k=factor_k, factor_e=factor_e,
        delta_bpm=delta_bpm, delta_e=delta_e, dist_cam=dist_cam,
        cam_a=cam_a, cam_b=cam_b, estilo=estilo,
    )

    tecnica, overlap = _tecnica_y_overlap(
        score=score, dist_cam=dist_cam, factor_b=factor_b,
        delta_e=delta_e, estilo=estilo,
    )

    return TransicionPlan(
        score=score,
        factor_bpm=factor_b,
        factor_key=factor_k,
        factor_energia=factor_e,
        delta_bpm=delta_bpm,
        delta_camelot=dist_cam if dist_cam != 99 else None,
        delta_energia=delta_e,
        razones=razones,
        tecnica_sugerida=tecnica,
        overlap_seg=overlap,
        estilo_aplicado=estilo,
    )


def _pesos_para_estilo(estilo: str) -> dict[str, float]:
    """Distribucion de pesos segun el estilo declarado en el intent.

    Los pesos suman 1.0. Estilos enfocados en armonia priorizan key, los de
    energia priorizan energia, etc.
    """
    if estilo == "smooth":
        return {"bpm": 0.45, "key": 0.30, "energia": 0.25}
    if estilo == "harmonic":
        return {"bpm": 0.25, "key": 0.55, "energia": 0.20}
    if estilo == "energetic":
        return {"bpm": 0.40, "key": 0.15, "energia": 0.45}
    if estilo == "aggressive":
        return {"bpm": 0.25, "key": 0.15, "energia": 0.60}
    if estilo == "cinematic":
        return {"bpm": 0.20, "key": 0.30, "energia": 0.50}
    return {"bpm": 0.40, "key": 0.30, "energia": 0.30}


def _razones_transicion(
    *, factor_b: float, factor_k: float, factor_e: float,
    delta_bpm: Optional[float], delta_e: Optional[float],
    dist_cam: int, cam_a: Optional[str], cam_b: Optional[str], estilo: str,
) -> list[str]:
    razones: list[str] = []
    if delta_bpm is not None:
        if factor_b >= 0.9:
            razones.append(f"BPM cercano (Δ={delta_bpm:+.1f})")
        elif factor_b >= 0.6:
            razones.append(f"BPM tolerable (Δ={delta_bpm:+.1f})")
        else:
            razones.append(f"salto de BPM grande (Δ={delta_bpm:+.1f})")
    if cam_a and cam_b:
        if dist_cam == 0:
            razones.append(f"tonalidad identica ({cam_a})")
        elif dist_cam == 1:
            razones.append(f"tonalidades vecinas ({cam_a}→{cam_b})")
        elif dist_cam == 2:
            razones.append(f"distancia armonica media ({cam_a}→{cam_b})")
        else:
            razones.append(f"tonalidades alejadas ({cam_a}→{cam_b})")
    if delta_e is not None:
        if abs(delta_e) <= 0.1:
            razones.append(f"energia estable (Δ={delta_e:+.2f})")
        elif delta_e > 0:
            razones.append(f"subida de energia (Δ={delta_e:+.2f})")
        else:
            razones.append(f"bajada de energia (Δ={delta_e:+.2f})")
    razones.append(f"estilo:{estilo}")
    return razones


def _tecnica_y_overlap(
    *, score: float, dist_cam: int, factor_b: float,
    delta_e: Optional[float], estilo: str,
) -> tuple[str, float]:
    """Recomienda tecnica de transicion y overlap en segundos.

    Tecnicas:
      - mix_armonico: cuando key y BPM son compatibles -> crossfade largo
        con potencial de mezcla por stems.
      - crossfade: caso general suave (4-6 s).
      - cut: cortes secos (estilo aggressive o score bajo).
      - drone: para final de pista cinematica -> fade lento a un sostenido.
    """
    if estilo == "aggressive":
        return ("cut", 0.5)
    if estilo == "cinematic":
        return ("drone", 6.0)
    if score >= 0.80 and dist_cam <= 1 and factor_b >= 0.85:
        return ("mix_armonico", 8.0)
    if score >= 0.6:
        return ("crossfade", 5.0)
    return ("crossfade", 3.0)


# =============================================================================
# REFINAMIENTO POST-PLANIFICACION
#
# Cuando el scheduler ha seleccionado una lista de pistas, este modulo puede
# refinar el ordenamiento intentando mejorar la SUMA de scores de transicion
# vecina sin alejarse de la curva de energia.
#
# Es un refinamiento local: intenta swaps de pares cercanos si mejoran el
# total. No reordena globalmente para no romper la curva.
# =============================================================================

def refinar_orden_para_transiciones(
    pistas: list[PistaCandidata],
    *,
    estilo: str = "smooth",
    iteraciones: int = 8,
) -> tuple[list[PistaCandidata], list[TransicionPlan]]:
    """Aplica swaps locales para optimizar la suma de transiciones vecinas.

    Devuelve la lista refinada y la lista de TransicionPlan resultantes
    (longitud len(pistas)-1).

    Bloqueos:
      - La primera pista no se mueve (es el inicio explicito).
      - Si dos swaps consecutivos no mejoran, se detiene anticipadamente.
    """
    if len(pistas) <= 2:
        return list(pistas), [
            planificar_transicion(pistas[i], pistas[i + 1], estilo=estilo)
            for i in range(len(pistas) - 1)
        ]

    pistas_actual = list(pistas)
    mejora = True
    iteracion = 0
    while mejora and iteracion < iteraciones:
        mejora = False
        iteracion += 1
        for i in range(1, len(pistas_actual) - 2):
            actual_a = planificar_transicion(pistas_actual[i - 1], pistas_actual[i], estilo=estilo).score
            actual_b = planificar_transicion(pistas_actual[i], pistas_actual[i + 1], estilo=estilo).score
            swap_a = planificar_transicion(pistas_actual[i - 1], pistas_actual[i + 1], estilo=estilo).score
            swap_b = planificar_transicion(pistas_actual[i + 1], pistas_actual[i], estilo=estilo).score
            # Sumamos: deben mejorar globalmente
            if (swap_a + swap_b) > (actual_a + actual_b) + 0.01:
                pistas_actual[i], pistas_actual[i + 1] = pistas_actual[i + 1], pistas_actual[i]
                mejora = True

    transiciones = [
        planificar_transicion(pistas_actual[i], pistas_actual[i + 1], estilo=estilo)
        for i in range(len(pistas_actual) - 1)
    ]
    return pistas_actual, transiciones


# =============================================================================
# AYUDAS PARA EL CONSTRUCTOR
# =============================================================================

def resolver_estilo_intent(intent_estilo: dict[str, float]) -> str:
    """Toma el dict de estilos del intent y devuelve el ESTILO predominante.

    Si esta vacio, devuelve 'smooth' como default seguro.
    """
    if not intent_estilo:
        return "smooth"
    return max(intent_estilo.items(), key=lambda kv: kv[1])[0]


def transicion_a_dict(plan: TransicionPlan) -> dict:
    """Serializa un TransicionPlan a dict (para almacenar en dj_pistas_sesion)."""
    return {
        "score": plan.score,
        "factor_bpm": plan.factor_bpm,
        "factor_key": plan.factor_key,
        "factor_energia": plan.factor_energia,
        "delta_bpm": plan.delta_bpm,
        "delta_camelot": plan.delta_camelot,
        "delta_energia": plan.delta_energia,
        "razones": list(plan.razones),
        "tecnica_sugerida": plan.tecnica_sugerida,
        "overlap_seg": plan.overlap_seg,
        "estilo_aplicado": plan.estilo_aplicado,
    }
