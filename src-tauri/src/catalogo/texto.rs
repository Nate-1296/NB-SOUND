//! Normalización de texto para catalogar (F4.1.2): la de la V1
//! (`utils/text.py` y las listas de `config/settings.py`), función a función.
//!
//! Todo es puro. Los nombres siguen a los de la V1 para poder comparar las dos
//! implementaciones a la vista, y las pruebas son sus ejemplos y las de
//! `tests/test_text_slug_unicode.py`.

use std::collections::HashSet;
use std::sync::LazyLock;

use regex::Regex;
use unicode_normalization::char::is_combining_mark;
use unicode_normalization::UnicodeNormalization;

/// `SLUG_MAX_LENGTH` de la V1.
pub const LARGO_MAXIMO_SLUG: usize = 80;

/// `PROMO_SUFFIXES`: lo que se corta del título antes de comparar, en este orden.
const SUFIJOS_PROMOCIONALES: &[&str] = &[
    "(official video)",
    "(official audio)",
    "(official music video)",
    "(lyrics)",
    "(lyric video)",
    "(visualizer)",
    "(audio)",
    "(hd)",
    "(hq)",
    "(4k)",
    "(explicit)",
    "(clean)",
    "[official video]",
    "[official audio]",
    "[lyrics]",
    "[explicit]",
    "[clean]",
    "[hd]",
    "(official)",
    "(video oficial)",
    "(audio oficial)",
    "[spotdown.org]",
    "(spotdown.org)",
    "spotdown.org",
    "[_spotdown.org]",
    "[www.spotdown.org]",
    "[mp3paw.com]",
    "[mp3juice.cc]",
    "[zippyshare.com]",
    "[freemusicdownload]",
    "(freemusicdownload)",
    "(remastered)",
    "(remaster)",
    "(remastered version)",
    "(2011 remaster)",
    "(2012 remaster)",
    "(2013 remaster)",
    "(2014 remaster)",
    "(2015 remaster)",
    "(2016 remaster)",
    "(2017 remaster)",
    "(2018 remaster)",
    "(2019 remaster)",
    "(2020 remaster)",
    "(2021 remaster)",
    "(2022 remaster)",
    "(2023 remaster)",
    "(2024 remaster)",
    "(2025 remaster)",
    "[remastered]",
    "[remaster]",
    "(deluxe edition)",
    "(deluxe version)",
    "(deluxe)",
    "[deluxe edition]",
    "[deluxe]",
    "(extended version)",
    "(extended edition)",
    "(extended)",
    "[extended]",
    "(album version)",
    "(single version)",
    "(radio edit)",
    "(radio version)",
    "(original mix)",
    "(original version)",
    "(bonus track)",
    "(bonus)",
    "(instrumental)",
    "[instrumental]",
    "(mono)",
    "(mono version)",
    "(stereo)",
    "(stereo version)",
    "(acoustic)",
    "(acoustic version)",
    "[acoustic]",
    "(live)",
    "[live]",
    "(demo)",
    "(demo version)",
    "[demo]",
    "(anniversary edition)",
    "(special edition)",
    "(super deluxe)",
    "(super deluxe edition)",
    "(anniversary)",
    "(20th anniversary)",
    "(25th anniversary)",
    "(30th anniversary)",
    "(40th anniversary)",
    "(50th anniversary)",
];

/// `VERSION_KEYWORDS`.
pub const PALABRAS_DE_VERSION: &[&str] = &[
    "remastered",
    "remaster",
    "deluxe",
    "extended",
    "album version",
    "radio edit",
    "single version",
    "acoustic",
    "instrumental",
    "demo",
    "live",
    "bonus",
    "anniversary",
    "special edition",
    "anniversary edition",
];

fn re(patron: &str) -> Regex {
    Regex::new(patron).expect("las expresiones de la V1 compilan")
}

static ESPACIOS: LazyLock<Regex> = LazyLock::new(|| re(r"\s+"));
static PUNTUACION: LazyLock<Regex> = LazyLock::new(|| re(r"[^\w\s]"));
static SITIOS_DESCARGA: LazyLock<Regex> = LazyLock::new(|| {
    re(concat!(
        r"(?i)[\[\(]?\s*(?:www\.)?(?:",
        r"spotdown\.org|mp3paw\.(?:com|cc|io)|mp3juice\.(?:cc|se|tel)|zippyshare\.com",
        r"|freemusicdownload\.[a-z]+|mp3\.pm|mp3skull\.[a-z]+|mr-jatt\.[a-z]+",
        r"|songspk\.[a-z]+|downloadming\.[a-z]+",
        r")\s*[\]\)]?"
    ))
});
static DOMINIO_ENTRE_CORCHETES: LazyLock<Regex> =
    LazyLock::new(|| re(r"(?i)[\[\(]\s*(?:www\.)?[\w\-]+\.(?:org|com|cc|io|net|me)\s*[\]\)]"));
