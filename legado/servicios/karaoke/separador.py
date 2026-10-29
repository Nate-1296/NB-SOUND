# =============================================================================
# servicios/karaoke/separador.py
#
# Separacion voz/instrumental usando Demucs.
#
# Diferencias importantes vs. la implementacion previa:
#   - NO usa `subprocess` — usa la API Python (`demucs.pretrained` +
#     `demucs.apply.apply_model`). Mas rapido, sin overhead de proceso,
#     y con cancelacion cooperativa real.
#   - Iteracion manual por segmentos: replicamos lo que hace `apply_model`
#     con `split=True`, pero con check de `stop_event` entre segmentos
#     y callback de progreso por chunk procesado.
#   - Conversion a MP3 320 kbps via ffmpeg (lossless intermedio en WAV).
#
# El instrumental se computa como (mezcla - voces) en el dominio temporal.
# Para htdemucs (4-stems) eso preserva drums+bass+other intactos.
# =============================================================================

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

import threading as _threading

from infra.binarios import resolver_bin
from infra.logger import obtener_logger


def _flags_subprocess_silencioso() -> dict:
    """``CREATE_NO_WINDOW`` en Windows GUI; vacio en POSIX."""
    if sys.platform.startswith("win"):
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}

from .errores import (
    ArchivoNoExisteError,
    AudioCorruptoError,
    FfmpegFaltanteError,
    KaraokeCanceladoError,
    MemoriaInsuficienteError,
    ModeloFaltanteError,
)
from .modelo import cargar_modelo

_log = obtener_logger("servicios.karaoke.separador")

ProgressCb = Callable[[float], None]
StopEvent = _threading.Event

# Bitrate del MP3 final. 320 kbps es el limite practico de calidad audible.
MP3_BITRATE = "320k"

# Tamano del bloque que pasamos a apply_model. Demucs/htdemucs define un
# `segment` (~7-8s); usamos el valor del propio modelo para no tener que
# ajustar nada. La iteracion por chunks es nuestra y permite cancelacion.


def _comprobar_ffmpeg() -> str:
    binario = resolver_bin("ffmpeg")
    if not binario:
        raise FfmpegFaltanteError(
            "ffmpeg no esta disponible (ni embebido ni en PATH).",
            detalle=(
                "Las builds oficiales de NB Sound traen ffmpeg embebido. "
                "Si estas ejecutando desde codigo fuente, instalalo desde "
                "el gestor de paquetes del sistema."
            ),
        )
    return binario


def _cargar_audio(ruta: Path):
    """Carga el audio como tensor (canales, muestras). Resamplea si hace falta."""
    try:
        from demucs.audio import AudioFile  # type: ignore
        from demucs.apply import apply_model  # noqa: F401  asegura import valido
        import torch  # type: ignore
    except Exception as exc:
        raise ModeloFaltanteError(
            "No se pudo importar demucs.audio.",
            detalle=str(exc),
        ) from exc

    if not ruta.exists():
        raise ArchivoNoExisteError(f"No existe: {ruta}")

    try:
        # AudioFile decodifica via ffmpeg internamente.
        wav = AudioFile(str(ruta)).read(streams=0, samplerate=44100, channels=2)
    except Exception as exc:
        raise AudioCorruptoError(
            f"No se pudo decodificar {ruta.name}",
            detalle=str(exc),
        ) from exc

    # Algunos archivos llegan como (channels, samples) o (samples, channels).
    # AudioFile devuelve (channels, samples).
    if wav.ndim != 2:
        raise AudioCorruptoError("El audio decodificado no es 2D")
    # Normalizar tensor a float32 si no lo es.
    if wav.dtype != torch.float32:
        wav = wav.to(torch.float32)
    return wav


