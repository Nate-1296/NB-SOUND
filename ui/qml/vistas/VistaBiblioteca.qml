import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtQuick.Effects
import QtQml

import "../componentes"
import "../componentes/UiUtils.js" as UiUtils

Rectangle {
    id: raiz
    color: tema.fondo
    clip: true

    property var shell: null
    readonly property var tema: shell ? shell.tema : temaUi

    property string modo_vista: "albums"
    property bool detalle_abierto: false
    property bool detalle_artista_abierto: false
    property var album_activo: null
    property var artista_activo: null
    property string grupo_albums: "albums"
    property string filtro_albums: ""
    property string orden_albums: "artista"
    property string filtro_artistas: ""
    property string orden_artistas: "nombre"
    property string filtro_pistas: ""
    property string orden_pistas: "titulo"
    property bool solo_favoritas: false
    property bool _estado_restaurado: false
    property var historial_biblioteca: []
    property real _scroll_albums: 0
    property real _scroll_artistas: 0
    property real _scroll_pistas: 0

    readonly property bool mostrando_detalle: detalle_abierto || detalle_artista_abierto
    readonly property int margen_lateral: width < 980 ? UiTokens.spacing16 : UiTokens.spacing24
    readonly property bool mostrar_columna_album: width >= 1080
    readonly property int ancho_columna_album: width < 1180 ? 150 : 230
    readonly property int acciones_pistas_ancho: width < 1080 ? 300 : (width < 1180 ? 464 : 528)

    function portadaDe(ruta) { return UiUtils.toMediaSource(ruta) }

    function desenfocar_busqueda() {
        if (filtroAlbumsInput && filtroAlbumsInput.limpiarFoco)
            filtroAlbumsInput.limpiarFoco()
        if (filtroArtistasInput && filtroArtistasInput.limpiarFoco)
            filtroArtistasInput.limpiarFoco()
        if (filtroPistasInput && filtroPistasInput.limpiarFoco)
            filtroPistasInput.limpiarFoco()
    }

    function _tapDentroDeBuscador(posicion) {
        var campos = [filtroAlbumsInput, filtroArtistasInput, filtroPistasInput]
        for (var i = 0; i < campos.length; ++i) {
            if (campos[i] && campos[i].contienePuntoRaiz && campos[i].contienePuntoRaiz(posicion))
                return true
        }
        return false
    }

    TapHandler {
        acceptedButtons: Qt.LeftButton
        onTapped: function(point, button) {
            if (_tapDentroDeBuscador(point.position))
                return
            desenfocar_busqueda()
        }
    }

    function _opcionesOrdenAlbums() {
        return [
            {"label": "Artista A-Z", "valor": "artista", "icon": "../assets/icons/sort-asc.svg"},
            {"label": "Artista Z-A", "valor": "artista_desc", "icon": "../assets/icons/sort-desc.svg"},
            {"label": "Título A-Z", "valor": "titulo", "icon": "../assets/icons/sort-asc.svg"},
            {"label": "Título Z-A", "valor": "titulo_desc", "icon": "../assets/icons/sort-desc.svg"},
            {"label": "Año reciente", "valor": "anio", "icon": "../assets/icons/sort-desc.svg"},
            {"label": "Año antiguo", "valor": "anio_asc", "icon": "../assets/icons/sort-asc.svg"},
            {"label": "Más pistas", "valor": "pistas", "icon": "../assets/icons/sort-desc.svg"},
            {"label": "Menos pistas", "valor": "pistas_asc", "icon": "../assets/icons/sort-asc.svg"},
            {"label": "Mayor duración", "valor": "duracion", "icon": "../assets/icons/sort-desc.svg"},
            {"label": "Menor duración", "valor": "duracion_asc", "icon": "../assets/icons/sort-asc.svg"}
        ]
    }

    function _opcionesOrdenArtistas() {
        return [
            {"label": "Nombre A-Z", "valor": "nombre", "icon": "../assets/icons/sort-asc.svg"},
            {"label": "Nombre Z-A", "valor": "nombre_desc", "icon": "../assets/icons/sort-desc.svg"},
            {"label": "Más pistas", "valor": "num_pistas", "icon": "../assets/icons/sort-desc.svg"},
            {"label": "Menos pistas", "valor": "num_pistas_asc", "icon": "../assets/icons/sort-asc.svg"},
            {"label": "Más álbumes", "valor": "num_albums", "icon": "../assets/icons/sort-desc.svg"},
            {"label": "Menos álbumes", "valor": "num_albums_asc", "icon": "../assets/icons/sort-asc.svg"},
            {"label": "Mayor duración", "valor": "duracion", "icon": "../assets/icons/sort-desc.svg"},
            {"label": "Menor duración", "valor": "duracion_asc", "icon": "../assets/icons/sort-asc.svg"}
        ]
    }

    function _opcionesOrdenPistas() {
        return [
            {"label": "Título A-Z", "valor": "titulo", "icon": "../assets/icons/sort-asc.svg"},
            {"label": "Título Z-A", "valor": "titulo_desc", "icon": "../assets/icons/sort-desc.svg"},
            {"label": "Artista A-Z", "valor": "artista", "icon": "../assets/icons/sort-asc.svg"},
            {"label": "Artista Z-A", "valor": "artista_desc", "icon": "../assets/icons/sort-desc.svg"},
            {"label": "Álbum A-Z", "valor": "album", "icon": "../assets/icons/sort-asc.svg"},
            {"label": "Álbum Z-A", "valor": "album_desc", "icon": "../assets/icons/sort-desc.svg"},
            {"label": "Año reciente", "valor": "anio", "icon": "../assets/icons/sort-desc.svg"},
            {"label": "Año antiguo", "valor": "anio_asc", "icon": "../assets/icons/sort-asc.svg"},
            {"label": "Mayor duración", "valor": "duracion", "icon": "../assets/icons/sort-desc.svg"},
            {"label": "Menor duración", "valor": "duracion_asc", "icon": "../assets/icons/sort-asc.svg"},
            {"label": "Recientes", "valor": "reciente", "icon": "../assets/icons/sort-desc.svg"},
            {"label": "Antiguas", "valor": "reciente_asc", "icon": "../assets/icons/sort-asc.svg"},
            {"label": "Más reproducidas", "valor": "reproducida", "icon": "../assets/icons/sort-desc.svg"},
            {"label": "Menos reproducidas", "valor": "reproducida_asc", "icon": "../assets/icons/sort-asc.svg"}
        ]
    }

    function _textoPista(pista) {
        return pista && (pista.titulo || pista.nombre_archivo) ? (pista.titulo || pista.nombre_archivo) : "Sin título"
    }

    function _portadaUi(item) {
        if (!item)
            return ""
        if (item.portada_display_ruta !== undefined)
            return item.portada_display_ruta || ""
        if (item.portada_thumb_ruta !== undefined && item.portada_thumb_ruta)
            return item.portada_thumb_ruta
        return item.portada_ruta || ""
    }

    function _textoMetaAlbum(album) {
        if (!album) return ""
        var partes = []
        if (album.tipo) partes.push(_etiquetaTipoAlbum(album.tipo))
        if (album.anio) partes.push(album.anio)
        partes.push((album.num_pistas || 0) + " pistas")
        if (album.duracion_total_seg) partes.push(reproductor.formatear_duracion_larga(album.duracion_total_seg))
        return partes.join(" · ")
    }

    function _etiquetaTipoAlbum(tipo) {
        var valor = String(tipo || "").trim()
        if (valor.toLowerCase() === "album")
            return "Álbum"
        return valor
    }

    function _textoMetaPista(pista) {
        if (!pista) return ""
        var partes = []
        if (pista.artista_nombre) partes.push(pista.artista_nombre)
        if (pista.album_titulo) partes.push(pista.album_titulo)
        if (pista.anio) partes.push(pista.anio)
        if (pista.genero) partes.push(pista.genero)
        return partes.join(" · ")
    }

    function _resumenActual() {
        if (detalle_abierto && album_activo)
            return (album_activo.num_pistas || 0) + " pistas"
        if (detalle_artista_abierto && artista_activo)
            return (artista_activo.num_albums || 0) + " álbumes · " + (artista_activo.num_pistas || 0) + " pistas"
        if (modo_vista === "artistas")
            return biblioteca.artistas.total + " artistas"
        if (modo_vista === "pistas")
            return biblioteca.pistas.total + " pistas"
        return biblioteca.albums.total + " álbumes"
    }

    function _ordenValidoPistas(valor) {
        return ["titulo", "titulo_desc", "artista", "artista_desc", "album", "album_desc", "anio", "anio_asc", "duracion", "duracion_asc", "reciente", "reciente_asc", "reproducida", "reproducida_asc"].indexOf(valor) >= 0 ? valor : "titulo"
    }

    function _ordenValidoAlbums(valor) {
        return ["artista", "artista_desc", "titulo", "titulo_desc", "anio", "anio_asc", "pistas", "pistas_asc", "duracion", "duracion_asc"].indexOf(valor) >= 0 ? valor : "artista"
    }

    function _ordenValidoArtistas(valor) {
        return ["nombre", "nombre_desc", "num_pistas", "num_pistas_asc", "num_albums", "num_albums_asc", "duracion", "duracion_asc"].indexOf(valor) >= 0 ? valor : "nombre"
    }

    function _capturar_scroll() {
        if (albumGrid.visible)
            _scroll_albums = albumGrid.contentY
        if (artistGrid.visible)
            _scroll_artistas = artistGrid.contentY
        if (trackList.visible)
            _scroll_pistas = trackList.contentY
    }

    function _estado_actual() {
        _capturar_scroll()
        return {
            "seccion": modo_vista,
            "grupo_albums": grupo_albums,
            "detalle": detalle_abierto ? "album" : (detalle_artista_abierto ? "artista" : ""),
            "album_id": album_activo && album_activo.id ? album_activo.id : 0,
            "artista_id": artista_activo && artista_activo.id ? artista_activo.id : 0,
            "filtro_albums": filtro_albums,
            "filtro_artistas": filtro_artistas,
            "filtro_pistas": filtro_pistas,
            "solo_favoritas": solo_favoritas,
            "orden_pistas": orden_pistas,
            "orden_albums": orden_albums,
            "orden_artistas": orden_artistas,
            "scroll_albums": _scroll_albums,
            "scroll_artistas": _scroll_artistas,
            "scroll_pistas": _scroll_pistas
        }
    }

    function _push_historial() {
        if (!_estado_restaurado)
            return
        var estado = _estado_actual()
        var pila = historial_biblioteca.slice()
        pila.push(estado)
        if (pila.length > 40)
            pila.shift()
        historial_biblioteca = pila
    }

    function _aplicar_estado_navegacion(estado) {
        if (!estado)
            return
        modo_vista = estado.seccion || "albums"
        grupo_albums = estado.grupo_albums || "albums"
        filtro_albums = estado.filtro_albums || ""
        filtro_artistas = estado.filtro_artistas || ""
        filtro_pistas = estado.filtro_pistas || ""
        solo_favoritas = !!estado.solo_favoritas
        orden_pistas = _ordenValidoPistas(estado.orden_pistas || "titulo")
        orden_albums = _ordenValidoAlbums(estado.orden_albums || "artista")
        orden_artistas = _ordenValidoArtistas(estado.orden_artistas || "nombre")
        _scroll_albums = estado.scroll_albums || 0
        _scroll_artistas = estado.scroll_artistas || 0
        _scroll_pistas = estado.scroll_pistas || 0
        detalle_abierto = false
        detalle_artista_abierto = false
        album_activo = null
        artista_activo = null

        biblioteca.cargar_grupos_albums()
        _asegurar_grupo_album_valido()
        _cargar_vista_actual(true)

        if (estado.detalle === "album" && estado.album_id > 0) {
            abrir_album_id(estado.album_id, false)
        } else if (estado.detalle === "artista" && estado.artista_id > 0) {
            abrir_artista_id(estado.artista_id, false)
        }
        _programar_guardado()
    }

    function volver_biblioteca() {
        if (historial_biblioteca.length > 0) {
            var pila = historial_biblioteca.slice()
            var estado = pila.pop()
            historial_biblioteca = pila
            _aplicar_estado_navegacion(estado)
            return
        }

        if (detalle_abierto) {
            detalle_abierto = false
            album_activo = null
            modo_vista = "albums"
            _cargar_vista_actual(true)
            _programar_guardado()
            return
        }

        if (detalle_artista_abierto) {
            detalle_artista_abierto = false
            artista_activo = null
            modo_vista = "artistas"
            _cargar_vista_actual(true)
            _programar_guardado()
        }
    }

    function _programar_guardado() {
        if (!_estado_restaurado)
            return
        guardarEstadoTimer.restart()
    }

    function _guardar_estado_actual() {
        if (_estado_restaurado)
            biblioteca.guardar_estado_vista(_estado_actual())
    }

    function _asegurar_grupo_album_valido() {
        if (biblioteca.grupos_albums.total === 0)
            return
        for (var i = 0; i < biblioteca.grupos_albums.total; ++i) {
            if (biblioteca.grupos_albums.obtener(i).clave === grupo_albums)
                return
        }
        grupo_albums = biblioteca.grupos_albums.obtener(0).clave || "albums"
    }

    function _restaurar_scroll_actual() {
        Qt.callLater(function() {
            if (modo_vista === "albums")
                albumGrid.contentY = Math.max(0, _scroll_albums)
            else if (modo_vista === "artistas")
                artistGrid.contentY = Math.max(0, _scroll_artistas)
            else
                trackList.contentY = Math.max(0, _scroll_pistas)
        })
    }

    function _cargar_vista_actual(restaurarScroll) {
        _asegurar_grupo_album_valido()
        if (modo_vista === "artistas") {
            biblioteca.cargar_artistas(filtro_artistas, orden_artistas)
        } else if (modo_vista === "pistas") {
            biblioteca.cargar_pistas(filtro_pistas, solo_favoritas, orden_pistas)
        } else {
            biblioteca.cargar_albums_por_grupo(grupo_albums, orden_albums, filtro_albums)
        }
        if (restaurarScroll)
            _restaurar_scroll_actual()
    }

    function cambiar_seccion(seccion) {
        if (modo_vista === seccion && !mostrando_detalle)
            return
        _capturar_scroll()
        modo_vista = seccion
        detalle_abierto = false
        detalle_artista_abierto = false
        _cargar_vista_actual(true)
        _programar_guardado()
    }

    function cambiar_grupo_album(grupo) {
        if (grupo_albums === grupo)
            return
        _capturar_scroll()
        grupo_albums = grupo
        albumGrid.contentY = 0
        _scroll_albums = 0
        biblioteca.cargar_albums_por_grupo(grupo_albums, orden_albums, filtro_albums)
        _programar_guardado()
    }

    function cambiar_orden_albums(valor) {
        var nuevo = _ordenValidoAlbums(valor)
        if (orden_albums === nuevo)
            return
        orden_albums = nuevo
        albumGrid.contentY = 0
        _scroll_albums = 0
        biblioteca.cargar_albums_por_grupo(grupo_albums, orden_albums, filtro_albums)
        _programar_guardado()
    }

    function cambiar_orden_artistas(valor) {
        var nuevo = _ordenValidoArtistas(valor)
        if (orden_artistas === nuevo)
            return
        orden_artistas = nuevo
        artistGrid.contentY = 0
        _scroll_artistas = 0
        biblioteca.cargar_artistas(filtro_artistas, orden_artistas)
        _programar_guardado()
    }

    function cambiar_orden_pistas(valor) {
        var nuevo = _ordenValidoPistas(valor)
        if (orden_pistas === nuevo)
            return
        orden_pistas = nuevo
        biblioteca.cargar_pistas(filtro_pistas, solo_favoritas, orden_pistas)
        _programar_guardado()
    }

    function filtrar_albums() {
        biblioteca.cargar_albums_por_grupo(grupo_albums, orden_albums, filtro_albums)
        albumGrid.contentY = 0
        _scroll_albums = 0
        _programar_guardado()
    }

    function filtrar_artistas() {
        biblioteca.cargar_artistas(filtro_artistas, orden_artistas)
        artistGrid.contentY = 0
        _scroll_artistas = 0
        _programar_guardado()
    }

    function filtrar_pistas() {
        biblioteca.cargar_pistas(filtro_pistas, solo_favoritas, orden_pistas)
        trackList.contentY = 0
        _scroll_pistas = 0
        _programar_guardado()
    }

    function refrescar_pistas_conservando_scroll() {
        _capturar_scroll()
        biblioteca.cargar_pistas(filtro_pistas, solo_favoritas, orden_pistas)
        _restaurar_scroll_actual()
        _programar_guardado()
    }

    function alternar_favorita_pista(pista) {
        if (!pista || !pista.id)
            return
        biblioteca.toggle_favorita(pista.id)
        if (detalle_abierto && album_activo && album_activo.id) {
            biblioteca.abrir_album(album_activo.id)
            album_activo = biblioteca.album_detalle
        } else if (detalle_artista_abierto && artista_activo && artista_activo.id) {
            biblioteca.abrir_artista(artista_activo.id)
            artista_activo = biblioteca.artista_detalle
        } else {
            refrescar_pistas_conservando_scroll()
        }
    }

    // Eliminación definitiva de una pista: abre el diálogo de confirmación.
    property var _pistaPendienteEliminar: ({})
    function pedir_eliminar_pista(pista) {
        if (!pista || !pista.id)
            return
        _pistaPendienteEliminar = pista
        dialogoEliminarPista.open()
    }

    function abrir_album_id(albumId, guardarHistorial) {
        if (!albumId)
            return
        var debeGuardarHistorial = guardarHistorial === undefined ? true : !!guardarHistorial
        if (debeGuardarHistorial && !(detalle_abierto && album_activo && album_activo.id === albumId))
            _push_historial()
        biblioteca.abrir_album(albumId)
        album_activo = biblioteca.album_detalle
        detalle_abierto = true
        detalle_artista_abierto = false
        modo_vista = "albums"
        _programar_guardado()
    }

    function abrir_artista_id(artistaId, guardarHistorial) {
        if (!artistaId)
            return
        var debeGuardarHistorial = guardarHistorial === undefined ? true : !!guardarHistorial
        if (debeGuardarHistorial && !(detalle_artista_abierto && artista_activo && artista_activo.id === artistaId))
            _push_historial()
        biblioteca.abrir_artista(artistaId)
        artista_activo = biblioteca.artista_detalle
        detalle_artista_abierto = true
        detalle_abierto = false
        modo_vista = "artistas"
        _programar_guardado()
    }

    function cerrar_detalle_album() {
        volver_biblioteca()
    }

    function cerrar_detalle_artista() {
        volver_biblioteca()
    }

    function abrir_album_desde_pista(pista) {
        var resultado = biblioteca.abrir_album_desde_pista(pista)
        if (!resultado || !resultado.ok) {
            mostrar_toast(resultado && resultado.mensaje ? resultado.mensaje : "No se pudo abrir el álbum")
            return
        }
        _push_historial()
        album_activo = biblioteca.album_detalle
        modo_vista = "albums"
        detalle_abierto = true
        detalle_artista_abierto = false
        _programar_guardado()
    }

    function abrir_artista_desde_pista(pista) {
        var resultado = biblioteca.abrir_artista_desde_pista(pista)
        if (!resultado || !resultado.ok) {
            mostrar_toast(resultado && resultado.mensaje ? resultado.mensaje : "No se pudo abrir el artista")
            return
        }
        _push_historial()
        artista_activo = biblioteca.artista_detalle
        modo_vista = "artistas"
        detalle_artista_abierto = true
        detalle_abierto = false
        _programar_guardado()
    }

    function ir_a_inicio_biblioteca() {
        _capturar_scroll()
        biblioteca.cargar_grupos_albums()
        grupo_albums = biblioteca.primer_grupo_albums()
        modo_vista = "albums"
        detalle_abierto = false
        detalle_artista_abierto = false
        album_activo = null
        artista_activo = null
        historial_biblioteca = []
        _scroll_albums = 0
        albumGrid.contentY = 0
        biblioteca.cargar_albums_por_grupo(grupo_albums, orden_albums, filtro_albums)
        _programar_guardado()
    }

    function _restaurar_estado_inicial() {
        var estado = biblioteca.estado_vista()
        modo_vista = estado.seccion || "albums"
        grupo_albums = estado.grupo_albums || "albums"
        filtro_albums = estado.filtro_albums || ""
        filtro_artistas = estado.filtro_artistas || ""
        filtro_pistas = estado.filtro_pistas || ""
        solo_favoritas = !!estado.solo_favoritas
        orden_pistas = _ordenValidoPistas(estado.orden_pistas || "titulo")
        orden_albums = _ordenValidoAlbums(estado.orden_albums || "artista")
        orden_artistas = _ordenValidoArtistas(estado.orden_artistas || "nombre")
        _scroll_albums = estado.scroll_albums || 0
        _scroll_artistas = estado.scroll_artistas || 0
        _scroll_pistas = estado.scroll_pistas || 0

        biblioteca.cargar_grupos_albums()
        _asegurar_grupo_album_valido()
        _cargar_vista_actual(true)

        if (estado.detalle === "album" && estado.album_id > 0)
            abrir_album_id(estado.album_id, false)
        else if (estado.detalle === "artista" && estado.artista_id > 0)
            abrir_artista_id(estado.artista_id, false)

        _estado_restaurado = true
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(96, toolbarContenido.implicitHeight + UiTokens.spacing24)
            color: tema.fondoElevado
            border.color: tema.borde
            border.width: 0

            ColumnLayout {
                id: toolbarContenido
                anchors.fill: parent
                anchors.leftMargin: raiz.margen_lateral
                anchors.rightMargin: raiz.margen_lateral
                anchors.topMargin: UiTokens.spacing14
                anchors.bottomMargin: UiTokens.spacing10
                spacing: UiTokens.spacing10

                RowLayout {
                    Layout.fillWidth: true
                    spacing: UiTokens.spacing12

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: UiTokens.spacing2
                        AppText {
                            text: detalle_abierto && album_activo
                                  ? (album_activo.titulo || "Álbum")
                                  : (detalle_artista_abierto && artista_activo ? (artista_activo.nombre || "Artista") : "Biblioteca")
                            color: tema.texto
                            font.pixelSize: 25
                            font.bold: true
                            elide: Text.ElideRight
                            maximumLineCount: 1
                            Layout.fillWidth: true
                        }
                        AppText {
                            text: _resumenActual()
                            color: tema.textoSec
                            font.pixelSize: UiTokens.fontSizeMd
                            elide: Text.ElideRight
                            maximumLineCount: 1
                            Layout.fillWidth: true
                        }
                    }

                    Flow {
                        Layout.preferredWidth: 288
                        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                        spacing: UiTokens.spacing6
                        Repeater {
                            model: [
                                {"label": "Álbumes", "seccion": "albums"},
                                {"label": "Artistas", "seccion": "artistas"},
                                {"label": "Pistas", "seccion": "pistas"}
                            ]
                            delegate: SegmentButton {
                                texto: modelData.label
                                activo: modo_vista === modelData.seccion && !mostrando_detalle
                                onClicked: cambiar_seccion(modelData.seccion)
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: visible ? implicitHeight : 0
                    visible: modo_vista === "albums" && !mostrando_detalle
                    spacing: UiTokens.spacing8

                    LibrarySearchField {
                        id: filtroAlbumsInput
                        Layout.fillWidth: true
                        Layout.preferredHeight: UiTokens.controlHeightMd
                        texto: filtro_albums
                        placeholder: "Buscar por álbum, artista, canción o género"
                        onTextoCambiado: function(nuevoTexto) {
                            if (filtro_albums === nuevoTexto)
                                return
                            filtro_albums = nuevoTexto
                            filtroAlbumsTimer.restart()
                        }
                    }

                    Flow {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(UiTokens.controlHeightSm, childrenRect.height)
                        spacing: UiTokens.spacing6

                        Repeater {
                            model: biblioteca.grupos_albums
                            delegate: PillButton {
                                texto: label + " · " + total
                                activo: grupo_albums === clave
                                onClicked: cambiar_grupo_album(clave)
                            }
                        }
                    }

                    Flow {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(UiTokens.controlHeightSm, childrenRect.height)
                        spacing: UiTokens.spacing6

                        ToolbarLabel { texto: "Orden" }

                        Repeater {
                            model: _opcionesOrdenAlbums()
                            delegate: PillButton {
                                texto: modelData.label
                                iconSource: modelData.icon
                                activo: orden_albums === modelData.valor
                                onClicked: cambiar_orden_albums(modelData.valor)
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: visible ? implicitHeight : 0
                    visible: modo_vista === "artistas" && !mostrando_detalle
                    spacing: UiTokens.spacing8

                    LibrarySearchField {
                        id: filtroArtistasInput
                        Layout.fillWidth: true
                        Layout.preferredHeight: UiTokens.controlHeightMd
                        texto: filtro_artistas
                        placeholder: "Buscar por artista, canción, álbum o género"
                        onTextoCambiado: function(nuevoTexto) {
                            if (filtro_artistas === nuevoTexto)
                                return
                            filtro_artistas = nuevoTexto
                            filtroArtistasTimer.restart()
                        }
                    }

                    Flow {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(UiTokens.controlHeightSm, childrenRect.height)
                        spacing: UiTokens.spacing6

                        ToolbarLabel { texto: "Orden" }

                        Repeater {
                            model: _opcionesOrdenArtistas()
                            delegate: PillButton {
                                texto: modelData.label
                                iconSource: modelData.icon
                                activo: orden_artistas === modelData.valor
                                onClicked: cambiar_orden_artistas(modelData.valor)
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: visible ? implicitHeight : 0
                    visible: modo_vista === "pistas" && !mostrando_detalle
                    spacing: UiTokens.spacing8

                    LibrarySearchField {
                        id: filtroPistasInput
                        Layout.fillWidth: true
                        Layout.preferredHeight: UiTokens.controlHeightMd
                        texto: filtro_pistas
                        placeholder: "Buscar por pista, artista, álbum o género"
                        onTextoCambiado: function(nuevoTexto) {
                            if (filtro_pistas === nuevoTexto)
                                return
                            filtro_pistas = nuevoTexto
                            filtroTimer.restart()
                        }
                    }

                    Flow {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(UiTokens.controlHeightSm, childrenRect.height)
                        spacing: UiTokens.spacing6

                        PillButton {
                            texto: "Favoritas"
                            activo: solo_favoritas
                            iconSource: "../assets/icons/favorite.svg"
                            onClicked: {
                                solo_favoritas = !solo_favoritas
                                filtrar_pistas()
                            }
                        }
                    }

                    Flow {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(UiTokens.controlHeightSm, childrenRect.height)
                        spacing: UiTokens.spacing6

                        ToolbarLabel { texto: "Orden" }

                        Repeater {
                            model: _opcionesOrdenPistas()
                            delegate: PillButton {
                                texto: modelData.label
                                iconSource: modelData.icon
                                activo: orden_pistas === modelData.valor
                                onClicked: cambiar_orden_pistas(modelData.valor)
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: tema.borde
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            VistaDetalleAlbum {
                anchors.fill: parent
                visible: detalle_abierto
                opacity: detalle_abierto ? 1.0 : 0.0
                shell: raiz.shell
                datos_album: album_activo || {}
                onVolver: cerrar_detalle_album()
                onFavoritaToggled: function(pista) { alternar_favorita_pista(pista) }
                Behavior on opacity { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }
            }

            Rectangle {
                anchors.fill: parent
                color: tema.fondo
                visible: detalle_artista_abierto
                opacity: detalle_artista_abierto ? 1.0 : 0.0
                Behavior on opacity { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }

                ScrollView {
                    id: artistaDetalleScroll
                    anchors.fill: parent
                    contentWidth: availableWidth
                    contentHeight: artistaDetalleContenido.implicitHeight
                    clip: true
                    ScrollBar.vertical: LibraryScrollBar {
                        parent: artistaDetalleScroll.parent
                        anchors.top: artistaDetalleScroll.top
                        anchors.right: parent.right
                        anchors.bottom: artistaDetalleScroll.bottom
                        z: 20
                        policy: artistaDetalleContenido.implicitHeight > artistaDetalleScroll.height + 2 ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
                    }

                    ColumnLayout {
                        id: artistaDetalleContenido
                        width: parent.width
                        spacing: UiTokens.spacing16

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.leftMargin: raiz.margen_lateral
                            Layout.rightMargin: raiz.margen_lateral
                            Layout.topMargin: UiTokens.spacing20
                            spacing: UiTokens.spacing20

                            BackButton {
                                onClicked: volver_biblioteca()
                            }

                            PortadaArtista {
                                Layout.preferredWidth: 112
                                Layout.preferredHeight: 112
                                avatarRuta: _portadaUi(artista_activo)
                                nombreArtista: artista_activo && artista_activo.nombre ? artista_activo.nombre : ""
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                spacing: UiTokens.spacing8

                                AppText {
                                    text: artista_activo ? (artista_activo.nombre || "") : ""
                                    color: tema.texto
                                    font.pixelSize: 30
                                    font.bold: true
                                    wrapMode: Text.WordWrap
                                    maximumLineCount: 2
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                AppText {
                                    text: artista_activo
                                          ? [
                                                (artista_activo.num_albums || 0) + " álbumes",
                                                (artista_activo.num_pistas || 0) + " pistas",
                                                reproductor.formatear_duracion_larga(artista_activo.duracion_total_seg || 0)
                                            ].join(" · ")
                                          : ""
                                    color: tema.textoSec
                                    font.pixelSize: UiTokens.fontSizeBase
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }
                                Flow {
                                    Layout.fillWidth: true
                                    spacing: UiTokens.spacing8
                                    LibraryActionButton {
                                        primary: true
                                        texto: "Reproducir todas las pistas del artista"
                                        iconSource: "../assets/icons/play.svg"
                                        enabled: artista_activo && (artista_activo.pistas || []).length > 0
                                        onClicked: if (artista_activo) reproductor.reproducir_cola_desde_pistas(artista_activo.pistas || [], 0)
                                    }
                                    LibraryActionButton {
                                        texto: "Añadir todas las canciones a la cola"
                                        iconSource: "../assets/icons/queue-play.svg"
                                        enabled: artista_activo && (artista_activo.pistas || []).length > 0
                                        onClicked: {
                                            if (!artista_activo) return
                                            var pistas = artista_activo.pistas || []
                                            for (var i = 0; i < pistas.length; ++i)
                                                reproductor.agregar_a_cola(pistas[i])
                                            if (pistas.length > 0)
                                                mostrar_toast("Artista agregado a la cola")
                                        }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.leftMargin: raiz.margen_lateral
                            Layout.rightMargin: raiz.margen_lateral
                            height: 1
                            color: tema.borde
                        }

                        AppText {
                            Layout.leftMargin: raiz.margen_lateral
                            text: "Discografía"
                            color: tema.texto
                            font.pixelSize: UiTokens.fontSizeXl
                            font.weight: Font.DemiBold
                        }

                        Repeater {
                            model: artista_activo ? (artista_activo.albums || []) : []
                            delegate: Rectangle {
                                Layout.fillWidth: true
                                Layout.leftMargin: raiz.margen_lateral
                                Layout.rightMargin: raiz.margen_lateral
                                height: 78
                                radius: UiTokens.radiusSm
                                color: albumArtistaHover.containsMouse ? tema.hover : tema.superficie
                                border.color: albumArtistaHover.containsMouse ? tema.acento : tema.borde
                                border.width: 1

                                MouseArea {
                                    id: albumArtistaHover
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    scrollGestureEnabled: false
                                    cursorShape: Qt.PointingHandCursor
                                    onPressed: desenfocar_busqueda()
                                    onClicked: abrir_album_id(modelData.id)
                                    acceptedButtons: Qt.LeftButton
                                }

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: UiTokens.spacing10
                                    spacing: UiTokens.spacing12

                                    PortadaAlbum {
                                        Layout.preferredWidth: 48
                                        Layout.preferredHeight: 48
                                        portadaRuta: _portadaUi(modelData)
                                        titulo: modelData.titulo || ""
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 0
                                        spacing: UiTokens.spacing2
                                        AppText { text: modelData.titulo || ""; color: tema.texto; font.pixelSize: UiTokens.fontSizeLg; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                                        AppText { text: _textoMetaAlbum(modelData); color: tema.textoSec; font.pixelSize: UiTokens.fontSizeMd; Layout.fillWidth: true; elide: Text.ElideRight }
                                    }

                                }
                            }
                        }

                        EmptyState {
                            Layout.fillWidth: true
                            Layout.leftMargin: raiz.margen_lateral
                            Layout.rightMargin: raiz.margen_lateral
                            visible: artista_activo && (artista_activo.albums || []).length === 0
                            tema: raiz.tema
                            title: "Sin discografía visible"
                            description: "Este artista todavía no tiene álbumes en biblioteca."
                            iconSource: "../assets/icons/library.svg"
                        }

                        AppText {
                            Layout.leftMargin: raiz.margen_lateral
                            Layout.topMargin: UiTokens.spacing4
                            text: "Pistas destacadas"
                            color: tema.texto
                            font.pixelSize: UiTokens.fontSizeXl
                            font.weight: Font.DemiBold
                            visible: artista_activo && (artista_activo.pistas_destacadas || []).length > 0
                        }

                        LibraryHeaderRow {
                            Layout.fillWidth: true
                            Layout.leftMargin: raiz.margen_lateral
                            Layout.rightMargin: raiz.margen_lateral
                            visible: artista_activo && (artista_activo.pistas_destacadas || []).length > 0
                            mostrarFavorito: true
                            mostrarArtista: false
                            accionesWidth: raiz.acciones_pistas_ancho
                            mostrarAlbum: raiz.mostrar_columna_album
                        }

                        Repeater {
                            model: artista_activo ? (artista_activo.pistas_destacadas || []) : []
                            delegate: PistaFila {
                                Layout.fillWidth: true
                                Layout.leftMargin: raiz.margen_lateral
                                Layout.rightMargin: raiz.margen_lateral
                                pista: modelData
                                indiceVisible: index + 1
                                mostrarFavorito: true
                                mostrarBotonArtista: false
                                accionesWidth: raiz.acciones_pistas_ancho
                                mostrarAlbum: raiz.mostrar_columna_album
                            }
                        }

                        Item { Layout.fillWidth: true; height: UiTokens.spacing32 }
                    }
                }
            }

            Item {
                anchors.fill: parent
                visible: !mostrando_detalle
                opacity: !mostrando_detalle ? 1.0 : 0.0
                Behavior on opacity { NumberAnimation { duration: UiTokens.durationBase; easing.type: Easing.OutQuad } }

                GridView {
                    id: albumGrid
                    anchors.fill: parent
                    anchors.leftMargin: raiz.margen_lateral
                    anchors.rightMargin: raiz.margen_lateral
                    anchors.topMargin: UiTokens.spacing16
                    anchors.bottomMargin: UiTokens.spacing16
                    visible: modo_vista === "albums"
                    clip: true
                    reuseItems: true
                    cacheBuffer: 720
                    model: biblioteca.albums
                    property int anchoObjetivo: width < 740 ? 154 : (width < 1020 ? 188 : 224)
                    property int columnas: Math.max(1, Math.floor(Math.max(1, width) / anchoObjetivo))
                    property int modoTarjeta: cellWidth < 176 ? 0 : (cellWidth < 218 ? 1 : 2)
                    property int margenCelda: modoTarjeta === 0 ? UiTokens.spacing4 : UiTokens.spacing6
                    property int paddingTarjeta: modoTarjeta === 0 ? UiTokens.spacing8 : UiTokens.spacing10
                    property int portadaSize: Math.max(96, cellWidth - (margenCelda * 2) - (paddingTarjeta * 2))
                    cellWidth: Math.floor(Math.max(1, width) / columnas)
                    cellHeight: modoTarjeta === 0
                                ? cellWidth
                                : (modoTarjeta === 1 ? cellWidth + 74 : cellWidth + 138)
                    onMovementEnded: _programar_guardado()
                    LibraryScrollBar {
                        parent: albumGrid.parent
                        flickable: albumGrid
                        anchors.top: albumGrid.top
                        anchors.right: parent.right
                        anchors.bottom: albumGrid.bottom
                        z: 20
                        policy: albumGrid.visible && albumGrid.contentHeight > albumGrid.height + 2 ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
                    }

                    delegate: Item {
                        property var albumData: biblioteca.albums.obtener(index)
                        width: albumGrid.cellWidth
                        height: albumGrid.cellHeight

                        Rectangle {
                            id: albumCard
                            anchors.fill: parent
                            anchors.margins: albumGrid.margenCelda
                            radius: UiTokens.radiusSm
                            color: albumHover.containsMouse ? tema.hover : tema.superficie
                            border.color: albumHover.containsMouse ? tema.acento : tema.borde
                            border.width: 1
                            clip: true

                            MouseArea {
                                id: albumHover
                                anchors.fill: parent
                                hoverEnabled: true
                                scrollGestureEnabled: false
                                cursorShape: Qt.PointingHandCursor
                                onPressed: desenfocar_busqueda()
                                onClicked: abrir_album_id(albumData.id)
                            }

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: albumGrid.paddingTarjeta
                                spacing: albumGrid.modoTarjeta === 0 ? 0 : UiTokens.spacing6

                                PortadaAlbum {
                                    Layout.alignment: Qt.AlignHCenter
                                    Layout.preferredWidth: albumGrid.portadaSize
                                    Layout.preferredHeight: albumGrid.portadaSize
                                    portadaRuta: _portadaUi(albumData)
                                    titulo: albumData.titulo || ""
                                }

                                AppText {
                                    visible: albumGrid.modoTarjeta >= 1
                                    text: albumData.titulo || ""
                                    color: tema.texto
                                    font.pixelSize: UiTokens.fontSizeLg
                                    font.bold: true
                                    maximumLineCount: albumGrid.modoTarjeta === 1 ? 2 : 3
                                    wrapMode: Text.WordWrap
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                AppText {
                                    visible: albumGrid.modoTarjeta >= 1
                                    text: albumData.artista_nombre || ""
                                    color: tema.textoSec
                                    font.pixelSize: UiTokens.fontSizeMd
                                    maximumLineCount: 2
                                    wrapMode: Text.WordWrap
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                AppText {
                                    visible: albumGrid.modoTarjeta >= 2
                                    text: _textoMetaAlbum({
                                        "tipo": albumData.tipo,
                                        "anio": albumData.anio,
                                        "num_pistas": albumData.num_pistas,
                                        "duracion_total_seg": albumData.duracion_total_seg
                                    })
                                    color: tema.textoMuted
                                    font.pixelSize: UiTokens.fontSizeSm
                                    maximumLineCount: 1
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }

                            }
                        }
                    }

                    footer: Item { width: 1; height: UiTokens.spacing16 }
                }

                GridView {
                    id: artistGrid
                    anchors.fill: parent
                    anchors.leftMargin: raiz.margen_lateral
                    anchors.rightMargin: raiz.margen_lateral
                    anchors.topMargin: UiTokens.spacing16
                    anchors.bottomMargin: UiTokens.spacing16
                    visible: modo_vista === "artistas"
                    clip: true
                    reuseItems: true
                    cacheBuffer: 680
                    model: biblioteca.artistas
                    property int columnas: Math.max(1, Math.floor(Math.max(1, width) / 288))
                    cellWidth: Math.max(260, Math.floor(Math.max(1, width) / columnas))
                    cellHeight: 132
                    onMovementEnded: _programar_guardado()
                    Component.onCompleted: if (modo_vista === "artistas") biblioteca.cargar_artistas(filtro_artistas, orden_artistas)
                    LibraryScrollBar {
                        parent: artistGrid.parent
                        flickable: artistGrid
                        anchors.top: artistGrid.top
                        anchors.right: parent.right
                        anchors.bottom: artistGrid.bottom
                        z: 20
                        policy: artistGrid.visible && artistGrid.contentHeight > artistGrid.height + 2 ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
                    }

                    delegate: Item {
                        property var artistData: biblioteca.artistas.obtener(index)
                        width: artistGrid.cellWidth
                        height: artistGrid.cellHeight

                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: UiTokens.spacing6
                            radius: UiTokens.radiusSm
                            color: artistHover.containsMouse ? tema.hover : tema.superficie
                            border.color: artistHover.containsMouse ? tema.acento : tema.borde
                            border.width: 1
                            clip: true

                            MouseArea {
                                id: artistHover
                                anchors.fill: parent
                                hoverEnabled: true
                                scrollGestureEnabled: false
                                cursorShape: Qt.PointingHandCursor
                                onPressed: desenfocar_busqueda()
                                onClicked: abrir_artista_id(artistData.id)
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: UiTokens.spacing12
                                spacing: UiTokens.spacing12

                                PortadaArtista {
                                    Layout.preferredWidth: 62
                                    Layout.preferredHeight: 62
                                    avatarRuta: _portadaUi(artistData)
                                    nombreArtista: artistData.nombre || ""
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 0
                                    spacing: UiTokens.spacing4
                                    AppText {
                                        text: artistData.nombre || ""
                                        color: tema.texto
                                        font.pixelSize: 15
                                        font.bold: true
                                        maximumLineCount: 2
                                        wrapMode: Text.WordWrap
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }
                                    AppText {
                                        text: (artistData.num_albums || 0) + " álbumes · " + (artistData.num_pistas || 0) + " pistas"
                                        color: tema.textoSec
                                        font.pixelSize: UiTokens.fontSizeMd
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                    }
                                    AppText {
                                        text: reproductor.formatear_duracion_larga(artistData.duracion_total_seg || 0)
                                        color: tema.textoMuted
                                        font.pixelSize: UiTokens.fontSizeSm
                                        Layout.fillWidth: true
                                    }
                                }
                            }
                        }
                    }
                }

                ListView {
                    id: trackList
                    anchors.fill: parent
                    anchors.leftMargin: raiz.margen_lateral
                    anchors.rightMargin: raiz.margen_lateral
                    anchors.topMargin: UiTokens.spacing12
                    anchors.bottomMargin: UiTokens.spacing16
                    visible: modo_vista === "pistas"
                    clip: true
                    reuseItems: true
                    cacheBuffer: 900
                    spacing: UiTokens.spacing4
                    model: biblioteca.pistas
                    onMovementEnded: _programar_guardado()
                    LibraryScrollBar {
                        parent: trackList.parent
                        flickable: trackList
                        anchors.top: trackList.top
                        anchors.right: parent.right
                        anchors.bottom: trackList.bottom
                        z: 20
                        policy: trackList.visible && trackList.contentHeight > trackList.height + 2 ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
                    }

                    header: LibraryHeaderRow {
                        width: trackList.width
                        mostrarFavorito: true
                        mostrarArtista: true
                        accionesWidth: raiz.acciones_pistas_ancho
                        mostrarAlbum: raiz.mostrar_columna_album
                        z: 2
                    }

                    delegate: PistaFila {
                        width: trackList.width
                        pista: biblioteca.pistas.obtener(index)
                        indiceVisible: index + 1
                        mostrarFavorito: true
                        mostrarBotonArtista: true
                        accionesWidth: raiz.acciones_pistas_ancho
                        mostrarAlbum: raiz.mostrar_columna_album
                    }
                }

                EmptyState {
                    anchors.centerIn: parent
                    tema: raiz.tema
                    visible: modo_vista === "albums" && biblioteca.albums.total === 0
                    title: filtro_albums !== "" ? "Sin resultados" : (biblioteca.grupos_albums.total === 0 ? "Biblioteca vacía" : "Sin álbumes en esta categoría")
                    description: filtro_albums !== "" ? "Ajusta la búsqueda para volver a ver álbumes." : (biblioteca.grupos_albums.total === 0 ? "Importa música para poblar tu biblioteca." : "Cambia de categoría o importa más música.")
                    iconSource: "../assets/icons/library.svg"
                }

                EmptyState {
                    anchors.centerIn: parent
                    tema: raiz.tema
                    visible: modo_vista === "artistas" && biblioteca.artistas.total === 0
                    title: filtro_artistas !== "" ? "Sin resultados" : "Sin artistas"
                    description: filtro_artistas !== "" ? "Ajusta la búsqueda para volver a ver artistas." : "Los artistas aparecerán automáticamente al importar música."
                    iconSource: "../assets/icons/artist.svg"
                }

                EmptyState {
                    anchors.centerIn: parent
                    tema: raiz.tema
                    visible: modo_vista === "pistas" && biblioteca.pistas.total === 0
                    title: filtro_pistas !== "" || solo_favoritas ? "Sin resultados" : "Sin pistas"
                    description: filtro_pistas !== "" || solo_favoritas ? "Ajusta los filtros para volver a ver pistas." : "No hay pistas cargadas todavía."
                    iconSource: "../assets/icons/search.svg"
                }
            }
        }
    }

    Timer {
        id: filtroAlbumsTimer
        interval: 220
        repeat: false
        onTriggered: filtrar_albums()
    }

    Timer {
        id: filtroArtistasTimer
        interval: 220
        repeat: false
        onTriggered: filtrar_artistas()
    }

    Timer {
        id: filtroTimer
        interval: 220
        repeat: false
        onTriggered: filtrar_pistas()
    }

    Timer {
        id: guardarEstadoTimer
        interval: 260
        repeat: false
        onTriggered: _guardar_estado_actual()
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

    component SegmentButton: Rectangle {
        id: segment
        property string texto: ""
        property bool activo: false
        signal clicked()
        width: Math.max(88, label.implicitWidth + 24)
        height: UiTokens.controlHeightMd
        radius: UiTokens.radiusSm
        color: activo ? tema.seleccion : (segmentMouse.containsMouse ? tema.hover : "transparent")
        border.color: activo ? tema.acento : tema.borde
        border.width: 1
        AppText {
            id: label
            anchors.centerIn: parent
            text: segment.texto
            color: segment.activo ? tema.texto : tema.textoSec
            font.pixelSize: UiTokens.fontSizeMd
            font.weight: segment.activo ? Font.DemiBold : Font.Normal
        }
        MouseArea {
            id: segmentMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onPressed: desenfocar_busqueda()
            onClicked: segment.clicked()
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

    component LibraryScrollBar: ScrollBar {
        id: scrollBar
        property var flickable: null
        readonly property real _maxContentY: flickable ? Math.max(0, flickable.contentHeight - flickable.height) : 0
        readonly property real _trackRange: Math.max(0, 1 - size)
        interactive: true
        hoverEnabled: true
        enabled: visible
        active: visible
        orientation: Qt.Vertical
        minimumSize: 0.08
        width: 10
        padding: UiTokens.spacing2
        visible: policy !== ScrollBar.AlwaysOff

        Binding {
            target: scrollBar
            property: "size"
            when: scrollBar.flickable !== null
            value: scrollBar.flickable
                   ? Math.max(scrollBar.minimumSize, Math.min(1, scrollBar.flickable.visibleArea.heightRatio))
                   : 1
        }

        Binding {
            target: scrollBar
            property: "position"
            when: scrollBar.flickable !== null && !scrollBar.pressed
            value: scrollBar.flickable
                   ? Math.max(0, Math.min(scrollBar._trackRange, (scrollBar.flickable.contentY / Math.max(1, scrollBar._maxContentY)) * scrollBar._trackRange))
                   : 0
        }

        onPositionChanged: {
            if (!pressed || !flickable || _maxContentY <= 0)
                return
            var ratio = _trackRange > 0 ? position / _trackRange : 0
            flickable.contentY = Math.max(0, Math.min(_maxContentY, ratio * _maxContentY))
        }

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

    component PillButton: Rectangle {
        id: pill
        property string texto: ""
        property bool activo: false
        property string iconSource: ""
        signal clicked()
        width: Math.max(76, pillRow.implicitWidth + 20)
        height: UiTokens.controlHeightSm
        radius: UiTokens.radiusPill
        color: activo ? tema.seleccion
                      : (pillMouse.containsMouse ? tema.hover : "transparent")
        border.color: activo ? tema.acento : tema.borde
        border.width: 1

        Row {
            id: pillRow
            anchors.centerIn: parent
            spacing: UiTokens.spacing6
            ThemedIcon {
                visible: pill.iconSource !== ""
                width: 13
                height: 13
                source: pill.iconSource
                iconColor: pill.activo ? tema.acento : (pillMouse.containsMouse ? tema.texto : tema.textoSec)
                anchors.verticalCenter: parent.verticalCenter
            }
            AppText {
                text: pill.texto
                color: pill.activo ? tema.texto : (pillMouse.containsMouse ? tema.texto : tema.textoSec)
                font.pixelSize: UiTokens.fontSizeSm
                font.weight: pill.activo ? Font.DemiBold : Font.Normal
                anchors.verticalCenter: parent.verticalCenter
            }
        }
        MouseArea {
            id: pillMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onPressed: desenfocar_busqueda()
            onClicked: pill.clicked()
        }
    }

    component LibrarySearchField: Rectangle {
        id: buscador
        property string texto: ""
        property string placeholder: "Buscar"
        signal textoCambiado(string texto)
        radius: UiTokens.radiusPill
        color: searchInput.activeFocus ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.08) : tema.superficie
        border.color: searchInput.activeFocus ? tema.acento : tema.borde
        border.width: 1

        function limpiarFoco() {
            searchInput.deselect()
            searchInput.focus = false
        }

        function contienePuntoRaiz(posicion) {
            var local = buscador.mapFromItem(raiz, posicion.x, posicion.y)
            return local.x >= 0 && local.y >= 0 && local.x <= buscador.width && local.y <= buscador.height
        }

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.IBeamCursor
            onClicked: searchInput.forceActiveFocus(Qt.MouseFocusReason)
        }

        ThemedIcon {
            id: searchIcon
            anchors.left: parent.left
            anchors.leftMargin: UiTokens.spacing12
            anchors.verticalCenter: parent.verticalCenter
            width: 16
            height: 16
            source: "../assets/icons/search.svg"
            iconColor: tema.textoMuted
            iconOpacity: 0.82
        }

        TextInput {
            id: searchInput
            anchors.left: searchIcon.right
            anchors.leftMargin: UiTokens.spacing8
            anchors.right: clearSearch.left
            anchors.rightMargin: UiTokens.spacing8
            anchors.verticalCenter: parent.verticalCenter
            text: buscador.texto
            selectByMouse: true
            activeFocusOnPress: true
            color: tema.texto
            selectionColor: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.35)
            selectedTextColor: tema.texto
            font.pixelSize: UiTokens.fontSizeBase
            clip: true
            onTextChanged: {
                if (buscador.texto !== text)
                    buscador.textoCambiado(text)
            }
        }

        AppText {
            anchors.left: searchInput.left
            anchors.right: searchInput.right
            anchors.verticalCenter: parent.verticalCenter
            text: buscador.placeholder
            color: tema.textoMuted
            font.pixelSize: UiTokens.fontSizeBase
            elide: Text.ElideRight
            visible: searchInput.text.length === 0 && !searchInput.activeFocus
        }

        IconButton {
            id: clearSearch
            anchors.right: parent.right
            anchors.rightMargin: UiTokens.spacing4
            anchors.verticalCenter: parent.verticalCenter
            width: UiTokens.controlHeightSm
            height: UiTokens.controlHeightSm
            iconSource: "../assets/icons/close.svg"
            visible: searchInput.text.length > 0
            onClicked: {
                searchInput.text = ""
                buscador.textoCambiado("")
                searchInput.forceActiveFocus()
            }
        }
    }

    component IconButton: Rectangle {
        id: boton
        property string iconSource: ""
        property bool primary: false
        // Color del icono. Por defecto sigue el estado (primario/hover); se puede
        // sobreescribir (p. ej. rojo para acciones destructivas como eliminar).
        property color iconColor: boton.primary ? tema.fondo : (botonMouse.containsMouse ? tema.texto : tema.textoSec)
        signal clicked()
        width: UiTokens.controlHeightMd
        height: UiTokens.controlHeightMd
        radius: UiTokens.radiusSm
        opacity: enabled ? 1.0 : 0.45
        color: !enabled ? tema.borde : (primary ? (botonMouse.containsMouse ? tema.acentoFuerte : tema.acento) : (botonMouse.containsMouse ? tema.hover : "transparent"))
        border.color: primary || !enabled ? "transparent" : tema.borde
        border.width: primary || !enabled ? 0 : 1

        ThemedIcon {
            anchors.centerIn: parent
            width: 17
            height: 17
            source: boton.iconSource
            iconColor: boton.iconColor
        }
        MouseArea {
            id: botonMouse
            anchors.fill: parent
            hoverEnabled: true
            enabled: boton.enabled
            cursorShape: boton.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onPressed: desenfocar_busqueda()
            onClicked: boton.clicked()
        }
    }

    component BackButton: Rectangle {
        id: backButton
        signal clicked()
        width: UiTokens.controlHeightMd
        height: UiTokens.controlHeightMd
        radius: UiTokens.radiusPill
        color: backMouse.containsMouse ? tema.hover : "transparent"
        border.color: tema.borde
        border.width: 1

        ThemedIcon {
            anchors.centerIn: parent
            width: 16
            height: 16
            source: "../assets/icons/back.svg"
            iconColor: tema.textoSec
        }

        MouseArea {
            id: backMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onPressed: desenfocar_busqueda()
            onClicked: backButton.clicked()
        }
    }

    component LibraryActionButton: Rectangle {
        id: accion
        property string texto: ""
        property string iconSource: ""
        property bool primary: false
        signal clicked()
        width: Math.max(primary ? 116 : 74, accionRow.implicitWidth + 24)
        height: UiTokens.controlHeightMd
        radius: UiTokens.radiusPill
        opacity: enabled ? 1.0 : 0.45
        color: !enabled ? tema.borde
              : (primary ? (accionMouse.containsMouse ? tema.acentoFuerte : tema.acento)
                         : (accionMouse.containsMouse ? tema.hover : "transparent"))
        border.color: primary || !enabled ? "transparent" : tema.borde
        border.width: primary || !enabled ? 0 : 1

        Row {
            id: accionRow
            anchors.centerIn: parent
            spacing: UiTokens.spacing6
            ThemedIcon {
                visible: accion.iconSource !== ""
                width: 15
                height: 15
                source: accion.iconSource
                iconColor: accion.primary ? tema.fondo : (accionMouse.containsMouse ? tema.texto : tema.textoSec)
                anchors.verticalCenter: parent.verticalCenter
            }
            AppText {
                text: accion.texto
                color: accion.primary ? tema.fondo : (accionMouse.containsMouse ? tema.texto : tema.textoSec)
                font.pixelSize: UiTokens.fontSizeMd
                font.weight: Font.DemiBold
                anchors.verticalCenter: parent.verticalCenter
            }
        }
        MouseArea {
            id: accionMouse
            anchors.fill: parent
            hoverEnabled: true
            enabled: accion.enabled
            cursorShape: accion.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onPressed: desenfocar_busqueda()
            onClicked: accion.clicked()
        }
    }

    component FavoriteButton: Rectangle {
        id: favorito
        property bool activo: false
        signal clicked()
        width: UiTokens.controlHeightMd
        height: UiTokens.controlHeightMd
        radius: UiTokens.radiusPill
        color: activo ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.20)
                      : (favMouse.containsMouse ? tema.hover : "transparent")
        border.color: activo ? tema.acento : tema.borde
        border.width: 1

        ThemedIcon {
            anchors.centerIn: parent
            width: 16
            height: 16
            source: favorito.activo ? "../assets/icons/favorite-filled.svg" : "../assets/icons/favorite.svg"
            iconColor: favorito.activo ? tema.acento : tema.textoSec
            iconOpacity: favorito.activo ? 1.0 : 0.72
        }

        MouseArea {
            id: favMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onPressed: desenfocar_busqueda()
            onClicked: favorito.clicked()
        }
    }

    component LibraryHeaderRow: Rectangle {
        id: header
        property bool mostrarFavorito: false
        property bool mostrarArtista: true
        property bool mostrarAlbum: true
        property int accionesWidth: 420
        property string albumLabel: "Álbum"
        height: 36
        radius: UiTokens.radiusSm
        color: tema.superficieAlt
        border.color: tema.borde
        border.width: 1

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: UiTokens.spacing12
            anchors.rightMargin: UiTokens.spacing12
            spacing: UiTokens.spacing8

            AppText {
                text: "#"
                color: tema.textoMuted
                font.pixelSize: UiTokens.fontSizeSm
                font.weight: Font.DemiBold
                Layout.preferredWidth: 34
                horizontalAlignment: Text.AlignHCenter
            }
            Item { Layout.preferredWidth: 42 }
            AppText {
                text: "Pista"
                color: tema.textoMuted
                font.pixelSize: UiTokens.fontSizeSm
                font.weight: Font.DemiBold
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignLeft
            }
            AppText {
                visible: header.mostrarAlbum
                text: header.albumLabel
                color: tema.textoMuted
                font.pixelSize: UiTokens.fontSizeSm
                font.weight: Font.DemiBold
                Layout.preferredWidth: raiz.ancho_columna_album
                horizontalAlignment: Text.AlignLeft
            }
            AppText {
                text: "Duración"
                color: tema.textoMuted
                font.pixelSize: UiTokens.fontSizeSm
                font.weight: Font.DemiBold
                Layout.preferredWidth: 74
                horizontalAlignment: Text.AlignHCenter
            }
            AppText {
                text: "Acciones"
                color: tema.textoMuted
                font.pixelSize: UiTokens.fontSizeSm
                font.weight: Font.DemiBold
                Layout.preferredWidth: header.accionesWidth
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    component PortadaAlbum: Rectangle {
        id: portadaAlbum
        property string portadaRuta: ""
        property string titulo: ""
        radius: UiTokens.radiusSm
        color: albumCover.visible ? "transparent" : tema.superficieAlt
        border.color: albumCover.visible ? "transparent" : tema.borde
        border.width: albumCover.visible ? 0 : 1
        clip: true

        Image {
            id: albumCover
            anchors.fill: parent
            visible: portadaAlbum.portadaRuta !== "" && status !== Image.Error
            source: portadaAlbum.portadaRuta !== "" ? portadaDe(portadaAlbum.portadaRuta) : ""
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            cache: true
            sourceSize.width: Math.max(96, width * 2)
            sourceSize.height: Math.max(96, height * 2)
            smooth: true
        }

        CoverPlaceholder {
            visible: !albumCover.visible
            anchors.fill: parent
            iconSource: "../assets/icons/library.svg"
            circular: false
        }
    }

    component PortadaArtista: Rectangle {
        id: portadaArtista
        property string avatarRuta: ""
        property string nombreArtista: ""
        radius: width / 2
        color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.12)
        border.color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.28)
        border.width: 1
        clip: true

        Image {
            id: artistAvatar
            anchors.fill: parent
            visible: portadaArtista.avatarRuta !== "" && status !== Image.Error
            source: portadaArtista.avatarRuta !== "" ? portadaDe(portadaArtista.avatarRuta) : ""
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            cache: true
            sourceSize.width: Math.max(96, width * 2)
            sourceSize.height: Math.max(96, height * 2)
            smooth: true
        }

        CoverPlaceholder {
            visible: !artistAvatar.visible
            anchors.fill: parent
            iconSource: "../assets/icons/artist.svg"
            circular: true
        }
    }

    component CoverPlaceholder: Item {
        id: coverPlaceholder
        property string iconSource: "../assets/icons/library.svg"
        property bool circular: false

        Rectangle {
            anchors.fill: parent
            radius: coverPlaceholder.circular ? width / 2 : UiTokens.radiusSm
            color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.08)
        }

        Rectangle {
            id: coverPulse
            anchors.centerIn: parent
            width: Math.min(parent.width, parent.height) * 0.72
            height: width
            radius: coverPlaceholder.circular ? width / 2 : UiTokens.radiusSm
            color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.10)
            border.width: 1
            border.color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.22)
            scale: 0.92
            opacity: 0.82

            SequentialAnimation on scale {
                running: coverPlaceholder.visible
                loops: Animation.Infinite
                NumberAnimation { to: 1.0; duration: 1100; easing.type: Easing.InOutQuad }
                NumberAnimation { to: 0.92; duration: 1100; easing.type: Easing.InOutQuad }
            }
            SequentialAnimation on opacity {
                running: coverPlaceholder.visible
                loops: Animation.Infinite
                NumberAnimation { to: 0.52; duration: 1100; easing.type: Easing.InOutQuad }
                NumberAnimation { to: 0.82; duration: 1100; easing.type: Easing.InOutQuad }
            }
        }

        ThemedIcon {
            anchors.centerIn: parent
            width: Math.min(parent.width, parent.height) * 0.30
            height: width
            source: coverPlaceholder.iconSource
            iconColor: tema.acento
            iconOpacity: 0.82
        }
    }

    component PistaFila: Rectangle {
        id: filaPista
        property var pista: ({})
        property int indiceVisible: 0
        property bool mostrarFavorito: true
        property bool mostrarBotonArtista: true
        property bool mostrarAlbum: true
        property int accionesWidth: 420
        readonly property bool accionesCompactas: accionesWidth < 360
        height: 62
        radius: UiTokens.radiusSm
        color: pistaHover.containsMouse ? tema.hover : "transparent"
        border.color: pistaHover.containsMouse ? tema.borde : "transparent"
        border.width: pistaHover.containsMouse ? 1 : 0

        MouseArea {
            id: pistaHover
            anchors.fill: parent
            hoverEnabled: true
            scrollGestureEnabled: false
            cursorShape: Qt.ArrowCursor
            acceptedButtons: Qt.NoButton
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: UiTokens.spacing12
            anchors.rightMargin: UiTokens.spacing12
            spacing: UiTokens.spacing8

            AppText {
                text: String(filaPista.indiceVisible)
                color: tema.textoMuted
                font.pixelSize: UiTokens.fontSizeSm
                Layout.preferredWidth: 34
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }

            PortadaAlbum {
                Layout.preferredWidth: 42
                Layout.preferredHeight: 42
                portadaRuta: _portadaUi(filaPista.pista)
                titulo: filaPista.pista.album_titulo || filaPista.pista.titulo || ""
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: UiTokens.spacing2
                AppText {
                    text: _textoPista(filaPista.pista)
                    color: tema.texto
                    font.pixelSize: UiTokens.fontSizeBase
                    font.weight: Font.DemiBold
                    maximumLineCount: 1
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                AppText {
                    text: _textoMetaPista(filaPista.pista)
                    color: tema.textoSec
                    font.pixelSize: UiTokens.fontSizeSm
                    maximumLineCount: 1
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }

            AppText {
                visible: filaPista.mostrarAlbum
                text: filaPista.pista.album_titulo || ""
                color: tema.textoSec
                font.pixelSize: UiTokens.fontSizeMd
                elide: Text.ElideRight
                maximumLineCount: 1
                Layout.preferredWidth: raiz.ancho_columna_album
                horizontalAlignment: Text.AlignLeft
            }

            AppText {
                text: reproductor.formatear_tiempo(filaPista.pista.duracion_seg || 0)
                color: tema.textoSec
                font.pixelSize: UiTokens.fontSizeMd
                Layout.preferredWidth: 74
                horizontalAlignment: Text.AlignHCenter
            }

            RowLayout {
                Layout.preferredWidth: filaPista.accionesWidth
                spacing: UiTokens.spacing6
                Layout.alignment: Qt.AlignVCenter

                FavoriteButton {
                    visible: filaPista.mostrarFavorito
                    activo: !!(filaPista.pista.favorita)
                    onClicked: alternar_favorita_pista(filaPista.pista)
                }
                IconButton {
                    iconSource: "../assets/icons/more-vertical.svg"
                    onClicked: menuAgregarPlaylist.abrir(filaPista.pista.id, _textoPista(filaPista.pista))
                }
                IconButton {
                    objectName: "biblioteca_pista_eliminar"
                    iconSource: "../assets/icons/trash.svg"
                    iconColor: tema.peligro
                    onClicked: pedir_eliminar_pista(filaPista.pista)
                }
                LibraryActionButton {
                    visible: !filaPista.accionesCompactas
                    primary: true
                    texto: "Reproducir"
                    iconSource: "../assets/icons/play.svg"
                    onClicked: reproductor.reproducir(filaPista.pista)
                }
                IconButton {
                    visible: filaPista.accionesCompactas
                    primary: true
                    iconSource: "../assets/icons/play.svg"
                    onClicked: reproductor.reproducir(filaPista.pista)
                }
                LibraryActionButton {
                    visible: !filaPista.accionesCompactas
                    texto: "Añadir a cola"
                    iconSource: "../assets/icons/queue-play.svg"
                    onClicked: {
                        reproductor.agregar_a_cola(filaPista.pista)
                        mostrar_toast("Pista agregada a la cola")
                    }
                }
                IconButton {
                    visible: filaPista.accionesCompactas
                    iconSource: "../assets/icons/queue-play.svg"
                    onClicked: {
                        reproductor.agregar_a_cola(filaPista.pista)
                        mostrar_toast("Pista agregada a la cola")
                    }
                }
                LibraryActionButton {
                    visible: !filaPista.accionesCompactas
                    texto: "Abrir álbum"
                    enabled: !!(filaPista.pista.album_id || filaPista.pista.album_titulo)
                    onClicked: abrir_album_desde_pista(filaPista.pista)
                }
                IconButton {
                    visible: filaPista.accionesCompactas
                    iconSource: "../assets/icons/library.svg"
                    enabled: !!(filaPista.pista.album_id || filaPista.pista.album_titulo)
                    onClicked: abrir_album_desde_pista(filaPista.pista)
                }
                LibraryActionButton {
                    visible: filaPista.mostrarBotonArtista && !filaPista.accionesCompactas
                    texto: "Abrir artista"
                    enabled: !!(filaPista.pista.artista_id || filaPista.pista.artista_nombre)
                    onClicked: abrir_artista_desde_pista(filaPista.pista)
                }
                IconButton {
                    visible: filaPista.mostrarBotonArtista && filaPista.accionesCompactas
                    iconSource: "../assets/icons/artist.svg"
                    enabled: !!(filaPista.pista.artista_id || filaPista.pista.artista_nombre)
                    onClicked: abrir_artista_desde_pista(filaPista.pista)
                }
            }
        }
    }

    Component.onCompleted: _restaurar_estado_inicial()

    Connections {
        target: biblioteca
        function onAlbumDetalleActivo() { album_activo = biblioteca.album_detalle }
        function onArtistaDetalleActivo() { artista_activo = biblioteca.artista_detalle }
        function onGruposAlbumsCargados() {
            _asegurar_grupo_album_valido()
            if (modo_vista === "albums" && !detalle_abierto)
                biblioteca.cargar_albums_por_grupo(grupo_albums, orden_albums, filtro_albums)
        }
    }

    MenuAgregarPlaylist {
        id: menuAgregarPlaylist
        tema: raiz.tema
        onGuardado: function(mensaje) { mostrar_toast(mensaje) }
    }

    // ─── Confirmación de eliminación definitiva de una pista ──────────────────
    Popup {
        id: dialogoEliminarPista
        objectName: "biblioteca_dialogo_eliminar"
        parent: Overlay.overlay
        modal: true
        dim: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        width: Math.min(480, raiz.width - UiTokens.spacing32)
        x: Math.round((((parent ? parent.width : raiz.width) - width) / 2))
        y: Math.round((((parent ? parent.height : raiz.height) - height) / 2))
        padding: 0

        readonly property string _titulo: (raiz._pistaPendienteEliminar && raiz._pistaPendienteEliminar.titulo)
            ? raiz._pistaPendienteEliminar.titulo : "esta canción"

        background: Rectangle {
            color: tema.fondoElevado
            radius: UiTokens.radiusLg
            border.color: Qt.rgba(tema.peligro.r, tema.peligro.g, tema.peligro.b, 0.45)
            border.width: 1
        }

        contentItem: ColumnLayout {
            spacing: UiTokens.spacing16
            // padding interno
            Item { Layout.preferredHeight: UiTokens.spacing4 }

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: UiTokens.spacing20
                Layout.rightMargin: UiTokens.spacing20
                spacing: UiTokens.spacing12
                Rectangle {
                    width: 36; height: 36; radius: 18
                    color: Qt.rgba(tema.peligro.r, tema.peligro.g, tema.peligro.b, 0.14)
                    ThemedIcon {
                        anchors.centerIn: parent
                        width: 18; height: 18
                        source: "../assets/icons/trash.svg"
                        iconColor: tema.peligro
                    }
                }
                AppText {
                    Layout.fillWidth: true
                    text: "Eliminar canción"
                    color: tema.texto
                    font.pixelSize: UiTokens.fontSizeXl
                    font.bold: true
                    wrapMode: Text.WordWrap
                }
            }

            AppText {
                Layout.fillWidth: true
                Layout.leftMargin: UiTokens.spacing20
                Layout.rightMargin: UiTokens.spacing20
                text: "Vas a eliminar «" + dialogoEliminarPista._titulo + "» de forma permanente."
                color: tema.texto
                font.pixelSize: UiTokens.fontSizeBase
                wrapMode: Text.WordWrap
            }
            AppText {
                Layout.fillWidth: true
                Layout.leftMargin: UiTokens.spacing20
                Layout.rightMargin: UiTokens.spacing20
                text: "Se borrarán su archivo de audio, sus datos, letras y carátulas propias, "
                      + "y desaparecerá de la biblioteca, las playlists y las sesiones de DJ. "
                      + "Las carátulas o fotos de artista compartidas con otras canciones se conservan. "
                      + "Esta acción no se puede deshacer."
                color: tema.textoMuted
                font.pixelSize: UiTokens.fontSizeSm
                wrapMode: Text.WordWrap
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: UiTokens.spacing20
                Layout.rightMargin: UiTokens.spacing20
                Layout.bottomMargin: UiTokens.spacing20
                spacing: UiTokens.spacing10
                Item { Layout.fillWidth: true }
                LibraryActionButton {
                    texto: "Cancelar"
                    onClicked: dialogoEliminarPista.close()
                }
                // Botón destructivo (rojo) — distinto del primario de acento.
                Rectangle {
                    id: botonEliminarDef
                    objectName: "biblioteca_eliminar_confirmar"
                    Layout.preferredHeight: 36
                    implicitWidth: filaEliminar.implicitWidth + UiTokens.spacing24
                    radius: UiTokens.radiusSm
                    color: eliminarMa.containsMouse
                        ? Qt.darker(tema.peligro, 1.12) : tema.peligro
                    Behavior on color { ColorAnimation { duration: 150 } }
                    RowLayout {
                        id: filaEliminar
                        anchors.centerIn: parent
                        spacing: UiTokens.spacing6
                        AppText {
                            text: "Eliminar"
                            color: UiUtils.contrasteSobre(tema.peligro)
                            font.pixelSize: UiTokens.fontSizeBase
                            font.weight: Font.DemiBold
                        }
                    }
                    MouseArea {
                        id: eliminarMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            var pista = raiz._pistaPendienteEliminar
                            dialogoEliminarPista.close()
                            if (pista && pista.id)
                                biblioteca.eliminar_pista(pista.id)
                        }
                    }
                }
            }
        }
    }
}