static PARENTESIS_VACIOS: LazyLock<Regex> = LazyLock::new(|| re(r"\(\s*\)|\[\s*\]"));
static FEAT_SEPARA: LazyLock<Regex> =
    LazyLock::new(|| re(r"(?i)\s*[\(\[]?\s*(?:featuring|feat\.?|ft\.?|with|w/)\s+"));
static FEAT_EN_TITULO: LazyLock<Regex> =
    LazyLock::new(|| re(r"(?i)[\(\[]\s*(?:featuring|feat\.?|ft\.?|with)\s+([^\)\]]+)[\)\]]"));
static VERSION_EN_TITULO: LazyLock<Regex> = LazyLock::new(|| {
    let mut claves: Vec<&str> = PALABRAS_DE_VERSION.to_vec();
    claves.sort_by_key(|k| std::cmp::Reverse(k.len()));
    let alternativas: Vec<String> = claves.iter().map(|k| regex::escape(k)).collect();
    re(&format!(
        r"(?i)\s*[\(\[]\s*(?:{})[^\)\]]*[\)\]]",
        alternativas.join("|")
    ))
});
static ARTISTA_TITULO: LazyLock<Regex> = LazyLock::new(|| re(r"^(.+?)\s*-\s*(.+)$"));
static NUMERO_TITULO: LazyLock<Regex> = LazyLock::new(|| re(r"^(\d{1,3})[.\-\s_]+(.+)$"));
static ARTISTA_NUMERO_TITULO: LazyLock<Regex> =
    LazyLock::new(|| re(r"^(.+?)\s*-\s*(\d{2})\s*[-_.]\s*(.+)$"));
