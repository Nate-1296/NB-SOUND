//! Copia a dispositivos externos (F8.4): tarjetas microSD, memorias USB y
//! reproductores portátiles.
//!
//! Copia toda la biblioteca, las canciones favoritas o una playlist a la carpeta
//! elegida por el usuario con el selector nativo:
//! - Estructura de carpetas elegible (`Artista / Álbum / Pista`, `Artista / Pista`
//!   o plana en la raíz) con nombres saneados para FAT32 / exFAT.
//! - Etiquetas y portada incrustadas en la copia mediante `lofty`, sin tocar nunca
//!   el archivo original de la biblioteca del usuario.
//! - Conversión opcional a WAV PCM estándar (16 bits, 44,1 kHz estéreo) decodificando
//!   con `symphonia` (`audio::Decodificador`), sin depender de `ffmpeg` (ADR-006).
//! - Lista `.m3u8` con rutas relativas al exportar favoritas o una playlist.

use std::io::Write as _;
use std::path::{Path, PathBuf};

use lofty::config::WriteOptions;
use lofty::file::{AudioFile, TaggedFileExt};
use lofty::picture::{MimeType, Picture, PictureType};
use lofty::prelude::ItemKey;
use lofty::tag::{Accessor, Tag};
use rubato::{FftFixedIn, Resampler};
use serde::{Deserialize, Serialize};
use ts_rs::TS;

use crate::audio::decodificador::Decodificador;
use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};
use crate::paths::Rutas;
use crate::playlists;
use crate::portadas::{self, Clase, Peticion};

const TASA_WAV: u32 = 44_100;

/// Qué conjunto de pistas copiar al dispositivo (F8.4).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub enum OrigenCopia {
    Biblioteca,
    Favoritas,
    Playlist,
}

/// Cómo organizar las carpetas dentro del dispositivo (F8.4).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub enum EstructuraCarpetas {
    /// `Artista / Álbum / 01 - Título.ext`
    ArtistaAlbum,
    /// `Artista / 01 - Título.ext`
    Artista,
    /// `Artista - Título.ext` en la raíz del destino.
    Plana,
}

/// Opciones elegidas por el usuario para copiar a un dispositivo externo (F8.4).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct OpcionesCopiaDispositivo {
    pub origen: OrigenCopia,
    #[ts(type = "number | null")]
    pub playlist_id: Option<i64>,
    pub estructura: EstructuraCarpetas,
    pub incrustar_portada: bool,
    pub convertir_a_wav: bool,
}

/// Resultado de una copia a dispositivo externo (F8.4).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct ResumenCopiaDispositivo {
    pub copiadas: u32,
    pub omitidas: u32,
    pub errores: u32,
    #[ts(type = "number")]
    pub bytes_escritos: u64,
    pub lista_m3u8: Option<String>,
}

struct PistaParaCopia {
    id: i64,
    ruta: String,
    titulo: String,
    artista: String,
    album: String,
    numero: Option<u32>,
    anio: Option<i32>,
    duracion_seg: f64,
}

/// Sanea un nombre de carpeta o archivo para sistemas FAT32 / exFAT:
/// sustituye `<>:"/\|?*` y caracteres de control por `'_'`, recorta espacios y
/// puntos finales y limita la longitud a 80 caracteres.
#[must_use]
pub fn sanear_componente_fat32(nombre: &str) -> String {
    let mut limpio = String::with_capacity(nombre.len());
    let mut ultimo_espacio = false;
    for c in nombre.chars() {
        let reemplazado = match c {
            '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*' => '_',
            c if c.is_control() => '_',
            c if c.is_whitespace() => ' ',
            c => c,
        };
        if reemplazado == ' ' {
            if !ultimo_espacio && !limpio.is_empty() {
                limpio.push(' ');
            }
            ultimo_espacio = true;
        } else {
            limpio.push(reemplazado);
            ultimo_espacio = false;
        }
    }
    let recortado = limpio.trim_matches(|c: char| c == ' ' || c == '.');
    let acotado: String = recortado.chars().take(80).collect();
    let final_limpio = acotado.trim_matches(|c: char| c == ' ' || c == '.');
    if final_limpio.is_empty() {
        "Sin nombre".to_owned()
    } else {
        final_limpio.to_owned()
    }
}

