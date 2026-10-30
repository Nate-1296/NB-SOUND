//! MusicBrainz (F4.1.4): de unos datos normalizados a las grabaciones candidatas,
//! cada una con el mejor lanzamiento en el que aparece.
//!
//! Es `external/musicbrainz_client.py` de la V1 con sus seis estrategias, en su
//! orden y con sus condiciones de parada. La V1 hablaba con la API XML a través
//! de `musicbrainzngs`; la V2 usa la JSON, que trae lo mismo con otros nombres
//! (`releases` por `release-list`, `secondary-types` por `secondary-type-list`).
//! Una diferencia conocida: en los resultados de búsqueda la V1 casi nunca
//! encontraba el número de pista (buscaba la grabación dentro de cada pista, y la
//! búsqueda XML no la trae); la JSON da la pista de esa grabación directamente.
//! Se mide en la paridad global de la fase.

use std::collections::{HashMap, HashSet};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde_json::Value;

use super::texto::{
    detectar_tipo_variante, limpiar_version_titulo, para_comparacion, parsear_variante_titulo,
    separar_artista_principal,
};
use crate::error::{NsError, NsResult};
use crate::net::{Red, Servicio};

/// `MB_SEARCH_LIMIT`, `MB_MAX_RELEASES_PER_RECORDING`, `MAX_CANDIDATES_PER_FILE`,
/// `MIN_RESULTS_PER_STRATEGY` y `_UMBRAL_CANDIDATOS_SUFICIENTES` de la V1.
const LIMITE_BUSQUEDA: usize = 10;
const MAX_LANZAMIENTOS: usize = 15;
pub const MAX_CANDIDATOS: usize = 8;
const MIN_RESULTADOS_POR_ESTRATEGIA: usize = 3;
const CANDIDATOS_SUFICIENTES: usize = 3;
/// MusicBrainz pide como mucho una petición por segundo; la V1 dejaba 1,1 s.
const ENTRE_PETICIONES: Duration = Duration::from_millis(1100);
const REINTENTOS: u32 = 3;
const ESPERA_INICIAL: Duration = Duration::from_secs(2);

const SECUNDARIOS_PENALIZADOS: [&str; 7] = [
    "Live",
    "Remix",
    "Compilation",
    "DJ-mix",
    "Mixtape/Street",
    "Demo",
    "Interview",
];

/// `RELEASE_TYPE_PRIORITY`.
fn prioridad_tipo(tipo: &str) -> i64 {
    match tipo {
        "Album" => 50,
        "EP" => 40,
        "Single" => 35,
        "Compilation" => 20,
        "Soundtrack" => 15,
        "Live" => 12,
        "Remix" => 10,
        "DJ-mix" | "Mixtape/Street" => 8,
        "Broadcast" | "Other" => 5,
        "Audiobook" | "Interview" | "Spoken Word" => 3,
        "" => 2,
        _ => 5,
    }
}

/// Los alias de tipo de la V1 (`_ALIASES_TIPO`).
fn tipo_canonico(tipo: &str) -> String {
    match tipo.to_lowercase().as_str() {
        "album" => "Album",
        "single" => "Single",
        "ep" => "EP",
        "other" | "broadcast" => "Other",
        "compilation" => "Compilation",
        "live" => "Live",
        "remix" => "Remix",
        "dj-mix" => "DJ-mix",
        "mixtape/street" => "Mixtape/Street",
        "soundtrack" => "Soundtrack",
        "audiobook" => "Audiobook",
        "interview" => "Interview",
        "spoken word" => "Spoken Word",
        _ => return tipo.to_owned(),
    }
    .to_owned()
}

/// Una grabación con su mejor lanzamiento (`CandidatoMB`).
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Candidato {
    pub mbid_grabacion: String,
    pub mbid_lanzamiento: String,
    pub mbid_grupo: String,
    pub titulo: String,
    pub artista: String,
    pub artistas: Vec<String>,
    pub album: String,
    pub numero: Option<u32>,
    pub total: Option<u32>,
    pub anio: Option<i32>,
    pub duracion_seg: Option<f64>,
    pub isrc: Option<String>,
    pub tipo: String,
    pub secundarios: Vec<String>,
    pub estado: String,
    pub oficial: bool,
    pub recopilatorio: bool,
    pub de_acoustid: bool,
    pub puntaje: f64,
    pub penalizaciones: Vec<String>,
}

