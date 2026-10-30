//! Rutas por plataforma.
//!
//! La única ruta que decide el usuario es la carpeta de su música (ADR-007).
//! Todo lo demás vive en los directorios estándar del sistema operativo, y los
//! datos y la caché regenerable van separados: vaciar la caché nunca pierde nada.
//!
//! Los nombres de carpeta de la V2 (`nb-sound`, `NB Sound`) son distintos de los
//! de la V1 (`nb_sound`, `NBSound`) a propósito: las dos versiones conviven en la
//! misma máquina durante la transición, y la V2 nunca escribe en lo de la V1
//! (Constitución, regla 3). Dónde está lo de la V1 lo dice [`RutasV1`].
//!
//! `NB_SOUND_TEST_DIR` desvía **todas** las rutas a un directorio temporal, para
//! que las pruebas no toquen la instalación de quien las ejecuta.

use std::path::{Path, PathBuf};

use crate::error::{NsError, NsResult};

/// Variable que aísla el entorno durante las pruebas.
pub const TEST_DIR_ENV: &str = "NB_SOUND_TEST_DIR";

/// Directorios del runtime.
#[derive(Debug, Clone)]
pub struct Rutas {
    /// Base de datos, agregados y archivos pendientes de revisar. Se respalda.
    pub datos: PathBuf,
    /// Caché regenerable: portadas reducidas, formas de onda. No se respalda.
    pub cache: PathBuf,
    /// Registros de diagnóstico.
    pub registros: PathBuf,
}

impl Rutas {
    /// Resuelve los directorios y los crea si no existen.
    ///
    /// # Errors
    ///
    /// [`NsError::StorageFailure`] si el sistema no expone un directorio de datos
    /// o si no se pueden crear.
    pub fn resolver() -> NsResult<Self> {
        if let Some(base) = std::env::var_os(TEST_DIR_ENV) {
            return Self::bajo(&PathBuf::from(base));
        }
        let datos = plataforma::datos().ok_or(NsError::StorageFailure)?;
        let cache = plataforma::cache().ok_or(NsError::StorageFailure)?;
        Self {
            registros: datos.join("registros"),
            datos,
            cache,
        }
        .crear()
    }

    /// Todas las rutas bajo una sola carpeta. Lo usan las pruebas.
    ///
    /// # Errors
    ///
    /// [`NsError::StorageFailure`] si no se pueden crear.
    pub fn bajo(base: &Path) -> NsResult<Self> {
        Self {
            datos: base.join("datos"),
            cache: base.join("cache"),
            registros: base.join("registros"),
        }
        .crear()
    }

    fn crear(self) -> NsResult<Self> {
        for dir in [&self.datos, &self.cache, &self.registros] {
            std::fs::create_dir_all(dir).map_err(|_| NsError::StorageFailure)?;
        }
        Ok(self)
    }

    /// Archivo de la base de datos.
    pub fn base_de_datos(&self) -> PathBuf {
        self.datos.join("nb-sound.sqlite")
    }

    /// Agregados instalados, uno por subcarpeta. **La lista de instalados es esta
    /// carpeta**: quitar uno no puede dejar rastro en otro sitio (ADR-006).
    pub fn agregados(&self) -> PathBuf {
        self.datos.join("agregados")
    }

    /// Archivos que esperan en Por revisar. Nunca es una carpeta que el usuario
    /// tenga que gestionar (enmienda de ADR-007).
    pub fn por_revisar(&self) -> PathBuf {
        self.datos.join("por-revisar")
    }

    /// Stems de karaoke ya separados. En datos y no en caché: rehacerlos cuesta
    /// minutos de procesador por canción.
    pub fn stems(&self) -> PathBuf {
        self.datos.join("stems")
    }

    /// Portadas e imágenes de artista originales, una por contenido. En datos y
    /// no en caché: muchas vinieron de servicios que quizá ya no las den. Los
    /// tamaños reducidos sí van a la caché.
    pub fn portadas(&self) -> PathBuf {
        self.datos.join("portadas")
    }

    /// Identidad TLS del servidor móvil (ADR-005).
    pub fn identidad_movil(&self) -> PathBuf {
        self.datos.join("movil")
    }
}

/// La carpeta de música de quien no ha elegido ninguna: la del sistema
/// (`XDG_MUSIC_DIR` en Linux, `Music` en Windows y macOS).
pub fn musica_por_defecto() -> Option<PathBuf> {
    if let Some(x) = std::env::var_os("XDG_MUSIC_DIR").filter(|v| !v.is_empty()) {
        return Some(PathBuf::from(x));
    }
    let casa = PathBuf::from(std::env::var_os("HOME").or_else(|| std::env::var_os("USERPROFILE"))?);
    // En Linux, el escritorio la nombra en su idioma (`~/Música`) en user-dirs.dirs.
    let config = std::env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| casa.join(".config"));
    if let Ok(texto) = std::fs::read_to_string(config.join("user-dirs.dirs")) {
        let valor = texto
            .lines()
            .find_map(|l| l.trim().strip_prefix("XDG_MUSIC_DIR="))
            .map(|v| {
                v.trim_matches('"')
                    .replace("$HOME", &casa.to_string_lossy())
            });
        if let Some(v) = valor.filter(|v| !v.is_empty()) {
            return Some(PathBuf::from(v));
        }
    }
    Some(casa.join("Music"))
}