static EXTENSION: LazyLock<Regex> = LazyLock::new(|| re(r"\.[a-zA-Z0-9]{2,5}$"));
static CORCHETES: LazyLock<Regex> = LazyLock::new(|| re(r"\s*\[.*?\]\s*"));
static SOLO_DIGITOS: LazyLock<Regex> = LazyLock::new(|| re(r"^\d+$"));
static ANIO: LazyLock<Regex> = LazyLock::new(|| re(r"\b(19[0-9]{2}|20[0-2][0-9])\b"));
static ISRC: LazyLock<Regex> = LazyLock::new(|| re(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$"));

/// Los patrones de variante, en el orden en que la V1 los prueba.
static VARIANTES: LazyLock<Vec<(&'static str, Regex)>> = LazyLock::new(|| {
    vec![
        (
            "Remix",
            re(concat!(
                r"(?i)[\(\[]\s*(?:[^\)\]]*\s+)?(?:remix|rmx|rework|bootleg|flip|dub mix|club mix|radio mix|extended mix|[a-z]+ mix)",
                r"(?:\s[^\)\]]*)?[\)\]]|\b(?:remix|rmx)\b"
            )),
        ),
        (
            "Live",
            re(
                r"(?i)[\(\[]\s*(?:live|en vivo|ao vivo|en directo|concert|concierto|tour)(?:[^\)\]]*)?[\)\]]|\blive\b",
            ),
        ),
        (
            "Acoustic",
            re(r"(?i)[\(\[]\s*acoustic(?:\s+[^\)\]]*)?[\)\]]|\bacoustic(?:\s+version)?\b"),
        ),
        (
            "Instrumental",
            re(r"(?i)[\(\[]\s*instrumental(?:\s+[^\)\]]*)?[\)\]]|\binstrumental\b"),
        ),
        (
            "Demo",
            re(r"(?i)[\(\[]\s*demo(?:\s+[^\)\]]*)?[\)\]]|\bdemo\b"),
        ),
    ]
});
static BLOQUE_VARIANTE: LazyLock<Regex> = LazyLock::new(|| {
    re(concat!(
        r"(?i)\s*[\(\[]\s*(?:(?:[^\)\]]*\s+)?(?:remix|rmx|rework|bootleg|flip|[a-z]+ mix)",
        r"|live(?:\s+[^\)\]]*)?|en vivo(?:\s+[^\)\]])?|acoustic(?:\s+version)?|instrumental",
        r"|demo(?:\s+version)?)\s*[\)\]]"
    ))
});

/// NFKD sin marcas combinantes (`eliminar_acentos`).
pub fn eliminar_acentos(texto: &str) -> String {
    texto.nfkd().filter(|c| !is_combining_mark(*c)).collect()
}

pub fn limpiar_espacios(texto: &str) -> String {
    ESPACIOS.replace_all(texto, " ").trim().to_owned()
}

/// Sin caracteres de control y con los espacios colapsados; conserva los acentos.
pub fn normalizar_base(texto: &str) -> String {
    let sin_control: String = texto.chars().filter(|c| !c.is_control()).collect();
    limpiar_espacios(&sin_control)
}

/// Quita las marcas de las webs de descarga (`[spotdown.org]` y compañía).
pub fn limpiar_basura_descarga(texto: &str) -> String {
    if texto.is_empty() {
        return String::new();
    }
    let t = SITIOS_DESCARGA.replace_all(texto, " ");
    let t = DOMINIO_ENTRE_CORCHETES.replace_all(&t, " ");
    limpiar_espacios(&t)
}

/// Un nombre apto para carpetas y archivos, que conserva cualquier alfabeto: la
/// regla de las claves de artista y álbum de la V1 (`construir_slug`).
pub fn construir_slug(texto: &str) -> String {
    construir_slug_con(texto, LARGO_MAXIMO_SLUG)
}

pub fn construir_slug_con(texto: &str, largo: usize) -> String {
    const VACIO: &str = "sin_titulo";
    let base: String = texto.nfkc().collect();
    let base = limpiar_espacios(&base).to_lowercase();
    let mut s = String::with_capacity(base.len());
    for c in base.chars() {
        if c.is_alphanumeric() && !is_combining_mark(c) {
            s.push(c);
        } else if is_combining_mark(c) {
            // Una marca solo vale detrás de algo que se conserva.
            if !s.is_empty() && !s.ends_with('_') {
                s.push(c);
            }
        } else {
            s.push('_');
        }
    }
    let mut colapsado = String::with_capacity(s.len());
    for c in s.chars() {
        if !(c == '_' && colapsado.ends_with('_')) {
            colapsado.push(c);
        }
    }
    let recortar = |t: &str| t.trim_matches(['.', '_', ' ']).to_owned();
    let limpio = recortar(&colapsado);
    if limpio.is_empty() {
        return VACIO.to_owned();
    }
    let cortado: String = limpio.chars().take(largo).collect();
    let cortado = cortado.trim_end_matches(['.', '_', ' ']).to_owned();
    if cortado.is_empty() {
        VACIO.to_owned()
    } else {
        cortado
    }
}

/// Minúsculas, sin acentos ni símbolos (`para_comparacion`).
pub fn para_comparacion(texto: &str) -> String {
    if texto.is_empty() {
        return String::new();
    }
    let t = eliminar_acentos(&texto.to_lowercase());
    limpiar_espacios(&PUNTUACION.replace_all(&t, " "))
}

/// Comillas y guiones tipográficos a su forma ASCII.
fn prenormalizar(texto: &str) -> String {
    let mut s = String::with_capacity(texto.len());
    for c in texto.chars() {
        match c {
            '\u{2018}' | '\u{2019}' | '\u{201a}' | '\u{201b}' | '\u{2bc}' | '`' => s.push('\''),
            '\u{201c}' | '\u{201d}' | '\u{201e}' | '\u{201f}' | '\u{ab}' | '\u{bb}' => s.push('"'),
            '\u{2013}' | '\u{2014}' | '\u{2212}' | '\u{2010}' => s.push('-'),
            '\u{2026}' => s.push_str("..."),
            otro => s.push(otro),
        }
    }
    s
}

/// La comparación tolerante que comparten catalogación y deduplicación
/// (`normalizar_para_comparar`): `"Canción"` y `"cancion"` son iguales.
pub fn normalizar_para_comparar(texto: &str) -> String {
    if texto.is_empty() {
        return String::new();
    }
    let sin_marcas: String = prenormalizar(texto)
        .nfd()
        .filter(|c| !is_combining_mark(*c))
        .collect();
    limpiar_espacios(&PUNTUACION.replace_all(&sin_marcas, " ")).to_lowercase()
}

/// Un título listo para buscar: sin marcas de descarga, sufijos promocionales ni
/// paréntesis vacíos (`normalizar_titulo`).
pub fn normalizar_titulo(titulo: &str) -> String {
    if titulo.is_empty() {
        return String::new();
    }
    let mut t = normalizar_base(&limpiar_basura_descarga(titulo));
    let mut minus = t.to_lowercase();
    for sufijo in SUFIJOS_PROMOCIONALES {
        if let Some(i) = minus.find(sufijo) {
            // La V1 corta por la posición en minúsculas: con texto ASCII antes del
            // sufijo (lo normal) coincide con la del original.
            let i = t
                .char_indices()
                .nth(minus[..i].chars().count())
                .map_or(t.len(), |(b, _)| b);
            t = t[..i].trim().to_owned();
            minus = t.to_lowercase();
        }
    }
    limpiar_espacios(&PARENTESIS_VACIOS.replace_all(&t, ""))
}

/// El título sin la anotación de versión entre paréntesis (`limpiar_version_titulo`).
pub fn limpiar_version_titulo(titulo: &str) -> String {
    let r = VERSION_EN_TITULO.replace_all(titulo, "").trim().to_owned();
    if r.is_empty() {
        titulo.to_owned()
    } else {
        r
    }
}

/// Artista principal y colaboradores (`separar_artista_principal`).
pub fn separar_artista_principal(texto: &str) -> (String, Option<String>) {
    if texto.is_empty() {
        return (String::new(), None);
    }
    let mut partes = FEAT_SEPARA.splitn(texto, 2);
    let principal = partes.next().unwrap_or_default();
    match partes.next() {
        Some(resto) => (
            principal
                .trim()
                .trim_end_matches(['(', '[', ' '])
                .to_owned(),
            Some(resto.trim().trim_end_matches([']', ')']).to_owned()),
        ),
        None => (texto.trim().to_owned(), None),
    }
}

pub fn normalizar_artista(artista: &str) -> String {
    if artista.is_empty() {
        return String::new();
    }
    limpiar_espacios(&separar_artista_principal(&normalizar_base(artista)).0)
}

/// El título sin el `(feat. X)` y el colaborador (`extraer_featuring_del_titulo`).
pub fn extraer_featuring_del_titulo(titulo: &str) -> (String, Option<String>) {
    match FEAT_EN_TITULO.captures(titulo) {
        Some(c) => {
            let feat = c.get(1).map(|m| m.as_str().trim().to_owned());
            let limpio = limpiar_espacios(FEAT_EN_TITULO.replace_all(titulo, "").trim());
            (limpio, feat)
        }
        None => (titulo.trim().to_owned(), None),
    }
}

/// Lo que se deduce del nombre del archivo (`parsear_nombre_archivo`).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct DelNombre {
    pub artista: Option<String>,
    pub titulo: Option<String>,
    pub numero: Option<String>,
}

