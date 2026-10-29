from pathlib import Path

from core.validator import _extraer_metadata_cruda


class FakeFrame:
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value


class FakeTXXX:
    def __init__(self, desc, value):
        self.desc = desc
        self.text = [value]

    def __str__(self):
        return self.text[0]


class FakeTags:
    def __init__(self):
        self._map = {
            "TIT2": FakeFrame("Song"),
            "TPE1": FakeFrame("Artist"),
            "TCOM": FakeFrame("Composer X"),
            "USLT": FakeFrame("embedded lyric"),
            "SYLT": FakeFrame("[00:01]embedded lyric"),
            "TLAN": FakeFrame("eng"),
            "TPOS": FakeFrame("2/4"),
        }
        self._txxx = [
            FakeTXXX("musicbrainz_recordingid", "rid"),
            FakeTXXX("musicbrainz_workid", "wid"),
            FakeTXXX("iswc", "T-123.456.789-Z"),
            FakeTXXX("arranger", "Arranger Y"),
            FakeTXXX("performer:guitar", "Player Z"),
            FakeTXXX("acoustid_id", "aid"),
            FakeTXXX("acoustid_fingerprint", "fp"),
        ]

    def get(self, frame_id):
        return self._map.get(frame_id)

    def getall(self, frame_id):
        if frame_id == "TXXX":
            return self._txxx
        return []


class FakeInfo:
    length = 123.4
    bitrate = 192000
    sample_rate = 44100
    mode = 0


class FakeMp3:
    info = FakeInfo()
    tags = FakeTags()


def test_extraer_metadata_cruda_extendida():
    meta = _extraer_metadata_cruda(Path("demo.mp3"), FakeMp3())
    assert meta.titulo == "Song"
    assert meta.composer == "Composer X"
    assert meta.lyrics_plain == "embedded lyric"
    assert meta.lyrics_synced == "[00:01]embedded lyric"
    assert meta.language == "eng"
    assert meta.disc_number == "2"
    assert meta.total_discs == "4"
    assert meta.musicbrainz_ids["musicbrainz_recordingid"] == "rid"
    assert meta.musicbrainz_ids["musicbrainz_workid"] == "wid"
    assert meta.musicbrainz_ids["iswc"] == "T-123.456.789-Z"
    assert meta.arranger == "Arranger Y"
    assert meta.performer_roles["performer:guitar"] == "Player Z"
    assert meta.acoustid_id == "aid"
    assert meta.acoustid_fingerprint == "fp"
