//! Los indicios del juego y la comprobación de lo que escribe el jugador:
//! `servicios/explorador_ciego/hints.py`.
//!
//! El juego premia acercarse, no transcribir: ambos lados se normalizan como en la
//! catalogación (sin tildes, sin signos, comillas y guiones de cualquier tipo
//! iguales) y se comparan con el `SequenceMatcher` de difflib.

use serde::Serialize;
use ts_rs::TS;

use crate::catalogo::texto::{normalizar_para_comparar, ratio_secuencias};

/// Desde aquí, acierto.
pub const UMBRAL_ACIERTO: f64 = 0.84;
/// Desde aquí y hasta el acierto, "casi".
pub const UMBRAL_CERCA: f64 = 0.62;

/// El sistema de escritura de un carácter, por su bloque Unicode.
fn alfabeto_de(c: char) -> &'static str {
    match u32::from(c) {
        0..=0x024F => "latino",
        0x0370..=0x03FF => "griego",
        0x0400..=0x04FF => "cirilico",
        0x0590..=0x05FF => "hebreo",
        0x0600..=0x06FF => "arabe",
        0x0900..=0x097F => "devanagari",
        0x3040..=0x30FF => "japones",
        0x4E00..=0x9FFF => "chino",
        0xAC00..=0xD7AF => "coreano",
        _ => "otro",
    }
}

/// `detectar_alfabeto`: el de más letras; sin letras, latino. Con empate gana el
/// primero que aparece, como el `max` sobre el `dict` de la V1.
#[must_use]
pub fn alfabeto(titulo: &str) -> &'static str {
    let mut cuenta: Vec<(&'static str, usize)> = Vec::new();
    for c in titulo.chars().filter(|c| c.is_alphabetic()) {
        let a = alfabeto_de(c);
        match cuenta.iter_mut().find(|(k, _)| *k == a) {
            Some((_, n)) => *n += 1,
            None => cuenta.push((a, 1)),
        }
    }
    let mut mejor: Option<(&'static str, usize)> = None;
    for (a, n) in cuenta {
        if mejor.is_none_or(|(_, m)| n > m) {
            mejor = Some((a, n));
        }
    }
    mejor.map_or("latino", |(a, _)| a)
}

/// `requiere_escritura`: se puede pedir que se escriba el título solo si todas sus
/// letras son latinas; si no, el jugador dice "¡La sé!" y se fía de él.
#[must_use]
pub fn se_puede_escribir(titulo: &str) -> bool {
    titulo
        .chars()
        .filter(|c| c.is_alphabetic())
        .all(|c| alfabeto_de(c) == "latino")
}

/// Lo que dice la comprobación de un intento.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
pub struct Intento {
    pub acierto: bool,
    pub cerca: bool,
    pub ratio: f64,
}

/// `validar_intento`.
#[must_use]
pub fn comprobar(titulo: &str, intento: &str) -> Intento {
    let (real, dicho) = (
        normalizar_para_comparar(titulo),
        normalizar_para_comparar(intento),
    );
    if real.is_empty() || dicho.is_empty() {
        return Intento {
            acierto: false,
            cerca: false,
            ratio: 0.0,
        };
    }
    if real == dicho {
        return Intento {
            acierto: true,
            cerca: false,
            ratio: 1.0,
        };
    }
    let a: Vec<char> = real.chars().take(200).collect();
    let b: Vec<char> = dicho.chars().take(200).collect();
    let ratio = ratio_secuencias(&a, &b);
    Intento {
        acierto: ratio >= UMBRAL_ACIERTO,
        cerca: (UMBRAL_CERCA..UMBRAL_ACIERTO).contains(&ratio),
        ratio: crate::dj::redondear(ratio, 4),
    }
}

/// Los indicios que se pueden pedir, en el orden en que se ofrecen.
#[derive(
    Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, serde::Deserialize, TS,
)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub enum Indicio {
    Alfabeto,
    EmpiezaCon,
    TerminaCon,
    CantidadPalabras,
    CantidadLetras,
}

pub const INDICIOS: [Indicio; 5] = [
    Indicio::Alfabeto,
    Indicio::EmpiezaCon,
    Indicio::TerminaCon,
    Indicio::CantidadPalabras,
    Indicio::CantidadLetras,
];

/// `hint_empieza_con`: la primera letra o cifra, en mayúscula.
#[must_use]
pub fn empieza_con(titulo: &str) -> Option<String> {
    titulo
        .chars()
        .find(|c| c.is_alphanumeric())
        .map(|c| c.to_uppercase().collect())
}

