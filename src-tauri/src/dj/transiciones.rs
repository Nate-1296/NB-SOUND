//! Qué tal pasa una pista a la siguiente: `servicios/dj_privado/transiciones.py`.
//!
//! Tres factores de 0 a 1 (tempo, tonalidad en la rueda Camelot y salto de
//! energía), pesados según el estilo de transición del pedido, dan la puntuación,
//! las razones que ve el usuario y la técnica y el solapamiento que se sugieren. El
//! constructor reordena cada bloque con intercambios locales para subir la suma.
//! Cómo suena la mezcla es cosa del motor (F6.1.3); esto solo la planifica.

use serde_json::json;

use super::planificador::Candidata;

/// `codigo_camelot`. El modo cuenta como menor si contiene "min".
#[must_use]
pub fn camelot(tonalidad: Option<&str>, modo: Option<&str>) -> Option<&'static str> {
    const MAYOR: [(&str, &str); 17] = [
        ("C", "8B"),
        ("C#", "3B"),
        ("D", "10B"),
        ("D#", "5B"),
        ("E", "12B"),
        ("F", "7B"),
        ("F#", "2B"),
        ("G", "9B"),
        ("G#", "4B"),
        ("A", "11B"),
        ("A#", "6B"),
        ("B", "1B"),
        ("Db", "3B"),
        ("Eb", "5B"),
        ("Gb", "2B"),
        ("Ab", "4B"),
        ("Bb", "6B"),
    ];
    const MENOR: [(&str, &str); 17] = [
        ("A", "8A"),
        ("A#", "3A"),
        ("B", "10A"),
        ("C", "5A"),
        ("C#", "12A"),
        ("D", "7A"),
        ("D#", "2A"),
        ("E", "9A"),
        ("F", "4A"),
        ("F#", "11A"),
        ("G", "6A"),
        ("G#", "1A"),
        ("Bb", "3A"),
        ("Db", "12A"),
        ("Eb", "2A"),
        ("Gb", "11A"),
        ("Ab", "1A"),
    ];
    let t = tonalidad?.trim();
    if t.is_empty() {
        return None;
    }
    let menor = modo.is_some_and(|m| m.to_lowercase().contains("min"));
    let tabla = if menor { &MENOR } else { &MAYOR };
    tabla.iter().find(|(k, _)| *k == t).map(|(_, c)| *c)
}

fn partes(codigo: &str) -> Option<(i32, char)> {
    let letra = codigo.chars().last()?;
    if letra != 'A' && letra != 'B' {
        return None;
    }
    let n: i32 = codigo[..codigo.len() - 1].parse().ok()?;
    (1..=12).contains(&n).then_some((n, letra))
}

/// `distancia_camelot`: 0 igual, 1 vecina o cambio de modo, 2 a dos pasos, 3 lo
/// demás; 99 si alguno no es un código.
#[must_use]
pub fn distancia_camelot(a: &str, b: &str) -> i32 {
    let (Some((na, la)), Some((nb, lb))) = (partes(a), partes(b)) else {
        return 99;
    };
    let d = (na - nb).abs();
    let d = d.min(12 - d);
    match (d, la != lb) {
        (0, false) => 0,
        (0, true) | (1, false) => 1,
        (2, false) => 2,
        _ => 3,
    }
}

/// `factor_bpm`, contando el doble y la mitad del tempo como cercanos.
#[must_use]
pub fn factor_bpm(a: Option<f64>, b: Option<f64>) -> f64 {
    const TOLERANCIA: f64 = 8.0;
    let (Some(a), Some(b)) = (a, b) else {
        return 0.5;
    };
    if a <= 0.0 || b <= 0.0 {
        return 0.5;
    }
    let d = (a - b)
        .abs()
        .min((a * 2.0 - b).abs())
        .min((a / 2.0 - b).abs());
    if d <= TOLERANCIA {
        1.0
    } else if d <= TOLERANCIA * 2.0 {
        1.0 - 0.5 * ((d - TOLERANCIA) / TOLERANCIA)
    } else if d <= 30.0 {
        0.5 - 0.5 * ((d - TOLERANCIA * 2.0) / (30.0 - TOLERANCIA * 2.0))
    } else {
        0.0
    }
}

