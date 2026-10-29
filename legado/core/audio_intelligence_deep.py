from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import settings

ANALYZER_VERSION = "audio_intel_essentia_v2"


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    task: str
    filename: str
    metadata_filename: str
    predictor_family: str
    output_node: str
    classes: tuple[str, ...] = ()
    positive_class: str = ""
    required_embedding: str = ""
    embedding_filename: str = ""
    embedding_output_node: str = ""
    legacy_filenames: tuple[str, ...] = ()
    top_n: int = 8
    official_url: str = ""
    notes: str = ""

    @property
    def candidate_filenames(self) -> tuple[str, ...]:
        return (self.filename, *self.legacy_filenames)


MODELS: tuple[ModelSpec, ...] = (
    ModelSpec(
        "msd_musicnn_embeddings",
        "embeddings",
        "msd-musicnn-1.pb",
        "msd-musicnn-1.json",
        "musicnn_embedding",
        "model/dense/BiasAdd",
        official_url="https://essentia.upf.edu/models/feature-extractors/musicnn/msd-musicnn-1.json",
    ),
    ModelSpec(
        "audioset_vggish_embeddings",
        "embeddings",
        "audioset-vggish-3.pb",
        "audioset-vggish-3.json",
        "vggish_embedding",
        "model/vggish/embeddings",
        official_url="https://essentia.upf.edu/models/feature-extractors/vggish/audioset-vggish-3.json",
    ),
    ModelSpec(
        "tags_msd50",
        "auto_tagging",
        "msd-musicnn-1.pb",
        "msd-musicnn-1.json",
        "musicnn_tags",
        "model/Sigmoid",
        classes=(
            "rock", "pop", "alternative", "indie", "electronic", "female vocalists",
            "dance", "00s", "alternative rock", "jazz", "beautiful", "metal",
            "chillout", "male vocalists", "classic rock", "soul", "indie rock",
            "Mellow", "electronica", "80s", "folk", "90s", "chill",
            "instrumental", "punk", "oldies", "blues", "hard rock", "ambient",
            "acoustic", "experimental", "female vocalist", "guitar", "Hip-Hop",
            "70s", "party", "country", "easy listening", "sexy", "catchy",
            "funk", "electro", "heavy metal", "Progressive rock", "60s", "rnb",
            "indie pop", "sad", "House", "happy",
        ),
        official_url="https://essentia.upf.edu/models/feature-extractors/musicnn/msd-musicnn-1.json",
    ),
    ModelSpec(
        "danceability",
        "danceability",
        "danceability-msd-musicnn-1.pb",
        "danceability-msd-musicnn-1.json",
        "musicnn_head",
        "model/Softmax",
        classes=("danceable", "not_danceable"),
        positive_class="danceable",
        required_embedding="msd_musicnn_embeddings",
        embedding_filename="msd-musicnn-1.pb",
        embedding_output_node="model/dense/BiasAdd",
        legacy_filenames=("danceability.pb",),
        official_url="https://essentia.upf.edu/models/classification-heads/danceability/danceability-msd-musicnn-1.json",
    ),
    ModelSpec(
        "mood_aggressive",
        "mood",
        "mood_aggressive-msd-musicnn-1.pb",
        "mood_aggressive-msd-musicnn-1.json",
        "musicnn_head",
        "model/Softmax",
        classes=("aggressive", "not_aggressive"),
        positive_class="aggressive",
        required_embedding="msd_musicnn_embeddings",
        embedding_filename="msd-musicnn-1.pb",
        embedding_output_node="model/dense/BiasAdd",
        official_url="https://essentia.upf.edu/models/classification-heads/mood_aggressive/mood_aggressive-msd-musicnn-1.json",
    ),
    ModelSpec(
        "mood_happy",
        "mood",
        "mood_happy-msd-musicnn-1.pb",
        "mood_happy-msd-musicnn-1.json",
        "musicnn_head",
        "model/Softmax",
        classes=("happy", "non_happy"),
        positive_class="happy",
        required_embedding="msd_musicnn_embeddings",
        embedding_filename="msd-musicnn-1.pb",
        embedding_output_node="model/dense/BiasAdd",
        legacy_filenames=("mood_happy.pb",),
        official_url="https://essentia.upf.edu/models/classification-heads/mood_happy/mood_happy-msd-musicnn-1.json",
    ),
    ModelSpec(
        "mood_party",
        "mood",
        "mood_party-msd-musicnn-1.pb",
        "mood_party-msd-musicnn-1.json",
        "musicnn_head",
        "model/Softmax",
        classes=("non_party", "party"),
        positive_class="party",
        required_embedding="msd_musicnn_embeddings",
        embedding_filename="msd-musicnn-1.pb",
        embedding_output_node="model/dense/BiasAdd",
        official_url="https://essentia.upf.edu/models/classification-heads/mood_party/mood_party-msd-musicnn-1.json",
    ),
    ModelSpec(
        "mood_relaxed",
        "mood",
        "mood_relaxed-msd-musicnn-1.pb",
        "mood_relaxed-msd-musicnn-1.json",
        "musicnn_head",
        "model/Softmax",
        classes=("non_relaxed", "relaxed"),
        positive_class="relaxed",
        required_embedding="msd_musicnn_embeddings",
        embedding_filename="msd-musicnn-1.pb",
        embedding_output_node="model/dense/BiasAdd",
        official_url="https://essentia.upf.edu/models/classification-heads/mood_relaxed/mood_relaxed-msd-musicnn-1.json",
    ),
    ModelSpec(
        "mood_sad",
        "mood",
        "mood_sad-msd-musicnn-1.pb",
        "mood_sad-msd-musicnn-1.json",
        "musicnn_head",
        "model/Softmax",
        classes=("non_sad", "sad"),
        positive_class="sad",
        required_embedding="msd_musicnn_embeddings",
        embedding_filename="msd-musicnn-1.pb",
        embedding_output_node="model/dense/BiasAdd",
        legacy_filenames=("mood_sad.pb",),
        official_url="https://essentia.upf.edu/models/classification-heads/mood_sad/mood_sad-msd-musicnn-1.json",
    ),
    ModelSpec(
        "arousal_valence",
        "arousal_valence",
        "deam-msd-musicnn-2.pb",
        "deam-msd-musicnn-2.json",
        "musicnn_head",
        "model/Identity",
        classes=("valence", "arousal"),
        required_embedding="msd_musicnn_embeddings",
        embedding_filename="msd-musicnn-1.pb",
        embedding_output_node="model/dense/BiasAdd",
        official_url="https://essentia.upf.edu/models/classification-heads/deam/deam-msd-musicnn-2.json",
    ),
    ModelSpec(
        "genre_discogs400",
        "genre_style",
        "genre_discogs400-discogs-effnet-1.pb",
        "genre_discogs400-discogs-effnet-1.json",
        "effnet_head",
        "PartitionedCall:0",
        required_embedding="discogs_effnet_embeddings",
        embedding_filename="discogs-effnet-bs64-1.pb",
        embedding_output_node="PartitionedCall:1",
        top_n=10,
        official_url="https://essentia.upf.edu/models/classification-heads/genre_discogs400/genre_discogs400-discogs-effnet-1.json",
    ),
)


