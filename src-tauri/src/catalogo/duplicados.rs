//! Duplicados (F4.1.8): `core/dedupe.py` de la V1, con sus tres ejes.
//!
//! 1. **Exacto**: el mismo archivo, por su huella de contenido.
//! 2. **Identidad**: la misma grabación de MusicBrainz o el mismo ISRC. Si el nuevo
//!    es claramente mejor (calidad 0,08 por encima), es un duplicado *mejorable*.
//! 3. **Observable**: mismo título, artista y álbum normalizados, misma portada y
//!    duración a 3 s o menos. Si falta cualquiera de los cuatro, no hay clave: la
//!    ausencia de datos nunca produce un falso positivo.
//!
//! Los índices nacen con lo que ya hay en la biblioteca, para que repetir una
//! importación cancelada a medias no duplique nada.

use std::collections::HashMap;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;

use sha2::{Digest, Sha256};

use super::texto::normalizar_para_comparar;
use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};

/// `DUPLICATE_BETTER_MIN_DELTA` y `DUPLICATE_OBSERVABLE_TOLERANCIA_SEG`.
const MEJORA_MINIMA: f64 = 0.08;
const TOLERANCIA_SEG: f64 = 3.0;
const INICIO: u64 = 512 * 1024;
const FINAL: u64 = 512 * 1024;

/// La huella de contenido de un archivo (`_calcular_hash_combinado` de la V1): el
/// SHA-256 de los primeros 512 KB y los últimos 512 KB. Es la `x-nb-sound-hash`
/// que el teléfono comprueba al descargar, con esta misma regla
/// (`download_repository.dart`), y la que trajo el importador; hasta 1 MB coincide
/// con el SHA-256 del archivo entero.
///
/// # Errors
///
/// [`NsError::FileNotFound`] si no se puede leer.
pub fn huella_de_archivo(ruta: &Path) -> NsResult<String> {
    let mut f = std::fs::File::open(ruta).map_err(|_| NsError::FileNotFound)?;
    let tamano = f.metadata().map_err(|_| NsError::FileNotFound)?.len();
    let mut h = Sha256::new();
    let mut buf = vec![0u8; 8192];
    let mut leidos = 0u64;
    while leidos < INICIO {
        let n = f.read(&mut buf).map_err(|_| NsError::FileNotFound)?;
        if n == 0 {
            break;
        }
        h.update(&buf[..n]);
        leidos += n as u64;
    }
    let desde = tamano.saturating_sub(FINAL);
    if desde > leidos {
        f.seek(SeekFrom::Start(desde))
            .map_err(|_| NsError::FileNotFound)?;
        loop {
            let n = f.read(&mut buf).map_err(|_| NsError::FileNotFound)?;
            if n == 0 {
                break;
            }
            h.update(&buf[..n]);
        }
    }
    Ok(h.finalize().iter().map(|b| format!("{b:02x}")).collect())
}

/// Qué duplicado es y de qué pista (su id en la biblioteca, si ya estaba).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Duplicado {
    Exacto(Referencia),
    Identidad(Referencia),
    Mejorable(Referencia),
    Observable(Referencia),
}

/// Contra qué se detectó: una pista de la biblioteca o un archivo de esta misma
/// importación.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Referencia {
    Pista(i64),
    Archivo(String),
}

type Clave = (String, String, String, String);

/// Lo que se ve de una pista: el eje observable.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct Visible<'a> {
    pub titulo: &'a str,
    pub artista: &'a str,
    pub album: &'a str,
    pub duracion: Option<f64>,
    /// El SHA-256 del contenido de la portada.
    pub portada: Option<&'a str>,
}

fn clave_observable(
    titulo: &str,
    artista: &str,
    album: &str,
    portada: Option<&str>,
) -> Option<Clave> {
    let (t, a, al) = (
        normalizar_para_comparar(titulo),
        normalizar_para_comparar(artista),
        normalizar_para_comparar(album),
    );
    let p = portada.filter(|p| !p.is_empty())?;
    (!t.is_empty() && !a.is_empty() && !al.is_empty()).then(|| (t, a, al, p.to_owned()))
}

