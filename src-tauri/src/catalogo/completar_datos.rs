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

use serde::Serialize;
use ts_rs::TS;

use super::canalizacion::{alta_de_candidato, completar, identificar_y_decidir, validar, Entorno};
use super::edicion;
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
    let fila = edicion::leer_fila(e.db, pista)?;
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
    let mut alta = edicion::alta_de_fila(&fila);
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
                alta.genero = fila.genero.clone();
                edicion::escribir_etiquetas(&archivo, &alta);
                let (artista, album) = edicion::reasignar(e, pista, &fila, &alta, &archivo)?;
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
    use crate::catalogo::canalizacion::Alta;
    use crate::catalogo::canalizacion::{procesar, Resultado};
    use crate::catalogo::duplicados::huella_de_archivo;
    use crate::catalogo::duplicados::Gestor;
    use crate::catalogo::etiquetas::{self, Escritura};
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
        let fila = edicion::leer_fila(&db, 7).unwrap();
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
        let (artista, album) = edicion::reasignar(&e, 7, &fila, &alta, &archivo).unwrap();
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
