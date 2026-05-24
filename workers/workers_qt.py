# =============================================================================
# workers/workers_qt.py
#
# Workers Qt para tareas de larga duracion.
#
# Cada worker hereda de QThread y emite seniales para comunicar progreso
# y resultados a los modelos QML. Nunca bloquean el hilo principal.
# =============================================================================

import threading

from PySide6.QtCore import QThread, Signal

from infra.logger import obtener_logger

logger = obtener_logger(__name__)


# =============================================================================
# WORKER DE IMPORTACION
# =============================================================================

class WorkerImportacion(QThread):
    """
    Ejecuta el pipeline del tagger en background.

    Seniales:
        progreso(procesados, total, nombre_archivo, etapa)
        completado(resumen_dict)
        error(mensaje)
    """
    progreso   = Signal(int, int, str, str)
    completado = Signal(dict)
    cancelado  = Signal(dict)
    error      = Signal(str)

    def __init__(self, config_importacion, parent=None):
        super().__init__(parent)
        self._config = config_importacion
        self.setObjectName("WorkerImportacion")

    def run(self):
        try:
            from servicios.importacion import ServicioImportacion

            svc = ServicioImportacion()
            terminado = threading.Event()
            resumen_final = {}
            error_final = None

            def _progreso_fwd(procesados, total, nombre, etapa):
                self.progreso.emit(procesados, total, nombre, etapa)
            svc.on_progreso(_progreso_fwd)

            def _completado_fwd(resumen):
                nonlocal resumen_final
                resumen_final = resumen
                terminado.set()
            svc.on_completado(_completado_fwd)

            def _error_fwd(mensaje):
                nonlocal error_final
                error_final = mensaje
                terminado.set()
            svc.on_error(_error_fwd)

            def _cancelado_fwd(resumen):
                nonlocal resumen_final
                resumen_final = resumen
                terminado.set()
            svc.on_cancelado(_cancelado_fwd)

            if not svc.iniciar(self._config):
                self.error.emit("Ya existe una importacion en ejecucion.")
                return

            while not terminado.wait(0.1):
                if self.isInterruptionRequested():
                    svc.cancelar()

            if error_final:
                self.error.emit(error_final)
                return

            if resumen_final.get("cancelada"):
                self.cancelado.emit(resumen_final)
                return

            self.completado.emit(resumen_final)
        except Exception as e:
            self.error.emit(str(e))


# =============================================================================
# WORKER DE AUDIO INTELLIGENCE BACKGROUND
# =============================================================================

class WorkerAudioIntelligenceBackground(QThread):
    """
    Ejecuta la cola persistente de Audio Intelligence deep sin bloquear QML.
    """
    progreso = Signal(dict)
    completado = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        reactivate_cancelled=False,
        force_retry_failed=False,
        enqueue_missing=True,
        parent=None,
    ):
        super().__init__(parent)
        self._reactivate_cancelled = bool(reactivate_cancelled)
        self._force_retry_failed = bool(force_retry_failed)
        self._enqueue_missing = bool(enqueue_missing)
        self._stop_event = threading.Event()
        self.setObjectName("WorkerAudioIntelligenceBackground")

    def requestInterruption(self):
        self._stop_event.set()
        super().requestInterruption()

    def run(self):
        # Audio Intelligence carga modelos TensorFlow grandes y satura CPU.
        # Bajamos la prioridad del QThread a LowestPriority para que el
        # hilo de la UI (event loop de Qt) tenga ciclos suficientes y la
        # ventana no se trabe mientras el análisis está activo.
        try:
            self.setPriority(QThread.LowestPriority)
        except Exception:
            pass
        try:
            from core.audio_intelligence_background import AudioIntelligenceBackgroundService

            svc = AudioIntelligenceBackgroundService()

            def _progress(snapshot):
                self.progreso.emit(dict(snapshot or {}))

            snapshot = svc.process_pending(
                reactivate_cancelled=self._reactivate_cancelled,
                force_retry_failed=self._force_retry_failed,
                enqueue_missing=self._enqueue_missing,
                progress_callback=_progress,
                stop_event=self._stop_event,
            )
            self.completado.emit(snapshot)
        except Exception as e:
            self.error.emit(str(e))


# =============================================================================
# WORKER DE DIAGNOSTICO/REINTENTOS POST-IMPORT
# =============================================================================

class WorkerImportRecovery(QThread):
    """Ejecuta diagnostico y reintentos auxiliares sin bloquear QML."""

    completado = Signal(dict)
    error = Signal(str)

    def __init__(self, action: str, parent=None):
        super().__init__(parent)
        self._action = str(action or "status")
        self.setObjectName("WorkerImportRecovery")

    def run(self):
        try:
            from core.import_recovery_service import ImportRecoveryService

            svc = ImportRecoveryService()
            if self._action == "status":
                snapshot = svc.status()
            elif self._action == "retry_track_covers":
                snapshot = svc.retry_assets_missing(kinds={"track", "album"})
            elif self._action == "retry_artist_images":
                snapshot = svc.retry_assets_missing(kinds={"artist"})
            elif self._action == "retry_visual_assets":
                snapshot = svc.retry_assets_missing(kinds={"track", "album", "artist"})
            elif self._action == "retry_enrichment":
                snapshot = svc.retry_enrichment_missing()
            elif self._action == "retry_lyrics":
                snapshot = svc.retry_enrichment_missing(lyrics_only=True)
            elif self._action == "retry_audio_features":
                snapshot = svc.retry_audio_features_failed(include_missing=True)
            elif self._action == "retry_deep_failed":
                snapshot = svc.retry_deep_failed()
            elif self._action == "retry_sidecars":
                snapshot = svc.retry_sidecars_failed()
            else:
                snapshot = {**svc.status(), "warning": f"Accion desconocida: {self._action}"}
            self.completado.emit(dict(snapshot or {}))
        except Exception as e:
            self.error.emit(str(e))


