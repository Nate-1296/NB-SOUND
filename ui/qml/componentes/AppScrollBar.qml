import QtQuick
import QtQuick.Controls

// ── AppScrollBar ─────────────────────────────────────────────────────────────
// Scrollbar unificada para toda la aplicación. Replica el patrón visual y de
// comportamiento usado en VistaInicio (referencia oficial). Para Flickable
// internos, asigna `flickable` y `policy` desde fuera; para attached pattern
// (ScrollBar.vertical: ...), basta con `policy`.
ScrollBar {
    id: sb

    // Flickable opcional para Binding manual de size/position (caso InicioScrollBar).
    // Cuando se usa attached (ScrollBar.vertical: AppScrollBar {}) puede dejarse en null;
    // Controls maneja el binding internamente.
    property var flickable: null
    property var tema: temaUi

    readonly property real _maxContentY:
        flickable ? Math.max(0, flickable.contentHeight - flickable.height) : 0
    readonly property real _trackRange: Math.max(0, 1 - size)

    interactive: true
    hoverEnabled: true
    enabled: visible
    active: visible
    orientation: Qt.Vertical
    minimumSize: 0.08
    width: 10
    padding: UiTokens.spacing2

    Binding {
        target: sb
        property: "size"
        when: sb.flickable !== null
        value: sb.flickable
               ? Math.max(sb.minimumSize, Math.min(1, sb.flickable.visibleArea.heightRatio))
               : 1
    }

    Binding {
        target: sb
        property: "position"
        when: sb.flickable !== null && !sb.pressed
        value: sb.flickable
               ? Math.max(0, Math.min(sb._trackRange,
                     (sb.flickable.contentY / Math.max(1, sb._maxContentY)) * sb._trackRange))
               : 0
    }

    onPositionChanged: {
        if (!pressed || !flickable || _maxContentY <= 0) return
        var ratio = _trackRange > 0 ? position / _trackRange : 0
        flickable.contentY = Math.max(0, Math.min(_maxContentY, ratio * _maxContentY))
    }

    contentItem: Rectangle {
        implicitWidth: 6
        implicitHeight: 6
        radius: width / 2
        color: sb.tema && sb.tema.acentoFuerte ? sb.tema.acentoFuerte : "#777"
    }

    background: Rectangle {
        radius: width / 2
        color: sb.tema && sb.tema.borde
               ? Qt.rgba(sb.tema.borde.r, sb.tema.borde.g, sb.tema.borde.b, 0.20)
               : "transparent"
        visible: sb.policy !== ScrollBar.AlwaysOff
    }
}
