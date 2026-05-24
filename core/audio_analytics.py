from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from mutagen.mp3 import MP3

from infra.logger import obtener_logger

_log = obtener_logger("audio_analytics")


@dataclass
class AudioAnalytics:
    status: str = "not_computed"
    duration_sec: Optional[float] = None
    bitrate_kbps: Optional[int] = None
    sample_rate_hz: Optional[int] = None
    channels: Optional[int] = None
    bits_per_sample: Optional[int] = None
    format_detected: str = "mp3"
    peak: Optional[float] = None
    loudness_lufs: Optional[float] = None
    dynamic_range: Optional[float] = None
    silence_start_sec: Optional[float] = None
    silence_end_sec: Optional[float] = None
    bpm: Optional[float] = None
    musical_key: Optional[str] = None
    mode: Optional[str] = None
    instrumental_probability: Optional[float] = None
    extractor: str = "mutagen_headers"

    def to_dict(self) -> dict:
        return asdict(self)


class AudioAnalyticsExtractor:
    def extract(self, ruta_mp3: Path) -> AudioAnalytics:
        try:
            audio = MP3(str(ruta_mp3))
            info = audio.info
            duration = float(info.length) if getattr(info, "length", None) else None
            bitrate = int(info.bitrate / 1000) if getattr(info, "bitrate", None) else None
            sample_rate = int(getattr(info, "sample_rate", 0) or 0) or None
            channels = int(getattr(info, "channels", 0) or 0) or None

            analytics = AudioAnalytics(
                status="computed",
                duration_sec=duration,
                bitrate_kbps=bitrate,
                sample_rate_hz=sample_rate,
                channels=channels,
                bits_per_sample=None,
                peak=None,
                loudness_lufs=None,
                dynamic_range=None,
                silence_start_sec=None,
                silence_end_sec=None,
            )
            return analytics
        except Exception as e:
            _log.debug(f"No se pudo extraer analítica de {ruta_mp3}: {e}")
            return AudioAnalytics(status="error", extractor="mutagen_headers")
