from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from infra.binarios import resolver_bin
from infra.logger import obtener_logger


def _flags_subprocess_silencioso() -> dict:
    """Args extra para que ``subprocess`` no muestre consola en Windows GUI.

    En builds congeladas con console=False, sys.stdin/stdout/stderr son None
    y la creación de un hijo con consola heredada provoca un parpadeo de
    ventana negra. ``CREATE_NO_WINDOW`` evita ese flash.
    En POSIX el dict queda vacío y subprocess.run lo ignora.
    """
    if sys.platform.startswith("win"):
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}

_log = obtener_logger("transcoder")


@dataclass
class ResultadoTranscodificacion:
    exito: bool
    ruta_salida: Optional[Path] = None
    formato_entrada: str = ""
    error: Optional[str] = None


class TranscodificadorAudio:
    """Convierte formatos de audio soportados a MP3 usando ffmpeg."""

    def __init__(self, directorio_temp: Path, timeout_seg: int = 120) -> None:
        self._base_temp = directorio_temp / "transcoded"
        self._timeout = timeout_seg

    def convertir_a_mp3(self, ruta_entrada: Path) -> ResultadoTranscodificacion:
        formato = ruta_entrada.suffix.lower().lstrip(".")
        if ruta_entrada.suffix.lower() == ".mp3":
            return ResultadoTranscodificacion(
                exito=True,
                ruta_salida=ruta_entrada,
                formato_entrada=formato,
            )

        ffmpeg_bin = resolver_bin("ffmpeg")
        if not ffmpeg_bin:
            return ResultadoTranscodificacion(
                exito=False,
                formato_entrada=formato,
                error="ffmpeg no está disponible (ni embebido ni en PATH)",
            )

        self._base_temp.mkdir(parents=True, exist_ok=True)
        output_name = f"{ruta_entrada.stem}.mp3"
        ruta_salida = self._resolver_conflicto(self._base_temp / output_name)

        cmd = [
            ffmpeg_bin,
            "-y",
            "-i",
            str(ruta_entrada),
            "-vn",
            "-codec:a",
            "libmp3lame",
            "-q:a",
            "2",
            "-map_metadata",
            "0",
            str(ruta_salida),
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
                **_flags_subprocess_silencioso(),
            )
        except subprocess.TimeoutExpired:
            return ResultadoTranscodificacion(
                exito=False,
                formato_entrada=formato,
                error=f"timeout de transcodificación ({self._timeout}s)",
            )
        except OSError as e:
            return ResultadoTranscodificacion(
                exito=False,
                formato_entrada=formato,
                error=f"error ejecutando ffmpeg: {e}",
            )

        if proc.returncode != 0 or not ruta_salida.exists() or ruta_salida.stat().st_size == 0:
            stderr = (proc.stderr or "").strip()
            return ResultadoTranscodificacion(
                exito=False,
                formato_entrada=formato,
                error=f"ffmpeg falló: {stderr[:300]}",
            )

        self._escribir_manifest_conversion(ruta_entrada, ruta_salida, formato)
        _log.info(f"Transcodificado a MP3: {ruta_entrada.name} -> {ruta_salida.name}")
        return ResultadoTranscodificacion(
            exito=True,
            ruta_salida=ruta_salida,
            formato_entrada=formato,
        )

    @staticmethod
    def _resolver_conflicto(base: Path) -> Path:
        if not base.exists():
            return base
        n = 2
        candidate = base.parent / f"{base.stem}_{n}{base.suffix}"
        while candidate.exists() and n < 10_000:
            n += 1
            candidate = base.parent / f"{base.stem}_{n}{base.suffix}"
        return candidate

    def _escribir_manifest_conversion(self, entrada: Path, salida: Path, formato: str) -> None:
        manifest = self._base_temp / "conversions.jsonl"
        payload = {
            "input": str(entrada),
            "output": str(salida),
            "input_format": formato,
            "output_format": "mp3",
        }
        try:
            with open(manifest, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except OSError:
            _log.debug("No se pudo escribir conversions.jsonl", exc_info=True)
