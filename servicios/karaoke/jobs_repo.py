# =============================================================================
# servicios/karaoke/jobs_repo.py
#
# Capa de persistencia para `karaoke_jobs`. Funciones pequenas, una
# responsabilidad cada una: encolar, transicionar estado, sacar el siguiente
# de la cola, limpiar, contar.
#
# La tabla pistas.karaoke_* se mantiene sincronizada como cache desnormalizado
# del estado del job vigente, para que el reproductor lo consulte sin JOIN.
# =============================================================================

from __future__ import annotations

from typing import Iterable, Optional

from db.conexion import (
    ejecutar,
    obtener_filas,
    obtener_una_fila,
    transaccion,
)
from infra.logger import obtener_logger

_log = obtener_logger("servicios.karaoke.jobs_repo")

# Estados validos de un job individual.
ESTADOS_JOB = frozenset({
    "en_cola", "preparando", "procesando", "generando",
    "lista", "fallida", "cancelada",
})

# Estados desde los que se considera que un job esta "activo" (consume
# espacio en la cola). Si reencolas una pista, sus jobs activos quedan
# cancelados antes de crear uno nuevo.
ESTADOS_ACTIVOS = frozenset({"en_cola", "preparando", "procesando", "generando"})

# Estados validos de la columna pistas.karaoke_estado (cache desnormalizado).
ESTADOS_PISTA = frozenset({
    "no_procesada", "en_cola", "procesando", "lista", "fallida", "no_aplica",
})

# Mapeo de estado de job -> estado de pista (desnormalizado).
_PISTA_DESDE_JOB: dict[str, str] = {
    "en_cola":    "en_cola",
    "preparando": "procesando",
    "procesando": "procesando",
    "generando":  "procesando",
    "lista":      "lista",
    "fallida":    "fallida",
    # `cancelada` no figura: al cancelar, la pista vuelve a un estado base
    # (no_procesada por defecto, salvo que el llamador especifique otro).
}


def estado_pista_desde_job(estado_job: str) -> Optional[str]:
    """Estado desnormalizado para la pista a partir del estado del job."""
    return _PISTA_DESDE_JOB.get(estado_job)


# ── Inserts/Updates ──────────────────────────────────────────────────────────

def encolar(pista_id: int, *, max_intentos: int = 2, modelo: str = "htdemucs",
            backend: str = "demucs") -> Optional[int]:
    """Crea un job en estado `en_cola` para la pista indicada.

    Semantica:
      - Devuelve el id del job recien creado si la operacion creo uno.
      - Devuelve None si la pista no se puede encolar (no existe, esta marcada
        `no_aplica`, o ya tiene un job activo).
    """
    if int(pista_id) <= 0:
        return None
    with transaccion() as con:
        fila_pista = con.execute(
            "SELECT karaoke_estado FROM pistas WHERE id = ? AND estado = 'biblioteca'",
            (pista_id,),
        ).fetchone()
        if not fila_pista:
            return None
        if fila_pista["karaoke_estado"] == "no_aplica":
            return None

        # Si ya hay un job activo, no se crea otro.
        ya = con.execute(
            """
            SELECT id FROM karaoke_jobs
            WHERE pista_id = ? AND estado IN ('en_cola','preparando','procesando','generando')
            ORDER BY id DESC LIMIT 1
            """,
            (pista_id,),
        ).fetchone()
        if ya:
            return None

        cur = con.execute(
            """
            INSERT INTO karaoke_jobs(
                pista_id, estado, intento, max_intentos, modelo, backend,
                progreso, creado_en, actualizado_en
            )
            VALUES (?, 'en_cola', 0, ?, ?, ?, 0.0, datetime('now'), datetime('now'))
            """,
            (pista_id, max_intentos, modelo, backend),
        )
        # Sincronizar cache de la pista.
        con.execute(
            """
            UPDATE pistas
            SET karaoke_estado = 'en_cola',
                karaoke_actualizado_en = datetime('now'),
                karaoke_error_codigo = NULL,
                karaoke_error_mensaje = NULL
            WHERE id = ?
            """,
            (pista_id,),
        )
        return int(cur.lastrowid)


def encolar_muchas(pista_ids: Iterable[int], **kwargs) -> int:
    """Encola varias pistas. Retorna cuantos jobs nuevos se crearon."""
    creados = 0
    for pid in pista_ids:
        try:
            if encolar(int(pid), **kwargs):
                creados += 1
        except Exception as exc:
            _log.warning("encolar(%s) fallo: %s", pid, exc)
    return creados


