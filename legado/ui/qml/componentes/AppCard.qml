import QtQuick
import QtQuick.Layouts

import "UiUtils.js" as UiUtils

Rectangle {
    id: card
    property var tema: temaUi
    property int padding: UiTokens.spacing20
    property bool elevated: false

    radius: UiTokens.radiusLg
    implicitWidth: layout.implicitWidth + (card.padding * 2)
    implicitHeight: layout.implicitHeight + (card.padding * 2)
    color: elevated ? tema.superficieAlt : tema.superficie
    border.color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, elevated ? 0.95 : 0.8)
    border.width: 1
    antialiasing: true
    clip: true

    Rectangle {
        anchors.top: parent.top
        width: parent.width
        height: 1
        color: UiUtils.veloClaro(0.06)
    }

    default property alias contentData: layout.data

    ColumnLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: card.padding
        spacing: UiTokens.spacing10
    }
}
