#!/usr/bin/env bash
# Arma el agregado de aceleración para Linux con NVIDIA (F5.1.5, P6):
# ONNX Runtime con el proveedor CUDA y las bibliotecas de CUDA 12 y cuDNN 9 que
# necesita, sacadas de las ruedas oficiales de NVIDIA en PyPI (solo se descomprimen;
# no se usa Python). Con el controlador de NVIDIA instalado, no hace falta nada más.
#
# Uso: scripts/agregados/aceleracion-linux.sh <carpeta de trabajo>
# Deja <carpeta>/aceleracion-linux-1.zip y su SHA-256 y tamaño en la salida, que es
# lo que se copia al catálogo de `agregados.rs`.
set -euo pipefail

TRABAJO=${1:?carpeta de trabajo}
ORT_VERSION=1.31.1
ORT="onnxruntime-linux-x64-gpu_cuda12-$ORT_VERSION"
RUEDAS=(nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 nvidia-cufft-cu12 nvidia-curand-cu12 nvidia-cudnn-cu12)

mkdir -p "$TRABAJO/descargas" "$TRABAJO/contenido"
cd "$TRABAJO"
rm -rf contenido/*

if [[ ! -f "descargas/$ORT.tgz" ]]; then
  curl -fL --retry 3 -o "descargas/$ORT.tgz" \
    "https://github.com/microsoft/onnxruntime/releases/download/v$ORT_VERSION/$ORT.tgz"
fi
tar -xzf "descargas/$ORT.tgz" -C descargas
# Solo las bibliotecas, con el nombre que carga NB Sound para la principal.
cp -L "descargas/$ORT/lib/libonnxruntime.so.$ORT_VERSION" contenido/libonnxruntime.so
cp -L descargas/"$ORT"/lib/libonnxruntime_providers_shared.so contenido/
cp -L descargas/"$ORT"/lib/libonnxruntime_providers_cuda.so contenido/

for rueda in "${RUEDAS[@]}"; do
  url=$(curl -fs "https://pypi.org/pypi/$rueda/json" |
    jq -r '[.urls[] | select(.filename | test("manylinux.*x86_64"))][0].url')
  archivo="descargas/$(basename "$url")"
  [[ -f $archivo ]] || curl -fL --retry 3 -o "$archivo" "$url"
  unzip -oq "$archivo" 'nvidia/*/lib/*.so*' -d descargas/ruedas
done
find descargas/ruedas -name '*.so*' -type f -exec cp {} contenido/ \;

cat >contenido/LEEME.txt <<'TXT'
NB Sound - agregado de aceleración (Linux, NVIDIA)
ONNX Runtime (MIT) con el proveedor CUDA, y CUDA Runtime, cuBLAS, cuFFT, cuRAND y cuDNN
de NVIDIA, redistribuidos según el acuerdo de licencia de CUDA (EULA de NVIDIA,
"Attachment A", bibliotecas redistribuibles) y el de cuDNN. Necesita el controlador
de NVIDIA del sistema.
TXT

rm -f aceleracion-linux-1.zip
(cd contenido && zip -q -9 -r ../aceleracion-linux-1.zip .)
du -sh contenido
printf 'TAMANO %s\nSHA256 %s\n' "$(stat -c %s aceleracion-linux-1.zip)" \
  "$(sha256sum aceleracion-linux-1.zip | cut -d' ' -f1)"
