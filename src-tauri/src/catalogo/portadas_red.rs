//! Portadas e imágenes de artista (F4.1.10): `core/assets_pipeline.py` de la V1.
//!
//! - **Pista**: la que trae el archivo en sus etiquetas.
//! - **Álbum**: Cover Art Archive (el lanzamiento y, si no, su grupo) y, si no
//!   hay, iTunes.
//! - **Artista**: TheAudioDB (si hay clave), Deezer, iTunes y Wikipedia, cada uno
//!   con su puntuación; gana la mayor.
//!
//! La V1 guardaba dos copias de cada imagen, la normal y la HD; la V2 guarda una
//! sola por contenido, la HD si existe (P11), y las miniaturas salen de ella
//! (`portadas.rs`). Solo JPEG y PNG, los dos formatos que decodifica la V2.

use std::path::Path;

use regex::Regex;
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};
use crate::importador_v1::archivos::dimensiones_de;
use crate::net::Servicio;
use crate::paths::Rutas;

/// `ASSETS_HD_MAX_IMAGE_BYTES` y `ASSETS_MIN_RESOLUTION`.
const MAX_BYTES: usize = 25_000_000;
const RESOLUCION_MINIMA: u32 = 250;
const LADO_HD: u32 = 1000;

/// Una imagen descargada o extraída, ya comprobada.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Imagen {
    pub bytes: Vec<u8>,
    pub ancho: u32,
    pub alto: u32,
    pub mime: &'static str,
    /// `etiqueta`, `cover_art_archive`, `itunes`, `deezer`…
    pub origen: &'static str,
}

impl Imagen {
    /// `_inspeccionar_imagen`: solo JPEG o PNG con tamaño legible.
    pub fn de(bytes: Vec<u8>, origen: &'static str) -> Option<Self> {
        if bytes.is_empty() || bytes.len() > MAX_BYTES {
            return None;
        }
        let (ancho, alto, mime) = dimensiones_de(&bytes)?;
        Some(Self {
            bytes,
            ancho,
            alto,
            mime,
            origen,
        })
    }

    pub fn es_hd(&self) -> bool {
        self.ancho.min(self.alto) >= LADO_HD
    }
}

/// Lo que pide bytes a un servicio. `None` si no hay o falla.
pub trait Fuente {
    fn json(&self, servicio: Servicio, url: &str) -> Option<Value>;
    fn bytes(&self, servicio: Servicio, url: &str) -> Option<Vec<u8>>;
}

pub struct EnLaRed<'a>(pub &'a crate::net::Red);

impl Fuente for EnLaRed<'_> {
    fn json(&self, servicio: Servicio, url: &str) -> Option<Value> {
        let cuerpo = self
            .0
            .obtener(servicio, url, &[("Accept", "application/json")])
            .ok()?;
        serde_json::from_slice(&cuerpo).ok()
    }

    fn bytes(&self, servicio: Servicio, url: &str) -> Option<Vec<u8>> {
        self.0
            .obtener(
                servicio,
                url,
                &[("Accept", "image/jpeg,image/png,image/*;q=0.8")],
            )
            .ok()
    }
}

fn quote(texto: &str) -> String {
    let mut s = String::with_capacity(texto.len() * 3);
    for b in texto.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' | b'/' => {
                s.push(b as char)
            }
            _ => s.push_str(&format!("%{b:02X}")),
        }
    }
    s
}

/// La portada que trae el archivo, la primera de sus imágenes.
pub fn de_etiquetas(ruta: &Path) -> Option<Imagen> {
    use lofty::file::TaggedFileExt;
    let f = lofty::read_from_path(ruta).ok()?;
    let tag = f.primary_tag().or_else(|| f.first_tag())?;
    let p = tag
        .pictures()
        .iter()
        .find(|p| p.pic_type() == lofty::picture::PictureType::CoverFront)
        .or_else(|| tag.pictures().first())?;
    Imagen::de(p.data().to_vec(), "etiqueta")
}

