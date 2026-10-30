//! Las claves de servicio de la V1, al llavero (F1.2.4).
//!
//! La V1 las tenía en dos sitios: en `config_ui`, en texto plano, si el usuario
//! las pegó en Configuración, y en su `.env` si las escribió a mano. La de
//! `config_ui` gana, porque es la que la V1 usaba (`config/settings.py`,
//! `_leer_clave_api`). Ninguna pasa por la base de la V2 ni por el registro.

use std::collections::HashMap;
use std::path::Path;

use crate::error::NsResult;
use crate::net::Servicio;
use crate::secrets;

/// Dónde se guardan. En producción, el llavero del sistema; en las pruebas, uno
/// en memoria, para no escribir en el de quien las ejecuta.
pub trait Llavero {
    /// # Errors
    ///
    /// Los de [`secrets::guardar`].
    fn guardar(&self, cuenta: &str, secreto: &str) -> NsResult<()>;
}

/// El llavero del sistema.
pub struct LlaveroDelSistema;

impl Llavero for LlaveroDelSistema {
    fn guardar(&self, cuenta: &str, secreto: &str) -> NsResult<()> {
        secrets::guardar(cuenta, secreto)
    }
}

/// Clave de `config_ui`, variable del `.env` y cuenta de la V2.
const CLAVES: [(&str, &str, Servicio, &str); 4] = [
    (
        "acoustid_key",
        "ACOUSTID_API_KEY",
        Servicio::AcoustId,
        "api.acoustid.org",
    ),
    (
        "anthropic_key",
        "ANTHROPIC_API_KEY",
        Servicio::ProveedorIa,
        "api.anthropic.com",
    ),
    (
        "openai_key",
        "OPENAI_API_KEY",
        Servicio::ProveedorIa,
        "api.openai.com",
    ),
    (
        "theaudiodb_api_key",
        "THEAUDIODB_API_KEY",
        Servicio::TheAudioDb,
        "www.theaudiodb.com",
    ),
];

/// La clave pública de pruebas de TheAudioDB, que la V1 traía de fábrica. No es
/// del usuario y no se guarda.
const CLAVE_PUBLICA_DE_THEAUDIODB: &str = "123";

/// Las variables de un `.env`: `CLAVE=valor`, con o sin comillas. Lo que no
/// tiene esa forma se ignora, como hacía `python-dotenv`.
fn leer_env(ruta: &Path) -> HashMap<String, String> {
    let Ok(texto) = std::fs::read_to_string(ruta) else {
        return HashMap::new();
    };
    texto
        .lines()
        .filter_map(|linea| {
            let linea = linea.trim();
            if linea.starts_with('#') {
                return None;
            }
            let (clave, valor) = linea
                .strip_prefix("export ")
                .unwrap_or(linea)
                .split_once('=')?;
            let valor = valor.trim();
            let valor = valor
                .strip_prefix('"')
                .and_then(|v| v.strip_suffix('"'))
                .or_else(|| valor.strip_prefix('\'').and_then(|v| v.strip_suffix('\'')))
                .unwrap_or(valor);
            Some((clave.trim().to_owned(), valor.to_owned()))
        })
        .collect()
}

/// Cuántas claves se movieron y cuántas no se pudieron guardar.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct Resultado {
    pub migradas: u32,
    pub no_migradas: u32,
}

/// Mueve las claves al llavero. `config` son las claves de `config_ui` que
/// terminan en `_key`; `env`, el `.env` de la V1 si lo hay. Si el sistema no
/// tiene llavero, no se guardan en ningún otro sitio: se cuentan como no
/// migradas y el usuario lo ve en el informe.
pub fn migrar(
    config: &HashMap<String, String>,
    env: Option<&Path>,
    llavero: &dyn Llavero,
) -> Resultado {
    let env = env.map(leer_env).unwrap_or_default();
    let mut r = Resultado::default();
    for (en_config, en_env, servicio, proveedor) in CLAVES {
        let valor = config
            .get(en_config)
            .or_else(|| env.get(en_env))
            .map(|v| v.trim())
            .filter(|v| !v.is_empty() && *v != CLAVE_PUBLICA_DE_THEAUDIODB);
        let Some(valor) = valor else {
            continue;
        };
        match llavero.guardar(&secrets::cuenta(servicio, proveedor), valor) {
            Ok(()) => r.migradas += 1,
            Err(error) => {
                tracing::warn!(
                    codigo = error.code(),
                    "una clave de la V1 no se pudo guardar en el llavero"
                );
                r.no_migradas += 1;
            }
        }
    }
    r
}

#[cfg(test)]
pub mod pruebas {
    use std::cell::RefCell;

    use super::*;
    use crate::error::NsError;

    /// Un llavero en memoria.
    #[derive(Default)]
    pub struct LlaveroDePrueba {
        pub guardado: RefCell<HashMap<String, String>>,
        pub roto: bool,
    }

    impl Llavero for LlaveroDePrueba {
        fn guardar(&self, cuenta: &str, secreto: &str) -> NsResult<()> {
            if self.roto {
                return Err(NsError::ComponentUnavailable);
            }
            self.guardado
                .borrow_mut()
                .insert(cuenta.to_owned(), secreto.to_owned());
            Ok(())
        }
    }

    #[test]
    fn la_clave_de_configuracion_gana_a_la_del_env() {
        let dir = std::env::temp_dir().join(format!("ns-claves-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let env = dir.join(".env");
        std::fs::write(
            &env,
            "# comentario\nACOUSTID_API_KEY=\"de-env\"\nOPENAI_API_KEY='sk-env'\nTHEAUDIODB_API_KEY=123\nUSER_LIBRARY_DIR=/m\n",
        )
        .unwrap();
        let config = HashMap::from([("acoustid_key".to_owned(), "de-config".to_owned())]);
        let llavero = LlaveroDePrueba::default();
        assert_eq!(
            migrar(&config, Some(&env), &llavero),
            Resultado {
                migradas: 2,
                no_migradas: 0
            }
        );
        let guardado = llavero.guardado.borrow();
        assert_eq!(guardado["acoustid@api.acoustid.org"], "de-config");
        assert_eq!(guardado["ia@api.openai.com"], "sk-env");
        assert!(
            !guardado.keys().any(|k| k.starts_with("theaudiodb")),
            "la pública no se guarda"
        );
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn sin_llavero_las_claves_no_van_a_ninguna_parte() {
        let config = HashMap::from([("openai_key".to_owned(), "sk".to_owned())]);
        let llavero = LlaveroDePrueba {
            roto: true,
            ..Default::default()
        };
        assert_eq!(
            migrar(&config, None, &llavero),
            Resultado {
                migradas: 0,
                no_migradas: 1
            }
        );
    }
}