/// Construye la ruta relativa dentro del dispositivo según la estructura elegida.
#[must_use]
pub fn ruta_relativa_destino(
    estructura: EstructuraCarpetas,
    artista: &str,
    album: &str,
    titulo: &str,
    numero: Option<u32>,
    extension: &str,
) -> PathBuf {
    let art = sanear_componente_fat32(if artista.trim().is_empty() {
        "Artista desconocido"
    } else {
        artista
    });
    let alb = sanear_componente_fat32(if album.trim().is_empty() {
        "Sencillos"
    } else {
        album
    });
    let tit = sanear_componente_fat32(if titulo.trim().is_empty() {
        "Pista"
    } else {
        titulo
    });
    let ext = extension
        .trim_start_matches('.')
        .chars()
        .filter(char::is_ascii_alphanumeric)
        .collect::<String>()
        .to_ascii_lowercase();
    let ext = if ext.is_empty() { "mp3" } else { &ext };

    let prefijo = match numero.filter(|n| *n > 0 && *n < 1000) {
        Some(n) => format!("{n:02} - "),
        None => String::new(),
    };

    match estructura {
        EstructuraCarpetas::ArtistaAlbum => PathBuf::from(&art)
            .join(&alb)
            .join(format!("{prefijo}{tit}.{ext}")),
        EstructuraCarpetas::Artista => PathBuf::from(&art).join(format!("{prefijo}{tit}.{ext}")),
        EstructuraCarpetas::Plana => {
            let base = sanear_componente_fat32(&format!("{art} - {tit}"));
            PathBuf::from(format!("{base}.{ext}"))
        }
    }
}

fn resolver_origen(musica: Option<&Path>, ruta: &str) -> PathBuf {
    let p = Path::new(ruta);
    if p.is_absolute() {
        p.to_path_buf()
    } else if let Some(base) = musica {
        base.join(p)
    } else {
        p.to_path_buf()
    }
}

fn cargar_estereo_44k(ruta: &Path) -> NsResult<(Vec<f32>, Vec<f32>)> {
    let mut d = Decodificador::abrir(ruta, 0.0)?;
    let origen = d.tasa;
    let mut frames = Vec::new();
    while d.leer(&mut frames, 65_536)? > 0 {}
    let izq: Vec<f32> = frames.iter().map(|f| f.left).collect();
    let der: Vec<f32> = frames.iter().map(|f| f.right).collect();
    drop(frames);
    if origen == TASA_WAV || izq.is_empty() {
        return Ok((izq, der));
    }
    let trozo = 4096;
    let mut rs = FftFixedIn::<f32>::new(origen as usize, TASA_WAV as usize, trozo, 2, 2)
        .map_err(|_| NsError::Internal)?;
    let esperado = (izq.len() as f64 * f64::from(TASA_WAV) / f64::from(origen)).round() as usize;
    let (mut a, mut b) = (Vec::with_capacity(esperado), Vec::with_capacity(esperado));
    let mut i = 0;
    while i + trozo <= izq.len() {
        let out = rs
            .process(&[&izq[i..i + trozo], &der[i..i + trozo]], None)
            .map_err(|_| NsError::Internal)?;
        a.extend_from_slice(&out[0]);
        b.extend_from_slice(&out[1]);
        i += trozo;
    }
    let resto = rs
        .process_partial(Some(&[&izq[i..], &der[i..]]), None)
        .map_err(|_| NsError::Internal)?;
    a.extend_from_slice(&resto[0]);
    b.extend_from_slice(&resto[1]);
    let cola = rs
        .process_partial::<&[f32]>(None, None)
        .map_err(|_| NsError::Internal)?;
    a.extend_from_slice(&cola[0]);
    b.extend_from_slice(&cola[1]);
    let retardo = rs.output_delay();
    Ok((
        a.into_iter().skip(retardo).take(esperado).collect(),
        b.into_iter().skip(retardo).take(esperado).collect(),
    ))
}

