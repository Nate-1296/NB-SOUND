//! Cómo se mezcla una transición: `servicios/dj_privado/mix_engine.py`.
//!
//! Por cada par de pistas vecinas se decide la técnica (corte en el pulso, fundido
//! largo, quitar graves, barrido de filtros o capas con el instrumental), cuánto se
//! solapan, desde dónde entra la siguiente y hasta dónde suena la que sale. Las
//! curvas dicen, para cada instante del solapamiento, el volumen y las diez bandas
//! de cada plato; el ejecutor (`audio::mezcla`) las aplica al motor.
//!
//! No se porta el cálculo de los puntos de mezcla por RMS: la V1 lo dejaba detrás de
//! `permitir_rms=False` en el único sitio que lo llamaba.

use serde::{Deserialize, Serialize};

pub use super::equipo::{tecnicas, Perfil};
use super::transiciones::Transicion;

/// `TecnicaMezcla`. Se guarda con los nombres de la V1; el texto que ve el usuario
/// sale del diccionario de la interfaz.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ts_rs::TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
pub enum Tecnica {
    /// Corte seco en el pulso: tempos casi iguales en el pico.
    #[serde(rename = "hard_cut")]
    Corte,
    /// Fundido largo de igual potencia, para las bajadas.
    #[serde(rename = "energy_blend")]
    Fundido,
    /// La que sale pierde los graves y la que entra los gana.
    #[serde(rename = "eq_kill_bass")]
    SinGraves,
    /// La que sale pierde graves y la que entra agudos, por bandas.
    #[serde(rename = "filter_sweep")]
    Barrido,
    /// La que entra lo hace sin voz, debajo de la que sale.
    #[serde(rename = "harmonic_mix")]
    Capas,
}

/// `MixPoints`: desde dónde suena la pista en una sesión y desde dónde puede
/// empezar a irse.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Puntos {
    pub entrada_seg: f64,
    pub salida_seg: f64,
    pub duracion_seg: f64,
    /// `bpm` o `default`, como la V1.
    pub fuente: &'static str,
}

/// Por debajo de un minuto la pista suena entera.
const MINIMA_PARA_RECORTAR: f64 = 60.0;

/// `calcular_mix_points_por_bpm`: 16 pulsos de entrada y 32 de salida; si así se
/// perdería más de la mitad de la pista, el 10 % y el 15 %.
#[must_use]
pub fn puntos_por_bpm(duracion: f64, bpm: Option<f64>) -> Option<Puntos> {
    let bpm = bpm.filter(|b| *b > 0.0)?;
    if duracion < MINIMA_PARA_RECORTAR {
        return None;
    }
    let pulso = 60.0 / bpm;
    let (mut entrada, mut salida) = (16.0 * pulso, 32.0 * pulso);
    if duracion - entrada - salida < duracion * 0.5 {
        entrada = duracion * 0.10;
        salida = duracion * 0.15;
    }
    Some(Puntos {
        entrada_seg: super::redondear(entrada, 2),
        salida_seg: super::redondear(f64::max(entrada + 30.0, duracion - salida), 2),
        duracion_seg: super::redondear(duracion, 2),
        fuente: "bpm",
    })
}

/// `mix_points_default`: 8 s de entrada y 12 de salida.
#[must_use]
pub fn puntos_fijos(duracion: f64) -> Puntos {
    if duracion < MINIMA_PARA_RECORTAR {
        return Puntos {
            entrada_seg: 0.0,
            salida_seg: super::redondear(duracion, 2),
            duracion_seg: super::redondear(duracion, 2),
            fuente: "default",
        };
    }
    Puntos {
        entrada_seg: 8.0,
        salida_seg: super::redondear(f64::max(0.0, duracion - 12.0), 2),
        duracion_seg: super::redondear(duracion, 2),
        fuente: "default",
    }
}

#[must_use]
pub fn puntos(duracion: f64, bpm: Option<f64>) -> Puntos {
    puntos_por_bpm(duracion, bpm).unwrap_or_else(|| puntos_fijos(duracion))
}

