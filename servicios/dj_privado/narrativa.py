# =============================================================================
# servicios/dj_privado/narrativa.py
#
# Modelo de narrativa de sesion (Session Energy Profile).
#
# Antes la "curva de energia" era una funcion atemporal con 5 formas fijas
# (stable/progressive/wave/descending/peak). Funcionaba como ordenamiento
# pero NO comunicaba intencion narrativa. Una sesion real tiene fases con
# proposito distinto: warmup, groove, peak, release, cooldown.
#
# Este modulo aporta:
#   - SessionPhase: dataclass con un slot temporal [start_t, end_t] y un
#     objetivo energetico (target_energy, target_tension, target_density,
#     target_brightness).
#   - perfil_para_intent(intent, duracion_seg) -> list[SessionPhase] que
#     reparte el tiempo total entre fases segun la intencion.
#   - objetivos_para_posicion(perfil, t) -> dict de ejes objetivo en t.
#
# Esta capa NO selecciona pistas: el scheduler lee los objetivos en cada
# posicion y los aproxima.
#
# El perfil tambien sirve a la UI para mostrar "estamos en groove" o
# "entrando al peak". Por eso los nombres de fase se publican como
# strings estables.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass

from servicios.dj_privado.intencion import IntentMusical


# Nombres canonicos de fase. Usar SOLO estos en codigo y UI.
PHASE_WARMUP   = "warmup"     # apertura, energia baja-media, presenta el clima
PHASE_GROOVE   = "groove"     # ritmo establecido, mantenimiento de energia
PHASE_PEAK     = "peak"       # climax energetico o emocional
PHASE_RELEASE  = "release"    # salida del peak, atenuacion gradual
PHASE_COOLDOWN = "cooldown"   # cierre, energia baja, resolucion narrativa

PHASES = (PHASE_WARMUP, PHASE_GROOVE, PHASE_PEAK, PHASE_RELEASE, PHASE_COOLDOWN)


@dataclass(frozen=True)
class SessionPhase:
    """Una fase de la sesion con su slot temporal y objetivos energeticos.

    Tiempo se expresa normalizado [0, 1] sobre la duracion total. El motor
    construye el perfil una sola vez; el scheduler interpola entre fases.
    """
    name: str            # uno de PHASES
    start_t: float       # inicio (0..1)
    end_t: float         # fin (0..1) (exclusivo logicamente)
    target_energy: float       # 0..1
    target_tension: float      # 0..1
    target_density: float      # 0..1 (rhythmic_density)
    target_brightness: float   # 0..1
    target_calmness: float     # 0..1
    # Una nota legible para mostrar al usuario en la UI ("entrando al peak").
    descripcion: str = ""


# =============================================================================
# CONSTRUCCION DE PERFILES POR INTENT
# =============================================================================

def _proporcion_fases(curva: str) -> list[tuple[str, float]]:
    """Devuelve las fases activas con su proporcion del tiempo total.

    Las proporciones suman 1.0. La curva "stable" colapsa a una sola fase
    de groove largo. "Progressive" alarga warmup+groove con peak final.
    """
    if curva == "progressive":
        # subida progresiva: warmup corto, groove largo, peak fuerte al final
        return [
            (PHASE_WARMUP,   0.15),
            (PHASE_GROOVE,   0.35),
            (PHASE_PEAK,     0.30),
            (PHASE_RELEASE,  0.15),
            (PHASE_COOLDOWN, 0.05),
        ]
    if curva == "peak":
        # club: subida rapida, peak largo, descenso al final
        return [
            (PHASE_WARMUP,   0.10),
            (PHASE_GROOVE,   0.20),
            (PHASE_PEAK,     0.45),
            (PHASE_RELEASE,  0.15),
            (PHASE_COOLDOWN, 0.10),
        ]
    if curva == "descending":
        # de alto a bajo: no hay peak en medio, todo desciende
        return [
            (PHASE_WARMUP,   0.10),
            (PHASE_GROOVE,   0.25),
            (PHASE_RELEASE,  0.35),
            (PHASE_COOLDOWN, 0.30),
        ]
    if curva == "wave":
        # ondulante: warmup, peak medio, retorno a groove, cierre
        return [
            (PHASE_WARMUP,   0.15),
            (PHASE_GROOVE,   0.20),
            (PHASE_PEAK,     0.25),
            (PHASE_GROOVE,   0.25),
            (PHASE_COOLDOWN, 0.15),
        ]
    # stable: una sola fase larga de groove con apertura y cierre cortos
    return [
        (PHASE_WARMUP,   0.10),
        (PHASE_GROOVE,   0.75),
        (PHASE_COOLDOWN, 0.15),
    ]


