# =============================================================================
# infra/version.py
#
# Fuente única de verdad para identidad y versión de la aplicación.
# Cualquier banner, --version, splash o metadata debe leer desde aquí.
# =============================================================================

APP_NAME = "NB SOUND"
APP_VERSION = "1.1.0"
# Versión legible para banners/--version. Sigue a APP_VERSION para que CLI y UI
# muestren siempre la versión real (p. ej. "v1.1.0"), no solo el major.
APP_VERSION_DISPLAY = f"v{APP_VERSION}"

CLI_NAME = f"{APP_NAME} CLI"
UI_NAME = f"{APP_NAME} UI"

CLI_BANNER = f"{CLI_NAME} {APP_VERSION_DISPLAY}"
UI_BANNER = f"{UI_NAME} {APP_VERSION_DISPLAY}"

APP_DESCRIPTION = "Catalogador inteligente de bibliotecas de audio"
APP_AUTHOR = "Nathan"
APP_LICENSE = "GPL-3.0-or-later"
APP_HOMEPAGE = "https://github.com/Nate-1296/NB-SOUND"
APP_IDENTIFIER = "com.nbsound.app"
