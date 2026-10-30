//! Lo que la V1 guardaba en manifiestos JSONL y no en la base: las letras y el
//! mapa de portadas en alta resolución y de imágenes de artista.
//!
//! Los dos son registros que solo crecen: cada nueva obtención añade una línea, y
//! la V1 se queda con **la última** de cada archivo. Una línea que no se puede
//! leer se salta, como hacía la V1, y se cuenta.

use std::collections::HashMap;
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};

use serde::Deserialize;

/// Las letras de un archivo.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LetraV1 {
    pub planas: Option<String>,
    pub sincronizadas: Option<String>,
    pub proveedor: Option<String>,
    pub idioma: Option<String>,
    pub obtenidas_en: Option<String>,
}

#[derive(Deserialize)]
struct LineaEnriquecimiento {
    file: Option<String>,
    timestamp: Option<String>,
    lyrics: Option<LetrasEnLinea>,
}

#[derive(Deserialize)]
struct LetrasEnLinea {
    plain_lyrics: Option<String>,
    synced_lyrics: Option<String>,
    provider: Option<String>,
    language: Option<String>,
    fetched_at: Option<String>,
}

fn no_vacio(texto: Option<String>) -> Option<String> {
    texto.map(|t| t.trim().to_owned()).filter(|t| !t.is_empty())
}

/// Recorre un JSONL y entrega cada línea que se pudo leer. Devuelve cuántas se
/// saltaron.
fn recorrer<T: for<'de> Deserialize<'de>>(ruta: &Path, mut cada: impl FnMut(T)) -> usize {
    let Ok(archivo) = File::open(ruta) else {
        return 0;
    };
    let mut saltadas = 0;
    for linea in BufReader::new(archivo).lines() {
        let Ok(linea) = linea else {
            saltadas += 1;
            continue;
        };
        if linea.trim().is_empty() {
            continue;
        }
        match serde_json::from_str::<T>(&linea) {
            Ok(valor) => cada(valor),
            Err(_) => saltadas += 1,
        }
    }
    saltadas
}

/// Letras por la ruta del archivo, tal como la escribió la V1. La última línea
/// de cada ruta manda, también cuando dice que ya no hay letra.
pub fn letras(enriquecimiento: &Path) -> (HashMap<String, LetraV1>, usize) {
    let mut por_ruta: HashMap<String, Option<LetraV1>> = HashMap::new();
    let saltadas = recorrer::<LineaEnriquecimiento>(enriquecimiento, |l| {
        let Some(ruta) = no_vacio(l.file) else {
            return;
        };
        let letra = l.lyrics.and_then(|x| {
            let planas = no_vacio(x.plain_lyrics);
            let sincronizadas = no_vacio(x.synced_lyrics);
            (planas.is_some() || sincronizadas.is_some()).then(|| LetraV1 {
                planas,
                sincronizadas,
                proveedor: no_vacio(x.provider),
                idioma: no_vacio(x.language),
                obtenidas_en: no_vacio(x.fetched_at).or_else(|| no_vacio(l.timestamp.clone())),
            })
        });
        por_ruta.insert(ruta, letra);
    });
    let letras = por_ruta
        .into_iter()
        .filter_map(|(ruta, letra)| letra.map(|l| (ruta, l)))
        .collect();
    (letras, saltadas)
}

#[derive(Deserialize)]
struct LineaRecursos {
    release_id: Option<String>,
    artista: Option<String>,
    album_cover_hd: Option<String>,
    artist_avatar: Option<String>,
    artist_avatar_hd: Option<String>,
}

/// El mapa de portadas de la V1 (`assets_manifest.jsonl`).
#[derive(Debug, Default)]
pub struct Recursos {
    /// Portada en alta resolución por `mb_release_id`, que es como la V1 la
    /// resolvía (`servicios/biblioteca.py`, `mapa_releases_hd`).
    pub album_hd: HashMap<String, PathBuf>,
    /// Imagen de artista por su nombre exacto, la de alta resolución si la hay.
    pub artista: HashMap<String, PathBuf>,
    pub saltadas: usize,
}

/// Lee el mapa de portadas. Solo guarda rutas que existen: una entrada que
/// apunta a un archivo borrado no es una portada.
pub fn recursos(manifiesto: &Path) -> Recursos {
    let mut r = Recursos::default();
    let existe = |ruta: Option<String>| no_vacio(ruta).map(PathBuf::from).filter(|p| p.is_file());
    r.saltadas = recorrer::<LineaRecursos>(manifiesto, |l| {
        if let (Some(release), Some(hd)) = (no_vacio(l.release_id), existe(l.album_cover_hd)) {
            r.album_hd.insert(release, hd);
        }
        if let Some(artista) = no_vacio(l.artista) {
            if let Some(imagen) = existe(l.artist_avatar_hd).or_else(|| existe(l.artist_avatar)) {
                r.artista.insert(artista, imagen);
            }
        }
    });
    r
}

#[cfg(test)]
mod tests {
    use super::*;

    fn escribir(nombre: &str, contenido: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("ns-manifiestos-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let ruta = dir.join(nombre);
        std::fs::write(&ruta, contenido).unwrap();
        ruta
    }

    #[test]
    fn la_ultima_linea_de_cada_archivo_manda() {
        let ruta = escribir(
            "letras.jsonl",
            concat!(
                r#"{"file": "/m/a.mp3", "lyrics": {"plain_lyrics": "vieja", "provider": "lrclib"}}"#,
                "\n",
                "esto no es json\n",
                r#"{"file": "/m/a.mp3", "lyrics": {"plain_lyrics": "nueva", "synced_lyrics": "[00:01.00] nueva"}}"#,
                "\n",
                r#"{"file": "/m/b.mp3", "lyrics": {"plain_lyrics": "algo"}}"#,
                "\n",
                r#"{"file": "/m/b.mp3", "lyrics": {"plain_lyrics": "  ", "synced_lyrics": ""}}"#,
                "\n",
            ),
        );
        let (letras, saltadas) = letras(&ruta);
        assert_eq!(saltadas, 1);
        assert_eq!(letras.len(), 1, "la última de b dice que no hay letra");
        let a = &letras["/m/a.mp3"];
        assert_eq!(a.planas.as_deref(), Some("nueva"));
        assert_eq!(a.sincronizadas.as_deref(), Some("[00:01.00] nueva"));
        assert_eq!(a.proveedor, None);
    }

    #[test]
    fn el_mapa_de_portadas_ignora_archivos_que_ya_no_existen() {
        let imagen = escribir("hd.jpg", "x");
        let contenido = format!(
            "{}\n{}\n",
            serde_json::json!({"release_id": "r1", "album_cover_hd": imagen, "artista": "A",
                               "artist_avatar": imagen}),
            serde_json::json!({"release_id": "r2", "album_cover_hd": "/no/existe.jpg"}),
        );
        let r = recursos(&escribir("recursos.jsonl", &contenido));
        assert_eq!(r.album_hd.get("r1"), Some(&imagen));
        assert!(!r.album_hd.contains_key("r2"));
        assert_eq!(r.artista.get("A"), Some(&imagen));
    }

    #[test]
    fn un_manifiesto_que_no_existe_no_es_un_error() {
        let (letras, saltadas) = letras(Path::new("/no/existe.jsonl"));
        assert!(letras.is_empty());
        assert_eq!(saltadas, 0);
    }
}
