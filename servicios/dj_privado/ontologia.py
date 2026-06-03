# =============================================================================
# servicios/dj_privado/ontologia.py
#
# Ontologia musical del DJ Privado.
#
# La ontologia define el vocabulario perceptual del sistema: conceptos
# musicales (no solo generos) con sus aliases (ES/EN), eje de influencia,
# peso perceptual y posibles afinidades/contradicciones con otros conceptos.
#
# Filosofia:
#   - Un "concepto" describe una PERCEPCION musical, no una etiqueta tecnica.
#   - "voces femeninas" no es un genero: es una prioridad perceptual.
#   - "cinematografico" no se mapea a un genero: ajusta varios ejes a la vez.
#   - Las contradicciones evitan combinaciones musicales incoherentes.
#
# La ontologia es la fuente de verdad para:
#   - Detectar conceptos en prompts de usuario (deterministico, sin LLM).
#   - Mapear conceptos a slots multi-eje (energy, vocal_focus, etc.).
#   - Calcular afinidades entre conceptos (para re-ranking).
#   - Detectar prompts contradictorios y resolver prioridades.
# =============================================================================

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Optional


# =============================================================================
# EJES PERCEPTUALES (slots musicales)
#
# Cada eje es una dimension continua [0.0, 1.0] que describe una propiedad
# perceptual de una pista o de una intencion. Los conceptos de la ontologia
# desplazan estos ejes; el scheduler los usa para puntuar candidatos.
#
# Los ejes son ortogonales a los generos: un track puede ser "rock" y tener
# alto vocal_focus, alto cinematic_level, baja darkness. Lo que el sistema
# selecciona NO es genero, sino la combinacion de ejes mas cercana.
# =============================================================================

EJES: tuple[str, ...] = (
    "energy",                  # nivel general de energia percibida
    "danceability",            # cuanto invita a moverse
    "vocal_focus",             # presencia/protagonismo vocal
    "vocal_female",            # afinidad por voces femeninas
    "vocal_male",              # afinidad por voces masculinas
    "instrumental_focus",      # preferencia por instrumental sin voz
    "cinematic_level",         # textura orquestal/narrativa
    "orchestral_weight",       # peso de cuerdas/maderas/orquesta
    "electronic_weight",       # peso de sintetizadores/produccion electronica
    "acoustic_weight",         # peso de instrumentos acusticos
    "darkness",                # tono oscuro/nocturno
    "brightness",              # tono brillante/luminoso
    "melancholy",              # tristeza/melancolia
    "euphoria",                # alegria/euforia
    "tension",                 # tension/disonancia/intensidad armonica
    "aggressiveness",          # agresividad
    "calmness",                # calma
    "rhythmic_density",        # densidad de percusion
    "bass_weight",             # peso de los graves
    "storytelling",            # narrativa progresiva
    "club_energy",             # energia de pista/club
    "focus_score",             # apto para concentracion
    "workout_score",           # apto para entrenamiento
    "night_score",             # apto para conducir/contexto nocturno
)


# Curvas de energia disponibles para una sesion completa.
CURVAS_ENERGIA: tuple[str, ...] = (
    "stable",       # mantener el nivel inicial
    "progressive",  # ascenso gradual
    "wave",         # ondulacion (sube-baja-sube)
    "descending",   # descenso gradual
    "peak",         # subida fuerte, plateau, descenso
)


# Estilos de transicion (objetivo perceptual de las uniones entre pistas).
ESTILOS_TRANSICION: tuple[str, ...] = (
    "smooth",       # transiciones suaves, BPM cercanos
    "cinematic",    # transiciones largas/dramaticas
    "aggressive",   # cortes secos, contrastes
    "harmonic",     # priorizar compatibilidad de key
    "energetic",    # priorizar continuidad de energia
)


# =============================================================================
# CONCEPTO MUSICAL
# =============================================================================

@dataclass(frozen=True)
class Concepto:
    """Un concepto perceptual de la ontologia musical.

    - name: identificador interno estable (snake_case).
    - aliases: variantes en texto libre (ES + EN) que activan el concepto.
    - axes: empuje a los ejes (eje -> delta, normalmente en [-1.0, 1.0]).
        Positivo: aumenta el peso del eje. Negativo: lo reduce.
        El delta NO es un valor absoluto; es un "voto" que el agregador
        combina con el resto de votos del prompt.
    - perceptual_weight: peso global del concepto (importancia con la que se
        combinan sus axes vs. otros conceptos del prompt). Conceptos muy
        especificos como "voces femeninas" suelen tener un peso alto.
    - role: papel del concepto.
        "context"   = contexto general (genero, ambiente)
        "priority"  = prioridad perceptual (lo que DEBE destacar)
        "modifier"  = ajuste sutil (intensidad, foco)
        "exclusion" = NO quiero esto
    - genres: pistas-pista de generos relacionados (debiles, solo hint).
    - contradicts: conceptos con los que entra en contradiccion fuerte.
    - boosts: conceptos que refuerza/asiste (afinidad).
    """

    name: str
    aliases: tuple[str, ...]
    axes: dict[str, float] = field(default_factory=dict)
    perceptual_weight: float = 1.0
    role: str = "context"
    genres: tuple[str, ...] = ()
    contradicts: tuple[str, ...] = ()
    boosts: tuple[str, ...] = ()


# =============================================================================
# CONCEPTOS — vocabulario perceptual del DJ
#
# Esta lista es la "biblia perceptual" del sistema. Esta intencionadamente
# en espanol/ingles dado el publico bilinge esperado. Anadir nuevos conceptos
# es seguro mientras se respete el contrato del dataclass.
# =============================================================================

