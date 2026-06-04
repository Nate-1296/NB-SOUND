# =============================================================================
# servicios/importacion.py
#
# Servicio de importacion: envuelve el pipeline del tagger para ejecutarlo
# desde la UI con progreso en tiempo real.
#
# La importacion es un proceso potencialmente largo (decenas de minutos para
# bibliotecas grandes). Se ejecuta en un hilo separado y comunica su progreso
# via callbacks para que la UI pueda actualizarse sin bloquearse.
#
# Despues de cada archivo aceptado, el indexador actualiza la BD para que
# la pista este disponible inmediatamente en la biblioteca.
# =============================================================================

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

from db.conexion import ejecutar, ejecutar_y_obtener_id
from infra.execution_control import ControlEjecucion
from infra.logger import obtener_logger
from servicios.indexador import IndexadorBiblioteca

_log = obtener_logger("importacion")

# Tipos de callback
# progreso:  (procesados, total, nombre_archivo, etapa) -> None
# completado: (resumen_dict) -> None
# error:     (mensaje) -> None
TipoCallbackProgreso   = Callable[[int, int, str, str], None]
TipoCallbackCompletado = Callable[[dict], None]
TipoCallbackError      = Callable[[str], None]
TipoCallbackCancelado  = Callable[[dict], None]


def marcar_sesiones_importacion_huerfanas() -> None:
    resumen = {
        "estado": "interrumpido",
        "motivo": "Sesion UI anterior sin worker activo al iniciar la app/importador",
    }
    ejecutar(
        """
        UPDATE sesiones_import SET
            finalizado_en = COALESCE(finalizado_en, datetime('now')),
            estado = 'interrumpido',
            reporte_json = COALESCE(reporte_json, ?)
        WHERE estado = 'en_progreso'
          AND finalizado_en IS NULL
        """,
        (json.dumps(resumen),),
    )


@dataclass
class ConfigImportacion:
    """Parametros para una sesion de importacion."""
    directorio_entrada:    Path
    directorio_biblioteca: Path
    directorio_revision:   Path
    directorio_cuarentena: Path
    directorio_logs:       Path
    directorio_procesados: Path
    directorio_cache:      Path
    directorio_temp:       Path
    dry_run:               bool = False
    enable_shazam:         bool = True
    enable_acoustid:       bool = True
    score_accept:          float = 0.82
    score_review:          float = 0.55
    ia_proveedor:          str = "No"
    acoustid_key:          str = ""
    anthropic_key:         str = ""
    openai_key:            str = ""
    ajustes_avanzados:     dict[str, str] = field(default_factory=dict)


