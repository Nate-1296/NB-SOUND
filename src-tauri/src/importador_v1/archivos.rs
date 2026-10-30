//! Copias de archivos de la V1 a las carpetas de la V2.
//!
//! El importador nunca mueve ni enlaza: copia. La V1 sigue funcionando mientras
//! la V2 madura (ADR-004), y un enlace duro haría que una escritura de una
//! versión cambiara el archivo de la otra.

use std::fs::File;
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};

use sha2::{Digest, Sha256};

use crate::error::{NsError, NsResult};

/// Un archivo ya en su sitio dentro de la V2.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Copiado {
    pub sha256: String,
    /// Relativa a la carpeta de destino, con `/` en todas las plataformas.
    pub relativa: String,
    pub bytes: u64,
}

const BLOQUE: usize = 256 * 1024;

fn hex(bytes: &[u8]) -> String {
    use std::fmt::Write as _;
    bytes.iter().fold(String::with_capacity(64), |mut s, b| {
        let _ = write!(s, "{b:02x}");
        s
    })
}

/// SHA-256 de un archivo, leyéndolo por bloques.
///
/// # Errors
///
/// El de E/S si no se puede leer.
pub fn sha256_de(ruta: &Path) -> io::Result<String> {
    let mut archivo = File::open(ruta)?;
    let mut hash = Sha256::new();
    let mut bloque = vec![0u8; BLOQUE];
    loop {
        let n = archivo.read(&mut bloque)?;
        if n == 0 {
            break;
        }
        hash.update(&bloque[..n]);
    }
    Ok(hex(&hash.finalize()))
}

/// Copia `origen` a `destino/ab/abcdef….ext`, con su SHA-256 por nombre. Lee el
/// origen una sola vez: calcula el hash mientras copia a un temporal, y lo
/// renombra al final. Si ya había un archivo con ese contenido, se queda el que
/// estaba: copiar dos veces la misma portada no duplica nada.
///
/// # Errors
///
/// - [`NsError::FileNotFound`] si el origen no existe.
/// - [`NsError::StorageFailure`] si no se puede leer o escribir.
pub fn copiar_por_contenido(origen: &Path, destino: &Path, extension: &str) -> NsResult<Copiado> {
    let mut entrada = File::open(origen).map_err(|error| match error.kind() {
        io::ErrorKind::NotFound => NsError::FileNotFound,
        _ => {
            tracing::warn!(error = %error, "no se pudo abrir un archivo de la V1");
            NsError::StorageFailure
        }
    })?;
    std::fs::create_dir_all(destino).map_err(|_| NsError::StorageFailure)?;
    let temporal = destino.join(format!(
        ".copiando-{}-{}",
        std::process::id(),
        CONTADOR.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
    ));
    let resultado = (|| -> io::Result<(String, u64)> {
        let mut salida = File::create(&temporal)?;
        let mut hash = Sha256::new();
        let mut bloque = vec![0u8; BLOQUE];
        let mut bytes = 0u64;
        loop {
            let n = entrada.read(&mut bloque)?;
            if n == 0 {
                break;
            }
            hash.update(&bloque[..n]);
            salida.write_all(&bloque[..n])?;
            bytes += n as u64;
        }
        salida.sync_all()?;
        Ok((hex(&hash.finalize()), bytes))
    })();
    let (sha256, bytes) = resultado.map_err(|error| {
        let _ = std::fs::remove_file(&temporal);
        tracing::warn!(error = %error, "no se pudo copiar un archivo de la V1");
        NsError::StorageFailure
    })?;

    let relativa = format!("{}/{sha256}.{extension}", &sha256[..2]);
    let final_ = destino.join(&relativa);
    if final_.is_file() {
        let _ = std::fs::remove_file(&temporal);
    } else {
        let colocar = final_
            .parent()
            .map_or(Ok(()), std::fs::create_dir_all)
            .and_then(|()| std::fs::rename(&temporal, &final_));
        if let Err(error) = colocar {
            let _ = std::fs::remove_file(&temporal);
            tracing::warn!(error = %error, "no se pudo dejar en su sitio un archivo copiado");
            return Err(NsError::StorageFailure);
        }
    }
    Ok(Copiado {
        sha256,
        relativa,
        bytes,
    })
}

static CONTADOR: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

/// Ruta absoluta de un [`Copiado`] dentro de su carpeta.
pub fn absoluta(destino: &Path, copiado: &Copiado) -> PathBuf {
    destino.join(&copiado.relativa)
}

/// Ancho, alto y tipo MIME de una imagen JPEG o PNG, leyendo solo su cabecera.
/// Basta para las portadas de la V1, que son todas JPEG o PNG; decodificar la
/// imagen entera para saber su tamaño costaría segundos por cada mil portadas.
pub fn dimensiones(ruta: &Path) -> Option<(u32, u32, &'static str)> {
    let mut archivo = File::open(ruta).ok()?;
    // Las cabeceras EXIF de una portada pueden ocupar decenas de KB antes del
    // marcador de tamaño; 512 KB cubre el máximo que admite un segmento APP.
    let mut cabecera = Vec::with_capacity(64 * 1024);
    Read::take(&mut archivo, 512 * 1024)
        .read_to_end(&mut cabecera)
        .ok()?;
    dimensiones_de(&cabecera)
}