/// `_seleccionar_urls_caa`: la frontal (o la primera) y, para HD, la original y
/// las miniaturas grandes.
pub fn urls_caa(d: &Value) -> (String, Vec<String>) {
    let Some(imagenes) = d.get("images").and_then(Value::as_array) else {
        return (String::new(), Vec::new());
    };
    let frontales: Vec<&Value> = imagenes
        .iter()
        .filter(|i| i.get("front").and_then(Value::as_bool) == Some(true))
        .collect();
    let Some(img) = frontales
        .first()
        .copied()
        .or_else(|| imagenes.iter().find(|i| i.is_object()))
    else {
        return (String::new(), Vec::new());
    };
    let t = img.get("thumbnails").cloned().unwrap_or(Value::Null);
    let s = |v: &Value, k: &str| {
        v.get(k)
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_owned()
    };
    let normal = ["500", "large", "1200"]
        .iter()
        .map(|k| s(&t, k))
        .find(|u| !u.is_empty())
        .unwrap_or_else(|| s(img, "image"));
    let mut hd = Vec::new();
    for u in
        std::iter::once(s(img, "image")).chain(["1200", "500", "large"].iter().map(|k| s(&t, k)))
    {
        if !u.is_empty() && !hd.contains(&u) {
            hd.push(u);
        }
    }
    (normal, hd)
}

/// `_itunes_artwork_variant`: la misma imagen de iTunes a otro tamaño.
pub fn variante_itunes(url: &str, lado: u32) -> String {
    let base = url.trim();
    let bb = Regex::new(r"\d+x\d+bb").expect("compila");
    if bb.is_match(base) {
        return bb
            .replace(base, format!("{lado}x{lado}bb").as_str())
            .into_owned();
    }
    let guion = Regex::new(r"\d+x\d+-\d+").expect("compila");
    if guion.is_match(base) {
        return guion
            .replace(base, format!("{lado}x{lado}bb").as_str())
            .into_owned();
    }
    base.to_owned()
}

/// `_itunes_hd_candidates`.
pub fn candidatas_hd_itunes(url: &str) -> Vec<String> {
    let mut v: Vec<String> = Vec::new();
    for lado in [3000, 2000, 1200, 1000, 600] {
        let u = variante_itunes(url, lado);
        if !u.is_empty() && !v.contains(&u) {
            v.push(u);
        }
    }
    v
}

/// `_seleccionar_url_itunes`: la del álbum que contiene el nombre buscado o, si
/// no, la primera.
pub fn url_itunes_album(d: &Value, album: &str) -> Option<String> {
    let filas = d.get("results")?.as_array()?;
    let objetivo = album.trim().to_lowercase();
    let arte = |f: &Value| {
        f.get("artworkUrl100")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|u| !u.is_empty())
            .map(str::to_owned)
    };
    for f in filas {
        let nombre = f
            .get("collectionName")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_lowercase();
        if let Some(a) = arte(f) {
            if !objetivo.is_empty() && nombre.contains(&objetivo) {
                return Some(variante_itunes(&a, 600));
            }
        }
    }
    arte(filas.first()?).map(|a| variante_itunes(&a, 600))
}

/// La mejor imagen de una lista de URL: la primera HD y, si ninguna lo es, la
/// normal.
fn descargar(
    f: &dyn Fuente,
    servicio: Servicio,
    origen: &'static str,
    hd: &[String],
    normal: &str,
) -> Option<Imagen> {
    for u in hd {
        if let Some(i) = f.bytes(servicio, u).and_then(|b| Imagen::de(b, origen)) {
            if i.es_hd() {
                return Some(i);
            }
        }
    }
    f.bytes(servicio, normal)
        .and_then(|b| Imagen::de(b, origen))
}

