//! Leer y escribir etiquetas (F4.1.1), con `lofty`, en todos los formatos que
//! importa la V2: ID3v2 (MP3, WAV, AIFF), Vorbis (FLAC, Ogg, Opus) y MP4 (M4A).
//!
//! La V1 solo leía MP3 con `mutagen` (`core/validator.py`) y convertía lo demás con
//! `ffmpeg`; la V2 no convierte nada (enmienda de ADR-006), así que lee y escribe
//! cada formato en el suyo. Se usan las claves estándar (las de Picard), que
//! `lofty` traduce a cada formato. Las `TXXX` propias de la V1 (`mb_recording_id`,
//! `tagger_status`…) no se leen: la V1 solo las escribía en archivos que ya están
//! en la biblioteca importada, con sus datos en la base.

use std::path::Path;

use lofty::config::WriteOptions;
use lofty::file::{AudioFile, TaggedFileExt};
use lofty::prelude::ItemKey;
use lofty::tag::{Accessor, Tag};

use crate::error::{NsError, NsResult};

/// Lo técnico del audio, que no sale de las etiquetas.
#[derive(Debug, Clone, PartialEq)]
pub struct Tecnico {
    pub duracion_seg: f64,
    pub bitrate_kbps: Option<u32>,
    pub frecuencia: Option<u32>,
    pub canales: Option<u8>,
}

/// Las etiquetas tal como están en el archivo, sin tocar (`MetadataCruda`).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Cruda {
    pub titulo: Option<String>,
    pub artista: Option<String>,
    pub album: Option<String>,
    pub artista_album: Option<String>,
    /// Como lo guarda la V1: `3` o `3/12`.
    pub numero: Option<String>,
    pub anio: Option<String>,
    pub genero: Option<String>,
    pub disco: Option<String>,
    pub total_discos: Option<String>,
    pub compositor: Option<String>,
    pub comentario: Option<String>,
    pub isrc: Option<String>,
    pub letra: Option<String>,
    pub mbid_grabacion: Option<String>,
    pub mbid_lanzamiento: Option<String>,
    pub mbid_grupo: Option<String>,
    pub mbid_artista: Option<String>,
    pub acoustid_id: Option<String>,
}

fn texto(tag: &Tag, clave: ItemKey) -> Option<String> {
    tag.get_string(clave)
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
}

fn abrir(ruta: &Path) -> NsResult<lofty::file::TaggedFile> {
    lofty::read_from_path(ruta).map_err(|error| {
        tracing::info!(error = %error, "lofty no pudo leer un archivo");
        if ruta.is_file() {
            NsError::AudioCorrupted
        } else {
            NsError::FileNotFound
        }
    })
}

/// # Errors
///
/// - [`NsError::FileNotFound`] si no existe.
/// - [`NsError::AudioCorrupted`] si no es un archivo de audio legible.
pub fn leer(ruta: &Path) -> NsResult<(Tecnico, Cruda)> {
    let archivo = abrir(ruta)?;
    let p = archivo.properties();
    let tecnico = Tecnico {
        duracion_seg: p.duration().as_secs_f64(),
        bitrate_kbps: p.audio_bitrate().or_else(|| p.overall_bitrate()),
        frecuencia: p.sample_rate(),
        canales: p.channels(),
    };
    let Some(tag) = archivo.primary_tag().or_else(|| archivo.first_tag()) else {
        return Ok((tecnico, Cruda::default()));
    };
    let numero = texto(tag, ItemKey::TrackNumber).map(|n| match texto(tag, ItemKey::TrackTotal) {
        Some(t) if !n.contains('/') => format!("{n}/{t}"),
        _ => n,
    });
    let (disco, total_discos) = match texto(tag, ItemKey::DiscNumber) {
        Some(d) => match d.split_once('/') {
            Some((a, b)) => (
                Some(a.trim().to_owned()).filter(|s| !s.is_empty()),
                Some(b.trim().to_owned()).filter(|s| !s.is_empty()),
            ),
            None => (Some(d), texto(tag, ItemKey::DiscTotal)),
        },
        None => (None, None),
    };
    let cruda = Cruda {
        titulo: texto(tag, ItemKey::TrackTitle),
        artista: texto(tag, ItemKey::TrackArtist),
        album: texto(tag, ItemKey::AlbumTitle),
        artista_album: texto(tag, ItemKey::AlbumArtist),
        numero,
        anio: texto(tag, ItemKey::RecordingDate)
            .or_else(|| texto(tag, ItemKey::Year))
            .or_else(|| texto(tag, ItemKey::ReleaseDate)),
        genero: texto(tag, ItemKey::Genre),
        disco,
        total_discos,
        compositor: texto(tag, ItemKey::Composer),
        comentario: texto(tag, ItemKey::Comment),
        isrc: texto(tag, ItemKey::Isrc),
        letra: texto(tag, ItemKey::UnsyncLyrics).or_else(|| texto(tag, ItemKey::Lyrics)),
        mbid_grabacion: texto(tag, ItemKey::MusicBrainzRecordingId),
        mbid_lanzamiento: texto(tag, ItemKey::MusicBrainzReleaseId),
        mbid_grupo: texto(tag, ItemKey::MusicBrainzReleaseGroupId),
        mbid_artista: texto(tag, ItemKey::MusicBrainzArtistId),
        acoustid_id: texto(tag, ItemKey::AcoustId),
    };
    Ok((tecnico, cruda))
}

