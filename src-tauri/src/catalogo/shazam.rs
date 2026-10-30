//! Shazam (F4.1.5): la firma acústica, la consulta y su respuesta.
//!
//! La V1 usaba `shazamio`, cuyo núcleo (`shazamio-core`) es la firma de
//! `songrec`. Aquí está portada de `songrec` 0.8 (GPL-3.0+, como NB Sound):
//! `core/fingerprinting/algorithm.rs` y `signature_format.rs`. Es una API no
//! oficial (ADR-009): si cambia, Shazam deja de identificar y la catalogación
//! sigue con las demás fuentes.
//!
//! La firma se hace sobre 12 s del centro de la pista, en mono a 16 kHz: FFT de
//! 2048 con ventana de Hann cada 128 muestras, picos que se extienden en
//! frecuencia y en tiempo, y los que sobreviven se guardan por bandas.

use std::path::Path;
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use rustfft::num_complex::Complex;
use rustfft::{Fft, FftPlanner};
use serde_json::Value;
use tokio_rustls::rustls::crypto::ring::default_provider;

use super::modelo::DeShazam;
use super::texto::normalizar_isrc;
use crate::error::{NsError, NsResult};
use crate::net::{Red, Servicio};

const TASA: u32 = 16_000;
/// La ventana que mandan los clientes de Shazam y la que usaba la V1
/// (`shazamio`, `WINDOW_SECONDS`): 10 s del centro. `songrec` usa 12.
const VENTANA_SEG: f64 = 10.0;
#[cfg(test)]
const MUESTRAS: usize = 12 * TASA as usize;
/// `SHAZAM_MIN_DURACION_SEG` de la V1: no se manda nada más corto.
pub const DURACION_MINIMA_SEG: f64 = 20.0;

/// Un pico: en qué pasada de FFT, con qué magnitud y en qué frecuencia (en
/// sesenta y cuatroavos de bin).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Pico {
    pub pasada: u32,
    pub magnitud: u16,
    pub bin: u16,
}

/// La firma, con los picos de cada una de las cuatro bandas.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Firma {
    pub muestras: u32,
    pub bandas: [Vec<Pico>; 4],
}

/// Hann de 2048 sin los ceros de los extremos: la tabla de `songrec` es
/// `sin²(π(i+1)/2049)` redondeada.
fn hann() -> Vec<f32> {
    (0..2048)
        .map(|i| {
            let x = (std::f64::consts::PI * (i as f64 + 1.0) / 2049.0).sin();
            (x * x) as f32
        })
        .collect()
}

struct Generador {
    anillo: [i16; 2048],
    indice_anillo: usize,
    ventana: Vec<f32>,
    fft: Arc<dyn Fft<f32>>,
    tampon: Vec<Complex<f32>>,
    salidas: Vec<[f32; 1025]>,
    indice_salidas: u8,
    extendidas: Vec<[f32; 1025]>,
    indice_extendidas: u8,
    hechas: u32,
    bandas: [Vec<Pico>; 4],
}

impl Generador {
    fn nuevo() -> Self {
        Self {
            anillo: [0; 2048],
            indice_anillo: 0,
            ventana: hann(),
            fft: FftPlanner::<f32>::new().plan_fft_forward(2048),
            tampon: vec![Complex::new(0.0, 0.0); 2048],
            salidas: vec![[0.0; 1025]; 256],
            indice_salidas: 0,
            extendidas: vec![[0.0; 1025]; 256],
            indice_extendidas: 0,
            hechas: 0,
            bandas: Default::default(),
        }
    }

    fn fft(&mut self, bloque: &[i16; 128]) {
        self.anillo[self.indice_anillo..self.indice_anillo + 128].copy_from_slice(bloque);
        self.indice_anillo = (self.indice_anillo + 128) & 2047;
        for (i, m) in self.ventana.iter().enumerate() {
            let x = f32::from(self.anillo[(i + self.indice_anillo) & 2047]) * m;
            self.tampon[i] = Complex::new(x, 0.0);
        }
        self.fft.process(&mut self.tampon);
        let salida = &mut self.salidas[self.indice_salidas as usize];
        for (r, c) in salida.iter_mut().zip(self.tampon.iter()) {
            *r = ((c.re * c.re + c.im * c.im) / (1u32 << 17) as f32).max(0.000_000_000_1);
        }
        self.indice_salidas = self.indice_salidas.wrapping_add(1);
    }