/// Lo que se busca: lo que dio la normalización.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Busqueda {
    pub artista: String,
    pub titulo: String,
    pub featuring: Option<String>,
    pub isrc: Option<String>,
    pub duracion_seg: Option<f64>,
}

fn s(v: &Value, k: &str) -> String {
    v.get(k)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_owned()
}

fn grupo(lanzamiento: &Value) -> &Value {
    lanzamiento
        .get("release-group")
        .filter(|g| g.is_object())
        .unwrap_or(&Value::Null)
}

fn secundarios(g: &Value) -> Vec<String> {
    g.get("secondary-types")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|t| {
            t.as_str()
                .map(str::trim)
                .filter(|t| !t.is_empty())
                .map(str::to_owned)
        })
        .collect()
}

fn fecha(l: &Value) -> String {
    let f = s(l, "date");
    if f.is_empty() {
        s(grupo(l), "first-release-date")
    } else {
        f
    }
}

/// `_score_release_quality`: oficial, el tipo, sin secundarios penalizados y el
/// más antiguo.
fn calidad(l: &Value) -> i64 {
    let mut p = match s(l, "status").as_str() {
        "Official" => 1000,
        "Promotion" => 100,
        _ => 0,
    };
    let g = grupo(l);
    let primario = s(g, "primary-type");
    let primario = match primario.to_lowercase().as_str() {
        "album" => "Album".to_owned(),
        "single" => "Single".to_owned(),
        "ep" => "EP".to_owned(),
        "other" | "broadcast" => "Other".to_owned(),
        _ => primario,
    };
    p += prioridad_tipo(&primario);
    p -= 200
        * secundarios(g)
            .iter()
            .filter(|t| SECUNDARIOS_PENALIZADOS.contains(&t.as_str()))
            .count() as i64;
    if let Some(anio) = fecha(l).get(..4).and_then(|a| a.parse::<i64>().ok()) {
        p += (2030 - anio).max(0);
    }
    p
}

/// La pista de esa grabación en el lanzamiento: en la búsqueda, cada medio trae
/// solo la suya (`track`); en una consulta por id, todas (`tracks`).
fn pista(l: &Value, grabacion: &str) -> Option<(u32, Option<u32>)> {
    for m in l
        .get("media")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let total = m
            .get("track-count")
            .and_then(Value::as_u64)
            .map(|t| t as u32);
        let pistas = m
            .get("track")
            .or_else(|| m.get("tracks"))
            .and_then(Value::as_array);
        for p in pistas.into_iter().flatten() {
            let es_esta = p
                .get("recording")
                .and_then(|r| r.get("id"))
                .and_then(Value::as_str)
                .is_none_or(|id| id == grabacion);
            if !es_esta {
                continue;
            }
            let numero = p
                .get("number")
                .and_then(Value::as_str)
                .and_then(|n| n.trim().parse::<u32>().ok())
                .or_else(|| p.get("position").and_then(Value::as_u64).map(|n| n as u32));
            if let Some(n) = numero {
                return Some((n, total));
            }
        }
    }
    None
}

/// Una grabación de la API como candidato (`_grabacion_a_candidato`). Sin
/// lanzamientos no es candidata: no habría álbum que escribir.
pub fn candidato_de(g: &Value) -> Option<Candidato> {
    let id = s(g, "id");
    let lanzamientos: Vec<&Value> = g
        .get("releases")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .take(MAX_LANZAMIENTOS)
        .collect();
    // El primero con la mejor calidad, como `max` estricto de la V1.
    let mut mejor: Option<(&Value, i64)> = None;
    for l in lanzamientos {
        let c = calidad(l);
        if mejor.is_none_or(|(_, m)| c > m) {
            mejor = Some((l, c));
        }
    }
    let (l, _) = mejor?;
    let creditos: Vec<String> = g
        .get("artist-credit")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|c| {
            c.get("artist")
                .and_then(|a| a.get("name"))
                .and_then(Value::as_str)
        })
        .filter(|n| !n.is_empty())
        .map(str::to_owned)
        .collect();
    let gr = grupo(l);
    let tipo = {
        let t = s(gr, "primary-type");
        if t.is_empty() {
            tipo_canonico(&s(gr, "type"))
        } else {
            tipo_canonico(&t)
        }
    };
    let sec = secundarios(gr);
    let estado = s(l, "status");
    let (numero, total) = pista(l, &id).map_or((None, None), |(n, t)| (Some(n), t));
    Some(Candidato {
        titulo: s(g, "title"),
        artista: creditos.first().cloned().unwrap_or_default(),
        artistas: creditos,
        duracion_seg: g
            .get("length")
            .and_then(Value::as_f64)
            .map(|ms| ms / 1000.0),
        isrc: g
            .get("isrcs")
            .and_then(Value::as_array)
            .and_then(|l| l.first())
            .and_then(Value::as_str)
            .map(str::to_owned),
        mbid_lanzamiento: s(l, "id"),
        album: s(l, "title"),
        oficial: estado == "Official",
        estado,
        numero,
        total,
        mbid_grupo: s(gr, "id"),
        tipo,
        recopilatorio: sec.iter().any(|t| t == "Compilation"),
        penalizaciones: sec
            .iter()
            .filter(|t| SECUNDARIOS_PENALIZADOS.contains(&t.as_str()))
            .map(|t| format!("tipo_secundario:{t}"))
            .collect(),
        secundarios: sec,
        anio: fecha(l).get(..4).and_then(|a| a.parse().ok()),
        mbid_grabacion: id,
        ..Candidato::default()
    })
}

