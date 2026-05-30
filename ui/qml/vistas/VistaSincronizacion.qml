// =============================================================================
// VistaSincronizacion.qml
//
// Vista del ecosistema móvil: enciende/apaga el servidor local, muestra el QR
// de emparejamiento, los dispositivos vinculados y el estado de conexión.
//
// Diseño consistente con VistaEstadoSistema / VistaConfiguracion:
//   * Reutiliza los botones locales BotonPrimario / BotonSecundario (idéntica
//     definición, mismos acentos del tema).
//   * Tarjetas sobre tema.fondoElevado con borde tema.borde y radius radiusLg.
//   * Centrado por contentMaxWidth con padding lateral responsive.
//   * Píldoras de estado con tema.acentoFuerte / tema.peligro / tema.advertencia.
//   * Degradación controlada: si faltan dependencias (aiohttp/qrcode/zeroconf)
//     muestra un banner que enlaza a "Estado del Sistema" para instalarlas.
// =============================================================================

import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtQuick.Dialogs
import "../componentes"

Rectangle {
    id: raiz
    objectName: "vista_sincronizacion"
    property var shell: null
    readonly property var tema: shell ? shell.tema : temaUi
    color: tema.fondo

    readonly property int contentMaxWidth: 1080
    readonly property int horizontalPadding:
        raiz.width >= 1200 ? 44 : (raiz.width >= 860 ? 32 : UiTokens.spacing20)

    function _plataformaEtiqueta(p) {
        switch (String(p || "").toLowerCase()) {
            case "android": return "Android"
            case "ios": return "iPhone"
            case "ipados": return "iPad"
            case "tablet": return "Tablet"
            default: return "Dispositivo"
        }
    }

    function _ultimaConexion(valor) {
        if (!valor || String(valor).length === 0)
            return "Nunca conectado"
        return "Última conexión: " + String(valor).replace("T", " ").substring(0, 19)
    }

    ScrollView {
        id: scrollSync
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical: AppScrollBar {
            parent: scrollSync
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            z: 20
            tema: raiz.tema
            policy: scrollSync.contentHeight > scrollSync.height + 2
                ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
        }

        ColumnLayout {
            width: scrollSync.availableWidth
            spacing: 0

            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: contenido.implicitHeight
                ColumnLayout {
                    id: contenido
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: Math.min(parent.width - raiz.horizontalPadding * 2, raiz.contentMaxWidth)
                    spacing: UiTokens.spacing16

                    // ─ Encabezado ──────────────────────────────────────
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 96
                        ColumnLayout {
                            anchors.left: parent.left
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: UiTokens.spacing12
                            spacing: UiTokens.spacing4
                            AppText {
                                text: "Sincronización"
                                font.pixelSize: 28
                                font.weight: Font.DemiBold
                                color: tema.texto
                            }
                            AppText {
                                text: "Conecta tu teléfono o tablet por WiFi para sincronizar tu música y controlar la reproducción."
                                font.pixelSize: UiTokens.fontSizeBase
                                color: tema.textoSec
                            }
                        }
                    }

                    // ─ Banner: faltan dependencias ─────────────────────
                    Rectangle {
                        Layout.fillWidth: true
                        visible: !sincronizacion.dependenciasDisponibles
                        Layout.preferredHeight: visible ? depLayout.implicitHeight + UiTokens.spacing24 : 0
                        color: Qt.tint(tema.fondoElevado, Qt.rgba(1, 0.7, 0.2, 0.10))
                        radius: UiTokens.radiusLg
                        border.color: tema.advertencia
                        border.width: 1
                        RowLayout {
                            id: depLayout
                            anchors.fill: parent
                            anchors.margins: UiTokens.spacing16
                            spacing: UiTokens.spacing16
                            AppText {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                text: "Para activar la sincronización móvil instala los componentes de red "
                                      + "(" + (sincronizacion.dependenciasFaltantes || []).join(", ") + ")."
                                color: tema.texto
                                font.pixelSize: UiTokens.fontSizeLg
                            }
                            BotonSecundario {
                                texto: "Estado del Sistema"
                                width: 200
                                height: 40
                                onClicked: if (shell) shell.vista_activa = "estado_sistema"
                            }
                        }
                    }

                    // ─ Estado del servidor ─────────────────────────────
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: servidorLayout.implicitHeight + UiTokens.spacing24
                        color: tema.fondoElevado
                        radius: UiTokens.radiusLg
                        border.color: sincronizacion.activo ? tema.acentoFuerte : tema.borde
                        border.width: 1

                        ColumnLayout {
                            id: servidorLayout
                            anchors.fill: parent
                            anchors.margins: UiTokens.spacing16
                            spacing: UiTokens.spacing12

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: UiTokens.spacing12
                                AppText {
                                    text: "Servidor local"
                                    color: tema.texto
                                    font.pixelSize: UiTokens.fontSizeXl
                                    font.weight: Font.DemiBold
                                    Layout.alignment: Qt.AlignVCenter
                                }
                                Item { Layout.fillWidth: true }
                                // Píldora de estado.
                                Rectangle {
                                    Layout.alignment: Qt.AlignVCenter
                                    color: sincronizacion.activo ? tema.acentoFuerte
                                         : (sincronizacion.ocupado ? tema.advertencia : tema.superficieAlt)
                                    radius: UiTokens.radiusPill
                                    implicitWidth: txtEstadoSrv.implicitWidth + UiTokens.spacing16
                                    implicitHeight: txtEstadoSrv.implicitHeight + UiTokens.spacing8
                                    border.color: sincronizacion.activo ? "transparent" : tema.borde
                                    border.width: sincronizacion.activo ? 0 : 1
                                    AppText {
                                        id: txtEstadoSrv
                                        anchors.centerIn: parent
                                        text: sincronizacion.ocupado ? "Procesando…"
                                            : (sincronizacion.activo ? "Activo" : "Apagado")
                                        color: sincronizacion.activo ? tema.textoSobreAcento : tema.textoSec
                                        font.pixelSize: UiTokens.fontSizeSm
                                        font.weight: Font.DemiBold
                                    }
                                }
                            }

                            AppText {
                                Layout.fillWidth: true
                                visible: sincronizacion.activo
                                text: "Dirección en la red local: " + sincronizacion.direccion
                                color: tema.textoSec
                                font.pixelSize: UiTokens.fontSizeBase
                                font.family: "monospace"
                            }
                            AppText {
                                Layout.fillWidth: true
                                visible: sincronizacion.activo
                                text: sincronizacion.clientesConectados > 0
                                    ? (sincronizacion.clientesConectados + " dispositivo(s) conectado(s) ahora")
                                    : "Sin dispositivos conectados en este momento."
                                color: tema.textoMuted
                                font.pixelSize: UiTokens.fontSizeSm
                            }
                            AppText {
                                Layout.fillWidth: true
                                visible: sincronizacion.mensaje.length > 0
                                text: sincronizacion.mensaje
                                color: tema.textoMuted
                                font.pixelSize: UiTokens.fontSizeSm
                                wrapMode: Text.WordWrap
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: UiTokens.spacing12
                                Item { Layout.fillWidth: true }
                                BotonSecundario {
                                    visible: sincronizacion.activo
                                    texto: "Regenerar QR"
                                    width: 170
                                    height: 40
                                    onClicked: sincronizacion.regenerarQr()
                                }
                                BotonPrimario {
                                    texto: sincronizacion.activo ? "Apagar servidor" : "Encender servidor"
                                    deshabilitado: sincronizacion.ocupado || !sincronizacion.dependenciasDisponibles
                                    width: 220
                                    height: 44
                                    onClicked: sincronizacion.alternar()
                                }
                            }
                        }
                    }

                    // ─ QR de emparejamiento ────────────────────────────
                    Rectangle {
                        Layout.fillWidth: true
                        visible: sincronizacion.activo
                        Layout.preferredHeight: visible ? qrLayout.implicitHeight + UiTokens.spacing24 : 0
                        color: tema.fondoElevado
                        radius: UiTokens.radiusLg
                        border.color: tema.borde
                        border.width: 1

                        ColumnLayout {
                            id: qrLayout
                            anchors.fill: parent
                            anchors.margins: UiTokens.spacing16
                            spacing: UiTokens.spacing12

                            AppText {
                                text: "Emparejar un dispositivo"
                                color: tema.texto
                                font.pixelSize: UiTokens.fontSizeXl
                                font.weight: Font.DemiBold
                            }
                            AppText {
                                Layout.fillWidth: true
                                text: "Abre NB Sound en tu teléfono y escanea este código para vincularlo. "
                                      + "El código es de un solo uso y caduca por seguridad."
                                color: tema.textoSec
                                font.pixelSize: UiTokens.fontSizeBase
                                wrapMode: Text.WordWrap
                            }

                            // Lienzo blanco para máximo contraste de lectura del QR.
                            Rectangle {
                                Layout.alignment: Qt.AlignHCenter
                                Layout.preferredWidth: 268
                                Layout.preferredHeight: 268
                                radius: UiTokens.radiusMd
                                color: "#ffffff"
                                border.color: tema.borde
                                border.width: 1

                                Image {
                                    anchors.centerIn: parent
                                    width: 240
                                    height: 240
                                    fillMode: Image.PreserveAspectFit
                                    smooth: false
                                    cache: false
                                    source: sincronizacion.qrImagen
                                    visible: sincronizacion.qrImagen.length > 0
                                }
                                AppText {
                                    anchors.centerIn: parent
                                    visible: sincronizacion.qrImagen.length === 0
                                    text: "Generando código…"
                                    color: "#555555"
                                    font.pixelSize: UiTokens.fontSizeBase
                                }
                            }
                        }
                    }

                    // ─ Dispositivos emparejados ────────────────────────
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: dispLayout.implicitHeight + UiTokens.spacing24
                        color: tema.fondoElevado
                        radius: UiTokens.radiusLg
                        border.color: tema.borde
                        border.width: 1

                        ColumnLayout {
                            id: dispLayout
                            anchors.fill: parent
                            anchors.margins: UiTokens.spacing16
                            spacing: UiTokens.spacing10

                            RowLayout {
                                Layout.fillWidth: true
                                AppText {
                                    text: "Dispositivos vinculados"
                                    color: tema.texto
                                    font.pixelSize: UiTokens.fontSizeXl
                                    font.weight: Font.DemiBold
                                }
                                Item { Layout.fillWidth: true }
                                BotonSecundario {
                                    texto: "Actualizar"
                                    width: 130
                                    height: 36
                                    onClicked: sincronizacion.recargarDispositivos()
                                }
                            }

                            AppText {
                                Layout.fillWidth: true
                                visible: (sincronizacion.dispositivos || []).length === 0
                                text: "Aún no has vinculado ningún dispositivo. Enciende el servidor y escanea el QR desde tu teléfono."
                                color: tema.textoMuted
                                font.pixelSize: UiTokens.fontSizeBase
                                wrapMode: Text.WordWrap
                            }

                            Repeater {
                                model: sincronizacion.dispositivos
                                delegate: Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: filaDisp.implicitHeight + UiTokens.spacing16
                                    color: Qt.tint(tema.fondo, Qt.rgba(0, 0, 0, 0.12))
                                    radius: UiTokens.radiusMd
                                    border.color: tema.borde
                                    border.width: 1

                                    RowLayout {
                                        id: filaDisp
                                        anchors.fill: parent
                                        anchors.margins: UiTokens.spacing12
                                        spacing: UiTokens.spacing12

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: UiTokens.spacing2
                                            AppText {
                                                text: modelData.nombre || "Dispositivo"
                                                color: tema.texto
                                                font.pixelSize: UiTokens.fontSizeLg
                                                font.weight: Font.DemiBold
                                            }
                                            AppText {
                                                text: raiz._plataformaEtiqueta(modelData.plataforma)
                                                      + " · " + raiz._ultimaConexion(modelData.ultima_conexion)
                                                color: tema.textoMuted
                                                font.pixelSize: UiTokens.fontSizeSm
                                            }
                                        }
                                        BotonSecundario {
                                            texto: "Revocar"
                                            width: 120
                                            height: 36
                                            onClicked: sincronizacion.revocar(modelData.id)
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // ─ Copia de seguridad ──────────────────────────────
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: backupLayout.implicitHeight + UiTokens.spacing24
                        color: tema.fondoElevado
                        radius: UiTokens.radiusLg
                        border.color: tema.borde
                        border.width: 1

                        ColumnLayout {
                            id: backupLayout
                            anchors.fill: parent
                            anchors.margins: UiTokens.spacing16
                            spacing: UiTokens.spacing10

                            AppText {
                                text: "Copia de seguridad"
                                color: tema.texto
                                font.pixelSize: UiTokens.fontSizeXl
                                font.weight: Font.DemiBold
                            }
                            AppText {
                                Layout.fillWidth: true
                                text: "Respalda tu catálogo, playlists, historial y portadas en un archivo "
                                      + ".nbsound-backup. La restauración reemplaza la biblioteca actual de "
                                      + "forma segura (valida integridad antes de aplicar)."
                                color: tema.textoSec
                                font.pixelSize: UiTokens.fontSizeBase
                                wrapMode: Text.WordWrap
                            }
                            AppText {
                                Layout.fillWidth: true
                                visible: backupMensaje.length > 0
                                text: backupMensaje
                                color: tema.textoMuted
                                font.pixelSize: UiTokens.fontSizeSm
                                wrapMode: Text.WordWrap
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: UiTokens.spacing12
                                Item { Layout.fillWidth: true }
                                BotonSecundario {
                                    texto: "Restaurar…"
                                    width: 170
                                    height: 40
                                    onClicked: dialogoRestaurar.open()
                                }
                                BotonPrimario {
                                    texto: "Crear copia…"
                                    width: 190
                                    height: 44
                                    onClicked: dialogoCarpetaBackup.open()
                                }
                            }
                        }
                    }

                    Item { Layout.fillWidth: true; Layout.preferredHeight: UiTokens.spacing24 }
                }
            }
        }
    }

    property string backupMensaje: ""

    Connections {
        target: sincronizacion
        function onBackupTerminado(ok, mensaje, ruta) {
            raiz.backupMensaje = mensaje
            if (shell)
                shell.mostrar_toast_global(mensaje, ok ? "info" : "danger")
            if (ok)
                sincronizacion.recargarDispositivos()
        }
        function onDispositivoEmparejado(dispositivo) {
            if (shell)
                shell.mostrar_toast_global("Dispositivo vinculado: " + (dispositivo.nombre || "móvil"), "info")
        }
    }

    FolderDialog {
        id: dialogoCarpetaBackup
        title: "Elige dónde guardar la copia de seguridad"
        onAccepted: {
            raiz.backupMensaje = "Creando copia de seguridad…"
            sincronizacion.crearBackup(selectedFolder.toString())
        }
    }

    FileDialog {
        id: dialogoRestaurar
        title: "Selecciona un archivo .nbsound-backup"
        nameFilters: ["Copia NB Sound (*.nbsound-backup)", "Todos los archivos (*)"]
        onAccepted: {
            raiz.backupMensaje = "Restaurando copia de seguridad…"
            sincronizacion.restaurarBackup(selectedFile.toString())
        }
    }

    // ── Componentes locales: misma definición que en VistaEstadoSistema ──

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
