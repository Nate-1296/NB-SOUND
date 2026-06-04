import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtQuick.Effects

import "../componentes"
import "../componentes/UiUtils.js" as UiUtils

// VistaKaraoke — Preparacion de pistas con separacion voz/instrumental real
// (Demucs). El backend vive integro en Python; QML solo renderiza estado y
// dispara acciones via `kar` (ModeloKaraoke).
Rectangle {
    id: raiz
    objectName: "vista_karaoke"
    color: raiz.tema.fondo

    property var shell: null
    required property var temaBase
    required property var cfg
    required property var kar
    required property var rep
    readonly property var tema: shell ? shell.tema : temaBase

    // ── Responsive ──────────────────────────────────────────────────────
    readonly property int  hMax: 1240
    readonly property int  hPad: raiz.width >= 1320 ? 44 : (raiz.width >= 860 ? 32 : UiTokens.spacing20)
    readonly property real aW:   Math.min(hMax, Math.max(0, raiz.width - hPad * 2))
    readonly property bool cW:   aW < 700
    readonly property bool mW:   aW >= 900
    readonly property bool wW:   aW >= 1100

    // ── Columnas (desktop) ─────────────────────────────────────────────
    readonly property int colChk:      24
    readonly property int colPortada:  38
    readonly property int colEstado:   94
    readonly property int colProgreso: 90
    readonly property int colDuracion: 56
    readonly property int colAcciones: wW ? 280 : (mW ? 230 : 170)

    // ── Estado de seleccion ─────────────────────────────────────────────
    //
    // La seleccion masiva (checkboxes + master + banner) SOLO tiene sentido
    // en la pestana "Sin preparar": ahi el usuario decide que pistas envia a
    // la cola. En el resto de pestanas, las pistas ya estan en un flujo y la
    // accion correcta es por fila o global de pestana.
    property var  sel_ids: ({})
    property bool sel_todos_completo: false
    readonly property int sel_count: Object.keys(sel_ids).length
    readonly property int vis_count: kar.pistas.total
    readonly property int master_st: {
        if (sel_count === 0) return 0
        if (sel_count >= vis_count && vis_count > 0) return 2
        return 1
    }

    // Pestana activa permite seleccion masiva?  Solo "sin_preparar".
    readonly property bool tab_permite_seleccion: kar.filtro_estado === "sin_preparar"

    // ── FileDialog diferido (instrumental manual) ───────────────────────
    property int    _asig_id:     -1
    property string _asig_titulo: ""

    // ── Modal de detalle de error/job ───────────────────────────────────
    property bool   modal_error_open:  false
    property var    modal_error_datos: ({})

    // ── Helpers ─────────────────────────────────────────────────────────
    function _dur(seg) {
        if (!seg || seg <= 0) return "—"
        var s = Math.round(seg), m = Math.floor(s/60), h = Math.floor(m/60)
        if (h > 0) return h+":"+_p2(m%60)+":"+_p2(s%60)
        return m+":"+_p2(s%60)
    }
    function _p2(n) { return n < 10 ? "0"+n : ""+n }
    function _etiq(e) {
        switch(e) {
            case "lista":        return "Lista"
            case "procesando":   return "Procesando"
            case "en_cola":      return "En cola"
            case "fallida":      return "Fallida"
            case "no_procesada": return "Sin preparar"
            case "no_aplica":    return "No aplica"
            default:             return e || "—"
        }
    }
    function _tono(e) {
        switch(e) {
            case "lista":        return "success"
            case "procesando":   return "info"
            case "en_cola":      return "info"
            case "fallida":      return "danger"
            case "no_aplica":    return "neutral"
            default:             return "warning"
        }
    }
    function _err_texto(codigo) {
        switch(codigo) {
            case "backend_no_disponible": return "Demucs no esta instalado"
            case "ffmpeg_faltante":       return "Falta ffmpeg"
            case "modelo_faltante":       return "Modelo no disponible (sin internet?)"
            case "audio_corrupto":        return "Archivo de audio corrupto"
            case "archivo_no_existe":     return "Archivo no encontrado en disco"
            case "memoria_insuficiente":  return "Memoria insuficiente"
            case "timeout":               return "Tiempo de procesamiento agotado"
            case "cancelado":             return "Cancelado"
            default:                      return codigo || "Error desconocido"
        }
    }
    function _puedeEjecutar()  { return !kar.procesando && kar.resumen.en_cola > 0 }
    function _puedeCancelar()  { return kar.procesando }
    function _toggle(id) {
        var c = Object.assign({}, sel_ids)
        var k = String(id)
        if (c[k] !== undefined) { delete c[k]; sel_todos_completo = false }
        else                     c[k] = true
        sel_ids = c
    }
    function _selTodos() {
        var c = {}
        for (var i = 0; i < kar.pistas.total; i++) {
            var p = kar.pistas.obtener(i)
            if (p && p.id !== undefined && p.id !== null) c[String(p.id)] = true
        }
        sel_ids = c
    }
    function _limpiar() { sel_ids = {}; sel_todos_completo = false }
    function _toggleMaster() {
        if (master_st === 0) _selTodos()
        else                 _limpiar()
    }
    function _idsSeleccionados() {
        return Object.keys(sel_ids).map(Number)
    }
    function _alturaLista() {
        var n = kar.pistas.total
        if (n <= 0) return 180
        var rowH = cW ? 88 : 60
        var desired = n * rowH + Math.max(0, n - 1) * 5
        return Math.min(cW ? 480 : 560, Math.max(cW ? 120 : 100, desired))
    }
    function _textoRango() {
        var lim = kar.limite_pagina, tot = kar.total_filtrado
        if (tot <= 0 || lim <= 0) return "Sin resultados"
        var desde = kar.pagina_actual * lim + 1
        var hasta = Math.min((kar.pagina_actual + 1) * lim, tot)
        return desde + "–" + hasta + " de " + tot
    }
    function _toast(msg, tone) {
        if (shell) shell.mostrar_toast_global(msg, tone || "info")
    }
    function _abrirErrorDetalle(pid) {
        var d = kar.detalle_job(pid)
        if (d && d.error_codigo) {
            raiz.modal_error_datos = d
            raiz.modal_error_open = true
        } else {
            raiz._toast("No hay detalle disponible para esta pista.", "info")
        }
    }
    function _estadoProcesoTexto(e) {
        switch(e) {
            case "preparando":   return "Preparando modelo"
            case "procesando":   return "Procesando"
            case "completado":   return "Completado"
            case "cancelado":    return "Cancelado"
            case "error":        return "Error"
            default:             return "Inactivo"
        }
    }
    function _estadoProcesoTono(e) {
        switch(e) {
            case "preparando":   return "info"
            case "procesando":   return "info"
            case "completado":   return "success"
            case "error":        return "danger"
            case "cancelado":    return "warning"
            default:             return "neutral"
        }
    }

    // ── Conexiones ──────────────────────────────────────────────────────
    Connections {
        target: kar
        function onPistasCargadas()    { if (raiz.sel_count > 0 && kar.pistas.total === 0) raiz._limpiar() }
        function onOperacionOk(msg)    { raiz._toast(msg, "info") }
        function onOperacionError(msg) { raiz._toast(msg, "warning") }
        function onKaraokeActualizado(_pid) { rep.refrescar_karaoke_pista_activa() }
    }

    // ── FileDialog para instrumental manual ─────────────────────────────
    Loader {
        id: dlg_loader
        active: false
        onLoaded: {
            if (!item) return
            item.asig_titulo = Qt.binding(function() { return raiz._asig_titulo })
            item.seleccionada.connect(function(ruta) {
                if (raiz._asig_id >= 0) kar.asignar_instrumental(raiz._asig_id, ruta)
                raiz._asig_id = -1; raiz._asig_titulo = ""
            })
            item.cancelado.connect(function() { raiz._asig_id = -1; raiz._asig_titulo = "" })
            item.open()
        }
    }
    function _abrirDialogoInstrumental(pid, titulo) {
        raiz._asig_id = pid; raiz._asig_titulo = titulo
        if (!dlg_loader.active) {
            dlg_loader.source = Qt.resolvedUrl("../componentes/KaraokeFileDialog.qml")
            dlg_loader.active = true
        } else if (dlg_loader.item) {
            dlg_loader.item.open()
        }
    }

    // ── Modal de error (sobre el scroll) ────────────────────────────────
    Rectangle {
        id: modal_error
        anchors.fill: parent
        z: 500
        visible: raiz.modal_error_open
        color: UiUtils.veloOscuro(0.55)
        MouseArea { anchors.fill: parent; onClicked: raiz.modal_error_open = false }
        Rectangle {
            anchors.centerIn: parent
            width: Math.min(parent.width - 32, 520)
            height: Math.min(parent.height - 64, _meCol.implicitHeight + 32)
            radius: UiTokens.radiusLg
            color: raiz.tema.superficie
            border.color: raiz.tema.borde; border.width: 1
            MouseArea { anchors.fill: parent }  // bloquea cierre al hacer click dentro
            ColumnLayout {
                id: _meCol
                anchors.fill: parent
                anchors.margins: 18
                spacing: UiTokens.spacing12
                RowLayout {
                    Layout.fillWidth: true; spacing: UiTokens.spacing8
                    AppText {
                        text: "Detalle de procesamiento"
                        color: raiz.tema.texto
                        font.pixelSize: UiTokens.fontSizeXl; font.weight: Font.DemiBold
                        Layout.fillWidth: true
                    }
                    Rectangle {
                        width: 28; height: 28; radius: UiTokens.radiusLg
                        color: _meXm.containsMouse ? Qt.rgba(raiz.tema.peligro.r, raiz.tema.peligro.g, raiz.tema.peligro.b, 0.18) : "transparent"
                        AppText { anchors.centerIn: parent; text: "×"; color: raiz.tema.textoSec; font.pixelSize: UiTokens.fontSize2xl }
                        MouseArea { id: _meXm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: raiz.modal_error_open = false }
                    }
                }
                StatusBadge {
                    tema: raiz.tema
                    text: raiz._err_texto((raiz.modal_error_datos && raiz.modal_error_datos.error_codigo) || "")
                    tone: "danger"; compact: true
                }
                AppText {
                    text: (raiz.modal_error_datos && raiz.modal_error_datos.error_mensaje) || "(sin mensaje)"
                    color: raiz.tema.texto
                    wrapMode: Text.WordWrap; font.pixelSize: UiTokens.fontSizeBase
                    Layout.fillWidth: true
                }
                GridLayout {
                    Layout.fillWidth: true; columns: 2; columnSpacing: 16; rowSpacing: 4
                    AppText { text: "Intento";  color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm }
                    AppText { text: ((raiz.modal_error_datos.intento) || 0) + " / " + ((raiz.modal_error_datos.max_intentos) || 0); color: raiz.tema.texto; font.pixelSize: UiTokens.fontSizeSm }
                    AppText { text: "Modelo";   color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm }
                    AppText { text: (raiz.modal_error_datos.modelo) || "—"; color: raiz.tema.texto; font.pixelSize: UiTokens.fontSizeSm }
                    AppText { text: "Device";   color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm }
                    AppText { text: (raiz.modal_error_datos.device) || "—"; color: raiz.tema.texto; font.pixelSize: UiTokens.fontSizeSm }
                    AppText { text: "Finalizado"; color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm }
                    AppText { text: UiUtils.formatearFechaLocal(raiz.modal_error_datos.finalizado_en); color: raiz.tema.texto; font.pixelSize: UiTokens.fontSizeSm }
                }
                Rectangle {
                    Layout.fillWidth: true; Layout.preferredHeight: 38; radius: 19
                    color: raiz.tema.acento
                    AppText { anchors.centerIn: parent; text: "Cerrar"; color: raiz.tema.textoSobreAcento; font.weight: Font.DemiBold; font.pixelSize: UiTokens.fontSizeBase }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: raiz.modal_error_open = false }
                }
            }
        }
    }

    // ── Scroll principal ────────────────────────────────────────────────
    ScrollView {
        id: _kar_scroll
        anchors.fill: parent
        contentWidth: availableWidth
        contentHeight: col_raiz.implicitHeight
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical: AppScrollBar {
            parent: _kar_scroll
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            z: 20
            tema: raiz.tema
            policy: _kar_scroll.contentHeight > _kar_scroll.height + 2 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
        }

        ColumnLayout {
            id: col_raiz
            width: raiz.width
            spacing: 0

            // ── CABECERA ─────────────────────────────────────────────
            Item {
                Layout.fillWidth: true; height: 88
                AppText {
                    anchors { left: parent.left; leftMargin: raiz.hPad; bottom: parent.bottom; bottomMargin: UiTokens.spacing16 }
                    text: "Preparar Karaoke"
                    font.pixelSize: 28; font.weight: Font.DemiBold; color: raiz.tema.texto
                }
            }

            // ── BANNER DE BACKEND (solo si falla) ─────────────────────
            AppCard {
                Layout.fillWidth: true
                Layout.leftMargin: raiz.hPad; Layout.rightMargin: raiz.hPad
                Layout.maximumWidth: raiz.hMax; Layout.alignment: Qt.AlignHCenter
                tema: raiz.tema
                visible: !kar.backend_listo

                ColumnLayout {
                    Layout.fillWidth: true; spacing: UiTokens.spacing8
                    RowLayout {
                        Layout.fillWidth: true; spacing: UiTokens.spacing8
                        StatusBadge { tema: raiz.tema; text: "Backend faltante"; tone: "warning"; compact: true }
                        AppText {
                            text: kar.backend_diag.mensaje || "Detectando..."
                            color: raiz.tema.texto
                            font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold
                            elide: Text.ElideRight; Layout.fillWidth: true
                        }
                    }
                    AppText {
                        text: kar.backend_diag.instrucciones || ""
                        visible: text !== ""
                        color: raiz.tema.textoSec
                        font.pixelSize: UiTokens.fontSizeMd; wrapMode: Text.WordWrap; Layout.fillWidth: true
                    }
                    Rectangle {
                        implicitWidth: Math.min(220, _refBe.implicitWidth + 28); implicitHeight: 32; radius: 16
                        color: _refBeM.containsMouse ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.18) : raiz.tema.superficieAlt
                        border.color: raiz.tema.acento; border.width: 1
                        AppText { id: _refBe; anchors.centerIn: parent; text: "Re-detectar backend"; color: raiz.tema.acento; font.pixelSize: UiTokens.fontSizeMd; font.weight: Font.DemiBold }
                        MouseArea { id: _refBeM; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: kar.detectar_backend() }
                    }
                }
            }

            // ── TARJETA RESUMEN ───────────────────────────────────────
            AppCard {
                Layout.fillWidth: true
                Layout.leftMargin: raiz.hPad; Layout.rightMargin: raiz.hPad
                Layout.topMargin: !kar.backend_listo ? UiTokens.spacing10 : 0
                Layout.maximumWidth: raiz.hMax; Layout.alignment: Qt.AlignHCenter
                tema: raiz.tema; elevated: true

                GridLayout {
                    Layout.fillWidth: true; columns: raiz.cW ? 1 : 2; columnSpacing: 12; rowSpacing: 8
                    ColumnLayout {
                        Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: UiTokens.spacing4
                        AppText { text: "Estado de preparacion"; color: raiz.tema.texto; font.pixelSize: 20; font.weight: Font.DemiBold; Layout.fillWidth: true }
                        AppText {
                            text: "Selecciona pistas y ponlas en cola. Demucs separa la voz del instrumental. Las 'Listas' activan el modo karaoke en el reproductor."
                            color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeMd; wrapMode: Text.WordWrap; Layout.fillWidth: true
                        }
                    }
                    Flow {
                        Layout.fillWidth: raiz.cW; Layout.preferredWidth: raiz.cW ? -1 : 240
                        Layout.alignment: raiz.cW ? Qt.AlignLeft : (Qt.AlignRight | Qt.AlignTop); spacing: UiTokens.spacing6
                        StatusBadge { tema: raiz.tema; text: "Total " + (kar.resumen.total || 0); tone: "neutral"; compact: true; maxTextWidth: 100 }
                        StatusBadge { tema: raiz.tema; text: (kar.resumen.lista || 0) + " lista" + ((kar.resumen.lista || 0) !== 1 ? "s" : ""); tone: "success"; compact: true; maxTextWidth: 90 }
                    }
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: raiz.wW ? 5 : (raiz.mW ? 3 : 2)
                    rowSpacing: 10; columnSpacing: 10

                    component StatKar: Rectangle {
                        id: _sk; property string etiq: ""; property int n: 0
                        property string tono: "neutral"; property string fId: ""
                        Layout.fillWidth: true; Layout.minimumWidth: 0
                        height: raiz.cW ? 76 : 82; radius: UiTokens.radiusMd
                        color: kar.filtro_estado === fId
                               ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.13)
                               : raiz.tema.superficieAlt
                        border.color: kar.filtro_estado === fId ? raiz.tema.acento : Qt.rgba(raiz.tema.borde.r, raiz.tema.borde.g, raiz.tema.borde.b, 0.7)
                        border.width: kar.filtro_estado === fId ? 1.5 : 1
                        ColumnLayout { anchors.centerIn: parent; width: parent.width - 16; spacing: UiTokens.spacing6
                            StatusBadge { tema: raiz.tema; text: _sk.etiq; tone: _sk.tono; maxTextWidth: Math.max(40, _sk.width - 28); compact: raiz.cW; Layout.alignment: Qt.AlignHCenter }
                            AppText { text: _sk.n; color: raiz.tema.texto; font.weight: Font.DemiBold; font.pixelSize: 24; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true; elide: Text.ElideRight }
                        }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { raiz._limpiar(); kar.establecer_filtro_estado(_sk.fId) } }
                    }

                    StatKar { etiq: "Sin preparar"; n: kar.resumen.sin_preparar || 0; tono: "warning"; fId: "sin_preparar" }
                    // "En cola" agrupa en_cola + procesando (igual que su filtro):
                    // así la suma de las pestañas SIEMPRE iguala al Total (y a
                    // Pistas). Mostrar solo en_cola dejaba fuera lo que se está
                    // procesando ahora y el total parecía "perder" una pista.
                    StatKar { etiq: "En cola";      n: (kar.resumen.en_cola || 0) + (kar.resumen.procesando || 0); tono: "info";    fId: "en_cola";
                              visible: (kar.resumen.en_cola || 0) > 0 || (kar.resumen.procesando || 0) > 0 || kar.filtro_estado === "en_cola" }
                    StatKar { etiq: "Lista";        n: kar.resumen.lista        || 0; tono: "success"; fId: "lista" }
                    StatKar { etiq: "Fallida";      n: kar.resumen.fallida      || 0; tono: "danger";  fId: "fallida" }
                    StatKar { etiq: "No aplica";    n: kar.resumen.no_aplica    || 0; tono: "neutral"; fId: "no_aplica" }
                }
            }

            // ── PANEL DE PROCESAMIENTO ────────────────────────────────
            AppCard {
                id: panel_proceso
                objectName: "karaoke_panel_proceso"
                Layout.fillWidth: true
                Layout.leftMargin: raiz.hPad; Layout.rightMargin: raiz.hPad
                Layout.topMargin: UiTokens.spacing12
                Layout.maximumWidth: raiz.hMax; Layout.alignment: Qt.AlignHCenter
                tema: raiz.tema

                GridLayout {
                    Layout.fillWidth: true; columns: raiz.cW ? 1 : 2; columnSpacing: 10; rowSpacing: 8
                    ColumnLayout {
                        Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: UiTokens.spacing4
                        AppText { text: "Procesamiento"; color: raiz.tema.texto; font.pixelSize: 17; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
                        AppText {
                            text: {
                                if (kar.warning_proceso !== "") return kar.warning_proceso
                                if (kar.mensaje_proceso !== "") return kar.mensaje_proceso
                                return kar.backend_listo
                                    ? ("Demucs · device " + (kar.device_activo || "cpu") + (kar.modelo_activo ? " · " + kar.modelo_activo : ""))
                                    : "Backend no detectado"
                            }
                            color: kar.warning_proceso !== "" ? raiz.tema.advertencia : raiz.tema.textoMuted
                            font.pixelSize: UiTokens.fontSizeMd; wrapMode: Text.WordWrap; Layout.fillWidth: true
                        }
                    }
                    Flow {
                        Layout.fillWidth: raiz.cW; Layout.preferredWidth: raiz.cW ? -1 : 320
                        Layout.alignment: raiz.cW ? Qt.AlignLeft : (Qt.AlignRight | Qt.AlignTop); spacing: UiTokens.spacing6
                        StatusBadge { tema: raiz.tema; text: raiz._estadoProcesoTexto(kar.estado_proceso); tone: raiz._estadoProcesoTono(kar.estado_proceso); compact: true; maxTextWidth: 130 }
                        StatusBadge { tema: raiz.tema; text: "listas " + kar.resumen.lista; tone: "success"; compact: true; maxTextWidth: 100 }
                    }
                }

                // Barra de progreso GLOBAL (cuantas pistas)
                Rectangle {
                    Layout.fillWidth: true; height: 8; radius: 4; color: raiz.tema.superficieAlt; clip: true
                    visible: kar.procesando || kar.total_proceso > 0
                    Rectangle {
                        width: parent.width * Math.max(0, Math.min(1, kar.porcentaje_proceso))
                        height: parent.height; radius: 4; color: raiz.tema.acento
                        Behavior on width { NumberAnimation { duration: 220 } }
                    }
                }

                // Barra de progreso del JOB ACTUAL (dentro de la pista)
                Rectangle {
                    Layout.fillWidth: true; height: 4; radius: 2; color: raiz.tema.superficieAlt; clip: true
                    visible: kar.procesando
                    Rectangle {
                        width: parent.width * Math.max(0, Math.min(1, kar.porcentaje_job))
                        height: parent.height; radius: 2
                        color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.55)
                        Behavior on width { NumberAnimation { duration: 180 } }
                    }
                }

                // Stats de proceso
                GridLayout {
                    Layout.fillWidth: true
                    columns: raiz.wW ? 5 : (raiz.mW ? 3 : (raiz.cW ? 2 : 3))
                    rowSpacing: 8; columnSpacing: 8

                    component StatProceso: Rectangle {
                        id: _sp; property string etiq: ""; property var val: "—"; property string tono: "neutral"
                        Layout.fillWidth: true; Layout.minimumWidth: 0; height: raiz.cW ? 72 : 78; radius: UiTokens.radiusMd
                        color: raiz.tema.superficieAlt
                        border.color: Qt.rgba(raiz.tema.borde.r, raiz.tema.borde.g, raiz.tema.borde.b, 0.7); border.width: 1
                        ColumnLayout { anchors.centerIn: parent; width: parent.width - 12; spacing: 5
                            StatusBadge { tema: raiz.tema; text: _sp.etiq; tone: _sp.tono; maxTextWidth: Math.max(36, _sp.width-20); compact: raiz.cW; Layout.alignment: Qt.AlignHCenter }
                            AppText { text: _sp.val; color: raiz.tema.texto; font.weight: Font.DemiBold; font.pixelSize: 20; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true; elide: Text.ElideRight }
                        }
                    }
                    StatProceso { etiq: "Procesadas"; val: kar.procesadas_proceso + "/" + kar.total_proceso; tono: "neutral" }
                    StatProceso { etiq: "Listas";     val: kar.ready_proceso;    tono: "success" }
                    StatProceso { etiq: "Fallidas";   val: kar.failed_proceso;   tono: kar.failed_proceso > 0 ? "danger" : "neutral" }
                    StatProceso { etiq: "Pendientes"; val: kar.pendientes_proceso; tono: kar.pendientes_proceso > 0 ? "info" : "neutral" }
                    StatProceso { etiq: "Velocidad";  val: Number(kar.velocidad_proceso || 0).toFixed(1) + "/min"; tono: "neutral" }
                }

                // Detalle pista actual + ETA
                GridLayout {
                    Layout.fillWidth: true; columns: raiz.cW ? 1 : 2; columnSpacing: 12; rowSpacing: 8
                    component DetalleLinea: Rectangle {
                        id: _dl; property string etiq: ""; property string val: ""
                        Layout.fillWidth: true; radius: UiTokens.radiusMd; color: raiz.tema.superficieAlt
                        border.color: raiz.tema.borde; border.width: 1; implicitHeight: _dllay.implicitHeight + 16
                        ColumnLayout { id: _dllay; anchors.fill: parent; anchors.margins: UiTokens.spacing8; spacing: 3
                            AppText { text: _dl.etiq; color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.DemiBold }
                            AppText { text: _dl.val || "—"; color: raiz.tema.texto; font.pixelSize: UiTokens.fontSizeMd; elide: Text.ElideMiddle; Layout.fillWidth: true }
                        }
                    }
                    DetalleLinea { etiq: "Pista actual"; val: kar.pista_actual_proceso }
                    DetalleLinea { etiq: "ETA estimado"; val: kar.eta_proceso }
                }

                // Botones de control
                Flow {
                    Layout.fillWidth: true; spacing: UiTokens.spacing10

                    component BtnControl: Rectangle {
                        id: _bc
                        property string texto: ""; property string tono: "accent"; property bool habilitado: true
                        signal clicked()
                        // Alphas unificadas con AccBtn para coherencia entre niveles.
                        // Accent: fondo solido; hover atenua a 0.88 (no se intensifica).
                        // Resto: tinte sutil (alpha ~0.10 / 0.18 hover) + borde del color.
                        // NOTA: las propiedades del tema (acento, peligro, etc) llegan
                        // como string desde Python. `.r .g .b` sobre string es undefined
                        // → Qt.rgba(undef, undef, undef, X) pinta NEGRO. Hay que forzar
                        // Qt.color() para garantizar la conversión a tipo color.
                        function _bg() {
                            if (!_bc.habilitado) return raiz.tema.superficieAlt
                            var c
                            var a
                            if (tono === "danger") {
                                c = Qt.color(raiz.tema.peligro);     a = _bcm.containsMouse ? 0.18 : 0.10
                            } else if (tono === "neutral") {
                                c = Qt.color(raiz.tema.textoMuted);  a = _bcm.containsMouse ? 0.16 : 0.08
                            } else if (tono === "warning") {
                                c = Qt.color(raiz.tema.advertencia); a = _bcm.containsMouse ? 0.18 : 0.10
                            } else {
                                // accent: solido; hover atenua (no brilla mas)
                                c = Qt.color(raiz.tema.acento);      a = _bcm.containsMouse ? 0.88 : 1.0
                            }
                            return Qt.rgba(c.r, c.g, c.b, a)
                        }
                        function _fc() {
                            if (!_bc.habilitado) return raiz.tema.textoMuted
                            if (tono === "danger")  return raiz.tema.peligro
                            if (tono === "neutral") return raiz.tema.textoSec
                            if (tono === "warning") return raiz.tema.advertencia
                            return raiz.tema.textoSobreAcento
                        }
                        implicitWidth: Math.min(Math.max(110, _bcl.implicitWidth + 24), 220)
                        height: 36; radius: 18; clip: true; opacity: habilitado ? 1.0 : 0.65
                        color: _bg()
                        // Borde: cuando deshabilitado siempre visible (tema.borde) para
                        // que el botón no quede como un "rectángulo plano negro" sobre
                        // superficie oscura. Cuando habilitado y accent, sin borde
                        // (color sólido del acento ya es suficiente).
                        border.color: !habilitado
                            ? raiz.tema.borde
                            : (tono !== "accent" ? _fc() : "transparent")
                        border.width: (!habilitado || tono !== "accent") ? 1 : 0
                        AppText { id: _bcl; anchors.centerIn: parent; width: Math.max(0, parent.width-22); text: _bc.texto; color: _bc._fc(); font.pixelSize: UiTokens.fontSizeMd; font.weight: Font.DemiBold; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight }
                        MouseArea { id: _bcm; anchors.fill: parent; hoverEnabled: true; enabled: _bc.habilitado; cursorShape: _bc.habilitado ? Qt.PointingHandCursor : Qt.ArrowCursor; onClicked: _bc.clicked() }
                    }

                    // Panel de procesamiento: SOLO acciones sobre EL proceso
                    // (no sobre el contenido). Las acciones sobre el contenido
                    // (vaciar cola, reintentar fallidas, etc) viven en la
                    // cabecera de la tabla, contextuales a la pestana activa.
                    BtnControl {
                        objectName: "kar_btn_iniciar"
                        visible: raiz._puedeEjecutar()
                        texto: "Iniciar procesamiento"
                        tono: "accent"; habilitado: !kar.procesando && kar.backend_listo
                        onClicked: kar.iniciar_procesamiento()
                    }
                    BtnControl {
                        objectName: "kar_btn_cancelar"
                        visible: raiz._puedeCancelar()
                        texto: "Cancelar actual"; tono: "warning"
                        onClicked: kar.cancelar_procesamiento()
                    }
                    BtnControl {
                        objectName: "kar_btn_cancelar_y_vaciar"
                        visible: raiz._puedeCancelar()
                        texto: "Cancelar y vaciar cola"; tono: "danger"
                        onClicked: kar.cancelar_y_vaciar()
                    }
                    BtnControl {
                        objectName: "kar_btn_refrescar"
                        texto: "Refrescar"; tono: "neutral"
                        onClicked: { kar.cargar(); kar.detectar_backend() }
                    }
                }
            }

            // ── PANEL DE PISTA ACTIVA ────────────────────────────────
            AppCard {
                Layout.fillWidth: true
                Layout.leftMargin: raiz.hPad; Layout.rightMargin: raiz.hPad
                Layout.topMargin: UiTokens.spacing8
                Layout.maximumWidth: raiz.hMax; Layout.alignment: Qt.AlignHCenter
                tema: raiz.tema; visible: rep.titulo_activo !== ""

                RowLayout {
                    Layout.fillWidth: true; spacing: UiTokens.spacing10
                    Rectangle {
                        width: 38; height: 38; radius: UiTokens.radiusSm; color: raiz.tema.superficieAlt; clip: true
                        readonly property string src: (rep.pista_activa && rep.pista_activa.portada_ruta) ? UiUtils.toMediaSource(rep.pista_activa.portada_ruta) : ""
                        Image { anchors.fill: parent; source: parent.src; fillMode: Image.PreserveAspectCrop; visible: parent.src !== ""; asynchronous: true }
                        Image { id: _khImg; anchors.centerIn: parent; width: 18; height: 18; source: "../assets/icons/track.svg"; sourceSize.width: 36; sourceSize.height: 36; smooth: true; opacity: 0; visible: parent.src === "" }
                        MultiEffect { visible: _khImg.visible; anchors.fill: _khImg; source: _khImg; colorization: 1.0; colorizationColor: raiz.tema.textoMuted }
                    }
                    ColumnLayout { Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: UiTokens.spacing2
                        AppText { text: rep.titulo_activo; color: raiz.tema.texto; font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                        AppText { text: rep.artista_activo; color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm; elide: Text.ElideRight; Layout.fillWidth: true }
                    }
                    StatusBadge { tema: raiz.tema; text: raiz._etiq(rep.karaoke_estado); tone: raiz._tono(rep.karaoke_estado); compact: true; maxTextWidth: 100 }
                    // Toggle Karaoke: estilo unificado con AccBtn "accent".
                    // Cuando activo, fondo solido acento; cuando inactivo, tinte sutil.
                    // El texto contrasta dinamicamente con la luminosidad del acento.
                    Rectangle {
                        id: _kar_toggle
                        visible: rep.karaoke_disponible
                        height: 30
                        width: Math.max(110, _kl.implicitWidth + 22)
                        radius: 15
                        readonly property real lum_ac: 0.299 * raiz.tema.acento.r + 0.587 * raiz.tema.acento.g + 0.114 * raiz.tema.acento.b
                        color: rep.karaoke_activo
                            ? raiz.tema.acento
                            : Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, _kar_toggle_ma.containsMouse ? 0.18 : 0.10)
                        border.color: raiz.tema.acento
                        border.width: rep.karaoke_activo ? 0 : 1
                        AppText {
                            id: _kl
                            anchors.centerIn: parent
                            text: rep.karaoke_activo ? "Karaoke activo" : "Activar"
                            color: rep.karaoke_activo
                                ? raiz.tema.textoSobreAcento
                                : raiz.tema.acento
                            font.pixelSize: UiTokens.fontSizeMd; font.weight: Font.DemiBold
                        }
                        MouseArea {
                            id: _kar_toggle_ma
                            anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: rep.alternar_karaoke()
                        }
                    }
                }
            }

            // ── TABS ────────────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: raiz.hPad; Layout.rightMargin: raiz.hPad
                Layout.topMargin: UiTokens.spacing14
                Layout.maximumWidth: raiz.hMax; Layout.alignment: Qt.AlignHCenter
                implicitHeight: 52; radius: UiTokens.radiusLg; color: raiz.tema.superficie
                border.color: raiz.tema.borde; border.width: 1

                RowLayout {
                    anchors.fill: parent; anchors.margins: UiTokens.spacing6; spacing: UiTokens.spacing6

                    component SegTab: Rectangle {
                        id: _st; property string texto: ""; property string tabId: ""; property int cuenta: 0
                        Layout.fillWidth: true; implicitHeight: 38; radius: UiTokens.radiusMd
                        readonly property bool activo: kar.filtro_estado === tabId
                        color: activo ? raiz.tema.seleccion : (_stm.containsMouse ? Qt.rgba(raiz.tema.hover.r, raiz.tema.hover.g, raiz.tema.hover.b, 0.6) : "transparent")
                        border.color: activo ? raiz.tema.acento : "transparent"; border.width: activo ? 1 : 0
                        RowLayout { anchors.centerIn: parent; spacing: 5
                            AppText { text: _st.texto; font.pixelSize: UiTokens.fontSizeBase; font.weight: _st.activo ? Font.DemiBold : Font.Normal; color: _st.activo ? raiz.tema.texto : raiz.tema.textoSec }
                            Rectangle { visible: _st.cuenta > 0; width: Math.max(20, _cntl.implicitWidth + 8); height: 18; radius: 9; color: _st.activo ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.22) : raiz.tema.superficieAlt
                                AppText { id: _cntl; anchors.centerIn: parent; text: _st.cuenta; font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.DemiBold; color: _st.activo ? raiz.tema.acento : raiz.tema.textoMuted }
                            }
                        }
                        MouseArea { id: _stm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { raiz._limpiar(); kar.establecer_filtro_estado(_st.tabId) } }
                    }

                    SegTab { texto: "Sin preparar"; tabId: "sin_preparar"; cuenta: kar.resumen.sin_preparar || 0 }
                    SegTab { texto: "En cola";      tabId: "en_cola";      cuenta: (kar.resumen.en_cola || 0) + (kar.resumen.procesando || 0); visible: ((kar.resumen.en_cola || 0) + (kar.resumen.procesando || 0)) > 0 || kar.filtro_estado === "en_cola" }
                    SegTab { texto: "Listas";       tabId: "lista";        cuenta: kar.resumen.lista    || 0 }
                    SegTab { texto: "Fallidas";     tabId: "fallida";      cuenta: kar.resumen.fallida  || 0 }
                    SegTab { texto: "No aplica";    tabId: "no_aplica";    cuenta: kar.resumen.no_aplica || 0 }
                }
            }

            // ── TABLA DE PISTAS ───────────────────────────────────────
            AppCard {
                id: tabla_card
                Layout.fillWidth: true
                Layout.leftMargin: raiz.hPad; Layout.rightMargin: raiz.hPad
                Layout.topMargin: UiTokens.spacing8
                Layout.maximumWidth: raiz.hMax; Layout.alignment: Qt.AlignHCenter
                tema: raiz.tema

                // ── Barra superior contextual por pestana ───────────────────
                //
                // Solo se muestran las acciones que tienen sentido para la
                // pestana activa:
                //   sin_preparar  →  checkbox master + buscar + Encolar
                //   en_cola       →  buscar + Vaciar cola (si hay items)
                //   lista         →  buscar
                //   fallida       →  buscar + Reintentar todas
                //   no_aplica     →  buscar + Restaurar todas
                RowLayout {
                    Layout.fillWidth: true; spacing: 8

                    // Checkbox master: SOLO en "sin_preparar"
                    Item {
                        width: raiz.tab_permite_seleccion ? raiz.colChk : 0
                        height: raiz.colChk
                        visible: raiz.tab_permite_seleccion
                        CkBox {
                            anchors.centerIn: parent
                            sel: raiz.master_st === 2
                            indeterminate: raiz.master_st === 1
                            onToggled: raiz._toggleMaster()
                        }
                    }

                    TextField {
                        id: campo_busq
                        Layout.fillWidth: true; Layout.minimumWidth: 0
                        placeholderText: "Buscar por titulo, artista o album..."
                        placeholderTextColor: raiz.tema.textoMuted; selectByMouse: true; color: raiz.tema.texto
                        selectionColor: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.32); selectedTextColor: raiz.tema.texto
                        onTextChanged: debounce.restart()
                        background: Rectangle { radius: UiTokens.radiusSm; color: raiz.tema.superficieAlt; border.color: campo_busq.activeFocus ? raiz.tema.acento : raiz.tema.borde; border.width: campo_busq.activeFocus ? 1.5 : 1 }
                        Timer { id: debounce; interval: 240; onTriggered: kar.establecer_filtro_texto(campo_busq.text) }
                    }

                    // Boton de accion GLOBAL contextual
                    //
                    // Jerarquia visual:
                    //   - Primary (Encolar en sin_preparar): fondo acento solido,
                    //     hover muy ligeramente atenuado (alpha 0.88) para
                    //     comunicar interaccion sin "brillo extra".
                    //   - Secondary (Vaciar/Reintentar/Restaurar): fondo tinted
                    //     suave del color semantico + borde del mismo color +
                    //     texto del color. Sin glow.
                    Rectangle {
                        id: btn_accion_global
                        readonly property string modo: {
                            switch (kar.filtro_estado) {
                                case "sin_preparar": return "encolar"
                                case "en_cola":      return "vaciar"
                                case "fallida":      return "reintentar"
                                case "no_aplica":    return "restaurar"
                                default:             return ""
                            }
                        }
                        readonly property bool habilitado: {
                            if (modo === "encolar")    return raiz.sel_count > 0 || raiz.sel_todos_completo || (kar.resumen.sin_preparar || 0) > 0
                            if (modo === "vaciar")     return !kar.procesando && (kar.resumen.en_cola || 0) > 0
                            if (modo === "reintentar") return !kar.procesando && (kar.resumen.fallida || 0) > 0
                            if (modo === "restaurar")  return (kar.resumen.no_aplica || 0) > 0
                            return false
                        }
                        readonly property string texto: {
                            if (modo === "encolar") {
                                if (raiz.sel_todos_completo) return "Encolar todo (" + (kar.resumen.sin_preparar || 0) + ")"
                                if (raiz.sel_count > 0)      return "Encolar " + raiz.sel_count + " seleccionada" + (raiz.sel_count !== 1 ? "s" : "")
                                return "Encolar todo (" + (kar.resumen.sin_preparar || 0) + ")"
                            }
                            if (modo === "vaciar")     return "Vaciar cola (" + (kar.resumen.en_cola || 0) + ")"
                            if (modo === "reintentar") return "Reintentar todas (" + (kar.resumen.fallida || 0) + ")"
                            if (modo === "restaurar")  return "Restaurar todas (" + (kar.resumen.no_aplica || 0) + ")"
                            return ""
                        }
                        readonly property bool primario: modo === "encolar"
                        readonly property color colorSemantico: {
                            if (modo === "vaciar")     return raiz.tema.advertencia
                            if (modo === "reintentar") return raiz.tema.acento
                            if (modo === "restaurar")  return raiz.tema.acento
                            return raiz.tema.acento
                        }
                        visible: modo !== ""
                        height: 34
                        width: Math.max(raiz.cW ? 140 : 170, _bagL.implicitWidth + 24)
                        radius: 17
                        opacity: habilitado ? 1.0 : 0.65
                        // Mismo issue que BtnControl: forzar Qt.color() para que
                        // los componentes .r .g .b funcionen sobre strings del tema.
                        color: {
                            if (!habilitado) return raiz.tema.superficieAlt
                            var c = primario ? Qt.color(raiz.tema.acento) : Qt.color(colorSemantico)
                            var a = primario
                                ? (_bagM.containsMouse ? 0.88 : 1.0)
                                : (_bagM.containsMouse ? 0.18 : 0.10)
                            return Qt.rgba(c.r, c.g, c.b, a)
                        }
                        // Cuando deshabilitado, siempre con borde para no quedar
                        // como rectángulo negro plano sobre superficie oscura.
                        border.color: !habilitado
                            ? raiz.tema.borde
                            : primario
                                ? "transparent"
                                : colorSemantico
                        border.width: (!habilitado || !primario) ? 1 : 0
                        AppText {
                            id: _bagL
                            anchors.centerIn: parent
                            width: Math.max(0, parent.width - 20)
                            text: btn_accion_global.texto
                            color: !btn_accion_global.habilitado
                                ? raiz.tema.textoMuted
                                : btn_accion_global.primario
                                    ? raiz.tema.textoSobreAcento
                                    : btn_accion_global.colorSemantico
                            font.pixelSize: UiTokens.fontSizeMd; font.weight: Font.DemiBold
                            horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                        }
                        MouseArea {
                            id: _bagM
                            anchors.fill: parent; hoverEnabled: true
                            enabled: btn_accion_global.habilitado
                            cursorShape: btn_accion_global.habilitado ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: {
                                switch (btn_accion_global.modo) {
                                    case "encolar":
                                        if (raiz.sel_todos_completo) {
                                            kar.encolar_todas_sin_preparar()
                                        } else if (raiz.sel_count > 0) {
                                            kar.encolar_pistas(raiz._idsSeleccionados())
                                        } else {
                                            // Sin seleccion: encolar TODO sin_preparar (no solo la pagina).
                                            kar.encolar_todas_sin_preparar()
                                        }
                                        raiz._limpiar()
                                        break
                                    case "vaciar":
                                        kar.vaciar_cola()
                                        break
                                    case "reintentar":
                                        kar.reintentar_todas_fallidas()
                                        break
                                    case "restaurar":
                                        // Restaurar todas: iteramos sobre la pagina visible. Si hay
                                        // mas que la pagina, requerimos snapshot completo.
                                        var ids = []
                                        for (var i = 0; i < kar.pistas.total; i++) {
                                            var p = kar.pistas.obtener(i)
                                            if (p && p.id !== undefined && p.id !== null) ids.push(p.id)
                                        }
                                        for (var j = 0; j < ids.length; j++) {
                                            kar.restaurar_no_aplica(ids[j])
                                        }
                                        break
                                }
                            }
                        }
                    }

                    Rectangle {
                        width: 34; height: 34; radius: 17
                        color: _refm.containsMouse ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.15) : raiz.tema.superficieAlt
                        border.color: raiz.tema.borde; border.width: 1
                        AppText { anchors.centerIn: parent; text: "↺"; font.pixelSize: 15; color: raiz.tema.textoSec }
                        MouseArea { id: _refm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: kar.cargar() }
                    }
                }

                // Banner: ofrecer seleccion completa cuando hay paginacion.
                // Solo en "sin_preparar" (unica pestana con seleccion).
                Rectangle {
                    Layout.fillWidth: true
                    visible: raiz.tab_permite_seleccion && master_st === 2 && kar.total_filtrado > vis_count && !sel_todos_completo
                    height: visible ? 36 : 0; radius: 7
                    color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.09)
                    border.color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.26); border.width: 1
                    RowLayout { anchors.fill: parent; anchors.leftMargin: UiTokens.spacing12; anchors.rightMargin: UiTokens.spacing12; spacing: UiTokens.spacing8
                        AppText { text: vis_count + " visibles seleccionadas."; color: raiz.tema.textoSec; font.pixelSize: UiTokens.fontSizeMd; Layout.fillWidth: true }
                        AppText { text: "Seleccionar todas las " + kar.total_filtrado; color: raiz.tema.acento; font.pixelSize: UiTokens.fontSizeMd; font.weight: Font.DemiBold
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { raiz._selTodos(); raiz.sel_todos_completo = true } }
                        }
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    visible: raiz.tab_permite_seleccion && sel_todos_completo
                    height: visible ? 36 : 0; radius: 7
                    color: Qt.rgba(raiz.tema.exito.r, raiz.tema.exito.g, raiz.tema.exito.b, 0.09)
                    border.color: Qt.rgba(raiz.tema.exito.r, raiz.tema.exito.g, raiz.tema.exito.b, 0.26); border.width: 1
                    RowLayout { anchors.fill: parent; anchors.leftMargin: UiTokens.spacing12; anchors.rightMargin: UiTokens.spacing12; spacing: UiTokens.spacing8
                        AppText { text: "Todas las " + kar.total_filtrado + " seleccionadas."; color: raiz.tema.textoSec; font.pixelSize: UiTokens.fontSizeMd; Layout.fillWidth: true }
                        AppText { text: "Cancelar seleccion"; color: raiz.tema.acento; font.pixelSize: UiTokens.fontSizeMd; font.weight: Font.DemiBold
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: raiz._limpiar() }
                        }
                    }
                }

                // Header de columnas (desktop). La columna "Progreso" solo
                // tiene sentido durante procesamiento (pestana en_cola).
                Rectangle {
                    Layout.fillWidth: true; visible: !raiz.cW && kar.pistas.total > 0
                    height: 30; radius: 7; color: raiz.tema.fondoElevado; border.color: raiz.tema.borde; border.width: 1
                    RowLayout { anchors.fill: parent; anchors.leftMargin: UiTokens.spacing10; anchors.rightMargin: UiTokens.spacing10; spacing: UiTokens.spacing8
                        Item { width: raiz.tab_permite_seleccion ? raiz.colChk : 0; visible: raiz.tab_permite_seleccion }
                        Item { width: raiz.colPortada }
                        AppText { text: "Pista"; color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.Bold; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                        AppText { text: "Estado"; color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.Bold; Layout.preferredWidth: raiz.colEstado; horizontalAlignment: Text.AlignHCenter }
                        AppText { text: "Progreso"; color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.Bold; Layout.preferredWidth: raiz.colProgreso; horizontalAlignment: Text.AlignHCenter; visible: raiz.mW && kar.filtro_estado === "en_cola" }
                        AppText { text: "Dur."; color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.Bold; Layout.preferredWidth: raiz.colDuracion; horizontalAlignment: Text.AlignHCenter; visible: raiz.mW }
                        AppText { text: "Acciones"; color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.Bold; Layout.preferredWidth: raiz.colAcciones; horizontalAlignment: Text.AlignHCenter }
                    }
                }

                // ListView
                //
                // `cacheBuffer: 0` evita el warning "DelegateModel::cancel: index
                // out of range" que ocurre cuando ListView pre-incuba delegates
                // fuera del viewport y el modelo se contrae (cambio de pestana
                // o de filtro reduce drasticamente el numero de filas). Sin
                // cache no se pre-incuba nada — los delegates solo se crean al
                // entrar en viewport, y nunca quedan delegates en cola apuntando
                // a indices invalidos.
                //
                // `reuseItems: true` reutiliza los delegates al hacer scroll, lo
                // que reduce alocacion/GC y elimina el flicker percibido al
                // cambiar de pestana sin perder responsividad.
                ListView {
                    id: lista_kar
                    objectName: "karaoke_listview"
                    Layout.fillWidth: true
                    Layout.preferredHeight: raiz._alturaLista()
                    clip: true; interactive: contentHeight > height; spacing: 5
                    model: kar.pistas; boundsBehavior: Flickable.StopAtBounds
                    cacheBuffer: 0
                    reuseItems: true
                    ScrollBar.vertical: AppScrollBar { tema: raiz.tema; policy: lista_kar.contentHeight > lista_kar.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff }
                    delegate: FilaDelegate { width: lista_kar.width }
                    Item {
                        anchors.fill: parent; visible: lista_kar.count === 0
                        EmptyState {
                            anchors.centerIn: parent; width: Math.min(parent.width, 440)
                            tema: raiz.tema
                            title: campo_busq.text !== "" ? "Sin resultados" : "Sin pistas en esta categoria"
                            description: campo_busq.text !== "" ? "Prueba con otro texto de busqueda."
                                : { "sin_preparar": "Todas las pistas ya tienen instrumental o estan en cola.",
                                    "en_cola":      "No hay pistas en cola ahora mismo.",
                                    "lista":        "Aun no hay pistas listas. Selecciona y encola pistas para procesarlas.",
                                    "fallida":      "No hay pistas con error de procesamiento.",
                                    "no_aplica":    "No hay pistas marcadas como no aplicables."
                                  }[kar.filtro_estado] || ""
                        }
                    }
                }

                // Paginacion
                RowLayout {
                    Layout.fillWidth: true; visible: kar.total_filtrado > 0; spacing: UiTokens.spacing4
                    AppText { text: raiz._textoRango(); color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                    component PagBtn: Rectangle {
                        id: _pb; property string texto: ""; property bool activo: true
                        signal clicked()
                        width: Math.max(28, _pbl.implicitWidth + 10); height: 28; radius: 7; opacity: activo ? 1.0 : 0.32
                        color: _pbm.containsMouse && activo ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.16) : raiz.tema.superficieAlt
                        border.color: raiz.tema.borde; border.width: 1
                        AppText { id: _pbl; anchors.centerIn: parent; text: _pb.texto; font.pixelSize: UiTokens.fontSizeMd; color: raiz.tema.textoSec }
                        MouseArea { id: _pbm; anchors.fill: parent; hoverEnabled: true; cursorShape: activo ? Qt.PointingHandCursor : Qt.ArrowCursor; enabled: activo; onClicked: _pb.clicked() }
                    }
                    PagBtn { texto: "«";   activo: kar.pagina_actual > 0; onClicked: kar.ir_a_pagina(0) }
                    PagBtn { texto: "−10"; visible: kar.total_paginas > 11 && kar.pagina_actual >= 10; activo: kar.pagina_actual >= 10; onClicked: kar.ir_a_pagina(Math.max(0, kar.pagina_actual - 10)) }
                    PagBtn { texto: "‹";   activo: kar.pagina_actual > 0; onClicked: kar.pagina_anterior() }
                    Row {
                        spacing: UiTokens.spacing4
                        Repeater {
                            model: Math.min(kar.total_paginas, 7)
                            delegate: Rectangle {
                                id: _pgItem
                                required property int index
                                readonly property int pag: {
                                    var tp = kar.total_paginas, cp = kar.pagina_actual, sh = Math.min(tp, 7)
                                    return Math.max(0, Math.min(cp - Math.floor(sh/2), tp - sh)) + index
                                }
                                readonly property bool actual: pag === kar.pagina_actual
                                readonly property real lum_ac: 0.299 * raiz.tema.acento.r + 0.587 * raiz.tema.acento.g + 0.114 * raiz.tema.acento.b
                                width: 28; height: 28; radius: 7
                                color: actual
                                    ? raiz.tema.acento
                                    : (_nm.containsMouse ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.14) : raiz.tema.superficieAlt)
                                border.color: actual ? raiz.tema.acento : raiz.tema.borde; border.width: 1
                                AppText {
                                    anchors.centerIn: parent
                                    text: _pgItem.pag + 1
                                    font.pixelSize: UiTokens.fontSizeMd
                                    font.weight: _pgItem.actual ? Font.DemiBold : Font.Normal
                                    color: _pgItem.actual
                                        ? raiz.tema.textoSobreAcento
                                        : raiz.tema.textoSec
                                }
                                MouseArea { id: _nm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: kar.ir_a_pagina(_pgItem.pag) }
                            }
                        }
                    }
                    PagBtn { texto: "›";   activo: kar.pagina_actual < kar.total_paginas - 1; onClicked: kar.pagina_siguiente() }
                    PagBtn { texto: "+10"; visible: kar.total_paginas > 11 && kar.pagina_actual <= kar.total_paginas - 11; activo: kar.pagina_actual <= kar.total_paginas - 11; onClicked: kar.ir_a_pagina(Math.min(kar.total_paginas-1, kar.pagina_actual+10)) }
                    PagBtn { texto: "»";   activo: kar.pagina_actual < kar.total_paginas - 1; onClicked: kar.ir_a_pagina(kar.total_paginas - 1) }
                    AppText { text: "Pag " + (kar.pagina_actual + 1) + " / " + kar.total_paginas; color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm }
                }
            }

            Item { Layout.fillWidth: true; height: UiTokens.spacing24 }
        }
    }

    // ── Delegate ──────────────────────────────────────────────────────────
    component FilaDelegate: Rectangle {
        id: fd
        required property int index

        readonly property var    datos:   kar.pistas.obtener(fd.index)
        readonly property int    pid:     (datos && datos.id !== undefined && datos.id !== null) ? parseInt(datos.id) : -1
        readonly property string titulo:  (datos && datos.titulo) || ""
        readonly property string artista: (datos && datos.artista_nombre) || ""
        readonly property string album:   (datos && datos.album_titulo) || ""
        readonly property real   dur:     (datos && datos.duracion_seg) || 0
        readonly property string kest:    (datos && datos.karaoke_estado) || "no_procesada"
        readonly property string portada: (datos && datos.album_portada_ruta) || ""
        readonly property real   prog:    (datos && datos.karaoke_progreso !== undefined && datos.karaoke_progreso !== null) ? Number(datos.karaoke_progreso) : 0
        readonly property string ecod:    (datos && datos.karaoke_error_codigo) || ""

        readonly property bool sel: {
            if (fd.pid < 0) return false
            if (raiz.sel_todos_completo) return true
            return raiz.sel_ids[String(fd.pid)] !== undefined
        }

        implicitHeight: raiz.cW ? _fdc.implicitHeight + 18 : Math.max(56, _fdd.implicitHeight + 14)
        radius: UiTokens.radiusSm
        color: sel ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.10) : (_fdm.containsMouse ? raiz.tema.hover : raiz.tema.superficieAlt)
        border.color: sel ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.36) : raiz.tema.borde
        border.width: sel ? 1.5 : 1
        MouseArea { id: _fdm; anchors.fill: parent; hoverEnabled: true; onClicked: if (fd.pid >= 0) raiz._toggle(fd.pid) }

        // Compact
        ColumnLayout {
            id: _fdc; visible: raiz.cW
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: UiTokens.spacing10 }
            spacing: 5
            RowLayout { Layout.fillWidth: true; spacing: 8
                // Checkbox solo en "sin_preparar"
                Item {
                    width: raiz.tab_permite_seleccion ? raiz.colChk : 0
                    height: raiz.colChk
                    visible: raiz.tab_permite_seleccion
                    CkBox { anchors.centerIn: parent; sel: fd.sel; onToggled: if (fd.pid >= 0) raiz._toggle(fd.pid) }
                }
                Rectangle { width: 32; height: 32; radius: UiTokens.radiusSm; color: raiz.tema.superficie; clip: true
                    Image { anchors.fill: parent; source: fd.portada ? UiUtils.toMediaSource(fd.portada) : ""; fillMode: Image.PreserveAspectCrop; visible: fd.portada !== "" && status !== Image.Error; asynchronous: true }
                    Image { id: _kp1Img; anchors.centerIn: parent; width: 16; height: 16; source: "../assets/icons/track.svg"; sourceSize.width: 32; sourceSize.height: 32; smooth: true; opacity: 0; visible: fd.portada === "" }
                    MultiEffect { visible: _kp1Img.visible; anchors.fill: _kp1Img; source: _kp1Img; colorization: 1.0; colorizationColor: raiz.tema.textoMuted }
                }
                ColumnLayout { Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: UiTokens.spacing2
                    AppText { text: fd.titulo; color: raiz.tema.texto; font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                    AppText { text: fd.artista + (fd.album ? " · " + fd.album : ""); color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm; elide: Text.ElideRight; Layout.fillWidth: true; visible: fd.artista !== "" || fd.album !== "" }
                }
                StatusBadge { tema: raiz.tema; text: raiz._etiq(fd.kest); tone: raiz._tono(fd.kest); compact: true; maxTextWidth: 88 }
            }
            // Mini barra de progreso del job (si esta procesando)
            Rectangle {
                visible: fd.kest === "procesando" && fd.prog > 0
                Layout.fillWidth: true; height: 4; radius: 2; color: raiz.tema.superficieAlt; clip: true
                Rectangle { width: parent.width * Math.max(0, Math.min(1, fd.prog)); height: parent.height; radius: 2; color: raiz.tema.acento }
            }
            // Mensaje de error (si fallida)
            AppText {
                visible: fd.kest === "fallida" && fd.ecod !== ""
                text: raiz._err_texto(fd.ecod); color: raiz.tema.peligro; font.pixelSize: UiTokens.fontSizeSm
            }
            // Acciones contextuales
            FilaAcciones { fd_pid: fd.pid; fd_titulo: fd.titulo; fd_kest: fd.kest }
        }

        // Desktop
        RowLayout {
            id: _fdd; visible: !raiz.cW
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; leftMargin: UiTokens.spacing10; rightMargin: UiTokens.spacing10 }
            spacing: 8
            // Checkbox solo en "sin_preparar"
            Item {
                width: raiz.tab_permite_seleccion ? raiz.colChk : 0
                height: raiz.colChk
                visible: raiz.tab_permite_seleccion
                CkBox { anchors.centerIn: parent; sel: fd.sel; onToggled: if (fd.pid >= 0) raiz._toggle(fd.pid) }
            }
            Rectangle {
                width: raiz.colPortada; height: raiz.colPortada; radius: UiTokens.radiusSm; color: raiz.tema.superficie; clip: true
                Image { anchors.fill: parent; source: fd.portada ? UiUtils.toMediaSource(fd.portada) : ""; fillMode: Image.PreserveAspectCrop; visible: fd.portada !== "" && status !== Image.Error; asynchronous: true }
                Image { id: _kp2Img; anchors.centerIn: parent; width: 18; height: 18; source: "../assets/icons/track.svg"; sourceSize.width: 36; sourceSize.height: 36; smooth: true; opacity: 0; visible: fd.portada === "" || parent.children[0].status === Image.Error }
                MultiEffect { visible: _kp2Img.visible; anchors.fill: _kp2Img; source: _kp2Img; colorization: 1.0; colorizationColor: raiz.tema.textoMuted }
            }
            ColumnLayout { Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: UiTokens.spacing2
                AppText { text: fd.titulo; color: raiz.tema.texto; font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                AppText {
                    text: {
                        if (fd.kest === "fallida" && fd.ecod !== "") return raiz._err_texto(fd.ecod)
                        if (fd.artista !== "" || fd.album !== "") return fd.artista + (fd.album ? " · " + fd.album : "")
                        return ""
                    }
                    color: (fd.kest === "fallida" && fd.ecod !== "") ? raiz.tema.peligro : raiz.tema.textoMuted
                    font.pixelSize: UiTokens.fontSizeSm; elide: Text.ElideRight; Layout.fillWidth: true
                }
            }
            Item {
                Layout.preferredWidth: raiz.colEstado; Layout.preferredHeight: 22; Layout.alignment: Qt.AlignVCenter
                StatusBadge { anchors.centerIn: parent; tema: raiz.tema; text: raiz._etiq(fd.kest); tone: raiz._tono(fd.kest); compact: true; maxTextWidth: raiz.colEstado - 4 }
            }
            // Columna "Progreso" solo en pestana "en_cola"; en otras no aplica
            // y la columna se colapsa para dar mas espacio a las acciones.
            Item {
                width: (raiz.mW && kar.filtro_estado === "en_cola") ? raiz.colProgreso : 0
                visible: raiz.mW && kar.filtro_estado === "en_cola"
                height: 16
                Rectangle {
                    visible: fd.kest === "procesando"
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - 4; height: 5; radius: 2.5; color: raiz.tema.superficieAlt; clip: true
                    Rectangle { width: parent.width * Math.max(0, Math.min(1, fd.prog)); height: parent.height; radius: 2.5; color: raiz.tema.acento }
                }
                AppText {
                    visible: fd.kest !== "procesando"
                    anchors.centerIn: parent
                    text: fd.kest === "en_cola" ? "En cola" : "—"
                    color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm
                }
            }
            AppText { text: raiz._dur(fd.dur); color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm; Layout.preferredWidth: raiz.colDuracion; horizontalAlignment: Text.AlignHCenter; visible: raiz.mW }
            FilaAcciones { fd_pid: fd.pid; fd_titulo: fd.titulo; fd_kest: fd.kest; Layout.preferredWidth: raiz.colAcciones }
        }
    }

    // ── Acciones contextuales por estado ───────────────────────────────
    component FilaAcciones: Item {
        id: _ac
        property int    fd_pid: -1
        property string fd_titulo: ""
        property string fd_kest: "no_procesada"
        implicitWidth: rowAcc.implicitWidth
        implicitHeight: rowAcc.implicitHeight
        Row {
            id: rowAcc
            anchors.centerIn: parent
            spacing: UiTokens.spacing4; layoutDirection: raiz.cW ? Qt.LeftToRight : Qt.RightToLeft

            // no_procesada
            AccBtn { texto: "Encolar"; tono: "accent";
                visible: _ac.fd_kest === "no_procesada"
                onClicked: kar.encolar_pistas([_ac.fd_pid]) }
            AccBtn { texto: "No aplica"; tono: "neutral";
                visible: _ac.fd_kest === "no_procesada"
                onClicked: kar.marcar_no_aplica(_ac.fd_pid) }
            AccBtn { texto: "Asignar inst."; tono: "neutral";
                visible: _ac.fd_kest === "no_procesada"
                onClicked: raiz._abrirDialogoInstrumental(_ac.fd_pid, _ac.fd_titulo) }

            // en_cola / procesando — ambos usan el cancelar robusto por pista:
            // funciona aunque el estado esté desincronizado o el worker trabado.
            AccBtn { texto: "Sacar de cola"; tono: "warning";
                visible: _ac.fd_kest === "en_cola"
                onClicked: kar.cancelar_pista(_ac.fd_pid) }
            AccBtn { texto: "Cancelar"; tono: "danger";
                visible: _ac.fd_kest === "procesando"
                onClicked: kar.cancelar_pista(_ac.fd_pid) }

            // fallida
            AccBtn { texto: "Reintentar"; tono: "info";
                visible: _ac.fd_kest === "fallida"
                onClicked: kar.reintentar_fallida(_ac.fd_pid) }
            AccBtn { texto: "Ver error"; tono: "neutral";
                visible: _ac.fd_kest === "fallida"
                onClicked: raiz._abrirErrorDetalle(_ac.fd_pid) }
            AccBtn { texto: "Resetear"; tono: "neutral";
                visible: _ac.fd_kest === "fallida"
                onClicked: kar.resetear_estado(_ac.fd_pid) }

            // lista
            AccBtn { texto: "Activar karaoke"; tono: "accent";
                visible: _ac.fd_kest === "lista" && rep.pista_activa && rep.pista_activa.id === _ac.fd_pid && rep.karaoke_disponible
                onClicked: rep.alternar_karaoke() }
            AccBtn { texto: "Reprocesar"; tono: "info";
                visible: _ac.fd_kest === "lista"
                onClicked: kar.reprocesar(_ac.fd_pid) }
            AccBtn { texto: "Resetear"; tono: "neutral";
                visible: _ac.fd_kest === "lista"
                onClicked: kar.resetear_estado(_ac.fd_pid) }

            // no_aplica
            AccBtn { texto: "Restaurar"; tono: "info";
                visible: _ac.fd_kest === "no_aplica"
                onClicked: kar.restaurar_no_aplica(_ac.fd_pid) }
        }
    }

    // ── Checkbox ──────────────────────────────────────────────────────
    component CkBox: Rectangle {
        id: _ck
        property bool sel: false
        property bool indeterminate: false
        signal toggled()
        width: raiz.colChk; height: raiz.colChk; radius: 5
        color: (sel || indeterminate) ? raiz.tema.acento : raiz.tema.superficieAlt
        border.color: (sel || indeterminate) ? raiz.tema.acento : raiz.tema.borde; border.width: 1.5
        Rectangle { visible: _ck.indeterminate && !_ck.sel; anchors.centerIn: parent; width: 10; height: 2; radius: 1; color: raiz.tema.textoSobreAcento }
        Image {
            id: _ckChk
            visible: _ck.sel
            anchors.centerIn: parent
            width: 12; height: 12
            source: "../assets/icons/check.svg"
            sourceSize.width: 24; sourceSize.height: 24
            smooth: true
            opacity: 0
        }
        MultiEffect {
            visible: _ckChk.visible
            anchors.fill: _ckChk
            source: _ckChk
            colorization: 1.0
            colorizationColor: raiz.tema.textoSobreAcento
        }
        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: function(mouse) { mouse.accepted = true; _ck.toggled() } }
    }

    // ── Boton de accion en fila ───────────────────────────────────────
    //
    // Estilo ghost/outlined: borde del color semantico + fondo tinted muy
    // sutil. Hover sube el alpha pero NO genera glow. Mantiene legibilidad
    // sobre la fila resaltada por seleccion sin competir con el contenido.
    component AccBtn: Rectangle {
        id: _ab
        property string texto: ""
        property string tono: "accent"
        signal clicked()
        function _bg() {
            if (tono === "danger")  return Qt.rgba(raiz.tema.peligro.r,    raiz.tema.peligro.g,    raiz.tema.peligro.b,    _abm.containsMouse ? 0.18 : 0.09)
            if (tono === "neutral") return Qt.rgba(raiz.tema.textoMuted.r, raiz.tema.textoMuted.g, raiz.tema.textoMuted.b, _abm.containsMouse ? 0.16 : 0.08)
            if (tono === "info")    return Qt.rgba(raiz.tema.acento.r,     raiz.tema.acento.g,     raiz.tema.acento.b,     _abm.containsMouse ? 0.20 : 0.10)
            if (tono === "warning") return Qt.rgba(raiz.tema.advertencia.r, raiz.tema.advertencia.g, raiz.tema.advertencia.b, _abm.containsMouse ? 0.18 : 0.09)
            return Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, _abm.containsMouse ? 0.22 : 0.12)
        }
        function _fc() {
            if (tono === "danger")  return raiz.tema.peligro
            if (tono === "neutral") return raiz.tema.textoSec
            if (tono === "info")    return raiz.tema.acento
            if (tono === "warning") return raiz.tema.advertencia
            return raiz.tema.acento
        }
        implicitWidth: Math.max(56, _abl.implicitWidth + 16)
        implicitHeight: 26; height: 26; radius: 13; clip: true
        color: _bg(); border.color: _fc(); border.width: 1
        AppText { id: _abl; anchors.centerIn: parent; width: Math.max(0, parent.width - 14); text: _ab.texto; color: _ab._fc(); font.pixelSize: UiTokens.fontSizeSm; font.weight: Font.DemiBold; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight }
        MouseArea { id: _abm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: function(mouse) { mouse.accepted = true; _ab.clicked() } }
    }

    // ── Ciclo de vida ─────────────────────────────────────────────────
    Component.onCompleted: {
        var tabGuardada = cfg.obtener("karaoke_tab_activa") || "sin_preparar"
        kar.establecer_filtro_estado(tabGuardada)
        // El diagnóstico del backend se dispara al arranque de la app
        // (main_ui.py), por lo que normalmente ya está resuelto al llegar aquí.
        // Solo re-detectamos si todavía no lo está: cubre el caso de navegar
        // muy rápido antes de que termine la detección inicial.
        if (!kar.backend_listo)
            kar.detectar_backend()
    }
    onVisibleChanged: {
        if (!visible) {
            cfg.guardar("karaoke_tab_activa", kar.filtro_estado)
        } else {
            kar.cargar()
            // Re-detectar solo si el backend no está listo: evita relanzar un
            // subprocess de diagnóstico en cada entrada cuando ya quedó
            // confirmado, pero se auto-cura si el usuario instaló Demucs/ffmpeg
            // a mitad de sesión (el botón "Re-detectar" cubre el refresco manual).
            if (!kar.backend_listo)
                kar.detectar_backend()
        }
    }
}
