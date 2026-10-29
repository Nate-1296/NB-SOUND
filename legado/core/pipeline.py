# =============================================================================
# core/pipeline.py
#
# Orquestador principal del pipeline de catalogacion v3.
#
# Flujo completo por archivo de audio:
#   1. Verificar si ya fue procesado
#   2. Validacion tecnica (duracion, bitrate, legibilidad)
#   3. Normalizacion de metadata local (tags ID3)
#   4. Generacion de fingerprint acustico (opcional — AcoustID)
#   5. Identificacion por Shazam (opcional)
#   6. Fusion de evidencias (metadata + Shazam + AcoustID -> MetadataNormalizada)
#   7. Consulta a MusicBrainz (con ISRC y recording_ids si disponibles)
#   8. Scoring determinista multicriterio
#   9. Desempate con IA si hay ambiguedad (opcional — Anthropic)
#  10. Escritura segura de tags sobre copia temporal + validacion
#  11. Movimiento a estructura de biblioteca
#  12. Cuarentena o revision si no se acepta
#
# Todas las rutas del sistema se inyectan desde el exterior (via main.py).
# El pipeline nunca crea nada dentro del directorio del proyecto.
# =============================================================================

import time
import json
import queue
import shutil
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings as _settings
from config.settings import (
    SKIP_ALREADY_PROCESSED,
    ENABLE_DEDUPLICATION,
    ENABLE_SEMANTIC_DEDUPLICATION,
    ENABLE_ASSETS_PIPELINE,
    DUPLICATE_POLICY,
    INIT_COMPONENT_MAX_RETRIES,
    INIT_COMPONENT_RETRY_BACKOFF_SEG,
    SIDECAR_FUTURE_TIMEOUT_SEG,
    SIDECAR_WAIT_HEARTBEAT_SEG,
    ENABLE_SECOND_STAGE_RESOLUTION,
    ENABLE_THIRD_STAGE_RESOLUTION,
)
from domain.models import (
    ResultadoEjecucion,
    DecisionTipo,
    DecisionArchivo,
    CuarentenaCausa,
    RevisionCausa,
    ArchivoAudio,
)
from core.discovery import descubrir_archivos
from core.validator import validar_archivo
from core.normalizer import normalizar_metadata
from core.matcher import evaluar_candidatos
from core.writer import escribir_y_mover
from core.second_stage import SegundaFaseResolucion
from core.third_stage import TerceraFaseResolucion
from core.dedupe import GestorDuplicados
from core.assets_pipeline import PipelineAssets
from core.enrichment_pipeline import EnrichmentPipeline
from core.manifests import GestorManifests
from core.discography import OrganizadorDiscografias
from core.overrides import MemoriaOverrides
from core.audit import DoctorBiblioteca
from external.cache import CacheLocal
from external.musicbrainz_client import ClienteMusicBrainz
from external.acoustid_client import ClienteAcoustID
from external.shazam_client import ClienteShazam
from external.ia_client import ClienteIA
from external.itunes_client import ClienteItunes
from external.transcoder import TranscodificadorAudio
from infra.logger import (
    inicializar_logging,
    cerrar_logging,
    obtener_logger,
    log_inicio_archivo,
    log_decision,
    log_error_archivo,
    registrar_evento,
)
from infra.progress import BarraProgreso
from infra.quarantine import GestorCuarentena
from infra.processed import GestorProcesados
from infra.reports import guardar_reporte, imprimir_resumen_consola
from infra.version import CLI_BANNER
from infra.execution_control import ControlEjecucion

_log = obtener_logger("pipeline")


class _ComponenteInactivo:
    """
    Sustituto nulo (null object) para componentes externos que no pudieron
    inicializarse tras agotar los reintentos de arranque.

    Permite que el pipeline continúe ejecutándose en modo degradado: cualquier
    llamada a métodos del componente retorna una lista vacía sin lanzar excepciones.
    El atributo ``activo = False`` permite al pipeline saber que el servicio
    está deshabilitado y ajustar su comportamiento (logs, contadores, flujo).
    """

    def __init__(self, nombre: str) -> None:
        self.nombre = nombre
        self.activo = False
        self.estadisticas = {}

    def __getattr__(self, _name: str):
        def _noop(*_args, **_kwargs):
            return []
        return _noop


