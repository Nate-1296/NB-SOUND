//! La intención del DJ (F6.1.1): `servicios/dj_privado/intencion.py`.
//!
//! La traducción **determinista** de lo que pide el usuario a controles que el
//! planificador consume: empujes en los ejes, focos, exclusiones, géneros, curva de
//! energía y estilo de transición. Sin modelos de lenguaje: negaciones por ventana
//! de palabras, amplificadores ("muy", "un poco") y la prioridad de la ontología
//! para lo contradictorio.
//!
//! Se guarda en `dj_sesiones.intencion` con las claves y el formato JSON de la V1
//! (`IntentMusical.to_dict`), para que las sesiones que trajo la V1 se sigan
//! leyendo y las nuevas se guarden igual. Las notas y el resumen son las frases de
//! la V1, tal cual, porque forman parte de ese registro.

use serde::{Deserialize, Serialize};

use super::ontologia::{self, Coincidencia, Mapa, Rol};

const NEGADORES: [&str; 12] = [
    "sin",
    "nada de",
    "no",
    "no quiero",
    "no me gusta",
    "menos",
    "sin nada de",
    "evita",
    "evitar",
    "without",
    "no ",
    "skip",
];
/// Lo que corta el alcance de una negación: "no quiero pop pero sí rock".
const RUPTORES: [&str; 8] = ["pero", "but", "aunque", "y", "and", "con", "with", "que"];
const FACTOR_FUERTE: f64 = 1.6;
const FACTOR_DEBIL: f64 = 0.55;

/// `IntentMusical`, con sus claves de la V1.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Intencion {
    pub prompt: String,
    #[serde(with = "ontologia::objeto")]
    pub axes: Mapa,
    pub focos: Vec<String>,
    pub exclusiones: Vec<String>,
    #[serde(with = "ontologia::objeto")]
    pub generos: Mapa,
    pub generos_excluidos: Vec<String>,
    pub curva_energia: String,
    #[serde(with = "ontologia::objeto")]
    pub estilo_transicion: Mapa,
    pub contradicciones: Vec<(String, String)>,
    pub vacio: bool,
    pub notas: Vec<String>,
    pub resumen: String,
    pub duracion_minutos: u32,
    pub motor_version: String,
}

impl Default for Intencion {
    fn default() -> Self {
        Self {
            prompt: String::new(),
            axes: Mapa::new(),
            focos: Vec::new(),
            exclusiones: Vec::new(),
            generos: Mapa::new(),
            generos_excluidos: Vec::new(),
            curva_energia: "stable".to_owned(),
            estilo_transicion: Mapa::new(),
            contradicciones: Vec::new(),
            vacio: false,
            notas: Vec::new(),
            resumen: String::new(),
            duracion_minutos: 60,
            motor_version: "dj_intent_v1".to_owned(),
        }
    }
}

fn es_palabra(c: char) -> bool {
    c.is_alphanumeric() || c == '_'
}

/// `re.search(r"\bruptor\b", texto)`.
fn contiene_palabra(texto: &[char], palabra: &str) -> bool {
    let p: Vec<char> = palabra.chars().collect();
    if p.len() > texto.len() {
        return false;
    }
    (0..=texto.len() - p.len()).any(|i| {
        texto[i..i + p.len()] == p[..]
            && (i == 0 || !es_palabra(texto[i - 1]))
            && (i + p.len() == texto.len() || !es_palabra(texto[i + p.len()]))
    })
}

/// `_esta_negado`: un negador en las últimas cuatro palabras, sin un ruptor entre
/// él y el concepto.
fn esta_negado(segmento: &str) -> bool {
    let tokens: Vec<&str> = segmento.split_whitespace().collect();
    if tokens.is_empty() {
        return false;
    }
    let ventana: Vec<char> = tokens[tokens.len().saturating_sub(4)..]
        .join(" ")
        .chars()
        .collect();
    let mut negador: Option<usize> = None;
    for neg in NEGADORES {
        let n: Vec<char> = neg.chars().collect();
        if n.len() > ventana.len() {
            continue;
        }
        if let Some(idx) = (0..=ventana.len() - n.len()).find(|&i| ventana[i..i + n.len()] == n[..])
        {
            if negador.is_none_or(|actual| idx > actual) {
                negador = Some(idx);
            }
        }
    }
    let Some(idx) = negador else {
        return false;
    };
    let resto = &ventana[idx + 1..];
    !RUPTORES.iter().any(|r| contiene_palabra(resto, r))
}

