# =============================================================================
# infra/execution_control.py
#
# Control de ejecución del pipeline: pausa, cancelación y persistencia de
# estado incremental a disco en formato JSON.
#
# ControlEjecucion es el único punto de verdad del estado de una corrida.
# Tanto el proceso CLI (pipeline) como la UI lo leen/escriben para
# coordinar pausa/cancelación y visualizar progreso en tiempo real.
#
# Diseño de concurrencia:
#   - _lock (RLock) protege toda mutación de _estado.
#   - _pausa (Event) bloquea al hilo worker en esperar_si_pausado().
#   - _cancelar (Event) permite interrupciones cooperativas.
#   - _persistir() escribe a disco via rename atómico con PID+TID en el
#     nombre temporal para evitar colisiones entre hilos concurrentes.
#
# Ciclo de vida esperado:
#   1. Instanciar -> persiste estado inicial "running".
#   2. Hilo worker llama checkpoint()/fase()/progreso_fase() a lo largo
#      de la ejecución.
#   3. La UI llama pausar()/reanudar()/cancelar() según la interacción.
#   4. Hilo worker verifica esperar_si_pausado() y cancelado() en cada
#      iteración del loop principal.
#   5. Al terminar, cerrar() escribe el status final.
# =============================================================================

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Centinela para distinguir "no se pasó el argumento" de None explícito,
# necesario en campos opcionales como eta_seconds y extras.
_UNSET = object()


@dataclass
class EstadoEjecucion:
    """
    Snapshot mutable del estado de una ejecución del pipeline.

    Todos los campos se serializan directamente al JSON de estado. La UI
    lee este JSON para renderizar el progreso sin necesidad de IPC complejo.

    Campos de fase: describen el bloque de trabajo en curso (p.ej.
    "fingerprint", "shazam", "assets"). Campos de progreso global describen
    el avance sobre el total de archivos descubiertos.

    `extras` es un mapa tipo -> contadores para sidecars asíncronos (assets,
    enrichment, manifest). `errors` acumula errores individuales de tareas
    extra para auditoría post-ejecución.
    """
    status: str = "running"
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_descubiertos: int = 0
    procesados: int = 0
    current_file: str = ""
    current_stage: str = ""
    phase_id: str = "startup"
    phase_label: str = "Preparando"
    phase_current: int = 0
    phase_total: int = 0
    current_item: str = ""
    current_task: str = ""
    eta_seconds: float | None = None
    phase_eta_seconds: float | None = None
    elapsed_seconds: float = 0.0
    last_event: str = ""
    severity: str = "info"
    pause_reason: str = ""
    cancel_reason: str = ""
    counters: dict[str, int] = field(default_factory=dict)
    extras: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    operaciones: list[dict[str, str]] = field(default_factory=list)


