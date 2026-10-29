"""
Tests para los fixes de iteración tras feedback visual del usuario:
  1) Scrollbars con patrón parent+anchors explícitos (evita "punto" en esquina sup-izq).
  2) Karaoke: BtnControl y btn_accion_global usan Qt.color() para forzar
     conversión y evitar el bug "rectángulo negro".
"""
from pathlib import Path

import pytest

QML_DIR = Path(__file__).resolve().parent.parent / "ui" / "qml"


# ─── Fix scrollbars ──────────────────────────────────────────────────────────

VISTAS_CON_SCROLLVIEW_FIX = [
    ("componentes/NavLateral.qml", "nav_scroll"),
    ("vistas/VistaBusqueda.qml", "resultadosScroll"),
    ("vistas/DjSesionActiva.qml", "_dj_sesion_scroll"),
    ("vistas/VistaDJPrivado.qml", "scroll_construir"),
    ("vistas/VistaDJPrivado.qml", "_prompt_scroll"),
    ("vistas/VistaExploradorCiego.qml", "scrollInicio"),
    ("vistas/VistaExploradorCiego.qml", "scrollJuego"),
    ("vistas/VistaImportacion.qml", "scrollImport"),
    ("vistas/VistaKaraoke.qml", "_kar_scroll"),
    ("vistas/VistaConfiguracion.qml", "configScroll"),
]


@pytest.mark.parametrize("ruta_rel,scroll_id", VISTAS_CON_SCROLLVIEW_FIX)
def test_scrollview_appscrollbar_tiene_parent_y_anchors_explicitos(ruta_rel, scroll_id):
    """Cada ScrollView con AppScrollBar custom debe declarar parent y anchors
    al ScrollView mismo. Sin esto el ScrollBar queda en (0,0) como un punto."""
    contenido = (QML_DIR / ruta_rel).read_text(encoding="utf-8")
    # Debe haber un bloque AppScrollBar con parent: <scroll_id>
    assert f"parent: {scroll_id}\n" in contenido or f"parent: {scroll_id} " in contenido or f"parent: {scroll_id};" in contenido, (
        f"{ruta_rel}: AppScrollBar para '{scroll_id}' no declara `parent: {scroll_id}`"
    )
    # Y anchors al parent (top/right/bottom)
    for prop in ("anchors.top: parent.top", "anchors.right: parent.right", "anchors.bottom: parent.bottom"):
        assert prop in contenido, (
            f"{ruta_rel}: AppScrollBar para '{scroll_id}' debe declarar {prop}"
        )


def test_app_scrollbar_no_tiene_width_padding_extra():
    """AppScrollBar revertido: width: 10 y padding: spacing2 (no width:12 ni rightPadding/leftPadding extras)."""
    contenido = (QML_DIR / "componentes" / "AppScrollBar.qml").read_text(encoding="utf-8")
    assert "width: 10" in contenido
    assert "padding: UiTokens.spacing2" in contenido
    # No deben existir los paddings extra que rompían el layout
    assert "rightPadding:" not in contenido
    assert "leftPadding:" not in contenido
    assert "topPadding:" not in contenido
    assert "bottomPadding:" not in contenido


def test_ningun_scrollview_tiene_rightmargin_extra():
    """No deben quedar `anchors.rightMargin: UiTokens.spacing4` ni `Layout.rightMargin: UiTokens.spacing4`
    en ScrollViews que fueron tocados (esto rompía layouts)."""
    sospechosos = [
        "componentes/NavLateral.qml",
        "vistas/VistaBusqueda.qml",
        "vistas/DjSesionActiva.qml",
        "vistas/VistaDJPrivado.qml",
        "vistas/VistaExploradorCiego.qml",
        "vistas/VistaImportacion.qml",
        "vistas/VistaKaraoke.qml",
        "vistas/VistaConfiguracion.qml",
    ]
    # Estos archivos PUEDEN tener rightMargin en otros sitios legítimos (no en mi ScrollView fix).
    # Auditamos: cada uso de `rightMargin: UiTokens.spacing4` que esté DENTRO del bloque inmediato del
    # ScrollView modificado debería haber sido removido. La aproximación pragmática es buscar la
    # combinación específica de patrón que añadí.
    for ruta in sospechosos:
        contenido = (QML_DIR / ruta).read_text(encoding="utf-8")
        # Patrón antiguo a NO encontrar: `anchors.fill: parent\n        anchors.rightMargin: UiTokens.spacing4`
        # (significaba que mi rightMargin extra seguía aplicado al ScrollView)
        assert "anchors.fill: parent\n        anchors.rightMargin: UiTokens.spacing4" not in contenido, (
            f"{ruta}: ScrollView aún tiene anchors.rightMargin extra (debe quitarse)"
        )


# ─── Fix karaoke botones negros ──────────────────────────────────────────────

def test_karaoke_btn_control_usa_qt_color_para_evitar_undefined():
    """BtnControl debe usar Qt.color() para garantizar conversión cuando
    `tema.acento` (etc) llegan como string desde Python; sin esto, `.r .g .b`
    sobre string es undefined y `Qt.rgba(undef,...)` pinta NEGRO."""
    contenido = (QML_DIR / "vistas" / "VistaKaraoke.qml").read_text(encoding="utf-8")
    # Buscar Qt.color en _bg() del BtnControl
    assert "c = Qt.color(raiz.tema.acento)" in contenido, (
        "BtnControl._bg() no usa Qt.color(raiz.tema.acento) — los botones tono='accent' aparecerán negros"
    )
    assert "c = Qt.color(raiz.tema.peligro)" in contenido
    assert "c = Qt.color(raiz.tema.advertencia)" in contenido


def test_karaoke_btn_accion_global_usa_qt_color():
    """btn_accion_global (Encolar) también debe usar Qt.color() para evitar el bug visual."""
    contenido = (QML_DIR / "vistas" / "VistaKaraoke.qml").read_text(encoding="utf-8")
    # Bloque del color del btn_accion_global usa Qt.color
    assert "var c = primario ? Qt.color(raiz.tema.acento) : Qt.color(colorSemantico)" in contenido, (
        "btn_accion_global no usa Qt.color() para el fondo — Encolar aparecerá negro"
    )


# ─── Fix scrollbars en ListViews import ──────────────────────────────────────

def test_vista_importacion_listviews_tienen_appscrollbar():
    """historialList y pendingList deben usar AppScrollBar attached."""
    contenido = (QML_DIR / "vistas" / "VistaImportacion.qml").read_text(encoding="utf-8")
    # Contar ListView con AppScrollBar attached
    # Patrón mínimo: "ListView { ... ScrollBar.vertical: AppScrollBar ..."
    # Buscamos al menos 2 ocurrencias (historial + pending)
    apariciones = contenido.count("ScrollBar.vertical: AppScrollBar { tema: raiz.tema; policy: ScrollBar.AsNeeded }")
    assert apariciones >= 2, (
        f"VistaImportacion debe tener AppScrollBar en historialList Y pendingList; encontradas: {apariciones}"
    )
