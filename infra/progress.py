# =============================================================================
# infra/progress.py
#
# Visualizacion de progreso en terminal durante la ejecucion del pipeline.
# Muestra en tiempo real: archivo actual, etapa, contadores acumulados
# por resultado y estimacion de tiempo restante.
#
# Implementado sin dependencias externas (no usa tqdm ni rich) para mantener
# portabilidad maxima. Usa ANSI escape codes para actualizacion de linea.
#
# Novedades v3:
#   - La barra de estado muestra un indicador "S" (Shazam) y "A" (AcoustID)
#     cuando estos modulos han identificado archivos en la sesion actual.
#   - La etapa "fingerprint" y "shazam" se muestran en la columna de etapa.
# =============================================================================

import os
import sys
import time
import threading
from dataclasses import dataclass, field

from infra.version import CLI_BANNER
from typing import Any, Optional

# =============================================================================
# AJUSTES INTERNOS
# =============================================================================

_ANCHO_NOMBRE_ARCHIVO   = 45
_ANCHO_ETAPA            = 18
_INTERVALO_REFRESCO_SEG = 0.15
_INTERVALO_LOG_DEFAULT_SEG = 2.0

_SIMBOLO = {
    "aceptado":            "✓",
    "aceptado_provisional": "◎",
    "revision":            "~",
    "cuarentena":          "✗",
    "duplicado_exacto":    "D",
    "duplicado_semantico": "D",
    "duplicado_mejorable": "D",
    "omitido":             "○",
    "error":               "!",
}

_C_VERDE    = "\033[92m"
_C_AMARILLO = "\033[93m"
_C_ROJO     = "\033[91m"
_C_GRIS     = "\033[90m"
_C_CIAN     = "\033[96m"
_C_NEGRITA  = "\033[1m"
_C_RESET    = "\033[0m"


def _stdout_isatty() -> bool:
    """TTY check seguro para apps GUI en Windows donde sys.stdout puede ser None."""
    try:
        return bool(sys.stdout is not None and sys.stdout.isatty())
    except Exception:
        return False


_CLEAR_LINE   = "\033[K" if _stdout_isatty() else ""
_COLOR_ACTIVO = _stdout_isatty() and os.getenv("NO_COLOR") is None
if not _COLOR_ACTIVO:
    _C_VERDE = _C_AMARILLO = _C_ROJO = _C_GRIS = _C_CIAN = _C_NEGRITA = _C_RESET = ""

_EXTRA_LABELS = {
    "assets": "imagenes",
    "enrichment": "letras",
    "manifest": "manifest",
}

_EXTRA_PESOS = {
    # Pesos para porcentaje de trabajo visible. El ETA usa tiempos reales/EWMA.
    "assets": 0.45,
    "enrichment": 0.45,
    "manifest": 0.05,
}

_EXTRA_ETA_DEFAULT = {
    # Estimaciones iniciales conservadoras hasta tener muestras reales.
    "assets": 5.0,
    "enrichment": 4.0,
    "manifest": 0.2,
}

_MODOS_VALIDOS = {"auto", "tty", "log", "quiet"}


def _env_float(nombre: str, default: float, minimo: float, maximo: float) -> float:
    valor = os.getenv(nombre)
    if valor is None:
        return default
    try:
        numero = float(valor)
    except ValueError:
        return default
    return min(max(numero, minimo), maximo)


def _resolver_modo_salida() -> str:
    modo = os.getenv("NB_SOUND_PROGRESS_MODE", "auto").strip().lower()
    if modo not in _MODOS_VALIDOS:
        modo = "auto"
    if modo == "auto":
        return "tty" if _stdout_isatty() else "log"
    return modo


# =============================================================================
# ESTADO INTERNO
# =============================================================================

