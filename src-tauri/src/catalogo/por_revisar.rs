//! Por revisar (F4.2.4 y F4.2.8): lo que no entró solo, con su motivo, y lo que
//! el usuario puede hacer con cada archivo (enmienda de ADR-007).
//!
//! - **Importar tal como está**: entra con sus etiquetas, sin verificar.
//! - **Elegir un candidato**: entra con los datos de ese candidato, verificado.
//! - **Descartar**: a la papelera del sistema; nunca se borra del todo.
//! - **Buscar de nuevo**: vuelve a la cola de importación.

use std::path::{Path, PathBuf};

use rusqlite::OptionalExtension;
use serde::Serialize;
use serde_json::Value;
use ts_rs::TS;

use super::canalizacion::{self, Alta, Entorno};
use super::etiquetas;
use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};

/// Tope de lo que se lista: en la instalación real de la V1 había 116.
pub const MAX_PENDIENTES: usize = 5_000;

/// Un candidato que se ofrece para elegir.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct CandidatoRevisar {
    pub titulo: String,
    pub artista: String,
    pub album: String,
    #[ts(type = "number | null")]
    pub anio: Option<i64>,
    pub tipo: String,
    pub duracion_seg: Option<f64>,
}

/// Un archivo pendiente.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct Pendiente {
    #[ts(type = "number")]
    pub id: i64,
    /// El nombre con el que llegó el archivo.
    pub nombre: String,
    /// La causa, con los valores de la enmienda de ADR-007.
    pub causa: String,
    pub titulo: Option<String>,
    pub artista: Option<String>,
    pub album: Option<String>,
    pub duracion_seg: Option<f64>,
    pub candidatos: Vec<CandidatoRevisar>,
    /// Lo que le faltaría si se importa tal como está: `portada`, `letra`,
    /// `album`, `anio`.
    pub faltaria: Vec<String>,
    pub registrado_en: String,
}

fn bd<T>(r: rusqlite::Result<T>) -> NsResult<T> {
    r.map_err(|_| NsError::StorageFailure)
}

fn texto(v: &Value, k: &str) -> Option<String> {
    v.get(k)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
}

/// Cota: [`MAX_PENDIENTES`].
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn listar(db: &BaseDeDatos) -> NsResult<Vec<Pendiente>> {
    let conn = db.conexion()?;
    let mut s = bd(conn.prepare(
        "SELECT id, ruta, causa, metadatos, registrado_en FROM por_revisar
         WHERE resuelto_en IS NULL ORDER BY registrado_en DESC, id DESC LIMIT ?1",
    ))?;
    let filas = bd(s.query_map([MAX_PENDIENTES as i64], |f| {
        Ok((
            f.get::<_, i64>(0)?,
            f.get::<_, String>(1)?,
            f.get::<_, String>(2)?,
            f.get::<_, Option<String>>(3)?,
            f.get::<_, String>(4)?,
        ))
    }))?;
    let mut salida = Vec::new();
    for fila in filas {
        let (id, ruta, causa, datos, registrado_en) = bd(fila)?;
        let d: Value = datos
            .and_then(|d| serde_json::from_str(&d).ok())
            .unwrap_or(Value::Null);
        let e = d.get("etiquetas").cloned().unwrap_or(Value::Null);
        let candidatos = d
            .get("candidatos")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .map(|c| CandidatoRevisar {
                titulo: texto(c, "titulo").unwrap_or_default(),
                artista: texto(c, "artista").unwrap_or_default(),
                album: texto(c, "album").unwrap_or_default(),
                anio: c.get("anio").and_then(Value::as_i64),
                tipo: texto(c, "tipo").unwrap_or_default(),
                duracion_seg: c.get("duracion_seg").and_then(Value::as_f64),
            })
            .collect();
        let (album, anio) = (texto(&e, "album"), texto(&e, "anio"));
        let mut faltaria = Vec::new();
        // Lo que se sabe sin abrir el archivo; la portada y la letra se miran en él.
        let archivo = Path::new(&ruta);
        if crate::catalogo::portadas_red::de_etiquetas(archivo).is_none() {
            faltaria.push("portada".to_owned());
        }
        if etiquetas::leer(archivo)
            .ok()
            .and_then(|(_, c)| c.letra)
            .is_none()
        {
            faltaria.push("letra".to_owned());
        }
        if album.is_none() {
            faltaria.push("album".to_owned());
        }
        if anio.is_none() {
            faltaria.push("anio".to_owned());
        }
        salida.push(Pendiente {
            id,
            nombre: texto(&d, "nombre_original").unwrap_or_else(|| {
                archivo
                    .file_name()
                    .map(|n| n.to_string_lossy().into_owned())
                    .unwrap_or_default()
            }),
            causa,
            titulo: texto(&e, "titulo"),
            artista: texto(&e, "artista"),
            album,
            duracion_seg: d.get("duracion_seg").and_then(Value::as_f64),
            candidatos,
            faltaria,
            registrado_en,
        });
    }
    Ok(salida)
}