    fn extender(&mut self) {
        let mut e = self.salidas[self.indice_salidas.wrapping_sub(1) as usize];
        for p in 0..=1022 {
            e[p] = e[p].max(e[p + 1]).max(e[p + 2]);
        }
        self.extendidas[self.indice_extendidas as usize] = e;
        for p in 0..=1024 {
            for anterior in [1u8, 3, 6] {
                let otra =
                    &mut self.extendidas[self.indice_extendidas.wrapping_sub(anterior) as usize];
                otra[p] = otra[p].max(e[p]);
            }
        }
        self.indice_extendidas = self.indice_extendidas.wrapping_add(1);
    }

    fn reconocer(&mut self) {
        let f46 = self.salidas[self.indice_salidas.wrapping_sub(46) as usize];
        let f49 = self.extendidas[self.indice_extendidas.wrapping_sub(49) as usize];
        let magnitud = |x: f32| x.ln().max(1.0 / 64.0) * 1477.3 + 6144.0;
        for bin in 10..=1014usize {
            if !(f46[bin] >= 1.0 / 64.0 && f46[bin] >= f49[bin - 1]) {
                continue;
            }
            let mut vecino = 0.0f32;
            for d in [-10i32, -7, -4, -3, 1, 2, 5, 8] {
                vecino = vecino.max(f49[(bin as i32 + d) as usize]);
            }
            if f46[bin] <= vecino {
                continue;
            }
            let mut otros = vecino;
            for d in [
                -53i32, -45, 165, 172, 179, 186, 193, 200, 214, 221, 228, 235, 242, 249,
            ] {
                let o = &self.extendidas[((i32::from(self.indice_extendidas) + d) & 255) as usize];
                otros = otros.max(o[bin - 1]);
            }
            if f46[bin] <= otros {
                continue;
            }
            let (m, antes, despues) = (
                magnitud(f46[bin]),
                magnitud(f46[bin - 1]),
                magnitud(f46[bin + 1]),
            );
            let v1 = m * 2.0 - antes - despues;
            let v2 = (despues - antes) * 32.0 / v1;
            let corregido = ((bin as i32 * 64) + v2 as i32) as u16;
            let hz = f32::from(corregido) * (16_000.0 / 2.0 / 1024.0 / 64.0);
            let banda = match hz as i32 {
                250..=519 => 0,
                520..=1449 => 1,
                1450..=3499 => 2,
                3500..=5500 => 3,
                _ => continue,
            };
            self.bandas[banda].push(Pico {
                pasada: self.hechas - 46,
                magnitud: m as u16,
                bin: corregido,
            });
        }
    }
}

/// La firma de unas muestras mono a 16 kHz, en [-1, 1].
pub fn firma_de(muestras: &[f32]) -> Firma {
    let mut g = Generador::nuevo();
    let s16: Vec<i16> = muestras
        .iter()
        .map(|x| (x * 32_768.0).clamp(-32_768.0, 32_767.0) as i16)
        .collect();
    for bloque in s16.as_chunks::<128>().0 {
        g.fft(bloque);
        g.extender();
        g.hechas += 1;
        if g.hechas >= 46 {
            g.reconocer();
        }
    }
    Firma {
        muestras: muestras.len() as u32,
        bandas: g.bandas,
    }
}

/// La firma de una pista: la ventana del centro, o la pista entera si es más corta.
///
/// # Errors
///
/// Los de [`crate::audio::remuestreo::mono`].
pub fn firma(ruta: &Path, duracion_seg: f64) -> NsResult<Firma> {
    let desde = (duracion_seg / 2.0 - VENTANA_SEG / 2.0).max(0.0);
    let m = crate::audio::remuestreo::mono(ruta, TASA, desde, VENTANA_SEG)?;
    Ok(firma_de(&m))
}