CONCEPTOS: tuple[Concepto, ...] = (
    # -------------------------------------------------------------------------
    # Generos amplios (contexto)
    # -------------------------------------------------------------------------
    Concepto(
        "pop", aliases=("pop",),
        axes={"vocal_focus": 0.3, "brightness": 0.2, "danceability": 0.2},
        role="context", genres=("pop", "indie pop"),
    ),
    Concepto(
        "rock", aliases=("rock",),
        axes={"energy": 0.4, "aggressiveness": 0.2, "rhythmic_density": 0.3},
        role="context", genres=("rock", "alternative rock", "classic rock", "hard rock"),
    ),
    Concepto(
        "indie", aliases=("indie", "alternativo", "alternative"),
        axes={"acoustic_weight": 0.2, "vocal_focus": 0.2},
        role="context", genres=("indie", "indie pop", "indie rock", "alternative"),
    ),
    Concepto(
        "electronica", aliases=("electronica", "electronic", "electronico", "edm"),
        axes={"electronic_weight": 0.6, "danceability": 0.4, "bass_weight": 0.3},
        role="context", genres=("electronic", "electronica", "dance", "house"),
    ),
    Concepto(
        "edm_agresivo", aliases=("edm agresivo", "edm fuerte", "hard edm", "big room"),
        axes={"electronic_weight": 0.7, "aggressiveness": 0.5, "energy": 0.5},
        role="context", genres=("electronic", "dance"),
        contradicts=("calmness", "tranquilo", "acustico", "soft"),
    ),
    Concepto(
        "house", aliases=("house",),
        axes={"electronic_weight": 0.5, "danceability": 0.6, "club_energy": 0.4},
        role="context", genres=("house",), boosts=("club_party",),
    ),
    Concepto(
        "techno", aliases=("techno",),
        axes={"electronic_weight": 0.7, "rhythmic_density": 0.5, "club_energy": 0.5, "darkness": 0.3},
        role="context", genres=("techno",), boosts=("club_party",),
    ),
    Concepto(
        "hip_hop", aliases=("hip hop", "hiphop", "rap"),
        axes={"vocal_focus": 0.4, "bass_weight": 0.5, "rhythmic_density": 0.4},
        role="context", genres=("Hip-Hop", "rap"),
    ),
    Concepto(
        "reggaeton",
        aliases=("reggaeton", "reggaetón", "perreo", "perreo viejo",
                 "reggaeton viejo", "reggaetón viejo"),
        axes={"vocal_focus": 0.35, "bass_weight": 0.55,
              "rhythmic_density": 0.55, "danceability": 0.5},
        role="context", genres=("reggaeton", "latin urban"),
    ),
    Concepto(
        "reggae", aliases=("reggae",),
        axes={"calmness": 0.35, "vocal_focus": 0.3, "rhythmic_density": 0.3},
        role="context", genres=("reggae",),
    ),
    Concepto(
        "salsa", aliases=("salsa",),
        axes={"danceability": 0.6, "rhythmic_density": 0.5, "vocal_focus": 0.35},
        role="context", genres=("salsa", "latin"),
    ),
    Concepto(
        "bachata", aliases=("bachata",),
        axes={"vocal_focus": 0.45, "danceability": 0.4, "calmness": 0.2},
        role="context", genres=("bachata", "latin"),
    ),
    Concepto(
        "merengue", aliases=("merengue",),
        axes={"danceability": 0.6, "rhythmic_density": 0.5, "vocal_focus": 0.3},
        role="context", genres=("merengue", "latin"),
    ),
    Concepto(
        "cumbia", aliases=("cumbia",),
        axes={"danceability": 0.5, "rhythmic_density": 0.4, "vocal_focus": 0.3},
        role="context", genres=("cumbia", "latin"),
    ),
    Concepto(
        "trap", aliases=("trap",),
        axes={"bass_weight": 0.55, "rhythmic_density": 0.45, "vocal_focus": 0.35},
        role="context", genres=("trap",),
    ),
    Concepto(
        "rnb", aliases=("rnb", "r&b", "r and b", "soul"),
        axes={"vocal_focus": 0.5, "calmness": 0.2, "bass_weight": 0.2},
        role="context", genres=("rnb", "soul"),
    ),
    Concepto(
        "jazz", aliases=("jazz",),
        axes={"acoustic_weight": 0.4, "calmness": 0.3, "instrumental_focus": 0.2},
        role="context", genres=("jazz",),
    ),
    Concepto(
        "clasica", aliases=("clasica", "clasico", "classical", "classic"),
        axes={"orchestral_weight": 0.7, "acoustic_weight": 0.6, "cinematic_level": 0.5,
              "calmness": 0.2, "instrumental_focus": 0.4},
        role="context", genres=("classical",),
        contradicts=("edm_agresivo", "club_party"),
    ),
    Concepto(
        "ambient", aliases=("ambient", "ambiental"),
        axes={"calmness": 0.6, "instrumental_focus": 0.4, "electronic_weight": 0.2, "energy": -0.2},
        role="context", genres=("ambient",),
    ),
    Concepto(
        "folk", aliases=("folk", "folklor", "folclor"),
        axes={"acoustic_weight": 0.6, "vocal_focus": 0.3, "storytelling": 0.3},
        role="context", genres=("folk", "acoustic"),
    ),
    Concepto(
        "metal", aliases=("metal",),
        axes={"aggressiveness": 0.6, "energy": 0.6, "rhythmic_density": 0.5, "darkness": 0.3},
        role="context", genres=("metal", "heavy metal"),
        contradicts=("calmness", "clasica"),
    ),
    Concepto(
        "blues", aliases=("blues",),
        axes={"vocal_focus": 0.4, "melancholy": 0.3, "acoustic_weight": 0.3},
        role="context", genres=("blues",),
    ),
    Concepto(
        "funk", aliases=("funk",),
        axes={"danceability": 0.5, "bass_weight": 0.4, "rhythmic_density": 0.4, "euphoria": 0.3},
        role="context", genres=("funk",),
    ),

    # -------------------------------------------------------------------------
    # Atmosferas / texturas perceptuales (priority/modifier)
    # -------------------------------------------------------------------------
    Concepto(
        "cinematografico", aliases=("cinematografico", "cinematic", "cinemato", "epico"),
        axes={"cinematic_level": 0.7, "orchestral_weight": 0.4, "storytelling": 0.4},
        role="priority", perceptual_weight=1.2,
    ),
    Concepto(
        "orquestal", aliases=("orquestal", "orchestral", "sinfonico", "symphonic", "orquesta"),
        axes={"orchestral_weight": 0.8, "acoustic_weight": 0.4, "cinematic_level": 0.4},
        role="priority", perceptual_weight=1.2,
    ),
    Concepto(
        "narrativo", aliases=("narrativo", "storytelling", "que cuente", "que cuente algo"),
        axes={"storytelling": 0.7, "cinematic_level": 0.3},
        role="priority", perceptual_weight=1.1,
    ),
    Concepto(
        # NOTA: "etereo"/"ethereal"/"dreamy" tienen un concepto propio mas
        # rico (etereo) en la expansion semantica. Aqui mantenemos los
        # aliases que NO colisionan con ese concepto.
        "sonador", aliases=("sonador", "ensonacion", "sonadora"),
        axes={"brightness": 0.3, "calmness": 0.4, "cinematic_level": 0.3, "electronic_weight": 0.2},
        role="priority",
    ),
    Concepto(
        "nocturno", aliases=("nocturno", "noche", "de noche", "por la noche", "night",
                                 "night drive", "manejar de noche", "conducir de noche",
                                 "madrugada", "antes de dormir", "tarde noche",
                                 "night driving"),
        axes={"darkness": 0.4, "night_score": 0.7, "calmness": 0.2, "cinematic_level": 0.2},
        role="priority", perceptual_weight=1.1,
    ),
    Concepto(
        "elegante", aliases=("elegante", "elegant", "sofisticado", "classy", "refinado"),
        axes={"calmness": 0.2, "acoustic_weight": 0.3, "orchestral_weight": 0.2, "vocal_focus": 0.2},
        role="modifier",
    ),
    Concepto(
        "minimalista", aliases=("minimalista", "minimal", "minimalismo"),
        axes={"instrumental_focus": 0.3, "calmness": 0.3, "rhythmic_density": -0.2},
        role="modifier",
    ),

    # -------------------------------------------------------------------------
    # Emociones (priority)
    # -------------------------------------------------------------------------
    Concepto(
        # NOTA: "melancolico"/"nostalgico" tienen conceptos propios mas matizados
        # (melancolico_profundo, nostalgico). Aqui solo conservamos las formas
        # mas inmediatas para no colisionar con ellos.
        "triste", aliases=("triste", "sad", "blue", "tristeza", "dolido", "down", "depre"),
        axes={"melancholy": 0.7, "euphoria": -0.3, "darkness": 0.2},
        role="priority", perceptual_weight=1.1,
    ),
    Concepto(
        "feliz", aliases=("feliz", "happy", "alegre", "joyful", "contento", "alegria",
                            "animado"),
        axes={"euphoria": 0.6, "brightness": 0.4, "melancholy": -0.4},
        role="priority", perceptual_weight=1.1,
        contradicts=("triste",),
    ),
    Concepto(
        "esperanzador", aliases=("esperanzador", "hopeful", "uplifting", "que levante",
                                       "levantar animo", "esperanza", "animarme"),
        axes={"euphoria": 0.4, "brightness": 0.4, "storytelling": 0.3, "melancholy": -0.1},
        role="priority", perceptual_weight=1.1,
    ),
    Concepto(
        "tranquilo", aliases=("tranquilo", "calm", "relajado", "relax", "chill", "calma",
                                  "tranqui", "calmadito", "calmadita", "para descansar"),
        axes={"calmness": 0.7, "energy": -0.3, "aggressiveness": -0.4},
        role="priority", perceptual_weight=1.1,
        contradicts=("agresivo", "edm_agresivo", "club_party"),
    ),
    Concepto(
        "agresivo", aliases=("agresivo", "aggressive", "intenso", "intense", "duro", "hard",
                                "fuerte", "violento", "rabioso"),
        axes={"aggressiveness": 0.7, "energy": 0.5, "tension": 0.4},
        role="priority", perceptual_weight=1.1,
        contradicts=("tranquilo", "calmness"),
    ),
    Concepto(
        "energetico", aliases=("energetico", "energetica", "energetic", "energico",
                                 "energica", "con energia", "alta energia"),
        axes={"energy": 0.7, "rhythmic_density": 0.3, "calmness": -0.3},
        role="priority", perceptual_weight=1.1,
    ),
    Concepto(
        "etereo_calido", aliases=("calido", "warm", "calida"),
        axes={"brightness": 0.2, "calmness": 0.2, "acoustic_weight": 0.2},
        role="modifier",
    ),

    # -------------------------------------------------------------------------
    # Voces (priority)
    # -------------------------------------------------------------------------
    Concepto(
        "voces_femeninas", aliases=("voces femeninas", "voz femenina", "female vocals",
                                      "female vocalist", "female vocalists", "cantantes mujeres",
                                      "voces de mujer"),
        axes={"vocal_focus": 0.6, "vocal_female": 0.9, "vocal_male": -0.3, "instrumental_focus": -0.4},
        role="priority", perceptual_weight=1.5,
    ),
    Concepto(
        "voces_masculinas", aliases=("voces masculinas", "voz masculina", "male vocals",
                                       "male vocalist", "male vocalists", "cantantes hombres"),
        axes={"vocal_focus": 0.6, "vocal_male": 0.9, "vocal_female": -0.3, "instrumental_focus": -0.4},
        role="priority", perceptual_weight=1.5,
    ),
    Concepto(
        "instrumental", aliases=("instrumental", "sin voz", "without vocals", "no vocals",
                                  "solo instrumental", "musica instrumental"),
        axes={"instrumental_focus": 0.9, "vocal_focus": -0.6},
        role="priority", perceptual_weight=1.4,
        contradicts=("voces_femeninas", "voces_masculinas"),
    ),
    Concepto(
        "que_resalten_voces", aliases=("que resalten las voces", "voces protagonistas",
                                         "que destaque la voz", "voz protagonica",
                                         "donde resalten las voces"),
        axes={"vocal_focus": 0.8, "instrumental_focus": -0.5},
        role="priority", perceptual_weight=1.4,
    ),

    # -------------------------------------------------------------------------
    # Sonido / produccion (modifier)
    # -------------------------------------------------------------------------
    Concepto(
        "bajos_fuertes", aliases=("bajos fuertes", "deep bass", "graves fuertes", "subgraves",
                                    "que retumben", "que peguen los bajos", "graves potentes",
                                    "bombo fuerte", "con bombo", "bajos potentes"),
        axes={"bass_weight": 0.8, "energy": 0.2},
        role="priority", perceptual_weight=1.2,
    ),
    Concepto(
        "acustico", aliases=("acustico", "acoustic", "unplugged"),
        axes={"acoustic_weight": 0.8, "electronic_weight": -0.4, "calmness": 0.2},
        role="modifier", perceptual_weight=1.1,
        contradicts=("electronica", "edm_agresivo"),
    ),
    Concepto(
        "electronico_modifier", aliases=("electronico", "electronica produccion", "sintetico"),
        axes={"electronic_weight": 0.6, "acoustic_weight": -0.3},
        role="modifier",
    ),
    Concepto(
        "oscuro", aliases=("oscuro", "dark", "tenebroso", "sombrio"),
        axes={"darkness": 0.7, "brightness": -0.4, "melancholy": 0.3},
        role="priority", perceptual_weight=1.1,
        contradicts=("brillante",),
    ),
    Concepto(
        "brillante", aliases=("brillante", "bright", "luminoso", "shining"),
        axes={"brightness": 0.7, "darkness": -0.4},
        role="modifier",
        contradicts=("oscuro",),
    ),

    # -------------------------------------------------------------------------
    # Transiciones (transition style)
    # -------------------------------------------------------------------------
    Concepto(
        "transiciones_suaves", aliases=("transiciones suaves", "smooth transitions",
                                          "que fluya", "que fluyan", "fluida"),
        axes={},
        role="modifier", perceptual_weight=1.2,
    ),
    Concepto(
        "transiciones_agresivas", aliases=("transiciones agresivas", "cortes secos",
                                              "transiciones fuertes", "cortes"),
        axes={},
        role="modifier", perceptual_weight=1.2,
    ),
    Concepto(
        "transicion_progresiva", aliases=("subida progresiva", "que vaya subiendo",
                                             "gradualmente", "build up", "progresivo"),
        axes={"storytelling": 0.3, "tension": 0.2},
        role="modifier", perceptual_weight=1.2,
    ),

    # -------------------------------------------------------------------------
    # Contextos de uso (priority)
    # -------------------------------------------------------------------------
    Concepto(
        "entrenar", aliases=("entrenar", "gym", "workout", "correr", "running",
                              "ejercicio", "para entrenar", "hacer ejercicio",
                              "para hacer ejercicio", "hacer deporte", "para hacer deporte",
                              "ejercitarme", "ejercitarse", "para ejercitarme",
                              "deporte", "para el deporte", "trotar", "para trotar",
                              "salir a correr", "para correr", "cardio", "para cardio",
                              "para el gimnasio", "en el gimnasio", "levantar pesas",
                              "hacer pesas", "rutina"),
        axes={"workout_score": 0.8, "energy": 0.5, "rhythmic_density": 0.3, "danceability": 0.3},
        role="priority", perceptual_weight=1.2,
    ),
    Concepto(
        "concentrarse", aliases=("concentrarme", "concentrarse", "concentracion",
                                   "estudiar", "para estudiar", "estudiando", "study",
                                   "focus", "trabajar", "para trabajar", "trabajando",
                                   "para concentrarme", "leer", "para leer", "leyendo",
                                   "manejar", "conducir", "para manejar", "para conducir",
                                   "viaje en carretera", "viaje largo", "por carretera",
                                   "en la carretera"),
        axes={"focus_score": 0.8, "calmness": 0.4, "instrumental_focus": 0.3, "aggressiveness": -0.3},
        role="priority", perceptual_weight=1.2,
    ),
    Concepto(
        "club_party", aliases=("fiesta", "party", "club", "discoteca", "antro", "rumba",
                                  "bailar", "para bailar", "salir a bailar", "salir",
                                  "previa", "para la previa", "after", "after party",
                                  "boliche"),
        axes={"club_energy": 0.8, "danceability": 0.6, "energy": 0.5},
        role="priority", perceptual_weight=1.2,
        boosts=("house", "techno"),
        contradicts=("clasica", "tranquilo", "ambient"),
    ),
    Concepto(
        "cocinar", aliases=("cocinar", "para cocinar", "cocinando", "en la cocina"),
        axes={"calmness": 0.3, "brightness": 0.2, "rhythmic_density": 0.2, "energy": 0.1},
        role="priority", perceptual_weight=1.0,
    ),
    Concepto(
        "lluvioso", aliases=("lluvia", "lluvioso", "lluviosa", "dia lluvioso",
                                "tarde lluviosa", "rainy", "rainy day"),
        axes={"melancholy": 0.4, "calmness": 0.4, "darkness": 0.2, "brightness": -0.1},
        role="priority", perceptual_weight=1.0,
    ),
    Concepto(
        "lo_fi", aliases=("lo-fi", "lofi", "lo fi", "low fi"),
        axes={"calmness": 0.5, "brightness": -0.1, "electronic_weight": 0.3,
              "rhythmic_density": -0.1, "focus_score": 0.3},
        role="priority", perceptual_weight=1.1,
        genres=("lo-fi", "lofi"),
    ),
    Concepto(
        "romantico", aliases=("romantico", "romantica", "romantic", "love"),
        axes={"vocal_focus": 0.5, "calmness": 0.2, "melancholy": 0.1, "brightness": 0.1},
        role="priority", perceptual_weight=1.1,
    ),
    Concepto(
        "sin_edm_agresivo", aliases=("sin edm", "sin edm agresivo", "sin electronica fuerte",
                                        "nada de edm", "no edm"),
        axes={"electronic_weight": -0.5, "aggressiveness": -0.5},
        role="exclusion", perceptual_weight=1.3,
    ),

    # =========================================================================
    # EXPANSION SEMANTICA — conceptos humanos que el parser anterior no captaba
    #
    # Cada concepto define ademas `boosts` (refuerzos) y `contradicts` para que
    # el motor entienda relaciones, no solo keywords. Esto produce
    # interpretacion contextual: "emocionante" no es una palabra suelta, mueve
    # 4 ejes a la vez y refuerza progresiones.
    # =========================================================================

    # --- Emociones / intensidades complementarias ---
    Concepto(
        "emocionante",
        aliases=("emocionante", "emocional", "exciting", "epic moment", "que emocione",
                  "intenso emocionalmente"),
        axes={"euphoria": 0.4, "storytelling": 0.5, "tension": 0.3, "energy": 0.3,
              "cinematic_level": 0.2},
        role="priority", perceptual_weight=1.3,
        boosts=("cinematografico", "narrativo", "transicion_progresiva"),
    ),
    Concepto(
        "sentimental",
        aliases=("sentimental", "sentimental song", "que toque", "que llegue al alma"),
        axes={"melancholy": 0.4, "vocal_focus": 0.4, "calmness": 0.2, "storytelling": 0.3},
        role="priority", perceptual_weight=1.2,
        boosts=("voces_femeninas", "voces_masculinas"),
    ),
    Concepto(
        "melancolico_profundo",
        aliases=("melancolico", "melancolica", "melancholy", "melancholic", "nostalgia profunda",
                  "anhelo", "longing", "wistful"),
        axes={"melancholy": 0.8, "euphoria": -0.3, "darkness": 0.2, "calmness": 0.3,
              "vocal_focus": 0.2},
        role="priority", perceptual_weight=1.2,
        boosts=("triste", "nostalgico"),
    ),
    Concepto(
        "nostalgico",
        aliases=("nostalgico", "nostalgica", "nostalgic", "nostalgia", "recuerdos", "memories"),
        axes={"melancholy": 0.5, "storytelling": 0.4, "brightness": 0.1, "calmness": 0.2},
        role="priority", perceptual_weight=1.1,
    ),
    Concepto(
        "dramatico",
        aliases=("dramatico", "dramatica", "dramatic", "tragico", "tragic"),
        axes={"tension": 0.6, "cinematic_level": 0.5, "darkness": 0.3, "storytelling": 0.4},
        role="priority", perceptual_weight=1.2,
        boosts=("cinematografico",),
    ),
    Concepto(
        "epico",
        aliases=("epico", "epic", "epicas", "epica", "monumental", "grand"),
        axes={"cinematic_level": 0.6, "orchestral_weight": 0.5, "energy": 0.4,
              "storytelling": 0.5, "tension": 0.3},
        role="priority", perceptual_weight=1.3,
        boosts=("cinematografico", "orquestal", "transicion_progresiva"),
    ),
    # NOTA: "intenso" / "intense" ya estan cubiertos por el concepto "agresivo"
    # existente (aliases). Si quieres separar mas finamente "intenso" sin
    # connotacion negativa, hazlo extendiendo "agresivo.axes" o creando un
    # concepto distinto con aliases que NO colisionen ("que pegue", "que golpee").
    Concepto(
        "que_pegue",
        aliases=("que pegue", "que golpee", "que tenga garra", "que sea fuerte",
                  "potente", "powerful"),
        axes={"energy": 0.6, "tension": 0.4, "rhythmic_density": 0.4, "bass_weight": 0.3},
        role="priority", perceptual_weight=1.1,
    ),
    Concepto(
        "suave",
        aliases=("suave", "smooth", "soft", "softly", "gentil", "gentle"),
        axes={"calmness": 0.6, "aggressiveness": -0.5, "tension": -0.3, "energy": -0.2},
        role="priority", perceptual_weight=1.1,
        contradicts=("agresivo", "intenso", "edm_agresivo", "metal"),
    ),
    Concepto(
        "relajante",
        aliases=("relajante", "para relajar", "para descansar", "soothing"),
        axes={"calmness": 0.7, "aggressiveness": -0.5, "energy": -0.3, "focus_score": 0.2},
        role="priority", perceptual_weight=1.2,
        boosts=("tranquilo", "ambient"),
        contradicts=("agresivo", "club_party", "edm_agresivo"),
    ),

    # --- Texturas / atmosferas ---
    Concepto(
        "atmosferico",
        aliases=("atmosferico", "atmospheric", "ambient pad", "wash"),
        axes={"calmness": 0.4, "electronic_weight": 0.3, "cinematic_level": 0.5,
              "instrumental_focus": 0.3, "rhythmic_density": -0.2},
        role="priority", perceptual_weight=1.1,
        boosts=("ambient", "cinematografico"),
    ),
    Concepto(
        "etereo",
        aliases=("etereo", "ethereal", "etherico", "etherea", "dreamy", "dreamlike",
                  "ensoñado", "ensonado"),
        axes={"brightness": 0.4, "calmness": 0.4, "cinematic_level": 0.3,
              "electronic_weight": 0.2, "instrumental_focus": 0.2},
        role="priority", perceptual_weight=1.1,
        boosts=("sonador", "atmosferico"),
    ),
    Concepto(
        "espacial",
        aliases=("espacial", "spacey", "space", "spatial", "cosmico", "cosmic"),
        axes={"electronic_weight": 0.4, "cinematic_level": 0.4, "darkness": 0.2,
              "instrumental_focus": 0.3},
        role="priority", perceptual_weight=1.1,
        boosts=("atmosferico", "etereo", "sonador"),
    ),
    Concepto(
        "futurista",
        aliases=("futurista", "futuristic", "sci fi", "ciberpunk", "cyberpunk"),
        axes={"electronic_weight": 0.6, "darkness": 0.2, "cinematic_level": 0.3,
              "tension": 0.2, "bass_weight": 0.2},
        role="priority", perceptual_weight=1.1,
        boosts=("electronica", "techno", "synthwave"),
    ),
    Concepto(
        "synthwave",
        aliases=("synthwave", "synth wave", "retrowave", "outrun"),
        axes={"electronic_weight": 0.7, "brightness": 0.3, "melancholy": 0.2,
              "bass_weight": 0.3, "cinematic_level": 0.3, "night_score": 0.3},
        role="context", perceptual_weight=1.2,
        genres=("synthwave", "electronic"),
        boosts=("nostalgico", "espacial", "futurista"),
    ),
    Concepto(
        "underground",
        aliases=("underground", "alternativo profundo", "indie underground", "subterraneo"),
        axes={"darkness": 0.3, "aggressiveness": 0.2, "electronic_weight": 0.2},
        role="modifier", perceptual_weight=1.0,
    ),
    Concepto(
        "pesado",
        aliases=("pesado", "pesada", "heavy", "que pese", "denso", "dense"),
        axes={"bass_weight": 0.6, "aggressiveness": 0.4, "energy": 0.5,
              "rhythmic_density": 0.4, "darkness": 0.2},
        role="priority", perceptual_weight=1.2,
    ),
    Concepto(
        "minimal_textural",
        aliases=("minimal", "minimalismo electronico", "minimal techno"),
        axes={"electronic_weight": 0.4, "rhythmic_density": -0.2, "instrumental_focus": 0.3},
        role="modifier",
    ),

    # --- Detalles instrumentales / produccion ---
    Concepto(
        "bajos_profundos",
        aliases=("bajos profundos", "deep bass", "subbass", "sub bass", "graves profundos",
                  "808", "que tenga sub"),
        axes={"bass_weight": 0.9, "darkness": 0.2, "rhythmic_density": 0.2},
        role="priority", perceptual_weight=1.3,
        boosts=("bajos_fuertes",),
    ),
    Concepto(
        "percusion_fuerte",
        aliases=("percusion fuerte", "que peguen los tambores", "drums fuertes", "hard drums",
                  "punchy drums", "ritmo fuerte"),
        axes={"rhythmic_density": 0.7, "energy": 0.4, "danceability": 0.3},
        role="priority", perceptual_weight=1.2,
    ),
    Concepto(
        "vocal_dominante",
        aliases=("vocal dominante", "vocal protagonica", "que mande la voz", "donde mande la voz",
                  "voz al frente", "voz dominante"),
        axes={"vocal_focus": 0.9, "instrumental_focus": -0.5},
        role="priority", perceptual_weight=1.4,
        boosts=("que_resalten_voces",),
    ),
    Concepto(
        "voz_femenina_suave",
        aliases=("voz femenina suave", "voces femeninas suaves", "soft female vocals"),
        axes={"vocal_female": 0.9, "vocal_focus": 0.7, "calmness": 0.4, "aggressiveness": -0.5,
              "vocal_male": -0.3},
        role="priority", perceptual_weight=1.5,
        boosts=("voces_femeninas", "suave"),
    ),
    Concepto(
        "voz_masculina_grave",
        aliases=("voz masculina grave", "voz profunda masculina", "deep male vocals",
                  "voz baja masculina"),
        axes={"vocal_male": 0.9, "vocal_focus": 0.7, "darkness": 0.3, "bass_weight": 0.2,
              "vocal_female": -0.3},
        role="priority", perceptual_weight=1.4,
    ),

    # --- Modifiers de intensidad (amplificadores) ---
    # Estos NO mueven ejes; el parser los detecta y amplifica los conceptos
    # contiguos detectados (ver intencion.py).
    Concepto(
        "modifier_mucho",
        aliases=("mucho", "muy", "bastante", "extra", "super", "very", "really"),
        axes={},
        role="modifier", perceptual_weight=0.0,
    ),
    Concepto(
        "modifier_poco",
        aliases=("un poco", "ligero", "leve", "ligeramente", "lightly", "slightly", "discreto"),
        axes={},
        role="modifier", perceptual_weight=0.0,
    ),
)


