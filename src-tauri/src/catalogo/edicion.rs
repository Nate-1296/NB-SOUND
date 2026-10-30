//! Editar los datos de una pista o de un álbum (F4.2.5), y lo que comparte con
//! "Completar datos": rehacer una pista en su misma fila.
//!
//! **Los `id` no cambian.** NB Sound Mobile guarda los de pistas y álbumes
//! (ADR-005), y las playlists, el DJ y el historial apuntan a ellos. Por eso
//! renombrar un álbum actualiza su fila, con su portada, en vez de crear otro; solo
//! si ya existe un álbum con ese nombre del mismo artista se juntan los dos, porque
//! dos filas iguales serían el mismo álbum partido.
//!
//! El archivo recibe las etiquetas nuevas si se puede, y no se mueve. Si no admite
//! escritura (solo lectura), los datos quedan en la biblioteca igualmente: es lo
//! que ve la aplicación y lo que recibe el teléfono.

use std::path::{Path, PathBuf};

use rusqlite::{params, OptionalExtension};
use serde::{Deserialize, Serialize};
use ts_rs::TS;

use super::canalizacion::{album_id, artista_id, bd, Alta, Entorno};
use super::correcciones;
use super::duplicados::huella_de_archivo;
use super::etiquetas::{self, Escritura};
use super::texto::construir_slug;
use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};

/// Una pista tal como está en la base, con lo necesario para rehacerla.
pub(super) struct Fila {
    pub ruta: String,
    pub titulo: String,
    pub artista: String,
    pub album: String,
    pub artista_id: Option<i64>,
    pub album_id: Option<i64>,
    pub numero: Option<u32>,
    pub anio: Option<i32>,
    pub genero: Option<String>,
    pub isrc: Option<String>,
    pub mbid_grabacion: Option<String>,
    pub mbid_lanzamiento: Option<String>,
    pub tipo: Option<String>,
    pub verificada: bool,
}

/// # Errors
///
/// [`NsError::InvalidInput`] si la pista no existe; [`NsError::StorageFailure`]
/// si la consulta falla.
pub(super) fn leer_fila(db: &BaseDeDatos, pista: i64) -> NsResult<Fila> {
    db.conexion()?
        .query_row(
            "SELECT ruta, titulo, artista_nombre, album_titulo, artista_id, album_id, numero, anio,
                    genero, isrc, mbid_grabacion, mbid_lanzamiento, tipo_lanzamiento, verificada
             FROM pistas WHERE id = ?1",
            [pista],
            |f| {
                Ok(Fila {
                    ruta: f.get(0)?,
                    titulo: f.get(1)?,
                    artista: f.get(2)?,
                    album: f.get(3)?,
                    artista_id: f.get(4)?,
                    album_id: f.get(5)?,
                    numero: f.get(6)?,
                    anio: f.get(7)?,
                    genero: f.get(8)?,
                    isrc: f.get(9)?,
                    mbid_grabacion: f.get(10)?,
                    mbid_lanzamiento: f.get(11)?,
                    tipo: f.get(12)?,
                    verificada: f.get(13)?,
                })
            },
        )
        .optional()
        .map_err(|_| NsError::StorageFailure)?
        .ok_or(NsError::InvalidInput)
}

pub(super) fn alta_de_fila(f: &Fila) -> Alta {
    Alta {
        titulo: f.titulo.clone(),
        artista: f.artista.clone(),
        album: f.album.clone(),
        tipo: f.tipo.clone().unwrap_or_default(),
        numero: f.numero,
        anio: f.anio,
        genero: f.genero.clone(),
        isrc: f.isrc.clone(),
        mbid_grabacion: f.mbid_grabacion.clone(),
        mbid_lanzamiento: f.mbid_lanzamiento.clone(),
        verificada: f.verificada,
        ..Alta::default()
    }
}

/// El archivo de una pista: su ruta es relativa a la música salvo si quedó fuera.
pub(super) fn archivo_de(e: &Entorno<'_>, ruta: &str) -> PathBuf {
    if Path::new(ruta).is_absolute() {
        PathBuf::from(ruta)
    } else {
        e.musica.join(ruta)
    }
}

