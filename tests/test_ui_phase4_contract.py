from pathlib import Path

import pytest

from db.conexion import cerrar_db, get_conexion, inicializar_db
from ui.modelos_qml import ModeloImportacion, ModeloRevision


@pytest.fixture()
def db_tmp(tmp_path):
    ruta = tmp_path / "phase4_contract.db"
    inicializar_db(ruta)
    try:
        yield ruta
    finally:
        cerrar_db()


def test_principal_mantiene_revision_integrada_en_importacion():
    qml = Path("ui/qml/Principal.qml").read_text(encoding="utf-8")

    assert '"importacion": 4' in qml
    assert '"configuracion": 5' in qml
    assert '"revision":' not in qml
    assert 'loader_revision' not in qml
    assert 'comp_vista_revision' not in qml


def test_nav_lateral_no_expone_revision_como_destino():
    qml = Path("ui/qml/componentes/NavLateral.qml").read_text(encoding="utf-8")

    assert 'id: nav_importacion' in qml
    assert 'id: nav_revision' not in qml
    assert 'vista_activa === "revision"' not in qml
    assert 'focoSiguiente: nav_karaoke' in qml


def test_qmldir_no_registra_vista_revision():
    qml = Path("ui/qml/vistas/qmldir").read_text(encoding="utf-8")

    assert "VistaImportacion 1.0 VistaImportacion.qml" in qml
    assert "VistaRevision" not in qml


def test_vista_importacion_simple_y_pro_con_historial_y_filtros_revision():
    qml = Path("ui/qml/vistas/VistaImportacion.qml").read_text(encoding="utf-8")
    ruta_readonly = qml.split("component RutaReadOnly: Rectangle", 1)[1].split("component ExecutionStatusPanel", 1)[0]
    revision_integrada = qml.split('AppText { text: "Revisión integrada"', 1)[1].split("GridLayout {\n                        Layout.fillWidth: true\n                        columns: raiz.wideWidth", 1)[0]
    filter_group = qml.split("component FilterGroup: GridLayout", 1)[1].split("component HeaderBadgeFlow: Flow", 1)[0]
    execution_panel = qml.split("component ExecutionStatusPanel: AppCard", 1)[1].split("component HistoryPanel: AppCard", 1)[0]

    assert 'objectName: "vista_importacion"' in qml
    assert 'contentWidth: availableWidth' in qml
    assert 'ScrollBar.horizontal.policy: ScrollBar.AlwaysOff' in qml
    assert "StackLayout" in qml
    assert 'readonly property int contentMaxWidth: 1240' in qml
    assert 'readonly property real availableContentWidth' in qml
    assert 'objectName: "importacion_ruta_entrada_readonly"' in qml
    assert "TextField" not in ruta_readonly
    assert 'property int historial_simple_expandido: -1' in qml
    assert 'Resumen de ejecuciones' in qml
    assert 'Dry-run simula la corrida' in qml
    assert 'Detalle de ejecución' in qml
    assert 'filtro_revision_tipo' in qml
    assert 'filtro_revision_causa' in qml
    assert "component ThemedComboBox" not in qml
    assert "ComboBox" not in revision_integrada
    assert "component FilterGroup: GridLayout" in qml
    assert "component HeaderBadgeFlow: Flow" in qml
    assert 'Layout.alignment: raiz.compactWidth ? Qt.AlignLeft : (Qt.AlignRight | Qt.AlignTop)' in qml
    assert qml.count("HeaderBadgeFlow {") >= 3
    assert 'objectName: "filtros_revision_categoria"' in qml
    assert 'objectName: "filtros_revision_causa"' in qml
    assert 'readonly property var opciones_revision_tipo' in qml
    assert 'readonly property var opciones_revision_causa' in qml
    assert 'ActionButton { texto: "Limpiar"; tono: "neutral"; onClicked: raiz._limpiarFiltrosRevision() }' in revision_integrada
    assert 'ActionButton { texto: "Refrescar"; tono: "neutral"; onClicked: raiz.rev.cargar() }' in revision_integrada
    assert revision_integrada.index('objectName: "filtros_revision_categoria"') < revision_integrada.index('objectName: "filtros_revision_causa"') < revision_integrada.index("TextField {")
    assert "Qt.RightToLeft" not in filter_group
    assert 'Layout.alignment: Qt.AlignLeft | Qt.AlignTop' in filter_group
    assert "function _opcionesVisuales(opciones) {\n        return opciones\n    }" in qml
    assert "visible: raiz.imp.en_ejecucion" in execution_panel
    assert "Layout.preferredHeight: raiz.mediumWidth && raiz.es_pro ? 132 : 124" in execution_panel
    assert 'raiz.rev.set_filtros(' in qml
    assert 'raiz.rev.limpiar_filtros()' in qml
    assert 'Cuando inicies una ejecución aquí verás los detalles' in qml
    assert 'color: tono === "accent" ? (action.enabled ? raiz.tema.acento : raiz.tema.seleccion)' in qml
    assert 'color: tono === "accent" ? raiz.tema.textoSobreAcento : action.toneColor()' in qml


