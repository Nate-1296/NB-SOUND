//! Dónde vive tu música, y encontrarla sola cuando cambia de sitio.
//!
//! Las rutas de las pistas son relativas a la carpeta de la música, así que lo
//! único que se rompe al formatear el equipo, cambiar el nombre del usuario o
//! restaurar una copia en otro equipo es la preferencia `carpeta_musica`, que es
//! absoluta. Si ahí ya no está la música, al arrancar se prueba dónde lo más
//! probable es que esté:
//!
//! - la misma ruta bajo la carpeta personal de ahora (`/home/ana/Música/x` pasa a
//!   `/home/ana2/Música/x`, `C:\Users\ana\Music\x` a la casa de este equipo);
//! - la carpeta de música del sistema con las últimas partes de la ruta vieja: el
//!   escritorio en otro idioma la llama `Music` en vez de `Música`;
//! - la carpeta de música del sistema tal cual.
//!
//! Solo se adopta una candidata si en ella está la gran mayoría de una muestra de
//! la biblioteca: una carpeta que solo coincide en el nombre no sirve. Si ninguna
//! convence, no se adivina: la interfaz pregunta dónde está ([`comprobar`]).
//!
//! Se descartó guardar la ruta relativa a la carpeta personal: no cubre una
//! carpeta en otro disco, y la preferencia de antes seguiría sin repararse.

use std::path::{Path, PathBuf};
use std::sync::Mutex;

use serde::Serialize;
use ts_rs::TS;

use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};

/// Canciones que se miran para decidir si una carpeta es la buena: bastan para
/// distinguir la biblioteca de una carpeta cualquiera sin recorrer miles.
const MUESTRA: usize = 64;

/// Proporción de la muestra que una candidata debe tener para adoptarla sola.
const ADOPTAR: f64 = 0.8;

/// Si en este arranque la carpeta se encontró sola en otro sitio, el nombre de la
/// de antes, para avisarlo una vez.
static RECUPERADA: Mutex<Option<String>> = Mutex::new(None);

/// Lo que Ajustes y el arranque necesitan saber de la carpeta de la música.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct UbicacionMusica {
    pub carpeta: Option<String>,
    /// Canciones de la biblioteca.
    pub total: u32,
    /// Las que están en la carpeta.
    pub presentes: u32,
    /// No está ni la mitad: la carpeta se movió o se perdió y hay que decir dónde.
    pub perdida: bool,
    /// La carpeta de antes, si en este arranque NB Sound la encontró sola en otro
    /// sitio. Se dice una vez.
    pub recuperada_de: Option<String>,
}

pub(crate) fn rutas_de_la_biblioteca(db: &BaseDeDatos) -> NsResult<Vec<String>> {
    let conn = db.conexion()?;
    let mut s = conn
        .prepare("SELECT ruta FROM pistas ORDER BY id")
        .map_err(|_| NsError::StorageFailure)?;
    let filas = s
        .query_map([], |f| f.get::<_, String>(0))
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|_| NsError::StorageFailure);
    filas
}

fn carpeta_actual(db: &BaseDeDatos) -> NsResult<Option<PathBuf>> {
    crate::reproductor::carpeta_musica(&*db.conexion()?)
}

/// Cuenta cuántas canciones están en la carpeta. Mirar unas miles de rutas tarda
/// milisegundos.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base no responde.
pub fn comprobar(db: &BaseDeDatos) -> NsResult<UbicacionMusica> {
    let carpeta = carpeta_actual(db)?;
    let rutas = rutas_de_la_biblioteca(db)?;
    let presentes = carpeta
        .as_deref()
        .map_or(0, |c| rutas.iter().filter(|r| c.join(r).is_file()).count());
    let total = rutas.len();
    let recuperada_de = RECUPERADA.lock().map_or(None, |mut r| r.take());
    Ok(UbicacionMusica {
        carpeta: carpeta.map(|c| c.to_string_lossy().into_owned()),
        total: u32::try_from(total).unwrap_or(u32::MAX),
        presentes: u32::try_from(presentes).unwrap_or(u32::MAX),
        perdida: total > 0 && presentes * 2 < total,
        recuperada_de,
    })
}

