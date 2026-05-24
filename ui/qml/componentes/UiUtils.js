.pragma library

function toMediaSource(pathValue) {
    if (!pathValue)
        return ""

    var source = String(pathValue).trim()
    if (source === "")
        return ""

    if (source.indexOf("file://") === 0 || source.indexOf("qrc:/") === 0 || source.indexOf("http://") === 0 || source.indexOf("https://") === 0)
        return source

    source = source.replace(/\\/g, "/")

    if (source.match(/^[A-Za-z]:\//))
        return encodeURI("file:///" + source)

    if (source.charAt(0) === "/")
        return encodeURI("file://" + source)

    return source
}

function toFileUrl(pathValue) {
    if (!pathValue)
        return ""
    return toMediaSource(pathValue)
}

// Constantes neutras para lógica de contraste contra colores dinámicos
// (cuando el color base NO viene del tema, sino de cover/mood/preview).
// Centralizadas aquí para evitar hex literales dispersos.
var NEGRO_FIJO = "#000000"
var BLANCO_FIJO = "#ffffff"

// Devuelve negro o blanco según luminancia del color de referencia.
// Útil cuando el color de fondo se calcula dinámicamente desde una
// portada, mood o preview y no es uno de los tokens del tema.
function contrasteSobre(colorRef) {
    if (!colorRef) return BLANCO_FIJO
    var r = (typeof colorRef.r === "number") ? colorRef.r : 0
    var g = (typeof colorRef.g === "number") ? colorRef.g : 0
    var b = (typeof colorRef.b === "number") ? colorRef.b : 0
    var lum = 0.299 * r + 0.587 * g + 0.114 * b
    return lum > 0.5 ? NEGRO_FIJO : BLANCO_FIJO
}

// Variante que ya recibe la luminancia precalculada.
function contrastePorLuminancia(lum) {
    return lum > 0.5 ? NEGRO_FIJO : BLANCO_FIJO
}

// Velo blanco semitransparente sobre fondos dinámicos oscuros
// (mini reproductor, reproducción expandida, lyrics fullscreen).
// Centraliza el patrón Qt.rgba(1, 1, 1, alpha) que NO depende del
// tema porque el fondo está intencionalmente forzado oscuro.
function veloClaro(alpha) {
    return Qt.rgba(1, 1, 1, alpha)
}

// Velo negro semitransparente para sombras / oscurecimientos
// sobre fondos claros (carátulas, overlays hover).
function veloOscuro(alpha) {
    return Qt.rgba(0, 0, 0, alpha)
}