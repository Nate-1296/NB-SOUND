//! La portada de una playlist para el teléfono (`/api/v1/asset/playlist/{id}`).
//!
//! La V1 guardaba un mosaico generado en cada playlist; el importador no lo trajo
//! porque se recalcula (`migracion-v1.md`). La interfaz de la V2 lo compone en el
//! webview, pero el teléfono pide una imagen, así que aquí se compone una vez, con
//! las mismas cuatro portadas, y se guarda en la caché con el nombre de lo que la
//! forma: si cambian las pistas, cambia el nombre y se compone otra.

use std::io::Cursor;
use std::path::PathBuf;

use image::imageops::FilterType;
use image::{DynamicImage, ImageFormat, ImageReader, RgbImage};
use sha2::{Digest, Sha256};

use super::repositorio;
use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};
use crate::paths::Rutas;

/// Lado del mosaico: lo que pinta el teléfono en su cuadrícula a doble densidad.
const LADO: u32 = 600;

fn abrir(ruta: &PathBuf) -> Option<DynamicImage> {
    ImageReader::open(ruta)
        .ok()?
        .with_guessed_format()
        .ok()?
        .decode()
        .ok()
}

/// Una sola portada si hay menos de cuatro distintas, como el mosaico de la V1 y
/// el de la interfaz; con cuatro, la cuadrícula de 2×2.
fn componer(portadas: &[DynamicImage]) -> RgbImage {
    if portadas.len() < 4 {
        return portadas[0]
            .resize_to_fill(LADO, LADO, FilterType::Lanczos3)
            .to_rgb8();
    }
    let medio = LADO / 2;
    let mut lienzo = RgbImage::new(LADO, LADO);
    for (i, p) in portadas.iter().take(4).enumerate() {
        let trozo = p
            .resize_to_fill(medio, medio, FilterType::Lanczos3)
            .to_rgb8();
        let (x, y) = ((i as u32 % 2) * medio, (i as u32 / 2) * medio);
        image::imageops::replace(&mut lienzo, &trozo, i64::from(x), i64::from(y));
    }
    lienzo
}

/// El archivo del mosaico, compuesto si hace falta. `None` si la playlist no existe,
/// está oculta o ninguna de sus pistas tiene portada.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla o no se puede escribir la caché.
pub fn de_playlist(db: &BaseDeDatos, rutas: &Rutas, id: i64) -> NsResult<Option<PathBuf>> {
    let portadas = repositorio::portadas_de_playlist(db, rutas, id)?;
    if portadas.is_empty() {
        return Ok(None);
    }
    let clave = portadas
        .iter()
        .fold(Sha256::new(), |h, (pid, _)| {
            h.chain_update(pid.to_le_bytes())
        })
        .finalize();
    let nombre: String = clave.iter().take(12).map(|b| format!("{b:02x}")).collect();
    let destino = rutas
        .cache
        .join("movil")
        .join(format!("playlist-{nombre}.jpg"));
    if destino.is_file() {
        return Ok(Some(destino));
    }
    let imagenes: Vec<DynamicImage> = portadas.iter().filter_map(|(_, r)| abrir(r)).collect();
    if imagenes.is_empty() {
        return Ok(None);
    }
    let mut bytes = Vec::new();
    componer(&imagenes)
        .write_to(&mut Cursor::new(&mut bytes), ImageFormat::Jpeg)
        .map_err(|_| NsError::Internal)?;
    if let Some(dir) = destino.parent() {
        std::fs::create_dir_all(dir).map_err(|_| NsError::StorageFailure)?;
    }
    let temporal = destino.with_extension(format!("{}.parcial", std::process::id()));
    std::fs::write(&temporal, &bytes)
        .and_then(|()| std::fs::rename(&temporal, &destino))
        .map_err(|_| {
            let _ = std::fs::remove_file(&temporal);
            NsError::StorageFailure
        })?;
    Ok(Some(destino))
}

#[cfg(test)]
mod tests {
    use super::*;
    use image::Rgb;

    #[test]
    fn con_cuatro_portadas_es_una_cuadricula_y_con_menos_una_sola() {
        let colores = [[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 0]];
        let imgs: Vec<DynamicImage> = colores
            .iter()
            .map(|c| DynamicImage::ImageRgb8(RgbImage::from_pixel(50, 50, Rgb(*c))))
            .collect();
        let m = componer(&imgs);
        assert_eq!(m.dimensions(), (LADO, LADO));
        let cerca = |p: &Rgb<u8>, c: [u8; 3]| p.0.iter().zip(c).all(|(a, b)| a.abs_diff(b) < 10);
        assert!(cerca(m.get_pixel(10, 10), colores[0]));
        assert!(cerca(m.get_pixel(LADO - 10, 10), colores[1]));
        assert!(cerca(m.get_pixel(10, LADO - 10), colores[2]));
        assert!(cerca(m.get_pixel(LADO - 10, LADO - 10), colores[3]));
        let una = componer(&imgs[..2]);
        assert!(cerca(una.get_pixel(LADO - 10, LADO - 10), colores[0]));
    }
}