# =============================================================================
# INDICES PRECOMPUTADOS
# =============================================================================

def _normalizar_para_busqueda(texto: str) -> str:
    """Lowercase + sin acentos + espacios normalizados. Acepta None.

    No uso utils.text.para_comparacion aqui para evitar dependencias circulares
    con la cadena de imports del paquete y para preservar simbolos como '&'
    si fueran necesarios en aliases futuros (aunque hoy no se usan).
    """
    if not texto:
        return ""
    norm = unicodedata.normalize("NFKD", texto)
    sin_diacriticos = "".join(c for c in norm if not unicodedata.combining(c))
    sin_diacriticos = sin_diacriticos.lower()
    sin_diacriticos = re.sub(r"[^\w\s]", " ", sin_diacriticos)
    sin_diacriticos = re.sub(r"\s+", " ", sin_diacriticos).strip()
    return sin_diacriticos


_INDICE_ALIAS_A_CONCEPTO: dict[str, Concepto] = {}
_INDICE_NOMBRE_A_CONCEPTO: dict[str, Concepto] = {}
_ALIASES_ORDENADOS: list[tuple[str, Concepto]] = []


def _construir_indices() -> None:
    """Construye los indices de busqueda al cargar el modulo.

    El orden por longitud descendente es crucial para detectar
    "voces femeninas" antes que "voces" o "femenina" como sub-tokens.
    """
    global _ALIASES_ORDENADOS
    pares: list[tuple[str, Concepto]] = []
    for concepto in CONCEPTOS:
        _INDICE_NOMBRE_A_CONCEPTO[concepto.name] = concepto
        for alias in concepto.aliases:
            alias_norm = _normalizar_para_busqueda(alias)
            if not alias_norm:
                continue
            _INDICE_ALIAS_A_CONCEPTO[alias_norm] = concepto
            pares.append((alias_norm, concepto))
    pares.sort(key=lambda par: len(par[0]), reverse=True)
    _ALIASES_ORDENADOS = pares


