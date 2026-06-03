from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from core.audio_analytics import AudioAnalytics
from core.enrichment_pipeline import EnrichmentPipeline
from domain.models import ArchivoAudio, CandidatoMB, DecisionArchivo, DecisionTipo, MetadataCruda
from external.lyrics_client import LyricsClient


def test_lyrics_prefiere_lrclib_sobre_lyrics_ovh():
    client = LyricsClient()
    with patch("external.lyrics_client.ENABLE_LYRICS_ENRICHMENT", True), \
         patch("external.lyrics_client.ENABLE_LRCLIB", True), \
         patch("external.lyrics_client.ENABLE_LYRICS_OVH", True), \
         patch("external.lyrics_client._fetch_json", side_effect=[
             {"plainLyrics": "hello", "syncedLyrics": "[00:01]hello", "language": "en"},
         ]):
        result = client.fetch("Artist", "Song", 123)

    assert result.status == "found"
    assert result.provider == "lrclib"
    assert result.plain_lyrics == "hello"


def test_lyrics_fallback_a_lyrics_ovh_si_lrclib_no_encuentra():
    client = LyricsClient()
    with patch("external.lyrics_client.ENABLE_LYRICS_ENRICHMENT", True), \
         patch("external.lyrics_client.ENABLE_LRCLIB", True), \
         patch("external.lyrics_client.ENABLE_LYRICS_OVH", True), \
         patch("external.lyrics_client._fetch_json", side_effect=[None, [], {"lyrics": "fallback"}]):
        result = client.fetch("Artist", "Song", 123)

    assert result.status == "partial"
    assert result.provider == "lyrics_ovh"
    assert "fallback" in result.plain_lyrics


def test_enrichment_manifest_persistido():
    with TemporaryDirectory() as td:
        pipeline = EnrichmentPipeline(Path(td))
        decision = DecisionArchivo(
            tipo=DecisionTipo.ACEPTADO,
            archivo=ArchivoAudio(ruta_original=Path("/tmp/a.mp3"), metadata_cruda=MetadataCruda(lyrics_plain="embedded", composer="Mozart", arranger="Arr", work="Work X", musicbrainz_ids={"musicbrainz_workid": "wid", "iswc": "T-123"}, acoustid_id="aid", acoustid_fingerprint="afp", disc_number="2", total_discs="4")),
            candidato_elegido=CandidatoMB(
                recording_id="rid",
                release_id="rel",
                release_group_id="rg",
                artista_principal="Artist",
                titulo_oficial="Song",
            ),
        )
        decision.ruta_destino = Path(td) / "song.mp3"
        decision.ruta_destino.write_bytes(b"x")

        with patch.object(pipeline._lyrics, "fetch") as mock_fetch, \
             patch.object(pipeline._analytics, "extract") as mock_extract:
            mock_fetch.return_value.status = "found"
            mock_fetch.return_value.provider = "lrclib"
            mock_fetch.return_value.plain_lyrics = "lyrics"
            mock_fetch.return_value.synced_lyrics = ""
            mock_fetch.return_value.language = "en"
            mock_fetch.return_value.instrumental = False
            mock_fetch.return_value.is_translation = False
            mock_fetch.return_value.confidence = 0.9
            mock_fetch.return_value.match_method = "m"
            mock_fetch.return_value.fetched_at = "2026-01-01T00:00:00Z"
            mock_extract.return_value = AudioAnalytics(status="computed", duration_sec=3.2)
            pipeline.procesar(decision)

        manifest = (Path(td) / "enrichment" / "enrichment_manifest.jsonl").read_text(encoding="utf-8")
        assert '"recording_id": "rid"' in manifest
        assert '"provider": "lrclib"' in manifest
        assert '"status": "computed"' in manifest
        assert '"embedded"' in manifest
        assert 'embedded' in manifest
        assert 'Mozart' in manifest
        assert 'Work X' in manifest
        assert 'wid' in manifest
        assert 'T-123' in manifest
        assert 'aid' in manifest
        assert 'afp' in manifest
        assert 'total_discs' in manifest
        assert '"acoustid"' in manifest