/// `seleccionar_tecnica`, en el orden de prioridad de la V1, con las razones que
/// explican la decisión.
#[must_use]
pub fn seleccionar(
    plan: &Transicion,
    habilitadas: &[Tecnica],
    fase: &str,
    bpm_a: Option<f64>,
    bpm_b: Option<f64>,
    instrumental_listo: bool,
) -> (Tecnica, Vec<String>) {
    let mut razones = Vec::new();
    let fase = fase.to_lowercase();
    let tempos_iguales = match (bpm_a, bpm_b) {
        (Some(a), Some(b)) if a > 0.0 && b > 0.0 => (a - b).abs() <= 2.0,
        _ => false,
    };
    if fase == "peak" && tempos_iguales {
        razones.push("peak con BPM casi iguales -> corte seco".to_owned());
        if habilitadas.contains(&Tecnica::Corte) {
            return (Tecnica::Corte, razones);
        }
    }
    if fase == "release" || fase == "cooldown" {
        razones.push("fase de descenso -> fundido largo".to_owned());
        if habilitadas.contains(&Tecnica::Fundido) {
            return (Tecnica::Fundido, razones);
        }
    }
    if instrumental_listo
        && habilitadas.contains(&Tecnica::Capas)
        && plan.factor_tonalidad >= 0.6
        && plan.factor_bpm >= 0.6
    {
        razones.push("tonalidades compatibles y stems listos -> mezcla con capas".to_owned());
        return (Tecnica::Capas, razones);
    }
    if plan.factor_bpm >= 0.75 && habilitadas.contains(&Tecnica::SinGraves) {
        razones.push("BPM cercano -> EQ kill bass".to_owned());
        return (Tecnica::SinGraves, razones);
    }
    razones.push("transición neutra -> barrido de filtros".to_owned());
    (Tecnica::Barrido, razones)
}

/// `overlap_recomendado`.
#[must_use]
pub fn solapamiento(tecnica: Tecnica, base: f64) -> f64 {
    match tecnica {
        Tecnica::Corte => 0.4,
        Tecnica::Fundido => base.max(10.0),
        Tecnica::Capas => base.max(8.0),
        Tecnica::Barrido => base.max(6.0),
        Tecnica::SinGraves => base,
    }
}

/// `curva_volumen`: el volumen lineal de la que sale y de la que entra en el punto
/// `p` del solapamiento.
///
/// Difiere de la V1 en las capas: allí la que entraba aparecía de golpe al 40 % y la
/// que salía se cortaba al 40 % al terminar, dos saltos de volumen que el criterio
/// de la fase no admite. Aquí la que entra sube del 0 al 40 % en el primer 5 % y la
/// que sale baja a 0 en el último cuarto; entre medias, la curva es la de la V1.
#[must_use]
pub fn volumenes(tecnica: Tecnica, p: f64) -> (f64, f64) {
    let p = p.clamp(0.0, 1.0);
    match tecnica {
        Tecnica::Corte => {
            if p < 0.5 {
                (1.0, 0.0)
            } else {
                (0.0, 1.0)
            }
        }
        Tecnica::Fundido => ((1.0 - p).sqrt(), p.sqrt()),
        Tecnica::Capas => {
            let a = if p <= 0.75 {
                1.0 - p * 0.6
            } else {
                0.55 * (1.0 - p) / 0.25
            };
            let b = f64::min(1.0, 0.4 + p * 0.6) * f64::min(1.0, p / 0.05);
            (a, b)
        }
        Tecnica::Barrido | Tecnica::SinGraves => (1.0 - p, p),
    }
}

/// Atenuación de una banda "quitada", en dB.
pub const QUITAR_DB: f32 = -16.0;

/// `curva_eq`: las diez bandas (las del ecualizador, en dB) de la que sale y de la
/// que entra.
#[must_use]
pub fn bandas(tecnica: Tecnica, p: f64) -> ([f32; 10], [f32; 10]) {
    let p = p.clamp(0.0, 1.0);
    let (mut a, mut b) = ([0.0f32; 10], [0.0f32; 10]);
    match tecnica {
        Tecnica::SinGraves => {
            let quitar = QUITAR_DB * p as f32;
            a[0] = quitar;
            a[1] = quitar;
            a[2] = quitar * 0.5;
            b[0] = 3.0 * p as f32;
            b[1] = 3.0 * p as f32;
        }
        Tecnica::Barrido => {
            // La V1 movía el corte de banda en banda (`int(round(p * 5))`), con
            // saltos de 4 dB que se oyen; aquí el corte avanza de forma continua y
            // coincide con la V1 cuando cae en una banda exacta.
            let corte_a = p * 5.0;
            for (i, g) in a.iter_mut().enumerate() {
                let d = corte_a - i as f64;
                if d > 0.0 {
                    *g = f32::max(QUITAR_DB, (-4.0 * d) as f32);
                }
            }
            let limite = 9.0 - (1.0 - p) * 5.0;
            for (i, g) in b.iter_mut().enumerate() {
                let d = i as f64 - limite;
                if d > 0.0 {
                    *g = f32::max(QUITAR_DB, (-4.0 * d) as f32);
                }
            }
        }
        Tecnica::Corte | Tecnica::Fundido | Tecnica::Capas => {}
    }
    (a, b)
}