@dataclass
class _EstadoProgreso:
    """
    Estado interno mutable de BarraProgreso.

    Encapsula tanto los contadores de resultado (aceptados, cuarentena, etc.)
    como los datos de ETA y la información de sidecars asíncronos (extras).

    El ETA global usa EWMA (α=0.35) sobre el tiempo real por archivo para
    suavizar picos. Para sidecars, combina tiempo real observado con
    estimaciones conservadoras definidas en _EXTRA_ETA_DEFAULT.

    No expone estado al exterior: BarraProgreso es la única clase que lo
    instancia y manipula.
    """
    total_archivos:   int   = 0
    procesados:       int   = 0
    aceptados:        int   = 0
    provisionales:    int   = 0
    revision:         int   = 0
    cuarentena:       int   = 0
    omitidos:         int   = 0
    errores:          int   = 0
    duplicados:       int   = 0

    archivo_actual:   str   = ""
    etapa_actual:     str   = ""
    ultimo_resultado: str   = ""
    tarea_extra_actual: str = ""
    fase_id:          str   = "startup"
    fase_label:       str   = "Preparando"
    fase_actual:      int   = 0
    fase_total:       int   = 0
    item_actual:      str   = ""
    tarea_actual:     str   = ""
    ultimo_evento:    str   = ""
    severidad:        str   = "info"

    tiempo_inicio:    float = field(default_factory=time.time)
    tiempo_fase_inicio: float = field(default_factory=time.time)
    ultimo_refresco:  float = 0.0
    ewma_tiempo_archivo: Optional[float] = None
    ewma_tiempo_extra: dict[str, float] = field(default_factory=dict)
    extras_programadas: dict[str, int] = field(default_factory=dict)
    extras_completadas: dict[str, int] = field(default_factory=dict)
    extras_error: dict[str, int] = field(default_factory=dict)
    extras_omitidas: dict[str, int] = field(default_factory=dict)
    extras_pendientes: dict[str, int] = field(default_factory=dict)
    _alpha_ewma: float = 0.35

    def incrementar(self, resultado: str) -> None:
        self.procesados += 1
        if resultado == "aceptado":
            self.aceptados += 1
        elif resultado == "aceptado_provisional":
            # FIX v3.2: los provisionales se contaban como errores (else branch)
            self.provisionales += 1
        elif resultado == "revision":
            self.revision += 1
        elif resultado == "cuarentena":
            self.cuarentena += 1
        elif resultado == "omitido":
            self.omitidos += 1
        elif resultado in {"duplicado_exacto", "duplicado_semantico", "duplicado_mejorable"}:
            self.duplicados += 1
        else:
            self.errores += 1
        self.ultimo_resultado = resultado
        self.ultimo_evento = f"resultado:{resultado}"

    def registrar_tiempo_archivo(self, duracion_seg: Optional[float]) -> None:
        if duracion_seg is None or duracion_seg <= 0:
            return
        if self.ewma_tiempo_archivo is None:
            self.ewma_tiempo_archivo = duracion_seg
            return
        self.ewma_tiempo_archivo = (
            self._alpha_ewma * duracion_seg
            + (1 - self._alpha_ewma) * self.ewma_tiempo_archivo
        )

    def registrar_extra(self, tipo: str, descripcion: str) -> None:
        self.extras_programadas[tipo] = self.extras_programadas.get(tipo, 0) + 1
        self.extras_pendientes[tipo] = self.extras_pendientes.get(tipo, 0) + 1
        self.tarea_extra_actual = descripcion
        self.ultimo_evento = descripcion

    def omitir_extra(self, tipo: str) -> None:
        self.extras_omitidas[tipo] = self.extras_omitidas.get(tipo, 0) + 1
        self.ultimo_evento = f"{_EXTRA_LABELS.get(tipo, tipo)} omitido"

    def completar_extra(
        self,
        tipo: str,
        ok: bool,
        duracion_seg: Optional[float],
        descripcion: str = "",
    ) -> None:
        pendientes = self.extras_pendientes.get(tipo, 0)
        if pendientes > 0:
            self.extras_pendientes[tipo] = pendientes - 1

        destino = self.extras_completadas if ok else self.extras_error
        destino[tipo] = destino.get(tipo, 0) + 1
        self.tarea_extra_actual = descripcion
        self.ultimo_evento = descripcion

        if duracion_seg is None or duracion_seg <= 0:
            return
        anterior = self.ewma_tiempo_extra.get(tipo)
        if anterior is None:
            self.ewma_tiempo_extra[tipo] = duracion_seg
            return
        self.ewma_tiempo_extra[tipo] = (
            self._alpha_ewma * duracion_seg
            + (1 - self._alpha_ewma) * anterior
        )

    def tiempo_transcurrido(self) -> float:
        return time.time() - self.tiempo_inicio

    def tiempo_restante_estimado(self) -> Optional[float]:
        """
        Calcula el ETA total combinando:
          1. Archivos pendientes * tiempo promedio mixto (EWMA + global).
          2. Sidecars pendientes ya programados * tiempo estimado por tipo.
          3. Proyección de sidecars futuros para archivos aún no procesados,
             basada en la tasa de sidecars observada hasta ahora.

        Retorna None si no hay datos suficientes para estimar.
        """
        if self.procesados == 0 and not self._extras_pendientes_total():
            return None

        restantes_archivos = max(0, self.total_archivos - self.procesados)
        eta_archivos = 0.0
        if self.procesados > 0:
            promedio_global = self.tiempo_transcurrido() / self.procesados
            promedio = self.ewma_tiempo_archivo or promedio_global
            # Mezcla EWMA (peso 75%) con promedio global (peso 25%) para
            # responder a picos recientes sin ser demasiado volátil.
            promedio_mixto = (0.75 * promedio) + (0.25 * promedio_global)
            eta_archivos = promedio_mixto * restantes_archivos

        eta_extras = 0.0
        for tipo, pendientes in self.extras_pendientes.items():
            eta_extras += max(0, pendientes) * self._estimacion_extra(tipo)

        # Estimar sidecars futuros con base en lo observado hasta ahora. No intenta
        # adivinar qué archivos se aceptarán; usa la tasa real de sidecars ya
        # programados por archivo procesado para que el ETA no ignore trabajo de red.
        if self.procesados > 0 and restantes_archivos > 0:
            for tipo, programadas in self.extras_programadas.items():
                tasa_por_archivo = programadas / self.procesados
                eta_extras += restantes_archivos * tasa_por_archivo * self._estimacion_extra(tipo)

        return eta_archivos + eta_extras

    def establecer_fase(
        self,
        fase_id: str,
        fase_label: str,
        total: Optional[int] = None,
        actual: int = 0,
        item: str = "",
        tarea: str = "",
    ) -> None:
        self.fase_id = fase_id
        self.fase_label = fase_label
        self.fase_total = max(0, int(total or 0))
        self.fase_actual = max(0, int(actual))
        if self.fase_total:
            self.fase_actual = min(self.fase_actual, self.fase_total)
        self.item_actual = item
        self.tarea_actual = tarea
        self.ultimo_evento = f"fase:{fase_label}"
        self.severidad = "info"
        self.tiempo_fase_inicio = time.time()

    def actualizar_fase(
        self,
        actual: Optional[int] = None,
        total: Optional[int] = None,
        item: Optional[str] = None,
        tarea: Optional[str] = None,
        severidad: str = "info",
    ) -> None:
        if total is not None:
            self.fase_total = max(0, int(total))
        if actual is not None:
            self.fase_actual = max(0, int(actual))
            if self.fase_total:
                self.fase_actual = min(self.fase_actual, self.fase_total)
        if item is not None:
            self.item_actual = item
        if tarea is not None:
            self.tarea_actual = tarea
        self.severidad = severidad
        partes = [self.fase_label]
        if self.fase_total:
            partes.append(f"{self.fase_actual}/{self.fase_total}")
        if self.item_actual:
            partes.append(self.item_actual)
        self.ultimo_evento = " · ".join(partes)

    def eta_fase(self) -> Optional[float]:
        if self.fase_total <= 0 or self.fase_actual <= 0 or self.fase_actual >= self.fase_total:
            return None
        transcurrido = max(0.0, time.time() - self.tiempo_fase_inicio)
        if transcurrido < 1.0:
            return None
        return (transcurrido / max(1, self.fase_actual)) * (self.fase_total - self.fase_actual)

    def trabajo_total(self) -> float:
        total = float(self.total_archivos)
        for tipo, cantidad in self.extras_programadas.items():
            total += cantidad * _EXTRA_PESOS.get(tipo, 0.25)
        return max(total, 1.0)

    def trabajo_completado(self) -> float:
        total = float(self.procesados)
        tipos = set(self.extras_completadas) | set(self.extras_error)
        for tipo in tipos:
            cantidad = self.extras_completadas.get(tipo, 0) + self.extras_error.get(tipo, 0)
            total += cantidad * _EXTRA_PESOS.get(tipo, 0.25)
        return min(total, self.trabajo_total())

    def _estimacion_extra(self, tipo: str) -> float:
        return self.ewma_tiempo_extra.get(
            tipo,
            _EXTRA_ETA_DEFAULT.get(tipo, 2.0),
        )

    def _extras_pendientes_total(self) -> int:
        return sum(max(0, n) for n in self.extras_pendientes.values())

    def snapshot(self) -> dict[str, Any]:
        return {
            "phase_id": self.fase_id,
            "phase_label": self.fase_label,
            "processed_files": self.procesados,
            "total_files": self.total_archivos,
            "phase_current": self.fase_actual,
            "phase_total": self.fase_total,
            "current_item": self.item_actual or self.archivo_actual,
            "current_task": self.tarea_actual or self.etapa_actual,
            "extras": {
                tipo: {
                    "scheduled": self.extras_programadas.get(tipo, 0),
                    "completed": self.extras_completadas.get(tipo, 0),
                    "error": self.extras_error.get(tipo, 0),
                    "skipped": self.extras_omitidas.get(tipo, 0),
                    "pending": self.extras_pendientes.get(tipo, 0),
                }
                for tipo in sorted(
                    set(self.extras_programadas)
                    | set(self.extras_completadas)
                    | set(self.extras_error)
                    | set(self.extras_omitidas)
                    | set(self.extras_pendientes)
                )
            },
            "eta_seconds": self.tiempo_restante_estimado(),
            "phase_eta_seconds": self.eta_fase(),
            "elapsed_seconds": self.tiempo_transcurrido(),
            "last_event": self.ultimo_evento,
            "severity": self.severidad,
        }


