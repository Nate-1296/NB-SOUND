//! El arco de una sesión: `servicios/dj_privado/narrativa.py`.
//!
//! La sesión se reparte en fases (apertura, ritmo, pico, bajada y cierre) según la
//! curva de energía del pedido, y cada fase pide una energía, una tensión, una
//! densidad, un brillo y una calma. El planificador elige cada pista mirando lo que
//! pide el punto de la sesión en el que cae.

use serde::Serialize;

use super::intencion::Intencion;

#[derive(Debug, Clone, Copy, PartialEq, Serialize)]
pub struct Objetivos {
    pub energia: f64,
    pub tension: f64,
    pub densidad: f64,
    pub brillo: f64,
    pub calma: f64,
}

/// Una fase, con su tramo de la sesión de 0 a 1. Se serializa con las claves de la
/// V1 (`perfil_a_dict`), que es lo que guarda `dj_sesiones.resumen`.
#[derive(Debug, Clone, PartialEq)]
pub struct Fase {
    pub nombre: &'static str,
    pub inicio: f64,
    pub fin: f64,
    pub objetivos: Objetivos,
}

fn proporciones(curva: &str) -> &'static [(&'static str, f64)] {
    match curva {
        "progressive" => &[
            ("warmup", 0.15),
            ("groove", 0.35),
            ("peak", 0.30),
            ("release", 0.15),
            ("cooldown", 0.05),
        ],
        "peak" => &[
            ("warmup", 0.10),
            ("groove", 0.20),
            ("peak", 0.45),
            ("release", 0.15),
            ("cooldown", 0.10),
        ],
        "descending" => &[
            ("warmup", 0.10),
            ("groove", 0.25),
            ("release", 0.35),
            ("cooldown", 0.30),
        ],
        "wave" => &[
            ("warmup", 0.15),
            ("groove", 0.20),
            ("peak", 0.25),
            ("groove", 0.25),
            ("cooldown", 0.15),
        ],
        _ => &[("warmup", 0.10), ("groove", 0.75), ("cooldown", 0.15)],
    }
}

fn base(fase: &str) -> Objetivos {
    let o = |energia, tension, densidad, brillo, calma| Objetivos {
        energia,
        tension,
        densidad,
        brillo,
        calma,
    };
    match fase {
        "warmup" => o(0.45, 0.30, 0.40, 0.55, 0.55),
        "groove" => o(0.60, 0.45, 0.55, 0.55, 0.45),
        "peak" => o(0.85, 0.65, 0.75, 0.60, 0.20),
        "release" => o(0.55, 0.40, 0.45, 0.50, 0.55),
        _ => o(0.35, 0.25, 0.30, 0.45, 0.75),
    }
}

type Campo = fn(&mut Objetivos) -> &mut f64;

/// `_ajustar_por_intent`: cada eje del pedido mueve su objetivo hasta un 15 %, en
/// el orden de la V1 (el recorte a 0..1 tras cada paso hace que el orden cuente), y
/// un pedido muy calmado templa el pico.
fn ajustar(mut o: Objetivos, intencion: &Intencion, fase: &str) -> Objetivos {
    let eje = |nombre: &str| super::ontologia::valor(&intencion.axes, nombre).unwrap_or(0.0);
    let pasos: [(&str, Campo, f64); 7] = [
        ("energy", |o| &mut o.energia, 1.0),
        ("tension", |o| &mut o.tension, 1.0),
        ("rhythmic_density", |o| &mut o.densidad, 1.0),
        ("brightness", |o| &mut o.brillo, 1.0),
        ("darkness", |o| &mut o.brillo, -1.0),
        ("calmness", |o| &mut o.calma, 1.0),
        ("aggressiveness", |o| &mut o.tension, 1.0),
    ];
    for (nombre, campo, signo) in pasos {
        let valor = eje(nombre);
        if valor == 0.0 {
            continue;
        }
        let c = campo(&mut o);
        *c = (*c + signo * valor * 0.15).clamp(0.0, 1.0);
    }
    if fase == "peak" && eje("calmness") > 0.5 {
        o.energia = (o.energia - 0.20).max(0.5);
        o.tension = (o.tension - 0.15).max(0.3);
    }
    o
}

