# =============================================================================
# servicios/karaoke/cola.py
#
# Orquestador de la cola karaoke. Procesa jobs uno a la vez (decision
# explicita: dos jobs Demucs paralelos saturan CPU y degradan ambos).
#
# Diseno:
#   - `procesar_cola()` corre en un hilo background (lo invoca el worker Qt).
#   - Emite snapshots de progreso via callback (no senales Qt: este modulo
#     es puro Python para ser testeable sin Qt).
#   - Cancelacion cooperativa via `stop_event`.
#   - Persistencia total via `jobs_repo`: si la app se cae, la cola sigue
#     ahi (jobs `procesando`/`generando` se quedan colgados; se limpian al
#     proximo arranque).
# =============================================================================

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional, TypedDict

from infra.logger import obtener_logger

from . import jobs_repo, rutas, backend
from .errores import (
    ArchivoNoExisteError,
    AudioCorruptoError,
    FfmpegFaltanteError,
    KaraokeCanceladoError,
    KaraokeError,
    MemoriaInsuficienteError,
    ModeloFaltanteError,
)
from .separador import separar_pista_instrumental

_log = obtener_logger("servicios.karaoke.cola")

# ── Tipos ────────────────────────────────────────────────────────────────────

class SnapshotProceso(TypedDict, total=False):
    estado: str          # inactivo | preparando | procesando | completado | cancelado | error
    procesando: bool
    backend: str
    device: str
    modelo: str
    total: int
    procesadas: int
    ready: int
    failed: int
    cancelled: int
    pendientes: int
    porcentaje: float    # porcentaje global (jobs completados)
    porcentaje_job: float  # progreso del job actual
    pista_actual: str
    job_id_actual: int
    eta: str
    eta_seg: float
    velocidad: float
    mensaje: str
    warning: str
    error_codigo: str

ProgressCb = Callable[[SnapshotProceso], None]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_eta(seg: float) -> str:
    if seg <= 0:
        return ""
    s = int(seg)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}min"
    if m > 0:
        return f"{m}min {s}s"
    return f"{s}s"


def _snapshot(
    estado: str, *,
    procesadas: int, total: int, ready: int, failed: int, cancelled: int,
    pista_actual: str = "", job_id_actual: int = 0,
    porcentaje_job: float = 0.0,
    backend_nombre: str = "", device: str = "", modelo: str = "",
    inicio_ts: float = 0.0,
    inicio_job_ts: float = 0.0,
    mensaje: str = "", warning: str = "", error_codigo: str = "",
) -> SnapshotProceso:
    """Construye un snapshot del estado de la cola.

    El ETA se calcula con la mejor estimacion disponible:

    1. Si ya hay >=1 pista completa, usamos la media real (tiempo_total /
       procesadas) × pendientes.
    2. Si no, pero la pista actual ya tiene progreso medible (>5%), usamos
       el tiempo gastado en ESTE job para extrapolar el job actual y los
       pendientes que vienen detras.
    3. Si ni siquiera tenemos eso, devolvemos "calculando..." sin numero.

    Asi la ETA aparece desde los primeros segundos y no espera a que termine
    el primer job.
    """
    pendientes = max(0, total - procesadas)
    now = time.monotonic()
    eta_seg = -1.0
    velocidad = 0.0

    if procesadas > 0 and inicio_ts > 0:
        elapsed = max(0.001, now - inicio_ts)
        seg_por_pista = elapsed / procesadas
        velocidad = round(60.0 / seg_por_pista, 2)
        eta_seg = seg_por_pista * pendientes
    elif (porcentaje_job > 0.05 and inicio_job_ts > 0.0 and pendientes > 0):
        # Sin pista completa todavia, pero el job actual progresa.
        elapsed_job = max(0.001, now - inicio_job_ts)
        seg_por_pista_estimado = elapsed_job / porcentaje_job
        velocidad = round(60.0 / seg_por_pista_estimado, 2)
        # Falta lo que queda del job actual + el resto de pendientes -1.
        eta_seg = seg_por_pista_estimado * (1.0 - porcentaje_job) + \
                  seg_por_pista_estimado * max(0, pendientes - 1)
    eta_human = _fmt_eta(eta_seg) if eta_seg > 0 else ("calculando..." if pendientes > 0 else "")
    porc_global = min(1.0, procesadas / max(1, total)) if total > 0 else 0.0
    return {
        "estado":          estado,
        "procesando":      estado in {"preparando", "procesando"},
        "backend":         backend_nombre,
        "device":          device,
        "modelo":          modelo,
        "total":           total,
        "procesadas":      procesadas,
        "ready":           ready,
        "failed":          failed,
        "cancelled":       cancelled,
        "pendientes":      pendientes,
        "porcentaje":      porc_global,
        "porcentaje_job":  max(0.0, min(1.0, porcentaje_job)),
        "pista_actual":    pista_actual,
        "job_id_actual":   int(job_id_actual or 0),
        "eta":             eta_human,
        "eta_seg":         eta_seg,
        "velocidad":       velocidad,
        "mensaje":         mensaje,
        "warning":         warning,
        "error_codigo":    error_codigo,
    }