/// Unas canciones repartidas por toda la biblioteca, no las primeras: las
/// primeras suelen ser del mismo artista.
fn muestra(rutas: &[String]) -> Vec<&str> {
    if rutas.len() <= MUESTRA {
        return rutas.iter().map(String::as_str).collect();
    }
    (0..MUESTRA)
        .map(|i| rutas[i * rutas.len() / MUESTRA].as_str())
        .collect()
}

fn proporcion(carpeta: &Path, muestra: &[&str]) -> f64 {
    if muestra.is_empty() || !carpeta.is_dir() {
        return 0.0;
    }
    let hay = muestra.iter().filter(|r| carpeta.join(r).is_file()).count();
    #[allow(clippy::cast_precision_loss)]
    let p = hay as f64 / muestra.len() as f64;
    p
}

/// Las partes de una ruta, separadas por `/` o por `\`: una copia hecha en
/// Windows se puede restaurar en Linux y al revés.
fn partes(ruta: &str) -> Vec<&str> {
    ruta.split(['/', '\\'])
        .filter(|p| !p.is_empty() && !p.ends_with(':'))
        .collect()
}

/// Lo que va después de la carpeta personal (`home/<usuario>` o
/// `Users/<usuario>`), si la ruta estaba dentro de una.
fn tras_la_casa<'a>(partes: &'a [&'a str]) -> Option<&'a [&'a str]> {
    let i = partes
        .iter()
        .take(3)
        .position(|p| p.eq_ignore_ascii_case("home") || p.eq_ignore_ascii_case("users"))?;
    partes.get(i + 2..).filter(|resto| !resto.is_empty())
}

fn unir(base: &Path, partes: &[&str]) -> PathBuf {
    partes.iter().fold(base.to_path_buf(), |r, p| r.join(p))
}

/// Dónde podría estar ahora una carpeta que estaba en `vieja`, de lo más probable
/// a lo menos.
fn candidatas(vieja: &str, casa: Option<&Path>, sistema: Option<&Path>) -> Vec<PathBuf> {
    let p = partes(vieja);
    let mut v = Vec::new();
    if let (Some(casa), Some(resto)) = (casa, tras_la_casa(&p)) {
        v.push(unir(casa, resto));
    }
    for k in 1..=p.len().min(3) {
        let cola = &p[p.len() - k..];
        v.extend(sistema.map(|s| unir(s, cola)));
        v.extend(casa.map(|c| unir(c, cola)));
    }
    v.extend(sistema.map(Path::to_path_buf));
    let mut vistas = std::collections::HashSet::new();
    v.retain(|c| c.as_os_str() != vieja && vistas.insert(c.clone()));
    v
}

fn guardar_preferencia(db: &BaseDeDatos, clave: &str, valor: &Path) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    tx.execute(
        "INSERT INTO preferencias (clave, valor) VALUES (?1, ?2)
         ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor",
        [
            clave.to_owned(),
            serde_json::Value::from(valor.to_string_lossy().into_owned()).to_string(),
        ],
    )
    .map_err(|_| NsError::StorageFailure)?;
    tx.commit().map_err(|_| NsError::StorageFailure)
}

fn preferencia_ruta(db: &BaseDeDatos, clave: &str) -> Option<String> {
    use rusqlite::OptionalExtension;
    db.conexion()
        .ok()?
        .query_row(
            "SELECT valor FROM preferencias WHERE clave = ?1",
            [clave],
            |f| f.get::<_, String>(0),
        )
        .optional()
        .ok()?
        .and_then(|v| serde_json::from_str::<String>(&v).ok())
        .filter(|v| !v.is_empty())
}

