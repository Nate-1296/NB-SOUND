# =============================================================================
# core/dedupe.py
#
# Deteccion de duplicados dentro de una ejecucion del pipeline.
#
# Capas implementadas:
#   1) Duplicado exacto por hash SHA256 (archivo binariamente equivalente).
#   2) Duplicado semantico por identidad musical (ISRC o recording_id de MB).
#
# Este modulo no elimina archivos por si solo; solo toma decisiones de si un
# archivo debe considerarse duplicado frente a otro ya aceptado en la corrida.
# =============================================================================

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config.settings import DUPLICATE_POLICY, DUPLICATE_BETTER_MIN_DELTA
from domain.models import ArchivoAudio, DecisionArchivo
from infra.logger import obtener_logger

_log = obtener_logger("core.dedupe")


@dataclass(frozen=True)
class DuplicadoDetectado:
    tipo: str
    referencia: str


class GestorDuplicados:
    """Mantiene indices para detectar duplicados.

    Pre-carga los hashes / recording_ids / ISRCs de pistas ya en biblioteca
    al construirse, así una corrida que repite archivos ya importados en
    sesiones anteriores los marca como duplicados en vez de añadirlos
    como nuevos. Sin esta precarga, cancelar una importación a mitad y
    relanzarla suele dejar canciones duplicadas en la biblioteca (la
    primera corrida ya las había copiado, la segunda no las identifica
    porque los índices internos arrancaban vacíos cada vez).
    """

    def __init__(self) -> None:
        self._por_hash: dict[str, Path] = {}
        self._por_identidad: dict[str, Path] = {}
        self._calidad_por_identidad: dict[str, float] = {}
        self._precargar_desde_biblioteca()

    def _precargar_desde_biblioteca(self) -> None:
        """Llena los índices con lo que ya está catalogado en la BD.

        Lee de la tabla ``pistas``: las claves de identidad MusicBrainz
        (``mb_recording_id``) e ISRC viven ahí, no en una tabla aparte.
        Si la BD aún no se inicializó (primera ejecución), no hay tabla
        y la consulta lanza excepción; en ese caso arrancamos con
        índices vacíos, equivalente al comportamiento anterior.
        """
        try:
            from db.conexion import obtener_filas
            filas = obtener_filas(
                "SELECT hash_sha256, ruta_archivo, mb_recording_id, isrc "
                "FROM pistas WHERE estado IN ('biblioteca', 'aceptado')"
            )
        except Exception as exc:
            _log.warning(
                "GestorDuplicados: precarga falló (%s). Iniciando con "
                "índices vacíos — reimportar puede crear duplicados.",
                exc,
            )
            return
        _log.info(
            "GestorDuplicados: precarga OK, %d filas leídas de la BD",
            len(filas),
        )
        for fila in filas:
            ruta = Path(str(fila["ruta_archivo"] or ""))
            h = str(fila["hash_sha256"] or "")
            rid = str(fila["mb_recording_id"] or "")
            isrc = str(fila["isrc"] or "")
            if h and h not in self._por_hash:
                self._por_hash[h] = ruta
            for clave in (f"rid:{rid}" if rid else "", f"isrc:{isrc}" if isrc else ""):
                if clave and clave not in self._por_identidad:
                    self._por_identidad[clave] = ruta
                    # Calidad neutra. Si la corrida actual encuentra un
                    # candidato con calidad >> 0.5 podrá marcarse como
                    # "duplicado_mejorable"; en caso contrario, identidad
                    # semántica (descartar).
                    self._calidad_por_identidad[clave] = 0.5

    def registrar_hash(self, archivo: ArchivoAudio) -> Optional[DuplicadoDetectado]:
        """
        Registra hash del archivo y detecta duplicado exacto.

        Returns:
            DuplicadoDetectado si ya existia ese hash, None en caso contrario.
        """
        if not archivo.hash_sha256:
            return None

        existente = self._por_hash.get(archivo.hash_sha256)
        if existente is not None:
            return DuplicadoDetectado(
                tipo="hash_exacto",
                referencia=str(existente),
            )

        self._por_hash[archivo.hash_sha256] = archivo.ruta_original
        return None

    def registrar_identidad_aceptada(
        self,
        decision: DecisionArchivo,
    ) -> Optional[DuplicadoDetectado]:
        """
        Registra la identidad musical de una decision aceptada y detecta
        duplicado semantico respecto a un track ya aceptado anteriormente.
        """
        candidato = decision.candidato_elegido
        if candidato is None:
            return None

        claves: list[str] = []
        if candidato.recording_id:
            claves.append(f"rid:{candidato.recording_id}")

        isrc = decision.archivo.isrc_disponible or candidato.isrc
        if isrc:
            claves.append(f"isrc:{isrc}")

        conflicto = self.detectar_duplicado_identidad(decision)
        if conflicto is not None:
            return conflicto

        ruta_ref = decision.ruta_destino or decision.archivo.ruta_original
        calidad = self._score_calidad(decision)
        for clave in claves:
            self._por_identidad[clave] = ruta_ref
            self._calidad_por_identidad[clave] = calidad

        return None

    def detectar_duplicado_identidad(self, decision: DecisionArchivo) -> Optional[DuplicadoDetectado]:
        candidato = decision.candidato_elegido
        if candidato is None:
            return None

        claves: list[str] = []
        if candidato.recording_id:
            claves.append(f"rid:{candidato.recording_id}")
        isrc = decision.archivo.isrc_disponible or candidato.isrc
        if isrc:
            claves.append(f"isrc:{isrc}")

        for clave in claves:
            existente = self._por_identidad.get(clave)
            if existente is not None:
                calidad_nueva = self._score_calidad(decision)
                calidad_existente = self._calidad_por_identidad.get(clave, 0.0)
                if (
                    DUPLICATE_POLICY in {"replace_if_better", "prefer_new_if_quality_higher"}
                    and (calidad_nueva - calidad_existente) >= DUPLICATE_BETTER_MIN_DELTA
                ):
                    tipo = "duplicado_mejorable"
                else:
                    tipo = "identidad_semantica"
                return DuplicadoDetectado(
                    tipo=tipo,
                    referencia=str(existente),
                )
        return None

    @staticmethod
    def _score_calidad(decision: DecisionArchivo) -> float:
        archivo = decision.archivo
        cand = decision.candidato_elegido
        score = 0.0
        if decision.puntaje_maximo:
            score += min(0.5, decision.puntaje_maximo * 0.5)
        if cand:
            if cand.recording_id:
                score += 0.1
            if cand.release_id:
                score += 0.08
            if cand.isrc:
                score += 0.06
            if cand.track_number:
                score += 0.04
        if archivo.metadata_cruda:
            if archivo.metadata_cruda.bitrate_kbps and archivo.metadata_cruda.bitrate_kbps >= 256:
                score += 0.1
            if archivo.metadata_cruda.titulo and archivo.metadata_cruda.artista:
                score += 0.05
        if archivo.resultado_acoustid and archivo.resultado_acoustid.recording_ids:
            score += 0.07
        if archivo.isrc_disponible:
            score += 0.05
        return round(min(score, 1.0), 4)
