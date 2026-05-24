import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import "../componentes"
import "../componentes/UiUtils.js" as UiUtils

// =============================================================================
// VistaDJPrivado
//
// Arquitectura UX:
//   Tres modos contextuales bajo el mismo header:
//     - "construir"  → prompt + intent + sugerencias.
//     - "sesion"     → reproductor DJ propio + timeline visual + lista de pistas.
//     - "historial"  → workspace de sesiones generadas (tabla + acciones).
//
// La vista NUNCA habla con el reproductor global; usa `djPrivado` que
// gestiona internamente el ReproductorSesionDj aislado. Cuando una sesion
// esta reproduciendose, el global queda suspendido (set_modo_dj=true).
// =============================================================================

Rectangle {
    id: raiz
    objectName: "vista_dj_privado"

    property var shell: null
    required property var temaBase
    required property var cfg
    readonly property var tema: shell ? shell.tema : temaBase
    color: tema.fondo

    // ── Estado local ───────────────────────────────────────────────────
    property string prompt_actual: ""
    property int    minutos_objetivo: 45
    // Tab activo. Si hay sesion en reproduccion, forzamos "sesion".
    property string tab_actual: "construir"
    readonly property bool sesion_activa: djPrivado.dj_reproduciendo || djPrivado.dj_pausado

    // Categorías de palabras que el motor reconoce. Sirven como ayuda
    // visual: cada palabra es un chip clickeable que se añade al prompt.
    // No hace falta exponer toda la ontología — basta con las formas más
    // humanas (las variantes con tildes/sinónimos se detectan igualmente
    // en el parser).
    property var categorias_palabras: [
        {
            "titulo": "Voces",
            "palabras": ["voces femeninas", "voces masculinas", "instrumental",
                         "que resalten las voces"]
        },
        {
            "titulo": "Géneros",
            "palabras": ["pop", "rock", "indie", "electrónica", "house", "techno",
                         "jazz", "clásica", "hip hop", "r&b", "ambient", "folk",
                         "metal", "blues", "funk", "lo-fi", "reggaetón", "reggae",
                         "trap", "salsa", "bachata", "merengue", "cumbia"]
        },
        {
            "titulo": "Estado de ánimo",
            "palabras": ["triste", "feliz", "esperanzador", "melancólico",
                         "nostálgico", "romántico", "dramático", "épico",
                         "sentimental", "emocionante"]
        },
        {
            "titulo": "Energía",
            "palabras": ["tranquilo", "energético", "agresivo", "suave",
                         "relajante", "intenso", "que pegue"]
        },
        {
            "titulo": "Atmósfera",
            "palabras": ["cinematográfico", "oscuro", "brillante", "elegante",
                         "minimalista", "atmosférico", "acústico", "orquestal",
                         "cálido"]
        },
        {
            "titulo": "Contextos",
            "palabras": ["para entrenar", "hacer ejercicio", "para concentrarme",
                         "para estudiar", "para manejar", "viaje en carretera",
                         "fiesta", "para bailar", "nocturno", "cocinar",
                         "tarde lluviosa"]
        },
        {
            "titulo": "Transiciones",
            "palabras": ["transiciones suaves", "transiciones agresivas",
                         "subida progresiva", "bajos fuertes"]
        }
    ]

    function _agregar_al_prompt(palabra) {
        var actual = raiz.prompt_actual.trim()
        var nueva = actual.length === 0
                    ? palabra
                    : (actual + (actual.endsWith(",") ? " " : ", ") + palabra)
        raiz.prompt_actual = nueva
        if (input_prompt) {
            input_prompt.text = nueva
            input_prompt.cursorPosition = nueva.length
            input_prompt.forceActiveFocus()
        }
    }

    property var sugerencias_chips: [
        "algo cinematográfico con voces femeninas para una noche tranquila",
        "para concentrarme mientras estudio, sin voces que distraigan",
        "subida progresiva para entrenar, que termine con energía alta",
        "elegante y melancólico para manejar de noche por la ciudad",
        "bajos fuertes pero transiciones suaves, ambiente de club bajo",
        "triste pero esperanzador, con pianos y cuerdas",
        "sesión energética pero sin EDM agresivo, más rock alternativo",
        "clásica con pop, que destaque lo orquestal y las voces femeninas",
        "lo-fi para trabajar en casa, sin saltos bruscos de energía",
        "indie acústico melancólico para una tarde lluviosa",
        "club techno minimal para la madrugada, oscuro y rítmico",
        "para cocinar, con groove pero relajado",
        "jazz nocturno con voz femenina, elegante y sofisticado",
        "rock clásico para hacer ejercicio sin pop comercial",
        "synthwave ochentero para conducir por carretera",
        "ambient cinemático para meditar, sin percusión",
        "reggaetón solo perreo viejo, nada moderno",
        "punk rápido y agresivo para entrenar fuerte"
    ]

    // ── Responsive ─────────────────────────────────────────────────────
    readonly property int  hPad: width >= 1320 ? 36 : (width >= 860 ? 24 : 18)
    readonly property int  hMax: 1280
    readonly property real aW:   Math.min(hMax, Math.max(0, width - hPad * 2))
    readonly property bool cW:   aW < 720      // compact
    readonly property bool mW:   aW >= 920     // medium
    readonly property bool wW:   aW >= 1140    // wide

    // ── Helpers ────────────────────────────────────────────────────────
    function _fmtDur(seg) {
        if (!seg || seg <= 0) return "—"
        var s = Math.round(seg), m = Math.floor(s/60), h = Math.floor(m/60)
        if (h > 0) return h + ":" + _pad(m % 60) + ":" + _pad(s % 60)
        return m + ":" + _pad(s % 60)
    }
    function _fmtMin(min) {
        var h = Math.floor(min / 60), m = min % 60
        if (h > 0) return h + "h " + (m > 0 ? m + "min" : "")
        return m + "min"
    }
    function _pad(n) { return n < 10 ? "0" + n : "" + n }
    function _fmtFecha(iso) {
        if (!iso) return "—"
        // "YYYY-MM-DD HH:MM:SS" → "DD MMM, HH:MM"
        var partes = iso.split(" ")
        if (partes.length < 2) return iso
        var dia = partes[0].split("-")
        var hh = partes[1].substring(0, 5)
        var meses = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
        var m = parseInt(dia[1]) - 1
        if (m < 0 || m > 11) return iso
        return dia[2] + " " + meses[m] + ", " + hh
    }
    function _toast(msg, tono) {
        if (shell) shell.mostrar_toast_global(msg, tono || "info")
    }
    function _iniciar_construccion() {
        if (raiz.prompt_actual.trim().length === 0) return
        djPrivado.iniciar_sesion(raiz.prompt_actual.trim(), raiz.minutos_objetivo)
    }
    function _ir_a(tab) { raiz.tab_actual = tab }

    // ── Conexiones a senales del modelo ────────────────────────────────
    readonly property int minutos_default: 45
    Connections {
        target: djPrivado
        function onSesionLista() {
            // Cuando se acaba de construir desde la pestaña "Construir",
            // cambiamos automáticamente a "En sesión" para que el usuario
            // vea lo que se generó. Si está en otra pestaña (p.ej. mirando
            // Historial), respetamos su contexto y no lo movemos.
            if (djPrivado.tiene_sesion && raiz.tab_actual === "construir") {
                raiz.tab_actual = "sesion"
            }
            // Reseteamos la pantalla de Construir para que un nuevo prompt
            // empiece en blanco. El TextArea hace bind a `prompt_actual`,
            // pero su `onTextChanged` reescribe la propiedad y rompe el
            // binding entrante: forzamos también el reset imperativo.
            raiz.prompt_actual = ""
            raiz.minutos_objetivo = raiz.minutos_default
            if (input_prompt) input_prompt.text = ""
        }
        function onError(msg) { raiz._toast(msg, "danger") }
        function onAvisoUi(msg, tono) { raiz._toast(msg, tono) }
        // Importante: NO forzamos cambio a la pestaña "sesion" en cada
        // cambio de reproducción. Si el usuario está en Construir o en
        // Historial mientras la sesión sigue sonando, debe quedarse ahí
        // — solo el banner discreto "Tu sesión está lista" le invita a
        // entrar cuando él quiera.
        function onSesionFinalizada() {
            raiz._toast("Sesión finalizada.", "info")
        }
    }

    Component.onCompleted: {
        djPrivado.refrescar_estado_motor()
        djPrivado.cargar_historial()
    }

    // ═══════════════════════════════════════════════════════════════════
    // OVERLAY: "Preparando tu mezcla..."
    //
    // Aparece encima del contenido cuando el constructor está trabajando
    // pero la sesión aún no se puede reproducir. NO bloquea interacción
    // con la app (z alto pero opacidad limitada). Permite cancelar.
    // ═══════════════════════════════════════════════════════════════════
    Rectangle {
        id: overlay_preparando
        anchors.fill: parent
        z: 10
        // Local: el usuario puede esconder el overlay (la construcción sigue
        // en background). Se vuelve a mostrar la próxima vez que arranque.
        property bool ocultado_por_usuario: false
        visible: djPrivado.construyendo && !ocultado_por_usuario
        color: Qt.rgba(raiz.tema.fondo.r, raiz.tema.fondo.g, raiz.tema.fondo.b, 0.78)
        opacity: visible ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 220 } }

        Connections {
            target: djPrivado
            function onConstruyendoCambiado() {
                if (djPrivado.construyendo) {
                    overlay_preparando.ocultado_por_usuario = false
                }
            }
        }

        // Capturar clicks para que no se filtren al contenido detrás.
        MouseArea { anchors.fill: parent; hoverEnabled: true }

        AppCard {
            anchors.centerIn: parent
            tema: raiz.tema
            padding: UiTokens.spacing20
            implicitWidth: 360

            RowLayout {
                Layout.fillWidth: true
                spacing: UiTokens.spacing12
                Rectangle {
                    Layout.preferredWidth: 18; Layout.preferredHeight: 18
                    radius: 9
                    color: "transparent"
                    border.color: raiz.tema.acento
                    border.width: 2
                    RotationAnimator on rotation {
                        from: 0; to: 360; duration: 1200
                        loops: Animation.Infinite
                        running: overlay_preparando.visible
                    }
                    Rectangle {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        width: 9; height: 9; radius: 4.5
                        color: raiz.tema.acento
                    }
                }
                AppText {
                    text: "Preparando tu mezcla…"
                    color: raiz.tema.texto
                    font.pixelSize: UiTokens.fontSizeXl; font.weight: Font.DemiBold
                    Layout.fillWidth: true
                }
            }
            AppText {
                text: "Estamos eligiendo las pistas y planificando las transiciones según lo que pediste. Tarda unos segundos."
                color: raiz.tema.textoSec
                font.pixelSize: UiTokens.fontSizeMd
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                lineHeight: 1.25
            }
            Rectangle {
                Layout.alignment: Qt.AlignRight
                Layout.topMargin: UiTokens.spacing4
                implicitWidth: 140
                implicitHeight: 32
                radius: 16
                color: cancel_prep_ma.containsMouse ? raiz.tema.hover : raiz.tema.superficieAlt
                border.color: raiz.tema.borde; border.width: 1
                AppText {
                    anchors.centerIn: parent
                    text: "Continuar sin esperar"
                    color: raiz.tema.texto
                    font.pixelSize: UiTokens.fontSizeMd; font.weight: Font.DemiBold
                }
                MouseArea {
                    id: cancel_prep_ma
                    anchors.fill: parent; hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: overlay_preparando.ocultado_por_usuario = true
                }
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // LAYOUT RAIZ
    // ═══════════════════════════════════════════════════════════════════
    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin:   raiz.hPad
        anchors.rightMargin:  raiz.hPad
        anchors.topMargin:    UiTokens.spacing16
        anchors.bottomMargin: UiTokens.spacing12
        spacing: UiTokens.spacing14

        // ── HEADER (titulo + estado motor + tabs) ────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.maximumWidth: raiz.hMax
            Layout.alignment: Qt.AlignHCenter
            spacing: UiTokens.spacing12

            ColumnLayout {
                spacing: UiTokens.spacing2
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                AppText {
                    text: "DJ Privado"
                    color: raiz.tema.texto
                    font.pixelSize: 28
                    font.weight: Font.DemiBold
                }
                AppText {
                    text: raiz.sesion_activa
                        ? "Sonando tu sesión · tu música normal está en pausa mientras tanto"
                        : "Describe lo que quieres escuchar y armamos una experiencia continua: no una playlist, una sesión mezclada"
                    color: raiz.tema.textoMuted
                    font.pixelSize: UiTokens.fontSizeMd
                    wrapMode: Text.WordWrap
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }

            // Indicador de sesion activa (en vez de jerga tecnica del motor).
            // Solo se muestra cuando ya hay una sesion construida que el
            // usuario puede escuchar — comunica algo accionable.
            Rectangle {
                visible: djPrivado.tiene_sesion && !raiz.sesion_activa
                implicitHeight: 28
                implicitWidth: hint_label.implicitWidth + 24
                radius: UiTokens.radiusLg
                color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.10)
                border.color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.28)
                border.width: 1
                AppText {
                    id: hint_label
                    anchors.centerIn: parent
                    text: "Tu sesión está lista — escúchala"
                    color: raiz.tema.acento
                    font.pixelSize: UiTokens.fontSizeSm
                    font.weight: Font.DemiBold
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: raiz.tab_actual = "sesion"
                }
            }
        }

        // ── TABS ──────────────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.maximumWidth: raiz.hMax
            Layout.alignment: Qt.AlignHCenter
            implicitHeight: 50
            radius: 12
            color: raiz.tema.superficie
            border.color: raiz.tema.borde; border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.margins: UiTokens.spacing6
                spacing: UiTokens.spacing6

                component TabBtn: Rectangle {
                    id: _tab
                    property string tabId: ""
                    property string texto: ""
                    property string subtitulo: ""
                    property bool destacar: false
                    Layout.fillWidth: true
                    implicitHeight: 38
                    radius: UiTokens.radiusSm
                    readonly property bool activo: raiz.tab_actual === tabId
                    color: activo
                        ? raiz.tema.seleccion
                        : (_tabm.containsMouse ? Qt.rgba(raiz.tema.hover.r, raiz.tema.hover.g, raiz.tema.hover.b, 0.5) : "transparent")
                    border.color: activo ? raiz.tema.acento : "transparent"
                    border.width: activo ? 1 : 0

                    RowLayout {
                        anchors.centerIn: parent
                        spacing: UiTokens.spacing6
                        AppText {
                            text: _tab.texto
                            color: _tab.activo ? raiz.tema.texto : raiz.tema.textoSec
                            font.pixelSize: UiTokens.fontSizeBase
                            font.weight: _tab.activo ? Font.DemiBold : Font.Normal
                        }
                        // Punto rojo cuando hay sesion activa en la tab Sesion
                        Rectangle {
                            visible: _tab.destacar
                            width: 7; height: 7; radius: 3.5
                            color: raiz.tema.acento
                        }
                        // Contador (historial)
                        Rectangle {
                            visible: _tab.subtitulo !== ""
                            implicitWidth: _tabcnt.implicitWidth + 10
                            implicitHeight: 16
                            radius: UiTokens.radiusSm
                            color: _tab.activo
                                ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.20)
                                : raiz.tema.superficieAlt
                            AppText {
                                id: _tabcnt
                                anchors.centerIn: parent
                                text: _tab.subtitulo
                                color: _tab.activo ? raiz.tema.acento : raiz.tema.textoMuted
                                font.pixelSize: UiTokens.fontSizeXs; font.weight: Font.DemiBold
                            }
                        }
                    }

                    MouseArea {
                        id: _tabm
                        anchors.fill: parent; hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: raiz.tab_actual = _tab.tabId
                    }
                }

                TabBtn { tabId: "construir"; texto: "Construir" }
                TabBtn {
                    tabId: "sesion"
                    texto: raiz.sesion_activa ? "En sesión" : "Sesión"
                    destacar: raiz.sesion_activa
                    visible: djPrivado.tiene_sesion
                }
                TabBtn {
                    tabId: "historial"; texto: "Historial"
                    subtitulo: djPrivado.historial.total > 0 ? "" + djPrivado.historial.total : ""
                }
            }
        }

        // ── ÁREA DE CONTENIDO ─────────────────────────────────────────
        // StackLayout permite intercambiar las tres vistas sin recrearlas.
        StackLayout {
            id: stack
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.maximumWidth: raiz.hMax
            Layout.alignment: Qt.AlignHCenter
            currentIndex: {
                if (raiz.tab_actual === "sesion") return 1
                if (raiz.tab_actual === "historial") return 2
                return 0
            }

            // ────────────────────────────────────────────────────────
            // (0) TAB CONSTRUIR
            // ────────────────────────────────────────────────────────
            ScrollView {
                id: scroll_construir
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                ScrollBar.vertical: AppScrollBar {
                    parent: scroll_construir
                    anchors.top: parent.top
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    z: 20
                    tema: raiz.tema
                    policy: scroll_construir.contentHeight > scroll_construir.height + 2 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
                }
                contentWidth: availableWidth

                ColumnLayout {
                    width: scroll_construir.availableWidth
                    spacing: UiTokens.spacing12

                    AppCard {
                        Layout.fillWidth: true
                        tema: raiz.tema; padding: UiTokens.spacing20

                        AppText {
                            text: "¿Qué quieres escuchar?"
                            color: raiz.tema.texto
                            font.pixelSize: UiTokens.fontSize2xl; font.weight: Font.DemiBold
                            Layout.fillWidth: true
                        }
                        AppText {
                            text: "Describe el ambiente, la energía o el estilo. El motor interpreta la intención y construye una sesión continua, no una playlist."
                            color: raiz.tema.textoMuted
                            font.pixelSize: UiTokens.fontSizeMd; wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        // Input multilinea con ScrollView interno por si hay textos largos
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 96
                            radius: UiTokens.radiusMd
                            color: raiz.tema.superficieAlt
                            border.color: input_prompt.activeFocus ? raiz.tema.acento : raiz.tema.borde
                            border.width: 1

                            ScrollView {
                                id: _prompt_scroll
                                anchors.fill: parent
                                anchors.margins: UiTokens.spacing8
                                clip: true
                                ScrollBar.vertical: AppScrollBar {
                                    parent: _prompt_scroll
                                    anchors.top: parent.top
                                    anchors.right: parent.right
                                    anchors.bottom: parent.bottom
                                    z: 20
                                    tema: raiz.tema
                                    policy: _prompt_scroll.contentHeight > _prompt_scroll.height + 2 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
                                }
                                TextArea {
                                    id: input_prompt
                                    placeholderText: "Ej: algo cinematográfico con voces femeninas para una noche tranquila"
                                    placeholderTextColor: raiz.tema.textoMuted
                                    color: raiz.tema.texto
                                    font.pixelSize: UiTokens.fontSizeLg
                                    wrapMode: TextArea.Wrap
                                    selectByMouse: true
                                    background: Item {}
                                    text: raiz.prompt_actual
                                    onTextChanged: {
                                        raiz.prompt_actual = text
                                        chips_preview.actualizar(text)
                                    }
                                    Keys.onPressed: function(event) {
                                        if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                                            && (event.modifiers & Qt.ControlModifier)) {
                                            raiz._iniciar_construccion()
                                            event.accepted = true
                                        }
                                    }
                                }
                            }
                        }

                        // Chips detectados en vivo
                        Flow {
                            id: chips_preview
                            Layout.fillWidth: true
                            spacing: UiTokens.spacing6
                            property var conceptos: []
                            function actualizar(prompt) { conceptos = djPrivado.previsualizar_intent(prompt) }
                            Repeater {
                                model: chips_preview.conceptos
                                Rectangle {
                                    radius: 13; height: 24
                                    width: chip_txt.implicitWidth + 16
                                    color: {
                                        if (modelData.role === "priority") return Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.16)
                                        if (modelData.role === "exclusion") return Qt.rgba(raiz.tema.peligro.r, raiz.tema.peligro.g, raiz.tema.peligro.b, 0.16)
                                        return Qt.rgba(raiz.tema.textoSec.r, raiz.tema.textoSec.g, raiz.tema.textoSec.b, 0.10)
                                    }
                                    border.color: {
                                        if (modelData.role === "priority") return Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.32)
                                        if (modelData.role === "exclusion") return Qt.rgba(raiz.tema.peligro.r, raiz.tema.peligro.g, raiz.tema.peligro.b, 0.30)
                                        return Qt.rgba(raiz.tema.borde.r, raiz.tema.borde.g, raiz.tema.borde.b, 0.6)
                                    }
                                    border.width: 1
                                    AppText {
                                        id: chip_txt
                                        anchors.centerIn: parent
                                        text: modelData.alias
                                        color: modelData.role === "exclusion" ? raiz.tema.peligro : raiz.tema.texto
                                        font.pixelSize: UiTokens.fontSizeSm; font.weight: Font.DemiBold
                                    }
                                }
                            }
                        }

                        // Duracion + CTA
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: UiTokens.spacing12
                            AppText { text: "Duración:"; color: raiz.tema.textoSec; font.pixelSize: UiTokens.fontSizeBase }
                            Slider {
                                id: slider_minutos
                                Layout.fillWidth: true
                                from: 15; to: 240; stepSize: 5
                                value: raiz.minutos_objetivo
                                onValueChanged: raiz.minutos_objetivo = Math.round(value)
                            }
                            AppText {
                                text: raiz._fmtMin(raiz.minutos_objetivo)
                                color: raiz.tema.texto; font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold
                                Layout.preferredWidth: 70
                                horizontalAlignment: Text.AlignRight
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: 42; radius: 21
                            readonly property bool habilitado: !djPrivado.construyendo && raiz.prompt_actual.trim().length > 0
                            color: habilitado
                                ? (_cta_ma.containsMouse ? raiz.tema.acentoFuerte : raiz.tema.acento)
                                : raiz.tema.superficieAlt
                            opacity: habilitado ? 1.0 : 0.55
                            border.color: habilitado ? "transparent" : raiz.tema.borde
                            border.width: habilitado ? 0 : 1
                            AppText {
                                anchors.centerIn: parent
                                text: djPrivado.construyendo ? "Construyendo sesión…" : "Construir sesión"
                                color: parent.habilitado ? raiz.tema.textoSobreAcento : raiz.tema.textoMuted
                                font.pixelSize: UiTokens.fontSizeLg; font.weight: Font.DemiBold
                            }
                            MouseArea {
                                id: _cta_ma
                                anchors.fill: parent; hoverEnabled: true
                                enabled: parent.habilitado
                                cursorShape: parent.habilitado ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: raiz._iniciar_construccion()
                            }
                        }
                    }

                    // Palabras que entiendo, agrupadas por categoría.
                    // Cada chip es una píldora clickeable: se añade al
                    // prompt, separada con coma. Sirve para que el usuario
                    // construya frases sin saber qué vocabulario reconoce.
                    AppCard {
                        Layout.fillWidth: true
                        tema: raiz.tema; padding: UiTokens.spacing16

                        AppText {
                            text: "Palabras que entiendo"
                            color: raiz.tema.texto; font.pixelSize: UiTokens.fontSizeLg; font.weight: Font.DemiBold
                        }
                        AppText {
                            text: "Toca cualquier palabra para añadirla a tu sesión. Puedes combinar varias."
                            color: raiz.tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm
                            wrapMode: Text.WordWrap; Layout.fillWidth: true
                        }

                        Repeater {
                            model: raiz.categorias_palabras
                            delegate: ColumnLayout {
                                Layout.fillWidth: true
                                spacing: UiTokens.spacing6
                                AppText {
                                    text: modelData.titulo
                                    color: raiz.tema.textoSec
                                    font.pixelSize: UiTokens.fontSizeSm
                                    font.weight: Font.DemiBold
                                    font.letterSpacing: 0.6
                                    Layout.topMargin: UiTokens.spacing6
                                }
                                Flow {
                                    Layout.fillWidth: true
                                    spacing: UiTokens.spacing6
                                    Repeater {
                                        model: modelData.palabras
                                        Rectangle {
                                            radius: 13
                                            height: 26
                                            width: cat_chip_txt.implicitWidth + 18
                                            color: cat_chip_ma.containsMouse
                                                ? raiz.tema.hover
                                                : Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.06)
                                            border.color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.24)
                                            border.width: 1
                                            AppText {
                                                id: cat_chip_txt
                                                anchors.centerIn: parent
                                                text: modelData
                                                color: raiz.tema.texto
                                                font.pixelSize: UiTokens.fontSizeSm
                                                font.weight: Font.DemiBold
                                            }
                                            MouseArea {
                                                id: cat_chip_ma
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: raiz._agregar_al_prompt(modelData)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // Sugerencias
                    AppCard {
                        Layout.fillWidth: true
                        tema: raiz.tema; padding: UiTokens.spacing16
                        AppText {
                            text: "Ideas para empezar"
                            color: raiz.tema.texto; font.pixelSize: UiTokens.fontSizeLg; font.weight: Font.DemiBold
                        }
                        Flow {
                            Layout.fillWidth: true
                            spacing: UiTokens.spacing6
                            Repeater {
                                model: raiz.sugerencias_chips
                                Rectangle {
                                    radius: UiTokens.radiusLg
                                    height: 28
                                    width: sug_text.implicitWidth + 18
                                    color: sug_area.containsMouse
                                        ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.16)
                                        : Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.06)
                                    border.color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.28)
                                    border.width: 1
                                    AppText {
                                        id: sug_text
                                        anchors.centerIn: parent
                                        text: modelData
                                        color: raiz.tema.texto
                                        font.pixelSize: UiTokens.fontSizeMd
                                    }
                                    MouseArea {
                                        id: sug_area
                                        anchors.fill: parent; hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            raiz.prompt_actual = modelData
                                            input_prompt.text = modelData
                                            input_prompt.forceActiveFocus()
                                        }
                                    }
                                }
                            }
                        }
                    }

                    Item { Layout.fillWidth: true; Layout.preferredHeight: UiTokens.spacing16 }
                }
            }

            // ────────────────────────────────────────────────────────
            // (1) TAB SESIÓN ACTIVA
            // ────────────────────────────────────────────────────────
            DjSesionActiva {
                tema: raiz.tema
                shell: raiz.shell
                onAbrirGuardar: dialog_guardar.open()
                onAbrirHistorial: raiz.tab_actual = "historial"
                onAbrirConstruir: raiz.tab_actual = "construir"
                formatDur: raiz._fmtDur
                formatFecha: raiz._fmtFecha
                aW: raiz.aW
                cW: raiz.cW
                mW: raiz.mW
                wW: raiz.wW
            }

            // ────────────────────────────────────────────────────────
            // (2) TAB HISTORIAL (workspace)
            // ────────────────────────────────────────────────────────
            DjHistorial {
                tema: raiz.tema
                shell: raiz.shell
                formatDur: raiz._fmtDur
                formatFecha: raiz._fmtFecha
                cW: raiz.cW
                mW: raiz.mW
                wW: raiz.wW
                onIrAConstruir: raiz.tab_actual = "construir"
                onIrASesion: raiz.tab_actual = "sesion"
            }
        }
    }

    // ─────────────────────────────────────────────────────────────────
    // Popup: guardar sesion como playlist (patrón coherente con
    // VistaConfiguracion: Popup modal con background propio y botones
    // locales en vez de los standardButtons del Qt Dialog clásico).
    // ─────────────────────────────────────────────────────────────────
    Popup {
        id: dialog_guardar
        objectName: "popup_dj_guardar_playlist"
        property string nombreSugerido: djPrivado.intent && djPrivado.intent.prompt
            ? "DJ: " + djPrivado.intent.prompt.substring(0, 40)
            : "Sesión DJ"
        modal: true; focus: true
        parent: raiz
        x: Math.round((raiz.width - width) / 2)
        y: Math.round((raiz.height - height) / 2)
        width: Math.min(560, raiz.width - 40)
        height: guardarCol.implicitHeight + 36
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: 12; color: raiz.tema.superficie
            border.width: 1
            border.color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.48)
        }
        contentItem: ColumnLayout {
            id: guardarCol
            anchors.fill: parent
            anchors.margins: 18
            spacing: UiTokens.spacing12

            AppText {
                text: "Guardar tu sesión como playlist"
                font.pixelSize: UiTokens.fontSizeXl; font.weight: Font.DemiBold
                color: raiz.tema.texto
            }
            AppText {
                text: "Aparecerá en tu biblioteca de playlists con las mismas pistas, en el mismo orden, sin las transiciones."
                color: raiz.tema.textoSec
                font.pixelSize: UiTokens.fontSizeMd; wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 40
                radius: UiTokens.radiusSm
                color: raiz.tema.superficieAlt
                border.color: input_nombre.activeFocus ? raiz.tema.acento : raiz.tema.borde
                border.width: 1
                TextField {
                    id: input_nombre
                    anchors.fill: parent
                    anchors.leftMargin: UiTokens.spacing12; anchors.rightMargin: UiTokens.spacing12
                    verticalAlignment: TextInput.AlignVCenter
                    text: dialog_guardar.nombreSugerido
                    color: raiz.tema.texto
                    selectByMouse: true
                    background: Item {}
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: UiTokens.spacing10
                Item { Layout.fillWidth: true }
                Rectangle {
                    implicitWidth: 120; implicitHeight: 36; radius: 18
                    color: cancel_ma.containsMouse ? raiz.tema.hover : raiz.tema.superficieAlt
                    border.color: raiz.tema.borde; border.width: 1
                    AppText {
                        anchors.centerIn: parent; text: "Cancelar"
                        color: raiz.tema.texto; font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold
                    }
                    MouseArea {
                        id: cancel_ma
                        anchors.fill: parent; hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: dialog_guardar.close()
                    }
                }
                Rectangle {
                    implicitWidth: 180; implicitHeight: 36; radius: 18
                    readonly property bool habilitado: input_nombre.text.trim().length > 0
                    color: habilitado
                        ? (save_ma.containsMouse ? raiz.tema.acentoFuerte : raiz.tema.acento)
                        : raiz.tema.superficieAlt
                    border.color: habilitado ? "transparent" : raiz.tema.borde
                    border.width: habilitado ? 0 : 1
                    opacity: habilitado ? 1.0 : 0.55
                    AppText {
                        anchors.centerIn: parent
                        text: "Guardar en playlists"
                        color: parent.habilitado ? raiz.tema.textoSobreAcento : raiz.tema.textoMuted
                        font.pixelSize: UiTokens.fontSizeBase; font.weight: Font.DemiBold
                    }
                    MouseArea {
                        id: save_ma
                        anchors.fill: parent; hoverEnabled: true
                        enabled: parent.habilitado
                        cursorShape: parent.habilitado ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: {
                            var pid = djPrivado.guardar_como_playlist(input_nombre.text)
                            if (pid > 0) raiz._toast("Sesión guardada en tus playlists.", "info")
                            dialog_guardar.close()
                        }
                    }
                }
            }
        }
    }
}
