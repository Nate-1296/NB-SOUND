import QtQuick
import QtQuick.Dialogs

// Loader solo puede cargar Items (no QtObject puro).
// Este Item de tamaño cero envuelve el FileDialog para poder cargarse dinámicamente.
Item {
    id: root
    width: 0
    height: 0
    visible: false

    property string asig_titulo: ""

    signal seleccionada(string ruta)
    signal cancelado()

    function open() { _dlg.open() }

    FileDialog {
        id: _dlg
        title: "Seleccionar instrumental — " + root.asig_titulo
        nameFilters: [
            "Audio (*.mp3 *.flac *.wav *.ogg *.m4a *.aac *.opus *.wma)",
            "Todos los archivos (*)"
        ]
        onAccepted: {
            var ruta = selectedFile.toString().replace(/^file:\/\//, "")
            root.seleccionada(ruta)
        }
        onRejected: root.cancelado()
    }
}