fn crc32(datos: &[u8]) -> u32 {
    let mut c = 0xffff_ffffu32;
    for b in datos {
        c ^= u32::from(*b);
        for _ in 0..8 {
            c = if c & 1 != 0 {
                (c >> 1) ^ 0xedb8_8320
            } else {
                c >> 1
            };
        }
    }
    !c
}

fn base64(bytes: &[u8]) -> String {
    const A: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut s = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for t in bytes.chunks(3) {
        let n = t
            .iter()
            .enumerate()
            .fold(0u32, |n, (i, b)| n | u32::from(*b) << (16 - 8 * i));
        for i in 0..4 {
            if i <= t.len() {
                s.push(A[(n >> (18 - 6 * i) & 63) as usize] as char);
            } else {
                s.push('=');
            }
        }
    }
    s
}

impl Firma {
    /// El binario de Shazam (`encode_to_binary`): cabecera de 48 bytes con su
    /// CRC-32 y, por banda, los picos con su pasada en diferencia.
    pub fn binario(&self) -> Vec<u8> {
        let mut b: Vec<u8> = Vec::with_capacity(1024);
        let u32le = |b: &mut Vec<u8>, x: u32| b.extend_from_slice(&x.to_le_bytes());
        u32le(&mut b, 0xcafe_2580);
        u32le(&mut b, 0);
        u32le(&mut b, 0);
        u32le(&mut b, 0x9411_9c00);
        for _ in 0..3 {
            u32le(&mut b, 0);
        }
        u32le(&mut b, 3 << 27);
        u32le(&mut b, 0);
        u32le(&mut b, 0);
        u32le(&mut b, self.muestras + (TASA as f32 * 0.24) as u32);
        u32le(&mut b, (15 << 19) + 0x40000);
        u32le(&mut b, 0x4000_0000);
        u32le(&mut b, 0);
        for (banda, picos) in self.bandas.iter().enumerate() {
            if picos.is_empty() {
                continue;
            }
            let mut p: Vec<u8> = Vec::new();
            let mut pasada = 0u32;
            for pico in picos {
                if pico.pasada - pasada >= 255 {
                    p.push(0xff);
                    p.extend_from_slice(&pico.pasada.to_le_bytes());
                    pasada = pico.pasada;
                }
                p.push((pico.pasada - pasada) as u8);
                p.extend_from_slice(&pico.magnitud.to_le_bytes());
                p.extend_from_slice(&pico.bin.to_le_bytes());
                pasada = pico.pasada;
            }
            u32le(&mut b, 0x6003_0040 + banda as u32);
            u32le(&mut b, p.len() as u32);
            b.extend_from_slice(&p);
            b.resize(b.len() + (4 - p.len() % 4) % 4, 0);
        }
        let tamano = (b.len() - 48) as u32;
        b[8..12].copy_from_slice(&tamano.to_le_bytes());
        b[52..56].copy_from_slice(&tamano.to_le_bytes());
        let crc = crc32(&b[8..]);
        b[4..8].copy_from_slice(&crc.to_le_bytes());
        b
    }

    pub fn uri(&self) -> String {
        format!(
            "data:audio/vnd.shazam.sig;base64,{}",
            base64(&self.binario())
        )
    }
}

fn uuid_v4() -> NsResult<String> {
    let mut b = [0u8; 16];
    default_provider()
        .secure_random
        .fill(&mut b)
        .map_err(|_| NsError::Internal)?;
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    let h: String = b.iter().map(|x| format!("{x:02x}")).collect();
    Ok(format!(
        "{}-{}-{}-{}-{}",
        &h[0..8],
        &h[8..12],
        &h[12..16],
        &h[16..20],
        &h[20..32]
    ))
}