/// Escribe los datos en el archivo. Devuelve si pudo: si no, la base manda.
pub(super) fn escribir_etiquetas(archivo: &Path, a: &Alta) -> bool {
    let hecho = etiquetas::escribir(
        archivo,
        &Escritura {
            titulo: Some(a.titulo.clone()),
            artista: Some(a.artista.clone()),
            album: Some(a.album.clone()).filter(|x| !x.is_empty()),
            numero: a.numero,
            total: a.total,
            anio: a.anio,
            isrc: a.isrc.clone(),
            mbid_grabacion: a.mbid_grabacion.clone(),
            mbid_lanzamiento: a.mbid_lanzamiento.clone(),
            mbid_grupo: a.mbid_grupo.clone(),
            tipo_lanzamiento: Some(a.tipo.clone()).filter(|x| !x.is_empty()),
        },
    )
    .is_ok();
    if !hecho {
        tracing::warn!("no se pudieron escribir las etiquetas; quedan solo en la biblioteca");
    }
    hecho
}

/// Borra el álbum y el artista que se hayan quedado sin nada.
fn limpiar_vacios(
    tx: &rusqlite::Transaction<'_>,
    album: Option<i64>,
    artista: Option<i64>,
) -> NsResult<()> {
    if let Some(a) = album {
        bd(tx.execute(
            "DELETE FROM albumes WHERE id = ?1
             AND NOT EXISTS (SELECT 1 FROM pistas WHERE album_id = ?1)",
            [a],
        ))?;
    }
    if let Some(a) = artista {
        bd(tx.execute(
            "DELETE FROM artistas WHERE id = ?1
             AND NOT EXISTS (SELECT 1 FROM pistas WHERE artista_id = ?1)
             AND NOT EXISTS (SELECT 1 FROM albumes WHERE artista_id = ?1)",
            [a],
        ))?;
    }
    Ok(())
}

/// Pone los datos de `a` en la misma fila (también `verificada`, la de `a`) y
/// borra el álbum y el artista que se queden vacíos. Devuelve los ids nuevos de
/// artista y álbum.
pub(super) fn reasignar(
    e: &Entorno<'_>,
    pista: i64,
    anterior: &Fila,
    a: &Alta,
    archivo: &Path,
) -> NsResult<(i64, Option<i64>)> {
    // Las etiquetas nuevas cambian el principio del archivo, y con él la huella
    // que comprueba el teléfono: se vuelve a medir después de escribir.
    let sha256 = huella_de_archivo(archivo)?;
    let tamano = std::fs::metadata(archivo).map(|m| m.len()).unwrap_or(0);
    let carpeta = Path::new(&anterior.ruta)
        .parent()
        .map(|p| p.to_string_lossy().into_owned())
        .filter(|p| !p.is_empty());
    let mut conn = e.db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    let artista = artista_id(&tx, &a.artista)?;
    let album = album_id(&tx, artista, a, carpeta.as_deref())?;
    let artista_nombre: String = bd(tx.query_row(
        "SELECT nombre FROM artistas WHERE id = ?1",
        [artista],
        |f| f.get(0),
    ))?;
    let album_titulo: String = match album {
        Some(id) => bd(
            tx.query_row("SELECT titulo FROM albumes WHERE id = ?1", [id], |f| {
                f.get(0)
            }),
        )?,
        None => String::new(),
    };
    bd(tx.execute(
        "UPDATE pistas SET titulo = ?1, artista_id = ?2, artista_nombre = ?3, album_id = ?4,
             album_titulo = ?5, numero = ?6, anio = ?7, genero = ?8, isrc = ?9,
             mbid_grabacion = ?10, mbid_lanzamiento = ?11, tipo_lanzamiento = ?12,
             fuentes_etiquetado = ?13, sha256 = ?14, tamano = ?15, verificada = ?16,
             actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
         WHERE id = ?17",
        params![
            a.titulo.trim(),
            artista,
            artista_nombre,
            album,
            album_titulo,
            a.numero.filter(|n| *n > 0),
            a.anio.filter(|y| (1000..=9999).contains(y)),
            a.genero,
            a.isrc,
            a.mbid_grabacion,
            a.mbid_lanzamiento,
            Some(a.tipo.clone()).filter(|x| !x.is_empty()),
            serde_json::to_string(&a.fuentes).ok(),
            sha256,
            tamano as i64,
            a.verificada,
            pista,
        ],
    ))?;
    limpiar_vacios(
        &tx,
        anterior.album_id.filter(|v| Some(*v) != album),
        anterior.artista_id.filter(|v| *v != artista),
    )?;
    bd(tx.commit())?;
    Ok((artista, album))
}

// --- Editar -----------------------------------------------------------------------

