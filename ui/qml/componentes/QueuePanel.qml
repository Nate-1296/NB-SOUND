import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts

import "UiUtils.js" as UiUtils

AppCard {
    id: panel
    property var tema: temaUi
    property int indice_arrastrando: -1
    property int indice_destino: -1
    property int autoScrollDireccion: 0
    readonly property bool hayContenido: reproductor.cola.total > 0
    readonly property bool compacto: width < 360
    readonly property bool muy_compacto: width < 310
    readonly property int autoScrollMargen: compacto ? 34 : 44
    readonly property int autoScrollPaso: compacto ? 10 : 16
    padding: UiTokens.spacing14

    function _resetArrastre() {
        _detenerAutoScroll()
        indice_arrastrando = -1
        indice_destino = -1
    }

    function _confirmarArrastre() {
        if (indice_arrastrando >= 0
                && indice_destino >= 0
                && indice_arrastrando !== indice_destino
                && indice_destino < reproductor.cola.total) {
            reproductor.mover_en_cola(indice_arrastrando, indice_destino)
        }
        _resetArrastre()
    }

    function _maxContentY() {
        return Math.max(0, lista_cola.contentHeight - lista_cola.height)
    }

    function _limitarContentY(valor) {
        return Math.max(0, Math.min(_maxContentY(), valor))
    }

    function _detenerAutoScroll() {
        autoScrollDireccion = 0
        auto_scroll_drag_timer.stop()
    }

    function _actualizarAutoScroll(yEnLista) {
        if (indice_arrastrando < 0 || lista_cola.count <= 0) {
            _detenerAutoScroll()
            return
        }
        if (yEnLista < autoScrollMargen && lista_cola.contentY > 0) {
            autoScrollDireccion = -1
            auto_scroll_drag_timer.start()
            return
        }
        if (yEnLista > lista_cola.height - autoScrollMargen && lista_cola.contentY < _maxContentY()) {
            autoScrollDireccion = 1
            auto_scroll_drag_timer.start()
            return
        }
        _detenerAutoScroll()
    }

    Timer {
        id: auto_scroll_drag_timer
        interval: 24
        repeat: true
        onTriggered: {
            if (panel.indice_arrastrando < 0 || panel.autoScrollDireccion === 0) {
                panel._detenerAutoScroll()
                return
            }
            lista_cola.contentY = panel._limitarContentY(
                        lista_cola.contentY + panel.autoScrollDireccion * panel.autoScrollPaso)
        }
    }

    function _textoCantidadPistas() {
        var total = reproductor.cola.total
        if (total <= 0)
            return "Cola vacía"
        return total === 1 ? "1 pista" : total + " pistas"
    }

    function _textoDuracionCola() {
        return reproductor.formatear_duracion_larga(reproductor.duracion_cola_seg || 0)
    }

    function _metadataSecundaria(artistaNombre, artistaAlt, albumTitulo, albumAlt) {
        var artistaTexto = String(artistaNombre || artistaAlt || "Artista desconocido")
        if (panel.compacto)
            return artistaTexto
        var albumTexto = String(albumTitulo || albumAlt || "")
        return albumTexto !== "" ? artistaTexto + " · " + albumTexto : artistaTexto
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: UiTokens.spacing8

        RowLayout {
            Layout.fillWidth: true
            spacing: UiTokens.spacing10

            AppText {
                text: "Cola de reproducción"
                font.pixelSize: 15
                font.bold: true
                color: tema.texto
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                elide: Text.ElideRight
                maximumLineCount: 1
            }

            Rectangle {
                Layout.preferredWidth: 76
                Layout.preferredHeight: 30
                Layout.alignment: Qt.AlignVCenter
                radius: UiTokens.radiusSm
                color: limpiarHover.containsMouse && limpiarHover.enabled ? tema.hover : "transparent"
                border.color: tema.borde
                opacity: limpiarHover.enabled ? 1.0 : 0.45

                AppText {
                    anchors.centerIn: parent
                    text: "Vaciar"
                    color: tema.textoSec
                    font.pixelSize: UiTokens.fontSizeSm
                }

                MouseArea {
                    id: limpiarHover
                    anchors.fill: parent
                    hoverEnabled: true
                    enabled: reproductor.cola.total > 0
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: reproductor.vaciar_cola_mantener_actual()
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: UiTokens.spacing8

            StatusBadge {
                tema: panel.tema
                text: panel._textoCantidadPistas()
                tone: panel.hayContenido ? "info" : "neutral"
            }

            StatusBadge {
                visible: panel.hayContenido
                tema: panel.tema
                text: panel._textoDuracionCola()
                tone: "neutral"
            }

            Item { Layout.fillWidth: true }
        }
    }

    ListView {
        id: lista_cola
        Layout.fillWidth: true
        Layout.fillHeight: true
        model: reproductor.cola
        clip: true
        spacing: 7
        cacheBuffer: 220
        reuseItems: false
        currentIndex: reproductor.indice_cola
        boundsBehavior: Flickable.StopAtBounds

        move: Transition {
            NumberAnimation { properties: "x,y"; duration: UiTokens.durationBase; easing.type: Easing.OutQuad }
        }
        moveDisplaced: Transition {
            NumberAnimation { properties: "x,y"; duration: UiTokens.durationBase; easing.type: Easing.OutQuad }
        }
        remove: Transition {
            NumberAnimation { property: "opacity"; to: 0; duration: UiTokens.durationFast }
        }
        removeDisplaced: Transition {
            NumberAnimation { properties: "x,y"; duration: UiTokens.durationBase; easing.type: Easing.OutQuad }
        }

        ScrollBar.vertical: AppScrollBar { tema: panel.tema; policy: ScrollBar.AsNeeded }

        EmptyState {
            anchors.centerIn: parent
            tema: panel.tema
            title: "Cola vacía"
            description: "¡Empieza a escuchar!"
            visible: lista_cola.count === 0
        }

        delegate: Item {
            id: fila
            width: ListView.view.width
            height: panel.compacto ? 62 : 66
            z: dragHandle.drag.active ? 20 : 1
            property int queueIndex: index
            property bool esActual: index === reproductor.indice_cola
            property bool esSonando: esActual && reproductor.reproduciendo
            property bool esPausada: esActual && reproductor.pausado
            property bool esDestino: panel.indice_destino === index && panel.indice_arrastrando >= 0
            property string tituloRol: typeof titulo === "undefined" ? "" : String(titulo || "")
            property string nombreArchivoRol: typeof nombre_archivo === "undefined" ? "" : String(nombre_archivo || "")
            property string artistaNombreRol: typeof artista_nombre === "undefined" ? "" : String(artista_nombre || "")
            property string artistaRol: typeof artista === "undefined" ? "" : String(artista || "")
            property string albumTituloRol: typeof album_titulo === "undefined" ? "" : String(album_titulo || "")
            property string albumRol: typeof album === "undefined" ? "" : String(album || "")
            property string portadaRutaRol: typeof portada_ruta === "undefined" ? "" : String(portada_ruta || "")
            property real duracionSegRol: typeof duracion_seg === "undefined" ? 0 : Number(duracion_seg || 0)

            Drag.active: dragHandle.drag.active
            Drag.source: fila
            Drag.keys: ["queue-row"]
            Drag.hotSpot.x: width / 2
            Drag.hotSpot.y: height / 2

            DropArea {
                anchors.fill: parent
                keys: ["queue-row"]
                onEntered: function(drag) {
                    if (panel.indice_arrastrando >= 0 && drag.source !== fila)
                        panel.indice_destino = fila.queueIndex
                }
            }

            Rectangle {
                anchors.fill: parent
                radius: UiTokens.radiusSm
                color: fila.esSonando
                       ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.16)
                       : (fila.esPausada
                          ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.09)
                       : (hoverFila.hovered || fila.esDestino
                          ? tema.hover
                          : Qt.rgba(tema.superficieAlt.r, tema.superficieAlt.g, tema.superficieAlt.b, 0.52)))
                border.color: fila.esSonando
                              ? tema.acento
                              : ((fila.esDestino || fila.esPausada)
                                 ? tema.borde
                                 : "transparent")
                border.width: fila.esDestino || fila.esActual ? 1 : 0
                opacity: dragHandle.drag.active ? 0.92 : 1.0

                Behavior on color { ColorAnimation { duration: UiTokens.durationBase } }
                Behavior on opacity { NumberAnimation { duration: UiTokens.durationFast } }

                HoverHandler {
                    id: hoverFila
                    cursorShape: Qt.ArrowCursor
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: panel.compacto ? 7 : 8
                    anchors.rightMargin: panel.compacto ? 7 : 8
                    spacing: panel.compacto ? UiTokens.spacing6 : UiTokens.spacing8

                    Rectangle {
                        Layout.preferredWidth: panel.compacto ? 22 : 24
                        Layout.preferredHeight: panel.compacto ? 40 : 42
                        Layout.alignment: Qt.AlignVCenter
                        radius: UiTokens.radiusSm
                        color: dragHandle.containsMouse || dragHandle.drag.active
                               ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.14)
                               : "transparent"

                        Image {
                            id: _dragIcon
                            anchors.centerIn: parent
                            width: 15
                            height: 15
                            source: "../assets/icons/drag.svg"
                            sourceSize.width: 30
                            sourceSize.height: 30
                            opacity: 0
                            smooth: true
                        }
                        MultiEffect {
                            anchors.fill: _dragIcon
                            source: _dragIcon
                            colorization: 1.0
                            colorizationColor: panel.tema.textoSec
                            opacity: dragHandle.containsMouse || dragHandle.drag.active ? 1.0 : 0.58
                        }

                        MouseArea {
                            id: dragHandle
                            anchors.fill: parent
                            hoverEnabled: true
                            preventStealing: true
                            cursorShape: Qt.SizeVerCursor
                            drag.target: fila
                            drag.axis: Drag.YAxis
                            onPressed: {
                                panel.indice_arrastrando = index
                                panel.indice_destino = index
                            }
                            onPositionChanged: function(mouse) {
                                var punto = dragHandle.mapToItem(lista_cola, mouse.x, mouse.y)
                                panel._actualizarAutoScroll(punto.y)
                            }
                            onReleased: {
                                fila.x = 0
                                fila.y = 0
                                panel._confirmarArrastre()
                            }
                            onCanceled: {
                                panel._resetArrastre()
                                fila.x = 0
                                fila.y = 0
                            }
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: panel.compacto ? 38 : 40
                        Layout.preferredHeight: panel.compacto ? 38 : 40
                        Layout.alignment: Qt.AlignVCenter
                        radius: 7
                        clip: true
                        color: tema.superficie

                        AppText {
                            visible: (fila.portadaRutaRol === "" || portada_img.status === Image.Error)
                                     && !fila.esSonando
                                     && !fila.esPausada
                            anchors.centerIn: parent
                            text: index + 1
                            color: tema.textoMuted
                            font.pixelSize: UiTokens.fontSizeSm
                        }

                        Image {
                            id: _playIcon
                            visible: (fila.portadaRutaRol === "" || portada_img.status === Image.Error) && fila.esSonando
                            anchors.centerIn: parent
                            width: 16
                            height: 16
                            source: "../assets/icons/queue-play.svg"
                            sourceSize.width: 32
                            sourceSize.height: 32
                            opacity: 0
                            smooth: true
                        }
                        MultiEffect {
                            visible: _playIcon.visible
                            anchors.fill: _playIcon
                            source: _playIcon
                            colorization: 1.0
                            colorizationColor: panel.tema.acento
                            opacity: 0.95
                        }

                        Image {
                            id: _pauseIcon
                            visible: (fila.portadaRutaRol === "" || portada_img.status === Image.Error) && fila.esPausada
                            anchors.centerIn: parent
                            width: 16
                            height: 16
                            source: "../assets/icons/pause.svg"
                            sourceSize.width: 32
                            sourceSize.height: 32
                            opacity: 0
                            smooth: true
                        }
                        MultiEffect {
                            visible: _pauseIcon.visible
                            anchors.fill: _pauseIcon
                            source: _pauseIcon
                            colorization: 1.0
                            colorizationColor: panel.tema.textoMuted
                            opacity: 0.9
                        }

                        Image {
                            id: portada_img
                            anchors.fill: parent
                            visible: fila.portadaRutaRol !== "" && status !== Image.Error
                            source: fila.portadaRutaRol !== "" ? UiUtils.toMediaSource(fila.portadaRutaRol) : ""
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                            smooth: true
                            sourceSize.width: 80
                            sourceSize.height: 80
                        }

                        Rectangle {
                            anchors.fill: parent
                            color: fila.esActual ? UiUtils.veloOscuro(0.28) : "transparent"
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        Layout.alignment: Qt.AlignVCenter
                        spacing: UiTokens.spacing2

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: panel.compacto ? UiTokens.spacing6 : UiTokens.spacing8
                            AppText {
                                text: fila.tituloRol || fila.nombreArchivoRol || "Pista sin título"
                                color: tema.texto
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                elide: Text.ElideRight
                                maximumLineCount: 1
                                font.pixelSize: UiTokens.fontSizeMd
                                font.bold: fila.esActual
                            }

                            Rectangle {
                                id: badge_estado_actual
                                visible: (fila.esSonando || fila.esPausada) && !panel.compacto
                                Layout.preferredWidth: Math.ceil(texto_estado_actual.implicitWidth + 16)
                                Layout.preferredHeight: 18
                                Layout.alignment: Qt.AlignVCenter
                                radius: 9
                                color: fila.esSonando
                                       ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.14)
                                       : Qt.rgba(tema.superficieAlt.r, tema.superficieAlt.g, tema.superficieAlt.b, 0.72)
                                border.color: fila.esSonando
                                              ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.55)
                                              : tema.borde
                                border.width: 1

                                AppText {
                                    id: texto_estado_actual
                                    anchors.centerIn: parent
                                    text: fila.esSonando ? "Sonando" : "En pausa"
                                    color: fila.esSonando ? tema.acento : tema.textoSec
                                    font.pixelSize: UiTokens.fontSizeXs
                                    font.bold: true
                                    maximumLineCount: 1
                                }
                            }
                        }

                        AppText {
                            visible: !panel.muy_compacto
                            text: panel._metadataSecundaria(
                                      fila.artistaNombreRol,
                                      fila.artistaRol,
                                      fila.albumTituloRol,
                                      fila.albumRol)
                            color: tema.textoSec
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            elide: Text.ElideRight
                            maximumLineCount: 1
                            font.pixelSize: UiTokens.fontSizeSm
                        }
                    }

                    AppText {
                        visible: !panel.compacto
                        text: reproductor.formatear_tiempo(fila.duracionSegRol)
                        color: tema.textoMuted
                        font.pixelSize: UiTokens.fontSizeSm
                        Layout.preferredWidth: 46
                        Layout.alignment: Qt.AlignVCenter
                        horizontalAlignment: Text.AlignRight
                        maximumLineCount: 1
                    }

                    BotonFila {
                        iconSource: "../assets/icons/queue-play.svg"
                        colorHover: tema.acento
                        fondoHover: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.14)
                        onClicked: reproductor.reproducir_indice_cola(index)
                    }

                    BotonFila {
                        iconSource: "../assets/icons/close.svg"
                        colorHover: tema.peligro
                        fondoHover: Qt.rgba(tema.peligro.r, tema.peligro.g, tema.peligro.b, 0.14)
                        iconSize: 14
                        onClicked: reproductor.quitar_de_cola(index)
                    }
                }
            }
        }
    }

    component BotonFila: Rectangle {
        id: botonFila
        property string iconSource: ""
        property color colorHover: panel.tema.acento
        property color fondoHover: panel.tema.hover
        property int iconSize: 13
        signal clicked()

        Layout.preferredWidth: 28
        Layout.preferredHeight: 28
        Layout.alignment: Qt.AlignVCenter
        radius: UiTokens.radiusSm
        color: areaBotonFila.containsMouse ? fondoHover : "transparent"
        border.color: areaBotonFila.containsMouse ? colorHover : "transparent"
        border.width: areaBotonFila.containsMouse ? 1 : 0

        Image {
            id: _bfIcon
            anchors.centerIn: parent
            width: botonFila.iconSize
            height: botonFila.iconSize
            source: botonFila.iconSource
            sourceSize.width: botonFila.iconSize * 2
            sourceSize.height: botonFila.iconSize * 2
            opacity: 0
            smooth: true
        }
        MultiEffect {
            anchors.fill: _bfIcon
            source: _bfIcon
            colorization: 1.0
            colorizationColor: areaBotonFila.containsMouse
                ? botonFila.colorHover
                : panel.tema.textoSec
            opacity: areaBotonFila.containsMouse ? 1.0 : 0.85
        }

        MouseArea {
            id: areaBotonFila
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: botonFila.clicked()
        }

    }
}