/// Lo que contesta Shazam, como lo leía la V1 (`_identificar_async`).
pub fn interpretar(r: &Value) -> DeShazam {
    let Some(t) = r.get("track") else {
        return DeShazam::default();
    };
    let s = |v: &Value, k: &str| {
        v.get(k)
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_owned()
    };
    let mut d = DeShazam {
        titulo: s(t, "title"),
        artista: s(t, "subtitle"),
        isrc: t
            .get("isrc")
            .and_then(Value::as_str)
            .and_then(normalizar_isrc),
        ..DeShazam::default()
    };
    for seccion in t
        .get("sections")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        if seccion.get("type").and_then(Value::as_str) != Some("SONG") {
            continue;
        }
        for meta in seccion
            .get("metadata")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            let titulo = s(meta, "title").to_lowercase();
            let texto = s(meta, "text");
            if texto.is_empty() {
                continue;
            }
            if titulo.contains("album") {
                d.album = Some(texto);
            } else if titulo.contains("released") {
                d.anio = texto.get(..4).and_then(|a| a.parse().ok());
            }
        }
    }
    d.identificado = !d.titulo.is_empty() || !d.artista.is_empty();
    d
}

/// Pregunta a Shazam por una pista. Las de menos de 20 s no se mandan.
///
/// # Errors
///
/// Los de [`firma`] y de [`Red::enviar_json`].
pub fn identificar(red: &Red, ruta: &Path, duracion_seg: f64) -> NsResult<DeShazam> {
    if duracion_seg < DURACION_MINIMA_SEG {
        return Ok(DeShazam::default());
    }
    let f = firma(ruta, duracion_seg)?;
    let ahora = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u32;
    let cuerpo = serde_json::json!({
        "geolocation": {"altitude": 300, "latitude": 45, "longitude": 2},
        "signature": {
            "samplems": (f.muestras as f32 / TASA as f32 * 1000.0) as u32,
            "timestamp": ahora,
            "uri": f.uri(),
        },
        "timestamp": ahora,
        "timezone": "Europe/Paris",
    });
    let url = format!(
        "https://amp.shazam.com/discovery/v5/en/US/android/-/tag/{}/{}?sync=true&webv3=true&sampling=true&connected=&shazamapiversion=v3&sharehub=true&video=v3",
        uuid_v4()?.to_uppercase(),
        uuid_v4()?
    );
    let (estado, r) = red.enviar_json(
        Servicio::Shazam,
        &url,
        &[
            ("Content-Language", "en_US"),
            (
                "User-Agent",
                "Dalvik/2.1.0 (Linux; U; Android 6.0.1; SM-G920F Build/MMB29K)",
            ),
        ],
        cuerpo.to_string().as_bytes(),
    )?;
    if !(200..300).contains(&estado) {
        return Err(NsError::NetworkFailure);
    }
    let v: Value = serde_json::from_slice(&r).map_err(|_| NsError::NetworkFailure)?;
    Ok(interpretar(&v))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn la_ventana_es_la_tabla_de_songrec() {
        let h = hann();
        assert!((h[0] - 0.000_002_350_8).abs() < 1e-9);
        assert!((h[3] - 0.000_037_612).abs() < 1e-8);
        assert!((h[1023] - 1.0).abs() < 1e-5);
    }

    #[test]
    fn el_crc_y_el_base64_son_los_estandar() {
        assert_eq!(crc32(b"123456789"), 0xcbf4_3926);
        assert_eq!(base64(b"foobar"), "Zm9vYmFy");
        assert_eq!(base64(b"fooba"), "Zm9vYmE=");
        assert_eq!(base64(b"foob"), "Zm9vYg==");
    }

    fn tonos() -> Vec<f32> {
        (0..MUESTRAS)
            .map(|i| {
                let t = i as f32 / TASA as f32;
                // Notas que cambian cada medio segundo, en las cuatro bandas.
                let nota = [330.0, 660.0, 1200.0, 2500.0, 4200.0, 900.0][(t * 2.0) as usize % 6];
                (2.0 * std::f32::consts::PI * nota * t).sin() * 0.4
                    + (2.0 * std::f32::consts::PI * nota * 1.5 * t).sin() * 0.2
            })
            .collect()
    }

    #[test]
    fn la_firma_encuentra_picos_en_las_bandas_de_lo_que_suena() {
        let f = firma_de(&tonos());
        assert_eq!(f.muestras, MUESTRAS as u32);
        for (i, b) in f.bandas.iter().enumerate() {
            assert!(!b.is_empty(), "banda {i} vacía");
            assert!(b.windows(2).all(|w| w[0].pasada <= w[1].pasada));
        }
        let silencio = firma_de(&[0.0; MUESTRAS]);
        assert!(silencio.bandas.iter().all(Vec::is_empty));
    }

    #[test]
    fn el_binario_lleva_su_cabecera_y_su_crc() {
        let f = firma_de(&tonos());
        let b = f.binario();
        assert_eq!(&b[0..4], &0xcafe_2580u32.to_le_bytes());
        let tamano = u32::from_le_bytes(b[8..12].try_into().unwrap()) as usize;
        assert_eq!(tamano, b.len() - 48);
        assert_eq!(
            u32::from_le_bytes(b[4..8].try_into().unwrap()),
            crc32(&b[8..])
        );
        assert_eq!(b.len() % 4, 0);
        assert!(f.uri().starts_with("data:audio/vnd.shazam.sig;base64,gCX+"));
    }

    #[test]
    fn la_respuesta_se_lee_como_en_la_v1() {
        let r = serde_json::json!({"track": {"title": " Despacito ", "subtitle": "Luis Fonsi",
            "isrc": "USUM71700626",
            "sections": [{"type": "SONG", "metadata": [
                {"title": "Album", "text": "VIDA"}, {"title": "Released", "text": "2017"}]}]}});
        let d = interpretar(&r);
        assert!(d.identificado);
        assert_eq!(
            (d.titulo.as_str(), d.artista.as_str()),
            ("Despacito", "Luis Fonsi")
        );
        assert_eq!(
            (d.album.as_deref(), d.anio, d.isrc.as_deref()),
            (Some("VIDA"), Some(2017), Some("USUM71700626"))
        );
        assert!(!interpretar(&serde_json::json!({"matches": []})).identificado);
    }

    #[test]
    fn el_uuid_es_de_la_version_4() {
        let u = uuid_v4().unwrap();
        assert_eq!(u.len(), 36);
        assert_eq!(&u[14..15], "4");
    }

    /// Contra `shazamio_core` de la V1 sobre un archivo local (`NS_SHAZAM_ARCHIVO` y
    /// `NS_SHAZAM_PICOS`, los bytes de cada banda que dio la V1, separados por
    /// comas). El remuestreo no es el mismo, así que se pide parecido, no igual.
    #[test]
    #[ignore = "necesita un archivo local"]
    fn la_firma_de_un_archivo_se_parece_a_la_de_la_v1() {
        let (Ok(ruta), Ok(v1)) = (
            std::env::var("NS_SHAZAM_ARCHIVO"),
            std::env::var("NS_SHAZAM_PICOS"),
        ) else {
            return;
        };
        let (t, _) = crate::catalogo::etiquetas::leer(Path::new(&ruta)).unwrap();
        let f = firma(Path::new(&ruta), t.duracion_seg).unwrap();
        let nuestros: Vec<usize> = f.bandas.iter().map(|b| b.len() * 5).collect();
        let suyos: Vec<usize> = v1.split(',').map(|x| x.parse().unwrap()).collect();
        eprintln!(
            "bytes por banda: V2 {nuestros:?}, V1 {suyos:?}, muestras {}",
            f.muestras
        );
        for (a, b) in nuestros.iter().zip(&suyos) {
            let (a, b) = (*a as f64, *b as f64);
            assert!(
                (a - b).abs() / b.max(1.0) < 0.25,
                "{nuestros:?} frente a {suyos:?}"
            );
        }
    }
}