/// Lo que mide la calidad de una aceptación (`_score_calidad`).
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct Calidad {
    pub puntaje: f64,
    pub con_grabacion: bool,
    pub con_lanzamiento: bool,
    pub con_isrc_candidato: bool,
    pub con_numero: bool,
    pub bitrate_kbps: Option<u32>,
    pub etiquetas_con_titulo_y_artista: bool,
    pub con_acoustid: bool,
    pub con_isrc_archivo: bool,
}

impl Calidad {
    pub fn valor(&self) -> f64 {
        let mut s = 0.0;
        if self.puntaje != 0.0 {
            s += f64::min(0.5, self.puntaje * 0.5);
        }
        for (si, v) in [
            (self.con_grabacion, 0.1),
            (self.con_lanzamiento, 0.08),
            (self.con_isrc_candidato, 0.06),
            (self.con_numero, 0.04),
            (self.bitrate_kbps.is_some_and(|b| b >= 256), 0.1),
            (self.etiquetas_con_titulo_y_artista, 0.05),
            (self.con_acoustid, 0.07),
            (self.con_isrc_archivo, 0.05),
        ] {
            if si {
                s += v;
            }
        }
        super::texto::redondear(f64::min(s, 1.0), 4)
    }
}

/// Los tres índices.
#[derive(Debug, Default)]
pub struct Gestor {
    por_huella: HashMap<String, Referencia>,
    por_identidad: HashMap<String, (Referencia, f64)>,
    por_observable: HashMap<Clave, Vec<(Referencia, f64)>>,
}

impl Gestor {
    /// Con lo que ya está en la biblioteca (`_precargar_desde_biblioteca`). La
    /// calidad de lo que ya estaba vale 0,5, como en la V1.
    ///
    /// # Errors
    ///
    /// [`NsError::StorageFailure`] si la consulta falla.
    pub fn desde_biblioteca(db: &BaseDeDatos) -> NsResult<Self> {
        let mut g = Self::default();
        let conn = db.conexion()?;
        let mut s = conn
            .prepare(
                "SELECT p.id, p.sha256, p.mbid_grabacion, p.isrc, p.titulo, p.artista_nombre,
                        p.album_titulo, p.duracion_seg, po.sha256
                 FROM pistas p LEFT JOIN albumes a ON a.id = p.album_id
                 LEFT JOIN portadas po ON po.id = a.portada_id
                 WHERE p.estado = 'biblioteca'",
            )
            .map_err(|_| NsError::StorageFailure)?;
        let filas = s
            .query_map([], |f| {
                Ok((
                    f.get::<_, i64>(0)?,
                    f.get::<_, Option<String>>(1)?,
                    f.get::<_, Option<String>>(2)?,
                    f.get::<_, Option<String>>(3)?,
                    f.get::<_, String>(4)?,
                    f.get::<_, String>(5)?,
                    f.get::<_, String>(6)?,
                    f.get::<_, Option<f64>>(7)?,
                    f.get::<_, Option<String>>(8)?,
                ))
            })
            .map_err(|_| NsError::StorageFailure)?;
        for fila in filas {
            let (id, huella, mbid, isrc, titulo, artista, album, duracion, portada) =
                fila.map_err(|_| NsError::StorageFailure)?;
            let r = Referencia::Pista(id);
            if let Some(h) = huella.filter(|h| !h.is_empty()) {
                g.por_huella.entry(h).or_insert_with(|| r.clone());
            }
            for clave in [
                mbid.map(|m| format!("rid:{m}")),
                isrc.map(|i| format!("isrc:{i}")),
            ]
            .into_iter()
            .flatten()
            .filter(|c| !c.ends_with(':'))
            {
                g.por_identidad
                    .entry(clave)
                    .or_insert_with(|| (r.clone(), 0.5));
            }
            g.indexar_observable(
                r,
                Visible {
                    titulo: &titulo,
                    artista: &artista,
                    album: &album,
                    duracion,
                    portada: portada.as_deref(),
                },
            );
        }
        Ok(g)
    }