def _separar_por_segmentos(
    modelo,
    mezcla,                       # torch.Tensor (channels, samples) en CPU
    device: str,
    *,
    stop_event: Optional[StopEvent],
    progress_cb: Optional[ProgressCb],
):
    """Aplica el modelo por segmentos con cancelacion cooperativa.

    Replica el camino `apply_model(split=True, shifts=0)` pero iteramos los
    offsets nosotros para chequear `stop_event` entre chunks. La salida tiene
    forma (n_stems, channels, samples).
    """
    import torch  # type: ignore
    from demucs.apply import apply_model  # type: ignore

    # Forma esperada por apply_model: (batch, channels, length)
    ref = mezcla.mean(0)
    mezcla = (mezcla - ref.mean()) / (ref.std() + 1e-8)
    mix_batch = mezcla.unsqueeze(0)

    samplerate = modelo.samplerate
    segment = float(getattr(modelo, "segment", 7.8))
    overlap = 0.25
    segment_length = int(samplerate * segment)
    stride = max(1, int((1 - overlap) * segment_length))

    _, channels, length = mix_batch.shape
    n_stems = len(modelo.sources)

    # Acumuladores en CPU para evitar duplicar VRAM/RAM con tensores intermedios.
    salida = torch.zeros(n_stems, channels, length, dtype=torch.float32)
    peso_total = torch.zeros(length, dtype=torch.float32)

    # Triangular window igual que demucs.
    half = segment_length // 2
    peso = torch.cat([
        torch.arange(1, half + 1, dtype=torch.float32),
        torch.arange(segment_length - half, 0, -1, dtype=torch.float32),
    ])
    peso = peso / peso.max()

    offsets = list(range(0, length, stride))
    total_chunks = max(1, len(offsets))

    for i, offset in enumerate(offsets):
        if stop_event is not None and stop_event.is_set():
            raise KaraokeCanceladoError("Cancelado por el usuario")

        chunk_len = min(segment_length, length - offset)
        if chunk_len <= 0:
            break
        chunk = mix_batch[..., offset:offset + chunk_len]

        # Pad para que el modelo siempre vea segment_length completo.
        if chunk_len < segment_length:
            pad = torch.zeros(1, channels, segment_length - chunk_len, dtype=chunk.dtype)
            chunk_padded = torch.cat([chunk, pad], dim=-1)
        else:
            chunk_padded = chunk

        try:
            with torch.no_grad():
                # split=False: el chunk ya tiene tamano segment.
                out = apply_model(
                    modelo, chunk_padded.to(device),
                    shifts=0, split=False, overlap=0.0,
                    progress=False, device=device, num_workers=0,
                    segment=segment,
                ).cpu()
        except RuntimeError as exc:
            mensaje = str(exc).lower()
            if "out of memory" in mensaje or "cuda" in mensaje and "memory" in mensaje:
                raise MemoriaInsuficienteError(
                    "Memoria insuficiente para procesar la pista.",
                    detalle=str(exc),
                ) from exc
            raise AudioCorruptoError(
                f"Error de procesamiento: {exc}",
                detalle=str(exc),
            ) from exc

        # out shape: (1, n_stems, channels, segment_length)
        out = out[0]
        peso_chunk = peso[:chunk_len]
        salida[..., offset:offset + chunk_len] += out[..., :chunk_len] * peso_chunk
        peso_total[offset:offset + chunk_len] += peso_chunk

        if progress_cb is not None:
            try:
                progress_cb(min(1.0, (i + 1) / total_chunks))
            except Exception as _exc:
                _log.debug("Excepcion ignorada en %s: %s", "separador.py", _exc)

    if peso_total.min() <= 0:
        # Hay zona sin cobertura; usar peso 1 para no dividir entre cero.
        peso_total = peso_total.clamp(min=1e-8)

    salida = salida / peso_total
    # Renormalizar: deshacemos la normalizacion que aplicamos al inicio.
    # demucs internamente usa la media/std del mix; el resultado mantiene
    # las amplitudes relativas correctas. Multiplicamos por std del mix original.
    salida = salida * (ref.std() + 1e-8) + ref.mean()
    return salida


def _guardar_wav_temp(tensor, samplerate: int, destino: Path) -> None:
    """Escribe un WAV float32 usando soundfile (estable, sin TorchCodec)."""
    try:
        import soundfile as sf  # type: ignore
        import numpy as np  # type: ignore
    except Exception as exc:
        raise FfmpegFaltanteError(
            "soundfile/numpy no estan disponibles.",
            detalle=str(exc),
        ) from exc
    destino.parent.mkdir(parents=True, exist_ok=True)
    # tensor shape: (channels, samples). soundfile espera (samples, channels).
    arr = tensor.clamp(-1.0, 1.0).cpu().numpy()
    if arr.ndim == 2:
        arr = arr.T  # (samples, channels)
    sf.write(str(destino), arr.astype(np.float32, copy=False), int(samplerate))


def _convertir_a_mp3(origen_wav: Path, destino_mp3: Path) -> None:
    """Convierte WAV a MP3 320 kbps via ffmpeg. Sobrescribe si existe."""
    binario = _comprobar_ffmpeg()
    destino_mp3.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        binario, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(origen_wav),
        "-codec:a", "libmp3lame", "-b:a", MP3_BITRATE,
        str(destino_mp3),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120,
        **_flags_subprocess_silencioso(),
    )
    if proc.returncode != 0 or not destino_mp3.exists():
        raise FfmpegFaltanteError(
            "ffmpeg fallo al codificar a MP3.",
            detalle=proc.stderr[:500],
        )