/// `PlanMezcla`: todo lo que el ejecutor necesita para una transición.
#[derive(Debug, Clone, PartialEq)]
pub struct Plan {
    pub tecnica: Tecnica,
    pub solapamiento_seg: f64,
    /// Cuándo empieza a irse la que suena, en segundos de esa pista.
    pub salida_a_seg: f64,
    /// Desde dónde entra la siguiente, en segundos de esa pista.
    pub entrada_b_seg: f64,
    /// La que entra lo hace con su instrumental: solo en las capas.
    pub instrumental_b: bool,
    pub usa_bandas: bool,
    pub razones: Vec<String>,
}

/// Lo que se sabe de cada pista al preparar la transición.
#[derive(Debug, Clone, Copy)]
pub struct Lado {
    pub duracion_seg: f64,
    pub bpm: Option<f64>,
}

/// `preparar_transicion`. `instrumental_listo` dice si la que entra tiene su
/// instrumental del karaoke en disco; sin él, las capas se degradan a otra técnica.
#[must_use]
pub fn preparar(
    transicion: &Transicion,
    perfil: Perfil,
    fase: &str,
    a: Lado,
    b: Lado,
    instrumental_listo: bool,
) -> Plan {
    let habilitadas = tecnicas(perfil);
    let listo = instrumental_listo && habilitadas.contains(&Tecnica::Capas);
    let (tecnica, razones) = seleccionar(transicion, habilitadas, fase, a.bpm, b.bpm, listo);
    let solape = solapamiento(tecnica, transicion.solapamiento_seg);
    let pa = puntos(a.duracion_seg, a.bpm);
    let pb = puntos(b.duracion_seg, b.bpm);
    Plan {
        tecnica,
        solapamiento_seg: super::redondear(solape, 2),
        salida_a_seg: super::redondear(
            f64::min(pa.salida_seg, f64::max(0.0, a.duracion_seg - solape)),
            2,
        ),
        entrada_b_seg: super::redondear(pb.entrada_seg.max(0.0), 2),
        instrumental_b: tecnica == Tecnica::Capas,
        usa_bandas: matches!(tecnica, Tecnica::SinGraves | Tecnica::Barrido),
        razones,
    }
}

#[cfg(test)]
mod pruebas {
    //! Las propiedades de `tests/test_dj_mix_engine.py` de la V1.

    use super::*;

    fn transicion(factor_bpm: f64, factor_tonalidad: f64, solape: f64) -> Transicion {
        Transicion {
            puntuacion: 0.8,
            factor_bpm,
            factor_tonalidad,
            factor_energia: 0.7,
            delta_bpm: Some(0.0),
            delta_camelot: Some(0),
            delta_energia: Some(0.0),
            razones: Vec::new(),
            tecnica: "crossfade",
            solapamiento_seg: solape,
            estilo: "smooth".to_owned(),
        }
    }

    const TODAS: [Tecnica; 5] = [
        Tecnica::Corte,
        Tecnica::Fundido,
        Tecnica::SinGraves,
        Tecnica::Barrido,
        Tecnica::Capas,
    ];

    #[test]
    fn con_tempo_la_entrada_son_16_pulsos_y_la_salida_32() {
        let p = puntos_por_bpm(240.0, Some(120.0)).unwrap();
        assert_eq!(
            (p.entrada_seg, p.salida_seg, p.duracion_seg),
            (8.0, 224.0, 240.0)
        );
        assert_eq!(p.fuente, "bpm");
        let rapida = puntos_por_bpm(90.0, Some(200.0)).unwrap();
        assert!(rapida.entrada_seg < 10.0 && rapida.salida_seg > 60.0);
    }

