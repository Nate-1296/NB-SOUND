import sqlite3
from core.music_discovery_service import parse_query, MusicDiscoveryService

def _db():
    cx=sqlite3.connect(':memory:')
    cx.row_factory=sqlite3.Row
    cx.execute("CREATE TABLE albums(id INTEGER PRIMARY KEY, portada_ruta TEXT, mb_release_id TEXT)")
    cx.execute("CREATE TABLE pistas(id INTEGER PRIMARY KEY, album_id INTEGER, artista_id INTEGER, titulo TEXT, artista_nombre TEXT, album_titulo TEXT, ruta_archivo TEXT, hash_sha256 TEXT, estado TEXT DEFAULT 'biblioteca', duracion_seg REAL, favorita INTEGER DEFAULT 0)")
    cx.execute('CREATE TABLE track_audio_features(track_id TEXT PRIMARY KEY, analysis_status TEXT, energy REAL, melancholy_proxy REAL, valence_proxy REAL, brightness REAL, party_score_proxy REAL, danceability_proxy REAL, workout_score_proxy REAL, bpm REAL, calmness_proxy REAL, focus_score_proxy REAL, night_score_proxy REAL, darkness_proxy REAL, aggressiveness_proxy REAL)')
    cx.execute('CREATE TABLE track_deep_audio_features(track_id TEXT PRIMARY KEY, analysis_status TEXT, mood_sad REAL, mood_happy REAL, mood_relaxed REAL, mood_aggressive REAL, mood_party REAL, danceability_model REAL, arousal REAL, valence REAL, tags_json TEXT)')
    return cx


# ---------------------------------------------------------------------------
# parse_query — all keyword intents
# ---------------------------------------------------------------------------

def test_parse_keywords():
    assert parse_query('pon algo triste').intent == 'sad'
    assert parse_query('algo para entrenar').intent == 'workout'
    assert parse_query('algo chill').intent == 'chill'


def test_parse_keywords_energetica():
    """Keyword 'energía' / 'energético' should resolve to workout."""
    assert parse_query('quiero energía').intent == 'workout'
    assert parse_query('algo energético').intent == 'workout'
    assert parse_query('canción energetica').intent == 'workout'
    assert parse_query('algo potente').intent == 'workout'
    assert parse_query('algo activo').intent == 'workout'


def test_parse_keywords_fiesta_bailable():
    """Party/dance keywords."""
    assert parse_query('para fiesta').intent == 'party'
    assert parse_query('bailable').intent == 'party'
    assert parse_query('bailar').intent == 'party'


def test_parse_keywords_feliz():
    assert parse_query('algo feliz').intent == 'happy'
    assert parse_query('musica alegre').intent == 'happy'
    assert parse_query('positiva').intent == 'happy'


def test_parse_keywords_concentracion():
    assert parse_query('concentracion').intent == 'focus'
    assert parse_query('para estudiar').intent == 'focus'


def test_parse_keywords_oscura_nocturna():
    assert parse_query('oscura').intent == 'dark'
    assert parse_query('musica nocturna').intent == 'dark'


def test_parse_keywords_intensa_agresiva():
    assert parse_query('intensa').intent == 'intense'
    assert parse_query('agresiva').intent == 'intense'


def test_parse_keywords_suave():
    assert parse_query('algo suave').intent == 'soft'


def test_parse_keywords_velocidad():
    assert parse_query('rapido').intent == 'fast'
    assert parse_query('algo rápido').intent == 'fast'
    assert parse_query('lento').intent == 'slow'
    assert parse_query('despacio').intent == 'slow'


def test_parse_keywords_relajada():
    assert parse_query('algo relajado').intent == 'chill'
    assert parse_query('tranquila').intent == 'chill'
    assert parse_query('calma').intent == 'chill'


def test_parse_query_mixta_combina_intenciones():
    parsed = parse_query('algo triste pero con energía')

    assert parsed.intent == 'mixed'
    assert {'sad', 'workout'} <= set(parsed.weights)


