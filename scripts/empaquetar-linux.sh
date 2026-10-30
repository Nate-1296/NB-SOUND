#!/usr/bin/env bash
# Empaqueta NB Sound para Linux dentro de un Ubuntu 22.04 (F0.3.4).
#
# Por qué en un contenedor: compilado en Arch, el binario exige la glibc de Arch
# (2.44) y no arranca en Ubuntu 24.04 (2.39) ni en nada más antiguo. Se compila en
# la distribución más antigua que se soporta, y lo compilado ahí corre en todo lo
# posterior. Lo mismo hace el CI de Tauri.
#
# Uso: scripts/empaquetar-linux.sh        (necesita podman)
# Deja el .deb y la AppImage en src-tauri/target/ubuntu-22.04/release/bundle/.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
IMAGEN="docker.io/library/ubuntu:22.04"

podman run --rm \
  --memory 8g \
  -v "$RAIZ":/repo:Z \
  -v nb-sound-cargo:/root/.cargo \
  -v nb-sound-rustup:/root/.rustup \
  -w /repo \
  -e CARGO_TARGET_DIR=/repo/src-tauri/target/ubuntu-22.04 \
  -e DEBIAN_FRONTEND=noninteractive \
  "$IMAGEN" bash -euo pipefail -c '
    apt-get update -qq
    apt-get install -y -qq curl ca-certificates build-essential pkg-config file xz-utils \
      libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev libssl-dev patchelf >/dev/null
    if ! command -v node >/dev/null; then
      curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null
      apt-get install -y -qq nodejs >/dev/null
    fi
    corepack enable >/dev/null 2>&1 || npm install -g pnpm >/dev/null
    [ -x /root/.cargo/bin/cargo ] || curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain 1.98.0 >/dev/null
    export PATH=/root/.cargo/bin:$PATH
    pnpm install --frozen-lockfile >/dev/null
    node scripts/fetch-binarios.mjs
    pnpm tauri build --bundles deb,appimage
  '