/// La portada de un álbum: Cover Art Archive y, si no, iTunes
/// (`_descargar_portadas_album` y su respaldo).
pub fn portada_album(
    f: &dyn Fuente,
    lanzamiento: &str,
    grupo: &str,
    artista: &str,
    album: &str,
) -> Option<Imagen> {
    for (tipo, id) in [
        ("release", lanzamiento.trim()),
        ("release-group", grupo.trim()),
    ] {
        if id.is_empty() {
            continue;
        }
        let base = format!("https://coverartarchive.org/{tipo}/{}", quote(id));
        let (mut normal, mut hd) = f
            .json(Servicio::CoverArtArchive, &base)
            .map(|d| urls_caa(&d))
            .unwrap_or_default();
        if normal.is_empty() {
            normal = format!("{base}/front-500");
            hd = vec![format!("{base}/front")];
        }
        if let Some(i) = descargar(
            f,
            Servicio::CoverArtArchive,
            "cover_art_archive",
            &hd,
            &normal,
        ) {
            return Some(i);
        }
    }
    let (artista, album) = (artista.trim(), album.trim());
    if artista.is_empty() || album.is_empty() {
        return None;
    }
    let url = format!(
        "https://itunes.apple.com/search?term={}&entity=album&limit=5",
        quote(&format!("{artista} {album}"))
    );
    let normal = url_itunes_album(&f.json(Servicio::Itunes, &url)?, album)?;
    descargar(
        f,
        Servicio::Itunes,
        "itunes",
        &candidatas_hd_itunes(&normal),
        &normal,
    )
}

/// Una imagen de artista candidata (`AssetCandidate`).
#[derive(Debug, Clone, PartialEq)]
pub struct CandidataArtista {
    pub origen: &'static str,
    pub url: String,
    pub lado: u32,
    pub puntaje: f64,
}

/// `_score_candidate`.
fn puntuar(origen: &str, base: f64, lado: u32) -> f64 {
    let res = if lado == 0 || lado >= RESOLUCION_MINIMA {
        0.05
    } else {
        -0.08
    };
    let bono = match origen {
        "theaudiodb" => 0.10,
        "deezer" => 0.07,
        "itunes" => 0.05,
        "wikipedia" => 0.02,
        _ => 0.0,
    };
    super::texto::redondear((base + bono + res).clamp(0.0, 1.0), 4)
}

pub fn candidatas_artista(
    f: &dyn Fuente,
    nombre: &str,
    clave_theaudiodb: Option<&str>,
) -> Vec<CandidataArtista> {
    let nombre = nombre.trim();
    let mut c: Vec<CandidataArtista> = Vec::new();
    let s = |v: &Value, k: &str| {
        v.get(k)
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_owned()
    };
    if let Some(clave) = clave_theaudiodb.filter(|k| !k.is_empty()) {
        let url = format!(
            "https://www.theaudiodb.com/api/v1/json/{}/search.php?s={}",
            quote(clave),
            quote(nombre)
        );
        if let Some(a) = f
            .json(Servicio::TheAudioDb, &url)
            .and_then(|d| d.get("artists")?.as_array()?.first().cloned())
        {
            let u = [
                "strArtistThumb",
                "strArtistWideThumb",
                "strArtistFanart",
                "strArtistFanart2",
                "strArtistFanart3",
                "strArtistFanart4",
            ]
            .iter()
            .map(|k| s(&a, k))
            .find(|u| !u.is_empty());
            if let Some(url) = u {
                c.push(CandidataArtista {
                    origen: "theaudiodb",
                    url,
                    lado: 720,
                    puntaje: puntuar("theaudiodb", 0.8, 720),
                });
            }
        }
    }
    let url = format!("https://api.deezer.com/search/artist?q={}", quote(nombre));
    if let Some(p) = f
        .json(Servicio::Deezer, &url)
        .and_then(|d| d.get("data")?.as_array()?.first().cloned())
    {
        for (k, lado) in [
            ("picture_xl", 1000),
            ("picture_big", 500),
            ("picture_medium", 250),
            ("picture", 0),
        ] {
            let u = s(&p, k);
            if !u.is_empty() {
                c.push(CandidataArtista {
                    origen: "deezer",
                    url: u,
                    lado,
                    puntaje: puntuar("deezer", 0.72, lado),
                });
                break;
            }
        }
    }
    let url = format!(
        "https://itunes.apple.com/search?term={}&entity=musicArtist&limit=3",
        quote(nombre)
    );
    if let Some(filas) = f
        .json(Servicio::Itunes, &url)
        .and_then(|d| d.get("results")?.as_array().cloned())
    {
        if let Some(u) = filas
            .iter()
            .map(|r| s(r, "artworkUrl100"))
            .find(|u| !u.is_empty())
        {
            c.push(CandidataArtista {
                origen: "itunes",
                url: variante_itunes(&u, 600),
                lado: 600,
                puntaje: puntuar("itunes", 0.66, 600),
            });
        }
    }
    let url = format!(
        "https://en.wikipedia.org/api/rest_v1/page/summary/{}",
        quote(nombre)
    );
    if let Some(d) = f.json(Servicio::Wikipedia, &url) {
        let original = d
            .get("originalimage")
            .filter(|o| !s(o, "source").is_empty());
        if let Some(img) = original.or_else(|| d.get("thumbnail")) {
            let u = s(img, "source");
            if !u.is_empty() {
                let lado = img
                    .get("width")
                    .and_then(Value::as_u64)
                    .unwrap_or(0)
                    .min(img.get("height").and_then(Value::as_u64).unwrap_or(0))
                    as u32;
                c.push(CandidataArtista {
                    origen: "wikipedia",
                    url: u,
                    lado,
                    puntaje: puntuar("wikipedia", 0.58, lado),
                });
            }
        }
    }
    c.sort_by(|a, b| b.puntaje.total_cmp(&a.puntaje));
    c
}

