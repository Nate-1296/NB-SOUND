//! Letras de la red (F4.1.11): LRCLIB y lyrics.ovh, como `external/lyrics_client.py`
//! de la V1.
//!
//! Orden: LRCLIB exacto, LRCLIB buscando, lyrics.ovh exacto y lyrics.ovh por sus
//! sugerencias. La primera que dé letra gana. Un 429 se apunta como «bloqueado» y
//! se devuelve solo si nadie dio letra, para reintentar en otra importación.

use serde_json::Value;

use super::texto::{normalizar_titulo, para_comparacion, redondear, similitud_combinada};
use crate::error::NsError;
use crate::net::{Red, Servicio};

/// `LYRICS_SUGGEST_LIMIT`.
const SUGERENCIAS: usize = 3;
const PARECIDO_MINIMO: f64 = 0.72;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Estado {
    /// Con letra plana (y quizá sincronizada).
    Encontrada,
    /// Solo una de las dos.
    Parcial,
    NoEncontrada,
    /// El servicio pidió esperar.
    Bloqueada,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Resultado {
    pub estado: Estado,
    pub proveedor: &'static str,
    pub planas: String,
    pub sincronizadas: String,
    pub idioma: Option<String>,
    pub instrumental: bool,
    pub confianza: f64,
}

impl Resultado {
    fn nada(estado: Estado, proveedor: &'static str) -> Self {
        Self {
            estado,
            proveedor,
            planas: String::new(),
            sincronizadas: String::new(),
            idioma: None,
            instrumental: false,
            confianza: 0.0,
        }
    }

    fn con_letra(&self) -> bool {
        matches!(self.estado, Estado::Encontrada | Estado::Parcial)
    }
}

/// Una respuesta: el JSON, nada (404 o error) o bloqueado (429).
pub enum Respuesta {
    Json(Value),
    Nada,
    Bloqueado,
}

/// Lo que pide JSON a un servicio; en las pruebas, respuestas guardadas.
pub trait Fuente {
    fn pedir(&self, servicio: Servicio, url: &str) -> Respuesta;
}

/// La red de verdad, con un reintento ante fallos de servidor, como la V1.
pub struct EnLaRed<'a>(pub &'a Red);

impl Fuente for EnLaRed<'_> {
    fn pedir(&self, servicio: Servicio, url: &str) -> Respuesta {
        for intento in 1..=2u64 {
            match self.0.obtener_con_estado(servicio, url, &[]) {
                Ok((429, _)) => return Respuesta::Bloqueado,
                Ok((200..=299, cuerpo)) => {
                    return serde_json::from_slice(&cuerpo).map_or(Respuesta::Nada, Respuesta::Json)
                }
                Ok((500..=599, _)) | Err(NsError::NetworkFailure) if intento == 1 => {
                    std::thread::sleep(std::time::Duration::from_millis(800));
                }
                _ => return Respuesta::Nada,
            }
        }
        Respuesta::Nada
    }
}

/// `urllib.parse.quote`: deja sin codificar lo seguro y la barra.
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

fn de_lrclib(d: &Value) -> Resultado {
    let s = |k: &str| {
        d.get(k)
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_owned()
    };
    let (planas, sincronizadas) = (s("plainLyrics"), s("syncedLyrics"));
    if planas.is_empty() && sincronizadas.is_empty() {
        return Resultado::nada(Estado::NoEncontrada, "lrclib");
    }
    Resultado {
        estado: if planas.is_empty() {
            Estado::Parcial
        } else {
            Estado::Encontrada
        },
        proveedor: "lrclib",
        confianza: if !planas.is_empty() && !sincronizadas.is_empty() {
            0.93
        } else {
            0.82
        },
        idioma: Some(s("language")).filter(|l| !l.is_empty()),
        instrumental: d
            .get("instrumental")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        planas,
        sincronizadas,
    }
}

/// `_score_text_match`.
fn parecido(artista_c: &str, artista: &str, titulo_c: &str, titulo: &str) -> f64 {
    let t = similitud_combinada(&normalizar_titulo(titulo_c), &normalizar_titulo(titulo));
    let a = similitud_combinada(&para_comparacion(artista_c), &para_comparacion(artista));
    redondear(t * 0.62 + a * 0.38, 4)
}

/// `_score_lrclib_row`.
fn puntuar_fila(f: &Value, artista: &str, titulo: &str, duracion: Option<f64>, album: &str) -> f64 {
    let s = |k: &str| {
        f.get(k)
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_owned()
    };
    let titulo_c = {
        let t = s("trackName");
        if t.is_empty() {
            s("name")
        } else {
            t
        }
    };
    let mut p = parecido(&s("artistName"), artista, &titulo_c, titulo);
    let album_c = s("albumName");
    if !album.is_empty() && !album_c.is_empty() {
        p = p * 0.85 + similitud_combinada(&album_c, album) * 0.15;
    }
    if let Some(d) = duracion.filter(|d| *d != 0.0) {
        let c = f.get("duration").and_then(Value::as_f64).unwrap_or(0.0);
        if c > 0.0 {
            let delta = (c - d).abs();
            if delta <= 3.0 {
                p += 0.08;
            } else if delta <= 10.0 {
                p += 0.03;
            } else if delta > 30.0 {
                p -= 0.18;
            }
        }
    }
    redondear(p.clamp(0.0, 1.0), 4)
}