def encolar_todas_sin_preparar(**kwargs) -> int:
    """Encola todas las pistas en estado `no_procesada` o `fallida`."""
    filas = obtener_filas(
        """
        SELECT id FROM pistas
        WHERE estado='biblioteca' AND karaoke_estado IN ('no_procesada','fallida')
        """
    )
    return encolar_muchas((f["id"] for f in filas), **kwargs)


def cancelar_pista(pista_id: int, *, mensaje: str = "Cancelado por el usuario") -> bool:
    """Cancela el karaoke de una pista en CUALQUIER estado activo y reconcilia.

    A diferencia de :func:`sacar_de_cola` (solo 'en_cola') y de
    :func:`marcar_cancelado` (por job_id), esta función es robusta ante la
    desincronización que el usuario reportaba: una pista podía quedar marcada
    'procesando'/'en_cola' en su cache mientras el job real estaba en otro
    estado o ya no existía (un "procesando falso" colgado tras un cierre
    forzado o un worker que murió). En ese caso los botones por estado no hacían
    nada. Aquí:

      1. Se cancela cualquier job activo de la pista (en_cola/preparando/
         procesando/generando), sin exigir un estado exacto.
      2. Se devuelve la pista a 'no_procesada' SIEMPRE que su cache esté en un
         estado activo, aunque no hubiera ningún job vivo que cancelar.

    Devuelve True si cambió algo (job cancelado o cache reconciliado). La
    interrupción del worker, si esta pista es la que se procesa ahora mismo, la
    coordina la capa de modelo (este módulo no conoce hilos Qt).
    """
    cambiado = False
    with transaccion() as con:
        cur_job = con.execute(
            """
            UPDATE karaoke_jobs
            SET estado='cancelada', finalizado_en=datetime('now'),
                actualizado_en=datetime('now'),
                error_codigo='cancelado', error_mensaje=?
            WHERE pista_id = ? AND estado IN ('en_cola','preparando','procesando','generando')
            """,
            (mensaje[:500], pista_id),
        )
        if (cur_job.rowcount or 0) > 0:
            cambiado = True
        # Reconciliar el cache desnormalizado aunque no hubiera job vivo: ese es
        # justo el caso del 'procesando falso' que dejaba el botón inservible.
        cur_pista = con.execute(
            """
            UPDATE pistas
            SET karaoke_estado='no_procesada',
                karaoke_actualizado_en=datetime('now'),
                karaoke_error_codigo=NULL, karaoke_error_mensaje=NULL
            WHERE id = ? AND karaoke_estado IN ('en_cola','procesando')
            """,
            (pista_id,),
        )
        if (cur_pista.rowcount or 0) > 0:
            cambiado = True
    return cambiado


def sacar_de_cola(pista_id: int) -> bool:
    """Cancela el job `en_cola` (si existe) y devuelve la pista a `no_procesada`.

    No cancela jobs que ya estan en procesamiento — para eso usa
    `marcar_cancelado`.
    """
    with transaccion() as con:
        cur = con.execute(
            """
            UPDATE karaoke_jobs
            SET estado='cancelada', finalizado_en=datetime('now'),
                actualizado_en=datetime('now'),
                error_codigo='cancelado', error_mensaje='Sacada de cola'
            WHERE pista_id = ? AND estado = 'en_cola'
            """,
            (pista_id,),
        )
        if cur.rowcount <= 0:
            return False
        con.execute(
            """
            UPDATE pistas
            SET karaoke_estado='no_procesada',
                karaoke_actualizado_en=datetime('now'),
                karaoke_error_codigo=NULL, karaoke_error_mensaje=NULL
            WHERE id = ?
            """,
            (pista_id,),
        )
        return True


def vaciar_cola() -> int:
    """Cancela TODOS los jobs `en_cola`. No toca los que estan procesandose.

    Las pistas afectadas vuelven a `no_procesada`. Retorna cuantos se afectaron.
    """
    with transaccion() as con:
        cur = con.execute(
            """
            UPDATE karaoke_jobs
            SET estado='cancelada', finalizado_en=datetime('now'),
                actualizado_en=datetime('now'),
                error_codigo='cancelado', error_mensaje='Cola vaciada'
            WHERE estado = 'en_cola'
            """,
        )
        afectados = int(cur.rowcount or 0)
        if afectados > 0:
            con.execute(
                """
                UPDATE pistas
                SET karaoke_estado='no_procesada',
                    karaoke_actualizado_en=datetime('now'),
                    karaoke_error_codigo=NULL, karaoke_error_mensaje=NULL
                WHERE karaoke_estado='en_cola'
                """,
            )
        return afectados


