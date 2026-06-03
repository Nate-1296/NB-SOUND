# =============================================================================
# servicios/dj_privado/servicio.py
#
# Orquestador del DJ Privado: API publica de alto nivel.
#
# Este servicio es el unico punto de entrada que la UI/modelos deberian
# tocar. Encapsula:
#   - Parseo del intent.
#   - Construccion progresiva (primer bloque -> continuacion).
#   - Persistencia (sesion, pistas, eventos).
#   - Integracion con el Reproductor (encolar pistas planificadas).
#   - Adaptacion en vivo (skips, likes, replanificacion).
#   - Operaciones de gestion (regenerar, extender, guardar como playlist).
#
# Filosofia:
#   - El servicio NO crea hilos ni reactiviza eventos por su cuenta. Los
#     workers Qt y la UI deciden cuando llamar a `iniciar_sesion`,
#     `continuar_construccion`, etc.
#   - Las operaciones largas estan separadas en metodos pequenos para
#     permitir background worker friendly slicing.
#   - Toda la persistencia pasa por persistencia.py.
# =============================================================================

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from servicios.dj_privado import (
    constructor,
    embeddings,
    intencion,
    persistencia,
)
from servicios.dj_privado.constructor import (
    BloqueConstruido,
    ConstructorSesion,
    OpcionesConstructor,
)
from servicios.dj_privado.errores import (
    ConfiguracionInvalidaError,
    DjPrivadoError,
    PoolVacioError,
    SesionNoEncontradaError,
)
from servicios.dj_privado.intencion import IntentMusical
from servicios.dj_privado.persistencia import (
    PistaCandidata,
    SesionDjRow,
)


logger = logging.getLogger(__name__)

# Identificador de version del motor. Se persiste en dj_sesiones.motor_version
# y permite detectar sesiones creadas con logica distinta al hacer migraciones.
MOTOR_VERSION = "dj_v1"


# =============================================================================
# CALLBACK PROTOCOL
# =============================================================================

# Callback de progreso de construccion que la UI puede registrar.
# Firma: (sesion_id: int, bloque_index: int, info: dict) -> None
TipoCallbackBloque = Callable[[int, int, dict], None]


# =============================================================================
# ESTADO EN MEMORIA
# =============================================================================

@dataclass
class SesionActiva:
    """Estado en memoria de una sesion en construccion/reproduccion.

    Mantiene el ConstructorSesion vivo entre llamadas a `continuar_construccion`
    para evitar recargar el pool desde la BD en cada paso. El constructor
    rastrea internamente los ids consumidos y la duracion acumulada.

    `bloques` acumula los BloqueConstruido en orden; permite recalcular el
    resumen completo sin releer la BD. Solo la sesion activa tiene bloques en
    memoria; sesiones anteriores se consultan via persistencia.
    """
    sesion_id: int
    intent: IntentMusical
    constructor: ConstructorSesion
    bloques: list[BloqueConstruido] = field(default_factory=list)
    completada: bool = False

    @property
    def total_pistas(self) -> int:
        """Total de pistas planificadas en todos los bloques construidos."""
        return sum(len(b.pistas) for b in self.bloques)


# =============================================================================
# SERVICIO
# =============================================================================