pub fn parsear_nombre_archivo(nombre: &str) -> DelNombre {
    let mut r = DelNombre::default();
    if nombre.is_empty() {
        return r;
    }
    let base = EXTENSION.replace(nombre, "").replace('_', " ");
    let base = limpiar_basura_descarga(base.trim());
    let base = limpiar_espacios(&CORCHETES.replace_all(&base, " "));
    let limpiar = |v: &str| Some(normalizar_titulo(&limpiar_espacios(v))).filter(|s| !s.is_empty());
    if let Some(m) = ARTISTA_NUMERO_TITULO.captures(&base) {
        r.artista = limpiar(&m[1]);
        r.numero = Some(m[2].to_owned());
        r.titulo = limpiar(&m[3]);
        return r;
    }
    if let Some(m) = ARTISTA_TITULO.captures(&base) {
        let artista = limpiar_espacios(&m[1]);
        if !SOLO_DIGITOS.is_match(&artista) {
            r.artista = limpiar(&artista);
            r.titulo = limpiar(&m[2]);
            return r;
        }
    }
    if let Some(m) = NUMERO_TITULO.captures(&base) {
        if m[1].parse::<u32>().is_ok_and(|n| (1..=99).contains(&n)) {
            r.numero = Some(m[1].to_owned());
            r.titulo = limpiar(&m[2]);
            return r;
        }
    }
    r.titulo = limpiar(&base);
    r
}

/// Jaccard de palabras.
pub fn similitud_tokens(a: &str, b: &str) -> f64 {
    let ta: HashSet<String> = para_comparacion(a)
        .split_whitespace()
        .map(str::to_owned)
        .collect();
    let tb: HashSet<String> = para_comparacion(b)
        .split_whitespace()
        .map(str::to_owned)
        .collect();
    if ta.is_empty() || tb.is_empty() {
        return 0.0;
    }
    ta.intersection(&tb).count() as f64 / ta.union(&tb).count() as f64
}

