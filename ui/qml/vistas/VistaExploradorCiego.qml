import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects

import "../componentes"
import "../componentes/UiUtils.js" as UiUtils

// =============================================================================
// VistaExploradorCiego — Fase 12 (¡A ciegas!)
//
// Experiencia ludica de redescubrimiento sobre la biblioteca local.
//
// Arquitectura UX:
//   - PANTALLA INICIO: tarjetas de modo con conteo y selector de "rondas"
//     (cuantas pistas se jugaran). Sin sliders: botones explicitos.
//   - RONDA: card central con portada/audio enmascarado, input de texto
//     para escribir el titulo (cuando el alfabeto del titulo lo permite)
//     y panel de hints/acciones lateral.
//   - RESUMEN FINAL: animacion + estadisticas + CTA para volver a jugar.
//
// Reglas estrictas:
//   - Sin emojis ni glifos como iconos: TODO con SVGs del proyecto.
//   - Sin colores ni tamanos hardcoded: tema + UiTokens.
//   - El blur de portada cubre la card completa, no solo el centro.
//   - Cuando hay fragmento activo, modo ciego en el reproductor global
//     (definido en ModeloReproductor) censura titulo/artista/album/portada
//     en la barra inferior.
// =============================================================================

Rectangle {
    id: raiz
    objectName: "vista_explorador_ciego"

    property var shell: null
    readonly property var tema: shell ? shell.tema : temaUi
    color: tema.fondo

    // ── Responsive ─────────────────────────────────────────────────────
    readonly property int  hMax: 1180
    readonly property int  hPad: width >= 1320 ? 36 : (width >= 860 ? 24 : 18)
    readonly property real aW:   Math.min(hMax, Math.max(0, width - hPad * 2))
    readonly property bool cW:   aW < 720
    readonly property bool mW:   aW >= 920
    readonly property bool wW:   aW >= 1140

    // ── Pantallas internas ─────────────────────────────────────────────
    property string pantalla: "inicio"  // "inicio" | "jugando" | "fin"
    property var ultimoResumen: ({})

    // Catalogo de modos. Cada uno declara su SVG asociado, etiqueta y un
    // texto descriptivo orientado a jugador, no a desarrollador.
    readonly property var catalogoModos: [
        {
            "id": "portada",
            "titulo": "Adivina por portada",
            "descripcion": "Ves la portada borrosa. ¿Sabes qué es antes de revelar?",
            "icono": "../assets/icons/eye-off.svg",
            "etiqueta": "Visual"
        },
        {
            "id": "audio",
            "titulo": "Adivina por audio",
            "descripcion": "Un fragmento sin pistas visuales. Solo tus oídos.",
            "icono": "../assets/icons/headphones.svg",
            "etiqueta": "Audio"
        },
        {
            "id": "redescubrimiento",
            "titulo": "Redescubrimiento",
            "descripcion": "Pistas que amabas y dejaste de oír hace tiempo.",
            "icono": "../assets/icons/clock.svg",
            "etiqueta": "Memoria"
        },
        {
            "id": "nunca_eliges",
            "titulo": "Lo que nunca eliges",
            "descripcion": "Tu biblioteca infrautilizada. Sorpréndete.",
            "icono": "../assets/icons/compass.svg",
            "etiqueta": "Exploración"
        }
    ]

    // Opciones de cantidad de pistas por ronda. 4 botones — el usuario
    // pidio explicitamente "no mas de 4". El valor 5 queda recomendado por
    // defecto.
    readonly property var opcionesRetos: [3, 5, 8, 12]
    property int retosPorRonda: 5

    // ── Helpers ────────────────────────────────────────────────────────
    function _toast(msg, tono) {
        if (shell) shell.mostrar_toast_global(msg, tono || "info")
    }
    function _modoActual() {
        var id = exploradorCiego.modo_activo
        for (var i = 0; i < catalogoModos.length; i++) {
            if (catalogoModos[i].id === id) return catalogoModos[i]
        }
        return null
    }
    function _disponibles(modoId) {
        var d = exploradorCiego.disponibles_por_modo || {}
        var v = d[modoId]
        return (v === undefined || v === null) ? 0 : parseInt(v) || 0
    }
    function _iniciarModo(modoId) {
        var ok = exploradorCiego.iniciar_ronda(modoId, raiz.retosPorRonda)
        if (ok) raiz.pantalla = "jugando"
    }
    function _esModoVisual() { return exploradorCiego.modo_activo === "portada" }
    function _esModoAudio()  { return exploradorCiego.modo_activo === "audio" }
    function _puedeMostrarPortada() {
        var nivel = (exploradorCiego.reto && exploradorCiego.reto.nivel) || "oculto"
        if (nivel === "total") return true
        if (raiz._esModoVisual()) return true   // portada borrosa visible
        if (raiz._esModoAudio())  return false  // ocultamos hasta revelar
        return true
    }
    function _fragmentoEnCurso() {
        return !!exploradorCiego.fragmento_reproduciendose
    }

    // ── Conexiones ─────────────────────────────────────────────────────
    Connections {
        target: exploradorCiego
        function onRondaTerminada(resumen) {
            raiz.ultimoResumen = resumen || {}
            raiz.pantalla = "fin"
        }
        function onError(msg) { raiz._toast(msg, "warning") }
        function onMensajeUi(msg, tono) { raiz._toast(msg, tono) }
    }

    Component.onCompleted: {
        exploradorCiego.refrescar()
        if (exploradorCiego.ronda_activa) {
            raiz.pantalla = "jugando"
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

        // ── HEADER global ───────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.maximumWidth: raiz.hMax
            Layout.alignment: Qt.AlignHCenter
            spacing: UiTokens.spacing12

            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: UiTokens.spacing2
                AppText {
                    text: "¡A ciegas!"
                    color: raiz.tema.texto
                    font.pixelSize: 28
                    font.weight: Font.DemiBold
                }
                AppText {
                    text: {
                        if (raiz.pantalla === "jugando") {
                            var m = raiz._modoActual()
                            return m ? ("Modo: " + m.titulo) : "Modo en curso"
                        }
                        if (raiz.pantalla === "fin") return "Ronda terminada"
                        return "Redescubre tu biblioteca jugando con ella"
                    }
                    color: raiz.tema.textoMuted
                    font.pixelSize: UiTokens.fontSizeMd
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }

            BotonPlano {
                visible: raiz.pantalla === "jugando"
                texto: "Terminar ronda"
                iconSource: "../assets/icons/flag.svg"
                onClicked: exploradorCiego.terminar_ronda()
            }
        }

        // ── STACKLAYOUT de pantallas ─────────────────────────────────
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.maximumWidth: raiz.hMax
            Layout.alignment: Qt.AlignHCenter
            currentIndex: {
                if (raiz.pantalla === "jugando") return 1
                if (raiz.pantalla === "fin")     return 2
                return 0
            }

            // ────────────────────────────────────────────────────────
            // (0) INICIO
            // ────────────────────────────────────────────────────────
            Item {
                ScrollView {
                    id: scrollInicio
                    anchors.fill: parent
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ScrollBar.vertical: AppScrollBar {
                        parent: scrollInicio
                        anchors.top: parent.top
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        z: 20
                        tema: raiz.tema
                        policy: scrollInicio.contentHeight > scrollInicio.height + 2 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
                    }
                    contentWidth: availableWidth

                    ColumnLayout {
                        width: scrollInicio.availableWidth
                        spacing: UiTokens.spacing14

                        // Estado vacio total: sin biblioteca.
                        EmptyState {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 280
                            Layout.alignment: Qt.AlignHCenter
                            visible: !exploradorCiego.hay_biblioteca
                            tema: raiz.tema
                            title: "Aún no hay con qué jugar"
                            description: "Importa música a tu biblioteca y vuelve para empezar a redescubrir."
                            iconSource: "../assets/icons/nav/a_ciegas.svg"
                        }

                        // CTA + selector de cantidad de pistas.
                        Rectangle {
                            Layout.fillWidth: true
                            visible: exploradorCiego.hay_biblioteca
                            radius: UiTokens.radiusLg
                            color: raiz.tema.superficie
                            border.color: Qt.rgba(raiz.tema.borde.r, raiz.tema.borde.g, raiz.tema.borde.b, 0.85)
                            border.width: 1
                            implicitHeight: introCol.implicitHeight + UiTokens.spacing20 * 2

                            ColumnLayout {
                                id: introCol
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: UiTokens.spacing20
                                spacing: UiTokens.spacing8

                                AppText {
                                    text: "Elige cómo quieres jugar"
                                    color: raiz.tema.texto
                                    font.pixelSize: UiTokens.fontSize2xl
                                    font.weight: Font.DemiBold
                                    Layout.fillWidth: true
                                }
                                AppText {
                                    text: "Cada modo construye una ronda de canciones aleatorias de tu biblioteca. Puedes adivinar escribiendo el título o pedir pistas. Si te rindes, revelamos y seguimos."
                                    color: raiz.tema.textoMuted
                                    font.pixelSize: UiTokens.fontSizeMd
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                    lineHeight: 1.25
                                }

                                AppText {
                                    text: "Canciones por ronda"
                                    color: raiz.tema.textoSec
                                    font.pixelSize: UiTokens.fontSizeMd
                                    font.weight: Font.DemiBold
                                    Layout.topMargin: UiTokens.spacing8
                                }
                                Flow {
                                    Layout.fillWidth: true
                                    spacing: UiTokens.spacing8
                                    Repeater {
                                        model: raiz.opcionesRetos
                                        delegate: PillOption {
                                            texto: modelData + " canciones"
                                            activo: raiz.retosPorRonda === modelData
                                            onClicked: raiz.retosPorRonda = modelData
                                        }
                                    }
                                }
                            }
                        }

                        // Grid de modos disponibles.
                        Grid {
                            Layout.fillWidth: true
                            visible: exploradorCiego.hay_biblioteca
                            columns: raiz.wW ? 2 : (raiz.mW ? 2 : 1)
                            columnSpacing: UiTokens.spacing12
                            rowSpacing: UiTokens.spacing12

                            Repeater {
                                model: raiz.catalogoModos
                                delegate: TarjetaModo {
                                    width: (raiz.aW - (parent.columns - 1) * UiTokens.spacing12) / parent.columns
                                    titulo: modelData.titulo
                                    descripcion: modelData.descripcion
                                    iconSource: modelData.icono
                                    etiqueta: modelData.etiqueta
                                    disponibles: raiz._disponibles(modelData.id)
                                    onActivado: raiz._iniciarModo(modelData.id)
                                }
                            }
                        }

                        Item { Layout.fillWidth: true; Layout.preferredHeight: UiTokens.spacing16 }
                    }
                }
            }

            // ────────────────────────────────────────────────────────
            // (1) JUGANDO
            // ────────────────────────────────────────────────────────
            Item {
                ScrollView {
                    id: scrollJuego
                    anchors.fill: parent
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ScrollBar.vertical: AppScrollBar {
                        parent: scrollJuego
                        anchors.top: parent.top
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        z: 20
                        tema: raiz.tema
                        policy: scrollJuego.contentHeight > scrollJuego.height + 2 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
                    }
                    contentWidth: availableWidth

                    ColumnLayout {
                        width: scrollJuego.availableWidth
                        spacing: UiTokens.spacing14

                        // Barra de progreso + contadores.
                        Rectangle {
                            Layout.fillWidth: true
                            radius: UiTokens.radiusLg
                            color: raiz.tema.superficie
                            border.color: Qt.rgba(raiz.tema.borde.r, raiz.tema.borde.g, raiz.tema.borde.b, 0.85)
                            border.width: 1
                            implicitHeight: progresoCol.implicitHeight + UiTokens.spacing14 * 2

                            ColumnLayout {
                                id: progresoCol
                                anchors.fill: parent
                                anchors.margins: UiTokens.spacing14
                                spacing: UiTokens.spacing8

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: UiTokens.spacing12
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: UiTokens.spacing2
                                        AppText {
                                            text: "Canción " + (exploradorCiego.indice_reto + 1) + " de " + exploradorCiego.total_retos
                                            color: raiz.tema.texto
                                            font.pixelSize: UiTokens.fontSizeLg
                                            font.weight: Font.DemiBold
                                        }
                                        AppText {
                                            readonly property var c: exploradorCiego.conteo
                                            text: (c.acertados || 0) + " acertadas · "
                                                  + (c.revelados || 0) + " reveladas · "
                                                  + (c.pasados || 0) + " saltadas"
                                            color: raiz.tema.textoMuted
                                            font.pixelSize: UiTokens.fontSizeSm
                                        }
                                    }
                                    Rectangle {
                                        visible: !!raiz._modoActual()
                                        implicitWidth: badgeText.implicitWidth + 24
                                        implicitHeight: 24
                                        radius: 12
                                        color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.12)
                                        border.color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.28)
                                        border.width: 1
                                        AppText {
                                            id: badgeText
                                            anchors.centerIn: parent
                                            text: {
                                                var m = raiz._modoActual()
                                                return m ? m.etiqueta : ""
                                            }
                                            color: raiz.tema.acento
                                            font.pixelSize: UiTokens.fontSizeXs
                                            font.weight: Font.DemiBold
                                            font.letterSpacing: 0.6
                                        }
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 6
                                    radius: 3
                                    color: Qt.rgba(raiz.tema.borde.r, raiz.tema.borde.g, raiz.tema.borde.b, 0.5)
                                    Rectangle {
                                        height: parent.height
                                        radius: 3
                                        color: raiz.tema.acento
                                        width: {
                                            if (exploradorCiego.total_retos <= 0) return 0
                                            var f = (exploradorCiego.indice_reto + 1) / exploradorCiego.total_retos
                                            return parent.width * Math.max(0, Math.min(1, f))
                                        }
                                        Behavior on width {
                                            NumberAnimation { duration: UiTokens.durationSlow; easing.type: Easing.OutQuad }
                                        }
                                    }
                                }
                            }
                        }

                        // Tarjeta central del reto.
                        TarjetaReto {
                            Layout.fillWidth: true
                            reto: exploradorCiego.reto || ({})
                            modoActual: exploradorCiego.modo_activo
                            puedeMostrarPortada: raiz._puedeMostrarPortada()
                            fragmentoActivo: raiz._fragmentoEnCurso()
                            esModoVisual: raiz._esModoVisual()
                            anchoVista: raiz.aW
                            cw: raiz.cW

                            onReproducirFragmento: exploradorCiego.reproducir_fragmento()
                            onDetenerFragmento: exploradorCiego.detener_fragmento()
                            // El modelo se encarga de emitir el toast con el
                            // resultado: aqui solo disparamos la accion.
                            // Devolver desde una signal QML no funciona — por
                            // eso movimos la logica de feedback al modelo.
                            onIntentarAdivinar: function(texto) { exploradorCiego.intentar_adivinar(texto) }
                            onRevelarHint: function(clave) { exploradorCiego.revelar_hint(clave) }
                            onMarcarAcertada: exploradorCiego.marcar_acertada()
                            onRevelarTitulo: exploradorCiego.revelar_titulo()
                            onRendirse: function() {
                                // Orden importa: primero marcar como
                                // "pasada" mientras el estado es EN_CURSO;
                                // luego revelar el titulo. Revelar antes
                                // dejaria estado=REVELADO y la rendicion
                                // no se reflejaria en el resumen.
                                exploradorCiego.marcar_pasado()
                                exploradorCiego.revelar_titulo()
                            }
                            onReproducirCompleta: exploradorCiego.reproducir_completa()
                            onAgregarACola: exploradorCiego.agregar_a_cola()
                            onAlternarFavorita: function(pid) { exploradorCiego.alternar_favorita(pid) }
                            onIrAArtista: function() {
                                if (shell && shell.navegar_a_vista) shell.navegar_a_vista("biblioteca")
                            }
                            onIrAAlbum: function() {
                                if (shell && shell.navegar_a_vista) shell.navegar_a_vista("biblioteca")
                            }
                        }

                        // Navegacion final de ronda.
                        Rectangle {
                            Layout.fillWidth: true
                            radius: UiTokens.radiusLg
                            color: raiz.tema.superficie
                            border.color: Qt.rgba(raiz.tema.borde.r, raiz.tema.borde.g, raiz.tema.borde.b, 0.85)
                            border.width: 1
                            implicitHeight: navCol.implicitHeight + UiTokens.spacing14 * 2

                            // Solo "Siguiente": una vez avanzas, la cancion
                            // anterior queda abandonada. En un juego de
                            // adivinanza no tiene sentido retroceder (verias
                            // la respuesta de algo que ya pasaste). Si fuese
                            // util en el futuro, el servicio aun expone
                            // `retroceder()`; aqui solo lo escondemos.
                            RowLayout {
                                id: navCol
                                anchors.fill: parent
                                anchors.margins: UiTokens.spacing14
                                spacing: UiTokens.spacing10

                                Item { Layout.fillWidth: true }
                                BotonPrincipal {
                                    Layout.preferredWidth: 180
                                    readonly property bool esUltima: exploradorCiego.indice_reto + 1 >= exploradorCiego.total_retos
                                    texto: esUltima ? "Terminar ronda" : "Siguiente canción"
                                    iconSource: esUltima ? "../assets/icons/check.svg" : "../assets/icons/chevron-right.svg"
                                    onClicked: exploradorCiego.siguiente_reto()
                                }
                            }
                        }

                        Item { Layout.fillWidth: true; Layout.preferredHeight: UiTokens.spacing16 }
                    }
                }
            }

            // ────────────────────────────────────────────────────────
            // (2) FIN
            // ────────────────────────────────────────────────────────
            Item {
                ColumnLayout {
                    anchors.centerIn: parent
                    width: Math.min(parent.width, 560)
                    spacing: UiTokens.spacing16

                    Item {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 120
                        Layout.preferredHeight: 120

                        Rectangle {
                            anchors.centerIn: parent
                            width: 96; height: 96; radius: 48
                            color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.12)
                            border.color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.36)
                            border.width: 2

                            SequentialAnimation on scale {
                                running: raiz.pantalla === "fin"
                                loops: Animation.Infinite
                                NumberAnimation { from: 1.0; to: 1.08; duration: 900; easing.type: Easing.InOutQuad }
                                NumberAnimation { from: 1.08; to: 1.0; duration: 900; easing.type: Easing.InOutQuad }
                            }

                            IconoSvg {
                                anchors.centerIn: parent
                                size: 44
                                source: "../assets/icons/trophy.svg"
                                colorIcono: raiz.tema.acento
                            }
                        }
                    }

                    AppText {
                        Layout.alignment: Qt.AlignHCenter
                        text: "¡Ronda terminada!"
                        color: raiz.tema.texto
                        font.pixelSize: 22
                        font.weight: Font.DemiBold
                    }

                    AppText {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.fillWidth: true
                        text: {
                            var r = raiz.ultimoResumen || {}
                            var total = parseInt(r.total || 0)
                            if (total <= 0) return ""
                            var ac = parseInt(r.acertados || 0)
                            var re = parseInt(r.revelados || 0)
                            var pa = parseInt(r.pasados || 0)
                            var partes = []
                            if (ac > 0) partes.push(ac + (ac === 1 ? " acertada" : " acertadas"))
                            if (re > 0) partes.push(re + (re === 1 ? " revelada" : " reveladas"))
                            if (pa > 0) partes.push(pa + (pa === 1 ? " saltada" : " saltadas"))
                            if (partes.length === 0) return ""
                            return partes.join(" · ")
                        }
                        color: raiz.tema.textoSec
                        font.pixelSize: UiTokens.fontSizeBase
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }

                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.topMargin: UiTokens.spacing12
                        spacing: UiTokens.spacing10
                        BotonPlano {
                            texto: "Elegir otro modo"
                            iconSource: "../assets/icons/grid.svg"
                            onClicked: {
                                raiz.pantalla = "inicio"
                                exploradorCiego.refrescar()
                            }
                        }
                        BotonPrincipal {
                            texto: "Otra ronda igual"
                            iconSource: "../assets/icons/refresh.svg"
                            visible: !!raiz.ultimoResumen && !!raiz.ultimoResumen.modo
                            onClicked: {
                                var m = raiz.ultimoResumen && raiz.ultimoResumen.modo
                                if (m) raiz._iniciarModo(m)
                            }
                        }
                    }
                }
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // COMPONENTES INTERNOS
    // ═══════════════════════════════════════════════════════════════════

    // IconoSvg — pinta un SVG aplicando un color del tema.
    // Mantenemos este componente local para no propagar dependencias del
    // visor de la app principal: aqui usamos solo Image + MultiEffect.
    component IconoSvg: Item {
        property string source: ""
        property color colorIcono: raiz.tema.texto
        property int size: UiTokens.iconMd
        implicitWidth: size
        implicitHeight: size

        Image {
            id: imgIcono
            anchors.fill: parent
            source: parent.source
            sourceSize.width: parent.size * 2
            sourceSize.height: parent.size * 2
            smooth: true
            // opacidad 0 + MultiEffect: tecnicismo Qt para colorizar sin
            // mostrar el icono original. El visible: source !== "" evita
            // pintar un cuadro vacio cuando no hay svg.
            opacity: 0
            visible: parent.source !== ""
        }
        MultiEffect {
            anchors.fill: imgIcono
            source: imgIcono
            colorization: 1.0
            colorizationColor: parent.colorIcono
            visible: parent.source !== ""
        }
    }

    // PillOption — boton tipo pildora (igual estilo que VistaConfiguracion).
    component PillOption: Rectangle {
        property string texto: ""
        property bool activo: false
        signal clicked()

        implicitWidth: pillText.implicitWidth + 32
        height: 38
        radius: 19
        color: activo ? raiz.tema.acento : (pillMa.containsMouse ? raiz.tema.hover : raiz.tema.superficieAlt)
        border.color: activo ? raiz.tema.acento : (pillMa.containsMouse ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.45) : raiz.tema.borde)
        border.width: 1

        Behavior on color { ColorAnimation { duration: 180 } }
        Behavior on border.color { ColorAnimation { duration: 180 } }

        AppText {
            id: pillText
            anchors.centerIn: parent
            text: parent.texto
            color: parent.activo ? raiz.tema.textoSobreAcento : raiz.tema.textoSec
            font.pixelSize: UiTokens.fontSizeBase
            font.weight: parent.activo ? Font.DemiBold : Font.Normal
            Behavior on color { ColorAnimation { duration: 180 } }
        }

        MouseArea {
            id: pillMa
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: parent.clicked()
        }
    }

    // BotonPlano — pildora secundaria con icono opcional.
    // Variantes de "destacado":
    //   "ninguno" (default)  -> apariencia neutra (superficie + borde).
    //   "acento"             -> tinta acento del tema (favoritas activas).
    //   "peligro"            -> tinta peligro del tema (Me rindo).
    component BotonPlano: Rectangle {
        property string texto: ""
        property string iconSource: ""
        property string destacar: "ninguno"

        readonly property color colorDestacado: destacar === "peligro"
            ? raiz.tema.peligro
            : (destacar === "acento" ? raiz.tema.acento : raiz.tema.texto)
        readonly property bool tieneDestaque: destacar !== "ninguno"
        signal clicked()

        implicitHeight: 34
        implicitWidth: filaContenido.implicitWidth + 28
        radius: 17
        color: bpMa.containsMouse
            ? raiz.tema.hover
            : (tieneDestaque
                ? Qt.rgba(colorDestacado.r, colorDestacado.g, colorDestacado.b, 0.12)
                : raiz.tema.superficieAlt)
        border.color: tieneDestaque
            ? Qt.rgba(colorDestacado.r, colorDestacado.g, colorDestacado.b, 0.30)
            : raiz.tema.borde
        border.width: 1

        Row {
            id: filaContenido
            anchors.centerIn: parent
            spacing: UiTokens.spacing6
            IconoSvg {
                visible: iconSource !== ""
                source: iconSource
                size: 14
                colorIcono: tieneDestaque ? colorDestacado : raiz.tema.texto
                anchors.verticalCenter: parent.verticalCenter
            }
            AppText {
                text: parent.parent.texto
                color: parent.parent.tieneDestaque
                    ? parent.parent.colorDestacado
                    : raiz.tema.texto
                font.pixelSize: UiTokens.fontSizeMd
                font.weight: Font.DemiBold
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        MouseArea {
            id: bpMa
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: parent.clicked()
        }
    }

    // BotonPrincipal — CTA primaria (acento).
    component BotonPrincipal: Rectangle {
        property string texto: ""
        property string iconSource: ""
        property bool habilitado: true
        signal clicked()

        implicitHeight: 40
        implicitWidth: filaPrincipal.implicitWidth + 36
        radius: UiTokens.radiusPill
        color: !habilitado
            ? raiz.tema.superficieAlt
            : (bpMa.containsMouse ? raiz.tema.acentoFuerte : raiz.tema.acento)
        border.color: habilitado ? "transparent" : raiz.tema.borde
        border.width: habilitado ? 0 : 1
        opacity: habilitado ? 1.0 : 0.55

        Row {
            id: filaPrincipal
            anchors.centerIn: parent
            spacing: UiTokens.spacing6
            AppText {
                text: parent.parent.texto
                color: parent.parent.habilitado ? raiz.tema.textoSobreAcento : raiz.tema.textoMuted
                font.pixelSize: UiTokens.fontSizeBase
                font.weight: Font.DemiBold
                anchors.verticalCenter: parent.verticalCenter
            }
            IconoSvg {
                visible: parent.parent.iconSource !== ""
                source: parent.parent.iconSource
                size: 14
                colorIcono: parent.parent.habilitado ? raiz.tema.textoSobreAcento : raiz.tema.textoMuted
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        MouseArea {
            id: bpMa
            anchors.fill: parent
            hoverEnabled: true
            enabled: parent.habilitado
            cursorShape: parent.habilitado ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: parent.clicked()
        }
    }

    // BotonIcono — circular, solo icono. Para favorita y play del reto.
    component BotonIcono: Rectangle {
        property string iconSource: ""
        property color iconColor: raiz.tema.texto
        property color fondoHover: raiz.tema.hover
        property color fondoBase: "transparent"
        property color bordeColor: "transparent"
        property int bordeWidth: 0
        property int diametro: 34
        signal clicked()

        implicitWidth: diametro
        implicitHeight: diametro
        radius: diametro / 2
        color: biMa.containsMouse ? fondoHover : fondoBase
        border.color: bordeColor
        border.width: bordeWidth

        IconoSvg {
            anchors.centerIn: parent
            source: parent.iconSource
            size: Math.round(parent.diametro * 0.46)
            colorIcono: parent.iconColor
        }

        MouseArea {
            id: biMa
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: parent.clicked()
        }
    }

    // TarjetaModo — card de seleccion de modo en pantalla inicio.
    component TarjetaModo: Rectangle {
        id: tarjetaModo
        property string titulo: ""
        property string descripcion: ""
        property string iconSource: ""
        property string etiqueta: ""
        property int disponibles: 0
        signal activado()

        readonly property bool habilitado: tarjetaModo.disponibles > 0

        implicitHeight: 170
        radius: UiTokens.radiusLg
        color: tarjetaModoMa.containsMouse && habilitado
               ? Qt.lighter(raiz.tema.superficie, 1.05)
               : raiz.tema.superficie
        border.color: tarjetaModoMa.containsMouse && habilitado
            ? Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.45)
            : Qt.rgba(raiz.tema.borde.r, raiz.tema.borde.g, raiz.tema.borde.b, 0.85)
        border.width: 1
        antialiasing: true
        clip: true
        Behavior on color { ColorAnimation { duration: UiTokens.durationFast } }
        Behavior on border.color { ColorAnimation { duration: UiTokens.durationFast } }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: UiTokens.spacing16
            spacing: UiTokens.spacing8

            RowLayout {
                Layout.fillWidth: true
                spacing: UiTokens.spacing10

                Rectangle {
                    Layout.preferredWidth: 44
                    Layout.preferredHeight: 44
                    radius: 22
                    color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.14)
                    border.color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.30)
                    border.width: 1
                    IconoSvg {
                        anchors.centerIn: parent
                        source: tarjetaModo.iconSource
                        size: 22
                        colorIcono: raiz.tema.acento
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 0

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: UiTokens.spacing6
                        AppText {
                            text: tarjetaModo.titulo
                            color: raiz.tema.texto
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Rectangle {
                            implicitHeight: 18
                            implicitWidth: etiqText.implicitWidth + 12
                            radius: 9
                            color: Qt.rgba(raiz.tema.textoSec.r, raiz.tema.textoSec.g, raiz.tema.textoSec.b, 0.10)
                            AppText {
                                id: etiqText
                                anchors.centerIn: parent
                                text: tarjetaModo.etiqueta
                                color: raiz.tema.textoMuted
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                                font.letterSpacing: 0.5
                            }
                        }
                    }
                    AppText {
                        Layout.fillWidth: true
                        text: tarjetaModo.descripcion
                        color: raiz.tema.textoSec
                        font.pixelSize: UiTokens.fontSizeMd
                        wrapMode: Text.WordWrap
                        lineHeight: 1.25
                    }
                }
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: UiTokens.spacing8
                spacing: UiTokens.spacing8
                AppText {
                    text: tarjetaModo.habilitado
                          ? (tarjetaModo.disponibles + " pistas listas")
                          : "Sin pistas disponibles"
                    color: tarjetaModo.habilitado ? raiz.tema.textoSec : raiz.tema.textoMuted
                    font.pixelSize: UiTokens.fontSizeSm
                    Layout.fillWidth: true
                }
                BotonPrincipal {
                    texto: "Jugar"
                    habilitado: tarjetaModo.habilitado
                    onClicked: tarjetaModo.activado()
                }
            }
        }

        MouseArea {
            id: tarjetaModoMa
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: tarjetaModo.habilitado ? Qt.PointingHandCursor : Qt.ArrowCursor
            enabled: tarjetaModo.habilitado
            onClicked: tarjetaModo.activado()
        }
    }

    // TarjetaReto — card central del juego.
    // En desktop usa dos columnas (portada + datos) para aprovechar el
    // ancho. En compacto se apila verticalmente.
    component TarjetaReto: Rectangle {
        id: tarjetaReto
        property var reto: ({})
        property string modoActual: ""
        property bool puedeMostrarPortada: false
        property bool fragmentoActivo: false
        property bool esModoVisual: false
        property real anchoVista: 0
        property bool cw: false

        signal reproducirFragmento()
        signal detenerFragmento()
        signal intentarAdivinar(string texto)
        signal revelarHint(string clave)
        signal marcarAcertada()
        signal revelarTitulo()
        signal rendirse()
        signal reproducirCompleta()
        signal agregarACola()
        signal alternarFavorita(int pistaId)
        signal irAArtista()
        signal irAAlbum()

        radius: UiTokens.radiusLg
        color: raiz.tema.superficie
        border.color: Qt.rgba(raiz.tema.borde.r, raiz.tema.borde.g, raiz.tema.borde.b, 0.85)
        border.width: 1
        antialiasing: true
        clip: true
        implicitHeight: contenidoLayout.implicitHeight + UiTokens.spacing20 * 2

        readonly property string nivel: tarjetaReto.reto.nivel || "oculto"
        readonly property bool artistaRevelado: nivel === "artista" || nivel === "album" || nivel === "total"
        readonly property bool albumRevelado:   nivel === "album"   || nivel === "total"
        readonly property bool tituloRevelado:  nivel === "total"
        readonly property bool retoActivo: !!tarjetaReto.reto.pista_id
        readonly property bool requiereEscritura: !!tarjetaReto.reto.requiere_escritura
        readonly property string alfabeto: tarjetaReto.reto.alfabeto || "latino"

        readonly property string tituloMostrado:  tituloRevelado  ? (reto.titulo || "")  : "???"
        readonly property string artistaMostrado: artistaRevelado ? (reto.artista || "") : "???"
        readonly property string albumMostrado:   albumRevelado   ? (reto.album || "")   : "???"
        readonly property string portadaRuta:     reto.portada_ruta || ""
        readonly property var hintsVisibles:      reto.hints_visibles || ({})
        readonly property int  intentosFallidos:  parseInt(reto.intentos_fallidos || 0)

        // Tamaño compartido para portada y placeholder. Diseñado para que
        // el espacio interior se aproveche bien tanto en compact como wide.
        readonly property int ladoPortada: tarjetaReto.cw
            ? Math.max(140, Math.min(280, tarjetaReto.anchoVista - UiTokens.spacing20 * 2))
            : Math.max(220, Math.min(300, tarjetaReto.width * 0.34))

        GridLayout {
            id: contenidoLayout
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: UiTokens.spacing20
            columns: tarjetaReto.cw ? 1 : 2
            columnSpacing: UiTokens.spacing20
            rowSpacing: UiTokens.spacing14

            // ── Columna izquierda: portada/audio + play ─────────────
            // En modo compacto (cw=true) se centra horizontalmente sin
            // estirarse a fillWidth: la portada SIEMPRE debe ser cuadrada
            // (width == height == ladoPortada), independientemente del ancho.
            Item {
                Layout.preferredWidth:  tarjetaReto.ladoPortada
                Layout.preferredHeight: tarjetaReto.ladoPortada
                Layout.alignment:       Qt.AlignTop | Qt.AlignHCenter

                // Fondo de la zona portada/audio (color tema, no hardcoded).
                Rectangle {
                    id: portadaFondo
                    anchors.fill: parent
                    radius: UiTokens.radiusLg
                    color: raiz.tema.superficieAlt
                    border.color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.18)
                    border.width: 1
                    clip: true
                }

                // Portada visible (en modo audio se oculta hasta revelar).
                // Para que el blur cubra TODO el contenedor sin "halo" en
                // los bordes, montamos la Image dentro de un Item con
                // anclajes y aplicamos MultiEffect anclado al mismo Item.
                // Esto evita el bug donde el blur deja franjas nitidas.
                Item {
                    id: capaPortada
                    anchors.fill: portadaFondo
                    anchors.margins: 1
                    visible: tarjetaReto.puedeMostrarPortada && tarjetaReto.portadaRuta !== ""
                    clip: true
                    layer.enabled: true
                    layer.smooth: true

                    Image {
                        id: imgPortada
                        anchors.fill: parent
                        source: tarjetaReto.portadaRuta
                                ? UiUtils.toMediaSource(tarjetaReto.portadaRuta)
                                : ""
                        fillMode: Image.PreserveAspectCrop
                        smooth: true
                        asynchronous: true
                        sourceSize.width: Math.max(320, tarjetaReto.ladoPortada * 2)
                        sourceSize.height: Math.max(320, tarjetaReto.ladoPortada * 2)
                    }
                }

                // Capa de blur: una sola MultiEffect anclada al MISMO area
                // que la portada. Cuando el reto no requiere blur (album
                // revelado o no es modo visual), opacidad 0.
                MultiEffect {
                    anchors.fill: capaPortada
                    source: capaPortada
                    visible: tarjetaReto.esModoVisual && !tarjetaReto.tituloRevelado
                    blurEnabled: true
                    blurMax: 96
                    // Niveles progresivos: arrancamos casi opaco, bajamos a
                    // medio al revelar artista, casi nitido al revelar album,
                    // nitido total al revelar todo (no llega aqui porque
                    // visible: false en ese caso).
                    blur: tarjetaReto.albumRevelado ? 0.32
                          : (tarjetaReto.artistaRevelado ? 0.62 : 0.98)
                    saturation: tarjetaReto.tituloRevelado ? 0.0 : -0.20
                }

                // Placeholder cuando NO mostramos portada (modo audio).
                Item {
                    anchors.centerIn: portadaFondo
                    visible: !tarjetaReto.puedeMostrarPortada || tarjetaReto.portadaRuta === ""

                    Rectangle {
                        anchors.centerIn: parent
                        width: 112; height: 112; radius: 56
                        color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.10)
                        border.color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.30)
                        border.width: 1

                        SequentialAnimation on scale {
                            running: tarjetaReto.fragmentoActivo
                            loops: Animation.Infinite
                            NumberAnimation { from: 1.0; to: 1.10; duration: 700; easing.type: Easing.InOutQuad }
                            NumberAnimation { from: 1.10; to: 1.0; duration: 700; easing.type: Easing.InOutQuad }
                        }

                        IconoSvg {
                            anchors.centerIn: parent
                            source: "../assets/icons/headphones.svg"
                            size: 52
                            colorIcono: raiz.tema.acento
                        }
                    }
                }

                // Boton de play/stop fragmento — flota sobre la portada.
                BotonIcono {
                    anchors.bottom: portadaFondo.bottom
                    anchors.right: portadaFondo.right
                    anchors.bottomMargin: UiTokens.spacing10
                    anchors.rightMargin: UiTokens.spacing10
                    diametro: 56
                    visible: tarjetaReto.retoActivo
                    iconSource: tarjetaReto.fragmentoActivo
                                ? "../assets/icons/pause.svg"
                                : "../assets/icons/play.svg"
                    fondoBase: tarjetaReto.fragmentoActivo
                               ? raiz.tema.acentoFuerte
                               : raiz.tema.acento
                    fondoHover: raiz.tema.acentoFuerte
                    iconColor: raiz.tema.textoSobreAcento
                    onClicked: {
                        if (tarjetaReto.fragmentoActivo) tarjetaReto.detenerFragmento()
                        else tarjetaReto.reproducirFragmento()
                    }
                }
            }

            // ── Columna derecha: datos + input + acciones ───────────
            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                spacing: UiTokens.spacing10

                // Metadatos siempre visibles, censura segun nivel.
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: UiTokens.spacing4

                    AppText {
                        text: "TÍTULO"
                        color: raiz.tema.textoMuted
                        font.pixelSize: UiTokens.fontSizeXs
                        font.weight: Font.DemiBold
                        font.letterSpacing: 0.8
                    }
                    AppText {
                        text: tarjetaReto.tituloMostrado
                        color: tarjetaReto.tituloRevelado ? raiz.tema.texto : raiz.tema.textoMuted
                        font.pixelSize: 22
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: UiTokens.spacing4
                        spacing: UiTokens.spacing16

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            AppText {
                                text: "ARTISTA"
                                color: raiz.tema.textoMuted
                                font.pixelSize: UiTokens.fontSizeXs
                                font.weight: Font.DemiBold
                                font.letterSpacing: 0.8
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: UiTokens.spacing6
                                AppText {
                                    text: tarjetaReto.artistaMostrado
                                    color: tarjetaReto.artistaRevelado ? raiz.tema.texto : raiz.tema.textoMuted
                                    font.pixelSize: UiTokens.fontSizeLg
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                BotonIcono {
                                    visible: tarjetaReto.artistaRevelado
                                             && tarjetaReto.reto.artista_id
                                             && parseInt(tarjetaReto.reto.artista_id) > 0
                                    diametro: 24
                                    iconSource: "../assets/icons/chevron-right.svg"
                                    iconColor: raiz.tema.acento
                                    fondoBase: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.08)
                                    bordeColor: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.28)
                                    bordeWidth: 1
                                    onClicked: tarjetaReto.irAArtista()
                                }
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            AppText {
                                text: "ÁLBUM"
                                color: raiz.tema.textoMuted
                                font.pixelSize: UiTokens.fontSizeXs
                                font.weight: Font.DemiBold
                                font.letterSpacing: 0.8
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: UiTokens.spacing6
                                AppText {
                                    text: tarjetaReto.albumMostrado
                                    color: tarjetaReto.albumRevelado ? raiz.tema.texto : raiz.tema.textoMuted
                                    font.pixelSize: UiTokens.fontSizeBase
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                BotonIcono {
                                    visible: tarjetaReto.albumRevelado
                                             && tarjetaReto.reto.album_id
                                             && parseInt(tarjetaReto.reto.album_id) > 0
                                    diametro: 24
                                    iconSource: "../assets/icons/chevron-right.svg"
                                    iconColor: raiz.tema.acento
                                    fondoBase: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.08)
                                    bordeColor: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.28)
                                    bordeWidth: 1
                                    onClicked: tarjetaReto.irAAlbum()
                                }
                            }
                        }
                    }

                    AppText {
                        visible: tarjetaReto.tituloRevelado
                        Layout.topMargin: UiTokens.spacing6
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        color: raiz.tema.textoMuted
                        font.pixelSize: UiTokens.fontSizeSm
                        font.italic: true
                        text: {
                            var v = parseInt(tarjetaReto.reto.veces_reproducida || 0)
                            if (v <= 0) return "No la habías reproducido nunca."
                            if (v === 1) return "La has reproducido 1 vez."
                            return "La has reproducido " + v + " veces."
                        }
                    }
                }

                // ── Sistema de adivinanza ──────────────────────────
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: UiTokens.spacing6
                    spacing: UiTokens.spacing6
                    visible: tarjetaReto.retoActivo && !tarjetaReto.tituloRevelado

                    // Caso A: alfabeto latino — input de texto.
                    Rectangle {
                        Layout.fillWidth: true
                        visible: tarjetaReto.requiereEscritura
                        implicitHeight: 44
                        radius: 22
                        color: raiz.tema.superficieAlt
                        border.color: inputAdivinanza.activeFocus
                            ? raiz.tema.acento
                            : raiz.tema.borde
                        border.width: 1

                        Behavior on border.color { ColorAnimation { duration: 160 } }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: UiTokens.spacing16
                            anchors.rightMargin: UiTokens.spacing6
                            spacing: UiTokens.spacing8

                            IconoSvg {
                                source: "../assets/icons/search.svg"
                                size: 16
                                colorIcono: raiz.tema.textoMuted
                                Layout.alignment: Qt.AlignVCenter
                            }
                            TextField {
                                id: inputAdivinanza
                                Layout.fillWidth: true
                                placeholderText: "Escribe el título y pulsa Enter…"
                                placeholderTextColor: raiz.tema.textoMuted
                                color: raiz.tema.texto
                                font.pixelSize: UiTokens.fontSizeLg
                                background: Item {}
                                selectByMouse: true
                                // ID del reto cuyo input estamos editando.
                                // Cuando cambia (avanzar/retroceder/terminar),
                                // limpiamos el campo: mantener texto residual
                                // de la pista anterior era confuso.
                                property int retoIdActual: parseInt(tarjetaReto.reto.pista_id || 0)
                                onRetoIdActualChanged: text = ""
                                // El modelo emite el toast con el resultado:
                                // aqui solo limpiamos el input despues de cada
                                // intento para que la siguiente jugada
                                // empiece en blanco.
                                onAccepted: {
                                    var t = text.trim()
                                    if (t.length === 0) return
                                    tarjetaReto.intentarAdivinar(t)
                                    text = ""
                                }
                            }
                            BotonPrincipal {
                                texto: "Adivinar"
                                iconSource: "../assets/icons/check.svg"
                                onClicked: inputAdivinanza.accepted()
                            }
                        }
                    }

                    // Caso B: alfabeto no latino — boton "La sé" como salida.
                    BotonPrincipal {
                        Layout.fillWidth: true
                        visible: !tarjetaReto.requiereEscritura
                        texto: "¡La sé!"
                        iconSource: "../assets/icons/check.svg"
                        onClicked: tarjetaReto.marcarAcertada()
                    }

                    // Feedback de progreso de intentos.
                    AppText {
                        visible: tarjetaReto.intentosFallidos > 0
                        text: tarjetaReto.intentosFallidos === 1
                            ? "1 intento fallido. ¿Pides una pista?"
                            : tarjetaReto.intentosFallidos + " intentos fallidos. ¿Necesitas otra pista?"
                        color: raiz.tema.textoMuted
                        font.pixelSize: UiTokens.fontSizeSm
                        font.italic: true
                        Layout.fillWidth: true
                    }
                }

                // ── Pistas (hints) ─────────────────────────────────
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: UiTokens.spacing6
                    spacing: UiTokens.spacing4
                    visible: tarjetaReto.retoActivo && !tarjetaReto.tituloRevelado

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: UiTokens.spacing6
                        IconoSvg {
                            source: "../assets/icons/lightbulb.svg"
                            size: 14
                            colorIcono: raiz.tema.acento
                            Layout.alignment: Qt.AlignVCenter
                        }
                        AppText {
                            text: "Pistas"
                            color: raiz.tema.textoSec
                            font.pixelSize: UiTokens.fontSizeSm
                            font.weight: Font.DemiBold
                            font.letterSpacing: 0.6
                            Layout.fillWidth: true
                        }
                    }

                    // Hints reveladas (chips informativos).
                    Flow {
                        Layout.fillWidth: true
                        spacing: UiTokens.spacing6
                        visible: Object.keys(tarjetaReto.hintsVisibles).length > 0

                        Repeater {
                            model: [
                                { "clave": "empieza_con",      "etiqueta": "Empieza con" },
                                { "clave": "termina_con",      "etiqueta": "Termina con" },
                                { "clave": "cantidad_palabras","etiqueta": "Palabras" },
                                { "clave": "cantidad_letras",  "etiqueta": "Letras" },
                                { "clave": "alfabeto",         "etiqueta": "Alfabeto" }
                            ]
                            delegate: Rectangle {
                                visible: tarjetaReto.hintsVisibles[modelData.clave] !== undefined
                                         && tarjetaReto.hintsVisibles[modelData.clave] !== ""
                                radius: 13
                                height: 26
                                width: chipHintTxt.implicitWidth + 18
                                color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.08)
                                border.color: Qt.rgba(raiz.tema.acento.r, raiz.tema.acento.g, raiz.tema.acento.b, 0.28)
                                border.width: 1
                                AppText {
                                    id: chipHintTxt
                                    anchors.centerIn: parent
                                    text: modelData.etiqueta + ": " + String(tarjetaReto.hintsVisibles[modelData.clave])
                                    color: raiz.tema.texto
                                    font.pixelSize: UiTokens.fontSizeSm
                                    font.weight: Font.DemiBold
                                }
                            }
                        }
                    }

                    // Botones para desbloquear hints pendientes.
                    Flow {
                        Layout.fillWidth: true
                        spacing: UiTokens.spacing6

                        Repeater {
                            model: [
                                { "clave": "empieza_con",      "etiqueta": "Empieza con…" },
                                { "clave": "termina_con",      "etiqueta": "Termina con…" },
                                { "clave": "cantidad_palabras","etiqueta": "¿Cuántas palabras?" },
                                { "clave": "cantidad_letras",  "etiqueta": "¿Cuántas letras?" },
                                { "clave": "alfabeto",         "etiqueta": "¿Qué alfabeto?" }
                            ]
                            delegate: Rectangle {
                                readonly property bool revelada: tarjetaReto.hintsVisibles[modelData.clave] !== undefined
                                                                 && tarjetaReto.hintsVisibles[modelData.clave] !== ""
                                visible: !revelada
                                radius: 13
                                height: 26
                                width: txtHintBtn.implicitWidth + 18
                                color: hintBtnMa.containsMouse
                                    ? raiz.tema.hover
                                    : raiz.tema.superficieAlt
                                border.color: raiz.tema.borde
                                border.width: 1
                                AppText {
                                    id: txtHintBtn
                                    anchors.centerIn: parent
                                    text: modelData.etiqueta
                                    color: raiz.tema.textoSec
                                    font.pixelSize: UiTokens.fontSizeSm
                                    font.weight: Font.DemiBold
                                }
                                MouseArea {
                                    id: hintBtnMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: tarjetaReto.revelarHint(modelData.clave)
                                }
                            }
                        }
                    }
                }

                // ── Acciones secundarias (siempre disponibles) ─────
                // Orden y agrupamiento por intencion:
                //   Audio neutro: Reproducir completa, Añadir a la cola.
                //   Revelacion/rendicion: Revelar título, ¡Me rindo!
                //     (solo si el titulo aun no se revelo).
                //   Favorita: alternable, persiste fuera del juego.
                Flow {
                    Layout.fillWidth: true
                    Layout.topMargin: UiTokens.spacing6
                    spacing: UiTokens.spacing6
                    visible: tarjetaReto.retoActivo

                    BotonPlano {
                        texto: "Reproducir completa"
                        iconSource: "../assets/icons/play.svg"
                        onClicked: tarjetaReto.reproducirCompleta()
                    }
                    BotonPlano {
                        texto: "Añadir a la cola"
                        iconSource: "../assets/icons/queue-play.svg"
                        onClicked: tarjetaReto.agregarACola()
                    }
                    BotonPlano {
                        // Revelar SIN rendirse: el reto pasa a estado
                        // "revelado" (no "pasado"). Util cuando el usuario
                        // se da por vencido pero solo quiere ver la respuesta
                        // sin penalizarse a si mismo como "saltada".
                        visible: !tarjetaReto.tituloRevelado
                        texto: "Revelar título"
                        iconSource: "../assets/icons/eye.svg"
                        onClicked: tarjetaReto.revelarTitulo()
                    }
                    BotonPlano {
                        // Favorita: usar `!!` (coerce a bool) en vez de
                        // `parseInt(... || 0) > 0` porque Python envia
                        // True/False; parseInt(true) = NaN > 0 = false,
                        // por eso la estrella no se actualizaba antes.
                        readonly property bool esFav: !!tarjetaReto.reto.favorita
                        texto: esFav ? "Quitar de favoritas" : "Añadir a favoritas"
                        iconSource: esFav
                                    ? "../assets/icons/favorite-filled.svg"
                                    : "../assets/icons/favorite.svg"
                        // Favorita activa: tinta de acento (no peligro/rojo).
                        // El rojo solo lo reservamos para "Me rindo".
                        destacar: esFav ? "acento" : "ninguno"
                        onClicked: {
                            var pid = parseInt(tarjetaReto.reto.pista_id || 0)
                            if (pid > 0) tarjetaReto.alternarFavorita(pid)
                        }
                    }
                    BotonPlano {
                        visible: !tarjetaReto.tituloRevelado
                        texto: "¡Me rindo!"
                        iconSource: "../assets/icons/flag.svg"
                        destacar: "peligro"
                        onClicked: tarjetaReto.rendirse()
                    }
                }
            }
        }
    }
}
