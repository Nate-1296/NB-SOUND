# =============================================================================
# servicios/dj_privado/constructor.py
#
# Constructor progresivo de sesiones del DJ Privado.
#
# Este modulo orquesta intent -> scheduler -> transiciones -> persistencia,
# y soporta CONSTRUCCION POR BLOQUES para que la UI no tenga que esperar
# a que se planifiquen 50 pistas antes de empezar a reproducir.
#
# Filosofia:
#   - La sesion se construye en bloques (primer bloque ~8 pistas).
#   - Cada bloque se persiste inmediatamente para que el usuario pueda
#     empezar a reproducir y el constructor siga trabajando.
#   - El refinamiento de transiciones se aplica DENTRO de cada bloque y,
#     opcionalmente, en la frontera entre bloques.
#   - El proceso es REENTRANTE: se puede continuar la sesion mas tarde,
#     extender, replanificar.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from servicios.dj_privado import embeddings, persistencia, scheduler, transiciones
from servicios.dj_privado.intencion import IntentMusical
from servicios.dj_privado.persistencia import (
    PistaCandidata,
    PistaSesionRow,
)
from servicios.dj_privado.scheduler import PistaSesionPlanificada
from servicios.dj_privado.transiciones import TransicionPlan


# =============================================================================
# CONFIGURACION DEL CONSTRUCTOR
# =============================================================================

@dataclass
class OpcionesConstructor:
    """Parametros que ajustan el comportamiento del constructor.

    Defaults razonables para una experiencia de usuario fluida:
      - tam_bloque_inicial: tamano del primer bloque (rapido).
      - tam_bloque_continuacion: bloques subsecuentes (mas pistas).
      - max_pistas_por_artista: limite de diversidad.
      - peso_embedding: refuerzo semantico (0 = solo ejes).
      - pool_top_k: tamano del pool tras scoring inicial.
      - refinar_transiciones: si aplicar refinamiento local.
      - requerir_features: si solo usar pistas con audio_features ready.
    """
    tam_bloque_inicial: int = 8
    tam_bloque_continuacion: int = 12
    max_pistas_por_artista: int = 2
    peso_embedding: float = 0.20
    pool_top_k: int = 250
    refinar_transiciones: bool = True
    requerir_features: bool = False
    semilla: Optional[int] = None


# =============================================================================
# RESULTADO PARCIAL DEL CONSTRUCTOR
# =============================================================================

@dataclass
class BloqueConstruido:
    """Resultado de construir un bloque de la sesion.

    `pistas` y `transiciones` ya estan en orden refinado y listos para
    persistir en dj_pistas_sesion.
    """
    posicion_inicio: int
    pistas: list[PistaSesionPlanificada]
    transiciones: list[TransicionPlan]
    duracion_seg: float
    completado: bool   # True si se alcanzo la duracion objetivo
    motivo_corte: str  # 'objetivo_cumplido' | 'pool_agotado' | 'bloque_lleno'


# =============================================================================
# CONSTRUCTOR PRINCIPAL
# =============================================================================