def test_status_badge_y_decision_panel_envuelven_textos_y_acciones():
    badge = Path("ui/qml/componentes/StatusBadge.qml").read_text(encoding="utf-8")
    decision = Path("ui/qml/componentes/DecisionPanel.qml").read_text(encoding="utf-8")

    assert "property int maxTextWidth" in badge
    assert "property bool compact" in badge
    assert "elide: Text.ElideRight" in badge
    assert "clip: true" in badge
    assert "Flow {" in decision
    assert "padding: UiTokens.spacing16" in decision
    assert "maxTextWidth: 96" in decision


def test_vista_importacion_resultados_usa_ejecucion_no_sesion():
    qml = Path("ui/qml/vistas/VistaImportacion.qml").read_text(encoding="utf-8")

    assert 'property int historial_seleccion_indice: 0' in qml
    assert 'function _ejecucionHistorialActiva()' in qml
    assert 'Mostrando ejecución #' in qml
    assert 'Resumen técnico' not in qml
    assert '_sesionHistorialActiva' not in qml
    assert '_reporteSesion' not in qml
    assert 'Sesión' not in qml
    assert 'sesion' not in qml


def test_decision_panel_no_incluye_preescucha_ni_acciones_falsas():
    qml = Path("ui/qml/componentes/DecisionPanel.qml").read_text(encoding="utf-8")

    assert "Preescuchar" not in qml
    assert "Resolver" not in qml
    assert "Aceptar" not in qml
    assert "Rechazar" not in qml
    assert "Reclasificar" not in qml
    assert "Marcar visto" in qml
    assert "Abrir ruta" in qml
    assert "Abrir carpeta" in qml
    assert "property var rev" in qml
    assert "revision." not in qml


def test_importacion_audio_deep_y_recovery_tienen_modelos_y_acciones():
    principal = Path("ui/qml/Principal.qml").read_text(encoding="utf-8")
    qml = Path("ui/qml/vistas/VistaImportacion.qml").read_text(encoding="utf-8")
    modelo = Path("ui/modelos_qml.py").read_text(encoding="utf-8")

    assert "readonly property var audioDeepModel: audioDeep" in principal
    assert "audioDeep: ventana_principal.audioDeepModel" in principal
    assert "required property var audioDeep" in qml
    assert 'objectName: "importacion_audio_deep_panel"' in qml
    for nombre in (
        "refrescarAudioDeepEstado",
        "pausarAudioDeepBackground",
        "reanudarAudioDeepBackground",
        "cancelarAudioDeepConservar",
        "cancelarAudioDeepDescartar",
        "reintentarAudioDeepFallidas",
    ):
        assert f"def {nombre}" in modelo
        assert f"raiz.audioDeep.{nombre}()" in qml

    assert 'objectName: "importacion_recovery_panel"' in qml
    for nombre in (
        "reintentarPortadasFaltantes",
        "reintentarImagenesArtistasFaltantes",
        "reintentarAssetsVisualesFaltantes",
        "reintentarEnrichmentFallido",
        "reintentarLyricsFaltantes",
        "reintentarAudioFeaturesFallidas",
    ):
        assert f"def {nombre}" in modelo
        assert f"raiz.imp.{nombre}()" in qml