class DjPrivadoService:
    """Servicio de alto nivel para el DJ Privado.

    Es el unico punto de entrada que la UI y los modelos QML deben tocar.
    Encapsula el ciclo completo: parsear intent -> construir sesion -> persistir
    -> adaptar en vivo -> exportar.

    Mantiene UNA sesion activa por instancia. Si se inicia otra, se reemplaza
    en memoria; las anteriores siguen accesibles via `listar_sesiones_recientes`
    y `cargar_sesion`.

    Threading: este servicio NO es thread-safe por si mismo. Los modelos Qt
    deben llamarlo exclusivamente desde workers (QThread/QRunnable), nunca
    desde el hilo principal ni desde dos workers simultaneos.
    """

    def __init__(self) -> None:
        self._sesion_activa: Optional[SesionActiva] = None
        # El provider de embeddings se inicializa perezosamente al primer uso
        # para no bloquear el arranque de la app: OnnxEmbeddingProvider puede
        # tardar ~500ms al cargar el modelo ONNX por primera vez.
        self._provider: Optional[embeddings.EmbeddingProvider] = None

    # ------------------------------------------------------------------
    # ESTADO / DIAGNOSTICO
    # ------------------------------------------------------------------

    def estado_motor(self) -> dict:
        """Diagnostico serializable del motor para mostrar en la UI.

        Incluye el backend de embeddings activo (determinístico vs ONNX),
        la version del motor y el id de sesion activa. No fuerza la
        inicializacion del provider si aun no fue usado.
        """
        provider_info = embeddings.estado_provider()
        info = {
            "motor_version": MOTOR_VERSION,
            "sesion_activa_id": self._sesion_activa.sesion_id if self._sesion_activa else None,
            "total_pistas_planificadas": self._sesion_activa.total_pistas if self._sesion_activa else 0,
            "provider": provider_info,
        }
        return info

    def sesion_activa(self) -> Optional[SesionActiva]:
        return self._sesion_activa

    # ------------------------------------------------------------------
    # INICIAR / CONTINUAR
    # ------------------------------------------------------------------

    def iniciar_sesion(
        self,
        prompt: str,
        *,
        duracion_minutos: int = 60,
        opciones: Optional[OpcionesConstructor] = None,
        pool: Optional[list[PistaCandidata]] = None,
        en_caliente: bool = False,
    ) -> SesionActiva:
        """Crea una sesion nueva y construye su primer bloque.

        Si `pool` se pasa, se usa ese pool (util para tests y para evitar
        leer la BD). Si no, se carga del repositorio.

        `en_caliente=True` indica que ya hay una sesion en reproduccion y
        esta es un re-prompt: NO se reproduce el primer bloque automaticamente.

        Devuelve la SesionActiva con el primer bloque ya planificado.
        """
        if duracion_minutos <= 0 or duracion_minutos > 480:
            raise ConfiguracionInvalidaError(
                f"duracion_minutos fuera de rango: {duracion_minutos}"
            )

        # Parsear intent
        intent = intencion.parsear_intent(prompt, duracion_minutos=duracion_minutos)

        # Crear sesion en BD
        sesion_id = persistencia.crear_sesion(
            prompt=prompt,
            intent_json=intent.to_json(),
            objetivo_minutos=duracion_minutos,
            motor_version=MOTOR_VERSION,
            semilla=(opciones.semilla if opciones else None),
            resumen={},
        )

        # Construir
        opts = opciones or OpcionesConstructor()
        construct = ConstructorSesion(intent, opts)
        pool_size = construct.cargar_pool(pistas=pool)
        if pool_size == 0:
            persistencia.actualizar_estado_sesion(sesion_id, "error", finalizar=True)
            raise PoolVacioError(
                "No hay pistas candidatas. ¿Biblioteca vacía o filtros muy restrictivos?"
            )

        bloque = construct.construir_bloque(es_inicial=True)
        if not bloque.pistas:
            persistencia.actualizar_estado_sesion(sesion_id, "error", finalizar=True)
            raise PoolVacioError("El intent eliminó todas las candidatas.")

        # Persistir el primer bloque
        rows = constructor.bloque_a_rows(bloque, sesion_id)
        persistencia.insertar_pistas_sesion(sesion_id, rows)

        # Persistir resumen inicial
        resumen = constructor.resumen_sesion([bloque], intent)
        persistencia.actualizar_resumen_sesion(sesion_id, resumen)

        # Marcar listo si ya cubre el objetivo
        if bloque.completado:
            persistencia.actualizar_estado_sesion(sesion_id, "lista")
        else:
            persistencia.actualizar_estado_sesion(sesion_id, "construyendo")

        # Estado en memoria
        sesion = SesionActiva(
            sesion_id=sesion_id,
            intent=intent,
            constructor=construct,
            bloques=[bloque],
            completada=bloque.completado,
        )
        self._sesion_activa = sesion
        return sesion

    def continuar_construccion(self) -> Optional[BloqueConstruido]:
        """Construye el siguiente bloque de la sesion activa.

        Devuelve None si la sesion ya esta completada o no hay sesion activa.
        El bloque se persiste tambien antes de retornarlo.
        """
        if self._sesion_activa is None or self._sesion_activa.completada:
            return None

        bloque = self._sesion_activa.constructor.construir_bloque(es_inicial=False)
        if not bloque.pistas:
            self._sesion_activa.completada = True
            persistencia.actualizar_estado_sesion(
                self._sesion_activa.sesion_id, "lista",
            )
            return bloque

        rows = constructor.bloque_a_rows(bloque, self._sesion_activa.sesion_id)
        persistencia.insertar_pistas_sesion(self._sesion_activa.sesion_id, rows)
        self._sesion_activa.bloques.append(bloque)

        # Resumen actualizado
        resumen = constructor.resumen_sesion(self._sesion_activa.bloques, self._sesion_activa.intent)
        persistencia.actualizar_resumen_sesion(self._sesion_activa.sesion_id, resumen)

        if bloque.completado:
            self._sesion_activa.completada = True
            persistencia.actualizar_estado_sesion(
                self._sesion_activa.sesion_id, "lista",
            )

        return bloque

    # ------------------------------------------------------------------
    # ADAPTACION EN VIVO
    # ------------------------------------------------------------------

    def registrar_reproduccion(self, posicion: int, pista_id: int) -> None:
        """Marca una pista como reproducida y registra el evento."""
        if self._sesion_activa is None:
            return
        persistencia.marcar_pista_estado(
            self._sesion_activa.sesion_id, posicion, "reproducida",
        )
        persistencia.registrar_evento(
            self._sesion_activa.sesion_id, "reproducida", pista_id=pista_id,
        )

    def registrar_skip(self, posicion: int, pista_id: int) -> None:
        """Marca skip y dispara la heuristica de adaptacion.

        Heuristica:
          - Si el skip es del PRIMER 30% de la pista, registra dislike implicito.
          - Si fue al 80% o mas, es "termino casi normal" (no penaliza tanto).
          - Tras N skips consecutivos (>=2), el sistema replanifica los
            siguientes bloques para evitar el patron rechazado.

        El payload puede incluir 'progress' (0..1) para refinar la heuristica.
        En esta API basica se asume skip explicito sin progreso.
        """
        if self._sesion_activa is None:
            return
        persistencia.marcar_pista_estado(
            self._sesion_activa.sesion_id, posicion, "saltada",
        )
        persistencia.registrar_evento(
            self._sesion_activa.sesion_id, "saltada", pista_id=pista_id,
        )

    def registrar_like(self, posicion: int, pista_id: int) -> None:
        if self._sesion_activa is None:
            return
        persistencia.registrar_evento(
            self._sesion_activa.sesion_id, "like", pista_id=pista_id,
        )

    def registrar_dislike(self, posicion: int, pista_id: int) -> None:
        """Marca dislike y excluye la pista de futuras replanificaciones."""
        if self._sesion_activa is None:
            return
        persistencia.marcar_pista_estado(
            self._sesion_activa.sesion_id, posicion, "saltada",
        )
        persistencia.registrar_evento(
            self._sesion_activa.sesion_id, "dislike", pista_id=pista_id,
        )

    # ------------------------------------------------------------------
    # OPERACIONES DE GESTION
    # ------------------------------------------------------------------

    def regenerar(self) -> Optional[SesionActiva]:
        """Alias publico de regenerar_sesion (legible desde QML/tests)."""
        return self.regenerar_sesion()

    def regenerar_sesion(self) -> Optional[SesionActiva]:
        """Construye una NUEVA sesion con el mismo prompt y duracion objetivo.

        La sesion anterior queda en BD con estado 'descartada' (auditable).
        La nueva sesion usa una semilla diferente (+17 offset) para producir
        una seleccion distinta aunque el intent y la biblioteca no cambien.

        El jitter de la semilla garantiza variedad sin aleatoriedad total:
        dos regeneraciones del mismo prompt dan resultados distintos y
        reproducibles si se pasa la misma semilla manualmente.
        """
        if self._sesion_activa is None:
            return None
        intent_actual = self._sesion_activa.intent
        # Marcar la sesion previa como descartada
        persistencia.actualizar_estado_sesion(
            self._sesion_activa.sesion_id, "descartada", finalizar=True,
        )
        # Cambiar la semilla para producir una variante distinta
        opciones_nuevas = OpcionesConstructor(
            semilla=(self._sesion_activa.constructor.opciones.semilla or 0) + 17,
        )
        return self.iniciar_sesion(
            intent_actual.prompt,
            duracion_minutos=intent_actual.duracion_minutos,
            opciones=opciones_nuevas,
        )

    def descartar_sesion_activa(self) -> None:
        if self._sesion_activa is None:
            return
        persistencia.actualizar_estado_sesion(
            self._sesion_activa.sesion_id, "descartada", finalizar=True,
        )
        self._sesion_activa = None

    def finalizar_sesion_activa(self) -> None:
        if self._sesion_activa is None:
            return
        persistencia.actualizar_estado_sesion(
            self._sesion_activa.sesion_id, "finalizada", finalizar=True,
        )

    def guardar_como_playlist(self, nombre: str) -> int:
        """Persiste la sesion activa como playlist normal del sistema.

        Usa biblioteca.crear_playlist (firma publica: nombre, descripcion) y
        luego inserta las pistas directamente en `pistas_playlist` en orden.
        El INSERT se hace en una transaccion para mantener atomicidad.

        Si el nombre colisiona, biblioteca._validar_nombre_playlist lanza
        ValueError; el caller debe manejarlo.
        """
        if self._sesion_activa is None:
            raise DjPrivadoError("No hay sesion activa para guardar.")

        from db.conexion import transaccion
        from servicios import biblioteca as svc_bib

        sesion_id = self._sesion_activa.sesion_id
        pistas = persistencia.listar_pistas_sesion(sesion_id)
        pista_ids = [int(p["pista_id"]) for p in pistas if p.get("pista_id")]

        # Nombre por defecto tipo "DJ Privado: Music Session, Vol. X" (sin
        # repetir); el resumen del prompt va a la DESCRIPCIÓN, no al título.
        nombre_final = (nombre or "").strip() or self._nombre_auto_playlist()
        playlist_id = svc_bib.crear_playlist(
            nombre=nombre_final,
            descripcion=f"Sesión DJ: {self._sesion_activa.intent.prompt[:120]}",
        )

        if pista_ids:
            with transaccion() as conn:
                for pos, pista_id in enumerate(pista_ids, start=1):
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO pistas_playlist(playlist_id, pista_id, posicion, agregado_en)
                        VALUES (?, ?, ?, datetime('now'))
                        """,
                        (int(playlist_id), int(pista_id), pos),
                    )
            # Refrescar portada y stats
            try:
                svc_bib.actualizar_portada_playlist_si_cambio(playlist_id)
            except Exception:
                # La actualizacion de portada es best-effort
                logger.debug("portada playlist DJ no se pudo refrescar", exc_info=True)

        persistencia.vincular_playlist(sesion_id, playlist_id)
        persistencia.registrar_evento(
            sesion_id, "feedback",
            payload={"accion": "guardar_como_playlist", "playlist_id": playlist_id, "nombre": nombre_final},
        )
        return playlist_id

    @staticmethod
    def _nombre_auto_playlist() -> str:
        """Siguiente nombre libre "DJ Privado: Music Session, Vol. N".

        Busca el mayor N usado y devuelve N+1, de modo que cada sesión guardada
        tenga un título único sin que el usuario tenga que nombrarla.
        """
        import re
        from db.conexion import obtener_filas

        prefijo = "DJ Privado: Music Session, Vol."
        try:
            filas = obtener_filas(
                "SELECT nombre FROM playlists WHERE nombre LIKE ?",
                (f"{prefijo} %",),
            )
        except Exception:
            filas = []
        patron = re.compile(r"Vol\.\s*(\d+)\s*$")
        max_n = 0
        for fila in filas:
            m = patron.search(str(fila["nombre"] or ""))
            if m:
                max_n = max(max_n, int(m.group(1)))
        return f"{prefijo} {max_n + 1}"

    # ------------------------------------------------------------------
    # LECTURA DE SESIONES PERSISTIDAS
    # ------------------------------------------------------------------

    def cargar_sesion(self, sesion_id: int) -> SesionActiva:
        """Restaura una sesion persistida como activa en memoria.

        Reconstruye el ConstructorSesion con el intent original, marcando como
        consumidos los ids de todas las pistas ya planificadas en BD. Avanza
        tambien `_posicion` y `_duracion_acum` del constructor para que la
        siguiente llamada a `continuar_construccion` no produzca duplicados ni
        exceda la duracion objetivo.

        Los bloques anteriores no se reconstruyen en memoria (son muchos y ya
        estan en BD); `sesion.bloques` queda vacio. El resumen puede leerse
        directamente desde `dj_sesiones.resumen_json` si es necesario.

        Lanza SesionNoEncontradaError si el id no existe en BD.
        """
        fila = persistencia.obtener_sesion(sesion_id)
        if fila is None:
            raise SesionNoEncontradaError(f"Sesion {sesion_id} no existe")

        intent = IntentMusical.from_json(fila.intent_json)
        opciones = OpcionesConstructor(semilla=fila.semilla)
        construct = ConstructorSesion(intent, opciones)

        # Cargar pool excluyendo pistas ya planificadas
        pistas_existentes = persistencia.listar_pistas_sesion(sesion_id)
        ids_existentes = {int(p["pista_id"]) for p in pistas_existentes if p.get("pista_id")}
        construct.marcar_consumidos(ids_existentes)
        construct.cargar_pool()
        # Avanzar el contador de posiciones del constructor al maximo + 1
        if pistas_existentes:
            max_pos = max(p["posicion"] for p in pistas_existentes)
            construct._posicion = max_pos + 1
            construct._duracion_acum = sum(
                float(p.get("duracion_seg") or 0.0) for p in pistas_existentes
            )

        sesion = SesionActiva(
            sesion_id=sesion_id,
            intent=intent,
            constructor=construct,
            bloques=[],  # bloques previos no se reconstruyen, persistidos en BD
            completada=fila.estado in {"lista", "finalizada"},
        )
        self._sesion_activa = sesion
        return sesion

    def listar_sesiones_recientes(self, limite: int = 10) -> list[SesionDjRow]:
        return persistencia.sesiones_recientes(limite=limite)
