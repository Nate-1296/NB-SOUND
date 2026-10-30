//! Portadas para la interfaz: miniaturas en caché y el color dominante.
//!
//! El webview nunca recibe una ruta. Pide `portada://localhost/<clase>/<id>/<tamaño>`
//! (una pista, un álbum o un artista, por su `id`) y el runtime resuelve el archivo,
//! lo reduce si hace falta y devuelve los bytes. Así no hay rutas del usuario que
//! canonicalizar en la frontera (`check-rutas`), y las originales de 2,4 MB no
//! llegan a una lista de cientos de filas.
//!
//! Las miniaturas van a la caché: se regeneran solas si se borran. Las originales
//! están en los datos ([`Rutas::portadas`]).

use std::io::Cursor;
use std::path::{Path, PathBuf};

use image::imageops::FilterType;
use image::{DynamicImage, ImageFormat, ImageReader};
use rusqlite::OptionalExtension;

use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};
use crate::paths::Rutas;

/// Los tamaños que se sirven, en píxeles del lado mayor. Pocos y fijos: cada uno es
/// un archivo en caché por portada.
pub const TAMANOS: [u32; 4] = [64, 160, 320, 640];

/// De qué es la portada que se pide.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Clase {
    Pista,
    Album,
    Artista,
}

/// Una petición ya interpretada.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Peticion {
    pub clase: Clase,
    pub id: i64,
    /// `None` es la original.
    pub tamano: Option<u32>,
}

/// Interpreta la ruta de una URL `portada://`: `/album/10/160`. Todo lo que no
/// tenga esa forma exacta se rechaza: es la frontera con el webview.
pub fn interpretar(ruta: &str) -> Option<Peticion> {
    let mut partes = ruta.trim_start_matches('/').split('/');
    let clase = match partes.next()? {
        "pista" => Clase::Pista,
        "album" => Clase::Album,
        "artista" => Clase::Artista,
        _ => return None,
    };
    let id = partes.next()?.parse::<i64>().ok().filter(|i| *i > 0)?;
    let tamano = match partes.next() {
        None | Some("original") => None,
        Some(t) => {
            let t = t.parse::<u32>().ok()?;
            // Se sirve el tamaño fijo más pequeño que cubra lo pedido.
            Some(
                TAMANOS
                    .iter()
                    .copied()
                    .find(|x| *x >= t)
                    .unwrap_or(TAMANOS[3]),
            )
        }
    };
    if partes.next().is_some() {
        return None;
    }
    Some(Peticion { clase, id, tamano })
}

/// La portada original que corresponde a una petición: su `id` en `portadas`, su
/// ruta y su color si ya se calculó.
fn original(db: &BaseDeDatos, p: Peticion) -> NsResult<Option<(i64, String, Option<String>)>> {
    let conn = db.conexion()?;
    let sql = match p.clase {
        // Una pista usa la suya y, si no tiene, la de su álbum.
        Clase::Pista => {
            "SELECT po.id, po.ruta, po.color FROM pistas p
             LEFT JOIN albumes a ON a.id = p.album_id
             JOIN portadas po ON po.id = coalesce(p.portada_id, a.portada_id)
             WHERE p.id = ?1"
        }
        Clase::Album => {
            "SELECT po.id, po.ruta, po.color FROM albumes a
             JOIN portadas po ON po.id = a.portada_id WHERE a.id = ?1"
        }
        Clase::Artista => {
            "SELECT po.id, po.ruta, po.color FROM artistas a
             JOIN portadas po ON po.id = a.imagen_id WHERE a.id = ?1"
        }
    };
    conn.query_row(sql, [p.id], |f| Ok((f.get(0)?, f.get(1)?, f.get(2)?)))
        .optional()
        .map_err(|_| NsError::StorageFailure)
}

/// El color medio de la imagen reducida, oscurecido si es casi blanco para que el
/// texto claro siga leyéndose encima. En `#rrggbb`.
pub fn color_dominante(imagen: &DynamicImage) -> String {
    let pequena = imagen.resize_exact(16, 16, FilterType::Triangle).to_rgb8();
    let (mut r, mut g, mut b) = (0u32, 0u32, 0u32);
    for p in pequena.pixels() {
        r += u32::from(p[0]);
        g += u32::from(p[1]);
        b += u32::from(p[2]);
    }
    let n = pequena.pixels().len() as u32;
    let (r, g, b) = (r / n, g / n, b / n);
    let luz = (r * 299 + g * 587 + b * 114) / 1000;
    let factor = if luz > 200 { 0.7 } else { 1.0 };
    let c = |x: u32| ((x as f32 * factor) as u32).min(255);
    format!("#{:02x}{:02x}{:02x}", c(r), c(g), c(b))
}