def test_parse_query_sinonimos_ampliados():
    assert parse_query('para estudiar').intent == 'focus'
    assert parse_query('algo oscuro de noche').intent == 'dark'
    assert parse_query('melancólica').intent == 'sad'
    assert parse_query('suave').intent == 'soft'
    assert parse_query('para manejar').intent == 'focus'
    assert parse_query('para caminar').intent == 'workout'
    assert parse_query('para levantar ánimo').intent == 'happy'
    assert parse_query('baja energía').intent == 'soft'


def test_parse_query_sin_intencion():
    """Generic query without strong intent."""
    parsed = parse_query('algo de los beatles')
    assert parsed.intent == 'generic'
    assert 'generic' in parsed.weights


def test_parse_query_vacia():
    """Empty / None query returns generic."""
    assert parse_query('').intent == 'generic'
    assert parse_query(None).intent == 'generic'


# ---------------------------------------------------------------------------
# MusicDiscoveryService — ranking & edge cases
# ---------------------------------------------------------------------------

def test_discovery_ranking():
    cx=_db()
    cx.execute("INSERT INTO albums VALUES(10,'/covers/a.jpg','rel-a')")
    cx.execute("INSERT INTO pistas VALUES(1,10,20,'A','X','ALB','/a','h','biblioteca',120,0)")
    cx.execute("INSERT INTO pistas VALUES(2,11,21,'B','Y','ALB','/b','h2','biblioteca',120,0)")
    cx.execute("INSERT INTO track_audio_features VALUES('1','ready',0.2,0.9,0.1,0.2,0.1,0.1,0.1,80,0.7,0.6,0.8,0.9,0.2)")
    cx.execute("INSERT INTO track_audio_features VALUES('2','ready',0.9,0.1,0.9,0.8,0.9,0.8,0.9,150,0.2,0.2,0.1,0.2,0.9)")
    svc=MusicDiscoveryService(cx, min_confidence=0.0)
    out=svc.discover('pon algo triste', limit=5)
    assert out['results'][0]['track_id'] == '1'
    assert out['results'][0]['origin'] == 'basic'
    assert out['results'][0]['actions']['play'] is True
    assert out['results'][0]['titulo'] == 'A'
    assert out['results'][0]['artista_nombre'] == 'X'
    assert out['results'][0]['album_titulo'] == 'ALB'
    assert out['results'][0]['duracion_seg'] == 120
    assert out['results'][0]['favorita'] == 0
    assert out['results'][0]['portada_ruta'] == '/covers/a.jpg'
    assert 'portada_display_ruta' in out['results'][0]
    assert out['understood'] is True


def test_discovery_consulta_mixta_combina_ranking():
    cx = _db()
    cx.execute("INSERT INTO pistas VALUES(1,10,20,'Sad Low','X','ALB','/a','h','biblioteca',120,0)")
    cx.execute("INSERT INTO pistas VALUES(2,11,21,'Sad Energy','Y','ALB','/b','h2','biblioteca',120,0)")
    cx.execute("INSERT INTO track_audio_features VALUES('1','ready',0.1,0.95,0.05,0.2,0.1,0.1,0.1,75,0.7,0.5,0.8,0.8,0.1)")
    cx.execute("INSERT INTO track_audio_features VALUES('2','ready',0.9,0.85,0.15,0.6,0.4,0.4,0.9,150,0.4,0.4,0.5,0.5,0.3)")
    svc = MusicDiscoveryService(cx, min_confidence=0.0)

    out = svc.discover('algo triste pero con energía', limit=5)

    assert out['intent'] == 'mixed'
    assert out['results'][0]['track_id'] == '2'


