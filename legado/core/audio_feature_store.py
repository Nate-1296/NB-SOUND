"""
audio_feature_store.py
----------------------
Capa de persistencia para features de audio ligero (librosa).

Responsabilidades:
    - Escribir o actualizar la fila de track_audio_features en SQLite.
    - Escribir o actualizar las filas de track_vibe_tags derivadas del análisis básico.
    - Escribir entradas de log en manifests JSONL para auditoría y replay.

Contrato de persistencia:
    - La clave primaria de track_audio_features es track_id.  Un upsert
      por ON CONFLICT sobreescribe todos los campos sin duplicar filas.
    - Las vibe tags tienen clave compuesta (track_id, tag, source).
      Un upsert actualiza score, confidence, explanation y analyzer_version
      si la tag ya existía para ese source.
    - Los manifests JSONL son append-only y sirven como registro histórico;
      no se sincronizan con eliminaciones en la DB.

Threading:
    - Las funciones de escritura aceptan conn opcional.  Si conn es None,
      usan ejecutar() del pool global (thread-safe).  Si conn se provee,
      el caller es responsable del commit/rollback.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.audio_features import AudioFeatureResult, derive_vibe_tags


def upsert_audio_features(conn, result: AudioFeatureResult) -> None:
    """
    Inserta o actualiza la fila de features en track_audio_features.

    Usa ON CONFLICT(track_id) para garantizar idempotencia: llamar esta
    función dos veces con el mismo resultado sobreescribe la fila existente
    y actualiza updated_at, sin duplicar.

    Args:
        conn: Conexión SQLite activa, o None para usar el pool global.
        result: Resultado del análisis a persistir.
    """
    from db.conexion import ejecutar
    data = result.to_dict()
    columns = list(data.keys())
    placeholders = ",".join(["?"] * len(columns))
    update_cols = [col for col in columns if col != "track_id"]
    assignments = ", ".join(f"{col}=excluded.{col}" for col in update_cols)
    sql = (
        f"INSERT INTO track_audio_features ({','.join(columns)})"
        f" VALUES ({placeholders})"
        f" ON CONFLICT(track_id) DO UPDATE SET {assignments}, updated_at=datetime('now')"
    )
    params = tuple(data[col] for col in columns)
    if conn is not None:
        conn.execute(sql, params)
    else:
        ejecutar(sql, params)


def upsert_vibe_tags(conn, tags: list[dict]) -> None:
    """
    Inserta o actualiza vibe tags en track_vibe_tags.

    La clave de conflicto es (track_id, tag, source), lo que permite
    coexistir tags del mismo nombre generadas por fuentes distintas
    (e.g. 'basic_rules' y 'deep_model').

    Args:
        conn: Conexión SQLite activa, o None para usar el pool global.
        tags: Lista de dicts en el formato producido por derive_vibe_tags().
    """
    from db.conexion import ejecutar
    sql = """
        INSERT INTO track_vibe_tags(
            track_id, tag, score, confidence, source, explanation,
            analyzer_version, updated_at
        ) VALUES(?,?,?,?,?,?,?,datetime('now'))
        ON CONFLICT(track_id, tag, source) DO UPDATE SET
            score=excluded.score,
            confidence=excluded.confidence,
            explanation=excluded.explanation,
            analyzer_version=excluded.analyzer_version,
            updated_at=excluded.updated_at
    """
    for tag in tags:
        params = (
            tag["track_id"],
            tag["tag"],
            tag["score"],
            tag["confidence"],
            tag["source"],
            tag.get("explanation", ""),
            tag.get("analyzer_version", result_version(tag)),
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            ejecutar(sql, params)


def result_version(tag: dict) -> str:
    return str(tag.get("analyzer_version") or "")


def write_audio_feature_manifests(base_dir: Path | None, result: AudioFeatureResult, tags: list[dict]) -> None:
    """
    Escribe entradas JSONL en los manifests de features y vibe tags.

    Los manifests sirven para:
        - Auditoría post-importación sin necesidad de consultar la DB.
        - Replay de análisis si la DB se corrompe.
        - Inspección rápida de features por archivo de texto.

    Archivos generados:
        {base_dir}/enrichment/audio_features_manifest.jsonl
        {base_dir}/enrichment/vibe_tags_manifest.jsonl

    Si base_dir es None, la función es un no-op (modo sin assets persistidos).
    """
    if base_dir is None:
        return
    enrichment_dir = base_dir / "enrichment"
    enrichment_dir.mkdir(parents=True, exist_ok=True)
    feature_manifest = enrichment_dir / "audio_features_manifest.jsonl"
    vibe_manifest = enrichment_dir / "vibe_tags_manifest.jsonl"
    with feature_manifest.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "track_id": result.track_id,
                    "file_path": result.file_path,
                    "file_hash": result.file_hash,
                    "analyzer_version": result.analyzer_version,
                    "analysis_mode": result.analysis_mode,
                    "status": result.analysis_status,
                    "started_at": result.started_at,
                    "analyzed_at": result.analyzed_at,
                    "duration_sec": result.duration_sec,
                    "bpm": result.bpm,
                    "energy": result.energy,
                    "danceability_proxy": result.danceability_proxy,
                    "valence_proxy": result.valence_proxy,
                    "error_code": result.error_code,
                    "error_message": result.error_message,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    with vibe_manifest.open("a", encoding="utf-8") as fh:
        for tag in tags:
            fh.write(json.dumps(tag, ensure_ascii=False) + "\n")


def persist_basic_analysis(conn, base_dir: Path | None, result: AudioFeatureResult) -> list[dict]:
    """
    Punto de entrada principal para persistir un análisis de audio básico.

    Orquesta en orden:
        1. Derivar vibe tags (solo si analysis_status='ready').
        2. Upsert features en DB.
        3. Upsert tags en DB.
        4. Escribir manifests JSONL.

    Returns:
        Lista de vibe tags derivadas y persistidas.
    """
    tags = derive_vibe_tags(result) if result.analysis_status == "ready" else []
    upsert_audio_features(conn, result)
    upsert_vibe_tags(conn, tags)
    write_audio_feature_manifests(base_dir, result, tags)
    return tags
