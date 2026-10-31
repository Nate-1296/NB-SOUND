//! La ontología musical del DJ Privado (F6.1.1): `servicios/dj_privado/ontologia.py`.
//!
//! El vocabulario perceptual del DJ: conceptos (no solo géneros) con sus alias en
//! español e inglés, cuánto empuja cada uno los 24 ejes perceptuales, su peso y con
//! qué otros choca o se refuerza. Es determinista y sin modelos: detecta conceptos
//! en una frase y los traduce a ejes.
//!
//! Los datos están en `ontologia_datos.rs`, transcritos de la V1 en su orden; aquí,
//! la búsqueda y la agregación, que deben dar lo mismo que la V1 (lo comprueban las
//! respuestas doradas de `intencion.rs`).

use std::collections::BTreeMap;

pub use super::ontologia_datos::{CONCEPTOS, EJES};
use crate::catalogo::texto::eliminar_acentos;

/// El papel de un concepto en la frase.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Rol {
    /// Género o ambiente general.
    Contexto,
    /// Lo que debe destacar ("voces femeninas").
    Prioridad,
    /// Un ajuste ("muy", "un poco").
    Modificador,
    /// Lo que no se quiere ("sin EDM agresivo"): sus ejes ya son negativos.
    Exclusion,
}

/// Un concepto perceptual.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Concepto {
    pub nombre: &'static str,
    pub alias: &'static [&'static str],
    /// Cuánto empuja cada eje: un voto, no un valor absoluto.
    pub ejes: &'static [(&'static str, f64)],
    /// `perceptual_weight`.
    pub peso: f64,
    pub rol: Rol,
    pub generos: &'static [&'static str],
    pub contradice: &'static [&'static str],
    pub refuerza: &'static [&'static str],
}

/// Un mapa con el orden de inserción, como un `dict` de Python: el orden decide la
/// suma de coma flotante y, con ella, la paridad con la V1.
pub type Mapa = Vec<(String, f64)>;

pub fn sumar(m: &mut Mapa, clave: &str, valor: f64) {
    match m.iter_mut().find(|(k, _)| k == clave) {
        Some((_, v)) => *v += valor,
        None => m.push((clave.to_owned(), valor)),
    }
}

/// Un mapa ordenado por clave, para guardar y comparar.
#[must_use]
pub fn ordenado(m: &Mapa) -> BTreeMap<String, f64> {
    m.iter().cloned().collect()
}

/// `\w` de Python: letras, dígitos y el guion bajo.
fn es_palabra(c: char) -> bool {
    c.is_alphanumeric() || c == '_'
}

/// `_normalizar_para_busqueda`: minúsculas, sin diacríticos, lo que no es palabra
/// ni espacio a espacios, y los espacios juntos.
#[must_use]
pub fn normalizar(texto: &str) -> String {
    let sin = eliminar_acentos(texto).to_lowercase();
    let limpio: String = sin
        .chars()
        .map(|c| {
            if es_palabra(c) || c.is_whitespace() {
                c
            } else {
                ' '
            }
        })
        .collect();
    limpio.split_whitespace().collect::<Vec<_>>().join(" ")
}

/// Una coincidencia en la frase, con su posición en el texto normalizado (en
/// caracteres, como Python).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Coincidencia {
    pub concepto: &'static Concepto,
    pub inicio: usize,
    pub fin: usize,
}