/// `difflib.SequenceMatcher(None, a, b).ratio()`, con su heurística de basura
/// automática (`autojunk`) para secuencias de 200 o más.
pub fn ratio_secuencias(a: &[char], b: &[char]) -> f64 {
    let total = a.len() + b.len();
    if total == 0 {
        return 1.0;
    }
    2.0 * coincidencias(a, b) as f64 / total as f64
}

fn coincidencias(a: &[char], b: &[char]) -> usize {
    use std::collections::HashMap;
    let mut b2j: HashMap<char, Vec<usize>> = HashMap::new();
    for (j, c) in b.iter().enumerate() {
        b2j.entry(*c).or_default().push(j);
    }
    if b.len() >= 200 {
        let limite = b.len() / 100 + 1;
        b2j.retain(|_, v| v.len() <= limite);
    }
    // La búsqueda recursiva de bloques de `get_matching_blocks`, con una pila.
    let mut total = 0;
    let mut pila = vec![(0, a.len(), 0, b.len())];
    while let Some((alo, ahi, blo, bhi)) = pila.pop() {
        let (i, j, k) = bloque_mas_largo(a, &b2j, alo, ahi, blo, bhi);
        if k > 0 {
            total += k;
            if alo < i && blo < j {
                pila.push((alo, i, blo, j));
            }
            if i + k < ahi && j + k < bhi {
                pila.push((i + k, ahi, j + k, bhi));
            }
        }
    }
    total
}

fn bloque_mas_largo(
    a: &[char],
    b2j: &std::collections::HashMap<char, Vec<usize>>,
    alo: usize,
    ahi: usize,
    blo: usize,
    bhi: usize,
) -> (usize, usize, usize) {
    use std::collections::HashMap;
    let (mut mi, mut mj, mut mk) = (alo, blo, 0usize);
    let mut j2len: HashMap<usize, usize> = HashMap::new();
    for (i, c) in a.iter().enumerate().take(ahi).skip(alo) {
        let mut nuevo = HashMap::new();
        if let Some(js) = b2j.get(c) {
            for &j in js {
                if j < blo {
                    continue;
                }
                if j >= bhi {
                    break;
                }
                let k = j
                    .checked_sub(1)
                    .and_then(|p| j2len.get(&p))
                    .copied()
                    .unwrap_or(0)
                    + 1;
                nuevo.insert(j, k);
                if k > mk {
                    (mi, mj, mk) = (i + 1 - k, j + 1 - k, k);
                }
            }
        }
        j2len = nuevo;
    }
    (mi, mj, mk)
}

pub fn similitud_secuencial(a: &str, b: &str) -> f64 {
    if a.is_empty() || b.is_empty() {
        return 0.0;
    }
    let (a, b): (Vec<char>, Vec<char>) = (
        para_comparacion(a).chars().collect(),
        para_comparacion(b).chars().collect(),
    );
    ratio_secuencias(&a, &b)
}

pub fn similitud_trigrama(a: &str, b: &str) -> f64 {
    if a.is_empty() || b.is_empty() {
        return 0.0;
    }
    let (na, nb): (Vec<char>, Vec<char>) = (
        para_comparacion(a).chars().collect(),
        para_comparacion(b).chars().collect(),
    );
    if na.len() < 3 || nb.len() < 3 {
        return similitud_secuencial(a, b);
    }
    let trigramas =
        |s: &[char]| -> HashSet<String> { s.windows(3).map(|w| w.iter().collect()).collect() };
    let (ta, tb) = (trigramas(&na), trigramas(&nb));
    ta.intersection(&tb).count() as f64 / ta.union(&tb).count() as f64
}

/// 50 % secuencial, 35 % palabras y 15 % trigramas, a cuatro decimales.
pub fn similitud_combinada(a: &str, b: &str) -> f64 {
    if a.is_empty() || b.is_empty() {
        return 0.0;
    }
    let v = similitud_secuencial(a, b) * 0.50
        + similitud_tokens(a, b) * 0.35
        + similitud_trigrama(a, b) * 0.15;
    redondear(v, 4)
}

/// `round(x, n)` de Python: al par en el empate exacto.
pub fn redondear(x: f64, decimales: i32) -> f64 {
    let f = 10f64.powi(decimales);
    let y = x * f;
    let r = y.round();
    let r = if (y - y.trunc()).abs() == 0.5 {
        2.0 * (y / 2.0).round()
    } else {
        r
    };
    r / f
}

