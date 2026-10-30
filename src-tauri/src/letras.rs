//! Letras para la vista de reproducción (F2.2.6) y el color de su fondo.
//!
//! Las reglas son las de la V1 (`ui/modelos_qml.py`, `_normalizar_lyrics_para_ui`),
//! y sus pruebas están traducidas abajo con su nombre:
//!
//! * La sincronizada manda: si existe y es válida, la plana no se muestra; si
//!   existe y está rota (una línea sin marca de tiempo, segundos de 60 o más),
//!   **no se muestra ninguna**, porque una letra mal sincronizada es peor que
//!   ninguna.
//! * Las etiquetas de LRC (`[ar:…]`, `[offset:…]`) se ignoran sin invalidar.
//! * Lo que va detrás de `^` es una traducción pegada por el proveedor: se corta.
//! * Una plana que parece un documento (un párrafo largo y con mucha
//!   puntuación) se oculta: no es una letra.

use rusqlite::OptionalExtension;
use serde::Serialize;
use ts_rs::TS;

use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};

/// Una línea de la letra sincronizada.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct LineaLetra {
    pub ms: u32,
    pub texto: String,
}

/// La letra lista para pintarse: sincronizada, plana o ninguna.
#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct Letra {
    pub sincronizada: Vec<LineaLetra>,
    pub plana: Vec<String>,
}

const METADATOS: [&str; 12] = [
    "ar", "al", "ti", "au", "length", "by", "offset", "re", "ve", "tool", "la", "id",
];

fn es_metadato(linea: &str) -> bool {
    let Some(dentro) = linea.strip_prefix('[').and_then(|l| l.strip_suffix(']')) else {
        return false;
    };
    let Some((clave, _)) = dentro.split_once(':') else {
        return false;
    };
    METADATOS.contains(&clave.to_ascii_lowercase().as_str()) && !dentro.contains(']')
}

/// Las marcas `[mm:ss.xx]` al principio de una línea y el resto. `None` si alguna
/// marca está mal formada.
fn marcas(linea: &str) -> Option<(Vec<u32>, &str)> {
    let mut resto = linea;
    let mut tiempos = Vec::new();
    while let Some(dentro) = resto.strip_prefix('[') {
        let fin = dentro.find(']')?;
        let marca = &dentro[..fin];
        let (min, seg) = marca.split_once(':')?;
        let (seg, frac) = seg.split_once('.').unwrap_or((seg, ""));
        if min.is_empty() || min.len() > 2 || seg.len() != 2 || frac.len() > 3 {
            return None;
        }
        let todos_digitos = |s: &str| s.chars().all(|c| c.is_ascii_digit());
        if !todos_digitos(min) || !todos_digitos(seg) || !todos_digitos(frac) {
            return None;
        }
        let (min, seg): (u32, u32) = (min.parse().ok()?, seg.parse().ok()?);
        if seg >= 60 {
            return None;
        }
        let ms_frac = match frac.len() {
            0 => 0,
            1 => frac.parse::<u32>().ok()? * 100,
            2 => frac.parse::<u32>().ok()? * 10,
            _ => frac.parse::<u32>().ok()?,
        };
        tiempos.push((min * 60 + seg) * 1000 + ms_frac);
        resto = &dentro[fin + 1..];
    }
    Some((tiempos, resto))
}