/// `factor_energia`: cada estilo tolera o busca saltos distintos.
#[must_use]
pub fn factor_energia(a: Option<f64>, b: Option<f64>, estilo: &str) -> f64 {
    let (Some(a), Some(b)) = (a, b) else {
        return 0.5;
    };
    let d = b - a;
    let ad = d.abs();
    match estilo {
        "smooth" => {
            if ad <= 0.10 {
                1.0
            } else if ad <= 0.25 {
                1.0 - (ad - 0.10) / 0.30
            } else {
                f64::max(0.0, 0.5 - (ad - 0.25) * 2.0)
            }
        }
        "aggressive" => {
            if ad >= 0.30 {
                1.0
            } else {
                0.5 + ad
            }
        }
        "energetic" => {
            if (0.0..=0.15).contains(&d) {
                1.0
            } else if d < 0.0 {
                f64::max(0.0, 0.5 + d * 2.0)
            } else {
                f64::max(0.3, 1.0 - (d - 0.15) * 1.5)
            }
        }
        "cinematic" => {
            if ad <= 0.30 {
                1.0 - ad * 0.5
            } else {
                f64::max(0.0, 0.7 - (ad - 0.30))
            }
        }
        _ => 1.0 - ad.min(1.0),
    }
}

/// `TransicionPlan`.
#[derive(Debug, Clone, PartialEq)]
pub struct Transicion {
    pub puntuacion: f64,
    pub factor_bpm: f64,
    pub factor_tonalidad: f64,
    pub factor_energia: f64,
    pub delta_bpm: Option<f64>,
    pub delta_camelot: Option<i32>,
    pub delta_energia: Option<f64>,
    pub razones: Vec<String>,
    pub tecnica: &'static str,
    pub solapamiento_seg: f64,
    pub estilo: String,
}

impl Transicion {
    /// `transicion_a_dict`: lo que guarda `dj_sesion_pistas.transicion`.
    #[must_use]
    pub fn a_json(&self) -> serde_json::Value {
        json!({
            "score": self.puntuacion,
            "factor_bpm": self.factor_bpm,
            "factor_key": self.factor_tonalidad,
            "factor_energia": self.factor_energia,
            "delta_bpm": self.delta_bpm,
            "delta_camelot": self.delta_camelot,
            "delta_energia": self.delta_energia,
            "razones": self.razones,
            "tecnica_sugerida": self.tecnica,
            "overlap_seg": self.solapamiento_seg,
            "estilo_aplicado": self.estilo,
        })
    }
}

impl Transicion {
    /// Lee lo que guardó [`Self::a_json`] (o la V1). Sin datos, una transición
    /// neutra de 4 s, como `TransicionPlan` por defecto.
    #[must_use]
    pub fn desde_json(v: &serde_json::Value) -> Self {
        let f = |k: &str, d: f64| v[k].as_f64().unwrap_or(d);
        Self {
            puntuacion: f("score", 0.5),
            factor_bpm: f("factor_bpm", 0.5),
            factor_tonalidad: f("factor_key", 0.5),
            factor_energia: f("factor_energia", 0.5),
            delta_bpm: v["delta_bpm"].as_f64(),
            delta_camelot: v["delta_camelot"]
                .as_i64()
                .and_then(|d| i32::try_from(d).ok()),
            delta_energia: v["delta_energia"].as_f64(),
            razones: v["razones"]
                .as_array()
                .map(|r| {
                    r.iter()
                        .filter_map(|x| x.as_str().map(str::to_owned))
                        .collect()
                })
                .unwrap_or_default(),
            tecnica: match v["tecnica_sugerida"].as_str() {
                Some("cut") => "cut",
                Some("drone") => "drone",
                Some("mix_armonico") => "mix_armonico",
                _ => "crossfade",
            },
            solapamiento_seg: f("overlap_seg", 4.0),
            estilo: v["estilo_aplicado"].as_str().unwrap_or("smooth").to_owned(),
        }
    }
}

fn pesos(estilo: &str) -> (f64, f64, f64) {
    match estilo {
        "smooth" => (0.45, 0.30, 0.25),
        "harmonic" => (0.25, 0.55, 0.20),
        "energetic" => (0.40, 0.15, 0.45),
        "aggressive" => (0.25, 0.15, 0.60),
        "cinematic" => (0.20, 0.30, 0.50),
        _ => (0.40, 0.30, 0.30),
    }
}