    #[test]
    fn sin_tempo_o_con_menos_de_un_minuto_no_se_recorta_por_pulsos() {
        assert!(puntos_por_bpm(240.0, None).is_none());
        assert!(puntos_por_bpm(240.0, Some(0.0)).is_none());
        assert!(puntos_por_bpm(240.0, Some(-1.0)).is_none());
        assert!(puntos_por_bpm(45.0, Some(120.0)).is_none());
        assert_eq!(puntos_fijos(45.0).entrada_seg, 0.0);
        assert_eq!(puntos_fijos(45.0).salida_seg, 45.0);
        let p = puntos_fijos(200.0);
        assert_eq!((p.entrada_seg, p.salida_seg), (8.0, 188.0));
    }

    #[test]
    fn el_pico_con_tempos_iguales_corta_en_seco() {
        let t = transicion(0.8, 0.8, 5.0);
        let todas = tecnicas(Perfil::Alto);
        let (tec, razones) = seleccionar(&t, todas, "peak", Some(128.0), Some(128.5), true);
        assert_eq!(tec, Tecnica::Corte);
        assert!(razones.iter().any(|r| r.contains("peak")));
        let (tec, _) = seleccionar(&t, todas, "peak", Some(120.0), Some(140.0), false);
        assert_ne!(tec, Tecnica::Corte);
    }

    #[test]
    fn las_bajadas_funden_largo() {
        let t = transicion(0.8, 0.8, 5.0);
        for fase in ["release", "cooldown"] {
            let (tec, _) = seleccionar(
                &t,
                tecnicas(Perfil::Medio),
                fase,
                Some(120.0),
                Some(120.0),
                false,
            );
            assert_eq!(tec, Tecnica::Fundido);
        }
    }

    #[test]
    fn las_capas_piden_instrumental_armonia_y_un_perfil_que_las_permita() {
        let t = transicion(0.9, 0.9, 5.0);
        let (tec, _) = seleccionar(
            &t,
            tecnicas(Perfil::Alto),
            "groove",
            Some(120.0),
            Some(121.0),
            true,
        );
        assert_eq!(tec, Tecnica::Capas);
        let (tec, _) = seleccionar(
            &t,
            tecnicas(Perfil::Bajo),
            "groove",
            Some(120.0),
            Some(121.0),
            true,
        );
        assert_ne!(tec, Tecnica::Capas);
    }

    #[test]
    fn tempo_cercano_quita_graves_y_lo_demas_barre() {
        let (tec, _) = seleccionar(
            &transicion(0.85, 0.4, 5.0),
            tecnicas(Perfil::Bajo),
            "groove",
            Some(124.0),
            Some(125.0),
            false,
        );
        assert_eq!(tec, Tecnica::SinGraves);
        let (tec, _) = seleccionar(
            &transicion(0.5, 0.3, 5.0),
            tecnicas(Perfil::Bajo),
            "warmup",
            Some(100.0),
            Some(130.0),
            false,
        );
        assert_eq!(tec, Tecnica::Barrido);
    }

    #[test]
    fn el_solapamiento_depende_de_la_tecnica() {
        assert!(solapamiento(Tecnica::Corte, 8.0) < 1.0);
        assert!(solapamiento(Tecnica::Fundido, 4.0) >= 10.0);
        assert_eq!(solapamiento(Tecnica::Barrido, 3.0), 6.0);
        assert_eq!(solapamiento(Tecnica::SinGraves, 3.0), 3.0);
    }

    #[test]
    fn cada_curva_empieza_en_la_que_sale_y_acaba_en_la_que_entra() {
        for t in TODAS {
            let (a0, b0) = volumenes(t, 0.0);
            let (a1, b1) = volumenes(t, 1.0);
            assert!((a0 - 1.0).abs() < 1e-9 && b0.abs() < 1e-9, "{t:?}");
            assert!(a1.abs() < 1e-9 && (b1 - 1.0).abs() < 1e-9, "{t:?}");
            assert_eq!(volumenes(t, -0.5), volumenes(t, 0.0));
            assert_eq!(volumenes(t, 1.5), volumenes(t, 1.0));
        }
        assert_eq!(volumenes(Tecnica::Corte, 0.3), (1.0, 0.0));
        assert_eq!(volumenes(Tecnica::Corte, 0.7), (0.0, 1.0));
        let (a, b) = volumenes(Tecnica::Fundido, 0.5);
        assert!((a - b).abs() < 1e-9 && (a * a + b * b - 1.0).abs() < 1e-9);
    }

