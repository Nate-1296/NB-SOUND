//! "Completar datos" de una pista importada tal como está (F4.2.8, enmienda de
//! ADR-007): identificarla de nuevo y buscarle portada y letra, **sin cambiar su
//! `id`**. El teléfono, las playlists, el DJ y el historial la siguen
//! reconociendo; el manifiesto móvil se entera por los disparadores de V5.
//!
//! La identificación es la de la canalización ([`identificar_y_decidir`]). Si
//! entra, la fila se actualiza en su sitio y queda verificada; el archivo recibe
//! las etiquetas nuevas pero **no se mueve**: cambiar la ruta de algo que el
//! usuario ya tiene en su biblioteca por pulsar "Completar datos" sería una
//! sorpresa. Portada y letra salen de [`completar`], que solo rellena lo que
//! falta.

use std::path::{Path, PathBuf};

use rusqlite::{params, OptionalExtension};
use serde::Serialize;
use ts_rs::TS;

use super::canalizacion::{
    album_id, alta_de_candidato, artista_id, bd, completar, identificar_y_decidir, validar, Alta,
    Entorno,
};
use super::duplicados::huella_de_archivo;
use super::etiquetas::{self, Escritura};
use crate::db;
use crate::error::{NsError, NsResult};
use crate::net::Servicio;

/// Lo que se le añadió a la pista. Todo en falso quiere decir que no se
/// encontró nada nuevo, no que fallara.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct DatosCompletados {
    /// Se identificó y ahora está verificada.
    pub identificada: bool,
    pub portada: bool,
    pub letra: bool,
}

struct Fila {
    ruta: String,
    titulo: String,
    artista: String,
    album: String,
    artista_id: Option<i64>,
    album_id: Option<i64>,
    numero: Option<u32>,
    anio: Option<i32>,
    isrc: Option<String>,
    mbid_grabacion: Option<String>,
    mbid_lanzamiento: Option<String>,
    tipo: Option<String>,
    verificada: bool,
}

fn leer_fila(e: &Entorno<'_>, pista: i64) -> NsResult<Fila> {
    e.db.conexion()?
        .query_row(
            "SELECT ruta, titulo, artista_nombre, album_titulo, artista_id, album_id, numero, anio,
                    isrc, mbid_grabacion, mbid_lanzamiento, tipo_lanzamiento, verificada
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
                    isrc: f.get(8)?,
                    mbid_grabacion: f.get(9)?,
                    mbid_lanzamiento: f.get(10)?,
                    tipo: f.get(11)?,
                    verificada: f.get(12)?,
                })
            },
        )
        .optional()
        .map_err(|_| NsError::StorageFailure)?
        .ok_or(NsError::InvalidInput)
}

/// Lo que ya tiene: portada (suya o de su álbum) y letra.
fn tiene(e: &Entorno<'_>, pista: i64) -> NsResult<(bool, bool)> {
    let conn = e.db.conexion()?;
    let portada: Option<i64> = conn
        .query_row(
            "SELECT coalesce(p.portada_id, a.portada_id) FROM pistas p
             LEFT JOIN albumes a ON a.id = p.album_id WHERE p.id = ?1",
            [pista],
            |f| f.get(0),
        )
        .map_err(|_| NsError::StorageFailure)?;
    let letra: bool = conn
        .query_row(
            "SELECT EXISTS (SELECT 1 FROM letras WHERE pista_id = ?1)",
            [pista],
            |f| f.get(0),
        )
        .map_err(|_| NsError::StorageFailure)?;
    Ok((portada.is_some(), letra))
}

fn alta_de_fila(f: &Fila) -> Alta {
    Alta {
        titulo: f.titulo.clone(),
        artista: f.artista.clone(),
        album: f.album.clone(),
        tipo: f.tipo.clone().unwrap_or_default(),
        numero: f.numero,
        anio: f.anio,
        isrc: f.isrc.clone(),
        mbid_grabacion: f.mbid_grabacion.clone(),
        mbid_lanzamiento: f.mbid_lanzamiento.clone(),
        verificada: f.verificada,
        ..Alta::default()
    }
}