/// `_escapar_lucene`.
pub fn escapar_lucene(texto: &str) -> String {
    let especiales = "+-&|!(){}[]^\"~*?:\\/";
    let mut s = String::with_capacity(texto.len());
    for c in texto.chars() {
        if especiales.contains(c) {
            s.push('\\');
        }
        s.push(c);
    }
    s
}

fn codificar(texto: &str) -> String {
    let mut s = String::with_capacity(texto.len() * 3);
    for b in texto.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                s.push(b as char)
            }
            _ => s.push_str(&format!("%{b:02X}")),
        }
    }
    s
}

/// Lo que se pide a MusicBrainz. En la aplicación es la red; en las pruebas,
/// respuestas guardadas. `None` es "no existe" (404).
pub trait Fuente: Send + Sync {
    fn pedir(&self, ruta_y_consulta: &str) -> NsResult<Option<Value>>;
}

/// La red de verdad, con el ritmo que pide MusicBrainz y los reintentos de la V1.
pub struct EnLaRed<'a> {
    red: &'a Red,
    ultima: Mutex<Option<Instant>>,
}

impl<'a> EnLaRed<'a> {
    pub fn new(red: &'a Red) -> Self {
        Self {
            red,
            ultima: Mutex::new(None),
        }
    }

    fn esperar_turno(&self) {
        let mut u = self
            .ultima
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        if let Some(t) = *u {
            if let Some(falta) = ENTRE_PETICIONES.checked_sub(t.elapsed()) {
                std::thread::sleep(falta);
            }
        }
        *u = Some(Instant::now());
    }
}

impl Fuente for EnLaRed<'_> {
    fn pedir(&self, ruta_y_consulta: &str) -> NsResult<Option<Value>> {
        let url = format!("https://musicbrainz.org/ws/2/{ruta_y_consulta}");
        let mut espera = ESPERA_INICIAL;
        for intento in 0..=REINTENTOS {
            self.esperar_turno();
            let r = self.red.obtener_con_estado(
                Servicio::MusicBrainz,
                &url,
                &[("Accept", "application/json")],
            );
            // `_clasificar_error_mb`: 404 no existe; 429, 5xx y la red se reintentan.
            let reintentar = match r {
                Ok((200..=299, cuerpo)) => {
                    return serde_json::from_slice(&cuerpo)
                        .map(Some)
                        .map_err(|_| NsError::NetworkFailure)
                }
                Ok((404, _)) => return Ok(None),
                Ok((429 | 500..=599, _)) | Err(NsError::NetworkFailure) => true,
                Ok(_) => return Err(NsError::NetworkFailure),
                Err(e) => return Err(e),
            };
            if reintentar && intento < REINTENTOS {
                std::thread::sleep(espera);
                espera *= 2;
            }
        }
        Err(NsError::NetworkFailure)
    }
}

/// El cliente, con la caché de la sesión de importación: dos pistas del mismo
/// álbum no preguntan dos veces lo mismo.
pub struct Cliente<F: Fuente> {
    fuente: F,
    cache: Mutex<HashMap<String, Option<Value>>>,
}

