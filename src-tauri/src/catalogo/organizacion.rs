//! Dónde va cada pista dentro de la carpeta de música (parte de F4.1.4 y F4.1.9).
//!
//! La regla de la V1 (`core/writer.py`, `construir_ruta_destino`, y
//! `core/discography.py`), que es la que tiene hoy la biblioteca real:
//!
//! ```text
//! <artista>/albumes/<álbum>/<nn>_<título>.<ext>
//! <artista>/singles_y_ep/<lanzamiento>/<nn>_<título>.<ext>
//! <artista>/otros[/<álbum>]/<nn>_<título>.<ext>
//! ```
//!
//! con los nombres pasados por [`construir_slug`] y `00` si no hay número. La
//! única diferencia: la V1 convertía todo a MP3 y la V2 conserva la extensión.

use std::path::{Path, PathBuf};

use super::texto::{construir_slug, limpiar_version_titulo, para_comparacion, similitud_combinada};

/// `RELEASE_TYPE_TO_FOLDER`.
fn carpeta_de_tipo(tipo: &str) -> Option<&'static str> {
    Some(match tipo {
        "Album" => "albumes",
        "Single" | "EP" => "singles_y_ep",
        "Compilation" | "Live" | "Remix" | "DJ-mix" | "Mixtape/Street" | "Soundtrack"
        | "Audiobook" | "Interview" | "Spoken Word" | "Other" => "otros",
        _ => return None,
    })
}

/// Lo que decide la ruta.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Destino<'a> {
    pub artista: &'a str,
    pub titulo: &'a str,
    pub album: &'a str,
    /// `Album`, `Single`, `EP`… o vacío si no se sabe.
    pub tipo: &'a str,
    pub numero: Option<u32>,
    pub extension: &'a str,
}

/// La carpeta de tipo y la del álbum (`_clasificar_carpeta_biblioteca`).
fn clasificar(d: &Destino<'_>) -> (&'static str, Option<String>) {
    if let Some(carpeta) = carpeta_de_tipo(d.tipo) {
        if carpeta == "otros" {
            return (
                "otros",
                (!d.album.is_empty()).then(|| construir_slug(d.album)),
            );
        }
        let album = if d.album.is_empty() {
            "sin_album"
        } else {
            d.album
        };
        return (carpeta, Some(construir_slug(album)));
    }
    if !d.album.is_empty() {
        // Sin tipo, un lanzamiento que se llama como la pista es un sencillo.
        let titulo = para_comparacion(&limpiar_version_titulo(d.titulo));
        let album = para_comparacion(&limpiar_version_titulo(d.album));
        let parecido = if titulo.is_empty() || album.is_empty() {
            0.0
        } else {
            similitud_combinada(&titulo, &album)
        };
        let carpeta = if parecido >= 0.75 {
            "singles_y_ep"
        } else {
            "albumes"
        };
        return (carpeta, Some(construir_slug(d.album)));
    }
    ("otros", None)
}

/// La ruta relativa a la carpeta de música.
pub fn ruta_relativa(d: &Destino<'_>) -> PathBuf {
    let artista = if d.artista.trim().is_empty() {
        "desconocido"
    } else {
        d.artista
    };
    let (carpeta, sub) = clasificar(d);
    let mut r = PathBuf::from(construir_slug(artista)).join(carpeta);
    if let Some(s) = sub {
        r.push(s);
    }
    let ext = d.extension.trim_start_matches('.').to_lowercase();
    r.push(format!(
        "{:02}_{}.{ext}",
        d.numero.unwrap_or(0),
        construir_slug(d.titulo)
    ));
    r
}

