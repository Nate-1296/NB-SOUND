// =============================================================================
// VistaEstadoSistema.qml
//
// Pantalla "plug & play" de NB Sound. Muestra el catálogo de dependencias
// detectadas por `infra.dependencias` y permite al usuario instalarlas o
// repararlas sin salir de la app.
//
// Diseño consistente con el resto de Configuración:
//   * Botones reutilizan los componentes locales BotonPrimario / BotonSecundario
//     definidos al final del archivo (idénticos a los de VistaConfiguracion).
//   * Píldoras OK / Faltante usan tema.acentoFuerte / tema.peligro respectivamente,
//     con texto en `tema.textoSobreAcento` / texto blanco para máximo contraste.
//   * Logs de instalación: solo las últimas N líneas (`MAX_LOG_LINEAS`); se
//     limpian automáticamente cuando la dependencia pasa a OK para no dejar
//     ruido visual en pantalla.
//   * Layout responsive: ancho máximo del contenido (`contentMaxWidth`)
//     centrado igual que en VistaConfiguracion, con padding lateral que
//     se ajusta al tamaño de la ventana.
// =============================================================================

import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import "../componentes"

Rectangle {
    id: raiz
    objectName: "vista_estado_sistema"
    property var shell: null
    readonly property var tema: shell ? shell.tema : temaUi
    color: tema.fondo

    readonly property int contentMaxWidth: 1080
    readonly property int horizontalPadding:
        raiz.width >= 1200 ? 44 : (raiz.width >= 860 ? 32 : UiTokens.spacing20)

    // Cuántas líneas de log se conservan visibles por dependencia.
    readonly property int maxLogLineas: 24

    // Mapa { dep_id -> string con últimas N líneas de log }.
    property var consolaPorDep: ({})

    // ── Helpers de presentación ──────────────────────────────────────────────

    function _colorPildora(estado, requerida) {
        if (estado === "ok") return tema.acentoFuerte
        if (estado === "instalando") return tema.acento
        if (requerida) return tema.peligro
        return tema.advertencia
    }

    function _colorTextoPildora(estado) {
        if (estado === "ok") return tema.textoSobreAcento
        if (estado === "instalando") return tema.textoSobreAcento
        return "#ffffff"
    }

    function _etiquetaEstado(estado) {
        switch (estado) {
            case "ok": return "OK"
            case "faltante": return "Faltante"
            case "instalando": return "Instalando…"
            case "error_instalacion": return "Error"
            default: return "Sin verificar"
        }
    }

    function _accionTexto(dep) {
        if (dep.estado === "ok") return "Re-verificar"
        if (dep.tipo === "pip") return "Instalar automáticamente"
        if (dep.tipo === "modelos") return "Descargar modelos"
        if (dep.tipo === "sistema" || dep.tipo === "binario_path") return "Cómo instalar"
        return "Re-verificar"
    }

    function _ejecutarAccion(dep) {
        if (dep.estado === "ok") {
            // Re-verificar es una operación corta; limpiar consola si quedó algo.
            raiz._limpiarConsola(dep.id)
            dependencias.revisarUna(dep.id)
            return
        }
        if (dep.tipo === "pip" || dep.tipo === "modelos") {
            raiz._reiniciarConsola(dep.id)
            dependencias.instalar(dep.id)
            return
        }
        dependencias.abrirInstruccionesSO(dep.id)
    }

    function _reiniciarConsola(depId) {
        const draft = ({})
        for (const k in raiz.consolaPorDep) draft[k] = raiz.consolaPorDep[k]
        draft[depId] = "Preparando…"
        raiz.consolaPorDep = draft
    }

    function _limpiarConsola(depId) {
        if (raiz.consolaPorDep[depId] === undefined) return
        const draft = ({})
        for (const k in raiz.consolaPorDep) if (k !== depId) draft[k] = raiz.consolaPorDep[k]
        raiz.consolaPorDep = draft
    }

    function _bufferLineas(previo, linea) {
        const acumulado = previo ? previo + "\n" + linea : linea
        const lineas = acumulado.split("\n")
        if (lineas.length <= raiz.maxLogLineas) return acumulado
        return lineas.slice(lineas.length - raiz.maxLogLineas).join("\n")
    }

    // ── Conexión a las señales del modelo ────────────────────────────────────

    Connections {
        target: dependencias

        function onProgresoInstalacion(depId, linea) {
            const draft = ({})
            for (const k in raiz.consolaPorDep) draft[k] = raiz.consolaPorDep[k]
            const previo = draft[depId] || ""
            draft[depId] = raiz._bufferLineas(previo, linea)
            raiz.consolaPorDep = draft
        }

        function onInstalacionTerminada(depId, ok, mensaje, detalle) {
            const draft = ({})
            for (const k in raiz.consolaPorDep) draft[k] = raiz.consolaPorDep[k]
            const previo = draft[depId] || ""
            const sello = (ok ? "✓ " : "✗ ") + mensaje
            draft[depId] = raiz._bufferLineas(previo, sello)
            raiz.consolaPorDep = draft
        }

        function onEstadoCambiado() {
            // Cuando una dependencia recién instalada pasa a OK, limpiar su
            // consola para no dejar el recuadro residual en pantalla.
            for (let i = 0; i < dependencias.estado.length; i++) {
                const rep = dependencias.estado[i]
                if (rep.estado === "ok" && raiz.consolaPorDep[rep.id] !== undefined) {
                    raiz._limpiarConsola(rep.id)
                }
            }
        }
    }

    // ── Scroll principal ─────────────────────────────────────────────────────

    ScrollView {
        id: scrollEstado
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical: AppScrollBar {
            parent: scrollEstado
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            z: 20
            tema: raiz.tema
            policy: scrollEstado.contentHeight > scrollEstado.height + 2
                ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
        }

        ColumnLayout {
            id: contenidoExterior
            width: scrollEstado.availableWidth
            spacing: 0

            // Centrador igual que en VistaConfiguracion: ancho máximo
            // limitado por `contentMaxWidth` para legibilidad en monitores
            // grandes.
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: contenido.implicitHeight
                ColumnLayout {
                    id: contenido
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: Math.min(parent.width - raiz.horizontalPadding * 2,
                                    raiz.contentMaxWidth)
                    spacing: UiTokens.spacing16

                    // ─ Encabezado ──────────────────────────────────────
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 96
                        AppText {
                            anchors.left: parent.left
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: UiTokens.spacing12
                            text: "Estado del Sistema"
                            font.pixelSize: 28
                            font.weight: Font.DemiBold
                            color: tema.texto
                        }
                    }

                    // ─ Banner resumen ──────────────────────────────────
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: bannerLayout.implicitHeight + UiTokens.spacing24
                        color: dependencias.faltanRequeridas
                            ? Qt.tint(tema.fondoElevado, Qt.rgba(1, 0.2, 0.3, 0.12))
                            : (dependencias.faltanOpcionales
                               ? Qt.tint(tema.fondoElevado, Qt.rgba(1, 0.7, 0.2, 0.10))
                               : Qt.tint(tema.fondoElevado, Qt.rgba(0.2, 1, 0.5, 0.08)))
                        radius: UiTokens.radiusLg
                        border.color: dependencias.faltanRequeridas
                            ? tema.peligro
                            : (dependencias.faltanOpcionales ? tema.advertencia : tema.acentoFuerte)
                        border.width: 1

                        RowLayout {
                            id: bannerLayout
                            anchors.fill: parent
                            anchors.margins: UiTokens.spacing16
                            spacing: UiTokens.spacing16
                            AppText {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                text: dependencias.faltanRequeridas
                                    ? "Faltan dependencias requeridas. Algunas funciones críticas no estarán disponibles hasta instalarlas."
                                    : (dependencias.faltanOpcionales
                                       ? "Hay dependencias opcionales sin instalar. La app funciona; las funciones extra (Karaoke, Deep, AcoustID) quedan deshabilitadas hasta instalarlas."
                                       : "Todas las dependencias están instaladas. NB Sound está listo para usarse al máximo.")
                                color: tema.texto
                                font.pixelSize: UiTokens.fontSizeLg
                            }
                            BotonSecundario {
                                texto: "Re-verificar todo"
                                width: 200
                                height: 40
                                onClicked: dependencias.revisarTodas()
                            }
                        }
                    }

                    // ─ Aviso Python ────────────────────────────────────
                    Rectangle {
                        Layout.fillWidth: true
                        visible: !dependencias.diagnostico.python_utilizable
                        Layout.preferredHeight: visible ? pythonLayout.implicitHeight + UiTokens.spacing24 : 0
                        color: Qt.tint(tema.fondoElevado, Qt.rgba(1, 0.7, 0.2, 0.10))
                        radius: UiTokens.radiusLg
                        border.color: tema.advertencia
                        border.width: 1

                        ColumnLayout {
                            id: pythonLayout
                            anchors.fill: parent
                            anchors.margins: UiTokens.spacing16
                            spacing: UiTokens.spacing8
                            AppText {
                                text: "Python del sistema"
                                color: tema.texto
                                font.pixelSize: UiTokens.fontSizeXl
                                font.weight: Font.DemiBold
                            }
                            AppText {
                                Layout.fillWidth: true
                                text: {
                                    const d = dependencias.diagnostico
                                    if (!d.python_detectado)
                                        return "No se detectó Python 3.10+ en el sistema. Es necesario para instalar componentes opcionales (PyTorch, Demucs, Essentia)."
                                    const partes = ["Python " + (d.python_version || "?") + " detectado en " + d.python_detectado + ", pero le faltan módulos:"]
                                    if (d.python_falta_pip) partes.push("• pip")
                                    if (d.python_falta_venv) partes.push("• venv / ensurepip")
                                    return partes.join("\n")
                                }
                                color: tema.textoSec
                                wrapMode: Text.WrapAnywhere
                                font.pixelSize: UiTokens.fontSizeBase
                            }
                            AppText {
                                Layout.fillWidth: true
                                visible: dependencias.diagnostico.reparacion_disponible === true
                                text: "Se intentará reparar con: " + (dependencias.diagnostico.reparacion_comando || "")
                                color: tema.textoMuted
                                wrapMode: Text.WrapAnywhere
                                font.pixelSize: UiTokens.fontSizeSm
                                font.family: "monospace"
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: UiTokens.spacing12
                                Item { Layout.fillWidth: true }
                                BotonPrimario {
                                    width: 220
                                    height: 40
                                    visible: dependencias.diagnostico.reparacion_disponible === true
                                    texto: "Reparar automáticamente"
                                    onClicked: dependencias.repararPython()
                                }
                            }
                        }
                    }

                    // ─ Lista de dependencias ───────────────────────────
                    Repeater {
                        model: dependencias.estado
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: filaCol.implicitHeight + UiTokens.spacing24
                            color: tema.fondoElevado
                            radius: UiTokens.radiusLg
                            border.color: tema.borde
                            border.width: 1

                            ColumnLayout {
                                id: filaCol
                                anchors.fill: parent
                                anchors.margins: UiTokens.spacing16
                                spacing: UiTokens.spacing10

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: UiTokens.spacing12
                                    AppText {
                                        text: modelData.nombre
                                        color: tema.texto
                                        font.pixelSize: UiTokens.fontSizeXl
                                        font.weight: Font.DemiBold
                                        Layout.alignment: Qt.AlignVCenter
                                    }
                                    // Tag "requerida" / "opcional"
                                    Rectangle {
                                        Layout.alignment: Qt.AlignVCenter
                                        color: modelData.requerida
                                            ? Qt.rgba(tema.peligro.r, tema.peligro.g, tema.peligro.b, 0.18)
                                            : Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.16)
                                        radius: UiTokens.radiusPill
                                        implicitWidth: txtReq.implicitWidth + UiTokens.spacing16
                                        implicitHeight: txtReq.implicitHeight + UiTokens.spacing6
                                        AppText {
                                            id: txtReq
                                            anchors.centerIn: parent
                                            text: modelData.requerida ? "requerida" : "opcional"
                                            color: modelData.requerida ? tema.peligro : tema.acento
                                            font.pixelSize: UiTokens.fontSizeSm
                                            font.weight: Font.DemiBold
                                        }
                                    }
                                    Item { Layout.fillWidth: true }
                                    // Píldora de estado con colores del tema.
                                    Rectangle {
                                        Layout.alignment: Qt.AlignVCenter
                                        color: raiz._colorPildora(modelData.estado, modelData.requerida)
                                        radius: UiTokens.radiusPill
                                        implicitWidth: txtEstado.implicitWidth + UiTokens.spacing16
                                        implicitHeight: txtEstado.implicitHeight + UiTokens.spacing8
                                        AppText {
                                            id: txtEstado
                                            anchors.centerIn: parent
                                            text: raiz._etiquetaEstado(modelData.estado)
                                            color: raiz._colorTextoPildora(modelData.estado)
                                            font.pixelSize: UiTokens.fontSizeSm
                                            font.weight: Font.DemiBold
                                        }
                                    }
                                }

                                AppText {
                                    Layout.fillWidth: true
                                    text: modelData.descripcion
                                    color: tema.textoSec
                                    font.pixelSize: UiTokens.fontSizeBase
                                    wrapMode: Text.WordWrap
                                }

                                AppText {
                                    Layout.fillWidth: true
                                    visible: modelData.version && modelData.version.length > 0
                                    text: "Versión: " + modelData.version
                                    color: tema.textoMuted
                                    font.pixelSize: UiTokens.fontSizeSm
                                    wrapMode: Text.WordWrap
                                }

                                AppText {
                                    Layout.fillWidth: true
                                    visible: modelData.funciones_que_habilita
                                             && modelData.funciones_que_habilita.length > 0
                                    text: "Habilita: " + (modelData.funciones_que_habilita || []).join(", ")
                                    color: tema.textoMuted
                                    font.pixelSize: UiTokens.fontSizeSm
                                    wrapMode: Text.WordWrap
                                }

                                AppText {
                                    Layout.fillWidth: true
                                    visible: modelData.estado !== "ok"
                                             && (modelData.tipo === "sistema" || modelData.tipo === "binario_path")
                                             && modelData.instruccion_manual
                                             && modelData.instruccion_manual.length > 0
                                    text: modelData.instruccion_manual
                                    color: tema.textoMuted
                                    font.pixelSize: UiTokens.fontSizeSm
                                    font.family: "monospace"
                                    wrapMode: Text.WrapAnywhere
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: UiTokens.spacing12
                                    Item { Layout.fillWidth: true }
                                    BotonSecundario {
                                        visible: modelData.estado !== "ok"
                                        texto: "Re-verificar"
                                        width: 160
                                        height: 38
                                        onClicked: {
                                            raiz._limpiarConsola(modelData.id)
                                            dependencias.revisarUna(modelData.id)
                                        }
                                    }
                                    BotonPrimario {
                                        texto: raiz._accionTexto(modelData)
                                        width: 260
                                        height: 40
                                        onClicked: raiz._ejecutarAccion(modelData)
                                    }
                                }

                                // Consola: solo aparece durante / después de una
                                // instalación, y se limpia automáticamente cuando
                                // la dependencia pasa a OK.
                                Rectangle {
                                    Layout.fillWidth: true
                                    visible: raiz.consolaPorDep[modelData.id] !== undefined
                                             && (raiz.consolaPorDep[modelData.id] || "").length > 0
                                             && modelData.estado !== "ok"
                                    Layout.preferredHeight: visible
                                        ? consolaTxt.implicitHeight + UiTokens.spacing16 : 0
                                    color: Qt.tint(tema.fondo, Qt.rgba(0, 0, 0, 0.20))
                                    radius: UiTokens.radiusSm
                                    border.color: tema.borde
                                    border.width: 1
                                    AppText {
                                        id: consolaTxt
                                        anchors.fill: parent
                                        anchors.margins: UiTokens.spacing8
                                        text: raiz.consolaPorDep[modelData.id] || ""
                                        color: tema.textoSec
                                        font.family: "monospace"
                                        font.pixelSize: UiTokens.fontSizeSm
                                        wrapMode: Text.WrapAnywhere
                                    }
                                }
                            }
                        }
                    }

                    // ─ Diagnóstico al pie ──────────────────────────────
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.bottomMargin: UiTokens.spacing24
                        Layout.preferredHeight: diagColumna.implicitHeight + UiTokens.spacing24
                        color: tema.fondoElevado
                        radius: UiTokens.radiusLg
                        border.color: tema.borde
                        border.width: 1
                        ColumnLayout {
                            id: diagColumna
                            anchors.fill: parent
                            anchors.margins: UiTokens.spacing16
                            spacing: UiTokens.spacing6
                            AppText {
                                text: "Diagnóstico del entorno"
                                color: tema.texto
                                font.pixelSize: UiTokens.fontSizeLg
                                font.weight: Font.DemiBold
                            }
                            AppText {
                                Layout.fillWidth: true
                                text: dependencias.diagnostico.python_utilizable
                                    ? "Python del sistema: " + (dependencias.diagnostico.python_detectado || "")
                                      + " (versión " + (dependencias.diagnostico.python_version || "?") + ")"
                                    : "Python del sistema: no utilizable (revisa el aviso superior)"
                                color: tema.textoSec
                                wrapMode: Text.WrapAnywhere
                                font.pixelSize: UiTokens.fontSizeSm
                            }
                            AppText {
                                Layout.fillWidth: true
                                text: "Plataforma: " + (dependencias.diagnostico.plataforma || "?") +
                                      (dependencias.diagnostico.frozen ? " (bundle empaquetado)" : " (desarrollo)")
                                color: tema.textoSec
                                wrapMode: Text.WrapAnywhere
                                font.pixelSize: UiTokens.fontSizeSm
                            }
                            AppText {
                                Layout.fillWidth: true
                                visible: (dependencias.diagnostico.site_packages_runtime || "").length > 0
                                text: "Site-packages runtime: " + (dependencias.diagnostico.site_packages_runtime || "")
                                color: tema.textoMuted
                                wrapMode: Text.WrapAnywhere
                                font.pixelSize: UiTokens.fontSizeSm
                            }
                        }
                    }
                }
            }
        }
    }

    // ── Componentes locales: misma definición que en VistaConfiguracion ──
    // Se duplican aquí adrede para no tener que importar VistaConfiguracion.
    // El estilo debe quedar EXACTAMENTE igual; si cambia uno cambian ambos.

    component BotonPrimario: Rectangle {
        id: botonPrimarioRoot
        property string texto: ""
        property bool deshabilitado: false
        signal clicked()
        width: 220; height: 44
        radius: 22
        color: deshabilitado ? tema.superficie : (bpMa.containsMouse ? tema.acentoFuerte : tema.acento)
        border.color: deshabilitado ? tema.borde : "transparent"
        border.width: deshabilitado ? 1 : 0
        opacity: deshabilitado ? 0.45 : 1.0

        Behavior on color { ColorAnimation { duration: 180 } }
        Behavior on opacity { NumberAnimation { duration: 200 } }
        Behavior on scale { NumberAnimation { duration: 120 } }

        AppText {
            anchors.centerIn: parent
            text: texto
            color: deshabilitado ? tema.textoMuted : tema.fondo
            font.bold: true; font.pixelSize: UiTokens.fontSizeBase
            Behavior on color { ColorAnimation { duration: 180 } }
        }

        MouseArea {
            id: bpMa; anchors.fill: parent
            hoverEnabled: true; enabled: !botonPrimarioRoot.deshabilitado
            cursorShape: botonPrimarioRoot.deshabilitado ? Qt.ArrowCursor : Qt.PointingHandCursor
            onClicked: botonPrimarioRoot.clicked()
            SequentialAnimation {
                id: bpPressAnim
                NumberAnimation { target: botonPrimarioRoot; property: "scale"; to: 0.96; duration: 80 }
                NumberAnimation { target: botonPrimarioRoot; property: "scale"; to: 1.0; duration: 100 }
            }
            onPressed: { if (!botonPrimarioRoot.deshabilitado) bpPressAnim.start() }
        }
    }

    component BotonSecundario: Rectangle {
        id: botonSecundarioRoot
        property string texto: ""
        signal clicked()
        width: 220; height: 44
        radius: 22
        color: bsMa.containsMouse ? tema.hover : tema.superficieAlt
        border.color: bsMa.containsMouse
            ? Qt.rgba(tema.acento.r, tema.acento.g, tema.acento.b, 0.35) : tema.borde
        border.width: 1

        Behavior on color { ColorAnimation { duration: 180 } }
        Behavior on border.color { ColorAnimation { duration: 150 } }
        Behavior on scale { NumberAnimation { duration: 120 } }

        AppText {
            anchors.centerIn: parent; text: texto
            color: tema.texto; font.bold: true; font.pixelSize: UiTokens.fontSizeBase
        }
        MouseArea {
            id: bsMa; anchors.fill: parent
            hoverEnabled: true; cursorShape: Qt.PointingHandCursor
            onClicked: botonSecundarioRoot.clicked()
            SequentialAnimation {
                id: bsPressAnim
                NumberAnimation { target: botonSecundarioRoot; property: "scale"; to: 0.96; duration: 80 }
                NumberAnimation { target: botonSecundarioRoot; property: "scale"; to: 1.0; duration: 100 }
            }
            onPressed: bsPressAnim.start()
        }
    }
}
