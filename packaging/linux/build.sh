#!/usr/bin/env bash
# =============================================================================
# packaging/linux/build.sh
#
# Construye el bundle Linux de NB Sound con PyInstaller. Empaqueta la salida
# como .tar.gz reproducible y opcionalmente genera un AppImage si la
# herramienta `appimagetool` esta disponible.
#
# Uso:
#   bash packaging/linux/build.sh [--appimage]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT"

WANT_APPIMAGE=0
for arg in "$@"; do
  case "$arg" in
    --appimage) WANT_APPIMAGE=1 ;;
    *) echo "Opcion desconocida: $arg" >&2; exit 2 ;;
  esac
done

echo "[nb_sound] Verificando entorno Python (requiere Python 3.12)…"
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]] && "$ROOT/.venv/bin/python" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)' 2>/dev/null; then
    PYTHON_BIN="$ROOT/.venv/bin/python"
  elif command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="python3.12"
  elif [[ -x "$HOME/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu/bin/python3.12" ]]; then
    PYTHON_BIN="$HOME/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu/bin/python3.12"
  elif command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)' 2>/dev/null; then
    PYTHON_BIN="python3"
  else
    echo "[nb_sound] ERROR: No se encontró Python 3.12. Instala Python 3.12 o define PYTHON_BIN." >&2
    exit 1
  fi
fi

echo "[nb_sound] Usando Python: $("$PYTHON_BIN" --version) ($PYTHON_BIN)"

if ! "$PYTHON_BIN" -m PyInstaller --version >/dev/null 2>&1; then
  echo "[nb_sound] PyInstaller no encontrado en $PYTHON_BIN, instalando…"
  if command -v uv >/dev/null 2>&1; then
    uv pip install "pyinstaller>=6.0" --python "$PYTHON_BIN"
  else
    "$PYTHON_BIN" -m pip install "pyinstaller>=6.0"
  fi
fi

echo "[nb_sound] Limpiando builds previos…"
rm -rf build dist

echo "[nb_sound] Generando bundle PyInstaller…"
"$PYTHON_BIN" -m PyInstaller packaging/linux/nb_sound.spec --noconfirm

ARTIFACT_DIR="dist/nb_sound"
if [[ ! -d "$ARTIFACT_DIR" ]]; then
  echo "[nb_sound] ERROR: $ARTIFACT_DIR no fue creado por PyInstaller." >&2
  exit 1
fi

echo "[nb_sound] Empaquetando tar.gz…"
TAR_NAME="nb_sound-linux-x64.tar.gz"
( cd dist && tar -czf "$TAR_NAME" nb_sound )
sha256sum "dist/$TAR_NAME" > "dist/${TAR_NAME}.sha256"
echo "[nb_sound] OK: dist/$TAR_NAME"

if [[ "$WANT_APPIMAGE" -eq 1 ]]; then
  if ! command -v appimagetool >/dev/null 2>&1; then
    echo "[nb_sound] appimagetool no encontrado; salto AppImage." >&2
    exit 0
  fi
  APPDIR="dist/NBSound.AppDir"
  rm -rf "$APPDIR"
  mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
           "$APPDIR/usr/share/icons/hicolor/512x512/apps" \
           "$APPDIR/usr/share/metainfo"
  cp -r "$ARTIFACT_DIR"/* "$APPDIR/usr/bin/"
  cp packaging/linux/nb-sound.desktop "$APPDIR/usr/share/applications/"
  cp packaging/linux/nb-sound.desktop "$APPDIR/nb-sound.desktop"
  cp ui/qml/assets/logo/logo_512.png "$APPDIR/usr/share/icons/hicolor/512x512/apps/nb-sound.png"
  cp ui/qml/assets/logo/logo_512.png "$APPDIR/nb-sound.png"
  cp packaging/linux/com.nbsound.NBSound.metainfo.xml "$APPDIR/usr/share/metainfo/" 2>/dev/null || true
  cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/nb_sound" "$@"
EOF
  chmod +x "$APPDIR/AppRun"
  ARCH="$(uname -m)" appimagetool "$APPDIR" "dist/NB_Sound-x86_64.AppImage"
  echo "[nb_sound] OK: dist/NB_Sound-x86_64.AppImage"
fi
