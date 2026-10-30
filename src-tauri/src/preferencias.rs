//! Preferencias del usuario que la interfaz lee y cambia (Ajustes).
//!
//! Viven en la tabla `preferencias` como JSON (V3), adonde el importador trajo las
//! de la V1. La interfaz solo puede escribir las claves de esta lista, y cada una
//! con su tipo: una clave nueva se añade aquí con su validación, no se acepta a
//! ciegas lo que llegue del webview.

use rusqlite::OptionalExtension;
use serde::Serialize;
use serde_json::Value;
use ts_rs::TS;

use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};

/// Las tipografías que viajan con la aplicación (`src/fuentes.css`).
pub const TIPOGRAFIAS: [&str; 5] = [
    "Inter",
    "Fira Sans",
    "IBM Plex Sans",
    "Atkinson Hyperlegible",
    "Source Sans 3",
];

/// Lo que la interfaz necesita para pintarse como la dejó el usuario.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct Apariencia {
    /// El id de un tema de la V1.
    pub tema: String,
    pub tipografia: String,
    /// En porcentaje, como la V1 (`ui_scale`).
    pub escala: f64,
    /// La vista de reproducción toma el color de la portada.
    pub color_por_portada: bool,
    pub nombre_usuario: Option<String>,
}

fn leer(conn: &rusqlite::Connection, clave: &str) -> NsResult<Option<Value>> {
    let v: Option<String> = conn
        .query_row(
            "SELECT valor FROM preferencias WHERE clave = ?1",
            [clave],
            |f| f.get(0),
        )
        .optional()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(v.and_then(|v| serde_json::from_str(&v).ok()))
}

/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn apariencia(db: &BaseDeDatos) -> NsResult<Apariencia> {
    let conn = db.conexion()?;
    let texto = |v: Option<Value>| v.and_then(|v| v.as_str().map(str::to_owned));
    Ok(Apariencia {
        tema: texto(leer(&conn, "tema")?).unwrap_or_else(|| "negro_puro".to_owned()),
        tipografia: texto(leer(&conn, "tipografia")?)
            .filter(|t| TIPOGRAFIAS.contains(&t.as_str()))
            .unwrap_or_else(|| "Inter".to_owned()),
        escala: leer(&conn, "escala")?
            .and_then(|v| v.as_f64())
            .filter(|e| (75.0..=150.0).contains(e))
            .unwrap_or(100.0),
        color_por_portada: leer(&conn, "color_por_portada")?
            .and_then(|v| v.as_bool())
            .unwrap_or(true),
        nombre_usuario: texto(leer(&conn, "nombre_usuario")?).filter(|n| !n.trim().is_empty()),
    })
}

/// Comprueba que un valor vale para su clave. Las claves fuera de la lista se
/// rechazan.
fn validar(clave: &str, valor: &Value) -> NsResult<()> {
    let ok = match clave {
        "tema" => valor.as_str().is_some_and(|t| {
            !t.is_empty()
                && t.len() <= 64
                && t.chars()
                    .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
        }),
        "tipografia" => valor.as_str().is_some_and(|t| TIPOGRAFIAS.contains(&t)),
        "escala" => valor.as_f64().is_some_and(|e| (75.0..=150.0).contains(&e)),
        "color_por_portada" | "analisis_activado" | "servidor_movil_al_arrancar" => {
            valor.is_boolean()
        }
        "nombre_usuario" => valor.as_str().is_some_and(|n| n.chars().count() <= 60),
        _ => return Err(NsError::PathNotAllowed),
    };
    if ok {
        Ok(())
    } else {
        Err(NsError::InvalidInput)
    }
}

/// # Errors
///
/// - [`NsError::PathNotAllowed`] si la clave no es una de las que la interfaz
///   puede cambiar.
/// - [`NsError::InvalidInput`] si el valor no vale para esa clave.
pub fn guardar(db: &BaseDeDatos, clave: &str, valor: &Value) -> NsResult<()> {
    validar(clave, valor)?;
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    tx.execute(
        "INSERT INTO preferencias (clave, valor) VALUES (?1, ?2)
         ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor,
             actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
        rusqlite::params![clave, valor.to_string()],
    )
    .map_err(|_| NsError::StorageFailure)?;
    tx.commit().map_err(|_| NsError::StorageFailure)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn sin_preferencias_la_apariencia_es_la_de_fabrica_de_la_v1() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let a = apariencia(&db).unwrap();
        assert_eq!(
            (a.tema.as_str(), a.tipografia.as_str(), a.escala),
            ("negro_puro", "Inter", 100.0)
        );
    }

    #[test]
    fn lo_que_trajo_el_importador_se_respeta() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO preferencias (clave, valor) VALUES
                     ('tema', '\"sangre_dragon\"'), ('tipografia', '\"Fira Sans\"'), ('escala', '110');",
            )
            .unwrap();
        let a = apariencia(&db).unwrap();
        assert_eq!(
            (a.tema.as_str(), a.tipografia.as_str(), a.escala),
            ("sangre_dragon", "Fira Sans", 110.0)
        );
    }

    #[test]
    fn una_tipografia_que_no_viaja_con_la_aplicacion_cae_en_la_de_fabrica() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute(
                "INSERT INTO preferencias (clave, valor) VALUES ('tipografia', '\"Comic Sans\"')",
                [],
            )
            .unwrap();
        assert_eq!(apariencia(&db).unwrap().tipografia, "Inter");
    }

    #[test]
    fn solo_se_guardan_las_claves_de_la_lista_con_su_tipo() {
        let db = BaseDeDatos::en_memoria().unwrap();
        guardar(&db, "tema", &json!("lava")).unwrap();
        assert_eq!(apariencia(&db).unwrap().tema, "lava");
        assert_eq!(
            guardar(&db, "politica_de_red", &json!({})),
            Err(NsError::PathNotAllowed)
        );
        assert_eq!(
            guardar(&db, "escala", &json!(400)),
            Err(NsError::InvalidInput)
        );
        assert_eq!(
            guardar(&db, "tema", &json!("<script>")),
            Err(NsError::InvalidInput)
        );
        assert_eq!(
            guardar(&db, "tipografia", &json!("Comic Sans")),
            Err(NsError::InvalidInput)
        );
    }
}
