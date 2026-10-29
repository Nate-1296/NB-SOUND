from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from external.transcoder import TranscodificadorAudio


def test_transcoder_retorna_error_si_no_hay_ffmpeg():
    with TemporaryDirectory() as td:
        src = Path(td) / "a.flac"
        src.write_bytes(b"x")
        t = TranscodificadorAudio(Path(td))
        with patch("external.transcoder.resolver_bin", return_value=None):
            out = t.convertir_a_mp3(src)
        assert out.exito is False
        assert "ffmpeg" in (out.error or "")


def test_transcoder_retorna_misma_ruta_para_mp3():
    with TemporaryDirectory() as td:
        src = Path(td) / "a.mp3"
        src.write_bytes(b"x")
        t = TranscodificadorAudio(Path(td))
        out = t.convertir_a_mp3(src)
        assert out.exito is True
        assert out.ruta_salida == src