fn transcodificar_a_wav(origen: &Path, destino: &Path) -> NsResult<u64> {
    let (izq, der) = cargar_estereo_44k(origen)?;
    let n = izq.len().min(der.len());
    let datos = u32::try_from(n * 4).map_err(|_| NsError::Internal)?;
    let mut b = Vec::with_capacity(44 + n * 4);
    b.extend_from_slice(b"RIFF");
    b.extend_from_slice(&(36 + datos).to_le_bytes());
    b.extend_from_slice(b"WAVEfmt ");
    b.extend_from_slice(&16u32.to_le_bytes());
    b.extend_from_slice(&1u16.to_le_bytes());
    b.extend_from_slice(&2u16.to_le_bytes());
    b.extend_from_slice(&TASA_WAV.to_le_bytes());
    b.extend_from_slice(&(TASA_WAV * 4).to_le_bytes());
    b.extend_from_slice(&4u16.to_le_bytes());
    b.extend_from_slice(&16u16.to_le_bytes());
    b.extend_from_slice(b"data");
    b.extend_from_slice(&datos.to_le_bytes());
    let muestra = |v: f32| ((v.clamp(-1.0, 1.0) * 32_767.0).round() as i16).to_le_bytes();
    for i in 0..n {
        b.extend_from_slice(&muestra(izq[i]));
        b.extend_from_slice(&muestra(der[i]));
    }
    if let Some(dir) = destino.parent() {
        std::fs::create_dir_all(dir).map_err(|_| NsError::StorageFailure)?;
    }
    let temporal = destino.with_extension("wav.parcial");
    let mut f = std::fs::File::create(&temporal).map_err(|_| NsError::StorageFailure)?;
    f.write_all(&b).map_err(|_| NsError::StorageFailure)?;
    f.sync_all().map_err(|_| NsError::StorageFailure)?;
    std::fs::rename(&temporal, destino).map_err(|_| NsError::StorageFailure)?;
    Ok(b.len() as u64)
}

fn incrustar_en_copia(
    archivo_copiado: &Path,
    pista: &PistaParaCopia,
    portada: Option<(&[u8], &str)>,
) {
    let Ok(mut archivo) = lofty::read_from_path(archivo_copiado) else {
        return;
    };
    let tipo = archivo.primary_tag_type();
    if archivo.tag(tipo).is_none() {
        archivo.insert_tag(Tag::new(tipo));
    }
    let Some(tag) = archivo.tag_mut(tipo) else {
        return;
    };
    if !pista.titulo.trim().is_empty() {
        tag.insert_text(ItemKey::TrackTitle, pista.titulo.trim().to_owned());
    }
    if !pista.artista.trim().is_empty() {
        tag.insert_text(ItemKey::TrackArtist, pista.artista.trim().to_owned());
        tag.insert_text(ItemKey::AlbumArtist, pista.artista.trim().to_owned());
    }
    if !pista.album.trim().is_empty() {
        tag.insert_text(ItemKey::AlbumTitle, pista.album.trim().to_owned());
    }
    if let Some(n) = pista.numero.filter(|n| *n > 0) {
        tag.set_track(n);
    }
    if let Some(anio) = pista.anio {
        tag.insert_text(ItemKey::RecordingDate, anio.to_string());
    }
    if let Some((bytes, mime)) = portada {
        let mime_lofty = if mime == "image/png" {
            MimeType::Png
        } else {
            MimeType::Jpeg
        };
        tag.remove_picture_type(PictureType::CoverFront);
        let pic = Picture::unchecked(bytes.to_vec())
            .pic_type(PictureType::CoverFront)
            .mime_type(mime_lofty)
            .build();
        tag.push_picture(pic);
    }
    let _ = archivo.save_to_path(archivo_copiado, WriteOptions::default());
}