def test_discovery_usa_deep_cuando_configurado():
    cx=_db()
    cx.execute("INSERT INTO pistas VALUES(1,10,20,'A','X','ALB','/a','h','biblioteca',120,0)")
    cx.execute("INSERT INTO pistas VALUES(2,11,21,'B','Y','ALB','/b','h2','biblioteca',120,0)")
    cx.execute("INSERT INTO track_audio_features VALUES('1','ready',0.2,0.2,0.8,0.2,0.1,0.1,0.1,80,0.7,0.6,0.8,0.9,0.2)")
    cx.execute("INSERT INTO track_audio_features VALUES('2','ready',0.2,0.2,0.8,0.2,0.1,0.1,0.1,80,0.7,0.6,0.8,0.9,0.2)")
    cx.execute("INSERT INTO track_deep_audio_features VALUES('2','ready',0.95,0.1,0.1,0.1,0.1,0.1,0.2,0.1,'{}')")
    svc=MusicDiscoveryService(cx, use_deep=True, min_confidence=0.0)
    out=svc.discover('pon algo triste', limit=5)
    assert out['results'][0]['track_id'] == '2'
    assert out['results'][0]['origin'] == 'basic+deep'


def test_discovery_db_vacia_sin_pistas():
    """Empty library should return empty results with warning."""
    cx = _db()
    svc = MusicDiscoveryService(cx, min_confidence=0.0)
    out = svc.discover('algo triste', limit=5)
    assert out['results'] == []
    assert len(out['warnings']) > 0


def test_discovery_pistas_sin_features():
    """Tracks exist but no audio features → warning, no crash."""
    cx = _db()
    cx.execute("INSERT INTO pistas VALUES(1,10,20,'A','X','ALB','/a','h','biblioteca',120,0)")
    svc = MusicDiscoveryService(cx, min_confidence=0.0)
    out = svc.discover('algo triste', limit=5)
    assert out['results'] == []
    assert len(out['warnings']) > 0


def test_discovery_min_confidence_filtra():
    """min_confidence should filter out low-score results."""
    cx = _db()
    cx.execute("INSERT INTO pistas VALUES(1,10,20,'A','X','ALB','/a','h','biblioteca',120,0)")
    cx.execute("INSERT INTO track_audio_features VALUES('1','ready',0.1,0.1,0.1,0.1,0.1,0.1,0.1,60,0.1,0.1,0.1,0.1,0.1)")
    svc = MusicDiscoveryService(cx, min_confidence=0.95)
    out = svc.discover('fiesta', limit=5)
    # With very low features and very high threshold, should get no results
    assert len(out['results']) == 0


def test_discovery_deep_desactivado_solo_usa_basic():
    """With use_deep=False, origin should always be 'basic'."""
    cx = _db()
    cx.execute("INSERT INTO pistas VALUES(1,10,20,'A','X','ALB','/a','h','biblioteca',120,0)")
    cx.execute("INSERT INTO track_audio_features VALUES('1','ready',0.8,0.1,0.8,0.8,0.8,0.8,0.8,140,0.2,0.2,0.1,0.2,0.8)")
    cx.execute("INSERT INTO track_deep_audio_features VALUES('1','ready',0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,'{}')")
    svc = MusicDiscoveryService(cx, use_deep=False, min_confidence=0.0)
    out = svc.discover('fiesta', limit=5)
    assert out['results'][0]['origin'] == 'basic'


def test_discovery_funciona_sin_tabla_deep():
    cx = _db()
    cx.execute("DROP TABLE track_deep_audio_features")
    cx.execute("INSERT INTO pistas VALUES(1,10,20,'A','X','ALB','/a','h','biblioteca',120,1)")
    cx.execute("INSERT INTO track_audio_features VALUES('1','ready',0.8,0.1,0.8,0.8,0.8,0.8,0.8,140,0.2,0.2,0.1,0.2,0.8)")
    svc = MusicDiscoveryService(cx, use_deep=True, min_confidence=0.0)

    out = svc.discover('fiesta', limit=5)

    assert out['results'][0]['origin'] == 'basic'
    assert out['results'][0]['favorita'] == 1