class ControlEjecucion:
    """
    Controla pausa/cancelación y persiste estado incremental de ejecución.

    El archivo JSON en ruta_estado permite que CLI y UI lean el estado real
    del pipeline sin IPC directo. La UI monitorea el archivo periódicamente;
    el pipeline lo actualiza en cada checkpoint.

    Thread-safety: todos los métodos públicos son seguros para uso concurrente.
    El hilo worker y el hilo de la UI pueden llamar a métodos distintos
    simultáneamente sin race conditions.

    Persistencia: _persistir() usa rename atómico. Si el proceso termina
    abruptamente el archivo temporal (.tmp) puede quedar huérfano, pero
    ruta_estado siempre queda en un estado válido o no existe.
    """

    def __init__(self, ruta_estado: Path) -> None:
        self._ruta_estado = ruta_estado
        self._lock = threading.RLock()
        # Event de pausa: set = pausado, clear = corriendo.
        self._pausa = threading.Event()
        # Event de cancelación: una vez seteado no se revierte.
        self._cancelar = threading.Event()
        self._estado = EstadoEjecucion()
        # Persistir el estado inicial para que la UI ya tenga un archivo válido.
        self._persistir()

    @property
    def ruta_estado(self) -> Path:
        return self._ruta_estado

    def pausar(self, reason: str = "manual") -> None:
        with self._lock:
            self._pausa.set()
            self._estado.status = "paused"
            self._estado.pause_reason = reason
            self._estado.updated_at = datetime.now(timezone.utc).isoformat()
            self._persistir()

    def reanudar(self) -> None:
        with self._lock:
            self._pausa.clear()
            self._estado.status = "running"
            self._estado.pause_reason = ""
            self._estado.updated_at = datetime.now(timezone.utc).isoformat()
            self._persistir()

    def cancelar(self, reason: str = "manual") -> None:
        with self._lock:
            self._cancelar.set()
            self._estado.status = "cancelling"
            self._estado.cancel_reason = reason
            self._estado.updated_at = datetime.now(timezone.utc).isoformat()
            self._persistir()

    def cancelado(self) -> bool:
        return self._cancelar.is_set()

    def pausa_activa(self) -> bool:
        return self._pausa.is_set()

    def esperar_si_pausado(self) -> None:
        """
        Bloquea el hilo worker mientras la pausa esté activa.

        El worker debe llamar a este método al inicio de cada iteración del
        loop principal. Si se solicita cancelación durante la pausa, el bucle
        termina inmediatamente para que el worker pueda detectar cancelado().
        """
        while self.pausa_activa() and not self.cancelado():
            # Persistir estado en cada ciclo de espera para mantener updated_at fresco.
            self.checkpoint()
            threading.Event().wait(0.25)

    def checkpoint(
        self,
        *,
        # Solo se actualizan los campos que el caller pasa explícitamente.
        # Los campos con default _UNSET permiten distinguir None intencional
        # (limpiar el valor) de "no actualizar".
        total_descubiertos: int | None = None,
        procesados: int | None = None,
        current_file: str | None = None,
        current_stage: str | None = None,
        counters: dict[str, int] | None = None,
        phase_id: str | None = None,
        phase_label: str | None = None,
        phase_current: int | None = None,
        phase_total: int | None = None,
        current_item: str | None = None,
        current_task: str | None = None,
        eta_seconds: float | None | object = _UNSET,
        phase_eta_seconds: float | None | object = _UNSET,
        elapsed_seconds: float | None = None,
        last_event: str | None = None,
        severity: str | None = None,
        extras: dict[str, dict[str, Any]] | None | object = _UNSET,
    ) -> None:
        with self._lock:
            if total_descubiertos is not None:
                self._estado.total_descubiertos = total_descubiertos
            if procesados is not None:
                self._estado.procesados = procesados
            if current_file is not None:
                self._estado.current_file = current_file
            if current_stage is not None:
                self._estado.current_stage = current_stage
            if counters is not None:
                self._estado.counters = dict(counters)
            if phase_id is not None:
                self._estado.phase_id = phase_id
            if phase_label is not None:
                self._estado.phase_label = phase_label
            if phase_current is not None:
                self._estado.phase_current = max(0, int(phase_current))
            if phase_total is not None:
                self._estado.phase_total = max(0, int(phase_total))
            if current_item is not None:
                self._estado.current_item = current_item
            if current_task is not None:
                self._estado.current_task = current_task
            if eta_seconds is not _UNSET:
                self._estado.eta_seconds = (
                    None if eta_seconds is None else max(0.0, float(eta_seconds))
                )
            if phase_eta_seconds is not _UNSET:
                self._estado.phase_eta_seconds = (
                    None if phase_eta_seconds is None else max(0.0, float(phase_eta_seconds))
                )
            if elapsed_seconds is not None:
                self._estado.elapsed_seconds = max(0.0, float(elapsed_seconds))
            if last_event is not None:
                self._estado.last_event = last_event
            if severity is not None:
                self._estado.severity = severity
            if extras is not _UNSET:
                self._estado.extras = {} if extras is None else dict(extras)
            self._estado.updated_at = datetime.now(timezone.utc).isoformat()
            self._persistir()

    def fase(
        self,
        phase_id: str,
        phase_label: str,
        *,
        total: int | None = None,
        current: int = 0,
        current_item: str = "",
        current_task: str = "",
    ) -> None:
        """
        Anuncia el inicio de una nueva fase del pipeline.

        Conveniencia sobre checkpoint() que fija phase_id, phase_label y
        emite last_event con prefijo 'fase:' para que la UI lo detecte.
        """
        self.checkpoint(
            phase_id=phase_id,
            phase_label=phase_label,
            phase_total=total if total is not None else 0,
            phase_current=current,
            current_item=current_item,
            current_task=current_task,
            current_stage=phase_id,
            last_event=f"fase:{phase_label}",
            severity="info",
        )

    def progreso_fase(
        self,
        *,
        current: int | None = None,
        total: int | None = None,
        current_item: str | None = None,
        current_task: str | None = None,
        last_event: str | None = None,
        severity: str = "info",
    ) -> None:
        self.checkpoint(
            phase_current=current,
            phase_total=total,
            current_item=current_item,
            current_task=current_task,
            current_stage=current_task,
            last_event=last_event,
            severity=severity,
        )

    def registrar_tarea_extra(
        self,
        tipo: str,
        nombre: str,
        status: str,
        detalle: str = "",
    ) -> None:
        """
        Actualiza los contadores de una tarea sidecar asíncrona.

        Los tipos reconocidos son "assets", "enrichment" y "manifest".
        Status válidos: "scheduled", "ok"/"saved"/"completed", "timeout",
        "skipped"/"omitted". Cualquier otro valor incrementa "error" y
        registra la falla en errors para auditoría post-ejecución.
        """
        with self._lock:
            data = dict(self._estado.extras.get(tipo, {}))
            if status == "scheduled":
                data["scheduled"] = int(data.get("scheduled", 0)) + 1
                data["pending"] = int(data.get("pending", 0)) + 1
            elif status in {"ok", "saved", "completed"}:
                data["completed"] = int(data.get("completed", 0)) + 1
                data["pending"] = max(0, int(data.get("pending", 0)) - 1)
            elif status == "timeout":
                data["timeout"] = int(data.get("timeout", 0)) + 1
                data["pending"] = max(0, int(data.get("pending", 0)) - 1)
            elif status in {"skipped", "omitted"}:
                data["skipped"] = int(data.get("skipped", 0)) + 1
            else:
                data["error"] = int(data.get("error", 0)) + 1
                data["pending"] = max(0, int(data.get("pending", 0)) - 1)
                self._estado.errors.append(
                    {"tipo": tipo, "nombre": nombre, "status": status, "detalle": detalle}
                )
            data["last_name"] = nombre
            data["last_status"] = status
            if detalle:
                data["last_detail"] = detalle
            self._estado.extras[tipo] = data
            self._estado.last_event = f"{tipo}:{status}:{nombre}"
            self._estado.updated_at = datetime.now(timezone.utc).isoformat()
            self._persistir()

    def registrar_operacion(self, tipo: str, origen: Path, destino: Path) -> None:
        """
        Registra un movimiento de archivo en el log de operaciones del estado.

        Permite reconstruir qué archivos se movieron (hacia biblioteca,
        cuarentena, revisión o procesados) si el proceso termina abruptamente.
        """
        with self._lock:
            self._estado.operaciones.append(
                {
                    "tipo": tipo,
                    "origen": str(origen),
                    "destino": str(destino),
                }
            )
            self._estado.updated_at = datetime.now(timezone.utc).isoformat()
            self._persistir()

    def operaciones(self) -> list[dict[str, str]]:
        with self._lock:
            return list(self._estado.operaciones)

    def cerrar(self, status: str) -> None:
        """
        Escribe el estado final de la ejecución.

        status debe ser uno de: "completed", "cancelled", "error".
        Después de este llamado el archivo de estado queda en disco para
        que la UI lo lea una última vez y limpie su indicador de progreso.
        """
        with self._lock:
            self._estado.status = status
            self._estado.updated_at = datetime.now(timezone.utc).isoformat()
            self._persistir()

    def _persistir(self) -> None:
        """
        Escribe el estado a disco de forma atómica.

        Usa un archivo temporal con TID en el nombre para evitar que dos
        hilos sobreescriban el mismo .tmp. La secuencia write+rename garantiza
        que el lector nunca ve el archivo a medias.

        Side-effect: crea el directorio padre si no existe.
        """
        self._ruta_estado.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "status": self._estado.status,
            "started_at": self._estado.started_at,
            "updated_at": self._estado.updated_at,
            "total_descubiertos": self._estado.total_descubiertos,
            "procesados": self._estado.procesados,
            "current_file": self._estado.current_file,
            "current_stage": self._estado.current_stage,
            "phase_id": self._estado.phase_id,
            "phase_label": self._estado.phase_label,
            "phase_current": self._estado.phase_current,
            "phase_total": self._estado.phase_total,
            "current_item": self._estado.current_item,
            "current_task": self._estado.current_task,
            "eta_seconds": self._estado.eta_seconds,
            "phase_eta_seconds": self._estado.phase_eta_seconds,
            "elapsed_seconds": self._estado.elapsed_seconds,
            "last_event": self._estado.last_event,
            "severity": self._estado.severity,
            "pause_reason": self._estado.pause_reason,
            "cancel_reason": self._estado.cancel_reason,
            "counters": self._estado.counters,
            "extras": self._estado.extras,
            "errors": self._estado.errors,
            "operaciones": self._estado.operaciones,
        }
        contenido = json.dumps(payload, ensure_ascii=False, indent=2)
        ruta_tmp = self._ruta_estado.with_name(
            f".{self._ruta_estado.name}.{threading.get_ident()}.tmp"
        )
        try:
            ruta_tmp.write_text(contenido, encoding="utf-8")
            ruta_tmp.replace(self._ruta_estado)
        finally:
            if ruta_tmp.exists():
                ruta_tmp.unlink(missing_ok=True)
