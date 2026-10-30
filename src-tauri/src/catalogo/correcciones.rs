//! Las correcciones del catálogo: lo que el usuario dejó dicho sobre una canción
//! y que, al importarla otra vez, gana a lo que digan las fuentes
//! (`core/overrides.py` de la V1, F4.2.5).
//!
//! La V1 las guardaba sin interfaz para crearlas; la V2 las crea al editar los
//! datos de una pista, y el importador ya trajo las de la V1 a
//! `correcciones_catalogo` con sus mismos tipos y su mismo JSON. Por eso se leen
//! las claves de la V1 (`titulo_oficial`, `artista_principal`…) además de las
//! que escribe la V2.

use rusqlite::{params, OptionalExtension};
use serde_json::{json, Value};

use super::canalizacion::Alta;
use super::texto::para_comparacion;
use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};

/// La clave de "artista y título" de la V1: los dos normalizados para comparar.
#[must_use]
pub fn clave_artista_titulo(artista: &str, titulo: &str) -> Option<String> {
    let (a, t) = (para_comparacion(artista), para_comparacion(titulo));
    (!a.is_empty() && !t.is_empty()).then(|| format!("{a}::{t}"))
}

/// Busca una corrección activa en el orden de la V1: por huella, por ISRC y por
/// artista y título. La primera que vale gana.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn buscar(
    db: &BaseDeDatos,
    huella: &str,
    isrc: Option<&str>,
    artista_titulo: Option<&str>,
) -> NsResult<Option<Alta>> {
    let conn = db.conexion()?;
    let claves = [
        ("hash", Some(huella).filter(|h| !h.is_empty())),
        ("isrc", isrc.filter(|i| !i.trim().is_empty())),
        ("artist_title", artista_titulo),
    ];
    for (tipo, valor) in claves {
        let Some(valor) = valor else { continue };
        let cambios: Option<String> = conn
            .query_row(
                "SELECT cambios FROM correcciones_catalogo
                 WHERE activa = 1 AND tipo = ?1 AND valor = ?2
                 ORDER BY actualizada_en DESC LIMIT 1",
                params![tipo, valor],
                |f| f.get(0),
            )
            .optional()
            .map_err(|_| NsError::StorageFailure)?;
        // Una corrección que no se entiende no tapa a las siguientes.
        if let Some(a) = cambios
            .and_then(|c| serde_json::from_str::<Value>(&c).ok())
            .and_then(|v| alta_de(&v))
        {
            return Ok(Some(a));
        }
    }
    Ok(None)
}

fn texto(v: &Value, claves: &[&str]) -> Option<String> {
    claves
        .iter()
        .find_map(|k| v.get(k).and_then(Value::as_str))
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
}

/// `candidato_desde_payload`: vale si dice al menos qué grabación, qué
/// lanzamiento, qué ISRC, qué artista o qué título.
fn alta_de(v: &Value) -> Option<Alta> {
    let titulo = texto(v, &["titulo_oficial", "titulo"]);
    let artista = texto(v, &["artista_principal", "artista"]);
    let mbid_grabacion = texto(v, &["recording_id"]);
    let mbid_lanzamiento = texto(v, &["release_id"]);
    let isrc = texto(v, &["isrc"]);
    if titulo.is_none()
        && artista.is_none()
        && mbid_grabacion.is_none()
        && mbid_lanzamiento.is_none()
        && isrc.is_none()
    {
        return None;
    }
    let numero = v.get("numero").and_then(Value::as_u64);
    let anio = v.get("anio").and_then(Value::as_i64);
    Some(Alta {
        titulo: titulo.unwrap_or_default(),
        artista: artista.unwrap_or_default(),
        album: texto(v, &["album_oficial", "album"]).unwrap_or_default(),
        tipo: texto(v, &["tipo_release"]).unwrap_or_default(),
        numero: numero.and_then(|n| u32::try_from(n).ok()),
        anio: anio.and_then(|a| i32::try_from(a).ok()),
        genero: texto(v, &["genero"]),
        // Lo que identificó MusicBrainz sigue verificado; lo escrito a mano, no.
        verificada: mbid_grabacion.is_some() || mbid_lanzamiento.is_some(),
        isrc,
        mbid_grabacion,
        mbid_lanzamiento,
        mbid_grupo: texto(v, &["release_group_id"]),
        fuentes: vec!["correccion"],
        ..Alta::default()
    })
}

