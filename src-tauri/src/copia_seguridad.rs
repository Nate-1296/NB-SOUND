//! Copia de seguridad y restauración (F4.2.6): `servicios/backup.py` de la V1.
//!
//! El formato es el de la V1: un ZIP `.nbsound-backup` con la base
//! (`db.sqlite3`, sacada con `VACUUM INTO`, que da una copia coherente sin
//! bloquear ni arrastrar el WAL), las portadas (`assets/`) y un `manifest.json`
//! con la suma sha256 de cada entrada. Ni el audio, que es del usuario y no de la
//! aplicación, ni las claves, que viven en el llavero (ADR-009), ni la identidad
//! del servidor móvil. El manifiesto añade `esquema`, la versión de la base de la
//! V2: así una copia de la V1, que no lo lleva, se reconoce y se rechaza con su
//! motivo (P12 sigue abierta).
//!
//! **Restaurar no reemplaza la base en caliente.** Con el pool de conexiones, el
//! reproductor y el servidor móvil leyendo, cambiar el archivo por debajo es
//! pedir una base a medias. La copia se valida entera (sumas, `integrity_check`,
//! la tabla `pistas` y que su esquema no sea más nuevo que esta versión), se
//! deja preparada junto a la base y se aplica en el siguiente arranque, antes de
//! abrirla ([`aplicar_restauracion_pendiente`]).

use std::fs::File;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use rusqlite::OptionalExtension;
use serde::Serialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use ts_rs::TS;
use zip::write::SimpleFileOptions;
use zip::{CompressionMethod, ZipArchive, ZipWriter};

use crate::db::{self, migraciones, BaseDeDatos};
use crate::error::{NsError, NsResult};
use crate::paths::Rutas;

const FORMATO: &str = "nbsound-backup";
pub const EXTENSION: &str = "nbsound-backup";
const DB_EN_ZIP: &str = "db.sqlite3";
const MANIFIESTO: &str = "manifest.json";
const PREFIJO_PORTADAS: &str = "assets/";

/// Tope de lo que se descomprime de una entrada: una copia manipulada no puede
/// llenar el disco con una bomba de compresión.
const TOPE_ENTRADA: u64 = 8 * 1024 * 1024 * 1024;

/// Lo que se cuenta al terminar una copia.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct ResumenCopia {
    // Por JSON viaja como número; una copia no se acerca a 2^53 bytes.
    #[ts(type = "number")]
    pub bytes: u64,
    pub portadas: u32,
}

/// Lo que muestra Ajustes. La carpeta solo se dice por su nombre: la ruta entera
/// no cruza el puente.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct EstadoCopia {
    /// 0: sin copias automáticas.
    pub cada_dias: u32,
    pub carpeta: Option<String>,
    /// Cuándo se hizo la última, en ISO 8601 UTC.
    pub ultima: Option<String>,
    /// Hay una restauración preparada que se aplicará al reiniciar.
    pub restauracion_pendiente: bool,
}

fn hex(d: &[u8]) -> String {
    d.iter().fold(String::with_capacity(64), |mut s, b| {
        use std::fmt::Write as _;
        let _ = write!(s, "{b:02x}");
        s
    })
}

fn sha256_de(ruta: &Path) -> NsResult<String> {
    let mut f = File::open(ruta).map_err(|_| NsError::StorageFailure)?;
    let mut h = Sha256::new();
    let mut buf = vec![0u8; 1 << 20];
    loop {
        let n = f.read(&mut buf).map_err(|_| NsError::StorageFailure)?;
        if n == 0 {
            break;
        }
        h.update(&buf[..n]);
    }
    Ok(hex(&h.finalize()))
}

