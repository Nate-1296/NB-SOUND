# =============================================================================
# servicios/dj_privado/ownership.py
#
# SessionOwnershipManager — Propiedad exclusiva del audio.
#
# Hasta ahora la "suspension" del reproductor global vivía dispersa en varios
# sitios: el modelo QML llamaba a `set_modo_dj(True/False)` directamente en
# distintos puntos (reproducir, descartar, terminar). Eso producia los
# siguientes problemas reales:
#
#   - Si la sesion finalizaba naturalmente, el callback restauraba el global.
#   - Si el usuario "detener_sesion" tambien restauraba.
#   - Si descartaba la sesion, otro path restauraba.
#   - Si cambiaba a otra sesion sin detener la actual, el ownership pasaba
#     ambiguamente y a veces el global quedaba bloqueado sin razon.
#
# El SessionOwnershipManager es UN componente que sabe quien tiene el audio
# en cada momento y aplica el bloqueo/desbloqueo exactamente UNA vez por
# transicion de estado:
#
#   GLOBAL  --acquire()-->  SESION_DJ
#   SESION_DJ  --release()-->  GLOBAL
#
# Es idempotente: llamar acquire() dos veces no doble-bloquea. release() sin
# acquire previo no falla. Esto elimina la clase entera de bugs de
# "estado fantasma" y "modo dj colgado".
# =============================================================================

from __future__ import annotations

import threading
from enum import Enum
from typing import Callable, Optional

from infra.logger import obtener_logger

logger = obtener_logger(__name__)


class Owner(Enum):
    """Quien tiene el control del audio en este momento."""
    GLOBAL    = "global"      # reproductor global activo (default)
    SESION_DJ = "sesion_dj"   # sesion DJ activa, global suspendido


# Callback: (nuevo_owner, anterior_owner) -> None
TipoCallbackCambio = Callable[[Owner, Owner], None]


