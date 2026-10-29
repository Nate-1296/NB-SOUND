# =============================================================================
# servicios/dj_privado/intencion.py
#
# Intent estructurado del DJ Privado.
#
# Una IntentMusical es la traduccion DETERMINISTICA del prompt del usuario
# a una estructura controlable que el scheduler puede consumir directamente.
# NO depende de LLMs ni de modelos generativos. Cualquier ambiguedad se
# resuelve con reglas explicitas y prioridades de la ontologia.
#
# Filosofia:
#   "texto -> estructura musical" (no "texto -> genero")
#
# El intent NO produce una playlist. El intent produce CONTROLES:
#   - desplazamientos en ejes perceptuales (que ejes priorizar y cuanto)
#   - listas de exclusion (que NO mostrar)
#   - sesgos de genero (hint suave, no filtro duro)
#   - estilo de transicion deseado
#   - curva de energia
#   - foco perceptual ("voces femeninas" antes que "pop")
#
# Se serializa a/desde JSON para persistir en dj_sesiones.intent_json.
# =============================================================================

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from typing import Optional

from servicios.dj_privado.ontologia import (
    CoincidenciaConcepto,
    agregar_ejes,
    aplicar_boosts,
    buscar_conceptos,
    curva_energia_sugerida,
    detectar_contradicciones,
    estilo_transicion_sugerido,
    generos_sugeridos,
)


# =============================================================================
# DETECCION DE NEGACIONES
#
# La ontologia detecta conceptos en texto, pero no sabe si fueron negados.
# Frases como "sin agresivo", "nada de pop", "no quiero edm" deben revertir
# el efecto del concepto detectado.
#
# El sistema usa una ventana de palabras antes del concepto detectado para
# decidir si esta negado, en vez de un parser sintactico complejo (que seria
# fragil con prompts cortos y mezcla de idiomas).
# =============================================================================

_NEGADORES = (
    "sin",
    "nada de",
    "no",
    "no quiero",
    "no me gusta",
    "menos",
    "sin nada de",
    "evita",
    "evitar",
    "without",
    "no ",
    "skip",
)

# Palabras que CORTAN el alcance de la negacion (no encadenar negaciones
# accidentalmente). Ej: "no quiero pop pero si rock" -> "rock" no esta negado.
_RUPTORES = ("pero", "but", "aunque", "y", "and", "con", "with", "que")

# Modificadores de intensidad que multiplican el peso del proximo concepto.
# Estos son detectados como conceptos en la ontologia, pero su `axes` es
# vacio: aqui les damos significado real amplificando el siguiente match.
_AMPLIFICADORES_FUERTES = ("modifier_mucho",)
_AMPLIFICADORES_DEBILES = ("modifier_poco",)
_FACTOR_FUERTE = 1.6
_FACTOR_DEBIL  = 0.55


def _normalizar(texto: str) -> str:
    """Misma normalizacion que la ontologia (lowercase + sin acentos)."""
    if not texto:
        return ""
    norm = unicodedata.normalize("NFKD", texto)
    sin = "".join(c for c in norm if not unicodedata.combining(c))
    sin = sin.lower()
    sin = re.sub(r"[^\w\s]", " ", sin)
    sin = re.sub(r"\s+", " ", sin).strip()
    return sin


def _segmento_previo(texto_norm: str, fin_anterior: int, inicio_actual: int) -> str:
    """Texto entre dos coincidencias (o desde el inicio si no hay anterior)."""
    return texto_norm[fin_anterior:inicio_actual]


def _esta_negado(segmento_previo: str) -> bool:
    """Determina si el segmento inmediatamente previo niega el concepto.

    Busca un negador en las ultimas ~4 palabras del segmento previo.
    Si encuentra un ruptor entre el negador y el concepto, la negacion
    no se propaga (ej. "sin pop pero CON rock" -> rock NO negado).
    """
    if not segmento_previo:
        return False
    tokens = segmento_previo.strip().split()
    if not tokens:
        return False
    # Solo miramos las ultimas 4 palabras
    ventana = tokens[-4:]
    ventana_str = " ".join(ventana)
    # Hay un negador en la ventana?
    negador_idx = -1
    for neg in _NEGADORES:
        idx = ventana_str.find(neg)
        if idx >= 0:
            if negador_idx < 0 or idx > negador_idx:
                negador_idx = idx
    if negador_idx < 0:
        return False
    # Algun ruptor APARECE DESPUES del negador y antes del final?
    resto = ventana_str[negador_idx + 1:]
    for ruptor in _RUPTORES:
        # ruptor como palabra entera
        if re.search(rf"\b{re.escape(ruptor)}\b", resto):
            return False
    return True