fn preferencia(db: &BaseDeDatos, clave: &str) -> NsResult<Option<Value>> {
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

fn guardar_preferencia(db: &BaseDeDatos, clave: &str, valor: &Value) -> NsResult<()> {
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

fn ahora_iso(db: &BaseDeDatos) -> NsResult<String> {
    db.conexion()?
        .query_row("SELECT strftime('%Y-%m-%dT%H:%M:%SZ', 'now')", [], |f| {
            f.get(0)
        })
        .map_err(|_| NsError::StorageFailure)
}

// --- Crear -------------------------------------------------------------------------

/// Crea una copia en `destino` (se le añade la extensión si no la lleva). Se
/// escribe en un `.tmp` y se renombra al terminar: un corte a medias no deja una
/// copia que parezca buena.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede leer la base o escribir la copia.
pub fn crear(db: &BaseDeDatos, rutas: &Rutas, destino: &Path) -> NsResult<ResumenCopia> {
    let destino = con_extension(destino);
    let temporal_db = rutas
        .cache
        .join(format!("copia-{}.sqlite", std::process::id()));
    let _ = std::fs::remove_file(&temporal_db);
    db.conexion()?
        .execute("VACUUM INTO ?1", [temporal_db.to_string_lossy()])
        .map_err(|error| {
            tracing::error!(error = %error, "no se pudo sacar la copia de la base");
            NsError::StorageFailure
        })?;
    let zip_tmp = destino.with_extension(format!("{EXTENSION}.tmp"));
    let resultado = escribir_zip(db, rutas, &temporal_db, &zip_tmp).and_then(|n| {
        std::fs::rename(&zip_tmp, &destino)
            .map(|()| n)
            .map_err(|_| NsError::StorageFailure)
    });
    let _ = std::fs::remove_file(&temporal_db);
    let portadas = match resultado {
        Ok(n) => n,
        Err(error) => {
            let _ = std::fs::remove_file(&zip_tmp);
            return Err(error);
        }
    };
    let bytes = std::fs::metadata(&destino).map(|m| m.len()).unwrap_or(0);
    guardar_preferencia(db, "copia_ultima", &Value::from(ahora_iso(db)?))?;
    tracing::info!(bytes, portadas, "copia de seguridad creada");
    Ok(ResumenCopia { bytes, portadas })
}

fn con_extension(destino: &Path) -> PathBuf {
    if destino.extension().and_then(|e| e.to_str()) == Some(EXTENSION) {
        destino.to_path_buf()
    } else {
        let mut nombre = destino.as_os_str().to_owned();
        nombre.push(".");
        nombre.push(EXTENSION);
        PathBuf::from(nombre)
    }
}

fn escribir_zip(db: &BaseDeDatos, rutas: &Rutas, base: &Path, zip_tmp: &Path) -> NsResult<u32> {
    let f = File::create(zip_tmp).map_err(|_| NsError::StorageFailure)?;
    let mut z = ZipWriter::new(f);
    let opciones = SimpleFileOptions::default()
        .compression_method(CompressionMethod::Deflated)
        .large_file(true);
    let mut sumas = serde_json::Map::new();
    let mut anadir = |z: &mut ZipWriter<File>, nombre: &str, origen: &Path| -> NsResult<()> {
        z.start_file(nombre, opciones)
            .map_err(|_| NsError::StorageFailure)?;
        let mut f = File::open(origen).map_err(|_| NsError::StorageFailure)?;
        std::io::copy(&mut f, z).map_err(|_| NsError::StorageFailure)?;
        sumas.insert(nombre.to_owned(), Value::from(sha256_de(origen)?));
        Ok(())
    };
    anadir(&mut z, DB_EN_ZIP, base)?;
    let dir = rutas.portadas();
    let mut portadas = Vec::new();
    if dir.is_dir() {
        let mut pila = vec![dir.clone()];
        while let Some(d) = pila.pop() {
            for e in std::fs::read_dir(&d)
                .map_err(|_| NsError::StorageFailure)?
                .flatten()
            {
                let p = e.path();
                if p.is_dir() {
                    pila.push(p);
                } else if p.is_file() {
                    portadas.push(p);
                }
            }
        }
    }
    portadas.sort();
    for p in &portadas {
        let relativa = p
            .strip_prefix(&dir)
            .map_err(|_| NsError::Internal)?
            .to_string_lossy()
            .replace('\\', "/");
        anadir(&mut z, &format!("{PREFIJO_PORTADAS}{relativa}"), p)?;
    }
    let total = u32::try_from(portadas.len()).unwrap_or(u32::MAX);
    let mut contenido = vec!["db"];
    if total > 0 {
        contenido.push("assets");
    }
    let manifiesto = json!({
        "formato": FORMATO,
        "version_app": env!("CARGO_PKG_VERSION"),
        "esquema": migraciones::version_esperada(),
        "creado_en": ahora_iso(db)?,
        "contenido": contenido,
        "total_assets": total,
        "checksums": sumas,
    });
    z.start_file(MANIFIESTO, opciones)
        .map_err(|_| NsError::StorageFailure)?;
    z.write_all(
        serde_json::to_string_pretty(&manifiesto)
            .map_err(|_| NsError::Internal)?
            .as_bytes(),
    )
    .map_err(|_| NsError::StorageFailure)?;
    let f = z.finish().map_err(|_| NsError::StorageFailure)?;
    f.sync_all().map_err(|_| NsError::StorageFailure)?;
    Ok(total)
}

// --- Validar y restaurar -----------------------------------------------------------

/// Por qué una copia no se puede restaurar. Va a la interfaz como código.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CopiaInvalida {
    /// No es un ZIP o le falta la base o el manifiesto.
    Formato,
    /// Es una copia de la V1 (P12).
    DeLaV1,
    /// De una versión de NB Sound más nueva que esta.
    MasNueva,
    /// Alguna suma no coincide o la base no pasa `integrity_check`.
    Danada,
}

impl From<CopiaInvalida> for NsError {
    fn from(c: CopiaInvalida) -> Self {
        match c {
            CopiaInvalida::Formato | CopiaInvalida::DeLaV1 => NsError::FormatUnsupported,
            CopiaInvalida::MasNueva => NsError::SchemaMismatch,
            CopiaInvalida::Danada => NsError::IntegrityMismatch,
        }
    }
}

fn manifiesto(z: &mut ZipArchive<File>) -> Result<Value, CopiaInvalida> {
    let mut texto = String::new();
    z.by_name(MANIFIESTO)
        .map_err(|_| CopiaInvalida::Formato)?
        .take(1024 * 1024)
        .read_to_string(&mut texto)
        .map_err(|_| CopiaInvalida::Formato)?;
    let m: Value = serde_json::from_str(&texto).map_err(|_| CopiaInvalida::Formato)?;
    if m["formato"] != FORMATO {
        return Err(CopiaInvalida::Formato);
    }
    match m["esquema"].as_u64() {
        None => Err(CopiaInvalida::DeLaV1),
        Some(e) if e > u64::from(migraciones::version_esperada()) => Err(CopiaInvalida::MasNueva),
        Some(_) => Ok(m),
    }
}

/// Extrae una entrada a `salida` comprobando su suma por el camino.
fn extraer(
    z: &mut ZipArchive<File>,
    nombre: &str,
    esperada: &str,
    salida: &Path,
) -> Result<(), CopiaInvalida> {
    let mut entrada = z.by_name(nombre).map_err(|_| CopiaInvalida::Danada)?;
    if let Some(dir) = salida.parent() {
        std::fs::create_dir_all(dir).map_err(|_| CopiaInvalida::Danada)?;
    }
    let mut f = File::create(salida).map_err(|_| CopiaInvalida::Danada)?;
    let mut h = Sha256::new();
    let mut buf = vec![0u8; 1 << 20];
    let mut total = 0u64;
    loop {
        let n = entrada.read(&mut buf).map_err(|_| CopiaInvalida::Danada)?;
        if n == 0 {
            break;
        }
        total += n as u64;
        if total > TOPE_ENTRADA {
            return Err(CopiaInvalida::Danada);
        }
        h.update(&buf[..n]);
        f.write_all(&buf[..n]).map_err(|_| CopiaInvalida::Danada)?;
    }
    if hex(&h.finalize()) != esperada {
        return Err(CopiaInvalida::Danada);
    }
    Ok(())
}

fn base_integra(ruta: &Path) -> bool {
    let Ok(conn) =
        rusqlite::Connection::open_with_flags(ruta, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY)
    else {
        return false;
    };
    let integra = conn
        .query_row("PRAGMA integrity_check", [], |f| f.get::<_, String>(0))
        .is_ok_and(|e| e.eq_ignore_ascii_case("ok"));
    let con_pistas = conn
        .query_row(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'pistas'",
            [],
            |_| Ok(()),
        )
        .is_ok();
    integra && con_pistas
}

/// Dónde se deja preparada la restauración: junto a la base, para que el
/// cambio final sea un `rename` en el mismo disco.
fn preparada(rutas: &Rutas) -> (PathBuf, PathBuf) {
    (
        rutas.datos.join("restaurar.sqlite"),
        rutas.datos.join("restaurar-portadas"),
    )
}

/// Valida una copia entera y la deja preparada para el próximo arranque. No toca
/// la base en uso.
///
/// # Errors
///
/// - [`NsError::FormatUnsupported`] si no es una copia de la V2.
/// - [`NsError::SchemaMismatch`] si es de una versión más nueva.
/// - [`NsError::IntegrityMismatch`] si está dañada.
pub fn preparar_restauracion(rutas: &Rutas, copia: &Path) -> NsResult<()> {
    let (base, portadas) = preparada(rutas);
    let _ = std::fs::remove_file(&base);
    let _ = std::fs::remove_dir_all(&portadas);
    let resultado = (|| -> Result<(), CopiaInvalida> {
        let f = File::open(copia).map_err(|_| CopiaInvalida::Formato)?;
        let mut z = ZipArchive::new(f).map_err(|_| CopiaInvalida::Formato)?;
        let m = manifiesto(&mut z)?;
        let sumas = m["checksums"].as_object().ok_or(CopiaInvalida::Formato)?;
        let suma_db = sumas
            .get(DB_EN_ZIP)
            .and_then(Value::as_str)
            .ok_or(CopiaInvalida::Formato)?;
        extraer(&mut z, DB_EN_ZIP, suma_db, &base)?;
        if !base_integra(&base) {
            return Err(CopiaInvalida::Danada);
        }
        for (nombre, suma) in sumas {
            if !nombre.starts_with(PREFIJO_PORTADAS) {
                continue;
            }
            // Se extrae a la ruta saneada, nunca al nombre tal cual: una entrada
            // con `..` o absoluta no sale de la carpeta de portadas.
            let relativa = z
                .by_name(nombre)
                .ok()
                .and_then(|e| e.enclosed_name())
                .and_then(|p| {
                    p.strip_prefix(PREFIJO_PORTADAS.trim_end_matches('/'))
                        .ok()
                        .map(Path::to_path_buf)
                })
                .filter(|p| !p.as_os_str().is_empty())
                .ok_or(CopiaInvalida::Danada)?;
            let suma = suma.as_str().ok_or(CopiaInvalida::Danada)?;
            extraer(&mut z, nombre, suma, &portadas.join(relativa))?;
        }
        Ok(())
    })();
    if let Err(c) = resultado {
        let _ = std::fs::remove_file(&base);
        let _ = std::fs::remove_dir_all(&portadas);
        tracing::warn!(?c, "se rechazó una copia de seguridad");
        return Err(c.into());
    }
    Ok(())
}

/// Si hay una restauración preparada. La interfaz la usa para ofrecer reiniciar.
#[must_use]
pub fn restauracion_pendiente(rutas: &Rutas) -> bool {
    preparada(rutas).0.is_file()
}

/// Aplica la restauración preparada, si la hay. Se llama al arrancar, **antes**
/// de abrir la base. La base y las portadas de antes se apartan con el sufijo
/// `.antes`, sustituyendo las de una restauración anterior: una sola vuelta
/// atrás posible, sin acumular copias.
pub fn aplicar_restauracion_pendiente(rutas: &Rutas) {
    let (base, portadas) = preparada(rutas);
    if !base.is_file() {
        return;
    }
    let actual = rutas.base_de_datos();
    let antes = actual.with_extension("sqlite.antes");
    let _ = std::fs::remove_file(&antes);
    if actual.is_file() && std::fs::rename(&actual, &antes).is_err() {
        tracing::error!("no se pudo apartar la base para restaurar la copia");
        return;
    }
    for extra in ["-wal", "-shm"] {
        let mut colateral = actual.as_os_str().to_owned();
        colateral.push(extra);
        let _ = std::fs::remove_file(PathBuf::from(colateral));
    }
    if std::fs::rename(&base, &actual).is_err() {
        tracing::error!("no se pudo poner la base restaurada; se vuelve a la de antes");
        let _ = std::fs::rename(&antes, &actual);
        return;
    }
    if portadas.is_dir() {
        let dir = rutas.portadas();
        let apartadas = rutas.datos.join("portadas.antes");
        let _ = std::fs::remove_dir_all(&apartadas);
        let _ = std::fs::rename(&dir, &apartadas);
        if std::fs::rename(&portadas, &dir).is_err() {
            tracing::error!("no se pudieron poner las portadas restauradas");
        }
    }
    tracing::info!("copia de seguridad restaurada");
}

// --- Copias automáticas ------------------------------------------------------------

/// `backup_programado_vencido`: con frecuencia 0 no hay copias automáticas; sin
/// ninguna anterior, toca; si no, toca cuando pasaron los días.
#[must_use]
pub fn vencida(cada_dias: u32, segundos_desde_la_ultima: Option<i64>) -> bool {
    if cada_dias == 0 {
        return false;
    }
    segundos_desde_la_ultima.is_none_or(|s| s >= i64::from(cada_dias) * 86_400)
}

fn segundos_desde(db: &BaseDeDatos, iso: &str) -> Option<i64> {
    db.conexion()
        .ok()?
        .query_row(
            "SELECT CAST(strftime('%s', 'now') AS INTEGER) - CAST(strftime('%s', ?1) AS INTEGER)",
            [iso],
            |f| f.get::<_, Option<i64>>(0),
        )
        .ok()
        .flatten()
}

/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn estado(db: &BaseDeDatos, rutas: &Rutas) -> NsResult<EstadoCopia> {
    let cada_dias = preferencia(db, "copia_cada_dias")?
        .and_then(|v| v.as_u64())
        .and_then(|d| u32::try_from(d).ok())
        .unwrap_or(0);
    let carpeta = preferencia(db, "copia_carpeta")?
        .and_then(|v| v.as_str().map(PathBuf::from))
        .and_then(|p| p.file_name().map(|n| n.to_string_lossy().into_owned()));
    let ultima = preferencia(db, "copia_ultima")?.and_then(|v| v.as_str().map(str::to_owned));
    Ok(EstadoCopia {
        cada_dias,
        carpeta,
        ultima,
        restauracion_pendiente: restauracion_pendiente(rutas),
    })
}

/// Las frecuencias que ofrece Ajustes, como la V1: nunca, a diario, cada semana
/// y cada mes.
pub const FRECUENCIAS: [u32; 4] = [0, 1, 7, 30];

/// # Errors
///
/// - [`NsError::InvalidInput`] si la frecuencia no es una de las de Ajustes.
/// - [`NsError::StorageFailure`] si no se puede guardar.
pub fn fijar_frecuencia(db: &BaseDeDatos, cada_dias: u32) -> NsResult<()> {
    if !FRECUENCIAS.contains(&cada_dias) {
        return Err(NsError::InvalidInput);
    }
    guardar_preferencia(db, "copia_cada_dias", &Value::from(cada_dias))
}

/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede guardar.
pub fn fijar_carpeta(db: &BaseDeDatos, carpeta: &Path) -> NsResult<()> {
    guardar_preferencia(
        db,
        "copia_carpeta",
        &Value::from(carpeta.to_string_lossy().into_owned()),
    )
}

/// Hace la copia automática si toca. Se llama al arrancar, en su propio hilo.
pub fn automatica_si_toca(db: &BaseDeDatos, rutas: &Rutas) {
    let Ok(e) = estado(db, rutas) else { return };
    let desde = e.ultima.as_deref().and_then(|u| segundos_desde(db, u));
    if !vencida(e.cada_dias, desde) {
        return;
    }
    let Some(carpeta) = preferencia(db, "copia_carpeta")
        .ok()
        .flatten()
        .and_then(|v| v.as_str().map(PathBuf::from))
        .filter(|c| c.is_dir())
    else {
        return;
    };
    let fecha: String = db
        .conexion()
        .ok()
        .and_then(|c| {
            c.query_row("SELECT date('now', 'localtime')", [], |f| f.get(0))
                .ok()
        })
        .unwrap_or_else(|| "copia".to_owned());
    if let Err(error) = crear(db, rutas, &carpeta.join(format!("nb-sound-{fecha}"))) {
        tracing::error!(
            codigo = error.code(),
            "falló la copia de seguridad automática"
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn montaje(nombre: &str) -> (PathBuf, Rutas, BaseDeDatos) {
        let dir = std::env::temp_dir().join(format!("ns-copia-{nombre}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let rutas = Rutas::bajo(&dir).unwrap();
        let db = BaseDeDatos::abrir(&rutas.base_de_datos()).unwrap();
        db.conexion()
            .unwrap()
            .execute(
                "INSERT INTO pistas (titulo, ruta) VALUES ('original', 'a.mp3')",
                [],
            )
            .unwrap();
        std::fs::create_dir_all(rutas.portadas().join("ab")).unwrap();
        std::fs::write(rutas.portadas().join("ab/portada.jpg"), b"jpg").unwrap();
        (dir, rutas, db)
    }

    #[test]
    fn una_copia_restaurada_devuelve_la_base_y_las_portadas_al_arrancar() {
        let (dir, rutas, db) = montaje("vuelta");
        let destino = dir.join("mi-copia");
        let r = crear(&db, &rutas, &destino).unwrap();
        assert_eq!(r.portadas, 1);
        let copia = dir.join("mi-copia.nbsound-backup");
        assert!(copia.is_file());

        // Después de la copia, la biblioteca cambia.
        db.conexion()
            .unwrap()
            .execute("UPDATE pistas SET titulo = 'cambiado'", [])
            .unwrap();
        std::fs::remove_file(rutas.portadas().join("ab/portada.jpg")).unwrap();
        drop(db);

        preparar_restauracion(&rutas, &copia).unwrap();
        assert!(restauracion_pendiente(&rutas));
        aplicar_restauracion_pendiente(&rutas);
        assert!(!restauracion_pendiente(&rutas));

        let db = BaseDeDatos::abrir(&rutas.base_de_datos()).unwrap();
        let titulo: String = db
            .conexion()
            .unwrap()
            .query_row("SELECT titulo FROM pistas", [], |f| f.get(0))
            .unwrap();
        assert_eq!(titulo, "original");
        assert_eq!(
            std::fs::read(rutas.portadas().join("ab/portada.jpg")).unwrap(),
            b"jpg"
        );
        assert!(rutas
            .base_de_datos()
            .with_extension("sqlite.antes")
            .is_file());
        let _ = std::fs::remove_dir_all(&dir);
    }

    fn reescribir_manifiesto(origen: &Path, destino: &Path, cambio: impl Fn(&mut Value)) {
        let mut z = ZipArchive::new(File::open(origen).unwrap()).unwrap();
        let mut w = ZipWriter::new(File::create(destino).unwrap());
        for i in 0..z.len() {
            let mut e = z.by_index(i).unwrap();
            let nombre = e.name().unwrap().into_owned();
            let mut datos = Vec::new();
            e.read_to_end(&mut datos).unwrap();
            if nombre == MANIFIESTO {
                let mut m: Value = serde_json::from_slice(&datos).unwrap();
                cambio(&mut m);
                datos = serde_json::to_vec(&m).unwrap();
            }
            w.start_file(nombre, SimpleFileOptions::default()).unwrap();
            w.write_all(&datos).unwrap();
        }
        w.finish().unwrap();
    }

    #[test]
    fn una_copia_de_la_v1_mas_nueva_o_danada_se_rechaza_sin_preparar_nada() {
        let (dir, rutas, db) = montaje("rechazos");
        crear(&db, &rutas, &dir.join("buena")).unwrap();
        let buena = dir.join("buena.nbsound-backup");
        type Cambio = Box<dyn Fn(&mut Value)>;
        let casos: [(&str, Cambio, NsError); 3] = [
            (
                "v1",
                Box::new(|m| {
                    m.as_object_mut().unwrap().remove("esquema");
                }),
                NsError::FormatUnsupported,
            ),
            (
                "nueva",
                Box::new(|m| m["esquema"] = Value::from(9_999)),
                NsError::SchemaMismatch,
            ),
            (
                "danada",
                Box::new(|m| m["checksums"][DB_EN_ZIP] = Value::from("0".repeat(64))),
                NsError::IntegrityMismatch,
            ),
        ];
        for (nombre, cambio, error) in casos {
            let mala = dir.join(format!("{nombre}.nbsound-backup"));
            reescribir_manifiesto(&buena, &mala, cambio);
            assert_eq!(preparar_restauracion(&rutas, &mala), Err(error), "{nombre}");
            assert!(!restauracion_pendiente(&rutas), "{nombre}");
        }
        std::fs::write(dir.join("no-zip.nbsound-backup"), b"hola").unwrap();
        assert_eq!(
            preparar_restauracion(&rutas, &dir.join("no-zip.nbsound-backup")),
            Err(NsError::FormatUnsupported)
        );
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn una_portada_con_ruta_trampa_no_sale_de_su_carpeta() {
        let (dir, rutas, db) = montaje("trampa");
        crear(&db, &rutas, &dir.join("buena")).unwrap();
        let buena = dir.join("buena.nbsound-backup");
        let mala = dir.join("trampa.nbsound-backup");
        let suma = hex(&Sha256::digest(b"x"));
        let mut z = ZipArchive::new(File::open(&buena).unwrap()).unwrap();
        let mut w = ZipWriter::new(File::create(&mala).unwrap());
        for i in 0..z.len() {
            let mut e = z.by_index(i).unwrap();
            let nombre = e.name().unwrap().into_owned();
            let mut datos = Vec::new();
            e.read_to_end(&mut datos).unwrap();
            if nombre == MANIFIESTO {
                let mut m: Value = serde_json::from_slice(&datos).unwrap();
                m["checksums"]["assets/../../fuera.txt"] = Value::from(suma.clone());
                datos = serde_json::to_vec(&m).unwrap();
            }
            w.start_file(nombre, SimpleFileOptions::default()).unwrap();
            w.write_all(&datos).unwrap();
        }
        w.start_file("assets/../../fuera.txt", SimpleFileOptions::default())
            .unwrap();
        w.write_all(b"x").unwrap();
        w.finish().unwrap();
        assert_eq!(
            preparar_restauracion(&rutas, &mala),
            Err(NsError::IntegrityMismatch)
        );
        assert!(!rutas.datos.join("fuera.txt").exists());
        assert!(!dir.join("fuera.txt").exists());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn la_copia_automatica_toca_como_en_la_v1() {
        assert!(!vencida(0, None));
        assert!(vencida(7, None));
        assert!(!vencida(7, Some(6 * 86_400)));
        assert!(vencida(7, Some(7 * 86_400)));
    }

    #[test]
    fn solo_valen_las_frecuencias_de_ajustes() {
        let db = BaseDeDatos::en_memoria().unwrap();
        fijar_frecuencia(&db, 7).unwrap();
        assert_eq!(fijar_frecuencia(&db, 3), Err(NsError::InvalidInput));
    }
}
