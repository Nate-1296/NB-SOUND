"""
Tests de consistencia QML: ningún glifo Unicode como icono, sin hardcodes
de hex sobre superficies funcionales, scrollbars unificadas.
"""
import re
from pathlib import Path

import pytest

QML_DIR = Path(__file__).resolve().parent.parent / "ui" / "qml"


GLIFOS_PROHIBIDOS_COMO_ICONO = ["♪", "♫", "♬", "♩"]


def _archivos_qml():
    return list(QML_DIR.rglob("*.qml"))


def test_ningun_glifo_unicode_en_text_como_icono():
    """Ningún archivo debe tener `text: "♪"` (glifo musical como icono)."""
    ofensores = []
    for path in _archivos_qml():
        contenido = path.read_text(encoding="utf-8")
        for glifo in GLIFOS_PROHIBIDOS_COMO_ICONO:
            if f'text: "{glifo}"' in contenido or f"text: '{glifo}'" in contenido:
                ofensores.append(f"{path.relative_to(QML_DIR)}: {glifo}")
    assert ofensores == [], (
        "Glifos Unicode usados como icono detectados:\n  " + "\n  ".join(ofensores)
    )


def test_scrollbars_inline_usan_appscrollbar():
    """Cero `ScrollBar { policy: ... }` inline. Debe ser AppScrollBar { tema: ..., policy: ... }
    o un componente derivado (LibraryScrollBar, InicioScrollBar, PerfilScrollBar, AlbumScrollBar)."""
    pat_inline = re.compile(r"ScrollBar\.\w+\s*:\s*ScrollBar\s*\{\s*policy")
    ofensores = []
    for path in _archivos_qml():
        contenido = path.read_text(encoding="utf-8")
        if pat_inline.search(contenido):
            ofensores.append(str(path.relative_to(QML_DIR)))
    assert ofensores == [], (
        "Scrollbars inline detectadas (usar AppScrollBar):\n  " + "\n  ".join(ofensores)
    )


def test_app_scrollbar_existe_y_define_contrato():
    asb = QML_DIR / "componentes" / "AppScrollBar.qml"
    assert asb.exists(), "AppScrollBar.qml no existe"
    contenido = asb.read_text(encoding="utf-8")
    assert "property var flickable" in contenido
    assert "property var tema" in contenido


def test_uitokens_define_jerarquia_tipografica_completa():
    contenido = (QML_DIR / "componentes" / "UiTokens.qml").read_text(encoding="utf-8")
    for token in (
        "fontSizeXs", "fontSizeSm", "fontSizeMd",
        "fontSizeBase", "fontSizeLg", "fontSizeXl",
        "fontSize2xl", "fontSizeDisplay",
    ):
        assert f"property int {token}" in contenido, f"Token {token} ausente en UiTokens"


def test_uitokens_define_escala_spacing_completa():
    contenido = (QML_DIR / "componentes" / "UiTokens.qml").read_text(encoding="utf-8")
    for n in (2, 4, 6, 8, 10, 12, 14, 16, 20, 24, 32):
        assert f"spacing{n}" in contenido, f"spacing{n} ausente en UiTokens"


def test_uitokens_define_radios_y_pill():
    contenido = (QML_DIR / "componentes" / "UiTokens.qml").read_text(encoding="utf-8")
    for radio in ("radiusSm", "radiusMd", "radiusLg", "radiusPill"):
        assert radio in contenido, f"{radio} ausente en UiTokens"


def test_no_existe_tooltip_en_qml():
    """Cero ToolTip en QML (decisión de diseño v1)."""
    ofensores = []
    for path in _archivos_qml():
        contenido = path.read_text(encoding="utf-8")
        if re.search(r"\bToolTip\s*\{", contenido):
            ofensores.append(str(path.relative_to(QML_DIR)))
    assert ofensores == [], f"ToolTip detectado: {ofensores}"


def test_sin_color_hex_hardcoded_en_componentes_centrales():
    """Componentes núcleo no deben tener `color: "#xxxxxx"` literal salvo el default
    de ToastMessage (intencional como fallback sobreescribible)."""
    PERMITIDOS = {"ToastMessage.qml"}
    pat = re.compile(r'\bcolor:\s*"#[0-9a-fA-F]{3,8}"')
    ofensores = []
    for path in (QML_DIR / "componentes").glob("*.qml"):
        if path.name in PERMITIDOS:
            continue
        contenido = path.read_text(encoding="utf-8")
        for m in pat.finditer(contenido):
            ofensores.append(f"{path.name}: {m.group(0)}")
    assert ofensores == [], (
        "Hex hardcoded en componentes núcleo:\n  " + "\n  ".join(ofensores)
    )


def test_iconos_referenciados_existen():
    """Cada `source: ".../assets/icons/X.svg"` debe apuntar a un asset real."""
    pat_icon = re.compile(r'source:\s*"\.\./assets/icons/([\w\-./]+\.svg)"')
    base_iconos = QML_DIR / "assets" / "icons"
    faltantes = []
    for path in _archivos_qml():
        contenido = path.read_text(encoding="utf-8")
        for m in pat_icon.finditer(contenido):
            ruta = base_iconos / m.group(1)
            if not ruta.exists():
                faltantes.append(f"{path.relative_to(QML_DIR)} → {m.group(1)}")
    assert faltantes == [], (
        "SVGs referenciados pero ausentes:\n  " + "\n  ".join(faltantes)
    )