class ServicioImportacion:
    """
    Ejecuta el pipeline del tagger en background y expone callbacks de progreso.

    Uso:
        svc = ServicioImportacion()
        svc.on_progreso(mi_cb_progreso)
        svc.on_completado(mi_cb_completado)
        svc.iniciar(config)
    """

    def __init__(self) -> None:
        self._hilo:           Optional[threading.Thread] = None
        self._cancelar        = threading.Event()
        self._control:        Optional[ControlEjecucion] = None
        self._en_ejecucion    = False
        self._sesion_id:      Optional[int] = None

        self._cb_progreso:    list[TipoCallbackProgreso]   = []
        self._cb_completado:  list[TipoCallbackCompletado] = []
        self._cb_error:       list[TipoCallbackError]      = []
        self._cb_cancelado:   list[TipoCallbackCancelado]  = []

    # ------------------------------------------------------------------
    # REGISTRO DE CALLBACKS
    # ------------------------------------------------------------------

    def on_progreso(self, cb: TipoCallbackProgreso) -> None:
        self._cb_progreso.append(cb)

    def on_completado(self, cb: TipoCallbackCompletado) -> None:
        self._cb_completado.append(cb)

    def on_error(self, cb: TipoCallbackError) -> None:
        self._cb_error.append(cb)

    def on_cancelado(self, cb: TipoCallbackCancelado) -> None:
        self._cb_cancelado.append(cb)

    # ------------------------------------------------------------------
    # CONTROL
    # ------------------------------------------------------------------

    def iniciar(self, config: ConfigImportacion) -> bool:
        """
        Inicia el proceso de importacion en background.
        Retorna False si ya hay una importacion en curso.
        """
        if self._en_ejecucion:
            return False

        self._cancelar.clear()
        config.directorio_logs.mkdir(parents=True, exist_ok=True)
        self._marcar_sesiones_huerfanas()
        self._en_ejecucion = True
        self._sesion_id = self._crear_sesion(config.directorio_entrada)

        self._hilo = threading.Thread(
            target=self._ejecutar_pipeline,
            args=(config,),
            daemon=True,
        )
        self._hilo.start()
        return True

    def cancelar(self) -> None:
        """Solicita la cancelacion de la importacion en curso."""
        self._cancelar.set()
        if self._control:
            self._control.cancelar("ui_request")

    @property
    def en_ejecucion(self) -> bool:
        return self._en_ejecucion

    @staticmethod
    def _bool_config(valor: object, default: bool) -> bool:
        if valor is None:
            return default
        texto = str(valor).strip().lower()
        if texto in {"1", "true", "yes", "on", "si", "sí"}:
            return True
        if texto in {"0", "false", "no", "off"}:
            return False
        return default

    @staticmethod
    def _aplicar_ajustes_avanzados(cfg, ajustes: dict[str, str]) -> None:
        if not ajustes:
            return

        bool_map = {
            "skip_already_processed": "SKIP_ALREADY_PROCESSED",
            "enable_deduplication": "ENABLE_DEDUPLICATION",
            "enable_semantic_deduplication": "ENABLE_SEMANTIC_DEDUPLICATION",
            "enable_assets_pipeline": "ENABLE_ASSETS_PIPELINE",
            "enable_cover_art_archive": "ENABLE_COVER_ART_ARCHIVE",
            "enable_theaudiodb_artist_images": "ENABLE_THEAUDIODB_ARTIST_IMAGES",
            "enable_itunes_cover_fallback": "ENABLE_ITUNES_COVER_FALLBACK",
            "enable_deezer_artist_images": "ENABLE_DEEZER_ARTIST_IMAGES",
            "enable_wikipedia_artist_images": "ENABLE_WIKIPEDIA_ARTIST_IMAGES",
            "enable_itunes_artist_images": "ENABLE_ITUNES_ARTIST_IMAGES",
            "enable_external_enrichment": "ENABLE_EXTERNAL_ENRICHMENT",
            "enable_lyrics_enrichment": "ENABLE_LYRICS_ENRICHMENT",
            "enable_lrclib": "ENABLE_LRCLIB",
            "enable_lyrics_ovh": "ENABLE_LYRICS_OVH",
            "enable_second_stage_resolution": "ENABLE_SECOND_STAGE_RESOLUTION",
            "second_stage_cause_enabled": "SECOND_STAGE_CAUSE_ENABLED",
            "enable_third_stage_resolution": "ENABLE_THIRD_STAGE_RESOLUTION",
            "enable_ia_discography": "ENABLE_IA_DISCOGRAPHY",
            "enable_overrides": "ENABLE_OVERRIDES",
            "enable_audio_features": "ENABLE_AUDIO_FEATURES",
            "audio_features_analyze_on_import": "AUDIO_FEATURES_ANALYZE_ON_IMPORT",
            "audio_features_background": "AUDIO_FEATURES_BACKGROUND",
            "audio_features_analyze_full_track": "AUDIO_FEATURES_ANALYZE_FULL_TRACK",
            "audio_features_reanalyze_on_version_change": "AUDIO_FEATURES_REANALYZE_ON_VERSION_CHANGE",
            "audio_features_fail_silently": "AUDIO_FEATURES_FAIL_SILENTLY",
            "enable_audio_intelligence_deep": "ENABLE_AUDIO_INTELLIGENCE_DEEP",
            "enable_audio_mood_models": "ENABLE_AUDIO_MOOD_MODELS",
            "enable_audio_embeddings": "ENABLE_AUDIO_EMBEDDINGS",
            "enable_audio_tagging_models": "ENABLE_AUDIO_TAGGING_MODELS",
            "audio_intelligence_analyze_after_import_background": "AUDIO_INTELLIGENCE_ANALYZE_AFTER_IMPORT_BACKGROUND",
            "audio_intelligence_resume_pending_on_startup": "AUDIO_INTELLIGENCE_RESUME_PENDING_ON_STARTUP",
            "audio_intelligence_background_autostart": "AUDIO_INTELLIGENCE_BACKGROUND_AUTOSTART",
            "audio_intelligence_background": "AUDIO_INTELLIGENCE_BACKGROUND",
            "audio_intelligence_allow_model_downloads": "AUDIO_INTELLIGENCE_ALLOW_MODEL_DOWNLOADS",
            "audio_intelligence_reanalyze_on_model_change": "AUDIO_INTELLIGENCE_REANALYZE_ON_MODEL_CHANGE",
            "audio_intelligence_retry_failed": "AUDIO_INTELLIGENCE_RETRY_FAILED",
            "audio_intelligence_cancel_discard_outputs": "AUDIO_INTELLIGENCE_CANCEL_DISCARD_OUTPUTS",
            "audio_intelligence_fail_silently": "AUDIO_INTELLIGENCE_FAIL_SILENTLY",
            "enable_music_discovery": "ENABLE_MUSIC_DISCOVERY",
            "music_discovery_use_audio_features": "MUSIC_DISCOVERY_USE_AUDIO_FEATURES",
            "music_discovery_use_deep_features": "MUSIC_DISCOVERY_USE_DEEP_FEATURES",
            "music_discovery_explain_results": "MUSIC_DISCOVERY_EXPLAIN_RESULTS",
        }
        int_map = {
            "shazam_timeout_seg": "SHAZAM_TIMEOUT_SEG",
            "shazam_min_duracion_seg": "SHAZAM_MIN_DURACION_SEG",
            "ia_max_tokens": "IA_MAX_TOKENS",
            "ia_timeout_seg": "IA_TIMEOUT_SEG",
            "init_component_max_retries": "INIT_COMPONENT_MAX_RETRIES",
            "assets_timeout_seg": "ASSETS_TIMEOUT_SEG",
            "assets_max_retries": "ASSETS_MAX_RETRIES",
            "assets_cache_ttl_seg": "ASSETS_CACHE_TTL_SEG",
            "assets_negative_cache_ttl_seg": "ASSETS_NEGATIVE_CACHE_TTL_SEG",
            "assets_min_resolution": "ASSETS_MIN_RESOLUTION",
            "assets_hd_max_image_bytes": "ASSETS_HD_MAX_IMAGE_BYTES",
            "lyrics_timeout_seg": "LYRICS_TIMEOUT_SEG",
            "lyrics_max_retries": "LYRICS_MAX_RETRIES",
            "lyrics_suggest_limit": "LYRICS_SUGGEST_LIMIT",
            "second_stage_max_candidates": "SECOND_STAGE_MAX_CANDIDATES",
            "manifest_schema_version": "MANIFEST_SCHEMA_VERSION",
            "audio_features_max_workers": "AUDIO_FEATURES_MAX_WORKERS",
            "audio_features_segment_seconds": "AUDIO_FEATURES_SEGMENT_SECONDS",
            "audio_intelligence_max_workers": "AUDIO_INTELLIGENCE_MAX_WORKERS",
            "audio_intelligence_background_batch_size": "AUDIO_INTELLIGENCE_BACKGROUND_BATCH_SIZE",
            "audio_intelligence_background_max_runtime_min": "AUDIO_INTELLIGENCE_BACKGROUND_MAX_RUNTIME_MIN",
            "audio_intelligence_segment_seconds": "AUDIO_INTELLIGENCE_SEGMENT_SECONDS",
            "audio_intelligence_max_attempts": "AUDIO_INTELLIGENCE_MAX_ATTEMPTS",
            "music_discovery_default_limit": "MUSIC_DISCOVERY_DEFAULT_LIMIT",
        }
        float_map = {
            "ia_tiebreak_min_gap": "IA_TIEBREAK_MIN_GAP",
            "init_component_retry_backoff_seg": "INIT_COMPONENT_RETRY_BACKOFF_SEG",
            "duplicate_better_min_delta": "DUPLICATE_BETTER_MIN_DELTA",
            "assets_retry_backoff_seg": "ASSETS_RETRY_BACKOFF_SEG",
            "lyrics_retry_backoff_seg": "LYRICS_RETRY_BACKOFF_SEG",
            "sidecar_future_timeout_seg": "SIDECAR_FUTURE_TIMEOUT_SEG",
            "sidecar_wait_heartbeat_seg": "SIDECAR_WAIT_HEARTBEAT_SEG",
            "nb_sound_progress_interval_sec": "NB_SOUND_PROGRESS_INTERVAL_SEC",
            "second_stage_min_evidence": "SECOND_STAGE_MIN_EVIDENCE",
            "second_stage_min_gap": "SECOND_STAGE_MIN_GAP",
            "third_stage_min_evidence": "THIRD_STAGE_MIN_EVIDENCE",
            "third_stage_min_gap": "THIRD_STAGE_MIN_GAP",
            "discography_ia_min_confidence": "DISCOGRAPHY_IA_MIN_CONFIDENCE",
            "audio_intelligence_background_idle_delay_sec": "AUDIO_INTELLIGENCE_BACKGROUND_IDLE_DELAY_SEC",
            "music_discovery_min_confidence": "MUSIC_DISCOVERY_MIN_CONFIDENCE",
        }
        str_map = {
            "duplicate_policy": "DUPLICATE_POLICY",
            "theaudiodb_api_key": "THEAUDIODB_API_KEY",
            "nb_sound_progress_mode": "NB_SOUND_PROGRESS_MODE",
            "audio_features_mode": "AUDIO_FEATURES_MODE",
            "audio_features_sample_strategy": "AUDIO_FEATURES_SAMPLE_STRATEGY",
            "audio_intelligence_backend": "AUDIO_INTELLIGENCE_BACKEND",
            "audio_intelligence_model_dir": "AUDIO_INTELLIGENCE_MODEL_DIR",
            "audio_intelligence_sample_strategy": "AUDIO_INTELLIGENCE_SAMPLE_STRATEGY",
        }

        for clave, atributo in bool_map.items():
            if clave in ajustes:
                setattr(cfg, atributo, ServicioImportacion._bool_config(ajustes.get(clave), bool(getattr(cfg, atributo))))
        for clave, atributo in int_map.items():
            if clave not in ajustes:
                continue
            try:
                setattr(cfg, atributo, int(float(str(ajustes.get(clave, "")).strip())))
            except (TypeError, ValueError):
                continue
        for clave, atributo in float_map.items():
            if clave not in ajustes:
                continue
            try:
                setattr(cfg, atributo, float(str(ajustes.get(clave, "")).strip()))
            except (TypeError, ValueError):
                continue
        for clave, atributo in str_map.items():
            if clave in ajustes:
                setattr(cfg, atributo, str(ajustes.get(clave, "")).strip())

    # ------------------------------------------------------------------
    # EJECUCION EN BACKGROUND
    # ------------------------------------------------------------------

    def _ejecutar_pipeline(self, config: ConfigImportacion) -> None:
        try:
            # Validar pre-condiciones operativas claras antes de crear el
            # pipeline. Sin esto, un directorio inexistente provoca un
            # ResultadoEjecucion vacío sin error visible para el usuario, que
            # percibe "no pasó nada" tras pulsar "Iniciar importación".
            entrada = config.directorio_entrada
            if not entrada or str(entrada).strip() == "":
                raise FileNotFoundError(
                    "El directorio de entrada no esta configurado. "
                    "Configuralo desde Configuracion > Rutas."
                )
            if not entrada.exists():
                # Crearlo es la opcion mas amable: el usuario tiene una carpeta
                # vacia donde dejar la musica para la proxima importacion.
                try:
                    entrada.mkdir(parents=True, exist_ok=True)
                    _log.info("Directorio de entrada creado: %s", entrada)
                except OSError as exc:
                    raise FileNotFoundError(
                        f"No se pudo crear el directorio de entrada "
                        f"'{entrada}': {exc}"
                    ) from exc
            elif not entrada.is_dir():
                raise NotADirectoryError(
                    f"La ruta de entrada '{entrada}' no es un directorio."
                )

            from config import settings as cfg

            # Aplicar configuracion operativa inyectada por la UI.
            cfg.DRY_RUN = config.dry_run
            cfg.ENABLE_SHAZAM = config.enable_shazam
            cfg.ENABLE_ACOUSTID = config.enable_acoustid
            cfg.SCORE_THRESHOLD_ACCEPT = config.score_accept
            cfg.SCORE_THRESHOLD_REVIEW = config.score_review
            cfg.IA_PROVEEDOR = config.ia_proveedor
            if config.acoustid_key:
                cfg.ACOUSTID_API_KEY = config.acoustid_key
            if config.anthropic_key:
                cfg.ANTHROPIC_API_KEY = config.anthropic_key
            if config.openai_key:
                cfg.OPENAI_API_KEY = config.openai_key
            self._aplicar_ajustes_avanzados(cfg, config.ajustes_avanzados)

            # Recalcular valores derivados para clientes externos.
            cfg.IA_TIEBREAK_MODEL = (
                cfg.IA_TIEBREAK_MODEL_OPENAI if cfg.IA_PROVEEDOR == "OpenAI"
                else cfg.IA_TIEBREAK_MODEL_ANTHROPIC if cfg.IA_PROVEEDOR == "Anthropic"
                else ""
            )
            cfg.ACOUSTID_API_KEY_RESOLVED = cfg._leer_clave_api("ACOUSTID_API_KEY", cfg.__dict__)
            cfg.ANTHROPIC_API_KEY_RESOLVED = cfg._leer_clave_api("ANTHROPIC_API_KEY", cfg.__dict__)
            cfg.OPENAI_API_KEY_RESOLVED = cfg._leer_clave_api("OPENAI_API_KEY", cfg.__dict__)

            from core.pipeline import PipelineCatalogacion
            self._control = ControlEjecucion(config.directorio_logs / "run_state.json")

            pipeline = PipelineCatalogacion(
                directorio_entrada    = config.directorio_entrada,
                directorio_biblioteca = config.directorio_biblioteca,
                directorio_quarantine = config.directorio_cuarentena,
                directorio_revision   = config.directorio_revision,
                directorio_logs       = config.directorio_logs,
                directorio_procesados = config.directorio_procesados,
                directorio_cache      = config.directorio_cache,
                directorio_temp       = config.directorio_temp,
                control               = self._control,
            )

            # Sobreescribir el metodo de barra de progreso para usar nuestros callbacks
            pipeline._barra = _BarraProgresoBridge(
                callback=self._notificar_progreso,
                cancelar_evento=self._cancelar,
            )

            resultado = pipeline.ejecutar()

            # Indexar archivos aceptados en la BD
            if not config.dry_run and resultado.total_aceptados > 0:
                indexador = IndexadorBiblioteca(config.directorio_biblioteca)
                indexador.ejecutar_rescan()

            # Registrar archivos en revision/cuarentena
            self._registrar_pendientes(
                config.directorio_revision,
                config.directorio_cuarentena,
                self._sesion_id,
            )

            # Actualizar sesion en BD
            resumen = _resumen_desde_resultado(resultado, dry_run=config.dry_run)
            self._cerrar_sesion(self._sesion_id, resumen, estado="completado")
            if not config.dry_run:
                self._programar_audio_deep_post_import()

            for cb in self._cb_completado:
                try:
                    cb(resumen)
                except Exception as exc:
                    _log.warning("Callback de importacion completada fallo: %s", exc)

        except KeyboardInterrupt:
            resumen = {"cancelada": True, "sesion_id": self._sesion_id}
            self._cerrar_sesion(self._sesion_id, resumen, estado="cancelado")
            for cb in self._cb_cancelado:
                try:
                    cb(resumen)
                except Exception as exc:
                    _log.warning("Callback de importacion cancelada fallo: %s", exc)
        except Exception as e:
            resumen = {"error": str(e), "sesion_id": self._sesion_id}
            self._cerrar_sesion(self._sesion_id, resumen, estado="error")
            for cb in self._cb_error:
                try:
                    cb(str(e))
                except Exception as exc:
                    _log.warning("Callback de error de importacion fallo: %s", exc)
        finally:
            self._control = None
            self._en_ejecucion = False

    def _programar_audio_deep_post_import(self) -> None:
        try:
            from core.audio_intelligence_background import (
                AudioIntelligenceBackgroundConfig,
                AudioIntelligenceBackgroundService,
            )

            cfg = AudioIntelligenceBackgroundConfig.load()
            if not (
                cfg.enabled
                and cfg.background_enabled
                and cfg.analyze_after_import_background
            ):
                return
            svc = AudioIntelligenceBackgroundService()
            snapshot = svc.enqueue_pending_tracks()
            if cfg.autostart and int(snapshot.get("pendientes") or 0) > 0:
                hilo = threading.Thread(
                    target=svc.process_pending,
                    kwargs={"idle_delay_sec": cfg.idle_delay_sec},
                    name="nb_sound_audio_deep_background",
                    daemon=True,
                )
                hilo.start()
        except Exception as exc:
            _log.warning("No se pudo programar Audio Intelligence deep background post-import: %s", exc)

    def _notificar_progreso(
        self, procesados: int, total: int, nombre: str, etapa: str
    ) -> None:
        for cb in self._cb_progreso:
            try:
                cb(procesados, total, nombre, etapa)
            except Exception as exc:
                _log.warning("Callback de progreso de importacion fallo: %s", exc)

    # ------------------------------------------------------------------
    # PERSISTENCIA DE SESION
    # ------------------------------------------------------------------

    def _crear_sesion(self, directorio_entrada: Path) -> int:
        return ejecutar_y_obtener_id(
            """
            INSERT INTO sesiones_import(directorio_entrada, estado)
            VALUES (?, 'en_progreso')
            """,
            (str(directorio_entrada),),
        )


    def _marcar_sesiones_huerfanas(self) -> None:
        marcar_sesiones_importacion_huerfanas()

    def _cerrar_sesion(self, sesion_id: Optional[int], resumen: dict, estado: str = "completado") -> None:
        if not sesion_id:
            return
        ejecutar(
            """
            UPDATE sesiones_import SET
                finalizado_en      = datetime('now'),
                total_descubiertos = ?,
                total_aceptados    = ?,
                total_revision     = ?,
                total_cuarentena   = ?,
                total_errores      = ?,
                estado             = ?,
                reporte_json       = ?
            WHERE id = ?
            """,
            (
                resumen.get("total_descubiertos", 0),
                resumen.get("total_aceptados", 0),
                resumen.get("total_revision", 0),
                resumen.get("total_cuarentena", 0),
                resumen.get("total_errores", 0),
                estado,
                json.dumps(resumen),
                sesion_id,
            ),
        )

    def _registrar_pendientes(
        self,
        dir_revision: Path,
        dir_cuarentena: Path,
        sesion_id: Optional[int],
    ) -> None:
        """Registra en archivos_pendientes los archivos en revision y cuarentena."""

        def _registrar_directorio(carpeta: Path, tipo: str) -> None:
            if not carpeta.exists():
                return
            for subcarpeta in carpeta.iterdir():
                if not subcarpeta.is_dir():
                    continue
                causa = subcarpeta.name
                manifiesto_ruta = subcarpeta / "_manifiesto.jsonl"
                manifiesto_texto = None
                if manifiesto_ruta.exists():
                    try:
                        manifiesto_texto = manifiesto_ruta.read_text(encoding="utf-8")
                    except Exception as _exc:
                        _log.debug("Excepcion ignorada en %s: %s", "importacion.py", _exc)

                for archivo in subcarpeta.glob("*.mp3"):
                    ejecutar(
                        """
                        INSERT OR IGNORE INTO archivos_pendientes
                            (ruta_archivo, nombre_archivo, tipo, causa, manifiesto_json, sesion_id)
                        VALUES (?,?,?,?,?,?)
                        """,
                        (
                            str(archivo), archivo.name, tipo,
                            causa, manifiesto_texto, sesion_id,
                        ),
                    )

        _registrar_directorio(dir_revision,   "revision")
        _registrar_directorio(dir_cuarentena, "cuarentena")