/// Quita la traducción pegada tras `^` y los espacios repetidos.
fn limpiar(texto: &str) -> String {
    let corte = texto.split('^').next().unwrap_or("");
    corte.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn lineas(texto: &str) -> impl Iterator<Item = &str> {
    texto.lines().map(str::trim).filter(|l| !l.is_empty())
}

/// La sincronizada, o vacía si está rota.
pub fn sincronizada(texto: &str) -> Vec<LineaLetra> {
    let mut salida = Vec::new();
    for linea in lineas(texto) {
        if es_metadato(linea) {
            continue;
        }
        let Some((tiempos, resto)) = marcas(linea) else {
            return Vec::new();
        };
        if tiempos.is_empty() {
            return Vec::new();
        }
        let texto = limpiar(resto);
        if texto.is_empty() {
            continue;
        }
        for ms in tiempos {
            salida.push(LineaLetra {
                ms,
                texto: texto.clone(),
            });
        }
    }
    salida.sort_by_key(|l| l.ms);
    salida
}

/// La plana, sin marcas ni metadatos, o vacía si parece un documento.
pub fn plana(texto: &str) -> Vec<String> {
    let mut salida = Vec::new();
    for linea in lineas(texto) {
        if es_metadato(linea) {
            continue;
        }
        let sin_marcas = marcas(linea).map_or(linea, |(_, resto)| resto);
        let limpia = limpiar(sin_marcas);
        if !limpia.is_empty() {
            salida.push(limpia);
        }
    }
    if parece_documento(&salida) {
        return Vec::new();
    }
    salida
}

fn parece_documento(lineas: &[String]) -> bool {
    if lineas.is_empty() {
        return false;
    }
    let largos: Vec<usize> = lineas.iter().map(|l| l.chars().count()).collect();
    let total: usize = largos.iter().sum();
    if total == 0 {
        return true;
    }
    let max = *largos.iter().max().unwrap_or(&0);
    let promedio = total as f64 / lineas.len() as f64;
    let palabras: usize = lineas.iter().map(|l| l.split_whitespace().count()).sum();
    let puntuacion = lineas
        .iter()
        .flat_map(|l| l.chars())
        .filter(|c| ".,;:!?".contains(*c))
        .count();
    let densidad = puntuacion as f64 / total as f64;
    max > 180
        || (lineas.len() <= 2 && total > 160)
        || (lineas.len() < 4 && palabras > 55)
        || promedio > 110.0
        || (densidad > 0.12 && promedio > 70.0)
}

/// Normaliza lo guardado como lo mostraba la V1.
pub fn normalizar(planas: Option<&str>, sincronizadas: Option<&str>) -> Letra {
    if let Some(s) = sincronizadas.map(str::trim).filter(|s| !s.is_empty()) {
        return Letra {
            sincronizada: sincronizada(s),
            plana: Vec::new(),
        };
    }
    Letra {
        sincronizada: Vec::new(),
        plana: planas.map(plana).unwrap_or_default(),
    }
}

/// La letra de una pista, ya normalizada. Vacía si no tiene.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn de_pista(db: &BaseDeDatos, pista: i64) -> NsResult<Letra> {
    let conn = db.conexion()?;
    let fila: Option<(Option<String>, Option<String>)> = conn
        .query_row(
            "SELECT planas, sincronizadas FROM letras WHERE pista_id = ?1",
            [pista],
            |f| Ok((f.get(0)?, f.get(1)?)),
        )
        .optional()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(fila.map_or_else(Letra::default, |(p, s)| {
        normalizar(p.as_deref(), s.as_deref())
    }))
}

/// El color del fondo de la vista de reproducción, en HSL de 0 a 1.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
pub struct Ambiente {
    pub h: f64,
    pub s: f64,
    pub l: f64,
}

/// El tono medio de la portada, con la saturación y la luz acotadas para que el
/// texto claro se lea encima (`_mood_desde_portada` de la V1). `None` si la
/// imagen es casi gris o casi negra o blanca.
pub fn ambiente_de_imagen(imagen: &image::DynamicImage) -> Option<Ambiente> {
    let pequena = imagen.thumbnail(48, 48).to_rgba8();
    let (mut sen, mut cos, mut sat, mut luz, mut peso_total) = (0.0, 0.0, 0.0, 0.0, 0.0);
    for p in pequena.pixels() {
        if f64::from(p[3]) / 255.0 < 0.55 {
            continue;
        }
        let (h, s, l) = hsl(p[0], p[1], p[2]);
        if s < 0.14 || !(0.08..=0.92).contains(&l) {
            continue;
        }
        let peso = s.max(0.08) * (0.45 + l.min(0.55));
        let angulo = h * std::f64::consts::TAU;
        sen += angulo.sin() * peso;
        cos += angulo.cos() * peso;
        sat += s * peso;
        luz += l * peso;
        peso_total += peso;
    }
    if peso_total <= 0.0 {
        return None;
    }
    Some(Ambiente {
        h: (sen.atan2(cos) / std::f64::consts::TAU).rem_euclid(1.0),
        s: ((sat / peso_total) * 0.86).clamp(0.34, 0.70),
        l: (0.16 + (luz / peso_total) * 0.16).clamp(0.16, 0.31),
    })
}

/// Un color estable por pista cuando no hay portada (`_mood_fallback` de la V1:
/// FNV-1a sobre una semilla).
pub fn ambiente_de_semilla(semilla: &str) -> Ambiente {
    let mut h: u32 = 2_166_136_261;
    for c in semilla.chars() {
        h ^= c as u32;
        h = h.wrapping_mul(16_777_619);
    }
    Ambiente {
        h: f64::from(h % 360) / 360.0,
        s: (0.42 + f64::from((h >> 8) % 20) / 100.0).clamp(0.34, 0.68),
        l: (0.18 + f64::from((h >> 16) % 9) / 100.0).clamp(0.16, 0.30),
    }
}

