from pathlib import Path
from unittest.mock import patch

from core.writer import _escribir_tags
from domain.models import (
    ArchivoAudio,
    CandidatoMB,
    DecisionArchivo,
    DecisionTipo,
    FuenteIdentificacion,
)


class FakeTags:
    def __init__(self):
        self.deleted = []
        self.added = []
        self.saved = False

    def delall(self, frame):
        self.deleted.append(frame)

    def add(self, frame):
        self.added.append(frame)

    def save(self, *_args, **_kwargs):
        self.saved = True


def _fake_frame(*_args, **kwargs):
    return kwargs


def test_writer_preserva_frames_no_gestionados_y_reescribe_claves_canonicas():
    decision = DecisionArchivo(
        tipo=DecisionTipo.ACEPTADO,
        archivo=ArchivoAudio(ruta_original=Path("/tmp/a.mp3")),
        candidato_elegido=CandidatoMB(
            titulo_oficial="Song",
            artista_principal="Artist",
            album_oficial="Album",
            track_number=1,
            track_total=10,
            anio_release=2001,
            recording_id="rid",
            release_id="rel",
            release_group_id="rg",
            tipo_release="Album",
            isrc="USAAA0000001",
        ),
        fuentes_usadas=[FuenteIdentificacion.MUSICBRAINZ],
    )

    fake_tags = FakeTags()
    with patch("core.writer.ID3", return_value=fake_tags), \
         patch("core.writer.TIT2", side_effect=_fake_frame), \
         patch("core.writer.TPE1", side_effect=_fake_frame), \
         patch("core.writer.TPE2", side_effect=_fake_frame), \
         patch("core.writer.TALB", side_effect=_fake_frame), \
         patch("core.writer.TRCK", side_effect=_fake_frame), \
         patch("core.writer.TDRC", side_effect=_fake_frame), \
         patch("core.writer.TSRC", side_effect=_fake_frame), \
         patch("core.writer.TXXX", side_effect=_fake_frame):
        ok, _ = _escribir_tags(Path("/tmp/fake.mp3"), decision)

    assert ok is True
    assert "TIT2" in fake_tags.deleted
    assert "TXXX:mb_release_group_id" in fake_tags.deleted
    assert fake_tags.saved is True
    assert any(frame.get("desc") == "mb_release_group_id" for frame in fake_tags.added)
