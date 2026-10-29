from pathlib import Path
import json
from core.audio_intelligence_deep import write_deep_manifest

def test_deep_manifest_line_format(tmp_path: Path):
    row={
        "track_id":"1",
        "file_hash":"h",
        "analyzer_version":"v1",
        "analysis_status":"ready",
        "model_summary_json": json.dumps({"successful_models":["mood_happy"]}),
        "model_outputs_json": json.dumps({"mood_happy":{"score":0.8}}),
        "raw_output_json": json.dumps({"mood_happy":[0.8,0.2]}),
        "inference_time_ms":12,
        "error_code":"",
        "error_message":"",
        "analyzed_at":"2026-01-01T00:00:00Z",
    }
    write_deep_manifest(tmp_path, row)
    p=tmp_path/'enrichment'/'deep_audio_features_manifest.jsonl'
    data=json.loads(p.read_text(encoding='utf-8').splitlines()[0])
    assert data['track_id']=='1'
    assert 'normalized_outputs' in data
    assert 'raw_outputs' in data
    assert data['status'] == 'ready'