def siguiente_job() -> Optional[dict]:
    """Saca el siguiente job `en_cola` (FIFO por creado_en, id)."""
    fila = obtener_una_fila(
        """
        SELECT j.*, p.titulo, p.ruta_archivo, p.artista_nombre
        FROM karaoke_jobs j
        JOIN pistas p ON p.id = j.pista_id
        WHERE j.estado = 'en_cola' AND p.estado = 'biblioteca'
        ORDER BY j.creado_en ASC, j.id ASC
        LIMIT 1
        """
    )
    return dict(fila) if fila else None


def transicionar_estado(job_id: int, nuevo_estado: str, *, progreso: Optional[float] = None,
                        device: Optional[str] = None) -> bool:
    """Cambia el estado de un job. Sincroniza la pista si aplica."""
    if nuevo_estado not in ESTADOS_JOB:
        return False
    with transaccion() as con:
        partes = ["estado = ?", "actualizado_en = datetime('now')"]
        params: list = [nuevo_estado]
        if nuevo_estado == "preparando":
            partes.append("iniciado_en = COALESCE(iniciado_en, datetime('now'))")
            partes.append("intento = intento + 1")
        if progreso is not None:
            partes.append("progreso = ?")
            params.append(max(0.0, min(1.0, float(progreso))))
        if device is not None:
            partes.append("device = ?")
            params.append(device)
        params.append(job_id)

        cur = con.execute(
            f"UPDATE karaoke_jobs SET {', '.join(partes)} WHERE id = ?",
            params,
        )
        if cur.rowcount <= 0:
            return False
        # Sincronizar cache de pista si corresponde.
        estado_pista = estado_pista_desde_job(nuevo_estado)
        if estado_pista:
            pista_id = con.execute(
                "SELECT pista_id FROM karaoke_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if pista_id:
                con.execute(
                    """
                    UPDATE pistas
                    SET karaoke_estado = ?,
                        karaoke_actualizado_en = datetime('now')
                    WHERE id = ?
                    """,
                    (estado_pista, pista_id["pista_id"]),
                )
        return True


def actualizar_progreso(job_id: int, progreso: float) -> None:
    """Update suave de progreso (no transiciona estado)."""
    p = max(0.0, min(1.0, float(progreso)))
    try:
        ejecutar(
            "UPDATE karaoke_jobs SET progreso = ?, actualizado_en = datetime('now') WHERE id = ?",
            (p, job_id),
        )
    except Exception as exc:
        _log.warning("actualizar_progreso(%s) fallo: %s", job_id, exc)


def marcar_lista(job_id: int, ruta_salida: str, *, bytes_salida: int,
                 duracion_proc_ms: int) -> bool:
    """Marca el job como completado con exito y sincroniza la pista."""
    with transaccion() as con:
        cur = con.execute(
            """
            UPDATE karaoke_jobs
            SET estado='lista', progreso=1.0,
                ruta_salida=?, bytes_salida=?, duracion_proc_ms=?,
                finalizado_en=datetime('now'), actualizado_en=datetime('now'),
                error_codigo=NULL, error_mensaje=NULL
            WHERE id = ?
            """,
            (ruta_salida, int(bytes_salida), int(duracion_proc_ms), job_id),
        )
        if cur.rowcount <= 0:
            return False
        fila = con.execute(
            "SELECT pista_id FROM karaoke_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if fila:
            con.execute(
                """
                UPDATE pistas
                SET karaoke_estado='lista',
                    karaoke_ruta_instrumental=?,
                    karaoke_actualizado_en=datetime('now'),
                    karaoke_error_codigo=NULL, karaoke_error_mensaje=NULL
                WHERE id = ?
                """,
                (ruta_salida, fila["pista_id"]),
            )
        return True


def marcar_fallido(job_id: int, *, error_codigo: str, error_mensaje: str) -> bool:
    with transaccion() as con:
        cur = con.execute(
            """
            UPDATE karaoke_jobs
            SET estado='fallida', finalizado_en=datetime('now'),
                actualizado_en=datetime('now'),
                error_codigo=?, error_mensaje=?
            WHERE id = ?
            """,
            (error_codigo, error_mensaje[:500], job_id),
        )
        if cur.rowcount <= 0:
            return False
        fila = con.execute(
            "SELECT pista_id FROM karaoke_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if fila:
            con.execute(
                """
                UPDATE pistas
                SET karaoke_estado='fallida',
                    karaoke_actualizado_en=datetime('now'),
                    karaoke_error_codigo=?, karaoke_error_mensaje=?
                WHERE id = ?
                """,
                (error_codigo, error_mensaje[:500], fila["pista_id"]),
            )
        return True


def marcar_cancelado(job_id: int, *, restaurar_estado_pista: str = "no_procesada",
                     mensaje: str = "Procesamiento cancelado") -> bool:
    """Cancela un job en curso y devuelve la pista al estado indicado."""
    if restaurar_estado_pista not in ESTADOS_PISTA:
        restaurar_estado_pista = "no_procesada"
    with transaccion() as con:
        cur = con.execute(
            """
            UPDATE karaoke_jobs
            SET estado='cancelada', finalizado_en=datetime('now'),
                actualizado_en=datetime('now'),
                error_codigo='cancelado', error_mensaje=?
            WHERE id = ?
            """,
            (mensaje[:500], job_id),
        )
        if cur.rowcount <= 0:
            return False
        fila = con.execute(
            "SELECT pista_id FROM karaoke_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if fila:
            con.execute(
                """
                UPDATE pistas
                SET karaoke_estado=?,
                    karaoke_actualizado_en=datetime('now'),
                    karaoke_error_codigo=NULL, karaoke_error_mensaje=NULL
                WHERE id = ?
                """,
                (restaurar_estado_pista, fila["pista_id"]),
            )
        return True


# ── Consultas ────────────────────────────────────────────────────────────────

def job_por_id(job_id: int) -> Optional[dict]:
    fila = obtener_una_fila("SELECT * FROM karaoke_jobs WHERE id = ?", (job_id,))
    return dict(fila) if fila else None


def job_activo_por_pista(pista_id: int) -> Optional[dict]:
    fila = obtener_una_fila(
        """
        SELECT * FROM karaoke_jobs
        WHERE pista_id = ? AND estado IN ('en_cola','preparando','procesando','generando')
        ORDER BY id DESC LIMIT 1
        """,
        (pista_id,),
    )
    return dict(fila) if fila else None


def ultimo_job_por_pista(pista_id: int) -> Optional[dict]:
    fila = obtener_una_fila(
        "SELECT * FROM karaoke_jobs WHERE pista_id = ? ORDER BY id DESC LIMIT 1",
        (pista_id,),
    )
    return dict(fila) if fila else None


def contar_pendientes() -> int:
    fila = obtener_una_fila(
        "SELECT COUNT(*) AS n FROM karaoke_jobs WHERE estado = 'en_cola'"
    )
    return int(fila["n"]) if fila else 0


def listar_cola() -> list[dict]:
    """Lista los jobs `en_cola` ordenados FIFO, con datos basicos de la pista."""
    filas = obtener_filas(
        """
        SELECT j.id AS job_id, j.pista_id, j.estado, j.intento, j.max_intentos,
               j.progreso, j.creado_en, p.titulo, p.artista_nombre
        FROM karaoke_jobs j
        JOIN pistas p ON p.id = j.pista_id
        WHERE j.estado IN ('en_cola','preparando','procesando','generando')
        ORDER BY j.creado_en ASC, j.id ASC
        """
    )
    return [dict(f) for f in filas]


def resumen_jobs() -> dict:
    """Cuenta jobs por estado. Usado por la UI para el panel de stats."""
    filas = obtener_filas(
        "SELECT estado, COUNT(*) AS n FROM karaoke_jobs GROUP BY estado"
    )
    base = {e: 0 for e in ESTADOS_JOB}
    for f in filas:
        if f["estado"] in base:
            base[f["estado"]] = int(f["n"])
    base["total"] = sum(base.values())
    return base


def resetear_estado_pista(pista_id: int) -> bool:
    """Cancela jobs activos de una pista y la deja en `no_procesada`.

    No borra archivos del cache; la siguiente encolada reutilizara el
    mismo destino. Para forzar un nuevo procesamiento desde cero, usa
    `marcar_para_reprocesar`.
    """
    with transaccion() as con:
        con.execute(
            """
            UPDATE karaoke_jobs
            SET estado='cancelada', finalizado_en=datetime('now'),
                actualizado_en=datetime('now'),
                error_codigo='cancelado', error_mensaje='Reset manual'
            WHERE pista_id = ? AND estado IN ('en_cola','preparando','procesando','generando')
            """,
            (pista_id,),
        )
        con.execute(
            """
            UPDATE pistas
            SET karaoke_estado='no_procesada',
                karaoke_ruta_instrumental=NULL,
                karaoke_actualizado_en=datetime('now'),
                karaoke_error_codigo=NULL, karaoke_error_mensaje=NULL
            WHERE id = ? AND estado = 'biblioteca'
            """,
            (pista_id,),
        )
        return True


def marcar_para_reprocesar(pista_id: int) -> Optional[int]:
    """Fuerza reprocesar una pista `lista`: borra el cache y crea un nuevo job.

    A diferencia de `encolar()` simple, esta funcion garantiza que el
    separador NO va a hacer cache hit con el archivo previo: lo elimina
    explicitamente. Devuelve el id del nuevo job, o None si no procede.
    """
    if int(pista_id) <= 0:
        return None
    # Borrar archivo de instrumental existente (si lo hay) antes de encolar.
    fila = obtener_una_fila(
        "SELECT karaoke_ruta_instrumental FROM pistas WHERE id = ? AND estado='biblioteca'",
        (pista_id,),
    )
    if not fila:
        return None
    ruta_vieja = fila["karaoke_ruta_instrumental"] or ""
    if ruta_vieja:
        try:
            from pathlib import Path
            p = Path(ruta_vieja)
            if p.exists():
                p.unlink()
        except Exception as exc:
            _log.warning("marcar_para_reprocesar: no se pudo borrar %s: %s", ruta_vieja, exc)

    with transaccion() as con:
        # Resetear estado de la pista para limpiar referencias al archivo viejo.
        con.execute(
            """
            UPDATE pistas
            SET karaoke_estado='no_procesada',
                karaoke_ruta_instrumental=NULL,
                karaoke_actualizado_en=datetime('now'),
                karaoke_error_codigo=NULL, karaoke_error_mensaje=NULL
            WHERE id = ? AND estado='biblioteca'
            """,
            (pista_id,),
        )
        # Cancelar cualquier job activo previo.
        con.execute(
            """
            UPDATE karaoke_jobs
            SET estado='cancelada', finalizado_en=datetime('now'),
                actualizado_en=datetime('now'),
                error_codigo='cancelado', error_mensaje='Reprocesar manual'
            WHERE pista_id = ? AND estado IN ('en_cola','preparando','procesando','generando')
            """,
            (pista_id,),
        )
    # Encolar fresco fuera de la transaccion previa (encolar abre la suya).
    return encolar(pista_id)


def asignar_instrumental_manual(pista_id: int, ruta: str) -> bool:
    """Marca una pista como `lista` con un instrumental externo provisto por el usuario.

    Crea un job sintetico `lista` para mantener trazabilidad.
    """
    if not ruta or int(pista_id) <= 0:
        return False
    with transaccion() as con:
        ya = con.execute(
            "SELECT id FROM pistas WHERE id = ? AND estado='biblioteca'",
            (pista_id,),
        ).fetchone()
        if not ya:
            return False
        con.execute(
            """
            INSERT INTO karaoke_jobs(
                pista_id, estado, progreso, intento, max_intentos,
                modelo, backend, ruta_salida,
                iniciado_en, finalizado_en, creado_en, actualizado_en
            )
            VALUES (?, 'lista', 1.0, 0, 0, NULL, 'manual', ?,
                    datetime('now'), datetime('now'), datetime('now'), datetime('now'))
            """,
            (pista_id, ruta),
        )
        con.execute(
            """
            UPDATE pistas
            SET karaoke_estado='lista',
                karaoke_ruta_instrumental=?,
                karaoke_actualizado_en=datetime('now'),
                karaoke_error_codigo=NULL, karaoke_error_mensaje=NULL
            WHERE id = ?
            """,
            (ruta, pista_id),
        )
    return True


def marcar_no_aplica(pista_id: int) -> bool:
    """Marca una pista como `no_aplica` (instrumental, ambient, etc.)."""
    with transaccion() as con:
        # Cancela jobs activos por si la habia encolada antes.
        con.execute(
            """
            UPDATE karaoke_jobs
            SET estado='cancelada', finalizado_en=datetime('now'),
                actualizado_en=datetime('now'),
                error_codigo='cancelado', error_mensaje='Marcada no_aplica'
            WHERE pista_id = ? AND estado IN ('en_cola','preparando','procesando','generando')
            """,
            (pista_id,),
        )
        cur = con.execute(
            """
            UPDATE pistas
            SET karaoke_estado='no_aplica',
                karaoke_actualizado_en=datetime('now'),
                karaoke_error_codigo=NULL, karaoke_error_mensaje=NULL
            WHERE id = ? AND estado='biblioteca'
            """,
            (pista_id,),
        )
        return cur.rowcount > 0


def restaurar_de_no_aplica(pista_id: int) -> bool:
    cur = ejecutar(
        """
        UPDATE pistas
        SET karaoke_estado='no_procesada',
            karaoke_actualizado_en=datetime('now')
        WHERE id = ? AND estado='biblioteca' AND karaoke_estado='no_aplica'
        """,
        (pista_id,),
    )
    return cur.rowcount > 0
