# =============================================================================
# infra/version.py
#
# Fuente única de verdad para identidad y versión de la aplicación.
# Cualquier banner, --version, splash o metadata debe leer desde aquí.
# =============================================================================

APP_NAME = "NB SOUND"
APP_VERSION = "1.0.1"
APP_VERSION_DISPLAY = "v1"

CLI_NAME = f"{APP_NAME} CLI"
UI_NAME = f"{APP_NAME} UI"

CLI_BANNER = f"{CLI_NAME} {APP_VERSION_DISPLAY}"
UI_BANNER = f"{UI_NAME} {APP_VERSION_DISPLAY}"

APP_DESCRIPTION = "Catalogador inteligente de bibliotecas de audio"
APP_AUTHOR = "Nathan"
APP_LICENSE = "GPL-3.0-or-later"
APP_HOMEPAGE = "https://github.com/Nate-1296/NB-SOUND"
APP_IDENTIFIER = "com.nbsound.app"