impl<F: Fuente> Cliente<F> {
    pub fn new(fuente: F) -> Self {
        Self {
            fuente,
            cache: Mutex::new(HashMap::new()),
        }
    }

    fn pedir(&self, ruta: &str) -> NsResult<Option<Value>> {
        if let Some(v) = self.cache.lock().ok().and_then(|c| c.get(ruta).cloned()) {
            return Ok(v);
        }
        let v = self.fuente.pedir(ruta)?;
        if let Ok(mut c) = self.cache.lock() {
            c.insert(ruta.to_owned(), v.clone());
        }
        Ok(v)
    }

    fn por_isrc(&self, isrc: &str) -> NsResult<Vec<Candidato>> {
        let Some(v) = self.pedir(&format!(
            "isrc/{}?fmt=json&inc=artists+releases+isrcs+release-groups+media",
            codificar(isrc)
        ))?
        else {
            return Ok(Vec::new());
        };
        Ok(v.get("recordings")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .take(LIMITE_BUSQUEDA)
            .filter_map(candidato_de)
            .map(|mut c| {
                c.isrc = Some(isrc.to_owned());
                c
            })
            .collect())
    }

    fn por_grabacion(&self, id: &str) -> NsResult<Vec<Candidato>> {
        let Some(v) = self.pedir(&format!(
            "recording/{}?fmt=json&inc=artists+releases+isrcs+release-groups+media",
            codificar(id)
        ))?
        else {
            return Ok(Vec::new());
        };
        Ok(candidato_de(&v)
            .map(|mut c| {
                c.de_acoustid = true;
                vec![c]
            })
            .unwrap_or_default())
    }

    fn buscar_texto(
        &self,
        artista: &str,
        titulo: &str,
        hechas: &mut HashSet<(String, String)>,
    ) -> NsResult<Vec<Candidato>> {
        if !hechas.insert((para_comparacion(artista), para_comparacion(titulo))) {
            return Ok(Vec::new());
        }
        let mut partes = Vec::new();
        if !artista.is_empty() {
            partes.push(format!("artist:\"{}\"", escapar_lucene(artista)));
        }
        if !titulo.is_empty() {
            partes.push(format!("recording:\"{}\"", escapar_lucene(titulo)));
        }
        if partes.is_empty() {
            return Ok(Vec::new());
        }
        let Some(v) = self.pedir(&format!(
            "recording?fmt=json&limit={LIMITE_BUSQUEDA}&query={}",
            codificar(&partes.join(" AND "))
        ))?
        else {
            return Ok(Vec::new());
        };
        Ok(v.get("recordings")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .take(LIMITE_BUSQUEDA)
            .filter_map(candidato_de)
            .collect())
    }

