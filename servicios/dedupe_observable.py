# =============================================================================
# servicios/dedupe_observable.py
#
# Tercera capa de deduplicacion: verificacion periodica de "duplicados
# observables" sobre la biblioteca ya catalogada.
#
# Un duplicado observable es un par de pistas que comparten SIMULTANEAMENTE:
#   - titulo normalizado   (utils.text.normalizar_para_comparar)
#   - artista normalizado
#   - album normalizado
#   - duracion +- DUPLICATE_OBSERVABLE_TOLERANCIA_SEG segundos
#   - portada (hash del CONTENIDO del archivo de portada del album)
#
# A diferencia de los ejes hash/ISRC/MBID (que actuan en el pipeline), este
# barrido corre sobre la biblioteca existente, en background, y resuelve los
# duplicados automaticamente segun DUPLICATE_POLICY, sin intervencion del
# usuario ni reinicio de la app.
#
# Resolucion (no destructiva): se conserva la "mejor" pista del grupo y las
# demas se marcan con estado='duplicado'. Esas filas dejan de aparecer en
# biblioteca/estadisticas/inicio (todas las consultas de servicios.biblioteca
# filtran estado='biblioteca') pero NO se borran de la BD ni del disco: la
# operacion es reversible y auditable. Cada decision se registra en el log.
#
# Reanudable: el progreso se persiste en config_ui. Ademas la operacion es
# idempotente -> una pista marcada 'duplicado' deja de ser candidata, de modo
# que reanudar tras una interrupcion continua de forma natural.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from config.settings import DUPLICATE_POLICY
from core.dedupe import duraciones_equivalentes
from db.conexion import obtener_filas, transaccion, guardar_config, obtener_config
from infra.logger import obtener_logger
from utils.text import normalizar_para_comparar

_log = obtener_logger("servicios.dedupe_observable")

# Estado con el que se marca la pista perdedora del grupo. No es 'biblioteca',
# por lo que queda oculta de todas las vistas sin borrarse.
ESTADO_DUPLICADO = "duplicado"

# Claves de checkpoint/observabilidad en config_ui.
_CLAVE_ULTIMA_CORRIDA = "dedupe_observable_ultima_corrida"
_CLAVE_PROGRESO = "dedupe_observable_progreso"


@dataclass
class ResultadoDedupeObservable:
    """Snapshot del resultado de una corrida del barrido observable."""
    grupos_detectados: int = 0
    duplicados_resueltos: int = 0
    pistas_escaneadas: int = 0
    grupos_procesados: int = 0
    completado: bool = False
    cancelado: bool = False
    decisiones: list[dict] = field(default_factory=list)

    def a_dict(self) -> dict:
        return {
            "grupos_detectados": self.grupos_detectados,
            "duplicados_resueltos": self.duplicados_resueltos,
            "pistas_escaneadas": self.pistas_escaneadas,
            "grupos_procesados": self.grupos_procesados,
            "completado": self.completado,
            "cancelado": self.cancelado,
            "decisiones": list(self.decisiones),
        }


def _puntaje_conservar(fila) -> tuple:
    """Clave de orden para decidir QUE pista conservar dentro de un grupo.

    Mayor es mejor (se conserva el maximo). Prioridades, en orden:
      1. Favorita (nunca descartar silenciosamente algo marcado por el usuario).
      2. Identidad fuerte: tiene mb_recording_id, luego isrc.
      3. Bitrate mas alto.
      4. Archivo mas grande (proxy de calidad cuando falta bitrate).
      5. Mas reproducida (el usuario ya la usa).
    El desempate final (id mas bajo = la mas antigua) lo aplica el llamador.
    """
    def _num(v) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    favorita = 1 if (fila["favorita"] or 0) else 0
    tiene_mbid = 1 if (fila["mb_recording_id"] or "") else 0
    tiene_isrc = 1 if (fila["isrc"] or "") else 0
    bitrate = _num(fila["bitrate_kbps"])
    tamano = _num(fila["tamano_bytes"])
    reproducciones = _num(fila["veces_reproducida"])
    return (favorita, tiene_mbid, tiene_isrc, bitrate, tamano, reproducciones)