class ConstructorSesion:
    """Construye una sesion DJ paso a paso.

    Uso tipico:
        c = ConstructorSesion(intent, opciones)
        c.cargar_pool()
        primer_bloque = c.construir_bloque(es_inicial=True)
        # ... persistir, empezar a reproducir ...
        siguiente = c.construir_bloque()
        ...

    El constructor mantiene el pool de candidatas y excluye las ya
    seleccionadas para evitar repeticiones. Tambien rastrea la duracion
    acumulada para saber cuando detenerse.
    """

    def __init__(
        self,
        intent: IntentMusical,
        opciones: Optional[OpcionesConstructor] = None,
        *,
        excluir_inicial: Optional[Iterable[int]] = None,
    ) -> None:
        self.intent = intent
        self.opciones = opciones or OpcionesConstructor()
        self._pool: list[PistaCandidata] = []
        self._consumidos: set[int] = set()
        if excluir_inicial:
            self._consumidos.update(int(i) for i in excluir_inicial)
        self._posicion = 0
        self._duracion_acum = 0.0
        self._provider: Optional[embeddings.EmbeddingProvider] = None
        self._estilo_transicion = transiciones.resolver_estilo_intent(
            self.intent.estilo_transicion or {}
        )

    # ------------------------------------------------------------------
    # CICLO DE VIDA
    # ------------------------------------------------------------------

    def cargar_pool(self, *, pistas: Optional[list[PistaCandidata]] = None) -> int:
        """Carga el pool de candidatas (desde la BD o desde un parametro).

        Si se pasa `pistas`, se usa ese pool (util para tests/biblioteca
        en memoria). Si no, se lee de la persistencia.

        Devuelve el tamano del pool.
        """
        if pistas is not None:
            self._pool = list(pistas)
        else:
            self._pool = persistencia.cargar_candidatos(
                excluir_ids=self._consumidos,
                requerir_features=self.opciones.requerir_features,
            )
        self._provider = embeddings.obtener_provider()
        return len(self._pool)

    @property
    def provider(self) -> Optional[embeddings.EmbeddingProvider]:
        return self._provider

    @property
    def posicion_actual(self) -> int:
        return self._posicion

    @property
    def duracion_acumulada_seg(self) -> float:
        return self._duracion_acum

    @property
    def tam_pool_restante(self) -> int:
        return sum(1 for p in self._pool if p.id not in self._consumidos)

    # ------------------------------------------------------------------
    # CONSTRUCCION DE BLOQUES
    # ------------------------------------------------------------------

    def construir_bloque(self, *, es_inicial: bool = False) -> BloqueConstruido:
        """Construye el siguiente bloque de la sesion.

        El primer bloque es mas pequeno (responde rapido a la UI). Los
        siguientes traen mas pistas para reducir el numero de llamadas.
        """
        if not self._provider:
            self._provider = embeddings.obtener_provider()

        max_pistas = self.opciones.tam_bloque_inicial if es_inicial else self.opciones.tam_bloque_continuacion
        duracion_objetivo_total_seg = self.intent.duracion_minutos * 60.0
        duracion_restante = max(0.0, duracion_objetivo_total_seg - self._duracion_acum)
        if duracion_restante <= 0 and not es_inicial:
            return BloqueConstruido(
                posicion_inicio=self._posicion, pistas=[], transiciones=[],
                duracion_seg=0.0, completado=True, motivo_corte="objetivo_cumplido",
            )

        # Estimar cuantos minutos cubrir en este bloque para no excedernos
        # del objetivo. Si quedan 10 minutos, no construyas 12 pistas de 3min.
        if es_inicial:
            duracion_bloque_min = min(duracion_restante / 60.0, max_pistas * 4.0)
        else:
            duracion_bloque_min = min(duracion_restante / 60.0, max_pistas * 4.0)

        # Pool disponible (excluyendo consumidos)
        pool_disp = [p for p in self._pool if p.id not in self._consumidos]
        if not pool_disp:
            return BloqueConstruido(
                posicion_inicio=self._posicion, pistas=[], transiciones=[],
                duracion_seg=0.0, completado=False, motivo_corte="pool_agotado",
            )

        # Planificar sobre el pool disponible
        planificadas = scheduler.planificar_sesion(
            pool_disp, self.intent,
            duracion_objetivo_min=max(1, int(round(duracion_bloque_min))),
            provider=self._provider,
            peso_embedding=self.opciones.peso_embedding,
            max_pistas_por_artista=self.opciones.max_pistas_por_artista,
            semilla=self.opciones.semilla,
            pool_top_k=self.opciones.pool_top_k,
        )

        # Cortar al maximo del bloque
        planificadas = planificadas[:max_pistas]

        # Refinar transiciones locales
        pistas_solas = [p.pista for p in planificadas]
        if self.opciones.refinar_transiciones and len(pistas_solas) >= 3:
            refinadas, transiciones_calc = transiciones.refinar_orden_para_transiciones(
                pistas_solas, estilo=self._estilo_transicion,
            )
            # Reasignar posiciones y reconstruir mapping pista -> score original
            mapa_score = {p.pista.id: p for p in planificadas}
            planificadas = []
            for idx, refinada in enumerate(refinadas):
                original = mapa_score[refinada.id]
                planificadas.append(PistaSesionPlanificada(
                    pista=refinada,
                    posicion=self._posicion + idx,
                    score_total=original.score_total,
                    score_intent=original.score_intent,
                    score_curva=original.score_curva,
                    razones=original.razones,
                ))
        else:
            transiciones_calc = []
            if len(pistas_solas) >= 2:
                transiciones_calc = [
                    transiciones.planificar_transicion(
                        pistas_solas[i], pistas_solas[i + 1],
                        estilo=self._estilo_transicion,
                    )
                    for i in range(len(pistas_solas) - 1)
                ]
            # Reasignar posiciones
            for idx, p in enumerate(planificadas):
                planificadas[idx] = PistaSesionPlanificada(
                    pista=p.pista, posicion=self._posicion + idx,
                    score_total=p.score_total, score_intent=p.score_intent,
                    score_curva=p.score_curva, razones=p.razones,
                )

        # ── Duración efectiva ──
        #
        # Sumamos duración bruta y descontamos overlaps planificados (cada
        # transición consume `overlap_seg` segundos compartidos entre A y B).
        #
        # NO recortamos la última pista: si el usuario pide 15 min y la
        # planificación cubre 19:45, la sesión dura 19:45. La duración
        # objetivo es una sugerencia para que el scheduler elija cuántas
        # pistas seleccionar; truncar el cierre arruina la experiencia
        # (corta una pista a medias y, peor aún, al terminar la sesión
        # finaliza antes de que la transición complete).
        duracion_bruta = sum(p.pista.duracion_seg or 0.0 for p in planificadas)
        overlap_total = sum(t.overlap_seg for t in transiciones_calc)
        duracion_efectiva = max(0.0, duracion_bruta - overlap_total)

        self._duracion_acum += duracion_efectiva
        for p in planificadas:
            self._consumidos.add(p.pista.id)
        self._posicion += len(planificadas)

        completado = self._duracion_acum >= duracion_objetivo_total_seg * 0.97
        motivo = "objetivo_cumplido" if completado else "bloque_lleno"
        if not planificadas:
            motivo = "pool_agotado"

        return BloqueConstruido(
            posicion_inicio=planificadas[0].posicion if planificadas else self._posicion,
            pistas=planificadas,
            transiciones=transiciones_calc,
            duracion_seg=duracion_efectiva,
            completado=completado,
            motivo_corte=motivo,
        )

    def marcar_consumidos(self, ids: Iterable[int]) -> None:
        """Agrega ids al set de consumidos sin alterar el pool.

        Util cuando una sesion se construyo en una llamada anterior y se
        retomara (extender) saltando lo ya planificado.
        """
        self._consumidos.update(int(i) for i in ids)


