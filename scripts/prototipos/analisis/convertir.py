"""F0.4.3, paso 1: convertir los modelos de Essentia a ONNX y comprobar el grafo.

Herramienta de desarrollo (ver check-sin-python). Entorno propio:

    cd scripts/prototipos/analisis
    uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python \
        tensorflow-cpu tf2onnx onnxruntime==1.31.1 numpy
    .venv/bin/python convertir.py <carpeta-pb> <carpeta-salida> [modelo...]

Para cada `.pb` lee su `.json` (entradas y salidas que declara Essentia), lo
convierte con tf2onnx y ejecuta el original en TensorFlow y el convertido en ONNX
Runtime 1.31.1 —el mismo que viaja en el instalador— sobre la misma entrada
aleatoria. Imprime la diferencia máxima por salida.

El cambio de formato es lo que permite la licencia de los modelos (CC 4.0,
sección 2.a.4: las modificaciones técnicas para usar la obra en otro formato no
producen material adaptado). Ver ADR-010.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import tensorflow as tf
import tf2onnx


def cargar_grafo(pb: Path) -> tf.compat.v1.GraphDef:
    grafo = tf.compat.v1.GraphDef()
    grafo.ParseFromString(pb.read_bytes())
    return grafo


def forma_con_lote(forma: list[int]) -> list[int]:
    # Essentia declara la forma sin el lote en los modelos de parches.
    return forma if len(forma) == 3 else [1, *forma]


def main() -> None:
    origen, destino = Path(sys.argv[1]), Path(sys.argv[2])
    destino.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(2026)
    solo = set(sys.argv[3:])
    for meta_ruta in sorted(origen.glob("*.json")):
        pb = meta_ruta.with_suffix(".pb")
        if not pb.exists() or (solo and pb.stem not in solo):
            continue
        meta = json.loads(meta_ruta.read_text())
        esquema = meta["schema"]
        entradas = [e["name"] for e in esquema["inputs"]]
        salidas = [s["name"] for s in esquema["outputs"]]
        grafo = cargar_grafo(pb)

        nombres_tf = [f"{n}:0" if ":" not in n else n for n in entradas]
        salidas_tf = [f"{n}:0" if ":" not in n else n for n in salidas]
        modelo, _ = tf2onnx.convert.from_graph_def(
            grafo, input_names=nombres_tf, output_names=salidas_tf, opset=17
        )
        onnx_ruta = destino / f"{pb.stem}.onnx"
        onnx_ruta.write_bytes(modelo.SerializeToString())

        forma = [d if isinstance(d, int) and d > 0 else 1 for d in forma_con_lote(esquema["inputs"][0]["shape"])]
        x = rng.standard_normal(forma).astype(np.float32)
        if "musicnn" in pb.stem and len(esquema["inputs"][0]["shape"]) == 1:
            x = np.abs(x)

        with tf.compat.v1.Session(graph=tf.Graph()) as sesion:
            tf.import_graph_def(grafo, name="")
            ref = sesion.run(salidas_tf, {nombres_tf[0]: x})

        sesion_onnx = ort.InferenceSession(str(onnx_ruta))
        nombre_entrada = sesion_onnx.get_inputs()[0].name
        # Las salidas se piden por nombre: tf2onnx no garantiza el orden.
        obtenido = sesion_onnx.run(salidas_tf, {nombre_entrada: x})
        difs = [float(np.max(np.abs(a - b))) for a, b in zip(ref, obtenido)]
        print(
            f"{pb.stem:42} entrada {forma}  {onnx_ruta.stat().st_size / 1e6:6.1f} MB  "
            f"diferencia máxima por salida: {', '.join(f'{d:.1e}' for d in difs)}",
            flush=True,
        )


if __name__ == "__main__":
    main()
