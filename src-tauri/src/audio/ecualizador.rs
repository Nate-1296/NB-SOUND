//! El ecualizador de 10 bandas con las 18 preselecciones de la V1 (F2.1.3).
//!
//! La tabla es la que la V1 extrajo de su propia libVLC
//! (`legado/servicios/reproductor.py`, `EQ_PRESETS`). Dos cosas cambian respecto
//! a aplicarla tal cual:
//!
//! 1. **Ganancias corregidas.** Diez campanas de una octava se solapan: con la
//!    tabla tal cual, la respuesta en los centros se desvía hasta 7,2 dB (F0.4.1).
//!    Se calcula la respuesta exacta de la cadena de filtros de Kira (el filtro de
//!    estado variable de Simper, `kira::effect::eq_filter`) y se corrigen las
//!    ganancias por iteración hasta que cada centro da el valor de la tabla.
//! 2. **Margen.** Los presets traen preamplificación alta (+12 dB en Plano) y
//!    bandas de hasta +16,8 dB. Como hacía la V1 (`_preamp_con_headroom`), la
//!    preamplificación aplicada se baja para que preamp más la mayor banda no pase
//!    de 0 dB: el ecualizador no recorta a ningún volumen.

use std::f64::consts::PI;

/// Frecuencias centrales de libVLC, en Hz.
pub const BANDAS_HZ: [f64; 10] = [
    31.0, 62.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0,
];
/// Una octava de ancho de banda.
pub const Q: f64 = 1.414;
/// Rango que admite cada banda y la preamplificación, en dB.
pub const RANGO_DB: (f32, f32) = (-20.0, 20.0);

/// Una preselección: nombre que ve el usuario, preamplificación y bandas.
pub struct Preseleccion {
    pub nombre: &'static str,
    pub preamp_db: f32,
    pub bandas_db: [f32; 10],
}

const fn p(nombre: &'static str, preamp_db: f32, bandas_db: [f32; 10]) -> Preseleccion {
    Preseleccion {
        nombre,
        preamp_db,
        bandas_db,
    }
}

/// En el orden de libVLC, que es el índice que guardaba la V1 (`eq_preset`).
pub const PRESELECCIONES: [Preseleccion; 18] = [
    p("Plano", 12.0, [0.0; 10]),
    p(
        "Clásica",
        12.0,
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -7.2, -7.2, -7.2, -9.6],
    ),
    p(
        "Club",
        6.0,
        [0.0, 0.0, 8.0, 5.6, 5.6, 5.6, 3.2, 0.0, 0.0, 0.0],
    ),
    p(
        "Dance",
        5.0,
        [9.6, 7.2, 2.4, 0.0, 0.0, -5.6, -7.2, -7.2, 0.0, 0.0],
    ),
    p(
        "Graves",
        5.0,
        [-8.0, 9.6, 9.6, 5.6, 1.6, -4.0, -8.0, -10.4, -11.2, -11.2],
    ),
    p(
        "Graves y agudos",
        4.0,
        [7.2, 5.6, 0.0, -7.2, -4.8, 1.6, 8.0, 11.2, 12.0, 12.0],
    ),
    p(
        "Agudos",
        3.0,
        [-9.6, -9.6, -9.6, -4.0, 2.4, 11.2, 16.0, 16.0, 16.0, 16.8],
    ),
    p(
        "Auriculares",
        4.0,
        [4.8, 11.2, 5.6, -3.2, -2.4, 1.6, 4.8, 9.6, 12.8, 14.4],
    ),
    p(
        "Sala grande",
        5.0,
        [10.4, 10.4, 5.6, 5.6, 0.0, -4.8, -4.8, -4.8, 0.0, 0.0],
    ),
    p(
        "En vivo",
        7.0,
        [-4.8, 0.0, 4.0, 5.6, 5.6, 5.6, 4.0, 2.4, 2.4, 2.4],
    ),
    p(
        "Fiesta",
        6.0,
        [7.2, 7.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 7.2, 7.2],
    ),
    p(
        "Pop",
        6.0,
        [-1.6, 4.8, 7.2, 8.0, 5.6, 0.0, -2.4, -2.4, -1.6, -1.6],
    ),
    p(
        "Reggae",
        8.0,
        [0.0, 0.0, 0.0, -5.6, 0.0, 6.4, 6.4, 0.0, 0.0, 0.0],
    ),
    p(
        "Rock",
        5.0,
        [8.0, 4.8, -5.6, -8.0, -3.2, 4.0, 8.8, 11.2, 11.2, 11.2],
    ),
    p(
        "Ska",
        6.0,
        [-2.4, -4.8, -4.0, 0.0, 4.0, 5.6, 8.8, 9.6, 11.2, 9.6],
    ),
    p(
        "Suave",
        5.0,
        [4.8, 1.6, 0.0, -2.4, 0.0, 4.0, 8.0, 9.6, 11.2, 12.0],
    ),
    p(
        "Soft rock",
        7.0,
        [4.0, 4.0, 2.4, 0.0, -4.0, -5.6, -3.2, 0.0, 2.4, 8.8],
    ),
    p(
        "Techno",
        5.0,
        [8.0, 5.6, 0.0, -5.6, -4.8, 0.0, 8.0, 9.6, 9.6, 8.8],
    ),
];