/// `planificar_transicion` de `a`, que sale, a `b`, que entra.
#[must_use]
pub fn planificar(a: &Candidata, b: &Candidata, estilo: &str) -> Transicion {
    let ca = camelot(a.tonalidad.as_deref(), a.modo.as_deref());
    let cb = camelot(b.tonalidad.as_deref(), b.modo.as_deref());
    let dist = match (ca, cb) {
        (Some(x), Some(y)) => distancia_camelot(x, y),
        _ => 99,
    };
    let fk = match dist {
        99 => 0.5,
        0 => 1.0,
        1 => 0.85,
        2 => 0.6,
        3 => 0.3,
        _ => 0.0,
    };
    let fb = factor_bpm(a.bpm, b.bpm);
    let fe = factor_energia(a.energia, b.energia, estilo);
    let (pb, pk, pe) = pesos(estilo);
    let puntuacion = pb * fb + pk * fk + pe * fe;
    let delta_bpm = a.bpm.zip(b.bpm).map(|(x, y)| y - x);
    let delta_e = a.energia.zip(b.energia).map(|(x, y)| y - x);

    let mut razones = Vec::new();
    if let Some(d) = delta_bpm {
        razones.push(if fb >= 0.9 {
            format!("BPM cercano (Δ={d:+.1})")
        } else if fb >= 0.6 {
            format!("BPM tolerable (Δ={d:+.1})")
        } else {
            format!("salto de BPM grande (Δ={d:+.1})")
        });
    }
    if let (Some(x), Some(y)) = (ca, cb) {
        razones.push(match dist {
            0 => format!("tonalidad identica ({x})"),
            1 => format!("tonalidades vecinas ({x}→{y})"),
            2 => format!("distancia armonica media ({x}→{y})"),
            _ => format!("tonalidades alejadas ({x}→{y})"),
        });
    }
    if let Some(d) = delta_e {
        razones.push(if d.abs() <= 0.1 {
            format!("energia estable (Δ={d:+.2})")
        } else if d > 0.0 {
            format!("subida de energia (Δ={d:+.2})")
        } else {
            format!("bajada de energia (Δ={d:+.2})")
        });
    }
    razones.push(format!("estilo:{estilo}"));

    let (tecnica, solapamiento_seg) = match estilo {
        "aggressive" => ("cut", 0.5),
        "cinematic" => ("drone", 6.0),
        _ if puntuacion >= 0.80 && dist <= 1 && fb >= 0.85 => ("mix_armonico", 8.0),
        _ if puntuacion >= 0.6 => ("crossfade", 5.0),
        _ => ("crossfade", 3.0),
    };
    Transicion {
        puntuacion,
        factor_bpm: fb,
        factor_tonalidad: fk,
        factor_energia: fe,
        delta_bpm,
        delta_camelot: (dist != 99).then_some(dist),
        delta_energia: delta_e,
        razones,
        tecnica,
        solapamiento_seg,
        estilo: estilo.to_owned(),
    }
}

/// Las transiciones entre cada par de vecinas.
#[must_use]
pub fn entre(pistas: &[Candidata], estilo: &str) -> Vec<Transicion> {
    pistas
        .windows(2)
        .map(|par| planificar(&par[0], &par[1], estilo))
        .collect()
}

/// `refinar_orden_para_transiciones`: intercambia vecinas mientras la suma de sus
/// dos transiciones suba más de una centésima, hasta ocho pasadas. La primera
/// pista no se mueve: es la apertura que eligió el planificador.
pub fn refinar(pistas: &mut [Candidata], estilo: &str) -> Vec<Transicion> {
    let n = pistas.len();
    if n > 2 {
        let p = |a: &Candidata, b: &Candidata| planificar(a, b, estilo).puntuacion;
        for _ in 0..8 {
            let mut mejora = false;
            for i in 1..n - 2 {
                let actual = p(&pistas[i - 1], &pistas[i]) + p(&pistas[i], &pistas[i + 1]);
                let cambio = p(&pistas[i - 1], &pistas[i + 1]) + p(&pistas[i + 1], &pistas[i]);
                if cambio > actual + 0.01 {
                    pistas.swap(i, i + 1);
                    mejora = true;
                }
            }
            if !mejora {
                break;
            }
        }
    }
    entre(pistas, estilo)
}