# =============================================================================
# WORKER DE BUSQUEDA (debounced)
# =============================================================================

class WorkerBusqueda(QThread):
    """
    Ejecuta una busqueda FTS en background.

    Seniales:
        resultados(dict con claves pistas/albums/artistas)
    """
    resultados = Signal(dict)

    def __init__(self, termino: str, parent=None):
        super().__init__(parent)
        self._termino = termino
        self.setObjectName("WorkerBusqueda")

    def run(self):
        try:
            from servicios.biblioteca import buscar
            if self.isInterruptionRequested():
                return
            resultado = buscar(self._termino)
            if self.isInterruptionRequested():
                return
            self.resultados.emit(resultado)
        except Exception as exc:
            if not self.isInterruptionRequested():
                logger.warning("Busqueda de biblioteca fallida para %r: %s", self._termino, exc)
                self.resultados.emit({"pistas": [], "albums": [], "artistas": []})


class WorkerBusquedaPlaylist(QThread):
    """Busca pistas para agregar a una playlist sin bloquear el hilo QML."""

    resultados = Signal(list)
    error = Signal(str)

    def __init__(self, termino: str, playlist_id: int = -1, limite: int = 50, parent=None):
        super().__init__(parent)
        self._termino = termino
        self._playlist_id = int(playlist_id or -1)
        self._limite = int(limite or 50)
        self.setObjectName("WorkerBusquedaPlaylist")

    def run(self):
        try:
            from servicios.biblioteca import buscar_pistas_para_playlist

            if self.isInterruptionRequested():
                return
            resultados = buscar_pistas_para_playlist(
                self._termino,
                self._playlist_id if self._playlist_id > 0 else None,
                limite=self._limite,
            )
            if self.isInterruptionRequested():
                return
            self.resultados.emit(list(resultados or []))
        except Exception as exc:
            if not self.isInterruptionRequested():
                logger.warning("Busqueda de pistas para playlist fallida para %r: %s", self._termino, exc)
                self.error.emit(str(exc))

# =============================================================================
# WORKER DE BUSQUEDA NATURAL / MUSIC DISCOVERY
# =============================================================================

class WorkerBusquedaNatural(QThread):
    """
    Ejecuta Music Discovery en background para no bloquear QML.
    """
    resultados = Signal(dict)
    error = Signal(str)

    def __init__(self, texto: str, limite: int = 25, parent=None):
        super().__init__(parent)
        self._texto = texto
        self._limite = int(limite or 25)
        self.setObjectName("WorkerBusquedaNatural")

    def run(self):
        try:
            from core.music_discovery_service import MusicDiscoveryService

            if self.isInterruptionRequested():
                return

            svc = MusicDiscoveryService(None)
            estado = svc.analysis_state()

            if self.isInterruptionRequested():
                return

            salida = svc.discover(self._texto or "", limit=self._limite)

            if self.isInterruptionRequested():
                return

            self.resultados.emit({
                "estado": estado,
                "salida": salida,
            })
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.error.emit(str(exc))


# =============================================================================
# WORKER DE PROCESAMIENTO KARAOKE EN BACKGROUND
# =============================================================================

class WorkerKaraokeCola(QThread):
    """Procesa la cola de karaoke en background sin bloquear la UI.

    Emite snapshots de progreso durante el procesamiento y un snapshot
    final al completar o cancelar. La cancelacion es cooperativa: se
    propaga al stop_event del servicio entre segmentos del modelo Demucs.
    """

    progreso   = Signal(dict)
    completado = Signal(dict)
    error      = Signal(str)

    def __init__(self, cache_dir: str, device_pref: str = "auto",
                 nombre_modelo: str = "htdemucs", parent=None):
        super().__init__(parent)
        self._cache_dir     = cache_dir
        self._device_pref   = device_pref or "auto"
        self._nombre_modelo = nombre_modelo or "htdemucs"
        self._stop_event    = threading.Event()
        self.setObjectName("WorkerKaraokeCola")

    def requestInterruption(self):
        self._stop_event.set()
        super().requestInterruption()

    def run(self):
        # Demucs satura CPU al separar. Misma estrategia que el worker
        # de Audio Intelligence: prioridad mínima para no robarle ciclos
        # al event loop de la UI mientras procesamos pistas.
        try:
            self.setPriority(QThread.LowestPriority)
        except Exception:
            pass
        try:
            from pathlib import Path
            from servicios.karaoke import procesar_cola

            def _progress(snapshot):
                self.progreso.emit(dict(snapshot or {}))

            snap = procesar_cola(
                cache_dir=Path(self._cache_dir),
                device_pref=self._device_pref,
                nombre_modelo=self._nombre_modelo,
                progress_callback=_progress,
                stop_event=self._stop_event,
            )
            self.completado.emit(dict(snap or {}))
        except Exception as exc:
            logger.exception("WorkerKaraokeCola error")
            self.error.emit(str(exc))