_construir_indices()


# =============================================================================
# API PUBLICA — busqueda de conceptos en texto
# =============================================================================

@dataclass(frozen=True)
class CoincidenciaConcepto:
    """Una coincidencia detectada en el texto del usuario."""
    concepto: Concepto
    alias: str
    inicio: int
    fin: int


def buscar_conceptos(texto: str) -> list[CoincidenciaConcepto]:
    """Detecta conceptos en un texto libre.

    Estrategia: greedy por longitud descendente con marcado de regiones
    consumidas, para evitar dobles matches solapados ("voces femeninas"
    no debe disparar tambien "voces").

    Retorna las coincidencias en orden de aparicion en el texto original.
    Es deterministico y O(n*m) sobre el tamano del texto y aliases.
    """
    texto_norm = _normalizar_para_busqueda(texto)
    if not texto_norm:
        return []

    consumido = [False] * len(texto_norm)
    encontrados: list[CoincidenciaConcepto] = []

    for alias_norm, concepto in _ALIASES_ORDENADOS:
        idx = 0
        while idx <= len(texto_norm) - len(alias_norm):
            pos = texto_norm.find(alias_norm, idx)
            if pos == -1:
                break
            fin = pos + len(alias_norm)
            # Frontera de palabra (evita "rocky" -> "rock" como falso match)
            antes_ok = pos == 0 or not texto_norm[pos - 1].isalnum()
            despues_ok = fin == len(texto_norm) or not texto_norm[fin].isalnum()
            disponible = not any(consumido[pos:fin])
            if antes_ok and despues_ok and disponible:
                for k in range(pos, fin):
                    consumido[k] = True
                encontrados.append(CoincidenciaConcepto(
                    concepto=concepto, alias=alias_norm, inicio=pos, fin=fin
                ))
            idx = pos + 1

    encontrados.sort(key=lambda m: m.inicio)
    return encontrados


