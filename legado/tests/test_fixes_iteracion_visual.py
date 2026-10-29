"""
Tests para los 6 fixes visuales/funcionales:
  1) A ciegas: portada se mantiene cuadrada en modo compacto.
  2) Búsqueda: orden con coincidencia exacta primero y favoritos sólo si matchean.
  3) Karaoke: botones deshabilitados con borde visible (no rectángulos negros planos).
  4) Perfil HabitCard: snapshot de items mostrados, botón reproduce EXACTAMENTE eso.
  5) Perfil recomendaciones: barajado para frescura entre sesiones.
  6) Scrollbars unificadas en todas las vistas + AppScrollBar con padding lateral.
"""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QML_DIR = Path(__file__).resolve().parent.parent / "ui" / "qml"


# ─── Fix 1: A ciegas portada cuadrada ────────────────────────────────────────

def test_explorador_ciego_portada_es_cuadrada():
    """En modo compacto, la columna de portada debe usar preferredWidth/Height
    iguales (cuadrado) y NO fillWidth (que la estiraba horizontalmente)."""
    contenido = (QML_DIR / "vistas" / "VistaExploradorCiego.qml").read_text(encoding="utf-8")
    # Debe usar preferredWidth + preferredHeight = ladoPortada
    assert "Layout.preferredWidth:  tarjetaReto.ladoPortada" in contenido
    assert "Layout.preferredHeight: tarjetaReto.ladoPortada" in contenido
    # No debe haber Layout.fillWidth: tarjetaReto.cw (el patrón antiguo que estiraba)
    assert "Layout.fillWidth:       tarjetaReto.cw" not in contenido


def test_explorador_ciego_lado_portada_tiene_minimo_razonable():
    """ladoPortada en cw debe tener un mínimo (Math.max) para no degenerar a 0
    en anchos muy pequeños."""
    contenido = (QML_DIR / "vistas" / "VistaExploradorCiego.qml").read_text(encoding="utf-8")
    assert "Math.max(140, Math.min(280, tarjetaReto.anchoVista" in contenido


# ─── Fix 2: Búsqueda reordenada ─────────────────────────────────────────────

def test_busqueda_helpers_normalizacion_y_match_exacto():
    contenido = (QML_DIR / "vistas" / "VistaBusqueda.qml").read_text(encoding="utf-8")
    for nombre in ("_normalizar", "_hayMatchExacto", "_ordenSeccionesBusqueda"):
        assert nombre in contenido, f"VistaBusqueda no define {nombre}"


def test_busqueda_ordenes_secciones_con_filas_planas():
    contenido = (QML_DIR / "vistas" / "VistaBusqueda.qml").read_text(encoding="utf-8")
    # Repeater principal consume el array plano
    assert "model: raiz._filasPlanas" in contenido
    # Y existe _ordenSeccionesBusqueda como input de _filasPlanas
    assert "_ordenSeccionesBusqueda" in contenido


def test_busqueda_filas_planas_sin_sub_columnlayout():
    """Las filas son items leaf directos en el padre — sin sub-ColumnLayout."""
    contenido = (QML_DIR / "vistas" / "VistaBusqueda.qml").read_text(encoding="utf-8")
    # Los Components legacy con sub-ColumnLayout NO deben existir
    assert "_compSeccionFavoritos" not in contenido
    assert "_compSeccionArtistas" not in contenido
    assert "_compSeccionAlbums" not in contenido
    assert "_compSeccionPistas" not in contenido


# ─── Fix 3: Karaoke botones deshabilitados con borde ─────────────────────────

def test_karaoke_btn_control_borde_visible_si_deshabilitado():
    contenido = (QML_DIR / "vistas" / "VistaKaraoke.qml").read_text(encoding="utf-8")
    # BtnControl debe tener border que considere !habilitado y use tema.borde
    assert "border.color: !habilitado\n                            ? raiz.tema.borde" in contenido
    # Y border.width debe ser 1 cuando !habilitado (no 0)
    assert "border.width: (!habilitado || tono !== \"accent\") ? 1 : 0" in contenido


def test_karaoke_btn_accion_global_borde_visible_si_deshabilitado():
    contenido = (QML_DIR / "vistas" / "VistaKaraoke.qml").read_text(encoding="utf-8")
    # btn_accion_global border.width debe ser 1 cuando deshabilitado
    assert "border.width: (!habilitado || !primario) ? 1 : 0" in contenido


# ─── Fix 4: HabitCard snapshot estable ───────────────────────────────────────

