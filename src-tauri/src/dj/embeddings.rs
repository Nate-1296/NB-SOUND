//! Los embeddings del DJ (F6.1.1): `servicios/dj_privado/embeddings.py`.
//!
//! Dos proveedores con la misma interfaz. El **determinista** funciona siempre: un
//! vector sobre los 24 ejes y los 81 conceptos de la ontología, con las mismas
//! cuentas que la V1, que no finge ser un modelo pero compara frases y pistas de
//! forma coherente. El **real** usa `all-MiniLM-L6-v2` del agregado de texto: el
//! tokenizador WordPiece de BERT sin mayúsculas, ONNX Runtime y la media de los
//! tokens. El tokenizador se escribe aquí y no con `tokenizers` de HuggingFace, que
//! ningún ADR aprueba: para BERT son unas decenas de líneas.

use std::collections::HashMap;
use std::path::Path;

use super::ontologia::{self, CONCEPTOS, EJES};
use crate::agregados::{self, IdAgregado};
use crate::error::{NsError, NsResult};

/// Lo que se sabe de una pista para su embedding, con los nombres de la V1.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct RasgosPista {
    pub numericos: Vec<(&'static str, f64)>,
    pub genero: Option<String>,
    /// Etiquetas con su puntuación.
    pub etiquetas: Vec<(String, f64)>,
    pub titulo: String,
    pub artista: String,
    pub album: String,
}

pub trait Proveedor {
    fn modelo(&self) -> &str;
    fn dimension(&self) -> usize;
    fn es_real(&self) -> bool;
    fn de_texto(&mut self, texto: &str) -> Vec<f64>;
    fn de_pista(&mut self, rasgos: &RasgosPista) -> Vec<f64>;
}

/// `similitud_coseno`: 0 si alguno es nulo; con longitudes distintas, la menor.
#[must_use]
pub fn coseno(a: &[f64], b: &[f64]) -> f64 {
    let n = a.len().min(b.len());
    if n == 0 {
        return 0.0;
    }
    let (mut dot, mut na, mut nb) = (0.0, 0.0, 0.0);
    for i in 0..n {
        dot += a[i] * b[i];
        na += a[i] * a[i];
        nb += b[i] * b[i];
    }
    if na == 0.0 || nb == 0.0 {
        0.0
    } else {
        dot / (na * nb).sqrt()
    }
}

/// Qué rasgo numérico empuja qué eje, en el orden de la V1.
const MAPEOS: [(&str, &str); 21] = [
    ("energy", "energy"),
    ("danceability_proxy", "danceability"),
    ("danceability_model", "danceability"),
    ("valence_proxy", "euphoria"),
    ("valence", "euphoria"),
    ("arousal_proxy", "energy"),
    ("arousal", "energy"),
    ("calmness_proxy", "calmness"),
    ("melancholy_proxy", "melancholy"),
    ("brightness", "brightness"),
    ("darkness_proxy", "darkness"),
    ("aggressiveness_proxy", "aggressiveness"),
    ("mood_aggressive", "aggressiveness"),
    ("mood_relaxed", "calmness"),
    ("mood_happy", "euphoria"),
    ("mood_sad", "melancholy"),
    ("mood_party", "club_energy"),
    ("focus_score_proxy", "focus_score"),
    ("workout_score_proxy", "workout_score"),
    ("party_score_proxy", "club_energy"),
    ("night_score_proxy", "night_score"),
];

/// `DeterministicEmbeddingProvider`.
#[derive(Debug, Default)]
pub struct Determinista;

fn eje(nombre: &str) -> Option<usize> {
    EJES.iter().position(|e| *e == nombre)
}

fn concepto_idx(nombre: &str) -> Option<usize> {
    CONCEPTOS.iter().position(|c| c.nombre == nombre)
}

impl Proveedor for Determinista {
    fn modelo(&self) -> &str {
        "dj_deterministic_v1"
    }

    fn dimension(&self) -> usize {
        EJES.len() + CONCEPTOS.len()
    }

    fn es_real(&self) -> bool {
        false
    }

    fn de_texto(&mut self, texto: &str) -> Vec<f64> {
        let mut v = vec![0.0; self.dimension()];
        let ms = ontologia::buscar(texto);
        for (e, valor) in ontologia::agregar_ejes(&ms, &[]) {
            if let Some(i) = eje(&e) {
                v[i] = valor;
            }
        }
        for m in &ms {
            if let Some(i) = concepto_idx(m.concepto.nombre) {
                v[EJES.len() + i] = m.concepto.peso;
            }
        }
        v
    }