# =============================================================================
# INTENT ESTRUCTURADO
# =============================================================================

@dataclass
class IntentMusical:
    """Resultado del parseo del prompt del usuario.

    Esta es la estructura que el scheduler consume. Todos los campos son
    autocontenidos y serializables. La intencion no contiene logica.
    """

    # Prompt original (para mostrar/persistir).
    prompt: str

    # Mapa eje -> valor agregado. Positivo = atraer, negativo = repeler.
    # No se clipea: el scheduler decide como normalizar al puntuar tracks.
    axes: dict[str, float] = field(default_factory=dict)

    # Conceptos detectados como prioridad (los que el usuario explicitamente
    # quiere destacar). Estos tienen peso adicional en el ranking.
    focos: tuple[str, ...] = ()

    # Conceptos negados explicitamente. Se aplican como filtros suaves
    # (penalizacion fuerte) o duros (exclusion completa) segun el role.
    exclusiones: tuple[str, ...] = ()

    # Generos sugeridos (peso normalizado). Hint suave, no filtro.
    generos: dict[str, float] = field(default_factory=dict)

    # Generos explicitamente excluidos (por negacion). Filtro duro.
    generos_excluidos: tuple[str, ...] = ()

    # Curva de energia objetivo para la sesion completa.
    curva_energia: str = "stable"

    # Pesos relativos de estilos de transicion para el motor de transiciones.
    estilo_transicion: dict[str, float] = field(default_factory=dict)

    # Contradicciones detectadas (pares concepto-concepto). Informativo.
    contradicciones: tuple[tuple[str, str], ...] = ()

    # Si el prompt no genero suficiente senal, el intent queda "vacio".
    # El scheduler interpreta esto como "selecion general inteligente".
    vacio: bool = False

    # Notas legibles para mostrar al usuario (no son razones de selection;
    # son notas del intent: "no entendí X", "voy a priorizar Y", etc.).
    notas: tuple[str, ...] = ()

    # Resumen humano: una frase que describe lo que se entendió.
    resumen: str = ""

    # Duracion objetivo de la sesion en minutos. Default 60.
    duracion_minutos: int = 60

    # Version del motor que produjo este intent. Util para migrar sesiones.
    motor_version: str = "dj_intent_v1"

    # ---- Serializacion ----

    def to_dict(self) -> dict:
        data = asdict(self)
        # Convertir tuplas a listas para JSON
        data["focos"] = list(self.focos)
        data["exclusiones"] = list(self.exclusiones)
        data["generos_excluidos"] = list(self.generos_excluidos)
        data["contradicciones"] = [list(par) for par in self.contradicciones]
        data["notas"] = list(self.notas)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict) -> "IntentMusical":
        kwargs = dict(data)
        kwargs["focos"] = tuple(data.get("focos", ()))
        kwargs["exclusiones"] = tuple(data.get("exclusiones", ()))
        kwargs["generos_excluidos"] = tuple(data.get("generos_excluidos", ()))
        contradicciones = data.get("contradicciones", ())
        kwargs["contradicciones"] = tuple(tuple(par) for par in contradicciones)
        kwargs["notas"] = tuple(data.get("notas", ()))
        return cls(**kwargs)

    @classmethod
    def from_json(cls, payload: str) -> "IntentMusical":
        return cls.from_dict(json.loads(payload or "{}"))


# =============================================================================
# PARSER PRINCIPAL
# =============================================================================