    #[test]
    fn ninguna_curva_salta_salvo_el_corte() {
        for t in [
            Tecnica::Fundido,
            Tecnica::SinGraves,
            Tecnica::Barrido,
            Tecnica::Capas,
        ] {
            let mut previa = volumenes(t, 0.0);
            for k in 1..=1000 {
                let v = volumenes(t, f64::from(k) / 1000.0);
                // Ninguno cambia más de un 3,5 % del volumen en una milésima del
                // solapamiento; el mayor paso es el arranque de la raíz del fundido.
                assert!(
                    (v.0 - previa.0).abs() < 0.035 && (v.1 - previa.1).abs() < 0.035,
                    "{t:?} {k}"
                );
                previa = v;
            }
        }
    }

    #[test]
    fn quitar_graves_atenua_los_bajos_de_la_que_sale() {
        assert_eq!(bandas(Tecnica::SinGraves, 0.0), ([0.0; 10], [0.0; 10]));
        let (a, b) = bandas(Tecnica::SinGraves, 1.0);
        assert_eq!((a[0], a[1]), (QUITAR_DB, QUITAR_DB));
        assert!(-10.0 < a[2] && a[2] < 0.0);
        assert!(a[3..].iter().all(|g| *g == 0.0));
        assert!(b[0] > 0.0 && b[1] > 0.0);
    }

    #[test]
    fn el_barrido_converge_y_las_demas_no_tocan_las_bandas() {
        let (a, b) = bandas(Tecnica::Barrido, 0.5);
        assert!(a[0] < 0.0 && b[9] < 0.0);
        // En los extremos, lo mismo que la V1.
        assert_eq!(bandas(Tecnica::Barrido, 0.0).0, [0.0; 10]);
        let (a, b) = bandas(Tecnica::Barrido, 1.0);
        assert_eq!(
            a,
            [-16.0, -16.0, -12.0, -8.0, -4.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        );
        assert_eq!(b, [0.0; 10]);
        let (_, b) = bandas(Tecnica::Barrido, 0.0);
        assert_eq!(
            b,
            [0.0, 0.0, 0.0, 0.0, 0.0, -4.0, -8.0, -12.0, -16.0, -16.0]
        );
        for t in [Tecnica::Corte, Tecnica::Fundido, Tecnica::Capas] {
            assert_eq!(bandas(t, 0.5), ([0.0; 10], [0.0; 10]));
        }
    }

    #[test]
    fn preparar_degrada_las_capas_sin_instrumental_o_con_perfil_bajo() {
        let t = transicion(0.9, 0.9, 5.0);
        let lado = Lado {
            duracion_seg: 200.0,
            bpm: Some(120.0),
        };
        let b = Lado {
            bpm: Some(121.0),
            ..lado
        };
        let alto = preparar(&t, Perfil::Alto, "groove", lado, b, true);
        assert_eq!(alto.tecnica, Tecnica::Capas);
        assert!(alto.instrumental_b);
        assert!(!preparar(&t, Perfil::Bajo, "groove", lado, b, true).instrumental_b);
        assert_ne!(
            preparar(&t, Perfil::Alto, "groove", lado, b, false).tecnica,
            Tecnica::Capas
        );
        let bajada = preparar(
            &transicion(0.8, 0.8, 4.0),
            Perfil::Bajo,
            "release",
            lado,
            lado,
            false,
        );
        assert_eq!(bajada.tecnica, Tecnica::Fundido);
        assert!(bajada.solapamiento_seg >= 10.0);
        // 32 pulsos a 120 son 16 s: sale en 184, y nunca después de duración − solape.
        assert_eq!(bajada.salida_a_seg, 184.0);
        assert_eq!(bajada.entrada_b_seg, 8.0);
    }

    #[test]
    fn la_tecnica_se_guarda_con_el_nombre_de_la_v1() {
        assert_eq!(
            serde_json::to_string(&Tecnica::SinGraves).unwrap(),
            "\"eq_kill_bass\""
        );
        assert_eq!(serde_json::to_string(&Perfil::Medio).unwrap(), "\"mid\"");
    }
}