    fn de_pista(&mut self, r: &RasgosPista) -> Vec<f64> {
        let mut v = vec![0.0; self.dimension()];
        let base = EJES.len();
        // Los rasgos de 0 a 1 se llevan a -1..1: 0,5 es neutro.
        for (rasgo, a) in MAPEOS {
            if let Some((_, x)) = r.numericos.iter().find(|(k, _)| *k == rasgo) {
                if let Some(i) = eje(a) {
                    v[i] += (x - 0.5) * 2.0;
                }
            }
        }
        if let Some(g) = r.genero.as_deref().map(str::trim).filter(|g| !g.is_empty()) {
            let g = g.to_lowercase();
            // El último concepto que declara el género, como el `dict` de la V1.
            if let Some(i) = CONCEPTOS
                .iter()
                .rposition(|c| c.generos.iter().any(|x| x.to_lowercase() == g))
            {
                v[base + i] += 1.0;
            }
        }
        for (etiqueta, puntuacion) in &r.etiquetas {
            if etiqueta.is_empty() {
                continue;
            }
            for m in ontologia::buscar(etiqueta) {
                if let Some(i) = concepto_idx(m.concepto.nombre) {
                    v[base + i] += puntuacion * m.concepto.peso;
                }
                for (e, delta) in m.concepto.ejes {
                    if let Some(i) = eje(e) {
                        v[i] += delta * puntuacion * 0.5;
                    }
                }
            }
        }
        let meta = format!("{} {} {}", r.titulo, r.artista, r.album);
        for m in ontologia::buscar(&meta) {
            if let Some(i) = concepto_idx(m.concepto.nombre) {
                v[base + i] += m.concepto.peso * 0.5;
            }
        }
        v
    }
}

// --- El tokenizador de BERT ----------------------------------------------------------------

/// WordPiece de BERT sin mayúsculas, como el `tokenizer.json` de MiniLM:
/// normalizar (limpiar, separar ideogramas, quitar acentos, minúsculas), separar
/// por espacios y puntuación, trocear cada palabra con `##`, y `[CLS] … [SEP]`.
pub struct Tokenizador {
    vocab: HashMap<String, i64>,
    cls: i64,
    sep: i64,
    unk: i64,
}

impl Tokenizador {
    /// Desde el vocabulario de `tokenizer.json` (`model.vocab`).
    ///
    /// # Errors
    ///
    /// [`NsError::ComponentUnavailable`] si falta el vocabulario o sus tokens
    /// especiales.
    pub fn desde_json(json: &serde_json::Value) -> NsResult<Self> {
        let vocab: HashMap<String, i64> = json["model"]["vocab"]
            .as_object()
            .ok_or(NsError::ComponentUnavailable)?
            .iter()
            .filter_map(|(k, v)| v.as_i64().map(|v| (k.clone(), v)))
            .collect();
        let id = |t: &str| vocab.get(t).copied().ok_or(NsError::ComponentUnavailable);
        Ok(Self {
            cls: id("[CLS]")?,
            sep: id("[SEP]")?,
            unk: id("[UNK]")?,
            vocab,
        })
    }

    fn normalizar(texto: &str) -> String {
        let mut s = String::with_capacity(texto.len());
        for c in texto.chars() {
            if c == '\0' || c == '\u{fffd}' || (c.is_control() && !c.is_whitespace()) {
                continue;
            }
            if es_ideograma(c) {
                s.push(' ');
                s.push(c);
                s.push(' ');
            } else if c.is_whitespace() {
                s.push(' ');
            } else {
                s.push(c);
            }
        }
        crate::catalogo::texto::eliminar_acentos(&s).to_lowercase()
    }

    fn palabras(texto: &str) -> Vec<String> {
        let mut out = Vec::new();
        for trozo in texto.split_whitespace() {
            let mut actual = String::new();
            for c in trozo.chars() {
                if es_puntuacion(c) {
                    if !actual.is_empty() {
                        out.push(std::mem::take(&mut actual));
                    }
                    out.push(c.to_string());
                } else {
                    actual.push(c);
                }
            }
            if !actual.is_empty() {
                out.push(actual);
            }
        }
        out
    }

    fn trocear(&self, palabra: &str, out: &mut Vec<i64>) {
        let chars: Vec<char> = palabra.chars().collect();
        if chars.len() > 100 {
            out.push(self.unk);
            return;
        }
        let mut piezas = Vec::new();
        let mut inicio = 0;
        while inicio < chars.len() {
            let mut fin = chars.len();
            let mut encontrada = None;
            while fin > inicio {
                let mut s: String = chars[inicio..fin].iter().collect();
                if inicio > 0 {
                    s.insert_str(0, "##");
                }
                if let Some(id) = self.vocab.get(&s) {
                    encontrada = Some(*id);
                    break;
                }
                fin -= 1;
            }
            let Some(id) = encontrada else {
                out.push(self.unk);
                return;
            };
            piezas.push(id);
            inicio = fin;
        }
        out.extend(piezas);
    }