def separar_pista_instrumental(
    ruta_audio: Path,
    ruta_salida_mp3: Path,
    directorio_modelos: Path,
    directorio_temporal: Path,
    *,
    nombre_modelo: str = "htdemucs",
    device: str = "cpu",
    stop_event: Optional[StopEvent] = None,
    progress_cb: Optional[ProgressCb] = None,
) -> dict:
    """Genera el instrumental (mezcla - voces) de una pista.

    El callback `progress_cb(p)` recibe valores en [0, 1] segun avanza el
    procesamiento. `stop_event` permite cancelacion cooperativa entre
    segmentos del modelo.

    Devuelve un dict con metricas: `bytes`, `duracion_proc_ms`, `samplerate`.

    Raises:
        ArchivoNoExisteError, AudioCorruptoError, FfmpegFaltanteError,
        ModeloFaltanteError, MemoriaInsuficienteError, KaraokeCanceladoError.
    """
    inicio = time.monotonic()
    ruta_audio = Path(ruta_audio)
    ruta_salida_mp3 = Path(ruta_salida_mp3)
    directorio_temporal = Path(directorio_temporal)

    if not ruta_audio.exists():
        raise ArchivoNoExisteError(f"No existe: {ruta_audio}")

    _comprobar_ffmpeg()  # falla rapido si no esta

    import torch  # type: ignore

    modelo = cargar_modelo(directorio_modelos, nombre_modelo)
    fuentes: list[str] = list(getattr(modelo, "sources", []))
    if "vocals" not in fuentes:
        raise ModeloFaltanteError(
            f"El modelo '{nombre_modelo}' no produce el stem 'vocals'."
        )

    # 1) Carga
    if progress_cb:
        try:
            progress_cb(0.02)
        except Exception as _exc:
            _log.debug("Excepcion ignorada en %s: %s", "separador.py", _exc)
    if stop_event is not None and stop_event.is_set():
        raise KaraokeCanceladoError("Cancelado por el usuario")

    mezcla = _cargar_audio(ruta_audio)

    # 2) Separacion (lo costoso: ~70% del tiempo total)
    # Reservamos el rango 0.05..0.92 para el progreso de separacion.
    def _scaled(p: float) -> None:
        if progress_cb:
            progress_cb(0.05 + p * 0.87)

    with torch.no_grad():
        stems = _separar_por_segmentos(
            modelo, mezcla, device,
            stop_event=stop_event, progress_cb=_scaled,
        )

    # stems shape: (n_stems, channels, samples). Indice de vocals:
    idx_vocals = fuentes.index("vocals")
    instrumental = mezcla - stems[idx_vocals]

    # 3) Guardado intermedio en WAV
    if stop_event is not None and stop_event.is_set():
        raise KaraokeCanceladoError("Cancelado por el usuario")
    if progress_cb:
        try:
            progress_cb(0.94)
        except Exception as _exc:
            _log.debug("Excepcion ignorada en %s: %s", "separador.py", _exc)
    directorio_temporal.mkdir(parents=True, exist_ok=True)
    wav_tmp = directorio_temporal / f"{ruta_audio.stem}_instrumental.wav"
    _guardar_wav_temp(instrumental, modelo.samplerate, wav_tmp)

    # 4) Conversion a MP3 320
    if stop_event is not None and stop_event.is_set():
        wav_tmp.unlink(missing_ok=True)
        raise KaraokeCanceladoError("Cancelado por el usuario")
    if progress_cb:
        try:
            progress_cb(0.97)
        except Exception as _exc:
            _log.debug("Excepcion ignorada en %s: %s", "separador.py", _exc)
    try:
        _convertir_a_mp3(wav_tmp, ruta_salida_mp3)
    finally:
        wav_tmp.unlink(missing_ok=True)

    if progress_cb:
        try:
            progress_cb(1.0)
        except Exception as _exc:
            _log.debug("Excepcion ignorada en %s: %s", "separador.py", _exc)

    transcurrido_ms = int((time.monotonic() - inicio) * 1000)
    return {
        "bytes": ruta_salida_mp3.stat().st_size if ruta_salida_mp3.exists() else 0,
        "duracion_proc_ms": transcurrido_ms,
        "samplerate": int(modelo.samplerate),
    }