def test_enrichment_usa_letra_embebida_si_externos_no_encuentran():
    with TemporaryDirectory() as td:
        pipeline = EnrichmentPipeline(Path(td))
        decision = DecisionArchivo(
            tipo=DecisionTipo.ACEPTADO,
            archivo=ArchivoAudio(
                ruta_original=Path("/tmp/a.mp3"),
                metadata_cruda=MetadataCruda(lyrics_plain="embedded fallback"),
            ),
            candidato_elegido=CandidatoMB(
                recording_id="rid",
                release_id="rel",
                artista_principal="Artist",
                titulo_oficial="Song",
            ),
        )
        decision.ruta_destino = Path(td) / "song.mp3"
        decision.ruta_destino.write_bytes(b"x")

        with patch.object(pipeline._lyrics, "fetch") as mock_fetch, \
             patch.object(pipeline._analytics, "extract") as mock_extract:
            mock_fetch.return_value.status = "not_found"
            mock_fetch.return_value.provider = "lrclib"
            mock_fetch.return_value.plain_lyrics = ""
            mock_fetch.return_value.synced_lyrics = ""
            mock_extract.return_value = AudioAnalytics(status="computed")
            pipeline.procesar(decision)

        manifest = (Path(td) / "enrichment" / "enrichment_manifest.jsonl").read_text(encoding="utf-8")
        assert '"provider": "embedded_tags"' in manifest
        assert "embedded fallback" in manifest


def test_lyrics_lrclib_search_fallback_por_score():
    client = LyricsClient()
    with patch("external.lyrics_client.ENABLE_LYRICS_ENRICHMENT", True), \
         patch("external.lyrics_client.ENABLE_LRCLIB", True), \
         patch("external.lyrics_client.ENABLE_LYRICS_OVH", False), \
         patch("external.lyrics_client._fetch_json", side_effect=[
             None,
             [{
                 "trackName": "Song",
                 "artistName": "Artist",
                 "albumName": "Album",
                 "duration": 123,
                 "plainLyrics": "from search",
                 "syncedLyrics": "",
             }],
         ]):
        result = client.fetch("Artist", "Song", 123, album="Album")

    assert result.status == "found"
    assert result.provider == "lrclib"
    assert result.match_method == "lrclib_search"
    assert result.plain_lyrics == "from search"


def test_lyrics_lrclib_rate_limit_continua_a_lyrics_ovh():
    client = LyricsClient()
    with patch("external.lyrics_client.ENABLE_LYRICS_ENRICHMENT", True), \
         patch("external.lyrics_client.ENABLE_LRCLIB", True), \
         patch("external.lyrics_client.ENABLE_LYRICS_OVH", True), \
         patch("external.lyrics_client._fetch_json", side_effect=[
             {"__blocked__": True},
             {"lyrics": "ovh fallback"},
         ]):
        result = client.fetch("Artist", "Song", 123)

    assert result.status == "partial"
    assert result.provider == "lyrics_ovh"
    assert result.plain_lyrics == "ovh fallback"


def test_lyrics_ovh_suggest_prueba_candidatos_canonicos():
    client = LyricsClient()
    with patch("external.lyrics_client.ENABLE_LYRICS_ENRICHMENT", True), \
         patch("external.lyrics_client.ENABLE_LRCLIB", False), \
         patch("external.lyrics_client.ENABLE_LYRICS_OVH", True), \
         patch("external.lyrics_client._fetch_json", side_effect=[
             None,
             {"data": [{"title_short": "Song", "artist": {"name": "Artist"}}]},
             {"lyrics": "suggested"},
         ]):
        result = client.fetch("Artist", "Song", 123)

    assert result.status == "partial"
    assert result.match_method == "lyrics_ovh_suggest"
    assert result.plain_lyrics == "suggested"


def test_lyrics_status_blocked_por_rate_limit():
    client = LyricsClient()
    with patch("external.lyrics_client.ENABLE_LYRICS_ENRICHMENT", True),          patch("external.lyrics_client.ENABLE_LRCLIB", True),          patch("external.lyrics_client.ENABLE_LYRICS_OVH", False),          patch("external.lyrics_client._fetch_json", return_value={"__blocked__": True}):
        result = client.fetch("Artist", "Song", 123)
    assert result.status == "blocked"
    assert result.provider == "lrclib"


def test_lyrics_unsupported_cuando_feature_flag_desactivado():
    client = LyricsClient()
    with patch("external.lyrics_client.ENABLE_LYRICS_ENRICHMENT", False):
        # active property se fija al crear instancia, por eso creamos otra
        client2 = LyricsClient()
        result = client2.fetch("Artist", "Song", 100)
    assert result.status == "unsupported"