def _objetivos_base(phase: str) -> dict:
    """Mapa de ejes objetivo por fase. Valores conservadores (rango medio)."""
    if phase == PHASE_WARMUP:
        return {"energy": 0.45, "tension": 0.30, "density": 0.40,
                "brightness": 0.55, "calmness": 0.55}
    if phase == PHASE_GROOVE:
        return {"energy": 0.60, "tension": 0.45, "density": 0.55,
                "brightness": 0.55, "calmness": 0.45}
    if phase == PHASE_PEAK:
        return {"energy": 0.85, "tension": 0.65, "density": 0.75,
                "brightness": 0.60, "calmness": 0.20}
    if phase == PHASE_RELEASE:
        return {"energy": 0.55, "tension": 0.40, "density": 0.45,
                "brightness": 0.50, "calmness": 0.55}
    # cooldown
    return {"energy": 0.35, "tension": 0.25, "density": 0.30,
            "brightness": 0.45, "calmness": 0.75}


def _ajustar_por_intent(base: dict, intent: IntentMusical, phase: str) -> dict:
    """Ajusta los objetivos base segun los axes del intent.

    Por ejemplo, si el intent tiene mucho `calmness`, el peak se atempera
    (no llega a 0.85 sino a 0.65). Si tiene mucho `tension`, el groove tiene
    mas tension de la base.
    """
    salida = dict(base)
    axes = intent.axes or {}

    # Aliases entre nombres de ontologia y campos del perfil
    map_eje_a_target = {
        "energy":     "energy",
        "tension":    "tension",
        "rhythmic_density": "density",
        "brightness": "brightness",
        "darkness":   "brightness",  # darkness reduce brightness
        "calmness":   "calmness",
        "aggressiveness": "tension",
    }
    for eje, target in map_eje_a_target.items():
        valor = axes.get(eje, 0.0)
        if valor == 0:
            continue
        # Para 'darkness', invertimos
        signo = -1.0 if eje == "darkness" else 1.0
        ajuste = signo * valor * 0.15  # max ~15% por eje
        salida[target] = max(0.0, min(1.0, salida[target] + ajuste))

    # Si el intent tiene `calmness` alto y la fase es peak, atemperar.
    if phase == PHASE_PEAK:
        calmness_intent = axes.get("calmness", 0.0)
        if calmness_intent > 0.5:
            salida["energy"] = max(0.5, salida["energy"] - 0.20)
            salida["tension"] = max(0.3, salida["tension"] - 0.15)

    return salida


def construir_perfil(intent: IntentMusical) -> list[SessionPhase]:
    """Construye el perfil de fases segun el intent.

    Las fases respetan la curva de energia del intent. El producto es una
    lista ORDENADA por start_t con start/end normalizados [0, 1].
    """
    curva = intent.curva_energia or "stable"
    proporciones = _proporcion_fases(curva)
    fases: list[SessionPhase] = []
    cursor = 0.0
    for nombre, peso in proporciones:
        fin = min(1.0, cursor + peso)
        base = _objetivos_base(nombre)
        ajustado = _ajustar_por_intent(base, intent, nombre)
        descripcion = _descripcion_humana(nombre)
        fases.append(SessionPhase(
            name=nombre,
            start_t=cursor,
            end_t=fin,
            target_energy=ajustado["energy"],
            target_tension=ajustado["tension"],
            target_density=ajustado["density"],
            target_brightness=ajustado["brightness"],
            target_calmness=ajustado["calmness"],
            descripcion=descripcion,
        ))
        cursor = fin
    # Asegurar que la ultima fase llega exactamente a 1.0 (compensar
    # acumulacion de errores de coma flotante).
    if fases:
        ultima = fases[-1]
        fases[-1] = SessionPhase(
            name=ultima.name,
            start_t=ultima.start_t,
            end_t=1.0,
            target_energy=ultima.target_energy,
            target_tension=ultima.target_tension,
            target_density=ultima.target_density,
            target_brightness=ultima.target_brightness,
            target_calmness=ultima.target_calmness,
            descripcion=ultima.descripcion,
        )
    return fases