def _politica_permite_resolver() -> bool:
    """El barrido resuelve salvo que la politica desactive explicitamente.

    Cualquier valor de DUPLICATE_POLICY distinto de keep_all/off/none implica
    que el usuario quiere deduplicar. Por defecto ('replace_if_better') resuelve.
    """
    return str(DUPLICATE_POLICY).strip().lower() not in {"keep_all", "off", "none", ""}


class ServicioDedupeObservable:
    """Servicio de barrido observable sobre la biblioteca catalogada.

    No depende de Qt: invocable desde un worker Qt, desde el CLI o desde tests.
    Toda la concurrencia de BD se delega al lock de db.conexion.
    """

    def escanear(
        self,
        *,
        progress_callback: Optional[Callable[[dict], None]] = None,
        stop_event=None,
        aplicar: bool = True,
    ) -> ResultadoDedupeObservable:
        """Ejecuta una corrida completa del barrido observable.

        Args:
            progress_callback: invocado con un dict de snapshot tras cada grupo.
            stop_event: objeto con ``.is_set()`` (threading.Event) para cancelar
                cooperativamente. La cancelacion deja la BD consistente: cada
                grupo se resuelve en su propia transaccion.
            aplicar: si False, detecta y registra pero NO marca duplicados
                (dry-run para tests/diagnostico).

        Returns:
            ResultadoDedupeObservable con el snapshot final.
        """
        resultado = ResultadoDedupeObservable()

        if aplicar and not _politica_permite_resolver():
            _log.info(
                "dedupe_observable: DUPLICATE_POLICY=%s no resuelve; corrida en modo deteccion.",
                DUPLICATE_POLICY,
            )
            aplicar = False

        grupos = self._construir_grupos(resultado)
        resultado.grupos_detectados = len(grupos)

        for clave, miembros in grupos.items():
            if stop_event is not None and stop_event.is_set():
                resultado.cancelado = True
                break
            self._resolver_grupo(clave, miembros, resultado, aplicar=aplicar)
            resultado.grupos_procesados += 1
            self._persistir_progreso(resultado)
            if progress_callback is not None:
                try:
                    progress_callback(resultado.a_dict())
                except Exception:
                    _log.debug("dedupe_observable: progress_callback fallo", exc_info=True)

        if not resultado.cancelado:
            resultado.completado = True
        self._persistir_progreso(resultado, final=True)
        _log.info(
            "dedupe_observable: corrida %s. grupos=%d resueltos=%d escaneadas=%d",
            "completada" if resultado.completado else "cancelada",
            resultado.grupos_detectados, resultado.duplicados_resueltos,
            resultado.pistas_escaneadas,
        )
        return resultado

    def _construir_grupos(self, resultado: ResultadoDedupeObservable) -> dict:
        """Agrupa las pistas de biblioteca por clave de transitividad.

        Clave = (titulo, artista, album) normalizados. La duración se valida por
        par en :meth:`_resolver_grupo` (no aquí). NO se exige hash de portada
        idéntico: dos importaciones del mismo álbum crean filas de álbum
        distintas con archivos de portada distintos (hash distinto) aunque la
        imagen sea la misma, lo que impedía detectar el duplicado obvio. Con
        título+artista+álbum+duración basta para afirmar que es la misma pista
        ("transitividad" sin mirar hashes/fingerprints).
        """
        try:
            filas = obtener_filas(
                "SELECT p.id, p.ruta_archivo, p.titulo, p.artista_nombre, "
                "       p.album_titulo, p.duracion_seg, p.bitrate_kbps, "
                "       p.tamano_bytes, p.veces_reproducida, p.favorita, "
                "       p.isrc, p.mb_recording_id, a.portada_ruta "
                "FROM pistas p LEFT JOIN albums a ON a.id = p.album_id "
                "WHERE p.estado = 'biblioteca' "
                "ORDER BY p.id ASC"
            )
        except Exception as exc:
            _log.warning("dedupe_observable: lectura de biblioteca fallo: %s", exc)
            return {}

        agrupados: dict[tuple, list] = {}
        for fila in filas:
            resultado.pistas_escaneadas += 1
            titulo = normalizar_para_comparar(fila["titulo"] or "")
            artista = normalizar_para_comparar(fila["artista_nombre"] or "")
            album = normalizar_para_comparar(fila["album_titulo"] or "")
            # Requiere los tres campos para no agrupar por ausencia de datos.
            if not titulo or not artista or not album:
                continue
            clave = (titulo, artista, album)
            agrupados.setdefault(clave, []).append(fila)

        return {k: v for k, v in agrupados.items() if len(v) >= 2}

    def _resolver_grupo(
        self,
        clave: tuple,
        miembros: list,
        resultado: ResultadoDedupeObservable,
        *,
        aplicar: bool,
    ) -> None:
        """Resuelve un grupo: conserva la mejor pista, marca el resto duplicado.

        Solo se consideran duplicados entre si los miembros cuya duracion cae
        dentro de la tolerancia respecto a la pista conservada. Los que difieren
        mas alla de la tolerancia se dejan intactos (no son el mismo material).
        """
        # Elegir la pista a conservar: mayor puntaje; desempate por id mas bajo.
        conservar = max(miembros, key=lambda f: (_puntaje_conservar(f), -int(f["id"])))
        dur_conservar = conservar["duracion_seg"]

        perdedores = []
        for fila in miembros:
            if int(fila["id"]) == int(conservar["id"]):
                continue
            if duraciones_equivalentes(dur_conservar, fila["duracion_seg"]):
                perdedores.append(fila)

        if not perdedores:
            return

        for fila in perdedores:
            razon = (
                f"observable: id={fila['id']} duplicado de id={conservar['id']} "
                f"(titulo='{clave[0]}' artista='{clave[1]}' album='{clave[2]}' "
                f"dur={fila['duracion_seg']}~{dur_conservar}) policy={DUPLICATE_POLICY}"
            )
            _log.info("dedupe_observable: %s", razon)
            resultado.decisiones.append({
                "conservada_id": int(conservar["id"]),
                "duplicada_id": int(fila["id"]),
                "duplicada_ruta": str(fila["ruta_archivo"]),
                "razon": razon,
            })
            if aplicar:
                try:
                    with transaccion() as con:
                        con.execute(
                            "UPDATE pistas SET estado = ?, actualizado_en = datetime('now') "
                            "WHERE id = ? AND estado = 'biblioteca'",
                            (ESTADO_DUPLICADO, int(fila["id"])),
                        )
                    resultado.duplicados_resueltos += 1
                except Exception as exc:
                    _log.warning(
                        "dedupe_observable: no se pudo marcar id=%s como duplicado: %s",
                        fila["id"], exc,
                    )

    def _persistir_progreso(self, resultado: ResultadoDedupeObservable, *, final: bool = False) -> None:
        """Persiste el progreso en config_ui (observabilidad + reanudacion)."""
        import json
        try:
            guardar_config(
                _CLAVE_PROGRESO,
                json.dumps({
                    "grupos_procesados": resultado.grupos_procesados,
                    "grupos_detectados": resultado.grupos_detectados,
                    "duplicados_resueltos": resultado.duplicados_resueltos,
                    "completado": resultado.completado,
                    "cancelado": resultado.cancelado,
                }, ensure_ascii=False),
            )
            if final:
                from datetime import datetime, timezone
                guardar_config(_CLAVE_ULTIMA_CORRIDA, datetime.now(timezone.utc).isoformat())
        except Exception:
            _log.debug("dedupe_observable: no se pudo persistir progreso", exc_info=True)

    def ultima_corrida(self) -> str:
        """ISO timestamp de la ultima corrida completada, o '' si nunca."""
        try:
            return obtener_config(_CLAVE_ULTIMA_CORRIDA, "")
        except Exception:
            return ""


def ejecutar_barrido(
    *,
    progress_callback: Optional[Callable[[dict], None]] = None,
    stop_event=None,
    aplicar: bool = True,
) -> dict:
    """Atajo funcional: ejecuta un barrido y devuelve el snapshot dict.

    Pensado para el worker Qt y el CLI.
    """
    servicio = ServicioDedupeObservable()
    return servicio.escanear(
        progress_callback=progress_callback,
        stop_event=stop_event,
        aplicar=aplicar,
    ).a_dict()