fn pistas_a_copiar(
    db: &BaseDeDatos,
    opciones: &OpcionesCopiaDispositivo,
) -> NsResult<(Vec<PistaParaCopia>, Option<String>)> {
    match opciones.origen {
        OrigenCopia::Biblioteca => {
            let conn = db.conexion()?;
            let mut s = conn
                .prepare(
                    "SELECT id, ruta, titulo, artista_nombre, album_titulo, numero, anio, coalesce(duracion_seg, 0)
                     FROM pistas
                     WHERE estado = 'biblioteca'
                     ORDER BY artista_nombre COLLATE NOCASE, album_titulo COLLATE NOCASE, coalesce(numero, 0), id",
                )
                .map_err(|_| NsError::StorageFailure)?;
            let filas = s
                .query_map([], mapear_pista)
                .map_err(|_| NsError::StorageFailure)?
                .collect::<rusqlite::Result<Vec<_>>>()
                .map_err(|_| NsError::StorageFailure)?;
            Ok((filas, None))
        }
        OrigenCopia::Favoritas => {
            let conn = db.conexion()?;
            let mut s = conn
                .prepare(
                    "SELECT id, ruta, titulo, artista_nombre, album_titulo, numero, anio, coalesce(duracion_seg, 0)
                     FROM pistas
                     WHERE estado = 'biblioteca' AND favorita = 1
                     ORDER BY artista_nombre COLLATE NOCASE, album_titulo COLLATE NOCASE, coalesce(numero, 0), id",
                )
                .map_err(|_| NsError::StorageFailure)?;
            let filas = s
                .query_map([], mapear_pista)
                .map_err(|_| NsError::StorageFailure)?
                .collect::<rusqlite::Result<Vec<_>>>()
                .map_err(|_| NsError::StorageFailure)?;
            Ok((filas, Some("Favoritas".to_owned())))
        }
        OrigenCopia::Playlist => {
            let id = opciones.playlist_id.ok_or(NsError::InvalidInput)?;
            let pl = playlists::una(db, id)?.ok_or(NsError::InvalidInput)?;
            let conn = db.conexion()?;
            let mut s = conn
                .prepare(
                    "SELECT p.id, p.ruta, p.titulo, p.artista_nombre, p.album_titulo, p.numero, p.anio,
                            coalesce(p.duracion_seg, 0)
                     FROM playlist_pistas pp
                     JOIN pistas p ON p.id = pp.pista_id
                     WHERE pp.playlist_id = ?1 AND p.estado = 'biblioteca'
                     ORDER BY pp.posicion",
                )
                .map_err(|_| NsError::StorageFailure)?;
            let filas = s
                .query_map([id], mapear_pista)
                .map_err(|_| NsError::StorageFailure)?
                .collect::<rusqlite::Result<Vec<_>>>()
                .map_err(|_| NsError::StorageFailure)?;
            Ok((filas, Some(pl.nombre)))
        }
    }
}

fn mapear_pista(f: &rusqlite::Row<'_>) -> rusqlite::Result<PistaParaCopia> {
    Ok(PistaParaCopia {
        id: f.get(0)?,
        ruta: f.get(1)?,
        titulo: f.get(2)?,
        artista: f.get(3)?,
        album: f.get(4)?,
        numero: f
            .get::<_, Option<i64>>(5)?
            .and_then(|n| u32::try_from(n).ok()),
        anio: f.get(6)?,
        duracion_seg: f.get(7)?,
    })
}