def obtener_concepto(nombre: str) -> Optional[Concepto]:
    """Acceso por nombre interno del concepto."""
    return _INDICE_NOMBRE_A_CONCEPTO.get(nombre)


def todos_los_conceptos() -> tuple[Concepto, ...]:
    """Lista completa de conceptos (orden estable)."""
    return CONCEPTOS


# =============================================================================
# AGREGACION DE EJES
# =============================================================================

def agregar_ejes(
    coincidencias: Iterable[CoincidenciaConcepto],
    *,
    factores_por_inicio: Optional[dict[int, float]] = None,
) -> dict[str, float]:
    """Combina los votos de varios conceptos en un mapa eje->valor.

    Regla:
      - Cada concepto contribuye axes[eje] * perceptual_weight * factor.
      - `factores_por_inicio` mapea posiciones a multiplicadores (>1 amplifica,
        <1 atenua). Lo aplican los amplificadores del parser ("muy", "un poco").
      - Los votos se SUMAN (no se promedian) para preservar la intensidad.
      - El resultado NO se clipea a [0,1]: el scheduler normaliza.
      - Conceptos con role="exclusion" suman su delta (negativo).

    Si no hay coincidencias, retorna dict vacio.
    """
    acumulado: dict[str, float] = {}
    factores = factores_por_inicio or {}
    for match in coincidencias:
        concepto = match.concepto
        peso = concepto.perceptual_weight
        factor = factores.get(match.inicio, 1.0)
        for eje, delta in concepto.axes.items():
            acumulado[eje] = acumulado.get(eje, 0.0) + delta * peso * factor
    return acumulado


