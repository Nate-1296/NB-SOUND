import QtQuick
import QtQuick.Effects

Rectangle {
    id: root
    property var tema: temaUi
    property string message: ""
    property int timeoutMs: 0
    // Color del texto: por defecto se calcula segun el tono actual para
    // garantizar contraste sobre el fondo del toast (rojo/naranja/verde/
    // acento dependen del tema y pueden tener luminancias muy distintas).
    // El caller puede sobreescribirlo si necesita un valor explicito.
    property color foregroundColor: foregroundForTone(tone)
    property string tone: "success"

    function backgroundColor() {
        if (tone === "warning") return Qt.rgba(tema.advertencia.r, tema.advertencia.g, tema.advertencia.b, 0.92)
        if (tone === "danger") return Qt.rgba(tema.peligro.r, tema.peligro.g, tema.peligro.b, 0.92)
        if (tone === "info") return Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.92)
        return Qt.rgba(tema.exito.r, tema.exito.g, tema.exito.b, 0.9)
    }

    function foregroundForTone(currentTone) {
        if (!tema)
            return "#FFFFFF"
        if (currentTone === "warning")
            return tema.textoSobreAdvertencia !== undefined ? tema.textoSobreAdvertencia : tema.textoSobreAcento
        if (currentTone === "danger")
            return tema.textoSobrePeligro !== undefined ? tema.textoSobrePeligro : tema.textoSobreAcento
        if (currentTone === "info")
            return tema.textoSobreAcento
        return tema.textoSobreExito !== undefined ? tema.textoSobreExito : tema.textoSobreAcento
    }

    function timeoutForTone(msgTone) {
        if (msgTone === "danger")
            return 4200
        if (msgTone === "warning")
            return 3400
        if (msgTone === "info")
            return 2600
        return 2200
    }

    width: Math.min(parent ? (parent.width - UiTokens.spacing24 * 2) : (toastText.implicitWidth + UiTokens.spacing32 * 2),
                    Math.max(240, toastText.implicitWidth + UiTokens.spacing32 * 2))
    height: UiTokens.controlHeightLg
    radius: UiTokens.radiusPill
    color: backgroundColor()
    visible: opacity > 0
    opacity: 0
    scale: opacity > 0 ? 1.0 : 0.96

    Behavior on opacity { NumberAnimation { duration: UiTokens.durationSlow; easing.type: Easing.OutQuad } }
    Behavior on scale { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }

    AppText {
        id: toastText
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: parent.left
        anchors.leftMargin: UiTokens.spacing12
        anchors.right: cerrar_toast.left
        anchors.rightMargin: UiTokens.spacing8
        text: root.message
        color: root.foregroundColor
        font.pixelSize: UiTokens.fontSizeLg
        font.bold: true
        horizontalAlignment: Text.AlignLeft
        elide: Text.ElideRight
    }

    Item {
        id: cerrar_toast
        anchors.right: parent.right
        anchors.rightMargin: UiTokens.spacing12
        anchors.verticalCenter: parent.verticalCenter
        width: UiTokens.iconSm
        height: UiTokens.iconSm

        Image {
            id: closeIcon
            anchors.fill: parent
            source: "../assets/icons/close.svg"
            sourceSize.width: UiTokens.iconSm * 2
            sourceSize.height: UiTokens.iconSm * 2
            smooth: true
            opacity: 0
        }

        MultiEffect {
            anchors.fill: closeIcon
            source: closeIcon
            colorization: 1.0
            colorizationColor: Qt.rgba(root.foregroundColor.r, root.foregroundColor.g, root.foregroundColor.b, 0.9)
        }
    }
    MouseArea {
        anchors.fill: cerrar_toast
        cursorShape: Qt.PointingHandCursor
        onClicked: root.opacity = 0
    }

    Timer {
        id: hideTimer
        interval: root.timeoutMs
        onTriggered: root.opacity = 0
    }

    function show(msg, msgTone) {
        var limpio = String(msg || "").trim()
        if (limpio === "")
            return
        root.message = limpio
        if (msgTone !== undefined && msgTone !== null && msgTone !== "")
            root.tone = msgTone
        else
            root.tone = "success"
        if (root.timeoutMs <= 0)
            hideTimer.interval = timeoutForTone(root.tone)
        else
            hideTimer.interval = root.timeoutMs
        root.opacity = 1.0
        hideTimer.restart()
    }
}