# =============================================================================
# FUNCIONES DE ALTO NIVEL
# =============================================================================

def bloque_a_rows(bloque: BloqueConstruido, sesion_id: int) -> list[PistaSesionRow]:
    """Convierte un BloqueConstruido a filas listas para persistir."""
    rows: list[PistaSesionRow] = []
    for idx, planificada in enumerate(bloque.pistas):
        transicion_dict = {}
        # La transicion ENTRA a esta pista (relacion con la anterior).
        # Para la primera pista del bloque, no hay transicion guardada
        # (es responsabilidad del bloque anterior).
        if idx > 0 and idx - 1 < len(bloque.transiciones):
            transicion_dict = transiciones.transicion_a_dict(bloque.transiciones[idx - 1])
        rows.append(PistaSesionRow(
            sesion_id=sesion_id,
            posicion=planificada.posicion,
            pista_id=planificada.pista.id,
            score_total=planificada.score_total,
            score_intent=planificada.score_intent,
            score_transicion=transicion_dict.get("score", 0.0) if transicion_dict else 0.0,
            score_curva=planificada.score_curva,
            razones=planificada.razones,
            transicion=transicion_dict,
            estado="planificada",
            bloqueada=False,
        ))
    return rows


def resumen_sesion(bloques: list[BloqueConstruido], intent: IntentMusical) -> dict:
    """Construye el dict de resumen para mostrar/persistir en la sesion.

    Es defensivo: maneja bloques vacios y ausencia de features.
    """
    total_pistas = sum(len(b.pistas) for b in bloques)
    duracion_total = sum(b.duracion_seg for b in bloques)
    artistas: list[str] = []
    artistas_set: set[str] = set()
    energia_inicial: Optional[float] = None
    energia_final: Optional[float] = None
    score_promedio = 0.0
    if total_pistas > 0:
        suma = 0.0
        for bloque in bloques:
            for p in bloque.pistas:
                suma += p.score_total
                nombre = p.pista.artista_nombre
                if nombre and nombre not in artistas_set:
                    artistas_set.add(nombre)
                    artistas.append(nombre)
                if p.pista.energy is not None:
                    if energia_inicial is None:
                        energia_inicial = float(p.pista.energy)
                    energia_final = float(p.pista.energy)
        score_promedio = suma / total_pistas

    # Cantidad de transiciones de calidad alta (>= 0.7) vs total
    total_trans = sum(len(b.transiciones) for b in bloques)
    buenas_trans = sum(
        1 for b in bloques for t in b.transiciones if t.score >= 0.7
    )

    # Perfil narrativo (fases) para la UI y el reproductor
    from servicios.dj_privado import narrativa
    perfil = narrativa.construir_perfil(intent)
    perfil_dict = narrativa.perfil_a_dict(perfil)

    return {
        "total_pistas": total_pistas,
        "duracion_seg": round(duracion_total, 1),
        "duracion_min": round(duracion_total / 60.0, 1),
        "artistas_distintos": len(artistas_set),
        "artistas_muestra": artistas[:10],
        "energia_inicial": energia_inicial,
        "energia_final": energia_final,
        "score_promedio": round(score_promedio, 3),
        "transiciones_buenas": buenas_trans,
        "transiciones_total": total_trans,
        "curva_energia": intent.curva_energia,
        "estilo_transicion": intent.estilo_transicion or {},
        "focos": list(intent.focos),
        "exclusiones": list(intent.exclusiones),
        "perfil_narrativo": perfil_dict,
    }
