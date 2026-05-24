import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects

import "../componentes"

// =============================================================================
// DjSesionActiva
//
// Vista contextual cuando hay una sesion construida o reproduciendose.
//
// Estructura:
//   1) Reproductor DJ propio (no es un now-playing tradicional: no muestra
//      portada/album, muestra prompt + posicion en sesion + transicion en vivo).
//   2) Timeline visual horizontal (curva de energia + bloques) -> sensacion
//      de "construccion musical" mas que "lista de canciones".
//   3) Lista detallada de pistas con razones, transiciones y acciones.
// =============================================================================

Rectangle {
    id: raiz
    color: "transparent"

    required property var tema
    property var shell: null
    required property var formatDur
    required property var formatFecha
    required property real aW
    required property bool cW
    required property bool mW
    required property bool wW

    signal abrirGuardar()
    signal abrirHistorial()
    signal abrirConstruir()

    // Tick de actualizacion local para los relojes (la senal de progreso del
    // modelo llega ~5Hz, pero queremos animar el avance del slider sin
    // necesidad de hacer binding directo al QVariant float).
    readonly property real _pos: djPrivado.dj_pos_sesion_seg
    readonly property real _dur: djPrivado.dj_dur_sesion_seg
    readonly property real _pos_pista: djPrivado.dj_pos_pista_seg
    readonly property real _dur_pista: djPrivado.dj_dur_pista_seg
    readonly property var  _trans:    djPrivado.dj_transicion_activa
    readonly property bool _transicionando: djPrivado.dj_transicionando
    readonly property int  _idx:     djPrivado.dj_indice_actual

    // Estado de drag sobre la barra de progreso: mientras el usuario arrastra,
    // el slider muestra el preview en vez del valor real para que no se sienta
    // que la barra "lucha" con el cabezal mientras se mueve.
    property bool _progreso_drag_activo: false
    property real _progreso_preview_ratio: 0.0
    readonly property real _progreso_ratio_real: _dur > 0 ? Math.max(0, Math.min(1, _pos / _dur)) : 0.0
    readonly property bool _hay_reproduccion: djPrivado.dj_reproduciendo || djPrivado.dj_pausado
                                              || djPrivado.dj_transicionando
                                              || (_idx >= 0 && djPrivado.pistas_planificadas.total > 0)

    function _titulo_pista(t) {
        // En esta app las pistas siempre tienen título; el fallback "—" solo
        // existe para defender contra estados antes de que se cargue el modelo.
        if (!t) return "—"
        var titulo = String(t.titulo || "").trim()
        return titulo.length > 0 ? titulo : "—"
    }
    function _nombre_pista_actual() {
        var i = djPrivado.dj_indice_actual
        if (i < 0) return "—"
        var t = djPrivado.pistas_planificadas.obtener(i)
        if (!t) return "—"
        var titulo = _titulo_pista(t)
        var artista = String(t.artista || "").trim()
        return artista ? (titulo + " — " + artista) : titulo
    }
    function _nombre_pista_siguiente() {
        if (!djPrivado.dj_transicionando) return ""
        var idx_b = (_trans && _trans.idx_b !== undefined) ? _trans.idx_b : -1
        if (idx_b < 0) return ""
        var t = djPrivado.pistas_planificadas.obtener(idx_b)
        if (!t) return ""
        var titulo = _titulo_pista(t)
        var artista = String(t.artista || "").trim()
        return artista ? (titulo + " — " + artista) : titulo
    }
    // Color base de cada fase narrativa, en formato sólido (alpha 1.0).
    // Las funciones de uso aplican alpha según el contexto: banda de fondo,
    // barra de la curva o indicador discreto.
    function _color_fase_rgb(nombre) {
        switch (String(nombre)) {
            case "warmup":   return Qt.rgba(0.30, 0.55, 0.85, 1.0)  // azul sereno
            case "groove":   return Qt.rgba(0.35, 0.75, 0.50, 1.0)  // verde groove
            case "peak":     return Qt.rgba(0.95, 0.55, 0.25, 1.0)  // naranja climax
            case "release":  return Qt.rgba(0.85, 0.45, 0.65, 1.0)  // rosa descenso
            case "cooldown": return Qt.rgba(0.50, 0.45, 0.75, 1.0)  // morado cierre
            default:          return Qt.rgba(0.5, 0.5, 0.5, 1.0)
        }
    }
    function _color_fase(nombre) {
        // Banda translúcida sobre el timeline para indicar fase narrativa.
        var c = _color_fase_rgb(nombre)
        return Qt.rgba(c.r, c.g, c.b, 0.10)
    }
    function _color_barra_fase(nombre, score) {
        // Barras de la curva: usan el color de su fase pero con intensidad
        // modulada por su score (energía). Así, las dos capas son coherentes
        // visualmente sin saturar.
        var c = _color_fase_rgb(nombre)
        var s = (score === undefined || score === null) ? 0.5 : Math.max(0.0, Math.min(1.0, score))
        var alpha = 0.55 + s * 0.30
        return Qt.rgba(c.r, c.g, c.b, alpha)
    }
    function _fase_en_t(t) {
        // Devuelve el nombre de la fase para un t∈[0,1]. Cadena vacía si
        // no hay perfil narrativo cargado.
        var perfil = djPrivado.resumen ? djPrivado.resumen.perfil_narrativo : null
        if (!perfil || perfil.length === 0) return ""
        if (t <= 0) return perfil[0].name
        if (t >= 1) return perfil[perfil.length - 1].name
        for (var i = 0; i < perfil.length; i++) {
            var f = perfil[i]
            if (t >= (f.start_t || 0) && t < (f.end_t || 1)) return f.name
        }
        return perfil[perfil.length - 1].name
    }
    function _label_fase(nombre) {
        switch (String(nombre)) {
            case "warmup":   return "apertura"
            case "groove":   return "ritmo"
            case "peak":     return "climax"
            case "release":  return "descenso"
            case "cooldown": return "cierre"
            default:          return String(nombre)
        }
    }
    function _frase_fase(nombre) {
        // Frase humana de lo que pasa en cada fase: orientada al usuario,
        // no al motor. Si la sesión todavía no arrancó, devuelve "".
        switch (String(nombre)) {
            case "warmup":   return "Apertura: presentando el clima"
            case "groove":   return "Ya entraste en calor, ahora viene lo bueno"
            case "peak":     return "Estás en el clímax de la sesión"
            case "release":  return "Bajando del pico, dejando respirar"
            case "cooldown": return "Cerrando con calma"
            default:          return ""
        }
    }
    function _fase_actual_descripcion() {
        var perfil = djPrivado.resumen ? djPrivado.resumen.perfil_narrativo : null
        if (!perfil || perfil.length === 0) return ""
        if (djPrivado.dj_dur_sesion_seg <= 0) return ""
        var t = Math.max(0, Math.min(1, djPrivado.dj_pos_sesion_seg / djPrivado.dj_dur_sesion_seg))
        for (var i = 0; i < perfil.length; i++) {
            var f = perfil[i]
            if (t >= (f.start_t || 0) && t < (f.end_t || 1)) {
                return _frase_fase(f.name)
            }
        }
        var ultima = perfil[perfil.length - 1]
        return _frase_fase(ultima.name)
    }

    // Empty state: la sesión está cerrada o aún no se ha construido. La
    // tab "En sesión" sigue accesible pero muestra un mensaje claro sobre
    // qué hacer a continuación.
    readonly property bool _hay_sesion_visible: djPrivado.pistas_planificadas.total > 0
    Item {
        anchors.fill: parent
        visible: !raiz._hay_sesion_visible
        EmptyState {
            anchors.centerIn: parent
            width: Math.min(parent.width - UiTokens.spacing32, 440)
            tema: raiz.tema
            title: "No hay sesión activa"
            description: "Cuando cierras una sesión la UI vuelve aquí. Puedes abrir una guardada desde Historial o crear una nueva en Construir."
            iconSource: "../assets/icons/nav/dj_privado.svg"
        }
        RowLayout {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: UiTokens.spacing32
            spacing: UiTokens.spacing10

            Rectangle {
                implicitWidth: 180; implicitHeight: 38; radius: 19
                color: ma_construir.containsMouse ? raiz.tema.acentoFuerte : raiz.tema.acento
                AppText {
                    anchors.centerIn: parent
                    text: "Construir una sesión"
                    color: raiz.tema.textoSobreAcento
                    font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold
                }
                MouseArea {
                    id: ma_construir
                    anchors.fill: parent; hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: raiz.abrirConstruir()
                }
            }
            Rectangle {
                implicitWidth: 180; implicitHeight: 38; radius: 19
                color: ma_historial.containsMouse ? raiz.tema.hover : raiz.tema.superficieAlt
                border.color: raiz.tema.borde; border.width: 1
                AppText {
                    anchors.centerIn: parent
                    text: "Abrir desde historial"
                    color: raiz.tema.texto
                    font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold
                }
                MouseArea {
                    id: ma_historial
                    anchors.fill: parent; hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: raiz.abrirHistorial()
                }
            }
        }
    }

    ScrollView {
        id: _dj_sesion_scroll
        anchors.fill: parent
        clip: true
        visible: raiz._hay_sesion_visible
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical: AppScrollBar {
            parent: _dj_sesion_scroll
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            z: 20
            tema: raiz.tema
            policy: _dj_sesion_scroll.contentHeight > _dj_sesion_scroll.height + 2 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
        }
        contentWidth: availableWidth

        ColumnLayout {
            width: parent.width
            spacing: UiTokens.spacing12

            // ── REPRODUCTOR DJ PROPIO ────────────────────────────────
            AppCard {
                Layout.fillWidth: true
                tema: raiz.tema
                padding: UiTokens.spacing16

                // Cabecera: estado + prompt + posicion
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12
                    // Indicador de estado (animado cuando transiciona)
                    Rectangle {
                        Layout.preferredWidth: 12
                        Layout.preferredHeight: 12
                        radius: 6
                        color: {
                            switch (djPrivado.estado_dj) {
                                case "reproduciendo":  return raiz.tema.exito
                                case "transicionando": return raiz.tema.acento
                                case "pausado":        return raiz.tema.advertencia
                                case "finalizado":    return raiz.tema.textoMuted
                                case "error":          return raiz.tema.peligro
                                default:                return raiz.tema.textoMuted
                            }
                        }
                        SequentialAnimation on opacity {
                            running: djPrivado.estado_dj === "reproduciendo" || djPrivado.estado_dj === "transicionando"
                            loops: Animation.Infinite
                            NumberAnimation { from: 1.0; to: 0.35; duration: 800; easing.type: Easing.InOutQuad }
                            NumberAnimation { from: 0.35; to: 1.0; duration: 800; easing.type: Easing.InOutQuad }
                        }
                    }
                    ColumnLayout {
                        spacing: UiTokens.spacing2
                        Layout.fillWidth: true; Layout.minimumWidth: 0
                        AppText {
                            text: {
                                switch (djPrivado.estado_dj) {
                                    case "reproduciendo":  return "En reproducción"
                                    case "transicionando": return "Mezclando…"
                                    case "pausado":        return "Pausado"
                                    case "preparando":     return "Preparando…"
                                    case "finalizado":    return "Sesión completa"
                                    case "error":          return "Error en sesión"
                                    default:                return "Sesión construida"
                                }
                            }
                            color: raiz.tema.texto
                            font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold
                        }
                        AppText {
                            text: djPrivado.intent && djPrivado.intent.prompt
                                  ? "“" + djPrivado.intent.prompt + "”"
                                  : ""
                            color: raiz.tema.textoMuted
                            font.pixelSize: UiTokens.fontSizeSm; elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                            Layout.fillWidth: true
                        }
                    }
                    // Chip persistente con la técnica de mezcla activa.
                    // Aparece SOLO durante una transición y desaparece al
                    // terminar. Texto siempre humano (etiqueta_ui del backend).
                    Rectangle {
                        visible: !!(djPrivado.dj_transicionando && raiz._trans
                                    && raiz._trans.etiqueta_ui)
                        implicitHeight: 22
                        implicitWidth: tecnica_chip_lbl.implicitWidth + 18
                        radius: 11
                        color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.16)
                        border.color: raiz.tema.acento
                        border.width: 1
                        AppText {
                            id: tecnica_chip_lbl
                            anchors.centerIn: parent
                            text: raiz._trans ? (raiz._trans.etiqueta_ui || "") : ""
                            color: raiz.tema.acento
                            font.pixelSize: UiTokens.fontSizeSm
                            font.weight: Font.DemiBold
                        }
                        SequentialAnimation on opacity {
                            running: parent.visible
                            loops: Animation.Infinite
                            NumberAnimation { from: 1.0; to: 0.6; duration: 900; easing.type: Easing.InOutQuad }
                            NumberAnimation { from: 0.6; to: 1.0; duration: 900; easing.type: Easing.InOutQuad }
                        }
                    }
                    StatusBadge {
                        tema: raiz.tema
                        visible: !!(djPrivado.resumen && djPrivado.resumen.total_pistas)
                        text: (djPrivado.resumen.total_pistas || 0) + " pistas · " + raiz.formatDur(djPrivado.resumen.duracion_seg || 0)
                        tone: "neutral"
                        compact: true
                        maxTextWidth: 180
                    }
                }

                // Pista actual + siguiente (en transicion)
                Item {
                    Layout.fillWidth: true
                    implicitHeight: 64

                    // Pista actual
                    ColumnLayout {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: UiTokens.spacing4
                        AppText {
                            id: now_playing
                            text: raiz._nombre_pista_actual()
                            color: raiz.tema.texto
                            font.pixelSize: raiz.cW ? 14 : 16
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        AppText {
                            visible: djPrivado.dj_transicionando
                            text: {
                                if (!raiz._trans) return ""
                                var etiqueta = raiz._trans.etiqueta_ui || "Mezclando"
                                var siguiente = raiz._nombre_pista_siguiente()
                                return siguiente
                                    ? (etiqueta + " · entrando: " + siguiente)
                                    : etiqueta
                            }
                            color: raiz.tema.acento
                            font.pixelSize: UiTokens.fontSizeSm; elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        AppText {
                            visible: !djPrivado.dj_transicionando && djPrivado.dj_indice_actual + 1 < djPrivado.pistas_planificadas.total
                            text: {
                                var sig_idx = djPrivado.dj_indice_actual + 1
                                if (sig_idx < 0 || sig_idx >= djPrivado.pistas_planificadas.total) return ""
                                var sig = djPrivado.pistas_planificadas.obtener(sig_idx)
                                if (!sig) return ""
                                return "siguiente · " + (sig.titulo || "") + " — " + (sig.artista || "")
                            }
                            color: raiz.tema.textoMuted
                            font.pixelSize: UiTokens.fontSizeSm; elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }
                }

                // Barra de progreso UNIFICADA y arrastrable.
                // Inspirada en BarraReproduccion: una sola línea con tiempo a
                // ambos extremos, SliderLine para preview/commit y, debajo,
                // un texto sutil con la posición dentro de la pista actual.
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: UiTokens.spacing4

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: UiTokens.spacing10
                        AppText {
                            text: raiz.formatDur(raiz._progreso_drag_activo
                                                  ? raiz._progreso_preview_ratio * raiz._dur
                                                  : raiz._pos)
                            color: raiz.tema.textoMuted
                            font.pixelSize: UiTokens.fontSizeSm
                            Layout.preferredWidth: 48
                            horizontalAlignment: Text.AlignRight
                        }
                        Item {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 26
                            SliderLine {
                                id: slider_progreso_dj
                                anchors.fill: parent
                                tema: raiz.tema
                                ratio: raiz._progreso_drag_activo
                                       ? raiz._progreso_preview_ratio
                                       : raiz._progreso_ratio_real
                                live: false
                                visualHeight: 5
                                handleBaseSize: 10
                                handleActiveSize: 14
                                enabled: raiz._dur > 0
                                onPreviewed: function(r) {
                                    raiz._progreso_drag_activo = true
                                    raiz._progreso_preview_ratio = r
                                }
                                onCommitted: function(r) {
                                    raiz._progreso_preview_ratio = r
                                    djPrivado.dj_buscar_global(r * raiz._dur)
                                    raiz._progreso_drag_activo = false
                                }
                                onCanceled: {
                                    raiz._progreso_drag_activo = false
                                }
                            }
                            // Marcadores de transición sobre el slider, sin
                            // capturar eventos (z bajo, MouseArea propio del
                            // slider tiene preferencia).
                            Repeater {
                                model: djPrivado.pistas_planificadas
                                delegate: Rectangle {
                                    visible: index > 0 && raiz._dur > 0
                                    width: 2
                                    height: 10
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: Qt.rgba(raiz.tema.fondo.r, raiz.tema.fondo.g, raiz.tema.fondo.b, 0.55)
                                    x: {
                                        if (!djPrivado.resumen || !djPrivado.resumen.duracion_seg) return -10
                                        var acum = 0
                                        for (var j = 0; j < index; j++) {
                                            var p = djPrivado.pistas_planificadas.obtener(j)
                                            if (p) acum += (p.duracion_seg || 0)
                                        }
                                        return parent.width * (acum / djPrivado.resumen.duracion_seg) - 1
                                    }
                                    z: -1
                                }
                            }
                        }
                        AppText {
                            text: raiz.formatDur(raiz._dur)
                            color: raiz.tema.textoMuted
                            font.pixelSize: UiTokens.fontSizeSm
                            Layout.preferredWidth: 48
                        }
                    }
                    AppText {
                        Layout.fillWidth: true
                        text: raiz._idx >= 0 && djPrivado.pistas_planificadas.total > 0
                              ? ("pista " + (raiz._idx + 1) + " de " + djPrivado.pistas_planificadas.total
                                 + " · " + raiz.formatDur(raiz._pos_pista) + " / " + raiz.formatDur(raiz._dur_pista))
                              : ""
                        color: raiz.tema.textoMuted
                        font.pixelSize: UiTokens.fontSizeSm
                        horizontalAlignment: Text.AlignHCenter
                    }
                }

                // Controles con SVG (sin emojis). Iconos colorizados con
                // MultiEffect siguiendo el patrón de BarraReproduccion.
                RowLayout {
                    Layout.fillWidth: true
                    spacing: UiTokens.spacing8

                    BotonIconoDj {
                        iconSource: "../assets/icons/prev.svg"
                        ayuda: "Anterior"
                        onClicked: djPrivado.dj_anterior()
                    }
                    BotonIconoDj {
                        id: btn_play_pausa
                        principal: true
                        iconSource: djPrivado.dj_reproduciendo
                                    ? "../assets/icons/pause.svg"
                                    : "../assets/icons/play.svg"
                        ayuda: djPrivado.dj_reproduciendo ? "Pausar" : "Reproducir"
                        onClicked: djPrivado.dj_play_pause()
                    }
                    BotonIconoDj {
                        iconSource: "../assets/icons/next.svg"
                        ayuda: "Siguiente"
                        onClicked: djPrivado.dj_siguiente()
                    }
                    Item { Layout.preferredWidth: 16 }
                    Rectangle {
                        id: btn_cerrar_sesion
                        Layout.preferredHeight: 36
                        Layout.preferredWidth: lbl_cerrar.implicitWidth + (icon_cerrar.width + 28)
                        radius: 18
                        color: btn_cerrar_ma.containsMouse
                            ? Qt.rgba(raiz.tema.peligro.r, raiz.tema.peligro.g, raiz.tema.peligro.b, 0.16)
                            : Qt.rgba(raiz.tema.peligro.r, raiz.tema.peligro.g, raiz.tema.peligro.b, 0.06)
                        border.color: raiz.tema.peligro; border.width: 1
                        RowLayout {
                            anchors.centerIn: parent
                            spacing: UiTokens.spacing6
                            Item {
                                width: UiTokens.iconSm
                                height: UiTokens.iconSm
                                Image {
                                    id: icon_cerrar
                                    anchors.fill: parent
                                    source: "../assets/icons/close.svg"
                                    sourceSize.width: UiTokens.iconSm
                                    sourceSize.height: UiTokens.iconSm
                                    opacity: 0
                                }
                                MultiEffect {
                                    anchors.fill: icon_cerrar
                                    source: icon_cerrar
                                    colorization: 1.0
                                    colorizationColor: raiz.tema.peligro
                                }
                            }
                            AppText {
                                id: lbl_cerrar
                                text: "Cerrar sesión"
                                color: raiz.tema.peligro
                                font.pixelSize: UiTokens.fontSizeMd; font.weight: Font.DemiBold
                            }
                        }
                        MouseArea {
                            id: btn_cerrar_ma
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: djPrivado.detener_sesion()
                        }
                    }
                    Item { Layout.fillWidth: true }
                    AppText {
                        text: "Tu música normal está en pausa"
                        color: raiz.tema.textoMuted
                        font.pixelSize: UiTokens.fontSizeSm; font.italic: true
                        visible: !raiz.cW
                    }
                }
            }

            // ── TIMELINE VISUAL (fases + energia + click-to-seek) ────
            //
            // El timeline es el CENTRO de la experiencia DJ. Permite ver
            // donde estamos en la narrativa de sesion (warmup/groove/peak/
            // release/cooldown) y saltar a cualquier punto con un click.
            //
            // Cada pista ocupa una franja proporcional a su duracion REAL
            // (no a su numero ordinal). Asi una pista de 6min se ve mas
            // ancha que una de 2min y el seeking es preciso.
            AppCard {
                Layout.fillWidth: true
                tema: raiz.tema
                padding: UiTokens.spacing12
                visible: djPrivado.pistas_planificadas.total > 0

                RowLayout {
                    Layout.fillWidth: true
                    spacing: UiTokens.spacing8
                    AppText {
                        text: "Línea de tiempo"
                        color: raiz.tema.texto; font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold
                    }
                    AppText {
                        visible: djPrivado.dj_reproduciendo || djPrivado.dj_pausado
                        text: raiz._fase_actual_descripcion()
                        color: raiz.tema.acento; font.pixelSize: UiTokens.fontSizeSm; font.italic: true
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    AppText {
                        visible: djPrivado.resumen && djPrivado.resumen.transiciones_total > 0 && !djPrivado.dj_reproduciendo && !djPrivado.dj_pausado
                        text: (djPrivado.resumen.transiciones_buenas || 0) + " / " + (djPrivado.resumen.transiciones_total || 0) + " mezclas óptimas"
                        color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm
                    }
                }

                // Canvas + MouseArea para click-to-seek
                Rectangle {
                    id: timeline_container
                    Layout.fillWidth: true
                    Layout.preferredHeight: 104
                    color: raiz.tema.superficieAlt
                    radius: UiTokens.radiusSm
                    border.color: raiz.tema.borde; border.width: 1
                    clip: true

                    // Fases narrativas (warmup/groove/peak/...) como bandas
                    // sutiles de color en el fondo. Comunica "donde estamos
                    // narrativamente" mas que solo "que track suena".
                    Repeater {
                        model: (djPrivado.resumen && djPrivado.resumen.perfil_narrativo)
                            ? djPrivado.resumen.perfil_narrativo
                            : []
                        delegate: Rectangle {
                            required property var modelData
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            x: parent.width * (modelData.start_t || 0)
                            width: parent.width * Math.max(0.01, ((modelData.end_t || 0) - (modelData.start_t || 0)))
                            color: raiz._color_fase(modelData.name || "")
                            border.width: 0
                            // Etiqueta de fase
                            AppText {
                                anchors.top: parent.top; anchors.left: parent.left
                                anchors.margins: UiTokens.spacing4
                                text: raiz._label_fase(modelData.name || "")
                                color: raiz.tema.textoMuted
                                font.pixelSize: 9; font.weight: Font.DemiBold
                                opacity: 0.7
                            }
                        }
                    }

                    Canvas {
                        id: curva_canvas
                        anchors.fill: parent
                        anchors.margins: UiTokens.spacing6
                        antialiasing: true
                        property int indiceActual: djPrivado.dj_indice_actual
                        property real posSesion: djPrivado.dj_pos_sesion_seg
                        property real durSesion: djPrivado.dj_dur_sesion_seg
                        onIndiceActualChanged: requestPaint()
                        Connections {
                            target: djPrivado
                            function onSesionLista() { curva_canvas.requestPaint() }
                            function onTransicionCambiada() { curva_canvas.requestPaint() }
                            function onProgresoSesionCambiado() { curva_canvas.requestPaint() }
                        }
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.clearRect(0, 0, width, height)
                            var total = djPrivado.pistas_planificadas.total
                            if (total <= 0) return

                            // Calcular ancho proporcional a duracion REAL
                            var sumas = []
                            var acumulado = 0
                            for (var i = 0; i < total; i++) {
                                var item = djPrivado.pistas_planificadas.obtener(i)
                                var d = (item && item.duracion_seg) ? item.duracion_seg : 180
                                acumulado += d
                                sumas.push(acumulado)
                            }
                            var duracion_total = acumulado || 1
                            var inicio_prev = 0
                            for (var k = 0; k < total; k++) {
                                var item2 = djPrivado.pistas_planificadas.obtener(k)
                                var score = (item2 && item2.score_curva !== undefined) ? item2.score_curva : 0.5
                                var x_inicio = (inicio_prev / duracion_total) * width
                                var x_fin = (sumas[k] / duracion_total) * width
                                inicio_prev = sumas[k]
                                var ancho = Math.max(2, x_fin - x_inicio - 1)
                                var altura = score * (height * 0.78) + height * 0.10
                                // Color de la barra = color de la fase en su
                                // posición temporal. Así las barras de la
                                // curva y las bandas de fondo comparten paleta.
                                var t_centro = ((inicio_prev - (item2 && item2.duracion_seg ? item2.duracion_seg : 180) / 2) / duracion_total)
                                var nombre_fase = raiz._fase_en_t(t_centro)
                                var col = raiz._color_barra_fase(nombre_fase, score)
                                var es_actual = (k === djPrivado.dj_indice_actual)
                                ctx.fillStyle = Qt.rgba(col.r, col.g, col.b, es_actual ? col.a : col.a * 0.55)
                                ctx.fillRect(x_inicio + 0.5, height - altura, ancho, altura - 2)
                            }

                            // Linea de curva interpolada
                            ctx.strokeStyle = raiz.tema.acento
                            ctx.lineWidth = 2
                            ctx.beginPath()
                            var x_curva = 0
                            for (var j = 0; j < total; j++) {
                                var item3 = djPrivado.pistas_planificadas.obtener(j)
                                var s = (item3 && item3.score_curva !== undefined) ? item3.score_curva : 0.5
                                var d3 = (item3 && item3.duracion_seg) ? item3.duracion_seg : 180
                                var mid = x_curva + (d3 / duracion_total) * width * 0.5
                                x_curva += (d3 / duracion_total) * width
                                var py = height - (s * (height * 0.78) + height * 0.10) + 1
                                if (j === 0) ctx.moveTo(mid, py); else ctx.lineTo(mid, py)
                            }
                            ctx.stroke()

                            // Marcador de posicion actual (en proporcion de tiempo)
                            if (curva_canvas.durSesion > 0 && curva_canvas.posSesion >= 0) {
                                var x_pos = (curva_canvas.posSesion / curva_canvas.durSesion) * width
                                ctx.strokeStyle = raiz.tema.acento
                                ctx.lineWidth = 2
                                ctx.beginPath()
                                ctx.moveTo(x_pos, 0)
                                ctx.lineTo(x_pos, height)
                                ctx.stroke()
                                // Punto luminoso
                                ctx.fillStyle = raiz.tema.acento
                                ctx.beginPath()
                                ctx.arc(x_pos, height - 4, 3, 0, Math.PI * 2)
                                ctx.fill()
                            }
                        }
                    }

                    // Zona de overlap visible durante una transición activa.
                    // Pinta una franja translúcida sobre el rango temporal donde
                    // las dos pistas suenan simultáneamente. Comunica visualmente
                    // que la mezcla ESTÁ ocurriendo, no solo que se cambia.
                    Rectangle {
                        id: overlap_overlay
                        visible: djPrivado.dj_transicionando && raiz._trans
                                 && raiz._dur > 0
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        property real _pos_actual: raiz._pos
                        property real _overlap: raiz._trans
                            ? (raiz._trans.overlap !== undefined ? raiz._trans.overlap : 4.0)
                            : 0.0
                        x: parent.width * Math.max(0, (_pos_actual - _overlap) / raiz._dur)
                        width: parent.width * Math.max(0.01, _overlap / Math.max(1, raiz._dur))
                        color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.18)
                        border.color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.55)
                        border.width: 1
                        radius: 4
                        Behavior on x { NumberAnimation { duration: 150 } }
                    }

                    // Click-to-seek sobre el timeline completo
                    MouseArea {
                        id: timeline_ma
                        anchors.fill: parent
                        cursorShape: djPrivado.dj_dur_sesion_seg > 0 ? Qt.PointingHandCursor : Qt.ArrowCursor
                        hoverEnabled: true
                        onClicked: function(mouse) {
                            if (djPrivado.dj_dur_sesion_seg <= 0) return
                            var ratio = Math.max(0, Math.min(1, mouse.x / width))
                            var seg = ratio * djPrivado.dj_dur_sesion_seg
                            djPrivado.dj_buscar_global(seg)
                        }
                    }
                }
            }

            // ── LISTA DE PISTAS DETALLADA ────────────────────────────
            AppCard {
                Layout.fillWidth: true
                tema: raiz.tema
                padding: UiTokens.spacing12

                RowLayout {
                    Layout.fillWidth: true
                    AppText {
                        text: {
                            // Contexto al prompt: "Tu sesión de 45 min · 12 pistas · cinematográfico…"
                            var partes = ["Tu sesión"]
                            if (djPrivado.resumen && djPrivado.resumen.duracion_min) {
                                partes[0] = "Tu sesión de " + Math.round(djPrivado.resumen.duracion_min) + " min"
                            }
                            var totalPistas = djPrivado.pistas_planificadas.total
                            if (totalPistas > 0) partes.push(totalPistas + " pistas")
                            var prompt = djPrivado.intent && djPrivado.intent.prompt ? djPrivado.intent.prompt : ""
                            if (prompt && prompt.length > 0) {
                                var corto = prompt.length > 60 ? prompt.substring(0, 57) + "…" : prompt
                                partes.push("“" + corto + "”")
                            }
                            return partes.join(" · ")
                        }
                        color: raiz.tema.texto; font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                    }
                    Item { Layout.preferredWidth: 8 }
                    Rectangle {
                        height: 28
                        width: btn_reg_lbl.implicitWidth + 28
                        radius: UiTokens.radiusLg
                        color: btn_reg_ma.containsMouse
                            ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.18)
                            : Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.08)
                        border.color: raiz.tema.acento; border.width: 1
                        AppText { id: btn_reg_lbl; anchors.centerIn: parent; text: "Crear variante"; color: raiz.tema.acento; font.pixelSize: UiTokens.fontSizeSm; font.weight: Font.DemiBold }
                        MouseArea { id: btn_reg_ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: djPrivado.regenerar() }
                    }
                    Rectangle {
                        height: 28
                        width: btn_ext_lbl.implicitWidth + 28
                        radius: UiTokens.radiusLg
                        color: btn_ext_ma.containsMouse
                            ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.18)
                            : Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.08)
                        border.color: raiz.tema.acento; border.width: 1
                        AppText { id: btn_ext_lbl; anchors.centerIn: parent; text: "Alargar 15 min"; color: raiz.tema.acento; font.pixelSize: UiTokens.fontSizeSm; font.weight: Font.DemiBold }
                        MouseArea { id: btn_ext_ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: djPrivado.extender(15) }
                    }
                    Rectangle {
                        height: 28
                        width: btn_save_lbl.implicitWidth + 28
                        radius: UiTokens.radiusLg
                        color: btn_save_ma.containsMouse
                            ? Qt.rgba(raiz.tema.textoSec.r, raiz.tema.textoSec.g, raiz.tema.textoSec.b, 0.18)
                            : raiz.tema.superficieAlt
                        border.color: raiz.tema.borde; border.width: 1
                        AppText { id: btn_save_lbl; anchors.centerIn: parent; text: "Guardar como playlist"; color: raiz.tema.textoSec; font.pixelSize: UiTokens.fontSizeSm; font.weight: Font.DemiBold }
                        MouseArea { id: btn_save_ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: raiz.abrirGuardar() }
                    }
                }

                ListView {
                    id: lista_pistas
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(420, Math.max(180, djPrivado.pistas_planificadas.total * 64 + 8))
                    model: djPrivado.pistas_planificadas
                    clip: true
                    spacing: UiTokens.spacing4
                    boundsBehavior: Flickable.StopAtBounds
                    cacheBuffer: 0
                    reuseItems: true
                    ScrollBar.vertical: AppScrollBar {
                        tema: raiz.tema
                        policy: lista_pistas.contentHeight > lista_pistas.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
                    }
                    delegate: Rectangle {
                        id: fila
                        required property int index
                        width: lista_pistas.width
                        height: 60
                        readonly property var datos: djPrivado.pistas_planificadas.obtener(index)
                        readonly property bool actual: index === djPrivado.dj_indice_actual
                        readonly property string trans_tecnica: datos && datos.transicion ? (datos.transicion.tecnica_sugerida || "") : ""
                        readonly property real trans_score: datos && datos.transicion ? (datos.transicion.score || 0) : 0

                        radius: UiTokens.radiusSm
                        color: actual
                            ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.13)
                            : (fila_ma.containsMouse ? raiz.tema.hover : raiz.tema.superficieAlt)
                        border.color: actual ? raiz.tema.acento : "transparent"
                        border.width: actual ? 1 : 0

                        MouseArea {
                            id: fila_ma
                            anchors.fill: parent; hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onDoubleClicked: djPrivado.dj_saltar_a(fila.index)
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: UiTokens.spacing12; anchors.rightMargin: UiTokens.spacing8
                            spacing: 10

                            // Numero
                            AppText {
                                text: (fila.index + 1)
                                color: fila.actual ? raiz.tema.acento : raiz.tema.textoMuted
                                font.pixelSize: UiTokens.fontSizeMd; font.weight: Font.DemiBold
                                Layout.preferredWidth: 24
                                horizontalAlignment: Text.AlignRight
                            }
                            // Mini barra de energía: usa el color de la fase
                            // narrativa donde cae la pista (aproximación por
                            // índice/total), coherente con timeline y curva.
                            Rectangle {
                                Layout.preferredWidth: 4
                                Layout.preferredHeight: 36
                                radius: 2
                                color: raiz.tema.fondoElevado
                                Rectangle {
                                    anchors.bottom: parent.bottom
                                    anchors.left: parent.left; anchors.right: parent.right
                                    radius: 2
                                    color: {
                                        var score = fila.datos ? (fila.datos.score_curva || 0) : 0
                                        var total = djPrivado.pistas_planificadas.total || 1
                                        var t = total > 0 ? (fila.index + 0.5) / total : 0
                                        return raiz._color_barra_fase(raiz._fase_en_t(t), score)
                                    }
                                    height: parent.height * Math.max(0.05, Math.min(1.0, fila.datos ? (fila.datos.score_curva || 0) : 0))
                                }
                            }
                            // Titulo + razones + transicion
                            ColumnLayout {
                                Layout.fillWidth: true; Layout.minimumWidth: 0
                                spacing: 1
                                AppText {
                                    text: raiz._titulo_pista(fila.datos)
                                    color: fila.actual ? raiz.tema.texto : raiz.tema.texto
                                    font.pixelSize: UiTokens.fontSizeBase
                                    font.weight: fila.actual ? Font.DemiBold : Font.Normal
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                AppText {
                                    text: {
                                        if (!fila.datos) return ""
                                        var artista = fila.datos.artista || ""
                                        var dur = fila.datos.duracion_seg ? raiz.formatDur(fila.datos.duracion_seg) : ""
                                        var partes = []
                                        if (artista) partes.push(artista)
                                        if (dur)     partes.push(dur)
                                        return partes.join(" · ")
                                    }
                                    color: raiz.tema.textoMuted
                                    font.pixelSize: UiTokens.fontSizeSm
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }
                            // Estado del slot (lenguaje humano)
                            StatusBadge {
                                tema: raiz.tema
                                visible: !!(fila.datos && (fila.datos.estado === "reproducida" || fila.datos.estado === "saltada" || fila.datos.bloqueada))
                                text: fila.datos
                                    ? (fila.datos.bloqueada ? "intocable"
                                       : (fila.datos.estado === "reproducida" ? "escuchada"
                                          : (fila.datos.estado === "saltada" ? "omitida" : "")))
                                    : ""
                                tone: fila.datos && fila.datos.bloqueada ? "info"
                                    : (fila.datos && fila.datos.estado === "reproducida" ? "success"
                                       : (fila.datos && fila.datos.estado === "saltada" ? "warning" : "neutral"))
                                compact: true
                                maxTextWidth: 80
                            }
                            // Fijar/soltar la pista. Cuando está fijada, la
                            // marca activa muestra el pin pintado del acento.
                            // Solo el texto en pantallas anchas — en
                            // compacto, queda solo el icono claro.
                            BotonAccionPista {
                                iconSource: "../assets/icons/pin.svg"
                                texto: raiz.cW ? "" : (fila.datos && fila.datos.bloqueada ? "Soltar" : "Fijar")
                                activo: !!(fila.datos && fila.datos.bloqueada)
                                onClicked: {
                                    if (!fila.datos) return
                                    if (fila.datos.bloqueada) djPrivado.desbloquear_posicion(fila.datos.posicion)
                                    else djPrivado.bloquear_posicion(fila.datos.posicion)
                                }
                            }
                            // Replanificar desde esta posición: vuelve a
                            // ordenar las siguientes pistas conservando las
                            // fijadas.
                            BotonAccionPista {
                                iconSource: "../assets/icons/sync.svg"
                                texto: raiz.cW ? "" : "Regenerar desde aquí"
                                onClicked: if (fila.datos) djPrivado.replanificar_desde(fila.datos.posicion)
                            }
                        }
                    }

                    Item {
                        anchors.fill: parent
                        visible: djPrivado.pistas_planificadas.total === 0
                        EmptyState {
                            anchors.centerIn: parent
                            width: Math.min(parent.width, 360)
                            tema: raiz.tema
                            title: "Sin pistas"
                            description: "Construye una sesión en la pestaña Construir."
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true; Layout.preferredHeight: UiTokens.spacing16 }
        }
    }

    // ─────────────────────────────────────────────────────────────────
    // Componentes locales
    // ─────────────────────────────────────────────────────────────────

    // Botón circular con SVG colorizado. Sigue el patrón de BarraReproduccion
    // (Multiple → MultiEffect) sin depender de Button (queremos forma libre y
    // hover preciso). `principal=true` lo pinta del acento, sin borde.
    component BotonIconoDj: Rectangle {
        id: btn
        property string iconSource: ""
        property string ayuda: ""
        property bool principal: false
        property bool habilitado: true
        signal clicked()

        Layout.preferredWidth: principal ? 48 : 36
        Layout.preferredHeight: principal ? 48 : 36
        radius: principal ? 24 : 18
        color: !habilitado
               ? Qt.rgba(raiz.tema.superficieAlt.r, raiz.tema.superficieAlt.g, raiz.tema.superficieAlt.b, 0.5)
               : (principal
                  ? (ma.containsMouse ? raiz.tema.acentoFuerte : raiz.tema.acento)
                  : (ma.containsMouse ? raiz.tema.hover : raiz.tema.superficieAlt))
        border.color: principal ? "transparent" : raiz.tema.borde
        border.width: principal ? 0 : 1
        opacity: habilitado ? 1.0 : 0.55

        readonly property color _colorIcono: principal ? raiz.tema.textoSobreAcento : raiz.tema.textoSec

        Item {
            anchors.centerIn: parent
            width: btn.principal ? UiTokens.iconLg : UiTokens.iconMd
            height: width
            Image {
                id: icono_btn
                anchors.fill: parent
                source: btn.iconSource
                sourceSize.width: parent.width
                sourceSize.height: parent.height
                smooth: true
                opacity: 0
            }
            MultiEffect {
                anchors.fill: icono_btn
                source: icono_btn
                colorization: 1.0
                colorizationColor: btn._colorIcono
            }
        }

        MouseArea {
            id: ma
            anchors.fill: parent
            hoverEnabled: true
            enabled: btn.habilitado
            cursorShape: btn.habilitado ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: btn.clicked()
        }
    }

    // Botón compacto para acciones por pista. Cuando se pasa `texto`,
    // muestra icono + texto en una píldora; si no, solo icono circular.
    // `activo=true` lo destaca con borde y color de acento (útil para
    // "fijada").
    component BotonAccionPista: Rectangle {
        id: bap
        property string iconSource: ""
        property string texto: ""
        property bool activo: false
        signal clicked()

        readonly property bool _soloIcono: texto.length === 0

        Layout.preferredWidth: _soloIcono ? 26 : (contenidoAccion.implicitWidth + 18)
        Layout.preferredHeight: 26
        radius: 13
        color: bap_ma.containsMouse
            ? raiz.tema.hover
            : (activo
                ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.12)
                : "transparent")
        border.color: activo ? raiz.tema.acento : "transparent"
        border.width: activo ? 1 : 0

        readonly property color _colorContenido: bap.activo
            ? raiz.tema.acento
            : (bap_ma.containsMouse ? raiz.tema.texto : raiz.tema.textoSec)

        RowLayout {
            id: contenidoAccion
            anchors.centerIn: parent
            spacing: bap._soloIcono ? 0 : UiTokens.spacing4

            Item {
                Layout.preferredWidth: 14
                Layout.preferredHeight: 14
                Image {
                    id: bap_icono
                    anchors.fill: parent
                    source: bap.iconSource
                    sourceSize.width: parent.width
                    sourceSize.height: parent.height
                    smooth: true
                    opacity: 0
                }
                MultiEffect {
                    anchors.fill: bap_icono
                    source: bap_icono
                    colorization: 1.0
                    colorizationColor: bap._colorContenido
                }
            }
            AppText {
                visible: !bap._soloIcono
                text: bap.texto
                color: bap._colorContenido
                font.pixelSize: UiTokens.fontSizeSm
                font.weight: Font.DemiBold
            }
        }

        MouseArea {
            id: bap_ma
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: bap.clicked()
        }
    }
}
