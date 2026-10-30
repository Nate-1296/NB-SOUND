//! Un tramo de una pista en mono y a otra frecuencia: lo que necesitan la firma de
//! Shazam (16 kHz) y los rasgos (22.050 Hz), que no son el reproductor.
//!
//! El remuestreador es el de F0.4.4 (`rubato`, por FFT), cuyo retardo se descarta
//! para que la salida quede alineada con el original.

use std::path::Path;

use rubato::{FftFixedIn, Resampler};

use super::decodificador::Decodificador;
use crate::error::{NsError, NsResult};

const TROZO: usize = 4096;

/// `segundos` de audio desde `desde_seg`, en mono a `tasa` Hz. Si la pista es
/// más corta, se devuelve lo que haya.
///
/// # Errors
///
/// Los de [`Decodificador::abrir`] y [`NsError::Internal`] si el remuestreador
/// no admite las frecuencias.
pub fn mono(ruta: &Path, tasa: u32, desde_seg: f64, segundos: f64) -> NsResult<Vec<f32>> {
    let mut d = Decodificador::abrir(ruta, 0.0)?;
    if desde_seg > 0.0 {
        d.buscar(desde_seg)?;
    }
    let origen = d.tasa;
    let total = (segundos * f64::from(origen)).ceil() as usize;
    let mut frames = Vec::with_capacity(total.min(1 << 24));
    let mut leidos = 0;
    while leidos < total {
        let n = d.leer(&mut frames, (total - leidos).min(16_384))?;
        if n == 0 {
            break;
        }
        leidos += n;
    }
    frames.truncate(total);
    let mono: Vec<f32> = frames.iter().map(|f| (f.left + f.right) * 0.5).collect();
    if origen == tasa {
        return Ok(mono);
    }
    let mut rs = FftFixedIn::<f32>::new(origen as usize, tasa as usize, TROZO, 2, 1)
        .map_err(|_| NsError::Internal)?;
    let mut salida = Vec::with_capacity(mono.len() * tasa as usize / origen as usize + TROZO);
    let mut i = 0;
    while i + TROZO <= mono.len() {
        let out = rs
            .process(&[&mono[i..i + TROZO]], None)
            .map_err(|_| NsError::Internal)?;
        salida.extend_from_slice(&out[0]);
        i += TROZO;
    }
    // Lo que queda, y un trozo de silencio para vaciar el retardo.
    let resto = rs
        .process_partial(Some(&[&mono[i..]]), None)
        .map_err(|_| NsError::Internal)?;
    salida.extend_from_slice(&resto[0]);
    let cola = rs
        .process_partial::<&[f32]>(None, None)
        .map_err(|_| NsError::Internal)?;
    salida.extend_from_slice(&cola[0]);
    let esperado = (mono.len() as f64 * f64::from(tasa) / f64::from(origen)).round() as usize;
    Ok(salida
        .into_iter()
        .skip(rs.output_delay())
        .take(esperado)
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::audio::pruebas::wav;

    #[test]
    fn un_tono_conserva_su_frecuencia_y_su_duracion() {
        let dir = std::env::temp_dir().join(format!("ns-remuestreo-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let ruta = dir.join("tono.wav");
        let _ = wav(&ruta, 44_100, 44_100 * 4, |i, _| {
            (2.0 * std::f32::consts::PI * 1000.0 * i as f32 / 44_100.0).sin() * 0.5
        });
        let m = mono(&ruta, 16_000, 1.0, 2.0).unwrap();
        assert_eq!(m.len(), 32_000);
        // Cruces por cero ascendentes: 1000 por segundo.
        let cruces = m.windows(2).filter(|w| w[0] < 0.0 && w[1] >= 0.0).count();
        assert!((1990..=2010).contains(&cruces), "{cruces}");
        let pico = m[1000..31_000].iter().fold(0.0f32, |a, x| a.max(x.abs()));
        assert!((0.45..0.55).contains(&pico), "{pico}");
        let corto = mono(&ruta, 16_000, 3.0, 10.0).unwrap();
        assert_eq!(corto.len(), 16_000, "lo que queda de la pista");
    }
}
