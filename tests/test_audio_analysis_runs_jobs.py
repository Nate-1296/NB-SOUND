from pathlib import Path
from db.conexion import inicializar_db, get_conexion, cerrar_db
from core.audio_analysis_runs import AudioRunTracker, compute_eta_metrics

def test_runs_jobs_tables_and_updates(tmp_path: Path):
    db=tmp_path/'x.sqlite'
    inicializar_db(db)
    run=AudioRunTracker('audio_features_basic', {'k':1})
    run.set_total(2)
    j1=run.register_job('1','basic'); run.finish_job(j1,'ready')
    j2=run.register_job('2','basic'); run.finish_job(j2,'failed','e','m')
    summary=run.finish()
    cx=get_conexion()
    assert summary['processed']==2
    assert cx.execute('SELECT COUNT(*) c FROM audio_analysis_jobs').fetchone()['c']==2
    assert cx.execute('SELECT COUNT(*) c FROM audio_analysis_runs').fetchone()['c']==1
    row = cx.execute('SELECT * FROM audio_analysis_runs WHERE run_id=?', (run.run_id,)).fetchone()
    assert row['processed_tracks'] == 2
    assert row['ready_tracks'] == 1
    assert row['failed_tracks'] == 1
    assert row['eta_human'] == '0s'
    job = cx.execute('SELECT run_id FROM audio_analysis_jobs LIMIT 1').fetchone()
    assert job['run_id'] == run.run_id
    cerrar_db()


def test_eta_partial_and_zero_processed():
    zero = compute_eta_metrics(total_tracks=10, processed_tracks=0, started_monotonic=100.0, now_monotonic=105.0)
    assert zero['eta_seconds'] is None
    assert zero['eta_human'] == 'desconocido'

    partial = compute_eta_metrics(total_tracks=10, processed_tracks=2, started_monotonic=100.0, now_monotonic=110.0)
    assert partial['elapsed_ms'] == 10000
    assert partial['avg_ms_per_track'] == 5000
    assert partial['tracks_per_minute'] == 12
    assert partial['eta_seconds'] == 40


def test_run_updates_during_loop_and_finishes(tmp_path: Path):
    db=tmp_path/'loop.sqlite'
    inicializar_db(db)
    run=AudioRunTracker('audio_intelligence_deep', {'backend':'test'})
    run.set_total(3)
    j1=run.register_job('11','deep', current_file_path='/tmp/a.mp3', current_stage='audio_intelligence_deep')
    run.finish_job(j1,'skipped','models_missing','missing')
    cx=get_conexion()
    row = cx.execute('SELECT * FROM audio_analysis_runs WHERE run_id=?', (run.run_id,)).fetchone()
    assert row['processed_tracks'] == 1
    assert row['skipped_tracks'] == 1
    assert row['current_track_id'] == '11'
    assert row['current_file_path'] == '/tmp/a.mp3'
    assert row['current_stage'] == 'audio_intelligence_deep'
    assert row['summary_json']
    summary=run.finish()
    assert summary['processed'] == 1
    assert summary['eta_human'] == '0s'
    cerrar_db()


def test_audio_analysis_schema_idempotent(tmp_path: Path):
    db=tmp_path/'schema.sqlite'
    inicializar_db(db)
    cerrar_db()
    inicializar_db(db)
    cx=get_conexion()
    run_cols={row['name'] for row in cx.execute('PRAGMA table_info(audio_analysis_runs)').fetchall()}
    job_cols={row['name'] for row in cx.execute('PRAGMA table_info(audio_analysis_jobs)').fetchall()}
    assert {'status','pending_tracks','current_track_id','current_file_path','current_stage','last_update_at','avg_ms_per_track','tracks_per_minute','eta_seconds','eta_human','cancel_policy'} <= run_cols
    assert {'run_id','model_version','file_hash','updated_at'} <= job_cols
    deep_cols={row['name'] for row in cx.execute('PRAGMA table_info(track_deep_audio_features)').fetchall()}
    assert 'last_run_id' in deep_cols
    cerrar_db()
