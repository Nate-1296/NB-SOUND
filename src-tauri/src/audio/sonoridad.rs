//! Normalización de volumen por sonoridad EBU R128 (F2.1.4).
//!
//! La V1 usaba el filtro `normvol` de VLC, que sube y baja el volumen sobre la
//! marcha según lo que suena y bombea en los pasajes tranquilos. La V2 mide una vez
//! la sonoridad integrada de cada pista (al importar o analizar) y aplica una
//! ganancia fija al decodificarla: dentro de una pista no cambia nada, y entre
//! pistas el nivel se iguala.
//!
//! La misma pasada deja la forma de onda de la pista (F8.1), que la barra de
//! progreso y el DJ dibujan.

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

/// Lo que se guarda de cada pista (tabla `sonoridad`).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Sonoridad {
    pub lufs: f64,
    /// Pico verdadero, en dBTP.
    pub pico_verdadero: f64,
    /// Rango de sonoridad, en LU.
    pub rango: f64,
}

/// Cuántos picos tiene la forma de onda de una pista, sea cual sea su duración
/// (F8.1): lo que se pinta es siempre la pista entera, y 1.000 dan para la barra
/// más ancha.
pub const PICOS: usize = 1000;

/// Los fotogramas de cada tramo mientras se decodifica. La duración no se sabe
/// hasta el final, así que se guardan los picos de tramos cortos y al acabar se
/// reducen a [`PICOS`]: 512 fotogramas son unos 11 ms, y una pista de diez
/// minutos deja 56.000 tramos, 225 KB que se sueltan en cuanto se reducen.
const TRAMO: usize = 512;

/// Lo que deja una pasada por la pista: su sonoridad, si la tiene, y su forma de
/// onda, que la tiene también el silencio.
#[derive(Debug, Clone, PartialEq)]
pub struct Medida {
    pub sonoridad: Option<Sonoridad>,
    /// [`PICOS`] valores de 0 a 255: el máximo absoluto de las dos voces en su
    /// tramo de la pista.
    pub picos: Vec<u8>,
}

/// Mide una pista entera: la sonoridad y la forma de onda salen de la misma
/// decodificación (F8.1), así que el archivo se lee una sola vez.
///
/// # Errors
///
/// Los de [`Decodificador::abrir`]; [`NsError::AudioCorrupted`] si la pista no
/// tiene ni un fotograma. El silencio no es un error: no tiene sonoridad, pero sí
/// forma de onda (plana).
pub fn medir(ruta: &Path) -> NsResult<Medida> {
    let mut d = Decodificador::abrir(ruta, 0.0)?;
    let mut medidor = EbuR128::new(2, d.tasa, Mode::I | Mode::TRUE_PEAK | Mode::LRA)
        .map_err(|_| NsError::Internal)?;
    let mut bloque = Vec::with_capacity(16_384);
    let mut entrelazado = Vec::with_capacity(32_768);
    let mut tramos: Vec<f32> = Vec::new();
    let (mut maximo, mut en_tramo) = (0.0f32, 0usize);
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
        for f in &bloque {
            maximo = maximo.max(f.left.abs()).max(f.right.abs());
            en_tramo += 1;
            if en_tramo == TRAMO {
                tramos.push(maximo);
                (maximo, en_tramo) = (0.0, 0);
            }
        }
    }
    if en_tramo > 0 {
        tramos.push(maximo);
    }
    if tramos.is_empty() {
        return Err(NsError::AudioCorrupted);
    }
    let sonoridad = medidor
        .loudness_global()
        .ok()
        .filter(|l| l.is_finite())
        .map(|lufs| {
            let pico = (0..2)
                .filter_map(|c| medidor.true_peak(c).ok())
                .fold(0.0f64, f64::max);
            Sonoridad {
                lufs,
                pico_verdadero: if pico > 0.0 {
                    20.0 * pico.log10()
                } else {
                    f64::NEG_INFINITY
                },
                rango: medidor.loudness_range().unwrap_or(0.0),
            }
        });
    Ok(Medida {
        sonoridad,
        picos: reducir(&tramos),
    })
}