/// Si ya hay un archivo con ese nombre, `_2`, `_3`… (`_resolver_conflicto`).
pub fn sin_conflicto(ruta: &Path) -> PathBuf {
    if !ruta.exists() {
        return ruta.to_path_buf();
    }
    let stem = ruta
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or_default();
    let ext = ruta
        .extension()
        .and_then(|s| s.to_str())
        .map(|e| format!(".{e}"))
        .unwrap_or_default();
    (2..10_000)
        .map(|n| ruta.with_file_name(format!("{stem}_{n}{ext}")))
        .find(|c| !c.exists())
        .unwrap_or_else(|| ruta.to_path_buf())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn d<'a>(tipo: &'a str, album: &'a str, titulo: &'a str, numero: Option<u32>) -> Destino<'a> {
        Destino {
            artista: "Benny Blanco",
            titulo,
            album,
            tipo,
            numero,
            extension: "mp3",
        }
    }

    #[test]
    fn la_ruta_es_la_de_la_biblioteca_de_la_v1() {
        let r = |x: Destino<'_>| ruta_relativa(&x).to_string_lossy().replace('\\', "/");
        assert_eq!(
            r(d("Single", "Bad Decisions", "Bad Decisions", None)),
            "benny_blanco/singles_y_ep/bad_decisions/00_bad_decisions.mp3"
        );
        assert_eq!(
            r(d("Album", "Friends Keep Secrets", "Eastside", Some(3))),
            "benny_blanco/albumes/friends_keep_secrets/03_eastside.mp3"
        );
        assert_eq!(
            r(d("Album", "", "X", Some(1))),
            "benny_blanco/albumes/sin_album/01_x.mp3"
        );
        assert_eq!(
            r(d("Compilation", "Hits", "X", Some(12))),
            "benny_blanco/otros/hits/12_x.mp3"
        );
        assert_eq!(r(d("", "", "X", None)), "benny_blanco/otros/00_x.mp3");
        assert_eq!(
            r(d("", "You", "You", None)),
            "benny_blanco/singles_y_ep/you/00_you.mp3"
        );
        assert_eq!(
            r(d("", "Un disco", "Otra cosa", Some(2))),
            "benny_blanco/albumes/un_disco/02_otra_cosa.mp3"
        );
        let flac = Destino {
            extension: ".FLAC",
            ..d("Album", "A", "B", Some(1))
        };
        assert!(r(flac).ends_with("01_b.flac"), "se conserva el formato");
    }

    #[test]
    fn un_nombre_ocupado_recibe_un_sufijo() {
        let dir = std::env::temp_dir().join(format!("ns-organizacion-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let a = dir.join("01_x.mp3");
        assert_eq!(sin_conflicto(&a), a);
        std::fs::write(&a, b"").unwrap();
        std::fs::write(dir.join("01_x_2.mp3"), b"").unwrap();
        assert_eq!(sin_conflicto(&a), dir.join("01_x_3.mp3"));
    }

    /// La biblioteca real de la V1 (`NS_RUTAS_CORPUS`: ruta, título, artista,
    /// álbum, tipo y número de cada pista). Solo cuenta coincidencias. La carpeta
    /// de tipo no se compara: la decidió el tipo de MusicBrainz al importar, y el
    /// `tipo` que guardó la base de la V1 es casi siempre `Album`.
    #[test]
    #[ignore = "necesita un corpus local"]
    fn la_biblioteca_local_tiene_las_rutas_de_esta_regla() {
        let Ok(ruta) = std::env::var("NS_RUTAS_CORPUS") else {
            return;
        };
        let v1: Vec<serde_json::Value> =
            serde_json::from_str(&std::fs::read_to_string(ruta).unwrap()).unwrap();
        let mut iguales = 0;
        for f in &v1 {
            let real = f["ruta"].as_str().unwrap();
            let t = |k: &str| f[k].as_str().unwrap_or_default().to_owned();
            let (titulo, artista, album, tipo) = (t("titulo"), t("artista"), t("album"), t("tipo"));
            let ext = Path::new(real)
                .extension()
                .and_then(|e| e.to_str())
                .unwrap_or("mp3");
            let nuestra = ruta_relativa(&Destino {
                artista: &artista,
                titulo: &titulo,
                album: &album,
                tipo: &tipo,
                numero: f["numero"].as_u64().map(|n| n as u32),
                extension: ext,
            });
            // Artista, álbum y archivo: las tres partes que pone esta regla. Un
            // sufijo `_2` es de un duplicado que ya estaba.
            let partes = |p: &Path| -> Vec<String> {
                let c: Vec<String> = p
                    .components()
                    .map(|c| c.as_os_str().to_string_lossy().into_owned())
                    .collect();
                let n = c.len();
                if n < 4 {
                    return c;
                }
                let archivo = Path::new(&c[n - 1]);
                let stem = archivo
                    .file_stem()
                    .and_then(|s| s.to_str())
                    .unwrap_or_default();
                let archivo = match stem.rsplit_once('_') {
                    Some((base, k))
                        if base.len() > 3
                            && k.len() == 1
                            && k.chars().all(|x| x.is_ascii_digit()) =>
                    {
                        format!("{base}.{ext}")
                    }
                    _ => c[n - 1].clone(),
                };
                vec![c[n - 4].clone(), c[n - 2].clone(), archivo]
            };
            if partes(Path::new(real)) == partes(&nuestra) {
                iguales += 1;
            } else if std::env::var("NS_VER").is_ok() {
                eprintln!("{real}  <>  {}", nuestra.display());
            }
        }
        let parte = iguales as f64 / v1.len() as f64;
        assert!(
            parte > 0.98,
            "{iguales} de {} rutas iguales ({:.1} %)",
            v1.len(),
            parte * 100.0
        );
    }
}
