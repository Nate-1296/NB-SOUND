import QtQuick

import "."
import "UiUtils.js" as UiUtils

Item {
    id: raiz
    property var tema: temaUi
    property bool running: false
    property real phase: 0
    property real originX: 0
    property real worldWidth: width

    readonly property real mundo: Math.max(1, worldWidth, width, originX + width)

    function colorTema(color, alpha) {
        if (color && color.r !== undefined)
            return Qt.rgba(color.r, color.g, color.b, alpha)
        return Qt.rgba(0.51, 0.63, 0.75, alpha)
    }

    function offsetGlobal(indice, velocidad, semilla, extra) {
        var ciclo = mundo + extra
        return ((phase * velocidad + indice * semilla) % ciclo) - (extra * 0.5) - originX
    }

    clip: true
    opacity: running ? 0.92 : 0
    visible: opacity > 0.01

    Behavior on opacity { NumberAnimation { duration: UiTokens.durationSlow } }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: UiUtils.veloClaro(0.010) }
            GradientStop { position: 0.48; color: raiz.colorTema(raiz.tema.acento, 0.016) }
            GradientStop { position: 1.0; color: UiUtils.veloOscuro(0.055) }
        }
    }

    Repeater {
        model: 8

        Rectangle {
            readonly property real anchoBarra: 44 + ((index * 31) % 84)
            readonly property bool oscura: index % 3 === 1
            readonly property real pulso: 0.55 + Math.sin(raiz.phase * (0.42 + index * 0.015) + index * 1.9) * 0.45

            width: anchoBarra
            height: raiz.height * 1.65 + 90
            x: raiz.offsetGlobal(index, 14 + index * 3.7, 149, 520)
            y: -height * 0.24
            rotation: -11
            radius: width / 2
            color: oscura
                   ? Qt.rgba(0.04, 0.06, 0.08, 0.026 + pulso * 0.030)
                   : Qt.rgba(0.76, 0.82, 0.88, 0.022 + pulso * 0.034)
            border.color: oscura
                          ? UiUtils.veloOscuro(0.016)
                          : raiz.colorTema(raiz.tema.acento, 0.012)
            border.width: 1
        }
    }

    Repeater {
        model: 4

        Rectangle {
            width: 14 + index * 5
            height: raiz.height * 1.7 + 80
            x: raiz.offsetGlobal(index, 22 + index * 5, 211, 460)
            y: -height * 0.25
            rotation: -11
            radius: width / 2
            color: Qt.rgba(0.96, 0.98, 1.0, 0.024 + (Math.sin(raiz.phase * 0.58 + index * 1.6) + 1) * 0.012)
        }
    }

    Repeater {
        model: 2

        Rectangle {
            width: raiz.width * 0.84
            height: 1
            x: raiz.width * 0.08
            y: raiz.height * (index === 0 ? 0.33 : 0.68)
               + Math.sin(raiz.phase * 0.20 + index) * 0.8
            rotation: index === 0 ? -0.25 : 0.25
            color: index === 0 ? UiUtils.veloClaro(0.020) : UiUtils.veloOscuro(0.035)
        }
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: UiUtils.veloOscuro(0.05) }
            GradientStop { position: 0.5; color: UiUtils.veloOscuro(0.00) }
            GradientStop { position: 1.0; color: UiUtils.veloOscuro(0.08) }
        }
    }
}