def aplicar_boosts(
    coincidencias: Iterable[CoincidenciaConcepto],
    axes: dict[str, float],
) -> dict[str, float]:
    """Aplica refuerzos cuando un concepto detectado tiene `boosts` activos.

    Si A esta detectado y A.boosts incluye B, y B tambien esta detectado:
      - El peso de los axes que ambos comparten se amplifica un 25%.
    No es un loop: aplica una sola pasada por par detectado.

    Retorna un nuevo dict con axes ajustados.
    """
    nombres_detectados = {m.concepto.name for m in coincidencias}
    resultado = dict(axes)
    for match in coincidencias:
        for objetivo in match.concepto.boosts:
            if objetivo not in nombres_detectados:
                continue
            concepto_objetivo = _INDICE_NOMBRE_A_CONCEPTO.get(objetivo)
            if concepto_objetivo is None:
                continue
            # Ejes compartidos -> +25% del valor actual
            for eje in match.concepto.axes:
                if eje in concepto_objetivo.axes and eje in resultado:
                    resultado[eje] *= 1.25
    return resultado


def detectar_contradicciones(coincidencias: Iterable[CoincidenciaConcepto]) -> list[tuple[str, str]]:
    """Devuelve pares (a, b) de conceptos detectados que se contradicen.

    No resuelve la contradiccion (eso es decision del intent layer); solo
    reporta los choques para que el sistema pueda explicarlos al usuario
    o aplicar prioridades.
    """
    nombres = [m.concepto.name for m in coincidencias]
    set_nombres = set(nombres)
    pares: list[tuple[str, str]] = []
    vistos: set[tuple[str, str]] = set()
    for match in coincidencias:
        for opuesto in match.concepto.contradicts:
            if opuesto in set_nombres:
                clave = tuple(sorted((match.concepto.name, opuesto)))
                if clave not in vistos:
                    vistos.add(clave)
                    pares.append((clave[0], clave[1]))
    return pares


