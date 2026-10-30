//! La huella acústica y AcoustID (F4.1.3).
//!
//! La huella la calcula `fpcalc` 1.6.2, que viaja dentro del instalador
//! (F0.4.6: `rusty-chromaprint` no da huellas idénticas). AcoustID devuelve las
//! grabaciones de MusicBrainz que suenan así, con su confianza; la V1
//! (`external/acoustid_client.py`) descartaba las de menos de 0,60 y la V2 también.

use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

use serde::Deserialize;

use crate::error::{NsError, NsResult};
use crate::net::{Red, Servicio};

/// `_SCORE_MINIMO` de la V1.
pub const CONFIANZA_MINIMA: f64 = 0.60;
/// `ACOUSTID_MAX_RETRIES` y la espera inicial de la V1, que se dobla.
const REINTENTOS: u32 = 3;
const ESPERA_INICIAL: Duration = Duration::from_secs(2);

/// La huella de un archivo y la duración que midió `fpcalc`.
#[derive(Debug, Clone, PartialEq)]
pub struct Huella {
    pub huella: String,
    pub duracion_seg: f64,
}

/// Dónde está `fpcalc`: junto al ejecutable, que es donde Tauri deja los binarios
/// de `externalBin`; si no, en el `PATH` (desarrollo).
pub fn ruta_fpcalc() -> PathBuf {
    let nombre = if cfg!(windows) {
        "fpcalc.exe"
    } else {
        "fpcalc"
    };
    std::env::current_exe()
        .ok()
        .and_then(|e| e.parent().map(|d| d.join(nombre)))
        .filter(|r| r.is_file())
        .unwrap_or_else(|| PathBuf::from(nombre))
}

#[derive(Deserialize)]
struct SalidaFpcalc {
    duration: f64,
    fingerprint: String,
}

/// # Errors
///
/// - [`NsError::ComponentUnavailable`] si `fpcalc` no se puede lanzar.
/// - [`NsError::AudioCorrupted`] si no saca huella del archivo.
pub fn calcular(fpcalc: &Path, archivo: &Path) -> NsResult<Huella> {
    let salida = Command::new(fpcalc)
        .arg("-json")
        .arg(archivo)
        .output()
        .map_err(|_| NsError::ComponentUnavailable)?;
    if !salida.status.success() {
        return Err(NsError::AudioCorrupted);
    }
    let s: SalidaFpcalc =
        serde_json::from_slice(&salida.stdout).map_err(|_| NsError::AudioCorrupted)?;
    if s.fingerprint.is_empty() || !s.duration.is_finite() || s.duration <= 0.0 {
        return Err(NsError::AudioCorrupted);
    }
    Ok(Huella {
        huella: s.fingerprint,
        duracion_seg: s.duration,
    })
}

/// Una grabación candidata y su confianza.
#[derive(Debug, Clone, PartialEq)]
pub struct Coincidencia {
    pub mbid_grabacion: String,
    pub confianza: f64,
}

#[derive(Deserialize)]
struct Respuesta {
    status: String,
    #[serde(default)]
    results: Vec<Resultado>,
}

#[derive(Deserialize)]
struct Resultado {
    score: f64,
    #[serde(default)]
    recordings: Vec<Grabacion>,
}

#[derive(Deserialize)]
struct Grabacion {
    id: String,
}

/// Las grabaciones de una respuesta, sin repetir y por encima del umbral, en el
/// orden de AcoustID (`_extraer_resultados_lookup`).
///
/// # Errors
///
/// [`NsError::NetworkFailure`] si la respuesta no es la esperada o trae un error.
pub fn interpretar(cuerpo: &[u8]) -> NsResult<Vec<Coincidencia>> {
    let r: Respuesta = serde_json::from_slice(cuerpo).map_err(|_| NsError::NetworkFailure)?;
    if r.status != "ok" {
        return Err(NsError::NetworkFailure);
    }
    let mut salida: Vec<Coincidencia> = Vec::new();
    for res in r.results.iter().filter(|r| r.score >= CONFIANZA_MINIMA) {
        for g in &res.recordings {
            if !g.id.is_empty() && !salida.iter().any(|c| c.mbid_grabacion == g.id) {
                salida.push(Coincidencia {
                    mbid_grabacion: g.id.clone(),
                    confianza: res.score,
                });
            }
        }
    }
    Ok(salida)
}