def _to_builtin(value: Any) -> Any:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, tuple):
        return [_to_builtin(v) for v in value]
    if isinstance(value, list):
        return [_to_builtin(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _to_builtin(v) for k, v in value.items()}
    try:
        import numpy as np
    except ImportError:
        return value
    if isinstance(value, np.generic):
        return value.item()
    return value


def _mean_vector(prediction: Any) -> list[float]:
    data = _to_builtin(prediction)
    if data is None:
        return []
    if isinstance(data, (int, float)):
        return [float(data)]
    if not isinstance(data, list):
        return []
    if not data:
        return []
    if all(isinstance(v, (int, float)) for v in data):
        return [float(v) for v in data]
    rows = [row for row in data if isinstance(row, list) and row]
    if not rows:
        return []
    width = max(len(row) for row in rows)
    out: list[float] = []
    for idx in range(width):
        values = [float(row[idx]) for row in rows if idx < len(row) and isinstance(row[idx], (int, float))]
        out.append(float(statistics.fmean(values)) if values else 0.0)
    return out


def _clip01(value: Any) -> float | None:
    try:
        return float(max(0.0, min(1.0, float(value))))
    except (TypeError, ValueError):
        return None


def _safe_json_load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _top_scores(classes: tuple[str, ...], vector: list[float], limit: int) -> list[dict]:
    pairs = []
    for idx, score in enumerate(vector):
        label = classes[idx] if idx < len(classes) else f"class_{idx}"
        pairs.append({"label": label, "score": float(score)})
    pairs.sort(key=lambda item: item["score"], reverse=True)
    return pairs[:limit]


class EssentiaTensorflowAnalyzer:
    def __init__(
        self,
        model_dir: str | None = None,
        *,
        backend: str | None = None,
        enable_mood_models: bool | None = None,
        enable_embeddings: bool | None = None,
        enable_tagging_models: bool | None = None,
        essentia_standard=None,
    ):
        raw_model_dir = str(model_dir if model_dir is not None else settings.AUDIO_INTELLIGENCE_MODEL_DIR or "").strip()
        self.model_dir_configured = bool(raw_model_dir)
        self.model_dir = Path(raw_model_dir) if raw_model_dir else Path("")
        self.backend = (backend if backend is not None else settings.AUDIO_INTELLIGENCE_BACKEND).strip().lower()
        self.enable_mood_models = settings.ENABLE_AUDIO_MOOD_MODELS if enable_mood_models is None else bool(enable_mood_models)
        self.enable_embeddings = settings.ENABLE_AUDIO_EMBEDDINGS if enable_embeddings is None else bool(enable_embeddings)
        self.enable_tagging_models = settings.ENABLE_AUDIO_TAGGING_MODELS if enable_tagging_models is None else bool(enable_tagging_models)
        self._essentia_standard = essentia_standard

    def backend_available(self) -> tuple[bool, str]:
        if self.backend in {"", "none", "disabled"}:
            return False, "backend_disabled"
        if self.backend not in {"essentia", "essentia_tensorflow", "essentia-tensorflow"}:
            return False, f"unsupported_backend:{self.backend}"
        if self._essentia_standard is not None:
            return True, ""
        try:
            import essentia.standard as es
        except Exception as exc:
            return False, str(exc)
        required = {"MonoLoader", "TensorflowPredictMusiCNN", "TensorflowPredict2D"}
        enabled_specs = [spec for spec in MODELS if self._enabled_for_spec(spec)]

        if any(spec.predictor_family == "vggish_embedding" for spec in enabled_specs):
            required.add("TensorflowPredictVGGish")

        if any(spec.predictor_family == "effnet_head" for spec in enabled_specs):
            required.add("TensorflowPredictEffnetDiscogs")

        missing = sorted(name for name in required if not hasattr(es, name))
        if missing:
            return False, "missing_essentia_tensorflow_algorithms:" + ",".join(missing)
        self._essentia_standard = es
        return True, ""

    def _es(self):
        ok, error = self.backend_available()
        if not ok:
            raise RuntimeError(error)
        return self._essentia_standard

    def _enabled_for_spec(self, spec: ModelSpec) -> bool:
        if spec.task == "mood":
            return self.enable_mood_models
        if spec.task in {"embeddings", "arousal_valence", "danceability"}:
            return self.enable_embeddings or spec.task in {"arousal_valence", "danceability"}
        if spec.task in {"auto_tagging", "genre_style"}:
            return self.enable_tagging_models
        return True

    def _resolve_model_path(self, spec: ModelSpec) -> Path:
        for filename in spec.candidate_filenames:
            path = self.model_dir / filename
            if path.exists():
                return path
        return self.model_dir / spec.filename

    def available_models(self) -> list[dict]:
        out = []
        model_dir_exists = self.model_dir_configured and self.model_dir.exists()
        for spec in MODELS:
            path = self._resolve_model_path(spec)
            required_paths = [path]
            if spec.embedding_filename:
                required_paths.append(self.model_dir / spec.embedding_filename)
            missing = [str(p) for p in required_paths if not p.exists()]
            metadata = _safe_json_load(self.model_dir / spec.metadata_filename)
            if metadata.get("classes") and not spec.classes:
                classes = tuple(str(c) for c in metadata.get("classes", []))
            else:
                classes = spec.classes
            out.append(
                {
                    "model_id": spec.model_id,
                    "task": spec.task,
                    "path": str(path),
                    "metadata_path": str(self.model_dir / spec.metadata_filename),
                    "required_embedding": spec.required_embedding,
                    "required_files": [str(p) for p in required_paths],
                    "missing_files": missing,
                    "is_available": model_dir_exists and not missing,
                    "enabled": self._enabled_for_spec(spec),
                    "classes": list(classes),
                    "official_url": spec.official_url,
                    "error_message": "" if model_dir_exists and not missing else "model_file_missing",
                }
            )
        return out

    def missing_models(self) -> list[dict]:
        return [m for m in self.available_models() if not m["is_available"]]

    def validate_task(self, task: str) -> bool:
        return task in {spec.task for spec in MODELS}

    def analyze(self, track_id: str, audio_path: str) -> dict:
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        t0 = time.perf_counter()
        ok, err = self.backend_available()
        if not ok:
            return self._status_payload(
                track_id,
                "skipped",
                started_at,
                t0,
                error_code="backend_unavailable",
                error_message=err,
                summary={"backend": self.backend, "available": False},
            )
        if not self.model_dir_configured or not self.model_dir.exists():
            return self._status_payload(
                track_id,
                "skipped",
                started_at,
                t0,
                error_code="model_dir_missing",
                error_message=str(self.model_dir),
                summary={"backend": self.backend, "model_dir": str(self.model_dir), "models": self.available_models()},
            )

        model_infos = self.available_models()
        runnable_specs = [
            spec for spec, info in zip(MODELS, model_infos)
            if info["is_available"] and info["enabled"]
        ]
        if not runnable_specs:
            return self._status_payload(
                track_id,
                "skipped",
                started_at,
                t0,
                error_code="models_missing",
                error_message="No hay modelos deep habilitados y disponibles",
                summary={"backend": self.backend, "model_dir": str(self.model_dir), "models": model_infos},
            )

        raw_outputs: dict[str, Any] = {}
        normalized: dict[str, Any] = {}
        errors: dict[str, dict[str, str]] = {}
        embeddings_cache: dict[str, Any] = {}
        audio = None

        for spec in runnable_specs:
            try:
                if audio is None:
                    audio = self._load_audio(audio_path)
                raw, norm, cache_key, cache_value = self._run_spec(spec, audio, embeddings_cache)
                raw_outputs[spec.model_id] = _to_builtin(raw)
                normalized[spec.model_id] = norm
                if cache_key:
                    embeddings_cache[cache_key] = cache_value
            except Exception as exc:
                errors[spec.model_id] = {
                    "error_code": "model_inference_error",
                    "error_message": str(exc)[:500],
                }

        fields = self._model_fields(normalized)
        status = "ready" if normalized else ("failed" if errors else "skipped")
        error_code = "" if status == "ready" else ("all_models_failed" if errors else "models_missing")
        error_message = "" if status == "ready" else json.dumps(errors, ensure_ascii=False)[:500]
        summary = {
            "backend": self.backend,
            "model_dir": str(self.model_dir),
            "models": model_infos,
            "successful_models": list(normalized.keys()),
            "failed_models": errors,
            "analyzer_version": ANALYZER_VERSION,
        }
        return self._status_payload(
            track_id,
            status,
            started_at,
            t0,
            error_code=error_code,
            error_message=error_message,
            outputs=normalized,
            raw=raw_outputs,
            summary=summary,
            extra_fields=fields,
        )

    def _load_audio(self, audio_path: str):
        es = self._es()
        return es.MonoLoader(filename=str(audio_path), sampleRate=16000, resampleQuality=4)()

    def _run_spec(self, spec: ModelSpec, audio, embeddings_cache: dict[str, Any]) -> tuple[Any, dict, str, Any]:
        es = self._es()
        path = self._resolve_model_path(spec)
        metadata = _safe_json_load(self.model_dir / spec.metadata_filename)
        classes = tuple(str(c) for c in metadata.get("classes", spec.classes))

        if spec.predictor_family == "musicnn_embedding":
            predictor = es.TensorflowPredictMusiCNN(graphFilename=str(path), output=spec.output_node)
            raw = predictor(audio)
            vector = _mean_vector(raw)
            return raw, {"dim": len(vector), "mean": vector}, spec.model_id, raw

        if spec.predictor_family == "vggish_embedding":
            predictor_factory = getattr(es, "TensorflowPredictVGGish", None)
            if predictor_factory is None:
                raise RuntimeError("missing_essentia_tensorflow_algorithm:TensorflowPredictVGGish")
            predictor = predictor_factory(graphFilename=str(path), output=spec.output_node)
            raw = predictor(audio)
            vector = _mean_vector(raw)
            return raw, {"dim": len(vector), "mean": vector}, spec.model_id, raw

        if spec.predictor_family == "musicnn_tags":
            predictor = es.TensorflowPredictMusiCNN(graphFilename=str(path), output=spec.output_node)
            raw = predictor(audio)
            vector = _mean_vector(raw)
            return raw, {"top_tags": _top_scores(classes, vector, spec.top_n), "scores": dict((item["label"], item["score"]) for item in _top_scores(classes, vector, len(classes)))}, "", None

        if spec.predictor_family == "musicnn_head":
            embeddings = self._musicnn_embeddings(audio, embeddings_cache, spec)
            predictor = es.TensorflowPredict2D(graphFilename=str(path), output=spec.output_node)
            raw = predictor(embeddings)
            vector = _mean_vector(raw)
            if spec.task == "arousal_valence":
                valence = _clip01(vector[0] if len(vector) > 0 else None)
                arousal = _clip01(vector[1] if len(vector) > 1 else None)
                return raw, {"valence": valence, "arousal": arousal, "vector": vector}, "", None
            score = self._positive_score(classes, vector, spec.positive_class)
            return raw, {"score": score, "classes": dict((label, vector[idx] if idx < len(vector) else 0.0) for idx, label in enumerate(classes))}, "", None

        if spec.predictor_family == "effnet_head":
            if "discogs_effnet_embeddings" not in embeddings_cache:
                embedding_model = es.TensorflowPredictEffnetDiscogs(
                    graphFilename=str(self.model_dir / spec.embedding_filename),
                    output=spec.embedding_output_node,
                )
                embeddings_cache["discogs_effnet_embeddings"] = embedding_model(audio)
            predictor = es.TensorflowPredict2D(graphFilename=str(path), output=spec.output_node)
            raw = predictor(embeddings_cache["discogs_effnet_embeddings"])
            vector = _mean_vector(raw)
            return raw, {"top_tags": _top_scores(classes, vector, spec.top_n)}, "", None

        raise ValueError(f"predictor_family no soportado: {spec.predictor_family}")

    def _musicnn_embeddings(self, audio, embeddings_cache: dict[str, Any], spec: ModelSpec):
        es = self._es()
        cache_key = spec.required_embedding or "msd_musicnn_embeddings"
        if cache_key in embeddings_cache:
            return embeddings_cache[cache_key]
        embedding_model = es.TensorflowPredictMusiCNN(
            graphFilename=str(self.model_dir / spec.embedding_filename),
            output=spec.embedding_output_node,
        )
        embeddings = embedding_model(audio)
        embeddings_cache[cache_key] = embeddings
        return embeddings

    @staticmethod
    def _positive_score(classes: tuple[str, ...], vector: list[float], positive_class: str) -> float | None:
        if positive_class and positive_class in classes:
            idx = classes.index(positive_class)
        else:
            idx = 0
        if idx >= len(vector):
            return None
        return _clip01(vector[idx])

    def _model_fields(self, outputs: dict[str, Any]) -> dict[str, Any]:
        fields = {
            "mood_happy": None,
            "mood_sad": None,
            "mood_relaxed": None,
            "mood_aggressive": None,
            "mood_party": None,
            "danceability_model": None,
            "arousal": None,
            "valence": None,
            "embeddings_dim": None,
            "tags_json": "{}",
        }
        for model_id in ("mood_happy", "mood_sad", "mood_relaxed", "mood_aggressive", "mood_party", "danceability"):
            if model_id in outputs:
                key = "danceability_model" if model_id == "danceability" else model_id
                fields[key] = _clip01(outputs[model_id].get("score"))
        if "arousal_valence" in outputs:
            fields["valence"] = _clip01(outputs["arousal_valence"].get("valence"))
            fields["arousal"] = _clip01(outputs["arousal_valence"].get("arousal"))
        for embedding_model_id in ("msd_musicnn_embeddings", "audioset_vggish_embeddings"):
            if embedding_model_id in outputs:
                fields["embeddings_dim"] = int(outputs[embedding_model_id].get("dim") or 0) or None
                break
        tag_payload = {}
        if "tags_msd50" in outputs:
            tag_payload["tags_msd50"] = outputs["tags_msd50"].get("top_tags", [])
        if "genre_discogs400" in outputs:
            tag_payload["genre_discogs400"] = outputs["genre_discogs400"].get("top_tags", [])
        fields["tags_json"] = json.dumps(tag_payload, ensure_ascii=False, sort_keys=True)
        return fields

    def _status_payload(
        self,
        track_id: str,
        status: str,
        started_at: str,
        t0: float,
        *,
        error_code: str = "",
        error_message: str = "",
        outputs: dict | None = None,
        raw: dict | None = None,
        summary: dict | None = None,
        extra_fields: dict | None = None,
    ) -> dict:
        analyzed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        fields = {
            "track_id": str(track_id),
            "analyzer_version": ANALYZER_VERSION,
            "analysis_status": status,
            "error_code": error_code,
            "error_message": error_message,
            "model_outputs_json": json.dumps(outputs or {}, ensure_ascii=False, sort_keys=True),
            "raw_output_json": json.dumps(raw or {}, ensure_ascii=False, sort_keys=True),
            "model_summary_json": json.dumps(summary or {}, ensure_ascii=False, sort_keys=True),
            "inference_time_ms": int((time.perf_counter() - t0) * 1000),
            "started_at": started_at,
            "analyzed_at": analyzed_at,
            "mood_happy": None,
            "mood_sad": None,
            "mood_relaxed": None,
            "mood_aggressive": None,
            "mood_party": None,
            "danceability_model": None,
            "arousal": None,
            "valence": None,
            "embeddings_path": "",
            "embeddings_dim": None,
            "tags_json": "{}",
        }
        fields.update(extra_fields or {})
        return fields


def derive_deep_vibe_tags(result: dict) -> list[dict]:
    if result.get("analysis_status") != "ready":
        return []
    mappings = [
        ("mood_happy", "feliz", "modelo deep mood_happy"),
        ("mood_sad", "triste", "modelo deep mood_sad"),
        ("mood_relaxed", "relajada", "modelo deep mood_relaxed"),
        ("mood_aggressive", "intensa", "modelo deep mood_aggressive"),
        ("mood_party", "fiesta", "modelo deep mood_party"),
        ("danceability_model", "bailable", "modelo deep danceability"),
    ]
    tags = []
    for field, tag, explanation in mappings:
        score = _clip01(result.get(field))
        if score is not None and score >= 0.35:
            tags.append(
                {
                    "track_id": str(result["track_id"]),
                    "tag": tag,
                    "score": round(float(score), 4),
                    "confidence": round(float(score), 4),
                    "source": "deep_model",
                    "explanation": explanation,
                    "analyzer_version": result.get("analyzer_version", ANALYZER_VERSION),
                }
            )
    return tags


def persist_deep_analysis(
    conn,
    base_dir: Path | None,
    result: dict,
    *,
    file_hash: str = "",
    run_id: str = "",
) -> list[dict]:
    from db.conexion import ejecutar

    columns = [
        "track_id", "file_hash", "analyzer_version", "analysis_status",
        "mood_happy", "mood_sad", "mood_relaxed", "mood_aggressive", "mood_party",
        "danceability_model", "arousal", "valence", "embeddings_path", "embeddings_dim",
        "tags_json", "model_outputs_json", "raw_output_json", "inference_time_ms",
        "model_summary_json", "error_code", "error_message", "started_at", "analyzed_at",
        "last_run_id",
    ]
    payload = dict(result)
    payload["file_hash"] = file_hash or payload.get("file_hash", "")
    payload["last_run_id"] = run_id or payload.get("last_run_id", "")
    placeholders = ",".join(["?"] * len(columns))
    update_cols = [col for col in columns if col != "track_id"]
    assignments = ", ".join(f"{col}=excluded.{col}" for col in update_cols)

    sql_features = f"""
        INSERT INTO track_deep_audio_features ({",".join(columns)})
        VALUES ({placeholders})
        ON CONFLICT(track_id) DO UPDATE SET {assignments}, updated_at=datetime('now')
    """
    params_features = tuple(payload.get(col) for col in columns)

    if conn is not None:
        conn.execute(sql_features, params_features)
    else:
        ejecutar(sql_features, params_features)

    tags = derive_deep_vibe_tags(payload)
    for tag in tags:
        sql_tags = """
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
        params_tags = (
            tag["track_id"],
            tag["tag"],
            tag["score"],
            tag["confidence"],
            tag["source"],
            tag["explanation"],
            tag["analyzer_version"],
        )
        if conn is not None:
            conn.execute(sql_tags, params_tags)
        else:
            ejecutar(sql_tags, params_tags)

    write_deep_manifest(base_dir, payload)
    return tags


def write_deep_manifest(base_dir: Path | None, result: dict) -> None:
    if base_dir is None:
        return
    manifest_path = base_dir / "enrichment" / "deep_audio_features_manifest.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "track_id": result.get("track_id"),
                    "file_hash": result.get("file_hash", ""),
                    "analyzer_version": result.get("analyzer_version", ANALYZER_VERSION),
                    "status": result.get("analysis_status"),
                    "model_summary": json.loads(result.get("model_summary_json") or "{}"),
                    "normalized_outputs": json.loads(result.get("model_outputs_json") or "{}"),
                    "raw_outputs": json.loads(result.get("raw_output_json") or "{}"),
                    "inference_time_ms": int(result.get("inference_time_ms") or 0),
                    "error_code": result.get("error_code", ""),
                    "error_message": result.get("error_message", ""),
                    "analyzed_at": result.get("analyzed_at", ""),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