    fn indexar_observable(&mut self, r: Referencia, v: Visible<'_>) {
        if let (Some(c), Some(d)) = (
            clave_observable(v.titulo, v.artista, v.album, v.portada),
            v.duracion,
        ) {
            self.por_observable.entry(c).or_default().push((r, d));
        }
    }

    /// Eje 1 (`registrar_hash`): si la huella ya estaba, es exacto; si no, se apunta.
    pub fn registrar_huella(&mut self, huella: &str, archivo: &str) -> Option<Duplicado> {
        if huella.is_empty() {
            return None;
        }
        if let Some(r) = self.por_huella.get(huella) {
            return Some(Duplicado::Exacto(r.clone()));
        }
        self.por_huella
            .insert(huella.to_owned(), Referencia::Archivo(archivo.to_owned()));
        None
    }

    fn claves(mbid: Option<&str>, isrc: Option<&str>) -> Vec<String> {
        let mut c = Vec::new();
        if let Some(m) = mbid.filter(|m| !m.is_empty()) {
            c.push(format!("rid:{m}"));
        }
        if let Some(i) = isrc.filter(|i| !i.is_empty()) {
            c.push(format!("isrc:{i}"));
        }
        c
    }

    /// Eje 2, solo consulta (`detectar_duplicado_identidad`).
    pub fn duplicado_de_identidad(
        &self,
        mbid: Option<&str>,
        isrc: Option<&str>,
        calidad: f64,
    ) -> Option<Duplicado> {
        for clave in Self::claves(mbid, isrc) {
            if let Some((r, existente)) = self.por_identidad.get(&clave) {
                return Some(if calidad - existente >= MEJORA_MINIMA {
                    Duplicado::Mejorable(r.clone())
                } else {
                    Duplicado::Identidad(r.clone())
                });
            }
        }
        None
    }

    /// Eje 2 (`registrar_identidad_aceptada`): si no choca, se apunta.
    pub fn registrar_identidad(
        &mut self,
        mbid: Option<&str>,
        isrc: Option<&str>,
        calidad: f64,
        archivo: &str,
    ) -> Option<Duplicado> {
        if let Some(d) = self.duplicado_de_identidad(mbid, isrc, calidad) {
            return Some(d);
        }
        for clave in Self::claves(mbid, isrc) {
            self.por_identidad
                .insert(clave, (Referencia::Archivo(archivo.to_owned()), calidad));
        }
        None
    }

    /// Eje 3, solo consulta (`detectar_duplicado_observable`).
    pub fn duplicado_observable(&self, v: Visible<'_>) -> Option<Duplicado> {
        let c = clave_observable(v.titulo, v.artista, v.album, v.portada)?;
        let d = v.duracion?;
        self.por_observable
            .get(&c)?
            .iter()
            .find(|(_, e)| (e - d).abs() <= TOLERANCIA_SEG)
            .map(|(r, _)| Duplicado::Observable(r.clone()))
    }