/// Pregunta a AcoustID por una huella, con los reintentos de la V1 ante fallos de
/// red. Sin consentimiento o sin red no reintenta: no va a cambiar.
///
/// # Errors
///
/// Los de [`Red::obtener`] y [`interpretar`].
pub fn consultar(red: &Red, clave: &str, h: &Huella) -> NsResult<Vec<Coincidencia>> {
    let url = format!(
        "https://api.acoustid.org/v2/lookup?format=json&meta=recordingids&client={}&duration={}&fingerprint={}",
        clave,
        h.duracion_seg as u64,
        h.huella
    );
    let mut espera = ESPERA_INICIAL;
    let mut intento = 0;
    loop {
        match red.obtener(Servicio::AcoustId, &url, &[]) {
            Ok(cuerpo) => return interpretar(&cuerpo),
            Err(NsError::NetworkFailure) if intento < REINTENTOS => {
                std::thread::sleep(espera);
                espera *= 2;
                intento += 1;
            }
            Err(e) => return Err(e),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn se_quedan_las_grabaciones_seguras_sin_repetir() {
        let cuerpo = br#"{"status": "ok", "results": [
            {"id": "a", "score": 0.97, "recordings": [{"id": "r1"}, {"id": "r2"}]},
            {"id": "b", "score": 0.81, "recordings": [{"id": "r2"}, {"id": "r3"}]},
            {"id": "c", "score": 0.40, "recordings": [{"id": "r4"}]},
            {"id": "d", "score": 0.90}
        ]}"#;
        let c = interpretar(cuerpo).unwrap();
        assert_eq!(
            c.iter()
                .map(|x| (x.mbid_grabacion.as_str(), x.confianza))
                .collect::<Vec<_>>(),
            [("r1", 0.97), ("r2", 0.97), ("r3", 0.81)]
        );
    }

    #[test]
    fn una_respuesta_de_error_no_se_toma_por_vacia() {
        let cuerpo = br#"{"status": "error", "error": {"code": 4, "message": "invalid API key"}}"#;
        assert_eq!(interpretar(cuerpo), Err(NsError::NetworkFailure));
        assert_eq!(
            interpretar(br#"{"status": "ok", "results": []}"#),
            Ok(vec![])
        );
    }

    #[test]
    fn sin_consentimiento_no_sale_ni_reintenta() {
        let red = Red::new(crate::net::PoliticaDeRed::default());
        let h = Huella {
            huella: "AQAA".into(),
            duracion_seg: 200.0,
        };
        let antes = std::time::Instant::now();
        assert_eq!(consultar(&red, "k", &h), Err(NsError::NetworkDisabled));
        assert!(antes.elapsed() < Duration::from_secs(1));
    }

    #[test]
    fn sin_fpcalc_el_componente_no_esta() {
        let r = calcular(Path::new("/no/existe/fpcalc"), Path::new("x.mp3"));
        assert_eq!(r, Err(NsError::ComponentUnavailable));
    }

    /// Con el `fpcalc` que descarga `fetch-binarios` (se salta si no está).
    #[test]
    fn fpcalc_saca_la_huella_de_un_archivo() {
        let triple = if cfg!(all(target_os = "linux", target_arch = "x86_64")) {
            "x86_64-unknown-linux-gnu"
        } else {
            return;
        };
        let fpcalc =
            Path::new(env!("CARGO_MANIFEST_DIR")).join(format!("binarios/fpcalc-{triple}"));
        if !fpcalc.is_file() {
            return;
        }
        let dir = std::env::temp_dir().join(format!("ns-fpcalc-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let ruta = dir.join("tono.wav");
        let _ = crate::audio::pruebas::wav(&ruta, 44_100, 44_100 * 12, |i, _| {
            let t = i as f32 / 44_100.0;
            ((2.0 * std::f32::consts::PI * 440.0 * t).sin()
                + (2.0 * std::f32::consts::PI * 660.0 * t * (1.0 + t / 10.0)).sin())
                * 0.2
        });
        let h = calcular(&fpcalc, &ruta).unwrap();
        assert!((h.duracion_seg - 12.0).abs() < 0.1, "{}", h.duracion_seg);
        assert!(
            h.huella.starts_with("AQ"),
            "huella comprimida de Chromaprint"
        );
        assert_eq!(
            calcular(&fpcalc, &ruta).unwrap(),
            h,
            "la misma huella cada vez"
        );
        std::fs::write(dir.join("roto.mp3"), b"nada").unwrap();
        assert_eq!(
            calcular(&fpcalc, &dir.join("roto.mp3")),
            Err(NsError::AudioCorrupted)
        );
    }
}