/// Lo que la catalogación escribe en el archivo (`writer._escribir_tags`). Lo
/// demás que hubiera se conserva, como en la V1.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Escritura {
    pub titulo: Option<String>,
    pub artista: Option<String>,
    pub album: Option<String>,
    pub numero: Option<u32>,
    pub total: Option<u32>,
    pub anio: Option<i32>,
    pub isrc: Option<String>,
    pub mbid_grabacion: Option<String>,
    pub mbid_lanzamiento: Option<String>,
    pub mbid_grupo: Option<String>,
    /// `Album`, `Single`, `EP`…
    pub tipo_lanzamiento: Option<String>,
}

/// Escribe sobre una copia y la pone en su sitio al terminar: un corte a medias
/// no deja nunca un archivo con las etiquetas rotas.
///
/// # Errors
///
/// - Los de [`leer`] si el archivo no se puede abrir.
/// - [`NsError::StorageFailure`] si no se puede escribir.
pub fn escribir(ruta: &Path, e: &Escritura) -> NsResult<()> {
    // La extensión se conserva: `lofty` reconoce el formato por ella.
    let temporal = ruta.with_extension(format!(
        "ns-parcial.{}",
        ruta.extension().and_then(|x| x.to_str()).unwrap_or("audio")
    ));
    std::fs::copy(ruta, &temporal).map_err(|_| NsError::StorageFailure)?;
    let resultado = (|| {
        let mut archivo = abrir(&temporal)?;
        let tipo = archivo.primary_tag_type();
        if archivo.tag(tipo).is_none() {
            archivo.insert_tag(Tag::new(tipo));
        }
        let tag = archivo.tag_mut(tipo).ok_or(NsError::Internal)?;
        let mut poner = |clave: ItemKey, valor: &Option<String>| {
            if let Some(v) = valor.as_deref().map(str::trim).filter(|v| !v.is_empty()) {
                tag.insert_text(clave, v.to_owned());
            }
        };
        poner(ItemKey::TrackTitle, &e.titulo);
        poner(ItemKey::TrackArtist, &e.artista);
        // La V1 escribía el mismo artista como artista del álbum (TPE2).
        poner(ItemKey::AlbumArtist, &e.artista);
        poner(ItemKey::AlbumTitle, &e.album);
        poner(ItemKey::Isrc, &e.isrc);
        poner(ItemKey::MusicBrainzRecordingId, &e.mbid_grabacion);
        poner(ItemKey::MusicBrainzReleaseId, &e.mbid_lanzamiento);
        poner(ItemKey::MusicBrainzReleaseGroupId, &e.mbid_grupo);
        poner(ItemKey::MusicBrainzReleaseType, &e.tipo_lanzamiento);
        if let Some(n) = e.numero {
            tag.set_track(n);
        }
        if let Some(t) = e.total {
            tag.set_track_total(t);
        }
        if let Some(a) = e.anio {
            tag.insert_text(ItemKey::RecordingDate, a.to_string());
        }
        archivo
            .save_to_path(&temporal, WriteOptions::default())
            .map_err(|error| {
                tracing::error!(error = %error, "no se pudieron escribir las etiquetas");
                NsError::StorageFailure
            })
    })();
    match resultado
        .and_then(|()| std::fs::rename(&temporal, ruta).map_err(|_| NsError::StorageFailure))
    {
        Ok(()) => Ok(()),
        Err(e) => {
            let _ = std::fs::remove_file(&temporal);
            Err(e)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::audio::pruebas::wav;

    fn temporal(nombre: &str) -> std::path::PathBuf {
        let d = std::env::temp_dir().join(format!("ns-etiquetas-{nombre}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d.join("pista.wav")
    }

    #[test]
    fn un_archivo_sin_etiquetas_da_lo_tecnico_y_nada_mas() {
        let ruta = temporal("vacio");
        let _ = wav(&ruta, 44_100, 44_100 * 2, |_, _| 0.1);
        let (t, c) = leer(&ruta).unwrap();
        assert!((t.duracion_seg - 2.0).abs() < 0.01, "{t:?}");
        assert_eq!((t.frecuencia, t.canales), (Some(44_100), Some(2)));
        assert_eq!(c, Cruda::default());
    }

    #[test]
    fn lo_escrito_se_lee_igual_y_lo_demas_se_conserva() {
        let ruta = temporal("escribir");
        let _ = wav(&ruta, 44_100, 44_100, |_, _| 0.1);
        escribir(
            &ruta,
            &Escritura {
                titulo: Some("Clavado en un bar".into()),
                artista: Some("Maná".into()),
                album: Some("Sueños líquidos".into()),
                numero: Some(3),
                total: Some(12),
                anio: Some(1997),
                isrc: Some("MXF019700001".into()),
                mbid_grabacion: Some("abc".into()),
                ..Escritura::default()
            },
        )
        .unwrap();
        let (_, c) = leer(&ruta).unwrap();
        assert_eq!(c.titulo.as_deref(), Some("Clavado en un bar"));
        assert_eq!(c.artista.as_deref(), Some("Maná"));
        assert_eq!(c.artista_album.as_deref(), Some("Maná"));
        assert_eq!(c.album.as_deref(), Some("Sueños líquidos"));
        assert_eq!(c.numero.as_deref(), Some("3/12"));
        assert_eq!(c.anio.as_deref(), Some("1997"));
        assert_eq!(c.isrc.as_deref(), Some("MXF019700001"));
        assert_eq!(c.mbid_grabacion.as_deref(), Some("abc"));
        // Una segunda escritura parcial no borra lo que no toca.
        escribir(
            &ruta,
            &Escritura {
                titulo: Some("Otro".into()),
                ..Escritura::default()
            },
        )
        .unwrap();
        let (_, c) = leer(&ruta).unwrap();
        assert_eq!(
            (c.titulo.as_deref(), c.album.as_deref()),
            (Some("Otro"), Some("Sueños líquidos"))
        );
        let restos: Vec<_> = std::fs::read_dir(ruta.parent().unwrap())
            .unwrap()
            .filter_map(Result::ok)
            .filter(|e| e.file_name().to_string_lossy().contains("parcial"))
            .collect();
        assert!(restos.is_empty(), "no queda ningún temporal");
    }

    #[test]
    fn lo_que_no_es_audio_es_un_archivo_danado() {
        let ruta = temporal("basura");
        std::fs::write(&ruta, b"esto no es audio").unwrap();
        assert_eq!(leer(&ruta).unwrap_err(), NsError::AudioCorrupted);
        assert_eq!(
            leer(&ruta.with_file_name("no-existe.mp3")).unwrap_err(),
            NsError::FileNotFound
        );
    }

    /// Lo que leía `mutagen` en la V1 sobre un corpus local (`NS_ETIQUETAS_CORPUS`,
    /// la salida de un volcado de `_extraer_metadata_cruda`). Solo lee; solo cuenta.
    #[test]
    #[ignore = "necesita un corpus local"]
    fn el_corpus_local_se_lee_como_en_la_v1() {
        let Ok(ruta) = std::env::var("NS_ETIQUETAS_CORPUS") else {
            return;
        };
        let v1: Vec<serde_json::Value> =
            serde_json::from_str(&std::fs::read_to_string(ruta).unwrap()).unwrap();
        let mut distintos = std::collections::BTreeMap::<&str, usize>::new();
        let mut duracion_max = 0.0f64;
        for f in &v1 {
            let (t, c) = leer(Path::new(f["ruta"].as_str().unwrap())).unwrap();
            for (campo, nuestro) in [
                ("titulo", &c.titulo),
                ("artista", &c.artista),
                ("album", &c.album),
                ("artista_album", &c.artista_album),
                ("numero", &c.numero),
                ("anio", &c.anio),
                ("genero", &c.genero),
            ] {
                if f[campo].as_str() != nuestro.as_deref() {
                    *distintos.entry(campo).or_default() += 1;
                }
            }
            duracion_max =
                duracion_max.max((t.duracion_seg - f["duracion"].as_f64().unwrap()).abs());
        }
        assert!(
            distintos.is_empty() && duracion_max < 0.1,
            "{} archivos; distintos: {distintos:?}; duración, diferencia máxima {duracion_max:.3} s",
            v1.len()
        );
    }
}
