import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtQuick.Effects
import "../componentes"
import "../componentes/UiUtils.js" as UiUtils

Rectangle {
    id: raiz
    color: "transparent"
    clip: false

    property var shell: null
    readonly property var tema: shell ? shell.tema : temaUi
    property string nombre_usuario: configuracion.obtener("nombre_usuario")
    readonly property bool esCompacta: width < 1120
    readonly property bool esMovil: width < 760
    readonly property int paddingHorizontal: esMovil ? UiTokens.spacing20 : (esCompacta ? 30 : 38)
    readonly property int separacionBloques: esMovil ? UiTokens.spacing24 : UiTokens.spacing32
    readonly property int saludoTamano: esMovil ? 28 : (esCompacta ? 32 : Math.min(52, Math.max(34, Math.floor(raiz.width * 0.038))))
    readonly property bool hayBiblioteca: (estadisticas.resumen.total_pistas || 0) > 0
    readonly property bool animacionesInicio: configuracion.obtener("animaciones_habilitadas") !== "0"
    readonly property int maxVolver: 12
    readonly property int maxTop: 10

    // ── helpers ───────────────────────────────────────────────────────────────

    function abrirItem(itemData, tipoFallback) {
        if (!itemData) return
        var tipoItem = itemData.tipo || tipoFallback || "pista"
        if (tipoItem === "pista" || tipoItem === "cancion") {
            reproductor.reproducir(itemData)
        } else if (tipoItem.indexOf("album") === 0) {
            var albumId = itemData.album_id || itemData.id
            if (albumId && shell && shell.abrir_album_desde_detalle)
                shell.abrir_album_desde_detalle(albumId)
        } else if (tipoItem.indexOf("artista") === 0) {
            var artistaId = itemData.artista_id || itemData.id
            if (artistaId && shell && shell.abrir_artista_desde_detalle)
                shell.abrir_artista_desde_detalle(artistaId)
        } else if (tipoItem.indexOf("playlist") === 0 && shell) {
            var playlistId = itemData.playlist_id || itemData.id
            if (playlistId && shell.abrir_playlist_desde_inicio)
                shell.abrir_playlist_desde_inicio(playlistId)
            else
                shell.vista_activa = "playlists"
        }
    }

    function portadaPrincipal(itemData) {
        if (!itemData) return ""
        if (itemData.portada_display_ruta) return UiUtils.toMediaSource(itemData.portada_display_ruta)
        if (itemData.portada_thumb_ruta)   return UiUtils.toMediaSource(itemData.portada_thumb_ruta)
        if (itemData.portada_ruta)         return UiUtils.toMediaSource(itemData.portada_ruta)
        if (itemData.portadas && itemData.portadas.length > 0) return UiUtils.toMediaSource(itemData.portadas[0])
        return ""
    }

    function tituloItem(itemData, tipoFallback) {
        if (!itemData) return ""
        var tipoItem = itemData.tipo || tipoFallback || "pista"
        if (tipoItem.indexOf("artista") === 0) return itemData.nombre || "Artista"
        if (tipoItem.indexOf("playlist") === 0) return itemData.nombre || "Playlist"
        return itemData.titulo || itemData.nombre_archivo || itemData.nombre || "Sin título"
    }

    function subtituloItem(itemData, tipoFallback) {
        if (!itemData) return ""
        if (itemData.subtitulo) return itemData.subtitulo
        var tipoItem = itemData.tipo || tipoFallback || "pista"
        if (tipoItem === "pista" || tipoItem === "cancion") {
            var partesPista = []
            if (itemData.artista_nombre) partesPista.push(itemData.artista_nombre)
            if (itemData.duracion_seg) partesPista.push(reproductor.formatear_tiempo(itemData.duracion_seg || 0))
            return partesPista.join(" - ")
        }
        if (tipoItem.indexOf("album") === 0) {
            var ar = itemData.artista_nombre || "Artista"
            var np = itemData.num_pistas || 0
            return np > 0 ? (ar + " · " + np + " pistas") : ar
        }
        if (tipoItem.indexOf("artista") === 0) {
            var npa = itemData.num_pistas || 0
            return npa > 0 ? (npa + " pistas") : ""
        }
        if (tipoItem.indexOf("playlist") === 0) {
            var tipo = tipoPlaylistTexto(itemData.tipo_playlist)
            var npp = itemData.num_pistas || 0
            return npp > 0 ? (tipo + " · " + npp + " pistas") : tipo
        }
        return ""
    }

    function tipoPlaylistTexto(tipoPlaylist) {
        var tipo = String(tipoPlaylist || "manual")
        if (tipo === "manual")       return "Lista del usuario"
        if (tipo === "automatica")   return "Lista automática"
        if (tipo === "this_is")      return "Lista de artista"
        if (tipo === "mix_diario")   return "Mix"
        if (tipo === "descubrimiento") return "Descubrimiento"
        if (tipo === "mood")         return "Mood"
        if (tipo === "sistema")      return "Sistema"
        return tipo.replace(/_/g, " ")
    }

    function contextoItem(itemData) {
        if (!itemData) return ""
        if (itemData.contexto) return itemData.contexto
        if ((itemData.reproducciones_total || 0) > 0) return itemData.reproducciones_total + " reproducciones"
        if ((itemData.num_pistas || 0) > 0) return itemData.num_pistas + " pistas"
        if (itemData.anio) return String(itemData.anio)
        return ""
    }

    function iconoTipo(tipoItem) {
        if (tipoItem === "playlist" || tipoItem === "playlist_top") return "../assets/icons/playlist.svg"
        if (tipoItem === "album"    || tipoItem === "album_top")    return "../assets/icons/album.svg"
        if (tipoItem === "artista"  || tipoItem === "artista_top")  return "../assets/icons/artist.svg"
        return "../assets/icons/track.svg"
    }

    // ── outer layout ──────────────────────────────────────────────────────────
    // Use Flickable directly to have full control over scroll position for
    // the custom scrollbar indicator (ScrollView's attached ScrollBar is
    // unreliable across Qt/QML styles and themes).

    Flickable {
        id: inicioScroll
        anchors.fill: parent
        // No right margin — the scrollbar overlays on the right edge (same as VistaBiblioteca)
        contentWidth: width
        contentHeight: inicioContenido.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickDeceleration: 3000
        maximumFlickVelocity: 4500
        opacity: raiz.animacionesInicio ? 0 : 1

        Component.onCompleted: {
            if (raiz.animacionesInicio) entradaAnimacion.start()
        }

        ParallelAnimation {
            id: entradaAnimacion
            NumberAnimation { target: inicioScroll;    property: "opacity"; from: 0; to: 1; duration: 550; easing.type: Easing.OutCubic }
            NumberAnimation { target: inicioContenido; property: "y";       from: 20; to: 0; duration: 650; easing.type: Easing.OutCubic }
        }

        ColumnLayout {
            id: inicioContenido
            width: inicioScroll.width
            spacing: 0

            // ── TOP EQUALIZER (scrolls with content) ──────────────────────────
            InicioEcualizadorBarras {
                Layout.fillWidth: true
                Layout.preferredHeight: raiz.esMovil ? 40 : 46
                modoFooter: false
            }

            // ── HERO ──────────────────────────────────────────────────────
            HeroSeccion {
                    Layout.fillWidth: true
                    Layout.leftMargin:  raiz.paddingHorizontal
                    Layout.rightMargin: raiz.paddingHorizontal
                    Layout.topMargin:   raiz.esMovil ? UiTokens.spacing16 : UiTokens.spacing20
                    Layout.bottomMargin: raiz.separacionBloques
                }

                // ── EMPTY STATE ───────────────────────────────────────────────
                Item {
                    Layout.fillWidth: true
                    Layout.leftMargin:  raiz.paddingHorizontal
                    Layout.rightMargin: raiz.paddingHorizontal
                    Layout.bottomMargin: UiTokens.spacing32
                    height: estadoVacio.implicitHeight
                    visible: (estadisticas.resumen.total_pistas || 0) === 0

                    Rectangle {
                        id: estadoVacio
                        width: parent.width
                        implicitHeight: estadoVacioLayout.implicitHeight + UiTokens.spacing32
                        radius: UiTokens.radiusLg
                        color: Qt.rgba(tema.modoBoxFondo.r, tema.modoBoxFondo.g, tema.modoBoxFondo.b, 0.92)
                        border.color: Qt.rgba(tema.modoBoxBorde.r, tema.modoBoxBorde.g, tema.modoBoxBorde.b, 0.88)
                        border.width: 1

                        RowLayout {
                            id: estadoVacioLayout
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin:  raiz.esMovil ? UiTokens.spacing16 : UiTokens.spacing24
                            anchors.rightMargin: raiz.esMovil ? UiTokens.spacing16 : UiTokens.spacing24
                            spacing: raiz.esMovil ? UiTokens.spacing12 : UiTokens.spacing20

                            Rectangle {
                                Layout.preferredWidth:  raiz.esMovil ? 58 : 72
                                Layout.preferredHeight: raiz.esMovil ? 58 : 72
                                Layout.alignment: Qt.AlignVCenter
                                radius: width / 2
                                color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.10)
                                border.color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.28)
                                border.width: 1
                                ThemedIcon {
                                    anchors.centerIn: parent
                                    width: raiz.esMovil ? 26 : 32; height: width
                                    source: "../assets/icons/import.svg"
                                    iconColor: tema.acento
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: UiTokens.spacing6
                                AppText {
                                    text: "Tu biblioteca empieza al importar música"
                                    font.pixelSize: raiz.esMovil ? 18 : 21
                                    font.bold: true; color: tema.texto
                                    wrapMode: Text.Wrap; Layout.fillWidth: true
                                }
                                AppText {
                                    text: "NB SOUND usará tus archivos locales para mostrar recientes, favoritos y música para retomar sin depender de servicios externos."
                                    font.pixelSize: raiz.esMovil ? 12 : 13
                                    color: tema.textoSec; wrapMode: Text.Wrap
                                    maximumLineCount: 3; Layout.fillWidth: true
                                }
                            }

                            PrimaryButton {
                                Layout.alignment: Qt.AlignVCenter
                                visible: !raiz.esMovil
                                texto: "Importar música"
                                iconSource: "../assets/icons/import.svg"
                                onClicked: if (shell) shell.vista_activa = "importacion"
                            }
                        }
                    }
                }

                PrimaryButton {
                    Layout.leftMargin:  raiz.paddingHorizontal
                    Layout.rightMargin: raiz.paddingHorizontal
                    Layout.bottomMargin: UiTokens.spacing32
                    visible: raiz.esMovil && (estadisticas.resumen.total_pistas || 0) === 0
                    texto: "Importar música"
                    iconSource: "../assets/icons/import.svg"
                    onClicked: if (shell) shell.vista_activa = "importacion"
                }

                // Sugerencia "primero revisa Estado del Sistema": las nuevas
                // instalaciones de NB Sound suelen tener dependencias opcionales
                // (Karaoke, Deep) sin instalar. Si la biblioteca está vacía y
                // hay deps faltantes mostramos un banner para guiar al usuario.
                Rectangle {
                    id: hintEstadoSistema
                    Layout.fillWidth: true
                    Layout.leftMargin:  raiz.paddingHorizontal
                    Layout.rightMargin: raiz.paddingHorizontal
                    Layout.bottomMargin: raiz.separacionBloques
                    visible: !raiz.hayBiblioteca
                             && (typeof dependencias !== "undefined")
                             && (dependencias.faltanRequeridas || dependencias.faltanOpcionales)
                    color: Qt.tint(tema.fondoElevado, Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.10))
                    radius: UiTokens.radiusLg
                    border.color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.45)
                    border.width: 1
                    implicitHeight: hintLayout.implicitHeight + UiTokens.spacing24

                    RowLayout {
                        id: hintLayout
                        anchors.fill: parent
                        anchors.margins: UiTokens.spacing16
                        spacing: UiTokens.spacing16

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: UiTokens.spacing6
                            AppText {
                                text: "Antes de importar, revisa el Estado del Sistema"
                                color: tema.texto
                                font.pixelSize: raiz.esMovil ? 16 : 19
                                font.bold: true
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                            }
                            AppText {
                                text: dependencias.faltanRequeridas
                                    ? "Hay dependencias requeridas sin instalar. Algunas funciones críticas (reproducción, transcodificación) podrían fallar hasta que las instales desde la pantalla de Estado del Sistema."
                                    : "Hay dependencias opcionales sin instalar (Karaoke, análisis profundo, AcoustID). NB Sound puede funcionar sin ellas, pero conviene revisarlas para saber qué tendrás disponible."
                                color: tema.textoSec
                                font.pixelSize: raiz.esMovil ? 12 : 13
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                            }
                        }
                        PrimaryButton {
                            Layout.alignment: Qt.AlignVCenter
                            visible: !raiz.esMovil
                            texto: "Ir a Estado del Sistema"
                            onClicked: if (shell) shell.vista_activa = "estado_sistema"
                        }
                    }
                }

                // ── VUELVE A TU MÚSICA ────────────────────────────────────────
                GridRetornarAsimetrico {
                    Layout.fillWidth: true
                    Layout.leftMargin:  raiz.paddingHorizontal
                    Layout.rightMargin: raiz.paddingHorizontal
                    Layout.bottomMargin: raiz.separacionBloques
                    visible: raiz.hayBiblioteca && estadisticas.para_volver && estadisticas.para_volver.total > 0
                }

                // ── PLAYLISTS DESTACADAS ──────────────────────────────────────
                SeccionCarrusel {
                    titulo:    "Tus playlists destacadas"
                    subtitulo: "Listas que has creado o escuchado más."
                    modelo:    estadisticas.playlists_destacadas
                    tipo:      "playlist"
                    estilo:    "editorial"
                    visible:   raiz.hayBiblioteca && estadisticas.playlists_destacadas && estadisticas.playlists_destacadas.total > 0
                }

                // ── TOP 10 EDITORIAL ──────────────────────────────────────────
                Top10Seccion {
                    Layout.fillWidth: true
                    Layout.leftMargin:  raiz.paddingHorizontal
                    Layout.rightMargin: raiz.paddingHorizontal
                    Layout.bottomMargin: raiz.separacionBloques
                    visible: raiz.hayBiblioteca && estadisticas.mas_escuchadas_canciones && estadisticas.mas_escuchadas_canciones.total > 0
                }

                // ── ÁLBUMES QUE VUELVEN ───────────────────────────────────────
                SeccionCarrusel {
                    titulo:    "Álbumes que vuelven a aparecer"
                    subtitulo: "Discos con canciones favoritas o escuchas frecuentes."
                    modelo:    estadisticas.albums_que_gustan
                    tipo:      "album"
                    estilo:    "editorial"
                    visible:   raiz.hayBiblioteca && estadisticas.albums_que_gustan && estadisticas.albums_que_gustan.total > 0
                }

                // ── ARTISTAS ──────────────────────────────────────────────────
                SeccionCarrusel {
                    titulo:    "Artistas que más suenan"
                    subtitulo: "Los nombres que más aparecen en tu historial."
                    modelo:    estadisticas.mas_escuchadas_artistas
                    tipo:      "artista"
                    estilo:    "ranking"
                    ranking:   true
                    maxItems:  raiz.maxTop
                    visible:   raiz.hayBiblioteca && estadisticas.mas_escuchadas_artistas && estadisticas.mas_escuchadas_artistas.total > 0
                }

                // ── ÚLTIMOS AÑADIDOS ──────────────────────────────────────────
                SeccionCarrusel {
                    titulo:    "Últimos añadidos"
                    subtitulo: "Lo más reciente que entró a tu biblioteca."
                    modelo:    estadisticas.recientes_canciones
                    tipo:      "pista"
                    estilo:    "normal"
                    visible:   raiz.hayBiblioteca && estadisticas.recientes_canciones && estadisticas.recientes_canciones.total > 0
                }

                // ── TOP ÁLBUMES ───────────────────────────────────────────────
                SeccionCarrusel {
                    titulo:    "Tus 10 álbumes más escuchados"
                    subtitulo: "Los discos que más han pasado por reproducción."
                    modelo:    estadisticas.mas_escuchadas_albums
                    tipo:      "album"
                    estilo:    "ranking"
                    ranking:   true
                    maxItems:  raiz.maxTop
                    visible:   raiz.hayBiblioteca && estadisticas.mas_escuchadas_albums && estadisticas.mas_escuchadas_albums.total > 0
                }

                // ── FOOTER ────────────────────────────────────────────────────
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin:  raiz.paddingHorizontal
                    Layout.rightMargin: raiz.paddingHorizontal
                    Layout.topMargin:   UiTokens.spacing16
                    Layout.bottomMargin: UiTokens.spacing12
                    spacing: UiTokens.spacing8

                    InicioEcualizadorBarras {
                        Layout.fillWidth: true
                        Layout.preferredHeight: raiz.esMovil ? 38 : 44
                        modoFooter: true
                    }

                    AppText {
                        visible: raiz.hayBiblioteca
                        text: (estadisticas.resumen.total_pistas || 0).toLocaleString()
                              + " pistas · "
                              + estadisticas.formatear_duracion_detallada(estadisticas.resumen.duracion_total_seg || 0)
                        font.pixelSize: UiTokens.fontSizeSm
                        color: tema.textoMuted
                        horizontalAlignment: Text.AlignHCenter
                        Layout.fillWidth: true
                    }
                }

                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: raiz.esMovil ? UiTokens.spacing24 : UiTokens.spacing32
                }
            }
    }

    // ── Scrollbar — mirrors the LibraryScrollBar pattern from VistaBiblioteca ───
    InicioScrollBar {
        id: scrollbarTrack
        flickable: inicioScroll
        anchors.top:    inicioScroll.top
        anchors.right:  inicioScroll.right
        anchors.bottom: inicioScroll.bottom
        z: 20
        policy: inicioScroll.contentHeight > inicioScroll.height + 2
                ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // INTERNAL COMPONENTS
    // ═══════════════════════════════════════════════════════════════════════════

    // ── Scrollbar component — same pattern and colors as LibraryScrollBar ─────
    component InicioScrollBar: ScrollBar {
        id: sb
        property var flickable: null
        readonly property real _maxContentY:
            flickable ? Math.max(0, flickable.contentHeight - flickable.height) : 0
        readonly property real _trackRange: Math.max(0, 1 - size)

        interactive: true
        hoverEnabled: true
        enabled: visible
        active: visible
        orientation: Qt.Vertical
        minimumSize: 0.08
        width: 10
        padding: UiTokens.spacing2

        Binding {
            target: sb
            property: "size"
            when: sb.flickable !== null
            value: sb.flickable
                   ? Math.max(sb.minimumSize, Math.min(1, sb.flickable.visibleArea.heightRatio))
                   : 1
        }

        Binding {
            target: sb
            property: "position"
            when: sb.flickable !== null && !sb.pressed
            value: sb.flickable
                   ? Math.max(0, Math.min(sb._trackRange,
                         (sb.flickable.contentY / Math.max(1, sb._maxContentY)) * sb._trackRange))
                   : 0
        }

        onPositionChanged: {
            if (!pressed || !flickable || _maxContentY <= 0) return
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
            visible: sb.policy !== ScrollBar.AlwaysOff
        }
    }

    // ── Equalizer bars (top and footer — identical style, different bar count) ──
    component InicioEcualizadorBarras: Item {
        property bool modoFooter: false

        readonly property int barCount:   modoFooter ? 26 : 48
        readonly property int barSpacing: modoFooter ? 6  : 3
        readonly property real barW: barContainer.width > 0
            ? Math.max(3, (barContainer.width - (barCount - 1) * barSpacing) / barCount)
            : 4

        Item {
            id: barContainer
            anchors.fill: parent
            anchors.leftMargin:   UiTokens.spacing12
            anchors.rightMargin:  UiTokens.spacing12
            anchors.bottomMargin: UiTokens.spacing4

            Row {
                id: barRow
                anchors.fill: parent
                spacing: barSpacing

                Repeater {
                    model: barCount
                    delegate: Item {
                        id: barDel
                        width:  barW
                        height: barRow.height - 4
                        // Initial level varies per bar so they don't all start at 0
                        property real nivel: 0.15 + (index % 7) * 0.06

                        Rectangle {
                            anchors.bottom: parent.bottom
                            anchors.horizontalCenter: parent.horizontalCenter
                            width:  parent.width
                            height: Math.max(3, Math.floor(parent.height * barDel.nivel))
                            radius: Math.min(width / 2, 4)
                            color:   tema.acento
                            opacity: modoFooter ? 0.82 : 0.90
                        }

                        // Each bar animates independently with InOutSine for smooth, organic motion.
                        // Running starts via a stagger Timer — NOT via PauseAnimation (which caused
                        // periodic synchronized "drop to minimum" artifacts).
                        SequentialAnimation on nivel {
                            id: barAnim
                            loops: Animation.Infinite
                            running: false  // started by staggerTimer below

                            // 4 keyframe targets; InOutSine with long durations (300–900 ms each)
                            // gives a natural, unhurried audio-visualizer feel.
                            NumberAnimation { to: 0.84 + (index % 4) * 0.05;  duration: 320 + (index % 7)  * 95; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 0.22 + (index % 5) * 0.06;  duration: 420 + (index % 11) * 68; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 0.68 + (index % 6) * 0.07;  duration: 290 + (index % 9)  * 62; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 0.12 + (index % 3) * 0.05;  duration: 390 + (index % 13) * 80; easing.type: Easing.InOutSine }
                        }

                        // Stagger each bar's start within a 1.8 s window (71 is coprime to 1800)
                        Timer {
                            id: staggerTimer
                            interval: (index * 71) % 1800
                            repeat: false
                            running: raiz.animacionesInicio
                            onTriggered: barAnim.running = true
                        }

                        // Stop animation cleanly when animations are disabled
                        Connections {
                            target: raiz
                            function onAnimacionesInicioChanged() {
                                if (!raiz.animacionesInicio) {
                                    barAnim.running = false
                                    staggerTimer.running = false
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // ── StatChip — individual stat card (4 used in a grid in the hero) ──────────
    component StatChip: Rectangle {
        id: statChip
        property string titulo: ""
        property string valor: ""
        property string iconSource: ""
        height: Math.max(raiz.esMovil ? 92 : 86, chipCol.implicitHeight + UiTokens.spacing16)
        radius: UiTokens.radiusMd
        color: Qt.rgba(tema.seleccion.r, tema.seleccion.g, tema.seleccion.b, 0.62)
        border.color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.42)
        border.width: 1

        ColumnLayout {
            id: chipCol
            anchors.centerIn: parent
            width: parent.width - UiTokens.spacing16
            spacing: UiTokens.spacing6

            Rectangle {
                Layout.preferredWidth: 36; Layout.preferredHeight: 36
                Layout.alignment: Qt.AlignHCenter
                radius: 18
                color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.14)
                ThemedIcon {
                    anchors.centerIn: parent; width: 17; height: 17
                    source: statChip.iconSource; iconColor: tema.acento
                }
            }
            AppText {
                text: statChip.valor
                font.pixelSize: raiz.esMovil ? 14 : 16; font.weight: Font.Bold; color: tema.texto
                horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true
                wrapMode: Text.Wrap; maximumLineCount: 2
            }
            AppText {
                text: statChip.titulo
                font.pixelSize: UiTokens.fontSizeXs; color: tema.textoSec
                horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true
            }
        }
    }

    // ── ThemedIcon ─────────────────────────────────────────────────────────────
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
            sourceSize.width:  Math.max(16, parent.width  * 2)
            sourceSize.height: Math.max(16, parent.height * 2)
            smooth: true; opacity: 0
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

    // ── PrimaryButton ──────────────────────────────────────────────────────────
    component PrimaryButton: Rectangle {
        id: primaryButton
        property string texto: ""
        property string iconSource: ""
        signal clicked()
        Layout.preferredWidth: Math.max(150, buttonRow.implicitWidth + 28)
        Layout.preferredHeight: UiTokens.controlHeightLg
        width:  Layout.preferredWidth
        height: UiTokens.controlHeightLg
        radius: UiTokens.radiusPill
        color: buttonMouse.containsMouse ? tema.acentoFuerte : tema.acento
        scale: buttonMouse.containsMouse ? 1.025 : 1.0

        Behavior on color { ColorAnimation { duration: UiTokens.durationFast } }
        Behavior on scale { NumberAnimation { duration: UiTokens.durationFast; easing.type: Easing.OutQuad } }

        Row {
            id: buttonRow
            anchors.centerIn: parent
            spacing: UiTokens.spacing8
            ThemedIcon {
                width: 17; height: 17
                anchors.verticalCenter: parent.verticalCenter
                source: primaryButton.iconSource
                iconColor: tema.fondo
            }
            AppText {
                text: primaryButton.texto
                anchors.verticalCenter: parent.verticalCenter
                color: tema.fondo; font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold
            }
        }

        MouseArea {
            id: buttonMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: primaryButton.clicked()
        }
    }

    // ── GhostButton ───────────────────────────────────────────────────────────
    component GhostButton: Rectangle {
        id: ghostBtn
        property string texto: ""
        signal clicked()
        Layout.preferredWidth: Math.max(120, ghostRow.implicitWidth + 28)
        Layout.preferredHeight: UiTokens.controlHeightLg
        width:  Layout.preferredWidth
        height: UiTokens.controlHeightLg
        radius: UiTokens.radiusPill
        color: ghostMouse.containsMouse
               ? Qt.rgba(tema.hover.r, tema.hover.g, tema.hover.b, 0.80)
               : Qt.rgba(tema.seleccion.r, tema.seleccion.g, tema.seleccion.b, 0.60)
        border.color: ghostMouse.containsMouse
                      ? Qt.rgba(tema.texto.r, tema.texto.g, tema.texto.b, 0.25)
                      : Qt.rgba(tema.borde.r,  tema.borde.g,  tema.borde.b,  0.50)
        border.width: 1

        Behavior on color { ColorAnimation { duration: UiTokens.durationFast } }

        Row {
            id: ghostRow
            anchors.centerIn: parent
            AppText {
                text: ghostBtn.texto
                color: tema.texto; font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.Medium
            }
        }

        MouseArea {
            id: ghostMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: ghostBtn.clicked()
        }
    }

    // ── IconButton ─────────────────────────────────────────────────────────────
    component IconButton: Rectangle {
        id: iconBtn
        property string iconSource: ""
        signal clicked()
        width: UiTokens.controlHeightMd; height: width
        radius: width / 2
        color: iconBtnMouse.containsMouse
               ? Qt.rgba(tema.hover.r, tema.hover.g, tema.hover.b, 0.80)
               : Qt.rgba(tema.seleccion.r, tema.seleccion.g, tema.seleccion.b, 0.60)
        border.color: iconBtnMouse.containsMouse
                      ? Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.70)
                      : Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.35)
        border.width: 1

        Behavior on color { ColorAnimation { duration: UiTokens.durationFast } }

        ThemedIcon {
            anchors.centerIn: parent
            width: 16; height: 16
            source: iconBtn.iconSource
            iconColor: iconBtnMouse.containsMouse ? tema.texto : tema.textoSec
        }

        MouseArea {
            id: iconBtnMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: iconBtn.clicked()
        }
    }

    // ── CoverArt ──────────────────────────────────────────────────────────────
    component CoverArt: Rectangle {
        id: cover
        property var itemData: ({})
        property string tipo: "pista"
        property bool circular: false
        property bool sinRecortePortada: false
        property string sourceUrl: raiz.portadaPrincipal(itemData)
        radius: circular ? width / 2 : UiTokens.radiusSm
        clip: true
        color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.08)
        border.color: imagen.visible ? "transparent" : Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.20)
        border.width: imagen.visible ? 0 : 1

        Rectangle {
            anchors.fill: parent; radius: cover.radius
            visible: !imagen.visible
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.18) }
                GradientStop { position: 1.0; color: Qt.rgba(tema.superficieAlt.r, tema.superficieAlt.g, tema.superficieAlt.b, 0.88) }
            }
        }

        Grid {
            anchors.fill: parent
            visible: !imagen.visible && cover.tipo === "playlist" && cover.itemData.portadas && cover.itemData.portadas.length > 1
            columns: 2; rows: 2; spacing: 0
            Repeater {
                model: cover.itemData.portadas || []
                Image {
                    width: cover.width / 2; height: cover.height / 2
                    source: UiUtils.toMediaSource(modelData)
                    sourceSize.width: Math.max(48, width * 2); sourceSize.height: Math.max(48, height * 2)
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true; cache: true; smooth: true
                    visible: index < 4
                }
            }
        }

        ThemedIcon {
            anchors.centerIn: parent
            visible: !imagen.visible && !(cover.tipo === "playlist" && cover.itemData.portadas && cover.itemData.portadas.length > 1)
            width: Math.max(22, Math.min(parent.width, parent.height) * 0.32); height: width
            source: raiz.iconoTipo(cover.tipo)
            iconColor: tema.acento; iconOpacity: 0.86
        }

        Image {
            id: imagen
            anchors.fill: parent
            anchors.margins: cover.sinRecortePortada ? 2 : 0
            source: cover.sourceUrl
            sourceSize.width: Math.max(64, width * 2); sourceSize.height: Math.max(64, height * 2)
            fillMode: cover.sinRecortePortada ? Image.PreserveAspectFit : Image.PreserveAspectCrop
            asynchronous: true; cache: true; smooth: true
            visible: cover.sourceUrl !== "" && status !== Image.Error
        }
    }

    // ── SectionHeader ─────────────────────────────────────────────────────────
    component SectionHeader: RowLayout {
        id: sectionHeader
        property string titulo: ""
        property string subtitulo: ""
        property string verTodoLabel: ""
        signal verTodo()
        Layout.fillWidth: true
        spacing: UiTokens.spacing12

        ColumnLayout {
            Layout.fillWidth: true
            spacing: UiTokens.spacing2
            AppText {
                text: sectionHeader.titulo
                font.pixelSize: raiz.esMovil ? 18 : 22
                font.bold: true; color: tema.texto
                elide: Text.ElideRight; Layout.fillWidth: true
            }
            AppText {
                text: sectionHeader.subtitulo
                visible: sectionHeader.subtitulo !== ""
                font.pixelSize: UiTokens.fontSizeMd; color: tema.textoSec
                elide: Text.ElideRight; Layout.fillWidth: true
            }
        }

        AppText {
            visible: sectionHeader.verTodoLabel !== ""
            text: sectionHeader.verTodoLabel !== "" ? sectionHeader.verTodoLabel + " →" : ""
            font.pixelSize: UiTokens.fontSizeMd; color: tema.acento; font.weight: Font.Medium
            MouseArea {
                anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                onClicked: sectionHeader.verTodo()
            }
        }
    }

    // ── CarouselButton ────────────────────────────────────────────────────────
    component CarouselButton: Rectangle {
        id: carouselButton
        property string iconSource: ""
        signal clicked()
        width: raiz.esMovil ? 36 : 40; height: width; radius: width / 2
        color: buttonArea.containsMouse
               ? Qt.rgba(tema.hover.r, tema.hover.g, tema.hover.b, 0.95)
               : Qt.rgba(tema.seleccion.r, tema.seleccion.g, tema.seleccion.b, 0.82)
        border.color: buttonArea.containsMouse
                      ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.48)
                      : tema.borde
        border.width: 1
        scale: buttonArea.containsMouse ? 1.03 : 1.0

        Behavior on color       { ColorAnimation  { duration: UiTokens.durationFast } }
        Behavior on border.color{ ColorAnimation  { duration: UiTokens.durationFast } }
        Behavior on scale       { NumberAnimation { duration: UiTokens.durationFast; easing.type: Easing.OutQuad } }

        ThemedIcon {
            anchors.centerIn: parent; width: 17; height: 17
            source: carouselButton.iconSource
            iconColor: buttonArea.containsMouse ? tema.texto : tema.textoSec
        }

        MouseArea {
            id: buttonArea
            anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
            onClicked: carouselButton.clicked()
        }
    }

    // ── DashboardCard ─────────────────────────────────────────────────────────
    component DashboardCard: Rectangle {
        id: card
        property var itemData: ({})
        property string tipoFallback: "pista"
        property string estilo: "normal"
        property bool ranking: false
        property int indice: 0
        readonly property string tipoItem: itemData.tipo || tipoFallback
        readonly property bool rankingCard: estilo === "ranking"
        readonly property bool editorialCard: estilo === "editorial"
        readonly property bool artistCard: tipoItem === "artista" || tipoItem === "artista_top"
        signal activated(var itemData, string tipoFallback)

        radius: UiTokens.radiusMd
        color: cardMouse.containsMouse
               ? Qt.rgba(tema.hover.r, tema.hover.g, tema.hover.b, card.editorialCard ? 0.94 : 0.90)
               : Qt.rgba(tema.seleccion.r, tema.seleccion.g, tema.seleccion.b, card.editorialCard ? 0.86 : 0.80)
        border.color: cardMouse.containsMouse
                      ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.58)
                      : (card.editorialCard ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.18) : tema.borde)
        border.width: card.editorialCard && cardMouse.containsMouse ? 2 : 1
        scale: cardMouse.containsMouse ? (card.editorialCard ? 1.025 : 1.012) : 1.0
        clip: true

        Behavior on color       { ColorAnimation  { duration: UiTokens.durationFast } }
        Behavior on border.color{ ColorAnimation  { duration: UiTokens.durationFast } }
        Behavior on scale       { NumberAnimation { duration: UiTokens.durationFast; easing.type: Easing.OutQuad } }

        RowLayout {
            anchors.fill: parent
            anchors.margins: rankingCard ? UiTokens.spacing10 : 0
            spacing: rankingCard ? UiTokens.spacing10 : 0
            visible: rankingCard

            AppText {
                visible: card.ranking
                Layout.preferredWidth: 30
                text: card.indice < 9 ? ("0" + (card.indice + 1)) : String(card.indice + 1)
                font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold; color: tema.acento
                horizontalAlignment: Text.AlignHCenter; Layout.alignment: Qt.AlignVCenter
            }

            CoverArt {
                Layout.preferredWidth:  rankingCard ? 72 : 58
                Layout.preferredHeight: Layout.preferredWidth
                Layout.alignment: Qt.AlignVCenter
                itemData: card.itemData; tipo: card.tipoItem; circular: card.artistCard
            }

            ColumnLayout {
                Layout.fillWidth: true; Layout.alignment: Qt.AlignVCenter
                spacing: UiTokens.spacing4
                AppText {
                    text: raiz.tituloItem(card.itemData, card.tipoFallback)
                    font.pixelSize: rankingCard ? 13 : 12; font.weight: Font.DemiBold; color: tema.texto
                    maximumLineCount: rankingCard ? 2 : 1
                    wrapMode: rankingCard ? Text.Wrap : Text.NoWrap
                    elide: Text.ElideRight; Layout.fillWidth: true
                }
                AppText {
                    text: raiz.subtituloItem(card.itemData, card.tipoFallback)
                    font.pixelSize: UiTokens.fontSizeSm; color: tema.textoSec
                    maximumLineCount: rankingCard ? 4 : 1
                    wrapMode: rankingCard ? Text.Wrap : Text.NoWrap
                    elide: Text.ElideRight; Layout.fillWidth: true
                }
                AppText {
                    visible: card.ranking && (card.itemData.reproducciones_total || 0) > 0
                    text: (card.itemData.reproducciones_total || 0) + " reproducciones"
                    font.pixelSize: UiTokens.fontSizeXs; color: tema.textoMuted; elide: Text.ElideRight; Layout.fillWidth: true
                }
                AppText {
                    visible: !card.ranking && raiz.contextoItem(card.itemData) !== ""
                    text: raiz.contextoItem(card.itemData)
                    font.pixelSize: UiTokens.fontSizeXs; color: tema.textoMuted; elide: Text.ElideRight; Layout.fillWidth: true
                }
            }

            Rectangle {
                Layout.preferredWidth: 32; Layout.preferredHeight: 32; Layout.alignment: Qt.AlignVCenter
                radius: 16
                color: cardMouse.containsMouse ? tema.acento : Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.14)
                visible: card.tipoItem === "pista"
                ThemedIcon {
                    anchors.centerIn: parent; width: 15; height: 15
                    source: "../assets/icons/play.svg"
                    iconColor: cardMouse.containsMouse ? tema.fondo : tema.acento
                }
            }
        }

        ColumnLayout {
            id: columnaCuadro
            anchors.fill: parent; anchors.margins: UiTokens.spacing10
            spacing: UiTokens.spacing8
            visible: !rankingCard
            readonly property real margInterior: UiTokens.spacing10
            readonly property real ladoPortadaCuad: Math.max(96, card.width - 2 * margInterior)

            CoverArt {
                Layout.fillWidth: true
                Layout.preferredWidth:  columnaCuadro.ladoPortadaCuad
                Layout.preferredHeight: columnaCuadro.ladoPortadaCuad
                Layout.maximumWidth:    columnaCuadro.ladoPortadaCuad
                Layout.maximumHeight:   columnaCuadro.ladoPortadaCuad
                Layout.alignment: Qt.AlignHCenter
                sinRecortePortada: true; itemData: card.itemData; tipo: card.tipoItem; circular: card.artistCard
            }

            RowLayout {
                Layout.fillWidth: true; spacing: UiTokens.spacing8
                ColumnLayout {
                    Layout.fillWidth: true; spacing: UiTokens.spacing4
                    AppText {
                        text: raiz.tituloItem(card.itemData, card.tipoFallback)
                        font.pixelSize: card.editorialCard ? 14 : 13; font.weight: Font.DemiBold; color: tema.texto
                        maximumLineCount: card.editorialCard ? 3 : 2; wrapMode: Text.Wrap
                        elide: Text.ElideRight; Layout.fillWidth: true
                    }
                    // Only show context when it has reproducciones (avoids duplicating num_pistas)
                    AppText {
                        visible: (card.itemData.reproducciones_total || 0) > 0
                        text: (card.itemData.reproducciones_total || 0) + " reproducciones"
                        font.pixelSize: UiTokens.fontSizeXs; color: tema.textoSec
                        maximumLineCount: 2; wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                    AppText {
                        text: raiz.subtituloItem(card.itemData, card.tipoFallback)
                        font.pixelSize: UiTokens.fontSizeSm; color: tema.textoSec
                        maximumLineCount: 3; wrapMode: Text.Wrap
                        elide: Text.ElideRight; Layout.fillWidth: true
                    }
                }
                Rectangle {
                    Layout.preferredWidth: 34; Layout.preferredHeight: 34; Layout.alignment: Qt.AlignTop
                    radius: 17; visible: card.tipoItem === "pista"
                    color: cardMouse.containsMouse ? tema.acento : Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.14)
                    ThemedIcon {
                        anchors.centerIn: parent; width: 15; height: 15
                        source: "../assets/icons/play.svg"
                        iconColor: cardMouse.containsMouse ? tema.fondo : tema.acento
                    }
                }
            }
        }

        MouseArea {
            id: cardMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
            onClicked: card.activated(card.itemData, card.tipoFallback)
        }
    }

    // ── RetomarCard (compact horizontal card) ─────────────────────────────────
    component RetomarCard: Rectangle {
        id: retomarCard
        property var itemData: ({})
        property string tipoFallback: "pista"
        readonly property string tipoItem: itemData.tipo || tipoFallback
        readonly property bool artistCard: tipoItem === "artista" || tipoItem === "artista_top"
        signal activated(var itemData, string tipoFallback)

        radius: UiTokens.radiusMd
        color: retomarMouse.containsMouse
               ? Qt.rgba(tema.hover.r, tema.hover.g, tema.hover.b, 0.90)
               : Qt.rgba(tema.seleccion.r, tema.seleccion.g, tema.seleccion.b, 0.72)
        border.color: retomarMouse.containsMouse
                      ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.42)
                      : Qt.rgba(tema.borde.r,  tema.borde.g,  tema.borde.b,  0.55)
        border.width: retomarMouse.containsMouse ? 2 : 1
        scale: retomarMouse.containsMouse ? 1.018 : 1.0
        clip: true

        Behavior on scale       { NumberAnimation { duration: UiTokens.durationFast; easing.type: Easing.OutQuad } }
        Behavior on color       { ColorAnimation  { duration: UiTokens.durationFast } }
        Behavior on border.color{ ColorAnimation  { duration: UiTokens.durationFast } }

        RowLayout {
            anchors.fill: parent; anchors.margins: UiTokens.spacing8; spacing: UiTokens.spacing10

            CoverArt {
                Layout.preferredWidth: 58; Layout.preferredHeight: 58; Layout.alignment: Qt.AlignVCenter
                itemData: retomarCard.itemData; tipo: retomarCard.tipoItem; circular: retomarCard.artistCard
            }

            ColumnLayout {
                Layout.fillWidth: true; Layout.alignment: Qt.AlignVCenter; spacing: UiTokens.spacing4
                AppText {
                    text: raiz.tituloItem(retomarCard.itemData, retomarCard.tipoFallback)
                    font.pixelSize: UiTokens.fontSizeMd; font.weight: Font.DemiBold; color: tema.texto
                    maximumLineCount: 2; wrapMode: Text.Wrap; elide: Text.ElideRight; Layout.fillWidth: true
                }
                AppText {
                    text: raiz.subtituloItem(retomarCard.itemData, retomarCard.tipoFallback)
                    font.pixelSize: UiTokens.fontSizeXs; color: tema.textoSec
                    maximumLineCount: 3; wrapMode: Text.Wrap; elide: Text.ElideRight; Layout.fillWidth: true
                }
                AppText {
                    visible: raiz.contextoItem(retomarCard.itemData) !== ""
                    text: raiz.contextoItem(retomarCard.itemData)
                    font.pixelSize: UiTokens.fontSizeXs; color: tema.textoMuted
                    maximumLineCount: 2; wrapMode: Text.Wrap; elide: Text.ElideRight; Layout.fillWidth: true
                }
            }

            Rectangle {
                Layout.preferredWidth: 30; Layout.preferredHeight: 30; Layout.alignment: Qt.AlignVCenter
                radius: 15; visible: retomarCard.tipoItem === "pista"
                color: retomarMouse.containsMouse ? tema.acento : Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.14)
                ThemedIcon {
                    anchors.centerIn: parent; width: 14; height: 14
                    source: "../assets/icons/play.svg"
                    iconColor: retomarMouse.containsMouse ? tema.fondo : tema.acento
                }
            }
        }

        MouseArea {
            id: retomarMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
            onClicked: retomarCard.activated(retomarCard.itemData, retomarCard.tipoFallback)
        }
    }

    // ── SeccionCarrusel ────────────────────────────────────────────────────────
    component SeccionCarrusel: Item {
        id: seccion
        property string titulo: ""
        property string subtitulo: ""
        property var modelo: null
        property string tipo: "pista"
        property string estilo: "normal"
        property bool ranking: false
        property int maxItems: 1000
        Layout.fillWidth: true
        Layout.leftMargin:  raiz.paddingHorizontal
        Layout.rightMargin: raiz.paddingHorizontal
        Layout.bottomMargin: raiz.esMovil ? UiTokens.spacing24 : raiz.separacionBloques
        Layout.preferredHeight: alturaSeccion
        implicitHeight: alturaSeccion

        readonly property int espacioCarrusel: raiz.esMovil ? UiTokens.spacing10 : UiTokens.spacing12
        readonly property bool rankingCard: estilo === "ranking"
        readonly property bool editorial: estilo === "editorial"
        readonly property int totalVisible: modelo ? Math.min(maxItems, modelo.total || 0) : 0
        readonly property real _listaW: Math.max(100, raiz.width - 2 * raiz.paddingHorizontal)
        readonly property int krColumnas: 1
        // Fixed width for ranking carousel cards — never wider than 310px
        readonly property real anchoCartaRanking: raiz.esMovil
            ? Math.min(_listaW * 0.92, 310)
            : 310
        readonly property real anchoCartaEditorial: raiz.esMovil ? 164 : (raiz.esCompacta ? 178 : 196)
        readonly property real anchoCartaListaPista: raiz.esMovil ? 158 : (raiz.esCompacta ? 172 : 184)
        readonly property real mTarjMar: UiTokens.spacing10
        readonly property real ladoListaPistaPortada: Math.max(98, anchoCartaListaPista - 2 * mTarjMar)
        readonly property int encabezadoHeight: subtitulo === "" ? 28 : 46
        readonly property int separacionHeaderLista: UiTokens.spacing12
        readonly property real itemWidth: rankingCard ? anchoCartaRanking
                                                       : (editorial ? anchoCartaEditorial : anchoCartaListaPista)
        readonly property real itemHeight: rankingCard ? 138
                                                        : editorial
                                                          ? Math.floor(anchoCartaEditorial + (raiz.esMovil ? 108 : 120))
                                                          : Math.floor(ladoListaPistaPortada + 2 * mTarjMar + (raiz.esMovil ? 100 : 108))
        readonly property real pasoPixeles: itemWidth + espacioCarrusel
        readonly property real pageStep: Math.max(pasoPixeles, Math.floor(Math.max(pasoPixeles, lista.width * 0.86) / pasoPixeles) * pasoPixeles)
        readonly property bool puedeIzquierda: lista.contentWidth > lista.width + 2 && !lista.atXBeginning
        readonly property bool puedeDerecha:   lista.contentWidth > lista.width + 2 && !lista.atXEnd
        readonly property int alturaSeccion: encabezadoHeight + separacionHeaderLista + itemHeight + 16

        function deslizar(delta) {
            var limite = Math.max(0, lista.contentWidth - lista.width)
            var destino = Math.max(0, Math.min(limite, lista.contentX + delta))
            if (Math.abs(destino - lista.contentX) < 1) return
            animacionLista.to = destino
            animacionLista.restart()
        }

        ColumnLayout {
            anchors.fill: parent; spacing: seccion.separacionHeaderLista

            SectionHeader {
                titulo: seccion.titulo; subtitulo: seccion.subtitulo
                Layout.preferredHeight: seccion.encabezadoHeight
            }

            Item {
                id: listaArea
                Layout.fillWidth: true; Layout.preferredHeight: seccion.itemHeight + 10
                clip: false

                ListView {
                    id: lista
                    anchors.fill: parent
                    orientation: ListView.Horizontal; spacing: seccion.espacioCarrusel
                    model: seccion.totalVisible; clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    flickDeceleration: 2500; maximumFlickVelocity: 4200
                    cacheBuffer: Math.max(320, seccion.itemWidth * 3)
                    reuseItems: true

                    delegate: DashboardCard {
                        width: seccion.itemWidth; height: seccion.itemHeight
                        itemData: seccion.modelo ? seccion.modelo.obtener(index) : ({})
                        tipoFallback: seccion.tipo; estilo: seccion.estilo
                        ranking: seccion.ranking; indice: index
                        onActivated: function(itemData, tipoFallback) { raiz.abrirItem(itemData, tipoFallback) }
                    }

                    ScrollBar.horizontal: AppScrollBar {
                        tema: raiz.tema
                        orientation: Qt.Horizontal
                        policy: lista.contentWidth > lista.width + 2 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
                        interactive: true; height: 6
                        active: hovered || pressed || lista.moving || lista.flicking
                    }
                }

                CarouselButton {
                    anchors.left: parent.left; anchors.leftMargin: UiTokens.spacing2; anchors.verticalCenter: parent.verticalCenter
                    iconSource: "../assets/icons/chevron-left.svg"
                    visible: seccion.puedeIzquierda
                    onClicked: seccion.deslizar(-seccion.pageStep)
                }
                CarouselButton {
                    anchors.right: parent.right; anchors.rightMargin: UiTokens.spacing2; anchors.verticalCenter: parent.verticalCenter
                    iconSource: "../assets/icons/chevron-right.svg"
                    visible: seccion.puedeDerecha
                    onClicked: seccion.deslizar(seccion.pageStep)
                }
            }
        }

        NumberAnimation {
            id: animacionLista; target: lista; property: "contentX"
            duration: UiTokens.durationSlow + 80; easing.type: Easing.InOutCubic
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // HERO SECTION
    // ═══════════════════════════════════════════════════════════════════════════

    component HeroSeccion: Item {
        id: heroSec
        implicitHeight: heroRow.implicitHeight

        readonly property var albumDestacado: {
            if (estadisticas.albums_que_gustan && (estadisticas.albums_que_gustan.total || 0) > 0)
                return estadisticas.albums_que_gustan.obtener(0)
            if (estadisticas.mas_escuchadas_albums && (estadisticas.mas_escuchadas_albums.total || 0) > 0)
                return estadisticas.mas_escuchadas_albums.obtener(0)
            return null
        }
        readonly property var pistaRetomar: (estadisticas.para_volver && (estadisticas.para_volver.total || 0) > 0)
                                            ? estadisticas.para_volver.obtener(0) : null

        RowLayout {
            id: heroRow
            anchors.left: parent.left; anchors.right: parent.right
            spacing: UiTokens.spacing20

            // ── LEFT COLUMN ──────────────────────────────────────────────────
            ColumnLayout {
                id: heroLeft
                Layout.fillWidth: true
                Layout.minimumWidth: 280
                // When the album panel is visible, ensure left column is at least as tall
                // so the retomar card (fillHeight) aligns its bottom with the album panel.
                Layout.minimumHeight: !raiz.esCompacta && heroSec.albumDestacado !== null
                                       ? heroRight.panelW : 0
                Layout.fillHeight: !raiz.esCompacta
                spacing: UiTokens.spacing16

                // Eyebrow
                Row {
                    spacing: UiTokens.spacing10
                    Rectangle {
                        id: eyebrowDot
                        width: 8; height: 8; radius: 4
                        color: tema.acento
                        anchors.verticalCenter: parent.verticalCenter
                        SequentialAnimation on opacity {
                            loops: Animation.Infinite; running: raiz.animacionesInicio
                            NumberAnimation { to: 0.3; duration: 900; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutSine }
                        }
                    }
                    AppText {
                        text: "Biblioteca local · sincronizada"
                        font.pixelSize: UiTokens.fontSizeSm; color: tema.textoSec
                        anchors.verticalCenter: parent.verticalCenter
                        font.family: "JetBrains Mono"
                    }
                }

                // Greeting
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: UiTokens.spacing8

                    AppText {
                        text: estadisticas.saludo_inicio || "Hoy es un gran día para descubrir."
                        font.pixelSize: raiz.saludoTamano
                        font.bold: true; color: tema.texto
                        wrapMode: Text.Wrap; maximumLineCount: 3
                        elide: Text.ElideRight; Layout.fillWidth: true
                    }

                    AppText {
                        text: raiz.hayBiblioteca
                              ? "Retoma, descubre y revisa lo que más valor tiene en tu biblioteca local. Sin servicios externos — solo tus archivos."
                              : "Importa tu música para construir un inicio con actividad, favoritos y recomendaciones locales."
                        color: tema.textoSec; font.pixelSize: raiz.esMovil ? 12 : 13
                        wrapMode: Text.Wrap; maximumLineCount: 3; Layout.fillWidth: true
                    }
                }

                // Stats — 4 separate cards in a grid (consistent with the rest of the app)
                GridLayout {
                    visible: raiz.hayBiblioteca
                    Layout.fillWidth: true
                    columns: raiz.esMovil ? 2 : 4
                    columnSpacing: UiTokens.spacing10
                    rowSpacing: UiTokens.spacing10

                    StatChip {
                        Layout.fillWidth: true
                        titulo: "Pistas"
                        valor: (estadisticas.resumen.total_pistas || 0).toLocaleString()
                        iconSource: "../assets/icons/track.svg"
                    }
                    StatChip {
                        Layout.fillWidth: true
                        titulo: "Artistas"
                        valor: (estadisticas.resumen.total_artistas || 0).toLocaleString()
                        iconSource: "../assets/icons/artist.svg"
                    }
                    StatChip {
                        Layout.fillWidth: true
                        titulo: "Álbumes"
                        valor: (estadisticas.resumen.total_albums || 0).toLocaleString()
                        iconSource: "../assets/icons/album.svg"
                    }
                    StatChip {
                        Layout.fillWidth: true
                        titulo: "Duración"
                        valor: estadisticas.formatear_duracion_detallada(estadisticas.resumen.duracion_total_seg || 0)
                        iconSource: "../assets/icons/clock.svg"
                    }
                }

                // Retomar card — fills remaining height so its bottom aligns with the album panel
                Rectangle {
                    id: retomarFeatureCard
                    visible: raiz.hayBiblioteca && heroSec.pistaRetomar !== null
                    Layout.fillWidth: true
                    Layout.fillHeight: !raiz.esCompacta  // fill to match album panel height
                    Layout.minimumHeight: 76
                    Layout.preferredHeight: 76
                    radius: UiTokens.radiusMd
                    color: rfcMouse.containsMouse
                           ? Qt.rgba(tema.hover.r, tema.hover.g, tema.hover.b, 0.82)
                           : Qt.rgba(tema.seleccion.r, tema.seleccion.g, tema.seleccion.b, 0.70)
                    border.color: rfcMouse.containsMouse
                                  ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.55)
                                  : Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.45)
                    border.width: 1
                    clip: true

                    // Subtle accent shimmer on hover
                    Rectangle {
                        anchors.fill: parent; radius: parent.radius
                        visible: rfcMouse.containsMouse
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0.0; color: Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.10) }
                            GradientStop { position: 1.0; color: "transparent" }
                        }
                    }

                    Behavior on color { ColorAnimation { duration: UiTokens.durationFast } }

                    RowLayout {
                        anchors.fill: parent; anchors.margins: UiTokens.spacing10
                        spacing: UiTokens.spacing12

                        CoverArt {
                            Layout.preferredWidth: 56; Layout.preferredHeight: 56
                            Layout.alignment: Qt.AlignVCenter
                            itemData: heroSec.pistaRetomar || ({})
                            tipo: (heroSec.pistaRetomar && heroSec.pistaRetomar.tipo) || "pista"
                        }

                        ColumnLayout {
                            Layout.fillWidth: true; Layout.alignment: Qt.AlignVCenter
                            spacing: UiTokens.spacing4

                            AppText {
                                text: "RETOMAR REPRODUCCIÓN"
                                font.pixelSize: UiTokens.fontSizeXs; color: tema.acento; font.weight: Font.DemiBold
                            }

                            AppText {
                                text: raiz.tituloItem(heroSec.pistaRetomar, "pista")
                                font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.Bold; color: tema.texto
                                elide: Text.ElideRight; Layout.fillWidth: true
                            }

                            AppText {
                                text: raiz.subtituloItem(heroSec.pistaRetomar, "pista")
                                font.pixelSize: UiTokens.fontSizeSm; color: tema.textoSec
                                elide: Text.ElideRight; Layout.fillWidth: true
                            }

                            // Progress bar
                            Item {
                                Layout.fillWidth: true; height: 3
                                Rectangle {
                                    anchors.fill: parent; radius: 2
                                    color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.50)
                                }
                                Rectangle {
                                    height: parent.height; radius: 2
                                    color: tema.acento
                                    width: {
                                        var ratio = 0
                                        var pa = reproductor.pista_activa
                                        if (heroSec.pistaRetomar && pa && pa.id
                                                && pa.id === heroSec.pistaRetomar.id
                                                && (reproductor.duracion_seg || 0) > 0) {
                                            ratio = Math.min(1.0, (reproductor.posicion_seg || 0) / reproductor.duracion_seg)
                                        }
                                        return parent.width * ratio
                                    }
                                }
                            }
                        }

                        // Play button
                        Rectangle {
                            Layout.preferredWidth: 38; Layout.preferredHeight: 38
                            Layout.alignment: Qt.AlignVCenter
                            radius: 19
                            color: rfcMouse.containsMouse ? tema.acento : Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.20)
                            Behavior on color { ColorAnimation { duration: UiTokens.durationFast } }
                            ThemedIcon {
                                anchors.centerIn: parent; width: 16; height: 16
                                source: "../assets/icons/play.svg"
                                iconColor: rfcMouse.containsMouse ? tema.fondo : tema.acento
                            }
                        }
                    }

                    MouseArea {
                        id: rfcMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onClicked: raiz.abrirItem(heroSec.pistaRetomar, "pista")
                    }
                }
            }

            // ── RIGHT PANEL — square to match album art 1:1 ──────────────────
            Rectangle {
                id: heroRight
                visible: !raiz.esCompacta && raiz.hayBiblioteca && heroSec.albumDestacado !== null
                // Square: height = width so album art fills without cropping
                readonly property real panelW: Math.min(420, Math.max(300, heroRow.width * 0.36))
                Layout.preferredWidth:  panelW
                Layout.preferredHeight: panelW
                Layout.alignment: Qt.AlignTop
                radius: UiTokens.radiusMd
                clip: true
                color: Qt.rgba(tema.superficieAlt.r, tema.superficieAlt.g, tema.superficieAlt.b, 0.80)
                border.color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.35)
                border.width: 1

                // Background cover — square panel + square album art = no crop needed
                Image {
                    anchors.fill: parent
                    source: heroSec.albumDestacado ? raiz.portadaPrincipal(heroSec.albumDestacado) : ""
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true; cache: true; smooth: true
                    visible: source !== "" && status !== Image.Error
                }

                // Gradient overlay — uses tema.fondo so it works in any theme
                Rectangle {
                    anchors.fill: parent; radius: parent.radius
                    gradient: Gradient {
                        orientation: Gradient.Vertical
                        GradientStop { position: 0.0;  color: "transparent" }
                        GradientStop { position: 0.50; color: Qt.rgba(tema.fondo.r, tema.fondo.g, tema.fondo.b, 0.20) }
                        GradientStop { position: 1.0;  color: Qt.rgba(tema.fondo.r, tema.fondo.g, tema.fondo.b, 0.88) }
                    }
                }

                // Content overlay at bottom
                ColumnLayout {
                    anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                    anchors.leftMargin: UiTokens.spacing16; anchors.rightMargin: UiTokens.spacing16
                    anchors.bottomMargin: UiTokens.spacing16
                    spacing: UiTokens.spacing6

                    AppText {
                        text: "ÁLBUM DESTACADO DEL DÍA"
                        font.pixelSize: UiTokens.fontSizeXs; color: tema.acentoFuerte; font.weight: Font.DemiBold
                    }

                    AppText {
                        text: heroSec.albumDestacado ? raiz.tituloItem(heroSec.albumDestacado, "album") : ""
                        font.pixelSize: 20; font.weight: Font.Bold; color: tema.texto
                        wrapMode: Text.Wrap; maximumLineCount: 2; Layout.fillWidth: true
                    }

                    AppText {
                        text: {
                            var ad = heroSec.albumDestacado
                            if (!ad) return ""
                            var partes = []
                            if (ad.artista_nombre) partes.push(ad.artista_nombre)
                            var np = ad.num_pistas || 0
                            if (np > 0) partes.push(np + " pistas")
                            if (ad.anio) partes.push(String(ad.anio))
                            return partes.join(" · ")
                        }
                        font.pixelSize: UiTokens.fontSizeMd; color: tema.textoSec; Layout.fillWidth: true
                        elide: Text.ElideRight
                    }

                    RowLayout {
                        spacing: UiTokens.spacing8; Layout.topMargin: UiTokens.spacing4

                        PrimaryButton {
                            texto: "Reproducir"
                            iconSource: "../assets/icons/play.svg"
                            onClicked: {
                                var ad = heroSec.albumDestacado
                                if (!ad) return
                                var albumId = ad.album_id || ad.id
                                if (!albumId) return
                                biblioteca.abrir_album(albumId)
                                var detalle = biblioteca.album_detalle
                                var pistas = (detalle && detalle.pistas) ? detalle.pistas : []
                                if (pistas.length > 0)
                                    reproductor.reproducir_cola_desde_pistas(pistas, 0)
                            }
                        }

                        GhostButton {
                            texto: "Ver álbum"
                            onClicked: {
                                var ad = heroSec.albumDestacado
                                if (ad && raiz.shell) raiz.shell.abrir_album_desde_detalle(ad.album_id || ad.id)
                            }
                        }
                    }
                }
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // GRID RETOMAR ASIMÉTRICO
    // ═══════════════════════════════════════════════════════════════════════════

    component GridRetornarAsimetrico: Item {
        id: gridRet
        implicitHeight: alturaTotal

        readonly property int totalVisible: estadisticas.para_volver ? Math.min(raiz.maxVolver, estadisticas.para_volver.total || 0) : 0
        readonly property bool usarAsimetrico: !raiz.esCompacta && totalVisible >= 5
        readonly property int gs: UiTokens.spacing10
        readonly property int heroH: 220
        readonly property int smallH: Math.floor((heroH - gs) / 2)
        readonly property real gridW: Math.max(100, width)
        readonly property real tercio: Math.floor((gridW - 2 * gs) / 3)

        // Fallback grid dimensions (compact)
        readonly property int minCellW: raiz.esMovil ? 168 : 272
        readonly property int fallbackCols: gridW > 0 ? Math.max(1, Math.min(totalVisible, Math.max(1, Math.floor((gridW + gs) / (minCellW + gs))))) : 1
        readonly property int fallbackFilas: Math.ceil(totalVisible / Math.max(1, fallbackCols))
        readonly property int fallbackItemH: raiz.esMovil ? 100 : 98
        readonly property int fallbackGridH: fallbackFilas * fallbackItemH + Math.max(0, fallbackFilas - 1) * gs

        readonly property int encabezadoH: 46
        readonly property int alturaTotal: totalVisible > 0
                                          ? encabezadoH + UiTokens.spacing12
                                            + (usarAsimetrico ? (heroH + gs + smallH) : fallbackGridH)
                                          : 0

        ColumnLayout {
            anchors.fill: parent; spacing: UiTokens.spacing12

            SectionHeader {
                titulo: "Vuelve a tu música"
                subtitulo: "Retoma canciones, álbumes y playlists de tu biblioteca."
                Layout.preferredHeight: gridRet.encabezadoH
            }

            // ── Asimétrico ────────────────────────────────────────────────────
            Item {
                visible: gridRet.usarAsimetrico
                Layout.fillWidth: true
                Layout.preferredHeight: gridRet.heroH + gridRet.gs + gridRet.smallH

                // Hero card (2/3 width × full height)
                HeroCardRetomar {
                    x: 0; y: 0
                    width:  gridRet.tercio * 2 + gridRet.gs
                    height: gridRet.heroH
                    itemData: estadisticas.para_volver && gridRet.totalVisible > 0
                              ? estadisticas.para_volver.obtener(0) : ({})
                    onActivated: function(d) { raiz.abrirItem(d, "pista") }
                }

                // Small card 1 (top-right)
                RetomarCard {
                    x: gridRet.tercio * 2 + gridRet.gs * 2
                    y: 0
                    width: gridRet.tercio
                    height: gridRet.smallH
                    itemData: estadisticas.para_volver && gridRet.totalVisible > 1
                              ? estadisticas.para_volver.obtener(1) : ({})
                    onActivated: function(d, t) { raiz.abrirItem(d, t) }
                }

                // Small card 2 (bottom-right)
                RetomarCard {
                    x: gridRet.tercio * 2 + gridRet.gs * 2
                    y: gridRet.smallH + gridRet.gs
                    width: gridRet.tercio
                    height: gridRet.smallH
                    itemData: estadisticas.para_volver && gridRet.totalVisible > 2
                              ? estadisticas.para_volver.obtener(2) : ({})
                    onActivated: function(d, t) { raiz.abrirItem(d, t) }
                }

                // Bottom row: 3 equal small cards
                RetomarCard {
                    x: 0
                    y: gridRet.heroH + gridRet.gs
                    width: gridRet.tercio
                    height: gridRet.smallH
                    itemData: estadisticas.para_volver && gridRet.totalVisible > 3
                              ? estadisticas.para_volver.obtener(3) : ({})
                    onActivated: function(d, t) { raiz.abrirItem(d, t) }
                }
                RetomarCard {
                    x: gridRet.tercio + gridRet.gs
                    y: gridRet.heroH + gridRet.gs
                    width: gridRet.tercio
                    height: gridRet.smallH
                    itemData: estadisticas.para_volver && gridRet.totalVisible > 4
                              ? estadisticas.para_volver.obtener(4) : ({})
                    onActivated: function(d, t) { raiz.abrirItem(d, t) }
                }
                RetomarCard {
                    x: gridRet.tercio * 2 + gridRet.gs * 2
                    y: gridRet.heroH + gridRet.gs
                    width: gridRet.tercio
                    height: gridRet.smallH
                    visible: gridRet.totalVisible > 5
                    itemData: estadisticas.para_volver && gridRet.totalVisible > 5
                              ? estadisticas.para_volver.obtener(5) : ({})
                    onActivated: function(d, t) { raiz.abrirItem(d, t) }
                }
            }

            // ── Fallback grid (compact/mobile) ────────────────────────────────
            GridLayout {
                visible: !gridRet.usarAsimetrico && gridRet.totalVisible > 0
                Layout.fillWidth: true
                Layout.preferredHeight: gridRet.fallbackGridH
                columns: gridRet.fallbackCols
                rowSpacing: gridRet.gs; columnSpacing: gridRet.gs

                Repeater {
                    model: gridRet.totalVisible
                    delegate: RetomarCard {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        Layout.preferredHeight: gridRet.fallbackItemH
                        itemData: estadisticas.para_volver ? estadisticas.para_volver.obtener(index) : ({})
                        tipoFallback: "pista"
                        onActivated: function(d, t) { raiz.abrirItem(d, t) }
                    }
                }
            }
        }
    }

    // ── HeroCardRetomar (large hero card: cover on left + meta on right) ────────
    component HeroCardRetomar: Rectangle {
        id: heroCard
        property var itemData: ({})
        signal activated(var itemData)

        radius: UiTokens.radiusMd
        clip: true
        color: hcMouse.containsMouse
               ? Qt.rgba(tema.hover.r, tema.hover.g, tema.hover.b, 0.88)
               : Qt.rgba(tema.seleccion.r, tema.seleccion.g, tema.seleccion.b, 0.72)
        border.color: hcMouse.containsMouse
                      ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.55)
                      : Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.45)
        border.width: 1
        scale: hcMouse.containsMouse ? 1.008 : 1.0

        Behavior on color       { ColorAnimation  { duration: UiTokens.durationFast } }
        Behavior on border.color{ ColorAnimation  { duration: UiTokens.durationFast } }
        Behavior on scale       { NumberAnimation { duration: UiTokens.durationFast; easing.type: Easing.OutQuad } }

        RowLayout {
            anchors.fill: parent
            anchors.margins: UiTokens.spacing14
            spacing: UiTokens.spacing16

            // Cover art — square, fills the height
            CoverArt {
                Layout.preferredWidth:  heroCard.height - 2 * UiTokens.spacing14
                Layout.preferredHeight: Layout.preferredWidth
                Layout.alignment: Qt.AlignVCenter
                itemData: heroCard.itemData
                tipo: (heroCard.itemData && heroCard.itemData.tipo) || "pista"
                radius: UiTokens.radiusSm
            }

            // Meta column
            ColumnLayout {
                Layout.fillWidth: true; Layout.alignment: Qt.AlignVCenter
                spacing: UiTokens.spacing6

                AppText {
                    text: "ÚLTIMA REPRODUCCIÓN"
                    font.pixelSize: UiTokens.fontSizeXs; color: tema.acento; font.weight: Font.DemiBold
                }

                AppText {
                    text: raiz.tituloItem(heroCard.itemData, "pista")
                    font.pixelSize: UiTokens.fontSizeXl; font.weight: Font.Bold; color: tema.texto
                    wrapMode: Text.Wrap; maximumLineCount: 2; Layout.fillWidth: true
                    elide: Text.ElideRight
                }

                AppText {
                    text: raiz.subtituloItem(heroCard.itemData, "pista")
                    font.pixelSize: UiTokens.fontSizeMd; color: tema.textoSec
                    elide: Text.ElideRight; Layout.fillWidth: true
                }

                AppText {
                    visible: raiz.contextoItem(heroCard.itemData) !== ""
                    text: raiz.contextoItem(heroCard.itemData)
                    font.pixelSize: UiTokens.fontSizeSm; color: tema.textoMuted
                    elide: Text.ElideRight; Layout.fillWidth: true
                }
            }

            // Play button
            Rectangle {
                Layout.preferredWidth: 42; Layout.preferredHeight: 42
                Layout.alignment: Qt.AlignVCenter
                radius: 21
                color: hcMouse.containsMouse ? tema.acento : Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.18)
                Behavior on color { ColorAnimation { duration: UiTokens.durationFast } }
                ThemedIcon {
                    anchors.centerIn: parent; width: 18; height: 18
                    source: "../assets/icons/play.svg"
                    iconColor: hcMouse.containsMouse ? tema.fondo : tema.acento
                }
            }
        }

        MouseArea {
            id: hcMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
            onClicked: heroCard.activated(heroCard.itemData)
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // TOP 10 EDITORIAL
    // ═══════════════════════════════════════════════════════════════════════════

    component Top10Seccion: Item {
        id: top10
        implicitHeight: alturaTotal

        readonly property int totalCanciones: estadisticas.mas_escuchadas_canciones
                                              ? Math.min(10, estadisticas.mas_escuchadas_canciones.total || 0) : 0
        readonly property int encabezadoH: 46
        readonly property int listaStart: raiz.esCompacta ? 0 : 1
        readonly property int listaCount: Math.max(0, totalCanciones - listaStart)
        readonly property int trackH: 46
        readonly property int listaHeaderH: 36
        readonly property int panelH: Math.max(300, listaHeaderH + listaCount * trackH + UiTokens.spacing16)
        readonly property int alturaTotal: encabezadoH + UiTokens.spacing12 + panelH

        ColumnLayout {
            anchors.fill: parent; spacing: UiTokens.spacing12

            SectionHeader {
                titulo: "Tu top 10 canciones"
                subtitulo: "Las que más has repetido en tu biblioteca."
                Layout.preferredHeight: top10.encabezadoH
            }

            RowLayout {
                Layout.fillWidth: true; Layout.preferredHeight: top10.panelH
                spacing: UiTokens.spacing14

                // ── SPOTLIGHT #1 — square panel so album art fills without black bars ─
                Rectangle {
                    id: spotlight
                    visible: !raiz.esCompacta && top10.totalCanciones > 0
                    // Width = height (panelH) so a square album cover fills perfectly via Crop
                    Layout.preferredWidth:  top10.panelH
                    Layout.preferredHeight: top10.panelH
                    radius: UiTokens.radiusMd; clip: true
                    color: Qt.rgba(tema.superficieAlt.r, tema.superficieAlt.g, tema.superficieAlt.b, 0.85)
                    border.color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.35)
                    border.width: 1

                    readonly property var pista0: top10.totalCanciones > 0
                                                  ? estadisticas.mas_escuchadas_canciones.obtener(0) : null

                    // Cover image — Crop: panel is square, album art is square → no black bars
                    Image {
                        anchors.fill: parent
                        source: spotlight.pista0 ? raiz.portadaPrincipal(spotlight.pista0) : ""
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true; cache: true; smooth: true
                        visible: source !== "" && status !== Image.Error
                    }

                    // Gradient overlay — theme-aware
                    Rectangle {
                        anchors.fill: parent; radius: parent.radius
                        gradient: Gradient {
                            orientation: Gradient.Vertical
                            GradientStop { position: 0.0;  color: Qt.rgba(tema.fondo.r, tema.fondo.g, tema.fondo.b, 0.08) }
                            GradientStop { position: 0.38; color: Qt.rgba(tema.fondo.r, tema.fondo.g, tema.fondo.b, 0.40) }
                            GradientStop { position: 1.0;  color: Qt.rgba(tema.fondo.r, tema.fondo.g, tema.fondo.b, 0.94) }
                        }
                    }

                    // "01" number — top-left
                    AppText {
                        anchors.top: parent.top; anchors.left: parent.left
                        anchors.topMargin: UiTokens.spacing10; anchors.leftMargin: UiTokens.spacing12
                        text: "01"
                        font.pixelSize: 72; font.weight: Font.Black
                        color: tema.acento; opacity: 0.25
                    }

                    ColumnLayout {
                        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                        anchors.leftMargin: UiTokens.spacing16; anchors.rightMargin: UiTokens.spacing16
                        anchors.bottomMargin: UiTokens.spacing16
                        spacing: UiTokens.spacing6

                        AppText {
                            text: "#1 MÁS REPRODUCIDA"
                            font.pixelSize: UiTokens.fontSizeXs; color: tema.acento; font.weight: Font.DemiBold
                        }

                        AppText {
                            text: spotlight.pista0 ? raiz.tituloItem(spotlight.pista0, "pista") : ""
                            font.pixelSize: UiTokens.fontSize2xl; font.weight: Font.Bold; color: tema.texto
                            wrapMode: Text.Wrap; maximumLineCount: 2; Layout.fillWidth: true
                        }

                        AppText {
                            text: spotlight.pista0 ? raiz.subtituloItem(spotlight.pista0, "pista") : ""
                            font.pixelSize: UiTokens.fontSizeMd; color: tema.textoSec
                            elide: Text.ElideRight; Layout.fillWidth: true
                        }

                        AppText {
                            visible: spotlight.pista0 && (spotlight.pista0.reproducciones_total || 0) > 0
                            text: (spotlight.pista0 ? (spotlight.pista0.reproducciones_total || 0) : 0) + " reproducciones"
                            font.pixelSize: UiTokens.fontSizeSm; color: tema.textoMuted
                        }

                        PrimaryButton {
                            texto: "Reproducir"
                            iconSource: "../assets/icons/play.svg"
                            Layout.topMargin: UiTokens.spacing4
                            onClicked: if (spotlight.pista0) raiz.abrirItem(spotlight.pista0, "pista")
                        }
                    }
                }

                // ── TRACK LIST ────────────────────────────────────────────────
                Rectangle {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    radius: UiTokens.radiusMd; clip: true
                    color: Qt.rgba(tema.seleccion.r, tema.seleccion.g, tema.seleccion.b, 0.55)
                    border.color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.35)
                    border.width: 1

                    ColumnLayout {
                        anchors.fill: parent; spacing: 0

                        // Header
                        Rectangle {
                            Layout.fillWidth: true; height: top10.listaHeaderH
                            color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.20)
                            radius: 0

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: UiTokens.spacing12; anchors.rightMargin: UiTokens.spacing12
                                spacing: UiTokens.spacing10

                                AppText {
                                    Layout.preferredWidth: 28; text: "#"
                                    font.pixelSize: UiTokens.fontSizeXs; color: tema.textoMuted; font.weight: Font.DemiBold
                                    horizontalAlignment: Text.AlignHCenter
                                }
                                Item { Layout.preferredWidth: 36 }
                                AppText {
                                    Layout.fillWidth: true; text: "PISTA"
                                    font.pixelSize: UiTokens.fontSizeXs; color: tema.textoMuted; font.weight: Font.DemiBold
                                }
                                AppText {
                                    visible: !raiz.esMovil
                                    Layout.preferredWidth: 60; text: "PLAYS"
                                    font.pixelSize: UiTokens.fontSizeXs; color: tema.textoMuted; font.weight: Font.DemiBold
                                    horizontalAlignment: Text.AlignRight
                                }
                                AppText {
                                    Layout.preferredWidth: 44; text: "DUR."
                                    font.pixelSize: UiTokens.fontSizeXs; color: tema.textoMuted; font.weight: Font.DemiBold
                                    horizontalAlignment: Text.AlignRight
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true; height: 1
                            color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.30)
                        }

                        // Track rows
                        Repeater {
                            model: top10.listaCount
                            delegate: TrackRow {
                                property int globalIdx: top10.listaStart + index
                                Layout.fillWidth: true
                                itemData: estadisticas.mas_escuchadas_canciones
                                          ? estadisticas.mas_escuchadas_canciones.obtener(globalIdx) : ({})
                                rankNumber: globalIdx + 1
                            }
                        }

                        Item { Layout.fillHeight: true }
                    }
                }
            }
        }
    }

    // ── TrackRow ──────────────────────────────────────────────────────────────
    component TrackRow: Rectangle {
        id: trackRow
        property var itemData: ({})
        property int rankNumber: 1
        height: 46
        color: trMouse.containsMouse
               ? Qt.rgba(tema.hover.r, tema.hover.g, tema.hover.b, 0.65)
               : "transparent"

        Behavior on color { ColorAnimation { duration: UiTokens.durationFast } }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: UiTokens.spacing12; anchors.rightMargin: UiTokens.spacing12
            spacing: UiTokens.spacing10

            AppText {
                Layout.preferredWidth: 28
                text: rankNumber < 10 ? ("0" + rankNumber) : String(rankNumber)
                font.pixelSize: UiTokens.fontSizeMd; font.weight: Font.DemiBold
                color: trMouse.containsMouse ? tema.acento : tema.textoMuted
                horizontalAlignment: Text.AlignHCenter
                Behavior on color { ColorAnimation { duration: UiTokens.durationFast } }
            }

            CoverArt {
                Layout.preferredWidth: 36; Layout.preferredHeight: 36
                Layout.alignment: Qt.AlignVCenter
                itemData: trackRow.itemData; tipo: "pista"
            }

            ColumnLayout {
                Layout.fillWidth: true; spacing: UiTokens.spacing2
                AppText {
                    text: raiz.tituloItem(trackRow.itemData, "pista")
                    font.pixelSize: UiTokens.fontSizeMd; font.weight: Font.DemiBold; color: tema.texto
                    elide: Text.ElideRight; Layout.fillWidth: true
                }
                AppText {
                    text: trackRow.itemData.artista_nombre || ""
                    font.pixelSize: UiTokens.fontSizeSm; color: tema.textoSec
                    elide: Text.ElideRight; Layout.fillWidth: true
                }
            }

            AppText {
                visible: !raiz.esMovil
                Layout.preferredWidth: 60
                text: (trackRow.itemData.reproducciones_total || 0) > 0
                      ? String(trackRow.itemData.reproducciones_total) : "—"
                font.pixelSize: UiTokens.fontSizeSm; color: tema.textoMuted; horizontalAlignment: Text.AlignRight
            }

            AppText {
                Layout.preferredWidth: 44
                text: reproductor.formatear_tiempo(trackRow.itemData.duracion_seg || 0)
                font.pixelSize: UiTokens.fontSizeSm; color: tema.textoMuted; horizontalAlignment: Text.AlignRight
            }
        }

        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            height: 1; color: Qt.rgba(tema.borde.r, tema.borde.g, tema.borde.b, 0.18)
        }

        MouseArea {
            id: trMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
            onClicked: raiz.abrirItem(trackRow.itemData, "pista")
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // LIFECYCLE
    // ═══════════════════════════════════════════════════════════════════════════

    Component.onCompleted: {
        nombre_usuario = configuracion.obtener("nombre_usuario")
        estadisticas.cargar()
        estadisticas.actualizar_saludo(nombre_usuario)
    }

    Connections {
        target: configuracion
        function onConfiguracionCambiada() {
            nombre_usuario = configuracion.obtener("nombre_usuario")
            estadisticas.actualizar_saludo(nombre_usuario)
        }
    }
}
