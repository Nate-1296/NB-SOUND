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

// Normaliza una marca de tiempo almacenada en UTC (cualquiera de los formatos
// canónicos de NB Sound) a una cadena ISO-8601 que `new Date()` interpreta
// como UTC. Devuelve "" si la entrada está vacía o no es reparable.
// Formatos contemplados:
//   "2026-06-03T20:43:18Z"             ISO UTC con sufijo Z
//   "2026-06-04T19:19:25.820341+00:00" ISO con offset explícito
//   "2026-06-03 21:27:44"              UTC naive (datetime('now') de SQLite)
//   "2026-06-04T18:01:739743Z"         legacy: microsegundos sin segundos
function normalizarMarcaUtc(valor) {
    if (valor === null || valor === undefined)
        return ""
    var s = String(valor).trim()
    if (s === "")
        return ""
    // Separador fecha/hora canónico.
    s = s.replace(" ", "T")
    // Repara el formato legacy "T<hh>:<mm>:<microsegundos>" (sin segundos).
    s = s.replace(/T(\d{2}):(\d{2}):(\d{6})(Z|[+-]\d{2}:?\d{2})?$/,
                  function(m, hh, mm, us, tz) { return "T" + hh + ":" + mm + ":00" + (tz ? tz : "Z") })
    // Sin indicador de zona => los datos canónicos están en UTC: añadimos Z.
    if (!/[Zz]$/.test(s) && !/[+-]\d{2}:?\d{2}$/.test(s))
        s += "Z"
    return s
}

// Marca de tiempo UTC almacenada -> texto local legible "DD/MM/AAAA HH:MM".
// `placeholder` se devuelve cuando no hay valor.
//
// El formateo es MANUAL (no usa `Locale`/`toLocaleString`): en un archivo JS con
// `.pragma library` el enum `Locale` no está en el scope y `Locale.ShortFormat`
// lanza «ReferenceError: Locale is not defined», lo que dejaba el campo vacío.
// `Date.getHours()`/`getDate()`/… ya devuelven la hora LOCAL del sistema, así que
// la conversión UTC->local se mantiene correcta.
function formatearFechaLocal(valor, placeholder) {
    var ph = (placeholder === undefined) ? "—" : placeholder
    var norm = normalizarMarcaUtc(valor)
    if (norm === "")
        return ph
    var d = new Date(norm)
    if (isNaN(d.getTime()))
        return String(valor).replace("T", " ").replace("Z", "")
    function _p2(n) { return (n < 10 ? "0" : "") + n }
    return _p2(d.getDate()) + "/" + _p2(d.getMonth() + 1) + "/" + d.getFullYear()
         + " " + _p2(d.getHours()) + ":" + _p2(d.getMinutes())
}