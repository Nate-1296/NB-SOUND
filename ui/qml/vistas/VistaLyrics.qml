import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import "../componentes"
import "../componentes/UiUtils.js" as UiUtils

Rectangle {
    id: raiz
    property var shell: null
    readonly property var tema: shell ? shell.tema : temaUi
    readonly property var pista: reproductor.pista_activa || ({})
    readonly property string semilla_base: String(pista.id || "") + "|" + String(pista.ruta_archivo || "")
    readonly property bool modo_fullscreen: !!shell && shell.reproduccion_expandida_visible
    readonly property var mood: reproductor.mood_visual || reproductor.lyrics_mood || ({})
    readonly property string letra_synced: String(reproductor.letra_synced_activa || "")
    property var lineas_sincronizadas: []
    property int indice_activo: -1
    property bool seguimiento_activo: true
    property bool usuario_desplazo_letra: false
    property bool sync_forzado: false
    property bool mostrar_cta_sync: false
    readonly property int transicion_verso_ms: 280
    readonly property int transicion_scroll_verso_ms: 360
    readonly property real altura_barra_reproduccion: shell ? shell.altura_barra_reproduccion : 94
    readonly property real ventana_visible_inicio_ratio: modo_fullscreen ? 0.15 : 0.18
    readonly property real ventana_visible_fin_ratio: modo_fullscreen ? 0.72 : 0.78
    readonly property real hue_base: _normalizar01(mood.h, (((_hashCadena(semilla_base) % 360) + 360) % 360) / 360.0)
    readonly property real saturacion_base: Math.max(0.32, Math.min(0.72, Number(mood.s || 0.48)))
    readonly property real luminosidad_base: Math.max(0.14, Math.min(0.34, Number(mood.l || 0.20)))
    color: _tonoMonocromo(0, 1.0)

    function _hashCadena(texto) {
        var base = texto || "nbsound-lyrics"
        var hash = 0
        for (var i = 0; i < base.length; ++i) {
            hash = ((hash * 31) + base.charCodeAt(i)) & 0x7fffffff
        }
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

    function _tonoMonocromo(offset, alpha) {
        var lightness = luminosidad_base + (offset * 0.085)
        return Qt.hsla(hue_base, saturacion_base, Math.max(0.10, Math.min(0.46, lightness)), alpha)
    }

    function _valorSemilla(indice) {
        var hash = _hashCadena(semilla_base + "|" + indice)
        return (hash % 1000) / 1000.0
    }

    function _limpiar_linea_lyrics(linea) {
        var limpia = String(linea || "").trim()
        if (limpia === "")
            return ""
        var corte = limpia.indexOf("^")
        if (corte >= 0)
            limpia = limpia.slice(0, corte).trim()
        return limpia
    }

    function _parsear_letra_sincronizada(letra) {
        var salida = []
        if (!letra || letra === "")
            return salida

        var lineas = String(letra).split("\n")
        var regex = /\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]/g

        for (var i = 0; i < lineas.length; ++i) {
            var lineaOriginal = String(lineas[i])
            var textoLimpio = _limpiar_linea_lyrics(lineaOriginal.replace(regex, ""))
            regex.lastIndex = 0

            var huboMarca = false
            var match
            while ((match = regex.exec(lineaOriginal)) !== null) {
                var minutos = parseInt(match[1], 10)
                var segundos = parseInt(match[2], 10)
                var centesimas = match[3] ? parseInt(match[3], 10) : 0
                if (isNaN(minutos) || isNaN(segundos))
                    continue
                var divisor = match[3] ? Math.pow(10, match[3].length) : 1
                var marca = (minutos * 60) + segundos + (centesimas / divisor)
                salida.push({ "t": marca, "text": textoLimpio })
                huboMarca = true
            }

            if (!huboMarca && textoLimpio !== "") {
                // Línea válida pero sin timestamp; se conserva como fallback
                // al final de parseo si no hubo ninguna marca válida.
                salida.push({ "t": -1, "text": textoLimpio })
            }
        }

        var conTiempo = []
        for (var k = 0; k < salida.length; ++k) {
            if (salida[k].t >= 0 && salida[k].text !== "")
                conTiempo.push(salida[k])
        }
        conTiempo.sort(function(a, b) { return a.t - b.t })
        return conTiempo
    }

    function _reconstruir_sync() {
        lineas_sincronizadas = _parsear_letra_sincronizada(letra_synced)
        indice_activo = -1
        _actualizar_linea_activa(true)
    }

    function _resolver_indice_activo(posicionSeg) {
        var lineas = lineas_sincronizadas || []
        if (lineas.length === 0)
            return -1

        if (posicionSeg <= lineas[0].t)
            return 0

        var izq = 0
        var der = lineas.length - 1
        var mejor = 0
        while (izq <= der) {
            var mid = Math.floor((izq + der) / 2)
            if (lineas[mid].t <= posicionSeg) {
                mejor = mid
                izq = mid + 1
            } else {
                der = mid - 1
            }
        }
        return mejor
    }

    function _auto_scroll_hacia_activa(forzado) {
        if (!seguimiento_activo && !forzado)
            return
        if (indice_activo < 0 || lista_sync.count === 0)
            return
        _activar_sync_forzado()
        lista_sync.positionViewAtIndex(indice_activo, ListView.Center)
    }

    function _ventana_usuario_metrica() {
        var yBase = lista_sync.height * ventana_visible_inicio_ratio
        var finCentral = lista_sync.height * ventana_visible_fin_ratio
        var finSeguroBarra = lista_sync.height - altura_barra_reproduccion - (modo_fullscreen ? 32 : 24)
        var yFin = Math.min(finCentral, finSeguroBarra)
        if (yFin <= yBase)
            yFin = Math.min(lista_sync.height - 36, yBase + 96)
        return {
            "y": yBase,
            "height": Math.max(72, yFin - yBase)
        }
    }

    function _verso_activo_en_ventana_usuario(margen) {
        if (indice_activo < 0 || !lista_sync || lista_sync.count === 0)
            return false
        var item = lista_sync.itemAtIndex(indice_activo)
        if (!item || !item.textoItem)
            return false

        var margenReal = Math.max(0, Number(margen || 0))
        var textoAncho = Math.max(1, item.textoItem.paintedWidth || item.textoItem.width)
        var textoAlto = Math.max(1, item.textoItem.paintedHeight || item.textoItem.height)
        var insetX = Math.max(0, (item.textoItem.width - textoAncho) * 0.5)
        var insetY = Math.max(0, (item.textoItem.height - textoAlto) * 0.5)
        var topLeft = item.textoItem.mapToItem(ventana_sync_usuario, insetX, insetY)
        var bottomRight = item.textoItem.mapToItem(ventana_sync_usuario, insetX + textoAncho, insetY + textoAlto)
        var centro = item.textoItem.mapToItem(ventana_sync_usuario, item.textoItem.width * 0.5, item.textoItem.height * 0.5)
        var overlapHeight = Math.min(bottomRight.y, ventana_sync_usuario.height - margenReal) - Math.max(topLeft.y, margenReal)
        var overlapWidth = Math.min(bottomRight.x, ventana_sync_usuario.width) - Math.max(topLeft.x, 0)
        var ratioVisible = overlapHeight / textoAlto

        return centro.x >= 0
                && centro.x <= ventana_sync_usuario.width
                && centro.y >= margenReal
                && centro.y <= (ventana_sync_usuario.height - margenReal)
                && overlapHeight >= Math.max(24, textoAlto * 0.58)
                && overlapWidth >= Math.max(40, textoAncho * 0.38)
                && ratioVisible >= 0.58
    }

    function _hay_desalineacion_visible() {
        if (!contenedor_sync.visible || indice_activo < 0)
            return false
        return !_verso_activo_en_ventana_usuario(18)
    }

    function _actualizar_visibilidad_cta_sync() {
        if (!_hay_desalineacion_visible()) {
            mostrar_cta_sync = false
            retraso_cta_sync.stop()
            return
        }
        if (!mostrar_cta_sync && !retraso_cta_sync.running)
            retraso_cta_sync.start()
    }

    function _actualizar_linea_activa(forzado) {
        var nuevo = _resolver_indice_activo(reproductor.posicion_seg || 0)
        if (!forzado && usuario_desplazo_letra) {
            indice_activo = nuevo
            seguimiento_activo = false
            _actualizar_visibilidad_cta_sync()
            return
        }
        if (!forzado && nuevo === indice_activo) {
            _actualizar_visibilidad_cta_sync()
            return
        }
        indice_activo = nuevo
        if (forzado) {
            seguimiento_activo = true
            usuario_desplazo_letra = false
            _auto_scroll_hacia_activa(true)
        } else if (seguimiento_activo) {
            _auto_scroll_hacia_activa(false)
        }
        _actualizar_visibilidad_cta_sync()
    }

    function _activar_sync_forzado() {
        sync_forzado = true
        liberar_sync_forzado.restart()
    }

    function _sincronizar_a_verso(indice) {
        _activar_sync_forzado()
        seguimiento_activo = true
        usuario_desplazo_letra = false
        indice_activo = indice
        lista_sync.positionViewAtIndex(indice, ListView.Center)
        mostrar_cta_sync = false
        retraso_cta_sync.stop()
    }

    Timer {
        id: liberar_sync_forzado
        interval: 420
        repeat: false
        onTriggered: raiz.sync_forzado = false
    }

    Canvas {
        id: manchas_fondo
        anchors.fill: parent
        opacity: 0.74
        antialiasing: true
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Connections {
            target: raiz
            function onHue_baseChanged() { manchas_fondo.requestPaint() }
            function onSaturacion_baseChanged() { manchas_fondo.requestPaint() }
            function onLuminosidad_baseChanged() { manchas_fondo.requestPaint() }
        }
        onPaint: {
            var ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            if (width <= 0 || height <= 0)
                return

            for (var i = 0; i < 8; ++i) {
                var semX = raiz._valorSemilla(i * 5 + 1)
                var semY = raiz._valorSemilla(i * 5 + 2)
                var semR = raiz._valorSemilla(i * 5 + 3)
                var columna = i % 4
                var fila = Math.floor(i / 4)
                var baseX = ((columna + 0.5) / 4.0) * width
                var baseY = ((fila + 0.5) / 2.0) * height
                var cx = baseX + ((semX - 0.5) * width * 0.24)
                var cy = baseY + ((semY - 0.5) * height * 0.20)
                var radio = (Math.min(width, height) * 0.18) + (semR * Math.min(width, height) * 0.24)
                var grad = ctx.createRadialGradient(cx, cy, radio * 0.12, cx, cy, radio * 1.15)
                var alphaCentro = 0.16 + (raiz._valorSemilla(i * 5 + 4) * 0.12)
                grad.addColorStop(0.0, Qt.rgba(raiz._tonoMonocromo(2, 1.0).r, raiz._tonoMonocromo(2, 1.0).g, raiz._tonoMonocromo(2, 1.0).b, alphaCentro))
                grad.addColorStop(0.68, Qt.rgba(raiz._tonoMonocromo(1, 1.0).r, raiz._tonoMonocromo(1, 1.0).g, raiz._tonoMonocromo(1, 1.0).b, alphaCentro * 0.30))
                grad.addColorStop(1.0, Qt.rgba(raiz._tonoMonocromo(0, 1.0).r, raiz._tonoMonocromo(0, 1.0).g, raiz._tonoMonocromo(0, 1.0).b, 0))
                ctx.fillStyle = grad
                ctx.beginPath()
                for (var p = 0; p < 7; ++p) {
                    var ang = (Math.PI * 2 * p) / 7
                    var dist = radio * (0.78 + (raiz._valorSemilla((i * 11) + p) * 0.36))
                    var px = cx + Math.cos(ang) * dist
                    var py = cy + Math.sin(ang) * dist
                    if (p === 0)
                        ctx.moveTo(px, py)
                    else
                        ctx.lineTo(px, py)
                }
                ctx.closePath()
                ctx.fill()
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        color: raiz._tonoMonocromo(-1, 0.34)
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: modo_fullscreen
                         ? (raiz.width < 1100 ? 28 : 48)
                         : (raiz.width < 900 ? 24 : 36)
        spacing: modo_fullscreen ? 18 : 14

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: modo_fullscreen ? 54 : 46

            Button {
                id: boton_volver_lyrics
                visible: !modo_fullscreen
                Layout.preferredWidth: visible ? 40 : 0
                Layout.preferredHeight: visible ? 40 : 0
                Layout.minimumWidth: 0
                Layout.maximumWidth: visible ? 40 : 0
                Layout.alignment: Qt.AlignVCenter
                focusPolicy: Qt.StrongFocus
                hoverEnabled: true
                text: ""
                icon.source: "../assets/icons/back.svg"
                icon.width: 20
                icon.height: 20
                readonly property bool presionado_visual: down && hovered
                icon.color: presionado_visual ? UiUtils.veloClaro(1.0) : (hovered ? UiUtils.veloClaro(0.96) : UiUtils.veloClaro(0.84))
                scale: presionado_visual ? 0.96 : (hovered ? 1.04 : 1.0)
                Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutQuad } }
                background: Rectangle {
                    radius: UiTokens.radiusPill
                    color: boton_volver_lyrics.presionado_visual
                           ? UiUtils.veloClaro(0.18)
                           : (boton_volver_lyrics.hovered
                              ? UiUtils.veloClaro(0.12)
                              : "transparent")
                    border.width: boton_volver_lyrics.presionado_visual || boton_volver_lyrics.activeFocus ? 1 : 0
                    border.color: UiUtils.veloClaro(boton_volver_lyrics.presionado_visual ? 0.36 : 0.22)
                }
                onCanceled: focus = false
                onReleased: if (!hovered) focus = false
                onClicked: {
                    if (shell)
                        shell.cerrar_vista_lyrics()
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1
                AppText {
                    text: pista.titulo || reproductor.titulo_activo || "Sin reproducción activa"
                    color: raiz.tema.textoInmersivo
                    font.pixelSize: modo_fullscreen ? (raiz.width < 1100 ? 21 : 24) : (raiz.width < 900 ? 16 : 18)
                    font.bold: true
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                AppText {
                    text: pista.artista_nombre || reproductor.artista_activo || "Artista"
                    color: UiUtils.veloClaro(0.88)
                    font.pixelSize: modo_fullscreen ? 15 : 12
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            Item {
                width: parent.width
                implicitHeight: Math.max(contenedor_sync.implicitHeight + 24, parent.height)

                Item {
                    id: contenedor_sync
                    anchors.fill: parent
                    visible: raiz.lineas_sincronizadas.length > 0

                    Item {
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.left: parent.left
                        width: Math.max(64, parent.width * 0.08)
                        clip: true
                        z: 1
                        visible: false
                        opacity: 0.0

                        Rectangle {
                            width: parent.width * 1.8
                            height: parent.height
                            x: -width * 0.45
                            color: "transparent"
                            gradient: Gradient {
                                GradientStop { position: 0.0; color: UiUtils.veloClaro(0.0) }
                                GradientStop { position: 0.45; color: UiUtils.veloClaro(0.13) }
                                GradientStop { position: 1.0; color: UiUtils.veloClaro(0.0) }
                            }
                            SequentialAnimation on y {
                                loops: Animation.Infinite
                                running: contenedor_sync.visible
                                NumberAnimation { from: -24; to: 18; duration: 2300; easing.type: Easing.InOutSine }
                                NumberAnimation { from: 18; to: -24; duration: 2300; easing.type: Easing.InOutSine }
                            }
                        }
                    }

                    Item {
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.right: parent.right
                        width: Math.max(64, parent.width * 0.08)
                        clip: true
                        z: 1
                        visible: false
                        opacity: 0.0

                        Rectangle {
                            width: parent.width * 1.8
                            height: parent.height
                            x: -width * 0.35
                            color: "transparent"
                            gradient: Gradient {
                                GradientStop { position: 0.0; color: UiUtils.veloClaro(0.0) }
                                GradientStop { position: 0.55; color: UiUtils.veloClaro(0.12) }
                                GradientStop { position: 1.0; color: UiUtils.veloClaro(0.0) }
                            }
                            SequentialAnimation on y {
                                loops: Animation.Infinite
                                running: contenedor_sync.visible
                                NumberAnimation { from: 18; to: -26; duration: 2600; easing.type: Easing.InOutSine }
                                NumberAnimation { from: -26; to: 18; duration: 2600; easing.type: Easing.InOutSine }
                            }
                        }
                    }

                    ListView {
                        id: lista_sync
                        anchors.fill: parent
                        anchors.leftMargin: modo_fullscreen ? (raiz.width < 1100 ? 20 : 34) : (raiz.width < 900 ? 6 : 14)
                        anchors.rightMargin: anchors.leftMargin
                        model: raiz.lineas_sincronizadas
                        spacing: modo_fullscreen ? 18 : 12
                        clip: true
                        interactive: true
                        reuseItems: true
                        cacheBuffer: 640
                        boundsBehavior: Flickable.StopAtBounds
                        topMargin: Math.max(0, height * 0.5 - (modo_fullscreen ? (raiz.width < 1200 ? 74 : 92) : (raiz.width < 980 ? 54 : 68)))
                        bottomMargin: topMargin
                        currentIndex: -1
                        highlightFollowsCurrentItem: false
                        highlightRangeMode: ListView.NoHighlightRange

                        Item {
                            id: ventana_sync_usuario
                            visible: false
                            z: 4
                            x: 0
                            width: lista_sync.width
                            y: raiz._ventana_usuario_metrica().y
                            height: raiz._ventana_usuario_metrica().height
                        }

                        Behavior on contentY {
                            enabled: !lista_sync.dragging && !lista_sync.flicking
                            NumberAnimation {
                                duration: raiz.transicion_scroll_verso_ms
                                easing.type: Easing.InOutCubic
                            }
                        }

                        onMovementStarted: {
                            if (!raiz.sync_forzado) {
                                raiz.seguimiento_activo = false
                                raiz.usuario_desplazo_letra = true
                            }
                            raiz._actualizar_visibilidad_cta_sync()
                        }
                        onMovementEnded: {
                            raiz._actualizar_visibilidad_cta_sync()
                        }
                        onContentYChanged: raiz._actualizar_visibilidad_cta_sync()

                        delegate: Item {
                            required property var modelData
                            required property int index
                            property alias textoItem: texto_linea
                            readonly property int distancia: Math.abs(index - raiz.indice_activo)
                            readonly property bool esActual: index === raiz.indice_activo
                            readonly property bool esPasada: index < raiz.indice_activo
                            readonly property real proximidad: Math.max(0, 1 - (distancia / 6))
                            readonly property real escalaBase: esActual
                                                               ? 1.15
                                                               : (esPasada
                                                                  ? (0.80 + (proximidad * 0.10))
                                                                  : (0.78 + (proximidad * 0.11)))
                            width: lista_sync.width
                            implicitHeight: Math.max(texto_linea.implicitHeight + 26, raiz.width < 980 ? 62 : 76)

                            AppText {
                                id: texto_linea
                                anchors.centerIn: parent
                                width: Math.min(parent.width, modo_fullscreen ? (raiz.width < 1200 ? 980 : 1120) : (raiz.width < 980 ? 860 : 980))
                                text: modelData.text || ""
                                wrapMode: Text.Wrap
                                horizontalAlignment: Text.AlignHCenter
                                transformOrigin: Item.Center
                                font.pixelSize: modo_fullscreen ? (raiz.width < 1200 ? 42 : 54) : (raiz.width < 980 ? 35 : 45)
                                font.weight: esActual ? Font.Bold : Font.DemiBold
                                maximumLineCount: 3
                                elide: Text.ElideRight
                                lineHeight: 1.20
                                color: {
                                    if (raiz.indice_activo < 0)
                                        return UiUtils.veloClaro(0.90)
                                    if (esActual)
                                        return raiz.tema.textoInmersivo
                                    if (esPasada)
                                        return UiUtils.veloClaro(Math.max(0.38, 0.72 - (Math.min(distancia, 8) * 0.055)))
                                    return UiUtils.veloClaro(Math.max(0.32, 0.66 - (Math.min(distancia, 8) * 0.06)))
                                }
                                scale: escalaBase * (click_linea.containsPress ? 0.985 : (click_linea.containsMouse ? 1.015 : 1.0))
                                Behavior on scale {
                                    NumberAnimation { duration: raiz.transicion_verso_ms; easing.type: Easing.OutCubic }
                                }
                                Behavior on color {
                                    ColorAnimation { duration: raiz.transicion_verso_ms; easing.type: Easing.OutCubic }
                                }
                            }

                            MouseArea {
                                id: click_linea
                                anchors.centerIn: texto_linea
                                width: Math.min(texto_linea.width, texto_linea.paintedWidth + 12)
                                height: Math.min(texto_linea.height, texto_linea.paintedHeight + 10)
                                acceptedButtons: Qt.LeftButton
                                hoverEnabled: true
                                preventStealing: false
                                cursorShape: modelData.t >= 0 ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: {
                                    if (modelData.t >= 0) {
                                        reproductor.buscar_posicion(modelData.t)
                                        raiz._sincronizar_a_verso(index)
                                    }
                                }
                                onCanceled: {}
                            }
                        }
                    }

                    Timer {
                        id: retraso_cta_sync
                        interval: 650
                        repeat: false
                        onTriggered: raiz.mostrar_cta_sync = raiz._hay_desalineacion_visible()
                    }
                }

                AppText {
                    id: lyricsTextFallback
                    anchors.centerIn: parent
                    width: Math.min(parent.width, modo_fullscreen ? 1120 : 980)
                    visible: !contenedor_sync.visible
                    text: "¡Lo sentimos! No hemos encontrado una letra para esta canción."
                    color: raiz.tema.textoInmersivo
                    opacity: 0.80
                    font.pixelSize: modo_fullscreen ? (raiz.width < 1200 ? 42 : 54) : (raiz.width < 980 ? 36 : 46)
                    font.weight: Font.DemiBold
                    lineHeight: 1.24
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                }
            }
        }

    }

    Button {
        id: boton_sync_lyrics
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: modo_fullscreen ? (raiz.width < 1100 ? 28 : 44) : (raiz.width < 900 ? 24 : 40)
        anchors.bottomMargin: raiz.altura_barra_reproduccion + (modo_fullscreen ? 26 : (raiz.width < 900 ? 14 : 20))
        implicitWidth: contenido_sync_lyrics.implicitWidth + 34
        width: Math.min(raiz.width - (anchors.rightMargin * 2), implicitWidth)
        height: 44
        visible: opacity > 0.01
        opacity: raiz.mostrar_cta_sync ? 1.0 : 0.0
        scale: raiz.mostrar_cta_sync ? 1.0 : 0.96
        enabled: raiz.mostrar_cta_sync
        focusPolicy: Qt.StrongFocus
        hoverEnabled: true
        text: "Sincronizar con la letra"
        font.pixelSize: UiTokens.fontSizeLg
        font.weight: Font.DemiBold
        icon.source: "../assets/icons/sync.svg"
        icon.width: 18
        icon.height: 18
        icon.color: raiz.tema.textoInmersivo
        display: AbstractButton.TextBesideIcon
        z: 4
        Behavior on opacity { NumberAnimation { duration: 150; easing.type: Easing.OutQuad } }
        Behavior on scale { NumberAnimation { duration: 150; easing.type: Easing.OutQuad } }
        background: Rectangle {
            radius: height / 2
            color: boton_sync_lyrics.down
                   ? raiz._tonoMonocromo(2, 0.86)
                   : (boton_sync_lyrics.hovered || boton_sync_lyrics.activeFocus
                      ? raiz._tonoMonocromo(2, 0.76)
                      : raiz._tonoMonocromo(1, 0.66))
            border.width: 1
            border.color: Qt.hsla(raiz.hue_base, raiz.saturacion_base, Math.min(0.58, raiz.luminosidad_base + 0.30), 0.64)
        }
        contentItem: Item {
            anchors.fill: parent
            Row {
                id: contenido_sync_lyrics
                anchors.centerIn: parent
                spacing: UiTokens.spacing8
                Image {
                    anchors.verticalCenter: parent.verticalCenter
                    source: boton_sync_lyrics.icon.source
                    sourceSize.width: 18
                    sourceSize.height: 18
                    width: 18
                    height: 18
                    opacity: boton_sync_lyrics.down ? 1.0 : 0.92
                }
                AppText {
                    anchors.verticalCenter: parent.verticalCenter
                    text: boton_sync_lyrics.text
                    color: raiz.tema.textoInmersivo
                    font: boton_sync_lyrics.font
                    elide: Text.ElideRight
                    maximumLineCount: 1
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
        onClicked: {
            raiz._activar_sync_forzado()
            raiz.seguimiento_activo = true
            raiz.usuario_desplazo_letra = false
            raiz._actualizar_linea_activa(true)
            raiz.mostrar_cta_sync = false
        }
    }

    onSemilla_baseChanged: {
        manchas_fondo.requestPaint()
        _reconstruir_sync()
        _actualizar_visibilidad_cta_sync()
    }
    onHue_baseChanged: manchas_fondo.requestPaint()
    onSaturacion_baseChanged: manchas_fondo.requestPaint()
    onLuminosidad_baseChanged: manchas_fondo.requestPaint()
    onLetra_syncedChanged: {
        _reconstruir_sync()
        _actualizar_visibilidad_cta_sync()
    }
    onIndice_activoChanged: _actualizar_visibilidad_cta_sync()

    Connections {
        target: reproductor
        function onProgresoCambiado() {
            raiz._actualizar_linea_activa(false)
        }
        function onPista_activaCambiada() {
            raiz.seguimiento_activo = true
            raiz.usuario_desplazo_letra = false
            raiz._reconstruir_sync()
        }
        function onLetraActivaCambiada() {
            raiz.seguimiento_activo = true
            raiz.usuario_desplazo_letra = false
            raiz._reconstruir_sync()
        }
    }

    Component.onCompleted: {
        manchas_fondo.requestPaint()
        _reconstruir_sync()
    }
}