def _peso_demucs_presente(modelos_dir: Path, nombre_modelo: str) -> bool:
    """Heurística: ¿hay pesos en `modelos_dir/hub/checkpoints/`?

    No verifica integridad — solo presencia. Sirve para distinguir
    "no descargado todavía" vs "descargado pero algo más falla", que
    es la diferencia importante para elegir el mensaje al usuario.
    """
    try:
        checkpoints = modelos_dir / "hub" / "checkpoints"
        if not checkpoints.is_dir():
            return False
        return any(checkpoints.glob("*.th"))
    except Exception:
        return False


def _codigo_para_excepcion(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, KaraokeError):
        return exc.codigo, str(exc)
    return "error_desconocido", str(exc) or exc.__class__.__name__


# ── API publica ──────────────────────────────────────────────────────────────

def limpiar_jobs_zombies() -> int:
    """Marca como cancelados jobs que quedaron en estados intermedios
    (procesando/generando/preparando) tras un crash o cierre forzado.

    Usar al iniciar el worker para empezar limpio.
    """
    from db.conexion import transaccion
    with transaccion() as con:
        cur = con.execute(
            """
            UPDATE karaoke_jobs
            SET estado='cancelada', finalizado_en=datetime('now'),
                actualizado_en=datetime('now'),
                error_codigo='cancelado', error_mensaje='Recuperado tras reinicio'
            WHERE estado IN ('preparando','procesando','generando')
            """,
        )
        afectados = int(cur.rowcount or 0)
        if afectados > 0:
            con.execute(
                """
                UPDATE pistas
                SET karaoke_estado='no_procesada',
                    karaoke_actualizado_en=datetime('now')
                WHERE karaoke_estado='procesando'
                """,
            )
        return afectados


