// =============================================================================
// componentes/MenuAgregarPlaylist.qml
//
// Selector "agregar a playlist" estilo Spotify, reutilizable desde cualquier
// vista donde aparezcan canciones en lista (Biblioteca, Búsqueda, detalle de
// playlist, reproductor global).
//
// Uso:
//   MenuAgregarPlaylist { id: menuAgregar; tema: raiz.tema; onGuardado: mostrar_toast(mensaje) }
//   ...
//   onClicked: menuAgregar.abrir(pista_id, titulo)
//
// Comportamiento:
//   - Al abrir, lee las playlists manuales del usuario y pre-marca las que ya
//     contienen la pista (`playlists.playlists_para_pista`).
//   - El usuario marca/desmarca y pulsa "Guardar": solo entonces se aplica el
//     diff (`playlists.aplicar_en_playlists`). Si cierra sin guardar, la
//     selección se descarta automáticamente (no se persiste nada).
//   - Permite crear una playlist nueva en el momento y queda preseleccionada.
// =============================================================================

pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtQuick.Effects
import "."

Popup {
    id: root

    property var tema: typeof temaUi !== "undefined" ? temaUi : null
    property int pistaId: -1
    property string pistaTitulo: ""

    // Estado interno del selector.
    property var _items: []          // [{playlist_id, nombre, num_pistas, contiene}]
    property var _seleccion: ({})    // { playlist_id: bool } — estado editable
    property var _inicial: ({})      // { playlist_id: bool } — estado al abrir
    property bool _creando: false

    signal guardado(string mensaje)

    function abrir(pid, titulo) {
        root.pistaId = pid
        root.pistaTitulo = titulo || ""
        root._cargarEstado()
        root.open()
    }

    function _cargarEstado() {
        var lista = playlists.playlists_para_pista(root.pistaId) || []
        var sel = ({})
        var ini = ({})
        for (var i = 0; i < lista.length; i++) {
            var id = lista[i].playlist_id
            var contiene = lista[i].contiene === true
            sel[id] = contiene
            ini[id] = contiene
        }
        root._items = lista
        root._seleccion = sel
        root._inicial = ini
        root._creando = false
        nuevoNombre.text = ""
    }

    function _estaSeleccionada(id) {
        return root._seleccion[id] === true
    }

    function _alternar(id) {
        // Reasignar un objeto nuevo para disparar la notificación de cambio
        // (mutar in-place no actualiza los bindings de los delegados).
        var copia = ({})
        for (var k in root._seleccion)
            copia[k] = root._seleccion[k]
        copia[id] = !(copia[id] === true)
        root._seleccion = copia
    }

    function _hayCambios() {
        for (var id in root._seleccion) {
            if ((root._seleccion[id] === true) !== (root._inicial[id] === true))
                return true
        }
        return false
    }

    function _guardar() {
        var agregar = []
        var quitar = []
        for (var id in root._seleccion) {
            var ahora = root._seleccion[id] === true
            var antes = root._inicial[id] === true
            if (ahora && !antes) agregar.push(parseInt(id))
            else if (!ahora && antes) quitar.push(parseInt(id))
        }
        if (agregar.length === 0 && quitar.length === 0) {
            root.close()
            return
        }
        var res = playlists.aplicar_en_playlists(root.pistaId, agregar, quitar)
        root.guardado(res && res.mensaje ? res.mensaje : "Playlists actualizadas")
        root.close()
    }

    function _crearPlaylist() {
        var nombre = nuevoNombre.text.trim()
        if (nombre === "")
            return
        var res = playlists.crear_playlist_para_seleccion(nombre)
        if (res && res.ok) {
            var nuevaId = res.playlist_id
            root._cargarEstado()           // recarga la lista (incluye la nueva)
            // Preseleccionar la recién creada para que se añada al guardar.
            var copia = ({})
            for (var k in root._seleccion)
                copia[k] = root._seleccion[k]
            copia[nuevaId] = true
            root._seleccion = copia
        } else {
            root.guardado(res && res.mensaje ? res.mensaje : "No se pudo crear la playlist")
        }
    }

    // ── Presentación ─────────────────────────────────────────────────────
    parent: Overlay.overlay
    modal: true
    dim: true
    focus: true
    padding: UiTokens.spacing24
    width: 440
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    x: Math.round((((parent ? parent.width : 0) - width) / 2))
    y: Math.round((((parent ? parent.height : 0) - height) / 2))

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0.0; to: 1.0; duration: UiTokens.durationBase; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.96; to: 1.0; duration: UiTokens.durationBase; easing.type: Easing.OutCubic }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1.0; to: 0.0; duration: UiTokens.durationFast; easing.type: Easing.InCubic }
    }

    Overlay.modal: Rectangle {
        color: Qt.rgba(0, 0, 0, 0.62)
        Behavior on opacity { NumberAnimation { duration: UiTokens.durationBase } }
    }

    background: Rectangle {
        radius: UiTokens.radiusMd
        color: root.tema ? root.tema.fondoElevado : "#0d0d0d"
        border.color: root.tema ? root.tema.borde : "#333"
        border.width: 1
    }

    // Icono recoloreado (mismo patrón que `Icono` de las vistas).
    component IconoMenu: Item {
        id: iconoRoot
        property string source: ""
        property color iconColor: "#fff"
        Image {
            id: img
            anchors.fill: parent
            source: iconoRoot.source
            sourceSize.width: iconoRoot.width * 2
            sourceSize.height: iconoRoot.height * 2
            smooth: true
            opacity: 0
        }
        MultiEffect {
            anchors.fill: img
            source: img
            colorization: 1.0
            colorizationColor: iconoRoot.iconColor
        }
    }

    // Botón interno reutilizable (evita depender de componentes locales de
    // cada vista).
    component BotonMenu: Rectangle {
        id: btn
        property string texto: ""
        property bool primario: false
        property bool habilitado: true
        signal pulsado()

        implicitWidth: etiqueta.implicitWidth + UiTokens.spacing24
        height: UiTokens.controlHeightMd
        radius: UiTokens.radiusSm
        opacity: btn.habilitado ? 1.0 : 0.45
        color: btn.primario
               ? (areaBtn.pressed ? (root.tema ? root.tema.acentoFuerte : "#00c8e0")
                                   : (root.tema ? root.tema.acento : "#00e5ff"))
               : (areaBtn.containsMouse ? (root.tema ? root.tema.hover : "#1f1f1f") : "transparent")
        border.color: btn.primario ? "transparent" : (root.tema ? root.tema.borde : "#333")

        AppText {
            id: etiqueta
            anchors.centerIn: parent
            text: btn.texto
            color: btn.primario ? (root.tema ? root.tema.fondo : "#000") : (root.tema ? root.tema.texto : "#fff")
            font.pixelSize: UiTokens.fontSizeMd
            font.bold: btn.primario
        }

        MouseArea {
            id: areaBtn
            anchors.fill: parent
            hoverEnabled: true
            enabled: btn.habilitado
            cursorShape: btn.habilitado ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: btn.pulsado()
        }
    }

    contentItem: ColumnLayout {
        spacing: UiTokens.spacing16

        // Encabezado
        ColumnLayout {
            Layout.fillWidth: true
            spacing: UiTokens.spacing2
            AppText {
                text: "Agregar a playlist"
                color: root.tema ? root.tema.texto : "#fff"
                font.pixelSize: UiTokens.fontSize2xl
                font.bold: true
            }
            AppText {
                visible: root.pistaTitulo !== ""
                text: root.pistaTitulo
                color: root.tema ? root.tema.textoSec : "#aaa"
                font.pixelSize: UiTokens.fontSizeSm
                elide: Text.ElideRight
                maximumLineCount: 1
                Layout.fillWidth: true
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.tema ? root.tema.borde : "#333" }

        // Lista de playlists manuales
        ScrollView {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(320, Math.max(48, contenidoLista.implicitHeight))
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                id: contenidoLista
                width: root.availableWidth
                spacing: UiTokens.spacing4

                Repeater {
                    model: root._items
                    delegate: Rectangle {
                        id: fila
                        required property var modelData
                        readonly property bool sel: root._estaSeleccionada(fila.modelData.playlist_id)
                        Layout.fillWidth: true
                        implicitHeight: UiTokens.controlHeightLg
                        radius: UiTokens.radiusSm
                        color: areaFila.containsMouse
                               ? (root.tema ? root.tema.hover : "#1f1f1f")
                               : "transparent"

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: UiTokens.spacing12
                            anchors.rightMargin: UiTokens.spacing12
                            spacing: UiTokens.spacing12

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                AppText {
                                    text: fila.modelData.nombre
                                    color: root.tema ? root.tema.texto : "#fff"
                                    font.pixelSize: UiTokens.fontSizeBase
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                AppText {
                                    text: fila.modelData.num_pistas + (fila.modelData.num_pistas === 1 ? " canción" : " canciones")
                                    color: root.tema ? root.tema.textoMuted : "#777"
                                    font.pixelSize: UiTokens.fontSizeXs
                                }
                            }

                            // Checkbox
                            Rectangle {
                                Layout.preferredWidth: 22
                                Layout.preferredHeight: 22
                                radius: 6
                                color: fila.sel ? (root.tema ? root.tema.acento : "#00e5ff") : "transparent"
                                border.width: fila.sel ? 0 : 1.5
                                border.color: root.tema ? root.tema.borde : "#555"

                                IconoMenu {
                                    anchors.centerIn: parent
                                    width: 14; height: 14
                                    visible: fila.sel
                                    source: "../assets/icons/check.svg"
                                    iconColor: root.tema ? root.tema.fondo : "#000"
                                }
                            }
                        }

                        MouseArea {
                            id: areaFila
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root._alternar(fila.modelData.playlist_id)
                        }
                    }
                }

                AppText {
                    visible: root._items.length === 0
                    Layout.fillWidth: true
                    Layout.topMargin: UiTokens.spacing8
                    Layout.bottomMargin: UiTokens.spacing8
                    text: "Aún no tienes playlists propias. Crea una abajo."
                    color: root.tema ? root.tema.textoMuted : "#777"
                    font.pixelSize: UiTokens.fontSizeSm
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
            }
        }

        // Crear nueva playlist
        ColumnLayout {
            Layout.fillWidth: true
            spacing: UiTokens.spacing8

            Rectangle {
                Layout.fillWidth: true
                visible: !root._creando
                implicitHeight: UiTokens.controlHeightMd
                radius: UiTokens.radiusSm
                color: areaNueva.containsMouse ? (root.tema ? root.tema.hover : "#1f1f1f") : "transparent"
                border.color: root.tema ? root.tema.borde : "#333"

                RowLayout {
                    anchors.centerIn: parent
                    spacing: UiTokens.spacing8
                    IconoMenu {
                        Layout.preferredWidth: 16
                        Layout.preferredHeight: 16
                        source: "../assets/icons/plus.svg"
                        iconColor: root.tema ? root.tema.acento : "#00e5ff"
                    }
                    AppText {
                        text: "Nueva playlist"
                        color: root.tema ? root.tema.acento : "#00e5ff"
                        font.pixelSize: UiTokens.fontSizeMd
                        font.weight: Font.DemiBold
                    }
                }
                MouseArea {
                    id: areaNueva
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: { root._creando = true; nuevoNombre.forceActiveFocus() }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                visible: root._creando
                spacing: UiTokens.spacing8

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: UiTokens.controlHeightMd
                    radius: UiTokens.radiusSm
                    color: root.tema ? root.tema.superficie : "#161616"
                    border.color: nuevoNombre.activeFocus ? (root.tema ? root.tema.acento : "#00e5ff") : (root.tema ? root.tema.borde : "#333")

                    TextField {
                        id: nuevoNombre
                        anchors.fill: parent
                        anchors.leftMargin: UiTokens.spacing12
                        anchors.rightMargin: UiTokens.spacing12
                        placeholderText: "Nombre de la playlist"
                        color: root.tema ? root.tema.texto : "#fff"
                        placeholderTextColor: root.tema ? root.tema.textoMuted : "#777"
                        selectionColor: root.tema ? root.tema.acento : "#00e5ff"
                        font.pixelSize: UiTokens.fontSizeMd
                        background: Item {}
                        verticalAlignment: TextInput.AlignVCenter
                        maximumLength: 120
                        onAccepted: root._crearPlaylist()
                    }
                }

                BotonMenu {
                    texto: "Crear"
                    primario: true
                    habilitado: nuevoNombre.text.trim() !== ""
                    onPulsado: root._crearPlaylist()
                }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.tema ? root.tema.borde : "#333" }

        // Pie: cancelar / guardar
        RowLayout {
            Layout.fillWidth: true
            spacing: UiTokens.spacing8
            Item { Layout.fillWidth: true }
            BotonMenu {
                texto: "Cancelar"
                onPulsado: root.close()
            }
            BotonMenu {
                texto: "Guardar"
                primario: true
                habilitado: root._hayCambios()
                onPulsado: root._guardar()
            }
        }
    }
}
