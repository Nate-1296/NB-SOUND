#!/usr/bin/env bash
# =============================================================================
# packaging/macos/build.sh
#
# Genera el bundle .app de NB Sound con PyInstaller y empaqueta como .zip
# (usando `ditto` para preservar metadata de macOS) o como .dmg si
# `create-dmg` esta disponible.
#
# Uso:
#   bash packaging/macos/build.sh [--dmg]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT"

WANT_DMG=0
for arg in "$@"; do
  case "$arg" in
    --dmg) WANT_DMG=1 ;;
    *) echo "Opcion desconocida: $arg" >&2; exit 2 ;;
  esac
done

echo "[nb_sound] Verificando PyInstaller…"
python3 -m pip show pyinstaller > /dev/null 2>&1 || python3 -m pip install "pyinstaller>=6.0"

echo "[nb_sound] Limpiando builds previos…"
rm -rf build dist

echo "[nb_sound] Generando .app…"
python3 -m PyInstaller packaging/macos/nb_sound.spec --noconfirm

APP_BUNDLE="dist/NB Sound.app"
if [[ ! -d "$APP_BUNDLE" ]]; then
  echo "[nb_sound] ERROR: $APP_BUNDLE no fue creado." >&2
  exit 1
fi

echo "[nb_sound] Empaquetando .zip…"
ZIP_NAME="nb_sound-macos-arm64.zip"
( cd dist && ditto -c -k --sequesterRsrc --keepParent "NB Sound.app" "$ZIP_NAME" )
shasum -a 256 "dist/$ZIP_NAME" > "dist/${ZIP_NAME}.sha256"
echo "[nb_sound] OK: dist/$ZIP_NAME"

if [[ "$WANT_DMG" -eq 1 ]]; then
  if ! command -v create-dmg >/dev/null 2>&1; then
    echo "[nb_sound] create-dmg no encontrado (brew install create-dmg); salto DMG." >&2
    exit 0
  fi
  DMG_NAME="dist/NBSound-macos.dmg"
  rm -f "$DMG_NAME"
  create-dmg \
    --volname "NB Sound" \
    --window-size 600 400 \
    --icon-size 100 \
    --app-drop-link 400 200 \
    "$DMG_NAME" \
    "$APP_BUNDLE"
  shasum -a 256 "$DMG_NAME" > "${DMG_NAME}.sha256"
  echo "[nb_sound] OK: $DMG_NAME"
fi
