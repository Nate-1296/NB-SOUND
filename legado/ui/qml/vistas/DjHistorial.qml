import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import "../componentes"

// =============================================================================
// DjHistorial — Workspace de sesiones generadas
//
// Reglas UX (post-revision humana):
//   - Filtro de estado como TABS, no como dropdown (el usuario no debe abrir
//     un combobox para algo tan visible).
//   - Cada accion tiene una etiqueta humana clara: "Reproducir", "Abrir",
//     "Generar variante", "Exportar a playlist", "Eliminar".
//   - Confirmaciones (eliminar) usan UN solo Dialog compartido a nivel de
//     la vista — NO uno por fila (evita binding loops y waste de memoria).
//   - Los helpers garantizan que NUNCA se entrega undefined a un binding de
//     string/bool. El default explicito es responsabilidad de la vista, no
//     del consumidor.
// =============================================================================

Rectangle {
    id: raiz
    color: "transparent"

    required property var tema
    property var shell: null
    required property var formatDur
    required property var formatFecha
    required property bool cW
    required property bool mW
    required property bool wW

    signal irAConstruir()
    signal irASesion()

    // Filtros aplicados (sincronizados con el backend via slot del modelo)
    property string filtro_estado: ""

    // Estado del dialogo de confirmacion (uno solo a nivel vista)
    property int    _id_a_eliminar: 0
    property string _prompt_a_eliminar: ""

    // Estados validos del backend (dj_sesiones.estado)
    readonly property var estados: [
        { id: "",             label: "Todas" },
        { id: "lista",        label: "Listas" },
        { id: "construyendo", label: "En curso" },
        { id: "finalizada",   label: "Completadas" },
        { id: "descartada",   label: "Descartadas" },
    ]

    // ─── Helpers garantizados ──────────────────────────────────────────
    //
    // Cada helper devuelve siempre el tipo que su consumidor declara. Eso
    // elimina la clase entera de warnings "Unable to assign [undefined]".

    function _str(valor) {
        return (valor === undefined || valor === null) ? "" : String(valor)
    }
    function _num(valor) {
        var n = Number(valor)
        return (isNaN(n) || valor === undefined || valor === null) ? 0 : n
    }
    function _label_estado(estado) {
        // Garantiza string. NO retorna undefined ni el parametro tal cual.
        var e = _str(estado)
        switch (e) {
            case "lista":         return "Lista"
            case "construyendo":  return "En curso"
            case "finalizada":    return "Completa"
            case "descartada":    return "Descartada"
            case "error":         return "Con errores"
            default:               return e || "—"
        }
    }
    function _tono_estado(estado) {
        switch (_str(estado)) {
            case "lista":         return "success"
            case "construyendo":  return "info"
            case "finalizada":    return "neutral"
            case "descartada":    return "neutral"
            case "error":         return "danger"
            default:               return "neutral"
        }
    }
    function _toast(msg, tono) { if (shell) shell.mostrar_toast_global(msg, tono || "info") }
    function _pedir_eliminar(datos) {
        raiz._id_a_eliminar = (datos && datos.id) ? datos.id : 0
        raiz._prompt_a_eliminar = (datos && datos.prompt) ? String(datos.prompt) : "(sin prompt)"
        confirm_eliminar.open()
    }
    function _cargar_y_reproducir(id) {
        djPrivado.cargar_sesion_anterior(parseInt(id))
        djPrivado.reproducir_sesion()
    }
    function _cargar_y_abrir(id) {
        djPrivado.cargar_sesion_anterior(parseInt(id))
        raiz.irASesion()
    }

    Component.onCompleted: djPrivado.cargar_historial()

    // ═══════════════════════════════════════════════════════════════════
    // Layout
    // ═══════════════════════════════════════════════════════════════════
    ColumnLayout {
        anchors.fill: parent
        spacing: UiTokens.spacing12

        // ── Card superior: titulo + descripcion + busqueda + tabs ───
        AppCard {
            Layout.fillWidth: true
            tema: raiz.tema
            padding: UiTokens.spacing14

            RowLayout {
                Layout.fillWidth: true
                spacing: UiTokens.spacing10
                ColumnLayout {
                    spacing: UiTokens.spacing2; Layout.fillWidth: true
                    AppText {
                        text: "Tus sesiones"
                        color: raiz.tema.texto
                        font.pixelSize: 17; font.weight: Font.DemiBold
                    }
                    AppText {
                        text: "Cada sesión es una experiencia que construiste con un prompt. Reproducí cualquiera, generá variantes o expórtala como playlist."
                        color: raiz.tema.textoMuted
                        font.pixelSize: UiTokens.fontSizeSm; wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
                DjHistorialAccion {
                    tema: raiz.tema
                    texto: raiz.cW ? "" : "Actualizar"
                    iconSource: "../assets/icons/sync.svg"
                    ayuda: "Recargar el historial"
                    onActivada: djPrivado.cargar_historial()
                }
            }

            // Buscador (busqueda por prompt)
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 36
                radius: UiTokens.radiusSm
                color: raiz.tema.superficieAlt
                border.color: busc.activeFocus ? raiz.tema.acento : raiz.tema.borde
                border.width: 1
                TextField {
                    id: busc
                    anchors.fill: parent
                    anchors.leftMargin: UiTokens.spacing12; anchors.rightMargin: UiTokens.spacing12
                    verticalAlignment: TextInput.AlignVCenter
                    placeholderText: "Buscar por descripción: cinemático, voces femeninas, para correr…"
                    inputMethodHints: Qt.ImhPreferLowercase
                    placeholderTextColor: raiz.tema.textoMuted
                    color: raiz.tema.texto
                    selectByMouse: true
                    background: Item {}
                    onTextChanged: busc_debounce.restart()
                    Timer {
                        id: busc_debounce
                        interval: 220
                        onTriggered: djPrivado.establecer_filtro_historial_texto(busc.text)
                    }
                }
            }

            // Tabs de filtro de estado
            Flow {
                Layout.fillWidth: true
                spacing: UiTokens.spacing6
                Repeater {
                    model: raiz.estados
                    delegate: Rectangle {
                        readonly property bool activo: raiz.filtro_estado === modelData.id
                        height: 28
                        width: tab_lbl.implicitWidth + 22
                        radius: UiTokens.radiusLg
                        color: activo
                            ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.20)
                            : (tab_ma.containsMouse
                                ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.08)
                                : raiz.tema.superficieAlt)
                        border.color: activo ? raiz.tema.acento : raiz.tema.borde
                        border.width: 1
                        AppText {
                            id: tab_lbl
                            anchors.centerIn: parent
                            text: raiz._str(modelData.label)
                            color: parent.activo ? raiz.tema.acento : raiz.tema.textoSec
                            font.pixelSize: UiTokens.fontSizeMd; font.weight: parent.activo ? Font.DemiBold : Font.Normal
                        }
                        MouseArea {
                            id: tab_ma
                            anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                raiz.filtro_estado = String(modelData.id)
                                djPrivado.establecer_filtro_historial_estado(raiz.filtro_estado)
                            }
                        }
                    }
                }
            }
        }

        // ── Tabla de sesiones ───────────────────────────────────────
        AppCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            tema: raiz.tema
            padding: UiTokens.spacing10

            // Header de tabla (solo en desktop). Centrado para alinear con
            // el contenido (que también está centrado en columnas numéricas).
            Rectangle {
                Layout.fillWidth: true
                visible: raiz.mW && djPrivado.historial.total > 0
                implicitHeight: 30
                radius: 6
                color: raiz.tema.fondoElevado
                border.color: raiz.tema.borde; border.width: 1
                // Anchos en sync con las celdas del delegate de cada fila.
                readonly property int acciones_w: raiz.wW ? 460 : 240
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: UiTokens.spacing12; anchors.rightMargin: UiTokens.spacing8
                    spacing: UiTokens.spacing10
                    AppText { text: "Sesión";   color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.Bold; Layout.fillWidth: true }
                    AppText { text: "Estado";   color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.Bold; Layout.preferredWidth: 88;  horizontalAlignment: Text.AlignHCenter }
                    AppText { text: "Pistas";   color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.Bold; Layout.preferredWidth: 56;  horizontalAlignment: Text.AlignHCenter }
                    AppText { text: "Mezclas";  color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.Bold; Layout.preferredWidth: 68;  horizontalAlignment: Text.AlignHCenter; visible: raiz.wW }
                    AppText { text: "Duración"; color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.Bold; Layout.preferredWidth: 78;  horizontalAlignment: Text.AlignHCenter }
                    AppText { text: "Creada";   color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.Bold; Layout.preferredWidth: 130; horizontalAlignment: Text.AlignHCenter; visible: raiz.wW }
                    AppText { text: "Acciones"; color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.Bold; Layout.preferredWidth: parent.parent.acciones_w; horizontalAlignment: Text.AlignHCenter }
                }
            }

            // Lista
            ListView {
                id: lista_hist
                Layout.fillWidth: true
                Layout.fillHeight: true
                model: djPrivado.historial
                clip: true
                spacing: UiTokens.spacing4
                cacheBuffer: 0
                reuseItems: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: AppScrollBar { tema: raiz.tema; policy: lista_hist.contentHeight > lista_hist.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff }

                delegate: Rectangle {
                    id: fila_hist
                    required property int index
                    width: lista_hist.width
                    // Defensivo: si el modelo aun no produjo este indice, datos es {}.
                    readonly property var datos: djPrivado.historial.obtener(index) || ({})
                    readonly property int  d_id:     raiz._num(datos.id)
                    readonly property string d_prompt:  raiz._str(datos.prompt)
                    readonly property string d_estado:  raiz._str(datos.estado)
                    readonly property int    d_minutos: raiz._num(datos.minutos)
                    readonly property int    d_artistas: raiz._num(datos.artistas_distintos)
                    readonly property int    d_pistas:  raiz._num(datos.total_pistas)
                    readonly property int    d_trans_b: raiz._num(datos.transiciones_buenas)
                    readonly property int    d_trans_t: raiz._num(datos.transiciones_total)
                    readonly property real   d_dur:    raiz._num(datos.duracion_seg)
                    readonly property string d_creado: raiz._str(datos.creado_en)
                    readonly property bool   es_actual: d_id > 0 && djPrivado.sesion_id === d_id

                    radius: UiTokens.radiusSm
                    color: hist_ma.containsMouse ? raiz.tema.hover : raiz.tema.superficieAlt
                    border.color: es_actual ? raiz.tema.acento : "transparent"
                    border.width: es_actual ? 1 : 0
                    implicitHeight: raiz.mW ? 56 : 92

                    MouseArea {
                        id: hist_ma
                        anchors.fill: parent; hoverEnabled: true
                    }

                    // ── Desktop (mW) ────────────────────────────────────
                    RowLayout {
                        visible: raiz.mW
                        anchors.fill: parent
                        anchors.leftMargin: UiTokens.spacing12; anchors.rightMargin: UiTokens.spacing8
                        spacing: UiTokens.spacing10
                        ColumnLayout {
                            Layout.fillWidth: true; Layout.minimumWidth: 0
                            spacing: UiTokens.spacing2
                            AppText {
                                text: fila_hist.d_prompt || "(sin prompt)"
                                color: raiz.tema.texto
                                font.pixelSize: UiTokens.fontSizeBase
                                font.weight: fila_hist.es_actual ? Font.DemiBold : Font.Normal
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            AppText {
                                text: "objetivo " + fila_hist.d_minutos + " min · " + fila_hist.d_artistas + " artistas distintos"
                                color: raiz.tema.textoMuted
                                font.pixelSize: UiTokens.fontSizeSm
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                        }
                        StatusBadge {
                            tema: raiz.tema
                            text: raiz._label_estado(fila_hist.d_estado)
                            tone: raiz._tono_estado(fila_hist.d_estado)
                            compact: true
                            maxTextWidth: 80
                            Layout.preferredWidth: 88
                            Layout.alignment: Qt.AlignHCenter
                        }
                        AppText {
                            text: String(fila_hist.d_pistas)
                            color: raiz.tema.textoSec; font.pixelSize: UiTokens.fontSizeMd
                            Layout.preferredWidth: 56; horizontalAlignment: Text.AlignHCenter
                        }
                        AppText {
                            visible: raiz.wW
                            text: fila_hist.d_trans_t > 0
                                ? (fila_hist.d_trans_b + "/" + fila_hist.d_trans_t)
                                : "—"
                            color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm
                            Layout.preferredWidth: 68; horizontalAlignment: Text.AlignHCenter
                        }
                        AppText {
                            text: raiz._str(raiz.formatDur(fila_hist.d_dur))
                            color: raiz.tema.textoSec; font.pixelSize: UiTokens.fontSizeMd
                            Layout.preferredWidth: 78; horizontalAlignment: Text.AlignHCenter
                        }
                        AppText {
                            visible: raiz.wW
                            text: raiz._str(raiz.formatFecha(fila_hist.d_creado))
                            color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm
                            Layout.preferredWidth: 130; horizontalAlignment: Text.AlignHCenter
                        }
                        // Acciones con texto + SVG. En ancho extra (wW) se
                        // muestran las 4 con texto. En ancho medio (mW)
                        // sólo "Reproducir" mantiene texto, los demás
                        // colapsan a icono para evitar el desborde de la
                        // columna de acciones.
                        RowLayout {
                            Layout.preferredWidth: raiz.wW ? 460 : 240
                            Layout.maximumWidth: raiz.wW ? 460 : 240
                            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                            spacing: UiTokens.spacing6

                            DjHistorialAccion {
                                tema: raiz.tema
                                texto: "Reproducir"
                                iconSource: "../assets/icons/play.svg"
                                primario: true
                                onActivada: raiz._cargar_y_reproducir(fila_hist.d_id)
                            }
                            DjHistorialAccion {
                                tema: raiz.tema
                                texto: raiz.wW ? "Cargar sesión" : ""
                                iconSource: "../assets/icons/import.svg"
                                onActivada: raiz._cargar_y_abrir(fila_hist.d_id)
                            }
                            DjHistorialAccion {
                                tema: raiz.tema
                                texto: raiz.wW ? "Regenerar" : ""
                                iconSource: "../assets/icons/sync.svg"
                                onActivada: djPrivado.duplicar_sesion(fila_hist.d_id)
                            }
                            DjHistorialAccion {
                                tema: raiz.tema
                                texto: raiz.wW ? "Eliminar" : ""
                                iconSource: "../assets/icons/trash.svg"
                                peligroso: true
                                onActivada: raiz._pedir_eliminar(fila_hist.datos)
                            }
                        }
                    }

                    // ── Compact (cW) ────────────────────────────────────
                    ColumnLayout {
                        visible: !raiz.mW
                        anchors.fill: parent
                        anchors.margins: UiTokens.spacing10
                        spacing: UiTokens.spacing4
                        RowLayout {
                            Layout.fillWidth: true; spacing: UiTokens.spacing6
                            AppText {
                                text: fila_hist.d_prompt || "(sin prompt)"
                                color: raiz.tema.texto
                                font.pixelSize: UiTokens.fontSizeBase
                                font.weight: fila_hist.es_actual ? Font.DemiBold : Font.Normal
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            StatusBadge {
                                tema: raiz.tema
                                text: raiz._label_estado(fila_hist.d_estado)
                                tone: raiz._tono_estado(fila_hist.d_estado)
                                compact: true
                                maxTextWidth: 80
                            }
                        }
                        AppText {
                            text: fila_hist.d_pistas + " pistas · " + raiz._str(raiz.formatDur(fila_hist.d_dur)) + " · " + raiz._str(raiz.formatFecha(fila_hist.d_creado))
                            color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Row {
                            spacing: UiTokens.spacing6
                            DjHistorialAccion {
                                tema: raiz.tema
                                texto: "Reproducir"
                                iconSource: "../assets/icons/play.svg"
                                primario: true
                                ayuda: "Reproducir esta sesión ahora"
                                onActivada: raiz._cargar_y_reproducir(fila_hist.d_id)
                            }
                            DjHistorialAccion {
                                tema: raiz.tema
                                iconSource: "../assets/icons/import.svg"
                                ayuda: "Cargar sesión"
                                onActivada: raiz._cargar_y_abrir(fila_hist.d_id)
                            }
                            DjHistorialAccion {
                                tema: raiz.tema
                                iconSource: "../assets/icons/sync.svg"
                                ayuda: "Regenerar (misma idea, otra mezcla)"
                                onActivada: djPrivado.duplicar_sesion(fila_hist.d_id)
                            }
                            DjHistorialAccion {
                                tema: raiz.tema
                                iconSource: "../assets/icons/trash.svg"
                                peligroso: true
                                ayuda: "Eliminar"
                                onActivada: raiz._pedir_eliminar(fila_hist.datos)
                            }
                        }
                    }
                }

                // Estado vacio
                Item {
                    anchors.fill: parent
                    visible: djPrivado.historial.total === 0
                    EmptyState {
                        anchors.centerIn: parent
                        width: Math.min(parent.width, 400)
                        tema: raiz.tema
                        title: "Sin sesiones aún"
                        description: "Construye tu primera sesión en Construir y aparecerá aquí."
                    }
                }
            }
        }
    }

    // ── Popup ÚNICO de confirmación (a nivel vista) ─────────────────
    //
    // Migrado al patrón Popup de VistaConfiguracion: background propio,
    // botones locales con texto contextual ("Sí, borrarla" en vez de
    // "Confirmar"). El texto explica claramente lo que pasa.
    Popup {
        id: confirm_eliminar
        objectName: "popup_dj_confirmar_eliminar"
        modal: true; focus: true
        parent: Overlay.overlay
        x: Math.round((parent.width - width) / 2)
        y: Math.round((parent.height - height) / 2)
        width: Math.min(480, parent.width - 40)
        height: confCol.implicitHeight + 36
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: 12; color: raiz.tema.superficie
            border.width: 1
            border.color: raiz.tema.peligro
        }
        contentItem: ColumnLayout {
            id: confCol
            anchors.fill: parent
            anchors.margins: 18
            spacing: UiTokens.spacing10
            AppText {
                text: "¿Borrar esta sesión?"
                font.pixelSize: UiTokens.fontSizeXl; font.weight: Font.DemiBold
                color: raiz.tema.texto
            }
            AppText {
                text: "“" + raiz._prompt_a_eliminar + "”"
                color: raiz.tema.texto
                font.pixelSize: UiTokens.fontSizeBase; font.italic: true
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            AppText {
                text: "Se eliminará del historial. Las canciones reales no se borran. Esta acción no se puede deshacer."
                color: raiz.tema.textoMuted
                font.pixelSize: UiTokens.fontSizeMd
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: UiTokens.spacing4
                spacing: UiTokens.spacing10
                Item { Layout.fillWidth: true }
                Rectangle {
                    implicitWidth: 130; implicitHeight: 36; radius: 18
                    color: cancel_ma.containsMouse ? raiz.tema.hover : raiz.tema.superficieAlt
                    border.color: raiz.tema.borde; border.width: 1
                    AppText {
                        anchors.centerIn: parent; text: "No, conservarla"
                        color: raiz.tema.texto; font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold
                    }
                    MouseArea {
                        id: cancel_ma
                        anchors.fill: parent; hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            raiz._id_a_eliminar = 0
                            raiz._prompt_a_eliminar = ""
                            confirm_eliminar.close()
                        }
                    }
                }
                Rectangle {
                    implicitWidth: 170; implicitHeight: 36; radius: 18
                    color: del_ma.containsMouse
                        ? Qt.rgba(raiz.tema.peligro.r, raiz.tema.peligro.g, raiz.tema.peligro.b, 0.16)
                        : Qt.rgba(raiz.tema.peligro.r, raiz.tema.peligro.g, raiz.tema.peligro.b, 0.06)
                    border.color: raiz.tema.peligro; border.width: 1
                    AppText {
                        anchors.centerIn: parent
                        text: "Sí, borrar esta sesión"
                        color: raiz.tema.peligro
                        font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold
                    }
                    MouseArea {
                        id: del_ma
                        anchors.fill: parent; hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (raiz._id_a_eliminar > 0) djPrivado.eliminar_sesion(raiz._id_a_eliminar)
                            raiz._id_a_eliminar = 0
                            raiz._prompt_a_eliminar = ""
                            confirm_eliminar.close()
                        }
                    }
                }
            }
        }
    }
}