def parsear_intent(prompt: str, *, duracion_minutos: int = 60) -> IntentMusical:
    """Convierte un prompt en una IntentMusical.

    Pasos:
      1. Detectar conceptos en el texto (ontologia).
      2. Detectar negaciones por proximidad de negadores.
      3. Particionar coincidencias en (positivas, negadas).
      4. Agregar ejes (positivos suman, negados se restan).
      5. Resolver contradicciones (la prioridad mas alta gana).
      6. Calcular curva de energia, estilo de transicion, generos.
      7. Construir notas humanas legibles.
    """
    prompt_limpio = (prompt or "").strip()
    if not prompt_limpio:
        return IntentMusical(
            prompt="",
            vacio=True,
            duracion_minutos=duracion_minutos,
            resumen="Sesion general sin intencion especifica.",
            notas=("No ingresaste una indicacion; usare seleccion general.",),
        )

    texto_norm = _normalizar(prompt_limpio)
    coincidencias = buscar_conceptos(prompt_limpio)

    if not coincidencias:
        return IntentMusical(
            prompt=prompt_limpio,
            vacio=True,
            duracion_minutos=duracion_minutos,
            resumen="No reconoci conceptos musicales claros. Hare una seleccion general.",
            notas=(
                "Prueba con expresiones como 'algo para concentrarme', "
                "'bajos fuertes', 'voces femeninas', 'cinematografico', "
                "'sin EDM agresivo', 'subida progresiva para entrenar'.",
            ),
        )

    # ---- Particionar positivos vs negados ----
    # Tambien aplicamos amplificadores: si un "modifier_mucho/poco" aparece
    # inmediatamente ANTES de un concepto con axes, se multiplica el peso
    # de ese concepto. Los amplificadores en si no se conservan (su axes es
    # vacio y solo sirven semanticamente).
    positivos: list[CoincidenciaConcepto] = []
    negados: list[CoincidenciaConcepto] = []
    factores_aplicados: dict[int, float] = {}   # inicio -> factor
    amplificador_pendiente: Optional[float] = None
    fin_anterior = 0

    for match in coincidencias:
        segmento = _segmento_previo(texto_norm, fin_anterior, match.inicio)
        nombre = match.concepto.name

        # Si el match ES un amplificador, lo registramos y NO lo agregamos.
        if nombre in _AMPLIFICADORES_FUERTES:
            amplificador_pendiente = _FACTOR_FUERTE
            fin_anterior = match.fin
            continue
        if nombre in _AMPLIFICADORES_DEBILES:
            amplificador_pendiente = _FACTOR_DEBIL
            fin_anterior = match.fin
            continue

        # Si hay un amplificador pendiente Y la distancia al concepto es
        # corta (<=12 chars) lo aplicamos al concepto que viene.
        if amplificador_pendiente is not None:
            distancia = len(segmento.strip())
            if distancia <= 12:
                factores_aplicados[match.inicio] = amplificador_pendiente
            amplificador_pendiente = None

        # El concepto de role="exclusion" YA es negativo por construccion
        # (sus axes son negativos), no se invierte de nuevo.
        if match.concepto.role == "exclusion":
            positivos.append(match)
        elif _esta_negado(segmento):
            negados.append(match)
        else:
            positivos.append(match)
        fin_anterior = match.fin

    # ---- Resolver contradicciones ----
    # Si "tranquilo" y "agresivo" estan ambos como positivos, gana el que
    # tenga mayor perceptual_weight. Si empatan, gana el ultimo mencionado
    # (interpreta el final del prompt como matiz final).
    contradicciones_detectadas = detectar_contradicciones(positivos)
    if contradicciones_detectadas:
        positivos = _resolver_contradicciones(positivos, contradicciones_detectadas)

    # ---- Agregar ejes (con factores de amplificadores) ----
    axes_positivos = agregar_ejes(positivos, factores_por_inicio=factores_aplicados)
    axes_negados = agregar_ejes(negados, factores_por_inicio=factores_aplicados)
    # Los negados se restan (con el mismo signo de su axes).
    axes_final: dict[str, float] = dict(axes_positivos)
    for eje, valor in axes_negados.items():
        axes_final[eje] = axes_final.get(eje, 0.0) - valor

    # ---- Aplicar boosts entre conceptos detectados ----
    # Si un concepto detectado tiene en `boosts` a otro concepto tambien
    # detectado, los ejes compartidos se refuerzan en 25%. Esto produce
    # comprension contextual: detectar "cinematografico" y "epico" juntos
    # refuerza orchestral_weight mas que cada uno por separado.
    axes_final = aplicar_boosts(positivos, axes_final)

    # ---- Focos perceptuales ----
    # Los priority-role positivos son focos. Los marcamos en orden de
    # aparicion para preservar el orden semantico del prompt.
    focos = tuple(
        match.concepto.name
        for match in positivos
        if match.concepto.role == "priority"
    )

    # ---- Exclusiones ----
    # Son: (a) conceptos negados, (b) conceptos role=exclusion detectados.
    exclusiones_nombres: list[str] = []
    for match in negados:
        if match.concepto.name not in exclusiones_nombres:
            exclusiones_nombres.append(match.concepto.name)
    for match in positivos:
        if match.concepto.role == "exclusion" and match.concepto.name not in exclusiones_nombres:
            exclusiones_nombres.append(match.concepto.name)
    exclusiones = tuple(exclusiones_nombres)

    # ---- Generos ----
    generos = generos_sugeridos(positivos)
    # Generos excluidos: si un concepto negado tiene generos, esos generos
    # se anaden a la lista de filtros duros.
    excluidos: list[str] = []
    for match in negados:
        for genero in match.concepto.genres:
            if genero not in excluidos:
                excluidos.append(genero)
    # sin_edm_agresivo ya esta como exclusion role; pero su genero NO esta
    # en la ontologia. Mantenemos solo lo que la ontologia declara.

    # ---- Transicion y curva ----
    estilo = estilo_transicion_sugerido(positivos)
    curva = curva_energia_sugerida(positivos) or "stable"

    # ---- Notas + resumen humano ----
    notas: list[str] = []
    if contradicciones_detectadas:
        notas.append(
            "Detecte conceptos contradictorios; aplique la prioridad mas fuerte: "
            + ", ".join(f"{a} vs {b}" for a, b in contradicciones_detectadas)
        )
    if negados:
        nombres_negados = [m.concepto.name for m in negados]
        notas.append("Evitare: " + ", ".join(nombres_negados))

    resumen = _construir_resumen(positivos, negados, curva)

    return IntentMusical(
        prompt=prompt_limpio,
        axes=axes_final,
        focos=focos,
        exclusiones=exclusiones,
        generos=generos,
        generos_excluidos=tuple(excluidos),
        curva_energia=curva,
        estilo_transicion=estilo,
        contradicciones=tuple(contradicciones_detectadas),
        vacio=False,
        notas=tuple(notas),
        resumen=resumen,
        duracion_minutos=duracion_minutos,
    )