    /// Los ids de un texto, con `[CLS]` y `[SEP]`, como mucho `maximo`.
    #[must_use]
    pub fn codificar(&self, texto: &str, maximo: usize) -> Vec<i64> {
        let mut ids = vec![self.cls];
        for p in Self::palabras(&Self::normalizar(texto)) {
            self.trocear(&p, &mut ids);
        }
        ids.truncate(maximo.saturating_sub(1).max(1));
        ids.push(self.sep);
        ids
    }
}

fn es_ideograma(c: char) -> bool {
    matches!(c as u32,
        0x4E00..=0x9FFF | 0x3400..=0x4DBF | 0x20000..=0x2A6DF | 0x2A700..=0x2B73F
        | 0x2B740..=0x2B81F | 0x2B820..=0x2CEAF | 0xF900..=0xFAFF | 0x2F800..=0x2FA1F)
}

/// La puntuación de BERT: los ASCII que no son letra ni dígito, y los de las
/// categorías de puntuación de Unicode.
fn es_puntuacion(c: char) -> bool {
    let n = c as u32;
    (33..=47).contains(&n)
        || (58..=64).contains(&n)
        || (91..=96).contains(&n)
        || (123..=126).contains(&n)
        || (c.is_ascii_punctuation())
        || (!c.is_alphanumeric()
            && !c.is_whitespace()
            && !c.is_control()
            && n > 127
            && !es_marca(c))
}

fn es_marca(c: char) -> bool {
    unicode_normalization::char::is_combining_mark(c)
}

// --- El proveedor real -----------------------------------------------------------------------

/// `OnnxEmbeddingProvider` con el agregado de texto: `model.onnx` y
/// `tokenizer.json`.
pub struct Real {
    sesion: ort::session::Session,
    tokenizador: Tokenizador,
    con_tipos: bool,
    dimension: usize,
}

/// Como mucho 256 tokens, como la V1.
const MAX_TOKENS: usize = 256;

impl Real {
    /// # Errors
    ///
    /// [`NsError::ComponentUnavailable`] si falta el modelo, su tokenizador u ONNX
    /// Runtime.
    pub fn abrir(dir: &Path) -> NsResult<Self> {
        let json: serde_json::Value = serde_json::from_slice(
            &std::fs::read(dir.join("tokenizer.json"))
                .map_err(|_| NsError::ComponentUnavailable)?,
        )
        .map_err(|_| NsError::ComponentUnavailable)?;
        let tokenizador = Tokenizador::desde_json(&json)?;
        let sesion = ort::session::Session::builder(crate::onnx::entorno()?)
            .map_err(|_| NsError::ComponentUnavailable)?
            .with_intra_threads(1)
            .map_err(|_| NsError::ComponentUnavailable)?
            .commit_from_file(dir.join("model.onnx"))
            .map_err(|_| NsError::ComponentUnavailable)?;
        let con_tipos = sesion.inputs().iter().any(|i| i.name() == "token_type_ids");
        let mut r = Self {
            sesion,
            tokenizador,
            con_tipos,
            dimension: 384,
        };
        r.dimension = r.incrustar("test")?.len();
        Ok(r)
    }

    fn incrustar(&mut self, texto: &str) -> NsResult<Vec<f64>> {
        let ids = self.tokenizador.codificar(texto, MAX_TOKENS);
        let n = ids.len();
        let tensor = |v: Vec<i64>| {
            ort::value::Tensor::from_array(([1usize, n], v)).map_err(|_| NsError::Internal)
        };
        let mut entradas: Vec<(
            std::borrow::Cow<'_, str>,
            ort::session::SessionInputValue<'_>,
        )> = vec![
            ("input_ids".into(), tensor(ids)?.into()),
            ("attention_mask".into(), tensor(vec![1; n])?.into()),
        ];
        if self.con_tipos {
            entradas.push(("token_type_ids".into(), tensor(vec![0; n])?.into()));
        }
        let salidas = self.sesion.run(entradas).map_err(|_| NsError::Internal)?;
        let (forma, datos) = salidas[0]
            .try_extract_tensor::<f32>()
            .map_err(|_| NsError::Internal)?;
        let ocultas = forma.last().copied().unwrap_or(0).max(0) as usize;
        if ocultas == 0 {
            return Err(NsError::Internal);
        }
        // Media sobre los tokens (todos cuentan: la máscara es de unos).
        let tokens = datos.len() / ocultas;
        Ok((0..ocultas)
            .map(|h| {
                (0..tokens)
                    .map(|t| f64::from(datos[t * ocultas + h]))
                    .sum::<f64>()
                    / tokens.max(1) as f64
            })
            .collect())
    }
}