fn lrclib(f: &dyn Fuente, artista: &str, titulo: &str, duracion: Option<f64>) -> Resultado {
    let mut url = format!(
        "https://lrclib.net/api/get?artist_name={}&track_name={}",
        quote(artista),
        quote(titulo)
    );
    if let Some(d) = duracion.filter(|d| *d != 0.0) {
        url.push_str(&format!("&duration={}", d.round() as i64));
    }
    match f.pedir(Servicio::Lrclib, &url) {
        Respuesta::Bloqueado => Resultado::nada(Estado::Bloqueada, "lrclib"),
        Respuesta::Json(v) if v.as_object().is_some_and(|o| !o.is_empty()) => de_lrclib(&v),
        _ => Resultado::nada(Estado::NoEncontrada, "lrclib"),
    }
}

fn lrclib_buscando(
    f: &dyn Fuente,
    artista: &str,
    titulo: &str,
    duracion: Option<f64>,
    album: &str,
) -> Resultado {
    let url = format!(
        "https://lrclib.net/api/search?q={}",
        quote(&format!("{artista} {titulo}"))
    );
    let filas = match f.pedir(Servicio::Lrclib, &url) {
        Respuesta::Bloqueado => return Resultado::nada(Estado::Bloqueada, "lrclib"),
        Respuesta::Json(Value::Array(filas)) => filas,
        _ => return Resultado::nada(Estado::NoEncontrada, "lrclib"),
    };
    let mut puntuadas: Vec<(f64, &Value)> = filas
        .iter()
        .filter(|f| f.is_object())
        .map(|f| (puntuar_fila(f, artista, titulo, duracion, album), f))
        .filter(|(p, _)| *p >= PARECIDO_MINIMO)
        .collect();
    puntuadas.sort_by(|a, b| b.0.total_cmp(&a.0));
    let Some((p, mejor)) = puntuadas.first() else {
        return Resultado::nada(Estado::NoEncontrada, "lrclib");
    };
    let mut r = de_lrclib(mejor);
    r.confianza = r.confianza.max(p.min(0.9));
    r
}

fn ovh(f: &dyn Fuente, artista: &str, titulo: &str) -> Resultado {
    let url = format!(
        "https://api.lyrics.ovh/v1/{}/{}",
        quote(artista),
        quote(titulo)
    );
    match f.pedir(Servicio::LyricsOvh, &url) {
        Respuesta::Bloqueado => Resultado::nada(Estado::Bloqueada, "lyrics_ovh"),
        Respuesta::Json(v) => {
            let planas = v
                .get("lyrics")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .trim()
                .to_owned();
            if planas.is_empty() {
                return Resultado::nada(Estado::NoEncontrada, "lyrics_ovh");
            }
            Resultado {
                estado: Estado::Parcial,
                proveedor: "lyrics_ovh",
                planas,
                confianza: 0.65,
                ..Resultado::nada(Estado::Parcial, "lyrics_ovh")
            }
        }
        Respuesta::Nada => Resultado::nada(Estado::NoEncontrada, "lyrics_ovh"),
    }
}

fn ovh_sugerencias(f: &dyn Fuente, artista: &str, titulo: &str) -> Resultado {
    let url = format!(
        "https://api.lyrics.ovh/suggest/{}",
        quote(&format!("{artista} {titulo}"))
    );
    let filas = match f.pedir(Servicio::LyricsOvh, &url) {
        Respuesta::Bloqueado => return Resultado::nada(Estado::Bloqueada, "lyrics_ovh"),
        Respuesta::Json(v) => v
            .get("data")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default(),
        Respuesta::Nada => return Resultado::nada(Estado::NoEncontrada, "lyrics_ovh"),
    };
    let mut intentos = 0;
    for fila in filas.iter().filter(|f| f.is_object()) {
        if intentos >= SUGERENCIAS {
            break;
        }
        let s = |v: &Value, k: &str| {
            v.get(k)
                .and_then(Value::as_str)
                .unwrap_or_default()
                .trim()
                .to_owned()
        };
        let titulo_c = {
            let t = s(fila, "title_short");
            if t.is_empty() {
                s(fila, "title")
            } else {
                t
            }
        };
        let artista_c = fila.get("artist").map(|a| s(a, "name")).unwrap_or_default();
        if parecido(&artista_c, artista, &titulo_c, titulo) < PARECIDO_MINIMO {
            continue;
        }
        intentos += 1;
        let a = if artista_c.is_empty() {
            artista
        } else {
            &artista_c
        };
        let t = if titulo_c.is_empty() {
            titulo
        } else {
            &titulo_c
        };
        let mut r = ovh(f, a, t);
        if r.con_letra() {
            r.confianza = r.confianza.max(0.72);
            return r;
        }
    }
    Resultado::nada(Estado::NoEncontrada, "lyrics_ovh")
}