fn hsl(r: u8, g: u8, b: u8) -> (f64, f64, f64) {
    let (r, g, b) = (
        f64::from(r) / 255.0,
        f64::from(g) / 255.0,
        f64::from(b) / 255.0,
    );
    let max = r.max(g).max(b);
    let min = r.min(g).min(b);
    let l = (max + min) / 2.0;
    if (max - min).abs() < f64::EPSILON {
        return (0.0, 0.0, l);
    }
    let d = max - min;
    let s = if l > 0.5 {
        d / (2.0 - max - min)
    } else {
        d / (max + min)
    };
    let h = if (max - r).abs() < f64::EPSILON {
        ((g - b) / d).rem_euclid(6.0)
    } else if (max - g).abs() < f64::EPSILON {
        (b - r) / d + 2.0
    } else {
        (r - g) / d + 4.0
    };
    (h / 6.0, s, l)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn textos(l: &[LineaLetra]) -> Vec<(u32, &str)> {
        l.iter().map(|x| (x.ms, x.texto.as_str())).collect()
    }

    #[test]
    fn modelo_lyrics_normaliza_synced_y_elimina_traduccion() {
        let l = normalizar(
            Some("fallback"),
            Some("[00:01.00]Hola mundo ^ Hello world\n[00:02]Siguiente verso"),
        );
        assert_eq!(
            textos(&l.sincronizada),
            [(1000, "Hola mundo"), (2000, "Siguiente verso")]
        );
        assert!(l.plana.is_empty());
    }

    #[test]
    fn modelo_lyrics_malformada_oculta_plain_fallback() {
        let l = normalizar(
            Some("Esta no debe mostrarse"),
            Some("[00:01.00]Linea valida\nLinea sin timestamp"),
        );
        assert_eq!(l, Letra::default());
    }

    #[test]
    fn modelo_lyrics_ignora_metadata_lrc_sin_invalidar() {
        let l = normalizar(
            None,
            Some("[ar:Artista]\n[ti:Tema]\n[offset:0]\n[00:03.500]Verso"),
        );
        assert_eq!(textos(&l.sincronizada), [(3500, "Verso")]);
    }

    #[test]
    fn modelo_lyrics_plain_sin_synced_se_sanitiza() {
        let l = normalizar(
            Some("[ar:Artista]\nPrimera linea ^ Translation\n[00:02.00]Segunda linea"),
            Some(""),
        );
        assert_eq!(l.plana, ["Primera linea", "Segunda linea"]);
    }

    #[test]
    fn modelo_lyrics_plain_tipo_documento_se_oculta() {
        let bloque = "Esta letra viene como un documento pegado en un solo parrafo, con muchas frases, \
                      puntuacion, explicaciones, texto extendido y una estructura que no sirve como lyric \
                      normal para una vista sincronizada.";
        assert_eq!(normalizar(Some(bloque), None), Letra::default());
    }

    #[test]
    fn varias_marcas_en_una_linea_la_repiten_en_orden() {
        let l = sincronizada("[00:10.00][00:01.5]Estribillo\n[00:05.25]Verso");
        assert_eq!(
            textos(&l),
            [
                (1500, "Estribillo"),
                (5250, "Verso"),
                (10_000, "Estribillo")
            ]
        );
    }

    #[test]
    fn segundos_de_sesenta_o_mas_invalidan_la_letra() {
        assert!(sincronizada("[00:61.00]mal").is_empty());
    }

    #[test]
    fn modelo_lyrics_mood_usa_color_dominante_de_portada() {
        let roja = image::DynamicImage::ImageRgb8(image::RgbImage::from_pixel(
            32,
            32,
            image::Rgb([0xe3, 0x31, 0x2c]),
        ));
        let a = ambiente_de_imagen(&roja).unwrap();
        assert!(a.h < 0.08 || a.h > 0.92, "{a:?}");
        assert!((0.34..=0.70).contains(&a.s));
        assert!((0.16..=0.31).contains(&a.l));
    }

    #[test]
    fn modelo_lyrics_mood_fallback_estable_y_en_rango() {
        let a = ambiente_de_semilla("pista:7");
        assert_eq!(a, ambiente_de_semilla("pista:7"));
        assert!((0.0..=1.0).contains(&a.h));
        assert!((0.34..=0.68).contains(&a.s));
        assert!((0.16..=0.30).contains(&a.l));
        let gris = image::DynamicImage::ImageRgb8(image::RgbImage::from_pixel(
            8,
            8,
            image::Rgb([128, 128, 128]),
        ));
        assert_eq!(ambiente_de_imagen(&gris), None, "lo gris no da color");
    }
}