/// `construir_perfil`: las fases en orden, la última hasta 1 exacto.
#[must_use]
pub fn perfil(intencion: &Intencion) -> Vec<Fase> {
    let curva = if intencion.curva_energia.is_empty() {
        "stable"
    } else {
        intencion.curva_energia.as_str()
    };
    let mut cursor = 0.0;
    let mut fases: Vec<Fase> = proporciones(curva)
        .iter()
        .map(|&(nombre, peso)| {
            let fin = f64::min(1.0, cursor + peso);
            let f = Fase {
                nombre,
                inicio: cursor,
                fin,
                objetivos: ajustar(base(nombre), intencion, nombre),
            };
            cursor = fin;
            f
        })
        .collect();
    if let Some(ultima) = fases.last_mut() {
        ultima.fin = 1.0;
    }
    fases
}

/// `fase_en_t`: el índice de la fase activa en `t`; fuera de 0..1, la extrema.
#[must_use]
pub fn fase_en(perfil: &[Fase], t: f64) -> usize {
    if t <= 0.0 {
        return 0;
    }
    perfil
        .iter()
        .position(|f| f.inicio <= t && t < f.fin)
        .unwrap_or(perfil.len().saturating_sub(1))
}

/// `objetivos_para_posicion`: en el último cuarto de una fase se mezcla con la
/// siguiente, para que la frontera no sea un salto.
#[must_use]
pub fn objetivos(perfil: &[Fase], t: f64) -> Objetivos {
    if perfil.is_empty() {
        return Objetivos {
            energia: 0.5,
            tension: 0.4,
            densidad: 0.5,
            brillo: 0.5,
            calma: 0.5,
        };
    }
    let i = fase_en(perfil, t);
    let f = &perfil[i];
    let avance = (t - f.inicio) / f64::max(1e-6, f.fin - f.inicio);
    let a = f.objetivos;
    match perfil.get(i + 1) {
        Some(s) if avance > 0.75 => {
            let ps = (avance - 0.75) / 0.25;
            let pa = 1.0 - ps;
            let b = s.objetivos;
            Objetivos {
                energia: pa * a.energia + ps * b.energia,
                tension: pa * a.tension + ps * b.tension,
                densidad: pa * a.densidad + ps * b.densidad,
                brillo: pa * a.brillo + ps * b.brillo,
                calma: pa * a.calma + ps * b.calma,
            }
        }
        _ => a,
    }
}

fn descripcion(fase: &str) -> &'static str {
    match fase {
        "warmup" => "Apertura, presentando el clima",
        "groove" => "Ritmo establecido, sostenido",
        "peak" => "Climax energetico",
        "release" => "Bajando del pico, atenuacion",
        _ => "Cierre, resolucion",
    }
}

/// `perfil_a_dict`.
#[must_use]
pub fn a_json(perfil: &[Fase]) -> serde_json::Value {
    perfil
        .iter()
        .map(|f| {
            serde_json::json!({
                "name": f.nombre,
                "start_t": super::redondear(f.inicio, 4),
                "end_t": super::redondear(f.fin, 4),
                "target_energy": super::redondear(f.objetivos.energia, 3),
                "target_tension": super::redondear(f.objetivos.tension, 3),
                "target_density": super::redondear(f.objetivos.densidad, 3),
                "target_brightness": super::redondear(f.objetivos.brillo, 3),
                "target_calmness": super::redondear(f.objetivos.calma, 3),
                "descripcion": descripcion(f.nombre),
            })
        })
        .collect()
}

#[cfg(test)]
mod pruebas {
    use super::*;
    use crate::dj::intencion;

    #[test]
    fn el_perfil_de_cada_pedido_es_el_de_la_v1() {
        let d: serde_json::Value =
            serde_json::from_str(include_str!("doradas_sesion.json")).expect("doradas");
        for s in d["sesiones"].as_array().expect("sesiones") {
            let i = intencion::interpretar(
                s["prompt"].as_str().expect("prompt"),
                s["minutos"].as_u64().expect("minutos") as u32,
            );
            assert_eq!(a_json(&perfil(&i)), s["perfil"], "{}", s["prompt"]);
        }
    }

    #[test]
    fn la_frontera_entre_fases_se_suaviza_en_el_ultimo_cuarto() {
        let p = perfil(&intencion::interpretar("algo que vaya subiendo", 60));
        let primera = &p[0];
        let dentro = objetivos(&p, primera.inicio + (primera.fin - primera.inicio) * 0.5);
        assert_eq!(dentro, primera.objetivos);
        let casi = objetivos(&p, primera.fin - 1e-9);
        assert!((casi.energia - p[1].objetivos.energia).abs() < 1e-6);
    }

    #[test]
    fn fuera_de_la_sesion_vale_la_fase_extrema() {
        let p = perfil(&Intencion::default());
        assert_eq!(fase_en(&p, -1.0), 0);
        assert_eq!(fase_en(&p, 2.0), p.len() - 1);
    }
}
