"""F0.4.3, paso 2: lo que Essentia le da a los modelos, para compararlo en Rust.

Herramienta de desarrollo (ver check-sin-python). Con el entorno de esta carpeta:

    .venv/bin/python referencia.py <carpeta-pb> <salida> <archivo>...

Para cada archivo reproduce exactamente la cadena de la V1
(`legado/core/audio_intelligence_deep.py`): `MonoLoader` a 16 kHz con
`resampleQuality=4`, y la red de streaming de Essentia con su `FrameCutter` y
`TensorflowInputMusiCNN`. Guarda en `<salida>`:

* `<id>.audio.f32`: la señal a 16 kHz que ve Essentia (para aislar el decodificador);
* `<id>.musicnn.f32`: las bandas mel de MusiCNN, marco a marco (96 por marco). VGGish no: la V1
  guardaba sus embeddings pero nada los usaba, y la V2 lo retira;
* `<id>.salidas.json`: las salidas medias de cada modelo, como las guardaba la V1.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import essentia
import essentia.standard as es
import essentia.streaming as ess

essentia.log.warningActive = False


def bandas(audio: np.ndarray, marco: int, salto: int, algoritmo) -> np.ndarray:
    pool = essentia.Pool()
    fuente = ess.VectorInput(audio)
    cortador = ess.FrameCutter(frameSize=marco, hopSize=salto)
    entrada = algoritmo()
    fuente.data >> cortador.signal
    cortador.frame >> entrada.frame
    entrada.bands >> (pool, "bandas")
    essentia.run(fuente)
    return np.array(pool["bandas"], dtype=np.float32)


def media(raw) -> list[float]:
    return np.asarray(raw, dtype=np.float64).mean(axis=0).tolist()


def main() -> None:
    modelos, salida = Path(sys.argv[1]), Path(sys.argv[2])
    salida.mkdir(parents=True, exist_ok=True)
    for archivo in map(Path, sys.argv[3:]):
        clave = hashlib.sha256(str(archivo).encode()).hexdigest()[:12]
        audio = es.MonoLoader(filename=str(archivo), sampleRate=16000, resampleQuality=4)()
        musicnn = bandas(audio, 512, 256, ess.TensorflowInputMusiCNN)
        # Crudo en f32 little-endian: lo lee el prototipo de Rust sin dependencias.
        for nombre, datos in (("audio", audio), ("musicnn", musicnn)):
            np.asarray(datos, dtype="<f4").tofile(salida / f"{clave}.{nombre}.f32")

        emb = es.TensorflowPredictMusiCNN(
            graphFilename=str(modelos / "msd-musicnn-1.pb"), output="model/dense/BiasAdd"
        )(audio)
        salidas = {
            "msd_musicnn_embeddings": media(emb),
            "tags_msd50": media(
                es.TensorflowPredictMusiCNN(
                    graphFilename=str(modelos / "msd-musicnn-1.pb"), output="model/Sigmoid"
                )(audio)
            ),
        }
        for cabeza, nodo in (
            ("danceability-msd-musicnn-1", "model/Softmax"),
            ("mood_happy-msd-musicnn-1", "model/Softmax"),
            ("mood_sad-msd-musicnn-1", "model/Softmax"),
            ("mood_relaxed-msd-musicnn-1", "model/Softmax"),
            ("mood_aggressive-msd-musicnn-1", "model/Softmax"),
            ("mood_party-msd-musicnn-1", "model/Softmax"),
            ("deam-msd-musicnn-2", "model/Identity"),
        ):
            salidas[cabeza] = media(
                es.TensorflowPredict2D(graphFilename=str(modelos / f"{cabeza}.pb"), output=nodo)(emb)
            )
        (salida / f"{clave}.salidas.json").write_text(
            json.dumps({"archivo": str(archivo), "marcos_musicnn": len(musicnn), **salidas})
        )
        print(f"{clave} {archivo.name}", flush=True)


if __name__ == "__main__":
    main()
