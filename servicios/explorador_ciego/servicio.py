# =============================================================================
# servicios/explorador_ciego/servicio.py
#
# Orquestador del Explorador Ciego.
#
# Responsabilidades:
#   - Construir rondas a partir de los selectores.
#   - Mantener el estado del reto actual (revelaciones, marcas, etc.).
#   - Decidir el inicio del fragmento de audio sin depender del backend de
#     audio (eso vive en el modelo QML, que coordina con el reproductor).
#
# El servicio NO conoce VLC ni Qt: es 100% Python puro. Se puede testear sin
# levantar UI ni audio. La capa QML (ModeloExploradorCiego) es la que conecta
# eventos del reproductor a este servicio.
# =============================================================================

from __future__ import annotations

import random
from typing import Optional

from infra.logger import obtener_logger

from .modelos import (
    EstadoReto,
    ModoExplorador,
    NivelRevelacion,
    ResumenRonda,
    Reto,
)
from . import selectores as sel
from . import hints as hints_mod


_log = obtener_logger("servicios.explorador_ciego")


# Defaults razonables que la UI puede sobreescribir si en el futuro queremos
# diferenciar entre "ronda corta / ronda larga".
DEFAULT_RETOS_POR_RONDA = 5
MAX_RETOS_POR_RONDA = 25
MIN_RETOS_POR_RONDA = 1

# Fragmento por defecto en modo audio: duracion del clip de prevista.
# 12 segundos es suficiente para reconocer la mayoria de pistas conocidas
# sin ser tan largo que se vuelva trivial. La UI puede ajustar via
# `set_segundos_fragmento`.
SEGUNDOS_FRAGMENTO_DEFAULT = 12.0