def _descripcion_humana(phase: str) -> str:
    return {
        PHASE_WARMUP:   "Apertura, presentando el clima",
        PHASE_GROOVE:   "Ritmo establecido, sostenido",
        PHASE_PEAK:     "Climax energetico",
        PHASE_RELEASE:  "Bajando del pico, atenuacion",
        PHASE_COOLDOWN: "Cierre, resolucion",
    }.get(phase, phase)


# =============================================================================
# CONSULTA POR POSICION
# =============================================================================

def fase_en_t(perfil: list[SessionPhase], t: float) -> SessionPhase:
    """Devuelve la fase activa en tiempo normalizado t (0..1).

    Si t cae fuera del rango, retorna la fase mas cercana (warmup si t<0,
    cooldown si t>1). NUNCA retorna None: la UI puede asumir el invariante.
    """
    if not perfil:
        # Default seguro
        return SessionPhase(
            name=PHASE_GROOVE, start_t=0.0, end_t=1.0,
            target_energy=0.5, target_tension=0.4, target_density=0.5,
            target_brightness=0.5, target_calmness=0.5,
            descripcion="Sesion sin perfil definido",
        )
    if t <= 0.0:
        return perfil[0]
    if t >= 1.0:
        return perfil[-1]
    for fase in perfil:
        if fase.start_t <= t < fase.end_t:
            return fase
    return perfil[-1]


def objetivos_para_posicion(perfil: list[SessionPhase], t: float) -> dict[str, float]:
    """Devuelve los ejes objetivo (energy/tension/density/brightness/calmness)
    para una posicion normalizada t.

    Internamente interpola linealmente entre el objetivo de la fase actual y
    el objetivo de la fase siguiente, dentro del 25% final de la fase actual.
    Esto evita saltos abruptos en frontera de fase.
    """
    if not perfil:
        return {"energy": 0.5, "tension": 0.4, "density": 0.5,
                "brightness": 0.5, "calmness": 0.5}

    fase_actual = fase_en_t(perfil, t)
    idx_actual = perfil.index(fase_actual)

    # ¿Estamos en el 25% final de la fase? Si si, interpolar con la siguiente.
    duracion_fase = max(1e-6, fase_actual.end_t - fase_actual.start_t)
    avance_fase = (t - fase_actual.start_t) / duracion_fase  # 0..1 dentro de la fase

    target = {
        "energy":     fase_actual.target_energy,
        "tension":    fase_actual.target_tension,
        "density":    fase_actual.target_density,
        "brightness": fase_actual.target_brightness,
        "calmness":   fase_actual.target_calmness,
    }

    if avance_fase > 0.75 and idx_actual + 1 < len(perfil):
        siguiente = perfil[idx_actual + 1]
        # Interpolacion lineal en el 25% final
        peso_siguiente = (avance_fase - 0.75) / 0.25  # 0..1
        peso_actual = 1.0 - peso_siguiente
        target["energy"]     = peso_actual * fase_actual.target_energy     + peso_siguiente * siguiente.target_energy
        target["tension"]    = peso_actual * fase_actual.target_tension    + peso_siguiente * siguiente.target_tension
        target["density"]    = peso_actual * fase_actual.target_density    + peso_siguiente * siguiente.target_density
        target["brightness"] = peso_actual * fase_actual.target_brightness + peso_siguiente * siguiente.target_brightness
        target["calmness"]   = peso_actual * fase_actual.target_calmness   + peso_siguiente * siguiente.target_calmness

    return target


def perfil_a_dict(perfil: list[SessionPhase]) -> list[dict]:
    """Serializa el perfil para QML/persistencia. Lista de dicts."""
    return [
        {
            "name":              f.name,
            "start_t":           round(f.start_t, 4),
            "end_t":             round(f.end_t, 4),
            "target_energy":     round(f.target_energy, 3),
            "target_tension":    round(f.target_tension, 3),
            "target_density":    round(f.target_density, 3),
            "target_brightness": round(f.target_brightness, 3),
            "target_calmness":   round(f.target_calmness, 3),
            "descripcion":       f.descripcion,
        }
        for f in perfil
    ]
