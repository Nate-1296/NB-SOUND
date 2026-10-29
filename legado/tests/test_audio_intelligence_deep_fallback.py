from pathlib import Path
import sys
import types

from db.conexion import cerrar_db, get_conexion, inicializar_db
from core.audio_intelligence_deep import (
    EssentiaTensorflowAnalyzer,
    persist_deep_analysis,
)


class _FakePredictor:
    def __init__(self, graphFilename="", output="", **_kwargs):
        self.graph = str(graphFilename)
        self.output = output

    def __call__(self, _input):
        if "msd-musicnn" in self.graph and self.output == "model/dense/BiasAdd":
            return [[0.10] * 200, [0.30] * 200]
        if "msd-musicnn" in self.graph and self.output == "model/Sigmoid":
            values = [0.01] * 50
            values[35] = 0.72
            values[47] = 0.66
            values[49] = 0.80
            return [values]
        if "mood_happy" in self.graph:
            return [0.81, 0.19]
        if "mood_sad" in self.graph:
            return [0.22, 0.78]
        if "mood_relaxed" in self.graph:
            return [0.30, 0.70]
        if "mood_aggressive" in self.graph:
            return [0.44, 0.56]
        if "mood_party" in self.graph:
            return [0.25, 0.75]
        if "danceability" in self.graph:
            return [0.88, 0.12]
        if "deam" in self.graph:
            return [0.62, 0.47]
        return [0.1, 0.9]


class _FakeEssentiaStandard:
    class MonoLoader:
        def __init__(self, **_kwargs):
            pass

        def __call__(self):
            return [0.0, 0.1, -0.1]

    TensorflowPredictMusiCNN = _FakePredictor
    TensorflowPredict2D = _FakePredictor
    TensorflowPredictVGGish = _FakePredictor




def _install_fake_essentia(monkeypatch, attrs: set[str]):
    essentia_pkg = types.ModuleType("essentia")
    standard_mod = types.ModuleType("essentia.standard")

    for attr in attrs:
        setattr(standard_mod, attr, object())

    essentia_pkg.standard = standard_mod
    monkeypatch.setitem(sys.modules, "essentia", essentia_pkg)
    monkeypatch.setitem(sys.modules, "essentia.standard", standard_mod)

    return standard_mod

def _touch_models(model_dir: Path, *names: str):
    for name in names:
        (model_dir / name).write_bytes(b"mock")


def test_backend_disabled_no_importa_essentia(monkeypatch, tmp_path):
    def guarded_import(name, *args, **kwargs):
        if name.startswith("essentia"):
            raise AssertionError("essentia no debía importarse con backend none")
        return original_import(name, *args, **kwargs)

    original_import = __import__
    monkeypatch.setattr("builtins.__import__", guarded_import)
    analyzer = EssentiaTensorflowAnalyzer(model_dir=str(tmp_path), backend="none")
    out = analyzer.analyze("1", "/tmp/no.wav")
    assert out["analysis_status"] == "skipped"
    assert out["error_code"] == "backend_unavailable"




def test_backend_available_detecta_vggish_faltante(monkeypatch, tmp_path: Path):
    _install_fake_essentia(
        monkeypatch,
        {
            "MonoLoader",
            "TensorflowPredictMusiCNN",
            "TensorflowPredict2D",
        },
    )

    analyzer = EssentiaTensorflowAnalyzer(
        model_dir=str(tmp_path),
        backend="essentia_tensorflow",
        enable_mood_models=False,
        enable_embeddings=True,
        enable_tagging_models=False,
    )

    ok, error = analyzer.backend_available()

    assert ok is False
    assert "TensorflowPredictVGGish" in error


def test_backend_available_detecta_effnet_faltante(monkeypatch, tmp_path: Path):
    _install_fake_essentia(
        monkeypatch,
        {
            "MonoLoader",
            "TensorflowPredictMusiCNN",
            "TensorflowPredict2D",
            "TensorflowPredictVGGish",
        },
    )

    analyzer = EssentiaTensorflowAnalyzer(
        model_dir=str(tmp_path),
        backend="essentia_tensorflow",
        enable_mood_models=False,
        enable_embeddings=False,
        enable_tagging_models=True,
    )

    ok, error = analyzer.backend_available()

    assert ok is False
    assert "TensorflowPredictEffnetDiscogs" in error

def test_deep_without_backend_or_models():
    analyzer = EssentiaTensorflowAnalyzer(model_dir="/tmp/nb_sound_missing_models", backend="essentia_tensorflow")
    out = analyzer.analyze("1", "/tmp/no.wav")
    assert out["analysis_status"] == "skipped"
    assert out["error_code"] in {"backend_unavailable", "model_dir_missing"}


def test_model_dir_vacio_produce_skipped_controlado(tmp_path: Path):
    analyzer = EssentiaTensorflowAnalyzer(
        model_dir=str(tmp_path),
        backend="essentia_tensorflow",
        essentia_standard=_FakeEssentiaStandard,
    )
    out = analyzer.analyze("1", "/tmp/no.wav")
    assert out["analysis_status"] == "skipped"
    assert out["error_code"] == "models_missing"


