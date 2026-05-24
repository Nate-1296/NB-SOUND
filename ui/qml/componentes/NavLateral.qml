import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import "."
import "UiUtils.js" as UiUtils

Rectangle {
    id: raiz
    property var shell: null
    property real animacion_fase: 0
    property real animacion_origen_x: 0
    property real animacion_ancho_mundo: width
    readonly property var tema: shell ? shell.tema : temaUi
    readonly property bool temaClaro: tema.fondo.hslLightness > 0.62
    readonly property bool compacto_vertical: height > 0 && height < 980
    readonly property bool estrecho_vertical: height > 0 && height < 760
    readonly property bool minimo_vertical: height > 0 && height < 640
    readonly property int margen_nav: minimo_vertical ? UiTokens.spacing4 : (estrecho_vertical ? UiTokens.spacing6 : (compacto_vertical ? UiTokens.spacing8 : UiTokens.spacing12))
    readonly property int espaciado_nav: minimo_vertical ? 0 : (compacto_vertical ? UiTokens.spacing2 : UiTokens.spacing4)
    readonly property int alto_marca_nav: minimo_vertical ? 24 : (estrecho_vertical ? 32 : (compacto_vertical ? 42 : 68))
    readonly property int alto_separador_nav: minimo_vertical ? 10 : (estrecho_vertical ? 14 : (compacto_vertical ? 18 : 34))
    readonly property int alto_item_nav: minimo_vertical ? 28 : (estrecho_vertical ? 30 : (compacto_vertical ? 34 : UiTokens.controlHeightLg))
    readonly property int alto_modo_nav: minimo_vertical ? 30 : (estrecho_vertical ? 36 : (compacto_vertical ? 44 : 64))
    readonly property int separacion_final_nav: minimo_vertical ? 2 : (estrecho_vertical ? 3 : (compacto_vertical ? 4 : 12))
    readonly property int font_marca_nav: minimo_vertical ? 14 : (estrecho_vertical ? 16 : (compacto_vertical ? 19 : UiTokens.fontSizeDisplay))
    readonly property int font_item_nav: minimo_vertical ? UiTokens.fontSizeSm : (compacto_vertical ? UiTokens.fontSizeMd : UiTokens.fontSizeLg)
    readonly property int icono_item_nav: compacto_vertical ? UiTokens.iconSm : UiTokens.iconMd
    color: tema.fondoElevado
    radius: 0
    clip: true

    signal navegar(string vista)
    property string vista_activa: "inicio"

    property string modo_ui: configuracion.obtener("ui_mode") || "simple"
    property string foto_perfil: configuracion.obtener("foto_perfil") || ""
    property string nombre_usuario: configuracion.obtener("nombre_usuario") || ""
    property bool es_pro: modo_ui === "pro"
    property int badge_pendientes: revision ? revision.total_revision + revision.total_cuarentena : 0

    function cambiarModo() {
        modo_ui = es_pro ? "simple" : "pro"
        configuracion.guardar("ui_mode", modo_ui)
    }

    Connections {
        target: configuracion
        function onConfiguracionCambiada() {
            raiz.modo_ui = configuracion.obtener("ui_mode") || "simple"
            raiz.foto_perfil = configuracion.obtener("foto_perfil") || ""
            raiz.nombre_usuario = configuracion.obtener("nombre_usuario") || ""
        }
    }

    AnimatedPlaybackBackground {
        anchors.fill: parent
        running: reproductor.reproduciendo
        phase: raiz.animacion_fase
        originX: raiz.animacion_origen_x
        worldWidth: raiz.animacion_ancho_mundo
        tema: raiz.tema
        z: 0
    }

    ScrollView {
        id: nav_scroll
        anchors.fill: parent
        z: 1
        clip: true
        contentWidth: availableWidth
        contentHeight: nav_contenido.implicitHeight + raiz.margen_nav
        ScrollBar.vertical: AppScrollBar {
            parent: nav_scroll
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            z: 20
            tema: raiz.tema
            policy: nav_scroll.contentHeight > nav_scroll.height + 2 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
        }

        ColumnLayout {
            id: nav_contenido
            x: raiz.margen_nav
            y: raiz.margen_nav
            width: Math.max(0, parent.width - (raiz.margen_nav * 2))
            spacing: raiz.espaciado_nav

            ColumnLayout {
                id: bloque_superior
                Layout.fillWidth: true
                spacing: raiz.espaciado_nav

                Item {
                    Layout.fillWidth: true
                    height: raiz.alto_marca_nav

                    AppText {
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.verticalCenter: parent.verticalCenter
                        text: "NB SOUND"
                        font.pixelSize: raiz.font_marca_nav
                        font.weight: Font.DemiBold
                        color: tema.texto
                        opacity: 0.97
                        font.letterSpacing: raiz.compacto_vertical ? 0.35 : 0.9
                    }
                }

                Separador { etiqueta: "EXPLORAR" }
                ElementoNav { id: nav_inicio; icono: "../assets/icons/nav/inicio.svg"; etiqueta: "Inicio"; activo: vista_activa === "inicio"; focoSiguiente: nav_buscar; onClicked: navegar("inicio") }
                ElementoNav { id: nav_buscar; icono: "../assets/icons/nav/buscar.svg"; etiqueta: "Buscar"; activo: vista_activa === "busqueda"; focoAnterior: nav_inicio; focoSiguiente: nav_biblioteca; onClicked: navegar("busqueda") }

                Separador { etiqueta: "TU MÚSICA" }
                ElementoNav { id: nav_biblioteca; icono: "../assets/icons/nav/biblioteca.svg"; etiqueta: "Biblioteca"; activo: vista_activa === "biblioteca"; focoAnterior: nav_buscar; focoSiguiente: nav_playlists; onClicked: navegar("biblioteca") }
                ElementoNav { id: nav_playlists; icono: "../assets/icons/nav/playlists.svg"; etiqueta: "Playlists"; activo: vista_activa === "playlists"; focoAnterior: nav_biblioteca; focoSiguiente: nav_dj_privado; onClicked: navegar("playlists") }

                Separador { etiqueta: "EXPERIENCIAS" }
                ElementoNav { id: nav_dj_privado; icono: "../assets/icons/nav/dj_privado.svg"; etiqueta: "DJ Privado"; activo: vista_activa === "dj_privado"; focoAnterior: nav_playlists; focoSiguiente: nav_a_ciegas; onClicked: navegar("dj_privado") }
                ElementoNav { id: nav_a_ciegas; icono: "../assets/icons/nav/a_ciegas.svg"; etiqueta: "¡A ciegas!"; activo: vista_activa === "explorador_ciego"; focoAnterior: nav_dj_privado; focoSiguiente: nav_importacion; onClicked: navegar("explorador_ciego") }

                Separador { etiqueta: "SISTEMA" }
                ElementoNav {
                    id: nav_importacion
                    icono: "../assets/icons/nav/importar.svg"
                    etiqueta: "Importar"
                    activo: vista_activa === "importacion"
                    badge: badge_pendientes
                    focoAnterior: nav_a_ciegas
                    focoSiguiente: nav_karaoke
                    onClicked: navegar("importacion")
                }
                ElementoNav { id: nav_karaoke; icono: "../assets/icons/nav/preparar_karaoke.svg"; etiqueta: "Preparar Karaoke"; activo: vista_activa === "karaoke"; focoAnterior: nav_importacion; focoSiguiente: nav_configuracion; onClicked: navegar("karaoke") }
                ElementoNav { id: nav_configuracion; icono: "../assets/icons/nav/configuracion.svg"; etiqueta: "Configuración"; activo: vista_activa === "configuracion"; focoAnterior: nav_karaoke; focoSiguiente: nav_estado_sistema; onClicked: navegar("configuracion") }
                ElementoNav {
                    id: nav_estado_sistema
                    icono: "../assets/icons/nav/configuracion.svg"
                    etiqueta: "Estado del Sistema"
                    activo: vista_activa === "estado_sistema"
                    focoAnterior: nav_configuracion
                    focoSiguiente: toggle_modo
                    onClicked: navegar("estado_sistema")
                }
            }

            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(
                                            UiTokens.spacing8,
                                            nav_scroll.height
                                            - (raiz.margen_nav * 2)
                                            - bloque_superior.implicitHeight
                                            - bloque_inferior.implicitHeight
                                        )
            }

            ColumnLayout {
                id: bloque_inferior
                Layout.fillWidth: true
                spacing: raiz.espaciado_nav

                Item {
                    Layout.fillWidth: true
                    height: raiz.alto_modo_nav

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: raiz.compacto_vertical ? 8 : 12
                        anchors.rightMargin: raiz.compacto_vertical ? 8 : 12
                        spacing: raiz.compacto_vertical ? UiTokens.spacing6 : UiTokens.spacing8

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            AppText { text: es_pro ? "Modo Pro" : "Modo Simple"; color: tema.texto; font.pixelSize: raiz.compacto_vertical ? UiTokens.fontSizeSm : UiTokens.fontSizeMd; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                            AppText { text: es_pro ? "Interfaz Avanzada" : "Interfaz simplificada"; color: tema.textoMuted; font.pixelSize: UiTokens.fontSizeXs; Layout.fillWidth: true; elide: Text.ElideRight; visible: !raiz.estrecho_vertical && !raiz.minimo_vertical }
                        }
                        Rectangle {
                            id: toggle_modo
                            property var focoAnterior: nav_configuracion
                            property var focoSiguiente: nav_perfil
                            property bool focoTecladoVisible: false
                            width: raiz.minimo_vertical ? 54 : (raiz.compacto_vertical ? 62 : 76); height: raiz.minimo_vertical ? 22 : (raiz.compacto_vertical ? 24 : UiTokens.controlHeightSm); radius: height / 2
                            color: toggle.containsMouse ? tema.acentoFuerte : tema.acento
                            activeFocusOnTab: true
                            border.width: 0
                            border.color: "transparent"

                            function enfocarObjetivo(objetivo, razon) {
                                if (!objetivo)
                                    return false
                                objetivo.focoTecladoVisible = true
                                objetivo.forceActiveFocus(razon)
                                return true
                            }
                            function enfocarSiguiente() {
                                return enfocarObjetivo(focoSiguiente, Qt.TabFocusReason)
                            }
                            function enfocarAnterior() {
                                return enfocarObjetivo(focoAnterior, Qt.BacktabFocusReason)
                            }
                            function activar() {
                                focoTecladoVisible = false
                                cambiarModo()
                            }
                            function manejarNavegacionTeclado(event) {
                                if (event.key === Qt.Key_Tab && (event.modifiers & Qt.ControlModifier)) {
                                    event.accepted = enfocarAnterior()
                                    return
                                }
                                if (event.key === Qt.Key_Backtab || (event.key === Qt.Key_Tab && (event.modifiers & Qt.ShiftModifier))) {
                                    event.accepted = enfocarAnterior()
                                    return
                                }
                                if (event.key === Qt.Key_Tab) {
                                    event.accepted = enfocarSiguiente()
                                }
                            }
                            onActiveFocusChanged: {
                                if (!activeFocus)
                                    focoTecladoVisible = false
                            }
                            Keys.priority: Keys.BeforeItem
                            Keys.onReturnPressed: activar()
                            Keys.onEnterPressed: activar()
                            Keys.onPressed: function(event) { manejarNavegacionTeclado(event) }
                            AppText { anchors.centerIn: parent; text: raiz.minimo_vertical ? (es_pro ? "Pro" : "Simple") : (es_pro ? "Cambiar" : "Activar"); color: tema.textoSobreAcento; font.bold: true; font.pixelSize: raiz.compacto_vertical ? UiTokens.fontSizeXs : UiTokens.fontSizeSm }
                            Rectangle {
                                anchors.fill: parent
                                radius: parent.radius
                                color: "transparent"
                                border.width: toggle_modo.focoTecladoVisible && toggle_modo.activeFocus ? 2 : 0
                                border.color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, raiz.temaClaro ? 0.78 : 0.92)
                                visible: border.width > 0
                            }
                            MouseArea {
                                id: toggle
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onPressed: {
                                    toggle_modo.focoTecladoVisible = false
                                    toggle_modo.forceActiveFocus(Qt.MouseFocusReason)
                                }
                                onClicked: toggle_modo.activar()
                            }
                        }
                    }
                }

                ElementoNav {
                    id: nav_perfil
                    icono: "../assets/icons/nav/perfil_fallback.svg"
                    avatarRuta: foto_perfil
                    etiqueta: raiz.nombre_usuario.length > 0 ? raiz.nombre_usuario : "Perfil"
                    activo: vista_activa === "perfil"
                    focoAnterior: toggle_modo
                    onClicked: navegar("perfil")
                }
                Item { height: raiz.separacion_final_nav }
            }
        }
    }

    component Separador: Item {
        property string etiqueta: ""
        Layout.fillWidth: true
        height: raiz.alto_separador_nav
        AppText {
            anchors.left: parent.left
            anchors.leftMargin: raiz.compacto_vertical ? 10 : 14
            anchors.bottom: parent.bottom
            anchors.bottomMargin: raiz.compacto_vertical ? 2 : 4
            text: etiqueta
            font.pixelSize: UiTokens.fontSizeXs
            font.bold: true
            color: tema.textoMuted
            font.letterSpacing: raiz.compacto_vertical ? 1.1 : 1.6
        }
    }

    component ElementoNav: Item {
        id: elemento_nav
        property string icono: ""
        property string avatarRuta: ""
        property string etiqueta: ""
        property bool activo: false
        property int badge: 0
        property var focoAnterior: null
        property var focoSiguiente: null
        property bool focoTecladoVisible: false
        readonly property bool presionadoVisible: area_mouse.pressed && area_mouse.containsMouse
        signal clicked()

        Layout.fillWidth: true
        height: raiz.alto_item_nav
        activeFocusOnTab: true

        function enfocarObjetivo(objetivo, razon) {
            if (!objetivo)
                return false
            objetivo.focoTecladoVisible = true
            objetivo.forceActiveFocus(razon)
            return true
        }
        function enfocarSiguiente() {
            return enfocarObjetivo(focoSiguiente, Qt.TabFocusReason)
        }
        function enfocarAnterior() {
            return enfocarObjetivo(focoAnterior, Qt.BacktabFocusReason)
        }
        function activar() {
            focoTecladoVisible = false
            clicked()
        }
        function manejarNavegacionTeclado(event) {
            if (event.key === Qt.Key_Tab && (event.modifiers & Qt.ControlModifier)) {
                event.accepted = enfocarAnterior()
                return
            }
            if (event.key === Qt.Key_Backtab || (event.key === Qt.Key_Tab && (event.modifiers & Qt.ShiftModifier))) {
                event.accepted = enfocarAnterior()
                return
            }
            if (event.key === Qt.Key_Tab) {
                event.accepted = enfocarSiguiente()
            }
        }
        onActiveFocusChanged: {
            if (!activeFocus)
                focoTecladoVisible = false
        }

        Keys.priority: Keys.BeforeItem
        Keys.onReturnPressed: activar()
        Keys.onEnterPressed: activar()
        Keys.onPressed: function(event) { manejarNavegacionTeclado(event) }

        Rectangle {
            anchors.fill: parent
            radius: UiTokens.radiusMd
            color: activo
                   ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.22)
                   : (elemento_nav.presionadoVisible
                      ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.24)
                      : (area_mouse.containsMouse
                         ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.10)
                         : "transparent"))
            border.color: activo
                          ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.52)
                          : "transparent"
            border.width: activo ? 1 : 0
            Behavior on color { ColorAnimation { duration: UiTokens.durationBase } }
            Behavior on border.color { ColorAnimation { duration: UiTokens.durationBase } }

            Rectangle {
                width: 3
                radius: 2
                height: parent.height - (raiz.compacto_vertical ? 10 : 12)
                anchors.left: parent.left
                anchors.leftMargin: UiTokens.spacing4
                anchors.verticalCenter: parent.verticalCenter
                color: activo ? tema.acento : "transparent"
            }

            RowLayout {
                anchors { fill: parent; leftMargin: raiz.compacto_vertical ? 12 : 16; rightMargin: raiz.compacto_vertical ? 8 : 10 }
                spacing: raiz.compacto_vertical ? 8 : 10
                Rectangle {
                    width: raiz.compacto_vertical ? 18 : 20
                    height: width
                    radius: UiTokens.radiusMd
                    color: avatarRuta ? Qt.rgba(tema.superficieAlt.r, tema.superficieAlt.g, tema.superficieAlt.b, 0.92) : "transparent"
                    clip: true

                    Image {
                        id: icono_avatar
                        anchors.centerIn: parent
                        source: avatarRuta ? UiUtils.toMediaSource(avatarRuta) : ""
                        width: parent.width
                        height: parent.height
                        visible: avatarRuta !== "" && status !== Image.Error
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                    }

                    Image {
                        id: icono_fuente
                        anchors.centerIn: parent
                        source: icono
                        width: raiz.icono_item_nav
                        height: raiz.icono_item_nav
                        visible: !icono_avatar.visible
                        sourceSize.width: raiz.icono_item_nav
                        sourceSize.height: raiz.icono_item_nav
                        // layer.effect requires hardware GL; in software renderer
                        // (QT_QUICK_BACKEND=software) layer.enabled:true with an
                        // effect makes the entire item transparent. Disabling the
                        // layer when hardware GL is unavailable shows the icon in
                        // its native SVG colour instead.
                        layer.enabled: GraphicsInfo.api !== GraphicsInfo.Software
                        layer.effect: MultiEffect {
                            colorization: 1.0
                            colorizationColor: activo
                                              ? tema.texto
                                              : (elemento_nav.presionadoVisible
                                                 ? tema.acento
                                                 : (area_mouse.containsMouse ? tema.texto : tema.textoSec))
                        }
                    }
                }
                AppText { text: etiqueta; font.pixelSize: raiz.font_item_nav; font.weight: activo ? Font.DemiBold : Font.Normal; color: activo ? tema.texto : tema.textoSec; Layout.fillWidth: true; elide: Text.ElideRight }
                Rectangle { visible: badge > 0; width: Math.max(20, badge_txt.implicitWidth + 8); height: 18; radius: 9; color: tema.peligro; AppText { id: badge_txt; anchors.centerIn: parent; text: badge > 99 ? "99+" : badge; font.pixelSize: UiTokens.fontSizeXs; font.bold: true; color: tema.textoSobrePeligro } }
            }
        }

        Rectangle {
            anchors.fill: parent
            radius: UiTokens.radiusMd
            color: "transparent"
            border.width: elemento_nav.focoTecladoVisible && elemento_nav.activeFocus ? 2 : 0
            border.color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, raiz.temaClaro ? 0.78 : 0.92)
            visible: border.width > 0
        }

        MouseArea {
            id: area_mouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onPressed: {
                elemento_nav.focoTecladoVisible = false
                elemento_nav.forceActiveFocus(Qt.MouseFocusReason)
            }
            onClicked: elemento_nav.activar()
        }
    }
}