/// `resolver_estilo_intent`: el de más peso; con empate, el primero en aparecer.
#[must_use]
pub fn estilo(pesos: &super::ontologia::Mapa) -> String {
    let mut mejor: Option<&(String, f64)> = None;
    for e in pesos {
        if mejor.is_none_or(|m| e.1 > m.1) {
            mejor = Some(e);
        }
    }
    mejor.map_or_else(|| "smooth".to_owned(), |(k, _)| k.clone())
}

#[cfg(test)]
mod pruebas {
    use super::*;

    #[test]
    fn la_rueda_camelot_es_circular_y_el_cambio_de_modo_cuesta_uno() {
        assert_eq!(distancia_camelot("12B", "1B"), 1);
        assert_eq!(distancia_camelot("8A", "8B"), 1);
        assert_eq!(distancia_camelot("8A", "10A"), 2);
        assert_eq!(distancia_camelot("8A", "11B"), 3);
        assert_eq!(distancia_camelot("13A", "1A"), 99);
        assert_eq!(camelot(Some("A"), Some("minor")), Some("8A"));
        assert_eq!(camelot(Some("A"), None), Some("11B"));
        assert_eq!(camelot(Some("H"), None), None);
    }

    #[test]
    fn el_doble_tempo_cuenta_como_cercano() {
        assert_eq!(factor_bpm(Some(70.0), Some(140.0)), 1.0);
        assert_eq!(factor_bpm(Some(120.0), Some(132.0)), 0.75);
        assert_eq!(factor_bpm(None, Some(120.0)), 0.5);
        assert_eq!(factor_bpm(Some(100.0), Some(160.0)), 0.0);
    }

    fn pista(id: i64, bpm: f64, tonalidad: &str, modo: &str, energia: f64) -> Candidata {
        Candidata {
            id,
            bpm: Some(bpm),
            tonalidad: Some(tonalidad.to_owned()),
            modo: Some(modo.to_owned()),
            energia: Some(energia),
            ..Candidata::default()
        }
    }

    #[test]
    fn tempo_y_tonalidad_vecinos_dan_una_transicion_excelente_y_lo_opuesto_una_mala() {
        let a = pista(1, 120.0, "C", "major", 0.6);
        let b = pista(2, 121.0, "G", "major", 0.65);
        assert!(planificar(&a, &b, "smooth").puntuacion > 0.85);
        let c = pista(3, 80.0, "C", "major", 0.3);
        let d = pista(4, 180.0, "F#", "minor", 0.95);
        assert!(planificar(&c, &d, "smooth").puntuacion < 0.4);
    }

    #[test]
    fn el_estilo_decide_si_un_salto_de_energia_es_bueno() {
        assert!(
            factor_energia(Some(0.5), Some(0.55), "smooth")
                > factor_energia(Some(0.5), Some(0.95), "smooth")
        );
        assert!(
            factor_energia(Some(0.5), Some(0.95), "aggressive")
                >= factor_energia(Some(0.5), Some(0.55), "aggressive")
        );
    }

    #[test]
    fn refinar_no_empeora_el_total_ni_mueve_la_apertura() {
        let original = vec![
            pista(1, 120.0, "C", "major", 0.5),
            pista(2, 180.0, "F#", "minor", 0.9),
            pista(3, 122.0, "G", "major", 0.55),
            pista(4, 124.0, "D", "major", 0.6),
        ];
        let total = |t: &[Transicion]| t.iter().map(|t| t.puntuacion).sum::<f64>();
        let antes = total(&entre(&original, "smooth"));
        let mut orden = original.clone();
        let despues = total(&refinar(&mut orden, "smooth"));
        assert!(despues >= antes);
        assert_eq!(orden[0].id, 1);
    }

    #[test]
    fn una_transicion_guardada_se_lee_igual_y_sin_datos_es_neutra() {
        let a = pista(1, 120.0, "C", "major", 0.6);
        let b = pista(2, 121.0, "G", "major", 0.65);
        let t = planificar(&a, &b, "harmonic");
        assert_eq!(Transicion::desde_json(&t.a_json()), t);
        let neutra = Transicion::desde_json(&serde_json::json!({}));
        assert_eq!((neutra.factor_bpm, neutra.solapamiento_seg), (0.5, 4.0));
    }

    #[test]
    fn con_empate_de_estilos_gana_el_primero_que_se_pidio() {
        let m = vec![("smooth".to_owned(), 1.0), ("aggressive".to_owned(), 1.0)];
        assert_eq!(estilo(&m), "smooth");
        assert_eq!(estilo(&Vec::new()), "smooth");
    }
}
