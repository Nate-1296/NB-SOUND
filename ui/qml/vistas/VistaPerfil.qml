import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Dialogs
import Qt5Compat.GraphicalEffects
import "../componentes"
import "../componentes/UiUtils.js" as UiUtils

Rectangle {
    id: raiz
    color: tema.fondo
    clip: false

    // ─── shell / tema ────────────────────────────────────────────────────────
    property var shell: null
    readonly property var tema: shell ? shell.tema : temaUi

    // ─── breakpoints ─────────────────────────────────────────────────────────
    readonly property bool esCompacta: width < 1120
    readonly property bool esMovil:    width < 760
    readonly property int  paddingH:   esMovil ? UiTokens.spacing20 : (esCompacta ? 28 : 36)
    readonly property int  separacion: esMovil ? UiTokens.spacing24 : UiTokens.spacing32
    readonly property int  columnasTops:   esMovil ? 1 : (esCompacta ? 2 : 3)
    readonly property int  columnasProbar: esMovil ? 1 : (esCompacta ? 2 : (width > 1360 ? 4 : 3))
    // 12 canciones para grids de 4/3/2/1 columnas sin huecos
    readonly property int  maxProbar: esMovil ? 4 : (esCompacta ? 6 : 12)

    // ─── datos de usuario (reactivos vía Connections) ─────────────────────────
    property string nombreUsuario: ""
    property string fotoRuta:      ""

    // ─── estado de paginación ────────────────────────────────────────────────
    property int probarOffset: 0

    // ─── estadísticas extras ─────────────────────────────────────────────────
    readonly property bool hayBiblioteca: (estadisticas.resumen.total_pistas || 0) > 0
    readonly property var  extrasP:           estadisticas.estadisticas_perfil || {}
    readonly property bool hayHistorial:      (extrasP.total_escuchas || 0) > 0
    readonly property bool animaciones:       configuracion.obtener("animaciones_habilitadas") !== "0"
    readonly property int  diasActivos:        extrasP.dias_activos_30d           || 0
    readonly property string anioMasEsc:       extrasP.anio_mas_escuchado         || ""
    readonly property var  actividadMes:       extrasP.actividad_mes              || {}
    readonly property int  totalEscuchas:      extrasP.total_escuchas             || 0
    readonly property int  pistasEscuchadas:   extrasP.pistas_distintas_escuchadas  || 0
    readonly property int  artistasEscuchados: extrasP.artistas_distintos_escuchados || 0
    readonly property int  albumsEscuchados:   extrasP.albums_distintos_escuchados  || 0
    readonly property real tiempoEscuchado:    extrasP.tiempo_escuchado_seg       || 0.0

    // Géneros de hoy sin vacíos ni "desconocido"
    // Géneros de hoy (ya filtrados sin vacíos en el backend)
    readonly property var generosHoyFiltrados: extrasP.generos_hoy || []
    // Artistas de hoy — fallback cuando no hay géneros disponibles
    readonly property var artistasHoy:    extrasP.artistas_hoy || []
    readonly property int totalEscuchasHoy: extrasP.total_escuchas_hoy || 0
    readonly property bool hayMoodHoy: generosHoyFiltrados.length > 0 || totalEscuchasHoy > 0
    readonly property int totalGenHoy: {
        var s = 0
        for (var i = 0; i < generosHoyFiltrados.length; i++) s += (generosHoyFiltrados[i].n || 0)
        return Math.max(s, 1)
    }

    // Hábito secundario: usa "jamás escuchadas" o, como fallback, "menos escuchadas"
    readonly property bool usarFallbackMenos: estadisticas.pistas_nunca_escuchadas.total === 0
    readonly property var  modeloHabitoSecundario: usarFallbackMenos
        ? estadisticas.pistas_menos_escuchadas : estadisticas.pistas_nunca_escuchadas
    readonly property string tituloHabitoSecundario: usarFallbackMenos
        ? "Menos escuchadas" : "Jamás escuchadas"

    // Solo pistas para "Probar"
    readonly property var pistasProbar: {
        var out = []
        var total = estadisticas.recomendaciones_inicio.total
        for (var i = 0; i < total; i++) {
            var item = estadisticas.recomendaciones_inicio.obtener(i) || {}
            if (item.tipo === "pista" || (!item.tipo && (item.ruta_archivo || "") !== ""))
                out.push(item)
        }
        return out
    }

    // ─── helpers ─────────────────────────────────────────────────────────────
    function _horaPico() {
        var h = extrasP.hora_pico
        if (h === null || h === undefined || h === "") return "—"
        var hora = parseInt(h)
        if (isNaN(hora) || hora < 0 || hora > 23) return "—"
        var sufijo = hora >= 12 ? "p.m." : "a.m."
        var h12 = hora % 12; if (h12 === 0) h12 = 12
        return h12 + ":00 " + sufijo
    }

    function _iniciales(nombre) {
        if (!nombre || !nombre.trim()) return ""
        var partes = nombre.trim().toUpperCase().split(/\s+/)
        if (partes.length >= 2) return partes[0][0] + partes[1][0]
        return partes[0].substring(0, Math.min(2, partes[0].length))
    }

    function _portada(item) {
        if (!item) return ""
        var ruta = item.portada_display_ruta || item.portada_thumb_ruta || item.portada_ruta || ""
        return ruta ? UiUtils.toMediaSource(ruta) : ""
    }

    function _subtitulo(item) {
        if (!item) return ""
        if (item.subtitulo) return item.subtitulo
        var tipo = item.tipo || "pista"
        if (tipo === "artista") return (item.num_pistas || 0) > 0 ? (item.num_pistas + " pistas") : ""
        if (tipo === "album")   return item.artista_nombre || ""
        var partes = []
        if (item.artista_nombre) partes.push(item.artista_nombre)
        if (item.album_titulo && item.album_titulo !== item.artista_nombre) partes.push(item.album_titulo)
        return partes.join(" · ")
    }

    function _nActividad(dia) {
        // actividad_mes llega con claves STRING (backend garantizado desde biblioteca.py)
        // Acceso por String(dia) es la forma correcta; int también funciona como fallback
        var v = actividadMes[String(dia)]
        if (v === undefined || v === null) v = actividadMes[dia]
        var n = (v !== undefined && v !== null) ? parseInt(v) : 0
        return isNaN(n) ? 0 : n
    }

    function _duracionLegible(seg) {
        var s = Math.floor(Math.max(0, seg || 0))
        if (s === 0) return "0 min"
        var dias = Math.floor(s / 86400)
        var hrs  = Math.floor((s % 86400) / 3600)
        var mins = Math.floor((s % 3600) / 60)
        if (dias > 0) return dias + "d " + hrs + "h"
        if (hrs > 0)  return hrs + "h " + mins + "m"
        return mins + " min"
    }

    function _guardarNombre(nombre) {
        var limpio = nombre.trim()
        if (limpio !== raiz.nombreUsuario) {
            configuracion.guardar("nombre_usuario", limpio)
            raiz.nombreUsuario = limpio
            estadisticas.actualizar_saludo(limpio)
        }
    }

    function _abrirItemTop(item, tipo) {
        if (!item) return
        var t = tipo || item.tipo || "pista"
        if (t === "artista") {
            var aid = parseInt(item.id || item.artista_id || 0)
            if (aid && raiz.shell && raiz.shell.abrir_artista_desde_detalle)
                raiz.shell.abrir_artista_desde_detalle(aid)
        } else if (t === "album") {
            var alid = parseInt(item.id || item.album_id || 0)
            if (alid && raiz.shell && raiz.shell.abrir_album_desde_detalle)
                raiz.shell.abrir_album_desde_detalle(alid)
        } else {
            reproductor.reproducir(item)
        }
    }

    function _reproducirEsencia() {
        var c = estadisticas.mas_escuchadas_canciones
        if (!c || c.total === 0) return
        var pistas = []
        for (var i = 0; i < Math.min(c.total, 25); i++) {
            var p = c.obtener(i); if (p) pistas.push(p)
        }
        if (pistas.length > 0) reproductor.reproducir_cola_desde_pistas(pistas, 0)
    }

    function _reproducirHabito(modelo, limite) {
        if (!modelo || modelo.total === 0) return
        var pistas = []
        for (var i = 0; i < Math.min(modelo.total, limite || 3); i++) {
            var p = modelo.obtener(i); if (p) pistas.push(p)
        }
        _reproducirPistas(pistas)
    }

    // Reproduce un array de pistas pasado directamente. Útil cuando el caller
    // ya tiene el snapshot exacto de items a reproducir (evita re-leer modelos
    // que podrían randomizar entre render y click).
    function _reproducirPistas(pistas) {
        if (!pistas || pistas.length === 0) return
        reproductor.reproducir_cola_desde_pistas(pistas, 0)
    }

    function _siguientePaginaProbar() {
        var n = pistasProbar.length
        if (n === 0) return
        probarOffset = (probarOffset + maxProbar) % n
    }

    // ─── Reactivo a cambios de configuración ─────────────────────────────────
    Connections {
        target: configuracion
        function onConfiguracionCambiada() {
            raiz.nombreUsuario = configuracion.obtener("nombre_usuario") || ""
            raiz.fotoRuta      = configuracion.obtener("foto_perfil")     || ""
        }
    }
    Component.onCompleted: {
        raiz.nombreUsuario = configuracion.obtener("nombre_usuario") || ""
        raiz.fotoRuta      = configuracion.obtener("foto_perfil")     || ""
    }

    onVisibleChanged: if (visible) { probarOffset = 0; estadisticas.cargar() }

    // ─── FileDialog — usa QML nativo, sin QWidget (cross-platform) ──────────
    FileDialog {
        id: fotoDialog
        title: "Seleccionar foto de perfil"
        // Filtros compatibles con Linux/macOS/Windows via QtQuick.Dialogs
        nameFilters: ["Imágenes (*.jpg *.jpeg *.png *.bmp *.webp)", "Todos los archivos (*)"]
        onAccepted: {
            // configuracion.guardar_foto_perfil copia el archivo al caché y guarda la ruta interna
            var url = fotoDialog.selectedFile.toString()
            configuracion.guardar_foto_perfil(url)
        }
    }

    // ═════════════════════════════════════════════════════════════════════════
    // SCROLL PRINCIPAL
    // ═════════════════════════════════════════════════════════════════════════
    Flickable {
        id: scroll
        anchors.fill: parent
        contentWidth: width
        contentHeight: contenido.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickDeceleration: 3000; maximumFlickVelocity: 4500
        opacity: raiz.animaciones ? 0 : 1
        Component.onCompleted: { if (raiz.animaciones) entradaAnim.start() }
        ParallelAnimation {
            id: entradaAnim
            NumberAnimation { target: scroll;    property: "opacity"; from: 0; to: 1; duration: 520; easing.type: Easing.OutCubic }
            NumberAnimation { target: contenido; property: "y";       from: 18; to: 0; duration: 640; easing.type: Easing.OutCubic }
        }

        ColumnLayout {
            id: contenido
            width: scroll.width
            spacing: 0

            // ─────────────────────────────────────────────────────────────
            // HERO — 9.2 Cabecera
            // ─────────────────────────────────────────────────────────────
            Item {
                id: heroSection
                Layout.fillWidth: true
                implicitHeight: heroCol.implicitHeight + (raiz.esMovil ? 40 : 56)

                // Fondo con degradados sutiles del tema
                Rectangle {
                    anchors.fill: parent
                    color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.05)
                    Rectangle {
                        anchors.fill: parent
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0.0; color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.10) }
                            GradientStop { position: 0.7; color: "transparent" }
                        }
                    }
                    Rectangle {
                        anchors.fill: parent
                        gradient: Gradient {
                            orientation: Gradient.Vertical
                            GradientStop { position: 0.0; color: Qt.rgba(tema.acento.r * 0.5, tema.acento.g * 0.7, tema.acento.b, 0.07) }
                            GradientStop { position: 1.0; color: "transparent" }
                        }
                    }
                    Rectangle {
                        anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right
                        height: 1; color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.40)
                    }
                }

                ColumnLayout {
                    id: heroCol
                    anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: raiz.paddingH; anchors.rightMargin: raiz.paddingH
                    spacing: 0

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: raiz.esMovil ? UiTokens.spacing16 : UiTokens.spacing24

                        // ── Avatar circular ───────────────────────────────
                        Item {
                            id: avatarZona
                            readonly property int avatarSize: raiz.esMovil ? 88 : (raiz.esCompacta ? 108 : 132)
                            Layout.preferredWidth:  avatarSize
                            Layout.preferredHeight: avatarSize
                            Layout.alignment: Qt.AlignTop

                            // Anillo exterior (gradiente del acento)
                            Rectangle {
                                id: avatarAnillo
                                anchors.fill: parent; radius: width / 2
                                gradient: Gradient {
                                    orientation: Gradient.Vertical
                                    GradientStop { position: 0.0; color: Qt.lighter(tema.acento, 1.15) }
                                    GradientStop { position: 1.0; color: tema.acento }
                                }

                                // Círculo interior — OpacityMask garantiza recorte circular real
                                Item {
                                    id: avatarInner
                                    anchors.fill: parent; anchors.margins: 3

                                    // Fondo oscuro (siempre visible detrás de iniciales)
                                    Rectangle {
                                        anchors.fill: parent; radius: width / 2
                                        color: tema.fondoElevado
                                    }

                                    // Iniciales cuando no hay foto
                                    Text {
                                        anchors.centerIn: parent
                                        text: raiz._iniciales(raiz.nombreUsuario)
                                        font.pixelSize: raiz.esMovil ? 24 : (raiz.esCompacta ? 32 : 44)
                                        font.weight: Font.Medium; color: tema.acento
                                        visible: raiz.fotoRuta === "" && raiz._iniciales(raiz.nombreUsuario) !== ""
                                    }

                                    // Imagen fuente para la máscara (oculta — la usa OpacityMask)
                                    Image {
                                        id: avatarImgSrc
                                        anchors.fill: parent
                                        source: raiz.fotoRuta ? UiUtils.toMediaSource(raiz.fotoRuta) : ""
                                        fillMode: Image.PreserveAspectCrop
                                        smooth: true; cache: false
                                        visible: false
                                        layer.enabled: true
                                    }

                                    // Máscara circular
                                    Rectangle {
                                        id: avatarCircleMask
                                        anchors.fill: avatarImgSrc
                                        radius: width / 2
                                        color: "white"
                                        visible: false
                                        layer.enabled: true
                                    }

                                    // Foto recortada al círculo mediante OpacityMask
                                    OpacityMask {
                                        anchors.fill: avatarImgSrc
                                        source: avatarImgSrc
                                        maskSource: avatarCircleMask
                                        visible: avatarImgSrc.source !== "" && avatarImgSrc.status === Image.Ready
                                    }
                                }

                                // Overlay de hover — Rectangle con radius pinta círculo (esquinas transparentes)
                                Rectangle {
                                    anchors.fill: avatarInner
                                    radius: width / 2
                                    color: UiUtils.veloOscuro(0.68)
                                    opacity: avatarMouse.containsMouse ? 1 : 0
                                    Behavior on opacity { NumberAnimation { duration: UiTokens.durationFast } }
                                    ColumnLayout {
                                        anchors.centerIn: parent; spacing: 3
                                        ThemedIcon { Layout.alignment: Qt.AlignHCenter; width: 18; height: 18; source: "../assets/icons/edit.svg"; iconColor: tema.textoInmersivo }
                                        Text { Layout.alignment: Qt.AlignHCenter; text: "Cambiar"; font.pixelSize: 9; color: tema.textoInmersivo }
                                    }
                                }
                            }

                            // Dot "escuchando ahora"
                            Rectangle {
                                anchors.right: parent.right; anchors.bottom: parent.bottom
                                anchors.rightMargin: UiTokens.spacing4; anchors.bottomMargin: UiTokens.spacing4
                                width: raiz.esMovil ? 13 : 16; height: width; radius: width / 2
                                color: tema.acento; border.color: tema.fondo; border.width: 3
                                visible: reproductor.reproduciendo
                                SequentialAnimation on opacity {
                                    running: reproductor.reproduciendo; loops: Animation.Infinite
                                    NumberAnimation { to: 0.3; duration: 900; easing.type: Easing.InOutSine }
                                    NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutSine }
                                }
                            }

                            // Botón × para eliminar la foto de perfil
                            Rectangle {
                                id: btnEliminarFoto
                                anchors.right: avatarAnillo.right
                                anchors.top:   avatarAnillo.top
                                anchors.rightMargin: 1; anchors.topMargin: 1
                                width: 22; height: 22; radius: 11; z: 10
                                color: tema.fondoElevado
                                border.color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.70)
                                border.width: 1
                                visible: raiz.fotoRuta !== ""
                                opacity: xMouse.containsMouse ? 1.0 : 0.80
                                Behavior on opacity { NumberAnimation { duration: UiTokens.durationFast } }
                                ThemedIcon {
                                    anchors.centerIn: parent; width: 10; height: 10
                                    source: "../assets/icons/close.svg"; iconColor: tema.textoSec
                                }
                                MouseArea {
                                    id: xMouse; anchors.fill: parent
                                    hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        configuracion.guardar("foto_perfil", "")
                                    }
                                }
                            }

                            MouseArea {
                                id: avatarMouse; anchors.fill: parent
                                hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: fotoDialog.open()
                            }
                        }

                        // ── Bloque de identidad ────────────────────────────
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: UiTokens.spacing8

                            // Eyebrow
                            Row {
                                spacing: UiTokens.spacing8
                                Rectangle { width: 6; height: 6; radius: 3; color: tema.acento; anchors.verticalCenter: parent.verticalCenter }
                                AppText { text: "TU IDENTIDAD MUSICAL"; font.pixelSize: UiTokens.fontSizeXs; font.letterSpacing: 1.8; color: tema.textoSec }
                            }

                            // ── Nombre editable inline ────────────────────
                            Item {
                                id: nombreArea
                                Layout.fillWidth: true
                                implicitHeight: nombreRow.implicitHeight + UiTokens.spacing4
                                property bool hovered: nombreMouse.containsMouse || nombreTE.activeFocus

                                // Fondo hover/foco
                                Rectangle {
                                    anchors.fill: parent; anchors.margins: -UiTokens.spacing8
                                    radius: UiTokens.radiusMd
                                    color: nombreArea.hovered && !nombreTE.activeFocus
                                        ? Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.14) : "transparent"
                                    border.color: nombreTE.activeFocus
                                        ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.30) : "transparent"
                                    border.width: 1
                                    Behavior on color       { ColorAnimation { duration: UiTokens.durationFast } }
                                    Behavior on border.color { ColorAnimation { duration: UiTokens.durationFast } }
                                }

                                RowLayout {
                                    id: nombreRow
                                    anchors.left: parent.left; anchors.right: parent.right
                                    spacing: UiTokens.spacing6

                                    TextEdit {
                                        id: nombreTE
                                        Layout.fillWidth: true
                                        font.pixelSize: raiz.esMovil ? 24 : (raiz.esCompacta ? 30 : Math.min(48, Math.max(28, Math.floor(raiz.width * 0.030))))
                                        font.weight: Font.Medium
                                        wrapMode: TextEdit.Wrap
                                        selectByMouse: true
                                        selectionColor: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.28)
                                        selectedTextColor: tema.texto
                                        color: text.trim() !== "" ? tema.texto : tema.textoSec

                                        // Sincronización reactiva: solo cuando no está editando
                                        Binding {
                                            target: nombreTE; property: "text"
                                            value: raiz.nombreUsuario
                                            when: !nombreTE.activeFocus
                                            restoreMode: Binding.RestoreNone
                                        }

                                        // Placeholder cuando vacío y sin foco
                                        Text {
                                            anchors.fill: parent
                                            text: "¿Cómo te llamas?"
                                            font: parent.font; color: tema.textoSec
                                            visible: parent.text.trim() === "" && !parent.activeFocus
                                        }

                                        Keys.onReturnPressed:  { raiz._guardarNombre(text); focus = false }
                                        Keys.onEscapePressed:  { focus = false }  // restaura via Binding
                                        onActiveFocusChanged:  { if (!activeFocus) raiz._guardarNombre(text) }
                                    }

                                    // Lápiz junto al nombre, solo en hover
                                    ThemedIcon {
                                        Layout.alignment: Qt.AlignVCenter
                                        width: 14; height: 14
                                        source: "../assets/icons/edit.svg"
                                        iconColor: tema.textoMuted
                                        opacity: nombreArea.hovered && !nombreTE.activeFocus ? 0.65 : 0
                                        Behavior on opacity { NumberAnimation { duration: UiTokens.durationFast } }
                                    }
                                }

                                // MouseArea para hover y clic fuera del texto
                                MouseArea {
                                    id: nombreMouse; anchors.fill: parent
                                    hoverEnabled: true; cursorShape: Qt.IBeamCursor
                                    propagateComposedEvents: true
                                    onClicked: function(mouse) {
                                        if (!nombreTE.activeFocus) nombreTE.forceActiveFocus()
                                        mouse.accepted = false
                                    }
                                }
                            }

                            // Descripción
                            AppText {
                                visible: !nombreTE.activeFocus
                                text: {
                                    if (!raiz.hayHistorial && !raiz.hayBiblioteca)
                                        return "Importa música y empieza a escuchar para ver tu identidad musical."
                                    if (!raiz.hayHistorial)
                                        return (estadisticas.resumen.total_pistas || 0).toLocaleString() + " pistas esperando sonar. Tu historia empieza en la primera reproducción."
                                    return totalEscuchas.toLocaleString() + " reproducciones · " + pistasEscuchadas.toLocaleString() + " pistas distintas de " + (estadisticas.resumen.total_pistas || 0).toLocaleString() + " en biblioteca."
                                }
                                font.pixelSize: raiz.esMovil ? 12 : 14; color: tema.textoSec
                                wrapMode: Text.Wrap; maximumLineCount: 3; Layout.fillWidth: true
                            }

                            // Tags de identidad
                            Flow {
                                Layout.fillWidth: true; spacing: UiTokens.spacing6
                                visible: raiz.hayHistorial && !nombreTE.activeFocus
                                TagChip { visible: raiz.anioMasEsc !== "";    texto: "Año favorito: " + raiz.anioMasEsc; colorDestaque: true }
                                TagChip { visible: raiz._horaPico() !== "—";  texto: "Hora pico: " + raiz._horaPico() }
                                TagChip { visible: raiz.diasActivos > 0;      texto: raiz.diasActivos + (raiz.diasActivos === 1 ? " día activo" : " días activos") + " este mes" }
                            }

                            // Acciones
                            Row {
                                spacing: UiTokens.spacing8; Layout.topMargin: UiTokens.spacing4
                                visible: !nombreTE.activeFocus
                                PBButton { texto: "Reproducir tu esencia"; iconSource: "../assets/icons/play.svg"; activo: raiz.hayHistorial; onClicked: raiz._reproducirEsencia() }
                                GBButton { texto: "Actualizar"; iconSource: "../assets/icons/sync.svg"; onClicked: { probarOffset = 0; estadisticas.cargar() } }
                            }
                        }
                    }
                }
            }

            // ─────────────────────────────────────────────────────────────
            // ESTADO VACÍO — sin biblioteca
            // ─────────────────────────────────────────────────────────────
            Item {
                Layout.fillWidth: true
                Layout.leftMargin: raiz.paddingH; Layout.rightMargin: raiz.paddingH
                Layout.topMargin: raiz.separacion; Layout.bottomMargin: raiz.separacion
                visible: !raiz.hayBiblioteca
                implicitHeight: visible ? vacioBox.implicitHeight + UiTokens.spacing32 : 0

                Rectangle {
                    id: vacioBox; width: parent.width
                    implicitHeight: vacioCols.implicitHeight + UiTokens.spacing32
                    radius: UiTokens.radiusLg; color: tema.modoBoxFondo
                    border.color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.55); border.width: 1
                    ColumnLayout {
                        id: vacioCols; anchors.centerIn: parent; width: parent.width - UiTokens.spacing32; spacing: UiTokens.spacing12
                        Rectangle {
                            Layout.alignment: Qt.AlignHCenter; width: 52; height: 52; radius: 26
                            color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.12)
                            border.color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.28); border.width: 1
                            ThemedIcon { anchors.centerIn: parent; width: 24; height: 24; source: "../assets/icons/import.svg"; iconColor: tema.acento }
                        }
                        AppText { text: "Tu perfil musical crece con tu biblioteca"; font.pixelSize: raiz.esMovil ? 16 : 19; font.weight: Font.Bold; color: tema.texto; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        AppText { text: "Importa música para ver estadísticas, tops, actividad mensual y sugerencias de tu propia colección."; font.pixelSize: UiTokens.fontSizeBase; color: tema.textoSec; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true; wrapMode: Text.Wrap; maximumLineCount: 3 }
                        PBButton { Layout.alignment: Qt.AlignHCenter; texto: "Importar música"; iconSource: "../assets/icons/import.svg"; onClicked: if (shell) shell.vista_activa = "importacion" }
                    }
                }
            }

            // ─────────────────────────────────────────────────────────────
            // RESUMEN — 9.3  estadísticas + mood + actividad
            // ─────────────────────────────────────────────────────────────
            ColumnLayout {
                Layout.fillWidth: true
                Layout.leftMargin: raiz.paddingH; Layout.rightMargin: raiz.paddingH
                Layout.topMargin: raiz.separacion; Layout.bottomMargin: raiz.separacion
                spacing: raiz.esMovil ? UiTokens.spacing16 : UiTokens.spacing20
                visible: raiz.hayBiblioteca

                SecTitulo {
                    titulo: "Tu actividad"
                    subtitulo: raiz.hayHistorial ? "Lo que tu historial local dice de ti." : "Aún no hay reproducciones registradas."
                }

                // 4 stats de escucha
                GridLayout {
                    Layout.fillWidth: true; columns: raiz.esMovil ? 2 : 4
                    rowSpacing: UiTokens.spacing10; columnSpacing: UiTokens.spacing10
                    visible: raiz.hayHistorial

                    StatCard { titulo: "Pistas escuchadas";  valor: raiz.pistasEscuchadas.toLocaleString();   iconSource: "../assets/icons/track.svg"  }
                    StatCard { titulo: "Artistas distintos"; valor: raiz.artistasEscuchados.toLocaleString(); iconSource: "../assets/icons/artist.svg" }
                    StatCard { titulo: "Álbumes distintos";  valor: raiz.albumsEscuchados.toLocaleString();   iconSource: "../assets/icons/album.svg"  }
                    StatCard { titulo: "Tiempo escuchado";   valor: raiz._duracionLegible(raiz.tiempoEscuchado); iconSource: "../assets/icons/clock.svg" }
                }

                // Mood del día + Actividad mensual — mismo alto (GridLayout iguala la fila)
                GridLayout {
                    id: moodActGrid
                    Layout.fillWidth: true
                    columns: (raiz.esMovil || raiz.esCompacta) ? 1 : 2
                    rowSpacing: UiTokens.spacing10; columnSpacing: UiTokens.spacing10
                    visible: raiz.hayHistorial

                    // ── MOOD DEL DÍA ──────────────────────────────────────
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true  // ← igual alto que actividad
                        Layout.minimumHeight: moodCol.implicitHeight + UiTokens.spacing32
                        radius: UiTokens.radiusLg; color: tema.modoBoxFondo
                        border.color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.45); border.width: 1
                        Rectangle {
                            anchors.fill: parent; radius: parent.radius
                            gradient: Gradient {
                                orientation: Gradient.Vertical
                                GradientStop { position: 0.0; color: Qt.rgba(tema.acento.r * 0.8, tema.acento.g * 0.5, tema.acento.b * 0.3, 0.13) }
                                GradientStop { position: 1.0; color: "transparent" }
                            }
                        }
                        ColumnLayout {
                            id: moodCol
                            anchors { left: parent.left; right: parent.right; top: parent.top; margins: UiTokens.spacing16 }
                            spacing: UiTokens.spacing10

                            Row {
                                spacing: UiTokens.spacing8
                                Rectangle {
                                    width: 8; height: 8; radius: 4; color: tema.acento
                                    anchors.verticalCenter: parent.verticalCenter
                                    SequentialAnimation on opacity { running: true; loops: Animation.Infinite
                                        NumberAnimation { to: 0.3; duration: 1000; easing.type: Easing.InOutSine }
                                        NumberAnimation { to: 1.0; duration: 1000; easing.type: Easing.InOutSine }
                                    }
                                }
                                AppText { text: "MOOD DEL DÍA"; font.pixelSize: UiTokens.fontSizeXs; font.letterSpacing: 1.6; color: tema.textoSec }
                            }

                            // Título principal del mood: género > artistas > sin escuchas
                            AppText {
                                text: {
                                    if (raiz.generosHoyFiltrados.length > 0) {
                                        var g = raiz.generosHoyFiltrados[0].genero
                                        return g.charAt(0).toUpperCase() + g.slice(1)
                                    }
                                    if (raiz.artistasHoy.length > 0)
                                        return raiz.artistasHoy[0].artista
                                    return "Sin escuchas hoy"
                                }
                                font.pixelSize: raiz.esMovil ? 22 : 28; font.weight: Font.Medium
                                color: tema.texto; wrapMode: Text.Wrap; Layout.fillWidth: true
                            }

                            // Descripción contextual
                            AppText {
                                text: {
                                    if (raiz.generosHoyFiltrados.length > 0)
                                        return "Calculado desde las reproducciones del día."
                                    if (raiz.totalEscuchasHoy > 0)
                                        return raiz.totalEscuchasHoy + " pista" + (raiz.totalEscuchasHoy !== 1 ? "s" : "") + " reproducida" + (raiz.totalEscuchasHoy !== 1 ? "s" : "") + " hoy. Sin datos de género en la biblioteca."
                                    return "Reproduce algo hoy para ver tu mood del día."
                                }
                                font.pixelSize: UiTokens.fontSizeBase; color: tema.textoSec; wrapMode: Text.Wrap; Layout.fillWidth: true
                            }

                            // Chips de géneros (cuando hay datos de género)
                            Flow {
                                Layout.fillWidth: true; spacing: UiTokens.spacing6
                                visible: raiz.generosHoyFiltrados.length > 0
                                Repeater {
                                    model: Math.min(raiz.generosHoyFiltrados.length, 5)
                                    delegate: Rectangle {
                                        property var gd: raiz.generosHoyFiltrados[index] || {}
                                        property int pct: Math.round((gd.n || 0) * 100 / raiz.totalGenHoy)
                                        height: 26; radius: 13
                                        color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.35)
                                        border.color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.55); border.width: 1
                                        implicitWidth: chipGR.implicitWidth + 20
                                        Row { id: chipGR; anchors.centerIn: parent; spacing: UiTokens.spacing4
                                            AppText { text: gd.genero || ""; font.pixelSize: UiTokens.fontSizeSm; color: tema.textoSec }
                                            AppText { text: "· " + pct + "%"; font.pixelSize: UiTokens.fontSizeSm; color: tema.acento }
                                        }
                                    }
                                }
                            }

                            // Chips de artistas (fallback cuando no hay géneros pero sí escuchas)
                            Flow {
                                Layout.fillWidth: true; spacing: UiTokens.spacing6
                                visible: raiz.generosHoyFiltrados.length === 0 && raiz.artistasHoy.length > 0
                                Repeater {
                                    model: Math.min(raiz.artistasHoy.length, 3)
                                    delegate: Rectangle {
                                        property var ad: raiz.artistasHoy[index] || {}
                                        height: 26; radius: 13
                                        color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.35)
                                        border.color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.55); border.width: 1
                                        implicitWidth: chipAR.implicitWidth + 20
                                        Row { id: chipAR; anchors.centerIn: parent; spacing: UiTokens.spacing4
                                            AppText { text: ad.artista || ""; font.pixelSize: UiTokens.fontSizeSm; color: tema.textoSec }
                                            AppText { text: "· " + (ad.n || 0); font.pixelSize: UiTokens.fontSizeSm; color: tema.acento }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // ── ACTIVIDAD DEL MES ─────────────────────────────────
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true  // ← igual alto que mood
                        Layout.minimumHeight: actMesCol.implicitHeight + UiTokens.spacing32
                        radius: UiTokens.radiusLg; color: tema.modoBoxFondo
                        border.color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.45); border.width: 1
                        Rectangle {
                            anchors.fill: parent; radius: parent.radius
                            gradient: Gradient {
                                orientation: Gradient.Vertical
                                GradientStop { position: 0.0; color: Qt.rgba(tema.acento.r * 0.3, tema.acento.g * 0.6, tema.acento.b, 0.10) }
                                GradientStop { position: 1.0; color: "transparent" }
                            }
                        }
                        ColumnLayout {
                            id: actMesCol
                            anchors { left: parent.left; right: parent.right; top: parent.top; margins: UiTokens.spacing16 }
                            spacing: UiTokens.spacing10

                            Row {
                                spacing: UiTokens.spacing8
                                Rectangle {
                                    width: 8; height: 8; radius: 4; color: tema.acento
                                    anchors.verticalCenter: parent.verticalCenter
                                    SequentialAnimation on opacity { running: true; loops: Animation.Infinite
                                        NumberAnimation { to: 0.3; duration: 1000; easing.type: Easing.InOutSine }
                                        NumberAnimation { to: 1.0; duration: 1000; easing.type: Easing.InOutSine }
                                    }
                                }
                                AppText { text: "ACTIVIDAD DEL MES"; font.pixelSize: UiTokens.fontSizeXs; font.letterSpacing: 1.6; color: tema.textoSec }
                            }

                            AppText {
                                text: raiz.diasActivos > 0
                                    ? raiz.diasActivos + (raiz.diasActivos === 1 ? " día activo" : " días activos") + " este mes"
                                    : "Sin actividad registrada este mes"
                                font.pixelSize: raiz.esMovil ? 20 : 24; font.weight: Font.Medium
                                color: tema.texto; wrapMode: Text.Wrap; Layout.fillWidth: true
                            }

                            // Cuadrícula 15 × 3 — cubre los 31 días
                            // Usa opacity en lugar de Qt.rgba() para evitar problemas de color
                            Grid {
                                columns: 15; rows: 3; spacing: UiTokens.spacing4; Layout.fillWidth: true
                                Repeater {
                                    model: 31
                                    delegate: Rectangle {
                                        property int actividad: raiz._nActividad(index + 1)
                                        width: 14; height: 14; radius: 3
                                        color: tema.acento   // color sólido del tema
                                        // opacity varía la intensidad — funciona en todos los temas
                                        opacity: actividad === 0 ? 0.16
                                               : actividad <= 5  ? 0.42
                                               : actividad <= 15 ? 0.72
                                               : 1.0
                                        scale: cellM.containsMouse ? 1.20 : 1.0
                                        Behavior on scale { NumberAnimation { duration: UiTokens.durationFast } }
                                        MouseArea { id: cellM; anchors.fill: parent; hoverEnabled: true }
                                    }
                                }
                            }

                            // Leyenda — mismos niveles de opacidad que las celdas
                            Flow {
                                Layout.fillWidth: true; spacing: UiTokens.spacing10
                                Repeater {
                                    model: [
                                        { label: "Sin escuchas", o: 0.16 },
                                        { label: "1–5",          o: 0.42 },
                                        { label: "6–15",         o: 0.72 },
                                        { label: "16+",          o: 1.00 }
                                    ]
                                    delegate: Row {
                                        spacing: 5
                                        Rectangle {
                                            width: 10; height: 10; radius: 2
                                            color: tema.acento
                                            opacity: modelData.o
                                            anchors.verticalCenter: parent.verticalCenter
                                        }
                                        AppText { text: modelData.label; font.pixelSize: UiTokens.fontSizeXs; color: tema.textoSec }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ─────────────────────────────────────────────────────────────
            // TOPS — 9.4
            // ─────────────────────────────────────────────────────────────
            ColumnLayout {
                Layout.fillWidth: true
                Layout.leftMargin: raiz.paddingH; Layout.rightMargin: raiz.paddingH
                Layout.bottomMargin: raiz.separacion
                spacing: raiz.esMovil ? UiTokens.spacing16 : UiTokens.spacing20
                visible: raiz.hayHistorial

                SeparadorSeccion {}
                SecTitulo { titulo: "Lo que más has querido"; subtitulo: "Tus tops según el historial. Álbum o artista → va a su vista en biblioteca." }

                GridLayout {
                    Layout.fillWidth: true; columns: raiz.columnasTops
                    rowSpacing: UiTokens.spacing10; columnSpacing: UiTokens.spacing10
                    TopCard { titulo: "Top canciones"; modelo: estadisticas.mas_escuchadas_canciones; tipo: "pista";   visible: estadisticas.mas_escuchadas_canciones.total > 0 }
                    TopCard { titulo: "Top álbumes";   modelo: estadisticas.mas_escuchadas_albums;   tipo: "album";   visible: estadisticas.mas_escuchadas_albums.total > 0 }
                    TopCard { titulo: "Top artistas";  modelo: estadisticas.mas_escuchadas_artistas; tipo: "artista"; visible: estadisticas.mas_escuchadas_artistas.total > 0 }
                }
            }

            // ─────────────────────────────────────────────────────────────
            // HÁBITOS — Tus extremos
            // ─────────────────────────────────────────────────────────────
            ColumnLayout {
                Layout.fillWidth: true
                Layout.leftMargin: raiz.paddingH; Layout.rightMargin: raiz.paddingH
                Layout.bottomMargin: raiz.separacion
                spacing: raiz.esMovil ? UiTokens.spacing16 : UiTokens.spacing20
                visible: raiz.hayHistorial || raiz.modeloHabitoSecundario.total > 0

                SeparadorSeccion {}
                SecTitulo { titulo: "Tus extremos"; subtitulo: "Lo que más defines y lo que aún espera sonar." }

                GridLayout {
                    Layout.fillWidth: true; columns: raiz.esMovil ? 1 : 2
                    rowSpacing: UiTokens.spacing10; columnSpacing: UiTokens.spacing10

                    HabitCard {
                        titulo: "Lo que más suena"; modelo: estadisticas.mas_escuchadas_canciones
                        emptyMessage: "Reproduce música para ver cuáles son tus favoritas reales."
                        accionLabel: "Reproducir"; accionVisible: estadisticas.mas_escuchadas_canciones.total > 0
                        onReproducirClicked: function(pistas) { raiz._reproducirPistas(pistas) }
                    }

                    HabitCard {
                        titulo: raiz.tituloHabitoSecundario
                        modelo: raiz.modeloHabitoSecundario
                        emptyMessage: "Todas tus pistas ya han sonado varias veces."
                        accionLabel: "Reproducir"; accionVisible: raiz.modeloHabitoSecundario.total > 0
                        onReproducirClicked: function(pistas) { raiz._reproducirPistas(pistas) }
                    }
                }
            }

            // ─────────────────────────────────────────────────────────────
            // PROBAR — 9.5 — 12 canciones, sin botón de cola
            // ─────────────────────────────────────────────────────────────
            ColumnLayout {
                Layout.fillWidth: true
                Layout.leftMargin: raiz.paddingH; Layout.rightMargin: raiz.paddingH
                Layout.bottomMargin: raiz.separacion
                spacing: raiz.esMovil ? UiTokens.spacing16 : UiTokens.spacing20
                visible: raiz.hayBiblioteca

                SeparadorSeccion {}

                RowLayout {
                    Layout.fillWidth: true; spacing: UiTokens.spacing12
                    SecTitulo { Layout.fillWidth: true; titulo: "Lo que podrías probar"; subtitulo: "Canciones de tu propia biblioteca. Sin servicios externos." }
                    GBButton {
                        texto: "Siguiente"; iconSource: "../assets/icons/shuffle.svg"
                        Layout.alignment: Qt.AlignBottom
                        activo: raiz.pistasProbar.length > raiz.maxProbar
                        onClicked: raiz._siguientePaginaProbar()
                    }
                }

                GridLayout {
                    Layout.fillWidth: true; columns: raiz.columnasProbar
                    rowSpacing: UiTokens.spacing10; columnSpacing: UiTokens.spacing10
                    visible: raiz.pistasProbar.length > 0

                    Repeater {
                        model: Math.min(raiz.maxProbar, raiz.pistasProbar.length)
                        delegate: ProbarCard {
                            required property int index
                            property var itemData: {
                                var n = raiz.pistasProbar.length
                                return n > 0 ? (raiz.pistasProbar[(raiz.probarOffset + index) % n] || {}) : {}
                            }
                            titulo:    itemData.titulo || itemData.nombre_archivo || "—"
                            subtitulo: raiz._subtitulo(itemData)
                            portadaUrl: raiz._portada(itemData)
                            contexto:  itemData.contexto || ""
                            Layout.fillWidth: true
                            onReproducirClicked: reproductor.reproducir(itemData)
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: sinSugC.implicitHeight + UiTokens.spacing24; radius: UiTokens.radiusMd
                    color: tema.modoBoxFondo; border.color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.35); border.width: 1
                    visible: raiz.pistasProbar.length === 0
                    ColumnLayout { id: sinSugC; anchors.centerIn: parent; width: parent.width - UiTokens.spacing32; spacing: UiTokens.spacing8
                        AppText { text: "Sin sugerencias aún"; font.pixelSize: UiTokens.fontSizeLg; font.weight: Font.DemiBold; color: tema.texto; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
                        AppText { text: "Importa más música o reproduce álbumes para recibir sugerencias."; font.pixelSize: UiTokens.fontSizeMd; color: tema.textoSec; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    }
                }
            }

            // Footer
            Item {
                Layout.fillWidth: true
                Layout.leftMargin: raiz.paddingH; Layout.rightMargin: raiz.paddingH
                Layout.topMargin: UiTokens.spacing12; Layout.bottomMargin: UiTokens.spacing8
                implicitHeight: footerC.implicitHeight
                ColumnLayout { id: footerC; width: parent.width; spacing: UiTokens.spacing4
                    AppText { text: "TODO CALCULADO EN LOCAL · NB SOUND NO ENVÍA DATOS A NINGÚN SERVIDOR"; font.pixelSize: UiTokens.fontSizeXs; font.letterSpacing: 0.8; color: tema.textoMuted; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    AppText { visible: raiz.hayBiblioteca; text: (estadisticas.resumen.total_pistas || 0).toLocaleString() + " pistas en biblioteca · " + estadisticas.formatear_duracion_detallada(estadisticas.resumen.duracion_total_seg || 0); font.pixelSize: UiTokens.fontSizeSm; color: tema.textoMuted; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
                }
            }

            Item { Layout.fillWidth: true; Layout.preferredHeight: raiz.esMovil ? UiTokens.spacing24 : UiTokens.spacing32 }
        }
    }

    // Scrollbar
    PerfilScrollBar {
        flickable: scroll
        anchors.top: scroll.top; anchors.right: scroll.right; anchors.bottom: scroll.bottom; z: 20
        policy: scroll.contentHeight > scroll.height + 2 ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
    }

    // ═════════════════════════════════════════════════════════════════════════
    // COMPONENTES INTERNOS
    // ═════════════════════════════════════════════════════════════════════════

    component PerfilScrollBar: ScrollBar {
        id: sb; property var flickable: null
        readonly property real _maxY: flickable ? Math.max(0, flickable.contentHeight - flickable.height) : 0
        readonly property real _tr:   Math.max(0, 1 - size)
        interactive: true; hoverEnabled: true; enabled: visible; active: visible
        orientation: Qt.Vertical; minimumSize: 0.08; width: 10; padding: UiTokens.spacing2
        Binding { target: sb; property: "size"; when: sb.flickable !== null
            value: sb.flickable ? Math.max(sb.minimumSize, Math.min(1, sb.flickable.visibleArea.heightRatio)) : 1 }
        Binding { target: sb; property: "position"; when: sb.flickable !== null && !sb.pressed
            value: sb.flickable ? Math.max(0, Math.min(sb._tr, (sb.flickable.contentY / Math.max(1, sb._maxY)) * sb._tr)) : 0 }
        onPositionChanged: {
            if (!pressed || !flickable || _maxY <= 0) return
            flickable.contentY = Math.max(0, Math.min(_maxY, (_tr > 0 ? position / _tr : 0) * _maxY))
        }
        contentItem: Rectangle { implicitWidth: 6; implicitHeight: 6; radius: width / 2; color: tema.acentoFuerte }
        background: Rectangle { radius: width / 2; color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.20); visible: sb.policy !== ScrollBar.AlwaysOff }
    }

    component ThemedIcon: Item {
        id: ti; property string source: ""; property color iconColor: tema.textoSec; property real iconOpacity: 1.0
        implicitWidth: UiTokens.iconMd; implicitHeight: UiTokens.iconMd
        Image { id: tiSrc; anchors.fill: parent; source: ti.source; sourceSize.width: Math.max(16, parent.width*2); sourceSize.height: Math.max(16, parent.height*2); smooth: true; opacity: 0; visible: ti.source !== "" }
        MultiEffect { anchors.fill: tiSrc; source: tiSrc; colorization: 1.0; colorizationColor: ti.iconColor; opacity: ti.iconOpacity; visible: ti.source !== "" }
    }

    component PBButton: Rectangle {
        id: pb; property string texto: ""; property string iconSource: ""; signal clicked(); property bool activo: true
        implicitWidth: Math.max(130, pbR.implicitWidth + 28); implicitHeight: UiTokens.controlHeightLg; radius: UiTokens.radiusPill
        color: !activo ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.35) : (pbM.containsMouse ? tema.acentoFuerte : tema.acento)
        opacity: activo ? 1 : 0.6; scale: pbM.containsMouse && activo ? 1.025 : 1.0
        Behavior on color { ColorAnimation { duration: UiTokens.durationFast } }
        Behavior on scale { NumberAnimation { duration: UiTokens.durationFast; easing.type: Easing.OutQuad } }
        Row { id: pbR; anchors.centerIn: parent; spacing: UiTokens.spacing8
            ThemedIcon { width: 15; height: 15; anchors.verticalCenter: parent.verticalCenter; source: pb.iconSource; iconColor: tema.fondo }
            AppText { text: pb.texto; anchors.verticalCenter: parent.verticalCenter; color: tema.fondo; font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold }
        }
        MouseArea { id: pbM; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; enabled: pb.activo; onClicked: pb.clicked() }
    }

    component GBButton: Rectangle {
        id: gb; property string texto: ""; property string iconSource: ""; signal clicked(); property bool activo: true
        implicitWidth: Math.max(90, gbR.implicitWidth + 28); implicitHeight: UiTokens.controlHeightLg; radius: UiTokens.radiusPill
        color: gbM.containsMouse ? Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.35) : "transparent"
        border.color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.50); border.width: 1; opacity: activo ? 1 : 0.5
        Behavior on color { ColorAnimation { duration: UiTokens.durationFast } }
        Row { id: gbR; anchors.centerIn: parent; spacing: UiTokens.spacing8
            ThemedIcon { width: 14; height: 14; anchors.verticalCenter: parent.verticalCenter; source: gb.iconSource; iconColor: tema.textoSec }
            AppText { text: gb.texto; anchors.verticalCenter: parent.verticalCenter; color: tema.textoSec; font.pixelSize: UiTokens.fontSizeBase }
        }
        MouseArea { id: gbM; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; enabled: gb.activo; onClicked: gb.clicked() }
    }

    component TagChip: Rectangle {
        id: tc; property string texto: ""; property bool colorDestaque: false
        implicitHeight: 26; radius: 13
        color: colorDestaque ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.12) : Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.35)
        border.color: colorDestaque ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.35) : Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.50)
        border.width: 1; implicitWidth: tcL.implicitWidth + 22
        AppText { id: tcL; anchors.centerIn: parent; text: tc.texto; font.pixelSize: UiTokens.fontSizeSm; color: tc.colorDestaque ? tema.acento : tema.textoSec }
    }

    component SeparadorSeccion: Rectangle {
        Layout.fillWidth: true; height: 1; color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.35)
    }

    component SecTitulo: ColumnLayout {
        property string titulo: ""; property string subtitulo: ""; spacing: UiTokens.spacing4
        AppText { text: titulo; font.pixelSize: raiz.esMovil ? 19 : 23; font.weight: Font.Medium; color: tema.texto; Layout.fillWidth: true; wrapMode: Text.Wrap }
        AppText { text: subtitulo; font.pixelSize: UiTokens.fontSizeMd; color: tema.textoSec; Layout.fillWidth: true; wrapMode: Text.Wrap; visible: subtitulo !== "" }
    }

    component StatCard: Rectangle {
        id: sc; property string titulo: ""; property string valor: ""; property string iconSource: ""
        Layout.fillWidth: true
        implicitHeight: Math.max(raiz.esMovil ? 88 : 96, scC.implicitHeight + UiTokens.spacing20)
        radius: UiTokens.radiusMd; color: tema.modoBoxFondo
        border.color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.45); border.width: 1
        ThemedIcon { anchors.top: parent.top; anchors.right: parent.right; anchors.margins: UiTokens.spacing12; width: 17; height: 17; source: sc.iconSource; iconColor: tema.textoMuted; iconOpacity: 0.65 }
        ColumnLayout {
            id: scC; anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: UiTokens.spacing16; anchors.rightMargin: UiTokens.spacing32; spacing: UiTokens.spacing4
            AppText { text: sc.titulo; font.pixelSize: UiTokens.fontSizeSm; font.letterSpacing: 0.4; color: tema.textoSec; Layout.fillWidth: true }
            AppText { text: sc.valor;  font.pixelSize: raiz.esMovil ? 20 : 24; font.weight: Font.Medium; color: tema.texto; Layout.fillWidth: true; elide: Text.ElideRight }
        }
    }

    component TopCard: Rectangle {
        id: topCard; property string titulo: ""; property var modelo: null; property string tipo: "pista"
        Layout.fillWidth: true
        implicitHeight: tcc.implicitHeight + UiTokens.spacing20
        radius: UiTokens.radiusMd; color: tema.modoBoxFondo
        border.color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.40); border.width: 1
        ColumnLayout {
            id: tcc
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
            anchors.margins: UiTokens.spacing14
            spacing: 0
            AppText { text: topCard.titulo; font.pixelSize: UiTokens.fontSizeMd; font.weight: Font.DemiBold; font.letterSpacing: 0.7; color: tema.textoSec }
            Rectangle { Layout.fillWidth: true; height: 1; color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.38); Layout.topMargin: UiTokens.spacing10; Layout.bottomMargin: UiTokens.spacing4 }
            Repeater {
                model: topCard.modelo ? Math.min(topCard.modelo.total, 5) : 0
                delegate: Item {
                    required property int index
                    property var itemD: topCard.modelo ? (topCard.modelo.obtener(index) || {}) : {}
                    Layout.fillWidth: true; implicitHeight: trL.implicitHeight + UiTokens.spacing8
                    Rectangle { anchors.fill: parent; radius: UiTokens.radiusSm; color: trM.containsMouse ? Qt.rgba(tema.seleccion.r, tema.seleccion.g, tema.seleccion.b, 0.55) : "transparent"; Behavior on color { ColorAnimation { duration: UiTokens.durationFast } } }
                    RowLayout {
                        id: trL
                        anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: UiTokens.spacing6; anchors.rightMargin: UiTokens.spacing6; spacing: UiTokens.spacing8
                        AppText { text: String(index + 1).padStart(2, "0"); font.pixelSize: index === 0 ? 17 : 13; font.weight: index === 0 ? Font.Medium : Font.Normal; color: index === 0 ? tema.acento : tema.textoMuted; Layout.preferredWidth: 24 }
                        Rectangle {
                            Layout.preferredWidth: 38; Layout.preferredHeight: 38
                            radius: topCard.tipo === "artista" ? 19 : UiTokens.radiusSm
                            color: Qt.rgba(tema.seleccion.r, tema.seleccion.g, tema.seleccion.b, 0.50); clip: true; layer.enabled: true
                            Image { anchors.fill: parent; source: raiz._portada(itemD); fillMode: Image.PreserveAspectCrop; smooth: true; visible: source !== "" && status === Image.Ready }
                            AppText {
                                anchors.centerIn: parent
                                text: { var n = itemD.titulo || itemD.nombre || "?"; return n.charAt(0).toUpperCase() }
                                font.pixelSize: UiTokens.fontSizeLg; font.weight: Font.Medium; color: tema.acento
                                visible: raiz._portada(itemD) === ""
                            }
                        }
                        ColumnLayout { Layout.fillWidth: true; spacing: UiTokens.spacing2
                            AppText { text: itemD.titulo || itemD.nombre || "—"; font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.Medium; color: tema.texto; elide: Text.ElideRight; Layout.fillWidth: true }
                            AppText { text: raiz._subtitulo(itemD); font.pixelSize: UiTokens.fontSizeSm; color: tema.textoSec; elide: Text.ElideRight; Layout.fillWidth: true; visible: text !== "" }
                        }
                        ThemedIcon { width: 12; height: 12; source: topCard.tipo !== "pista" ? "../assets/icons/chevron-right.svg" : ""; iconColor: tema.textoMuted; iconOpacity: 0.7; visible: topCard.tipo !== "pista" }
                    }
                    MouseArea { id: trM; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: raiz._abrirItemTop(topCard.modelo ? topCard.modelo.obtener(index) : null, topCard.tipo) }
                }
            }
        }
    }

    component HabitCard: Rectangle {
        id: hc; property string titulo: ""; property var modelo: null
        property string emptyMessage: ""; property string accionLabel: ""; property bool accionVisible: false
        property int maxItems: 3
        signal reproducirClicked(var pistas)

        // Snapshot estable de los items VISIBLES en el card. Se reconstruye
        // cuando el modelo cambia (set_datos o totalCambiado) — garantiza
        // que el botón Reproducir reproduzca EXACTAMENTE lo mostrado.
        property var itemsVisibles: []
        function _recomputarItems() {
            var out = []
            if (modelo && modelo.total > 0) {
                var n = Math.min(modelo.total, maxItems)
                for (var i = 0; i < n; i++) {
                    var p = modelo.obtener(i)
                    if (p) out.push(p)
                }
            }
            itemsVisibles = out
        }
        onModeloChanged: _recomputarItems()
        Connections {
            target: hc.modelo
            ignoreUnknownSignals: true
            function onTotalCambiado() { hc._recomputarItems() }
        }
        Component.onCompleted: _recomputarItems()

        Layout.fillWidth: true; implicitHeight: hcC.implicitHeight + UiTokens.spacing24
        radius: UiTokens.radiusLg; color: tema.modoBoxFondo
        border.color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.40); border.width: 1
        ColumnLayout {
            id: hcC
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
            anchors.margins: UiTokens.spacing16; spacing: UiTokens.spacing12
            AppText { text: hc.titulo; font.pixelSize: UiTokens.fontSizeXl; font.weight: Font.Medium; color: tema.texto; Layout.fillWidth: true }
            ColumnLayout {
                Layout.fillWidth: true; spacing: 0; visible: hc.itemsVisibles.length > 0
                Repeater {
                    model: hc.itemsVisibles.length
                    delegate: Item {
                        required property int index
                        property var itemD: hc.itemsVisibles[index] || {}
                        Layout.fillWidth: true; implicitHeight: hrL.implicitHeight + UiTokens.spacing10
                        Rectangle { anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right; height: 1; color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.28); visible: index > 0 }
                        RowLayout {
                            id: hrL
                            anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: UiTokens.spacing10
                            Rectangle {
                                Layout.preferredWidth: 36; Layout.preferredHeight: 36; radius: UiTokens.radiusSm
                                color: Qt.rgba(tema.seleccion.r, tema.seleccion.g, tema.seleccion.b, 0.45); clip: true; layer.enabled: true
                                Image { anchors.fill: parent; source: raiz._portada(itemD); fillMode: Image.PreserveAspectCrop; smooth: true; visible: source !== "" && status === Image.Ready }
                                AppText { anchors.centerIn: parent; text: (itemD.titulo || itemD.nombre || "?").charAt(0).toUpperCase(); font.pixelSize: UiTokens.fontSizeBase; color: tema.acento; visible: raiz._portada(itemD) === "" }
                            }
                            ColumnLayout { Layout.fillWidth: true; spacing: UiTokens.spacing2
                                AppText { text: itemD.titulo || itemD.nombre || "—"; font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.Medium; color: tema.texto; elide: Text.ElideRight; Layout.fillWidth: true }
                                AppText { text: raiz._subtitulo(itemD); font.pixelSize: UiTokens.fontSizeSm; color: tema.textoSec; elide: Text.ElideRight; Layout.fillWidth: true; visible: text !== "" }
                            }
                        }
                        MouseArea { anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: reproductor.reproducir(itemD) }
                    }
                }
            }
            AppText { visible: hc.itemsVisibles.length === 0; text: hc.emptyMessage; font.pixelSize: UiTokens.fontSizeBase; color: tema.textoSec; wrapMode: Text.Wrap; Layout.fillWidth: true }
            PBButton { visible: hc.accionVisible; texto: hc.accionLabel; iconSource: "../assets/icons/play.svg"; implicitHeight: UiTokens.controlHeightMd; onClicked: hc.reproducirClicked(hc.itemsVisibles) }
        }
    }

    component ProbarCard: Rectangle {
        id: pc; property string titulo: ""; property string subtitulo: ""; property string portadaUrl: ""; property string contexto: ""
        signal reproducirClicked()
        Layout.fillWidth: true; implicitHeight: pcC.implicitHeight + UiTokens.spacing24
        radius: UiTokens.radiusMd; color: tema.modoBoxFondo
        border.color: pcM.containsMouse ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.55) : Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.40)
        border.width: 1; scale: pcM.containsMouse ? 1.010 : 1.0
        Behavior on border.color { ColorAnimation { duration: UiTokens.durationFast } }
        Behavior on scale { NumberAnimation { duration: UiTokens.durationFast; easing.type: Easing.OutQuad } }
        ColumnLayout {
            id: pcC
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
            anchors.margins: UiTokens.spacing14; spacing: UiTokens.spacing8
            Item {
                Layout.fillWidth: true; implicitHeight: width
                Rectangle {
                    anchors.fill: parent; radius: UiTokens.radiusSm
                    color: Qt.rgba(tema.seleccion.r, tema.seleccion.g, tema.seleccion.b, 0.55); clip: true
                    Image { anchors.fill: parent; source: pc.portadaUrl; fillMode: Image.PreserveAspectCrop; smooth: true; visible: source !== "" && status === Image.Ready }
                    Rectangle { anchors.fill: parent; radius: parent.radius; color: UiUtils.veloOscuro(0.28); opacity: pcM.containsMouse ? 1 : 0; Behavior on opacity { NumberAnimation { duration: UiTokens.durationFast } } }
                    Rectangle {
                        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: UiTokens.spacing8
                        width: 34; height: 34; radius: 17; color: tema.acento
                        opacity: pcM.containsMouse ? 1 : 0; scale: pcM.containsMouse ? 1 : 0.7
                        Behavior on opacity { NumberAnimation { duration: UiTokens.durationFast } }
                        Behavior on scale { NumberAnimation { duration: UiTokens.durationFast; easing.type: Easing.OutBack } }
                        ThemedIcon { anchors.centerIn: parent; width: 14; height: 14; source: "../assets/icons/play.svg"; iconColor: tema.fondo }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: pc.reproducirClicked() }
                    }
                }
            }
            AppText { text: pc.contexto || "De tu biblioteca"; font.pixelSize: UiTokens.fontSizeXs; font.letterSpacing: 0.8; color: tema.acento; elide: Text.ElideRight; Layout.fillWidth: true }
            AppText { text: pc.titulo; font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold; color: tema.texto; elide: Text.ElideRight; Layout.fillWidth: true }
            AppText { text: pc.subtitulo; font.pixelSize: UiTokens.fontSizeSm; color: tema.textoSec; elide: Text.ElideRight; Layout.fillWidth: true; visible: text !== "" }
        }
        MouseArea { id: pcM; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: pc.reproducirClicked() }
    }
}