fn guardar_color(db: &BaseDeDatos, portada: i64, color: &str) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    tx.execute(
        "UPDATE portadas SET color = ?1 WHERE id = ?2 AND color IS NULL",
        rusqlite::params![color, portada],
    )
    .map_err(|_| NsError::StorageFailure)?;
    tx.commit().map_err(|_| NsError::StorageFailure)
}

/// Escribe por un temporal y renombra: dos peticiones a la vez de la misma
/// miniatura no dejan nunca un archivo a medias.
fn escribir(destino: &Path, bytes: &[u8]) -> NsResult<()> {
    if let Some(dir) = destino.parent() {
        std::fs::create_dir_all(dir).map_err(|_| NsError::StorageFailure)?;
    }
    let temporal = destino.with_extension(format!("{}.parcial", std::process::id()));
    std::fs::write(&temporal, bytes)
        .and_then(|()| std::fs::rename(&temporal, destino))
        .map_err(|_| {
            let _ = std::fs::remove_file(&temporal);
            NsError::StorageFailure
        })
}

/// Los bytes y el tipo MIME de lo pedido.
///
/// # Errors
///
/// - [`NsError::FileNotFound`] si no hay portada.
/// - [`NsError::FormatUnsupported`] si la imagen no se puede leer.
pub fn servir(db: &BaseDeDatos, rutas: &Rutas, p: Peticion) -> NsResult<(Vec<u8>, &'static str)> {
    let (id, ruta, color) = original(db, p)?.ok_or(NsError::FileNotFound)?;
    let ruta_original = rutas.portadas().join(&ruta);
    let Some(tamano) = p.tamano else {
        let bytes = std::fs::read(&ruta_original).map_err(|_| NsError::FileNotFound)?;
        let mime = if ruta.ends_with(".png") {
            "image/png"
        } else {
            "image/jpeg"
        };
        return Ok((bytes, mime));
    };
    let en_cache: PathBuf = rutas
        .cache
        .join("miniaturas")
        .join(format!("{id}-{tamano}.jpg"));
    if let Ok(bytes) = std::fs::read(&en_cache) {
        return Ok((bytes, "image/jpeg"));
    }
    let imagen = ImageReader::open(&ruta_original)
        .map_err(|_| NsError::FileNotFound)?
        .with_guessed_format()
        .map_err(|_| NsError::FormatUnsupported)?
        .decode()
        .map_err(|_| NsError::FormatUnsupported)?;
    if color.is_none() {
        let _ = guardar_color(db, id, &color_dominante(&imagen));
    }
    let reducida = if imagen.width().max(imagen.height()) > tamano {
        imagen.resize(tamano, tamano, FilterType::Lanczos3)
    } else {
        imagen
    };
    let mut bytes = Vec::new();
    reducida
        .to_rgb8()
        .write_to(&mut Cursor::new(&mut bytes), ImageFormat::Jpeg)
        .map_err(|_| NsError::Internal)?;
    escribir(&en_cache, &bytes)?;
    Ok((bytes, "image/jpeg"))
}

/// La foto de perfil (`portada://localhost/perfil`), que el importador copió de la
/// V1 a `datos/perfil`. Es una sola y pequeña: se sirve tal cual.
///
/// # Errors
///
/// [`NsError::FileNotFound`] si no hay foto.
pub fn servir_perfil(db: &BaseDeDatos, rutas: &Rutas) -> NsResult<(Vec<u8>, &'static str)> {
    let valor: Option<String> = db
        .conexion()?
        .query_row(
            "SELECT valor FROM preferencias WHERE clave = 'foto_perfil'",
            [],
            |f| f.get(0),
        )
        .optional()
        .map_err(|_| NsError::StorageFailure)?;
    let relativa = valor
        .and_then(|v| serde_json::from_str::<String>(&v).ok())
        .ok_or(NsError::FileNotFound)?;
    // La ruta viene de la base, pero se comprueba igual que no sale de su carpeta.
    let carpeta = rutas.datos.join("perfil");
    let ruta = crate::security::resolve_within(&carpeta, std::path::Path::new(&relativa))?;
    let bytes = std::fs::read(&ruta).map_err(|_| NsError::FileNotFound)?;
    let mime = if relativa.ends_with(".png") {
        "image/png"
    } else {
        "image/jpeg"
    };
    Ok((bytes, mime))
}