/// Lo que espera, para el número de la barra lateral.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn contar(db: &BaseDeDatos) -> NsResult<u32> {
    db.conexion()?
        .query_row(
            "SELECT count(*) FROM por_revisar WHERE resuelto_en IS NULL",
            [],
            |f| f.get::<_, i64>(0),
        )
        .map(|n| n as u32)
        .map_err(|_| NsError::StorageFailure)
}

fn fila(db: &BaseDeDatos, id: i64) -> NsResult<(PathBuf, Value)> {
    let f: Option<(String, Option<String>)> = bd(db
        .conexion()?
        .query_row(
            "SELECT ruta, metadatos FROM por_revisar WHERE id = ?1 AND resuelto_en IS NULL",
            [id],
            |f| Ok((f.get(0)?, f.get(1)?)),
        )
        .optional())?;
    let (ruta, datos) = f.ok_or(NsError::FileNotFound)?;
    Ok((
        PathBuf::from(ruta),
        datos
            .and_then(|d| serde_json::from_str(&d).ok())
            .unwrap_or(Value::Null),
    ))
}

fn resolver(db: &BaseDeDatos, id: i64) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    bd(tx.execute(
        "UPDATE por_revisar SET resuelto_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?1",
        [id],
    ))?;
    bd(tx.commit())
}

/// Importa un pendiente: tal como está (`candidato = None`) o con el candidato
/// elegido. Devuelve el id de la pista.
///
/// # Errors
///
/// - [`NsError::FileNotFound`] si ya no está pendiente o su archivo desapareció.
/// - [`NsError::AudioCorrupted`] si el archivo no se puede leer como audio.
/// - [`NsError::InvalidInput`] si el candidato no existe.
pub fn importar(e: &Entorno<'_>, id: i64, candidato: Option<usize>) -> NsResult<i64> {
    let (ruta, datos) = fila(e.db, id)?;
    if !ruta.is_file() {
        return Err(NsError::FileNotFound);
    }
    let (tecnico, cruda) = etiquetas::leer(&ruta)?;
    let nombre = texto(&datos, "nombre_original").unwrap_or_default();
    let (alta, escribir) = match candidato {
        None => (
            canalizacion::alta_tal_cual(&cruda, &nombre, tecnico.duracion_seg),
            false,
        ),
        Some(i) => {
            let c = datos
                .get("candidatos")
                .and_then(Value::as_array)
                .and_then(|l| l.get(i))
                .ok_or(NsError::InvalidInput)?;
            let t = |k: &str| texto(c, k).unwrap_or_default();
            (
                Alta {
                    titulo: t("titulo"),
                    artista: t("artista"),
                    album: t("album"),
                    tipo: t("tipo"),
                    anio: c.get("anio").and_then(Value::as_i64).map(|a| a as i32),
                    mbid_grabacion: texto(c, "mbid_grabacion"),
                    mbid_lanzamiento: texto(c, "mbid_lanzamiento"),
                    verificada: true,
                    fuentes: vec!["musicbrainz", "usuario"],
                    ..Alta::default()
                },
                true,
            )
        }
    };
    let pista = canalizacion::importar(e, &ruta, &alta, &tecnico, &cruda, escribir)?;
    resolver(e.db, id)?;
    Ok(pista)
}