class _SidecarExecutorDaemon:
    """
    Executor de hilos daemon para tareas sidecar (assets e enrichment).

    Las tareas sidecar son no críticas: su fallo nunca bloquea la decisión
    principal del archivo. Por eso se ejecutan en hilos daemon (mueren junto
    al proceso principal) y con un timeout configurable por tarea.

    Implementación propia en lugar de ThreadPoolExecutor estándar para tener
    control explícito sobre el shutdown y el estado de cada Future, necesario
    para la lógica de timeout por tarea individual y el rollback en cancelación.
    """

    def __init__(self, max_workers: int = 2) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._shutdown = False
        self._lock = threading.RLock()
        self._threads: list[threading.Thread] = []
        for idx in range(max(1, max_workers)):
            thread = threading.Thread(
                target=self._worker,
                name=f"nb_sound_sidecar_{idx + 1}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def submit(self, fn, /, *args, **kwargs) -> Future:
        """
        Encola una tarea para ejecución asíncrona.

        Retorna un Future que será resuelto por un worker daemon.
        Si el executor ya fue cerrado, el Future se rechaza con RuntimeError.
        """
        future: Future = Future()
        with self._lock:
            if self._shutdown:
                future.set_exception(RuntimeError("Sidecar executor cerrado"))
                return future
            self._queue.put((future, fn, args, kwargs))
        return future

    def shutdown(self, wait: bool = False, cancel_futures: bool = False) -> None:
        """
        Detiene el executor.

        Si ``cancel_futures=True``, vacía la cola y cancela los Futures pendientes
        antes de enviar la señal de parada a los workers. Si ``wait=True``, espera
        hasta 1s por worker a que terminen los hilos activos.
        """
        with self._lock:
            self._shutdown = True
            if cancel_futures:
                while True:
                    try:
                        item = self._queue.get_nowait()
                    except queue.Empty:
                        break
                    if item is None:
                        self._queue.task_done()
                        continue
                    future = item[0]
                    future.cancel()
                    self._queue.task_done()
            for _ in self._threads:
                self._queue.put(None)
        if wait:
            for thread in self._threads:
                thread.join(timeout=1.0)

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                future, fn, args, kwargs = item
                if not future.set_running_or_notify_cancel():
                    continue
                setattr(future, "_nb_sound_started_at", time.monotonic())
                try:
                    result = fn(*args, **kwargs)
                except BaseException as exc:
                    future.set_exception(exc)
                else:
                    future.set_result(result)
            finally:
                self._queue.task_done()


# =============================================================================
# CLASE PRINCIPAL
# =============================================================================

class PipelineCatalogacion:
    """
    Orquestador principal del pipeline de catalogación musical v3.

    Coordina las doce etapas del flujo por archivo (discovery → validación →
    transcodificación → normalización → identificación → matching → escritura →
    cuarentena/revisión) y las tres fases de resolución secuenciales.

    Diseño de inyección de dependencias:
      - Todas las rutas del sistema se reciben como parámetros. El pipeline
        nunca resuelve rutas relativas al directorio del proyecto.
      - Cada componente externo (MB, AcoustID, Shazam, IA) se inicializa con
        reintentos y cae a _ComponenteInactivo si falla, garantizando que
        el pipeline siempre puede arrancar en modo degradado.

    Modos de ejecución (parámetro ``modo``):
      - ``full``: flujo completo (por defecto).
      - ``metadata_only``: omite el pipeline de assets.
      - ``review_only``: reutiliza el directorio de revisión como entrada.
      - ``rebuild_manifests``: regenera manifiestos JSON desde la base de datos.
      - ``audit`` / ``repair``: inspección y reparación de la biblioteca.
      - ``assets_only`` / ``missing_assets_only``: rehidratación de imágenes.
      - ``duplicates_only``: auditoría de duplicados en la BD.
      - ``discography_organize``: reorganización por discografía canónica.
      - ``explain``: muestra el scoring detallado de un archivo específico.

    Side-effects principales de una ejecución ``full``:
      - Archivos aceptados: escritura de tags ID3 + movimiento a biblioteca.
      - Archivos rechazados: copia a cuarentena/revisión.
      - Archivos procesados: registro en directorio de procesados.
      - Sidecars (assets, enrichment, manifiestos): tareas diferidas asíncronas.
      - Logs y reporte JSON: escritos en directorio de logs.

    El pipeline soporta cancelación y pausa a través de ControlEjecucion.
    Si se cancela, se ejecuta rollback de las operaciones materializadas.
    """

    def __init__(
        self,
        directorio_entrada:    Optional[Path] = None,
        directorio_biblioteca: Optional[Path] = None,
        directorio_quarantine: Optional[Path] = None,
        directorio_revision:   Optional[Path] = None,
        directorio_logs:       Optional[Path] = None,
        directorio_procesados: Optional[Path] = None,
        directorio_cache:      Optional[Path] = None,
        directorio_temp:       Optional[Path] = None,
        modo: str = "full",
        explain_target: Optional[str] = None,
        dry_run: bool = False,
        control: Optional[ControlEjecucion] = None,
    ) -> None:
        self._dir_entrada    = directorio_entrada    or _settings.DEFAULT_INPUT_DIR
        self._dir_biblioteca = directorio_biblioteca or _settings.DEFAULT_LIBRARY_DIR
        self._dir_quarantine = directorio_quarantine or _settings.DEFAULT_QUARANTINE_DIR
        self._dir_revision   = directorio_revision   or _settings.DEFAULT_REVIEW_DIR
        self._dir_logs       = directorio_logs       or _settings.DEFAULT_LOGS_DIR
        self._dir_procesados = directorio_procesados or _settings.DEFAULT_PROCESSED_DIR
        self._dir_cache      = directorio_cache      or _settings.DEFAULT_CACHE_DIR
        self._dir_temp       = directorio_temp       or _settings.DEFAULT_TEMP_DIR
        self._modo = modo
        self._explain_target = explain_target
        self._dry_run = dry_run
        self._control = control

        # Componentes — cada uno recibe sus dependencias de forma explicita
        self._cache       = CacheLocal(directorio=self._dir_cache)
        self._mb_client   = self._crear_componente_reintentable(
            "MusicBrainz",
            lambda: ClienteMusicBrainz(cache=self._cache),
            lambda: ClienteMusicBrainz(cache=self._cache),
        )
        self._acoustid    = self._crear_componente_reintentable(
            "AcoustID",
            lambda: ClienteAcoustID(cache=self._cache),
            lambda: ClienteAcoustID(cache=self._cache),
        )
        self._shazam      = self._crear_componente_reintentable(
            "Shazam",
            lambda: ClienteShazam(cache=self._cache),
            lambda: ClienteShazam(cache=self._cache),
        )
        self._ia_client   = self._crear_componente_reintentable(
            "IA",
            ClienteIA,
            ClienteIA,
        )
        self._itunes_client = self._crear_componente_reintentable(
            "iTunes",
            lambda: ClienteItunes(cache=self._cache),
            lambda: ClienteItunes(cache=self._cache),
        )
        self._transcoder = TranscodificadorAudio(self._dir_temp)
        self._cuarentena  = GestorCuarentena(
            directorio_cuarentena=self._dir_quarantine,
            directorio_revision=self._dir_revision,
        )
        self._procesados = GestorProcesados(
            directorio_procesados=self._dir_procesados,
        )
        self._barra: Optional[BarraProgreso] = None
        self._dedupe = GestorDuplicados()
        self._assets = PipelineAssets(_settings.DEFAULT_ASSETS_DIR) if ENABLE_ASSETS_PIPELINE else None
        self._enrichment = EnrichmentPipeline(_settings.DEFAULT_ASSETS_DIR)
        if self._modo == "metadata_only":
            self._assets = None
        if self._modo == "review_only" and self._dir_revision is not None:
            self._dir_entrada = self._dir_revision
        self._manifests = GestorManifests(_settings.DEFAULT_MANIFESTS_DIR)
        self._overrides = MemoriaOverrides()
        self._assets_executor: Optional[_SidecarExecutorDaemon] = None
        self._assets_futures = []
        self._sidecar_lock = threading.RLock()
        self._sidecars_timeout: set[tuple[str, int, str]] = set()
        self._manifests_deferidos: dict[int, tuple[DecisionArchivo, str]] = {}
        self._ops_aplicadas: list[tuple[Path, Path]] = []

    # ------------------------------------------------------------------
    # PUNTO DE ENTRADA
    # ------------------------------------------------------------------

    def ejecutar(self) -> ResultadoEjecucion:
        """
        Punto de entrada principal. Ejecuta el pipeline completo según el modo
        configurado y retorna el ``ResultadoEjecucion`` con contadores y métricas.

        Modos especiales (rebuild_manifests, audit, repair, assets_only, etc.)
        se despachan antes del flujo estándar y retornan un ResultadoEjecucion
        mínimo sin procesar archivos individuales.

        En el flujo estándar:
          1. Descubre archivos de audio en el directorio de entrada.
          2. Procesa cada archivo de forma secuencial (pipeline individual).
          3. Ejecuta segunda y tercera fase de resolución sobre casos pendientes.
          4. Materializa decisiones finales (cuarentena/revisión/procesados).
          5. Espera sidecars asíncronos (assets, enrichment, manifiestos).
          6. Genera métricas, imprime resumen y guarda reporte JSON.

        El bloque ``finally`` garantiza que la barra de progreso, el executor de
        sidecars y el logging se cierran correctamente incluso en caso de excepción.

        Raises:
            No relanza excepciones: cualquier fallo interno se registra y se
            retorna un ResultadoEjecucion parcial.
        """
        if self._modo == "rebuild_manifests":
            print("\n--- Reconstruyendo Manifiestos ---")
            print("Escaneando la base de datos y recreando archivos JSON...")
            res = self._manifests.rebuild()
            print(f"Completado. Pistas reconstruidas: {res.get('tracks_rebuilt', 0)}\n")
            return ResultadoEjecucion(
                timestamp_inicio=datetime.now(timezone.utc).isoformat(),
                timestamp_fin=datetime.now(timezone.utc).isoformat(),
            )
        if self._modo == "audit":
            print("\n--- Auditoría de Biblioteca ---")
            print("Analizando assets, manifiestos y consistencia de archivos...")
            res = DoctorBiblioteca(self._dir_biblioteca, self._dir_procesados).audit()
            
            issues = res.get("issues", [])
            print(f"Total de problemas detectados: {res.get('total_issues', 0)}")
            if issues:
                print("\nDetalle de Problemas:")
                for i, issue in enumerate(issues, 1):
                    print(f"  {i}. [{issue.get('severity', 'info').upper()}] {issue.get('code')}: {issue.get('detail')}")
            print("-" * 31 + "\n")
            
            return ResultadoEjecucion(
                timestamp_inicio=datetime.now(timezone.utc).isoformat(),
                timestamp_fin=datetime.now(timezone.utc).isoformat(),
            )
        if self._modo == "repair":
            print("\n--- Reparación de Biblioteca ---")
            print("Ejecutando rutinas de reparación segura de assets y manifiestos...")
            res = DoctorBiblioteca(self._dir_biblioteca, self._dir_procesados).repair(dry_run=self._dry_run)
            
            actions = res.get("actions", [])
            print(f"Total de acciones tomadas: {res.get('total_actions', 0)} (Dry Run: {res.get('dry_run', True)})")
            if actions:
                print("\nDetalle de Acciones:")
                for i, action in enumerate(actions, 1):
                    print(f"  {i}. [{action.get('action')}] -> {action.get('path')}")
            print("-" * 32 + "\n")
            
            return ResultadoEjecucion(
                timestamp_inicio=datetime.now(timezone.utc).isoformat(),
                timestamp_fin=datetime.now(timezone.utc).isoformat(),
            )
        if self._modo in {"assets_only", "missing_assets_only"}:
            print("\n--- Procesamiento de Assets ---")
            print(f"Modo: {'Solo Faltantes' if self._modo == 'missing_assets_only' else 'Todos los Assets'}")
            self._rehidratar_assets(only_missing=self._modo == "missing_assets_only")
            return ResultadoEjecucion(
                timestamp_inicio=datetime.now(timezone.utc).isoformat(),
                timestamp_fin=datetime.now(timezone.utc).isoformat(),
            )
        if self._modo == "duplicates_only":
            self._auditar_duplicados_existentes()
            return ResultadoEjecucion(
                timestamp_inicio=datetime.now(timezone.utc).isoformat(),
                timestamp_fin=datetime.now(timezone.utc).isoformat(),
            )
        if self._modo == "discography_organize":
            print("\n--- Reorganización por Discografía ---")
            print("Calculando discografías canónicas y organizando carpetas...")
            resumen = OrganizadorDiscografias(
                manifests_dir=_settings.DEFAULT_MANIFESTS_DIR,
                biblioteca_dir=self._dir_biblioteca,
                ia_client=self._ia_client,
            ).ejecutar(dry_run=self._dry_run)
            print("\nResultados:")
            for k, v in resumen.items():
                print(f"  - {k}: {v}")
            print("-" * 38 + "\n")
            
            return ResultadoEjecucion(
                timestamp_inicio=datetime.now(timezone.utc).isoformat(),
                timestamp_fin=datetime.now(timezone.utc).isoformat(),
            )
        if self._modo == "explain" and self._explain_target:
            self._imprimir_explain(self._explain_target)
            return ResultadoEjecucion(
                timestamp_inicio=datetime.now(timezone.utc).isoformat(),
                timestamp_fin=datetime.now(timezone.utc).isoformat(),
            )
        inicializar_logging(self._dir_logs)
        try:
            _log.info("=" * 60)
            _log.info(f"INICIO DE EJECUCION — {CLI_BANNER}")
            _log.info(f"Entrada    : {self._dir_entrada}")
            _log.info(f"Biblioteca : {self._dir_biblioteca}")
            _log.info(f"Logs       : {self._dir_logs}")
            _log.info(f"Procesados : {self._dir_procesados}")
            _log.info(f"Cache      : {self._dir_cache}")
            _log.info(f"Temp       : {self._dir_temp}")
            _log.info(f"AcoustID   : {'activo' if self._acoustid.activo else 'inactivo'}")
            _log.info(f"Shazam     : {'activo' if self._shazam.activo else 'inactivo'}")
            _log.info(f"IA         : {'activa' if self._ia_client.activo else 'inactiva'}")
            _log.info(f"Modo       : {self._modo}")
            _log.info(f"Dry-run    : {'si' if self._dry_run else 'no'}")
            _log.info(f"Dedupe     : {'activo' if ENABLE_DEDUPLICATION else 'inactivo'}")
            _log.info(f"Dedupe sem.: {'activo' if ENABLE_SEMANTIC_DEDUPLICATION else 'inactivo'}")
            _log.info(f"Assets     : {'activo' if self._assets is not None else 'inactivo'}")
            _log.info(f"Enrichment : {'activo' if self._enrichment and self._enrichment.active else 'inactivo'}")
            _log.info("=" * 60)

            resultado = ResultadoEjecucion(
                timestamp_inicio=datetime.now(timezone.utc).isoformat(),
                directorio_entrada=str(self._dir_entrada),
            )
            tiempo_inicio = time.time()

            # --- Descubrimiento ---
            self._set_phase("discovery", "Descubriendo archivos", current_task="descubrimiento")
            try:
                archivos = descubrir_archivos(self._dir_entrada)
            except (FileNotFoundError, NotADirectoryError) as e:
                _log.error(f"Error en descubrimiento: {e}")
                resultado.timestamp_fin = datetime.now(timezone.utc).isoformat()
                if self._control:
                    self._control.cerrar("error")
                return resultado

            resultado.total_descubiertos = len(archivos)
            if self._control:
                self._control.checkpoint(total_descubiertos=len(archivos), procesados=0, current_stage="descubrimiento")
            _log.info(f"Descubiertos: {len(archivos)} archivos de audio soportados")

            if not archivos:
                _log.warning("No se encontraron archivos de audio soportados en la ruta indicada.")
                resultado.timestamp_fin = datetime.now(timezone.utc).isoformat()
                if self._control:
                    self._control.cerrar("completed")
                return resultado

            # --- Iniciar barra de progreso ---
            if self._barra is None:
                self._barra = BarraProgreso(total_archivos=len(archivos))
            elif hasattr(self._barra, "set_total_archivos"):
                self._barra.set_total_archivos(len(archivos))
            self._barra.iniciar()
            self._set_phase(
                "file_processing",
                "Procesando archivos",
                total=len(archivos),
                current=0,
                current_task="pipeline_individual",
            )
            if not self._ia_client.activo:
                self._barra.mensaje(
                    "Desempate IA inactivo: se usara decision determinista/fallbacks.",
                    nivel="warn",
                )

            # --- Procesar cada archivo ---
            decisiones: list[DecisionArchivo] = []
            for indice, archivo in enumerate(archivos, start=1):
                if self._control:
                    self._control.esperar_si_pausado()
                    if self._control.cancelado():
                        _log.warning("Cancelacion solicitada: se detiene la ejecucion y se revierten cambios aplicados.")
                        break
                self._update_phase(
                    current=indice - 1,
                    total=len(archivos),
                    current_item=archivo.nombre_archivo,
                    current_task="pipeline_individual",
                )
                decisiones.append(self._procesar_archivo(archivo, resultado))
                self._update_phase(
                    current=len(decisiones),
                    total=len(archivos),
                    current_item=archivo.nombre_archivo,
                    current_task="pipeline_individual",
                )
                if self._control:
                    self._control.checkpoint(
                        procesados=len(decisiones),
                        current_file=archivo.nombre_archivo,
                        current_stage="pipeline_individual",
                        counters=self._counters_resultado(resultado),
                    )

            if self._control and self._control.cancelado():
                self._rollback_cambios()
                resultado.timestamp_fin = datetime.now(timezone.utc).isoformat()
                if self._control:
                    self._control.cerrar("cancelled")
                return resultado

            # --- Segunda fase dirigida: solo casos revisión/cuarentena elegibles ---
            self._set_phase(
                "phase_2",
                "Fase 2 - resolucion dirigida" if ENABLE_SECOND_STAGE_RESOLUTION else "Fase 2 desactivada",
                total=len(decisiones),
                current=0,
                current_task="reevaluacion",
            )
            if self._barra:
                self._barra.mensaje(
                    "Iniciando fase 2 (resolucion dirigida)..."
                    if ENABLE_SECOND_STAGE_RESOLUTION
                    else "Fase 2 desactivada por configuracion.",
                    nivel="info",
                )
            decisiones = self._ejecutar_segunda_fase(decisiones, resultado)
            self._set_phase(
                "phase_3",
                "Fase 3 - ultima pasada conservadora" if ENABLE_THIRD_STAGE_RESOLUTION else "Fase 3 desactivada",
                total=len(decisiones),
                current=0,
                current_task="corroboracion",
            )
            if self._barra:
                self._barra.mensaje(
                    "Iniciando fase 3 (ultima pasada conservadora)..."
                    if ENABLE_THIRD_STAGE_RESOLUTION
                    else "Fase 3 desactivada por configuracion.",
                    nivel="info",
                )
            decisiones = self._ejecutar_tercera_fase(decisiones, resultado)

            # Materializar revisión/cuarentena final y consolidar contadores finales
            self._set_phase(
                "materialization",
                "Materializando resultados",
                total=len(decisiones),
                current=0,
                current_task="movimientos",
            )
            self._aplicar_decisiones_finales(decisiones, resultado)
            if self._control and self._control.cancelado():
                self._rollback_cambios()
                resultado.timestamp_fin = datetime.now(timezone.utc).isoformat()
                self._control.cerrar("cancelled")
                return resultado
            self._set_phase(
                "sidecars",
                "Finalizando assets, letras y manifiestos",
                total=len(self._assets_futures) + len(self._manifests_deferidos),
                current=0,
                current_task="sidecars",
            )
            self._esperar_assets_pendientes()

            # --- Metricas finales ---
            self._set_phase("finalizing", "Generando resumen final", current_task="reportes")
            tiempo_total = time.time() - tiempo_inicio
            resultado.timestamp_fin = datetime.now(timezone.utc).isoformat()
            resultado.duracion_total_seg = round(tiempo_total, 2)

            procesados = resultado.total_procesados()
            if procesados > 0:
                resultado.tiempo_promedio_seg = round(tiempo_total / procesados, 3)

            stats_mb = self._mb_client.estadisticas
            resultado.consultas_mb = stats_mb.get("total_consultas", 0)
            resultado.cache_hits = stats_mb.get("hits", 0)
            resultado.reintentos_mb = stats_mb.get("total_reintentos", 0)

            imprimir_resumen_consola(resultado)
            ruta_reporte = guardar_reporte(resultado, self._dir_logs)
            _log.info(f"Reporte final guardado en: {ruta_reporte}")

            registrar_evento("ejecucion_completada", datos={
                "total":            resultado.total_descubiertos,
                "aceptados":        resultado.total_aceptados,
                "duracion_seg":     resultado.duracion_total_seg,
                "shazam_ids":       resultado.total_identificados_shazam,
                "acoustid_ids":     resultado.total_identificados_acoustid,
                "ia_desempates":    resultado.total_desempatados_ia,
                "isrc_usados":      resultado.total_isrc_usados,
            })
            if self._control:
                self._control.cerrar("completed")
            return resultado
        finally:
            if self._barra:
                self._barra.finalizar()
                self._barra = None
            self._cerrar_executor_assets()
            cerrar_logging()

    def _rehidratar_assets(self, only_missing: bool) -> None:
        """
        Recorre los manifiestos JSON de la biblioteca y descarga/verifica assets
        (portadas HD, fotos de artista) para pistas ya catalogadas.

        Se usa cuando el pipeline de assets estuvo desactivado durante la
        catalogación original o cuando las imágenes son de baja calidad.

        Si ``only_missing=True``, omite las pistas que ya tienen album y artista HD.
        Los assets se procesan en línea (no en sidecar) porque este modo es el
        único trabajo que se realiza en la ejecución.

        Side-effects: descarga de imágenes a disco y actualización de manifiestos.
        """
        if self._assets is None:
            return
        from domain.models import CandidatoMB

        procesados = 0
        omitidos = 0
        
        manifests_files = list(self._manifests._tracks.glob("*.json"))  # noqa: SLF001
        total_archivos = len(manifests_files)
        
        if total_archivos == 0:
            print("No se encontraron manifiestos JSON. La biblioteca está vacía.")
            return

        print(f"Se escanearán {total_archivos} manifiestos para hidratación de assets...")

        for i, mf in enumerate(manifests_files, 1):
            if i % 10 == 0 or i == total_archivos:
                print(f"Progreso: {i}/{total_archivos} (Procesados: {procesados}, Omitidos: {omitidos})", end="\r", flush=True)
                
            try:
                data = json.loads(mf.read_text(encoding="utf-8"))
            except Exception:
                continue
            assets = data.get("assets") or {}
            album_assets = assets.get("album") if isinstance(assets.get("album"), dict) else {}
            artist_assets = assets.get("artist") if isinstance(assets.get("artist"), dict) else {}
            if only_missing and album_assets.get("selected_hd") and artist_assets.get("selected_hd"):
                omitidos += 1
                continue
            ruta = Path(data.get("ruta_actual") or "")
            if not ruta.exists():
                continue
            decision = DecisionArchivo(
                tipo=DecisionTipo.ACEPTADO,
                archivo=ArchivoAudio(ruta_original=ruta),
                candidato_elegido=CandidatoMB(
                    recording_id=str(data.get("recording_mbid") or ""),
                    release_id=str(data.get("release_mbid") or ""),
                    release_group_id=str(data.get("release_group_mbid") or ""),
                    titulo_oficial=str(data.get("canonical_title") or ""),
                    artista_principal=str(data.get("canonical_artist") or ""),
                    album_oficial=str(data.get("album") or ""),
                ),
                puntaje_maximo=float(data.get("score_final") or 0.0),
            )
            decision.ruta_destino = ruta
            self._assets.procesar(decision)
            try:
                self._manifests.escribir_decision(decision)
            except Exception as e:
                _log.debug(f"No se pudo refrescar manifest canonical tras assets_only para {ruta.name}: {e}")
            procesados += 1
            
        print("\n\n--- Resumen de Rehidratación ---")
        print(f"Archivos escaneados: {total_archivos}")
        print(f"Assets descargados/verificados: {procesados}")
        print(f"Omitidos por ya estar completos: {omitidos}")
        print("-" * 32 + "\n")
        
        _log.info(
            f"Rehidratacion assets completed (only_missing={only_missing}): "
            f"procesados={procesados} omitidos={omitidos}"
        )

    def _auditar_duplicados_existentes(self) -> None:
        """
        Consulta la base de datos para detectar pistas en biblioteca con la misma
        clave (recording_id, ISRC o titulo+artista) y muestra los grupos con más
        de una entrada.

        No modifica ningún archivo. Requiere que la BD esté inicializada.
        Informa el error si la BD no está disponible en lugar de lanzar excepción.
        """
        try:
            from db.conexion import obtener_filas
            rows = obtener_filas(
                """
                SELECT COALESCE(mb_recording_id, isrc, titulo || '::' || artista_nombre) AS k, COUNT(*) AS n
                FROM pistas
                WHERE estado='biblioteca'
                GROUP BY k
                HAVING COUNT(*) > 1
                ORDER BY n DESC
                """
            )
            print("\n--- Auditoría de Duplicados en Biblioteca ---")
            print(f"Total de grupos de duplicados detectados: {len(rows)}")
            if rows:
                print("\nTop 50 grupos con más duplicados:")
                for i, row in enumerate(rows[:50], 1):
                    print(f"  {i}. Clave: {row['k']} -> {row['n']} pistas")
            print("-" * 45 + "\n")
        except Exception as e:
            print(f"\nError en auditoría de duplicados: duplicates-only requiere DB inicializada: {e}\n")

    def _imprimir_explain(self, target: str) -> None:
        """
        Muestra en consola el desglose completo de scoring y decisión para un
        archivo ya procesado, identificado por nombre de archivo o recording_id.

        Útil para depurar por qué un archivo fue aceptado, rechazado o revisado,
        sin necesidad de reprocesarlo.
        """
        data = self._manifests.explicar(target)
        if not data:
            print("\n--- Explain ---")
            print(f"Error: Sin explain disponible para el target '{target}'.\n")
            return
        
        print("\n" + "=" * 50)
        print("EXPLAIN RESULT")
        print("=" * 50)
        print(f"Track ID:        {data.get('track_id', 'N/A')}")
        print(f"Decision:        {data.get('decision', 'N/A')}")
        print(f"Razon:           {data.get('decision_reason', 'N/A')}")
        print(f"Score Final:     {data.get('score_final', 0):.4f}")
        print(f"Provisional:     {'Sí' if data.get('provisional') else 'No'}")
        
        if data.get("score_breakdown"):
            print("\nDesglose de Score:")
            for k, v in data["score_breakdown"].items():
                print(f"  - {k}: {v}")
                
        if data.get("sources"):
            print("\nFuentes:")
            for k, v in data["sources"].items():
                print(f"  - {k}: {v}")
                
        if data.get("duplicate"):
            print(f"\nDuplicado:       {data['duplicate']}")
            
        if data.get("override"):
            print(f"\nOverride:        {data['override']}")
            
        if data.get("explain"):
            print("\nDetalle (explain):")
            print(f"  {data['explain']}")
            
        print("=" * 50 + "\n")

    # ------------------------------------------------------------------
    # PROCESAMIENTO DE UN ARCHIVO
    # ------------------------------------------------------------------

    def _procesar_archivo(
        self, archivo: ArchivoAudio, resultado: ResultadoEjecucion
    ) -> DecisionArchivo:
        """
        Wrapper de seguridad sobre ``_pipeline_individual``.

        Captura cualquier excepción no controlada para evitar que un archivo
        corrupto o un bug puntual detenga el procesamiento del lote completo.
        En caso de excepción, el archivo se envía a cuarentena con
        CuarentenaCausa.ERROR_INESPERADO y el error queda registrado en log.
        """
        nombre = archivo.nombre_archivo
        log_inicio_archivo(nombre)
        inicio_archivo = time.perf_counter()

        try:
            decision = self._pipeline_individual(archivo, resultado)
        except Exception as e:
            _log.error(
                f"Excepcion no capturada procesando {nombre}: {e}", exc_info=True
            )
            log_error_archivo(nombre, "pipeline_general", str(e))
            archivo.agregar_error(f"Excepcion: {e}")
            decision = DecisionArchivo(
                tipo=DecisionTipo.ERROR,
                archivo=archivo,
                causa_cuarentena=CuarentenaCausa.ERROR_INESPERADO,
                mensaje_decision=f"Excepcion inesperada: {e}",
            )

        log_decision(
            nombre, decision.tipo.value, decision.puntaje_maximo, decision.mensaje_decision
        )

        if self._barra:
            self._barra.registrar_resultado(
                decision.tipo.value,
                duracion_archivo_seg=(time.perf_counter() - inicio_archivo),
            )
        return decision

    def _pipeline_individual(
        self, archivo: ArchivoAudio, resultado: ResultadoEjecucion
    ) -> DecisionArchivo:
        """
        Ejecuta las etapas del pipeline para un único archivo de audio.

        Retorna anticipado en la primera etapa que descarte el archivo, evitando
        trabajo innecesario en etapas posteriores. Las etapas que producen
        retorno anticipado son:
          - Cancelación solicitada por el usuario.
          - Ya procesado (marcador TXXX en tags).
          - Transcodificación fallida (formatos no MP3).
          - Validación técnica fallida (tamaño, duración, bitrate, corrupción).
          - Duplicado exacto por hash SHA256.
          - Normalización fallida (sin artista ni título usable).
          - Override manual inválido.

        Las etapas de identificación externa (AcoustID + Shazam) se ejecutan
        en paralelo con ThreadPoolExecutor(max_workers=2) para reducir latencia.

        ``etapas_ms`` acumula el tiempo en milisegundos de cada etapa para
        el registro de auditoría del evento final.
        """
        nombre = archivo.nombre_archivo
        etapas_ms: dict[str, int] = {}
        if self._control:
            self._control.esperar_si_pausado()
            if self._control.cancelado():
                return DecisionArchivo(
                    tipo=DecisionTipo.OMITIDO,
                    archivo=archivo,
                    mensaje_decision="Cancelado por usuario antes de procesar archivo",
                )

        def _medir_etapa(etapa: str, inicio: float) -> None:
            etapas_ms[etapa] = int((time.perf_counter() - inicio) * 1000)

        # === ETAPA 1: Ya procesado? ===
        t0 = time.perf_counter()
        if SKIP_ALREADY_PROCESSED and self._ya_fue_procesado(archivo):
            _medir_etapa("chequeo_ya_procesado", t0)
            _log.debug(f"Omitido (ya procesado): {nombre}")
            if self._barra:
                self._barra.actualizar_archivo(nombre, "omitido")
            return DecisionArchivo(
                tipo=DecisionTipo.OMITIDO,
                archivo=archivo,
                mensaje_decision="Archivo ya procesado en ejecucion anterior",
            )

        # === ETAPA 1.5: Transcodificacion conservadora a MP3 (si aplica) ===
        t0 = time.perf_counter()
        if archivo.ruta_original.suffix.lower() != ".mp3":
            trans = self._transcoder.convertir_a_mp3(archivo.ruta_original)
            if not trans.exito or not trans.ruta_salida:
                if self._barra:
                    self._barra.mensaje(
                        f"Transcodificacion omitida para {nombre}: {trans.error}",
                        nivel="warn",
                    )
                decision = DecisionArchivo(
                    tipo=DecisionTipo.CUARENTENA,
                    archivo=archivo,
                    causa_cuarentena=CuarentenaCausa.ARCHIVO_ILEGIBLE,
                    mensaje_decision=f"Transcodificacion fallida ({trans.formato_entrada}): {trans.error}",
                )
                self._registrar_evento_archivo(nombre, decision, etapas_ms, archivo)
                return decision
            archivo.ruta_fuente_original = archivo.ruta_original
            archivo.ruta_original = trans.ruta_salida
            archivo.agregar_advertencia(
                f"Transcodificado {trans.formato_entrada}->mp3 para pipeline principal"
            )
        _medir_etapa("transcodificacion", t0)

        # === ETAPA 2: Validacion tecnica ===
        if self._barra:
            self._barra.actualizar_archivo(nombre, "validando")
        if self._control:
            self._control.checkpoint(current_file=nombre, current_stage="validando")
        archivo.etapa_actual = "validacion"

        t0 = time.perf_counter()
        es_valido, causa_cuarentena = validar_archivo(archivo)
        _medir_etapa("validacion_tecnica", t0)
        if not es_valido:
            decision = DecisionArchivo(
                tipo=DecisionTipo.CUARENTENA,
                archivo=archivo,
                causa_cuarentena=causa_cuarentena,
                mensaje_decision=(
                    f"Fallo validacion: "
                    f"{causa_cuarentena.value if causa_cuarentena else 'desconocido'}"
                ),
            )
            self._registrar_evento_archivo(nombre, decision, etapas_ms, archivo)
            return decision

        # === ETAPA 2.5: Deteccion de duplicado exacto por hash ===
        if ENABLE_DEDUPLICATION:
            duplicado = self._dedupe.registrar_hash(archivo)
            if duplicado is not None:
                decision = DecisionArchivo(
                    tipo=DecisionTipo.DUPLICADO_EXACTO,
                    archivo=archivo,
                    mensaje_decision=(
                        f"Duplicado detectado ({duplicado.tipo}) de {duplicado.referencia}"
                    ),
                )
                decision.info_duplicado = {
                    "tipo": duplicado.tipo,
                    "referencia": duplicado.referencia,
                    "policy": DUPLICATE_POLICY,
                }
                self._registrar_evento_archivo(nombre, decision, etapas_ms, archivo)
                return decision

        # === ETAPA 3-4: Identificacion externa paralela ===
        if self._acoustid.activo or self._shazam.activo:
            if self._barra:
                self._barra.actualizar_archivo(nombre, "identificacion_externa")
            if self._control:
                self._control.checkpoint(current_file=nombre, current_stage="identificacion_externa")
            archivo.etapa_actual = "identificacion_externa"
            duracion = archivo.metadata_cruda.duracion_seg if archivo.metadata_cruda else None

            def _acoustid_job():
                t_local = time.perf_counter()
                data = self._acoustid.identificar(
                    ruta_archivo=archivo.ruta_original,
                    hash_archivo=archivo.hash_sha256,
                )
                return data, int((time.perf_counter() - t_local) * 1000)

            def _shazam_job():
                t_local = time.perf_counter()
                data = self._shazam.identificar(
                    ruta_archivo=archivo.ruta_original,
                    duracion_seg=duracion,
                    hash_archivo=archivo.hash_sha256,
                )
                return data, int((time.perf_counter() - t_local) * 1000)

            futuros = {}
            with ThreadPoolExecutor(max_workers=2) as executor:
                if self._acoustid.activo:
                    futuros["acoustid"] = executor.submit(_acoustid_job)
                if self._shazam.activo:
                    futuros["shazam"] = executor.submit(_shazam_job)

                if "acoustid" in futuros:
                    data_acoustid, ms_acoustid = futuros["acoustid"].result()
                    archivo.resultado_acoustid = data_acoustid
                    etapas_ms["acoustid"] = ms_acoustid
                    if data_acoustid.recording_ids:
                        resultado.total_identificados_acoustid += 1

                if "shazam" in futuros:
                    data_shazam, ms_shazam = futuros["shazam"].result()
                    archivo.resultado_shazam = data_shazam
                    etapas_ms["shazam"] = ms_shazam
                    if data_shazam.identificado:
                        resultado.total_identificados_shazam += 1
                        if data_shazam.isrc:
                            resultado.total_isrc_usados += 1

        # === ETAPA 5: Normalizacion y fusion de evidencias ===
        if self._barra:
            self._barra.actualizar_archivo(nombre, "normalizando")
        if self._control:
            self._control.checkpoint(current_file=nombre, current_stage="normalizando")
        archivo.etapa_actual = "normalizacion"

        t0 = time.perf_counter()
        tiene_info, causa_cuarentena = normalizar_metadata(archivo)
        _medir_etapa("normalizacion", t0)
        if not tiene_info:
            decision = DecisionArchivo(
                tipo=DecisionTipo.CUARENTENA,
                archivo=archivo,
                causa_cuarentena=causa_cuarentena,
                mensaje_decision="Metadata insuficiente para realizar matching",
            )
            self._registrar_evento_archivo(nombre, decision, etapas_ms, archivo)
            return decision

        override = self._overrides.buscar_para(archivo, archivo.metadata_norm)
        if override is not None:
            candidato_override = self._overrides.candidato_desde_payload(override.payload)
            if candidato_override is None:
                decision = DecisionArchivo(
                    tipo=DecisionTipo.REVISION,
                    archivo=archivo,
                    causa_revision=RevisionCausa.CANDIDATOS_AMBIGUOS,
                    mensaje_decision=f"Override inválido ({override.match_type})",
                )
                decision.override_aplicado = {
                    "match_type": override.match_type,
                    "key": override.key,
                    "reason": override.reason,
                    "source": override.source,
                    "payload": override.payload,
                    "valid": False,
                }
                self._registrar_evento_archivo(nombre, decision, etapas_ms, archivo)
                return decision
            decision = DecisionArchivo(
                tipo=DecisionTipo.ACEPTADO,
                archivo=archivo,
                candidato_elegido=candidato_override,
                mensaje_decision=f"Override aplicado ({override.match_type})",
                puntaje_maximo=1.0,
            )
            decision.override_aplicado = {
                "match_type": override.match_type,
                "key": override.key,
                "reason": override.reason,
                "source": override.source,
                "payload": override.payload,
                "valid": True,
            }
            decision.esquema_explicacion = {
                "signals": ["override"],
                "override": decision.override_aplicado,
            }
            if self._barra:
                self._barra.actualizar_archivo(nombre, "escribiendo")
            t0 = time.perf_counter()
            exito, causa_escritura, msg_escritura = escribir_y_mover(
                decision,
                directorio_biblioteca=self._dir_biblioteca,
                directorio_temp=self._dir_temp,
            )
            _medir_etapa("escritura_y_movimiento", t0)
            if not exito:
                decision.tipo = DecisionTipo.CUARENTENA
                decision.causa_cuarentena = causa_escritura
                decision.mensaje_decision = f"Override aplicado pero escritura falló: {msg_escritura}"
            else:
                self._post_aceptacion_materializada(decision, nombre)
            self._registrar_evento_archivo(nombre, decision, etapas_ms, archivo)
            return decision

        # === ETAPA 6: Consulta a MusicBrainz ===
        if self._barra:
            self._barra.actualizar_archivo(nombre, "consultando MB")
        if self._control:
            self._control.checkpoint(current_file=nombre, current_stage="consultando_mb")
        archivo.etapa_actual = "consulta_mb"

        recording_ids_acoustid = (
            archivo.resultado_acoustid.recording_ids
            if archivo.resultado_acoustid else None
        )
        t0 = time.perf_counter()
        candidatos = self._mb_client.buscar_candidatos(
            archivo.metadata_norm,
            recording_ids_acoustid=recording_ids_acoustid,
        )
        _medir_etapa("musicbrainz", t0)

        # === ETAPA 7: Scoring y decision (con desempate IA) ===
        if self._barra:
            self._barra.actualizar_archivo(nombre, "evaluando")
        if self._control:
            self._control.checkpoint(current_file=nombre, current_stage="evaluando")
        archivo.etapa_actual = "matching"

        t0 = time.perf_counter()
        decision = evaluar_candidatos(
            archivo, candidatos, cliente_ia=self._ia_client
        )
        _medir_etapa("scoring", t0)

        # Contabilizar si la IA intervino
        if decision.decision_ia and decision.decision_ia.valida:
            resultado.total_desempatados_ia += 1
        top_candidatos = sorted(candidatos, key=lambda c: c.puntaje_total, reverse=True)[:3]
        decision.esquema_explicacion = {
            "signals": [f.value for f in decision.fuentes_usadas],
            "top_candidates": [
                {
                    "recording_id": c.recording_id,
                    "release_id": c.release_id,
                    "title": c.titulo_oficial,
                    "artist": c.artista_principal,
                    "score": round(c.puntaje_total, 4),
                    "breakdown": c.puntaje_detalle,
                    "penalties": c.penalizaciones,
                }
                for c in top_candidatos
            ],
            "winner": {
                "recording_id": decision.candidato_elegido.recording_id if decision.candidato_elegido else None,
                "release_id": decision.candidato_elegido.release_id if decision.candidato_elegido else None,
                "score": round(decision.puntaje_maximo, 4),
            },
            "second_stage": None,
        }

        # === ETAPA 8: Escribir y mover si fue ACEPTADO o ACEPTADO_PROVISIONAL ===
        if decision.tipo in (DecisionTipo.ACEPTADO, DecisionTipo.ACEPTADO_PROVISIONAL):
            if ENABLE_SEMANTIC_DEDUPLICATION:
                duplicado_sem = self._dedupe.detectar_duplicado_identidad(decision)
                if duplicado_sem is not None:
                    tipo_dup = (
                        DecisionTipo.DUPLICADO_MEJORABLE
                        if duplicado_sem.tipo == "duplicado_mejorable"
                        else DecisionTipo.DUPLICADO_SEMANTICO
                    )
                    promovido_a_aceptado = (
                        DUPLICATE_POLICY in {"replace_if_better", "prefer_new_if_quality_higher"}
                        and tipo_dup == DecisionTipo.DUPLICADO_MEJORABLE
                    )
                    if promovido_a_aceptado:
                        tipo_dup = decision.tipo
                    # Antes este reconstruía el `DecisionArchivo` desde cero
                    # perdiendo `candidato_elegido` y `puntaje_maximo`. Eso
                    # rompía el writer cuando el duplicado se promovía a
                    # ACEPTADO bajo política `replace_if_better`: la decisión
                    # llegaba al writer sin candidato y todo terminaba en
                    # cuarentena con "Decision no escribible: aceptado".
                    # Conservamos los datos críticos del candidato original.
                    candidato_previo = decision.candidato_elegido
                    puntaje_previo = decision.puntaje_maximo
                    mensaje_dup = f"Duplicado semantico detectado: {duplicado_sem.referencia}"
                    decision = DecisionArchivo(
                        tipo=tipo_dup,
                        archivo=archivo,
                        candidato_elegido=candidato_previo if promovido_a_aceptado else None,
                        puntaje_maximo=puntaje_previo if promovido_a_aceptado else 0.0,
                        mensaje_decision=mensaje_dup,
                    )
                    decision.info_duplicado = {
                        "tipo": duplicado_sem.tipo,
                        "referencia": duplicado_sem.referencia,
                        "policy": DUPLICATE_POLICY,
                    }
                    if decision.tipo in (DecisionTipo.DUPLICADO_SEMANTICO, DecisionTipo.DUPLICADO_MEJORABLE):
                        self._registrar_evento_archivo(nombre, decision, etapas_ms, archivo)
                        return decision

            if self._barra:
                self._barra.actualizar_archivo(nombre, "escribiendo")
            archivo.etapa_actual = "escritura"

            t0 = time.perf_counter()
            exito, causa_escritura, msg_escritura = escribir_y_mover(
                decision,
                directorio_biblioteca=self._dir_biblioteca,
                directorio_temp=self._dir_temp,
            )
            _medir_etapa("escritura_y_movimiento", t0)
            if not exito:
                _log.warning(f"Escritura fallida para {nombre}: {msg_escritura}")
                decision.tipo             = DecisionTipo.CUARENTENA
                decision.causa_cuarentena = causa_escritura
                decision.mensaje_decision = f"Escritura fallida: {msg_escritura}"
            else:
                self._post_aceptacion_materializada(decision, nombre)

        archivo.etapa_actual = "completado"
        self._registrar_evento_archivo(nombre, decision, etapas_ms, archivo)
        return decision

    def _ejecutar_segunda_fase(
        self,
        decisiones: list[DecisionArchivo],
        resultado: ResultadoEjecucion,
    ) -> list[DecisionArchivo]:
        """
        Delega en SegundaFaseResolucion los archivos en revisión/cuarentena
        elegibles para un segundo intento de identificación.

        La segunda fase usa estrategias alternativas de búsqueda en MusicBrainz
        (desambiguación, búsqueda por alias, relajación de filtros) sobre los casos
        que no superaron el umbral en la primera pasada.

        Actualiza los contadores de ``resultado`` con las métricas de la fase y
        programa sidecars/manifiestos para los archivos que fueron promovidos a
        ACEPTADO en esta fase mediante ``_cerrar_promociones_de_fase``.
        """
        resultado.total_revision_inicial = sum(1 for d in decisiones if d.tipo == DecisionTipo.REVISION)
        resultado.total_cuarentena_inicial = sum(1 for d in decisiones if d.tipo == DecisionTipo.CUARENTENA)
        tipos_entrada = {id(d): d.tipo for d in decisiones}

        resolver = SegundaFaseResolucion(
            mb_client=self._mb_client,
            ia_activa=self._ia_client.activo,
            directorio_biblioteca=self._dir_biblioteca,
            directorio_temp=self._dir_temp,
            barra=self._barra,
            control=self._control,
        )
        decisiones_finales, resumen = resolver.procesar(decisiones)

        resultado.segunda_fase_habilitada = resumen.habilitada
        resultado.segunda_fase_elegibles = resumen.elegibles
        resultado.segunda_fase_excluidos = resumen.excluidos
        resultado.segunda_fase_resueltos = resumen.resueltos
        resultado.segunda_fase_duracion_seg = resumen.duracion_seg

        if self._barra and resumen.habilitada:
            self._barra.mensaje(
                "2ª fase: "
                f"elegibles={resumen.elegibles} | excluidos={resumen.excluidos} | "
                f"resueltos={resumen.resueltos} | t={resumen.duracion_seg:.2f}s",
                nivel="info",
            )

        self._cerrar_promociones_de_fase(decisiones_finales, tipos_entrada, "fase_2")
        return decisiones_finales

    def _aplicar_decisiones_finales(
        self,
        decisiones: list[DecisionArchivo],
        resultado: ResultadoEjecucion,
    ) -> None:
        """
        Materializa las decisiones finales de todas las etapas de resolución:
          - CUARENTENA / REVISION / ERROR → GestorCuarentena mueve el archivo.
          - ACEPTADO / ACEPTADO_PROVISIONAL / OMITIDO / DUPLICADO → GestorProcesados
            archiva la ruta original y registra la operación para rollback.

        Los contadores de ``resultado`` se reinician desde cero antes de iterar
        para evitar doble conteo entre la primera pasada y las fases 2/3.

        Si el archivo fue transcodificado desde un formato no-MP3, el temporal
        MP3 generado se elimina aquí (la fuente original no se toca nunca).

        Side-effects: movimiento de archivos en disco, actualización de contadores.
        """
        # reiniciar contadores finales para evitar doble conteo inicial
        resultado.total_aceptados = 0
        resultado.total_aceptados_provisional = 0
        resultado.total_revision = 0
        resultado.total_cuarentena = 0
        resultado.total_duplicado_exacto = 0
        resultado.total_duplicado_semantico = 0
        resultado.total_duplicado_mejorable = 0
        resultado.total_omitidos = 0
        resultado.total_errores = 0
        resultado.archivos_aceptados.clear()
        resultado.archivos_revision.clear()
        resultado.archivos_cuarentena.clear()
        resultado.archivos_error.clear()

        for indice, decision in enumerate(decisiones, start=1):
            if self._control:
                self._control.esperar_si_pausado()
                if self._control.cancelado():
                    break
            self._update_phase(
                current=indice,
                total=len(decisiones),
                current_item=decision.archivo.nombre_archivo,
                current_task="materializacion",
            )
            ruta_convertida = (
                decision.archivo.ruta_original
                if decision.archivo.ruta_fuente_original is not None
                else None
            )
            ruta_entrada = decision.archivo.ruta_entrada
            decision.archivo.ruta_original = ruta_entrada
            if decision.tipo in (DecisionTipo.CUARENTENA, DecisionTipo.REVISION, DecisionTipo.ERROR):
                ruta_mover = self._cuarentena.procesar_decision(decision)
                if ruta_mover:
                    self._registrar_operacion_aplicada(ruta_entrada, ruta_mover)
            elif decision.tipo in (
                DecisionTipo.ACEPTADO,
                DecisionTipo.ACEPTADO_PROVISIONAL,
                DecisionTipo.OMITIDO,
                DecisionTipo.DUPLICADO_EXACTO,
                DecisionTipo.DUPLICADO_SEMANTICO,
                DecisionTipo.DUPLICADO_MEJORABLE,
            ):
                ruta_archivada = self._procesados.archivar(decision.archivo.ruta_original, decision.tipo)
                if ruta_archivada:
                    self._registrar_operacion_aplicada(ruta_entrada, ruta_archivada)
                if decision.ruta_destino and decision.ruta_destino.exists():
                    self._registrar_operacion_aplicada(ruta_entrada, decision.ruta_destino)
            if ruta_convertida and ruta_convertida.exists():
                try:
                    ruta_convertida.unlink()
                except OSError:
                    _log.debug(f"No se pudo eliminar temporal transcodificado: {ruta_convertida}")
            self._actualizar_resultado(resultado, decision)
            if self._control:
                self._control.checkpoint(
                    current_file=decision.archivo.nombre_archivo,
                    current_stage="materializacion",
                    counters=self._counters_resultado(resultado),
                )

    def _ejecutar_tercera_fase(
        self,
        decisiones: list[DecisionArchivo],
        resultado: ResultadoEjecucion,
    ) -> list[DecisionArchivo]:
        """
        Delega en TerceraFaseResolucion la última pasada conservadora sobre los
        casos que siguen sin resolverse después de la fase 2.

        La tercera fase incorpora iTunes como fuente de corroboración adicional
        y aplica criterios más permisivos para promover cuarentenas a revisión
        o revisiones a aceptados cuando la evidencia es suficiente.

        Actualiza métricas de la fase en ``resultado`` y cierra sidecars para
        archivos promovidos.
        """
        tipos_entrada = {id(d): d.tipo for d in decisiones}
        resolver = TerceraFaseResolucion(
            mb_client=self._mb_client,
            itunes_client=self._itunes_client,
            directorio_biblioteca=self._dir_biblioteca,
            directorio_temp=self._dir_temp,
            barra=self._barra,
            control=self._control,
        )
        decisiones_finales, resumen = resolver.procesar(decisiones)
        resultado.tercera_fase_habilitada = resumen.habilitada
        resultado.tercera_fase_elegibles = resumen.elegibles
        resultado.tercera_fase_promovidos = resumen.promovidos
        resultado.tercera_fase_mejorados_revision = resumen.mejorados_a_revision
        resultado.tercera_fase_sin_cambio = resumen.sin_cambio
        resultado.tercera_fase_duracion_seg = resumen.duracion_seg
        if self._barra and resumen.habilitada:
            self._barra.mensaje(
                "3ª fase: "
                f"elegibles={resumen.elegibles} | promovidos={resumen.promovidos} | "
                f"mejorados_revision={resumen.mejorados_a_revision} | "
                f"t={resumen.duracion_seg:.2f}s",
                nivel="info",
            )
        self._cerrar_promociones_de_fase(decisiones_finales, tipos_entrada, "fase_3")
        return decisiones_finales

    @staticmethod
    def _registrar_evento_archivo(
        nombre: str,
        decision: DecisionArchivo,
        etapas_ms: dict[str, int],
        archivo: ArchivoAudio,
    ) -> None:
        registrar_evento(
            "archivo_resumen",
            archivo=nombre,
            datos={
                "resultado": decision.tipo.value,
                "causa_cuarentena": (
                    decision.causa_cuarentena.value if decision.causa_cuarentena else None
                ),
                "causa_revision": (
                    decision.causa_revision.value if decision.causa_revision else None
                ),
                "puntaje": round(decision.puntaje_maximo, 4),
                "fuente_dominante": (
                    decision.fuentes_usadas[0].value if decision.fuentes_usadas else None
                ),
                "etapas_ms": etapas_ms,
                "errores": archivo.errores,
                "advertencias": archivo.advertencias,
                "duplicado": decision.info_duplicado,
                "override": decision.override_aplicado,
                "explain": decision.esquema_explicacion,
            },
        )

    # ------------------------------------------------------------------
    # UTILIDADES INTERNAS
    # ------------------------------------------------------------------

    @staticmethod
    def _counters_resultado(resultado: ResultadoEjecucion) -> dict[str, int]:
        return {
            "aceptados": resultado.total_aceptados,
            "aceptados_provisional": resultado.total_aceptados_provisional,
            "revision": resultado.total_revision,
            "cuarentena": resultado.total_cuarentena,
            "omitidos": resultado.total_omitidos,
            "errores": resultado.total_errores,
        }

    def _set_phase(
        self,
        phase_id: str,
        phase_label: str,
        *,
        total: Optional[int] = None,
        current: int = 0,
        current_item: str = "",
        current_task: str = "",
    ) -> None:
        if self._barra and hasattr(self._barra, "establecer_fase"):
            self._barra.establecer_fase(
                phase_id,
                phase_label,
                total=total,
                current=current,
                current_item=current_item,
                current_task=current_task,
            )
        if self._control:
            self._control.fase(
                phase_id,
                phase_label,
                total=total,
                current=current,
                current_item=current_item,
                current_task=current_task,
            )
        registrar_evento(
            "pipeline_phase",
            datos={
                "phase_id": phase_id,
                "phase_label": phase_label,
                "total": total or 0,
                "current": current,
            },
        )

    def _update_phase(
        self,
        *,
        current: Optional[int] = None,
        total: Optional[int] = None,
        current_item: Optional[str] = None,
        current_task: Optional[str] = None,
        last_event: Optional[str] = None,
        severity: str = "info",
    ) -> None:
        if self._barra and hasattr(self._barra, "actualizar_fase"):
            self._barra.actualizar_fase(
                current=current,
                total=total,
                current_item=current_item,
                current_task=current_task,
                severity=severity,
            )
        if self._control:
            snapshot = self._barra.snapshot() if self._barra and hasattr(self._barra, "snapshot") else {}
            self._control.progreso_fase(
                current=current,
                total=total,
                current_item=current_item,
                current_task=current_task,
                last_event=last_event or snapshot.get("last_event"),
                severity=severity,
            )
            if snapshot:
                self._control.checkpoint(
                    eta_seconds=snapshot.get("eta_seconds"),
                    phase_eta_seconds=snapshot.get("phase_eta_seconds"),
                    elapsed_seconds=snapshot.get("elapsed_seconds"),
                    extras=snapshot.get("extras"),
                )

    def _heartbeat_progress(self, texto: str) -> None:
        if self._barra and hasattr(self._barra, "heartbeat"):
            self._barra.heartbeat(texto)
        if self._control:
            snapshot = self._barra.snapshot() if self._barra and hasattr(self._barra, "snapshot") else {}
            self._control.checkpoint(
                last_event=texto,
                eta_seconds=snapshot.get("eta_seconds"),
                phase_eta_seconds=snapshot.get("phase_eta_seconds"),
                elapsed_seconds=snapshot.get("elapsed_seconds"),
                extras=snapshot.get("extras"),
            )

    def _crear_componente_reintentable(self, nombre: str, factory, fallback_factory):
        """
        Inicializa un componente externo con reintentos y backoff exponencial.

        Intenta hasta INIT_COMPONENT_MAX_RETRIES veces con pausa creciente entre
        intentos. Si todos fallan, prueba el factory de fallback; si también falla,
        retorna _ComponenteInactivo para que el pipeline arranque en modo degradado.

        El backoff es: INIT_COMPONENT_RETRY_BACKOFF_SEG * 2^intento
        """
        for intento in range(INIT_COMPONENT_MAX_RETRIES + 1):
            try:
                return factory()
            except Exception as e:
                ultimo = intento >= INIT_COMPONENT_MAX_RETRIES
                _log.warning(
                    f"Inicializacion {nombre} fallida (intento {intento + 1}/"
                    f"{INIT_COMPONENT_MAX_RETRIES + 1}): {e}"
                )
                if ultimo:
                    _log.error(f"{nombre} quedara desactivado tras agotar reintentos.")
                    try:
                        return fallback_factory()
                    except Exception:
                        return _ComponenteInactivo(nombre)
                pausa = INIT_COMPONENT_RETRY_BACKOFF_SEG * (2 ** intento)
                time.sleep(pausa)
        try:
            return fallback_factory()
        except Exception:
            return _ComponenteInactivo(nombre)

    def _registrar_operacion_aplicada(self, origen: Path, destino: Path) -> None:
        self._ops_aplicadas.append((origen, destino))
        if self._control:
            self._control.registrar_operacion("move", origen, destino)

    def _rollback_cambios(self) -> None:
        """
        Revierte en orden inverso las operaciones de movimiento registradas en
        ``_ops_aplicadas`` cuando el usuario cancela la ejecución.

        Para archivos en la biblioteca: elimina la copia escrita (no hay original
        que restaurar porque la biblioteca recibe una copia, no el original).
        Para archivos movidos a cuarentena/revisión: los devuelve al origen.

        Adicionalmente limpia el directorio de caché para evitar estado inconsistente.
        Los errores de rollback se registran pero no se propagan, dado que ya estamos
        en un escenario de cancelación.
        """
        if not self._ops_aplicadas:
            return
        _log.warning("Iniciando rollback de cambios aplicados por cancelacion...")
        for origen, destino in reversed(self._ops_aplicadas):
            try:
                if not destino.exists():
                    continue
                if destino.parent == self._dir_biblioteca or self._dir_biblioteca in destino.parents:
                    destino.unlink(missing_ok=True)
                    continue
                origen.parent.mkdir(parents=True, exist_ok=True)
                if origen.exists():
                    origen.unlink(missing_ok=True)
                shutil.move(str(destino), str(origen))
            except Exception as e:
                _log.warning(f"Rollback parcial fallido para {destino} -> {origen}: {e}")
        try:
            if self._dir_cache and self._dir_cache.exists():
                shutil.rmtree(self._dir_cache, ignore_errors=True)
        except Exception as e:
            _log.warning(f"No se pudo limpiar cache en rollback: {e}")
        self._ops_aplicadas.clear()

    @staticmethod
    def _ya_fue_procesado(archivo: ArchivoAudio) -> bool:
        """
        Verifica si el archivo ya fue procesado buscando el marcador TXXX.
        Soporta marcadores de v2 (TAGGER_V2) y v3 (TAGGER_V3) para no
        reprocesar archivos ya catalogados en ejecuciones anteriores.
        """
        if not archivo.ruta_original.exists():
            return False
        try:
            from mutagen.id3 import ID3
            from config.settings import PROCESSED_TAG_MARKER, PROCESSED_TAG_FIELD
            tags = ID3(str(archivo.ruta_original))
            txxx = tags.get(PROCESSED_TAG_FIELD)
            if txxx:
                valor = str(txxx)
                # Aceptar tanto el marcador actual como el de la version anterior
                if valor in {PROCESSED_TAG_MARKER, "TAGGER_V2"}:
                    return True
        except Exception as _exc:
            _log.debug("Excepcion ignorada en %s: %s", "pipeline.py", _exc)
        return False

    def _actualizar_resultado(
        self, resultado: ResultadoEjecucion, decision: DecisionArchivo
    ) -> None:
        nombre = decision.archivo.nombre_archivo

        if decision.tipo == DecisionTipo.ACEPTADO:
            resultado.total_aceptados += 1
            resultado.archivos_aceptados.append(nombre)
        elif decision.tipo == DecisionTipo.ACEPTADO_PROVISIONAL:
            resultado.total_aceptados_provisional += 1
            resultado.archivos_aceptados.append(nombre)  # Se escribe igualmente
        elif decision.tipo == DecisionTipo.REVISION:
            resultado.total_revision += 1
            resultado.archivos_revision.append(nombre)
        elif decision.tipo == DecisionTipo.CUARENTENA:
            resultado.total_cuarentena += 1
            resultado.archivos_cuarentena.append(nombre)
        elif decision.tipo == DecisionTipo.DUPLICADO_EXACTO:
            resultado.total_duplicado_exacto += 1
            resultado.archivos_duplicados.append(nombre)
        elif decision.tipo == DecisionTipo.DUPLICADO_SEMANTICO:
            resultado.total_duplicado_semantico += 1
            resultado.archivos_duplicados.append(nombre)
        elif decision.tipo == DecisionTipo.DUPLICADO_MEJORABLE:
            resultado.total_duplicado_mejorable += 1
            resultado.archivos_duplicados.append(nombre)
        elif decision.tipo == DecisionTipo.OMITIDO:
            resultado.total_omitidos += 1
        else:  # ERROR
            resultado.total_errores += 1
            resultado.archivos_error.append(nombre)

    def _cerrar_promociones_de_fase(
        self,
        decisiones: list[DecisionArchivo],
        tipos_entrada: dict[int, DecisionTipo],
        fase: str,
    ) -> None:
        """Completa sidecars/manifiestos para aceptados promovidos fuera del flujo principal."""
        escribibles = {DecisionTipo.ACEPTADO, DecisionTipo.ACEPTADO_PROVISIONAL}
        total = 0
        for decision in decisiones:
            tipo_previo = tipos_entrada.get(id(decision))
            if decision.tipo not in escribibles or tipo_previo in escribibles:
                continue
            decision.esquema_explicacion.setdefault("resolution_phase", fase)
            self._post_aceptacion_materializada(
                decision,
                decision.archivo.nombre_archivo,
            )
            total += 1
        if total and self._barra:
            self._barra.mensaje(
                f"{fase.replace('_', ' ')}: sidecars y manifiestos programados para {total} aceptado(s)",
                nivel="ok",
            )

    def _post_aceptacion_materializada(
        self,
        decision: DecisionArchivo,
        nombre: str,
    ) -> None:
        """
        Cierre común tras la materialización de un archivo aceptado.

        Centraliza en un único punto todas las acciones que siguen a la escritura
        exitosa, independientemente de si el archivo fue aceptado en la primera
        pasada, por override o promovido en fase 2/3:

          1. Registro de identidad en el gestor de deduplicación semántica.
          2. Programación del sidecar de assets (imágenes) en el executor daemon.
          3. Programación del sidecar de enrichment (letras, analítica).
          4. Si hay sidecars programados: el manifiesto se difiere hasta que
             completen (para incluir URLs de imágenes, etc.).
             Si no hay sidecars: el manifiesto se escribe inmediatamente.

        El patrón diferir-o-escribir-inmediatamente evita race conditions entre
        la escritura del manifiesto y los sidecars que enriquecen sus datos.
        """
        if ENABLE_SEMANTIC_DEDUPLICATION:
            self._dedupe.registrar_identidad_aceptada(decision)

        sidecars = decision.esquema_explicacion.setdefault("sidecars", {})
        scheduled = False

        if self._assets is not None:
            sidecars["assets"] = {"status": "scheduled"}
            scheduled = self._programar_assets(decision, nombre) or scheduled
        else:
            sidecars["assets"] = {"status": "disabled"}
            self._barra_omitir_extra("assets", nombre, "pipeline de imagenes desactivado")

        if self._enrichment is not None and self._enrichment.active:
            sidecars["enrichment"] = {"status": "scheduled"}
            scheduled = self._programar_enrichment(decision, nombre) or scheduled
        else:
            sidecars["enrichment"] = {"status": "disabled"}
            self._barra_omitir_extra("enrichment", nombre, "enrichment desactivado")

        if scheduled:
            self._manifests_deferidos[id(decision)] = (decision, nombre)
        else:
            self._escribir_manifest_seguro(decision, nombre)

    def _escribir_manifest_seguro(
        self,
        decision: DecisionArchivo,
        nombre: str,
    ) -> None:
        sidecars = decision.esquema_explicacion.setdefault("sidecars", {})
        sidecars["manifest"] = {"status": "saved"}
        inicio = time.perf_counter()
        self._barra_registrar_extra("manifest", nombre, f"manifest: {nombre}")
        try:
            self._manifests.escribir_decision(decision)
            registrar_evento(
                "sidecar_manifest",
                archivo=nombre,
                datos={"status": "saved"},
            )
            self._barra_finalizar_extra(
                "manifest",
                nombre,
                ok=True,
                duracion_seg=time.perf_counter() - inicio,
            )
        except Exception as e:
            sidecars["manifest"] = {"status": "error", "error": str(e)}
            _log.warning(f"No se pudo escribir manifiesto para {nombre}: {e}")
            registrar_evento(
                "sidecar_manifest",
                archivo=nombre,
                datos={"status": "error", "error": str(e)},
            )
            self._barra_finalizar_extra(
                "manifest",
                nombre,
                ok=False,
                detalle=str(e),
                duracion_seg=time.perf_counter() - inicio,
            )

    def _barra_registrar_extra(self, tipo: str, nombre: str, descripcion: str) -> None:
        if self._barra and hasattr(self._barra, "registrar_tarea_extra"):
            self._barra.registrar_tarea_extra(tipo, nombre, descripcion)
        if self._control:
            self._control.registrar_tarea_extra(tipo, nombre, "scheduled", descripcion)

    def _barra_finalizar_extra(
        self,
        tipo: str,
        nombre: str,
        ok: bool,
        detalle: str = "",
        duracion_seg: Optional[float] = None,
        status: Optional[str] = None,
    ) -> None:
        if self._barra and hasattr(self._barra, "finalizar_tarea_extra"):
            self._barra.finalizar_tarea_extra(
                tipo,
                nombre,
                ok=ok,
                detalle=detalle,
                duracion_seg=duracion_seg,
            )
        if self._control:
            self._control.registrar_tarea_extra(
                tipo,
                nombre,
                status or ("ok" if ok else "error"),
                detalle,
            )

    def _barra_omitir_extra(self, tipo: str, nombre: str, razon: str) -> None:
        if self._barra and hasattr(self._barra, "omitir_tarea_extra"):
            self._barra.omitir_tarea_extra(tipo, nombre, razon)
        if self._control:
            self._control.registrar_tarea_extra(tipo, nombre, "skipped", razon)

    @staticmethod
    def _sidecar_key(tipo: str, decision: DecisionArchivo, nombre: str) -> tuple[str, int, str]:
        return (tipo, id(decision), nombre)

    def _programar_assets(self, decision: DecisionArchivo, nombre: str) -> bool:
        if self._assets is None:
            return False
        if self._assets_executor is None:
            self._assets_executor = _SidecarExecutorDaemon(max_workers=2)
        self._barra_registrar_extra("assets", nombre, f"imagenes: {nombre}")
        key = self._sidecar_key("assets", decision, nombre)
        future = self._assets_executor.submit(self._ejecutar_assets_safe, decision, nombre, key)
        self._assets_futures.append(
            {
                "kind": "assets",
                "nombre": nombre,
                "decision": decision,
                "future": future,
                "submitted_at": time.monotonic(),
                "key": key,
            }
        )
        return True

    def _ejecutar_assets_safe(
        self,
        decision: DecisionArchivo,
        nombre: str,
        key: tuple[str, int, str],
    ) -> None:
        inicio = time.perf_counter()
        try:
            self._assets.procesar(decision)
            with self._sidecar_lock:
                late_after_timeout = key in self._sidecars_timeout
            if late_after_timeout:
                selection = decision.esquema_explicacion.get("asset_selection", {})
                selected = {
                    key: value.get("selected")
                    for key, value in selection.items()
                    if isinstance(value, dict) and value.get("selected")
                }
                decision.esquema_explicacion.setdefault("sidecars", {})["assets"] = {
                    "status": "late_saved" if selected else "late_not_found",
                    "retryable": not bool(selected),
                    "selected": selected,
                }
                registrar_evento(
                    "sidecar_assets_late_saved",
                    archivo=nombre,
                    datos={"status": "late_saved" if selected else "late_not_found", "selected": selected},
                )
                return
            selection = decision.esquema_explicacion.get("asset_selection", {})
            selected = {
                key: value.get("selected")
                for key, value in selection.items()
                if isinstance(value, dict) and value.get("selected")
            }
            status = "saved" if selected else "not_found"
            decision.esquema_explicacion.setdefault("sidecars", {})["assets"] = {
                "status": status,
                "selected": selected,
            }
            registrar_evento(
                "sidecar_assets",
                archivo=nombre,
                datos={"status": status, "selected": selected},
            )
            self._barra_finalizar_extra(
                "assets",
                nombre,
                ok=True,
                duracion_seg=time.perf_counter() - inicio,
            )
        except Exception as e:
            with self._sidecar_lock:
                if key in self._sidecars_timeout:
                    registrar_evento(
                        "sidecar_assets_late_ignored",
                        archivo=nombre,
                        datos={"status": "late_error_after_timeout", "error": str(e)},
                    )
                    return
            _log.warning(f"Assets pipeline fallo para {nombre}: {e}")
            decision.esquema_explicacion.setdefault("sidecars", {})["assets"] = {
                "status": "error",
                "error": str(e),
            }
            registrar_evento(
                "sidecar_assets",
                archivo=nombre,
                datos={"status": "error", "error": str(e)},
            )
            self._barra_finalizar_extra(
                "assets",
                nombre,
                ok=False,
                detalle=str(e),
                duracion_seg=time.perf_counter() - inicio,
            )


    def _programar_enrichment(self, decision: DecisionArchivo, nombre: str) -> bool:
        if self._enrichment is None or not self._enrichment.active:
            return False
        if self._assets_executor is None:
            self._assets_executor = _SidecarExecutorDaemon(max_workers=2)
        self._barra_registrar_extra("enrichment", nombre, f"letras/analitica: {nombre}")
        key = self._sidecar_key("enrichment", decision, nombre)
        future = self._assets_executor.submit(self._ejecutar_enrichment_safe, decision, nombre, key)
        self._assets_futures.append(
            {
                "kind": "enrichment",
                "nombre": nombre,
                "decision": decision,
                "future": future,
                "submitted_at": time.monotonic(),
                "key": key,
            }
        )
        return True

    def _ejecutar_enrichment_safe(
        self,
        decision: DecisionArchivo,
        nombre: str,
        key: tuple[str, int, str],
    ) -> None:
        inicio = time.perf_counter()
        try:
            self._enrichment.procesar(decision)
            with self._sidecar_lock:
                late_after_timeout = key in self._sidecars_timeout
            if late_after_timeout:
                summary = decision.esquema_explicacion.get("enrichment", {})
                decision.esquema_explicacion.setdefault("sidecars", {})["enrichment"] = {
                    "status": "late_saved",
                    "retryable": False,
                    **summary,
                }
                registrar_evento(
                    "sidecar_enrichment_late_saved",
                    archivo=nombre,
                    datos={"status": "late_saved", **summary},
                )
                return
            summary = decision.esquema_explicacion.get("enrichment", {})
            decision.esquema_explicacion.setdefault("sidecars", {})["enrichment"] = {
                "status": "saved",
                **summary,
            }
            registrar_evento(
                "sidecar_enrichment",
                archivo=nombre,
                datos={"status": "saved", **summary},
            )
            self._barra_finalizar_extra(
                "enrichment",
                nombre,
                ok=True,
                duracion_seg=time.perf_counter() - inicio,
            )
        except Exception as e:
            with self._sidecar_lock:
                if key in self._sidecars_timeout:
                    registrar_evento(
                        "sidecar_enrichment_late_ignored",
                        archivo=nombre,
                        datos={"status": "late_error_after_timeout", "error": str(e)},
                    )
                    return
            _log.debug(f"Enrichment pipeline fallo en {nombre}: {e}")
            decision.esquema_explicacion.setdefault("sidecars", {})["enrichment"] = {
                "status": "error",
                "error": str(e),
            }
            registrar_evento(
                "sidecar_enrichment",
                archivo=nombre,
                datos={"status": "error", "error": str(e)},
            )
            self._barra_finalizar_extra(
                "enrichment",
                nombre,
                ok=False,
                detalle=str(e),
                duracion_seg=time.perf_counter() - inicio,
            )

    def _esperar_assets_pendientes(self) -> None:
        """
        Bucle de espera activa para los Futures de sidecars (assets y enrichment).

        Cada iteración revisa el estado de los Futures pendientes:
          - Completado (done): obtiene el resultado, registra ok/error y avanza.
          - En ejecución pero excedido SIDECAR_FUTURE_TIMEOUT_SEG: cancela el Future,
            marca el sidecar como "timeout" en el esquema_explicacion de la decisión,
            y añade la key a _sidecars_timeout para que el worker lo detecte si
            termina tarde (late_saved vs late_error).

        El timestamp ``_nb_sound_started_at`` es inyectado por el worker al arrancar
        cada tarea, permitiendo medir el tiempo real de ejecución del sidecar.

        Una vez vaciada la lista de Futures, escribe los manifiestos diferidos
        (que esperaban a que los sidecars completaran sus datos).
        """
        pendientes = list(self._assets_futures)
        total_sidecars = len(pendientes)
        completados = 0
        siguiente_heartbeat = time.monotonic()
        timeouts_por_kind: dict[str, int] = {}
        ejemplos_timeout: dict[str, list[str]] = {}
        while pendientes:
            ahora = time.monotonic()
            progreso = False
            for item in list(pendientes):
                future = item["future"]
                nombre = item.get("nombre", "archivo")
                kind = item.get("kind", "sidecar")
                key = item.get("key")
                started_at = getattr(future, "_nb_sound_started_at", None)
                if future.done():
                    try:
                        future.result()
                    except Exception as e:
                        _log.warning(f"Sidecar {kind} fallo para {nombre}: {e}")
                        self._barra_finalizar_extra(kind, nombre, ok=False, detalle=str(e))
                    pendientes.remove(item)
                    completados += 1
                    progreso = True
                    self._update_phase(
                        current=completados,
                        total=total_sidecars,
                        current_item=nombre,
                        current_task=f"sidecar:{kind}",
                    )
                    continue
                if started_at is None:
                    continue
                if ahora - float(started_at) >= SIDECAR_FUTURE_TIMEOUT_SEG:
                    detalle = f"timeout tras {SIDECAR_FUTURE_TIMEOUT_SEG:.0f}s"
                    timeouts_por_kind[kind] = timeouts_por_kind.get(kind, 0) + 1
                    ejemplos = ejemplos_timeout.setdefault(kind, [])
                    if len(ejemplos) < 5:
                        ejemplos.append(str(nombre))
                    _log.debug(f"Sidecar {kind} excedio timeout para {nombre}: {detalle}")
                    if key is not None:
                        with self._sidecar_lock:
                            self._sidecars_timeout.add(key)
                    cancelado = future.cancel()
                    decision = item.get("decision")
                    if decision is not None:
                        decision.esquema_explicacion.setdefault("sidecars", {})[kind] = {
                            "status": "timeout",
                            "retryable": True,
                            "error": detalle,
                            "cancelled": bool(cancelado),
                        }
                    registrar_evento(
                        f"sidecar_{kind}_timeout",
                        archivo=nombre,
                        datos={"status": "timeout", "retryable": True, "cancelled": bool(cancelado)},
                    )
                    self._barra_finalizar_extra(
                        kind,
                        nombre,
                        ok=False,
                        detalle=detalle,
                        status="timeout",
                    )
                    pendientes.remove(item)
                    completados += 1
                    progreso = True
                    self._update_phase(
                        current=completados,
                        total=total_sidecars,
                        current_item=nombre,
                        current_task=f"sidecar_timeout:{kind}",
                        severity="warn",
                    )
            if not pendientes:
                break
            if progreso or ahora >= siguiente_heartbeat:
                nombres = ", ".join(str(i.get("nombre", "archivo")) for i in pendientes[:3])
                if len(pendientes) > 3:
                    nombres += f" +{len(pendientes) - 3}"
                self._heartbeat_progress(
                    f"Esperando sidecars: {completados}/{total_sidecars} completos; pendientes={len(pendientes)} ({nombres})"
                )
                siguiente_heartbeat = ahora + SIDECAR_WAIT_HEARTBEAT_SEG
            if self._control:
                self._control.esperar_si_pausado()
                if self._control.cancelado():
                    for item in pendientes:
                        item["future"].cancel()
                    break
            time.sleep(0.1)
        for kind, cantidad in sorted(timeouts_por_kind.items()):
            ejemplos = ", ".join(ejemplos_timeout.get(kind, []))
            if cantidad > len(ejemplos_timeout.get(kind, [])):
                ejemplos = f"{ejemplos} +{cantidad - len(ejemplos_timeout.get(kind, []))}"
            _log.warning(
                "Sidecars %s con timeout: %s tarea(s)%s",
                kind,
                cantidad,
                f" ({ejemplos})" if ejemplos else "",
            )
        self._assets_futures.clear()
        manifests = list(self._manifests_deferidos.values())
        if manifests:
            self._set_phase(
                "manifests",
                "Escribiendo manifiestos finales",
                total=len(manifests),
                current=0,
                current_task="manifest",
            )
        for indice, (decision, nombre) in enumerate(manifests, start=1):
            self._update_phase(
                current=indice,
                total=len(manifests),
                current_item=nombre,
                current_task="manifest",
            )
            self._escribir_manifest_seguro(decision, nombre)
        self._manifests_deferidos.clear()

    def _cerrar_executor_assets(self) -> None:
        if self._assets_executor is not None:
            self._assets_executor.shutdown(wait=False, cancel_futures=True)
            self._assets_executor = None
