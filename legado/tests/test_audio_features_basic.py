from core.audio_features import AudioFeatureResult, derive_vibe_tags
from core.audio_feature_store import persist_basic_analysis
from db.conexion import cerrar_db, get_conexion, inicializar_db

def test_vibe_tags_from_synthetic_features():
    r = AudioFeatureResult(track_id='1', file_path='x', file_hash='h', energy=0.9, danceability_proxy=0.8, melancholy_proxy=0.2, calmness_proxy=0.1, workout_score_proxy=0.9, party_score_proxy=0.8, focus_score_proxy=0.1, night_score_proxy=0.2)
    tags = {t['tag'] for t in derive_vibe_tags(r)}
    assert 'energetica' in tags
    assert 'bailable' in tags
    assert 'entrenamiento' in tags


def test_persist_basic_analysis_writes_tables_and_manifests(tmp_path):
    inicializar_db(tmp_path / "basic.sqlite")
    result = AudioFeatureResult(
        track_id="1",
        file_path="/tmp/a.mp3",
        file_hash="hash",
        energy=0.9,
        danceability_proxy=0.8,
        melancholy_proxy=0.2,
        calmness_proxy=0.1,
        workout_score_proxy=0.9,
        party_score_proxy=0.8,
        focus_score_proxy=0.1,
        night_score_proxy=0.2,
    )
    tags = persist_basic_analysis(get_conexion(), tmp_path, result)
    assert tags
    row = get_conexion().execute("SELECT * FROM track_audio_features WHERE track_id='1'").fetchone()
    assert row["analysis_status"] == "ready"
    assert get_conexion().execute("SELECT COUNT(*) c FROM track_vibe_tags").fetchone()["c"] >= 1
    assert (tmp_path / "enrichment" / "audio_features_manifest.jsonl").exists()
    assert (tmp_path / "enrichment" / "vibe_tags_manifest.jsonl").exists()
    cerrar_db()


def test_vibe_tags_umbral_035():
    """Scores below 0.35 should NOT produce tags."""
    r = AudioFeatureResult(
        track_id='2', file_path='x', file_hash='h',
        energy=0.34, danceability_proxy=0.34, melancholy_proxy=0.34,
        calmness_proxy=0.34, workout_score_proxy=0.34,
        party_score_proxy=0.34, focus_score_proxy=0.34,
        night_score_proxy=0.34,
    )
    tags = derive_vibe_tags(r)
    assert tags == [], f"No tag should be >= 0.35, but got {tags}"


def test_vibe_tags_exactamente_035():
    """Score exactly at 0.35 SHOULD produce a tag."""
    r = AudioFeatureResult(
        track_id='3', file_path='x', file_hash='h',
        energy=0.35, danceability_proxy=0.0, melancholy_proxy=0.0,
        calmness_proxy=0.0, workout_score_proxy=0.0,
        party_score_proxy=0.0, focus_score_proxy=0.0,
        night_score_proxy=0.0,
    )
    tags = derive_vibe_tags(r)
    assert any(t['tag'] == 'energetica' for t in tags)


def test_audio_feature_result_failed():
    """A failed result should have analysis_status='failed' and not produce vibe tags."""
    r = AudioFeatureResult(
        track_id='err', file_path='/x.mp3', file_hash='h',
        analysis_status='failed',
        error_code='analysis_error',
        error_message='file not found',
    )
    assert r.analysis_status == 'failed'
    tags = derive_vibe_tags(r)
    # energy/etc are None by default, so no tag should be >= 0.35
    assert tags == []


def test_audio_feature_result_to_dict():
    """to_dict() should include all fields."""
    r = AudioFeatureResult(track_id='1', file_path='x', file_hash='h')
    d = r.to_dict()
    assert d['track_id'] == '1'
    assert 'energy' in d
    assert 'bpm' in d
    assert 'key_name' in d


def test_persist_failed_analysis_writes_error(tmp_path):
    """A failed analysis should persist the error status and not create tags."""
    inicializar_db(tmp_path / "failed.sqlite")
    result = AudioFeatureResult(
        track_id="99",
        file_path="/tmp/bad.mp3",
        file_hash="h",
        analysis_status="failed",
        error_code="analysis_error",
        error_message="test error",
    )
    tags = persist_basic_analysis(get_conexion(), tmp_path, result)
    assert tags == []
    row = get_conexion().execute("SELECT * FROM track_audio_features WHERE track_id='99'").fetchone()
    assert row["analysis_status"] == "failed"
    assert row["error_code"] == "analysis_error"
    cerrar_db()


def test_persist_basic_analysis_conn_none_usa_conexion_global(tmp_path):
    """persist_basic_analysis(None, ...) debe usar la conexión global, no crashear con NoneType."""
    inicializar_db(tmp_path / "none_conn.sqlite")
    result = AudioFeatureResult(
        track_id="42",
        file_path="/tmp/b.mp3",
        file_hash="h",
        energy=0.7,
        danceability_proxy=0.6,
        melancholy_proxy=0.3,
        calmness_proxy=0.4,
        workout_score_proxy=0.5,
        party_score_proxy=0.5,
        focus_score_proxy=0.4,
        night_score_proxy=0.3,
    )
    tags = persist_basic_analysis(None, tmp_path, result)
    assert isinstance(tags, list)
    row = get_conexion().execute(
        "SELECT analysis_status FROM track_audio_features WHERE track_id='42'"
    ).fetchone()
    assert row is not None
    assert row["analysis_status"] == "ready"
    cerrar_db()


def test_persist_basic_analysis_conn_none_fallo_no_genera_tags(tmp_path):
    """persist_basic_analysis(None, ...) con status=failed no debe crashear y no genera vibe tags."""
    inicializar_db(tmp_path / "none_fail.sqlite")
    result = AudioFeatureResult(
        track_id="77",
        file_path="/tmp/fail.mp3",
        file_hash="h",
        analysis_status="failed",
        error_code="analysis_error",
        error_message="test",
    )
    tags = persist_basic_analysis(None, tmp_path, result)
    assert tags == []
    row = get_conexion().execute(
        "SELECT analysis_status FROM track_audio_features WHERE track_id='77'"
    ).fetchone()
    assert row is not None
    assert row["analysis_status"] == "failed"
    cerrar_db()


def test_persist_upsert_sobrescribe_anterior(tmp_path):
    """Persisting twice with the same track_id should update, not duplicate."""
    inicializar_db(tmp_path / "upsert.sqlite")
    r1 = AudioFeatureResult(track_id="1", file_path="/a.mp3", file_hash="h1", energy=0.5)
    persist_basic_analysis(get_conexion(), tmp_path, r1)
    r2 = AudioFeatureResult(track_id="1", file_path="/a.mp3", file_hash="h2", energy=0.9)
    persist_basic_analysis(get_conexion(), tmp_path, r2)
    count = get_conexion().execute("SELECT COUNT(*) c FROM track_audio_features WHERE track_id='1'").fetchone()["c"]
    assert count == 1
    row = get_conexion().execute("SELECT energy FROM track_audio_features WHERE track_id='1'").fetchone()
    assert row["energy"] == 0.9
    cerrar_db()