def generos_sugeridos(coincidencias: Iterable[CoincidenciaConcepto]) -> dict[str, float]:
    """Hint de generos extraido de los conceptos detectados.

    Cada concepto puede sugerir generos (pista contextual). Esto NO es el
    output principal del intent (los ejes lo son), pero ayuda al scheduler
    a filtrar/priorizar candidatos cuando se prefiere uno u otro estilo.
    """
    pesos: dict[str, float] = {}
    for match in coincidencias:
        concepto = match.concepto
        if not concepto.genres:
            continue
        # Conceptos de tipo exclusion no anaden generos positivamente.
        if concepto.role == "exclusion":
            continue
        peso_por_genero = concepto.perceptual_weight / max(len(concepto.genres), 1)
        for genero in concepto.genres:
            pesos[genero] = pesos.get(genero, 0.0) + peso_por_genero
    return pesos


def estilo_transicion_sugerido(coincidencias: Iterable[CoincidenciaConcepto]) -> dict[str, float]:
    """Detecta intencion sobre el estilo de transicion.

    Mapea conceptos de modificacion de transicion a los estilos disponibles.
    El scheduler lo usa para ajustar pesos del scoring de transicion entre
    pistas adyacentes.
    """
    pesos: dict[str, float] = {}
    for match in coincidencias:
        nombre = match.concepto.name
        if nombre == "transiciones_suaves":
            pesos["smooth"] = pesos.get("smooth", 0.0) + 1.0
        elif nombre == "transiciones_agresivas":
            pesos["aggressive"] = pesos.get("aggressive", 0.0) + 1.0
        elif nombre == "transicion_progresiva":
            pesos["energetic"] = pesos.get("energetic", 0.0) + 0.6
            pesos["smooth"] = pesos.get("smooth", 0.0) + 0.3
        elif nombre == "cinematografico":
            pesos["cinematic"] = pesos.get("cinematic", 0.0) + 0.7
        elif nombre == "clasica":
            pesos["harmonic"] = pesos.get("harmonic", 0.0) + 0.5
            pesos["smooth"] = pesos.get("smooth", 0.0) + 0.3
    return pesos


