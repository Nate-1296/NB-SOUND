import QtQuick
import QtQuick.Layouts
import QtQuick.Effects

Item {
    id: root
    property var tema: temaUi
    property string title: "Sin datos"
    property string description: ""
    property string iconText: ""
    property string iconSource: "../assets/icons/track.svg"

    implicitHeight: 228
    implicitWidth: 360

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(root.width - UiTokens.spacing24, 420)
        spacing: UiTokens.spacing10

        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            width: 72
            height: 72
            radius: 36
            color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.08)
            border.color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.2)
            border.width: 1
            Image {
                id: sourceIcon
                anchors.centerIn: parent
                width: UiTokens.iconXl
                height: UiTokens.iconXl
                source: root.iconSource
                sourceSize.width: UiTokens.iconXl * 2
                sourceSize.height: UiTokens.iconXl * 2
                smooth: true
                opacity: 0
                visible: root.iconSource !== ""
            }
            MultiEffect {
                anchors.fill: sourceIcon
                source: sourceIcon
                colorization: 1.0
                colorizationColor: tema.textoMuted
                visible: root.iconSource !== ""
            }
            AppText {
                visible: root.iconSource === ""
                anchors.centerIn: parent
                text: root.iconText
                font.pixelSize: UiTokens.iconXl
                color: tema.textoMuted
                horizontalAlignment: Text.AlignHCenter
            }
        }
        AppText {
            text: root.title
            font.pixelSize: UiTokens.fontSizeXl
            font.bold: true
            color: tema.texto
            Layout.alignment: Qt.AlignHCenter
        }
        AppText {
            text: root.description
            font.pixelSize: UiTokens.fontSizeMd
            color: tema.textoSec
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            lineHeight: 1.2
            Layout.fillWidth: true
            Layout.maximumWidth: 420
            Layout.alignment: Qt.AlignHCenter
        }
    }
}