class SessionOwnershipManager:
    """Gestiona la posesion del audio entre reproductor global y sesion DJ.

    Uso:
        manager = SessionOwnershipManager(reproductor_global)
        manager.adquirir_para_sesion(sesion_id=42)
        ...
        manager.liberar()

    Garantias:
      - acquire/release son idempotentes (llamadas dobles no rompen estado).
      - Solo un owner activo a la vez.
      - Cada transicion emite UN solo callback (no se duplica).
      - El estado interno SIEMPRE refleja la realidad del backend.
      - Si la app se cae mid-sesion, al arranque siguiente la sesion vieja
        no tiene ownership (default = GLOBAL).
    """

    def __init__(self, reproductor_global) -> None:
        self._reproductor_global = reproductor_global
        self._owner: Owner = Owner.GLOBAL
        self._sesion_id_activa: Optional[int] = None
        self._lock = threading.RLock()
        self._cb_cambio: list[TipoCallbackCambio] = []

    # ─── propiedades ───────────────────────────────────────────────────

    @property
    def owner(self) -> Owner:
        """Quien tiene el audio AHORA."""
        return self._owner

    @property
    def sesion_id_activa(self) -> Optional[int]:
        """Id de la sesion DJ que tiene el audio (None si owner=GLOBAL)."""
        return self._sesion_id_activa

    @property
    def global_suspendido(self) -> bool:
        """Atajo para QML/UI: True cuando el reproductor global esta bloqueado."""
        return self._owner == Owner.SESION_DJ

    # ─── observabilidad ────────────────────────────────────────────────

    def on_cambio(self, callback: TipoCallbackCambio) -> None:
        """Registra callback para cambios de ownership."""
        self._cb_cambio.append(callback)

    def off_cambio(self, callback: TipoCallbackCambio) -> None:
        try:
            self._cb_cambio.remove(callback)
        except ValueError:
            pass

    def _emitir_cambio(self, nuevo: Owner, anterior: Owner) -> None:
        for cb in list(self._cb_cambio):
            try:
                cb(nuevo, anterior)
            except Exception:
                logger.exception("cb ownership fallo")

    # ─── operaciones ───────────────────────────────────────────────────

    def adquirir_para_sesion(self, sesion_id: int) -> bool:
        """Marca la sesion como owner. Suspende el reproductor global.

        Si la sesion `sesion_id` ya es owner, es no-op (idempotente). Si
        otra sesion tenia el ownership, lo transfiere sin pasar por GLOBAL
        intermedio (mas eficiente y sin flicker).

        Devuelve True si se hizo cambio efectivo, False si era no-op.
        """
        with self._lock:
            sesion_id = int(sesion_id)
            if self._owner == Owner.SESION_DJ and self._sesion_id_activa == sesion_id:
                # Misma sesion ya tiene el ownership; no-op idempotente.
                return False
            anterior = self._owner
            self._owner = Owner.SESION_DJ
            self._sesion_id_activa = sesion_id
            # Aplicar bloqueo en el backend solo si veniamos de GLOBAL.
            # Si veniamos de otra SESION_DJ, el global ya estaba suspendido.
            if anterior == Owner.GLOBAL:
                try:
                    self._reproductor_global.set_modo_dj(True)
                except Exception:
                    logger.exception("set_modo_dj(True) fallo")
            logger.info("ownership %s -> SESION_DJ(%d)", anterior.value, sesion_id)
        self._emitir_cambio(Owner.SESION_DJ, anterior)
        return True

    def liberar(self) -> bool:
        """Libera el ownership y restaura el reproductor global.

        Idempotente. Defensiva: si el flag del reproductor estaba en True
        por una via externa (ej. set_modo_dj llamado fuera del manager),
        igualmente lo restauramos para evitar estados fantasmas.

        Devuelve True si la operacion produjo un cambio de estado real
        (en el manager O en el reproductor).
        """
        cambio = False
        with self._lock:
            anterior = self._owner
            if anterior != Owner.GLOBAL:
                self._owner = Owner.GLOBAL
                self._sesion_id_activa = None
                cambio = True
            # Defensivo: si el flag del reproductor sigue activo por
            # cualquier razon, forzar False. Idempotente en el reproductor.
            try:
                flag_actual = bool(getattr(self._reproductor_global, "modo_dj_activo", False))
            except Exception:
                flag_actual = False
            if flag_actual:
                try:
                    self._reproductor_global.set_modo_dj(False)
                    cambio = True
                except Exception:
                    logger.exception("set_modo_dj(False) fallo")
            if cambio:
                logger.info("ownership %s -> GLOBAL", anterior.value)
        if cambio:
            self._emitir_cambio(Owner.GLOBAL, anterior)
        return cambio

    def liberar_si_es_de(self, sesion_id: int) -> bool:
        """Libera SOLO si la sesion indicada es la dueña actual.

        Util para casos como "se elimino esta sesion": queremos liberar el
        global solo si era esa la que tenia control. Si era OTRA sesion, no
        se toca el ownership.
        """
        with self._lock:
            if self._owner != Owner.SESION_DJ:
                return False
            if int(sesion_id) != self._sesion_id_activa:
                return False
        return self.liberar()

    def transferir_a_sesion(self, nueva_sesion_id: int) -> None:
        """Cambia el ownership a otra sesion sin pasar por GLOBAL.

        Util cuando el usuario reproduce una sesion mientras otra esta
        activa: no soltamos el bloqueo global (no hay flicker visual ni
        reanudacion accidental del global).
        """
        with self._lock:
            if self._owner == Owner.SESION_DJ and self._sesion_id_activa == int(nueva_sesion_id):
                return
            anterior = self._owner
            self._owner = Owner.SESION_DJ
            self._sesion_id_activa = int(nueva_sesion_id)
            if anterior == Owner.GLOBAL:
                try:
                    self._reproductor_global.set_modo_dj(True)
                except Exception:
                    logger.exception("set_modo_dj(True) fallo en transferencia")
        self._emitir_cambio(Owner.SESION_DJ, anterior)