/// Lo mismo que [`dimensiones`] sobre los bytes ya leídos.
pub fn dimensiones_de(b: &[u8]) -> Option<(u32, u32, &'static str)> {
    const PNG: &[u8] = b"\x89PNG\r\n\x1a\n";
    if b.starts_with(PNG) && b.get(12..16) == Some(b"IHDR") {
        let ancho = u32::from_be_bytes(b.get(16..20)?.try_into().ok()?);
        let alto = u32::from_be_bytes(b.get(20..24)?.try_into().ok()?);
        return (ancho > 0 && alto > 0).then_some((ancho, alto, "image/png"));
    }
    if !b.starts_with(&[0xFF, 0xD8]) {
        return None;
    }
    let mut i = 2;
    while i + 4 <= b.len() {
        if b[i] != 0xFF {
            return None;
        }
        let marcador = b[i + 1];
        // Relleno entre marcadores.
        if marcador == 0xFF {
            i += 1;
            continue;
        }
        // Marcadores sin longitud.
        if marcador == 0xD8 || (0xD0..=0xD7).contains(&marcador) || marcador == 0x01 {
            i += 2;
            continue;
        }
        let longitud = usize::from(u16::from_be_bytes([b[i + 2], b[i + 3]]));
        // SOF0 a SOF15, salvo DHT (C4), JPG (C8) y DAC (CC), que comparten rango.
        let es_sof = (0xC0..=0xCF).contains(&marcador) && !matches!(marcador, 0xC4 | 0xC8 | 0xCC);
        if es_sof {
            let alto = u32::from(u16::from_be_bytes([*b.get(i + 5)?, *b.get(i + 6)?]));
            let ancho = u32::from(u16::from_be_bytes([*b.get(i + 7)?, *b.get(i + 8)?]));
            return (ancho > 0 && alto > 0).then_some((ancho, alto, "image/jpeg"));
        }
        if marcador == 0xDA || longitud < 2 {
            // Empieza la imagen sin haber visto el tamaño: no es un JPEG válido.
            return None;
        }
        i += 2 + longitud;
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temporal(nombre: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("ns-archivos-{nombre}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    /// Un PNG mínimo de 3 × 2 píxeles: firma y la parte de IHDR que se lee.
    fn png(ancho: u32, alto: u32) -> Vec<u8> {
        let mut b = b"\x89PNG\r\n\x1a\n\0\0\0\x0dIHDR".to_vec();
        b.extend(ancho.to_be_bytes());
        b.extend(alto.to_be_bytes());
        b.extend([8, 2, 0, 0, 0]);
        b
    }

    /// Un JPEG con un segmento APP1 delante del SOF0, como los que llevan EXIF.
    fn jpeg(ancho: u16, alto: u16) -> Vec<u8> {
        let mut b = vec![0xFF, 0xD8, 0xFF, 0xE1, 0x00, 0x08];
        b.extend(b"Exif\0\0");
        b.extend([0xFF, 0xC0, 0x00, 0x11, 0x08]);
        b.extend(alto.to_be_bytes());
        b.extend(ancho.to_be_bytes());
        b.extend([0x03; 10]);
        b.extend([0xFF, 0xDA]);
        b
    }

    #[test]
    fn las_dimensiones_salen_de_la_cabecera_de_png_y_jpeg() {
        assert_eq!(dimensiones_de(&png(3, 2)), Some((3, 2, "image/png")));
        assert_eq!(
            dimensiones_de(&jpeg(1200, 1199)),
            Some((1200, 1199, "image/jpeg"))
        );
        assert_eq!(dimensiones_de(b"GIF89a"), None);
        assert_eq!(dimensiones_de(&[0xFF, 0xD8, 0xFF, 0xDA, 0, 2]), None);
    }

    #[test]
    fn el_mismo_contenido_se_copia_una_sola_vez() {
        let dir = temporal("contenido");
        let (a, b) = (dir.join("a.jpg"), dir.join("b.jpg"));
        std::fs::write(&a, b"la misma portada").unwrap();
        std::fs::write(&b, b"la misma portada").unwrap();
        let destino = dir.join("destino");
        let ca = copiar_por_contenido(&a, &destino, "jpg").unwrap();
        let cb = copiar_por_contenido(&b, &destino, "jpg").unwrap();
        assert_eq!(ca, cb);
        assert_eq!(ca.sha256, sha256_de(&a).unwrap());
        assert_eq!(
            std::fs::read(absoluta(&destino, &ca)).unwrap(),
            b"la misma portada"
        );
        let restos = std::fs::read_dir(&destino)
            .unwrap()
            .filter(|e| {
                e.as_ref()
                    .unwrap()
                    .file_name()
                    .to_string_lossy()
                    .starts_with('.')
            })
            .count();
        assert_eq!(restos, 0, "ningún temporal queda atrás");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn copiar_un_archivo_que_no_existe_lo_dice() {
        let dir = temporal("falta");
        assert_eq!(
            copiar_por_contenido(&dir.join("no.jpg"), &dir, "jpg"),
            Err(NsError::FileNotFound)
        );
        let _ = std::fs::remove_dir_all(dir);
    }
}
