//! Ajustes > Privacidad y servicios en línea, e Inteligencia artificial (F4.2.7).
//!
//! La política de red se guarda en `preferencias` y se aplica a la puerta
//! ([`Red`]) en el acto: apagar un servicio corta la siguiente petición, no la
//! del próximo arranque. Del desempate por IA se guardan el proveedor y el
//! modelo; la clave va al llavero y **nunca vuelve al webview**: la interfaz solo
//! sabe si hay una (ADR-009).

use serde::{Deserialize, Serialize};
use serde_json::Value;
use ts_rs::TS;

use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};
use crate::net::{PoliticaDeRed, Red, Servicio};
use crate::secrets;

/// A quién se le pide el desempate.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub enum ProveedorIa {
    Anthropic,
    Openai,
}

impl ProveedorIa {
    /// El anfitrión de su API; también nombra la cuenta de su clave en el
    /// llavero, la misma bajo la que el importador dejó la de la V1.
    #[must_use]
    pub fn anfitrion(self) -> &'static str {
        match self {
            Self::Anthropic => "api.anthropic.com",
            Self::Openai => "api.openai.com",
        }
    }

    /// El modelo económico de cada uno. El de Anthropic lo fija ADR-009; el de
    /// OpenAI es el que usaba la V1 (`config/settings.py`).
    #[must_use]
    pub fn modelo_por_defecto(self) -> &'static str {
        match self {
            Self::Anthropic => "claude-haiku-5-5",
            Self::Openai => "gpt-4o-mini",
        }
    }

    fn cuenta(self) -> String {
        secrets::cuenta(Servicio::ProveedorIa, self.anfitrion())
    }
}

/// Lo que muestra la sección Inteligencia artificial.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct AjustesIa {
    pub proveedor: ProveedorIa,
    pub modelo: String,
    /// Si el llavero guarda una clave para este proveedor. La clave no viaja.
    pub tiene_clave: bool,
    /// Si el sistema tiene llavero. Sin él no se puede guardar ninguna clave, y
    /// no hay repliegue a texto plano.
    pub llavero: bool,
}

/// Tope del nombre de un modelo: los reales tienen unas decenas de caracteres.
const MODELO_MAXIMO: usize = 100;

fn leer(db: &BaseDeDatos, clave: &str) -> NsResult<Option<Value>> {
    use rusqlite::OptionalExtension;
    let v: Option<String> = db
        .conexion()?
        .query_row(
            "SELECT valor FROM preferencias WHERE clave = ?1",
            [clave],
            |f| f.get(0),
        )
        .optional()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(v.and_then(|v| serde_json::from_str(&v).ok()))
}

fn escribir(db: &BaseDeDatos, pares: &[(&str, Value)]) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    for (clave, valor) in pares {
        tx.execute(
            "INSERT INTO preferencias (clave, valor) VALUES (?1, ?2)
             ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor,
                 actualizada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
            rusqlite::params![clave, valor.to_string()],
        )
        .map_err(|_| NsError::StorageFailure)?;
    }
    tx.commit().map_err(|_| NsError::StorageFailure)
}

/// Guarda la política y la aplica a la puerta.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede guardar; entonces la puerta sigue
/// como estaba, para que lo que se ve y lo que se cumple no se separen.
pub fn cambiar_politica(db: &BaseDeDatos, red: &Red, nueva: PoliticaDeRed) -> NsResult<()> {
    let valor = serde_json::to_value(&nueva).map_err(|_| NsError::Internal)?;
    escribir(db, &[("politica_de_red", valor)])?;
    red.cambiar_politica(nueva);
    Ok(())
}

/// El proveedor y el modelo guardados, o los de fábrica.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn proveedor_y_modelo(db: &BaseDeDatos) -> NsResult<(ProveedorIa, String)> {
    let proveedor = leer(db, "ia_proveedor")?
        .and_then(|v| serde_json::from_value(v).ok())
        .unwrap_or(ProveedorIa::Anthropic);
    let modelo = leer(db, "ia_modelo")?
        .and_then(|v| v.as_str().map(str::to_owned))
        .filter(|m| modelo_valido(m))
        .unwrap_or_else(|| proveedor.modelo_por_defecto().to_owned());
    Ok((proveedor, modelo))
}

/// La clave del proveedor elegido, si hay llavero y una clave en él.
#[must_use]
pub fn clave(proveedor: ProveedorIa) -> Option<String> {
    secrets::leer(&proveedor.cuenta()).ok().flatten()
}

/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn ajustes_ia(db: &BaseDeDatos) -> NsResult<AjustesIa> {
    let (proveedor, modelo) = proveedor_y_modelo(db)?;
    let llavero = secrets::disponible();
    Ok(AjustesIa {
        proveedor,
        modelo,
        tiene_clave: llavero && clave(proveedor).is_some(),
        llavero,
    })
}

