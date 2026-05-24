from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from config.settings import (
    ENABLE_THIRD_STAGE_RESOLUTION,
    THIRD_STAGE_MIN_EVIDENCE,
    THIRD_STAGE_MIN_GAP,
    ACCEPTED_RELEASE_TYPES,
)
from core.second_stage import SegundaFaseResolucion
from core.writer import escribir_y_mover
from domain.models import DecisionArchivo, DecisionTipo, RevisionCausa, CuarentenaCausa
from external.itunes_client import ClienteItunes
from infra.logger import obtener_logger, registrar_evento
from utils.text import limpiar_version_titulo, para_comparacion, similitud_combinada

_log = obtener_logger("third_stage")


@dataclass
class ResumenTerceraFase:
    habilitada: bool = False
    evaluados: int = 0
    elegibles: int = 0
    promovidos: int = 0
    mejorados_a_revision: int = 0
    sin_cambio: int = 0
    duracion_seg: float = 0.0


class TerceraFaseResolucion:
    """Último intento conservador usando corroboración iTunes + MusicBrainz."""

    def __init__(
        self,
        mb_client,
        itunes_client: ClienteItunes,
        directorio_biblioteca: Path,
        directorio_temp: Path,
        writer_fn: Optional[Callable] = None,
        barra=None,
        control=None,
    ) -> None:
        self._mb_client = mb_client
        self._itunes = itunes_client
        self._dir_biblioteca = directorio_biblioteca
        self._dir_temp = directorio_temp
        self._writer_fn = writer_fn or escribir_y_mover
        self._barra = barra
        self._control = control

    def procesar(self, decisiones: list[DecisionArchivo]) -> tuple[list[DecisionArchivo], ResumenTerceraFase]:
        resumen = ResumenTerceraFase(habilitada=ENABLE_THIRD_STAGE_RESOLUTION)
        if not ENABLE_THIRD_STAGE_RESOLUTION:
            return decisiones, resumen

        inicio = time.perf_counter()
        finales: list[DecisionArchivo] = []

        total_decisiones = len(decisiones)
        for indice, decision in enumerate(decisiones, start=1):
            resumen.evaluados += 1
            if self._barra and hasattr(self._barra, "actualizar_fase"):
                self._barra.actualizar_fase(
                    current=indice,
                    total=total_decisiones,
                    current_item=decision.archivo.nombre_archivo,
                    current_task="fase_3:corroborando",
                )
            if self._control:
                self._control.progreso_fase(
                    current=indice,
                    total=total_decisiones,
                    current_item=decision.archivo.nombre_archivo,
                    current_task="fase_3:corroborando",
                )
            if not self._es_elegible(decision):
                resumen.sin_cambio += 1
                finales.append(decision)
                continue

            resumen.elegibles += 1
            resuelta = self._resolver(decision)
            if resuelta.tipo in (DecisionTipo.ACEPTADO, DecisionTipo.ACEPTADO_PROVISIONAL):
                resumen.promovidos += 1
            elif decision.tipo == DecisionTipo.CUARENTENA and resuelta.tipo == DecisionTipo.REVISION:
                resumen.mejorados_a_revision += 1
            else:
                resumen.sin_cambio += 1
            finales.append(resuelta)

        resumen.duracion_seg = round(time.perf_counter() - inicio, 3)
        registrar_evento("third_stage_finished", datos={
            "evaluados": resumen.evaluados,
            "elegibles": resumen.elegibles,
            "promovidos": resumen.promovidos,
            "mejorados_a_revision": resumen.mejorados_a_revision,
            "sin_cambio": resumen.sin_cambio,
            "duracion_seg": resumen.duracion_seg,
        })
        return finales, resumen

    def _resolver(self, decision: DecisionArchivo) -> DecisionArchivo:
        norm = decision.archivo.metadata_norm
        if norm is None:
            return decision

        hint = self._itunes.buscar_hint(norm.artista_principal, norm.titulo)
        if hint is None:
            decision.mensaje_decision = "3a fase: iTunes sin evidencia adicional"
            return decision

        evidencia_hint = self._evidencia_itunes(norm, hint)
        if evidencia_hint < 0.75:
            decision.mensaje_decision = f"3a fase: evidencia iTunes insuficiente ({evidencia_hint:.3f})"
            return self._degradar_si_aplica(decision, "itunes_debil")

        norm_lookup = norm
        if hint.isrc and not norm_lookup.isrc:
            from dataclasses import replace
            norm_lookup = replace(norm, isrc=hint.isrc)

        candidatos = self._mb_client.buscar_candidatos(
            norm_lookup,
            recording_ids_acoustid=(decision.archivo.resultado_acoustid.recording_ids if decision.archivo.resultado_acoustid else None),
        )[:5]
        if not candidatos:
            decision.mensaje_decision = "3a fase: sin candidatos MB tras corroboración iTunes"
            return self._degradar_si_aplica(decision, "sin_candidatos_post_itunes")

        analisis = [(c, SegundaFaseResolucion._puntaje_evidencia(decision.archivo, c)) for c in candidatos]
        analisis.sort(key=lambda x: x[1], reverse=True)
        mejor, score_ev = analisis[0]
        segundo = analisis[1][1] if len(analisis) > 1 else 0.0
        if hint.isrc and mejor.isrc and hint.isrc == mejor.isrc:
            score_ev = min(1.0, score_ev + 0.12)
        gap = score_ev - segundo

        has_hard_signal = bool(
            (hint.isrc and mejor.isrc and hint.isrc == mejor.isrc)
            or (decision.archivo.resultado_acoustid and mejor.recording_id in (decision.archivo.resultado_acoustid.recording_ids or []))
        )

        if score_ev >= THIRD_STAGE_MIN_EVIDENCE and gap >= THIRD_STAGE_MIN_GAP and evidencia_hint >= 0.8 and has_hard_signal:
            decision.candidato_elegido = mejor
            decision.tipo = DecisionTipo.ACEPTADO if mejor.tipo_release in ACCEPTED_RELEASE_TYPES else DecisionTipo.ACEPTADO_PROVISIONAL
            decision.causa_revision = None
            decision.causa_cuarentena = None
            decision.puntaje_maximo = round(max(decision.puntaje_maximo, score_ev), 4)
            decision.mensaje_decision = f"3a fase promovido: ev={score_ev:.3f} gap={gap:.3f} itunes={evidencia_hint:.3f}"
            ok, causa, msg = self._writer_fn(decision, directorio_biblioteca=self._dir_biblioteca, directorio_temp=self._dir_temp)
            if not ok:
                decision.tipo = DecisionTipo.CUARENTENA
                decision.causa_cuarentena = causa or CuarentenaCausa.ESCRITURA_FALLIDA
                decision.mensaje_decision = f"3a fase promovió pero falló escritura: {msg}"
            elif self._barra:
                self._barra.mensaje(f"3ª fase resolvió {decision.archivo.nombre_archivo}", nivel="ok")
            return decision

        decision.mensaje_decision = f"3a fase sin promoción: ev={score_ev:.3f} gap={gap:.3f} itunes={evidencia_hint:.3f}"
        return self._degradar_si_aplica(decision, "sin_umbral_fuerte")

    @staticmethod
    def _es_elegible(decision: DecisionArchivo) -> bool:
        if decision.archivo.metadata_norm is None:
            return False
        if decision.tipo == DecisionTipo.REVISION:
            return True
        if decision.tipo == DecisionTipo.CUARENTENA:
            return decision.causa_cuarentena in {CuarentenaCausa.SIN_CANDIDATOS, CuarentenaCausa.PUNTAJE_BAJO}
        return False

    @staticmethod
    def _evidencia_itunes(norm, hint) -> float:
        title = similitud_combinada(
            para_comparacion(limpiar_version_titulo(norm.titulo or "")),
            para_comparacion(limpiar_version_titulo(hint.title or "")),
        )
        artist = similitud_combinada(para_comparacion(norm.artista_principal or ""), para_comparacion(hint.artist or ""))
        duration = 0.5
        if norm.duracion_seg and hint.duration_sec:
            diff = abs(norm.duracion_seg - hint.duration_sec)
            duration = 1.0 if diff <= 3 else 0.8 if diff <= 8 else 0.35
        isrc = 1.0 if norm.isrc and hint.isrc and norm.isrc == hint.isrc else 0.0
        return round((title * 0.40) + (artist * 0.35) + (duration * 0.15) + (isrc * 0.10), 4)

    @staticmethod
    def _degradar_si_aplica(decision: DecisionArchivo, reason: str) -> DecisionArchivo:
        if decision.tipo == DecisionTipo.CUARENTENA:
            decision.tipo = DecisionTipo.REVISION
            decision.causa_cuarentena = None
            decision.causa_revision = RevisionCausa.PUNTAJE_INTERMEDIO
            decision.mensaje_decision = f"3a fase: mejora a revision ({reason})"
        return decision
