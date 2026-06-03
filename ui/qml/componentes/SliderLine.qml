import QtQuick

import "."

Item {
    id: slider
    property var tema: temaUi
    property real ratio: 0
    property bool live: true
    property real visualHeight: 5
    property real handleBaseSize: 10
    property real handleActiveSize: 14
    property bool arrastrando: mouse_slider.pressed
    property real _previewRatio: _ratioClamp(ratio)
    readonly property real ratio_visual: arrastrando ? _previewRatio : _ratioClamp(ratio)
    signal moved(real ratio)
    signal previewed(real ratio)
    signal committed(real ratio)
    signal canceled()

    function _ratioClamp(valor) {
        return Math.max(0, Math.min(1, Number(valor) || 0))
    }

    function moverDesde(posicionX) {
        if (!enabled || width <= 0)
            return _previewRatio
        var nuevoRatio = _ratioClamp(posicionX / width)
        _previewRatio = nuevoRatio
        previewed(nuevoRatio)
        if (live)
            moved(nuevoRatio)
        return nuevoRatio
    }

    height: Math.max(22, handleActiveSize + 8)
    opacity: enabled ? 1.0 : 0.5
    onRatioChanged: {
        if (!arrastrando)
            _previewRatio = _ratioClamp(ratio)
    }
    Component.onCompleted: _previewRatio = _ratioClamp(ratio)

    Rectangle {
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width
        height: slider.visualHeight
        radius: height / 2
        color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.86)

        Rectangle {
            width: parent.width * slider.ratio_visual
            height: parent.height
            radius: parent.radius
            color: tema.acento
        }
    }

    Rectangle {
        width: mouse_slider.pressed || mouse_slider.containsMouse ? slider.handleActiveSize : slider.handleBaseSize
        height: width
        radius: width / 2
        x: Math.max(0, Math.min(parent.width - width, (parent.width * slider.ratio_visual) - width / 2))
        anchors.verticalCenter: parent.verticalCenter
        color: tema.texto
        border.color: tema.acento
        border.width: 2

        Behavior on width { NumberAnimation { duration: UiTokens.durationFast } }
        Behavior on x {
            enabled: !slider.arrastrando
            NumberAnimation { duration: UiTokens.durationFast; easing.type: Easing.OutQuad }
        }
    }

    MouseArea {
        id: mouse_slider
        anchors.fill: parent
        hoverEnabled: true
        enabled: slider.enabled
        preventStealing: true
        acceptedButtons: Qt.LeftButton
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor

        onPressed: function(mouse) {
            mouse.accepted = true
            slider._previewRatio = slider._ratioClamp(slider.ratio)
            slider.moverDesde(mouse.x)
        }
        onPositionChanged: function(mouse) {
            if (pressed)
                slider.moverDesde(mouse.x)
        }
        onReleased: function(mouse) {
            if (!slider.enabled)
                return
            mouse.accepted = true
            slider.committed(slider._previewRatio)
        }
        onCanceled: {
            slider._previewRatio = slider._ratioClamp(slider.ratio)
            slider.canceled()
        }
    }
}