# =============================================================================
# CLASE PRINCIPAL
# =============================================================================

class BarraProgreso:
    """
    Renderiza el progreso del pipeline en terminal o log según el modo de salida.

    Modos de salida (NB_SOUND_PROGRESS_MODE):
        "tty"   — refresco en línea con ANSI (\\r + CLEAR_LINE), para terminales.
        "log"   — una línea por refresco, apta para logs y CI sin TTY.
        "quiet" — sin salida (útil en tests o cuando la UI toma control).
        "auto"  — detecta si stdout es TTY y elige "tty" o "log".

    Thread-safety: todos los métodos públicos adquieren _lock antes de mutar
    _estado o emitir salida. El hilo worker llama a los métodos de actualización
    y el hilo principal (o la UI) puede llamar a snapshot() concurrentemente.

    Uso tipico:
        barra = BarraProgreso(total=100)
        barra.iniciar()
        barra.actualizar_archivo("cancion.mp3", "validando")
        barra.registrar_resultado("aceptado")
        barra.finalizar()
    """

    def __init__(self, total_archivos: int) -> None:
        self._estado = _EstadoProgreso(total_archivos=total_archivos)
        self._activa = False
        self._lock = threading.RLock()
        self._modo_salida = _resolver_modo_salida()
        self._intervalo_log = _env_float(
            "NB_SOUND_PROGRESS_INTERVAL_SEC",
            _INTERVALO_LOG_DEFAULT_SEG,
            0.25,
            60.0,
        )

    # ------------------------------------------------------------------
    # API PUBLICA
    # ------------------------------------------------------------------

    def iniciar(self) -> None:
        with self._lock:
            self._activa = True
            self._estado.tiempo_inicio = time.time()
            self._imprimir_encabezado()

    def set_total_archivos(self, total: int) -> None:
        with self._lock:
            self._estado.total_archivos = max(0, int(total))
            self._refrescar_si_corresponde(forzar=True)

    def actualizar_archivo(self, nombre: str, etapa: str) -> None:
        with self._lock:
            self._estado.archivo_actual = self._truncar(nombre, _ANCHO_NOMBRE_ARCHIVO)
            self._estado.etapa_actual   = etapa
            self._estado.item_actual = nombre
            self._estado.tarea_actual = etapa
            self._estado.ultimo_evento = f"{etapa}: {nombre}"
            self._refrescar_si_corresponde()

    def establecer_fase(
        self,
        phase_id: str,
        phase_label: str,
        total: Optional[int] = None,
        current: int = 0,
        current_item: str = "",
        current_task: str = "",
    ) -> None:
        with self._lock:
            self._estado.establecer_fase(
                phase_id,
                phase_label,
                total=total,
                actual=current,
                item=current_item,
                tarea=current_task,
            )
            self._imprimir_aviso(f"Fase: {phase_label}", "info")
            self._refrescar_si_corresponde(forzar=True)

    def actualizar_fase(
        self,
        current: Optional[int] = None,
        total: Optional[int] = None,
        current_item: Optional[str] = None,
        current_task: Optional[str] = None,
        severity: str = "info",
    ) -> None:
        with self._lock:
            self._estado.actualizar_fase(
                actual=current,
                total=total,
                item=current_item,
                tarea=current_task,
                severidad=severity,
            )
            self._refrescar_si_corresponde()

    def heartbeat(self, texto: str = "") -> None:
        with self._lock:
            if texto:
                self._estado.ultimo_evento = texto
            self._refrescar_si_corresponde(forzar=True)

    def registrar_resultado(
        self,
        resultado: str,
        duracion_archivo_seg: Optional[float] = None,
    ) -> None:
        with self._lock:
            self._estado.incrementar(resultado)
            self._estado.registrar_tiempo_archivo(duracion_archivo_seg)
            self._imprimir_linea_resultado(resultado)
            self._refrescar_si_corresponde(forzar=True)

    def registrar_tarea_extra(self, tipo: str, nombre: str, descripcion: str = "") -> None:
        """Registra trabajo adicional posterior al archivo: imagenes, letras o manifest."""
        with self._lock:
            label = _EXTRA_LABELS.get(tipo, tipo)
            texto = descripcion or f"{label}: {nombre}"
            self._estado.registrar_extra(tipo, self._truncar(texto, 58))
            self._refrescar_si_corresponde(forzar=True)

    def finalizar_tarea_extra(
        self,
        tipo: str,
        nombre: str,
        ok: bool = True,
        detalle: str = "",
        duracion_seg: Optional[float] = None,
    ) -> None:
        with self._lock:
            label = _EXTRA_LABELS.get(tipo, tipo)
            estado = "ok" if ok else "error"
            texto = self._truncar(f"{label} {estado}: {nombre}", 58)
            self._estado.completar_extra(tipo, ok, duracion_seg, texto)
            if not ok:
                extra = f" ({detalle})" if detalle else ""
                self._imprimir_aviso(f"{label}: no se pudo guardar {nombre}{extra}", "warn")
            self._refrescar_si_corresponde(forzar=True)

    def omitir_tarea_extra(self, tipo: str, nombre: str, razon: str = "") -> None:
        with self._lock:
            _ = nombre
            self._estado.omitir_extra(tipo)
            if razon:
                self._estado.tarea_extra_actual = self._truncar(
                    f"{_EXTRA_LABELS.get(tipo, tipo)} omitido: {razon}",
                    58,
                )
            self._refrescar_si_corresponde(forzar=True)

    def finalizar(self) -> None:
        with self._lock:
            self._activa = False
            self._imprimir_resumen_final()

    def mensaje(self, texto: str, nivel: str = "info") -> None:
        """Imprime un aviso importante fuera del flujo normal de la barra."""
        with self._lock:
            self._estado.ultimo_evento = texto
            self._estado.severidad = nivel
            self._imprimir_aviso(texto, nivel)
            self._refrescar_si_corresponde(forzar=True)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._estado.snapshot()

    # ------------------------------------------------------------------
    # RENDERIZADO INTERNO
    # ------------------------------------------------------------------

    def _imprimir_encabezado(self) -> None:
        if self._modo_salida == "quiet":
            return
        separador = "─" * 74
        print(f"\n{_C_NEGRITA}  {CLI_BANNER} — Procesando biblioteca{_C_RESET}")
        print(f"  Total de archivos: {_C_CIAN}{self._estado.total_archivos}{_C_RESET}")
        print(f"  {separador}")
        print(
            f"  {'ARCHIVO':<{_ANCHO_NOMBRE_ARCHIVO}}  "
            f"{'ETAPA':<{_ANCHO_ETAPA}}  RESULTADO"
        )
        print(f"  {separador}")

    def _imprimir_linea_resultado(self, resultado: str) -> None:
        if self._modo_salida == "quiet":
            return
        simbolo = _SIMBOLO.get(resultado, "?")
        colores = {
            "aceptado":            _C_VERDE,
            "aceptado_provisional": _C_CIAN,   # FIX v3.2: provisional = exito parcial
            "revision":            _C_AMARILLO,
            "cuarentena":          _C_ROJO,
            "duplicado_exacto":    _C_CIAN,
            "duplicado_semantico": _C_CIAN,
            "duplicado_mejorable": _C_CIAN,
            "omitido":             _C_GRIS,
            "error":               _C_ROJO,
        }
        color  = colores.get(resultado, _C_RESET)
        nombre = self._truncar(self._estado.archivo_actual, _ANCHO_NOMBRE_ARCHIVO)
        etapa  = self._truncar(self._estado.etapa_actual,   _ANCHO_ETAPA)
        linea  = (
            f"  {nombre:<{_ANCHO_NOMBRE_ARCHIVO}}  "
            f"{etapa:<{_ANCHO_ETAPA}}  "
            f"{color}{simbolo} {resultado.upper()}{_C_RESET}"
        )
        if self._modo_salida == "tty":
            print(f"\r{linea}{_CLEAR_LINE}")
        else:
            print(linea, flush=True)

    def _imprimir_aviso(self, texto: str, nivel: str = "info") -> None:
        if self._modo_salida == "quiet":
            return
        colores = {
            "info":  _C_CIAN,
            "warn":  _C_AMARILLO,
            "error": _C_ROJO,
            "ok":    _C_VERDE,
        }
        color = colores.get(nivel, _C_RESET)
        if self._modo_salida == "tty":
            print(f"\r{color}  >> {texto}{_C_RESET}{_CLEAR_LINE}")
        else:
            print(f"  >> {texto}", flush=True)

    def _refrescar_si_corresponde(self, forzar: bool = False) -> None:
        if self._modo_salida == "quiet":
            return
        ahora = time.time()
        intervalo = _INTERVALO_REFRESCO_SEG if self._modo_salida == "tty" else self._intervalo_log
        if (not forzar
                and (ahora - self._estado.ultimo_refresco) < intervalo):
            return
        self._estado.ultimo_refresco = ahora
        self._imprimir_barra_estado()

    def _imprimir_barra_estado(self) -> None:
        if self._modo_salida == "quiet":
            return
        e          = self._estado
        trabajo_total = e.trabajo_total()
        trabajo_hecho = e.trabajo_completado()
        porcentaje = (trabajo_hecho / trabajo_total * 100) if trabajo_total else 0

        ancho_barra = 28
        llenos = int(ancho_barra * trabajo_hecho / max(trabajo_total, 1))
        barra  = f"{'█' * llenos}{'░' * (ancho_barra - llenos)}"

        eta = self._formato_eta(e.tiempo_restante_estimado())
        eta_fase = self._formato_eta(e.eta_fase())
        fase = e.fase_label
        if e.fase_total:
            fase = f"{fase} {e.fase_actual}/{e.fase_total}"

        extras = self._resumen_extras_inline(e)
        tarea_extra = f"  {e.tarea_extra_actual}" if e.tarea_extra_actual else ""
        actual = self._truncar(e.item_actual or e.archivo_actual, 42)
        tarea = self._truncar(e.tarea_actual or e.etapa_actual, 24)
        estado = (
            f"  {_C_CIAN}[{barra}]{_C_RESET} "
            f"{porcentaje:5.1f}%  "
            f"Fase:{fase}  "
            f"Arch:{e.procesados}/{e.total_archivos}  "
            f"{_C_VERDE}✓{e.aceptados}{_C_RESET}  "
            f"{_C_CIAN}◎{e.provisionales}{_C_RESET}  "
            f"{_C_AMARILLO}~{e.revision}{_C_RESET}  "
            f"{_C_ROJO}✗{e.cuarentena}{_C_RESET}  "
            f"{_C_CIAN}D:{e.duplicados}{_C_RESET}  "
            f"{_C_GRIS}○{e.omitidos}{_C_RESET}  "
            f"{extras}  "
            f"ETA:{eta}  "
            f"ETA fase:{eta_fase}  "
            f"Ritmo:{self._calcular_ritmo(e):>5}  "
            f"T:{self._formato_duracion(e.tiempo_transcurrido())}"
            f"  Actual:{actual or '-'}"
            f"  Tarea:{tarea or '-'}"
            f"{tarea_extra}   "
        )
        if self._modo_salida == "tty":
            print(f"\r{estado}{_CLEAR_LINE}", end="", flush=True)
        else:
            print(f"[progreso] {estado.strip()}", flush=True)

    def _imprimir_resumen_final(self) -> None:
        if self._modo_salida == "quiet":
            return
        e         = self._estado
        duracion  = e.tiempo_transcurrido()
        separador = "─" * 74

        print(f"\n\n  {separador}")
        print(f"  {_C_NEGRITA}RESUMEN DE EJECUCION{_C_RESET}")
        print(f"  {separador}")
        print(f"  Total descubiertos : {e.total_archivos}")
        print(f"  {_C_VERDE}Aceptados          : {e.aceptados}{_C_RESET}")
        print(f"  {_C_CIAN}Prov. aceptados    : {e.provisionales}{_C_RESET}")
        print(f"  {_C_AMARILLO}Revision           : {e.revision}{_C_RESET}")
        print(f"  {_C_ROJO}Cuarentena         : {e.cuarentena}{_C_RESET}")
        print(f"  {_C_CIAN}Duplicados         : {e.duplicados}{_C_RESET}")
        print(f"  {_C_GRIS}Omitidos           : {e.omitidos}{_C_RESET}")
        print(f"  {_C_ROJO}Errores            : {e.errores}{_C_RESET}")
        for tipo in sorted(
            set(e.extras_programadas) | set(e.extras_completadas)
            | set(e.extras_error) | set(e.extras_omitidas)
        ):
            label = _EXTRA_LABELS.get(tipo, tipo)
            ok = e.extras_completadas.get(tipo, 0)
            err = e.extras_error.get(tipo, 0)
            omit = e.extras_omitidas.get(tipo, 0)
            pend = e.extras_pendientes.get(tipo, 0)
            print(
                f"  Sidecar {label:<9}: "
                f"{_C_VERDE}ok {ok}{_C_RESET} / "
                f"{_C_ROJO}error {err}{_C_RESET} / "
                f"{_C_GRIS}omitido {omit}{_C_RESET} / pendiente {pend}"
            )
        print(f"  Duracion total     : {self._formato_duracion(duracion)}")
        if e.procesados > 0:
            promedio = duracion / e.procesados
            print(f"  Tiempo por archivo : {promedio:.2f}s promedio")
        print(f"  {separador}\n")

    @staticmethod
    def _resumen_extras_inline(estado: _EstadoProgreso) -> str:
        partes = []
        for tipo in ("assets", "enrichment", "manifest"):
            total = estado.extras_programadas.get(tipo, 0)
            if total <= 0:
                continue
            hechos = estado.extras_completadas.get(tipo, 0) + estado.extras_error.get(tipo, 0)
            pendientes = estado.extras_pendientes.get(tipo, 0)
            label = _EXTRA_LABELS.get(tipo, tipo)
            partes.append(f"{label}:{hechos}/{total}" + (f"+{pendientes}" if pendientes else ""))
        return " ".join(partes)

    @staticmethod
    def _truncar(texto: str, max_len: int) -> str:
        if len(texto) <= max_len:
            return texto
        return texto[:max_len - 3] + "..."

    @staticmethod
    def _formato_duracion(segundos: float) -> str:
        if segundos < 60:
            return f"{segundos:.1f}s"
        minutos = int(segundos) // 60
        segs    = int(segundos) % 60
        return f"{minutos}m {segs}s"

    @classmethod
    def _formato_eta(cls, segundos: Optional[float]) -> str:
        if segundos is None:
            return "calculando..."
        if segundos < 60:
            return f"~{int(segundos)}s"
        return f"~{int(segundos // 60)}m {int(segundos % 60)}s"

    @staticmethod
    def _calcular_ritmo(estado: _EstadoProgreso) -> str:
        transcurrido = estado.tiempo_transcurrido()
        if transcurrido <= 0:
            return "--/m"
        por_minuto = int((estado.procesados / transcurrido) * 60)
        return f"{por_minuto}/m"
