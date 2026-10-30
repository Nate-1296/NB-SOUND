//! El llavero del sistema para las claves de servicio (ADR-009).
//!
//! # Por qué no es la base de datos
//!
//! Una clave de servicio no es un ajuste: la base se respalda, se copia a otra
//! máquina y se lee en claro con cualquier visor de SQLite. La V1 guardaba sus
//! cuatro claves en `config_ui`, en texto plano; la V2 no tiene dónde guardarlas
//! en la base, y una prueba del importador comprueba que no aparecen en ella.
//!
//! Keychain en macOS, Credential Locker en Windows y Secret Service en el resto:
//! la librería elige según la plataforma. Portado de NB Books (`secrets.rs`).
//!
//! # Qué pasa cuando no hay llavero
//!
//! Se dice y se desactiva la función. **No hay repliegue a texto plano.** Un
//! escritorio mínimo o una sesión por SSH no tienen Secret Service, y ahí la
//! respuesta correcta es "esto no se puede usar aquí", no "se guarda peor sin
//! avisar".

use crate::error::{NsError, NsResult};
use crate::net::Servicio;

/// Servicio bajo el que se agrupan las credenciales en el llavero. Es lo que el
/// usuario verá si abre su gestor de contraseñas.
const SERVICIO: &str = "NB Sound";

/// Tope de un secreto. Una clave de API son decenas de caracteres; el límite
/// existe para que un valor absurdo se rechace aquí y no en el llavero, cuyo
/// mensaje de error no controlamos.
const MAXIMO: usize = 8 * 1024;

/// La cuenta de la clave de un servicio. Lleva el servicio dentro: la clave de
/// uno nunca se le manda a otro, porque se busca bajo otro nombre.
#[must_use]
pub fn cuenta(servicio: Servicio, proveedor: &str) -> String {
    let base = match servicio {
        Servicio::AcoustId => "acoustid",
        Servicio::TheAudioDb => "theaudiodb",
        Servicio::ProveedorIa => "ia",
        otro => return format!("{otro:?}@{}", proveedor.trim()).to_lowercase(),
    };
    format!("{base}@{}", proveedor.trim())
}

/// Si el sistema tiene un almacén de credenciales utilizable. No crea nada.
#[must_use]
pub fn disponible() -> bool {
    keyring::v1::Entry::store_status().is_ok()
}

/// Guarda un secreto bajo una cuenta, sustituyendo el que hubiera.
///
/// # Errors
///
/// - [`NsError::PathNotAllowed`] si la cuenta está vacía o el secreto fuera de
///   límites.
/// - [`NsError::ComponentUnavailable`] si el sistema no tiene llavero.
/// - [`NsError::StorageFailure`] si el llavero rechaza la escritura.
pub fn guardar(cuenta: &str, secreto: &str) -> NsResult<()> {
    let cuenta = validar(cuenta)?;
    if secreto.is_empty() || secreto.len() > MAXIMO {
        // El largo sí se registra; el contenido no, ni truncado.
        tracing::info!(
            largo = secreto.len(),
            "se rechazó un secreto fuera de límites"
        );
        return Err(NsError::PathNotAllowed);
    }
    entrada(cuenta)?.set_password(secreto).map_err(|error| {
        tracing::error!(error = %error, "el llavero no aceptó la credencial");
        NsError::StorageFailure
    })
}

/// Lee el secreto de una cuenta. `None` si no hay ninguno: es el estado de
/// fábrica de todo servicio, no un error.
///
/// # Errors
///
/// Los mismos que [`guardar`], salvo el de límites.
pub fn leer(cuenta: &str) -> NsResult<Option<String>> {
    let cuenta = validar(cuenta)?;
    match entrada(cuenta)?.get_password() {
        Ok(secreto) => Ok(Some(secreto)),
        Err(keyring::v1::Error::NoEntry) => Ok(None),
        Err(error) => {
            tracing::error!(error = %error, "el llavero no devolvió la credencial");
            Err(NsError::StorageFailure)
        }
    }
}

/// Borra el secreto de una cuenta. No falla si no había ninguno.
///
/// # Errors
///
/// Los mismos que [`leer`].
pub fn borrar(cuenta: &str) -> NsResult<()> {
    let cuenta = validar(cuenta)?;
    match entrada(cuenta)?.delete_credential() {
        Ok(()) | Err(keyring::v1::Error::NoEntry) => Ok(()),
        Err(error) => {
            tracing::error!(error = %error, "el llavero no borró la credencial");
            Err(NsError::StorageFailure)
        }
    }
}

fn validar(cuenta: &str) -> NsResult<&str> {
    let limpia = cuenta.trim();
    if limpia.is_empty() {
        tracing::info!("se pidió una credencial sin nombrar la cuenta");
        return Err(NsError::PathNotAllowed);
    }
    Ok(limpia)
}

fn entrada(cuenta: &str) -> NsResult<keyring::v1::Entry> {
    keyring::v1::Entry::new(SERVICIO, cuenta).map_err(|error| {
        tracing::info!(error = %error, "el sistema no tiene almacén de credenciales");
        NsError::ComponentUnavailable
    })
}

#[cfg(test)]
mod pruebas {
    use super::*;

    #[test]
    fn cada_proveedor_tiene_su_propia_cuenta() {
        assert_eq!(
            cuenta(Servicio::AcoustId, "api.acoustid.org"),
            "acoustid@api.acoustid.org"
        );
        assert_ne!(
            cuenta(Servicio::ProveedorIa, "api.anthropic.com"),
            cuenta(Servicio::ProveedorIa, "api.openai.com")
        );
    }

    #[test]
    fn una_cuenta_vacia_se_rechaza_antes_de_tocar_el_llavero() {
        assert_eq!(guardar("  ", "x"), Err(NsError::PathNotAllowed));
        assert_eq!(leer("").unwrap_err(), NsError::PathNotAllowed);
        assert_eq!(borrar("\t").unwrap_err(), NsError::PathNotAllowed);
    }

    #[test]
    fn un_secreto_desmesurado_se_rechaza() {
        assert_eq!(
            guardar("prueba", &"a".repeat(MAXIMO + 1)),
            Err(NsError::PathNotAllowed)
        );
        assert_eq!(guardar("prueba", ""), Err(NsError::PathNotAllowed));
    }
}