def test_perfil_habitcard_emite_snapshot_no_modelo():
    contenido = (QML_DIR / "vistas" / "VistaPerfil.qml").read_text(encoding="utf-8")
    # HabitCard ahora tiene property itemsVisibles
    assert "property var itemsVisibles" in contenido
    # signal reproducirClicked emite el array
    assert "signal reproducirClicked(var pistas)" in contenido
    # La función _recomputarItems existe
    assert "function _recomputarItems()" in contenido
    # Connections target del modelo para refrescar items
    assert "function onTotalCambiado() { hc._recomputarItems() }" in contenido


def test_perfil_handlers_usan_pistas_directas():
    contenido = (QML_DIR / "vistas" / "VistaPerfil.qml").read_text(encoding="utf-8")
    # Los handlers ahora aceptan el array directo y llaman _reproducirPistas
    assert "onReproducirClicked: function(pistas) { raiz._reproducirPistas(pistas) }" in contenido
    # Y _reproducirPistas existe
    assert "function _reproducirPistas(pistas)" in contenido


# ─── Fix 5: recomendaciones_inicio barajado ─────────────────────────────────

def test_recomendaciones_inicio_baraja_resultados():
    """servicios/biblioteca.py recomendaciones_inicio debe random.shuffle()
    los pools antes de mezclar para que cada llamada dé pistas distintas."""
    contenido = (Path(__file__).resolve().parent.parent / "servicios" / "biblioteca.py").read_text(encoding="utf-8")
    # Debe importar random
    assert "import random" in contenido
    # Y aplicar shuffle a favoritos y exploracion
    assert "random.shuffle(favoritos)" in contenido
    assert "random.shuffle(exploracion)" in contenido


def test_recomendaciones_inicio_devuelve_orden_distinto_entre_llamadas():
    """Smoke real: dos llamadas seguidas con biblioteca poblada deben dar
    al menos algún orden distinto. Si la biblioteca está vacía, se omite."""
    from db.conexion import inicializar_db, cerrar_db
    from servicios import biblioteca as svc_bib
    import tempfile
    from pathlib import Path as _P

    # Usamos la BD real del usuario si existe, sino skip.
    db_default = _P.home() / ".local" / "share" / "nb_sound" / "ui.db"
    try:
        from config import settings as _settings
        if _settings.DEFAULT_LIBRARY_DIR:
            db_default = _settings.DEFAULT_LIBRARY_DIR / "nb_sound.sqlite3"
    except Exception:
        pass

    if not db_default.exists():
        pytest.skip("Biblioteca real no disponible para smoke test")

    inicializar_db(db_default)
    try:
        r1 = svc_bib.recomendaciones_inicio(limite=30)
        r2 = svc_bib.recomendaciones_inicio(limite=30)
        if len(r1) < 6 or len(r2) < 6:
            pytest.skip(f"Biblioteca con muy pocas pistas ({len(r1)}, {len(r2)})")
        # Al menos uno de los primeros 6 debe diferir entre llamadas
        ids1 = [int(x.get("id") or 0) for x in r1[:6]]
        ids2 = [int(x.get("id") or 0) for x in r2[:6]]
        assert ids1 != ids2, (
            f"recomendaciones_inicio dio el mismo orden dos veces consecutivas: {ids1}"
        )
    finally:
        cerrar_db()


# ─── Fix 6: Scrollbars unificadas en TODAS las vistas ───────────────────────

def test_todas_las_scrollviews_usan_appscrollbar():
    """Cero ScrollView que use el ScrollBar default de Qt: deben asignar
    ScrollBar.vertical: AppScrollBar (o un componente derivado de mismo patrón)."""
    import re
    NAMED = ['AppScrollBar', 'LibraryScrollBar', 'InicioScrollBar',
             'PerfilScrollBar', 'AlbumScrollBar']
    ofensores = []
    for path in QML_DIR.rglob('*.qml'):
        contenido = path.read_text(encoding="utf-8")
        lineas = contenido.splitlines()
        for i, l in enumerate(lineas):
            if not re.search(r'\bScrollView\s*\{', l):
                continue
            chunk = "\n".join(lineas[i:i+30])
            usa = any(re.search(rf'ScrollBar\.vertical:\s*{n}\b', chunk) for n in NAMED)
            if not usa:
                ofensores.append(f"{path.relative_to(QML_DIR)}:{i+1}")
    assert ofensores == [], (
        "ScrollViews sin scrollbar unificada:\n  " + "\n  ".join(ofensores)
    )


def test_app_scrollbar_dimensiones_estandar():
    """AppScrollBar revertido a su patrón estándar: width: 10 + padding: spacing2.
    Cambios anteriores con width: 12 + padding extra rompían layout cuando se
    usaba como custom ScrollBar en ScrollView (ver test_fixes_scrollbar_y_karaoke_botones)."""
    contenido = (QML_DIR / "componentes" / "AppScrollBar.qml").read_text(encoding="utf-8")
    assert "width: 10" in contenido
    assert "padding: UiTokens.spacing2" in contenido