# =============================================================================
# PUENTE CON LA BARRA DE PROGRESO DEL PIPELINE
# =============================================================================

class _BarraProgresoBridge:
    """
    Implementa la interfaz de BarraProgreso esperada por el pipeline
    pero redirige el estado hacia los callbacks de la UI en lugar de
    imprimir en terminal.
    """

    def __init__(
        self,
        callback: TipoCallbackProgreso,
        cancelar_evento: threading.Event,
    ) -> None:
        self._callback        = callback
        self._cancelar        = cancelar_evento
        self._procesados      = 0
        self._total           = 0
        self._nombre_actual   = ""
        self._etapa_actual    = ""
        self._fase_label      = "Preparando"
        self._fase_actual     = 0
        self._fase_total      = 0
        self._extras: dict[str, dict[str, int]] = {}

    def iniciar(self) -> None:
        self._callback(0, self._total, "", "iniciando")

    def set_total_archivos(self, total: int) -> None:
        self._total = max(0, int(total))

    def finalizar(self) -> None:
        self._etapa_actual = "finalizado"
        self._emitir()

    def registrar_resultado(
        self,
        resultado: str,
        duracion_archivo_seg: Optional[float] = None,
    ) -> None:
        _ = duracion_archivo_seg  # Mantener compatibilidad de firma con BarraProgreso
        self._procesados += 1
        self._etapa_actual = resultado
        self._emitir()

    def actualizar_archivo(self, nombre: str, etapa: str) -> None:
        self._nombre_actual = nombre
        self._etapa_actual  = etapa
        self._emitir()
        # Verificar si se solicito cancelacion
        if self._cancelar.is_set():
            raise KeyboardInterrupt("Importacion cancelada por el usuario")

    def mensaje(self, texto: str, nivel: str = "info") -> None:
        self._etapa_actual = f"{nivel}: {texto}"
        self._emitir()

    def establecer_fase(
        self,
        phase_id: str,
        phase_label: str,
        total: Optional[int] = None,
        current: int = 0,
        current_item: str = "",
        current_task: str = "",
    ) -> None:
        _ = phase_id
        self._fase_label = phase_label
        self._fase_total = max(0, int(total or 0))
        self._fase_actual = max(0, int(current))
        if current_item:
            self._nombre_actual = current_item
        self._etapa_actual = self._formatear_estado_fase(current_task)
        self._emitir()

    def actualizar_fase(
        self,
        current: Optional[int] = None,
        total: Optional[int] = None,
        current_item: Optional[str] = None,
        current_task: Optional[str] = None,
        severity: str = "info",
    ) -> None:
        _ = severity
        if total is not None:
            self._fase_total = max(0, int(total))
        if current is not None:
            self._fase_actual = max(0, int(current))
        if current_item is not None:
            self._nombre_actual = current_item
        self._etapa_actual = self._formatear_estado_fase(current_task or self._etapa_actual)
        self._emitir()

    def heartbeat(self, texto: str = "") -> None:
        if texto:
            self._etapa_actual = texto
        self._emitir()

    def registrar_tarea_extra(self, tipo: str, nombre: str, descripcion: str = "") -> None:
        data = self._extras.setdefault(tipo, {"scheduled": 0, "done": 0, "pending": 0, "error": 0, "skipped": 0})
        data["scheduled"] += 1
        data["pending"] += 1
        self._nombre_actual = nombre
        self._etapa_actual = descripcion or self._formatear_extra(tipo, nombre, "programado")
        self._emitir()

    def finalizar_tarea_extra(
        self,
        tipo: str,
        nombre: str,
        ok: bool = True,
        detalle: str = "",
        duracion_seg: Optional[float] = None,
    ) -> None:
        _ = duracion_seg
        data = self._extras.setdefault(tipo, {"scheduled": 0, "done": 0, "pending": 0, "error": 0, "skipped": 0})
        data["done"] += 1
        data["pending"] = max(0, data["pending"] - 1)
        if not ok:
            data["error"] += 1
        estado = "ok" if ok else f"error {detalle}".strip()
        self._nombre_actual = nombre
        self._etapa_actual = self._formatear_extra(tipo, nombre, estado)
        self._emitir()

    def omitir_tarea_extra(self, tipo: str, nombre: str, razon: str = "") -> None:
        data = self._extras.setdefault(tipo, {"scheduled": 0, "done": 0, "pending": 0, "error": 0, "skipped": 0})
        data["skipped"] += 1
        self._nombre_actual = nombre
        self._etapa_actual = self._formatear_extra(tipo, nombre, f"omitido {razon}".strip())
        self._emitir()

    def _emitir(self) -> None:
        self._callback(self._procesados, self._total, self._nombre_actual, self._etapa_actual)
        if self._cancelar.is_set():
            raise KeyboardInterrupt("Importacion cancelada por el usuario")

    def _formatear_estado_fase(self, tarea: str = "") -> str:
        partes = [self._fase_label]
        if self._fase_total:
            partes.append(f"{min(self._fase_actual, self._fase_total)}/{self._fase_total}")
        if tarea:
            partes.append(str(tarea))
        extras = self._resumen_extras()
        if extras:
            partes.append(extras)
        return " · ".join(partes)

    def _formatear_extra(self, tipo: str, nombre: str, estado: str) -> str:
        return f"{self._fase_label} · {tipo}:{estado} · {nombre} · {self._resumen_extras()}"

    def _resumen_extras(self) -> str:
        partes = []
        for tipo, data in sorted(self._extras.items()):
            total = data.get("scheduled", 0)
            if total <= 0:
                continue
            hechos = data.get("done", 0)
            pendientes = data.get("pending", 0)
            partes.append(f"{tipo} {hechos}/{total}" + (f" pend:{pendientes}" if pendientes else ""))
        return " | ".join(partes)