    /// `_buscar_multiestrategia`: ISRC, grabaciones de AcoustID y cuatro búsquedas
    /// de texto cada vez más laxas, parando cuando hay bastantes.
    ///
    /// # Errors
    ///
    /// Los de la red; un fallo en una estrategia corta la búsqueda, porque las
    /// siguientes fallarían igual.
    pub fn candidatos(&self, b: &Busqueda, de_acoustid: &[String]) -> NsResult<Vec<Candidato>> {
        if b.artista.is_empty() && b.titulo.is_empty() && b.isrc.is_none() {
            return Ok(Vec::new());
        }
        let mut pool: Vec<Candidato> = Vec::new();
        let unir = |pool: &mut Vec<Candidato>, nuevos: Vec<Candidato>, acoustid: bool| {
            for mut c in nuevos {
                if c.mbid_grabacion.is_empty() {
                    continue;
                }
                c.de_acoustid |= acoustid;
                match pool
                    .iter_mut()
                    .find(|e| e.mbid_grabacion == c.mbid_grabacion)
                {
                    None => pool.push(c),
                    Some(e) if c.puntaje > e.puntaje => {
                        c.de_acoustid |= e.de_acoustid;
                        *e = c;
                    }
                    Some(_) => {}
                }
            }
        };
        if let Some(isrc) = &b.isrc {
            unir(&mut pool, self.por_isrc(isrc)?, false);
        }
        if !de_acoustid.is_empty() && pool.len() < CANDIDATOS_SUFICIENTES {
            for id in de_acoustid.iter().take(3) {
                unir(&mut pool, self.por_grabacion(id)?, true);
            }
        }
        if pool.len() >= CANDIDATOS_SUFICIENTES {
            pool.truncate(MAX_CANDIDATOS);
            return Ok(pool);
        }
        let mut hechas = HashSet::new();
        let (artista, titulo) = (b.artista.as_str(), b.titulo.as_str());
        let titulo_limpio = limpiar_version_titulo(titulo);
        let artista_sin_feat = if b.featuring.is_some() {
            separar_artista_principal(artista).0
        } else {
            artista.to_owned()
        };
        let variante = detectar_tipo_variante(titulo);
        let base = parsear_variante_titulo(if titulo_limpio.is_empty() {
            titulo
        } else {
            &titulo_limpio
        })
        .0;
        let limpio_o_titulo = if titulo_limpio.is_empty() {
            titulo
        } else {
            &titulo_limpio
        };

        if !artista.is_empty() && !titulo.is_empty() {
            unir(
                &mut pool,
                self.buscar_texto(artista, titulo, &mut hechas)?,
                false,
            );
        }
        if !titulo_limpio.is_empty()
            && titulo_limpio != titulo
            && pool.len() < MIN_RESULTADOS_POR_ESTRATEGIA
        {
            unir(
                &mut pool,
                self.buscar_texto(artista, &titulo_limpio, &mut hechas)?,
                false,
            );
        }
        if b.featuring.is_some()
            && artista_sin_feat != artista
            && pool.len() < MIN_RESULTADOS_POR_ESTRATEGIA
        {
            unir(
                &mut pool,
                self.buscar_texto(&artista_sin_feat, limpio_o_titulo, &mut hechas)?,
                false,
            );
        }
        if variante.is_some()
            && !base.is_empty()
            && base != titulo_limpio
            && pool.len() < MIN_RESULTADOS_POR_ESTRATEGIA
        {
            let a = if artista_sin_feat.is_empty() {
                artista
            } else {
                &artista_sin_feat
            };
            unir(&mut pool, self.buscar_texto(a, &base, &mut hechas)?, false);
        }
        if !titulo.is_empty() && pool.is_empty() {
            unir(
                &mut pool,
                self.buscar_texto("", limpio_o_titulo, &mut hechas)?,
                false,
            );
        }
        // Las puntuaciones las pone después el emparejador; aquí todas valen 0 y el
        // orden es el de llegada, como en la V1 antes de puntuar.
        pool.truncate(MAX_CANDIDATOS);
        Ok(pool)
    }