def curva_energia_sugerida(coincidencias: Iterable[CoincidenciaConcepto]) -> Optional[str]:
    """Determina curva de energia explicita si el prompt la sugiere.

    Retorna None si no hay senal clara, dejando al intent layer aplicar
    su default (normalmente 'stable' o 'progressive' segun contexto).

    La logica detecta indicios narrativos: si el prompt sugiere construccion
    progresiva o subida final, la curva se vuelve "peak". Si sugiere
    contencion emocional o cierre, se vuelve "descending". Etc.
    """
    nombres = {m.concepto.name for m in coincidencias}
    # Progressive: building up energy
    if any(n in nombres for n in (
        "transicion_progresiva", "entrenar", "emocionante", "epico", "dramatico",
    )):
        return "progressive"
    # Peak: climax dramatic
    if any(n in nombres for n in ("club_party",)):
        return "peak"
    # Stable: focus / chill
    if any(n in nombres for n in (
        "concentrarse", "tranquilo", "ambient", "relajante", "atmosferico",
    )):
        return "stable"
    # Descending: night / cooldown
    if any(n in nombres for n in (
        "nocturno", "triste", "melancolico_profundo", "nostalgico", "sentimental",
    )):
        return "descending"
    # Wave: cinematic, narrative
    if any(n in nombres for n in ("cinematografico", "narrativo")):
        return "wave"
    return None