def _resumen_desde_resultado(resultado, dry_run: bool) -> dict:
    """Normaliza el ResultadoEjecucion del core al contrato consumido por la UI."""
    total_aceptados_total = resultado.total_aceptados + resultado.total_aceptados_provisional
    return {
        "dry_run": dry_run,
        "total_descubiertos": resultado.total_descubiertos,
        "total_aceptados": total_aceptados_total,
        "total_aceptados_limpios": resultado.total_aceptados,
        "total_aceptados_provisionales": resultado.total_aceptados_provisional,
        "total_revision": resultado.total_revision,
        "total_cuarentena": resultado.total_cuarentena,
        "total_revision_inicial": resultado.total_revision_inicial,
        "total_cuarentena_inicial": resultado.total_cuarentena_inicial,
        "total_omitidos": resultado.total_omitidos,
        "total_errores": resultado.total_errores,
        "duracion_seg": resultado.duracion_total_seg,
        "porcentaje_exito": resultado.porcentaje_exito(),
        "consultas_mb": resultado.consultas_mb,
        "cache_hits": resultado.cache_hits,
        "reintentos_mb": resultado.reintentos_mb,
        "total_identificados_shazam": resultado.total_identificados_shazam,
        "total_identificados_acoustid": resultado.total_identificados_acoustid,
        "total_desempatados_ia": resultado.total_desempatados_ia,
        "total_isrc_usados": resultado.total_isrc_usados,
        "segunda_fase_habilitada": resultado.segunda_fase_habilitada,
        "segunda_fase_elegibles": resultado.segunda_fase_elegibles,
        "segunda_fase_excluidos": resultado.segunda_fase_excluidos,
        "segunda_fase_resueltos": resultado.segunda_fase_resueltos,
        "segunda_fase_duracion_seg": resultado.segunda_fase_duracion_seg,
    }
