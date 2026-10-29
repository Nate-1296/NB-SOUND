import QtQuick
import QtQuick.Layouts

AppCard {
    id: root
    property var tema: temaUi
    property var rev: null
    property var modelRef: null
    property int itemIndex: -1
    property string sectionLabel: ""
    padding: UiTokens.spacing16

    function rowData() {
        if (!modelRef || itemIndex < 0) return ({})
        return modelRef.obtener(itemIndex)
    }

    function parseManifesto() {
        if (!row.manifiesto_json || row.manifiesto_json === "") return ({})
        try {
            return JSON.parse(row.manifiesto_json)
        } catch (e) {
            return ({})
        }
    }

    function candidatoSugerido() {
        var m = parseManifesto()
        if (m.candidato_sugerido) return m.candidato_sugerido
        if (m.best_candidate) return m.best_candidate
        if (m.candidato) return m.candidato
        return ({})
    }

    property var row: rowData()
    property string causa: row.causa || "sin_detalle"
    property var candidato: candidatoSugerido()

    function causaTexto(causaId) {
        var mapa = {
            "puntaje_bajo": "Confianza insuficiente en la identificación",
            "puntaje_intermedio": "Confianza media: revisión recomendada",
            "candidatos_ambiguos": "Múltiples candidatos posibles",
            "sin_candidatos": "No hubo candidato en MusicBrainz",
            "metadata_insuficiente": "Metadatos insuficientes",
            "archivo_corrupto": "Archivo dañado o ilegible",
            "duracion_invalida": "Duración inválida",
            "bitrate_insuficiente": "Bitrate bajo",
            "archivo_muy_pequeno": "Archivo demasiado pequeño",
            "escritura_fallida": "Falló la escritura de tags",
            "ia_revision_manual": "La IA no desempató de forma confiable",
            "fuentes_discrepantes": "Fuentes de identificación inconsistentes",
            "release_type_dudoso": "Tipo de release dudoso"
        }
        return mapa[causaId] || causaId
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: UiTokens.spacing8
        AppText {
            text: row.nombre_archivo || "Archivo"
            color: tema.texto
            font.bold: true
            font.pixelSize: 15
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            elide: Text.ElideMiddle
            maximumLineCount: 1
        }
        StatusBadge {
            tema: root.tema
            text: sectionLabel
            tone: sectionLabel === "Cuarentena" ? "danger" : "warning"
            maxTextWidth: 96
            compact: true
        }
    }

    AppText { text: causaTexto(causa); color: tema.textoSec; font.pixelSize: UiTokens.fontSizeMd; Layout.fillWidth: true; wrapMode: Text.Wrap; lineHeight: 1.15 }

    GridLayout {
        Layout.fillWidth: true
        columns: root.width >= 460 ? 2 : 1
        rowSpacing: 8
        columnSpacing: 10
        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            AppText { text: "Local"; color: tema.textoMuted; font.pixelSize: UiTokens.fontSizeXs }
            AppText { text: row.nombre_archivo || "-"; color: tema.texto; font.pixelSize: UiTokens.fontSizeMd; elide: Text.ElideRight; Layout.fillWidth: true }
        }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            AppText { text: "Sugerido"; color: tema.textoMuted; font.pixelSize: UiTokens.fontSizeXs }
            AppText {
                text: (candidato.titulo || candidato.title || "Sin candidato") +
                      ((candidato.artista || candidato.artist) ? (" · " + (candidato.artista || candidato.artist)) : "")
                color: tema.texto
                font.pixelSize: UiTokens.fontSizeMd
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
        }
    }

    AppText { text: row.ruta_archivo || ""; color: tema.textoMuted; font.pixelSize: UiTokens.fontSizeSm; Layout.fillWidth: true; elide: Text.ElideLeft }

    Flow {
        Layout.fillWidth: true
        spacing: UiTokens.spacing6

        ActionBtn {
            texto: "Marcar visto"
            tono: "success"
            onClicked: {
                if (!root.rev || row.id === undefined) return
                root.rev.marcar_visto(row.id)
            }
        }
        ActionBtn {
            texto: "Abrir ruta"
            tono: "info"
            onClicked: {
                if (!root.rev || (row.ruta_archivo || "") === "") return
                root.rev.abrir_archivo(row.ruta_archivo)
            }
        }
        ActionBtn {
            texto: "Abrir carpeta"
            tono: "neutral"
            onClicked: {
                if (!root.rev || (row.ruta_archivo || "") === "") return
                root.rev.abrir_directorio(row.ruta_archivo)
            }
        }
    }

    component ActionBtn: Rectangle {
        id: btn
        property string texto: ""
        property string tono: "neutral"
        signal clicked()

        function toneColor() {
            if (tono === "success") return tema.exito
            if (tono === "danger") return tema.peligro
            if (tono === "info") return tema.acento
            return tema.textoMuted
        }

        implicitWidth: Math.min(Math.max(88, label.implicitWidth + 20), 132)
        implicitHeight: 30
        width: implicitWidth
        height: implicitHeight
        radius: 15
        clip: true
        color: Qt.rgba(toneColor().r, toneColor().g, toneColor().b, 0.15)
        border.color: toneColor()
        AppText {
            id: label
            anchors.centerIn: parent
            width: Math.max(0, parent.width - 16)
            text: btn.texto
            color: toneColor()
            font.pixelSize: UiTokens.fontSizeSm
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }
        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: btn.clicked() }
    }
}