/// Un nombre de modelo como los que publican los proveedores: sin espacios ni
/// nada que pueda romper el cuerpo de la petición.
fn modelo_valido(m: &str) -> bool {
    !m.is_empty()
        && m.len() <= MODELO_MAXIMO
        && m.chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.' | ':' | '/'))
}

/// Cambia el proveedor y el modelo. Un modelo vacío vuelve al de fábrica del
/// proveedor, que es lo que pide quien cambia de proveedor sin saber de modelos.
///
/// # Errors
///
/// - [`NsError::InvalidInput`] si el modelo no tiene forma de nombre de modelo.
/// - [`NsError::StorageFailure`] si no se puede guardar.
pub fn guardar_ia(db: &BaseDeDatos, proveedor: ProveedorIa, modelo: &str) -> NsResult<()> {
    let modelo = match modelo.trim() {
        "" => proveedor.modelo_por_defecto(),
        m if modelo_valido(m) => m,
        _ => return Err(NsError::InvalidInput),
    };
    let proveedor = serde_json::to_value(proveedor).map_err(|_| NsError::Internal)?;
    escribir(
        db,
        &[
            ("ia_proveedor", proveedor),
            ("ia_modelo", Value::from(modelo)),
        ],
    )
}

/// Guarda la clave del proveedor elegido en el llavero.
///
/// # Errors
///
/// Los de [`secrets::guardar`], y [`NsError::StorageFailure`] si no se puede
/// leer el proveedor.
pub fn guardar_clave_ia(db: &BaseDeDatos, clave: &str) -> NsResult<()> {
    let (proveedor, _) = proveedor_y_modelo(db)?;
    secrets::guardar(&proveedor.cuenta(), clave.trim())
}

/// Olvida la clave del proveedor elegido.
///
/// # Errors
///
/// Los de [`secrets::borrar`].
pub fn borrar_clave_ia(db: &BaseDeDatos) -> NsResult<()> {
    let (proveedor, _) = proveedor_y_modelo(db)?;
    secrets::borrar(&proveedor.cuenta())
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeSet;

    use super::*;

    #[test]
    fn cambiar_la_politica_la_guarda_y_la_aplica_a_la_puerta_en_el_acto() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let red = Red::new(PoliticaDeRed::default());
        let url = "https://lrclib.net/api/get";
        assert_eq!(
            red.autorizar(Servicio::Lrclib, url),
            Err(NsError::NetworkDisabled)
        );
        let nueva = PoliticaDeRed {
            general: true,
            servicios: BTreeSet::from([Servicio::Lrclib]),
        };
        cambiar_politica(&db, &red, nueva.clone()).unwrap();
        assert_eq!(red.autorizar(Servicio::Lrclib, url), Ok(()));
        assert_eq!(
            red.autorizar(Servicio::Shazam, "https://amp.shazam.com/x"),
            Err(NsError::ConsentRequired)
        );
        let guardada: PoliticaDeRed =
            serde_json::from_value(leer(&db, "politica_de_red").unwrap().unwrap()).unwrap();
        assert_eq!(guardada, nueva);
    }

    #[test]
    fn sin_ajustes_la_ia_es_anthropic_con_el_modelo_de_adr_009() {
        let db = BaseDeDatos::en_memoria().unwrap();
        assert_eq!(
            proveedor_y_modelo(&db).unwrap(),
            (ProveedorIa::Anthropic, "claude-haiku-5-5".to_owned())
        );
    }

    #[test]
    fn el_modelo_se_valida_y_vacio_vuelve_al_de_fabrica_del_proveedor() {
        let db = BaseDeDatos::en_memoria().unwrap();
        guardar_ia(&db, ProveedorIa::Openai, "  ").unwrap();
        assert_eq!(
            proveedor_y_modelo(&db).unwrap(),
            (ProveedorIa::Openai, "gpt-4o-mini".to_owned())
        );
        guardar_ia(&db, ProveedorIa::Anthropic, "claude-sonnet-5-5").unwrap();
        assert_eq!(proveedor_y_modelo(&db).unwrap().1, "claude-sonnet-5-5");
        assert_eq!(
            guardar_ia(&db, ProveedorIa::Anthropic, "modelo\", \"x\": \"y"),
            Err(NsError::InvalidInput)
        );
        assert_eq!(
            guardar_ia(&db, ProveedorIa::Anthropic, &"a".repeat(MODELO_MAXIMO + 1)),
            Err(NsError::InvalidInput)
        );
        assert_eq!(proveedor_y_modelo(&db).unwrap().1, "claude-sonnet-5-5");
    }

    #[test]
    fn la_clave_de_cada_proveedor_es_la_que_dejo_el_importador_de_la_v1() {
        assert_eq!(ProveedorIa::Anthropic.cuenta(), "ia@api.anthropic.com");
        assert_eq!(ProveedorIa::Openai.cuenta(), "ia@api.openai.com");
    }
}