/// `hint_termina_con`.
#[must_use]
pub fn termina_con(titulo: &str) -> Option<String> {
    titulo
        .chars()
        .rev()
        .find(|c| c.is_alphanumeric())
        .map(|c| c.to_uppercase().collect())
}

#[must_use]
pub fn palabras(titulo: &str) -> usize {
    titulo.split_whitespace().count()
}

/// Letras y cifras, sin espacios ni signos: "lo que mide el nombre".
#[must_use]
pub fn letras(titulo: &str) -> usize {
    titulo.chars().filter(|c| c.is_alphanumeric()).count()
}

/// El valor de un indicio para un título, como texto que la vista pone tras su
/// etiqueta.
#[must_use]
pub fn valor(indicio: Indicio, titulo: &str) -> String {
    match indicio {
        Indicio::Alfabeto => alfabeto(titulo).to_owned(),
        Indicio::EmpiezaCon => empieza_con(titulo).unwrap_or_default(),
        Indicio::TerminaCon => termina_con(titulo).unwrap_or_default(),
        Indicio::CantidadPalabras => palabras(titulo).to_string(),
        Indicio::CantidadLetras => letras(titulo).to_string(),
    }
}

#[cfg(test)]
mod pruebas {
    //! `tests/test_explorador_ciego_hints.py` de la V1.

    use super::*;

    #[test]
    fn el_titulo_exacto_con_otras_mayusculas_tildes_o_signos_acierta() {
        let si = |a: &str, b: &str| assert!(comprobar(a, b).acierto, "{a} / {b}");
        assert_eq!(comprobar("Yesterday", "Yesterday").ratio, 1.0);
        si("Yesterday", "yesterday");
        si("Canción del Mar", "cancion del mar");
        si("Don't Stop Believin'", "dont stop believin");
        si("Don\u{2019}t Stop", "Don't Stop");
        si("\u{201C}Hello\u{201D} World", "\"Hello\" World");
        si("Rock\u{2014}Roll Symphony", "Rock-Roll Symphony");
        si(
            "We Are Never Ever Getting Back Together",
            "we are never ever getting back together",
        );
    }

    #[test]
    fn una_letra_mal_acierta_otra_cancion_no_y_lo_parcial_queda_cerca() {
        assert!(comprobar("Bohemian Rhapsody", "Bohemia Rapsody").acierto);
        let lejos = comprobar("Bohemian Rhapsody", "Imagine");
        assert!(!lejos.acierto && !lejos.cerca);
        let parcial = comprobar("Stairway to Heaven", "Stairway Heaven");
        assert!(parcial.cerca || parcial.acierto);
        assert_eq!(comprobar("Yesterday", "").ratio, 0.0);
        assert!(!comprobar("", "algo").acierto);
        const { assert!(UMBRAL_CERCA < UMBRAL_ACIERTO) };
    }

    #[test]
    fn los_indicios_de_letras_ignoran_signos_y_espacios() {
        assert_eq!(
            empieza_con("(I Can't Get No) Satisfaction").as_deref(),
            Some("I")
        );
        assert_eq!(empieza_con("yesterday").as_deref(), Some("Y"));
        assert_eq!(empieza_con("99 Luftballons").as_deref(), Some("9"));
        assert_eq!(empieza_con("...").as_deref(), None);
        assert_eq!(termina_con("Help!").as_deref(), Some("P"));
        assert_eq!(palabras("Stairway to Heaven"), 3);
        assert_eq!(palabras(""), 0);
        assert_eq!(letras("Hey Jude"), 7);
        assert_eq!(letras("Route 66"), 7);
        assert_eq!(letras("Don't!"), 4);
    }

    #[test]
    fn el_alfabeto_es_el_de_mas_letras_y_sin_letras_latino() {
        assert_eq!(alfabeto("Yesterday"), "latino");
        assert_eq!(alfabeto("Кино"), "cirilico");
        assert_eq!(alfabeto("Ωμέγα"), "griego");
        assert_eq!(alfabeto("月亮代表我的心"), "chino");
        assert_eq!(alfabeto("さくら"), "japones");
        assert_eq!(alfabeto("حبيبي"), "arabe");
        assert_eq!(alfabeto(""), "latino");
        assert_eq!(alfabeto("Love Кино Кино"), "cirilico");
    }

    #[test]
    fn solo_se_pide_escribir_lo_que_es_todo_latino() {
        assert!(se_puede_escribir("Canción del Mar"));
        assert!(se_puede_escribir("1999 (Remastered) — Live!"));
        assert!(!se_puede_escribir("Кино"));
        assert!(!se_puede_escribir("Love Кино"));
        assert!(se_puede_escribir(""));
    }
}