# =============================================================================
# AUXILIARES
# =============================================================================

def _resolver_contradicciones(
    positivos: list[CoincidenciaConcepto],
    contradicciones: list[tuple[str, str]],
) -> list[CoincidenciaConcepto]:
    """Elimina el concepto perdedor de cada par contradictorio.

    Criterio:
      1. Gana el de mayor perceptual_weight.
      2. En empate, gana el mencionado mas tarde en el prompt (interpreta
         la cola del prompt como la idea dominante: "rock pero clasico"
         se queda con "clasica").

    No toca los otros conceptos. Si A vs B y B vs C, primero se evalua
    A vs B y, si A pierde, despues se reevalua C contra B (si B sobrevive).
    """
    sobrevivientes = list(positivos)
    set_contradicciones = list(contradicciones)
    cambios = True
    while cambios and set_contradicciones:
        cambios = False
        for par in list(set_contradicciones):
            a, b = par
            match_a = next((m for m in sobrevivientes if m.concepto.name == a), None)
            match_b = next((m for m in sobrevivientes if m.concepto.name == b), None)
            if match_a is None or match_b is None:
                set_contradicciones.remove(par)
                continue
            peso_a = match_a.concepto.perceptual_weight
            peso_b = match_b.concepto.perceptual_weight
            if peso_a > peso_b:
                perdedor = match_b
            elif peso_b > peso_a:
                perdedor = match_a
            else:
                # Empate -> gana el ultimo mencionado
                perdedor = match_a if match_a.inicio < match_b.inicio else match_b
            sobrevivientes.remove(perdedor)
            set_contradicciones.remove(par)
            cambios = True
    return sobrevivientes


def _construir_resumen(
    positivos: list[CoincidenciaConcepto],
    negados: list[CoincidenciaConcepto],
    curva: str,
) -> str:
    """Una frase legible que describe la intencion entendida."""
    if not positivos and not negados:
        return "Sesion general."
    pos_nombres = [m.concepto.name.replace("_", " ") for m in positivos]
    neg_nombres = [m.concepto.name.replace("_", " ") for m in negados]
    partes: list[str] = []
    if pos_nombres:
        partes.append("Voy a priorizar: " + ", ".join(pos_nombres))
    if neg_nombres:
        partes.append("Evitare: " + ", ".join(neg_nombres))
    if curva and curva != "stable":
        etiquetas = {
            "progressive": "subida progresiva",
            "wave": "energia ondulante",
            "descending": "energia descendente",
            "peak": "pico de energia",
        }
        if curva in etiquetas:
            partes.append("Curva: " + etiquetas[curva])
    return ". ".join(partes) + "."
