import QtQuick
import QtQuick.Controls

Text {
    id: root

    // Aplicar la familia de fuente global desde ApplicationWindow.font.family
    // Para ventanas no-ApplicationWindow, usar configuracion.valores.ui_font_family
    font.family: {
        // Intentar obtener desde ApplicationWindow.window (ventanas principales)
        if (Window.window && Window.window.hasOwnProperty("font") && Window.window.font.hasOwnProperty("family") && Window.window.font.family) {
            return Window.window.font.family
        }

        // Fallback para componentes en ventanas no-ApplicationWindow (ej. mini reproductor)
        if (typeof configuracion !== "undefined" && configuracion && configuracion.valores) {
            return configuracion.valores.ui_font_family || "Inter"
        }

        return "Inter"
    }
}