def test_model_dir_con_modelos_mock_detecta_registry(tmp_path: Path):
    _touch_models(
        tmp_path,
        "msd-musicnn-1.pb",
        "audioset-vggish-3.pb",
        "mood_relaxed-msd-musicnn-1.pb",
        "deam-msd-musicnn-2.pb",
    )
    analyzer = EssentiaTensorflowAnalyzer(
        model_dir=str(tmp_path),
        backend="essentia_tensorflow",
        enable_mood_models=True,
        enable_embeddings=True,
        essentia_standard=_FakeEssentiaStandard,
    )
    available = {m["model_id"]: m for m in analyzer.available_models()}
    assert available["mood_relaxed"]["is_available"] is True
    assert available["arousal_valence"]["is_available"] is True
    assert available["audioset_vggish_embeddings"]["is_available"] is True
    assert available["mood_party"]["is_available"] is False


def test_analyzer_mock_normaliza_outputs(tmp_path: Path):
    _touch_models(
        tmp_path,
        "msd-musicnn-1.pb",
        "mood_happy-msd-musicnn-1.pb",
        "mood_sad-msd-musicnn-1.pb",
        "mood_relaxed-msd-musicnn-1.pb",
        "mood_party-msd-musicnn-1.pb",
        "mood_aggressive-msd-musicnn-1.pb",
        "danceability-msd-musicnn-1.pb",
        "deam-msd-musicnn-2.pb",
    )
    analyzer = EssentiaTensorflowAnalyzer(
        model_dir=str(tmp_path),
        backend="essentia_tensorflow",
        enable_mood_models=True,
        enable_embeddings=True,
        enable_tagging_models=True,
        essentia_standard=_FakeEssentiaStandard,
    )
    out = analyzer.analyze("7", "/tmp/audio.mp3")
    assert out["analysis_status"] == "ready"
    assert out["mood_happy"] == 0.81
    assert out["mood_sad"] == 0.78
    assert out["mood_relaxed"] == 0.7
    assert out["mood_party"] == 0.75
    assert out["danceability_model"] == 0.88
    assert out["valence"] == 0.62
    assert out["arousal"] == 0.47
    assert out["embeddings_dim"] == 200


def test_analyzer_mock_normaliza_vggish_embedding(tmp_path: Path):
    _touch_models(tmp_path, "audioset-vggish-3.pb")
    analyzer = EssentiaTensorflowAnalyzer(
        model_dir=str(tmp_path),
        backend="essentia_tensorflow",
        enable_mood_models=False,
        enable_embeddings=True,
        enable_tagging_models=False,
        essentia_standard=_FakeEssentiaStandard,
    )
    out = analyzer.analyze("8", "/tmp/audio.mp3")
    assert out["analysis_status"] == "ready"
    assert out["embeddings_dim"] == 2
    assert "audioset_vggish_embeddings" in out["model_outputs_json"]


def test_persistencia_deep_vibe_tags_y_manifest(tmp_path: Path):
    db = tmp_path / "deep.sqlite"
    inicializar_db(db)
    result = {
        "track_id": "1",
        "analyzer_version": "audio_intel_essentia_v2",
        "analysis_status": "ready",
        "mood_happy": 0.8,
        "mood_sad": 0.1,
        "mood_relaxed": 0.4,
        "mood_aggressive": 0.2,
        "mood_party": 0.7,
        "danceability_model": 0.9,
        "arousal": 0.6,
        "valence": 0.7,
        "embeddings_path": "",
        "embeddings_dim": 200,
        "tags_json": "{}",
        "model_outputs_json": '{"mood_happy":{"score":0.8}}',
        "raw_output_json": '{"mood_happy":[0.8,0.2]}',
        "model_summary_json": '{"successful_models":["mood_happy"]}',
        "inference_time_ms": 12,
        "error_code": "",
        "error_message": "",
        "started_at": "2026-01-01T00:00:00Z",
        "analyzed_at": "2026-01-01T00:00:01Z",
    }
    tags = persist_deep_analysis(get_conexion(), tmp_path, result, file_hash="hash")
    assert any(tag["source"] == "deep_model" for tag in tags)
    row = get_conexion().execute("SELECT * FROM track_deep_audio_features WHERE track_id='1'").fetchone()
    assert row["analysis_status"] == "ready"
    assert row["mood_happy"] == 0.8
    vibe = get_conexion().execute("SELECT COUNT(*) c FROM track_vibe_tags WHERE source='deep_model'").fetchone()
    assert vibe["c"] >= 1
    manifest = tmp_path / "enrichment" / "deep_audio_features_manifest.jsonl"
    assert manifest.exists()
    assert "normalized_outputs" in manifest.read_text(encoding="utf-8")
    cerrar_db()
