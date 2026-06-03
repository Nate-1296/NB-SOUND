import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtQuick.Effects

import "../componentes"
import "../componentes/UiUtils.js" as UiUtils

Rectangle {
    id: raiz
    color: tema.fondo
    clip: true

    property var shell: null
    readonly property var tema: shell ? shell.tema : temaUi

    property string categoria_actual: configuracion.obtener("playlists_categoria") || "todo"
    property string modo_vista: configuracion.obtener("playlists_modo_vista") || "grid-md"
    readonly property string modo_vista_efectivo: layout_compacto ? "lista" : modo_vista
    property string orden_actual: configuracion.obtener("playlists_orden") || "recientes"
    property string filtro_texto: ""
    property var playlists_filtradas: []
    property int playlist_seleccionada_id: parseInt(configuracion.obtener("playlists_seleccionada_id") || "-1")
    property bool detalle_completo_abierto: false
    property int indice_arrastrando: -1
    property int indice_destino: -1
    property string titulo_confirmacion: ""
    property string mensaje_confirmacion: ""
    property var accionConfirmada: null
    property string error_nueva_playlist: ""
    property string error_editar_playlist: ""
    property bool _asegurandoSeleccion: false
    property real _scroll_playlists: 0
    property string _busqueda_agregar_pendiente: ""

    readonly property int margen_lateral: width < 980 ? UiTokens.spacing16 : UiTokens.spacing24
    readonly property bool layout_compacto: width < 900
    readonly property bool preview_lateral_visible: !detalle_completo_abierto && playlist_seleccionada_id > 0
    readonly property int ancho_preview: Math.max(220, Math.min(388, width * 0.26))

    // Color legible para los iconos de acción de las tarjetas (play y anclado):
    // parte del acento del tema y lo aclara en temas oscuros / lo oscurece en
    // claros, para que no se pierda sobre la superficie de la tarjeta ni sobre
    // la portada. No es un color fijo: deriva del acento activo.
    readonly property bool _temaClaro: (tema && tema.fondo) ? tema.fondo.hslLightness > 0.62 : false
    readonly property color colorAccionTarjeta: _temaClaro
                                                ? Qt.darker(tema.acento, 1.25)
                                                : Qt.lighter(tema.acento, 1.18)
    readonly property var categorias: [
        {"id": "todo", "nombre": "Todo", "icono": "../assets/icons/playlist.svg"},
        {"id": "favoritos", "nombre": "Me gusta", "icono": "../assets/icons/favorite.svg"},
        {"id": "mias", "nombre": "Creadas por mí", "icono": "../assets/icons/playlist.svg"},
        {"id": "para_ti", "nombre": "Creadas para ti", "icono": "../assets/icons/sync.svg"},
        {"id": "inteligentes", "nombre": "Inteligentes", "icono": "../assets/icons/surprise.svg"},
        {"id": "this_is", "nombre": "This is...", "icono": "../assets/icons/artist.svg"},
        {"id": "tops", "nombre": "Tops", "icono": "../assets/icons/sort-desc.svg"},
        {"id": "mixes", "nombre": "Mixes", "icono": "../assets/icons/shuffle.svg"},
        {"id": "ultimas", "nombre": "Últimas creadas para ti", "icono": "../assets/icons/clock.svg"}
    ]
    readonly property var modosVista: [
        {"id": "lista", "nombre": "Lista", "icono": "../assets/icons/list.svg"},
        {"id": "grid-sm", "nombre": "Pequeña", "icono": "../assets/icons/grid-small.svg"},
        {"id": "grid-md", "nombre": "Mediana", "icono": "../assets/icons/grid-medium.svg"},
        {"id": "grid-lg", "nombre": "Grande", "icono": "../assets/icons/grid-large.svg"}
    ]
    readonly property var opcionesOrden: [
        {"id": "recientes", "nombre": "Recientes", "icono": "../assets/icons/clock.svg"},
        {"id": "antiguos", "nombre": "Antiguos", "icono": "../assets/icons/clock.svg"},
        {"id": "nombre", "nombre": "A \u2192 Z", "icono": "../assets/icons/sort-asc.svg"},
        {"id": "nombre_desc", "nombre": "Z \u2192 A", "icono": "../assets/icons/sort-desc.svg"},
        {"id": "pistas", "nombre": "Canciones \u2193", "icono": "../assets/icons/sort-desc.svg"},
        {"id": "pistas_asc", "nombre": "Canciones \u2191", "icono": "../assets/icons/sort-asc.svg"}
    ]

    function abrir_playlist_id(playlist_id) {
        abrirDetallePlaylist(playlist_id)
    }

    function seleccionarPlaylist(pl) {
        var playlist_id = pl ? (pl.playlist_id || pl.id) : 0
        if (!playlist_id)
            return
        playlist_seleccionada_id = playlist_id
        configuracion.guardar("playlists_seleccionada_id", String(playlist_id))
        playlists.abrir_playlist(playlist_id)
    }

    function abrirDetallePlaylist(playlist_id) {
        if (!playlist_id)
            return
        playlist_seleccionada_id = playlist_id
        configuracion.guardar("playlists_seleccionada_id", String(playlist_id))
        detalle_completo_abierto = true
        playlists.abrir_playlist(playlist_id)
    }

    function cerrarDetalleCompleto() {
        detalle_completo_abierto = false
        reconstruirPlaylists()
        Qt.callLater(function() { flickPlaylists.contentY = Math.max(0, raiz._scroll_playlists) })
    }

    function portadaDe(ruta) {
        return UiUtils.toMediaSource(ruta)
    }

    function textoPistas(total) {
        var n = Number(total || 0)
        return n === 1 ? "1 pista" : n + " pistas"
    }

    function textoTipo(pl) {
        var subtipo = String(pl.tipo_playlist || pl.subtipo || "")
        var tipo = String(pl.tipo || pl.tipo_db || "")
        var origen = String(pl.origen || "")
        if (subtipo === "favoritos")
            return "Me gusta"
        if (subtipo === "this_is")
            return "This is..."
        if (subtipo === "top_canciones" || subtipo === "top_artistas" || subtipo === "top_albumes")
            return "Top"
        if (subtipo === "artist_mix" || subtipo === "album_mix")
            return "Mix"
        if (subtipo === "mood" || subtipo === "descubrimiento_local")
            return "Inteligente"
        if (origen === "generado" || tipo === "automatica")
            return "Para ti"
        if (tipo === "sistema")
            return "Sistema"
        return "Manual"
    }

    function coincideCategoriaId(pl, categoriaId) {
        var subtipo = String(pl.tipo_playlist || pl.subtipo || "")
        var tipo = String(pl.tipo || pl.tipo_db || "")
        var origen = String(pl.origen || "")
        if (categoriaId === "todo")
            return true
        if (categoriaId === "favoritos")
            return subtipo === "favoritos"
        if (categoriaId === "mias")
            return tipo === "manual" || origen === "usuario" || subtipo === "usuario"
        if (categoriaId === "para_ti")
            return origen === "generado" || tipo === "automatica"
        if (categoriaId === "inteligentes")
            return subtipo === "mood" || subtipo === "descubrimiento_local" || subtipo === "recientes"
        if (categoriaId === "this_is")
            return subtipo === "this_is"
        if (categoriaId === "tops")
            return subtipo === "top_canciones" || subtipo === "top_artistas" || subtipo === "top_albumes"
        if (categoriaId === "mixes")
            return subtipo === "artist_mix" || subtipo === "album_mix"
        if (categoriaId === "ultimas")
            return origen === "generado" || tipo === "automatica"
        return true
    }

    function coincideCategoria(pl) {
        return coincideCategoriaId(pl, categoria_actual)
    }

    function conteoCategoria(categoriaId) {
        var total = 0
        for (var i = 0; i < playlists.playlists.total; ++i) {
            var pl = playlists.playlists.obtener(i)
            if (pl && coincideCategoriaId(pl, categoriaId))
                total += 1
        }
        return total
    }

    function coincideTexto(pl) {
        var q = filtro_texto.trim().toLowerCase()
        if (q === "")
            return true
        var texto = [
            pl.nombre || "",
            pl.descripcion || "",
            textoTipo(pl),
            pl.origen || ""
        ].join(" ").toLowerCase()
        return texto.indexOf(q) >= 0
    }

    function valorFecha(pl) {
        return Date.parse(pl.actualizado_en || pl.ultima_generacion_en || pl.creado_en || "") || 0
    }

    function reconstruirPlaylists() {
        var arr = []
        for (var i = 0; i < playlists.playlists.total; ++i) {
            var pl = playlists.playlists.obtener(i)
            if (!pl || !coincideCategoria(pl) || !coincideTexto(pl))
                continue
            arr.push(pl)
        }
        arr.sort(function(a, b) {
            // Pinned siempre primero, ordenadas por fecha de anclaje desc
            var aPinned = a.es_anclada ? 1 : 0
            var bPinned = b.es_anclada ? 1 : 0
            if (aPinned !== bPinned)
                return bPinned - aPinned
            if (aPinned && bPinned) {
                var aPinDate = Date.parse(a.anclada_en || "") || 0
                var bPinDate = Date.parse(b.anclada_en || "") || 0
                if (aPinDate !== bPinDate)
                    return bPinDate - aPinDate
            }
            // Orden seleccionado para el resto
            if (orden_actual === "nombre")
                return String(a.nombre || "").localeCompare(String(b.nombre || ""), undefined, {sensitivity: "base"})
            if (orden_actual === "nombre_desc")
                return String(b.nombre || "").localeCompare(String(a.nombre || ""), undefined, {sensitivity: "base"})
            if (orden_actual === "pistas")
                return Number(b.num_pistas || 0) - Number(a.num_pistas || 0)
            if (orden_actual === "pistas_asc")
                return Number(a.num_pistas || 0) - Number(b.num_pistas || 0)
            if (orden_actual === "antiguos")
                return valorFecha(a) - valorFecha(b)
            // recientes (default)
            return valorFecha(b) - valorFecha(a)
        })
        playlists_filtradas = arr
        Qt.callLater(asegurarSeleccion)
    }

    function ordenValido(valor) {
        return ["recientes", "antiguos", "nombre", "nombre_desc", "pistas", "pistas_asc"].indexOf(String(valor || "")) >= 0 ? String(valor) : "recientes"
    }

    function cambiarOrden(orden) {
        orden_actual = ordenValido(orden)
        configuracion.guardar("playlists_orden", orden_actual)
        reconstruirPlaylists()
    }

    function cambiarCategoria(categoriaId) {
        categoria_actual = categoriaId || "todo"
        configuracion.guardar("playlists_categoria", categoria_actual)
        reconstruirPlaylists()
    }

    function playlistFiltradaPorId(playlistId) {
        for (var i = 0; i < playlists_filtradas.length; ++i) {
            var pl = playlists_filtradas[i]
            var id = pl ? (pl.playlist_id || pl.id || -1) : -1
            if (Number(id) === Number(playlistId))
                return pl
        }
        return null
    }

    function playlistInicial() {
        if (playlists_filtradas.length <= 0)
            return null
        for (var i = 0; i < playlists_filtradas.length; ++i) {
            var pl = playlists_filtradas[i]
            if (pl && String(pl.tipo_playlist || pl.subtipo || "") === "favoritos")
                return pl
        }
        return playlists_filtradas[0]
    }

    function asegurarSeleccion() {
        if (_asegurandoSeleccion)
            return
        _asegurandoSeleccion = true
        try {
            if (playlists_filtradas.length <= 0) {
                playlist_seleccionada_id = -1
                detalle_completo_abierto = false
                return
            }
            var seleccion = playlistFiltradaPorId(playlist_seleccionada_id)
            if (!seleccion)
                seleccion = playlistInicial()
            var playlistId = seleccion ? (seleccion.playlist_id || seleccion.id || -1) : -1
            if (playlistId > 0) {
                playlist_seleccionada_id = playlistId
                configuracion.guardar("playlists_seleccionada_id", String(playlistId))
                if (playlists.playlist_activa_id !== playlistId)
                    playlists.abrir_playlist(playlistId)
            }
        } finally {
            _asegurandoSeleccion = false
        }
    }

    function cambiarModo(modo) {
        modo_vista = modo
        configuracion.guardar("playlists_modo_vista", modo)
        reconstruirPlaylists()
    }

    function anchoTarjeta(contenedor) {
        if (modo_vista_efectivo === "lista")
            return contenedor
        var base = modo_vista_efectivo === "grid-sm" ? 168 : (modo_vista_efectivo === "grid-lg" ? 282 : 220)
        var columnas = Math.max(1, Math.floor((contenedor + UiTokens.spacing14) / (base + UiTokens.spacing14)))
        return Math.floor((contenedor - (columnas - 1) * UiTokens.spacing14) / columnas)
    }

    // Altura fija reservada bajo la carátula (título + meta + botón + márgenes).
    // La carátula ocupa el resto y queda SIEMPRE cuadrada: la tarjeta crece en
    // alto con su ancho para no recortar la portada (que es una imagen completa).
    function reservaTarjeta() {
        return modo_vista_efectivo === "grid-sm" ? 104 : 112
    }

    function altoTarjeta(ancho) {
        if (modo_vista_efectivo === "lista")
            return 86
        // Carátula cuadrada = ancho útil (ancho - 2 márgenes) + área de texto.
        return Math.round(ancho - 2 * UiTokens.spacing10 + reservaTarjeta())
    }

    function tocarPlaylist(pl) {
        seleccionarPlaylist(pl)
    }

    function pistasActivasArray() {
        var out = []
        for (var i = 0; i < playlists.pistas_activas.total; ++i)
            out.push(playlists.pistas_activas.obtener(i))
        return out
    }

    function reproducirPlaylistDesde(indice) {
        var datos = pistasActivasArray()
        if (datos.length <= 0) {
            mostrar_toast("No hay canciones para reproducir", "warning")
            return
        }
        var inicio = Math.max(0, Math.min(indice || 0, datos.length - 1))
        reproductor.reproducir_cola_desde_pistas(datos, inicio)
    }

    function agregarPlaylistActivaACola() {
        var datos = pistasActivasArray()
        if (datos.length <= 0) {
            mostrar_toast("No hay canciones para reproducir", "warning")
            return
        }
        reproductor.agregar_varias_a_cola(datos)
        mostrar_toast("Playlist agregada a la cola", "success")
    }

    function mostrar_toast(mensaje, tono) {
        if (!mensaje)
            return
        if (shell && shell.mostrar_toast_global) {
            shell.mostrar_toast_global(mensaje, tono || "info")
        } else if (toast) {
            toast.show(mensaje, tono || "info")
        }
    }

    function ejecutar(resultado, tonoOk, refrescarVista) {
        if (!resultado)
            return
        mostrar_toast(resultado.mensaje || (resultado.ok ? "Listo" : "No se pudo completar"), resultado.ok ? (tonoOk || "success") : "danger")
        if (refrescarVista !== false)
            reconstruirPlaylists()
    }

    function confirmar(titulo, mensaje, accion) {
        titulo_confirmacion = titulo
        mensaje_confirmacion = mensaje
        accionConfirmada = accion
        dialogo_confirmacion.open()
    }

    function abrirEditorActivo() {
        if (!playlists.playlist_activa || !playlists.playlist_activa.playlist_id)
            return
        campo_editar_nombre.text = playlists.playlist_activa.nombre || ""
        campo_editar_descripcion.text = playlists.playlist_activa.descripcion || ""
        dialogo_editar.open()
    }

    function abrirAgregar() {
        campo_buscar_agregar.text = ""
        buscarAgregar("", true)
        dialogo_agregar.open()
        campo_buscar_agregar.enfocar()
    }

    function buscarAgregar(valor, inmediato) {
        _busqueda_agregar_pendiente = valor || ""
        if (inmediato) {
            busquedaAgregarTimer.stop()
            playlists.buscar_pistas_para_playlist(_busqueda_agregar_pendiente, playlists.playlist_activa_id)
        } else {
            busquedaAgregarTimer.restart()
        }
    }

    function desenfocar_busqueda() {
        if (buscadorPlaylists && buscadorPlaylists.limpiarFoco)
            buscadorPlaylists.limpiarFoco()
        if (campo_buscar_agregar && campo_buscar_agregar.limpiarFoco)
            campo_buscar_agregar.limpiarFoco()
    }

    function _tapDentroDeBuscador(posicion) {
        var campos = [buscadorPlaylists, campo_buscar_agregar]
        for (var i = 0; i < campos.length; ++i) {
            if (campos[i] && campos[i].contienePuntoRaiz && campos[i].contienePuntoRaiz(posicion))
                return true
        }
        return false
    }

    Component.onCompleted: {
        categoria_actual = categoria_actual || "todo"
        orden_actual = ordenValido(orden_actual)
        playlists.sincronizar_inteligentes_async(0)
        reconstruirPlaylists()
    }

    onCategoria_actualChanged: {
        configuracion.guardar("playlists_categoria", categoria_actual)
        reconstruirPlaylists()
    }
    onFiltro_textoChanged: reconstruirPlaylists()
    onOrden_actualChanged: {
        orden_actual = ordenValido(orden_actual)
        configuracion.guardar("playlists_orden", orden_actual)
        reconstruirPlaylists()
    }

    Connections {
        target: playlists
        function onPlaylistsCambiadas() { reconstruirPlaylists() }
        function onPlaylistActivaCambiada() {
            if (playlists.playlist_activa_id > 0) {
                playlist_seleccionada_id = playlists.playlist_activa_id
            } else {
                playlist_seleccionada_id = -1
                detalle_completo_abierto = false
            }
        }
        function onErrorCambiado(mensaje) { mostrar_toast(mensaje, "danger") }
    }

    TapHandler {
        acceptedButtons: Qt.LeftButton
        onTapped: function(point, button) {
            if (_tapDentroDeBuscador(point.position))
                return
            desenfocar_busqueda()
        }
    }

    component Icono: Item {
        id: iconRoot
        property string source: ""
        property color iconColor: tema.texto
        property int iconSize: UiTokens.iconMd
        width: iconSize
        height: iconSize

        Image {
            id: iconImage
            anchors.fill: parent
            source: iconRoot.source
            sourceSize.width: iconRoot.iconSize * 2
            sourceSize.height: iconRoot.iconSize * 2
            smooth: true
            opacity: 0
        }
        MultiEffect {
            anchors.fill: iconImage
            source: iconImage
            colorization: 1.0
            colorizationColor: iconRoot.iconColor
        }
    }

    component IconButton: Rectangle {
        id: boton
        property string iconSource: ""
        property color iconColor: tema.texto
        property string tooltip: ""
        property bool danger: false
        property bool selected: false
        signal clicked()

        // implicitWidth/Height (no width/height) para que el botón se dimensione
        // correctamente como hijo de un Layout: la fila de modos de vista usa un
        // Repeater dentro de un RowLayout y, sin tamaño implícito, el layout les
        // asignaba ancho 0 y los botones se superponían (no se podían pulsar).
        implicitWidth: UiTokens.controlHeightMd
        implicitHeight: UiTokens.controlHeightMd
        radius: UiTokens.radiusSm
        color: area.containsMouse && enabled ? tema.hover : "transparent"
        border.color: selected ? tema.acento : (area.containsMouse && enabled ? tema.borde : "transparent")
        opacity: enabled ? 1.0 : 0.38

        Icono {
            anchors.centerIn: parent
            source: boton.iconSource
            iconColor: boton.danger ? tema.peligro : boton.iconColor
            iconSize: UiTokens.iconMd
        }

        MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            enabled: boton.enabled
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onPressed: boton.scale = 0.96
            onReleased: boton.scale = 1.0
            onCanceled: boton.scale = 1.0
            onClicked: boton.clicked()
        }
    }

    component ActionButton: Rectangle {
        id: accion
        property string text: ""
        property string iconSource: ""
        property bool primary: false
        property bool danger: false
        signal clicked()

        implicitWidth: contenido.implicitWidth + UiTokens.spacing24
        width: implicitWidth
        height: UiTokens.controlHeightMd
        radius: UiTokens.radiusSm
        color: !enabled ? tema.superficieAlt
               : primary ? (areaAccion.pressed ? tema.acentoFuerte : (areaAccion.containsMouse ? tema.acentoFuerte : tema.acento))
               : areaAccion.pressed ? tema.superficieAlt
               : (areaAccion.containsMouse ? tema.hover : "transparent")
        border.color: primary ? "transparent" : tema.borde
        opacity: enabled ? 1.0 : 0.42

        RowLayout {
            id: contenido
            anchors.centerIn: parent
            spacing: UiTokens.spacing8
            Icono {
                source: accion.iconSource
                iconColor: accion.primary ? tema.fondo : (accion.danger ? tema.peligro : tema.texto)
                iconSize: UiTokens.iconSm
            }
            AppText {
                text: accion.text
                color: accion.primary ? tema.fondo : (accion.danger ? tema.peligro : tema.texto)
                font.pixelSize: UiTokens.fontSizeMd
                font.bold: accion.primary
            }
        }

        MouseArea {
            id: areaAccion
            anchors.fill: parent
            hoverEnabled: true
            enabled: accion.enabled
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: accion.clicked()
        }
    }

    component CoverBox: Rectangle {
        id: cover
        property string portada: ""
        property int coverRadius: UiTokens.radiusSm
        property int imageFillMode: Image.PreserveAspectFit
        radius: coverRadius
        clip: true
        color: cover.portada !== "" ? "transparent" : tema.superficieAlt

        Image {
            anchors.fill: parent
            source: cover.portada ? portadaDe(cover.portada) : ""
            fillMode: cover.imageFillMode
            asynchronous: true
            smooth: true
            visible: cover.portada !== ""
        }

        Icono {
            visible: cover.portada === ""
            anchors.centerIn: parent
            source: "../assets/icons/playlist.svg"
            iconColor: tema.textoMuted
            iconSize: Math.min(cover.width, cover.height) * 0.38
        }
    }

    // Distintivo de "playlist anclada": chip con contraste propio (fondo
    // semiopaco + borde de acento) para verse sobre cualquier portada. Se
    // superpone en la esquina de la carátula según el modo de vista.
    component PinChip: Rectangle {
        property bool mostrar: false
        visible: mostrar
        implicitWidth: 24
        implicitHeight: 24
        radius: width / 2
        color: Qt.rgba(tema.fondoElevado.r, tema.fondoElevado.g, tema.fondoElevado.b, 0.82)
        border.width: 1
        border.color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.55)
        Icono {
            anchors.centerIn: parent
            source: "../assets/icons/pin.svg"
            iconColor: raiz.colorAccionTarjeta
            iconSize: 13
        }
    }

    component SearchBox: Rectangle {
        id: searchRoot
        property alias text: campo.text
        property string placeholderText: ""
        signal textoCambiado(string value)

        function limpiarFoco() {
            campo.focus = false
        }

        function enfocar() {
            campo.forceActiveFocus()
        }

        function contienePuntoRaiz(posicion) {
            var local = searchRoot.mapFromItem(raiz, posicion.x, posicion.y)
            return local.x >= 0 && local.y >= 0 && local.x <= searchRoot.width && local.y <= searchRoot.height
        }

        implicitHeight: raiz.layout_compacto ? UiTokens.controlHeightMd : UiTokens.controlHeightLg
        radius: UiTokens.radiusPill
        color: campo.activeFocus ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.08)
                                  : (areaSearch.containsMouse ? tema.hover : tema.superficie)
        border.color: campo.activeFocus ? tema.acento : (areaSearch.containsMouse ? tema.textoMuted : tema.borde)
        border.width: 1

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: UiTokens.spacing14
            anchors.rightMargin: UiTokens.spacing8
            spacing: UiTokens.spacing8

            Icono {
                source: "../assets/icons/search.svg"
                iconColor: campo.activeFocus ? tema.acento : tema.textoMuted
                iconSize: UiTokens.iconMd
                Layout.alignment: Qt.AlignVCenter
            }

            TextField {
                id: campo
                Layout.fillWidth: true
                Layout.fillHeight: true
                placeholderText: searchRoot.placeholderText
                color: tema.texto
                placeholderTextColor: tema.textoMuted
                selectedTextColor: tema.fondo
                selectionColor: tema.acento
                font.pixelSize: UiTokens.fontSizeMd
                background: Item {}
                verticalAlignment: TextInput.AlignVCenter
                onTextChanged: searchRoot.textoCambiado(text)
            }

            IconButton {
                Layout.preferredWidth: UiTokens.controlHeightSm
                Layout.preferredHeight: UiTokens.controlHeightSm
                iconSource: "../assets/icons/close.svg"
                iconColor: tema.textoMuted
                visible: campo.text.length > 0
                onClicked: {
                    campo.text = ""
                    campo.forceActiveFocus()
                }
            }
        }

        MouseArea {
            id: areaSearch
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.NoButton
            cursorShape: Qt.IBeamCursor
        }
    }

    component ToolbarLabel: AppText {
        id: toolbarLabel
        property string texto: ""
        width: implicitWidth + UiTokens.spacing8
        height: UiTokens.controlHeightSm
        text: texto
        color: tema.textoMuted
        font.pixelSize: UiTokens.fontSizeSm
        font.weight: Font.DemiBold
        verticalAlignment: Text.AlignVCenter
    }

    component OrdenChip: Rectangle {
        id: chipOrden
        property string texto: ""
        property string iconSource: ""
        property bool activo: false
        signal clicked()

        width: Math.max(raiz.layout_compacto ? 72 : 82, chipOrdenRow.implicitWidth + (raiz.layout_compacto ? UiTokens.spacing12 : UiTokens.spacing20))
        height: raiz.layout_compacto ? UiTokens.controlHeightSm : UiTokens.controlHeightMd
        radius: UiTokens.radiusPill
        color: activo ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.16)
                      : (chipOrdenArea.containsMouse ? tema.hover : tema.superficie)
        border.color: activo ? tema.acento : tema.borde

        Row {
            id: chipOrdenRow
            anchors.centerIn: parent
            spacing: UiTokens.spacing6
            Icono {
                anchors.verticalCenter: parent.verticalCenter
                source: chipOrden.iconSource
                iconColor: chipOrden.activo ? tema.acento : tema.textoMuted
                iconSize: UiTokens.iconSm
            }
            AppText {
                anchors.verticalCenter: parent.verticalCenter
                text: chipOrden.texto
                color: chipOrden.activo ? tema.texto : tema.textoSec
                font.pixelSize: UiTokens.fontSizeSm
                font.bold: chipOrden.activo
            }
        }

        MouseArea {
            id: chipOrdenArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: chipOrden.clicked()
        }
    }

    component ModalPopup: Popup {
        id: modalRoot
        property bool cerrarFuera: true

        parent: Overlay.overlay
        modal: true
        dim: true
        focus: true
        padding: UiTokens.spacing24
        closePolicy: cerrarFuera ? (Popup.CloseOnEscape | Popup.CloseOnPressOutside) : Popup.CloseOnEscape
        x: Math.round((((parent ? parent.width : raiz.width) - width) / 2))
        y: Math.round((((parent ? parent.height : raiz.height) - height) / 2))

        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0.0; to: 1.0; duration: UiTokens.durationBase; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.96; to: 1.0; duration: UiTokens.durationBase; easing.type: Easing.OutCubic }
        }
        exit: Transition {
            NumberAnimation { property: "opacity"; from: 1.0; to: 0.0; duration: UiTokens.durationFast; easing.type: Easing.InCubic }
        }

        Overlay.modal: Rectangle {
            color: UiUtils.veloOscuro(0.62)
            Behavior on opacity { NumberAnimation { duration: UiTokens.durationBase } }
        }

        background: Rectangle {
            radius: UiTokens.radiusMd
            color: tema.fondoElevado
            border.color: tema.borde
            border.width: 1
        }
    }

    component FormField: Rectangle {
        id: fieldRoot
        property alias text: input.text
        property string placeholderText: ""
        property bool multiline: false
        property bool fieldEnabled: true

        function enfocar() {
            if (multiline)
                area.forceActiveFocus()
            else
                input.forceActiveFocus()
        }

        implicitHeight: multiline ? 104 : UiTokens.controlHeightLg
        radius: UiTokens.radiusSm
        color: fieldEnabled ? tema.superficie : tema.superficieAlt
        border.color: fieldEnabled && (input.activeFocus || area.activeFocus) ? tema.acento : tema.borde
        opacity: fieldEnabled ? 1.0 : 0.52

        TextField {
            id: input
            visible: !fieldRoot.multiline
            enabled: fieldRoot.fieldEnabled
            anchors.fill: parent
            anchors.leftMargin: UiTokens.spacing12
            anchors.rightMargin: UiTokens.spacing12
            placeholderText: fieldRoot.placeholderText
            color: tema.texto
            placeholderTextColor: tema.textoMuted
            selectedTextColor: tema.fondo
            selectionColor: tema.acento
            font.pixelSize: UiTokens.fontSizeMd
            background: Item {}
            verticalAlignment: TextInput.AlignVCenter
        }

        TextArea {
            id: area
            visible: fieldRoot.multiline
            enabled: fieldRoot.fieldEnabled
            anchors.fill: parent
            anchors.margins: UiTokens.spacing10
            placeholderText: fieldRoot.placeholderText
            color: tema.texto
            placeholderTextColor: tema.textoMuted
            selectedTextColor: tema.fondo
            selectionColor: tema.acento
            font.pixelSize: UiTokens.fontSizeMd
            background: Item {}
            wrapMode: TextEdit.WordWrap
            text: input.text
            onTextChanged: input.text = text
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: margen_lateral
        spacing: UiTokens.spacing16

        RowLayout {
            Layout.fillWidth: true
            spacing: UiTokens.spacing16

            ColumnLayout {
                Layout.fillWidth: true
                spacing: UiTokens.spacing4
                AppText {
                    text: "Playlists"
                    color: tema.texto
                    font.pixelSize: UiTokens.fontSizeDisplay
                    font.bold: true
                }
                AppText {
                    text: "Listas manuales, favoritas y mezclas locales preparadas con tu biblioteca."
                    color: tema.textoSec
                    font.pixelSize: UiTokens.fontSizeMd
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                    maximumLineCount: 1
                }
            }

            ActionButton {
                text: "Crear para mí"
                iconSource: "../assets/icons/sync.svg"
                primary: false
                onClicked: raiz.ejecutar(playlists.sincronizar_inteligentes(3), "info")
            }
            ActionButton {
                text: "Nueva playlist"
                iconSource: "../assets/icons/plus.svg"
                primary: true
                onClicked: {
                    campo_nueva_nombre.text = ""
                    campo_nueva_descripcion.text = ""
                    error_nueva_playlist = ""
                    dialogo_nueva.open()
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: UiTokens.spacing10

            SearchBox {
                id: buscadorPlaylists
                Layout.fillWidth: true
                text: raiz.filtro_texto
                placeholderText: "Buscar por nombre, tipo u origen"
                onTextoCambiado: function(value) { raiz.filtro_texto = value }
            }

        }

        Flow {
            id: categoriasFlow
            Layout.fillWidth: true
            Layout.preferredHeight: implicitHeight
            spacing: raiz.layout_compacto ? UiTokens.spacing4 : UiTokens.spacing8

            Repeater {
                model: raiz.categorias
                delegate: Rectangle {
                    id: chipCategoria
                    readonly property bool activa: categoria_actual === modelData.id
                    readonly property bool disponible: modelData.id === "todo" || modelData.id === "favoritos" || raiz.conteoCategoria(modelData.id) > 0
                    visible: disponible
                    height: visible ? (raiz.layout_compacto ? UiTokens.controlHeightSm : UiTokens.controlHeightMd) : 0
                    width: visible ? chipContent.implicitWidth + (raiz.layout_compacto ? UiTokens.spacing16 : UiTokens.spacing24) : 0
                    radius: UiTokens.radiusPill
                    color: activa ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.16)
                                  : (chipArea.containsMouse ? tema.hover : tema.superficie)
                    border.color: activa ? tema.acento : tema.borde
                    opacity: disponible ? 1.0 : 0.0

                    RowLayout {
                        id: chipContent
                        anchors.centerIn: parent
                        spacing: UiTokens.spacing6
                        Icono {
                            source: modelData.icono
                            iconColor: chipCategoria.activa ? tema.acento : tema.textoMuted
                            iconSize: UiTokens.iconSm
                        }
                        AppText {
                            text: modelData.nombre
                            color: chipCategoria.activa ? tema.texto : tema.textoSec
                            font.pixelSize: UiTokens.fontSizeMd
                            font.bold: chipCategoria.activa
                        }
                    }
                    MouseArea {
                        id: chipArea
                        anchors.fill: parent
                        hoverEnabled: true
                        enabled: chipCategoria.disponible
                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: cambiarCategoria(modelData.id)
                    }
                }
            }
        }

        Flow {
            id: ordenFlow
            Layout.fillWidth: true
            Layout.preferredHeight: implicitHeight
            spacing: raiz.layout_compacto ? UiTokens.spacing4 : UiTokens.spacing8
            visible: raiz.opcionesOrden.length > 0

            ToolbarLabel { texto: "Orden" }
            
            Repeater {
                model: raiz.opcionesOrden
                delegate: OrdenChip {
                    texto: modelData.nombre
                    iconSource: modelData.icono
                    activo: orden_actual === modelData.id
                    onClicked: cambiarOrden(modelData.id)
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: UiTokens.spacing16

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: UiTokens.spacing10

                RowLayout {
                    Layout.fillWidth: true
                    spacing: UiTokens.spacing8
                    StatusBadge {
                        tema: raiz.tema
                        text: playlists_filtradas.length === 1 ? "1 playlist" : playlists_filtradas.length + " playlists"
                        tone: "neutral"
                    }
                    StatusBadge {
                        visible: categoria_actual === "inteligentes"
                        tema: raiz.tema
                        text: "Con datos locales"
                        tone: "info"
                    }
                    Item { Layout.fillWidth: true }
                    Repeater {
                        model: raiz.modosVista
                        delegate: IconButton {
                            iconSource: modelData.icono
                            iconColor: modo_vista_efectivo === modelData.id ? tema.acento : tema.textoSec
                            selected: modo_vista_efectivo === modelData.id
                            enabled: !raiz.layout_compacto
                            opacity: enabled ? 1.0 : 0.5
                            onClicked: cambiarModo(modelData.id)
                        }
                    }
                }



                Flickable {
                    id: flickPlaylists
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    contentWidth: width
                    contentHeight: playlistsFlow.height
                    ScrollBar.vertical: AppScrollBar { tema: raiz.tema; policy: ScrollBar.AsNeeded }
                    onContentYChanged: if (!detalle_completo_abierto) raiz._scroll_playlists = contentY

                    Flow {
                        id: playlistsFlow
                        width: flickPlaylists.width
                        spacing: UiTokens.spacing14
                        // Tamaño de tarjeta compartido y reactivo: una única fuente
                        // de verdad para todas las tarjetas (evita alturas
                        // inconsistentes que provocaban superposiciones al
                        // refrescar el modelo tras importar) y fuerza el reflow al
                        // cambiar de modo de vista.
                        readonly property int cardW: anchoTarjeta(width)
                        readonly property int cardH: altoTarjeta(cardW)

                        Repeater {
                            model: raiz.playlists_filtradas
                            delegate: playlistCardComponent
                        }
                    }

                    EmptyState {
                        anchors.centerIn: parent
                        visible: playlists_filtradas.length === 0
                        tema: raiz.tema
                        iconSource: "../assets/icons/playlist.svg"
                        title: "Sin playlists para mostrar"
                        description: "Crea tu primera playlist o deja que NB SOUND prepare algunas cuando tenga suficiente musica."
                    }
                }
            }

            Loader {
                Layout.preferredWidth: preview_lateral_visible ? ancho_preview : 0
                Layout.fillHeight: true
                active: preview_lateral_visible
                visible: active
                sourceComponent: previewComponent
            }
        }
    }

    Loader {
        anchors.fill: parent
        active: detalle_completo_abierto
        visible: active
        z: 20
        sourceComponent: detalleCompletoComponent
    }

    Component {
        id: playlistCardComponent
        Rectangle {
            id: card
            property var plData: modelData
            readonly property int playlistId: plData.playlist_id || plData.id || -1
            width: playlistsFlow.cardW
            height: playlistsFlow.cardH
            radius: UiTokens.radiusSm
            clip: true
            activeFocusOnTab: true
            color: areaCard.containsMouse || (playlist_seleccionada_id === playlistId)
                   ? tema.hover : tema.superficie
            border.color: playlist_seleccionada_id === playlistId ? tema.acento : tema.borde

            Keys.onReturnPressed: abrirDetallePlaylist(card.playlistId)
            Keys.onEnterPressed: abrirDetallePlaylist(card.playlistId)

            MouseArea {
                id: areaCard
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    card.forceActiveFocus()
                    tocarPlaylist(card.plData)
                }
                onDoubleClicked: abrirDetallePlaylist(card.playlistId)
            }

            RowLayout {
                visible: modo_vista_efectivo === "lista"
                anchors.fill: parent
                anchors.margins: UiTokens.spacing10
                spacing: UiTokens.spacing12

                CoverBox {
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 64
                    Layout.maximumWidth: 64
                    Layout.maximumHeight: 64
                    portada: card.plData.portada_ruta || ""
                    coverRadius: UiTokens.radiusSm

                    PinChip {
                        mostrar: !!card.plData.es_anclada
                        implicitWidth: 20
                        implicitHeight: 20
                        anchors.top: parent.top
                        anchors.right: parent.right
                        anchors.margins: 3
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: UiTokens.spacing4
                    AppText {
                        text: card.plData.nombre || "Playlist"
                        color: tema.texto
                        font.pixelSize: UiTokens.fontSizeLg
                        font.bold: true
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        Layout.fillWidth: true
                    }
                    AppText {
                        text: textoTipo(card.plData) + " - " + textoPistas(card.plData.num_pistas || 0)
                        color: tema.textoSec
                        font.pixelSize: UiTokens.fontSizeMd
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }

                IconButton {
                    iconSource: "../assets/icons/play.svg"
                    iconColor: raiz.colorAccionTarjeta
                    enabled: Number(card.plData.num_pistas || 0) > 0
                    onClicked: {
                        seleccionarPlaylist(card.plData)
                        Qt.callLater(function() { reproducirPlaylistDesde(0) })
                    }
                }
            }

            ColumnLayout {
                visible: modo_vista_efectivo !== "lista"
                anchors.fill: parent
                anchors.margins: UiTokens.spacing10
                spacing: UiTokens.spacing8

                CoverBox {
                    // Carátula cuadrada: alto = ancho útil de la tarjeta. La
                    // tarjeta reserva `reservaTarjeta()` para el texto, así que
                    // este alto coincide siempre con el ancho de la portada.
                    Layout.fillWidth: true
                    Layout.preferredHeight: card.height - reservaTarjeta()
                    portada: card.plData.portada_ruta || ""
                    coverRadius: UiTokens.radiusSm
                    imageFillMode: Image.PreserveAspectCrop

                    PinChip {
                        mostrar: !!card.plData.es_anclada
                        implicitWidth: modo_vista_efectivo === "grid-sm" ? 22 : 26
                        implicitHeight: modo_vista_efectivo === "grid-sm" ? 22 : 26
                        anchors.top: parent.top
                        anchors.right: parent.right
                        anchors.margins: UiTokens.spacing6
                    }
                }

                AppText {
                    text: card.plData.nombre || "Playlist"
                    color: tema.texto
                    font.pixelSize: modo_vista_efectivo === "grid-sm" ? UiTokens.fontSizeMd : UiTokens.fontSizeLg
                    font.bold: true
                    elide: Text.ElideRight
                    maximumLineCount: 1
                    Layout.fillWidth: true
                }
                AppText {
                    text: textoTipo(card.plData) + " - " + textoPistas(card.plData.num_pistas || 0)
                    color: tema.textoSec
                    font.pixelSize: UiTokens.fontSizeMd
                    elide: Text.ElideRight
                    maximumLineCount: 1
                    Layout.fillWidth: true
                }

                RowLayout {
                    Layout.fillWidth: true
                    Item { Layout.fillWidth: true }
                    IconButton {
                        iconSource: "../assets/icons/play.svg"
                        iconColor: raiz.colorAccionTarjeta
                        enabled: Number(card.plData.num_pistas || 0) > 0
                        onClicked: {
                            seleccionarPlaylist(card.plData)
                            Qt.callLater(function() { reproducirPlaylistDesde(0) })
                        }
                    }
                }
            }
        }
    }


    Component {
        id: previewComponent
        Rectangle {
            id: preview
            color: tema.fondoElevado
            radius: UiTokens.radiusMd
            border.color: tema.borde
            clip: true
            property var activa: playlists.playlist_activa || ({})
            readonly property bool tienePistas: playlists.pistas_activas.total > 0

            Flickable {
                anchors.fill: parent
                anchors.margins: UiTokens.spacing16
                clip: true
                contentWidth: width
                contentHeight: previewContenido.implicitHeight
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: AppScrollBar { tema: raiz.tema; policy: ScrollBar.AsNeeded }

                ColumnLayout {
                    id: previewContenido
                    width: parent.width
                    spacing: UiTokens.spacing12

                    CoverBox {
                        Layout.fillWidth: true
                        Layout.preferredHeight: width
                        Layout.maximumHeight: width
                        portada: preview.activa.portada_ruta || ""
                        coverRadius: UiTokens.radiusSm
                        imageFillMode: Image.PreserveAspectFit
                    }

                    StatusBadge {
                        tema: raiz.tema
                        text: textoTipo(preview.activa)
                        tone: "info"
                    }

                    AppText {
                        text: preview.activa.nombre || "Playlist"
                        color: tema.texto
                        font.pixelSize: UiTokens.fontSizeXl
                        font.bold: true
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        Layout.fillWidth: true
                    }

                    AppText {
                        text: textoPistas(preview.activa.num_pistas || playlists.pistas_activas.total)
                              + " - " + reproductor.formatear_duracion_larga(preview.activa.duracion_total_seg || 0)
                        color: tema.textoSec
                        font.pixelSize: UiTokens.fontSizeSm
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }

                    AppText {
                        text: preview.activa.descripcion || "Sin descripción"
                        color: tema.textoSec
                        font.pixelSize: UiTokens.fontSizeMd
                        wrapMode: Text.WordWrap
                        maximumLineCount: 5
                        Layout.fillWidth: true
                    }

                    Flow {
                        Layout.fillWidth: true
                        spacing: UiTokens.spacing8
                        ActionButton {
                            text: "Abrir"
                            iconSource: "../assets/icons/chevron-right.svg"
                            onClicked: abrirDetallePlaylist(preview.activa.playlist_id || playlist_seleccionada_id)
                        }
                        ActionButton {
                            text: preview.activa.es_anclada ? "Desanclar" : "Anclar"
                            iconSource: "../assets/icons/pin.svg"
                            enabled: preview.activa.puede_anclar === true
                            onClicked: raiz.ejecutar(playlists.anclar_playlist(preview.activa.playlist_id, !preview.activa.es_anclada), "info")
                        }
                        ActionButton {
                            text: "Reproducir"
                            iconSource: "../assets/icons/play.svg"
                            primary: true
                            enabled: preview.tienePistas
                            onClicked: reproducirPlaylistDesde(0)
                        }
                        ActionButton {
                            text: "Añadir a cola"
                            iconSource: "../assets/icons/queue-play.svg"
                            enabled: preview.tienePistas
                            onClicked: agregarPlaylistActivaACola()
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: tema.borde
                    }

                    AppText {
                        text: "Canciones"
                        color: tema.texto
                        font.pixelSize: UiTokens.fontSizeMd
                        font.bold: true
                    }

                    ListView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.min(210, Math.max(96, playlists.pistas_activas.total * 44))
                        visible: preview.tienePistas
                        model: playlists.pistas_activas
                        clip: true
                        interactive: contentHeight > height
                        spacing: UiTokens.spacing6
                        ScrollBar.vertical: AppScrollBar { tema: raiz.tema; policy: ScrollBar.AsNeeded }

                        delegate: RowLayout {
                            width: ListView.view.width
                            height: 38
                            spacing: UiTokens.spacing8
                            property var pista: playlists.pistas_activas.obtener(index)
                            AppText {
                                Layout.preferredWidth: 24
                                text: String(index + 1)
                                color: tema.textoMuted
                                font.pixelSize: UiTokens.fontSizeSm
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: UiTokens.spacing2
                                AppText {
                                    text: pista.titulo || pista.nombre_archivo || "Canción"
                                    color: tema.texto
                                    font.pixelSize: UiTokens.fontSizeSm
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                AppText {
                                    text: pista.artista_nombre || "Artista desconocido"
                                    color: tema.textoMuted
                                    font.pixelSize: UiTokens.fontSizeSm
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }
                        }
                    }

                    EmptyState {
                        Layout.fillWidth: true
                        visible: !preview.tienePistas
                        tema: raiz.tema
                        iconSource: "../assets/icons/playlist.svg"
                        title: preview.activa.tipo_playlist === "favoritos" ? "Me gusta está vacía" : "Playlist sin canciones"
                        description: preview.activa.tipo_playlist === "favoritos"
                                     ? "Marca canciones como favoritas y aparecerán aquí."
                                     : "Abre la playlist para agregar canciones."
                    }
                }
            }
        }
    }

    Component {
        id: detalleCompletoComponent
        Rectangle {
            id: detalle
            color: tema.fondo
            clip: true

            // Referencia explícita al root para evitar 'raiz is not defined' en delegates reciclados
            readonly property var _raiz: raiz
            property var activa: playlists.playlist_activa || ({})
            readonly property bool tienePistas: playlists.pistas_activas.total > 0
            property bool opcionesAvanzadas: false

            Rectangle {
                width: parent.width
                height: 300
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.12) }
                    GradientStop { position: 1.0; color: tema.fondo }
                }
            }

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                Item {
                    Layout.fillWidth: true
                    height: 60

                    Rectangle {
                        anchors.left: parent.left
                        anchors.leftMargin: margen_lateral
                        anchors.verticalCenter: parent.verticalCenter
                        width: volverDetalleRow.implicitWidth + UiTokens.spacing20
                        height: 34
                        radius: UiTokens.radiusPill
                        color: volverDetalleArea.containsMouse ? tema.hover : "transparent"
                        border.color: tema.borde

                        Row {
                            id: volverDetalleRow
                            anchors.centerIn: parent
                            spacing: UiTokens.spacing6
                            Icono {
                                anchors.verticalCenter: parent.verticalCenter
                                source: "../assets/icons/back.svg"
                                iconColor: tema.textoSec
                                iconSize: UiTokens.iconSm
                            }
                            AppText {
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Volver"
                                color: tema.textoSec
                                font.pixelSize: UiTokens.fontSizeSm
                                font.bold: true
                            }
                        }

                        MouseArea {
                            id: volverDetalleArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: cerrarDetalleCompleto()
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: margen_lateral
                    Layout.rightMargin: margen_lateral
                    Layout.bottomMargin: UiTokens.spacing24
                    spacing: layout_compacto ? UiTokens.spacing16 : UiTokens.spacing24

                    CoverBox {
                        Layout.preferredWidth: layout_compacto ? 138 : 212
                        Layout.preferredHeight: layout_compacto ? 138 : 212
                        Layout.maximumWidth: layout_compacto ? 150 : 212
                        Layout.maximumHeight: layout_compacto ? 150 : 212
                        portada: detalle.activa.portada_ruta || ""
                        coverRadius: UiTokens.radiusSm
                        imageFillMode: Image.PreserveAspectCrop
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignBottom
                        spacing: UiTokens.spacing8
                        StatusBadge {
                            tema: raiz.tema
                            text: textoTipo(detalle.activa)
                            tone: "info"
                        }
                        AppText {
                            text: detalle.activa.nombre || "Playlist"
                            color: tema.texto
                            font.pixelSize: layout_compacto ? 26 : 38
                            font.bold: true
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            Layout.fillWidth: true
                        }
                        AppText {
                            text: detalle.activa.descripcion || "Sin descripción"
                            color: tema.textoSec
                            font.pixelSize: layout_compacto ? UiTokens.fontSizeMd : UiTokens.fontSizeLg
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            Layout.fillWidth: true
                        }
                        AppText {
                            text: textoPistas(detalle.activa.num_pistas || playlists.pistas_activas.total)
                                  + " - " + reproductor.formatear_duracion_larga(detalle.activa.duracion_total_seg || 0)
                            color: tema.textoMuted
                            font.pixelSize: UiTokens.fontSizeMd
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }

                        Flow {
                            Layout.fillWidth: true
                            Layout.topMargin: UiTokens.spacing4
                            spacing: UiTokens.spacing8
                            ActionButton {
                                text: "Reproducir"
                                iconSource: "../assets/icons/play.svg"
                                primary: true
                                enabled: detalle.tienePistas
                                onClicked: reproducirPlaylistDesde(0)
                            }
                            ActionButton {
                                text: "Añadir a cola"
                                iconSource: "../assets/icons/queue-play.svg"
                                enabled: detalle.tienePistas
                                onClicked: agregarPlaylistActivaACola()
                            }
                            ActionButton {
                                text: "Agregar"
                                iconSource: "../assets/icons/plus.svg"
                                enabled: detalle.activa.puede_agregar === true
                                onClicked: abrirAgregar()
                            }
                            ActionButton {
                                text: "Editar"
                                iconSource: "../assets/icons/edit.svg"
                                enabled: detalle.activa.puede_renombrar === true || detalle.activa.puede_editar_descripcion === true
                                onClicked: abrirEditorActivo()
                            }
                            ActionButton {
                                text: detalle.activa.es_anclada ? "Desanclar" : "Anclar"
                                iconSource: "../assets/icons/pin.svg"
                                enabled: detalle.activa.puede_anclar === true
                                onClicked: { if (detalle._raiz) detalle._raiz.ejecutar(playlists.anclar_playlist(detalle.activa.playlist_id, !detalle.activa.es_anclada), "info") }
                            }
                            ActionButton {
                                text: detalle.opcionesAvanzadas ? "Ocultar opciones" : "Opciones"
                                iconSource: "../assets/icons/settings.svg"
                                onClicked: detalle.opcionesAvanzadas = !detalle.opcionesAvanzadas
                            }
                        }

                        Flow {
                            Layout.fillWidth: true
                            visible: detalle.opcionesAvanzadas
                            spacing: UiTokens.spacing8
                            ActionButton {
                                text: "Duplicar como manual"
                                iconSource: "../assets/icons/playlist.svg"
                                enabled: detalle.tienePistas
                                onClicked: {
                                    if (!detalle._raiz)
                                        return
                                    var resultado = playlists.duplicar_playlist(detalle.activa.playlist_id)
                                    detalle._raiz.ejecutar(resultado)
                                    // Tras duplicar, la lista se recarga en background y
                                    // `asegurarSeleccion` puede saltar a "Me gusta" si la
                                    // categoría activa no permite ver la nueva entrada
                                    // antes de que `abrir_playlist(nueva_id)` termine.
                                    // Forzamos selección + categoría "mías" para que la
                                    // duplicada quede visible y abierta de inmediato.
                                    if (resultado && resultado.ok && resultado.playlist_id) {
                                        if (!coincideCategoriaId(
                                                { tipo: "manual", origen: "usuario" },
                                                detalle._raiz.categoria_actual))
                                            detalle._raiz.categoria_actual = "mias"
                                        detalle._raiz.abrirDetallePlaylist(resultado.playlist_id)
                                    }
                                }
                            }
                            ActionButton {
                                text: "Vaciar"
                                iconSource: "../assets/icons/trash.svg"
                                danger: true
                                enabled: detalle.activa.puede_vaciar === true && detalle.tienePistas
                                onClicked: {
                                    var playlistId = detalle.activa.playlist_id
                                    var r = detalle._raiz
                                    if (r) r.confirmar("Vaciar playlist", "Se quitarán todas las canciones de esta playlist.", function() {
                                        r.ejecutar(playlists.vaciar_playlist(playlistId), "warning")
                                    })
                                }
                            }
                            ActionButton {
                                text: "Eliminar"
                                iconSource: "../assets/icons/trash.svg"
                                danger: true
                                enabled: detalle.activa.puede_eliminar === true
                                onClicked: {
                                    var playlistId = detalle.activa.playlist_id
                                    var r = detalle._raiz
                                    if (r) r.confirmar("Eliminar playlist", "La playlist dejará de aparecer en tu biblioteca.", function() {
                                        r.ejecutar(playlists.eliminar_playlist(playlistId), "warning")
                                    })
                                }
                            }
                            ActionButton {
                                text: "Regenerar"
                                iconSource: "../assets/icons/sync.svg"
                                enabled: !!detalle.activa.auto_key && detalle.activa.tipo_playlist !== "favoritos"
                                onClicked: { if (detalle._raiz) detalle._raiz.ejecutar(playlists.regenerar_playlist(detalle.activa.playlist_id), "info") }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.leftMargin: margen_lateral
                    Layout.rightMargin: margen_lateral
                    Layout.preferredHeight: 36
                    radius: UiTokens.radiusSm
                    color: tema.superficieAlt
                    border.color: tema.borde

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: UiTokens.spacing12
                        anchors.rightMargin: UiTokens.spacing12
                        spacing: UiTokens.spacing8
                        AppText { text: "#"; font.pixelSize: UiTokens.fontSizeSm; font.bold: true; color: tema.textoMuted; Layout.preferredWidth: 32; horizontalAlignment: Text.AlignHCenter }
                        AppText { text: "Título"; font.pixelSize: UiTokens.fontSizeSm; font.bold: true; color: tema.textoMuted; Layout.fillWidth: true }
                        AppText { text: "Duración"; font.pixelSize: UiTokens.fontSizeSm; font.bold: true; color: tema.textoMuted; Layout.preferredWidth: 72; horizontalAlignment: Text.AlignRight }
                        AppText { text: "Acciones"; font.pixelSize: UiTokens.fontSizeSm; font.bold: true; color: tema.textoMuted; Layout.preferredWidth: layout_compacto ? 112 : 152; horizontalAlignment: Text.AlignHCenter }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.leftMargin: margen_lateral
                    Layout.rightMargin: margen_lateral
                    Layout.preferredHeight: 1
                    color: tema.borde
                }

                ListView {
                    id: listaPistas
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.leftMargin: margen_lateral
                    Layout.rightMargin: margen_lateral
                    model: playlists.pistas_activas
                    clip: true
                    spacing: UiTokens.spacing6
                    boundsBehavior: Flickable.StopAtBounds
                    reuseItems: true
                    cacheBuffer: 420
                    move: Transition {
                        NumberAnimation { properties: "x,y"; duration: UiTokens.durationBase; easing.type: Easing.OutQuad }
                    }
                    moveDisplaced: Transition {
                        NumberAnimation { properties: "x,y"; duration: UiTokens.durationBase; easing.type: Easing.OutQuad }
                    }
                    ScrollBar.vertical: AppScrollBar { tema: raiz.tema; policy: ScrollBar.AsNeeded }

                    EmptyState {
                        anchors.centerIn: parent
                        visible: playlists.pistas_activas.total === 0
                        tema: raiz.tema
                        iconSource: "../assets/icons/playlist.svg"
                        title: detalle.activa.tipo_playlist === "favoritos" ? "Me gusta está vacía" : "Playlist sin canciones"
                        description: detalle.activa.tipo_playlist === "favoritos"
                                     ? "Marca canciones como favoritas y aparecerán aquí."
                                     : "Agrega canciones desde tu biblioteca para empezar."
                    }

                    delegate: Rectangle {
                        id: filaTrack
                        property var pista: playlists.pistas_activas.obtener(index)
                        property bool editable: detalle.activa.puede_reordenar === true
                        width: ListView.view.width
                        height: 64
                        radius: UiTokens.radiusSm
                        color: areaTrack.containsMouse || (detalle._raiz && detalle._raiz.indice_destino === index) ? tema.hover : "transparent"
                        border.color: (detalle._raiz && detalle._raiz.indice_destino === index) ? tema.acento : "transparent"
                        z: dragArea.drag.active ? 30 : 1
                        Drag.active: dragArea.drag.active
                        Drag.keys: ["playlist-track"]
                        Drag.hotSpot.x: width * 0.5
                        Drag.hotSpot.y: height * 0.5

                        DropArea {
                            anchors.fill: parent
                            keys: ["playlist-track"]
                            onEntered: {
                                var r = detalle._raiz
                                if (r && r.indice_arrastrando >= 0 && r.indice_arrastrando !== index)
                                    r.indice_destino = index
                            }
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: UiTokens.spacing8
                            spacing: UiTokens.spacing10

                            Rectangle {
                                Layout.preferredWidth: 28
                                Layout.preferredHeight: 48
                                radius: UiTokens.radiusSm
                                color: dragArea.containsMouse && filaTrack.editable ? tema.hover : "transparent"
                                opacity: filaTrack.editable ? 1.0 : 0.28

                                Icono {
                                    anchors.centerIn: parent
                                    source: "../assets/icons/drag-handle.svg"
                                    iconColor: tema.textoMuted
                                    iconSize: UiTokens.iconMd
                                }

                                MouseArea {
                                    id: dragArea
                                    anchors.fill: parent
                                    enabled: filaTrack.editable
                                    hoverEnabled: true
                                    drag.target: filaTrack
                                    cursorShape: enabled ? Qt.OpenHandCursor : Qt.ArrowCursor
                                    onPressed: { if (detalle._raiz) detalle._raiz.indice_arrastrando = index }
                                    onReleased: {
                                        filaTrack.x = 0
                                        filaTrack.y = 0
                                        var r = detalle._raiz
                                        if (r && r.indice_destino >= 0 && r.indice_destino !== index) {
                                            r.ejecutar(playlists.reordenar_playlist(detalle.activa.playlist_id, filaTrack.pista.id, r.indice_destino + 1), "info", false)
                                        }
                                        if (r) {
                                            r.indice_arrastrando = -1
                                            r.indice_destino = -1
                                        }
                                    }
                                }
                            }

                            AppText {
                                Layout.preferredWidth: 32
                                text: String(index + 1)
                                color: tema.textoMuted
                                font.pixelSize: UiTokens.fontSizeSm
                                horizontalAlignment: Text.AlignHCenter
                            }

                            CoverBox {
                                Layout.preferredWidth: 44
                                Layout.preferredHeight: 44
                                portada: filaTrack.pista.portada_ruta || ""
                                coverRadius: UiTokens.radiusSm
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: UiTokens.spacing2
                                AppText {
                                    text: filaTrack.pista.titulo || filaTrack.pista.nombre_archivo || "Canción"
                                    color: tema.texto
                                    font.pixelSize: UiTokens.fontSizeMd
                                    font.bold: true
                                    elide: Text.ElideRight
                                    maximumLineCount: 1
                                    Layout.fillWidth: true
                                }
                                AppText {
                                    text: (filaTrack.pista.artista_nombre || "Artista desconocido")
                                          + (filaTrack.pista.album_titulo ? " - " + filaTrack.pista.album_titulo : "")
                                    color: tema.textoSec
                                    font.pixelSize: UiTokens.fontSizeSm
                                    elide: Text.ElideRight
                                    maximumLineCount: 1
                                    Layout.fillWidth: true
                                }
                            }

                            AppText {
                                Layout.preferredWidth: 52
                                text: reproductor.formatear_tiempo(filaTrack.pista.duracion_seg || 0)
                                color: tema.textoMuted
                                font.pixelSize: UiTokens.fontSizeSm
                                horizontalAlignment: Text.AlignRight
                            }

                            IconButton {
                                iconSource: "../assets/icons/more-vertical.svg"
                                tooltip: "Agregar a playlist"
                                onClicked: menuAgregarPlaylist.abrir(
                                    filaTrack.pista.id,
                                    filaTrack.pista.titulo || filaTrack.pista.nombre_archivo || "Canción")
                            }
                            IconButton {
                                iconSource: "../assets/icons/move-up.svg"
                                enabled: filaTrack.editable && index > 0
                                onClicked: { if (detalle._raiz) detalle._raiz.ejecutar(playlists.reordenar_playlist(detalle.activa.playlist_id, filaTrack.pista.id, index), "info", false) }
                            }
                            IconButton {
                                iconSource: "../assets/icons/move-down.svg"
                                enabled: filaTrack.editable && index < playlists.pistas_activas.total - 1
                                onClicked: { if (detalle._raiz) detalle._raiz.ejecutar(playlists.reordenar_playlist(detalle.activa.playlist_id, filaTrack.pista.id, index + 2), "info", false) }
                            }
                            IconButton {
                                iconSource: "../assets/icons/trash.svg"
                                danger: true
                                enabled: detalle.activa.puede_quitar === true
                                onClicked: {
                                    var playlistId = detalle.activa.playlist_id
                                    var pistaId = filaTrack.pista.id
                                    var r = detalle._raiz
                                    if (r) r.confirmar("Quitar de esta playlist", "La canción se quitará solo de esta playlist.", function() {
                                        r.ejecutar(playlists.quitar_pista(playlistId, pistaId), "warning", false)
                                    })
                                }
                            }
                        }

                        MouseArea {
                            id: areaTrack
                            anchors.fill: parent
                            anchors.leftMargin: 72
                            anchors.rightMargin: 190
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: reproducirPlaylistDesde(index)
                        }
                    }
                }
            }
        }
    }

    ModalPopup {
        id: dialogo_nueva
        cerrarFuera: true
        width: Math.min(480, raiz.width - UiTokens.spacing32)
        onOpened: {
            error_nueva_playlist = ""
            campo_nueva_nombre.enfocar()
        }
        onClosed: {
            campo_nueva_nombre.text = ""
            campo_nueva_descripcion.text = ""
            error_nueva_playlist = ""
            desenfocar_busqueda()
        }

        contentItem: ColumnLayout {
            spacing: UiTokens.spacing16
            AppText {
                text: "Nueva playlist"
                color: tema.texto
                font.pixelSize: UiTokens.fontSizeXl
                font.bold: true
            }
            FormField {
                id: campo_nueva_nombre
                Layout.fillWidth: true
                placeholderText: "Nombre"
            }
            FormField {
                id: campo_nueva_descripcion
                Layout.fillWidth: true
                placeholderText: "Descripción opcional"
                multiline: true
            }
            AppText {
                Layout.fillWidth: true
                visible: error_nueva_playlist !== ""
                text: error_nueva_playlist
                color: tema.peligro
                font.pixelSize: UiTokens.fontSizeSm
                wrapMode: Text.WordWrap
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: "Cancelar"
                    iconSource: "../assets/icons/close.svg"
                    onClicked: dialogo_nueva.close()
                }
                ActionButton {
                    text: "Crear"
                    iconSource: "../assets/icons/plus.svg"
                    primary: true
                    onClicked: {
                        if (campo_nueva_nombre.text.trim() === "") {
                            error_nueva_playlist = "El nombre de la playlist es obligatorio."
                            mostrar_toast(error_nueva_playlist, "warning")
                            return
                        }
                        var r = playlists.crear_playlist(campo_nueva_nombre.text, campo_nueva_descripcion.text)
                        raiz.ejecutar(r)
                        if (r.ok) {
                            dialogo_nueva.close()
                            abrirDetallePlaylist(r.playlist_id)
                        } else {
                            error_nueva_playlist = r.mensaje || "No se pudo crear la playlist."
                        }
                    }
                }
            }
        }
    }

    ModalPopup {
        id: dialogo_editar
        cerrarFuera: true
        width: Math.min(500, raiz.width - UiTokens.spacing32)
        onOpened: {
            error_editar_playlist = ""
            campo_editar_nombre.enfocar()
        }
        onClosed: {
            error_editar_playlist = ""
            desenfocar_busqueda()
        }

        contentItem: ColumnLayout {
            spacing: UiTokens.spacing16
            AppText {
                text: "Editar playlist"
                color: tema.texto
                font.pixelSize: UiTokens.fontSizeXl
                font.bold: true
            }
            FormField {
                id: campo_editar_nombre
                Layout.fillWidth: true
                fieldEnabled: playlists.playlist_activa.puede_renombrar === true
                placeholderText: "Nombre"
            }
            FormField {
                id: campo_editar_descripcion
                Layout.fillWidth: true
                fieldEnabled: playlists.playlist_activa.puede_editar_descripcion === true
                placeholderText: "Descripción"
                multiline: true
            }
            AppText {
                Layout.fillWidth: true
                visible: error_editar_playlist !== ""
                text: error_editar_playlist
                color: tema.peligro
                font.pixelSize: UiTokens.fontSizeSm
                wrapMode: Text.WordWrap
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: "Cancelar"
                    iconSource: "../assets/icons/close.svg"
                    onClicked: dialogo_editar.close()
                }
                ActionButton {
                    text: "Guardar"
                    iconSource: "../assets/icons/edit.svg"
                    primary: true
                    onClicked: {
                        var ok = true
                        if (playlists.playlist_activa.puede_renombrar === true) {
                            var rn = playlists.renombrar_playlist(playlists.playlist_activa_id, campo_editar_nombre.text)
                            raiz.ejecutar(rn)
                            ok = ok && rn.ok
                            if (!rn.ok)
                                error_editar_playlist = rn.mensaje || "No se pudo renombrar."
                        }
                        if (playlists.playlist_activa.puede_editar_descripcion === true) {
                            var rd = playlists.editar_descripcion_playlist(playlists.playlist_activa_id, campo_editar_descripcion.text)
                            raiz.ejecutar(rd)
                            ok = ok && rd.ok
                            if (!rd.ok)
                                error_editar_playlist = rd.mensaje || "No se pudo guardar la descripción."
                        }
                        if (ok)
                            dialogo_editar.close()
                    }
                }
            }
        }
    }

    ModalPopup {
        id: dialogo_agregar
        cerrarFuera: true
        width: Math.min(760, raiz.width - UiTokens.spacing32)
        height: Math.min(640, raiz.height - UiTokens.spacing32)

        contentItem: ColumnLayout {
            spacing: UiTokens.spacing14

            AppText {
                text: "Agregar canciones"
                color: tema.texto
                font.pixelSize: UiTokens.fontSizeXl
                font.bold: true
            }
            AppText {
                text: "Busca por canción, artista o álbum."
                color: tema.textoSec
                font.pixelSize: UiTokens.fontSizeMd
            }

            SearchBox {
                id: campo_buscar_agregar
                Layout.fillWidth: true
                placeholderText: "Busca por canción, artista, álbum, género o año"
                onTextoCambiado: function(value) { raiz.buscarAgregar(value, false) }
            }

            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                model: playlists.resultados_agregar
                clip: true
                spacing: UiTokens.spacing6
                ScrollBar.vertical: AppScrollBar { tema: raiz.tema; policy: ScrollBar.AsNeeded }

                EmptyState {
                    anchors.centerIn: parent
                    visible: playlists.resultados_agregar.total === 0
                    tema: raiz.tema
                    iconSource: "../assets/icons/search.svg"
                    title: campo_buscar_agregar.text.trim() === "" ? "Busca en tu biblioteca" : "No encontré canciones"
                    description: campo_buscar_agregar.text.trim() === ""
                                 ? "Puedes buscar por canción, artista, álbum, género o año."
                                 : "Prueba con otro título, artista, álbum o género."
                }

                delegate: Rectangle {
                    id: filaAgregar
                    property var pista: playlists.resultados_agregar.obtener(index)
                    width: ListView.view.width
                    height: 62
                    radius: UiTokens.radiusSm
                    color: areaAgregar.containsMouse ? tema.hover : "transparent"

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: UiTokens.spacing8
                        spacing: UiTokens.spacing10
                        CoverBox {
                            Layout.preferredWidth: 44
                            Layout.preferredHeight: 44
                            portada: filaAgregar.pista.portada_ruta || ""
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: UiTokens.spacing2
                            AppText {
                                text: filaAgregar.pista.titulo || filaAgregar.pista.nombre_archivo || "Canción"
                                color: tema.texto
                                font.pixelSize: UiTokens.fontSizeMd
                                font.bold: true
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            AppText {
                                text: (filaAgregar.pista.artista_nombre || "Artista desconocido")
                                      + (filaAgregar.pista.album_titulo ? " - " + filaAgregar.pista.album_titulo : "")
                                color: tema.textoSec
                                font.pixelSize: UiTokens.fontSizeSm
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                        }
                        ActionButton {
                            text: filaAgregar.pista.ya_en_playlist ? "Ya está" : "Añadir"
                            iconSource: "../assets/icons/plus.svg"
                            enabled: !filaAgregar.pista.ya_en_playlist
                            onClicked: {
                                var r = playlists.agregar_pista(playlists.playlist_activa_id, filaAgregar.pista.id)
                                raiz.ejecutar(r, "success", false)
                                raiz.buscarAgregar(campo_buscar_agregar.text, true)
                            }
                        }
                    }

                    MouseArea {
                        id: areaAgregar
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.NoButton
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: "Cerrar"
                    iconSource: "../assets/icons/close.svg"
                    onClicked: dialogo_agregar.close()
                }
            }
        }
    }

    ModalPopup {
        id: dialogo_confirmacion
        cerrarFuera: true
        width: Math.min(430, raiz.width - UiTokens.spacing32)
        onClosed: {
            titulo_confirmacion = ""
            mensaje_confirmacion = ""
            accionConfirmada = null
        }

        contentItem: ColumnLayout {
            spacing: UiTokens.spacing14
            AppText {
                Layout.fillWidth: true
                text: titulo_confirmacion
                color: tema.texto
                font.pixelSize: UiTokens.fontSizeXl
                font.bold: true
                wrapMode: Text.WordWrap
            }
            AppText {
                Layout.fillWidth: true
                text: mensaje_confirmacion
                color: tema.textoSec
                font.pixelSize: UiTokens.fontSizeMd
                wrapMode: Text.WordWrap
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: "Cancelar"
                    iconSource: "../assets/icons/close.svg"
                    onClicked: dialogo_confirmacion.close()
                }
                ActionButton {
                    text: "Confirmar"
                    iconSource: "../assets/icons/trash.svg"
                    danger: true
                    onClicked: {
                        var accion = accionConfirmada
                        try {
                            if (typeof accion === "function")
                                accion()
                        } finally {
                            accionConfirmada = null
                            dialogo_confirmacion.close()
                        }
                    }
                }
            }
        }
    }

    Timer {
        id: busquedaAgregarTimer
        interval: 240
        repeat: false
        onTriggered: playlists.buscar_pistas_para_playlist(raiz._busqueda_agregar_pendiente, playlists.playlist_activa_id)
    }

    ToastMessage {
        id: toast
        parent: Overlay.overlay
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: UiTokens.spacing24
        tema: raiz.tema
    }

    MenuAgregarPlaylist {
        id: menuAgregarPlaylist
        tema: raiz.tema
        onGuardado: function(mensaje) { mostrar_toast(mensaje, "info") }
    }
}