fn acotar(db: f32) -> f32 {
    if db.is_finite() {
        db.clamp(RANGO_DB.0, RANGO_DB.1)
    } else {
        0.0
    }
}

/// La preamplificación que se aplica de verdad: la nominal, bajada lo justo para
/// que preamp más la mayor banda no pase de 0 dB. La nominal es la que se muestra
/// y se guarda.
pub fn preamp_con_margen(preamp_db: f32, bandas_db: &[f32; 10]) -> f32 {
    let pico = bandas_db.iter().copied().map(acotar).fold(0.0f32, f32::max);
    acotar(preamp_db).min(-pico)
}

/// Respuesta en dB, a la frecuencia `f`, de una campana de Kira centrada en `f0`
/// con ganancia `g_db`, a la tasa `tasa`. Es la del filtro de Simper con la
/// frecuencia predeformada por la transformación bilineal:
/// `H(s) = (s² + s·A/Q + 1) / (s² + s/(A·Q) + 1)` con `s = jΩ` y
/// `Ω = tan(π·f/tasa) / tan(π·f0/tasa)`.
fn campana_db(f: f64, f0: f64, g_db: f64, tasa: f64) -> f64 {
    // Kira acota la frecuencia relativa a 0,5.
    let rel = |x: f64| (x / tasa).clamp(0.0001, 0.5);
    let omega = (PI * rel(f)).tan() / (PI * rel(f0)).tan();
    let a = 10f64.powf(g_db / 40.0);
    let re = 1.0 - omega * omega;
    let num = re * re + (omega * a / Q).powi(2);
    let den = re * re + (omega / (a * Q)).powi(2);
    10.0 * (num / den).log10()
}

/// Respuesta de la cadena entera en cada frecuencia central.
pub fn respuesta(ganancias_db: &[f64; 10], tasa: f64) -> [f64; 10] {
    let mut r = [0.0; 10];
    for (i, f) in BANDAS_HZ.iter().enumerate() {
        r[i] = BANDAS_HZ
            .iter()
            .zip(ganancias_db)
            .map(|(f0, g)| campana_db(*f, *f0, *g, tasa))
            .sum();
    }
    r
}

/// Las ganancias que hay que dar a los diez filtros para que la respuesta en cada
/// centro sea `objetivo_db`, a la tasa de salida `tasa`.
pub fn ganancias_corregidas(objetivo_db: &[f32; 10], tasa: f64) -> [f32; 10] {
    let objetivo = objetivo_db.map(|g| f64::from(acotar(g)));
    let mut g = objetivo;
    for _ in 0..60 {
        let r = respuesta(&g, tasa);
        let mut max_error = 0.0f64;
        for k in 0..10 {
            let e = objetivo[k] - r[k];
            max_error = max_error.max(e.abs());
            // Kira acepta cualquier ganancia, pero una muy grande hace inestable el
            // cálculo de la cadena; ±30 dB basta para las preselecciones.
            g[k] = (g[k] + e).clamp(-30.0, 30.0);
        }
        if max_error < 0.001 {
            break;
        }
    }
    g.map(|x| x as f32)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn con_ganancias_corregidas_cada_centro_da_el_valor_de_la_tabla() {
        for tasa in [44_100.0, 48_000.0] {
            for p in &PRESELECCIONES {
                let g = ganancias_corregidas(&p.bandas_db, tasa).map(f64::from);
                let r = respuesta(&g, tasa);
                for (k, (medida, objetivo)) in r.iter().zip(p.bandas_db).enumerate() {
                    let error = (medida - f64::from(objetivo)).abs();
                    assert!(
                        error < 0.05,
                        "{} a {tasa} Hz, banda {k}: {error:.3} dB",
                        p.nombre
                    );
                }
            }
        }
    }

    #[test]
    fn la_tabla_tal_cual_se_desvia_que_es_por_lo_que_se_corrige() {
        let rock = &PRESELECCIONES[13];
        let r = respuesta(&rock.bandas_db.map(f64::from), 44_100.0);
        let peor = r
            .iter()
            .zip(rock.bandas_db)
            .map(|(a, b)| (a - f64::from(b)).abs())
            .fold(0.0, f64::max);
        assert!(peor > 2.0, "{peor}");
    }

    #[test]
    fn con_el_margen_ninguna_preseleccion_pasa_de_0_db() {
        for p in &PRESELECCIONES {
            let preamp = preamp_con_margen(p.preamp_db, &p.bandas_db);
            let pico = p.bandas_db.iter().copied().fold(0.0f32, f32::max);
            assert!(preamp + pico <= 0.0, "{}", p.nombre);
        }
        assert_eq!(preamp_con_margen(12.0, &[0.0; 10]), 0.0, "Plano no sube");
    }

    #[test]
    fn los_valores_fuera_de_rango_se_acotan() {
        assert_eq!(acotar(55.0), 20.0);
        assert_eq!(acotar(f32::NAN), 0.0);
        assert_eq!(preamp_con_margen(-50.0, &[0.0; 10]), -20.0);
    }

    #[test]
    fn hay_dieciocho_preselecciones_con_los_nombres_de_la_v1() {
        assert_eq!(PRESELECCIONES.len(), 18);
        assert_eq!(PRESELECCIONES[0].nombre, "Plano");
        assert_eq!(PRESELECCIONES[17].nombre, "Techno");
    }
}