/// Dónde está en la caché la miniatura de una petición, si ya se generó. Lo usan
/// los controles del sistema, que necesitan un archivo y no unos bytes.
pub fn ruta_en_cache(db: &BaseDeDatos, rutas: &Rutas, p: Peticion) -> Option<PathBuf> {
    let (id, _, _) = original(db, p).ok()??;
    let tamano = p.tamano?;
    let ruta = rutas
        .cache
        .join("miniaturas")
        .join(format!("{id}-{tamano}.jpg"));
    ruta.is_file().then_some(ruta)
}

#[cfg(test)]
mod tests {
    use super::*;
    use image::{Rgb, RgbImage};

    #[test]
    fn solo_se_aceptan_rutas_con_la_forma_exacta() {
        assert_eq!(
            interpretar("/album/10/160"),
            Some(Peticion {
                clase: Clase::Album,
                id: 10,
                tamano: Some(160)
            })
        );
        assert_eq!(
            interpretar("/pista/3/100").unwrap().tamano,
            Some(160),
            "se redondea hacia arriba"
        );
        assert_eq!(interpretar("/artista/7/5000").unwrap().tamano, Some(640));
        assert_eq!(interpretar("/album/10").unwrap().tamano, None);
        for mala in [
            "/../etc/passwd",
            "/album/-1/64",
            "/album/x/64",
            "/disco/1/64",
            "/album/1/64/mas",
            "",
        ] {
            assert_eq!(interpretar(mala), None, "{mala}");
        }
    }

    #[test]
    fn el_color_dominante_de_una_imagen_roja_es_rojo() {
        let img = DynamicImage::ImageRgb8(RgbImage::from_pixel(50, 50, Rgb([200, 30, 30])));
        assert_eq!(color_dominante(&img), "#c81e1e");
        let blanca = DynamicImage::ImageRgb8(RgbImage::from_pixel(10, 10, Rgb([255, 255, 255])));
        assert_eq!(
            color_dominante(&blanca),
            "#b2b2b2",
            "lo casi blanco se oscurece"
        );
    }

    #[test]
    fn una_portada_se_reduce_una_vez_y_guarda_su_color() {
        let dir = std::env::temp_dir().join(format!("ns-portadas-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let rutas = Rutas::bajo(&dir).unwrap();
        let original = rutas.portadas().join("ab/abc.png");
        std::fs::create_dir_all(original.parent().unwrap()).unwrap();
        RgbImage::from_pixel(1200, 1000, Rgb([10, 120, 200]))
            .save(&original)
            .unwrap();
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(&format!(
                "INSERT INTO portadas (id, sha256, ruta, ancho, alto, bytes, mime, origen)
                     VALUES (1, '{}', 'ab/abc.png', 1200, 1000, 10, 'image/png', 'v1');
                 INSERT INTO artistas (id, nombre, clave) VALUES (1, 'a', 'a');
                 INSERT INTO albumes (id, artista_id, titulo, clave, portada_id) VALUES (10, 1, 't', 't', 1);
                 INSERT INTO pistas (id, album_id, artista_id, titulo, ruta) VALUES (100, 10, 1, 'p', 'x');",
                "a".repeat(64)
            ))
            .unwrap();
        let (bytes, mime) = servir(&db, &rutas, interpretar("/pista/100/160").unwrap()).unwrap();
        assert_eq!(mime, "image/jpeg");
        let mini = image::load_from_memory(&bytes).unwrap();
        assert_eq!(mini.width().max(mini.height()), 160);
        assert!(rutas.cache.join("miniaturas/1-160.jpg").is_file());
        let color: Option<String> = db
            .conexion()
            .unwrap()
            .query_row("SELECT color FROM portadas WHERE id = 1", [], |f| f.get(0))
            .unwrap();
        assert_eq!(color.as_deref(), Some("#0a78c8"));
        assert_eq!(
            servir(&db, &rutas, interpretar("/album/99/64").unwrap()),
            Err(NsError::FileNotFound)
        );
        let _ = std::fs::remove_dir_all(dir);
    }
}