def test_discovery_analysis_state():
    """analysis_state() returns coherent data."""
    cx = _db()
    cx.execute("INSERT INTO pistas VALUES(1,10,20,'A','X','ALB','/a','h','biblioteca',120,0)")
    cx.execute("INSERT INTO pistas VALUES(2,11,21,'B','Y','ALB','/b','h2','biblioteca',120,0)")
    cx.execute("INSERT INTO track_audio_features VALUES('1','ready',0.5,0.5,0.5,0.5,0.5,0.5,0.5,120,0.5,0.5,0.5,0.5,0.5)")
    svc = MusicDiscoveryService(cx, min_confidence=0.0)
    state = svc.analysis_state()
    assert state['total_tracks'] == 2
    assert state['ready_features'] == 1
    assert state['has_features'] is True
    assert 0.0 <= state['percentage'] <= 1.0


def test_discovery_todos_intents_producen_resultados():
    """Every known intent produces a valid response structure."""
    cx = _db()
    cx.execute("INSERT INTO pistas VALUES(1,10,20,'A','X','ALB','/a','h','biblioteca',120,0)")
    cx.execute("INSERT INTO track_audio_features VALUES('1','ready',0.5,0.5,0.5,0.5,0.5,0.5,0.5,120,0.5,0.5,0.5,0.5,0.5)")
    svc = MusicDiscoveryService(cx, min_confidence=0.0)
    for query in ('triste', 'feliz', 'fiesta', 'entrenamiento', 'concentracion',
                  'chill', 'oscura', 'intensa', 'suave', 'rapido', 'lento', 'xyz genérico'):
        out = svc.discover(query, limit=5)
        assert 'results' in out
        assert 'intent' in out
        assert 'warnings' in out
        assert 'sections' in out


def test_discovery_feature_summary_presente():
    """Each result includes a feature_summary dict."""
    cx = _db()
    cx.execute("INSERT INTO pistas VALUES(1,10,20,'A','X','ALB','/a','h','biblioteca',120,0)")
    cx.execute("INSERT INTO track_audio_features VALUES('1','ready',0.8,0.1,0.8,0.8,0.8,0.8,0.8,140,0.2,0.2,0.1,0.2,0.8)")
    svc = MusicDiscoveryService(cx, min_confidence=0.0)
    out = svc.discover('fiesta', limit=5)
    assert len(out['results']) > 0
    fs = out['results'][0]['feature_summary']
    assert 'bpm' in fs
    assert 'energy' in fs
    assert 'valence_proxy' in fs


def test_discovery_consulta_sin_intencion_no_devuelve_lista_arbitraria():
    cx = _db()
    cx.execute("INSERT INTO pistas VALUES(1,10,20,'Hello','Adele','25','/a','h','biblioteca',120,0)")
    cx.execute("INSERT INTO track_audio_features VALUES('1','ready',0.9,0.1,0.8,0.8,0.8,0.8,0.8,140,0.2,0.2,0.1,0.2,0.8)")
    svc = MusicDiscoveryService(cx, min_confidence=0.0)

    for query in ("Hello", "Adele", "Bad Bunny", "x", "track 1"):
        out = svc.discover(query, limit=25)
        assert out["understood"] is False
        assert out["results"] == []
        assert out["sections"] == []
        assert "No entendí una intención musical" in out["user_message"]


def test_discovery_fiesta_devuelve_secciones_humanas():
    cx = _db()
    for idx in range(1, 5):
        cx.execute(
            "INSERT INTO pistas VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (idx, 10, 20, f"Party {idx}", "DJ", "Club", f"/p{idx}", f"h{idx}", "biblioteca", 120, 0),
        )
        cx.execute(
            "INSERT INTO track_audio_features VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(idx), "ready", 0.7 + idx * 0.04, 0.1, 0.7, 0.7,
                0.75 + idx * 0.04, 0.7 + idx * 0.03, 0.7, 120 + idx * 10,
                0.2, 0.2, 0.1, 0.2, 0.4,
            ),
        )
    svc = MusicDiscoveryService(cx, min_confidence=0.0)

    out = svc.discover("Para fiesta", limit=10)

    assert out["understood"] is True
    assert out["sections"]
    assert out["sections"][0]["title"] in {"Más fiesteras", "Más bailables", "Más rápidas", "Energía alta"}
    assert out["sections"][0]["results"][0]["titulo"].startswith("Party")
