//! JSON con el formato exacto de la V1.
//!
//! La V1 respondía con `json.dumps` de Python (lo que hace `aiohttp.json_response`):
//! `", "` y `": "` como separadores, todo lo que no es ASCII imprimible escapado
//! como `\uXXXX` y los reales como los escribe `repr`. El teléfono parsea el JSON y
//! no notaría la diferencia, pero las respuestas doradas guardan también el
//! `content-length`, y ADR-005 pide el contrato byte a byte: con `serde_json` tal
//! cual, cada respuesta mediría distinto.

use std::io::{self, Write};

use serde::Serialize;
use serde_json::ser::{CharEscape, Formatter, Serializer};

struct ComoPython;

impl Formatter for ComoPython {
    fn begin_array_value<W: ?Sized + Write>(&mut self, w: &mut W, first: bool) -> io::Result<()> {
        if first {
            Ok(())
        } else {
            w.write_all(b", ")
        }
    }

    fn begin_object_key<W: ?Sized + Write>(&mut self, w: &mut W, first: bool) -> io::Result<()> {
        if first {
            Ok(())
        } else {
            w.write_all(b", ")
        }
    }

    fn begin_object_value<W: ?Sized + Write>(&mut self, w: &mut W) -> io::Result<()> {
        w.write_all(b": ")
    }

    fn write_f64<W: ?Sized + Write>(&mut self, w: &mut W, valor: f64) -> io::Result<()> {
        w.write_all(real(valor).as_bytes())
    }

    fn write_f32<W: ?Sized + Write>(&mut self, w: &mut W, valor: f32) -> io::Result<()> {
        w.write_all(real(f64::from(valor)).as_bytes())
    }

    /// `ensure_ascii`: lo que `serde_json` deja pasar tal cual (todo menos comillas,
    /// barras y controles) se escapa aquí si no es ASCII imprimible. Python escapa
    /// también el DEL (0x7f).
    fn write_string_fragment<W: ?Sized + Write>(
        &mut self,
        w: &mut W,
        fragmento: &str,
    ) -> io::Result<()> {
        let mut desde = 0;
        for (i, c) in fragmento.char_indices() {
            if c.is_ascii() && c != '\x7f' {
                continue;
            }
            w.write_all(&fragmento.as_bytes()[desde..i])?;
            let mut unidades = [0u16; 2];
            for u in c.encode_utf16(&mut unidades) {
                write!(w, "\\u{u:04x}")?;
            }
            desde = i + c.len_utf8();
        }
        w.write_all(&fragmento.as_bytes()[desde..])
    }

    fn write_char_escape<W: ?Sized + Write>(&mut self, w: &mut W, e: CharEscape) -> io::Result<()> {
        let s: &[u8] = match e {
            CharEscape::Quote => b"\\\"",
            CharEscape::ReverseSolidus => b"\\\\",
            CharEscape::Solidus => b"/",
            CharEscape::Backspace => b"\\b",
            CharEscape::FormFeed => b"\\f",
            CharEscape::LineFeed => b"\\n",
            CharEscape::CarriageReturn => b"\\r",
            CharEscape::Tab => b"\\t",
            CharEscape::AsciiControl(b) => return write!(w, "\\u{b:04x}"),
        };
        w.write_all(s)
    }
}

/// Un real como lo escribe `repr` de Python: lo más corto que vuelve al mismo
/// valor, siempre con parte decimal, y en notación científica fuera de
/// `[1e-4, 1e16)` con al menos dos cifras de exponente (`1e-05`, `1e+16`).
fn real(x: f64) -> String {
    let abs = x.abs();
    if x == 0.0 || (1e-4..1e16).contains(&abs) {
        let s = format!("{x}");
        return if s.contains('.') { s } else { format!("{s}.0") };
    }
    // `{:e}` también da los dígitos más cortos; solo cambia cómo se escribe.
    let s = format!("{x:e}");
    let (mantisa, exponente) = s.split_once('e').unwrap_or((&s, "0"));
    let (signo, cifras) = match exponente.strip_prefix('-') {
        Some(c) => ('-', c),
        None => ('+', exponente),
    };
    format!("{mantisa}e{signo}{cifras:0>2}")
}

/// Serializa como la V1. Un tipo que no se pueda serializar es un defecto del
/// propio servidor, no de la petición: queda en el registro y se responde vacío.
pub fn a_bytes<T: Serialize + ?Sized>(valor: &T) -> Vec<u8> {
    let mut salida = Vec::with_capacity(256);
    let mut ser = Serializer::with_formatter(&mut salida, ComoPython);
    if valor.serialize(&mut ser).is_err() {
        tracing::error!("no se pudo serializar una respuesta del servidor móvil");
        return b"{}".to_vec();
    }
    salida
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn texto<T: Serialize>(v: &T) -> String {
        String::from_utf8(a_bytes(v)).unwrap()
    }

    #[test]
    fn los_separadores_son_los_de_json_dumps() {
        let v = json!({"ok": true, "lista": [1, 2], "nada": null});
        assert_eq!(texto(&v), r#"{"lista": [1, 2], "nada": null, "ok": true}"#);
    }

    #[test]
    fn lo_que_no_es_ascii_se_escapa_como_en_python() {
        assert_eq!(texto(&"Man\u{e1}"), r#""Man\u00e1""#);
        assert_eq!(
            texto(&"\u{1f3b5}"),
            r#""\ud83c\udfb5""#,
            "fuera del plano básico, en pares"
        );
        assert_eq!(texto(&"a\u{7f}b\n\"\\/"), r#""a\u007fb\n\"\\/""#);
        assert_eq!(texto(&"\u{1}"), r#""\u0001""#);
    }

    #[test]
    fn los_reales_se_escriben_como_repr() {
        let casos = [
            (180.0, "180.0"),
            (201.5, "201.5"),
            (150.25, "150.25"),
            (0.0, "0.0"),
            (-3.0, "-3.0"),
            (0.0001, "0.0001"),
            (0.000_012_5, "1.25e-05"),
            (1e16, "1e+16"),
            (1.5e300, "1.5e+300"),
            (123_456_789_012_345.6, "123456789012345.6"),
        ];
        for (x, esperado) in casos {
            assert_eq!(real(x), esperado, "{x}");
        }
        assert_eq!(
            texto(&f64::NAN),
            "null",
            "Python escribiría NaN, que no es JSON"
        );
    }
}