/// La imagen de un artista: la candidata mejor puntuada que se pueda descargar.
pub fn imagen_artista(
    f: &dyn Fuente,
    nombre: &str,
    clave_theaudiodb: Option<&str>,
) -> Option<Imagen> {
    if nombre.trim().is_empty() {
        return None;
    }
    for c in candidatas_artista(f, nombre, clave_theaudiodb) {
        let servicio = match c.origen {
            "theaudiodb" => Servicio::TheAudioDb,
            "deezer" => Servicio::Deezer,
            "itunes" => Servicio::Itunes,
            _ => Servicio::Wikipedia,
        };
        if let Some(i) = f
            .bytes(servicio, &c.url)
            .and_then(|b| Imagen::de(b, c.origen))
        {
            return Some(i);
        }
    }
    None
}

/// Guarda una imagen en la carpeta de portadas, una vez por contenido, y devuelve
/// su fila en `portadas`.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede escribir.
pub fn guardar(db: &BaseDeDatos, rutas: &Rutas, i: &Imagen) -> NsResult<i64> {
    let sha: String = Sha256::digest(&i.bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    let ext = if i.mime == "image/png" { "png" } else { "jpg" };
    let relativa = format!("{}/{sha}.{ext}", &sha[..2]);
    let destino = rutas.portadas().join(&relativa);
    if !destino.is_file() {
        if let Some(dir) = destino.parent() {
            std::fs::create_dir_all(dir).map_err(|_| NsError::StorageFailure)?;
        }
        let temporal = destino.with_extension(format!("{}.parcial", std::process::id()));
        std::fs::write(&temporal, &i.bytes)
            .and_then(|()| std::fs::rename(&temporal, &destino))
            .map_err(|_| {
                let _ = std::fs::remove_file(&temporal);
                NsError::StorageFailure
            })?;
    }
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    let id: i64 = tx
        .query_row(
            "INSERT INTO portadas (sha256, ruta, ancho, alto, bytes, mime, origen)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
             ON CONFLICT (sha256) DO UPDATE SET sha256 = excluded.sha256
             RETURNING id",
            rusqlite::params![
                sha,
                relativa,
                i.ancho,
                i.alto,
                i.bytes.len() as i64,
                i.mime,
                i.origen
            ],
            |f| f.get(0),
        )
        .map_err(|_| NsError::StorageFailure)?;
    tx.commit().map_err(|_| NsError::StorageFailure)?;
    Ok(id)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::collections::HashMap;

    fn png(lado: u32) -> Vec<u8> {
        let mut b = Vec::new();
        image::RgbImage::new(lado, lado)
            .write_to(&mut std::io::Cursor::new(&mut b), image::ImageFormat::Png)
            .unwrap();
        b
    }

    struct Guardada {
        json: HashMap<&'static str, Value>,
        bytes: HashMap<String, Vec<u8>>,
    }

    impl Fuente for Guardada {
        fn json(&self, _: Servicio, url: &str) -> Option<Value> {
            self.json
                .iter()
                .find(|(k, _)| url.contains(*k))
                .map(|(_, v)| v.clone())
        }
        fn bytes(&self, _: Servicio, url: &str) -> Option<Vec<u8>> {
            self.bytes.get(url).cloned()
        }
    }

    #[test]
    fn de_cover_art_archive_se_queda_la_hd() {
        let caa = json!({"images": [
            {"front": false, "image": "https://x/back.jpg"},
            {"front": true, "image": "https://x/orig.png", "thumbnails": {"500": "https://x/500.png", "1200": "https://x/1200.png"}}
        ]});
        assert_eq!(
            urls_caa(&caa),
            (
                "https://x/500.png".into(),
                vec![
                    "https://x/orig.png".into(),
                    "https://x/1200.png".into(),
                    "https://x/500.png".into()
                ]
            )
        );
        let f = Guardada {
            json: HashMap::from([("coverartarchive.org/release/r1", caa)]),
            bytes: HashMap::from([
                ("https://x/1200.png".to_owned(), png(1200)),
                ("https://x/500.png".to_owned(), png(500)),
            ]),
        };
        let i = portada_album(&f, "r1", "", "A", "B").unwrap();
        assert_eq!(
            (i.ancho, i.origen, i.es_hd()),
            (1200, "cover_art_archive", true)
        );
    }

    #[test]
    fn sin_cover_art_archive_va_a_itunes() {
        let f = Guardada {
            json: HashMap::from([(
                "itunes.apple.com/search",
                json!({"results": [
                    {"collectionName": "Otro", "artworkUrl100": "https://a/otro/100x100bb.jpg"},
                    {"collectionName": "Sueños Líquidos (Remaster)", "artworkUrl100": "https://a/s/100x100bb.jpg"}
                ]}),
            )]),
            bytes: HashMap::from([("https://a/s/600x600bb.jpg".to_owned(), png(600))]),
        };
        let i = portada_album(&f, "", "", "Maná", "sueños líquidos").unwrap();
        assert_eq!((i.ancho, i.origen), (600, "itunes"));
        assert_eq!(
            candidatas_hd_itunes("https://a/s/600x600bb.jpg")[0],
            "https://a/s/3000x3000bb.jpg"
        );
    }

    #[test]
    fn la_imagen_de_artista_sigue_la_puntuacion_de_la_v1() {
        let f = Guardada {
            json: HashMap::from([
                (
                    "api.deezer.com",
                    json!({"data": [{"picture_xl": "https://d/xl.png"}]}),
                ),
                (
                    "en.wikipedia.org",
                    json!({"thumbnail": {"source": "https://w/t.png", "width": 200, "height": 300}}),
                ),
            ]),
            bytes: HashMap::from([
                ("https://d/xl.png".to_owned(), png(1000)),
                ("https://w/t.png".to_owned(), png(200)),
            ]),
        };
        let c = candidatas_artista(&f, "Maná", None);
        assert_eq!(
            c.iter().map(|x| (x.origen, x.puntaje)).collect::<Vec<_>>(),
            [("deezer", 0.84), ("wikipedia", 0.52)]
        );
        assert_eq!(imagen_artista(&f, "Maná", None).unwrap().origen, "deezer");
    }

    #[test]
    fn se_guarda_una_vez_por_contenido() {
        let dir = std::env::temp_dir().join(format!("ns-portadas-red-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let rutas = Rutas::bajo(&dir).unwrap();
        let db = BaseDeDatos::en_memoria().unwrap();
        let i = Imagen::de(png(300), "deezer").unwrap();
        let a = guardar(&db, &rutas, &i).unwrap();
        assert_eq!(guardar(&db, &rutas, &i).unwrap(), a);
        let n: i64 = db
            .conexion()
            .unwrap()
            .query_row("SELECT count(*) FROM portadas", [], |f| f.get(0))
            .unwrap();
        assert_eq!(n, 1);
        assert!(Imagen::de(b"no".to_vec(), "x").is_none());
    }
}
