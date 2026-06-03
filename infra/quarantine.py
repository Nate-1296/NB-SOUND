# =============================================================================
# infra/quarantine.py
#
# Gestion estructurada de cuarentena y revision. Mueve archivos que no
# superaron el proceso automatico a carpetas especificas por causa, y
# genera un manifiesto JSONL en cada subcarpeta para auditoria posterior.
#
# Novedades v3:
#   - El manifiesto incluye las fuentes_usadas de la DecisionArchivo y,
#     si la IA intervino, el detalle de su decision.
#   - Subcarpetas con nombre exactamente igual al valor del Enum (snake_case)
#     para que sean programaticamente predecibles.
# =============================================================================

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings
from domain.models import (
    DecisionArchivo,
    DecisionTipo,
    CuarentenaCausa,
    RevisionCausa,
)
from infra.logger import obtener_logger, registrar_evento

_log = obtener_logger("quarantine")

_MANIFIESTO_NOMBRE = "_manifiesto.jsonl"


# =============================================================================
# CLASE PRINCIPAL
# =============================================================================

class GestorCuarentena:
    """
    Mueve archivos a cuarentena o revision segun la causa de la decision.
    Los directorios deben proporcionarse en la construccion; no tiene fallbacks
    para garantizar que nada se escribe dentro del proyecto.
    """

    def __init__(
        self,
        directorio_cuarentena: Optional[Path] = None,
        directorio_revision:   Optional[Path] = None,
    ) -> None:
        if directorio_cuarentena is None:
            raise ValueError(
                "GestorCuarentena requiere directorio_cuarentena. "
                "Configura USER_QUARANTINE_DIR en settings.py o usa --quarantine."
            )
        if directorio_revision is None:
            raise ValueError(
                "GestorCuarentena requiere directorio_revision. "
                "Configura USER_REVIEW_DIR en settings.py o usa --review."
            )

        self._dir_cuarentena = directorio_cuarentena
        self._dir_revision   = directorio_revision
        self._contadores: dict[str, int] = {}

    # ------------------------------------------------------------------
    # API PUBLICA
    # ------------------------------------------------------------------

    def procesar_decision(self, decision: DecisionArchivo) -> Optional[Path]:
        """Envia el archivo al destino correcto segun el tipo de decision."""
        if decision.tipo == DecisionTipo.CUARENTENA:
            return self._enviar_a_cuarentena(decision)
        elif decision.tipo == DecisionTipo.REVISION:
            return self._enviar_a_revision(decision)
        elif decision.tipo == DecisionTipo.ERROR:
            decision.causa_cuarentena = CuarentenaCausa.ERROR_INESPERADO
            return self._enviar_a_cuarentena(decision)
        return None

    def estadisticas(self) -> dict:
        return dict(self._contadores)

    # ------------------------------------------------------------------
    # CUARENTENA
    # ------------------------------------------------------------------

    def _enviar_a_cuarentena(self, decision: DecisionArchivo) -> Optional[Path]:
        causa     = decision.causa_cuarentena or CuarentenaCausa.ERROR_INESPERADO
        causa_str = causa.value

        carpeta_destino = self._dir_cuarentena / causa_str
        ruta_archivo    = decision.archivo.ruta_original

        if settings.DRY_RUN:
            _log.info(f"[DRY_RUN] Cuarentena ({causa_str}): {ruta_archivo.name}")
            self._incrementar(f"cuarentena:{causa_str}")
            return None

        carpeta_destino.mkdir(parents=True, exist_ok=True)
        ruta_final = self._mover_a_carpeta(ruta_archivo, carpeta_destino)

        if ruta_final:
            self._escribir_manifiesto(
                carpeta=carpeta_destino,
                nombre_archivo=ruta_archivo.name,
                ruta_destino=ruta_final,
                causa=causa_str,
                decision=decision,
            )
            registrar_evento(
                "cuarentena",
                archivo=ruta_archivo.name,
                datos={"causa": causa_str, "score": decision.puntaje_maximo},
            )
            _log.debug(
                f"[CUARENTENA:{causa_str}] {ruta_archivo.name} -> {ruta_final.name}"
            )

        self._incrementar(f"cuarentena:{causa_str}")
        return ruta_final

    # ------------------------------------------------------------------
    # REVISION
    # ------------------------------------------------------------------

    def _enviar_a_revision(self, decision: DecisionArchivo) -> Optional[Path]:
        causa     = decision.causa_revision or RevisionCausa.PUNTAJE_INTERMEDIO
        causa_str = causa.value

        carpeta_destino = self._dir_revision / causa_str
        ruta_archivo    = decision.archivo.ruta_original

        if settings.DRY_RUN:
            _log.info(f"[DRY_RUN] Revision ({causa_str}): {ruta_archivo.name}")
            self._incrementar(f"revision:{causa_str}")
            return None

        carpeta_destino.mkdir(parents=True, exist_ok=True)
        ruta_final = self._mover_a_carpeta(ruta_archivo, carpeta_destino)

        if ruta_final:
            self._escribir_manifiesto(
                carpeta=carpeta_destino,
                nombre_archivo=ruta_archivo.name,
                ruta_destino=ruta_final,
                causa=causa_str,
                decision=decision,
            )
            registrar_evento(
                "revision",
                archivo=ruta_archivo.name,
                datos={"causa": causa_str, "score": decision.puntaje_maximo},
            )
            _log.debug(
                f"[REVISION:{causa_str}] {ruta_archivo.name} -> {ruta_final.name}"
            )

        self._incrementar(f"revision:{causa_str}")
        return ruta_final

    # ------------------------------------------------------------------
    # UTILIDADES INTERNAS
    # ------------------------------------------------------------------

    @staticmethod
    def _mover_a_carpeta(
        ruta_origen: Path, carpeta_destino: Path
    ) -> Optional[Path]:
        nombre       = ruta_origen.name
        ruta_destino = carpeta_destino / nombre

        contador = 1
        while ruta_destino.exists():
            contador += 1
            ruta_destino = (
                carpeta_destino /
                f"{ruta_origen.stem}_{contador}{ruta_origen.suffix}"
            )
            if contador > 99:
                _log.error(
                    f"Demasiados conflictos en cuarentena para: {nombre}"
                )
                return None

        try:
            shutil.move(str(ruta_origen), str(ruta_destino))
            return ruta_destino
        except OSError as e:
            _log.error(f"No se pudo mover {ruta_origen.name} a cuarentena: {e}")
            return None

    @staticmethod
    def _escribir_manifiesto(
        carpeta: Path,
        nombre_archivo: str,
        ruta_destino: Path,
        causa: str,
        decision: DecisionArchivo,
    ) -> None:
        ruta_manifiesto = carpeta / _MANIFIESTO_NOMBRE

        candidato = decision.candidato_elegido
        ia        = decision.decision_ia

        entrada: dict = {
            "ts":               datetime.now(timezone.utc).isoformat(),
            "archivo_original": nombre_archivo,
            "archivo_destino":  ruta_destino.name,
            "causa":            causa,
            "puntaje":          round(decision.puntaje_maximo, 4),
            "mensaje":          decision.mensaje_decision,
            "fuentes_usadas":   [f.value for f in decision.fuentes_usadas],
            "candidato_top": {
                "artista":  candidato.artista_principal  if candidato else None,
                "titulo":   candidato.titulo_oficial     if candidato else None,
                "album":    candidato.album_oficial      if candidato else None,
                "tipo":     candidato.tipo_release       if candidato else None,
                "anio":     candidato.anio_release       if candidato else None,
                "isrc":     candidato.isrc               if candidato else None,
                "score":    round(candidato.puntaje_total, 4) if candidato else None,
                "detalle":  candidato.puntaje_detalle    if candidato else None,
            } if candidato else None,
            "ia": {
                "decision":   ia.decision,
                "confianza":  ia.confianza,
                "razones":    ia.razones,
                "modelo":     ia.modelo_usado,
            } if ia and ia.valida else None,
            "errores_archivo": decision.archivo.errores,
        }

        try:
            with open(ruta_manifiesto, "a", encoding="utf-8") as f:
                f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
        except OSError as e:
            _log.warning(f"No se pudo escribir manifiesto: {e}")

    def _incrementar(self, clave: str) -> None:
        self._contadores[clave] = self._contadores.get(clave, 0) + 1
