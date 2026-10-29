"""Tests del separador Demucs.

Tests rapidos: mockean el modelo. Tests lentos (`@pytest.mark.slow`):
descargan htdemucs y separan un sample sintetico real.

Para correr solo rapidos:   pytest tests/test_karaoke_separador.py -m "not slow"
Para correr todos:          pytest tests/test_karaoke_separador.py
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from servicios.karaoke import errores
from servicios.karaoke.separador import separar_pista_instrumental


# ─── Tests rapidos (no descargan modelo) ─────────────────────────────────────

def test_separar_pista_archivo_inexistente_lanza(tmp_path):
    with pytest.raises(errores.ArchivoNoExisteError):
        separar_pista_instrumental(
            ruta_audio=tmp_path / "no_existe.mp3",
            ruta_salida_mp3=tmp_path / "salida.mp3",
            directorio_modelos=tmp_path / "models",
            directorio_temporal=tmp_path / "tmp",
        )


def test_separar_pista_audio_corrupto_lanza(tmp_path):
    fake = tmp_path / "corrupto.mp3"
    fake.write_bytes(b"not really an audio file")
    with pytest.raises((errores.AudioCorruptoError, errores.ModeloFaltanteError)):
        separar_pista_instrumental(
            ruta_audio=fake,
            ruta_salida_mp3=tmp_path / "salida.mp3",
            directorio_modelos=tmp_path / "models",
            directorio_temporal=tmp_path / "tmp",
        )


def test_separar_pista_cancelacion_temprana_lanza(tmp_path, monkeypatch):
    """Si stop_event esta set antes de empezar, se aborta inmediatamente."""
    # Creamos un WAV minusculo valido (1s de silencio) para que pase la carga.
    try:
        import numpy as np
        import soundfile as sf
    except ImportError:
        pytest.skip("soundfile no disponible")
    silencio = np.zeros((44100, 2), dtype="float32")
    ruta = tmp_path / "silencio.wav"
    sf.write(str(ruta), silencio, 44100)

    stop = threading.Event(); stop.set()
    with pytest.raises(errores.KaraokeCanceladoError):
        separar_pista_instrumental(
            ruta_audio=ruta,
            ruta_salida_mp3=tmp_path / "salida.mp3",
            directorio_modelos=tmp_path / "models",
            directorio_temporal=tmp_path / "tmp",
            stop_event=stop,
        )


# ─── Test lento (integration con modelo real) ────────────────────────────────

@pytest.mark.slow
def test_separar_pista_genera_mp3_real(tmp_path):
    """Descarga htdemucs y separa un audio sintetico (~2s).

    Solo corre si NB_SOUND_RUN_SLOW_TESTS=1 esta presente, para no convertir
    toda la suite en un test de 5 minutos.
    """
    import os
    if not os.environ.get("NB_SOUND_RUN_SLOW_TESTS"):
        pytest.skip("Set NB_SOUND_RUN_SLOW_TESTS=1 to run slow integration tests")

    import numpy as np
    import soundfile as sf

    # Generar 3s de senal con dos componentes simulados:
    # - "voz" en 800 Hz
    # - "instrumental" mezcla de 220+330 Hz
    sr = 44100
    t = np.linspace(0, 3, sr * 3, endpoint=False, dtype="float32")
    voz = 0.3 * np.sin(2 * np.pi * 800 * t)
    inst = 0.5 * (np.sin(2 * np.pi * 220 * t) + np.sin(2 * np.pi * 330 * t))
    mezcla = (voz + inst) * 0.7
    stereo = np.stack([mezcla, mezcla], axis=1)

    fuente = tmp_path / "sintetica.wav"
    sf.write(str(fuente), stereo, sr)

    destino = tmp_path / "instrumental.mp3"
    progresos = []
    metricas = separar_pista_instrumental(
        ruta_audio=fuente,
        ruta_salida_mp3=destino,
        directorio_modelos=tmp_path / "models",
        directorio_temporal=tmp_path / "tmp",
        nombre_modelo="htdemucs",
        device="cpu",
        progress_cb=progresos.append,
    )
    assert destino.exists()
    assert destino.stat().st_size > 1024
    assert metricas["bytes"] > 1024
    assert metricas["duracion_proc_ms"] > 0
    assert progresos[-1] == 1.0
