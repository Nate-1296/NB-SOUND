import QtQuick
import QtQuick.Layouts

AppCard {
    id: panel
    property string title: "Procesando"
    property string subtitle: ""
    property real ratio: 0
    property int processed: 0
    property int total: 0
    property string stage: ""
    property string eta: ""
    property bool indeterminate: false
    property string helper: ""

    RowLayout {
        Layout.fillWidth: true
        AppText { text: panel.title; font.pixelSize: 17; font.bold: true; color: panel.tema.texto; Layout.fillWidth: true }
        StatusBadge {
            tema: panel.tema
            text: panel.indeterminate ? "Preparando" : (panel.total > 0 ? (panel.processed + "/" + panel.total) : "Lista")
            tone: panel.indeterminate ? "info" : "neutral"
        }
        AppText {
            text: panel.indeterminate
                  ? "Preparando…"
                  : (panel.total > 0 ? (Math.round(Math.max(0, Math.min(1, panel.ratio)) * 100) + "%") : "")
            font.pixelSize: UiTokens.fontSizeMd
            color: panel.tema.textoSec
        }
    }

    Rectangle {
        id: barraBase
        Layout.fillWidth: true
        height: 8
        radius: 4
        color: panel.tema.superficieAlt
        clip: true
        Rectangle {
            visible: !panel.indeterminate
            width: parent.width * Math.max(0, Math.min(1, panel.ratio))
            height: parent.height
            radius: 4
            color: panel.tema.acento
            Behavior on width { NumberAnimation { duration: 220 } }
        }
        Rectangle {
            id: barraIndeterminada
            visible: panel.indeterminate
            width: parent.width * 0.28
            height: parent.height
            radius: 4
            color: panel.tema.acento
            x: -width

            SequentialAnimation on x {
                running: panel.indeterminate
                loops: Animation.Infinite
                NumberAnimation { from: -barraIndeterminada.width; to: barraBase.width; duration: 1100; easing.type: Easing.InOutQuad }
            }
        }
    }

    AppText {
        text: !panel.indeterminate && panel.total > 0 ? (panel.processed + " de " + panel.total + " archivos") : "Calculando volumen de archivos…"
        color: panel.tema.textoSec
        font.pixelSize: UiTokens.fontSizeMd
    }
    AppText { text: panel.subtitle; color: panel.tema.textoSec; font.pixelSize: UiTokens.fontSizeMd; elide: Text.ElideMiddle; Layout.fillWidth: true; visible: panel.subtitle !== "" }
    AppText {
        text: panel.stage !== "" ? ("Etapa: " + panel.stage) : ""
        color: panel.tema.textoMuted
        font.pixelSize: UiTokens.fontSizeSm
        wrapMode: Text.Wrap
        maximumLineCount: 2
        elide: Text.ElideRight
        Layout.fillWidth: true
    }
    AppText { text: panel.eta !== "" ? ("ETA aprox: " + panel.eta) : ""; color: panel.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm }
    AppText { text: panel.helper; color: panel.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm; wrapMode: Text.Wrap; lineHeight: 1.15; Layout.fillWidth: true; visible: panel.helper !== "" }
}
