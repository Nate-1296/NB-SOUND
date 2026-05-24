import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects

import "."
import "UiUtils.js" as UiUtils

Rectangle {
    id: raiz
    property var shell: null
    property int capa_cola_z: 120
    property real animacion_fase: 0
    property real animacion_origen_x: 0
    property real animacion_ancho_mundo: width
    readonly property var tema: shell ? shell.tema : temaUi
    readonly property var pista_activa: reproductor.pista_activa || ({})
    readonly property var pista_visual: reproductor.pista_visual || ({})
    readonly property bool hay_pista_activa: _hayPistaActiva(pista_activa)
    readonly property bool hay_pista_visual: _hayPistaActiva(pista_visual)
    readonly property bool puede_reproducir: reproductor.cola.total > 0 || hay_pista_activa
    readonly property bool duracion_conocida: _numeroSeguro(reproductor.duracion_seg) > 0
    readonly property string titulo_seguro: hay_pista_visual ? (_textoSeguro(pista_visual.titulo) || _textoSeguro(reproductor.titulo_activo) || "Pista sin título") : "Sin reproducción activa"
    readonly property string artista_seguro: hay_pista_visual ? (_textoSeguro(pista_visual.artista_nombre) || _textoSeguro(pista_visual.artista) || _textoSeguro(reproductor.artista_activo) || "Artista desconocido") : "Selecciona una pista desde biblioteca"
    readonly property string album_seguro: hay_pista_visual ? (_textoSeguro(pista_visual.album_titulo) || _textoSeguro(pista_visual.album) || _textoSeguro(reproductor.album_activo)) : ""
    readonly property string portada_activa: pista_visual.portada_ruta ? UiUtils.toMediaSource(pista_visual.portada_ruta) : ""
    readonly property string icono_reproduccion: !puede_reproducir ? "../assets/icons/idle.svg" : (reproductor.reproduciendo ? "../assets/icons/pause.svg" : "../assets/icons/play.svg")
    readonly property int modo_responsive: width < 860 ? 0 : (width < 1180 ? 1 : 2)
    readonly property bool layout_compacto: modo_responsive === 0
    readonly property bool layout_medio: modo_responsive === 1
    readonly property bool layout_ancho: modo_responsive === 2
    readonly property bool karaoke_visible: reproductor.karaoke_disponible
    readonly property int columnas_utilidades: layout_compacto ? 4 : (karaoke_visible ? 7 : 6)
    property real margen_horizontal: layout_compacto ? UiTokens.spacing6 : UiTokens.spacing8
    property real margen_vertical: layout_compacto ? UiTokens.spacing8 : UiTokens.spacing10
    property real espaciado_barra: layout_compacto ? UiTokens.spacing6 : UiTokens.spacing8
    property real espaciado_controles: layout_compacto ? UiTokens.spacing6 : UiTokens.spacing10
    property real tam_portada: layout_compacto ? 46 : 60
    property real ancho_info: layout_compacto ? 150 : (layout_medio ? 240 : 320)
    property real ancho_info_min: layout_compacto ? 118 : (layout_medio ? 160 : 210)
    property real ancho_controles: layout_compacto ? 252 : (layout_medio ? 380 : 500)
    property real ancho_controles_min: layout_compacto ? 210 : (layout_medio ? 300 : 360)
    property real ancho_controles_max: layout_compacto ? 286 : (layout_medio ? 470 : 580)
    property real ancho_utilidades: layout_compacto ? 150 : (layout_medio ? (karaoke_visible ? 400 : 356) : (karaoke_visible ? 428 : 384))
    property real ancho_utilidades_min: layout_compacto ? 146 : (layout_medio ? (karaoke_visible ? 392 : 348) : (karaoke_visible ? 420 : 376))
    property real tam_boton: layout_compacto ? 30 : (layout_medio ? 34 : 36)
    property real alto_boton: layout_compacto ? 30 : 36
    property real tam_boton_principal: layout_compacto ? 38 : (layout_medio ? 42 : 44)
    property real alto_boton_principal: layout_compacto ? 36 : 40
    property real icono_boton: layout_compacto ? 15 : (layout_medio ? 16 : 17)
    property real icono_principal: layout_compacto ? 18 : (layout_medio ? 19 : 20)
    property real ancho_volumen: layout_compacto ? 54 : (layout_medio ? 82 : 104)
    property real ancho_progreso_min: layout_compacto ? 92 : (layout_medio ? 138 : 180)
    property real alto_slider: layout_compacto ? 24 : 26
    property bool progreso_drag_activo: false
    property real progreso_preview_ratio: 0
    property bool sorpresa_feedback_activo: false
    color: tema.fondoElevado
    clip: true
    property bool cola_visible: false

    Behavior on margen_horizontal { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on margen_vertical { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on espaciado_barra { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on espaciado_controles { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on tam_portada { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on ancho_info { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on ancho_info_min { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on ancho_controles { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on ancho_controles_min { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on ancho_controles_max { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on ancho_utilidades { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on ancho_utilidades_min { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on tam_boton { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on alto_boton { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on tam_boton_principal { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on alto_boton_principal { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on icono_boton { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on icono_principal { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on ancho_volumen { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on ancho_progreso_min { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
    Behavior on alto_slider { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }

    function _textoSeguro(valor) {
        if (valor === undefined || valor === null)
            return ""
        return String(valor).trim()
    }

    function _numeroSeguro(valor) {
        var numero = Number(valor)
        return isNaN(numero) ? 0 : numero
    }

    function _hayPistaActiva(pista) {
        if (!pista)
            return false
        return _textoSeguro(pista.id) !== ""
                || _textoSeguro(pista.ruta_archivo) !== ""
                || _textoSeguro(pista.titulo) !== ""
                || _textoSeguro(reproductor.titulo_activo) !== ""
    }

    function _textoTiempo(segundos) {
        return duracion_conocida ? reproductor.formatear_tiempo(segundos) : "--:--"
    }

    function _posicionVisualSeg() {
        if (!duracion_conocida)
            return 0
        if (progreso_drag_activo)
            return progreso_preview_ratio * _numeroSeguro(reproductor.duracion_seg)
        return _numeroSeguro(reproductor.posicion_seg)
    }

    function _ratioSeguro(valor) {
        return Math.max(0, Math.min(1, valor))
    }

    function _cancelarPreviewProgreso() {
        progreso_drag_activo = false
        progreso_preview_ratio = _ratioSeguro(reproductor.progreso_ratio)
    }

    function _accionSorprenderme() {
        var exito = reproductor.sorprenderme()
        sorpresa_feedback_activo = true
        sorpresa_feedback_timer.restart()
        if (!exito && shell) {
            shell.mostrar_toast_global("No hay sugerencias disponibles", "warning")
        }
    }

    function _alternarRepeticion() {
        var modos = ["ninguno", "todo", "uno"]
        var indice = modos.indexOf(reproductor.modo_repeticion)
        reproductor.set_modo_repeticion(modos[(indice + 1) % modos.length])
    }

    function alternar_cola() {
        if (cola_popup.opened || cola_visible) {
            cerrar_cola()
            return
        }
        cola_popup.open()
    }

    function cerrar_cola() {
        if (cola_popup.opened)
            cola_popup.close()
        cola_visible = false
    }

    function alternar_repeticion() {
        _alternarRepeticion()
    }

    AnimatedPlaybackBackground {
        anchors.fill: parent
        running: reproductor.reproduciendo
        phase: raiz.animacion_fase
        originX: raiz.animacion_origen_x
        worldWidth: raiz.animacion_ancho_mundo
        tema: raiz.tema
    }

    Timer {
        id: sorpresa_feedback_timer
        interval: 1300
        repeat: false
        onTriggered: sorpresa_feedback_activo = false
    }

    Rectangle { width: parent.width; height: 1; color: tema.borde; z: 2 }

    RowLayout {
        z: 1
        anchors {
            fill: parent
            leftMargin: raiz.margen_horizontal
            rightMargin: raiz.margen_horizontal
            topMargin: raiz.margen_vertical
            bottomMargin: raiz.margen_vertical
        }
        spacing: raiz.espaciado_barra

        RowLayout {
            Layout.alignment: Qt.AlignVCenter
            Layout.fillWidth: true
            Layout.minimumWidth: raiz.ancho_info_min
            Layout.preferredWidth: raiz.ancho_info
            Layout.maximumWidth: raiz.layout_compacto ? 210 : 380
            spacing: raiz.layout_compacto ? UiTokens.spacing6 : UiTokens.spacing12

            Rectangle {
                Layout.preferredWidth: raiz.tam_portada
                Layout.preferredHeight: raiz.tam_portada
                Layout.minimumWidth: raiz.tam_portada
                Layout.minimumHeight: raiz.tam_portada
                width: raiz.tam_portada
                height: raiz.tam_portada
                radius: UiTokens.radiusSm
                color: hay_pista_visual ? tema.superficieAlt : tema.superficie
                clip: true

                Image {
                    id: placeholder_portada_bar
                    visible: portada_activa === "" || portada.status === Image.Error
                    anchors.centerIn: parent
                    width: raiz.layout_compacto ? UiTokens.iconSm : UiTokens.iconMd
                    height: width
                    source: "../assets/icons/track.svg"
                    sourceSize.width: width * 2
                    sourceSize.height: height * 2
                    smooth: true
                    opacity: 0
                }
                MultiEffect {
                    visible: placeholder_portada_bar.visible
                    anchors.fill: placeholder_portada_bar
                    source: placeholder_portada_bar
                    colorization: 1.0
                    colorizationColor: tema.textoMuted
                }

                Image {
                    id: portada
                    visible: portada_activa !== "" && status !== Image.Error
                    anchors.fill: parent
                    source: portada_activa
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    smooth: true
                    sourceSize.width: 116
                    sourceSize.height: 116
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: UiTokens.spacing2

                LinkTexto {
                    Layout.fillWidth: true
                    texto: titulo_seguro
                    colorTexto: tema.texto
                    pixelSize: raiz.layout_compacto ? UiTokens.fontSizeMd : UiTokens.fontSizeLg
                    negrita: true
                    habilitado: hay_pista_activa
                    onClicked: {
                        if (shell) shell.abrir_pista_activa_en_biblioteca()
                    }
                }

                LinkTexto {
                    Layout.fillWidth: true
                    texto: artista_seguro
                    colorTexto: tema.textoSec
                    pixelSize: raiz.layout_compacto ? UiTokens.fontSizeSm : UiTokens.fontSizeMd
                    habilitado: hay_pista_activa
                    onClicked: {
                        if (!shell)
                            return
                        shell.abrir_artista_activo_en_biblioteca()
                    }
                }

                LinkTexto {
                    Layout.fillWidth: true
                    texto: album_seguro
                    visible: texto !== "" && !raiz.layout_compacto
                    colorTexto: tema.textoMuted
                    pixelSize: raiz.layout_compacto ? UiTokens.fontSizeXs : UiTokens.fontSizeSm
                    habilitado: hay_pista_activa
                    onClicked: {
                        if (shell) shell.abrir_album_activo_en_biblioteca()
                    }
                }
            }
        }

        ColumnLayout {
            Layout.alignment: Qt.AlignHCenter | Qt.AlignVCenter
            Layout.preferredWidth: raiz.ancho_controles
            Layout.minimumWidth: raiz.ancho_controles_min
            Layout.maximumWidth: raiz.ancho_controles_max
            spacing: raiz.layout_compacto ? UiTokens.spacing4 : UiTokens.spacing8

            RowLayout {
                Layout.alignment: Qt.AlignHCenter

                spacing: raiz.espaciado_controles
                BtnControl {
                    iconSource: "../assets/icons/shuffle.svg"
                    activo: reproductor.aleatorio
                    onClicked: reproductor.set_aleatorio(!reproductor.aleatorio)
                }
                BtnControl {
                    iconSource: "../assets/icons/prev.svg"
                    enabled: puede_reproducir
                    onClicked: reproductor.anterior()
                }
                BtnControl {
                    primary: true
                    iconSource: icono_reproduccion
                    enabled: puede_reproducir
                    onClicked: reproductor.pausar_reanudar()
                }
                BtnControl {
                    iconSource: "../assets/icons/next.svg"
                    enabled: puede_reproducir
                    onClicked: reproductor.siguiente()
                }
                BtnControl {
                    iconSource: "../assets/icons/repeat.svg"
                    activo: reproductor.modo_repeticion !== "ninguno"
                    badgeText: reproductor.modo_repeticion === "uno" ? "1" : ""
                    onClicked: _alternarRepeticion()
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: raiz.layout_compacto ? UiTokens.spacing6 : UiTokens.spacing10
                AppText {
                    text: _textoTiempo(_posicionVisualSeg())
                    font.pixelSize: raiz.layout_compacto ? UiTokens.fontSizeXs : UiTokens.fontSizeSm
                    color: tema.textoMuted
                    Layout.preferredWidth: raiz.layout_compacto ? 39 : 44
                    horizontalAlignment: Text.AlignRight
                    maximumLineCount: 1
                    elide: Text.ElideRight
                }
                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: raiz.alto_slider
                    Layout.minimumWidth: raiz.ancho_progreso_min

                    SliderLine {
                        id: slider_progreso
                        anchors.fill: parent
                        tema: raiz.tema
                        ratio: progreso_drag_activo ? progreso_preview_ratio : _ratioSeguro(reproductor.progreso_ratio)
                        live: false
                        visualHeight: raiz.layout_compacto ? 4 : 5
                        handleBaseSize: raiz.layout_compacto ? 9 : 10
                        handleActiveSize: raiz.layout_compacto ? 13 : 14
                        enabled: duracion_conocida
                        onPreviewed: function(ratio) {
                            raiz.progreso_drag_activo = true
                            raiz.progreso_preview_ratio = ratio
                        }
                        onCommitted: function(ratio) {
                            raiz.progreso_preview_ratio = ratio
                            reproductor.buscar_posicion(ratio * reproductor.duracion_seg)
                            raiz.progreso_drag_activo = false
                        }
                        onCanceled: {
                            raiz._cancelarPreviewProgreso()
                        }
                    }
                }
                AppText {
                    text: _textoTiempo(reproductor.duracion_seg)
                    font.pixelSize: raiz.layout_compacto ? UiTokens.fontSizeXs : UiTokens.fontSizeSm
                    color: tema.textoMuted
                    Layout.preferredWidth: raiz.layout_compacto ? 39 : 44
                    maximumLineCount: 1
                    elide: Text.ElideRight
                }
            }
        }

        Item {
            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
            Layout.fillWidth: false
            Layout.minimumWidth: raiz.ancho_utilidades_min
            Layout.preferredWidth: raiz.ancho_utilidades
            Layout.maximumWidth: raiz.ancho_utilidades
            Layout.fillHeight: true

            GridLayout {
                id: matriz_utilidades
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                columns: raiz.columnas_utilidades
                rowSpacing: raiz.layout_compacto ? UiTokens.spacing2 : 0
                columnSpacing: raiz.layout_compacto ? UiTokens.spacing4 : UiTokens.spacing8

                BtnControl {
                    iconSource: "../assets/icons/surprise.svg"
                    activo: reproductor.sorpresa_activa || sorpresa_feedback_activo
                    Layout.row: 0
                    Layout.column: 0
                    onClicked: _accionSorprenderme()
                }

                BtnControl {
                    id: boton_karaoke
                    visible: reproductor.karaoke_disponible
                    controlWidth: raiz.layout_compacto ? raiz.tam_boton : 36
                    controlHeight: raiz.alto_boton
                    iconSource: "../assets/icons/karaoke.svg"
                    activo: reproductor.karaoke_activo
                    Layout.row: 0
                    Layout.column: 1
                    onClicked: {
                        var exito = reproductor.alternar_karaoke()
                        if (shell) {
                            shell.mostrar_toast_global(
                                        exito
                                        ? (reproductor.karaoke_activo ? "Karaoke activo" : "Audio original")
                                        : "Karaoke no disponible",
                                        exito ? "info" : "warning")
                        }
                    }
                }

                BtnControl {
                    id: boton_lyrics
                    controlWidth: raiz.layout_compacto ? raiz.tam_boton : 36
                    controlHeight: raiz.alto_boton
                    iconSource: "../assets/icons/lyrics.svg"
                    activo: !!shell && shell.reproduccion_lyrics_activado
                    enabled: hay_pista_activa
                    Layout.row: 0
                    Layout.column: raiz.karaoke_visible ? 2 : 1
                    onClicked: {
                        if (shell) {
                            if (shell.reproduccion_expandida_visible)
                                shell.alternar_lyrics_en_fullscreen()
                            else
                                shell.alternar_vista_lyrics()
                        }
                    }
                }

                BtnControl {
                    id: boton_cola
                    controlWidth: raiz.layout_compacto
                                  ? Math.max(40, Math.min(54, (reproductor.cola.total > 99 ? 54 : 44)))
                                  : Math.max(46, Math.min(84, (reproductor.cola.total > 99 ? 84 : 70)))
                    controlHeight: raiz.alto_boton
                    iconSource: "../assets/icons/playlist.svg"
                    secondaryText: String(reproductor.cola.total)
                    activo: cola_visible
                    Layout.row: 0
                    Layout.column: raiz.karaoke_visible ? 3 : 2
                    Layout.minimumWidth: raiz.layout_compacto ? 40 : 46
                    Layout.maximumWidth: raiz.layout_compacto ? 54 : 84
                    onClicked: alternar_cola()

                    Popup {
                        id: cola_popup
                        readonly property real popupMargen: UiTokens.spacing6
                        readonly property real popupSeparacion: raiz.layout_compacto ? UiTokens.spacing12 : (UiTokens.spacing24 + UiTokens.spacing6)
                        readonly property real popupAnchoObjetivo: raiz.layout_compacto ? 340 : 440
                        readonly property real popupAltoObjetivo: raiz.layout_compacto ? 360 : 328
                        parent: Overlay.overlay
                        readonly property real popupViewportWidth: parent ? parent.width : raiz.width
                        readonly property real popupViewportHeight: parent ? parent.height : raiz.height
                        property real popupBotonCentroX: popupViewportWidth / 2
                        property real popupBotonTopY: raiz.height
                        z: raiz.capa_cola_z
                        function sincronizar_geometria() {
                            if (!parent || !shell)
                                return
                            var referencia = shell.contentItem ? shell.contentItem : raiz
                            var centro = boton_cola.mapToItem(referencia, boton_cola.width / 2, 0)
                            var origen = boton_cola.mapToItem(referencia, 0, 0)
                            popupBotonCentroX = centro.x
                            popupBotonTopY = origen.y
                        }
                        x: {
                            return Math.max(
                                        popupMargen,
                                        Math.min(popupBotonCentroX - (width / 2),
                                                 popupViewportWidth - width - popupMargen))
                        }
                        y: Math.max(popupMargen, popupBotonTopY - height - popupSeparacion)
                        width: Math.min(popupAnchoObjetivo, Math.max(0, popupViewportWidth - (popupMargen * 2)))
                        height: Math.min(popupAltoObjetivo, Math.max(0, popupBotonTopY - popupSeparacion - popupMargen))
                        margins: popupMargen
                        padding: 0
                        modal: true
                        dim: false
                        focus: true
                        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
                        background: Rectangle { color: "transparent" }
                        contentItem: QueuePanel {
                            tema: raiz.tema
                            padding: UiTokens.spacing12
                        }
                        onAboutToShow: Qt.callLater(sincronizar_geometria)
                        onOpened: {
                            cola_visible = true
                            Qt.callLater(sincronizar_geometria)
                        }
                        onClosed: cola_visible = false

                        Connections {
                            target: boton_cola
                            enabled: cola_popup.visible || cola_popup.opened
                            function onXChanged() { cola_popup.sincronizar_geometria() }
                            function onYChanged() { cola_popup.sincronizar_geometria() }
                            function onWidthChanged() { cola_popup.sincronizar_geometria() }
                            function onHeightChanged() { cola_popup.sincronizar_geometria() }
                        }

                        Connections {
                            target: raiz
                            enabled: cola_popup.visible || cola_popup.opened
                            function onWidthChanged() { cola_popup.sincronizar_geometria() }
                            function onHeightChanged() { cola_popup.sincronizar_geometria() }
                            function onLayout_compactoChanged() { cola_popup.sincronizar_geometria() }
                        }

                        Connections {
                            target: shell
                            enabled: !!shell && (cola_popup.visible || cola_popup.opened)
                            function onWidthChanged() { cola_popup.sincronizar_geometria() }
                            function onHeightChanged() { cola_popup.sincronizar_geometria() }
                        }
                    }
                }

                Item {
                    id: control_volumen
                    Layout.row: raiz.layout_compacto ? 1 : 0
                    Layout.column: raiz.layout_compacto ? 0 : (raiz.karaoke_visible ? 4 : 3)
                    Layout.columnSpan: raiz.layout_compacto ? 2 : 1
                    Layout.preferredWidth: raiz.ancho_volumen + (raiz.layout_compacto ? 20 : 26)
                    Layout.preferredHeight: raiz.alto_slider
                    Layout.minimumWidth: raiz.layout_compacto ? 70 : 100

                    RowLayout {
                        anchors.fill: parent
                        spacing: raiz.layout_compacto ? UiTokens.spacing4 : UiTokens.spacing6

                        Image {
                            source: "../assets/icons/volume.svg"
                            Layout.preferredWidth: raiz.layout_compacto ? 14 : 18
                            Layout.preferredHeight: raiz.layout_compacto ? 14 : 18
                            opacity: reproductor.volumen > 0 ? 1.0 : 0.45
                        }

                        Item {
                            Layout.fillWidth: true
                            Layout.minimumWidth: raiz.layout_compacto ? 48 : 72
                            Layout.preferredHeight: raiz.alto_slider

                            SliderLine {
                                anchors.fill: parent
                                tema: raiz.tema
                                ratio: _ratioSeguro(reproductor.volumen / 100)
                                visualHeight: raiz.layout_compacto ? 4 : 5
                                handleBaseSize: raiz.layout_compacto ? 8 : 10
                                handleActiveSize: raiz.layout_compacto ? 12 : 14
                                enabled: true
                                onMoved: function(ratio) {
                                    reproductor.set_volumen(Math.round(ratio * 100))
                                }
                            }
                        }
                    }
                }

                BtnControl {
                    iconSource: "../assets/icons/miniplayer.svg"
                    activo: !!shell && shell.mini_reproductor_activo
                    Layout.row: raiz.layout_compacto ? 1 : 0
                    Layout.column: raiz.layout_compacto ? 2 : (raiz.karaoke_visible ? 5 : 4)
                    onClicked: {
                        if (shell) shell.alternar_modo_mini_reproductor()
                    }
                }

                BtnControl {
                    iconSource: "../assets/icons/fullscreen.svg"
                    activo: !!shell && shell.reproduccion_expandida_visible
                    enabled: hay_pista_activa
                    Layout.row: raiz.layout_compacto && raiz.karaoke_visible ? 1 : 0
                    Layout.column: raiz.layout_compacto ? 3 : (raiz.karaoke_visible ? 6 : 5)
                    onClicked: {
                        if (shell) shell.alternar_visualizacion_ampliada()
                    }
                }
            }
        }
    }

    component LinkTexto: Item {
        id: link
        property string texto: ""
        property color colorTexto: "white"
        property int pixelSize: 12
        property bool negrita: false
        property bool habilitado: true
        signal clicked()

        implicitHeight: texto_link.implicitHeight
        implicitWidth: texto_link.implicitWidth

        AppText {
            id: texto_link
            anchors.fill: parent
            text: link.texto
            color: link.habilitado && area_link.containsMouse ? tema.acento : link.colorTexto
            font.pixelSize: link.pixelSize
            font.bold: link.negrita
            elide: Text.ElideRight
            maximumLineCount: 1
            textFormat: Text.PlainText
            verticalAlignment: Text.AlignVCenter
        }

        MouseArea {
            id: area_link
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(texto_link.paintedWidth, link.width)
            height: texto_link.paintedHeight
            enabled: link.habilitado && link.texto !== ""
            hoverEnabled: true
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: link.clicked()
        }

    }

    component BtnControl: Button {
        id: btn
        property string texto: ""
        property string iconSource: ""
        property bool activo: false
        property bool primary: false
        property string badgeText: ""
        property string secondaryText: ""
        property real controlWidth: primary ? raiz.tam_boton_principal : raiz.tam_boton
        property real controlHeight: primary ? raiz.alto_boton_principal : raiz.alto_boton
        property real iconSize: primary ? raiz.icono_principal : raiz.icono_boton

        function _fondoBoton() {
            if (!enabled)
                return primary ? tema.borde : "transparent"
            if (primary)
                return down || hovered ? tema.acentoFuerte : tema.acento
            if (down)
                return Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.26)
            if (activo)
                return Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.18)
            if (hovered)
                return tema.hover
            return "transparent"
        }

        function _bordeBoton() {
            if (_tieneBordeBoton() && activo)
                return tema.acento
            if (_tieneBordeBoton() && down)
                return Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.52)
            return "transparent"
        }

        function _tieneBordeBoton() {
            return enabled && !primary && (activo || down)
        }

        function _colorIcono() {
            if (!enabled)
                return tema.textoMuted
            if (primary)
                return tema.fondo
            if (activo || down)
                return tema.acento
            if (hovered)
                return tema.texto
            return tema.textoSec
        }

        text: texto
        padding: 0
        hoverEnabled: true
        focusPolicy: Qt.TabFocus
        implicitWidth: controlWidth
        implicitHeight: controlHeight
        Layout.preferredWidth: controlWidth
        Layout.preferredHeight: controlHeight
        opacity: enabled ? 1.0 : 0.45
        scale: down && enabled ? 0.96 : 1.0

        Behavior on scale { NumberAnimation { duration: UiTokens.durationFast } }
        Behavior on controlWidth { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
        Behavior on controlHeight { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
        Behavior on iconSize { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }

        background: Rectangle {
            radius: UiTokens.radiusSm
            color: btn._fondoBoton()
            border.color: btn._bordeBoton()
            border.width: btn._tieneBordeBoton() ? 1 : 0

            Behavior on color { ColorAnimation { duration: UiTokens.durationBase } }
            Behavior on border.color { ColorAnimation { duration: UiTokens.durationBase } }
        }

        HoverHandler {
            enabled: btn.enabled
            cursorShape: Qt.PointingHandCursor
        }

        contentItem: Item {
            implicitWidth: btn.controlWidth
            implicitHeight: btn.controlHeight

            AppText {
                anchors.centerIn: parent
                text: btn.texto
                visible: btn.iconSource === "" && btn.secondaryText === ""
                color: btn._colorIcono()
                font.pixelSize: UiTokens.fontSizeBase
                font.bold: btn.activo || btn.primary || btn.down
                maximumLineCount: 1
                elide: Text.ElideRight
            }

            Item {
                visible: btn.iconSource !== "" && btn.secondaryText === ""
                width: btn.iconSize
                height: btn.iconSize
                anchors.centerIn: parent

                Image {
                    id: icono_btn
                    anchors.fill: parent
                    source: btn.iconSource
                    opacity: 0
                    smooth: true
                    sourceSize.width: btn.iconSize
                    sourceSize.height: btn.iconSize
                }

                MultiEffect {
                    anchors.fill: icono_btn
                    source: icono_btn
                    colorization: 1.0
                    colorizationColor: btn._colorIcono()
                }
            }

            Row {
                visible: btn.iconSource !== "" && btn.secondaryText !== ""
                anchors.centerIn: parent
                spacing: UiTokens.spacing6

                Item {
                    width: btn.iconSize
                    height: btn.iconSize
                    anchors.verticalCenter: parent.verticalCenter

                    Image {
                        id: icono_btn_inline
                        anchors.fill: parent
                        source: btn.iconSource
                        opacity: 0
                        smooth: true
                        sourceSize.width: btn.iconSize
                        sourceSize.height: btn.iconSize
                    }

                    MultiEffect {
                        anchors.fill: icono_btn_inline
                        source: icono_btn_inline
                        colorization: 1.0
                        colorizationColor: btn._colorIcono()
                    }
                }

                AppText {
                    text: btn.secondaryText
                    color: btn._colorIcono()
                    font.pixelSize: UiTokens.fontSizeSm
                    font.bold: btn.activo
                    maximumLineCount: 1
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }

        Rectangle {
            visible: badgeText !== ""
            width: 14
            height: 14
            radius: 7
            anchors.right: parent.right
            anchors.rightMargin: 3
            anchors.top: parent.top
            anchors.topMargin: 3
            color: tema.acento
            AppText {
                anchors.centerIn: parent
                text: badgeText
                color: tema.fondo
                font.pixelSize: 9
                font.bold: true
            }
        }
    }

    TapHandler {
        acceptedButtons: Qt.LeftButton
        onTapped: {
            if (shell)
                shell.activar_atajos_reproduccion()
        }
    }

    // ── OVERLAY MODO DJ ──────────────────────────────────────────────────
    //
    // Cuando una sesion DJ Privado tiene el control de audio, cubrimos la
    // barra global con un mensaje claro: el reproductor tradicional esta
    // suspendido y los controles aqui no controlan la sesion DJ (que tiene
    // su propio reproductor). Atajo para volver a la vista DJ.
    Rectangle {
        id: overlay_modo_dj
        anchors.fill: parent
        visible: reproductor.modo_dj_activo
        color: Qt.rgba(raiz.tema.fondoElevado.r, raiz.tema.fondoElevado.g, raiz.tema.fondoElevado.b, 0.96)
        z: 99

        // Punto pulsante a la izquierda
        Rectangle {
            id: pulso_dj
            anchors.left: parent.left
            anchors.leftMargin: UiTokens.spacing16
            anchors.verticalCenter: parent.verticalCenter
            width: 12; height: 12; radius: 6
            color: raiz.tema.acento
            SequentialAnimation on opacity {
                running: overlay_modo_dj.visible
                loops: Animation.Infinite
                NumberAnimation { from: 1.0; to: 0.4; duration: 800; easing.type: Easing.InOutQuad }
                NumberAnimation { from: 0.4; to: 1.0; duration: 800; easing.type: Easing.InOutQuad }
            }
        }

        ColumnLayout {
            anchors.left: pulso_dj.right
            anchors.leftMargin: UiTokens.spacing14
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: btn_volver_dj.left
            anchors.rightMargin: UiTokens.spacing16
            spacing: UiTokens.spacing2
            AppText {
                text: "DJ Privado en sesión"
                color: raiz.tema.acento
                font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            AppText {
                text: "El reproductor global está suspendido. Vuelve a la vista DJ para controlar la sesión."
                color: raiz.tema.textoMuted
                font.pixelSize: UiTokens.fontSizeSm
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
        }

        Rectangle {
            id: btn_volver_dj
            anchors.right: parent.right
            anchors.rightMargin: UiTokens.spacing16
            anchors.verticalCenter: parent.verticalCenter
            implicitWidth: lbl_volver.implicitWidth + 28
            implicitHeight: 32
            radius: 16
            color: ma_volver.containsMouse ? raiz.tema.acentoFuerte : raiz.tema.acento
            AppText {
                id: lbl_volver
                anchors.centerIn: parent
                text: "Volver a DJ Privado"
                color: tema.textoSobreAcento
                font.pixelSize: UiTokens.fontSizeMd; font.weight: Font.DemiBold
            }
            MouseArea {
                id: ma_volver
                anchors.fill: parent; hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    if (shell && shell.navegar_a_vista) {
                        shell.navegar_a_vista("dj_privado")
                    }
                }
            }
        }

        // Captura clicks para que no atraviesen al control oculto debajo.
        MouseArea {
            anchors.fill: parent
            anchors.rightMargin: btn_volver_dj.width + 32
            hoverEnabled: false
            onClicked: {}
        }
    }
}