/// Dónde guardaba sus cosas la V1, para el importador (ADR-004). Solo se leen.
#[derive(Debug, Clone)]
pub struct RutasV1 {
    pub datos: PathBuf,
    pub config: PathBuf,
}

impl RutasV1 {
    /// Las rutas estándar de la V1 en esta plataforma (`legado/infra/bootstrap.py`).
    pub fn estandar() -> Option<Self> {
        plataforma::v1()
    }

    /// La base de la V1 cuando la carpeta de biblioteca no se cambió en su `.env`.
    pub fn base_de_datos(&self) -> PathBuf {
        self.datos.join("biblioteca").join("nb_sound.sqlite3")
    }

    /// El certificado y la clave del servidor móvil de la V1.
    pub fn identidad_movil(&self) -> PathBuf {
        self.config.join("sync")
    }
}

// Resolución sin dependencias externas: son pocas llamadas por plataforma, como
// en NB Books (`paths.rs`).
#[cfg(target_os = "linux")]
mod plataforma {
    use std::path::PathBuf;

    use super::RutasV1;

    fn xdg(var: &str, respaldo: &str) -> Option<PathBuf> {
        match std::env::var_os(var) {
            Some(v) if !v.is_empty() => Some(PathBuf::from(v)),
            _ => Some(PathBuf::from(std::env::var_os("HOME")?).join(respaldo)),
        }
    }

    pub fn datos() -> Option<PathBuf> {
        Some(xdg("XDG_DATA_HOME", ".local/share")?.join("nb-sound"))
    }

    pub fn cache() -> Option<PathBuf> {
        Some(xdg("XDG_CACHE_HOME", ".cache")?.join("nb-sound"))
    }

    pub fn v1() -> Option<RutasV1> {
        Some(RutasV1 {
            datos: xdg("XDG_DATA_HOME", ".local/share")?.join("nb_sound"),
            config: xdg("XDG_CONFIG_HOME", ".config")?.join("nb_sound"),
        })
    }
}

#[cfg(target_os = "windows")]
mod plataforma {
    use std::path::PathBuf;

    use super::RutasV1;

    fn var(nombre: &str) -> Option<PathBuf> {
        std::env::var_os(nombre).map(PathBuf::from)
    }

    pub fn datos() -> Option<PathBuf> {
        Some(var("APPDATA")?.join("NB Sound"))
    }

    pub fn cache() -> Option<PathBuf> {
        Some(var("LOCALAPPDATA")?.join("NB Sound").join("Cache"))
    }

    pub fn v1() -> Option<RutasV1> {
        Some(RutasV1 {
            datos: var("LOCALAPPDATA")?.join("NBSound"),
            config: var("APPDATA")?.join("NBSound"),
        })
    }
}

#[cfg(target_os = "macos")]
mod plataforma {
    use std::path::PathBuf;

    use super::RutasV1;

    fn home() -> Option<PathBuf> {
        std::env::var_os("HOME").map(PathBuf::from)
    }

    pub fn datos() -> Option<PathBuf> {
        Some(home()?.join("Library/Application Support/NB Sound"))
    }

    pub fn cache() -> Option<PathBuf> {
        Some(home()?.join("Library/Caches/NB Sound"))
    }

    pub fn v1() -> Option<RutasV1> {
        Some(RutasV1 {
            datos: home()?.join("Library/Application Support/NBSound"),
            config: home()?.join("Library/Preferences/NBSound"),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn todas_las_rutas_quedan_bajo_la_base_de_pruebas() {
        let base = std::env::temp_dir().join(format!("ns-rutas-{}", std::process::id()));
        let rutas = Rutas::bajo(&base).expect("se crean");
        for ruta in [
            rutas.base_de_datos(),
            rutas.agregados(),
            rutas.por_revisar(),
            rutas.stems(),
            rutas.identidad_movil(),
            rutas.cache.clone(),
            rutas.registros.clone(),
        ] {
            assert!(
                ruta.starts_with(&base),
                "{} escapa de la base",
                ruta.display()
            );
        }
        let _ = std::fs::remove_dir_all(base);
    }

    /// La V2 y la V1 conviven: si compartieran carpeta, la V2 escribiría donde la
    /// V1 guarda su base, que es justo lo que la Constitución prohíbe.
    #[test]
    fn la_v2_no_comparte_carpetas_con_la_v1() {
        let (Some(datos), Some(v1)) = (plataforma::datos(), RutasV1::estandar()) else {
            return;
        };
        assert_ne!(datos, v1.datos);
        assert!(!datos.starts_with(&v1.datos));
        assert!(!v1.base_de_datos().starts_with(&datos));
    }
}