/// `_resolver_contradicciones`: gana el de más peso; en empate, el mencionado más
/// tarde.
fn resolver(positivos: Vec<Coincidencia>, pares: &[(String, String)]) -> Vec<Coincidencia> {
    let mut vivos = positivos;
    let mut pendientes: Vec<(String, String)> = pares.to_vec();
    let mut cambios = true;
    while cambios && !pendientes.is_empty() {
        cambios = false;
        for par in pendientes.clone() {
            let a = vivos.iter().position(|m| m.concepto.nombre == par.0);
            let b = vivos.iter().position(|m| m.concepto.nombre == par.1);
            let (Some(ia), Some(ib)) = (a, b) else {
                pendientes.retain(|p| *p != par);
                continue;
            };
            let (ma, mb) = (vivos[ia], vivos[ib]);
            // Gana el de más peso; en empate, el mencionado más tarde.
            let pierde_a = mb.concepto.peso > ma.concepto.peso
                || (ma.concepto.peso == mb.concepto.peso && ma.inicio < mb.inicio);
            let perdedor = if pierde_a { ia } else { ib };
            vivos.remove(perdedor);
            pendientes.retain(|p| *p != par);
            cambios = true;
        }
    }
    vivos
}

fn resumen(positivos: &[Coincidencia], negados: &[Coincidencia], curva: &str) -> String {
    if positivos.is_empty() && negados.is_empty() {
        return "Sesion general.".to_owned();
    }
    let nombres = |v: &[Coincidencia]| -> Vec<String> {
        v.iter()
            .map(|m| m.concepto.nombre.replace('_', " "))
            .collect()
    };
    let mut partes = Vec::new();
    if !positivos.is_empty() {
        partes.push(format!(
            "Voy a priorizar: {}",
            nombres(positivos).join(", ")
        ));
    }
    if !negados.is_empty() {
        partes.push(format!("Evitare: {}", nombres(negados).join(", ")));
    }
    let etiqueta = match curva {
        "progressive" => Some("subida progresiva"),
        "wave" => Some("energia ondulante"),
        "descending" => Some("energia descendente"),
        "peak" => Some("pico de energia"),
        _ => None,
    };
    if let Some(e) = etiqueta {
        partes.push(format!("Curva: {e}"));
    }
    format!("{}.", partes.join(". "))
}

