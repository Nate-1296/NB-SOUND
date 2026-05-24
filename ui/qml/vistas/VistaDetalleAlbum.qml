// =============================================================================
// ui/qml/vistas/VistaDetalleAlbum.qml
//
// Vista de detalle de un álbum con su lista de pistas completa.
// Se desliza sobre la vista de biblioteca cuando se abre un álbum.
// =============================================================================

import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtQuick.Effects
import "../componentes"
import "../componentes/UiUtils.js" as UiUtils

Rectangle {
    id: raiz
    color: tema.fondo

    property var shell: null
    readonly property var tema: shell ? shell.tema : temaUi

    property var datos_album: ({})
    signal volver()
    signal favoritaToggled(var pista)

    function totalPistas() {
        if (datos_album.num_pistas && datos_album.num_pistas > 0) return datos_album.num_pistas
        const pistas = datos_album.pistas || []
        return pistas.length
    }

    function totalDuracionSeg() {
        if (datos_album.duracion_total_seg && datos_album.duracion_total_seg > 0) return datos_album.duracion_total_seg
        const pistas = datos_album.pistas || []
        var total = 0
        for (var i = 0; i < pistas.length; ++i) total += (pistas[i].duracion_seg || 0)
        return total
    }

    function etiquetaTipoAlbum(tipo) {
        const valor = String(tipo || "").trim()
        if (valor.toLowerCase() === "album") return "Álbum"
        return valor
    }

    function portadaAlbumUi() {
        if (!datos_album)
            return ""
        if (datos_album.portada_display_ruta !== undefined)
            return datos_album.portada_display_ruta || ""
        if (datos_album.portada_thumb_ruta !== undefined && datos_album.portada_thumb_ruta)
            return datos_album.portada_thumb_ruta
        return datos_album.portada_ruta || ""
    }

    // Fondo degradado usando el acento del tema
    Rectangle {
        width: parent.width
        height: 300
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.12) }
            GradientStop { position: 1.0; color: tema.fondo }
        }
    }

    ScrollView {
        id: detalleAlbumScroll
        anchors.fill: parent
        contentWidth: availableWidth
        contentHeight: detalleAlbumContent.implicitHeight
        clip: true
        ScrollBar.vertical: AlbumScrollBar {
            parent: detalleAlbumScroll.parent
            anchors.top: detalleAlbumScroll.top
            anchors.right: parent.right
            anchors.bottom: detalleAlbumScroll.bottom
            z: 20
            policy: detalleAlbumContent.implicitHeight > detalleAlbumScroll.height + 2 ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
        }

        ColumnLayout {
            id: detalleAlbumContent
            width: raiz.width
            spacing: 0

            // ---- Boton volver ----
            Item {
                Layout.fillWidth: true
                height: 60

                Rectangle {
                    anchors { left: parent.left; leftMargin: UiTokens.spacing32; verticalCenter: parent.verticalCenter }
                    width: fila_volver_album.implicitWidth + 20
                    height: 32
                    radius: 16
                    color: area_volver.containsMouse ? tema.hover : "transparent"
                    border.color: tema.borde
                    border.width: 1

                    Behavior on color { ColorAnimation { duration: 150 } }

                    Row {
                        id: fila_volver_album
                        anchors.centerIn: parent
                        spacing: UiTokens.spacing6
                        ThemedIcon {
                            width: 14
                            height: 14
                            source: "../assets/icons/back.svg"
                            iconColor: tema.textoSec
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        AppText { text: "Volver"; font.pixelSize: UiTokens.fontSizeBase; color: tema.textoSec }
                    }

                    MouseArea {
                        id: area_volver
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: raiz.volver()
                    }
                }
            }

            // ---- Cabecera del álbum ----
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: UiTokens.spacing32
                Layout.rightMargin: UiTokens.spacing32
                Layout.bottomMargin: UiTokens.spacing32
                spacing: 24

                // Portada
                Rectangle {
                    width: 212
                    height: 212
                    color: albumCover.visible ? "transparent" : tema.superficieAlt
                    radius: UiTokens.radiusSm
                    border.color: albumCover.visible ? "transparent" : tema.borde
                    border.width: albumCover.visible ? 0 : 1
                    clip: true

                    Image {
                        id: albumCover
                        readonly property string portadaUi: portadaAlbumUi()
                        visible: portadaUi !== "" && status !== Image.Error
                        anchors.fill: parent
                        source: portadaUi !== "" ? UiUtils.toMediaSource(portadaUi) : ""
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        cache: true
                        sourceSize.width: 424
                        sourceSize.height: 424
                    }
                    AlbumCoverPlaceholder {
                        visible: !albumCover.visible
                        anchors.fill: parent
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignBottom
                    spacing: UiTokens.spacing8

                    AppText {
                        text: etiquetaTipoAlbum(datos_album.tipo) || "Álbum"
                        font.pixelSize: UiTokens.fontSizeMd
                        font.bold: true
                        color: tema.acento
                        font.letterSpacing: 1.2
                    }
                    AppText {
                        text: datos_album.titulo || ""
                        font.pixelSize: 38
                        font.bold: true
                        color: tema.texto
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    AppText {
                        id: artistaAlbumLink
                        text: datos_album.artista_nombre || ""
                        font.pixelSize: UiTokens.fontSizeXl
                        color: datos_album.artista_id
                               ? (area_artista_album.containsMouse ? tema.acentoFuerte : tema.acento)
                               : tema.texto

                        MouseArea {
                            id: area_artista_album
                            anchors.fill: parent
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            hoverEnabled: true
                            scrollGestureEnabled: false
                            enabled: !!datos_album.artista_id
                            onClicked: if (shell && datos_album.artista_id) shell.abrir_artista_desde_detalle(datos_album.artista_id)
                        }
                    }
                    AppText {
                        text: [
                            datos_album.anio || "",
                            totalPistas() + " pistas",
                            reproductor.formatear_duracion_larga(totalDuracionSeg())
                        ].filter(Boolean).join(" · ")
                        font.pixelSize: UiTokens.fontSizeBase
                        color: tema.textoSec
                    }

                    // Botones de acción
                    Flow {
                        spacing: UiTokens.spacing12
                        Layout.topMargin: UiTokens.spacing8
                        Layout.fillWidth: true

                        AlbumActionButton {
                            primary: true
                            texto: "Reproducir álbum completo"
                            iconSource: "../assets/icons/play.svg"
                            enabled: (datos_album.pistas || []).length > 0
                            onClicked: {
                                var pistas = datos_album.pistas || []
                                if (pistas.length > 0)
                                    reproductor.reproducir_cola_desde_pistas(pistas, 0)
                            }
                        }

                        AlbumActionButton {
                            texto: "Añadir álbum a la cola"
                            iconSource: "../assets/icons/queue-play.svg"
                            enabled: (datos_album.pistas || []).length > 0
                            onClicked: {
                                var pistas = datos_album.pistas || []
                                for (var i = 0; i < pistas.length; i++)
                                    reproductor.agregar_a_cola(pistas[i])
                                if (pistas.length > 0)
                                    mostrar_toast("Álbum agregado a la cola")
                            }
                        }
                    }
                }
            }

            // ---- Encabezado de la tabla ----
            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: UiTokens.spacing32
                Layout.rightMargin: UiTokens.spacing32
                height: 36
                radius: UiTokens.radiusSm
                color: tema.superficieAlt
                border.color: tema.borde
                border.width: 1

                RowLayout {
                    anchors { fill: parent; leftMargin: UiTokens.spacing12; rightMargin: UiTokens.spacing12 }
                    spacing: UiTokens.spacing8
                    AppText { text: "#"; font.pixelSize: UiTokens.fontSizeSm; font.weight: Font.DemiBold; color: tema.textoMuted; Layout.preferredWidth: 40; horizontalAlignment: Text.AlignHCenter }
                    AppText { text: "Título"; font.pixelSize: UiTokens.fontSizeSm; font.weight: Font.DemiBold; color: tema.textoMuted; Layout.fillWidth: true; horizontalAlignment: Text.AlignLeft }
                    AppText { text: "Duración"; font.pixelSize: UiTokens.fontSizeSm; font.weight: Font.DemiBold; color: tema.textoMuted; Layout.preferredWidth: 74; horizontalAlignment: Text.AlignHCenter }
                    AppText { text: "Acciones"; font.pixelSize: UiTokens.fontSizeSm; font.weight: Font.DemiBold; color: tema.textoMuted; Layout.preferredWidth: 304; horizontalAlignment: Text.AlignHCenter }
                }
            }

            // ---- Lista de pistas ----
            Repeater {
                model: datos_album.pistas || []

                delegate: Rectangle {
                    Layout.fillWidth: true
                    Layout.leftMargin: UiTokens.spacing32
                    Layout.rightMargin: UiTokens.spacing32
                    height: 60
                    color: area_pista_d.containsMouse ? tema.hover : "transparent"
                    radius: UiTokens.radiusSm

                    Behavior on color { ColorAnimation { duration: 120 } }

                    MouseArea {
                        id: area_pista_d
                        anchors.fill: parent
                        hoverEnabled: true
                        scrollGestureEnabled: false
                        cursorShape: Qt.ArrowCursor
                        acceptedButtons: Qt.NoButton
                    }

                    RowLayout {
                        anchors { fill: parent; leftMargin: UiTokens.spacing12; rightMargin: UiTokens.spacing12 }
                        spacing: UiTokens.spacing8

                        Item {
                            Layout.preferredWidth: 40
                            AppText {
                                anchors.centerIn: parent
                                text: modelData.track_number || index + 1
                                font.pixelSize: UiTokens.fontSizeBase
                                color: tema.textoSec
                                horizontalAlignment: Text.AlignHCenter

                                Behavior on color { ColorAnimation { duration: 120 } }
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 3
                            AppText {
                                text: modelData.titulo || modelData.nombre_archivo || ""
                                font.pixelSize: UiTokens.fontSizeLg
                                color: tema.texto
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            AppText {
                                text: modelData.artista_nombre || ""
                                font.pixelSize: UiTokens.fontSizeMd
                                color: tema.textoSec
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                                visible: text !== datos_album.artista_nombre
                            }
                        }

                        AppText {
                            text: reproductor.formatear_tiempo(modelData.duracion_seg || 0)
                            font.pixelSize: UiTokens.fontSizeMd
                            color: tema.textoSec
                            Layout.preferredWidth: 74
                            horizontalAlignment: Text.AlignHCenter
                        }

                        RowLayout {
                            Layout.preferredWidth: 304
                            spacing: UiTokens.spacing8
                            Layout.alignment: Qt.AlignVCenter
                            AlbumFavoriteButton {
                                activo: !!(modelData.favorita)
                                onClicked: raiz.favoritaToggled(modelData)
                            }
                            AlbumActionButton {
                                primary: true
                                texto: "Reproducir"
                                iconSource: "../assets/icons/play.svg"
                                onClicked: reproductor.reproducir(modelData)
                            }
                            AlbumActionButton {
                                texto: "Añadir a cola"
                                iconSource: "../assets/icons/queue-play.svg"
                                onClicked: {
                                    reproductor.agregar_a_cola(modelData)
                                    mostrar_toast("Pista agregada a la cola")
                                }
                            }
                        }
                    }
                }
            }

            EmptyState {
                Layout.fillWidth: true
                Layout.leftMargin: UiTokens.spacing32
                Layout.rightMargin: UiTokens.spacing32
                Layout.topMargin: UiTokens.spacing24
                visible: (datos_album.pistas || []).length === 0
                tema: raiz.tema
                title: "Álbum sin pistas visibles"
                description: "No se encontraron pistas en biblioteca para este álbum."
                iconSource: "../assets/icons/library.svg"
            }

            Item { height: 40 }
        }
    }

    // ── Toast notification ──
    ToastMessage {
        id: toastMessage
        anchors.bottom: parent.bottom
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottomMargin: UiTokens.spacing24
        tema: raiz.tema
    }

    function mostrar_toast(msg) {
        toastMessage.show(msg)
    }

    component AlbumScrollBar: ScrollBar {
        id: scrollBar
        interactive: true
        hoverEnabled: true
        enabled: visible
        active: visible
        orientation: Qt.Vertical
        minimumSize: 0.08
        width: 10
        padding: UiTokens.spacing2
        visible: policy !== ScrollBar.AlwaysOff

        contentItem: Rectangle {
            implicitWidth: 6
            implicitHeight: 6
            radius: width / 2
            color: tema.acentoFuerte
        }

        background: Rectangle {
            radius: width / 2
            color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.20)
            visible: scrollBar.policy !== ScrollBar.AlwaysOff
        }
    }

    component AlbumActionButton: Rectangle {
        id: accionAlbum
        property string texto: ""
        property string iconSource: ""
        property bool primary: false
        signal clicked()
        width: Math.max(primary ? 112 : 82, accionAlbumRow.implicitWidth + 24)
        height: 36
        radius: 18
        opacity: enabled ? 1.0 : 0.45
        color: !enabled ? tema.borde
              : (primary ? (accionAlbumMouse.containsMouse ? tema.acentoFuerte : tema.acento)
                         : (accionAlbumMouse.containsMouse ? tema.hover : "transparent"))
        border.color: primary || !enabled ? "transparent" : tema.borde
        border.width: primary || !enabled ? 0 : 1

        Row {
            id: accionAlbumRow
            anchors.centerIn: parent
            spacing: UiTokens.spacing6
            ThemedIcon {
                visible: accionAlbum.iconSource !== ""
                width: 15
                height: 15
                source: accionAlbum.iconSource
                iconColor: accionAlbum.primary ? tema.fondo : (accionAlbumMouse.containsMouse ? tema.texto : tema.textoSec)
                anchors.verticalCenter: parent.verticalCenter
            }
            AppText {
                text: accionAlbum.texto
                color: accionAlbum.primary ? tema.fondo : (accionAlbumMouse.containsMouse ? tema.texto : tema.textoSec)
                font.pixelSize: UiTokens.fontSizeMd
                font.weight: Font.DemiBold
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        MouseArea {
            id: accionAlbumMouse
            anchors.fill: parent
            hoverEnabled: true
            enabled: accionAlbum.enabled
            cursorShape: accionAlbum.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: accionAlbum.clicked()
        }
    }

    component AlbumFavoriteButton: Rectangle {
        id: favoritoAlbum
        property bool activo: false
        signal clicked()
        width: 36
        height: 36
        radius: 18
        color: activo ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.20)
                      : (favAlbumMouse.containsMouse ? tema.hover : "transparent")
        border.color: activo ? tema.acento : tema.borde
        border.width: 1

        ThemedIcon {
            anchors.centerIn: parent
            width: 16
            height: 16
            source: favoritoAlbum.activo ? "../assets/icons/favorite-filled.svg" : "../assets/icons/favorite.svg"
            iconColor: favoritoAlbum.activo ? tema.acento : tema.textoSec
            iconOpacity: favoritoAlbum.activo ? 1.0 : 0.72
        }

        MouseArea {
            id: favAlbumMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: favoritoAlbum.clicked()
        }
    }

    component AlbumCoverPlaceholder: Item {
        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.08)
            radius: UiTokens.radiusSm
        }
        Rectangle {
            id: coverPulse
            anchors.centerIn: parent
            width: Math.min(parent.width, parent.height) * 0.70
            height: width
            radius: UiTokens.radiusSm
            color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.10)
            border.width: 1
            border.color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.22)
            scale: 0.92
            opacity: 0.82
            SequentialAnimation on scale {
                running: coverPulse.visible
                loops: Animation.Infinite
                NumberAnimation { to: 1.0; duration: 1100; easing.type: Easing.InOutQuad }
                NumberAnimation { to: 0.92; duration: 1100; easing.type: Easing.InOutQuad }
            }
            SequentialAnimation on opacity {
                running: coverPulse.visible
                loops: Animation.Infinite
                NumberAnimation { to: 0.52; duration: 1100; easing.type: Easing.InOutQuad }
                NumberAnimation { to: 0.82; duration: 1100; easing.type: Easing.InOutQuad }
            }
        }
        ThemedIcon {
            anchors.centerIn: parent
            width: Math.min(parent.width, parent.height) * 0.30
            height: width
            source: "../assets/icons/library.svg"
            iconColor: tema.acento
            iconOpacity: 0.82
        }
    }

    component ThemedIcon: Item {
        id: themedIcon
        property string source: ""
        property color iconColor: tema.textoSec
        property real iconOpacity: 1.0
        implicitWidth: UiTokens.iconMd
        implicitHeight: UiTokens.iconMd

        Image {
            id: themedIconSource
            anchors.fill: parent
            source: themedIcon.source
            sourceSize.width: Math.max(16, parent.width * 2)
            sourceSize.height: Math.max(16, parent.height * 2)
            smooth: true
            opacity: 0
            visible: themedIcon.source !== ""
        }
        MultiEffect {
            anchors.fill: themedIconSource
            source: themedIconSource
            colorization: 1.0
            colorizationColor: themedIcon.iconColor
            opacity: themedIcon.iconOpacity
            visible: themedIcon.source !== ""
        }
    }
}
