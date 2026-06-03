import QtQuick
import QtQuick.Layouts
import QtQuick.Effects

import "../componentes"

// Botón de acción del historial DJ.
//
// Soporta tres modos:
//   - icono + texto (modo cómodo, escritorio)
//   - solo texto (sin iconSource)
//   - solo icono (texto vacío)
//
// Tono visual:
//   - peligroso=true → acción destructiva (rojo).
//   - primario=true  → acción principal (acento sólido).
//   - default        → superficie alternativa con borde.
//
// La propiedad `ayuda` se conserva como sugerencia futura; no se usan
// tooltips por convención del proyecto.
Rectangle {
    id: raiz
    required property var tema
    property string texto: ""
    property string iconSource: ""
    property string ayuda: ""
    property bool primario: false
    property bool peligroso: false
    // Ancho mínimo cuando hay texto. El cálculo real es content-based.
    property real ancho: 0
    signal activada()

    readonly property bool _solo_icono: texto.length === 0 && iconSource.length > 0
    readonly property bool _tiene_icono: iconSource.length > 0

    implicitWidth: _solo_icono ? 34 : Math.max(ancho, contenido.implicitWidth + 24)
    implicitHeight: _solo_icono ? 30 : 32
    radius: 16
    color: {
        if (peligroso) {
            return ma.containsMouse
                ? Qt.rgba(raiz.tema.peligro.r, raiz.tema.peligro.g, raiz.tema.peligro.b, 0.18)
                : Qt.rgba(raiz.tema.peligro.r, raiz.tema.peligro.g, raiz.tema.peligro.b, 0.08)
        }
        if (primario) {
            return ma.containsMouse ? raiz.tema.acentoFuerte : raiz.tema.acento
        }
        return ma.containsMouse ? raiz.tema.hover : raiz.tema.superficieAlt
    }
    border.color: peligroso ? raiz.tema.peligro
                : primario ? "transparent"
                : raiz.tema.borde
    border.width: primario ? 0 : 1

    readonly property color _colorContenido: {
        if (peligroso) return raiz.tema.peligro
        if (primario) return raiz.tema.textoSobreAcento
        return raiz.tema.texto
    }

    RowLayout {
        id: contenido
        anchors.centerIn: parent
        spacing: raiz._solo_icono ? 0 : UiTokens.spacing6

        Item {
            visible: raiz._tiene_icono
            Layout.preferredWidth: UiTokens.iconSm
            Layout.preferredHeight: UiTokens.iconSm
            Image {
                id: icono
                anchors.fill: parent
                source: raiz.iconSource
                sourceSize.width: UiTokens.iconSm
                sourceSize.height: UiTokens.iconSm
                smooth: true
                opacity: 0
            }
            MultiEffect {
                anchors.fill: icono
                source: icono
                colorization: 1.0
                colorizationColor: raiz._colorContenido
            }
        }

        AppText {
            visible: !raiz._solo_icono
            text: raiz.texto
            color: raiz._colorContenido
            font.pixelSize: UiTokens.fontSizeMd
            font.weight: Font.DemiBold
        }
    }

    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: raiz.activada()
    }
}