/// Los datos de una pista que se pueden editar.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct DatosPista {
    pub titulo: String,
    pub artista: String,
    /// Vacío: la pista no es de ningún álbum.
    pub album: String,
    pub numero: Option<u32>,
    pub anio: Option<i32>,
    pub genero: Option<String>,
}

/// Los datos de un álbum que se pueden editar.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct DatosAlbum {
    pub titulo: String,
    pub artista: String,
    pub anio: Option<i32>,
}

/// Tope de un nombre: holgado para cualquier título real y corto para que un
/// valor absurdo no llegue a la base ni a las etiquetas.
const LARGO_MAXIMO: usize = 300;

fn texto(v: &str, vacio_vale: bool) -> NsResult<String> {
    let v = v.trim();
    if (!vacio_vale && v.is_empty()) || v.chars().count() > LARGO_MAXIMO {
        return Err(NsError::InvalidInput);
    }
    Ok(v.to_owned())
}

fn anio(v: Option<i32>) -> NsResult<Option<i32>> {
    match v {
        Some(a) if !(1000..=9999).contains(&a) => Err(NsError::InvalidInput),
        otro => Ok(otro),
    }
}

impl DatosPista {
    fn validados(&self) -> NsResult<Self> {
        if self.numero.is_some_and(|n| n == 0 || n > 999) {
            return Err(NsError::InvalidInput);
        }
        let genero = match self.genero.as_deref().map(str::trim) {
            None | Some("") => None,
            Some(g) if g.chars().count() <= 100 => Some(g.to_owned()),
            Some(_) => return Err(NsError::InvalidInput),
        };
        Ok(Self {
            titulo: texto(&self.titulo, false)?,
            artista: texto(&self.artista, false)?,
            album: texto(&self.album, true)?,
            numero: self.numero,
            anio: anio(self.anio)?,
            genero,
        })
    }
}

impl DatosAlbum {
    fn validados(&self) -> NsResult<Self> {
        Ok(Self {
            titulo: texto(&self.titulo, false)?,
            artista: texto(&self.artista, false)?,
            anio: anio(self.anio)?,
        })
    }
}

/// # Errors
///
/// Los de [`leer_fila`].
pub fn datos_pista(db: &BaseDeDatos, pista: i64) -> NsResult<DatosPista> {
    let f = leer_fila(db, pista)?;
    Ok(DatosPista {
        titulo: f.titulo,
        artista: f.artista,
        album: f.album,
        numero: f.numero,
        anio: f.anio,
        genero: f.genero,
    })
}

/// # Errors
///
/// [`NsError::InvalidInput`] si el álbum no existe.
pub fn datos_album(db: &BaseDeDatos, album: i64) -> NsResult<DatosAlbum> {
    db.conexion()?
        .query_row(
            "SELECT a.titulo, r.nombre, a.anio FROM albumes a
             JOIN artistas r ON r.id = a.artista_id WHERE a.id = ?1",
            [album],
            |f| {
                Ok(DatosAlbum {
                    titulo: f.get(0)?,
                    artista: f.get(1)?,
                    anio: f.get(2)?,
                })
            },
        )
        .optional()
        .map_err(|_| NsError::StorageFailure)?
        .ok_or(NsError::InvalidInput)
}

/// Cambia los datos de una pista. No cambia `verificada`: corregir a mano no
/// es haberla identificado.
///
/// # Errors
///
/// - [`NsError::InvalidInput`] si la pista no existe o un dato no vale.
/// - [`NsError::FileNotFound`] si su archivo ya no está.
/// - [`NsError::StorageFailure`] si la base falla.
pub fn editar_pista(e: &Entorno<'_>, pista: i64, datos: &DatosPista) -> NsResult<()> {
    let d = datos.validados()?;
    let fila = leer_fila(e.db, pista)?;
    let archivo = archivo_de(e, &fila.ruta);
    if !archivo.is_file() {
        return Err(NsError::FileNotFound);
    }
    let mut a = alta_de_fila(&fila);
    let cambia_album = d.album != fila.album || d.artista != fila.artista;
    a.titulo = d.titulo;
    a.artista = d.artista;
    a.album = d.album;
    a.numero = d.numero;
    a.anio = d.anio;
    a.genero = d.genero;
    if cambia_album {
        // El lanzamiento identificado ya no es el de la pista.
        a.mbid_lanzamiento = None;
        a.tipo = String::new();
    }
    a.fuentes = vec!["manual"];
    escribir_etiquetas(&archivo, &a);
    reasignar(e, pista, &fila, &a, &archivo)?;
    recordar_correcciones(e.db, &[pista])
}

