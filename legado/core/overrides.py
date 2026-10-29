from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from config.settings import ENABLE_OVERRIDES
from db.conexion import obtener_una_fila, ejecutar
from domain.models import CandidatoMB
from utils.text import para_comparacion


@dataclass
class OverrideResult:
    key: str
    match_type: str
    payload: dict
    reason: str
    source: str


class MemoriaOverrides:
    def __init__(self) -> None:
        self._enabled = ENABLE_OVERRIDES

    def buscar_para(self, archivo, metadata_norm) -> Optional[OverrideResult]:
        if not self._enabled:
            return None

        claves: list[tuple[str, str]] = []
        if getattr(archivo, "hash_sha256", None):
            claves.append(("hash", archivo.hash_sha256))
        isrc = archivo.isrc_disponible if archivo is not None else None
        if isrc:
            claves.append(("isrc", isrc))
        if metadata_norm:
            artist = para_comparacion(metadata_norm.artista_principal or "")
            title = para_comparacion(metadata_norm.titulo or "")
            if artist and title:
                claves.append(("artist_title", f"{artist}::{title}"))

        for match_type, match_value in claves:
            row = obtener_una_fila(
                """
                SELECT match_type, match_value, payload_json, reason, source
                FROM overrides_catalogacion
                WHERE active = 1 AND match_type = ? AND match_value = ?
                """,
                (match_type, match_value),
            )
            if not row:
                continue
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError:
                continue
            return OverrideResult(
                key=row["match_value"],
                match_type=row["match_type"],
                payload=payload,
                reason=row["reason"] or "",
                source=row["source"] or "manual",
            )
        return None

    def guardar(self, match_type: str, match_value: str, payload: dict, reason: str = "", source: str = "manual") -> None:
        if not match_type or not match_value:
            raise ValueError("Override invalido: match_type y match_value son obligatorios")
        if not self.validar_payload(payload):
            raise ValueError("Override invalido: payload incompleto")
        json_payload = json.dumps(payload, ensure_ascii=False)
        ejecutar(
            """
            INSERT INTO overrides_catalogacion(match_type, match_value, payload_json, reason, source, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(match_type, match_value) DO UPDATE SET
                payload_json = excluded.payload_json,
                reason = excluded.reason,
                source = excluded.source,
                active = 1,
                updated_at = datetime('now')
            """,
            (match_type, match_value, json_payload, reason, source),
        )

    @staticmethod
    def validar_payload(payload: dict) -> bool:
        if not isinstance(payload, dict):
            return False
        required_any = (
            payload.get("recording_id")
            or payload.get("release_id")
            or payload.get("isrc")
            or payload.get("artista_principal")
            or payload.get("titulo_oficial")
        )
        return bool(required_any)

    @staticmethod
    def candidato_desde_payload(payload: dict) -> Optional[CandidatoMB]:
        if not MemoriaOverrides.validar_payload(payload):
            return None
        return CandidatoMB(
            recording_id=str(payload.get("recording_id") or ""),
            release_id=str(payload.get("release_id") or ""),
            release_group_id=str(payload.get("release_group_id") or ""),
            titulo_oficial=str(payload.get("titulo_oficial") or payload.get("titulo") or ""),
            artista_principal=str(payload.get("artista_principal") or payload.get("artista") or ""),
            album_oficial=str(payload.get("album_oficial") or payload.get("album") or ""),
            tipo_release=str(payload.get("tipo_release") or "Album"),
            isrc=(str(payload.get("isrc")) if payload.get("isrc") else None),
            puntaje_total=1.0,
            puntaje_detalle={"override": 1.0},
        )
