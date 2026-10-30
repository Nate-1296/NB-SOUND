"""Prototipo F0.4.2: ¿htdemucs en ONNX separa igual que el PyTorch de la V1?

Herramienta de desarrollo, nunca viaja en el instalador (ver check-sin-python).
Se ejecuta con el entorno de la V1, desde `legado/`:

    cd legado && .venv/bin/python ../scripts/prototipos/karaoke/paridad.py torch <trabajo> <archivos>...
    cd legado && .venv/bin/python ../scripts/prototipos/karaoke/paridad.py onnx <trabajo> <modelo.onnx> <archivos>...

Para cada canción carga el audio exactamente como la V1 (`_cargar_audio`), separa
con el modelo de PyTorch y el algoritmo por segmentos de la V1
(`_separar_por_segmentos`), y repite el mismo algoritmo llamando a ONNX Runtime en
lugar de a PyTorch, con los pesos en fp32 y en fp16. Compara los instrumentales
(mezcla menos voces, como hace la V1) y mide el tiempo de cada uno.

Lee los archivos en solo lectura y no escribe nada.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch

sys.path.insert(0, str(Path.cwd()))
from servicios.karaoke import separador  # noqa: E402

SEGMENTO = 343_980  # 7,8 s a 44,1 kHz: la entrada fija del grafo exportado


def separar_onnx(sesion: ort.InferenceSession, mezcla: np.ndarray) -> np.ndarray:
    """El algoritmo de `_separar_por_segmentos` de la V1, con ONNX en vez de PyTorch."""
    ref = mezcla.mean(0)
    media, desv = float(ref.mean()), float(ref.std()) + 1e-8
    x = (mezcla - media) / desv
    canales, largo = x.shape
    paso = max(1, int(0.75 * SEGMENTO))
    mitad = SEGMENTO // 2
    peso = np.concatenate(
        [np.arange(1, mitad + 1), np.arange(SEGMENTO - mitad, 0, -1)]
    ).astype(np.float32)
    peso /= peso.max()
    salida = np.zeros((4, canales, largo), dtype=np.float32)
    total = np.zeros(largo, dtype=np.float32)
    for inicio in range(0, largo, paso):
        n = min(SEGMENTO, largo - inicio)
        if n <= 0:
            break
        trozo = np.zeros((1, canales, SEGMENTO), dtype=np.float32)
        trozo[0, :, :n] = x[:, inicio : inicio + n]
        (stems,) = sesion.run(None, {"mix": trozo})
        salida[..., inicio : inicio + n] += stems[0, ..., :n] * peso[:n]
        total[inicio : inicio + n] += peso[:n]
    salida /= np.maximum(total, 1e-8)
    return salida * desv + media


def sdr(referencia: np.ndarray, estimado: np.ndarray) -> float:
    ruido = np.sum((referencia - estimado) ** 2)
    return float(10 * np.log10(np.sum(referencia**2) / max(ruido, 1e-20)))


def main() -> None:
    """Por etapas, para no tener PyTorch y dos sesiones de ONNX en memoria a la vez
    (juntos pasan de 11 GB y la máquina de desarrollo tiene 19).

        paridad.py torch  <trabajo> <archivo>...   referencia de la V1 en <trabajo>/*.npy
        paridad.py onnx   <trabajo> <modelo.onnx> <archivo>...
    """
    etapa, trabajo = sys.argv[1], Path(sys.argv[2])
    trabajo.mkdir(parents=True, exist_ok=True)
    if etapa == "torch":
        torch.set_num_threads(8)
        modelo = separador.cargar_modelo(Path.home() / "Música/cache/karaoke/models", "htdemucs")
        idx_voz = list(modelo.sources).index("vocals")
        for archivo in map(Path, sys.argv[3:]):
            mezcla_t = separador._cargar_audio(archivo)
            dur = mezcla_t.shape[1] / 44_100
            t = time.perf_counter()
            with torch.no_grad():
                stems = separador._separar_por_segmentos(modelo, mezcla_t, "cpu", stop_event=None, progress_cb=None)
            rtf = (time.perf_counter() - t) / dur
            clave = hashlib_corto(archivo)
            np.save(trabajo / f"{clave}.mezcla.npy", mezcla_t.numpy())
            np.save(trabajo / f"{clave}.inst.npy", (mezcla_t - stems[idx_voz]).numpy())
            print(f"torch {archivo.name[:40]:40} {dur:6.1f} s  RTF {rtf:.2f}", flush=True)
        return
    modelo_onnx = Path(sys.argv[3])
    opciones = ort.SessionOptions()
    opciones.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sesion = ort.InferenceSession(str(modelo_onnx), opciones)
    for archivo in map(Path, sys.argv[4:]):
        clave = hashlib_corto(archivo)
        mezcla = np.load(trabajo / f"{clave}.mezcla.npy")
        inst_t = np.load(trabajo / f"{clave}.inst.npy")
        dur = mezcla.shape[1] / 44_100
        t = time.perf_counter()
        stems = separar_onnx(sesion, mezcla)
        rtf = (time.perf_counter() - t) / dur
        print(
            f"{modelo_onnx.stem:26} {archivo.name[:40]:40} RTF {rtf:.2f}  "
            f"instrumental frente a PyTorch: {sdr(inst_t, mezcla - stems[3]):.1f} dB",
            flush=True,
        )


def hashlib_corto(archivo: Path) -> str:
    import hashlib

    return hashlib.sha256(str(archivo).encode()).hexdigest()[:12]


if __name__ == "__main__":
    main()