def procesar_cola(
    cache_dir: Path,
    *,
    device_pref: str = "auto",
    nombre_modelo: str = "htdemucs",
    progress_callback: Optional[ProgressCb] = None,
    stop_event: Optional[threading.Event] = None,
) -> SnapshotProceso:
    """Procesa todos los jobs `en_cola` secuencialmente.

    Retorna el snapshot final. No lanza excepciones: las captura por job
    y las persiste en `karaoke_jobs.error_*`. Solo lanza si la validacion
    inicial del backend falla (sin demucs/ffmpeg) -> snapshot con
    `estado='error'`.

    `stop_event.set()` cancela el job activo (queda `cancelada`) y termina
    el bucle sin tocar los siguientes (siguen `en_cola`).
    """
    progress_callback = progress_callback or (lambda _s: None)
    inicio_ts = time.monotonic()

    # 0) Limpieza de zombies y validacion previa.
    zombies = limpiar_jobs_zombies()
    if zombies:
        _log.info("Limpieza inicial: %d job(s) zombies marcados cancelados.", zombies)

    diag = backend.diagnostico()
    backend_nombre = "demucs"
    if not diag["backend_listo"]:
        snap_err = _snapshot(
            "error",
            procesadas=0, total=0, ready=0, failed=0, cancelled=0,
            mensaje=diag["mensaje"],
            warning=diag["instrucciones"],
            backend_nombre=backend_nombre, device=diag["device_disponible"],
            error_codigo="backend_no_disponible" if not diag["demucs_disponible"] else "ffmpeg_faltante",
        )
        progress_callback(snap_err)
        return snap_err

    device = backend.seleccionar_device(device_pref)
    modelos_dir = rutas.directorio_modelos(cache_dir)

    # Pre-carga del modelo (descarga si hace falta). Damos feedback de UI.
    progress_callback(_snapshot(
        "preparando",
        procesadas=0, total=jobs_repo.contar_pendientes(),
        ready=0, failed=0, cancelled=0,
        backend_nombre=backend_nombre, device=device, modelo=nombre_modelo,
        inicio_ts=inicio_ts,
        mensaje="Preparando modelo de separacion...",
    ))
    try:
        from .modelo import cargar_modelo
        cargar_modelo(modelos_dir, nombre_modelo)
    except KaraokeError as exc:
        codigo, mensaje = _codigo_para_excepcion(exc)
        detalle_tecnico = str(getattr(exc, "detalle", "") or "")[:1000]
        _log.error(
            "Karaoke: cargar_modelo(%s, %s) fallo (codigo=%s): %s | detalle=%s",
            modelos_dir, nombre_modelo, codigo, mensaje, detalle_tecnico,
        )
        # El mensaje secundario depende del codigo real, no un "verifica
        # conexion" fijo. Si los pesos ya estan en disco pero get_model
        # falla por otra razon (ABI clash, torch corrupto, etc.), decirle
        # al usuario "revisa conexion" lo confunde.
        if codigo == "modelo_faltante" and not _peso_demucs_presente(modelos_dir, nombre_modelo):
            warning = (
                "Conecta a Internet para que la app descargue el modelo "
                "(~80 MB la primera vez)."
            )
        else:
            warning = (
                "El modelo esta descargado pero `demucs.pretrained.get_model` "
                "falla al cargarlo. Revisa los logs (busca 'cargar_modelo')."
            )
        snap_err = _snapshot(
            "error",
            procesadas=0, total=0, ready=0, failed=0, cancelled=0,
            backend_nombre=backend_nombre, device=device, modelo=nombre_modelo,
            mensaje=mensaje,
            warning=warning,
            error_codigo=codigo,
        )
        progress_callback(snap_err)
        return snap_err
    except Exception as exc:
        # Cualquier otra excepcion no esperada (import fail, ABI clash,
        # OOM al primer load) debe quedar en el log para diagnostico,
        # no enmascarada como un error generico.
        import traceback
        _log.error(
            "Karaoke: cargar_modelo(%s, %s) excepcion no clasificada: %s\n%s",
            modelos_dir, nombre_modelo, exc, traceback.format_exc()[-2000:],
        )
        snap_err = _snapshot(
            "error",
            procesadas=0, total=0, ready=0, failed=0, cancelled=0,
            backend_nombre=backend_nombre, device=device, modelo=nombre_modelo,
            mensaje=f"No se pudo cargar el modelo: {exc}",
            warning="Revisa los logs para el traceback completo.",
            error_codigo="cargar_modelo_excepcion",
        )
        progress_callback(snap_err)
        return snap_err

    # 1) Procesar uno a uno.
    procesadas = 0
    ready = 0
    failed = 0
    cancelled = 0
    total_inicial = jobs_repo.contar_pendientes()

    if total_inicial == 0:
        snap_final = _snapshot(
            "completado",
            procesadas=0, total=0, ready=0, failed=0, cancelled=0,
            backend_nombre=backend_nombre, device=device, modelo=nombre_modelo,
            mensaje="No hay pistas en cola.",
        )
        progress_callback(snap_final)
        return snap_final

    _log.info("Karaoke cola: total=%d device=%s modelo=%s",
              total_inicial, device, nombre_modelo)

    while True:
        if stop_event is not None and stop_event.is_set():
            break

        job = jobs_repo.siguiente_job()
        if not job:
            break

        job_id = int(job["id"])
        pista_id = int(job["pista_id"])
        titulo = str(job.get("titulo") or "")
        ruta_audio = str(job.get("ruta_archivo") or "")

        # Transicionar a `preparando` (inicia el reloj del job).
        jobs_repo.transicionar_estado(job_id, "preparando", device=device)
        inicio_job_ts = time.monotonic()

        progress_callback(_snapshot(
            "procesando",
            procesadas=procesadas, total=total_inicial,
            ready=ready, failed=failed, cancelled=cancelled,
            pista_actual=titulo, job_id_actual=job_id,
            porcentaje_job=0.0,
            backend_nombre=backend_nombre, device=device, modelo=nombre_modelo,
            inicio_ts=inicio_ts, inicio_job_ts=inicio_job_ts,
            mensaje=f"Procesando: {titulo}",
        ))

        salida = rutas.ruta_instrumental_para_pista(cache_dir, pista_id, ruta_audio)
        tmp_dir = rutas.directorio_temporal_para_job(cache_dir, job_id)

        # Si ya existe el archivo en cache y tiene contenido, lo reusamos.
        if salida.exists() and salida.stat().st_size > 1024:
            _log.info("Cache hit pista=%d -> %s", pista_id, salida)
            jobs_repo.marcar_lista(
                job_id, str(salida),
                bytes_salida=salida.stat().st_size,
                duracion_proc_ms=0,
            )
            ready += 1
            procesadas += 1
            progress_callback(_snapshot(
                "procesando",
                procesadas=procesadas, total=total_inicial,
                ready=ready, failed=failed, cancelled=cancelled,
                pista_actual=titulo, job_id_actual=job_id,
                porcentaje_job=1.0,
                backend_nombre=backend_nombre, device=device, modelo=nombre_modelo,
                inicio_ts=inicio_ts, inicio_job_ts=inicio_job_ts,
                mensaje=f"Cache hit: {titulo}",
            ))
            continue

        jobs_repo.transicionar_estado(job_id, "procesando", progreso=0.0, device=device)

        def _on_progress(p: float, _job_id=job_id, _titulo=titulo, _inicio_job=inicio_job_ts):
            jobs_repo.actualizar_progreso(_job_id, p)
            progress_callback(_snapshot(
                "procesando",
                procesadas=procesadas, total=total_inicial,
                ready=ready, failed=failed, cancelled=cancelled,
                pista_actual=_titulo, job_id_actual=_job_id,
                porcentaje_job=p,
                backend_nombre=backend_nombre, device=device, modelo=nombre_modelo,
                inicio_ts=inicio_ts, inicio_job_ts=_inicio_job,
                mensaje=f"Procesando: {_titulo}",
            ))

        try:
            metricas = separar_pista_instrumental(
                Path(ruta_audio), salida,
                directorio_modelos=modelos_dir,
                directorio_temporal=tmp_dir,
                nombre_modelo=nombre_modelo,
                device=device,
                stop_event=stop_event,
                progress_cb=_on_progress,
            )
        except KaraokeCanceladoError:
            jobs_repo.marcar_cancelado(
                job_id, restaurar_estado_pista="no_procesada",
                mensaje="Procesamiento cancelado",
            )
            cancelled += 1
            procesadas += 1
            # Limpieza de tmp
            try:
                import shutil as _sh
                _sh.rmtree(tmp_dir, ignore_errors=True)
            except Exception as _exc:
                _log.debug("Excepcion ignorada en %s: %s", "cola.py", _exc)
            break
        except (ArchivoNoExisteError, AudioCorruptoError,
                FfmpegFaltanteError, ModeloFaltanteError,
                MemoriaInsuficienteError) as exc:
            codigo, mensaje = _codigo_para_excepcion(exc)
            detalle = str(getattr(exc, "detalle", "") or "")[:1500]
            _log.warning(
                "Job %d fallo (%s): %s | ruta=%s | detalle=%s",
                job_id, codigo, mensaje, ruta_audio, detalle,
            )
            jobs_repo.marcar_fallido(
                job_id, error_codigo=codigo,
                error_mensaje=f"{mensaje} | {detalle}" if detalle else mensaje,
            )
            failed += 1
            procesadas += 1
        except Exception as exc:
            _log.exception("Job %d error inesperado", job_id)
            jobs_repo.marcar_fallido(
                job_id, error_codigo="error_desconocido",
                error_mensaje=str(exc) or exc.__class__.__name__,
            )
            failed += 1
            procesadas += 1
        else:
            jobs_repo.marcar_lista(
                job_id, str(salida),
                bytes_salida=int(metricas["bytes"]),
                duracion_proc_ms=int(metricas["duracion_proc_ms"]),
            )
            ready += 1
            procesadas += 1
        finally:
            try:
                import shutil as _sh
                _sh.rmtree(tmp_dir, ignore_errors=True)
            except Exception as _exc:
                _log.debug("Excepcion ignorada en %s: %s", "cola.py", _exc)

    # 2) Snapshot final.
    estado_final = "cancelado" if stop_event is not None and stop_event.is_set() else "completado"
    snap_final = _snapshot(
        estado_final,
        procesadas=procesadas, total=total_inicial,
        ready=ready, failed=failed, cancelled=cancelled,
        backend_nombre=backend_nombre, device=device, modelo=nombre_modelo,
        inicio_ts=inicio_ts,
        mensaje=f"Listas: {ready} · fallidas: {failed} · canceladas: {cancelled}",
    )
    progress_callback(snap_final)
    _log.info(
        "Cola karaoke terminada: estado=%s ready=%d failed=%d cancelled=%d",
        estado_final, ready, failed, cancelled,
    )
    return snap_final