/// Pone los datos identificados en la misma fila y borra el álbum y el artista
/// que se queden sin nada. Devuelve los ids nuevos de artista y álbum.
fn reasignar(
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
             album_titulo = ?5, numero = ?6, anio = ?7, isrc = ?8, mbid_grabacion = ?9,
             mbid_lanzamiento = ?10, tipo_lanzamiento = ?11, fuentes_etiquetado = ?12,
             sha256 = ?13, tamano = ?14, verificada = 1
         WHERE id = ?15",
        params![
            a.titulo.trim(),
            artista,
            artista_nombre,
            album,
            album_titulo,
            a.numero.filter(|n| *n > 0),
            a.anio.filter(|y| (1000..=9999).contains(y)),
            a.isrc,
            a.mbid_grabacion,
            a.mbid_lanzamiento,
            Some(a.tipo.clone()).filter(|x| !x.is_empty()),
            serde_json::to_string(&a.fuentes).ok(),
            sha256,
            tamano as i64,
            pista,
        ],
    ))?;
    if let Some(viejo) = anterior.album_id.filter(|v| Some(*v) != album) {
        bd(tx.execute(
            "DELETE FROM albumes WHERE id = ?1
             AND NOT EXISTS (SELECT 1 FROM pistas WHERE album_id = ?1)",
            [viejo],
        ))?;
    }
    if let Some(viejo) = anterior.artista_id.filter(|v| *v != artista) {
        bd(tx.execute(
            "DELETE FROM artistas WHERE id = ?1
             AND NOT EXISTS (SELECT 1 FROM pistas WHERE artista_id = ?1)
             AND NOT EXISTS (SELECT 1 FROM albumes WHERE artista_id = ?1)",
            [viejo],
        ))?;
    }
    bd(tx.commit())?;
    Ok((artista, album))
}

/// Completa una pista. Una pista ya verificada no se vuelve a identificar: solo
/// se le busca lo que le falte.
///
/// # Errors
///
/// - [`NsError::InvalidInput`] si la pista no existe.
/// - [`NsError::FileNotFound`] si su archivo ya no está.
/// - [`NsError::AudioCorrupted`] si el archivo no se puede leer.
/// - [`NsError::StorageFailure`] si la base falla.
pub fn completar_datos(e: &Entorno<'_>, pista: i64) -> NsResult<DatosCompletados> {
    let fila = leer_fila(e, pista)?;
    let archivo: PathBuf = if Path::new(&fila.ruta).is_absolute() {
        PathBuf::from(&fila.ruta)
    } else {
        e.musica.join(&fila.ruta)
    };
    if !archivo.is_file() {
        return Err(NsError::FileNotFound);
    }
    let (tecnico, cruda) = validar(&archivo).map_err(|_| NsError::AudioCorrupted)?;
    let antes = tiene(e, pista)?;
    let mut alta = alta_de_fila(&fila);
    let mut ids = (fila.artista_id, fila.album_id);
    let mut identificada = false;
    let con_red = e
        .red
        .autorizar(Servicio::MusicBrainz, "https://musicbrainz.org/ws/2/")
        .is_ok();
    if !fila.verificada && con_red {
        let nombre = archivo
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or_default();
        if let Ok(i) = identificar_y_decidir(e, &archivo, &cruda, &tecnico, nombre) {
            if let Some(c) = i.elegido.as_ref().filter(|_| i.veredicto.entra()) {
                let mut fuentes = vec!["tag_local"];
                if i.shazam.is_some() {
                    fuentes.push("shazam");
                }
                if i.acoustid
                    .as_ref()
                    .is_some_and(|a| !a.grabaciones.is_empty())
                {
                    fuentes.push("acoustid");
                }
                fuentes.push("musicbrainz");
                alta = alta_de_candidato(c, &i.norm, fuentes);
                // Si el archivo no admite escritura, los datos quedan en la
                // biblioteca igualmente: es lo que ve y sincroniza la aplicación.
                if etiquetas::escribir(
                    &archivo,
                    &Escritura {
                        titulo: Some(alta.titulo.clone()),
                        artista: Some(alta.artista.clone()),
                        album: Some(alta.album.clone()).filter(|x| !x.is_empty()),
                        numero: alta.numero,
                        total: alta.total,
                        anio: alta.anio,
                        isrc: alta.isrc.clone(),
                        mbid_grabacion: alta.mbid_grabacion.clone(),
                        mbid_lanzamiento: alta.mbid_lanzamiento.clone(),
                        mbid_grupo: alta.mbid_grupo.clone(),
                        tipo_lanzamiento: Some(alta.tipo.clone()).filter(|x| !x.is_empty()),
                    },
                )
                .is_err()
                {
                    tracing::warn!("no se pudieron escribir las etiquetas al completar datos");
                }
                let (artista, album) = reasignar(e, pista, &fila, &alta, &archivo)?;
                ids = (Some(artista), album);
                identificada = true;
            }
        }
    }
    completar(
        e,
        (pista, ids.0, ids.1),
        &archivo,
        &alta,
        &cruda,
        tecnico.duracion_seg,
    );
    let despues = tiene(e, pista)?;
    Ok(DatosCompletados {
        identificada,
        portada: !antes.0 && despues.0,
        letra: !antes.1 && despues.1,
    })
}