    /// Eje 3 (`registrar_observable_aceptado`): una pista aceptada en esta
    /// importación, para las siguientes.
    pub fn registrar_observable(&mut self, archivo: &str, v: Visible<'_>) {
        self.indexar_observable(Referencia::Archivo(archivo.to_owned()), v);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn la_huella_es_la_de_la_v1_y_la_que_comprueba_el_telefono() {
        let dir = std::env::temp_dir().join(format!("ns-duplicados-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let pequeno = dir.join("p.bin");
        std::fs::write(&pequeno, b"AUDIO-100-".repeat(64)).unwrap();
        // El de la respuesta dorada del contrato móvil.
        assert_eq!(
            huella_de_archivo(&pequeno).unwrap(),
            "d934c9f9dfcaf225befcce03108063788cacb9e4fa810ad3dc65fa26d6ea4ec3"
        );
        let grande = dir.join("g.bin");
        let datos: Vec<u8> = (0..3_000_000u32).map(|i| (i % 251) as u8).collect();
        std::fs::write(&grande, &datos).unwrap();
        let mut h = Sha256::new();
        h.update(&datos[..524_288]);
        h.update(&datos[datos.len() - 524_288..]);
        let esperado: String = h.finalize().iter().map(|b| format!("{b:02x}")).collect();
        assert_eq!(huella_de_archivo(&grande).unwrap(), esperado);
    }

    fn base() -> BaseDeDatos {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO portadas (id, sha256, ruta, ancho, alto, bytes, mime, origen)
                     VALUES (1, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'p.jpg', 1, 1, 1, 'image/jpeg', 'x');
                 INSERT INTO artistas (id, nombre, clave) VALUES (1, 'Maná', 'mana');
                 INSERT INTO albumes (id, artista_id, titulo, clave, portada_id) VALUES (10, 1, 'Sueños líquidos', 's', 1);
                 INSERT INTO pistas (id, album_id, titulo, artista_nombre, album_titulo, ruta, sha256, mbid_grabacion, isrc, duracion_seg)
                     VALUES (1, 10, 'Clavado en un bar', 'Maná', 'Sueños líquidos', 'a',
                             'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 'rec-1', 'MXF019700001', 300);",
            )
            .unwrap();
        db
    }

    #[test]
    fn lo_que_ya_esta_en_la_biblioteca_es_duplicado_por_los_tres_ejes() {
        let mut g = Gestor::desde_biblioteca(&base()).unwrap();
        assert_eq!(
            g.registrar_huella(&"b".repeat(64), "x"),
            Some(Duplicado::Exacto(Referencia::Pista(1)))
        );
        assert_eq!(g.registrar_huella(&"c".repeat(64), "x"), None);
        assert_eq!(
            g.registrar_huella(&"c".repeat(64), "y"),
            Some(Duplicado::Exacto(Referencia::Archivo("x".into())))
        );
        assert_eq!(
            g.duplicado_de_identidad(Some("rec-1"), None, 0.55),
            Some(Duplicado::Identidad(Referencia::Pista(1)))
        );
        assert_eq!(
            g.duplicado_de_identidad(None, Some("MXF019700001"), 0.6),
            Some(Duplicado::Mejorable(Referencia::Pista(1)))
        );
        let portada = "a".repeat(64);
        assert_eq!(
            g.duplicado_observable(Visible {
                titulo: "CLAVADO EN UN BAR",
                artista: "Mana",
                album: "Suenos liquidos",
                duracion: Some(302.5),
                portada: Some(&portada)
            }),
            Some(Duplicado::Observable(Referencia::Pista(1)))
        );
        assert_eq!(
            g.duplicado_observable(Visible {
                titulo: "Clavado en un bar",
                artista: "Maná",
                album: "Sueños líquidos",
                duracion: Some(310.0),
                portada: Some(&portada)
            }),
            None
        );
        assert_eq!(
            g.duplicado_observable(Visible {
                titulo: "Clavado en un bar",
                artista: "Maná",
                album: "",
                duracion: Some(300.0),
                portada: Some(&portada)
            }),
            None,
            "sin álbum no hay clave"
        );
    }

    #[test]
    fn la_calidad_suma_como_en_la_v1() {
        let c = Calidad {
            puntaje: 0.9,
            con_grabacion: true,
            con_lanzamiento: true,
            bitrate_kbps: Some(320),
            ..Calidad::default()
        };
        assert_eq!(c.valor(), 0.73);
        assert_eq!(Calidad::default().valor(), 0.0);
    }
}