/// Reduce los picos de los tramos a [`PICOS`], cada uno el máximo de los suyos.
/// Con menos tramos que picos (una pista de menos de 12 s), un tramo ocupa
/// varios picos seguidos.
fn reducir(tramos: &[f32]) -> Vec<u8> {
    let n = tramos.len();
    (0..PICOS)
        .map(|i| {
            let desde = (i * n / PICOS).min(n - 1);
            let hasta = ((i + 1) * n / PICOS).clamp(desde + 1, n);
            let m = tramos[desde..hasta].iter().fold(0.0f32, |a, &b| a.max(b));
            (m.clamp(0.0, 1.0) * 255.0).round() as u8
        })
        .collect()
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
        let a = medir(&alta).unwrap().sonoridad.unwrap();
        let b = medir(&baja).unwrap().sonoridad.unwrap();
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
    fn el_silencio_no_tiene_sonoridad_pero_si_forma_de_onda_plana() {
        let dir = std::env::temp_dir().join(format!("ns-silencio-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let ruta = dir.join("s.wav");
        let _ = wav(&ruta, 44_100, 44_100, |_, _| 0.0);
        let m = medir(&ruta).unwrap();
        assert_eq!(m.sonoridad, None);
        assert_eq!(m.picos, vec![0; PICOS]);
        let _ = std::fs::remove_dir_all(dir);
    }

    fn tono(i: usize, amplitud: f32) -> f32 {
        (2.0 * std::f32::consts::PI * 440.0 * i as f32 / 44_100.0).sin() * amplitud
    }

    #[test]
    fn los_picos_siguen_al_volumen_de_la_pista() {
        let dir = std::env::temp_dir().join(format!("ns-picos-sube-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let ruta = dir.join("sube.wav");
        let frames = 44_100 * 20;
        let _ = wav(&ruta, 44_100, frames, |i, _| {
            tono(i, 0.05 + 0.9 * i as f32 / frames as f32)
        });
        let m = medir(&ruta).unwrap();
        assert!(m.sonoridad.is_some(), "la misma pasada mide la sonoridad");
        assert_eq!(m.picos.len(), PICOS);
        // Cada décima parte sube respecto a la anterior.
        let decimos: Vec<u32> = m
            .picos
            .chunks(PICOS / 10)
            .map(|c| c.iter().map(|&v| u32::from(v)).max().unwrap())
            .collect();
        assert!(decimos.windows(2).all(|w| w[1] > w[0]), "{decimos:?}");
        assert!(decimos[0] < 50 && decimos[9] > 220, "{decimos:?}");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn un_silencio_en_medio_deja_sus_picos_a_cero() {
        let dir = std::env::temp_dir().join(format!("ns-picos-hueco-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let ruta = dir.join("hueco.wav");
        // 30 s: suena, 10 s de silencio entre el segundo 10 y el 20, y vuelve.
        let frames = 44_100 * 30;
        let _ = wav(&ruta, 44_100, frames, |i, _| {
            if (44_100 * 10..44_100 * 20).contains(&i) {
                0.0
            } else {
                tono(i, 0.6)
            }
        });
        let m = medir(&ruta).unwrap();
        // Lejos de los bordes del hueco, que comparten tramo con lo que suena.
        assert!(m.picos[350..650].iter().all(|&v| v == 0));
        assert!(m.picos[..320].iter().all(|&v| v > 140));
        assert!(m.picos[680..].iter().all(|&v| v > 140));
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn una_pista_mas_corta_que_los_picos_los_llena_todos() {
        let tramos = [0.5f32, 1.0, 0.0];
        let picos = reducir(&tramos);
        assert_eq!(picos.len(), PICOS);
        assert_eq!(picos[0], 128);
        assert_eq!(picos[PICOS / 2], 255);
        assert_eq!(picos[PICOS - 1], 0);
    }
}
