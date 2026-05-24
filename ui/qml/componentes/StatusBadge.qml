import QtQuick

Rectangle {
    id: badge
    property var tema: temaUi
    property string text: ""
    property string tone: "neutral" // neutral | success | warning | danger | info
    property int maxTextWidth: 160
    property bool compact: false

    radius: UiTokens.radiusMd
    implicitHeight: compact ? 20 : 22
    implicitWidth: Math.max(compact ? 44 : 56, Math.min(txt.implicitWidth + (compact ? 12 : 16), maxTextWidth + (compact ? 12 : 16)))
    width: implicitWidth
    height: implicitHeight
    clip: true

    function _toneColor() {
        if (tone === "success") return tema.exito
        if (tone === "warning") return tema.advertencia
        if (tone === "danger") return tema.peligro
        if (tone === "info") return tema.acento
        return tema.textoMuted
    }

    color: Qt.rgba(_toneColor().r, _toneColor().g, _toneColor().b, 0.14)
    border.color: _toneColor()
    border.width: 1

    AppText {
        id: txt
        anchors.centerIn: parent
        width: Math.max(0, parent.width - (badge.compact ? 12 : 16))
        text: badge.text
        font.pixelSize: badge.compact ? 10 : 11
        font.bold: true
        color: badge._toneColor()
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
    }
}