/// Si la música ya no está donde dice la preferencia, la busca en las candidatas
/// y, si una la tiene, apunta a ella. Hace lo mismo con la carpeta de las copias
/// de seguridad, que se rompe por la misma causa. Se llama al arrancar, antes de
/// vigilar e importar: una canción nueva no debe acabar en la carpeta vieja.
///
/// Devuelve la carpeta nueva, si cambió.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base no responde.
pub fn recuperar_si_hace_falta(
    db: &BaseDeDatos,
    casa: Option<&Path>,
    sistema: Option<&Path>,
) -> NsResult<Option<PathBuf>> {
    recolocar_copias(db, casa)?;
    let Some(vieja) = preferencia_ruta(db, "carpeta_musica") else {
        return Ok(None);
    };
    let rutas = rutas_de_la_biblioteca(db)?;
    let m = muestra(&rutas);
    if m.is_empty() || proporcion(Path::new(&vieja), &m) >= 0.5 {
        return Ok(None);
    }
    let mejor = candidatas(&vieja, casa, sistema)
        .into_iter()
        .map(|c| {
            let p = proporcion(&c, &m);
            (c, p)
        })
        .filter(|(_, p)| *p >= ADOPTAR)
        .max_by(|a, b| a.1.total_cmp(&b.1));
    let Some((nueva, _)) = mejor else {
        tracing::warn!("la carpeta de la música no está y no se encontró en otro sitio");
        return Ok(None);
    };
    guardar_preferencia(db, "carpeta_musica", &nueva)?;
    if let Ok(mut r) = RECUPERADA.lock() {
        *r = Some(vieja);
    }
    tracing::info!("la carpeta de la música se encontró en otro sitio");
    Ok(Some(nueva))
}

/// La carpeta de las copias automáticas, por la misma regla de la carpeta
/// personal. Si no aparece, se deja: Ajustes la enseña y la copia no se hace.
fn recolocar_copias(db: &BaseDeDatos, casa: Option<&Path>) -> NsResult<()> {
    let Some(vieja) = preferencia_ruta(db, "copia_carpeta") else {
        return Ok(());
    };
    if Path::new(&vieja).is_dir() {
        return Ok(());
    }
    let p = partes(&vieja);
    if let (Some(casa), Some(resto)) = (casa, tras_la_casa(&p)) {
        let nueva = unir(casa, resto);
        if nueva.is_dir() {
            guardar_preferencia(db, "copia_carpeta", &nueva)?;
        }
    }
    Ok(())
}