class ExploradorCiegoService:
    """Mantiene el estado de una ronda y expone operaciones puras.

    Una sola instancia vive en el ModeloExploradorCiego; no se comparte entre
    ventanas ni se persiste entre sesiones.

    Estados validos del servicio:
      - sin ronda activa (`ronda_activa == False`)
      - ronda activa con un reto en curso
      - ronda activa terminada (reto actual = ultimo, `ronda_terminada == True`)
    """

    def __init__(self) -> None:
        self._modo: Optional[ModoExplorador] = None
        self._retos: list[Reto] = []
        self._indice: int = -1
        self._segundos_fragmento: float = SEGUNDOS_FRAGMENTO_DEFAULT
        # Cache de candidatos por modo durante la ronda actual: evita
        # consultas redundantes si el usuario inicia rondas sucesivas del
        # mismo modo. Se invalida al cerrar ronda.
        self._pool_por_modo: dict[ModoExplorador, list[dict]] = {}

    # ------------------------------------------------------------------
    # Estado de ronda
    # ------------------------------------------------------------------

    @property
    def ronda_activa(self) -> bool:
        return self._modo is not None and 0 <= self._indice < len(self._retos)

    @property
    def ronda_terminada(self) -> bool:
        return bool(self._retos) and self._indice >= len(self._retos)

    @property
    def modo(self) -> Optional[ModoExplorador]:
        return self._modo

    @property
    def indice(self) -> int:
        return self._indice

    @property
    def total(self) -> int:
        return len(self._retos)

    @property
    def segundos_fragmento(self) -> float:
        return self._segundos_fragmento

    def set_segundos_fragmento(self, segundos: float) -> None:
        try:
            valor = float(segundos)
        except (TypeError, ValueError):
            return
        # Cap [4, 30]: menos de 4 es injugable; mas de 30 deja de ser fragmento.
        self._segundos_fragmento = max(4.0, min(30.0, valor))

    def reto_actual(self) -> Optional[Reto]:
        if not self.ronda_activa:
            return None
        return self._retos[self._indice]

    def conteo_estados(self) -> dict[str, int]:
        """Contadores agregados para mostrar progreso de ronda en vivo."""
        acertados = sum(1 for r in self._retos if r.estado == EstadoReto.ACERTADO)
        revelados = sum(1 for r in self._retos if r.estado == EstadoReto.REVELADO)
        pasados = sum(1 for r in self._retos if r.estado == EstadoReto.PASADO)
        return {
            "acertados": acertados,
            "revelados": revelados,
            "pasados": pasados,
            "en_curso": sum(1 for r in self._retos if r.estado == EstadoReto.EN_CURSO),
        }

    def resumen(self) -> Optional[ResumenRonda]:
        """Snapshot final para mostrar al cerrar la ronda."""
        if not self._modo or not self._retos:
            return None
        conteo = self.conteo_estados()
        return ResumenRonda(
            modo=self._modo,
            total=len(self._retos),
            acertados=conteo["acertados"],
            revelados=conteo["revelados"],
            pasados=conteo["pasados"],
        )

    # ------------------------------------------------------------------
    # Construccion de ronda
    # ------------------------------------------------------------------

    def disponibles_por_modo(self) -> dict[str, int]:
        """Cuenta por modo, util para que la UI muestre estado de cada uno."""
        salida: dict[str, int] = {}
        for modo in ModoExplorador:
            salida[modo.value] = sel.contar_disponibles(modo)
        return salida

    def puede_iniciar(self, modo: ModoExplorador, retos_pedidos: int) -> bool:
        """True si hay suficientes candidatos para una ronda de N retos."""
        disponibles = sel.contar_disponibles(modo)
        return disponibles >= max(1, min(retos_pedidos, MAX_RETOS_POR_RONDA))

    def iniciar_ronda(
        self,
        modo: ModoExplorador,
        retos: int = DEFAULT_RETOS_POR_RONDA,
        *,
        evitar_pistas_ids: Optional[set[int]] = None,
    ) -> Optional[Reto]:
        """Construye una ronda nueva y devuelve el primer reto.

        Si no hay suficientes candidatos, no inicia la ronda y devuelve None;
        la capa superior debe mostrar un mensaje claro al usuario.

        `evitar_pistas_ids` permite que la UI mantenga una memoria local de
        pistas ya jugadas en la sesion y se las pase para no repetirlas
        inmediatamente.
        """
        try:
            n = int(retos)
        except (TypeError, ValueError):
            n = DEFAULT_RETOS_POR_RONDA
        n = max(MIN_RETOS_POR_RONDA, min(n, MAX_RETOS_POR_RONDA))

        pool = list(self._pool_por_modo.get(modo) or sel.candidatos_para(modo))
        if not pool:
            self._reset_interno()
            return None

        if evitar_pistas_ids:
            evitar = set(int(i) for i in evitar_pistas_ids if isinstance(i, (int, float)))
            pool_filtrado = [p for p in pool if int(p.get("id") or 0) not in evitar]
            # Si filtrar lo vacia, no insistimos: mejor repetir alguna
            # antigua que dejar al usuario sin ronda.
            if pool_filtrado:
                pool = pool_filtrado

        random.shuffle(pool)
        seleccion = pool[:n]
        if not seleccion:
            self._reset_interno()
            return None

        self._modo = modo
        self._retos = [
            Reto(
                pista_id=int(p.get("id") or 0),
                pista=dict(p),
                modo=modo,
                nivel=NivelRevelacion.OCULTO,
                estado=EstadoReto.EN_CURSO,
            )
            for p in seleccion
            if int(p.get("id") or 0) > 0
        ]
        self._indice = 0 if self._retos else -1
        # Solo cacheamos si no hubo filtrado externo. Cachear post-filtrado
        # produciria sesgo en rondas siguientes.
        if not evitar_pistas_ids:
            self._pool_por_modo[modo] = pool
        if not self._retos:
            return None
        _log.info(
            "[explorador_ciego] ronda iniciada modo=%s n=%d ids=%s",
            modo.value,
            len(self._retos),
            [r.pista_id for r in self._retos],
        )
        return self._retos[0]

    def cerrar_ronda(self) -> Optional[ResumenRonda]:
        """Cierra la ronda activa y devuelve el resumen final."""
        resumen = self.resumen()
        self._reset_interno()
        return resumen

    def _reset_interno(self) -> None:
        self._modo = None
        self._retos = []
        self._indice = -1
        # No invalidamos pool_por_modo aqui: queremos reusar si la UI
        # arranca una segunda ronda inmediata del mismo modo.

    def invalidar_caches(self) -> None:
        """Limpia el cache de candidatos. Llamar tras cambios de biblioteca."""
        self._pool_por_modo.clear()

    # ------------------------------------------------------------------
    # Operaciones sobre el reto actual
    # ------------------------------------------------------------------

    def marcar_fragmento_escuchado(self) -> None:
        """Idempotente: registra que el usuario reprodujo al menos un fragmento."""
        reto = self.reto_actual()
        if reto is not None:
            reto.fragmento_escuchado = True

    def revelar_artista(self) -> Optional[Reto]:
        reto = self.reto_actual()
        if reto is None:
            return None
        if reto.nivel == NivelRevelacion.OCULTO:
            reto.nivel = NivelRevelacion.ARTISTA
        return reto

    def revelar_album(self) -> Optional[Reto]:
        reto = self.reto_actual()
        if reto is None:
            return None
        # Saltar a album incluye artista; las censuras estan ordenadas.
        if reto.nivel in (NivelRevelacion.OCULTO, NivelRevelacion.ARTISTA):
            reto.nivel = NivelRevelacion.ALBUM
        return reto

    def revelar_total(self) -> Optional[Reto]:
        reto = self.reto_actual()
        if reto is None:
            return None
        reto.nivel = NivelRevelacion.TOTAL
        if reto.estado == EstadoReto.EN_CURSO:
            reto.estado = EstadoReto.REVELADO
        return reto

    def marcar_acertada(self) -> Optional[Reto]:
        """El usuario dice "ya se cual es" antes de revelar. Eleva el nivel
        a TOTAL y marca como ACERTADO. No verificamos contra ground truth:
        el juego es por confianza, no por validacion semantica.

        Solo deberia usarse como salida alternativa cuando NO se puede
        validar por escritura (titulos en alfabetos no latinos). Para el
        flujo normal, la UI debe llamar a `intentar_adivinar` y dejar que
        el resultado decida si la marca acertada se aplica.
        """
        reto = self.reto_actual()
        if reto is None:
            return None
        reto.estado = EstadoReto.ACERTADO
        reto.nivel = NivelRevelacion.TOTAL
        return reto

    def intentar_adivinar(self, texto: str) -> dict:
        """Valida un intento del usuario contra el titulo real del reto.

        Devuelve un dict {"acierto", "cerca", "ratio"} (ver hints.validar_intento).
        Si acierto == True, eleva nivel a TOTAL y marca el reto como ACERTADO.
        Si no, incrementa `intentos_fallidos` y deja el reto intacto.

        El resultado se devuelve incluso si no hay reto activo (con acierto
        False) para que la UI no tenga que ramificar.
        """
        reto = self.reto_actual()
        if reto is None:
            return {"acierto": False, "cerca": False, "ratio": 0.0}
        resultado = hints_mod.validar_intento(reto.pista.get("titulo", ""), texto or "")
        if resultado.get("acierto"):
            reto.estado = EstadoReto.ACERTADO
            reto.nivel = NivelRevelacion.TOTAL
        else:
            reto.intentos_fallidos += 1
        return resultado

    def revelar_hint(self, clave: str) -> Optional[Reto]:
        """Marca una hint como revelada para el reto actual.

        Claves validas (vienen del catalogo de hints): alfabeto, empieza_con,
        termina_con, cantidad_palabras, cantidad_letras. Cualquier otra clave
        se ignora silenciosamente: la UI no debe poder forzar revelaciones
        de campos privados a traves de este metodo.
        """
        reto = self.reto_actual()
        if reto is None:
            return None
        validas = {
            "alfabeto", "empieza_con", "termina_con",
            "cantidad_palabras", "cantidad_letras",
        }
        if clave not in validas:
            return reto
        reto.hints_reveladas.add(clave)
        return reto

    def marcar_pasado(self) -> Optional[Reto]:
        reto = self.reto_actual()
        if reto is None:
            return None
        if reto.estado == EstadoReto.EN_CURSO:
            reto.estado = EstadoReto.PASADO
        return reto

    # ------------------------------------------------------------------
    # Navegacion de ronda
    # ------------------------------------------------------------------

    def avanzar(self) -> Optional[Reto]:
        """Avanza al siguiente reto.

        Si el reto actual sigue EN_CURSO (el usuario no decidio nada), lo
        marcamos como PASADO para que el resumen sea coherente. La UI puede
        forzar otro estado llamando antes a `marcar_acertada` o
        `revelar_total`.
        """
        if not self._retos or self._indice < 0:
            return None
        reto_actual = self._retos[self._indice]
        if reto_actual.estado == EstadoReto.EN_CURSO:
            reto_actual.estado = EstadoReto.PASADO
        self._indice += 1
        if self._indice >= len(self._retos):
            return None
        return self._retos[self._indice]

    def retroceder(self) -> Optional[Reto]:
        """Vuelve al reto anterior. Util si el usuario revelo por error.

        El estado del reto al que volvemos NO se resetea: si ya fue marcado
        como acertado/pasado, sigue asi. La UI puede ofrecer un "reabrir"
        explicito si lo necesita, pero no es necesario para la version 1.
        """
        if not self._retos or self._indice <= 0:
            return None
        self._indice -= 1
        return self._retos[self._indice]

    def ir_a_indice(self, indice: int) -> Optional[Reto]:
        try:
            i = int(indice)
        except (TypeError, ValueError):
            return None
        if not (0 <= i < len(self._retos)):
            return None
        self._indice = i
        return self._retos[self._indice]

    # ------------------------------------------------------------------
    # Helpers utiles para la capa de UI
    # ------------------------------------------------------------------

    def posicion_inicio_fragmento(self, reto: Reto) -> float:
        """Calcula el offset inicial recomendado para el fragmento de audio.

        Estrategia simple:
          - Si la pista dura < 60s: empezar en 0.
          - Si dura mas: arrancar al 30% (heuristica que cae a menudo en
            primer estribillo en musica popular).
        El servicio NO ejecuta el audio: solo sugiere el offset que la UI
        debe aplicar via `reproductor.buscar_posicion()`.
        """
        try:
            dur = float(reto.pista.get("duracion_seg") or 0.0)
        except (TypeError, ValueError):
            dur = 0.0
        if dur <= 60.0:
            return 0.0
        return round(max(0.0, dur * 0.30), 2)