/// `LyricsClient.fetch`. Sin artista o sin título no se pregunta.
pub fn buscar(
    f: &dyn Fuente,
    artista: &str,
    titulo: &str,
    duracion: Option<f64>,
    album: &str,
) -> Resultado {
    let (artista, titulo) = (artista.trim(), titulo.trim());
    if artista.is_empty() || titulo.is_empty() {
        return Resultado::nada(Estado::Parcial, "");
    }
    let mut bloqueada: Option<Resultado> = None;
    let r = lrclib(f, artista, titulo, duracion);
    if r.con_letra() {
        return r;
    }
    if r.estado == Estado::Bloqueada {
        bloqueada = Some(r);
    } else {
        let r = lrclib_buscando(f, artista, titulo, duracion, album);
        if r.con_letra() {
            return r;
        }
        if r.estado == Estado::Bloqueada {
            bloqueada = Some(r);
        }
    }
    let r = ovh(f, artista, titulo);
    if r.con_letra() {
        return r;
    }
    if r.estado == Estado::Bloqueada {
        bloqueada = bloqueada.or(Some(r));
    }
    let r = ovh_sugerencias(f, artista, titulo);
    if r.con_letra() {
        return r;
    }
    if r.estado == Estado::Bloqueada {
        bloqueada = bloqueada.or(Some(r));
    }
    bloqueada.unwrap_or_else(|| Resultado::nada(Estado::NoEncontrada, ""))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::cell::RefCell;

    struct Guardada {
        respuestas: Vec<(&'static str, Option<Value>)>,
        pedidas: RefCell<Vec<String>>,
    }

    impl Fuente for Guardada {
        fn pedir(&self, _: Servicio, url: &str) -> Respuesta {
            self.pedidas.borrow_mut().push(url.to_owned());
            match self.respuestas.iter().find(|(p, _)| url.contains(p)) {
                Some((_, Some(v))) => Respuesta::Json(v.clone()),
                Some((_, None)) => Respuesta::Bloqueado,
                None => Respuesta::Nada,
            }
        }
    }

    fn fuente(r: Vec<(&'static str, Option<Value>)>) -> Guardada {
        Guardada {
            respuestas: r,
            pedidas: RefCell::new(Vec::new()),
        }
    }

    #[test]
    fn lrclib_exacto_gana_con_letra_sincronizada() {
        let f = fuente(vec![(
            "api/get",
            Some(json!({"plainLyrics": "a\nb", "syncedLyrics": "[00:01.00] a", "language": "es"})),
        )]);
        let r = buscar(&f, "Maná", "Clavado en un bar", Some(300.4), "");
        assert_eq!(
            (r.estado, r.proveedor, r.confianza),
            (Estado::Encontrada, "lrclib", 0.93)
        );
        assert!(f.pedidas.borrow()[0]
            .contains("artist_name=Man%C3%A1&track_name=Clavado%20en%20un%20bar&duration=300"));
    }

    #[test]
    fn la_busqueda_elige_la_fila_que_se_parece() {
        let f = fuente(vec![(
            "api/search",
            Some(json!([
                {"artistName": "Otro", "trackName": "Otra cosa", "plainLyrics": "no"},
                {"artistName": "Maná", "trackName": "Clavado En Un Bar", "duration": 301, "plainLyrics": "sí"}
            ])),
        )]);
        let r = buscar(&f, "Maná", "Clavado en un bar", Some(300.0), "");
        assert_eq!((r.estado, r.planas.as_str()), (Estado::Encontrada, "sí"));
        assert!((r.confianza - 0.9).abs() < 1e-9);
    }

    #[test]
    fn lyrics_ovh_por_sus_sugerencias() {
        let f = fuente(vec![
            (
                "suggest/",
                Some(json!({"data": [{"title": "Clavado en un bar", "artist": {"name": "Mana"}}]})),
            ),
            ("v1/Mana/", Some(json!({"lyrics": "letra"}))),
        ]);
        let r = buscar(&f, "Maná", "Clavado en un bar", None, "");
        assert_eq!(
            (r.estado, r.proveedor, r.confianza),
            (Estado::Parcial, "lyrics_ovh", 0.72)
        );
    }

    #[test]
    fn bloqueado_solo_si_nadie_dio_letra() {
        let f = fuente(vec![("api/get", None)]);
        let r = buscar(&f, "A", "B", None, "");
        assert_eq!(r.estado, Estado::Bloqueada);
        assert!(
            f.pedidas.borrow().iter().all(|u| !u.contains("api/search")),
            "bloqueado, no se busca en LRCLIB"
        );
        assert_eq!(
            buscar(&fuente(vec![]), "A", "B", None, "").estado,
            Estado::NoEncontrada
        );
        assert_eq!(
            buscar(&fuente(vec![]), "", "B", None, "").estado,
            Estado::Parcial
        );
    }

    #[test]
    fn quote_deja_la_barra_como_python() {
        assert_eq!(quote("AC/DC & Co"), "AC/DC%20%26%20Co");
    }
}