#[cfg(test)]
mod tests {
    use lofty::config::WriteOptions;
    use lofty::file::{AudioFile, TaggedFileExt};
    use lofty::prelude::ItemKey;

    use super::*;
    use crate::audio::pruebas::wav;
    use crate::catalogo::canalizacion::{procesar, Resultado};
    use crate::catalogo::duplicados::Gestor;
    use crate::db::BaseDeDatos;
    use crate::net::{PoliticaDeRed, Red};
    use crate::paths::Rutas;

    fn entorno<'a>(
        db: &'a BaseDeDatos,
        rutas: &'a Rutas,
        red: &'a Red,
        musica: &Path,
    ) -> Entorno<'a> {
        Entorno {
            db,
            rutas,
            red,
            musica: musica.to_path_buf(),
            clave_acoustid: None,
            clave_theaudiodb: None,
            fpcalc: PathBuf::from("fpcalc"),
            organizar: true,
            importacion: None,
            ia: None,
        }
    }

    #[test]
    fn completar_le_anade_la_letra_que_trae_el_archivo_sin_cambiar_su_id() {
        let dir = std::env::temp_dir().join(format!("ns-completar-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let rutas = Rutas::bajo(&dir).unwrap();
        let musica = dir.join("musica");
        std::fs::create_dir_all(&musica).unwrap();
        let db = BaseDeDatos::en_memoria().unwrap();
        let red = Red::new(PoliticaDeRed::default());
        let e = entorno(&db, &rutas, &red, &musica);

        let origen = dir.join("cancion.wav");
        let _ = wav(&origen, 44_100, 44_100 * 20, |i, c| {
            ((i * (c + 3)) % 97) as f32 / 400.0
        });
        etiquetas::escribir(
            &origen,
            &Escritura {
                titulo: Some("Rayando el sol".into()),
                artista: Some("Maná".into()),
                ..Escritura::default()
            },
        )
        .unwrap();
        let Resultado::Importada { pista, verificada } =
            procesar(&e, &mut Gestor::default(), &origen).unwrap()
        else {
            panic!("no entró");
        };
        assert!(!verificada);
        assert_eq!(tiene(&e, pista).unwrap(), (false, false));

        // El usuario le pone la letra al archivo después de importarlo.
        let ruta: String = db
            .conexion()
            .unwrap()
            .query_row("SELECT ruta FROM pistas WHERE id = ?1", [pista], |f| {
                f.get(0)
            })
            .unwrap();
        let archivo = musica.join(ruta);
        let mut f = lofty::read_from_path(&archivo).unwrap();
        let tipo = f.primary_tag_type();
        f.tag_mut(tipo).unwrap().insert_text(
            ItemKey::UnsyncLyrics,
            "Rayando el sol, desesperación".into(),
        );
        f.save_to_path(&archivo, WriteOptions::default()).unwrap();

        let hecho = completar_datos(&e, pista).unwrap();
        assert_eq!(
            hecho,
            DatosCompletados {
                identificada: false,
                portada: false,
                letra: true
            }
        );
        let (cuantas, misma): (i64, i64) = db
            .conexion()
            .unwrap()
            .query_row(
                "SELECT count(*), (SELECT count(*) FROM letras WHERE pista_id = ?1) FROM pistas",
                [pista],
                |f| Ok((f.get(0)?, f.get(1)?)),
            )
            .unwrap();
        assert_eq!((cuantas, misma), (1, 1), "la misma pista, ahora con letra");
        // Lo que ya tiene no se vuelve a contar como añadido.
        assert_eq!(
            completar_datos(&e, pista).unwrap(),
            DatosCompletados::default()
        );
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn una_pista_que_no_existe_o_sin_archivo_lo_dice() {
        let dir = std::env::temp_dir().join(format!("ns-completar-falta-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let rutas = Rutas::bajo(&dir).unwrap();
        let db = BaseDeDatos::en_memoria().unwrap();
        let red = Red::new(PoliticaDeRed::default());
        let e = entorno(&db, &rutas, &red, &dir);
        assert_eq!(completar_datos(&e, 99), Err(NsError::InvalidInput));
        db.conexion()
            .unwrap()
            .execute(
                "INSERT INTO pistas (titulo, ruta, verificada) VALUES ('x', 'no/esta.mp3', 0)",
                [],
            )
            .unwrap();
        assert_eq!(completar_datos(&e, 1), Err(NsError::FileNotFound));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn identificarla_rehace_su_fila_y_borra_el_album_y_el_artista_que_se_quedan_vacios() {
        let dir = std::env::temp_dir().join(format!("ns-reasignar-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let rutas = Rutas::bajo(&dir).unwrap();
        std::fs::create_dir_all(dir.join("x")).unwrap();
        let archivo = dir.join("x/pista.mp3");
        std::fs::write(&archivo, b"audio").unwrap();
        let db = BaseDeDatos::en_memoria().unwrap();
        let red = Red::new(PoliticaDeRed::default());
        let e = entorno(&db, &rutas, &red, &dir);
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'mana', 'mana');
                 INSERT INTO albumes (id, artista_id, titulo, clave) VALUES (5, 1, 'sin album', 'sin-album');
                 INSERT INTO pistas (id, titulo, artista_id, artista_nombre, album_id, album_titulo, ruta, verificada)
                     VALUES (7, 'rayando', 1, 'mana', 5, 'sin album', 'x/pista.mp3', 0);",
            )
            .unwrap();
        let fila = leer_fila(&e, 7).unwrap();
        let alta = Alta {
            titulo: "Rayando el sol".into(),
            artista: "Maná".into(),
            album: "¿Dónde jugarán los niños?".into(),
            numero: Some(4),
            mbid_grabacion: Some("g".into()),
            verificada: true,
            fuentes: vec!["tag_local", "musicbrainz"],
            ..Alta::default()
        };
        let (artista, album) = reasignar(&e, 7, &fila, &alta, &archivo).unwrap();
        let conn = db.conexion().unwrap();
        let (titulo, a, al, v, sha): (String, i64, i64, bool, String) = conn
            .query_row(
                "SELECT titulo, artista_id, album_id, verificada, sha256 FROM pistas WHERE id = 7",
                [],
                |f| Ok((f.get(0)?, f.get(1)?, f.get(2)?, f.get(3)?, f.get(4)?)),
            )
            .unwrap();
        assert_eq!(
            (titulo.as_str(), a, Some(al), v),
            ("Rayando el sol", artista, album, true)
        );
        assert_eq!(sha, huella_de_archivo(&archivo).unwrap());
        let quedan: (i64, i64) = conn
            .query_row(
                "SELECT (SELECT count(*) FROM albumes WHERE id = 5),
                        (SELECT count(*) FROM artistas WHERE id = 1)",
                [],
                |f| Ok((f.get(0)?, f.get(1)?)),
            )
            .unwrap();
        assert_eq!(
            quedan,
            (0, 0),
            "sin pistas, el álbum y el artista viejos sobran"
        );
        let _ = std::fs::remove_dir_all(&dir);
    }
}