/// Copia las pistas elegidas a `destino` con la estructura y opciones dadas (F8.4).
///
/// # Errors
///
/// Devuelve error si la selección es inválida, si no se puede leer la base o si
/// la carpeta de destino no es escribible.
pub fn copiar(
    db: &BaseDeDatos,
    rutas: &Rutas,
    opciones: &OpcionesCopiaDispositivo,
    destino: &Path,
) -> NsResult<ResumenCopiaDispositivo> {
    std::fs::create_dir_all(destino).map_err(|_| NsError::StorageFailure)?;
    let carpeta_musica = {
        let conn = db.conexion()?;
        crate::reproductor::carpeta_musica(&conn)?
    };
    let (pistas, nombre_lista) = pistas_a_copiar(db, opciones)?;

    let mut copiadas = 0u32;
    let mut omitidas = 0u32;
    let mut errores = 0u32;
    let mut bytes_escritos = 0u64;
    let mut entradas_m3u8: Vec<(f64, String, String)> = Vec::new();

    for pista in &pistas {
        let origen_archivo = resolver_origen(carpeta_musica.as_deref(), &pista.ruta);
        if !origen_archivo.is_file() {
            errores += 1;
            continue;
        }
        let ext = if opciones.convertir_a_wav {
            "wav".to_owned()
        } else {
            origen_archivo
                .extension()
                .and_then(|x| x.to_str())
                .unwrap_or("mp3")
                .to_ascii_lowercase()
        };
        let rel = ruta_relativa_destino(
            opciones.estructura,
            &pista.artista,
            &pista.album,
            &pista.titulo,
            pista.numero,
            &ext,
        );
        let ruta_final = destino.join(&rel);
        let rel_m3u = rel
            .components()
            .map(|c| c.as_os_str().to_string_lossy().into_owned())
            .collect::<Vec<_>>()
            .join("/");

        if !opciones.convertir_a_wav
            && !opciones.incrustar_portada
            && ruta_final
                .metadata()
                .is_ok_and(|m| m.is_file() && m.len() > 0)
        {
            omitidas += 1;
            entradas_m3u8.push((
                pista.duracion_seg,
                format!("{} - {}", pista.artista, pista.titulo),
                rel_m3u,
            ));
            continue;
        }

        if let Some(dir) = ruta_final.parent() {
            if std::fs::create_dir_all(dir).is_err() {
                errores += 1;
                continue;
            }
        }

        let escrito = if opciones.convertir_a_wav {
            transcodificar_a_wav(&origen_archivo, &ruta_final)
        } else {
            std::fs::copy(&origen_archivo, &ruta_final).map_err(|_| NsError::StorageFailure)
        };

        let Ok(mut bytes) = escrito else {
            errores += 1;
            continue;
        };

        if opciones.incrustar_portada {
            let portada = portadas::servir(
                db,
                rutas,
                Peticion {
                    clase: Clase::Pista,
                    id: pista.id,
                    tamano: Some(640),
                },
            )
            .ok();
            let ref_portada = portada.as_ref().map(|(b, m)| (b.as_slice(), *m));
            incrustar_en_copia(&ruta_final, pista, ref_portada);
            if let Ok(meta) = ruta_final.metadata() {
                bytes = meta.len();
            }
        }

        copiadas += 1;
        bytes_escritos += bytes;
        entradas_m3u8.push((
            pista.duracion_seg,
            format!("{} - {}", pista.artista, pista.titulo),
            rel_m3u,
        ));
    }

    let lista_m3u8 = if let Some(nombre) = nombre_lista.filter(|_| !entradas_m3u8.is_empty()) {
        let archivo_m3u = format!("{}.m3u8", sanear_componente_fat32(&nombre));
        let ruta_m3u = destino.join(&archivo_m3u);
        let mut contenido = String::from("#EXTM3U\n");
        for (dur, etiqueta, rel) in &entradas_m3u8 {
            let seg = dur.round().max(0.0) as i64;
            contenido.push_str(&format!("#EXTINF:{seg},{etiqueta}\n{rel}\n"));
        }
        std::fs::write(&ruta_m3u, contenido.as_bytes()).map_err(|_| NsError::StorageFailure)?;
        bytes_escritos += contenido.len() as u64;
        Some(archivo_m3u)
    } else {
        None
    };

    Ok(ResumenCopiaDispositivo {
        copiadas,
        omitidas,
        errores,
        bytes_escritos,
        lista_m3u8,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::audio::pruebas::wav;
    use crate::catalogo::{etiquetas, portadas_red};

    fn dir_temporal(nombre: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("ns-copia-disp-{nombre}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    #[test]
    fn sanea_caracteres_prohibidos_en_fat32_y_construye_estructuras() {
        assert_eq!(
            sanear_componente_fat32("AC/DC: Live? *Best* <2026>... "),
            "AC_DC_ Live_ _Best_ _2026_"
        );
        assert_eq!(sanear_componente_fat32("   ...   "), "Sin nombre");

        let r1 = ruta_relativa_destino(
            EstructuraCarpetas::ArtistaAlbum,
            "Soda Stereo",
            "Canción Animal",
            "De música ligera",
            Some(4),
            "flac",
        );
        assert_eq!(
            r1,
            PathBuf::from("Soda Stereo")
                .join("Canción Animal")
                .join("04 - De música ligera.flac")
        );

        let r2 = ruta_relativa_destino(
            EstructuraCarpetas::Plana,
            "Soda Stereo",
            "Canción Animal",
            "De música ligera",
            Some(4),
            "mp3",
        );
        assert_eq!(r2, PathBuf::from("Soda Stereo - De música ligera.mp3"));
    }

    #[test]
    fn copia_incrusta_portada_en_destino_sin_tocar_original_y_genera_m3u8() {
        let base = dir_temporal("copia");
        let rutas = Rutas::bajo(&base.join("app")).unwrap();
        let db = BaseDeDatos::en_memoria().unwrap();

        let archivo_orig = base.join("origen").join("pista.wav");
        std::fs::create_dir_all(archivo_orig.parent().unwrap()).unwrap();
        let _ = wav(&archivo_orig, 44_100, 44_100, |i, _| {
            (i as f32 * 0.05).sin() * 0.2
        });
        let bytes_originales = std::fs::read(&archivo_orig).unwrap();

        // Creamos una imagen PNG válida de 16×16 en `portadas`.
        std::fs::create_dir_all(rutas.portadas()).unwrap();
        let img = image::DynamicImage::new_rgb8(16, 16);
        let ruta_portada = rutas.portadas().join("portada-test.png");
        img.save(&ruta_portada).unwrap();

        db.conexion()
            .unwrap()
            .execute_batch(&format!(
                "INSERT INTO portadas (id, sha256, ruta, mime, ancho, alto, bytes, origen)
                 VALUES (1, '{}', 'portada-test.png', 'image/png', 16, 16, 100, 'etiqueta');
                 INSERT INTO artistas (id, nombre, clave) VALUES (1, 'Gustavo Cerati', 'cerati');
                 INSERT INTO albumes (id, artista_id, titulo, clave, portada_id)
                 VALUES (10, 1, 'Bocanada', 'bocanada', 1);
                 INSERT INTO pistas (id, album_id, artista_id, titulo, artista_nombre, album_titulo, numero, anio, ruta, duracion_seg, favorita)
                 VALUES (100, 10, 1, 'Puente', 'Gustavo Cerati', 'Bocanada', 2, 1999, '{}', 1.0, 1);",
                "a".repeat(64),
                archivo_orig.to_string_lossy(),
            ))
            .unwrap();

        let destino = base.join("usb");
        let res = copiar(
            &db,
            &rutas,
            &OpcionesCopiaDispositivo {
                origen: OrigenCopia::Favoritas,
                playlist_id: None,
                estructura: EstructuraCarpetas::ArtistaAlbum,
                incrustar_portada: true,
                convertir_a_wav: false,
            },
            &destino,
        )
        .unwrap();

        assert_eq!(res.copiadas, 1);
        assert_eq!(res.errores, 0);
        assert_eq!(res.lista_m3u8.as_deref(), Some("Favoritas.m3u8"));

        // El archivo original de la biblioteca sigue intacto byte a byte.
        assert_eq!(std::fs::read(&archivo_orig).unwrap(), bytes_originales);

        // El archivo copiado en el USB tiene las etiquetas y la portada incrustada.
        let copiado = destino
            .join("Gustavo Cerati")
            .join("Bocanada")
            .join("02 - Puente.wav");
        assert!(copiado.is_file());
        let (_, cruda) = etiquetas::leer(&copiado).unwrap();
        assert_eq!(cruda.titulo.as_deref(), Some("Puente"));
        assert_eq!(cruda.artista.as_deref(), Some("Gustavo Cerati"));
        assert!(portadas_red::de_etiquetas(&copiado).is_some());

        let m3u = std::fs::read_to_string(destino.join("Favoritas.m3u8")).unwrap();
        assert!(m3u.contains("Gustavo Cerati/Bocanada/02 - Puente.wav"));

        // Segunda copia sin recodificar ni reescribir portada: omite el archivo ya existente.
        let res2 = copiar(
            &db,
            &rutas,
            &OpcionesCopiaDispositivo {
                origen: OrigenCopia::Favoritas,
                playlist_id: None,
                estructura: EstructuraCarpetas::ArtistaAlbum,
                incrustar_portada: false,
                convertir_a_wav: false,
            },
            &destino,
        )
        .unwrap();
        assert_eq!(res2.copiadas, 0);
        assert_eq!(res2.omitidas, 1);

        let _ = std::fs::remove_dir_all(&base);
    }
}
