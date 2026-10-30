//! Normalización de volumen por sonoridad EBU R128 (F2.1.4).
//!
//! La V1 usaba el filtro `normvol` de VLC, que sube y baja el volumen sobre la
//! marcha según lo que suena y bombea en los pasajes tranquilos. La V2 mide una vez
//! la sonoridad integrada de cada pista (al importar o analizar) y aplica una
//! ganancia fija al decodificarla: dentro de una pista no cambia nada, y entre
//! pistas el nivel se iguala.

use std::path::Path;

use ebur128::{EbuR128, Mode};

use super::decodificador::Decodificador;
use crate::error::{NsError, NsResult};

/// El nivel al que se llevan las pistas, el de los servicios de streaming.
pub const OBJETIVO_LUFS: f64 = -14.0;
/// Hasta dónde puede quedar el pico verdadero tras subir una pista: lo que la
/// normalización sube, no lo puede recortar el limitador.
const PICO_MAXIMO_DBTP: f64 = -1.0;
/// Una pista muy baja no se sube más que esto: subir 20 dB una grabación con ruido
/// de fondo lo convierte en protagonista.
const SUBIDA_MAXIMA_DB: f64 = 12.0;

/// Lo que se guarda de cada pista (`rasgos.lufs`, `pico_verdadero`, `rango_sonoridad`).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Sonoridad {
    pub lufs: f64,
    /// Pico verdadero, en dBTP.
    pub pico_verdadero: f64,
    /// Rango de sonoridad, en LU.
    pub rango: f64,
}

/// Mide una pista entera.
///
/// # Errors
///
/// Los de [`Decodificador::abrir`]; [`NsError::AudioCorrupted`] si la pista es
/// silencio o demasiado corta para medirse.
pub fn medir(ruta: &Path) -> NsResult<Sonoridad> {
    let mut d = Decodificador::abrir(ruta, 0.0)?;
    let mut medidor = EbuR128::new(2, d.tasa, Mode::I | Mode::TRUE_PEAK | Mode::LRA)
        .map_err(|_| NsError::Internal)?;
    let mut bloque = Vec::with_capacity(16_384);
    let mut entrelazado = Vec::with_capacity(32_768);
    loop {
        bloque.clear();
        if d.leer(&mut bloque, 16_384)? == 0 {
            break;
        }
        entrelazado.clear();
        entrelazado.extend(bloque.iter().flat_map(|f| [f.left, f.right]));
        medidor
            .add_frames_f32(&entrelazado)
            .map_err(|_| NsError::AudioCorrupted)?;
    }
    let lufs = medidor
        .loudness_global()
        .map_err(|_| NsError::AudioCorrupted)?;
    if !lufs.is_finite() {
        return Err(NsError::AudioCorrupted);
    }
    let pico = (0..2)
        .filter_map(|c| medidor.true_peak(c).ok())
        .fold(0.0f64, f64::max);
    Ok(Sonoridad {
        lufs,
        pico_verdadero: if pico > 0.0 {
            20.0 * pico.log10()
        } else {
            f64::NEG_INFINITY
        },
        rango: medidor.loudness_range().unwrap_or(0.0),
    })
}

/// La ganancia que lleva una pista al objetivo, en dB. Bajar no tiene tope; subir
/// lo tiene por el pico verdadero y por [`SUBIDA_MAXIMA_DB`]. Sin medida, 0.
pub fn ganancia_db(lufs: Option<f64>, pico_verdadero: Option<f64>) -> f32 {
    let Some(lufs) = lufs.filter(|l| l.is_finite()) else {
        return 0.0;
    };
    let mut g = OBJETIVO_LUFS - lufs;
    if g > 0.0 {
        let margen = pico_verdadero
            .filter(|p| p.is_finite())
            .map_or(f64::INFINITY, |p| PICO_MAXIMO_DBTP - p);
        g = g.min(margen.max(0.0)).min(SUBIDA_MAXIMA_DB);
    }
    g as f32
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::audio::pruebas::wav;

    #[test]
    fn dos_pistas_a_10_lu_suenan_a_menos_de_1_lu_normalizadas() {
        let dir = std::env::temp_dir().join(format!("ns-sonoridad-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let ruido = |amplitud: f32| {
            move |i: usize, c: usize| {
                let x = ((i * 7919 + c * 104_729) % 65_521) as f32 / 65_521.0 - 0.5;
                let tono = (2.0 * std::f32::consts::PI * 220.0 * i as f32 / 44_100.0).sin();
                (x * 0.5 + tono * 0.5) * amplitud
            }
        };
        let (alta, baja) = (dir.join("alta.wav"), dir.join("baja.wav"));
        let _ = wav(&alta, 44_100, 44_100 * 6, ruido(0.4));
        let _ = wav(
            &baja,
            44_100,
            44_100 * 6,
            ruido(0.4 / 10f32.powf(10.0 / 20.0)),
        );
        let a = medir(&alta).unwrap();
        let b = medir(&baja).unwrap();
        assert!((a.lufs - b.lufs - 10.0).abs() < 0.2, "{a:?} {b:?}");

        // La misma medida, sobre lo que entrega el decodificador con la ganancia.
        let medir_con = |ruta: &Path, g: f32| {
            let mut d = Decodificador::abrir(ruta, g).unwrap();
            let mut m = EbuR128::new(2, d.tasa, Mode::I).unwrap();
            let mut v = Vec::new();
            while d.leer(&mut v, 8192).unwrap() > 0 {}
            let e: Vec<f32> = v.iter().flat_map(|f| [f.left, f.right]).collect();
            m.add_frames_f32(&e).unwrap();
            m.loudness_global().unwrap()
        };
        let ga = ganancia_db(Some(a.lufs), Some(a.pico_verdadero));
        let gb = ganancia_db(Some(b.lufs), Some(b.pico_verdadero));
        let diferencia = (medir_con(&alta, ga) - medir_con(&baja, gb)).abs();
        assert!(diferencia < 1.0, "{diferencia} LU");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn subir_una_pista_nunca_lleva_el_pico_por_encima_de_menos_1_dbtp() {
        assert_eq!(ganancia_db(Some(-24.0), Some(-3.0)), 2.0);
        assert_eq!(
            ganancia_db(Some(-40.0), Some(-30.0)),
            12.0,
            "tope de subida"
        );
        assert_eq!(
            ganancia_db(Some(-8.0), Some(0.5)),
            -6.0,
            "bajar no tiene tope"
        );
        assert_eq!(
            ganancia_db(Some(-20.0), Some(0.0)),
            0.0,
            "sin margen no sube"
        );
    }

    #[test]
    fn sin_medida_no_se_toca_el_volumen() {
        assert_eq!(ganancia_db(None, None), 0.0);
        assert_eq!(ganancia_db(Some(f64::NEG_INFINITY), None), 0.0);
    }

    #[test]
    fn el_silencio_no_tiene_sonoridad() {
        let dir = std::env::temp_dir().join(format!("ns-silencio-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let ruta = dir.join("s.wav");
        let _ = wav(&ruta, 44_100, 44_100, |_, _| 0.0);
        assert_eq!(medir(&ruta), Err(NsError::AudioCorrupted));
        let _ = std::fs::remove_dir_all(dir);
    }
}
