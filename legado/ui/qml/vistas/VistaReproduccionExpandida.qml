import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import QtQuick.Window

import "../componentes"
import "../componentes/UiUtils.js" as UiUtils

Rectangle {
    id: raiz
    property var shell: null
    readonly property var tema: shell ? shell.tema : temaUi
    readonly property var pista: reproductor.pista_activa || ({})
    readonly property var mood: reproductor.mood_visual || reproductor.lyrics_mood || ({})
    readonly property string portada: pista.portada_hd_ruta ? UiUtils.toMediaSource(pista.portada_hd_ruta) : (pista.portada_ruta ? UiUtils.toMediaSource(pista.portada_ruta) : "")
    readonly property bool layout_compacto: width < 1180
    readonly property real altura_barra_reproduccion: shell ? shell.altura_barra_reproduccion : 94
    property real padding_inferior: shell && shell.barra_overlay_visible ? (altura_barra_reproduccion + 28) : 28
    readonly property string titulo_seguro: String(pista.titulo || reproductor.titulo_activo || "Sin reproducción activa")
    readonly property string artista_seguro: String(pista.artista_nombre || reproductor.artista_activo || "Artista desconocido")
    readonly property string album_seguro: String(pista.album_titulo || reproductor.album_activo || "Álbum desconocido")
    readonly property string duracion_segura: reproductor.formatear_tiempo(pista.duracion_seg || reproductor.duracion_seg || 0)
    readonly property string semilla_base: String(pista.id || "") + "|" + String(pista.ruta_archivo || "") + "|" + titulo_seguro
    readonly property real hue_base: _normalizar01(mood.h, (((_hashCadena(semilla_base) % 360) + 360) % 360) / 360.0)
    readonly property real saturacion_base: Math.max(0.32, Math.min(0.72, Number(mood.s || 0.48)))
    readonly property real luminosidad_base: Math.max(0.14, Math.min(0.34, Number(mood.l || 0.20)))
    readonly property var resumen_items: _resumenItems()
    property real desplazamiento_con_barra: shell && shell.barra_overlay_visible ? -(altura_barra_reproduccion * 0.14) : 0
    color: _tonoMood(-1, 1.0)

    Behavior on padding_inferior {
        NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
    }
    Behavior on desplazamiento_con_barra {
        NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
    }

    function _hashCadena(texto) {
        var base = texto || "nbsound-fullscreen"
        var hash = 0
        for (var i = 0; i < base.length; ++i)
            hash = ((hash * 31) + base.charCodeAt(i)) & 0x7fffffff
        return hash
    }

    function _normalizar01(valor, fallback) {
        var numero = Number(valor)
        if (isNaN(numero))
            return fallback
        while (numero < 0)
            numero += 1
        while (numero > 1)
            numero -= 1
        return numero
    }

    function _tonoMood(offset, alpha) {
        var lightness = luminosidad_base + (offset * 0.085)
        return Qt.hsla(hue_base, saturacion_base, Math.max(0.09, Math.min(0.48, lightness)), alpha)
    }

    function _valorSemilla(indice) {
        return (_hashCadena(semilla_base + "|" + indice) % 1000) / 1000.0
    }

    function _resumenItems() {
        var salida = []
        if (album_seguro && album_seguro !== "")
            salida.push({ "label": "Álbum", "value": album_seguro })
        if (pista.anio)
            salida.push({ "label": "Año", "value": String(pista.anio) })
        if (pista.track_number)
            salida.push({ "label": "Pista", "value": "#" + String(pista.track_number) })
        if (duracion_segura && duracion_segura !== "--:--")
            salida.push({ "label": "Duración", "value": duracion_segura })
        if (reproductor.karaoke_disponible)
            salida.push({ "label": "Karaoke", "value": "Disponible" })
        return salida
    }

    Rectangle {
        anchors.fill: parent
        color: _tonoMood(0, 1.0)
        gradient: Gradient {
            GradientStop { position: 0.0; color: raiz._tonoMood(-1, 1.0) }
            GradientStop { position: 0.52; color: raiz._tonoMood(0, 1.0) }
            GradientStop { position: 1.0; color: raiz._tonoMood(1, 1.0) }
        }
    }

    Item {
        id: figuras_fondo
        anchors.fill: parent
        clip: true

        Repeater {
            id: figuras_pulso
            model: raiz.layout_compacto ? 28 : 44

            Item {
                id: figura_ambiental
                required property int index
                readonly property real semilla: raiz._valorSemilla(index * 17 + 1)
                readonly property real semillaDos: raiz._valorSemilla(index * 17 + 2)
                readonly property real semillaTres: raiz._valorSemilla(index * 17 + 3)
                // Figuras puramente geométricas (sin glifos Unicode):
                //   0,1 = círculo hueco; 2 = línea; 3,4 = rombo hueco.
                readonly property int tipoFigura: Math.floor(raiz._valorSemilla(index * 17 + 4) * 5)
                property real pulso: 0.0
                width: 34 + (semillaTres * (raiz.layout_compacto ? 44 : 62))
                height: width
                x: Math.max(0, (figuras_fondo.width - width) * semilla)
                y: Math.max(0, (figuras_fondo.height - height) * semillaDos)
                opacity: (0.045 + (semillaTres * 0.055)) * (0.78 + (pulso * 0.22))
                scale: 0.92 + (pulso * 0.16)
                rotation: -22 + (semilla * 44)

                Rectangle {
                    anchors.centerIn: parent
                    visible: figura_ambiental.tipoFigura <= 1
                    width: parent.width * 0.62
                    height: width
                    radius: width / 2
                    color: "transparent"
                    border.width: 2
                    border.color: raiz._tonoMood(2, 0.58)
                }

                Rectangle {
                    anchors.centerIn: parent
                    visible: figura_ambiental.tipoFigura === 2
                    width: parent.width * 0.82
                    height: Math.max(2, parent.width * 0.055)
                    radius: height / 2
                    color: raiz._tonoMood(2, 0.54)
                }

                Rectangle {
                    anchors.centerIn: parent
                    visible: figura_ambiental.tipoFigura >= 3
                    width: parent.width * 0.50
                    height: width
                    rotation: 45
                    radius: 4
                    color: "transparent"
                    border.width: 2
                    border.color: raiz._tonoMood(2, 0.48)
                }

                SequentialAnimation on pulso {
                    loops: Animation.Infinite
                    running: raiz.visible
                    NumberAnimation {
                        from: 0.0
                        to: 1.0
                        duration: 2600 + Math.round(figura_ambiental.semilla * 1800)
                        easing.type: Easing.InOutSine
                    }
                    NumberAnimation {
                        from: 1.0
                        to: 0.0
                        duration: 3000 + Math.round(figura_ambiental.semillaDos * 1900)
                        easing.type: Easing.InOutSine
                    }
                }
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(raiz._tonoMood(-1, 1.0).r, raiz._tonoMood(-1, 1.0).g, raiz._tonoMood(-1, 1.0).b, 0.30)
    }

    Item {
        id: escenario_central
        anchors.fill: parent
        anchors.leftMargin: raiz.layout_compacto ? 28 : 44
        anchors.rightMargin: anchors.leftMargin
        anchors.topMargin: raiz.layout_compacto ? 28 : 44
        anchors.bottomMargin: raiz.padding_inferior

        Item {
            id: contenido_centrado
            anchors.centerIn: parent
            width: parent.width
            height: Math.min(parent.height,
                             raiz.layout_compacto
                             ? Math.max(480, parent.height * 0.92)
                             : Math.max(560, parent.height * 0.78))
            transform: Translate { y: raiz.desplazamiento_con_barra }

            Loader {
                anchors.fill: parent
                sourceComponent: raiz.layout_compacto ? contenido_compacto : contenido_ancho
            }
        }
    }

    Component {
        id: contenido_ancho

        RowLayout {
            spacing: 44

            Item {
                Layout.preferredWidth: Math.min(640, raiz.width * 0.46)
                Layout.fillHeight: true
                Layout.alignment: Qt.AlignVCenter | Qt.AlignHCenter

                Rectangle {
                    id: portada_frame_ancha
                    anchors.centerIn: parent
                    width: Math.min(parent.width, parent.height)
                    height: width
                    radius: UiTokens.radiusSm
                    color: UiUtils.veloClaro(0.10)
                    border.width: 1
                    border.color: UiUtils.veloClaro(0.18)
                    clip: true

                    Image {
                        id: portada_imagen_ancha
                        anchors.fill: parent
                        source: portada
                        visible: portada !== "" && status !== Image.Error
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                        smooth: true
                        cache: true
                        sourceSize.width: Math.max(960, Math.ceil(width * (Screen.devicePixelRatio || 1) * 1.35))
                        sourceSize.height: Math.max(960, Math.ceil(height * (Screen.devicePixelRatio || 1) * 1.35))
                    }

                    Rectangle {
                        anchors.fill: parent
                        visible: !portada_imagen_ancha.visible
                        color: UiUtils.veloClaro(0.06)

                        Image {
                            id: _phImgAncha
                            anchors.centerIn: parent
                            width: 96; height: 96
                            source: "../assets/icons/track.svg"
                            sourceSize.width: 192; sourceSize.height: 192
                            smooth: true; opacity: 0
                        }
                        MultiEffect {
                            anchors.fill: _phImgAncha
                            source: _phImgAncha
                            colorization: 1.0
                            colorizationColor: UiUtils.veloClaro(0.70)
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: 18

                AppText {
                    text: titulo_seguro
                    color: raiz.tema.textoInmersivo
                    font.pixelSize: raiz.width < 1440 ? 60 : 72
                    font.weight: Font.ExtraBold
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }

                AppText {
                    text: artista_seguro
                    color: UiUtils.veloClaro(0.92)
                    font.pixelSize: 28
                    font.weight: Font.Bold
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }

                AppText {
                    text: album_seguro
                    color: UiUtils.veloClaro(0.74)
                    font.pixelSize: 21
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: UiTokens.spacing10

                    Repeater {
                        model: raiz.resumen_items

                        Rectangle {
                            required property var modelData
                            radius: UiTokens.radiusSm
                            color: UiUtils.veloClaro(0.10)
                            border.width: 1
                            border.color: UiUtils.veloClaro(0.16)
                            height: 34
                            width: texto_chip_ancho.implicitWidth + 22

                            AppText {
                                id: texto_chip_ancho
                                anchors.centerIn: parent
                                text: modelData.label + " · " + modelData.value
                                color: raiz.tema.textoInmersivo
                                font.pixelSize: UiTokens.fontSizeBase
                                font.weight: Font.DemiBold
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: contenido_compacto

        ColumnLayout {
            spacing: UiTokens.spacing20

            Item { Layout.fillHeight: true }

            Rectangle {
                id: portada_frame_compacta
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: Math.min(raiz.width - 56, raiz.height * 0.42)
                Layout.preferredHeight: Math.min(raiz.width - 56, raiz.height * 0.42)
                radius: UiTokens.radiusSm
                color: UiUtils.veloClaro(0.10)
                border.width: 1
                border.color: UiUtils.veloClaro(0.18)
                clip: true

                Image {
                    id: portada_imagen_compacta
                    anchors.fill: parent
                    source: portada
                    visible: portada !== "" && status !== Image.Error
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    smooth: true
                    cache: true
                    sourceSize.width: Math.max(800, Math.ceil(width * (Screen.devicePixelRatio || 1) * 1.35))
                    sourceSize.height: Math.max(800, Math.ceil(height * (Screen.devicePixelRatio || 1) * 1.35))
                }

                Rectangle {
                    anchors.fill: parent
                    visible: !portada_imagen_compacta.visible
                    color: UiUtils.veloClaro(0.06)

                    Image {
                        id: _phImgComp
                        anchors.centerIn: parent
                        width: 88; height: 88
                        source: "../assets/icons/track.svg"
                        sourceSize.width: 176; sourceSize.height: 176
                        smooth: true; opacity: 0
                    }
                    MultiEffect {
                        anchors.fill: _phImgComp
                        source: _phImgComp
                        colorization: 1.0
                        colorizationColor: UiUtils.veloClaro(0.70)
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: UiTokens.spacing14

                AppText {
                    text: titulo_seguro
                    color: raiz.tema.textoInmersivo
                    font.pixelSize: raiz.width < 980 ? 34 : 42
                    font.weight: Font.ExtraBold
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true
                }

                AppText {
                    text: artista_seguro
                    color: UiUtils.veloClaro(0.92)
                    font.pixelSize: 22
                    font.weight: Font.Bold
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true
                }

                AppText {
                    text: album_seguro
                    color: UiUtils.veloClaro(0.74)
                    font.pixelSize: 17
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: UiTokens.spacing8

                    Repeater {
                        model: raiz.resumen_items

                        Rectangle {
                            required property var modelData
                            radius: UiTokens.radiusSm
                            color: UiUtils.veloClaro(0.10)
                            border.width: 1
                            border.color: UiUtils.veloClaro(0.16)
                            height: 32
                            width: texto_chip_compacto.implicitWidth + 20

                            AppText {
                                id: texto_chip_compacto
                                anchors.centerIn: parent
                                text: modelData.label + " · " + modelData.value
                                color: raiz.tema.textoInmersivo
                                font.pixelSize: UiTokens.fontSizeMd
                                font.weight: Font.DemiBold
                            }
                        }
                    }
                }
            }

            Item { Layout.fillHeight: true }
        }
    }
}