    /// El lanzamiento entero, con sus pistas (`obtener_detalle_release`).
    ///
    /// # Errors
    ///
    /// Los de la red.
    pub fn lanzamiento(&self, id: &str) -> NsResult<Option<Value>> {
        if id.is_empty() {
            return Ok(None);
        }
        self.pedir(&format!(
            "release/{}?fmt=json&inc=artists+recordings+release-groups+media",
            codificar(id)
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn grabacion(id: &str, lanzamientos: Value) -> Value {
        json!({
            "id": id, "title": "Clavado en un bar", "length": 300_500,
            "isrcs": ["MXF019700001"],
            "artist-credit": [{"name": "Maná", "artist": {"name": "Maná"}}],
            "releases": lanzamientos
        })
    }

    #[test]
    fn el_mejor_lanzamiento_es_el_album_oficial_mas_antiguo() {
        let g = grabacion(
            "r1",
            json!([
                {"id": "comp", "title": "Grandes éxitos", "status": "Official", "date": "2005",
                 "release-group": {"id": "g1", "primary-type": "Album", "secondary-types": ["Compilation"]}},
                {"id": "nuevo", "title": "Sueños líquidos (Remaster)", "status": "Official", "date": "2017",
                 "release-group": {"id": "g2", "primary-type": "Album"}},
                {"id": "orig", "title": "Sueños líquidos", "status": "Official", "date": "1997-10-21",
                 "release-group": {"id": "g2", "primary-type": "album"},
                 "media": [{"track-count": 12, "track": [{"number": "3", "title": "Clavado en un bar"}]}]},
                {"id": "bootleg", "title": "En vivo", "status": "Bootleg", "date": "1990",
                 "release-group": {"id": "g3", "primary-type": "Album"}}
            ]),
        );
        let c = candidato_de(&g).unwrap();
        assert_eq!(c.mbid_lanzamiento, "orig");
        assert_eq!(
            (c.album.as_str(), c.anio, c.tipo.as_str()),
            ("Sueños líquidos", Some(1997), "Album")
        );
        assert_eq!((c.numero, c.total), (Some(3), Some(12)));
        assert_eq!(c.duracion_seg, Some(300.5));
        assert_eq!(c.isrc.as_deref(), Some("MXF019700001"));
        assert!(c.oficial && !c.recopilatorio);
    }

    #[test]
    fn sin_lanzamientos_no_hay_candidato() {
        assert!(candidato_de(&grabacion("r", json!([]))).is_none());
    }

    #[test]
    fn el_recopilatorio_queda_marcado_y_penalizado() {
        let c = candidato_de(&grabacion(
            "r",
            json!([{"id": "c", "title": "Hits", "status": "Official",
                    "release-group": {"primary-type": "Album", "secondary-types": ["Compilation", "Live"]}}]),
        ))
        .unwrap();
        assert!(c.recopilatorio);
        assert_eq!(
            c.penalizaciones,
            ["tipo_secundario:Compilation", "tipo_secundario:Live"]
        );
    }

    #[test]
    fn lucene_se_escapa_como_en_la_v1() {
        assert_eq!(
            escapar_lucene("AC/DC: Back (In) Black!"),
            "AC\\/DC\\: Back \\(In\\) Black\\!"
        );
    }

    /// Una fuente que responde lo guardado y apunta lo que le piden.
    struct Guardada {
        respuestas: Vec<(&'static str, Value)>,
        pedidas: Mutex<Vec<String>>,
    }

    impl Fuente for Guardada {
        fn pedir(&self, r: &str) -> NsResult<Option<Value>> {
            self.pedidas.lock().unwrap().push(r.to_owned());
            Ok(self
                .respuestas
                .iter()
                .find(|(prefijo, _)| r.starts_with(prefijo))
                .map(|(_, v)| v.clone()))
        }
    }

    fn lanz() -> Value {
        json!([{"id": "l", "title": "A", "status": "Official", "release-group": {"primary-type": "Album"}}])
    }

    #[test]
    fn con_isrc_y_acoustid_suficientes_no_se_busca_por_texto() {
        let fuente = Guardada {
            respuestas: vec![
                (
                    "isrc/",
                    json!({"recordings": [grabacion("a", lanz()), grabacion("b", lanz())]}),
                ),
                ("recording/c", grabacion("c", lanz())),
            ],
            pedidas: Mutex::new(Vec::new()),
        };
        let cliente = Cliente::new(fuente);
        let b = Busqueda {
            artista: "Maná".into(),
            titulo: "Clavado en un bar".into(),
            isrc: Some("MXF019700001".into()),
            ..Busqueda::default()
        };
        let c = cliente.candidatos(&b, &["c".into(), "a".into()]).unwrap();
        assert_eq!(
            c.iter()
                .map(|x| x.mbid_grabacion.as_str())
                .collect::<Vec<_>>(),
            ["a", "b", "c"]
        );
        assert!(c[2].de_acoustid, "la que llegó por AcoustID queda marcada");
        // La que ya estaba por el ISRC no se sustituye (misma puntuación), y la V1
        // perdía ahí la marca: se conserva ese comportamiento hasta medir la paridad.
        assert!(!c[0].de_acoustid);
        let pedidas = cliente.fuente.pedidas.lock().unwrap().clone();
        assert!(
            pedidas.iter().all(|p| !p.starts_with("recording?")),
            "{pedidas:?}"
        );
    }

    #[test]
    fn sin_resultados_se_relaja_hasta_buscar_solo_el_titulo() {
        let fuente = Guardada {
            respuestas: vec![],
            pedidas: Mutex::new(Vec::new()),
        };
        let cliente = Cliente::new(fuente);
        let b = Busqueda {
            artista: "Drake feat. Future".into(),
            titulo: "Song (Remastered) (Remix)".into(),
            featuring: Some("Future".into()),
            ..Busqueda::default()
        };
        assert!(cliente.candidatos(&b, &[]).unwrap().is_empty());
        let pedidas = cliente.fuente.pedidas.lock().unwrap().clone();
        let consultas: Vec<String> = pedidas
            .iter()
            .map(|p| p.split("query=").nth(1).unwrap_or_default().to_owned())
            .collect();
        assert_eq!(consultas.len(), 5, "{consultas:?}");
        assert!(
            consultas[4].starts_with("recording%3A"),
            "la última sin artista: {}",
            consultas[4]
        );
    }
}