/// Los alias normalizados, de más largo a más corto (orden estable): "voces
/// femeninas" antes que "voces".
fn alias_ordenados() -> &'static [(Vec<char>, &'static Concepto)] {
    static ALIAS: std::sync::OnceLock<Vec<(Vec<char>, &'static Concepto)>> =
        std::sync::OnceLock::new();
    ALIAS.get_or_init(|| {
        let mut v: Vec<(Vec<char>, &'static Concepto)> = CONCEPTOS
            .iter()
            .flat_map(|c| {
                c.alias.iter().filter_map(move |a| {
                    let n: Vec<char> = normalizar(a).chars().collect();
                    (!n.is_empty()).then_some((n, c))
                })
            })
            .collect();
        v.sort_by_key(|a| std::cmp::Reverse(a.0.len()));
        v
    })
}

fn buscar_desde(texto: &[char], patron: &[char], desde: usize) -> Option<usize> {
    if patron.len() > texto.len() {
        return None;
    }
    (desde..=texto.len() - patron.len()).find(|&i| &texto[i..i + patron.len()] == patron)
}

/// `buscar_conceptos`: voraz por longitud, marcando lo consumido para no contar
/// "voces" dentro de "voces femeninas", con frontera de palabra ("rocky" no es
/// "rock"). En orden de aparición.
#[must_use]
pub fn buscar(texto: &str) -> Vec<Coincidencia> {
    let t: Vec<char> = normalizar(texto).chars().collect();
    if t.is_empty() {
        return Vec::new();
    }
    let mut consumido = vec![false; t.len()];
    let mut encontrados = Vec::new();
    for (alias, concepto) in alias_ordenados() {
        let mut desde = 0;
        while desde + alias.len() <= t.len() {
            let Some(pos) = buscar_desde(&t, alias, desde) else {
                break;
            };
            let fin = pos + alias.len();
            let antes = pos == 0 || !t[pos - 1].is_alphanumeric();
            let despues = fin == t.len() || !t[fin].is_alphanumeric();
            if antes && despues && !consumido[pos..fin].iter().any(|c| *c) {
                consumido[pos..fin].iter_mut().for_each(|c| *c = true);
                encontrados.push(Coincidencia {
                    concepto,
                    inicio: pos,
                    fin,
                });
            }
            desde = pos + 1;
        }
    }
    encontrados.sort_by_key(|m| m.inicio);
    encontrados
}

#[must_use]
pub fn concepto(nombre: &str) -> Option<&'static Concepto> {
    CONCEPTOS.iter().find(|c| c.nombre == nombre)
}

/// `agregar_ejes`: los votos se suman (no se promedian), con el factor de los
/// amplificadores por posición. Sin recortar: el planificador normaliza.
#[must_use]
pub fn agregar_ejes(coincidencias: &[Coincidencia], factores: &[(usize, f64)]) -> Mapa {
    let mut acumulado = Mapa::new();
    for m in coincidencias {
        let factor = factores
            .iter()
            .find(|(i, _)| *i == m.inicio)
            .map_or(1.0, |(_, f)| *f);
        for (eje, delta) in m.concepto.ejes {
            sumar(&mut acumulado, eje, delta * m.concepto.peso * factor);
        }
    }
    acumulado
}

/// `aplicar_boosts`: si un concepto refuerza a otro también presente, los ejes que
/// comparten suben un 25 %, una vez por pareja detectada.
#[must_use]
pub fn aplicar_refuerzos(coincidencias: &[Coincidencia], ejes: &Mapa) -> Mapa {
    let mut r = ejes.clone();
    for m in coincidencias {
        for objetivo in m.concepto.refuerza {
            if !coincidencias.iter().any(|x| x.concepto.nombre == *objetivo) {
                continue;
            }
            let Some(otro) = concepto(objetivo) else {
                continue;
            };
            for (eje, _) in m.concepto.ejes {
                if otro.ejes.iter().any(|(e, _)| e == eje) {
                    if let Some((_, v)) = r.iter_mut().find(|(k, _)| k == eje) {
                        *v *= 1.25;
                    }
                }
            }
        }
    }
    r
}

/// `detectar_contradicciones`: cada pareja que choca, una vez y ordenada.
#[must_use]
pub fn contradicciones(coincidencias: &[Coincidencia]) -> Vec<(String, String)> {
    let mut pares: Vec<(String, String)> = Vec::new();
    for m in coincidencias {
        for opuesto in m.concepto.contradice {
            if coincidencias.iter().any(|x| x.concepto.nombre == *opuesto) {
                let (a, b) = if m.concepto.nombre <= *opuesto {
                    (m.concepto.nombre, *opuesto)
                } else {
                    (*opuesto, m.concepto.nombre)
                };
                if !pares.iter().any(|(x, y)| x == a && y == b) {
                    pares.push((a.to_owned(), b.to_owned()));
                }
            }
        }
    }
    pares
}

/// `generos_sugeridos`: el peso de cada concepto repartido entre sus géneros.
#[must_use]
pub fn generos(coincidencias: &[Coincidencia]) -> Mapa {
    let mut pesos = Mapa::new();
    for m in coincidencias {
        let c = m.concepto;
        if c.generos.is_empty() || c.rol == Rol::Exclusion {
            continue;
        }
        let parte = c.peso / c.generos.len().max(1) as f64;
        for g in c.generos {
            sumar(&mut pesos, g, parte);
        }
    }
    pesos
}

/// `estilo_transicion_sugerido`.
#[must_use]
pub fn estilo_transicion(coincidencias: &[Coincidencia]) -> Mapa {
    let mut pesos = Mapa::new();
    for m in coincidencias {
        match m.concepto.nombre {
            "transiciones_suaves" => sumar(&mut pesos, "smooth", 1.0),
            "transiciones_agresivas" => sumar(&mut pesos, "aggressive", 1.0),
            "transicion_progresiva" => {
                sumar(&mut pesos, "energetic", 0.6);
                sumar(&mut pesos, "smooth", 0.3);
            }
            "cinematografico" => sumar(&mut pesos, "cinematic", 0.7),
            "clasica" => {
                sumar(&mut pesos, "harmonic", 0.5);
                sumar(&mut pesos, "smooth", 0.3);
            }
            _ => {}
        }
    }
    pesos
}

/// `curva_energia_sugerida`, en el orden de prioridad de la V1.
#[must_use]
pub fn curva_energia(coincidencias: &[Coincidencia]) -> Option<&'static str> {
    let hay = |nombres: &[&str]| {
        coincidencias
            .iter()
            .any(|m| nombres.contains(&m.concepto.nombre))
    };
    if hay(&[
        "transicion_progresiva",
        "entrenar",
        "emocionante",
        "epico",
        "dramatico",
    ]) {
        return Some("progressive");
    }
    if hay(&["club_party"]) {
        return Some("peak");
    }
    if hay(&[
        "concentrarse",
        "tranquilo",
        "ambient",
        "relajante",
        "atmosferico",
    ]) {
        return Some("stable");
    }
    if hay(&[
        "nocturno",
        "triste",
        "melancolico_profundo",
        "nostalgico",
        "sentimental",
    ]) {
        return Some("descending");
    }
    if hay(&["cinematografico", "narrativo"]) {
        return Some("wave");
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn la_tabla_es_la_de_la_v1() {
        assert_eq!((CONCEPTOS.len(), EJES.len()), (81, 24));
        let mut nombres: Vec<&str> = CONCEPTOS.iter().map(|c| c.nombre).collect();
        nombres.sort_unstable();
        nombres.dedup();
        assert_eq!(nombres.len(), CONCEPTOS.len(), "nombres únicos");
        let mut muertas = Vec::new();
        for c in CONCEPTOS {
            for (eje, _) in c.ejes {
                assert!(
                    EJES.contains(eje),
                    "{} usa un eje que no existe: {eje}",
                    c.nombre
                );
            }
            for otro in c.contradice.iter().chain(c.refuerza) {
                if concepto(otro).is_none() {
                    muertas.push((c.nombre, *otro));
                }
            }
        }
        // Cinco contradicciones de la V1 citan conceptos que no existen (ejes o un
        // nombre mal escrito) y nunca se disparan. Se conservan: corregirlas
        // cambiaría las sesiones respecto de la V1. Esta lista impide que aparezcan
        // otras sin decidirlo.
        assert_eq!(
            muertas,
            [
                ("edm_agresivo", "calmness"),
                ("edm_agresivo", "soft"),
                ("metal", "calmness"),
                ("agresivo", "calmness"),
                ("suave", "intenso"),
            ]
        );
    }

    #[test]
    fn la_busqueda_da_las_mismas_coincidencias_que_la_v1() {
        // Salidas de `buscar_conceptos` de la V1 (generadas con su módulo).
        type Esperado = &'static [(&'static str, usize, usize)];
        let casos: [(&str, Esperado); 3] = [
            (
                "voces femeninas cinematográfico",
                &[("voces_femeninas", 0, 15), ("cinematografico", 16, 31)],
            ),
            (
                "algo para concentrarme sin EDM agresivo",
                &[("concentrarse", 5, 22), ("sin_edm_agresivo", 23, 39)],
            ),
            ("rock pero clásico", &[("rock", 0, 4), ("clasica", 10, 17)]),
        ];
        for (texto, esperado) in casos {
            let r: Vec<(&str, usize, usize)> = buscar(texto)
                .iter()
                .map(|m| (m.concepto.nombre, m.inicio, m.fin))
                .collect();
            assert_eq!(r, esperado, "{texto}");
        }
        assert!(buscar("rocky balboa")
            .iter()
            .all(|m| m.concepto.nombre != "rock"));
    }
}
