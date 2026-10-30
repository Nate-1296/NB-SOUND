//! Prototipo F0.4.6: ¿`rusty-chromaprint` da la misma huella que `fpcalc`?
//!
//! Código desechable. Para cada archivo calcula la huella de los primeros 120 s
//! (lo mismo que `fpcalc` por defecto) con el algoritmo 2 y la compara con la de
//! `fpcalc -raw -json`: huella cruda y huella comprimida que se envía a AcoustID.
//!
//! Uso: cargo run --release -- <fpcalc> <archivo>...

mod decodificar;

use std::path::Path;
use std::process::Command;

use rusty_chromaprint::{Configuration, Fingerprinter, FingerprintCompressor};

fn base64_url(datos: &[u8]) -> String {
    // El alfabeto de chromaprint: base64 URL sin relleno.
    const A: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut s = String::new();
    for trozo in datos.chunks(3) {
        let b = [trozo[0], *trozo.get(1).unwrap_or(&0), *trozo.get(2).unwrap_or(&0)];
        let n = (b[0] as u32) << 16 | (b[1] as u32) << 8 | b[2] as u32;
        let chars = [(n >> 18) & 63, (n >> 12) & 63, (n >> 6) & 63, n & 63];
        for c in chars.iter().take(trozo.len() + 1) {
            s.push(A[*c as usize] as char);
        }
    }
    s
}

fn campo<'a>(json: &'a str, nombre: &str) -> &'a str {
    let i = json.find(&format!("\"{nombre}\"")).expect("campo");
    let resto = &json[i + nombre.len() + 2..];
    let resto = resto.trim_start_matches([':', ' ']);
    let fin = resto.find(['}', '\n']).unwrap_or(resto.len());
    resto[..fin].trim().trim_end_matches(',').trim_matches('"')
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let fpcalc = &args[1];
    let config = Configuration::preset_test2();
    let (mut iguales_crudo, mut iguales_comprimido, mut total) = (0, 0, 0);
    let mut parecido_min = 1.0f64;
    for archivo in &args[2..] {
        let pcm = decodificar::decodificar(Path::new(archivo), None).expect("decodificar");
        let n = (pcm.tasa as usize * 120).min(pcm.frames()) * 2;
        let muestras: Vec<i16> = pcm.muestras[..n]
            .iter()
            .map(|s| (s.clamp(-1.0, 1.0) * 32767.0).round() as i16)
            .collect();
        let mut f = Fingerprinter::new(&config);
        f.start(pcm.tasa, 2).expect("start");
        f.consume(&muestras);
        f.finish();
        let propia = f.fingerprint().to_vec();
        let comprimida = base64_url(&FingerprintCompressor::from(&config).compress(&propia));

        let crudo = Command::new(fpcalc).args(["-raw", "-json", archivo]).output().expect("fpcalc");
        let crudo = String::from_utf8_lossy(&crudo.stdout).to_string();
        let ref_crudo: Vec<u32> = campo(&crudo, "fingerprint")
            .trim_matches(['[', ']'])
            .split(',')
            .filter_map(|x| x.trim().parse().ok())
            .collect();
        let comp = Command::new(fpcalc).args(["-json", archivo]).output().expect("fpcalc");
        let comp = String::from_utf8_lossy(&comp.stdout).to_string();
        let ref_comp = campo(&comp, "fingerprint").to_string();

        // Parecido: fracción de bits iguales en las posiciones comunes.
        let comunes = propia.len().min(ref_crudo.len());
        let bits_distintos: u32 = propia
            .iter()
            .zip(&ref_crudo)
            .map(|(a, b)| (a ^ b).count_ones())
            .sum();
        let parecido = 1.0 - bits_distintos as f64 / (comunes as f64 * 32.0);
        parecido_min = parecido_min.min(parecido);
        total += 1;
        if propia == ref_crudo {
            iguales_crudo += 1;
        }
        if comprimida == ref_comp {
            iguales_comprimido += 1;
        }
        println!(
            "{:>4} vs {:>4} valores | bits iguales {:6.2} % | crudo {} | comprimido {}",
            propia.len(),
            ref_crudo.len(),
            parecido * 100.0,
            if propia == ref_crudo { "igual" } else { "distinto" },
            if comprimida == ref_comp { "igual" } else { "distinto" }
        );
    }
    println!(
        "{total} archivos: crudo idéntico en {iguales_crudo}, comprimido idéntico en {iguales_comprimido}; parecido mínimo {:.2} %",
        parecido_min * 100.0
    );
}