pub fn extraer_anio_del_texto(valor: &str) -> Option<i32> {
    ANIO.captures(valor).and_then(|c| c[1].parse().ok())
}

/// `3/12` o `3`; fuera de 1 a 999, nada.
pub fn limpiar_numero_pista(valor: &str) -> Option<u32> {
    valor
        .split('/')
        .next()?
        .trim()
        .parse::<i64>()
        .ok()
        .filter(|n| (1..=999).contains(n))
        .map(|n| n as u32)
}

pub fn normalizar_isrc(isrc: &str) -> Option<String> {
    let limpio: String = isrc
        .chars()
        .filter(|c| !c.is_whitespace() && *c != '-')
        .collect::<String>()
        .to_uppercase();
    ISRC.is_match(&limpio).then_some(limpio)
}

pub fn detectar_tipo_variante(titulo: &str) -> Option<&'static str> {
    VARIANTES
        .iter()
        .find(|(_, p)| p.is_match(titulo))
        .map(|(t, _)| *t)
}

pub fn parsear_variante_titulo(titulo: &str) -> (String, Option<&'static str>) {
    let Some(tipo) = detectar_tipo_variante(titulo) else {
        return (titulo.to_owned(), None);
    };
    let base = BLOQUE_VARIANTE.replace_all(titulo, "").trim().to_owned();
    (
        if base.is_empty() {
            titulo.to_owned()
        } else {
            base
        },
        Some(tipo),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn el_slug_conserva_cualquier_alfabeto() {
        let s = construir_slug("Песня 夜に駆ける");
        assert!(s.contains("песня") && s.contains("夜に駆ける"), "{s}");
        for (original, esperado) in [
            ("Шарлот", "шарлот"),
            ("Малышка", "малышка"),
            ("Четыре украинки", "четыре_украинки"),
            ("Мне пох", "мне_пох"),
            ("Последняя Любовь", "последняя_любовь"),
            ("Cristal & МОЁТ", "cristal_моёт"),
            ("Beyoncé - Niño", "beyoncé_niño"),
            ("Canción número 1", "canción_número_1"),
        ] {
            assert_eq!(construir_slug(original), esperado);
        }
    }

    #[test]
    fn el_slug_solo_cae_a_sin_titulo_si_no_queda_nada() {
        for vacio in ["", "   ", "////***:::|||???"] {
            assert_eq!(construir_slug(vacio), "sin_titulo");
        }
        assert_eq!(construir_slug(&"a".repeat(100)).chars().count(), 80);
    }

    #[test]
    fn comparar_ignora_tildes_comillas_y_mayusculas() {
        assert_eq!(normalizar_para_comparar("Canción"), "cancion");
        assert_eq!(normalizar_para_comparar("Don\u{2019}t Stop"), "don t stop");
        assert_eq!(normalizar_para_comparar("   hola  x  "), "hola x");
        assert_eq!(para_comparacion("Mañana, ¡Sí!"), "manana si");
        assert_eq!(eliminar_acentos("Ñoño café"), "Nono cafe");
    }

    #[test]
    fn las_marcas_de_descarga_desaparecen() {
        assert_eq!(limpiar_basura_descarga("Song [spotdown.org]"), "Song");
        assert_eq!(limpiar_basura_descarga("Song (www.spotdown.org)"), "Song");
        assert_eq!(
            limpiar_basura_descarga("Song [mp3paw.com] - Artist"),
            "Song - Artist"
        );
        assert_eq!(limpiar_basura_descarga("Song [algo.net]"), "Song");
        assert_eq!(limpiar_basura_descarga("website.band"), "website.band");
    }

    #[test]
    fn el_titulo_pierde_lo_promocional() {
        assert_eq!(normalizar_titulo("Hello (Official Video)"), "Hello");
        assert_eq!(normalizar_titulo("Song [spotdown.org] ()"), "Song");
        assert_eq!(
            normalizar_titulo("Yesterday (2009 Remaster)"),
            "Yesterday (2009 Remaster)"
        );
        assert_eq!(normalizar_titulo("Yesterday (2019 Remaster)"), "Yesterday");
    }

    #[test]
    fn la_version_se_quita_pero_el_feat_no() {
        assert_eq!(
            limpiar_version_titulo("Come Together (2019 Remix)"),
            "Come Together (2019 Remix)"
        );
        assert_eq!(
            limpiar_version_titulo("Hotel California (Remaster)"),
            "Hotel California"
        );
        assert_eq!(
            limpiar_version_titulo("Something (feat. Ringo)"),
            "Something (feat. Ringo)"
        );
        assert_eq!(limpiar_version_titulo("(Live)"), "(Live)");
    }

    #[test]
    fn el_featuring_se_separa() {
        assert_eq!(
            separar_artista_principal("Drake feat. Future"),
            ("Drake".to_owned(), Some("Future".to_owned()))
        );
        assert_eq!(
            separar_artista_principal("Jay-Z ft. Kanye"),
            ("Jay-Z".to_owned(), Some("Kanye".to_owned()))
        );
        assert_eq!(
            separar_artista_principal("Radiohead"),
            ("Radiohead".to_owned(), None)
        );
        assert_eq!(
            extraer_featuring_del_titulo("Umbrella (feat. Jay-Z)"),
            ("Umbrella".to_owned(), Some("Jay-Z".to_owned()))
        );
        assert_eq!(
            extraer_featuring_del_titulo("Title [ft. Artist]"),
            ("Title".to_owned(), Some("Artist".to_owned()))
        );
        assert_eq!(normalizar_artista("Bad Bunny (feat. Drake)"), "Bad Bunny");
    }

    #[test]
    fn el_nombre_del_archivo_da_artista_titulo_y_numero() {
        let p = parsear_nombre_archivo("Artist - Title.mp3");
        assert_eq!(
            (p.artista.as_deref(), p.titulo.as_deref()),
            (Some("Artist"), Some("Title"))
        );
        let p = parsear_nombre_archivo("Artist - 01 - Title.mp3");
        assert_eq!(
            (
                p.artista.as_deref(),
                p.numero.as_deref(),
                p.titulo.as_deref()
            ),
            (Some("Artist"), Some("01"), Some("Title"))
        );
        let p = parsear_nombre_archivo("01. Title.mp3");
        assert_eq!(
            (p.numero.as_deref(), p.titulo.as_deref()),
            (Some("01"), Some("Title"))
        );
        let p = parsear_nombre_archivo("01_Title [spotdown.org].mp3");
        assert_eq!(
            (p.numero.as_deref(), p.titulo.as_deref()),
            (Some("01"), Some("Title"))
        );
        let p = parsear_nombre_archivo("2024 - Title.mp3");
        assert_eq!(
            (p.artista, p.titulo.as_deref()),
            (None, Some("2024 - Title"))
        );
        let p = parsear_nombre_archivo("Solo.flac");
        assert_eq!(p.titulo.as_deref(), Some("Solo"));
    }

    #[test]
    fn sequence_matcher_da_lo_mismo_que_difflib() {
        // Valores de `difflib.SequenceMatcher(None, a, b).ratio()` en CPython 3.12.
        let r = |a: &str, b: &str| {
            let (a, b): (Vec<char>, Vec<char>) = (a.chars().collect(), b.chars().collect());
            redondear(ratio_secuencias(&a, &b), 6)
        };
        assert_eq!(r("abcd", "bcde"), 0.75);
        assert_eq!(r("hotel california", "hotel californa"), 0.967742);
        assert_eq!(r("", ""), 1.0);
        assert_eq!(r("abc", "xyz"), 0.0);
        assert_eq!(r("private", "pirate"), 0.769231);
    }

    #[test]
    fn la_similitud_combinada_pondera_las_tres_medidas() {
        assert_eq!(similitud_combinada("Hello", "hello"), 1.0);
        assert_eq!(similitud_combinada("", "x"), 0.0);
        // La V1 da 0.7596 para este par.
        assert_eq!(
            similitud_combinada("Hotel California", "California Hotel"),
            0.7596
        );
        assert_eq!(similitud_trigrama("ab", "ab"), 1.0, "cortas: secuencial");
    }

    #[test]
    fn utiles_de_campos() {
        assert_eq!(extraer_anio_del_texto("2003-01-15"), Some(2003));
        assert_eq!(extraer_anio_del_texto("ID3v2.4: 1999"), Some(1999));
        assert_eq!(extraer_anio_del_texto("3000"), None);
        assert_eq!(limpiar_numero_pista("3/12"), Some(3));
        assert_eq!(limpiar_numero_pista("0"), None);
        assert_eq!(limpiar_numero_pista("x"), None);
        assert_eq!(
            normalizar_isrc("us-rc1-17-00001").as_deref(),
            Some("USRC11700001")
        );
        assert_eq!(normalizar_isrc("nope"), None);
        assert_eq!(redondear(0.125, 2), 0.12);
        assert_eq!(redondear(0.135, 2), 0.14);
    }

    #[test]
    fn las_variantes_se_reconocen_y_se_separan() {
        assert_eq!(detectar_tipo_variante("Song (Remix)"), Some("Remix"));
        assert_eq!(
            detectar_tipo_variante("Song (Live at Wembley)"),
            Some("Live")
        );
        assert_eq!(
            detectar_tipo_variante("Song (Acoustic Version)"),
            Some("Acoustic")
        );
        assert_eq!(detectar_tipo_variante("Song"), None);
        assert_eq!(
            parsear_variante_titulo("Song (feat. A) (Remix)"),
            ("Song (feat. A)".to_owned(), Some("Remix"))
        );
        assert_eq!(
            parsear_variante_titulo("Song (Live at Wembley)"),
            ("Song".to_owned(), Some("Live"))
        );
    }

    /// Compara cada función con lo que respondió la V1 a cada frase.
    fn diferencias_con_la_v1(frases: &[serde_json::Value]) -> Vec<String> {
        let mut fallos = Vec::new();
        for f in frases {
            let e = f["entrada"].as_str().unwrap();
            let nombre = parsear_nombre_archivo(e);
            let (base, variante) = parsear_variante_titulo(e);
            let (principal, feat) = separar_artista_principal(e);
            let (sin_feat, feat_titulo) = extraer_featuring_del_titulo(e);
            let nuestro = [
                ("slug", serde_json::json!(construir_slug(e))),
                ("para_comparacion", serde_json::json!(para_comparacion(e))),
                (
                    "normalizar_para_comparar",
                    serde_json::json!(normalizar_para_comparar(e)),
                ),
                ("normalizar_titulo", serde_json::json!(normalizar_titulo(e))),
                (
                    "limpiar_version_titulo",
                    serde_json::json!(limpiar_version_titulo(e)),
                ),
                (
                    "normalizar_artista",
                    serde_json::json!(normalizar_artista(e)),
                ),
                (
                    "separar_artista_principal",
                    serde_json::json!([principal, feat]),
                ),
                (
                    "extraer_featuring_del_titulo",
                    serde_json::json!([sin_feat, feat_titulo]),
                ),
                (
                    "nombre_archivo",
                    serde_json::json!([nombre.artista, nombre.titulo, nombre.numero]),
                ),
                ("variante", serde_json::json!([base, variante])),
                (
                    "limpiar_basura_descarga",
                    serde_json::json!(limpiar_basura_descarga(e)),
                ),
            ];
            for (campo, valor) in nuestro {
                if f[campo] != valor {
                    fallos.push(format!("{campo}({e:?}): V1 {} V2 {valor}", f[campo]));
                }
            }
        }
        fallos
    }

    /// Lo que respondió la V1 a las frases de `scripts/prototipos/texto/grabar.py`.
    #[test]
    fn cada_funcion_responde_lo_mismo_que_en_la_v1() {
        let v1: serde_json::Value =
            serde_json::from_str(include_str!("../../tests/fixtures/texto_v1.json")).unwrap();
        let mut fallos = diferencias_con_la_v1(v1["frases"].as_array().unwrap());
        for p in v1["pares"].as_array().unwrap() {
            let (a, b) = (p["a"].as_str().unwrap(), p["b"].as_str().unwrap());
            let c = similitud_combinada(a, b);
            if Some(c) != p["combinada"].as_f64() {
                fallos.push(format!(
                    "combinada({a:?}, {b:?}): V1 {} V2 {c}",
                    p["combinada"]
                ));
            }
        }
        assert!(fallos.is_empty(), "{}", fallos.join("\n"));
    }

    /// Lo mismo sobre un corpus que no entra en el repositorio: la salida de
    /// `grabar.py` con un archivo de frases, en `NS_TEXTO_CORPUS`. Solo cuenta.
    #[test]
    #[ignore = "necesita un corpus local"]
    fn el_corpus_local_responde_lo_mismo_que_en_la_v1() {
        let Ok(ruta) = std::env::var("NS_TEXTO_CORPUS") else {
            return;
        };
        let v1: Vec<serde_json::Value> =
            serde_json::from_str(&std::fs::read_to_string(ruta).unwrap()).unwrap();
        let fallos = diferencias_con_la_v1(&v1);
        let mut por_funcion = std::collections::BTreeMap::<String, usize>::new();
        for f in &fallos {
            *por_funcion
                .entry(f.split('(').next().unwrap_or_default().to_owned())
                .or_default() += 1;
        }
        assert!(
            fallos.is_empty(),
            "{} frases, diferencias por función: {por_funcion:?}",
            v1.len()
        );
    }
}