/// A la papelera del sistema, y fuera de la lista.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la papelera no lo acepta.
pub fn descartar(db: &BaseDeDatos, id: i64) -> NsResult<()> {
    let (ruta, _) = fila(db, id)?;
    if ruta.exists() {
        trash::delete(&ruta).map_err(|error| {
            tracing::error!(error = %error, "la papelera no aceptó un archivo");
            NsError::StorageFailure
        })?;
    }
    resolver(db, id)
}

/// La ruta de un pendiente, para devolverlo a la cola de importación.
///
/// # Errors
///
/// [`NsError::FileNotFound`] si ya no está pendiente.
pub fn para_reintentar(db: &BaseDeDatos, id: i64) -> NsResult<PathBuf> {
    let (ruta, _) = fila(db, id)?;
    resolver(db, id)?;
    Ok(ruta)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::audio::pruebas::wav;
    use crate::catalogo::duplicados::Gestor;
    use crate::catalogo::etiquetas::Escritura;
    use crate::net::{PoliticaDeRed, Red};
    use crate::paths::Rutas;

    #[test]
    fn un_pendiente_se_importa_tal_cual_o_con_su_candidato() {
        let d = std::env::temp_dir().join(format!("ns-por-revisar-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        let rutas = Rutas::bajo(&d).unwrap();
        let musica = d.join("musica");
        std::fs::create_dir_all(&musica).unwrap();
        let db = BaseDeDatos::en_memoria().unwrap();
        let red = Red::new(PoliticaDeRed::default());
        let e = Entorno {
            db: &db,
            rutas: &rutas,
            red: &red,
            musica: musica.clone(),
            clave_acoustid: None,
            clave_theaudiodb: None,
            fpcalc: PathBuf::from("fpcalc"),
            organizar: true,
            importacion: None,
            ia: None,
        };
        let a = d.join("Maná - Clavado.wav");
        let _ = wav(&a, 44_100, 44_100 * 20, |i, _| (i % 50) as f32 / 200.0);
        etiquetas::escribir(
            &a,
            &Escritura {
                titulo: Some("Clavado".into()),
                ..Escritura::default()
            },
        )
        .unwrap();
        // Sin artista en las etiquetas ni red: a Por revisar.
        let mut g = Gestor::default();
        let r = canalizacion::procesar(&e, &mut g, &a).unwrap();
        let canalizacion::Resultado::PorRevisar { id, .. } = r else {
            panic!("{r:?}")
        };
        assert_eq!(contar(&db).unwrap(), 1);
        let l = listar(&db).unwrap();
        assert_eq!(
            (l[0].nombre.as_str(), l[0].titulo.as_deref()),
            ("Maná - Clavado.wav", Some("Clavado"))
        );
        assert!(l[0].faltaria.contains(&"portada".to_owned()));
        let pista = importar(&e, id, None).unwrap();
        assert_eq!(contar(&db).unwrap(), 0);
        let (titulo, artista, verificada): (String, String, bool) = db
            .conexion()
            .unwrap()
            .query_row(
                "SELECT titulo, artista_nombre, verificada FROM pistas WHERE id = ?1",
                [pista],
                |f| Ok((f.get(0)?, f.get(1)?, f.get(2)?)),
            )
            .unwrap();
        assert_eq!(
            (titulo.as_str(), artista.as_str(), verificada),
            ("Clavado", "Maná", false),
            "el artista sale del nombre"
        );
        assert_eq!(
            importar(&e, id, None),
            Err(NsError::FileNotFound),
            "ya no está pendiente"
        );
    }
}