/// La carpeta personal de este equipo.
#[must_use]
pub fn casa() -> Option<PathBuf> {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Temporal(PathBuf);

    impl Temporal {
        fn nueva(nombre: &str) -> Self {
            let d =
                std::env::temp_dir().join(format!("ns-ubicacion-{nombre}-{}", std::process::id()));
            let _ = std::fs::remove_dir_all(&d);
            std::fs::create_dir_all(&d).unwrap();
            Self(d)
        }
    }

    impl Drop for Temporal {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    const CANCIONES: [&str; 3] = ["a/x/uno.mp3", "a/dos.mp3", "b/tres.mp3"];

    fn biblioteca(carpeta: &str) -> BaseDeDatos {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO pistas (id, titulo, ruta) VALUES
                     (1, 'uno', 'a/x/uno.mp3'), (2, 'dos', 'a/dos.mp3'), (3, 'tres', 'b/tres.mp3');",
            )
            .unwrap();
        guardar_preferencia(&db, "carpeta_musica", Path::new(carpeta)).unwrap();
        db
    }

    fn poner_canciones(dir: &Path) {
        for r in CANCIONES {
            let p = dir.join(r);
            std::fs::create_dir_all(p.parent().unwrap()).unwrap();
            std::fs::write(&p, r).unwrap();
        }
    }

    fn carpeta(db: &BaseDeDatos) -> Option<PathBuf> {
        carpeta_actual(db).unwrap()
    }

    #[test]
    fn otra_carpeta_personal_se_repara_sola_al_arrancar() {
        let t = Temporal::nueva("casa");
        let casa = t.0.join("ana2");
        poner_canciones(&casa.join("Música/biblioteca"));
        let db = biblioteca("/home/ana/Música/biblioteca");
        let nueva = recuperar_si_hace_falta(&db, Some(&casa), None).unwrap();
        assert_eq!(nueva, Some(casa.join("Música/biblioteca")));
        assert_eq!(carpeta(&db), Some(casa.join("Música/biblioteca")));
        let u = comprobar(&db).unwrap();
        assert_eq!((u.presentes, u.total, u.perdida), (3, 3, false));
        assert_eq!(
            u.recuperada_de.as_deref(),
            Some("/home/ana/Música/biblioteca")
        );
        assert_eq!(
            comprobar(&db).unwrap().recuperada_de,
            None,
            "se avisa una vez"
        );
    }

    #[test]
    fn una_copia_de_windows_encuentra_la_musica_en_la_carpeta_del_sistema() {
        let t = Temporal::nueva("windows");
        let sistema = t.0.join("Música");
        poner_canciones(&sistema.join("biblioteca"));
        let db = biblioteca(r"C:\Users\Ana\Music\biblioteca");
        let nueva = recuperar_si_hace_falta(&db, Some(&t.0.join("casa")), Some(&sistema)).unwrap();
        assert_eq!(nueva, Some(sistema.join("biblioteca")));
    }

    #[test]
    fn una_carpeta_que_solo_coincide_en_el_nombre_no_se_adopta() {
        let t = Temporal::nueva("nombre");
        let casa = t.0.join("ana2");
        let otra = casa.join("Música/biblioteca");
        std::fs::create_dir_all(otra.join("a")).unwrap();
        std::fs::write(otra.join("a/dos.mp3"), "solo una").unwrap();
        let db = biblioteca("/home/ana/Música/biblioteca");
        assert_eq!(
            recuperar_si_hace_falta(&db, Some(&casa), None).unwrap(),
            None
        );
        assert_eq!(
            carpeta(&db),
            Some(PathBuf::from("/home/ana/Música/biblioteca"))
        );
        let u = comprobar(&db).unwrap();
        assert!(u.perdida, "sin carpeta buena, se pregunta");
        assert_eq!(u.presentes, 0);
    }

    #[test]
    fn la_carpeta_que_sigue_en_su_sitio_no_se_toca() {
        let t = Temporal::nueva("quieta");
        let musica = t.0.join("musica");
        poner_canciones(&musica);
        // Otra carpeta con las mismas canciones no la sustituye.
        poner_canciones(&t.0.join("casa/musica"));
        let db = biblioteca(&musica.to_string_lossy());
        assert_eq!(
            recuperar_si_hace_falta(&db, Some(&t.0.join("casa")), None).unwrap(),
            None
        );
        assert_eq!(carpeta(&db), Some(musica));
    }

    #[test]
    fn la_carpeta_de_las_copias_sigue_a_la_carpeta_personal() {
        let t = Temporal::nueva("copias");
        let casa = t.0.join("ana2");
        std::fs::create_dir_all(casa.join("Música/copias")).unwrap();
        let db = biblioteca("/home/ana/Música/biblioteca");
        guardar_preferencia(&db, "copia_carpeta", Path::new("/home/ana/Música/copias")).unwrap();
        recuperar_si_hace_falta(&db, Some(&casa), None).unwrap();
        assert_eq!(
            preferencia_ruta(&db, "copia_carpeta").map(PathBuf::from),
            Some(casa.join("Música/copias"))
        );
    }

    #[test]
    fn las_candidatas_prueban_la_casa_y_la_carpeta_del_sistema() {
        let c = candidatas(
            "/home/ana/Música/biblioteca",
            Some(Path::new("/home/bea")),
            Some(Path::new("/home/bea/Music")),
        );
        assert_eq!(c[0], PathBuf::from("/home/bea/Música/biblioteca"));
        assert!(c.contains(&PathBuf::from("/home/bea/Music/biblioteca")));
        assert!(c.contains(&PathBuf::from("/home/bea/Music")));
        assert!(!c.contains(&PathBuf::from("/home/ana/Música/biblioteca")));
    }
}