def test_modelo_importacion_expone_resumen_historial_acumulado(db_tmp):
    con = get_conexion()
    con.execute(
        """
        INSERT INTO sesiones_import(
            directorio_entrada, estado, total_descubiertos,
            total_aceptados, total_revision, total_cuarentena, total_errores
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("/entrada/uno", "completado", 10, 4, 3, 2, 1),
    )
    con.execute(
        """
        INSERT INTO sesiones_import(
            directorio_entrada, estado, total_descubiertos,
            total_aceptados, total_revision, total_cuarentena, total_errores
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("/entrada/dos", "completado", 8, 5, 1, 0, 0),
    )

    modelo = ModeloImportacion()

    # `total_pendientes` refleja los pendientes VIVOS (tabla
    # pendientes_revision). Como el test inserta solo en sesiones_import
    # sin tocar pendientes_revision, total_pendientes=0. El acumulado
    # histórico sigue en total_pendientes_historicos.
    #
    # `total_duplicados` se deriva por diferencia: lo que el pipeline
    # descartó como duplicado (exacto/semántico/mejorable) no aparece en
    # aceptados/revisión/cuarentena/errores. Para la primera sesión:
    # 10 descubiertos - 4 aceptados - 3 revisión - 2 cuarentena - 1 error = 0.
    # Para la segunda: 8 - 5 - 1 - 0 - 0 = 2.
    assert modelo.resumen_historial == {
        "total_descubiertos": 18,
        "total_aceptados": 9,
        "total_revision": 4,
        "total_cuarentena": 2,
        "total_duplicados": 2,
        "total_errores": 1,
        "total_pendientes": 0,
        "total_pendientes_historicos": 6,
        "total_ejecuciones": 2,
    }


def test_modelo_revision_filtra_y_marcar_visto_actualiza_contadores(db_tmp):
    con = get_conexion()
    con.execute(
        """
        INSERT INTO archivos_pendientes(ruta_archivo, nombre_archivo, tipo, causa)
        VALUES (?, ?, ?, ?)
        """,
        ("/tmp/revision_a.mp3", "revision_a.mp3", "revision", "puntaje_bajo"),
    )
    con.execute(
        """
        INSERT INTO archivos_pendientes(ruta_archivo, nombre_archivo, tipo, causa)
        VALUES (?, ?, ?, ?)
        """,
        ("/tmp/cuarentena_b.mp3", "cuarentena_b.mp3", "cuarentena", "archivo_corrupto"),
    )

    modelo = ModeloRevision()
    modelo.cargar()

    assert modelo.total_revision == 1
    assert modelo.total_cuarentena == 1

    modelo.set_filtros("revision", "puntaje_bajo", "todas")
    assert modelo.revision.total == 1
    assert modelo.cuarentena.total == 0

    pendiente_id = modelo.revision.obtener(0)["id"]
    modelo.marcar_visto(pendiente_id)

    assert modelo.total_revision == 0
    assert modelo.revision.total == 0


def test_modelo_revision_abrir_rutas_invalidas_no_emite_excepcion(db_tmp, tmp_path, caplog):
    modelo = ModeloRevision()
    caplog.set_level("WARNING")

    assert modelo.abrir_archivo(str(tmp_path / "no_existe.mp3")) is False
    assert modelo.abrir_directorio(str(tmp_path / "no_existe.mp3")) is False
    assert "No se pudo abrir" in caplog.text
