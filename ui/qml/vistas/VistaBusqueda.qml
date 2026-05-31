// =============================================================================
// ui/qml/vistas/VistaBusqueda.qml
//
// Busqueda universal: clasica por biblioteca y discovery musical local.
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
    property bool esta_buscando: false
    property bool modoNatural: false
    property string queryBusquedaClasica: ""
    property string queryBusquedaNatural: ""
    property bool _sincronizandoCampo: false
    readonly property bool mostrarResultadosClasicos: !modoNatural && queryBusquedaClasica.trim().length > 0
    readonly property bool mostrarResultadosNaturales: modoNatural && queryBusquedaNatural.trim().length > 0
    readonly property var ideasNaturales: [
        "Algo triste", "Para entrenar", "Algo tranquilo", "Para concentrarme",
        "Para fiesta", "Algo de noche", "Para manejar", "Para caminar",
        "Para trabajar", "Para estudiar", "Para dormir", "Para cocinar",
        "Para limpiar", "Para levantar ánimo", "Algo alegre", "Algo melancólico",
        "Algo intenso", "Algo oscuro", "Algo bailable", "Algo romántico",
        "Algo rápido", "Algo lento", "Triste pero con energía", "Baja energía"
    ]
    // Limit visible chips based on available width to avoid taking too many rows
    // at small sizes and leaving no room for results.
    readonly property int _maxChipsVisibles: {
        if (width >= 1100) return ideasNaturales.length
        if (width >= 900)  return 18
        if (width >= 750)  return 12
        return 8
    }

    function portadaDe(ruta) { return UiUtils.toMediaSource(ruta) }

    function _pistaTitulo(pista) {
        if (!pista) return "Sin título"
        return pista.titulo || pista.title || pista.nombre_archivo || "Sin título"
    }

    function _pistaArtista(pista) {
        if (!pista) return ""
        return pista.artista_nombre || pista.artist || ""
    }

    function _pistaAlbum(pista) {
        if (!pista) return ""
        return pista.album_titulo || pista.album || ""
    }

    function _pistaPortada(pista) {
        if (!pista) return ""
        return pista.portada_display_ruta || pista.portada_thumb_ruta || pista.portada_ruta || pista.album_portada_ruta || ""
    }

    function _textoMetaPista(pista) {
        var partes = []
        var artista = _pistaArtista(pista)
        var album = _pistaAlbum(pista)
        if (artista) partes.push(artista)
        if (album) partes.push(album)
        return partes.join(" · ")
    }

    function queryActiva() {
        return modoNatural ? queryBusquedaNatural : queryBusquedaClasica
    }

    // Normaliza para comparar: lowercase + sin diacríticos + trim. NO
    // toca puntuación porque queremos "coincidencia exacta" tolerante a
    // tildes/mayúsculas pero estricta con espacios y signos.
    function _normalizar(texto) {
        if (texto === undefined || texto === null) return ""
        var s = String(texto).trim().toLowerCase()
        try {
            s = s.normalize("NFD").replace(/[̀-ͯ]/g, "")
        } catch (e) { }
        return s
    }

    function _hayMatchExacto(modelo, campo, qNorm) {
        if (!modelo || !modelo.total || !qNorm) return false
        var total = modelo.total
        for (var i = 0; i < total; i++) {
            var item = modelo.obtener(i)
            if (!item) continue
            if (_normalizar(item[campo]) === qNorm) return true
        }
        return false
    }

    // Calcula el orden de secciones para resultados clásicos:
    //   1) sección con coincidencia exacta (pistas/albums/artistas), si la hay
    //   2) favoritos, sólo si el modelo trajo coincidencias
    //   3) resto en orden artistas → albums → pistas
    readonly property var _ordenSeccionesBusqueda: {
        if (!mostrarResultadosClasicos || esta_buscando) return []
        var q = _normalizar(queryBusquedaClasica)
        if (!q) return []
        var matchPistas = _hayMatchExacto(busqueda.pistas, "titulo", q)
        var matchAlbums = _hayMatchExacto(busqueda.albums, "titulo", q)
        var matchArtistas = _hayMatchExacto(busqueda.artistas, "nombre", q)

        var orden = []
        // Prioridad de match exacto: pistas > albums > artistas (lo más específico primero).
        if (matchPistas) orden.push("pistas")
        else if (matchAlbums) orden.push("albums")
        else if (matchArtistas) orden.push("artistas")

        // Favoritos sólo si el backend retornó coincidencias.
        if (busqueda.favoritos.total > 0) orden.push("favoritos")

        // Resto en orden default.
        var defecto = ["artistas", "albums", "pistas"]
        for (var k = 0; k < defecto.length; k++) {
            if (orden.indexOf(defecto[k]) === -1) orden.push(defecto[k])
        }
        return orden
    }

    // Aplana las secciones en una lista plana de filas (headers + items)
    // para evitar sub-Layouts anidados. Sin esto, ColumnLayout interno
    // generaba un gap visible al final de cada sección con >1 item.
    readonly property var _filasPlanas: {
        var filas = []
        var orden = _ordenSeccionesBusqueda
        for (var i = 0; i < orden.length; i++) {
            var sec = orden[i]
            var modelo = sec === "favoritos" ? busqueda.favoritos
                       : sec === "artistas"  ? busqueda.artistas
                       : sec === "albums"    ? busqueda.albums
                       : busqueda.pistas
            var total = modelo.total || 0
            if (total === 0) continue
            filas.push({ "tipo": "header", "seccion": sec, "total": total })
            for (var k = 0; k < total; k++) {
                filas.push({ "tipo": sec, "indice": k })
            }
        }
        return filas
    }

    function resetScrollBusqueda() {
        if (resultadosScroll.contentItem && resultadosScroll.contentItem.contentY !== undefined)
            resultadosScroll.contentItem.contentY = 0
    }

    function sincronizarCampoConModo() {
        _sincronizandoCampo = true
        campo_busqueda.text = queryActiva()
        _sincronizandoCampo = false
    }

    function ejecutarBusquedaActual() {
        var t = queryActiva().trim()
        if (t.length > 0) {
            esta_buscando = true
            if (modoNatural)
                busqueda.buscarNatural(t)
            else
                busqueda.buscar(t)
        } else {
            esta_buscando = false
            if (modoNatural)
                busqueda.buscarNatural("")
            else
                busqueda.buscar("")
        }
    }

    function cambiarModoNatural(valor) {
        if (modoNatural === valor)
            return
        modoNatural = valor
        esta_buscando = false
        timer_debounce.stop()
        resetScrollBusqueda()
        sincronizarCampoConModo()
        if (modoNatural) {
            busqueda.refrescarEstadoNatural()
            if (queryBusquedaNatural.trim().length === 0)
                busqueda.buscarNatural("")
        } else {
            if (queryBusquedaClasica.trim().length === 0)
                busqueda.buscar("")
        }
    }

    function ejecutarChip(texto) {
        queryBusquedaNatural = texto
        if (modoNatural) {
            _sincronizandoCampo = true
            campo_busqueda.text = texto
            _sincronizandoCampo = false
        }
        campo_busqueda.forceActiveFocus()
        timer_debounce.stop()
        resetScrollBusqueda()
        busqueda.buscarNatural(texto)
    }

    function reproducirPista(pista) {
        if (!pista || !pista.id)
            return
        reproductor.reproducir(pista)
    }

    function agregarPistaACola(pista) {
        if (!pista || !pista.id)
            return
        reproductor.agregar_a_cola(pista)
        mostrar_toast("Pista agregada a la cola")
    }

    function alternarFavorita(pista) {
        if (!pista || !pista.id)
            return
        biblioteca.toggle_favorita(pista.id)
        ejecutarBusquedaActual()
    }

    function esPistaFavorita(pista) {
        return !!(pista && pista.favorita)
    }

    Component.onCompleted: busqueda.refrescarEstadoNatural()

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        AppCard {
            Layout.fillWidth: true
            Layout.leftMargin: UiTokens.spacing24
            Layout.rightMargin: UiTokens.spacing24
            Layout.topMargin: UiTokens.spacing16
            tema: raiz.tema
            elevated: true

            RowLayout {
                Layout.fillWidth: true
                spacing: UiTokens.spacing8
                AppText { text: "Buscar"; font.pixelSize: 24; font.bold: true; color: tema.texto }
                Item { Layout.fillWidth: true }
                PillOption { texto: "Buscar"; activo: !modoNatural; onClicked: cambiarModoNatural(false) }
                PillOption { texto: "Háblale a tu biblioteca"; activo: modoNatural; onClicked: cambiarModoNatural(true) }
                StatusBadge { tema: raiz.tema; text: esta_buscando ? "Buscando..." : "Explorar"; tone: esta_buscando ? "info" : "neutral" }
            }
            AppText {
                text: modoNatural
                      ? "Describe una intención musical y descubre pistas de tu biblioteca."
                      : "Encuentra artistas, álbumes y pistas en toda tu biblioteca."
                color: tema.textoSec
                font.pixelSize: UiTokens.fontSizeBase
                wrapMode: Text.Wrap
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.leftMargin: UiTokens.spacing24
            Layout.rightMargin: UiTokens.spacing24
            Layout.topMargin: UiTokens.spacing12
            Layout.bottomMargin: UiTokens.spacing12
            height: 56
            radius: 26
            color: campo_busqueda.activeFocus
                ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.08)
                : (hoverSearch.containsMouse ? Qt.rgba(tema.superficieAlt.r, tema.superficieAlt.g, tema.superficieAlt.b, 0.7) : tema.superficieAlt)
            border.color: campo_busqueda.activeFocus ? tema.acento : tema.borde
            border.width: campo_busqueda.activeFocus ? 1.5 : 1

            Behavior on color { ColorAnimation { duration: 180 } }
            Behavior on border.color { ColorAnimation { duration: 180 } }

            MouseArea {
                id: hoverSearch
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.NoButton
            }

            RowLayout {
                anchors { fill: parent; leftMargin: UiTokens.spacing20; rightMargin: UiTokens.spacing20 }
                spacing: UiTokens.spacing14

                Image {
                    Layout.preferredWidth: 18
                    Layout.preferredHeight: 18
                    source: "../assets/icons/search.svg"
                    opacity: campo_busqueda.activeFocus ? 1.0 : 0.72
                    sourceSize.width: 24
                    sourceSize.height: 24
                }

                TextField {
                    id: campo_busqueda
                    Layout.fillWidth: true
                    placeholderText: modoNatural
                        ? "Ej: algo triste, música para entrenar, algo tranquilo de noche..."
                        : "Buscar artistas, álbumes o pistas..."
                    placeholderTextColor: tema.textoMuted
                    color: tema.texto
                    font.pixelSize: UiTokens.fontSizeXl
                    background: null
                    selectByMouse: true
                    onTextChanged: {
                        if (_sincronizandoCampo)
                            return
                        if (modoNatural)
                            queryBusquedaNatural = text
                        else
                            queryBusquedaClasica = text
                        resetScrollBusqueda()
                        timer_debounce.restart()
                    }
                    Keys.onEscapePressed: {
                        text = ""
                        focus = false
                    }
                }

                Item {
                    width: 20
                    height: 20
                    visible: esta_buscando

                    Rectangle {
                        anchors.centerIn: parent
                        width: 16
                        height: 16
                        radius: UiTokens.radiusSm
                        color: "transparent"
                        border.color: tema.acento
                        border.width: 2
                        opacity: 0.6

                        RotationAnimation on rotation {
                            from: 0
                            to: 360
                            duration: 800
                            loops: Animation.Infinite
                            running: esta_buscando
                        }

                        Rectangle {
                            width: 8
                            height: 4
                            radius: 2
                            color: tema.superficie
                            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                        }
                    }
                }

                SearchIconButton {
                    visible: campo_busqueda.text.length > 0
                    iconSource: "../assets/icons/close.svg"
                    compact: true
                    onClicked: {
                        campo_busqueda.text = ""
                        campo_busqueda.forceActiveFocus()
                    }
                }
            }
        }

        Flow {
            Layout.fillWidth: true
            Layout.leftMargin: UiTokens.spacing24
            Layout.rightMargin: UiTokens.spacing24
            Layout.bottomMargin: UiTokens.spacing8
            spacing: UiTokens.spacing8
            visible: modoNatural && busqueda.hayBibliotecaMusical && busqueda.hayFeaturesDisponibles

            AppText {
                text: "Ideas para probar"
                color: tema.textoSec
                font.pixelSize: UiTokens.fontSizeMd
                font.weight: Font.DemiBold
                height: 32
                verticalAlignment: Text.AlignVCenter
            }

            Repeater {
                model: Math.min(raiz._maxChipsVisibles, raiz.ideasNaturales.length)
                delegate: ChipSugerencia {
                    texto: raiz.ideasNaturales[index]
                    onClicked: ejecutarChip(raiz.ideasNaturales[index])
                }
            }
        }

        Timer {
            id: timer_debounce
            interval: 350
            repeat: false
            onTriggered: ejecutarBusquedaActual()
        }

        Connections {
            target: busqueda
            function onBuscando(val) { if (!modoNatural) esta_buscando = val }
            function onBuscandoNaturalCambiado() { if (modoNatural) esta_buscando = busqueda.buscandoNatural }
            function onResultadosCambiados() { if (!modoNatural) resetScrollBusqueda() }
            function onResultadosNaturalesCambiados() { if (modoNatural) resetScrollBusqueda() }
        }

        ScrollView {
            id: resultadosScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            contentHeight: resultadosContenido.implicitHeight
            clip: true
            ScrollBar.vertical: AppScrollBar {
                parent: resultadosScroll
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                z: 20
                tema: raiz.tema
                policy: resultadosScroll.contentHeight > resultadosScroll.height + 2 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
            }

            ColumnLayout {
                id: resultadosContenido
                width: raiz.width
                spacing: 0

                EmptyBlock {
                    visible: !modoNatural && queryBusquedaClasica.trim().length === 0
                    titulo: "¿Qué quieres escuchar?"
                    detalle: "Busca por artista, álbum o título de pista."
                    iconSource: "../assets/icons/search.svg"
                }

                EmptyBlock {
                    visible: modoNatural && !busqueda.hayBibliotecaMusical
                    titulo: "Tu biblioteca todavía está vacía"
                    detalle: "Importa música local para descubrirla desde Buscar."
                    iconSource: "../assets/icons/library.svg"
                }

                EmptyBlock {
                    visible: modoNatural && busqueda.hayBibliotecaMusical && !busqueda.hayFeaturesDisponibles
                    titulo: "Todavía no hay datos musicales suficientes para recomendar desde tu biblioteca."
                    detalle: "Activa Audio Features desde ajustes para mejorar recomendaciones."
                    iconSource: "../assets/icons/sync.svg"
                }

                EmptyBlock {
                    visible: mostrarResultadosClasicos && !esta_buscando &&
                             busqueda.favoritos.total === 0 && busqueda.pistas.total === 0 &&
                             busqueda.albums.total === 0 && busqueda.artistas.total === 0
                    titulo: "Sin resultados para \"" + queryBusquedaClasica + "\""
                    detalle: "Intenta con otro término de búsqueda."
                    iconSource: "../assets/icons/search.svg"
                }

                EmptyBlock {
                    visible: modoNatural && busqueda.hayBibliotecaMusical && busqueda.hayFeaturesDisponibles &&
                             queryBusquedaNatural.trim().length === 0
                    titulo: "Dile qué ambiente quieres escuchar"
                    detalle: "Usa una idea musical sencilla o prueba una sugerencia."
                    iconSource: "../assets/icons/surprise.svg"
                }

                EmptyBlock {
                    visible: modoNatural && busqueda.hayBibliotecaMusical && busqueda.hayFeaturesDisponibles &&
                             mostrarResultadosNaturales && !esta_buscando && busqueda.seccionesNatural.total === 0
                    titulo: "Sin coincidencias musicales"
                    detalle: busqueda.mensajeNatural.length > 0 ? busqueda.mensajeNatural : "Prueba con otra intención musical."
                    iconSource: "../assets/icons/search.svg"
                }

                // Secciones clásicas APLANADAS: cada fila (header o item) es
                // un Loader directo del padre `resultadosContenido`. Sin
                // sub-ColumnLayouts anidados → sin gap residual al final
                // de cada sección con >1 item.
                Repeater {
                    model: raiz._filasPlanas
                    delegate: Loader {
                        required property var modelData
                        Layout.fillWidth: true
                        // Los márgenes laterales viven aquí (no en los componentes
                        // internos): al estar envueltos en este Loader, su padre no
                        // es un Layout y sus Layout.leftMargin/rightMargin se ignoran.
                        // El modo natural inserta los componentes directos en un
                        // ColumnLayout, por eso allí sí se respetaba la separación.
                        Layout.leftMargin: UiTokens.spacing24
                        Layout.rightMargin: UiTokens.spacing24
                        sourceComponent: {
                            if (modelData.tipo === "header")    return _compHeader
                            if (modelData.tipo === "favoritos") return _compFilaPistaFav
                            if (modelData.tipo === "pistas")    return _compFilaPista
                            if (modelData.tipo === "artistas")  return _compFilaArtista
                            if (modelData.tipo === "albums")    return _compFilaAlbum
                            return null
                        }
                    }
                }

                Component {
                    id: _compHeader
                    SeccionResultado {
                        singular: parent && parent.modelData
                            ? (parent.modelData.seccion === "favoritos" ? "Favorito"
                              : parent.modelData.seccion === "artistas"  ? "Artista"
                              : parent.modelData.seccion === "albums"    ? "Álbum"
                              : "Pista")
                            : ""
                        plural: parent && parent.modelData
                            ? (parent.modelData.seccion === "favoritos" ? "Favoritos"
                              : parent.modelData.seccion === "artistas"  ? "Artistas"
                              : parent.modelData.seccion === "albums"    ? "Álbumes"
                              : "Pistas")
                            : ""
                        conteo: parent && parent.modelData ? (parent.modelData.total || 0) : 0
                    }
                }

                Component {
                    id: _compFilaPistaFav
                    SearchTrackRow {
                        readonly property int _idx: parent && parent.modelData ? (parent.modelData.indice || 0) : 0
                        pista: busqueda.favoritos.obtener(_idx)
                        indiceVisible: _idx + 1
                        onPlay: function(p) { reproducirPista(p) }
                        onAddToQueue: function(p) { agregarPistaACola(p) }
                        onToggleFavorite: function(p) { alternarFavorita(p) }
                    }
                }

                Component {
                    id: _compFilaPista
                    SearchTrackRow {
                        readonly property int _idx: parent && parent.modelData ? (parent.modelData.indice || 0) : 0
                        pista: busqueda.pistas.obtener(_idx)
                        indiceVisible: _idx + 1
                        onPlay: function(p) { reproducirPista(p) }
                        onAddToQueue: function(p) { agregarPistaACola(p) }
                        onToggleFavorite: function(p) { alternarFavorita(p) }
                    }
                }

                Component {
                    id: _compFilaArtista
                    SearchNavRow {
                        readonly property int _idx: parent && parent.modelData ? (parent.modelData.indice || 0) : 0
                        readonly property var _data: busqueda.artistas.obtener(_idx) || ({})
                        tipo: "artist"
                        titulo: _data.nombre || ""
                        detalle: (_data.num_albums || 0) + " álbumes · " + (_data.num_pistas || 0) + " pistas"
                        portadaRuta: _data.portada_display_ruta || _data.portada_ruta || ""
                        onClicked: {
                            if (shell && _data && _data.id)
                                shell.abrir_artista_desde_detalle(_data.id)
                        }
                    }
                }

                Component {
                    id: _compFilaAlbum
                    SearchNavRow {
                        readonly property int _idx: parent && parent.modelData ? (parent.modelData.indice || 0) : 0
                        readonly property var _data: busqueda.albums.obtener(_idx) || ({})
                        tipo: "album"
                        titulo: _data.titulo || ""
                        detalle: (_data.artista_nombre || "Artista") + " · " + (_data.num_pistas || 0) + " pistas"
                        portadaRuta: _data.portada_display_ruta || _data.portada_ruta || ""
                        onClicked: {
                            if (shell && _data && _data.id)
                                shell.abrir_album_desde_detalle(_data.id)
                        }
                    }
                }

                Repeater {
                    model: mostrarResultadosNaturales ? busqueda.seccionesNatural : 0
                    delegate: ColumnLayout {
                        Layout.fillWidth: true
                        property var seccionNatural: busqueda.seccionesNatural.obtener(index)
                        property var pistasSeccion: seccionNatural.pistas || seccionNatural.results || []

                        SeccionResultado {
                            tituloOverride: seccionNatural.titulo || seccionNatural.title || "Selección"
                            singular: "Pista"
                            plural: "Pistas"
                            conteo: pistasSeccion.length || 0
                            visible: modoNatural && (pistasSeccion.length || 0) > 0
                        }

                        Repeater {
                            model: pistasSeccion
                            delegate: SearchTrackRow {
                                pista: modelData
                                indiceVisible: index + 1
                                onPlay: function(pista) { reproducirPista(pista) }
                                onAddToQueue: function(pista) { agregarPistaACola(pista) }
                                onToggleFavorite: function(pista) { alternarFavorita(pista) }
                            }
                        }
                    }
                }

                Item { height: 40; Layout.fillWidth: true }
            }
        }
    }

    ToastMessage {
        id: toastMessage
        anchors.bottom: parent.bottom
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottomMargin: UiTokens.spacing24
        tema: raiz.tema
        z: 50
    }

    function mostrar_toast(msg) {
        if (shell && shell.mostrar_toast_global)
            shell.mostrar_toast_global(msg, "info")
        else
            toastMessage.show(msg)
    }

    component PillOption: Rectangle {
        property string texto: ""
        property bool activo: false
        signal clicked()

        implicitWidth: pillText.implicitWidth + 32
        height: 38
        radius: 19
        color: activo ? tema.acento : (pillMa.containsMouse ? tema.hover : tema.superficieAlt)
        border.color: activo ? tema.acento : (pillMa.containsMouse ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.45) : tema.borde)
        border.width: 1

        AppText {
            id: pillText
            anchors.centerIn: parent
            text: texto
            color: activo ? tema.textoSobreAcento : tema.textoSec
            font.pixelSize: UiTokens.fontSizeBase
            font.weight: activo ? Font.DemiBold : Font.Normal
        }

        MouseArea {
            id: pillMa
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: parent.clicked()
        }
    }

    component ChipSugerencia: Rectangle {
        property string texto: ""
        signal clicked()

        width: chipText.implicitWidth + 24
        height: 32
        radius: 16
        color: chipMouse.containsMouse ? tema.hover : tema.superficieAlt
        border.color: chipMouse.containsMouse ? tema.acento : tema.borde
        border.width: 1

        AppText {
            id: chipText
            anchors.centerIn: parent
            text: texto
            color: chipMouse.containsMouse ? tema.texto : tema.textoSec
            font.pixelSize: UiTokens.fontSizeMd
            font.weight: Font.DemiBold
        }

        MouseArea {
            id: chipMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: parent.clicked()
        }
    }

    component SearchIconButton: Rectangle {
        property string iconSource: ""
        property bool active: false
        property bool compact: false
        signal clicked()

        width: compact ? 28 : 34
        height: compact ? 28 : 34
        radius: width / 2
        color: active ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.18)
                      : (iconMouse.containsMouse ? tema.hover : "transparent")
        border.color: active ? tema.acento : tema.borde
        border.width: compact ? 0 : 1

        Image {
            anchors.centerIn: parent
            width: compact ? 13 : 16
            height: width
            source: iconSource
            sourceSize.width: 24
            sourceSize.height: 24
            opacity: active ? 1.0 : 0.78
        }

        MouseArea {
            id: iconMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            acceptedButtons: Qt.LeftButton
            preventStealing: true
            onClicked: parent.clicked()
        }
    }

    component SearchActionButton: Rectangle {
        id: actionButton
        property string texto: ""
        property string iconSource: ""
        signal clicked()

        width: Math.max(126, actionRow.implicitWidth + 24)
        height: 34
        radius: 17
        color: actionMouse.containsMouse ? tema.hover : "transparent"
        border.color: tema.borde
        border.width: 1

        Row {
            id: actionRow
            anchors.centerIn: parent
            spacing: UiTokens.spacing6

            ThemedIcon {
                width: 15
                height: 15
                source: actionButton.iconSource
                iconColor: actionMouse.containsMouse ? tema.texto : tema.textoSec
                anchors.verticalCenter: parent.verticalCenter
            }

            AppText {
                text: actionButton.texto
                color: actionMouse.containsMouse ? tema.texto : tema.textoSec
                font.pixelSize: UiTokens.fontSizeMd
                font.weight: Font.DemiBold
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        MouseArea {
            id: actionMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            acceptedButtons: Qt.LeftButton
            preventStealing: true
            onClicked: actionButton.clicked()
        }
    }

    component ThemedIcon: Item {
        id: themedIcon
        property string source: ""
        property color iconColor: tema.textoSec
        property real iconOpacity: 1.0
        implicitWidth: 16
        implicitHeight: 16

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

    component CoverBox: Rectangle {
        property string portadaRuta: ""
        property string tipo: "track"

        radius: tipo === "artist" ? width / 2 : 6
        color: coverImage.visible ? "transparent" : tema.superficieAlt
        border.color: coverImage.visible ? "transparent" : tema.borde
        border.width: coverImage.visible ? 0 : 1
        clip: true

        Image {
            id: coverImage
            anchors.fill: parent
            visible: portadaRuta !== "" && status !== Image.Error
            source: portadaRuta !== "" ? portadaDe(portadaRuta) : ""
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            smooth: true
            sourceSize.width: Math.max(96, width * 2)
            sourceSize.height: Math.max(96, height * 2)
        }

        Image {
            anchors.centerIn: parent
            visible: !coverImage.visible
            width: Math.min(parent.width, parent.height) * 0.42
            height: width
            source: tipo === "artist" ? "../assets/icons/artist.svg" : "../assets/icons/library.svg"
            opacity: 0.62
            sourceSize.width: 32
            sourceSize.height: 32
        }
    }

    component SearchNavRow: Rectangle {
        id: navRow
        property string tipo: "album"
        property string titulo: ""
        property string detalle: ""
        property string portadaRuta: ""
        signal clicked()

        Layout.fillWidth: true
        Layout.leftMargin: UiTokens.spacing24
        Layout.rightMargin: UiTokens.spacing24
        height: 62
        radius: UiTokens.radiusSm
        color: navMouse.containsMouse ? tema.hover : "transparent"
        border.color: navMouse.containsMouse ? tema.borde : "transparent"
        border.width: navMouse.containsMouse ? 1 : 0

        RowLayout {
            anchors { fill: parent; leftMargin: UiTokens.spacing12; rightMargin: UiTokens.spacing12 }
            spacing: UiTokens.spacing12

            CoverBox {
                Layout.preferredWidth: 42
                Layout.preferredHeight: 42
                portadaRuta: navRow.portadaRuta
                tipo: navRow.tipo
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: UiTokens.spacing2
                AppText { text: navRow.titulo; color: tema.texto; font.bold: true; font.pixelSize: UiTokens.fontSizeLg; elide: Text.ElideRight; Layout.fillWidth: true }
                AppText { text: navRow.detalle; color: tema.textoSec; font.pixelSize: UiTokens.fontSizeMd; elide: Text.ElideRight; Layout.fillWidth: true }
            }

            ThemedIcon {
                Layout.preferredWidth: 16
                Layout.preferredHeight: 16
                source: "../assets/icons/chevron-right.svg"
                iconColor: navMouse.containsMouse ? tema.texto : tema.textoMuted
                iconOpacity: 0.82
            }
        }

        MouseArea {
            id: navMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: navRow.clicked()
        }
    }

    component SearchTrackRow: Rectangle {
        id: trackRow
        property var pista: ({})
        property int indiceVisible: 0
        signal play(var pista)
        signal addToQueue(var pista)
        signal toggleFavorite(var pista)

        Layout.fillWidth: true
        Layout.leftMargin: UiTokens.spacing24
        Layout.rightMargin: UiTokens.spacing24
        height: 64
        radius: UiTokens.radiusSm
        color: rowMouse.containsMouse ? tema.hover : "transparent"
        border.color: rowMouse.containsMouse ? tema.borde : "transparent"
        border.width: rowMouse.containsMouse ? 1 : 0

        MouseArea {
            id: rowMouse
            anchors.fill: parent
            z: 0
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            acceptedButtons: Qt.LeftButton
            onClicked: trackRow.play(trackRow.pista)
        }

        RowLayout {
            anchors { fill: parent; leftMargin: UiTokens.spacing12; rightMargin: UiTokens.spacing12 }
            spacing: UiTokens.spacing10
            z: 1

            AppText {
                text: String(trackRow.indiceVisible)
                color: tema.textoMuted
                font.pixelSize: UiTokens.fontSizeSm
                Layout.preferredWidth: 28
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }

            CoverBox {
                Layout.preferredWidth: 42
                Layout.preferredHeight: 42
                portadaRuta: _pistaPortada(trackRow.pista)
                tipo: "track"
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: UiTokens.spacing2
                AppText {
                    text: _pistaTitulo(trackRow.pista)
                    color: tema.texto
                    font.pixelSize: UiTokens.fontSizeBase
                    font.weight: Font.DemiBold
                    maximumLineCount: 1
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                AppText {
                    text: _textoMetaPista(trackRow.pista)
                    color: tema.textoSec
                    font.pixelSize: UiTokens.fontSizeMd
                    maximumLineCount: 1
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }

            AppText {
                text: Number(trackRow.pista && trackRow.pista.duracion_seg ? trackRow.pista.duracion_seg : 0) > 0
                      ? reproductor.formatear_tiempo(trackRow.pista.duracion_seg || 0)
                      : ""
                color: tema.textoSec
                font.pixelSize: UiTokens.fontSizeMd
                Layout.preferredWidth: 62
                horizontalAlignment: Text.AlignHCenter
            }

            RowLayout {
                spacing: UiTokens.spacing6
                Layout.preferredWidth: 172
                Layout.alignment: Qt.AlignVCenter

                SearchActionButton {
                    texto: "Añadir a cola"
                    iconSource: "../assets/icons/queue-play.svg"
                    onClicked: trackRow.addToQueue(trackRow.pista)
                }

                SearchIconButton {
                    active: !!(trackRow.pista && trackRow.pista.favorita)
                    iconSource: active ? "../assets/icons/favorite-filled.svg" : "../assets/icons/favorite.svg"
                    onClicked: trackRow.toggleFavorite(trackRow.pista)
                }
            }
        }
    }

    component EmptyBlock: Item {
        property string titulo: ""
        property string detalle: ""
        property string iconSource: "../assets/icons/search.svg"

        Layout.fillWidth: true
        Layout.preferredHeight: 210

        ColumnLayout {
            anchors.centerIn: parent
            width: Math.min(parent.width - 48, 520)
            spacing: UiTokens.spacing12

            Rectangle {
                Layout.alignment: Qt.AlignHCenter
                width: 64
                height: 64
                radius: 32
                color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.10)
                border.color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.22)
                border.width: 1

                Image {
                    id: _ebIcon
                    anchors.centerIn: parent
                    width: 26
                    height: 26
                    source: iconSource
                    opacity: 0
                    sourceSize.width: 42
                    sourceSize.height: 42
                    smooth: true
                }
                MultiEffect {
                    anchors.fill: _ebIcon
                    source: _ebIcon
                    colorization: 1.0
                    colorizationColor: tema.textoMuted
                    opacity: 0.92
                }
            }

            AppText {
                Layout.alignment: Qt.AlignHCenter
                Layout.fillWidth: true
                text: titulo
                font.pixelSize: UiTokens.fontSize2xl
                font.bold: true
                color: tema.texto
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }
            AppText {
                Layout.alignment: Qt.AlignHCenter
                Layout.fillWidth: true
                text: detalle
                font.pixelSize: UiTokens.fontSizeBase
                color: tema.textoSec
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }
        }
    }

    component SeccionResultado: Item {
        property string tituloOverride: ""
        property string singular: ""
        property string plural: ""
        property int conteo: 0

        Layout.fillWidth: true
        Layout.leftMargin: UiTokens.spacing24
        Layout.rightMargin: UiTokens.spacing24
        Layout.topMargin: UiTokens.spacing16
        Layout.bottomMargin: UiTokens.spacing6
        height: 32

        RowLayout {
            anchors.fill: parent
            spacing: UiTokens.spacing8

            AppText {
                text: tituloOverride !== "" ? tituloOverride : (conteo === 1 ? singular : plural)
                font.pixelSize: UiTokens.fontSizeLg
                font.weight: Font.DemiBold
                color: tema.texto
            }

            Rectangle {
                width: conteoText.implicitWidth + 12
                height: 20
                radius: UiTokens.radiusMd
                color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.12)

                AppText {
                    id: conteoText
                    anchors.centerIn: parent
                    text: conteo
                    font.pixelSize: UiTokens.fontSizeSm
                    font.bold: true
                    color: tema.acento
                }
            }

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: tema.borde
            }
        }
    }

    // Clicking anywhere outside the TextField removes focus from it.
    // z: -1 keeps this behind all interactive content so it only fires on empty areas.
    MouseArea {
        anchors.fill: parent
        z: -1
        onClicked: campo_busqueda.focus = false
    }
}
