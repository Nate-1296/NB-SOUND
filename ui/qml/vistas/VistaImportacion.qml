pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls

import "../componentes"
import "../componentes/UiUtils.js" as UiUtils

Rectangle {
    id: raiz
    objectName: "vista_importacion"
    color: raiz.tema.fondo

    property var shell: null
    required property var temaBase
    required property var cfg
    required property var imp
    required property var audioDeep
    required property var rev
    readonly property var tema: shell ? shell.tema : temaBase

    property bool importacion_completada: false
    property var ultimo_resumen: ({})
    property string ultimo_error: ""
    property string modo_ui: raiz.cfg.obtener("ui_mode") || "simple"
    property bool es_pro: modo_ui === "pro"
    property int seccion_activa: 0
    property int historial_seleccion_indice: 0
    property int historial_simple_expandido: -1
    property string filtro_revision_tipo: "todos"
    property string filtro_revision_causa: "todas"
    property string filtro_revision_texto: ""
    readonly property var opciones_revision_tipo: [
        {"id": "todos", "text": "Todos"},
        {"id": "revision", "text": "Revisión"},
        {"id": "cuarentena", "text": "Cuarentena"}
    ]
    readonly property var opciones_revision_causa: [
        {"id": "todas", "text": "Todas"},
        {"id": "puntaje_intermedio", "text": "Puntaje intermedio"},
        {"id": "puntaje_bajo", "text": "Puntaje bajo"},
        {"id": "candidatos_ambiguos", "text": "Candidatos ambiguos"},
        {"id": "sin_candidatos", "text": "Sin candidatos"},
        {"id": "metadata_insuficiente", "text": "Metadatos insuficientes"},
        {"id": "archivo_corrupto", "text": "Archivo corrupto"},
        {"id": "error_inesperado", "text": "Error inesperado"}
    ]

    readonly property int contentMaxWidth: 1240
    readonly property int horizontalPadding: raiz.width >= 1320 ? 44 : (raiz.width >= 860 ? 32 : UiTokens.spacing20)
    readonly property real availableContentWidth: Math.min(raiz.contentMaxWidth, Math.max(0, raiz.width - (raiz.horizontalPadding * 2)))
    readonly property bool compactWidth: raiz.availableContentWidth < 760
    readonly property bool mediumWidth: raiz.availableContentWidth >= 900
    readonly property bool wideWidth: raiz.availableContentWidth >= 1180

    Connections {
        target: raiz.cfg
        function onConfiguracionCambiada() {
            raiz.modo_ui = raiz.cfg.obtener("ui_mode") || "simple"
        }
    }

    function _resumenHistorial() {
        return raiz.imp.resumen_historial || {
            "total_aceptados": 0,
            "total_revision": 0,
            "total_cuarentena": 0,
            "total_duplicados": 0,
            "total_pendientes": 0,
            "total_ejecuciones": 0
        }
    }

    function _estadoTexto(estado, ejecutando) {
        if (estado === "error") return "Error"
        if (estado === "cancelando") return "Cancelando"
        if (estado === "cancelada") return "Cancelada"
        if (estado === "completada") return "Completada"
        if (ejecutando || estado === "en_ejecucion") return "En progreso"
        return "Lista"
    }

    function _estadoTono(estado, ejecutando) {
        if (estado === "error") return "danger"
        if (estado === "completada") return "success"
        if (estado === "cancelando" || estado === "cancelada") return "warning"
        if (ejecutando || estado === "en_ejecucion") return "info"
        return "neutral"
    }

    function _etapaTexto(etapa) {
        var e = (etapa || "").toLowerCase()
        if (e === "") return ""
        if (e === "iniciando") return "Inicializando pipeline"
        if (e === "aceptado") return "Archivo importado correctamente"
        if (e === "revision") return "Enviado a revisión manual"
        if (e === "cuarentena") return "Movido a cuarentena"
        if (e === "omitido") return "Archivo omitido por reglas"
        if (e === "error") return "Se produjo un error de procesamiento"
        if (e.indexOf("info:") === 0) return etapa.substring(5).trim()
        if (e.indexOf("warning:") === 0) return etapa.substring(8).trim()
        return etapa
    }

    function _etaTexto(segundos) {
        if (segundos < 0) return ""
        var totalSeg = Math.max(1, Math.round(segundos))
        if (totalSeg < 60) return totalSeg + " s"
        var min = Math.floor(totalSeg / 60)
        var seg = totalSeg % 60
        if (min < 60) return min + " min " + seg + " s"
        var hrs = Math.floor(min / 60)
        var remMin = min % 60
        return hrs + " h " + remMin + " min"
    }

    function _deepEstadoTexto(estado) {
        if (estado === "procesando") return "Procesando"
        if (estado === "pendiente") return "Pendiente"
        if (estado === "pausado") return "Pausado"
        if (estado === "completado") return "Completado"
        if (estado === "cancelado") return "Cancelado"
        if (estado === "error_parcial") return "Error parcial"
        if (estado === "sin_pendientes") return "Sin tareas"
        if (estado === "error") return "Error"
        return "Inactivo"
    }

    function _deepEstadoTono(estado) {
        if (estado === "procesando") return "info"
        if (estado === "pendiente" || estado === "pausado" || estado === "cancelado") return "warning"
        if (estado === "completado" || estado === "sin_pendientes") return "success"
        if (estado === "error" || estado === "error_parcial") return "danger"
        return "neutral"
    }

    function _mensajePrincipal() {
        if (raiz.imp.estado === "error") return "La importación se detuvo. Revisa el detalle del error para continuar."
        if (raiz.imp.estado === "cancelando") return "Cancelando la importación de forma segura."
        if (raiz.imp.estado === "cancelada") return "Importación cancelada por el usuario."
        if (raiz.imp.estado === "completada") return "Importación finalizada. Biblioteca, resultados y pendientes quedaron actualizados."
        if (raiz.imp.en_ejecucion && raiz.imp.progreso_indeterminado) return "Preparando archivos y estimando el volumen total."
        if (raiz.imp.en_ejecucion) return "Procesando archivos. El detalle de ejecución muestra etapa, ETA y archivo actual."
        return "Configura las rutas en Configuración e inicia una importación cuando estés listo."
    }

    function _cfgValor(clave, predeterminado) {
        var valor = raiz.cfg.obtener(clave)
        return valor === "" ? predeterminado : valor
    }

    function _ejecucionHistorialActiva() {
        if (!raiz.imp.historial || raiz.imp.historial.total <= 0) return null
        var idx = Math.max(0, Math.min(raiz.historial_seleccion_indice, raiz.imp.historial.total - 1))
        return raiz.imp.historial.obtener(idx)
    }

    function _pendientesEjecucion(ejecucion) {
        if (!ejecucion) return 0
        return (ejecucion.total_revision || 0) + (ejecucion.total_cuarentena || 0)
    }

    function _textoFinEjecucion(ejecucion) {
        if (!ejecucion) return ""
        if (ejecucion.finalizado_en && ejecucion.finalizado_en !== "") return "finalizada: " + UiUtils.formatearFechaLocal(ejecucion.finalizado_en)
        if (ejecucion.estado === "en_progreso") return "en progreso"
        return "sin cierre registrado"
    }

    function _contrastText(colorValue) {
        return UiUtils.contrasteSobre(colorValue)
    }

    function _historialListHeight(modoSimple) {
        var total = raiz.imp.historial ? raiz.imp.historial.total : 0
        if (total <= 0) return 154
        var collapsed = modoSimple ? 46 : 44
        var desired = (total * collapsed) + (Math.max(0, total - 1) * 6)
        if (modoSimple && raiz.historial_simple_expandido >= 0) desired += 94
        var minHeight = modoSimple ? 110 : 96
        var maxHeight = modoSimple ? (raiz.compactWidth ? 250 : 318) : 246
        return Math.min(maxHeight, Math.max(minHeight, desired))
    }

    function _opcionesVisuales(opciones) {
        return opciones
    }

    function _ajustesAvanzadosPipeline() {
        return {
            "shazam_timeout_seg": _cfgValor("shazam_timeout_seg", "12"),
            "shazam_min_duracion_seg": _cfgValor("shazam_min_duracion_seg", "20"),
            "ia_tiebreak_min_gap": _cfgValor("ia_tiebreak_min_gap", "0.12"),
            "ia_max_tokens": _cfgValor("ia_max_tokens", "512"),
            "ia_timeout_seg": _cfgValor("ia_timeout_seg", "20"),
            "skip_already_processed": _cfgValor("skip_already_processed", "0"),
            "init_component_max_retries": _cfgValor("init_component_max_retries", "2"),
            "init_component_retry_backoff_seg": _cfgValor("init_component_retry_backoff_seg", "0.7"),
            "enable_deduplication": _cfgValor("enable_deduplication", "1"),
            "enable_semantic_deduplication": _cfgValor("enable_semantic_deduplication", "1"),
            "duplicate_policy": _cfgValor("duplicate_policy", "replace_if_better"),
            "duplicate_better_min_delta": _cfgValor("duplicate_better_min_delta", "0.08"),
            "enable_assets_pipeline": _cfgValor("enable_assets_pipeline", "1"),
            "enable_cover_art_archive": _cfgValor("enable_cover_art_archive", "1"),
            "enable_theaudiodb_artist_images": _cfgValor("enable_theaudiodb_artist_images", "1"),
            "enable_itunes_cover_fallback": _cfgValor("enable_itunes_cover_fallback", "1"),
            "enable_deezer_artist_images": _cfgValor("enable_deezer_artist_images", "1"),
            "enable_wikipedia_artist_images": _cfgValor("enable_wikipedia_artist_images", "1"),
            "enable_itunes_artist_images": _cfgValor("enable_itunes_artist_images", "1"),
            "theaudiodb_api_key": _cfgValor("theaudiodb_api_key", "123"),
            "assets_timeout_seg": _cfgValor("assets_timeout_seg", "10"),
            "assets_max_retries": _cfgValor("assets_max_retries", "2"),
            "assets_retry_backoff_seg": _cfgValor("assets_retry_backoff_seg", "0.8"),
            "assets_cache_ttl_seg": _cfgValor("assets_cache_ttl_seg", "259200"),
            "assets_negative_cache_ttl_seg": _cfgValor("assets_negative_cache_ttl_seg", "21600"),
            "assets_min_resolution": _cfgValor("assets_min_resolution", "250"),
            "assets_hd_max_image_bytes": _cfgValor("assets_hd_max_image_bytes", "25000000"),
            "enable_external_enrichment": _cfgValor("enable_external_enrichment", "1"),
            "enable_lyrics_enrichment": _cfgValor("enable_lyrics_enrichment", "1"),
            "enable_lrclib": _cfgValor("enable_lrclib", "1"),
            "enable_lyrics_ovh": _cfgValor("enable_lyrics_ovh", "1"),
            "lyrics_timeout_seg": _cfgValor("lyrics_timeout_seg", "8"),
            "lyrics_max_retries": _cfgValor("lyrics_max_retries", "1"),
            "lyrics_retry_backoff_seg": _cfgValor("lyrics_retry_backoff_seg", "0.8"),
            "lyrics_suggest_limit": _cfgValor("lyrics_suggest_limit", "3"),
            "enable_second_stage_resolution": _cfgValor("enable_second_stage_resolution", "1"),
            "second_stage_max_candidates": _cfgValor("second_stage_max_candidates", "5"),
            "second_stage_min_evidence": _cfgValor("second_stage_min_evidence", "0.86"),
            "second_stage_min_gap": _cfgValor("second_stage_min_gap", "0.12"),
            "second_stage_cause_enabled": _cfgValor("second_stage_cause_enabled", "1"),
            "enable_third_stage_resolution": _cfgValor("enable_third_stage_resolution", "1"),
            "third_stage_min_evidence": _cfgValor("third_stage_min_evidence", "0.90"),
            "third_stage_min_gap": _cfgValor("third_stage_min_gap", "0.14"),
            "enable_ia_discography": _cfgValor("enable_ia_discography", "1"),
            "discography_ia_min_confidence": _cfgValor("discography_ia_min_confidence", "0.90"),
            "enable_overrides": _cfgValor("enable_overrides", "1"),
            "manifest_schema_version": _cfgValor("manifest_schema_version", "1"),
            "nb_sound_progress_mode": _cfgValor("nb_sound_progress_mode", "auto"),
            "nb_sound_progress_interval_sec": _cfgValor("nb_sound_progress_interval_sec", "2.0"),
            "sidecar_future_timeout_seg": _cfgValor("sidecar_future_timeout_seg", "90.0"),
            "sidecar_wait_heartbeat_seg": _cfgValor("sidecar_wait_heartbeat_seg", "2.0"),
            "enable_audio_features": _cfgValor("enable_audio_features", "1"),
            "audio_features_mode": _cfgValor("audio_features_mode", "light"),
            "audio_features_analyze_on_import": _cfgValor("audio_features_analyze_on_import", "1"),
            "audio_features_background": _cfgValor("audio_features_background", "1"),
            "audio_features_max_workers": _cfgValor("audio_features_max_workers", "1"),
            "audio_features_analyze_full_track": _cfgValor("audio_features_analyze_full_track", "0"),
            "audio_features_sample_strategy": _cfgValor("audio_features_sample_strategy", "smart_segments"),
            "audio_features_segment_seconds": _cfgValor("audio_features_segment_seconds", "90"),
            "audio_features_reanalyze_on_version_change": _cfgValor("audio_features_reanalyze_on_version_change", "1"),
            "audio_features_fail_silently": _cfgValor("audio_features_fail_silently", "1"),
            "enable_audio_intelligence_deep": _cfgValor("enable_audio_intelligence_deep", "0"),
            "audio_intelligence_backend": _cfgValor("audio_intelligence_backend", "none"),
            "enable_audio_mood_models": _cfgValor("enable_audio_mood_models", "0"),
            "enable_audio_embeddings": _cfgValor("enable_audio_embeddings", "0"),
            "enable_audio_tagging_models": _cfgValor("enable_audio_tagging_models", "0"),
            "audio_intelligence_analyze_after_import_background": _cfgValor("audio_intelligence_analyze_after_import_background", "1"),
            "audio_intelligence_resume_pending_on_startup": _cfgValor("audio_intelligence_resume_pending_on_startup", "1"),
            "audio_intelligence_background_autostart": _cfgValor("audio_intelligence_background_autostart", "1"),
            "audio_intelligence_background": _cfgValor("audio_intelligence_background", "1"),
            "audio_intelligence_max_workers": _cfgValor("audio_intelligence_max_workers", "1"),
            "audio_intelligence_background_batch_size": _cfgValor("audio_intelligence_background_batch_size", "1"),
            "audio_intelligence_background_idle_delay_sec": _cfgValor("audio_intelligence_background_idle_delay_sec", "2.0"),
            "audio_intelligence_background_max_runtime_min": _cfgValor("audio_intelligence_background_max_runtime_min", "0"),
            "audio_intelligence_model_dir": _cfgValor("audio_intelligence_model_dir", ""),
            "audio_intelligence_allow_model_downloads": _cfgValor("audio_intelligence_allow_model_downloads", "0"),
            "audio_intelligence_sample_strategy": _cfgValor("audio_intelligence_sample_strategy", "smart_segments"),
            "audio_intelligence_segment_seconds": _cfgValor("audio_intelligence_segment_seconds", "120"),
            "audio_intelligence_reanalyze_on_model_change": _cfgValor("audio_intelligence_reanalyze_on_model_change", "1"),
            "audio_intelligence_retry_failed": _cfgValor("audio_intelligence_retry_failed", "0"),
            "audio_intelligence_max_attempts": _cfgValor("audio_intelligence_max_attempts", "1"),
            "audio_intelligence_cancel_discard_outputs": _cfgValor("audio_intelligence_cancel_discard_outputs", "0"),
            "audio_intelligence_fail_silently": _cfgValor("audio_intelligence_fail_silently", "1"),
            "enable_music_discovery": _cfgValor("enable_music_discovery", "1"),
            "music_discovery_use_audio_features": _cfgValor("music_discovery_use_audio_features", "1"),
            "music_discovery_use_deep_features": _cfgValor("music_discovery_use_deep_features", "1"),
            "music_discovery_min_confidence": _cfgValor("music_discovery_min_confidence", "0.35"),
            "music_discovery_default_limit": _cfgValor("music_discovery_default_limit", "25"),
            "music_discovery_explain_results": _cfgValor("music_discovery_explain_results", "1")
        }
    }

    function _configImportacion(dryRun) {
        return {
            "entrada": raiz.cfg.obtener("dir_entrada"),
            "biblioteca": raiz.cfg.obtener("dir_biblioteca"),
            "revision": raiz.cfg.obtener("dir_revision"),
            "cuarentena": raiz.cfg.obtener("dir_cuarentena"),
            "logs": raiz.cfg.obtener("dir_logs"),
            "procesados": raiz.cfg.obtener("dir_procesados"),
            "cache": raiz.cfg.obtener("dir_cache"),
            "temp": raiz.cfg.obtener("dir_temp"),
            "dry_run": dryRun,
            "enable_shazam": raiz.cfg.obtener("enable_shazam") === "1",
            "enable_acoustid": raiz.cfg.obtener("enable_acoustid") === "1",
            "score_accept": parseFloat(raiz.cfg.obtener("score_accept") || "0.82"),
            "score_review": parseFloat(raiz.cfg.obtener("score_review") || "0.55"),
            "ia_proveedor": raiz.cfg.obtener("ia_proveedor"),
            "acoustid_key": raiz.cfg.obtener("acoustid_key"),
            "anthropic_key": raiz.cfg.obtener("anthropic_key"),
            "openai_key": raiz.cfg.obtener("openai_key"),
            "ajustes_avanzados": _ajustesAvanzadosPipeline()
        }
    }

    function iniciarImportacionSimple() {
        raiz.importacion_completada = false
        raiz.ultimo_error = ""
        raiz.imp.iniciar_importacion(_configImportacion(false))
    }

    function iniciarImportacionPro() {
        raiz.importacion_completada = false
        raiz.ultimo_error = ""
        raiz.imp.iniciar_importacion(_configImportacion(dry_run.checked))
    }

    function _aplicarFiltrosRevision() {
        raiz.rev.set_filtros(raiz.filtro_revision_texto, raiz.filtro_revision_causa, "todas")
    }

    function _limpiarFiltrosRevision() {
        raiz.filtro_revision_tipo = "todos"
        raiz.filtro_revision_causa = "todas"
        raiz.filtro_revision_texto = ""
        raiz.rev.limpiar_filtros()
    }

    ScrollView {
        id: scrollImport
        anchors.fill: parent
        contentWidth: availableWidth
        contentHeight: contenido.implicitHeight
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical: AppScrollBar {
            parent: scrollImport
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            z: 20
            tema: raiz.tema
            policy: scrollImport.contentHeight > scrollImport.height + 2 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
        }

        ColumnLayout {
            id: contenido
            width: raiz.width
            spacing: 0

            Item {
                Layout.fillWidth: true
                height: 88
                AppText {
                    anchors { left: parent.left; leftMargin: raiz.horizontalPadding; bottom: parent.bottom; bottomMargin: UiTokens.spacing16 }
                    text: "Importar"
                    font.pixelSize: 28
                    font.weight: Font.DemiBold
                    color: raiz.tema.texto
                }
            }

            AppCard {
                Layout.fillWidth: true
                Layout.leftMargin: raiz.horizontalPadding
                Layout.rightMargin: raiz.horizontalPadding
                Layout.maximumWidth: raiz.contentMaxWidth
                Layout.alignment: Qt.AlignHCenter
                tema: raiz.tema
                elevated: true

                GridLayout {
                    Layout.fillWidth: true
                    columns: raiz.compactWidth ? 1 : 2
                    columnSpacing: 12
                    rowSpacing: 8
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        spacing: UiTokens.spacing4
                        AppText {
                            text: "Resumen de Importación"
                            color: raiz.tema.texto
                            font.pixelSize: 20
                            font.weight: Font.DemiBold
                            Layout.fillWidth: true
                        }
                        AppText {
                            text: "Acumulado histórico de importaciones registradas. El desglose individual vive en el historial."
                            color: raiz.tema.textoMuted
                            font.pixelSize: UiTokens.fontSizeMd
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                    HeaderBadgeFlow {
                        preferredDesktopWidth: 250
                        StatusBadge { tema: raiz.tema; text: raiz.es_pro ? "Modo Pro" : "Modo Simple"; tone: raiz.es_pro ? "info" : "neutral"; maxTextWidth: 96; compact: true }
                        StatusBadge { tema: raiz.tema; text: raiz._estadoTexto(raiz.imp.estado, raiz.imp.en_ejecucion); tone: raiz._estadoTono(raiz.imp.estado, raiz.imp.en_ejecucion); maxTextWidth: 112; compact: true }
                    }
                }

                AppText {
                    text: raiz._mensajePrincipal()
                    color: raiz.tema.textoSec
                    font.pixelSize: UiTokens.fontSizeBase
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: raiz.wideWidth ? 6 : (raiz.mediumWidth ? 3 : (raiz.compactWidth ? 1 : 2))
                    rowSpacing: 10
                    columnSpacing: 10
                    StatSimple { Layout.fillWidth: true; etiqueta: "Aceptados"; valor: raiz._resumenHistorial().total_aceptados || 0; tono: "success" }
                    StatSimple { Layout.fillWidth: true; etiqueta: "Revisión"; valor: raiz._resumenHistorial().total_revision || 0; tono: "warning" }
                    StatSimple { Layout.fillWidth: true; etiqueta: "Cuarentena"; valor: raiz._resumenHistorial().total_cuarentena || 0; tono: "danger" }
                    StatSimple { Layout.fillWidth: true; etiqueta: "Pendientes"; valor: raiz._resumenHistorial().total_pendientes || 0; tono: "info" }
                    StatSimple { Layout.fillWidth: true; etiqueta: "Ejecuciones"; valor: raiz._resumenHistorial().total_ejecuciones || 0; tono: "neutral" }
                }
            }

            ColumnLayout {
                visible: !raiz.es_pro
                Layout.fillWidth: true
                Layout.leftMargin: raiz.horizontalPadding
                Layout.rightMargin: raiz.horizontalPadding
                Layout.maximumWidth: raiz.contentMaxWidth
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: UiTokens.spacing24
                spacing: UiTokens.spacing16

                AppCard {
                    Layout.fillWidth: true
                    tema: raiz.tema
                    SectionHeading {
                        titulo: "Flujo rápido"
                        descripcion: "Inicia con las rutas guardadas en Configuración. La carpeta de entrada se muestra en vivo y no se edita desde aquí."
                    }

                    RutaReadOnly { Layout.fillWidth: true }

                    Flow {
                        Layout.fillWidth: true
                        spacing: UiTokens.spacing10
                        ActionButton {
                            texto: raiz.imp.en_ejecucion ? "Importando..." : "Iniciar importación"
                            tono: "accent"
                            enabled: !raiz.imp.en_ejecucion && raiz.cfg.rutas_configuradas()
                            onClicked: raiz.iniciarImportacionSimple()
                        }
                        ActionButton {
                            visible: raiz.imp.en_ejecucion
                            texto: raiz.imp.estado === "cancelando" ? "Cancelando" : "Cancelar"
                            tono: "neutral"
                            enabled: raiz.imp.estado !== "cancelando"
                            onClicked: raiz.imp.cancelar_importacion()
                        }
                    }

                    AppText {
                        visible: !raiz.cfg.rutas_configuradas()
                        text: "Completa las rutas obligatorias en Configuración antes de importar."
                        color: raiz.tema.advertencia
                        font.pixelSize: UiTokens.fontSizeMd
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    AppText {
                        text: (raiz.ultimo_error || raiz.imp.ultimo_error) !== "" ? ("Error: " + (raiz.ultimo_error || raiz.imp.ultimo_error)) : ""
                        color: raiz.tema.peligro
                        visible: text !== ""
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }

                ExecutionStatusPanel {
                    Layout.fillWidth: true
                    tema: raiz.tema
                    titulo: "Detalle de ejecución"
                }

                DeepBackgroundPanel {
                    Layout.fillWidth: true
                    tema: raiz.tema
                }

                RecoveryPanel {
                    Layout.fillWidth: true
                    tema: raiz.tema
                }

                HistoryPanel {
                    Layout.fillWidth: true
                    modoSimple: true
                }
            }

            Rectangle {
                visible: raiz.es_pro
                Layout.leftMargin: raiz.horizontalPadding
                Layout.rightMargin: raiz.horizontalPadding
                Layout.topMargin: UiTokens.spacing24
                Layout.bottomMargin: UiTokens.spacing16
                Layout.maximumWidth: raiz.contentMaxWidth
                Layout.alignment: Qt.AlignHCenter
                Layout.fillWidth: true
                implicitHeight: 52
                radius: UiTokens.radiusLg
                color: raiz.tema.superficie
                border.color: raiz.tema.borde
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: UiTokens.spacing6
                    spacing: UiTokens.spacing6
                    SegmentTab { objectName: "import_tab_importar"; Layout.fillWidth: true; texto: "Importar"; activo: raiz.seccion_activa === 0; onClicked: raiz.seccion_activa = 0 }
                    SegmentTab { objectName: "import_tab_resultados"; Layout.fillWidth: true; texto: "Resultados"; activo: raiz.seccion_activa === 1; onClicked: raiz.seccion_activa = 1 }
                    SegmentTab { objectName: "import_tab_revisar"; Layout.fillWidth: true; texto: "Revisar"; activo: raiz.seccion_activa === 2; onClicked: raiz.seccion_activa = 2 }
                }
            }

            StackLayout {
                id: stackPro
                visible: raiz.es_pro
                Layout.fillWidth: true
                Layout.leftMargin: raiz.horizontalPadding
                Layout.rightMargin: raiz.horizontalPadding
                Layout.maximumWidth: raiz.contentMaxWidth
                Layout.alignment: Qt.AlignHCenter
                currentIndex: raiz.seccion_activa
                Layout.preferredHeight: currentIndex === 0 ? proImportar.implicitHeight : (currentIndex === 1 ? proResultados.implicitHeight : proRevisar.implicitHeight)

                ColumnLayout {
                    id: proImportar
                    Layout.fillWidth: true
                    spacing: UiTokens.spacing16

                    GridLayout {
                        Layout.fillWidth: true
                        columns: raiz.mediumWidth ? 2 : 1
                        columnSpacing: 14
                        rowSpacing: 14

                        AppCard {
                            id: configuracionOperativaCard
                            Layout.fillWidth: true
                            Layout.fillHeight: raiz.mediumWidth
                            Layout.minimumWidth: 0
                            Layout.preferredWidth: raiz.wideWidth ? 520 : -1
                            Layout.alignment: Qt.AlignTop
                            tema: raiz.tema
                            SectionHeading {
                                titulo: "Configuración operativa"
                                descripcion: "Usa las rutas y parámetros guardados. Aquí solo eliges si la ejecución escribe cambios o se simula."
                            }

                            RutaReadOnly { Layout.fillWidth: true }

                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: dryRunLayout.implicitHeight + 20
                                radius: UiTokens.radiusMd
                                color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.06)
                                border.color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.18)
                                border.width: 1

                                RowLayout {
                                    id: dryRunLayout
                                    anchors.fill: parent
                                    anchors.margins: UiTokens.spacing10
                                    spacing: UiTokens.spacing10
                                    Switch {
                                        id: dry_run
                                        checked: false
                                        enabled: !raiz.imp.en_ejecucion
                                        implicitWidth: 44
                                        implicitHeight: 24
                                        indicator: Rectangle {
                                            implicitWidth: 42
                                            implicitHeight: 22
                                            x: 0
                                            y: parent.height / 2 - height / 2
                                            radius: height / 2
                                            color: dry_run.checked ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, dry_run.enabled ? 0.95 : 0.25) : raiz.tema.superficieAlt
                                            border.color: dry_run.checked ? raiz.tema.acento : raiz.tema.borde
                                            border.width: 1
                                            Rectangle {
                                                width: 16
                                                height: 16
                                                radius: UiTokens.radiusSm
                                                x: dry_run.checked ? parent.width - width - 3 : 3
                                                y: 3
                                                color: dry_run.enabled ? raiz._contrastText(parent.color) : raiz.tema.textoMuted
                                                Behavior on x { NumberAnimation { duration: UiTokens.durationBase } }
                                            }
                                        }
                                        contentItem: Item {}
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 0
                                        spacing: 3
                                        AppText { text: "Dry-run"; color: raiz.tema.texto; font.weight: Font.DemiBold; font.pixelSize: UiTokens.fontSizeBase }
                                        AppText {
                                            text: "Dry-run prueba la importación sin aplicarla: no verás los cambios en la app, pero sí se guarda el caché y el análisis. Al desactivarla e iniciar la importación, se aplicará rápido porque el trabajo pesado ya estará hecho. Útil si no estás seguro de poder dejar el equipo encendido mucho tiempo."
                                            color: raiz.tema.textoMuted
                                            font.pixelSize: UiTokens.fontSizeSm
                                            wrapMode: Text.WordWrap
                                            Layout.fillWidth: true
                                        }
                                    }
                                }
                            }

                            Flow {
                                Layout.fillWidth: true
                                spacing: UiTokens.spacing10
                                ActionButton {
                                    texto: raiz.imp.en_ejecucion ? "Importando..." : "Iniciar importación"
                                    tono: "accent"
                                    enabled: !raiz.imp.en_ejecucion && raiz.cfg.rutas_configuradas()
                                    onClicked: raiz.iniciarImportacionPro()
                                }
                                ActionButton {
                                    visible: raiz.imp.en_ejecucion
                                    texto: raiz.imp.estado === "cancelando" ? "Cancelando" : "Cancelar"
                                    tono: "neutral"
                                    enabled: raiz.imp.estado !== "cancelando"
                                    onClicked: raiz.imp.cancelar_importacion()
                                }
                            }
                        }

                        ExecutionStatusPanel {
                            Layout.fillWidth: true
                            Layout.fillHeight: raiz.mediumWidth
                            Layout.minimumWidth: 0
                            Layout.preferredWidth: raiz.wideWidth ? 700 : -1
                            Layout.alignment: Qt.AlignTop
                            tema: raiz.tema
                            titulo: "Detalle de ejecución"
                        }
                    }

                    DeepBackgroundPanel {
                        Layout.fillWidth: true
                        tema: raiz.tema
                    }

                    RecoveryPanel {
                        Layout.fillWidth: true
                        tema: raiz.tema
                    }
                }

                ColumnLayout {
                    id: proResultados
                    Layout.fillWidth: true
                    spacing: UiTokens.spacing16

                    HistoryPanel {
                        Layout.fillWidth: true
                        modoSimple: false
                    }

                    AppCard {
                        id: detalle_ejecucion_card
                        Layout.fillWidth: true
                        tema: raiz.tema
                        property var ejecucionActiva: raiz._ejecucionHistorialActiva()

                        SectionHeading {
                            titulo: "Detalle de ejecución"
                            descripcion: detalle_ejecucion_card.ejecucionActiva
                                ? ("Mostrando ejecución #" + (detalle_ejecucion_card.ejecucionActiva.id || "-") + ".")
                                : "Selecciona una ejecución del historial para revisar su resultado."
                        }

                        GridLayout {
                            visible: !!detalle_ejecucion_card.ejecucionActiva
                            Layout.fillWidth: true
                            columns: raiz.mediumWidth ? 4 : (raiz.compactWidth ? 1 : 2)
                            rowSpacing: 10
                            columnSpacing: 10
                            StatSimple { Layout.fillWidth: true; etiqueta: "Descubiertos"; valor: (detalle_ejecucion_card.ejecucionActiva && detalle_ejecucion_card.ejecucionActiva.total_descubiertos) || 0; tono: "neutral" }
                            StatSimple { Layout.fillWidth: true; etiqueta: "Aceptados"; valor: (detalle_ejecucion_card.ejecucionActiva && detalle_ejecucion_card.ejecucionActiva.total_aceptados) || 0; tono: "success" }
                            StatSimple { Layout.fillWidth: true; etiqueta: "Revisión"; valor: (detalle_ejecucion_card.ejecucionActiva && detalle_ejecucion_card.ejecucionActiva.total_revision) || 0; tono: "warning" }
                            StatSimple { Layout.fillWidth: true; etiqueta: "Cuarentena"; valor: (detalle_ejecucion_card.ejecucionActiva && detalle_ejecucion_card.ejecucionActiva.total_cuarentena) || 0; tono: "danger" }
                        }

                        GridLayout {
                            visible: !!detalle_ejecucion_card.ejecucionActiva
                            Layout.fillWidth: true
                            columns: raiz.mediumWidth ? 2 : 1
                            columnSpacing: 12
                            rowSpacing: 8
                            DetailLine { etiqueta: "Estado"; valor: detalle_ejecucion_card.ejecucionActiva ? (detalle_ejecucion_card.ejecucionActiva.estado || "desconocido") : "" }
                            DetailLine { etiqueta: "Inicio"; valor: detalle_ejecucion_card.ejecucionActiva ? UiUtils.formatearFechaLocal(detalle_ejecucion_card.ejecucionActiva.iniciado_en, "-") : "" }
                            DetailLine { etiqueta: "Finalización"; valor: detalle_ejecucion_card.ejecucionActiva ? UiUtils.formatearFechaLocal(detalle_ejecucion_card.ejecucionActiva.finalizado_en, "en curso") : "" }
                            DetailLine { etiqueta: "Carpeta de entrada"; valor: detalle_ejecucion_card.ejecucionActiva ? (detalle_ejecucion_card.ejecucionActiva.directorio_entrada || "-") : "" }
                        }

                        EmptyState {
                            visible: !detalle_ejecucion_card.ejecucionActiva
                            Layout.fillWidth: true
                            tema: raiz.tema
                            title: "Sin ejecución seleccionada"
                            description: "El historial aparecerá aquí cuando exista al menos una importación registrada."
                            iconSource: "../assets/icons/lightbulb.svg"
                        }
                    }
                }

                ColumnLayout {
                    id: proRevisar
                    Layout.fillWidth: true
                    spacing: UiTokens.spacing16

                    AppCard {
                        Layout.fillWidth: true
                        tema: raiz.tema

                        GridLayout {
                            Layout.fillWidth: true
                            columns: raiz.compactWidth ? 1 : 2
                            columnSpacing: 12
                            rowSpacing: 10
                            ColumnLayout {
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                spacing: UiTokens.spacing4
                                AppText { text: "Revisión integrada"; color: raiz.tema.texto; font.pixelSize: 17; font.weight: Font.DemiBold }
                                AppText {
                                    text: "Filtra pendientes activos y retira de la lista los que ya viste. Esta pantalla no reetiqueta ni borra archivos."
                                    color: raiz.tema.textoMuted
                                    font.pixelSize: UiTokens.fontSizeMd
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }
                            HeaderBadgeFlow {
                                preferredDesktopWidth: 260
                                StatusBadge { tema: raiz.tema; text: "Revisión: " + raiz.rev.total_revision; tone: "warning"; maxTextWidth: 106; compact: true }
                                StatusBadge { tema: raiz.tema; text: "Cuarentena: " + raiz.rev.total_cuarentena; tone: "danger"; maxTextWidth: 122; compact: true }
                            }
                        }

                        FilterGroup {
                            objectName: "filtros_revision_categoria"
                            Layout.fillWidth: true
                            titulo: "Categoría"
                            opciones: raiz.opciones_revision_tipo
                            activoId: raiz.filtro_revision_tipo
                            onSelected: function(id) {
                                raiz.filtro_revision_tipo = id
                            }
                        }

                        FilterGroup {
                            objectName: "filtros_revision_causa"
                            Layout.fillWidth: true
                            titulo: "Causa"
                            opciones: raiz.opciones_revision_causa
                            activoId: raiz.filtro_revision_causa
                            onSelected: function(id) {
                                raiz.filtro_revision_causa = id
                                raiz._aplicarFiltrosRevision()
                            }
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 1
                            columnSpacing: 10
                            rowSpacing: 10

                            TextField {
                                id: filtro_revision_text_input
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                placeholderText: "Filtrar por archivo, ruta o causa"
                                placeholderTextColor: raiz.tema.textoMuted
                                text: raiz.filtro_revision_texto
                                selectByMouse: true
                                color: raiz.tema.texto
                                selectionColor: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.32)
                                selectedTextColor: raiz.tema.texto
                                onTextChanged: {
                                    raiz.filtro_revision_texto = text
                                    raiz._aplicarFiltrosRevision()
                                }
                                background: Rectangle {
                                    radius: UiTokens.radiusSm
                                    color: raiz.tema.superficieAlt
                                    border.color: filtro_revision_text_input.activeFocus ? raiz.tema.acento : raiz.tema.borde
                                    border.width: filtro_revision_text_input.activeFocus ? 1.5 : 1
                                }
                            }
                        }

                        Flow {
                            Layout.fillWidth: true
                            Layout.alignment: raiz.compactWidth ? Qt.AlignLeft : Qt.AlignRight
                            spacing: UiTokens.spacing10
                            ActionButton { texto: "Limpiar"; tono: "neutral"; onClicked: raiz._limpiarFiltrosRevision() }
                            ActionButton { texto: "Refrescar"; tono: "neutral"; onClicked: raiz.rev.cargar() }
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: raiz.wideWidth && raiz.filtro_revision_tipo === "todos" ? 2 : 1
                        columnSpacing: 14
                        rowSpacing: 14

                        PendingListCard {
                            visible: raiz.filtro_revision_tipo === "todos" || raiz.filtro_revision_tipo === "revision"
                            Layout.fillWidth: true
                            sectionLabel: "Revisión"
                            tone: "warning"
                            modelRef: raiz.rev.revision
                            emptyTitle: "Sin pendientes de revisión"
                            emptyDescription: "Los archivos con confianza media aparecerán aquí."
                        }
                        PendingListCard {
                            visible: raiz.filtro_revision_tipo === "todos" || raiz.filtro_revision_tipo === "cuarentena"
                            Layout.fillWidth: true
                            sectionLabel: "Cuarentena"
                            tone: "danger"
                            modelRef: raiz.rev.cuarentena
                            emptyTitle: "Sin elementos en cuarentena"
                            emptyDescription: "Los archivos críticos aparecerán aquí para intervención manual."
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true; height: UiTokens.spacing24 }
        }
    }

    Connections {
        target: raiz.imp
        function onImportacionFin(resumen) {
            raiz.ultimo_resumen = resumen
            raiz.importacion_completada = true
            raiz.ultimo_error = ""
            raiz.rev.cargar()
            if (raiz.es_pro) raiz.seccion_activa = 1
        }
        function onImportacionError(mensaje) {
            raiz.ultimo_error = mensaje
            raiz.importacion_completada = false
            if (raiz.es_pro) raiz.seccion_activa = 0
        }
        function onImportacionCancelada(resumen) {
            raiz.ultimo_resumen = resumen
            raiz.importacion_completada = false
            raiz.ultimo_error = ""
            raiz.rev.cargar()
            if (raiz.es_pro) raiz.seccion_activa = 1
        }
        function onHistorialCambiado() {
            if (raiz.historial_seleccion_indice >= raiz.imp.historial.total) raiz.historial_seleccion_indice = 0
            if (raiz.historial_simple_expandido >= raiz.imp.historial.total) raiz.historial_simple_expandido = -1
        }
    }

    Component.onCompleted: {
        raiz.imp.cargar_historial()
        raiz.rev.cargar()
        raiz.imp.refrescarDiagnosticoImportacion()
        raiz.audioDeep.refrescarAudioDeepEstado()
    }

    onVisibleChanged: {
        if (!visible) return
        // Reconcilia el estado de "Diagnóstico y reintentos": si un reintento
        // quedó marcado como en curso pero su worker ya terminó (la señal de fin
        // puede perderse al cambiar de vista), limpia el estado fantasma para
        // que el refresco siguiente refleje el estado real.
        raiz.imp.reconciliarDiagnostico()
        raiz.imp.refrescarDiagnosticoImportacion()
        raiz.audioDeep.refrescarAudioDeepEstado()
    }

    component SectionHeading: ColumnLayout {
        property string titulo: ""
        property string descripcion: ""
        Layout.fillWidth: true
        spacing: UiTokens.spacing4
        AppText { text: titulo; color: raiz.tema.texto; font.pixelSize: UiTokens.fontSizeLg; font.weight: Font.DemiBold; Layout.fillWidth: true }
        AppText {
            text: descripcion
            visible: descripcion !== ""
            color: raiz.tema.textoMuted
            font.pixelSize: UiTokens.fontSizeMd
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    component SegmentTab: Rectangle {
        id: tabBtn
        property string texto: ""
        property bool activo: false
        signal clicked()
        implicitHeight: 38
        radius: UiTokens.radiusMd
        color: activo ? raiz.tema.seleccion : (tabMouse.containsMouse ? Qt.rgba(raiz.tema.hover.r, raiz.tema.hover.g, raiz.tema.hover.b, 0.6) : "transparent")
        border.color: activo ? raiz.tema.acento : "transparent"
        border.width: 1
        AppText {
            anchors.centerIn: parent
            width: parent.width - 18
            text: tabBtn.texto
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
            font.pixelSize: UiTokens.fontSizeBase
            font.weight: tabBtn.activo ? Font.DemiBold : Font.Normal
            color: tabBtn.activo ? raiz.tema.texto : raiz.tema.textoSec
        }
        MouseArea { id: tabMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: tabBtn.clicked() }
    }

    component FilterPill: Rectangle {
        id: pill
        property string texto: ""
        property bool activo: false
        signal clicked()
        width: Math.min(Math.max(92, pillLabel.implicitWidth + 24), raiz.compactWidth ? 170 : 210)
        height: 34
        radius: 17
        clip: true
        color: activo ? raiz.tema.seleccion : "transparent"
        border.color: activo ? raiz.tema.acento : raiz.tema.borde
        border.width: 1
        AppText {
            id: pillLabel
            anchors.centerIn: parent
            width: Math.max(0, parent.width - 20)
            text: pill.texto
            color: pill.activo ? raiz.tema.texto : raiz.tema.textoSec
            font.pixelSize: UiTokens.fontSizeMd
            font.weight: pill.activo ? Font.DemiBold : Font.Normal
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }
        MouseArea { anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: pill.clicked() }
    }

    component FilterGroup: GridLayout {
        id: filterGroup
        property string titulo: ""
        property var opciones: []
        property string activoId: ""
        signal selected(string id)

        columns: raiz.compactWidth ? 1 : 2
        columnSpacing: 12
        rowSpacing: 6

        AppText {
            text: filterGroup.titulo
            color: raiz.tema.textoMuted
            font.pixelSize: UiTokens.fontSizeSm
            font.weight: Font.DemiBold
            Layout.fillWidth: raiz.compactWidth
            Layout.preferredWidth: raiz.compactWidth ? -1 : 96
            Layout.alignment: Qt.AlignLeft | Qt.AlignTop
        }

        Flow {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.alignment: Qt.AlignLeft | Qt.AlignTop
            spacing: UiTokens.spacing8

            Repeater {
                model: raiz._opcionesVisuales(filterGroup.opciones)
                delegate: FilterPill {
                    required property var modelData
                    texto: modelData.text
                    activo: filterGroup.activoId === modelData.id
                    onClicked: filterGroup.selected(modelData.id)
                }
            }
        }
    }

    component HeaderBadgeFlow: Flow {
        property int preferredDesktopWidth: 240
        Layout.fillWidth: raiz.compactWidth
        Layout.preferredWidth: raiz.compactWidth ? -1 : preferredDesktopWidth
        Layout.minimumWidth: 0
        Layout.alignment: raiz.compactWidth ? Qt.AlignLeft : (Qt.AlignRight | Qt.AlignTop)
        spacing: UiTokens.spacing6
    }

    component ActionButton: Rectangle {
        id: action
        property string texto: ""
        property string tono: "neutral"
        signal clicked()

        function toneColor() {
            if (tono === "accent") return raiz.tema.acento
            if (tono === "success") return raiz.tema.exito
            if (tono === "danger") return raiz.tema.peligro
            if (tono === "warning") return raiz.tema.advertencia
            return raiz.tema.textoMuted
        }

        implicitWidth: Math.min(Math.max(96, actionLabel.implicitWidth + 24), raiz.compactWidth ? 178 : 220)
        implicitHeight: 36
        width: implicitWidth
        height: implicitHeight
        radius: 18
        clip: true
        opacity: enabled ? 1.0 : 0.55
        color: tono === "accent" ? (action.enabled ? raiz.tema.acento : raiz.tema.seleccion) : Qt.rgba(toneColor().r, toneColor().g, toneColor().b, actionMouse.containsMouse && action.enabled ? 0.20 : 0.12)
        border.color: tono === "accent" ? "transparent" : toneColor()
        border.width: tono === "accent" ? 0 : 1

        AppText {
            id: actionLabel
            anchors.centerIn: parent
            width: Math.max(0, parent.width - 22)
            text: action.texto
            color: tono === "accent" ? raiz.tema.textoSobreAcento : action.toneColor()
            font.pixelSize: UiTokens.fontSizeMd
            font.weight: Font.DemiBold
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }
        MouseArea {
            id: actionMouse
            anchors.fill: parent
            hoverEnabled: true
            enabled: action.enabled
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: action.clicked()
        }
    }

    component RutaReadOnly: Rectangle {
        id: rutaBox
        objectName: "importacion_ruta_entrada_readonly"
        radius: UiTokens.radiusMd
        color: raiz.tema.fondoElevado
        border.color: raiz.tema.borde
        border.width: 1
        implicitHeight: rutaLayout.implicitHeight + 20

        ColumnLayout {
            id: rutaLayout
            anchors.fill: parent
            anchors.margins: UiTokens.spacing10
            spacing: UiTokens.spacing6
            AppText { text: "Carpeta de entrada"; color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm; font.weight: Font.DemiBold }
            Rectangle {
                id: entrada_importacion_readonly
                objectName: "entrada_importacion_readonly"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                implicitHeight: 30
                radius: UiTokens.radiusSm
                color: raiz.tema.superficieAlt
                border.color: Qt.rgba(raiz.tema.borde.r, raiz.tema.borde.g, raiz.tema.borde.b, 0.6)
                border.width: 1
                clip: true

                AppText {
                    anchors.fill: parent
                    anchors.leftMargin: UiTokens.spacing10
                    anchors.rightMargin: UiTokens.spacing10
                    verticalAlignment: Text.AlignVCenter
                    text: raiz.cfg.obtener("dir_entrada") || "Configura dir_entrada en Configuración"
                    color: raiz.cfg.obtener("dir_entrada") ? raiz.tema.texto : raiz.tema.textoMuted
                    font.pixelSize: UiTokens.fontSizeMd
                    elide: Text.ElideMiddle
                }
            }
        }
    }

    component ExecutionStatusPanel: AppCard {
        id: execPanel
        property string titulo: "Detalle de ejecución"
        tema: raiz.tema

        GridLayout {
            Layout.fillWidth: true
            columns: raiz.compactWidth ? 1 : 2
            columnSpacing: 10
            rowSpacing: 6
            AppText {
                text: execPanel.titulo
                font.pixelSize: 17
                font.weight: Font.DemiBold
                color: raiz.tema.texto
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                elide: Text.ElideRight
            }
            HeaderBadgeFlow {
                visible: raiz.imp.en_ejecucion
                preferredDesktopWidth: 128
                StatusBadge {
                    tema: raiz.tema
                    text: raiz._estadoTexto(raiz.imp.estado, raiz.imp.en_ejecucion)
                    tone: raiz._estadoTono(raiz.imp.estado, raiz.imp.en_ejecucion)
                    maxTextWidth: 112
                    compact: true
                }
            }
        }

        Item {
            visible: !raiz.imp.en_ejecucion
            Layout.fillWidth: true
            Layout.fillHeight: raiz.mediumWidth && raiz.es_pro
            Layout.preferredHeight: raiz.mediumWidth && raiz.es_pro ? 132 : 124
            EmptyState {
                anchors.centerIn: parent
                width: Math.min(parent.width, 460)
                tema: raiz.tema
                title: "Sin ejecución activa"
                description: "Cuando inicies una ejecución aquí verás los detalles"
                iconSource: "../assets/icons/lightbulb.svg"
            }
        }

        ColumnLayout {
            visible: raiz.imp.en_ejecucion
            Layout.fillWidth: true
            spacing: UiTokens.spacing10

            Rectangle {
                id: barraBase
                Layout.fillWidth: true
                height: 8
                radius: 4
                color: raiz.tema.superficieAlt
                clip: true
                Rectangle {
                    visible: !raiz.imp.progreso_indeterminado
                    width: parent.width * Math.max(0, Math.min(1, raiz.imp.porcentaje))
                    height: parent.height
                    radius: 4
                    color: raiz.tema.acento
                    Behavior on width { NumberAnimation { duration: 220 } }
                }
                Rectangle {
                    id: barraIndeterminada
                    visible: raiz.imp.progreso_indeterminado
                    width: parent.width * 0.28
                    height: parent.height
                    radius: 4
                    color: raiz.tema.acento
                    x: -width
                    SequentialAnimation on x {
                        running: raiz.imp.progreso_indeterminado
                        loops: Animation.Infinite
                        NumberAnimation { from: -barraIndeterminada.width; to: barraBase.width; duration: 1100; easing.type: Easing.InOutQuad }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                AppText {
                    text: raiz.imp.progreso_indeterminado ? "Preparando volumen de archivos" : (raiz.imp.procesados + " de " + raiz.imp.total + " archivos")
                    color: raiz.tema.textoSec
                    font.pixelSize: UiTokens.fontSizeMd
                    Layout.fillWidth: true
                }
                AppText {
                    text: !raiz.imp.progreso_indeterminado && raiz.imp.total > 0 ? (Math.round(Math.max(0, Math.min(1, raiz.imp.porcentaje)) * 100) + "%") : ""
                    color: raiz.tema.textoSec
                    font.pixelSize: UiTokens.fontSizeMd
                }
            }

            AppText { text: raiz.imp.nombre_actual || "Preparando ejecución"; color: raiz.tema.textoSec; font.pixelSize: UiTokens.fontSizeMd; elide: Text.ElideMiddle; Layout.fillWidth: true }
            AppText {
                text: raiz.imp.etapa_actual !== "" ? ("Etapa: " + raiz._etapaTexto(raiz.imp.etapa_actual)) : "Etapa: inicializando"
                color: raiz.tema.textoMuted
                font.pixelSize: UiTokens.fontSizeSm
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            AppText {
                text: raiz._etaTexto(raiz.imp.eta_seg) !== "" ? ("ETA aprox: " + raiz._etaTexto(raiz.imp.eta_seg)) : "ETA aprox: calculando"
                color: raiz.tema.textoMuted
                font.pixelSize: UiTokens.fontSizeSm
            }
        }
    }

    component DeepBackgroundPanel: AppCard {
        id: deepPanel
        objectName: "importacion_audio_deep_panel"
        tema: raiz.tema
        // Fase 3: el análisis profundo (Essentia/TF) no existe en Windows.
        // Ocultamos el panel completo (estado, progreso y controles deep).
        // En QtQuick.Layouts un item invisible no ocupa espacio.
        visible: deepAnalyticsDisponible

        readonly property string estadoDeep: raiz.audioDeep.audioDeepEstado || "inactivo"
        readonly property bool hayPendientes: raiz.audioDeep.audioDeepPendientes > 0
        readonly property bool puedeEjecutar: !raiz.audioDeep.audioDeepProcesando && raiz.audioDeep.audioDeepWarning === "" && (hayPendientes || estadoDeep === "cancelado" || estadoDeep === "sin_pendientes" || estadoDeep === "completado" || estadoDeep === "error_parcial")
        readonly property bool puedeCancelar: raiz.audioDeep.audioDeepProcesando || raiz.audioDeep.audioDeepPausado || estadoDeep === "pendiente"

        GridLayout {
            Layout.fillWidth: true
            columns: raiz.compactWidth ? 1 : 2
            columnSpacing: 10
            rowSpacing: 8

            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: UiTokens.spacing4
                AppText {
                    text: "Análisis musical en segundo plano"
                    color: raiz.tema.texto
                    font.pixelSize: 17
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                AppText {
                    text: raiz.audioDeep.audioDeepWarning !== ""
                        ? raiz.audioDeep.audioDeepWarning
                        : (raiz.audioDeep.audioDeepMensaje !== "" ? raiz.audioDeep.audioDeepMensaje : "Etapa actual: audio_intelligence_deep")
                    color: raiz.audioDeep.audioDeepWarning !== "" ? raiz.tema.advertencia : raiz.tema.textoMuted
                    font.pixelSize: UiTokens.fontSizeMd
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }

            HeaderBadgeFlow {
                preferredDesktopWidth: 300
                StatusBadge {
                    tema: raiz.tema
                    text: raiz._deepEstadoTexto(deepPanel.estadoDeep)
                    tone: raiz._deepEstadoTono(deepPanel.estadoDeep)
                    maxTextWidth: 126
                    compact: true
                }
                StatusBadge {
                    tema: raiz.tema
                    text: "deep_ready " + raiz.audioDeep.audioDeepReadyBiblioteca
                    tone: "info"
                    maxTextWidth: 132
                    compact: true
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            height: 8
            radius: 4
            color: raiz.tema.superficieAlt
            clip: true
            Rectangle {
                width: parent.width * Math.max(0, Math.min(1, raiz.audioDeep.audioDeepPorcentaje))
                height: parent.height
                radius: 4
                color: raiz.tema.acento
                Behavior on width { NumberAnimation { duration: 220 } }
            }
        }

        GridLayout {
            Layout.fillWidth: true
            columns: raiz.wideWidth ? 6 : (raiz.mediumWidth ? 3 : (raiz.compactWidth ? 1 : 2))
            rowSpacing: 8
            columnSpacing: 8
            StatSimple { Layout.fillWidth: true; etiqueta: "Procesadas"; valor: raiz.audioDeep.audioDeepProcesadas + "/" + raiz.audioDeep.audioDeepTotal; tono: "neutral" }
            StatSimple { Layout.fillWidth: true; etiqueta: "Ready"; valor: raiz.audioDeep.audioDeepReady; tono: "success" }
            StatSimple { Layout.fillWidth: true; etiqueta: "Fallidas"; valor: raiz.audioDeep.audioDeepFailed; tono: raiz.audioDeep.audioDeepFailed > 0 ? "danger" : "neutral" }
            StatSimple { Layout.fillWidth: true; etiqueta: "Skipped"; valor: raiz.audioDeep.audioDeepSkipped; tono: "warning" }
            StatSimple { Layout.fillWidth: true; etiqueta: "Pendientes"; valor: raiz.audioDeep.audioDeepPendientes; tono: raiz.audioDeep.audioDeepPendientes > 0 ? "info" : "neutral" }
            StatSimple { Layout.fillWidth: true; etiqueta: "Velocidad"; valor: Number(raiz.audioDeep.audioDeepVelocidad || 0).toFixed(1) + "/min"; tono: "neutral" }
        }

        GridLayout {
            Layout.fillWidth: true
            columns: raiz.compactWidth ? 1 : 2
            columnSpacing: 12
            rowSpacing: 8
            DetailLine {
                etiqueta: "Pista actual"
                valor: raiz.audioDeep.audioDeepPistaActual !== "" ? raiz.audioDeep.audioDeepPistaActual : "sin pista activa"
            }
            DetailLine {
                etiqueta: "ETA"
                valor: raiz.audioDeep.audioDeepETA !== "" ? raiz.audioDeep.audioDeepETA : "desconocido"
            }
        }

        Flow {
            Layout.fillWidth: true
            spacing: UiTokens.spacing10
            ActionButton {
                objectName: "deep_background_start_button"
                visible: deepPanel.puedeEjecutar
                texto: deepPanel.hayPendientes ? "Ejecutar ahora" : "Buscar pendientes"
                tono: "accent"
                onClicked: raiz.audioDeep.iniciarAudioDeepBackground()
            }
            ActionButton {
                objectName: "deep_background_pause_button"
                visible: raiz.audioDeep.audioDeepProcesando
                texto: "Pausar"
                tono: "neutral"
                onClicked: raiz.audioDeep.pausarAudioDeepBackground()
            }
            ActionButton {
                objectName: "deep_background_resume_button"
                visible: raiz.audioDeep.audioDeepPausado || deepPanel.estadoDeep === "pendiente"
                texto: "Reanudar"
                tono: "accent"
                onClicked: raiz.audioDeep.reanudarAudioDeepBackground()
            }
            ActionButton {
                objectName: "deep_background_cancel_keep_button"
                visible: deepPanel.puedeCancelar
                texto: "Cancelar conservar"
                tono: "warning"
                onClicked: raiz.audioDeep.cancelarAudioDeepConservar()
            }
            ActionButton {
                objectName: "deep_background_cancel_discard_button"
                visible: deepPanel.puedeCancelar
                texto: "Cancelar descartar"
                tono: "danger"
                onClicked: raiz.audioDeep.cancelarAudioDeepDescartar()
            }
            ActionButton {
                objectName: "deep_background_retry_failed_button"
                visible: !raiz.audioDeep.audioDeepProcesando && raiz.audioDeep.audioDeepFailed > 0
                texto: "Reintentar fallidas"
                tono: "neutral"
                onClicked: raiz.audioDeep.reintentarAudioDeepFallidas()
            }
            ActionButton {
                objectName: "deep_background_refresh_button"
                texto: "Refrescar"
                tono: "neutral"
                onClicked: raiz.audioDeep.refrescarAudioDeepEstado()
            }
        }
    }

    component RecoveryPanel: AppCard {
        id: recoveryPanel
        objectName: "importacion_recovery_panel"
        tema: raiz.tema

        readonly property var diag: raiz.imp.diagnosticoPostImport || ({})
        readonly property int totalPortadas: Number(diag.missing_track_covers || 0) + Number(diag.missing_album_covers || 0)
        readonly property int totalFeatures: Number(diag.audio_features_missing || 0) + Number(diag.audio_features_failed || 0)
        readonly property int totalSidecars: Number(diag.missing_visual_assets || 0) + Number(diag.missing_enrichment || 0)

        GridLayout {
            Layout.fillWidth: true
            columns: raiz.compactWidth ? 1 : 2
            columnSpacing: 10
            rowSpacing: 8

            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: UiTokens.spacing4
                AppText {
                    text: "Diagnóstico y reintentos"
                    color: raiz.tema.texto
                    font.pixelSize: 17
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                AppText {
                    text: raiz.imp.diagnosticoEjecutando
                          ? raiz.imp.diagnosticoMensaje
                          : (recoveryPanel.diag.warning || raiz.imp.diagnosticoMensaje || "Estado post-importación listo para revisar.")
                    color: recoveryPanel.diag.warning ? raiz.tema.advertencia : raiz.tema.textoMuted
                    font.pixelSize: UiTokens.fontSizeMd
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }

            HeaderBadgeFlow {
                preferredDesktopWidth: 280
                StatusBadge {
                    tema: raiz.tema
                    text: "pistas " + Number(recoveryPanel.diag.total_tracks || 0)
                    tone: "info"
                    maxTextWidth: 100
                    compact: true
                }
                StatusBadge {
                    tema: raiz.tema
                    text: recoveryPanel.totalSidecars > 0 ? ("retry " + recoveryPanel.totalSidecars) : "sin faltantes"
                    tone: recoveryPanel.totalSidecars > 0 ? "warning" : "success"
                    maxTextWidth: 118
                    compact: true
                }
            }
        }

        GridLayout {
            Layout.fillWidth: true
            columns: raiz.wideWidth ? 6 : (raiz.mediumWidth ? 3 : (raiz.compactWidth ? 1 : 2))
            rowSpacing: 8
            columnSpacing: 8
            StatSimple { Layout.fillWidth: true; etiqueta: "Portadas"; valor: recoveryPanel.totalPortadas; tono: recoveryPanel.totalPortadas > 0 ? "warning" : "success" }
            StatSimple { Layout.fillWidth: true; etiqueta: "Artistas"; valor: Number(recoveryPanel.diag.missing_artist_images || 0); tono: Number(recoveryPanel.diag.missing_artist_images || 0) > 0 ? "warning" : "success" }
            StatSimple { Layout.fillWidth: true; etiqueta: "Assets"; valor: Number(recoveryPanel.diag.missing_visual_assets || 0); tono: Number(recoveryPanel.diag.missing_visual_assets || 0) > 0 ? "warning" : "success" }
            StatSimple { Layout.fillWidth: true; etiqueta: "Lyrics"; valor: Number(recoveryPanel.diag.missing_lyrics || 0); tono: Number(recoveryPanel.diag.missing_lyrics || 0) > 0 ? "warning" : "success" }
            StatSimple { Layout.fillWidth: true; etiqueta: "Features"; valor: recoveryPanel.totalFeatures; tono: recoveryPanel.totalFeatures > 0 ? "warning" : "success" }
            StatSimple { Layout.fillWidth: true; etiqueta: "Deep failed"; valor: Number(recoveryPanel.diag.deep_failed || 0); tono: Number(recoveryPanel.diag.deep_failed || 0) > 0 ? "danger" : "neutral" }
        }

        Flow {
            Layout.fillWidth: true
            spacing: UiTokens.spacing10
            ActionButton {
                objectName: "recovery_refresh_button"
                texto: "Refrescar"
                tono: "neutral"
                // Nunca se desactiva: además de refrescar, sirve para detectar
                // y reconciliar el estado real de un reintento en curso (si su
                // señal de fin se perdió al cambiar de vista). El propio modelo
                // evita lanzar dos reintentos concurrentes.
                onClicked: raiz.imp.refrescarDiagnosticoImportacion()
            }
            ActionButton {
                objectName: "recovery_retry_covers_button"
                visible: recoveryPanel.totalPortadas > 0
                texto: "Reintentar portadas"
                tono: "neutral"
                enabled: !raiz.imp.diagnosticoEjecutando
                onClicked: raiz.imp.reintentarPortadasFaltantes()
            }
            ActionButton {
                objectName: "recovery_retry_artist_images_button"
                visible: Number(recoveryPanel.diag.missing_artist_images || 0) > 0
                texto: "Reintentar artistas"
                tono: "neutral"
                enabled: !raiz.imp.diagnosticoEjecutando
                onClicked: raiz.imp.reintentarImagenesArtistasFaltantes()
            }
            ActionButton {
                objectName: "recovery_retry_visual_assets_button"
                visible: Number(recoveryPanel.diag.missing_visual_assets || 0) > 0
                texto: "Reintentar assets"
                tono: "neutral"
                enabled: !raiz.imp.diagnosticoEjecutando
                onClicked: raiz.imp.reintentarAssetsVisualesFaltantes()
            }
            ActionButton {
                objectName: "recovery_retry_enrichment_button"
                visible: Number(recoveryPanel.diag.missing_enrichment || 0) > 0
                texto: "Reintentar sidecars"
                tono: "neutral"
                enabled: !raiz.imp.diagnosticoEjecutando
                onClicked: raiz.imp.reintentarEnrichmentFallido()
            }
            ActionButton {
                objectName: "recovery_retry_lyrics_button"
                visible: Number(recoveryPanel.diag.missing_lyrics || 0) > 0
                texto: "Reintentar lyrics"
                tono: "neutral"
                enabled: !raiz.imp.diagnosticoEjecutando
                onClicked: raiz.imp.reintentarLyricsFaltantes()
            }
            ActionButton {
                objectName: "recovery_retry_audio_features_button"
                visible: recoveryPanel.totalFeatures > 0
                texto: "Reintentar features"
                tono: "neutral"
                enabled: !raiz.imp.diagnosticoEjecutando
                onClicked: raiz.imp.reintentarAudioFeaturesFallidas()
            }
            ActionButton {
                objectName: "recovery_retry_deep_failed_button"
                // Fase 3: oculto siempre en plataformas sin deep (Windows).
                visible: deepAnalyticsDisponible && Number(recoveryPanel.diag.deep_failed || 0) > 0
                texto: "Reintentar deep"
                tono: "neutral"
                enabled: !raiz.imp.diagnosticoEjecutando
                onClicked: raiz.imp.reintentarDeepFallidas()
            }
            ActionButton {
                objectName: "recovery_retry_all_sidecars_button"
                visible: recoveryPanel.totalSidecars > 0
                texto: "Reintentar visual+sidecars"
                tono: "accent"
                enabled: !raiz.imp.diagnosticoEjecutando
                onClicked: raiz.imp.reintentarSidecarsFallidos()
            }
        }
    }

    component HistoryPanel: AppCard {
        id: histPanel
        property bool modoSimple: true
        tema: raiz.tema

        SectionHeading {
            titulo: modoSimple ? "Resumen de ejecuciones" : "Historial de ejecuciones"
            descripcion: modoSimple
                ? "Expande una ejecución a la vez para ver su resumen individual."
                : "Selecciona una ejecución para ver su detalle debajo."
        }

        ListView {
            id: historialList
            Layout.fillWidth: true
            Layout.preferredHeight: raiz._historialListHeight(modoSimple)
            clip: true
            spacing: UiTokens.spacing6
            model: raiz.imp.historial
            currentIndex: raiz.historial_seleccion_indice
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: AppScrollBar { tema: raiz.tema; policy: ScrollBar.AsNeeded }

            delegate: Rectangle {
                id: histItem
                required property int index
                required property var model
                width: ListView.view.width
                height: histPanel.modoSimple && raiz.historial_simple_expandido === index ? 138 : 44
                radius: UiTokens.radiusMd
                color: (histPanel.modoSimple ? raiz.historial_simple_expandido === index : histItem.ListView.isCurrentItem) ? raiz.tema.seleccion : raiz.tema.superficieAlt
                border.color: raiz.tema.borde
                border.width: 1
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: UiTokens.spacing10
                    spacing: UiTokens.spacing8

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: UiTokens.spacing8
                        AppText {
                            text: "# Ejecución " + (histItem.model.id || "-") + " · " + (histItem.model.iniciado_en || "") + " · " + raiz._textoFinEjecucion(histItem.model)
                            color: raiz.tema.texto
                            font.pixelSize: UiTokens.fontSizeMd
                            font.weight: Font.DemiBold
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            elide: Text.ElideRight
                        }
                        StatusBadge {
                            tema: raiz.tema
                            text: histItem.model.estado || "sin estado"
                            tone: histItem.model.estado === "completado" ? "success" : (histItem.model.estado === "error" ? "danger" : "warning")
                            maxTextWidth: 96
                            compact: true
                        }
                    }

                    GridLayout {
                        visible: histPanel.modoSimple && raiz.historial_simple_expandido === index
                        Layout.fillWidth: true
                        columns: 2
                        rowSpacing: 6
                        columnSpacing: 10
                        AppText { text: "Aceptados: " + (histItem.model.total_aceptados || 0); color: raiz.tema.textoSec; font.pixelSize: UiTokens.fontSizeMd }
                        AppText { text: "Revisión: " + (histItem.model.total_revision || 0); color: raiz.tema.textoSec; font.pixelSize: UiTokens.fontSizeMd }
                        AppText { text: "Cuarentena: " + (histItem.model.total_cuarentena || 0); color: raiz.tema.textoSec; font.pixelSize: UiTokens.fontSizeMd }
                        AppText { text: "Pendientes: " + raiz._pendientesEjecucion(histItem.model); color: raiz.tema.textoSec; font.pixelSize: UiTokens.fontSizeMd }
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        historialList.currentIndex = index
                        raiz.historial_seleccion_indice = index
                        if (histPanel.modoSimple) {
                            raiz.historial_simple_expandido = raiz.historial_simple_expandido === index ? -1 : index
                        }
                    }
                }
            }

            EmptyState {
                anchors.centerIn: parent
                visible: historialList.count === 0
                tema: raiz.tema
                title: "Sin ejecuciones previas"
                description: "Cuando ejecutes una importación verás su historial aquí."
                iconSource: "../assets/icons/lightbulb.svg"
            }
        }
    }

    component PendingListCard: AppCard {
        id: pendingCard
        property var modelRef: null
        property string sectionLabel: ""
        property string tone: "neutral"
        property string emptyTitle: "Sin pendientes"
        property string emptyDescription: ""
        tema: raiz.tema

        RowLayout {
            Layout.fillWidth: true
            spacing: UiTokens.spacing8
            AppText {
                text: pendingCard.sectionLabel
                color: raiz.tema.texto
                font.pixelSize: 15
                font.weight: Font.DemiBold
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                elide: Text.ElideRight
            }
            StatusBadge { tema: raiz.tema; text: "" + (pendingCard.modelRef ? pendingCard.modelRef.total : 0); tone: pendingCard.tone; maxTextWidth: 64; compact: true }
        }

        ListView {
            id: pendingList
            Layout.fillWidth: true
            Layout.preferredHeight: pendingCard.modelRef && pendingCard.modelRef.total > 0 ? Math.min(500, Math.max(190, Math.min(pendingCard.modelRef.total, raiz.compactWidth ? 2 : 3) * 164)) : 190
            clip: true
            spacing: UiTokens.spacing10
            model: pendingCard.modelRef
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: AppScrollBar { tema: raiz.tema; policy: ScrollBar.AsNeeded }

            delegate: Item {
                id: pendingDelegate
                required property int index
                width: ListView.view.width
                height: panel.implicitHeight + 10
                DecisionPanel {
                    id: panel
                    width: parent.width
                    tema: raiz.tema
                    rev: raiz.rev
                    modelRef: pendingCard.modelRef
                    itemIndex: pendingDelegate.index
                    sectionLabel: pendingCard.sectionLabel
                }
            }

            EmptyState {
                anchors.centerIn: parent
                visible: pendingList.count === 0
                tema: raiz.tema
                title: pendingCard.emptyTitle
                description: pendingCard.emptyDescription
                iconSource: "../assets/icons/lightbulb.svg"
            }
        }
    }

    component StatSimple: Rectangle {
        id: stat
        property string etiqueta: ""
        property var valor: 0
        property string tono: "neutral"
        Layout.minimumWidth: 0
        height: raiz.compactWidth ? 76 : 82
        radius: 12
        color: raiz.tema.superficieAlt
        border.color: Qt.rgba(raiz.tema.borde.r, raiz.tema.borde.g, raiz.tema.borde.b, 0.7)
        border.width: 1

        ColumnLayout {
            anchors.centerIn: parent
            width: parent.width - 16
            spacing: UiTokens.spacing6
            StatusBadge { tema: raiz.tema; text: stat.etiqueta; tone: stat.tono; maxTextWidth: Math.max(46, stat.width - 32); compact: raiz.compactWidth; Layout.alignment: Qt.AlignHCenter }
            AppText {
                text: stat.valor
                color: raiz.tema.texto
                font.weight: Font.DemiBold
                font.pixelSize: 24
                horizontalAlignment: Text.AlignHCenter
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
        }
    }

    component DetailLine: Rectangle {
        id: detail
        property string etiqueta: ""
        property string valor: ""
        Layout.fillWidth: true
        radius: UiTokens.radiusMd
        color: raiz.tema.superficieAlt
        border.color: raiz.tema.borde
        border.width: 1
        implicitHeight: lineLayout.implicitHeight + 18

        ColumnLayout {
            id: lineLayout
            anchors.fill: parent
            anchors.margins: 9
            spacing: UiTokens.spacing4
            AppText { text: detail.etiqueta; color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.DemiBold }
            AppText { text: detail.valor || "-"; color: raiz.tema.texto; font.pixelSize: UiTokens.fontSizeMd; elide: Text.ElideMiddle; Layout.fillWidth: true }
        }
    }
}