/// Lo que se guarda: las claves de la V1, para que una sola forma sirva a las
/// dos.
fn cambios_de(a: &Alta) -> Value {
    json!({
        "titulo_oficial": a.titulo,
        "artista_principal": a.artista,
        "album_oficial": a.album,
        "tipo_release": a.tipo,
        "numero": a.numero,
        "anio": a.anio,
        "genero": a.genero,
        "isrc": a.isrc,
        "recording_id": a.mbid_grabacion,
        "release_id": a.mbid_lanzamiento,
    })
}

/// Recuerda lo que el usuario dejó en una pista, por su huella y por su ISRC.
/// La tabla no tiene unicidad por tipo y valor (la V1 sí), así que se actualiza
/// la que hubiera y si no se crea.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la escritura falla.
pub fn recordar(tx: &rusqlite::Transaction<'_>, huella: Option<&str>, a: &Alta) -> NsResult<()> {
    let cambios = cambios_de(a).to_string();
    let claves = [
        ("hash", huella.filter(|h| !h.is_empty())),
        ("isrc", a.isrc.as_deref().filter(|i| !i.trim().is_empty())),
    ];
    for (tipo, valor) in claves {
        let Some(valor) = valor else { continue };
        let cambiadas = tx
            .execute(
                "UPDATE correcciones_catalogo SET cambios = ?3, origen = 'manual', activa = 1,
                     actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                 WHERE tipo = ?1 AND valor = ?2",
                params![tipo, valor, cambios],
            )
            .map_err(|_| NsError::StorageFailure)?;
        if cambiadas == 0 {
            tx.execute(
                "INSERT INTO correcciones_catalogo (tipo, valor, cambios, motivo, origen)
                 VALUES (?1, ?2, ?3, 'editado a mano', 'manual')",
                params![tipo, valor, cambios],
            )
            .map_err(|_| NsError::StorageFailure)?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db;

    #[test]
    fn una_correccion_de_la_v1_se_lee_con_sus_claves() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute(
                "INSERT INTO correcciones_catalogo (tipo, valor, cambios) VALUES
                 ('artist_title', 'mana::rayando el sol',
                  '{\"titulo_oficial\": \"Rayando el sol\", \"artista_principal\": \"Maná\",
                    \"album_oficial\": \"Falta amor\", \"release_id\": \"r1\"}')",
                [],
            )
            .unwrap();
        let clave = clave_artista_titulo("Maná", "Rayando el Sol").unwrap();
        assert_eq!(clave, "mana::rayando el sol");
        let a = buscar(&db, "", None, Some(&clave)).unwrap().unwrap();
        assert_eq!(
            (
                a.titulo.as_str(),
                a.artista.as_str(),
                a.album.as_str(),
                a.verificada
            ),
            ("Rayando el sol", "Maná", "Falta amor", true)
        );
    }

    #[test]
    fn la_huella_gana_al_isrc_y_lo_que_no_vale_no_tapa_lo_siguiente() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO correcciones_catalogo (tipo, valor, cambios) VALUES
                     ('hash', 'h1', '{\"titulo\": \"por huella\"}'),
                     ('hash', 'h2', '{\"nada\": 1}'),
                     ('isrc', 'I1', '{\"titulo\": \"por isrc\"}');
                 INSERT INTO correcciones_catalogo (tipo, valor, cambios, activa) VALUES
                     ('isrc', 'I2', '{\"titulo\": \"apagada\"}', 0);",
            )
            .unwrap();
        let titulo = |h: &str, i: Option<&str>| buscar(&db, h, i, None).unwrap().map(|a| a.titulo);
        assert_eq!(titulo("h1", Some("I1")).as_deref(), Some("por huella"));
        assert_eq!(titulo("h2", Some("I1")).as_deref(), Some("por isrc"));
        assert_eq!(titulo("x", Some("I2")), None);
    }

    #[test]
    fn recordar_dos_veces_actualiza_en_vez_de_duplicar() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let mut a = Alta {
            titulo: "Uno".into(),
            artista: "A".into(),
            isrc: Some("I1".into()),
            ..Alta::default()
        };
        for titulo in ["Uno", "Dos"] {
            a.titulo = titulo.into();
            let mut conn = db.conexion().unwrap();
            let tx = db::transaccion_de_escritura(&mut conn).unwrap();
            recordar(&tx, Some("h"), &a).unwrap();
            tx.commit().unwrap();
        }
        let n: i64 = db
            .conexion()
            .unwrap()
            .query_row("SELECT count(*) FROM correcciones_catalogo", [], |f| {
                f.get(0)
            })
            .unwrap();
        assert_eq!(n, 2, "una por huella y una por ISRC");
        let a = buscar(&db, "h", None, None).unwrap().unwrap();
        assert_eq!((a.titulo.as_str(), a.verificada), ("Dos", false));
    }
}