impl Proveedor for Real {
    fn modelo(&self) -> &str {
        "dj_onnx:minilm"
    }

    fn dimension(&self) -> usize {
        self.dimension
    }

    fn es_real(&self) -> bool {
        true
    }

    fn de_texto(&mut self, texto: &str) -> Vec<f64> {
        if texto.is_empty() {
            return vec![0.0; self.dimension];
        }
        self.incrustar(texto)
            .unwrap_or_else(|_| vec![0.0; self.dimension])
    }

    fn de_pista(&mut self, r: &RasgosPista) -> Vec<f64> {
        let mut partes: Vec<&str> = [r.titulo.as_str(), r.artista.as_str(), r.album.as_str()]
            .into_iter()
            .chain(r.genero.as_deref())
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .collect();
        partes.extend(r.etiquetas.iter().map(|(e, _)| e.as_str()));
        self.de_texto(&partes.join(". "))
    }
}

/// `obtener_provider`: el real si el agregado de texto está instalado y abre; si
/// no, el determinista.
#[must_use]
pub fn proveedor(rutas: &crate::paths::Rutas) -> Box<dyn Proveedor + Send> {
    if agregados::instalado(rutas, IdAgregado::TextoDj).is_some() {
        match Real::abrir(&agregados::carpeta(rutas, IdAgregado::TextoDj)) {
            Ok(r) => return Box::new(r),
            Err(e) => tracing::warn!(codigo = e.code(), "el modelo de texto del DJ no abrió"),
        }
    }
    Box::new(Determinista)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dorada() -> serde_json::Value {
        serde_json::from_str::<serde_json::Value>(include_str!("doradas_intencion.json")).unwrap()
            ["embeddings"]
            .clone()
    }

    fn igual(a: &[f64], b: &serde_json::Value) {
        let b: Vec<f64> = b
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_f64().unwrap())
            .collect();
        assert_eq!(a.len(), b.len());
        for (i, (x, y)) in a.iter().zip(&b).enumerate() {
            assert!((x - y).abs() < 1e-9, "dimensión {i}: {x} frente a {y}");
        }
    }

    #[test]
    fn el_determinista_da_los_mismos_vectores_que_la_v1() {
        let d = dorada();
        let mut p = Determinista;
        assert_eq!(p.dimension() as u64, d["dim"].as_u64().unwrap());
        igual(&p.de_texto("voces femeninas cinematográfico"), &d["texto"]);
        let r = RasgosPista {
            numericos: vec![("energy", 0.8), ("valence_proxy", 0.3), ("mood_party", 0.9)],
            genero: Some("Rock".into()),
            etiquetas: vec![("electronic".into(), 0.6), ("chill".into(), 0.4)],
            titulo: "Nocturne (Instrumental)".into(),
            ..RasgosPista::default()
        };
        igual(&p.de_pista(&r), &d["pista"]);
    }

    #[test]
    fn el_coseno_es_el_de_siempre() {
        assert!((coseno(&[1.0, 0.0], &[1.0, 0.0]) - 1.0).abs() < 1e-12);
        assert_eq!(coseno(&[1.0, 0.0], &[0.0, 0.0]), 0.0);
        assert_eq!(coseno(&[], &[1.0]), 0.0);
        assert!(
            (coseno(&[1.0, 2.0, 9.0], &[1.0, 2.0]) - 1.0).abs() < 1e-12,
            "la menor longitud"
        );
    }

    #[test]
    fn el_tokenizador_trocea_como_bert() {
        let vocab: serde_json::Map<String, serde_json::Value> = [
            "[PAD]", "[UNK]", "[CLS]", "[SEP]", "musica", "para", "corr", "##er", ",", "!", "hola",
        ]
        .iter()
        .enumerate()
        .map(|(i, t)| ((*t).to_owned(), serde_json::Value::from(i)))
        .collect();
        let t = Tokenizador::desde_json(&serde_json::json!({"model": {"vocab": vocab}})).unwrap();
        // Minúsculas, sin acentos, la coma suelta, "correr" en dos piezas y lo
        // desconocido como [UNK].
        assert_eq!(
            t.codificar("Música para CORRER, xyz!", 256),
            [2, 4, 5, 6, 7, 8, 1, 9, 3]
        );
        assert_eq!(
            t.codificar("hola hola hola hola", 4),
            [2, 10, 10, 3],
            "se corta con [SEP]"
        );
    }
}