/// `parsear_intent`.
#[must_use]
pub fn interpretar(prompt: &str, duracion_minutos: u32) -> Intencion {
    let limpio = prompt.trim();
    if limpio.is_empty() {
        return Intencion {
            vacio: true,
            duracion_minutos,
            resumen: "Sesion general sin intencion especifica.".to_owned(),
            notas: vec!["No ingresaste una indicacion; usare seleccion general.".to_owned()],
            ..Intencion::default()
        };
    }
    let texto: Vec<char> = ontologia::normalizar(limpio).chars().collect();
    let coincidencias = ontologia::buscar(limpio);
    if coincidencias.is_empty() {
        return Intencion {
            prompt: limpio.to_owned(),
            vacio: true,
            duracion_minutos,
            resumen: "No reconoci conceptos musicales claros. Hare una seleccion general."
                .to_owned(),
            notas: vec!["Prueba con expresiones como 'algo para concentrarme', 'bajos fuertes', 'voces femeninas', 'cinematografico', 'sin EDM agresivo', 'subida progresiva para entrenar'.".to_owned()],
            ..Intencion::default()
        };
    }

    let (mut positivos, mut negados) = (Vec::new(), Vec::new());
    let mut factores: Vec<(usize, f64)> = Vec::new();
    let mut amplificador: Option<f64> = None;
    let mut fin_anterior = 0;
    for m in coincidencias {
        let segmento: String = texto[fin_anterior.min(m.inicio)..m.inicio].iter().collect();
        match m.concepto.nombre {
            "modifier_mucho" => {
                amplificador = Some(FACTOR_FUERTE);
                fin_anterior = m.fin;
                continue;
            }
            "modifier_poco" => {
                amplificador = Some(FACTOR_DEBIL);
                fin_anterior = m.fin;
                continue;
            }
            _ => {}
        }
        if let Some(f) = amplificador.take() {
            if segmento.trim().chars().count() <= 12 {
                factores.push((m.inicio, f));
            }
        }
        if m.concepto.rol == Rol::Exclusion || !esta_negado(&segmento) {
            positivos.push(m);
        } else {
            negados.push(m);
        }
        fin_anterior = m.fin;
    }

    let pares = ontologia::contradicciones(&positivos);
    if !pares.is_empty() {
        positivos = resolver(positivos, &pares);
    }
    let mut ejes: Mapa = ontologia::agregar_ejes(&positivos, &factores);
    for (eje, v) in ontologia::agregar_ejes(&negados, &factores) {
        ontologia::sumar(&mut ejes, &eje, -v);
    }
    let ejes = ontologia::aplicar_refuerzos(&positivos, &ejes);

    let focos = positivos
        .iter()
        .filter(|m| m.concepto.rol == Rol::Prioridad)
        .map(|m| m.concepto.nombre.to_owned())
        .collect();
    let mut exclusiones: Vec<String> = Vec::new();
    for m in negados.iter().chain(
        positivos
            .iter()
            .filter(|m| m.concepto.rol == Rol::Exclusion),
    ) {
        if !exclusiones.iter().any(|e| e == m.concepto.nombre) {
            exclusiones.push(m.concepto.nombre.to_owned());
        }
    }
    let mut excluidos: Vec<String> = Vec::new();
    for m in &negados {
        for g in m.concepto.generos {
            if !excluidos.iter().any(|e| e == g) {
                excluidos.push((*g).to_owned());
            }
        }
    }
    let curva = ontologia::curva_energia(&positivos).unwrap_or("stable");
    let mut notas = Vec::new();
    if !pares.is_empty() {
        notas.push(format!(
            "Detecte conceptos contradictorios; aplique la prioridad mas fuerte: {}",
            pares
                .iter()
                .map(|(a, b)| format!("{a} vs {b}"))
                .collect::<Vec<_>>()
                .join(", ")
        ));
    }
    if !negados.is_empty() {
        notas.push(format!(
            "Evitare: {}",
            negados
                .iter()
                .map(|m| m.concepto.nombre)
                .collect::<Vec<_>>()
                .join(", ")
        ));
    }
    Intencion {
        prompt: limpio.to_owned(),
        axes: ejes,
        focos,
        exclusiones,
        generos: ontologia::generos(&positivos),
        generos_excluidos: excluidos,
        curva_energia: curva.to_owned(),
        estilo_transicion: ontologia::estilo_transicion(&positivos),
        contradicciones: pares,
        vacio: false,
        notas,
        resumen: resumen(&positivos, &negados, curva),
        duracion_minutos,
        ..Intencion::default()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Las salidas de `parsear_intent` de la V1 para estas frases, generadas con su
    /// módulo (`to_dict`).
    const DORADAS: &str = include_str!("doradas_intencion.json");

    #[test]
    fn cada_frase_da_la_misma_intencion_que_la_v1() {
        let doradas: serde_json::Value = serde_json::from_str(DORADAS).unwrap();
        let casos = doradas["intenciones"].as_object().unwrap();
        assert!(casos.len() >= 14);
        for (frase, esperada) in casos {
            let esperada: Intencion = serde_json::from_value(esperada.clone()).unwrap();
            let propia = interpretar(frase, 60);
            assert_eq!(propia.axes.len(), esperada.axes.len(), "{frase}: ejes");
            for (eje, v) in &esperada.axes {
                let p = ontologia::valor(&propia.axes, eje).unwrap_or(f64::NAN);
                assert!((p - v).abs() < 1e-9, "{frase}: {eje} {p} frente a {v}");
            }
            for (m, (k, v)) in [
                (&propia.generos, &esperada.generos),
                (&propia.estilo_transicion, &esperada.estilo_transicion),
            ]
            .iter()
            .flat_map(|(p, e)| e.iter().map(move |kv| (*p, kv)))
            {
                assert!(
                    (ontologia::valor(m, k).unwrap_or(f64::NAN) - v).abs() < 1e-9,
                    "{frase}: {k}"
                );
            }
            assert_eq!(
                (
                    &propia.focos,
                    &propia.exclusiones,
                    &propia.generos_excluidos,
                    &propia.curva_energia,
                    &propia.contradicciones,
                    propia.vacio,
                    &propia.notas,
                    &propia.resumen,
                ),
                (
                    &esperada.focos,
                    &esperada.exclusiones,
                    &esperada.generos_excluidos,
                    &esperada.curva_energia,
                    &esperada.contradicciones,
                    esperada.vacio,
                    &esperada.notas,
                    &esperada.resumen,
                ),
                "{frase}"
            );
        }
    }

    #[test]
    fn el_json_es_el_de_la_v1_y_se_lee_de_vuelta() {
        let i = interpretar("muy energético para entrenar", 45);
        let json = serde_json::to_value(&i).unwrap();
        for clave in [
            "prompt",
            "axes",
            "focos",
            "exclusiones",
            "generos",
            "generos_excluidos",
            "curva_energia",
            "estilo_transicion",
            "contradicciones",
            "vacio",
            "notas",
            "resumen",
            "duracion_minutos",
            "motor_version",
        ] {
            assert!(json.get(clave).is_some(), "{clave}");
        }
        // Desde el texto, que conserva el orden de los mapas; `Value` los ordena.
        let vuelta: Intencion = serde_json::from_str(&serde_json::to_string(&i).unwrap()).unwrap();
        assert_eq!(vuelta, i);
        // Una de la V1 con claves que falten se lee con sus valores de fábrica.
        let vieja: Intencion = serde_json::from_str(r#"{"prompt": "x", "vacio": true}"#).unwrap();
        assert_eq!(
            (vieja.curva_energia.as_str(), vieja.duracion_minutos),
            ("stable", 60)
        );
    }
}