/// Guarda como corrección lo que quedó en cada pista, para que importarla otra
/// vez respete lo editado.
fn recordar_correcciones(db: &BaseDeDatos, pistas: &[i64]) -> NsResult<()> {
    let mut filas = Vec::with_capacity(pistas.len());
    for id in pistas {
        let f = leer_fila(db, *id)?;
        let huella: Option<String> = db
            .conexion()?
            .query_row("SELECT sha256 FROM pistas WHERE id = ?1", [id], |f| {
                f.get(0)
            })
            .map_err(|_| NsError::StorageFailure)?;
        filas.push((huella, alta_de_fila(&f)));
    }
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    for (huella, a) in &filas {
        correcciones::recordar(&tx, huella.as_deref(), a)?;
    }
    bd(tx.commit())
}

/// Cambia los datos de un álbum y de todas sus pistas. Devuelve el id del álbum
/// resultante: el mismo, salvo si se juntó con otro que ya existía.
///
/// # Errors
///
/// - [`NsError::InvalidInput`] si el álbum no existe o un dato no vale.
/// - [`NsError::StorageFailure`] si la base falla.
pub fn editar_album(e: &Entorno<'_>, album: i64, datos: &DatosAlbum) -> NsResult<i64> {
    let d = datos.validados()?;
    datos_album(e.db, album)?;
    let pistas: Vec<(i64, String)> = {
        let conn = e.db.conexion()?;
        let mut s = conn
            .prepare("SELECT id, ruta FROM pistas WHERE album_id = ?1")
            .map_err(|_| NsError::StorageFailure)?;
        let filas = s
            .query_map([album], |f| Ok((f.get(0)?, f.get(1)?)))
            .map_err(|_| NsError::StorageFailure)?
            .collect::<rusqlite::Result<Vec<_>>>()
            .map_err(|_| NsError::StorageFailure)?;
        filas
    };
    // Primero las etiquetas, fuera de la transacción: escribir archivos es lento
    // y no puede tener la base bloqueada.
    let mut medidas = Vec::with_capacity(pistas.len());
    for (id, ruta) in &pistas {
        let fila = leer_fila(e.db, *id)?;
        let archivo = archivo_de(e, ruta);
        if archivo.is_file() {
            let mut a = alta_de_fila(&fila);
            a.artista.clone_from(&d.artista);
            a.album.clone_from(&d.titulo);
            a.anio = d.anio.or(a.anio);
            escribir_etiquetas(&archivo, &a);
        }
        let sha = huella_de_archivo(&archivo).ok();
        let tamano = std::fs::metadata(&archivo).map(|m| m.len() as i64).ok();
        medidas.push((*id, sha, tamano));
    }
    let mut conn = e.db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    let artista_viejo: i64 = bd(tx.query_row(
        "SELECT artista_id FROM albumes WHERE id = ?1",
        [album],
        |f| f.get(0),
    ))?;
    let artista = artista_id(&tx, &d.artista)?;
    let clave = construir_slug(&d.titulo);
    let otro: Option<i64> = bd(tx
        .query_row(
            "SELECT id FROM albumes WHERE artista_id = ?1 AND clave = ?2 AND id <> ?3",
            params![artista, clave, album],
            |f| f.get(0),
        )
        .optional())?;
    let destino = match otro {
        Some(otro) => {
            // Ya existe: las pistas pasan a él y este se borra al quedar vacío. Si el
            // otro no tenía portada, se queda con la de este.
            bd(tx.execute(
                "UPDATE albumes SET portada_id = coalesce(portada_id,
                     (SELECT portada_id FROM albumes WHERE id = ?2)), anio = coalesce(?3, anio)
                 WHERE id = ?1",
                params![otro, album, d.anio],
            ))?;
            bd(tx.execute(
                "UPDATE pistas SET album_id = ?1 WHERE album_id = ?2",
                [otro, album],
            ))?;
            otro
        }
        None => {
            bd(tx.execute(
                "UPDATE albumes SET titulo = ?1, clave = ?2, artista_id = ?3, anio = ?4 WHERE id = ?5",
                params![d.titulo, clave, artista, d.anio, album],
            ))?;
            album
        }
    };
    let (titulo, nombre): (String, String) = bd(tx.query_row(
        "SELECT a.titulo, r.nombre FROM albumes a JOIN artistas r ON r.id = a.artista_id
         WHERE a.id = ?1",
        [destino],
        |f| Ok((f.get(0)?, f.get(1)?)),
    ))?;
    for (id, sha, tamano) in medidas {
        bd(tx.execute(
            "UPDATE pistas SET album_titulo = ?1, artista_nombre = ?2, artista_id = ?3,
                 anio = coalesce(?4, anio), sha256 = coalesce(?5, sha256),
                 tamano = coalesce(?6, tamano),
                 actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
             WHERE id = ?7",
            params![titulo, nombre, artista, d.anio, sha, tamano, id],
        ))?;
    }
    limpiar_vacios(
        &tx,
        Some(album).filter(|a| *a != destino),
        Some(artista_viejo).filter(|a| *a != artista),
    )?;
    bd(tx.commit())?;
    let ids: Vec<i64> = pistas.iter().map(|(id, _)| *id).collect();
    recordar_correcciones(e.db, &ids)?;
    Ok(destino)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::net::{PoliticaDeRed, Red};
    use crate::paths::Rutas;

    struct Montaje {
        dir: PathBuf,
        db: BaseDeDatos,
        rutas: Rutas,
        red: Red,
    }

    impl Montaje {
        fn nuevo(nombre: &str) -> Self {
            let dir =
                std::env::temp_dir().join(format!("ns-edicion-{nombre}-{}", std::process::id()));
            let _ = std::fs::remove_dir_all(&dir);
            std::fs::create_dir_all(dir.join("m")).unwrap();
            for f in ["m/1.mp3", "m/2.mp3", "m/3.mp3"] {
                std::fs::write(dir.join(f), f.as_bytes()).unwrap();
            }
            let db = BaseDeDatos::en_memoria().unwrap();
            db.conexion()
                .unwrap()
                .execute_batch(
                    "INSERT INTO portadas (id, sha256, ruta, ancho, alto, bytes, mime, origen)
                         VALUES (1, printf('%064d', 1), 'p.jpg', 1, 1, 1, 'image/jpeg', 'x');
                     INSERT INTO artistas (id, nombre, clave) VALUES (1, 'Mana', 'mana');
                     INSERT INTO albumes (id, artista_id, titulo, clave, portada_id)
                         VALUES (10, 1, 'Suenos', 'suenos', 1);
                     INSERT INTO albumes (id, artista_id, titulo, clave) VALUES (11, 1, 'Otro', 'otro');
                     INSERT INTO pistas (id, titulo, artista_id, artista_nombre, album_id, album_titulo, ruta)
                         VALUES (1, 'uno', 1, 'Mana', 10, 'Suenos', 'm/1.mp3'),
                                (2, 'dos', 1, 'Mana', 10, 'Suenos', 'm/2.mp3'),
                                (3, 'tres', 1, 'Mana', 11, 'Otro', 'm/3.mp3');",
                )
                .unwrap();
            Self {
                rutas: Rutas::bajo(&dir).unwrap(),
                dir,
                db,
                red: Red::new(PoliticaDeRed::default()),
            }
        }

        fn entorno(&self) -> Entorno<'_> {
            Entorno {
                db: &self.db,
                rutas: &self.rutas,
                red: &self.red,
                musica: self.dir.clone(),
                clave_acoustid: None,
                clave_theaudiodb: None,
                fpcalc: PathBuf::from("fpcalc"),
                organizar: true,
                importacion: None,
                ia: None,
            }
        }

        fn valor<T: rusqlite::types::FromSql>(&self, sql: &str) -> T {
            self.db
                .conexion()
                .unwrap()
                .query_row(sql, [], |f| f.get(0))
                .unwrap()
        }
    }

    impl Drop for Montaje {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.dir);
        }
    }

    #[test]
    fn renombrar_un_album_conserva_su_id_y_su_portada() {
        let m = Montaje::nuevo("renombrar");
        let datos = DatosAlbum {
            titulo: "Sueños líquidos".into(),
            artista: "Mana".into(),
            anio: Some(1997),
        };
        assert_eq!(editar_album(&m.entorno(), 10, &datos).unwrap(), 10);
        assert_eq!(
            m.valor::<String>(
                "SELECT titulo || '|' || anio || '|' || portada_id FROM albumes WHERE id = 10"
            ),
            "Sueños líquidos|1997|1"
        );
        assert_eq!(
            m.valor::<i64>("SELECT count(*) FROM pistas WHERE album_titulo = 'Sueños líquidos' AND anio = 1997"),
            2
        );
    }

    #[test]
    fn renombrarlo_como_otro_del_mismo_artista_los_junta_sin_perder_la_portada() {
        let m = Montaje::nuevo("juntar");
        let datos = DatosAlbum {
            titulo: "Otro".into(),
            artista: "Mana".into(),
            anio: None,
        };
        assert_eq!(editar_album(&m.entorno(), 10, &datos).unwrap(), 11);
        assert_eq!(
            m.valor::<i64>("SELECT count(*) FROM pistas WHERE album_id = 11"),
            3
        );
        assert_eq!(
            m.valor::<i64>("SELECT count(*) FROM albumes WHERE id = 10"),
            0
        );
        assert_eq!(
            m.valor::<i64>("SELECT portada_id FROM albumes WHERE id = 11"),
            1
        );
    }

    #[test]
    fn cambiar_el_artista_de_un_album_se_lleva_sus_pistas_y_borra_al_artista_vacio() {
        let m = Montaje::nuevo("artista");
        let e = m.entorno();
        editar_album(
            &e,
            11,
            &DatosAlbum {
                titulo: "Otro".into(),
                artista: "Maná".into(),
                anio: None,
            },
        )
        .unwrap();
        editar_album(
            &e,
            10,
            &DatosAlbum {
                titulo: "Suenos".into(),
                artista: "Maná".into(),
                anio: None,
            },
        )
        .unwrap();
        assert_eq!(
            m.valor::<String>("SELECT group_concat(DISTINCT artista_nombre) FROM pistas"),
            "Maná"
        );
        assert_eq!(
            m.valor::<i64>("SELECT count(*) FROM artistas WHERE id = 1"),
            0
        );
    }

    #[test]
    fn editar_una_pista_conserva_su_id_y_su_verificacion() {
        let m = Montaje::nuevo("pista");
        m.db.conexion()
            .unwrap()
            .execute("UPDATE pistas SET verificada = 0 WHERE id = 3", [])
            .unwrap();
        editar_pista(
            &m.entorno(),
            3,
            &DatosPista {
                titulo: " Tres ".into(),
                artista: "Mana".into(),
                album: "Suenos".into(),
                numero: Some(3),
                anio: Some(1997),
                genero: Some("Rock".into()),
            },
        )
        .unwrap();
        assert_eq!(
            datos_pista(&m.db, 3).unwrap(),
            DatosPista {
                titulo: "Tres".into(),
                artista: "Mana".into(),
                album: "Suenos".into(),
                numero: Some(3),
                anio: Some(1997),
                genero: Some("Rock".into()),
            }
        );
        assert_eq!(
            m.valor::<String>("SELECT album_id || '|' || verificada FROM pistas WHERE id = 3"),
            "10|0"
        );
        assert_eq!(
            m.valor::<i64>("SELECT count(*) FROM albumes WHERE id = 11"),
            0,
            "el álbum que se queda vacío sobra"
        );
        let huella: String = m.valor("SELECT sha256 FROM pistas WHERE id = 3");
        let recordada = correcciones::buscar(&m.db, &huella, None, None)
            .unwrap()
            .expect("editar deja la corrección para la próxima importación");
        assert_eq!(recordada.titulo, "Tres");
    }

    #[test]
    fn los_datos_que_no_valen_se_rechazan_sin_tocar_nada() {
        let m = Montaje::nuevo("validar");
        let e = m.entorno();
        let base = DatosPista {
            titulo: "x".into(),
            artista: "y".into(),
            album: String::new(),
            numero: None,
            anio: None,
            genero: None,
        };
        for malo in [
            DatosPista {
                titulo: "  ".into(),
                ..base.clone()
            },
            DatosPista {
                numero: Some(0),
                ..base.clone()
            },
            DatosPista {
                anio: Some(20_000),
                ..base.clone()
            },
            DatosPista {
                artista: "a".repeat(LARGO_MAXIMO + 1),
                ..base.clone()
            },
        ] {
            assert_eq!(editar_pista(&e, 1, &malo), Err(NsError::InvalidInput));
        }
        assert_eq!(editar_pista(&e, 99, &base), Err(NsError::InvalidInput));
        assert_eq!(
            m.valor::<String>("SELECT titulo FROM pistas WHERE id = 1"),
            "uno"
        );
    }
}
