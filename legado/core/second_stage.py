import time
from dataclasses import dataclass
from typing import Callable, Optional

from config.settings import (
    ENABLE_SECOND_STAGE_RESOLUTION,
    SECOND_STAGE_MAX_CANDIDATES,
    SECOND_STAGE_MIN_EVIDENCE,
    SECOND_STAGE_MIN_GAP,
    SCORE_THRESHOLD_REVIEW,
    ACCEPTED_RELEASE_TYPES,
    SECOND_STAGE_CAUSE_ENABLED,
)
from core.writer import escribir_y_mover
from domain.models import DecisionArchivo, DecisionTipo, RevisionCausa, CuarentenaCausa
from infra.logger import obtener_logger, registrar_evento
from utils.text import para_comparacion, similitud_combinada, limpiar_version_titulo

_log = obtener_logger("second_stage")


@dataclass
class ResumenSegundaFase:
    habilitada: bool = False
    evaluados: int = 0
    elegibles: int = 0
    excluidos: int = 0
    resueltos: int = 0
    quedan_revision: int = 0
    quedan_cuarentena: int = 0
    duracion_seg: float = 0.0


class SegundaFaseResolucion:
    """Resolución dirigida de casos recuperables post-clasificación inicial."""

    def __init__(
        self,
        mb_client,
        ia_activa: bool,
        directorio_biblioteca,
        directorio_temp,
        writer_fn: Optional[Callable] = None,
        barra=None,
        control=None,
    ) -> None:
        self._mb_client = mb_client
        self._ia_activa = ia_activa
        self._dir_biblioteca = directorio_biblioteca
        self._dir_temp = directorio_temp
        self._writer_fn = writer_fn or escribir_y_mover
        self._barra = barra
        self._control = control

    def procesar(self, decisiones: list[DecisionArchivo]) -> tuple[list[DecisionArchivo], ResumenSegundaFase]:
        resumen = ResumenSegundaFase(habilitada=ENABLE_SECOND_STAGE_RESOLUTION)
        if not ENABLE_SECOND_STAGE_RESOLUTION:
            return decisiones, resumen

        inicio = time.perf_counter()
        registrar_evento("second_stage_started", datos={"total_entrada": len(decisiones)})

        finales: list[DecisionArchivo] = []
        total_decisiones = len(decisiones)
        for indice, decision in enumerate(decisiones, start=1):
            resumen.evaluados += 1
            t0 = time.perf_counter()
            if self._barra and hasattr(self._barra, "actualizar_fase"):
                self._barra.actualizar_fase(
                    current=indice,
                    total=total_decisiones,
                    current_item=decision.archivo.nombre_archivo,
                    current_task="fase_2:evaluando",
                )
            if self._control:
                self._control.progreso_fase(
                    current=indice,
                    total=total_decisiones,
                    current_item=decision.archivo.nombre_archivo,
                    current_task="fase_2:evaluando",
                )

            elegible, motivo_skip = self._es_elegible(decision)
            if not elegible:
                resumen.excluidos += 1
                registrar_evento(
                    "second_stage_skipped",
                    archivo=decision.archivo.nombre_archivo,
                    datos={
                        "clasificacion_inicial": decision.tipo.value,
                        "causa_inicial": self._causa_inicial(decision),
                        "motivo": motivo_skip,
                    },
                )
                finales.append(decision)
                continue

            resumen.elegibles += 1
            estrategia = self._estrategia_para(decision)
            causa = self._causa_recuperable(decision)
            decision_resuelta = self._resolver(decision, estrategia)
            duracion_ms = int((time.perf_counter() - t0) * 1000)

            if decision_resuelta.tipo in (DecisionTipo.ACEPTADO, DecisionTipo.ACEPTADO_PROVISIONAL):
                resumen.resueltos += 1
                registrar_evento(
                    "second_stage_promoted",
                    archivo=decision.archivo.nombre_archivo,
                    datos={
                        "clasificacion_inicial": decision.tipo.value,
                        "causa_inicial": self._causa_inicial(decision),
                        "estrategia": estrategia,
                        "causa_recuperable": causa,
                        "score_posterior": round(decision_resuelta.puntaje_maximo, 4),
                        "resultado": decision_resuelta.tipo.value,
                        "duracion_ms": duracion_ms,
                    },
                )
                if self._barra:
                    self._barra.mensaje(
                        f"2ª fase resolvio {decision.archivo.nombre_archivo}: {decision_resuelta.tipo.value}",
                        nivel="ok",
                    )
            elif decision_resuelta.tipo == DecisionTipo.REVISION:
                resumen.quedan_revision += 1
                registrar_evento(
                    "second_stage_kept_review",
                    archivo=decision.archivo.nombre_archivo,
                    datos={
                        "clasificacion_inicial": decision.tipo.value,
                        "causa_inicial": self._causa_inicial(decision),
                        "estrategia": estrategia,
                        "causa_recuperable": causa,
                        "score_anterior": round(decision.puntaje_maximo, 4),
                        "motivo": decision_resuelta.mensaje_decision,
                        "duracion_ms": duracion_ms,
                    },
                )
            else:
                resumen.quedan_cuarentena += 1
                registrar_evento(
                    "second_stage_kept_quarantine",
                    archivo=decision.archivo.nombre_archivo,
                    datos={
                        "clasificacion_inicial": decision.tipo.value,
                        "causa_inicial": self._causa_inicial(decision),
                        "estrategia": estrategia,
                        "causa_recuperable": causa,
                        "motivo": decision_resuelta.mensaje_decision,
                        "duracion_ms": duracion_ms,
                    },
                )

            finales.append(decision_resuelta)

        resumen.duracion_seg = round(time.perf_counter() - inicio, 3)
        registrar_evento(
            "second_stage_finished",
            datos={
                "evaluados": resumen.evaluados,
                "elegibles": resumen.elegibles,
                "excluidos": resumen.excluidos,
                "resueltos": resumen.resueltos,
                "quedan_revision": resumen.quedan_revision,
                "quedan_cuarentena": resumen.quedan_cuarentena,
                "duracion_seg": resumen.duracion_seg,
            },
        )
        return finales, resumen

    def _resolver(self, decision: DecisionArchivo, estrategia: str) -> DecisionArchivo:
        archivo = decision.archivo
        norm = archivo.metadata_norm
        if norm is None:
            return decision

        candidatos = self._mb_client.buscar_candidatos(
            norm,
            recording_ids_acoustid=(
                archivo.resultado_acoustid.recording_ids
                if archivo.resultado_acoustid else None
            ),
        )[:SECOND_STAGE_MAX_CANDIDATES]
        candidatos = self._filtrar_candidatos_por_estrategia(candidatos, estrategia, norm)

        if not candidatos:
            decision.mensaje_decision = "2a fase: sin candidatos adicionales"
            return decision

        analisis = []
        for c in candidatos:
            ev = self._puntaje_evidencia(archivo, c)
            analisis.append((c, ev))
            registrar_evento(
                "second_stage_candidate_analysis",
                archivo=archivo.nombre_archivo,
                datos={
                    "estrategia": estrategia,
                    "recording_id": c.recording_id,
                    "release_id": c.release_id,
                    "evidencia": round(ev, 4),
                },
            )

        analisis.sort(key=lambda x: x[1], reverse=True)
        mejor, score_ev = analisis[0]
        segundo_score = analisis[1][1] if len(analisis) > 1 else 0.0
        gap = score_ev - segundo_score

        score_base = max(decision.puntaje_maximo, getattr(mejor, "puntaje_total", 0.0) or 0.0)
        score_nuevo = min(1.0, score_base + (score_ev - 0.5) * 0.25)

        tiene_senal_fuerte = (
            bool(archivo.isrc_disponible and mejor.isrc and archivo.isrc_disponible == mejor.isrc)
            or bool(archivo.resultado_acoustid and mejor.recording_id in (archivo.resultado_acoustid.recording_ids or []))
        )

        umbral_evidencia = SECOND_STAGE_MIN_EVIDENCE
        if estrategia == "score_intermedio":
            umbral_evidencia -= 0.03
        elif estrategia == "conflicto_version":
            umbral_evidencia += 0.04
        elif estrategia == "conflicto_alias":
            umbral_evidencia += 0.02

        if score_ev >= umbral_evidencia and gap >= SECOND_STAGE_MIN_GAP and tiene_senal_fuerte:
            decision.candidato_elegido = mejor
            decision.puntaje_maximo = round(max(score_nuevo, SCORE_THRESHOLD_REVIEW), 4)
            decision.causa_revision = None
            decision.causa_cuarentena = None
            decision.tipo = (
                DecisionTipo.ACEPTADO
                if (mejor.tipo_release in ACCEPTED_RELEASE_TYPES)
                else DecisionTipo.ACEPTADO_PROVISIONAL
            )
            decision.mensaje_decision = (
                f"2a fase {estrategia}: evidencia={score_ev:.3f} gap={gap:.3f}"
            )
            exito, causa_escritura, msg = self._writer_fn(
                decision,
                directorio_biblioteca=self._dir_biblioteca,
                directorio_temp=self._dir_temp,
            )
            if not exito:
                decision.tipo = DecisionTipo.CUARENTENA
                decision.causa_cuarentena = causa_escritura or CuarentenaCausa.ESCRITURA_FALLIDA
                decision.mensaje_decision = f"2a fase promovio pero fallo escritura: {msg}"
            return decision

        decision.mensaje_decision = (
            f"2a fase sin promotion: evidencia={score_ev:.3f} gap={gap:.3f}"
        )
        return decision

    @staticmethod
    def _puntaje_evidencia(archivo, candidato) -> float:
        norm = archivo.metadata_norm
        if norm is None:
            return 0.0

        titulo = similitud_combinada(
            para_comparacion(limpiar_version_titulo(norm.titulo or "")),
            para_comparacion(limpiar_version_titulo(candidato.titulo_oficial or "")),
        )
        artista = similitud_combinada(
            para_comparacion(norm.artista_principal or ""),
            para_comparacion(candidato.artista_principal or ""),
        )

        duracion = 0.5
        if norm.duracion_seg and candidato.duracion_seg:
            diff = abs(norm.duracion_seg - candidato.duracion_seg)
            if diff <= 2:
                duracion = 1.0
            elif diff <= 5:
                duracion = 0.8
            elif diff <= 12:
                duracion = 0.6
            else:
                duracion = 0.2

        isrc = 0.0
        if archivo.isrc_disponible and candidato.isrc:
            isrc = 1.0 if archivo.isrc_disponible == candidato.isrc else 0.0

        acoustid = 0.0
        if archivo.resultado_acoustid and candidato.recording_id:
            acoustid = 1.0 if candidato.recording_id in (archivo.resultado_acoustid.recording_ids or []) else 0.0

        return round(
            (titulo * 0.28)
            + (artista * 0.26)
            + (duracion * 0.18)
            + (isrc * 0.18)
            + (acoustid * 0.10),
            4,
        )

    def _es_elegible(self, decision: DecisionArchivo) -> tuple[bool, str]:
        if decision.tipo not in (DecisionTipo.REVISION, DecisionTipo.CUARENTENA):
            return False, "estado_no_reprocesable"

        if decision.tipo == DecisionTipo.CUARENTENA:
            if decision.causa_cuarentena in {
                CuarentenaCausa.ARCHIVO_CORRUPTO,
                CuarentenaCausa.ARCHIVO_ILEGIBLE,
                CuarentenaCausa.ARCHIVO_MUY_PEQUENO,
                CuarentenaCausa.DURACION_INVALIDA,
                CuarentenaCausa.BITRATE_INSUFICIENTE,
                CuarentenaCausa.METADATA_INSUFICIENTE,
                CuarentenaCausa.SIN_CANDIDATOS,
                CuarentenaCausa.PUNTAJE_BAJO,
                CuarentenaCausa.ESCRITURA_FALLIDA,
                CuarentenaCausa.VALIDACION_POST_ESCRITURA,
            }:
                return False, "cuarentena_inviable"

        if decision.tipo == DecisionTipo.REVISION:
            if decision.causa_revision in {
                RevisionCausa.CANDIDATOS_AMBIGUOS,
                RevisionCausa.PUNTAJE_INTERMEDIO,
                RevisionCausa.FUENTES_DISCREPANTES,
            }:
                return True, "ok"
            return False, "revision_no_elegible"

        return True, "ok"

    def _estrategia_para(self, decision: DecisionArchivo) -> str:
        titulo = (decision.archivo.metadata_norm.titulo if decision.archivo.metadata_norm else "").lower()
        if any(k in titulo for k in ("live", "remix", "remaster", "acoustic")):
            return "conflicto_version"
        if decision.causa_revision == RevisionCausa.CANDIDATOS_AMBIGUOS and not self._ia_activa:
            return "ambiguo_sin_ia"
        if decision.causa_revision == RevisionCausa.PUNTAJE_INTERMEDIO:
            return "score_intermedio"
        if decision.causa_revision == RevisionCausa.FUENTES_DISCREPANTES:
            return "conflicto_alias"
        if decision.causa_revision == RevisionCausa.CLASIFICACION_PROVISIONAL:
            return "release_incompleto"
        return "consistencia_evidencias"

    def _causa_recuperable(self, decision: DecisionArchivo) -> str:
        if not SECOND_STAGE_CAUSE_ENABLED:
            return "legacy"
        if decision.causa_revision == RevisionCausa.CANDIDATOS_AMBIGUOS:
            return "candidatos_ambiguos"
        if decision.causa_revision == RevisionCausa.PUNTAJE_INTERMEDIO:
            return "score_intermedio"
        if decision.causa_revision == RevisionCausa.FUENTES_DISCREPANTES:
            return "conflicto_featuring_alias"
        if decision.causa_revision == RevisionCausa.CLASIFICACION_PROVISIONAL:
            return "release_incompleto"
        return "otros"

    @staticmethod
    def _filtrar_candidatos_por_estrategia(candidatos, estrategia: str, norm) -> list:
        if estrategia == "release_incompleto":
            target_album = para_comparacion(norm.album or "")
            filtrados = [
                c for c in candidatos
                if target_album and para_comparacion(c.album_oficial or "") == target_album
            ]
            return filtrados or candidatos
        if estrategia == "conflicto_alias":
            # priorizar releases oficiales para discrepancias de fuente
            filtrados = [c for c in candidatos if getattr(c, "es_oficial", False)]
            return filtrados or candidatos
        if estrategia == "conflicto_version":
            base = para_comparacion(limpiar_version_titulo(norm.titulo or ""))
            filtrados = [
                c for c in candidatos
                if para_comparacion(limpiar_version_titulo(c.titulo_oficial or "")) == base
            ]
            return filtrados or candidatos
        return candidatos

    @staticmethod
    def _causa_inicial(decision: DecisionArchivo) -> Optional[str]:
        if decision.causa_revision:
            return decision.causa_revision.value
        if decision.causa_cuarentena:
            return decision.causa_cuarentena.value
        return None
