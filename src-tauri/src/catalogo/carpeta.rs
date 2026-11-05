//! Cambiar la carpeta de tu música (QA-R2).
//!
//! Las rutas de las pistas son relativas a la carpeta, así que cambiarla es una
//! preferencia: lo que importa es dónde están los archivos. Hay dos casos.
//!
//! - **Ya la moviste tú** (a otro disco, por ejemplo): la carpeta nueva tiene las
//!   canciones y basta con apuntar a ella. [`revisar`] cuenta cuántas encuentra
//!   para que la interfaz lo diga antes de aplicar.
//! - **Que la mueva NB Sound**: [`mover`] lleva cada archivo de la biblioteca a la
//!   misma ruta relativa dentro de la nueva. En el mismo disco es un `rename`; entre
//!   discos se copia y se comprueba el tamaño, y los originales solo se borran
//!   cuando todo ha llegado. Si algo falla, se deshace lo hecho y la carpeta sigue
//!   siendo la de antes: nunca queda la biblioteca a medias entre dos sitios.
//!
//! Lo que no es de la biblioteca (portadas sueltas, `.lrc`, otros archivos) se
//! queda donde estaba: no es nuestro.

use std::path::{Path, PathBuf};

use serde::Serialize;
use ts_rs::TS;

use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};

/// Lo que hay en una carpeta candidata, para decidir antes de cambiar.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct RevisionCarpeta {
    /// Para enseñarla; la ruta de verdad se queda en el proceso.
    pub carpeta: String,
    /// Canciones de la biblioteca que ya están en ella.
    pub encontradas: u32,
    pub total: u32,
    /// Es la misma que la actual: no hay nada que hacer.
    pub misma: bool,
}

fn rutas_de_la_biblioteca(db: &BaseDeDatos) -> NsResult<Vec<String>> {
    let conn = db.conexion()?;
    let mut s = conn
        .prepare("SELECT ruta FROM pistas")
        .map_err(|_| NsError::StorageFailure)?;
    let filas = s
        .query_map([], |f| f.get::<_, String>(0))
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|_| NsError::StorageFailure);
    filas
}

/// Cuántas canciones de la biblioteca están ya en `nueva`.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la base no responde.
pub fn revisar(db: &BaseDeDatos, actual: Option<&Path>, nueva: &Path) -> NsResult<RevisionCarpeta> {
    let rutas = rutas_de_la_biblioteca(db)?;
    let encontradas = rutas.iter().filter(|r| nueva.join(r).is_file()).count();
    Ok(RevisionCarpeta {
        carpeta: nueva.to_string_lossy().into_owned(),
        encontradas: u32::try_from(encontradas).unwrap_or(u32::MAX),
        total: u32::try_from(rutas.len()).unwrap_or(u32::MAX),
        misma: actual.is_some_and(|a| a == nueva),
    })
}

/// Apunta la biblioteca a `nueva`, sin tocar archivos.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si no se puede guardar.
pub fn fijar(db: &BaseDeDatos, nueva: &Path) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    tx.execute(
        "INSERT INTO preferencias (clave, valor) VALUES ('carpeta_musica', ?1)
         ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor",
        [serde_json::Value::from(nueva.to_string_lossy().into_owned()).to_string()],
    )
    .map_err(|_| NsError::StorageFailure)?;
    tx.commit().map_err(|_| NsError::StorageFailure)
}

/// Cómo llegó cada archivo, para deshacerlo si hace falta.
enum Hecho {
    Renombrado(PathBuf, PathBuf),
    Copiado(PathBuf, PathBuf),
}

fn deshacer(hechos: Vec<Hecho>) {
    for h in hechos.into_iter().rev() {
        match h {
            Hecho::Renombrado(origen, destino) => {
                let _ = std::fs::rename(destino, origen);
            }
            Hecho::Copiado(_, destino) => {
                let _ = std::fs::remove_file(destino);
            }
        }
    }
}

fn llevar(origen: &Path, destino: &Path) -> std::io::Result<Hecho> {
    if let Some(padre) = destino.parent() {
        std::fs::create_dir_all(padre)?;
    }
    if std::fs::rename(origen, destino).is_ok() {
        return Ok(Hecho::Renombrado(
            origen.to_path_buf(),
            destino.to_path_buf(),
        ));
    }
    // Otro disco: se copia y se comprueba; el original se borra al final.
    let copiados = std::fs::copy(origen, destino)?;
    if copiados != std::fs::metadata(origen)?.len() {
        let _ = std::fs::remove_file(destino);
        return Err(std::io::Error::other("copia incompleta"));
    }
    Ok(Hecho::Copiado(origen.to_path_buf(), destino.to_path_buf()))
}

/// Quita las carpetas que se quedaron vacías al mover, de dentro hacia fuera y
/// sin salir de `raiz`.
fn podar(raiz: &Path, archivo: &Path) {
    let mut d = archivo.parent();
    while let Some(dir) = d {
        if dir == raiz || !dir.starts_with(raiz) || std::fs::remove_dir(dir).is_err() {
            break;
        }
        d = dir.parent();
    }
}

/// Lleva los archivos de la biblioteca de `actual` a `nueva` y apunta a ella.
/// `avance` recibe (hechas, total). Devuelve cuántos se movieron; los que ya
/// estaban en la nueva se dejan y los que faltaban en la vieja no cuentan.
///
/// # Errors
///
/// [`NsError::InvalidInput`] si una carpeta está dentro de la otra;
/// [`NsError::StorageFailure`] si un archivo no se pudo llevar (y entonces
/// todo vuelve a su sitio) o la base no responde.
pub fn mover(
    db: &BaseDeDatos,
    actual: &Path,
    nueva: &Path,
    mut avance: impl FnMut(u32, u32),
) -> NsResult<u32> {
    if actual == nueva {
        return Ok(0);
    }
    if nueva.starts_with(actual) || actual.starts_with(nueva) {
        return Err(NsError::InvalidInput);
    }
    let rutas = rutas_de_la_biblioteca(db)?;
    let total = u32::try_from(rutas.len()).unwrap_or(u32::MAX);
    let mut hechos = Vec::new();
    for (i, r) in rutas.iter().enumerate() {
        let (origen, destino) = (actual.join(r), nueva.join(r));
        if origen.is_file() && !destino.exists() {
            match llevar(&origen, &destino) {
                Ok(h) => hechos.push(h),
                Err(_) => {
                    tracing::warn!(
                        movidas = hechos.len(),
                        "no se pudo mover la música; se deshace lo hecho"
                    );
                    deshacer(hechos);
                    return Err(NsError::StorageFailure);
                }
            }
        }
        avance(u32::try_from(i + 1).unwrap_or(u32::MAX), total);
    }
    if let Err(e) = fijar(db, nueva) {
        deshacer(hechos);
        return Err(e);
    }
    let movidas = u32::try_from(hechos.len()).unwrap_or(u32::MAX);
    for h in hechos {
        let origen = match h {
            Hecho::Copiado(origen, _) => {
                let _ = std::fs::remove_file(&origen);
                origen
            }
            Hecho::Renombrado(origen, _) => origen,
        };
        podar(actual, &origen);
    }
    tracing::info!(movidas, "música movida a la carpeta nueva");
    Ok(movidas)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn biblioteca(dir: &Path) -> BaseDeDatos {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO pistas (id, titulo, ruta) VALUES
                     (1, 'uno', 'a/x/uno.mp3'), (2, 'dos', 'a/dos.mp3'), (3, 'tres', 'b/tres.mp3');",
            )
            .unwrap();
        for r in ["a/x/uno.mp3", "a/dos.mp3", "b/tres.mp3"] {
            let p = dir.join(r);
            std::fs::create_dir_all(p.parent().unwrap()).unwrap();
            std::fs::write(&p, r).unwrap();
        }
        db
    }

    /// Una carpeta temporal propia de cada prueba, que se borra al terminar.
    struct Temporal(PathBuf);

    impl Temporal {
        fn nueva(nombre: &str) -> Self {
            let d =
                std::env::temp_dir().join(format!("ns-carpeta-{nombre}-{}", std::process::id()));
            let _ = std::fs::remove_dir_all(&d);
            std::fs::create_dir_all(&d).unwrap();
            Self(d)
        }

        fn path(&self) -> &Path {
            &self.0
        }
    }

    impl Drop for Temporal {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    fn carpeta(db: &BaseDeDatos) -> Option<PathBuf> {
        crate::reproductor::carpeta_musica(&db.conexion().unwrap()).unwrap()
    }

    #[test]
    fn mover_lleva_cada_cancion_a_su_ruta_y_apunta_a_la_nueva() {
        let t = Temporal::nueva("mover");
        let (vieja, nueva) = (t.path().join("vieja"), t.path().join("nueva"));
        let db = biblioteca(&vieja);
        std::fs::write(vieja.join("a/portada.jpg"), "no es nuestra").unwrap();
        let mut ultimo = (0, 0);
        let n = mover(&db, &vieja, &nueva, |h, t| ultimo = (h, t)).unwrap();
        assert_eq!((n, ultimo), (3, (3, 3)));
        for r in ["a/x/uno.mp3", "a/dos.mp3", "b/tres.mp3"] {
            assert_eq!(std::fs::read_to_string(nueva.join(r)).unwrap(), r);
            assert!(!vieja.join(r).exists());
        }
        assert!(
            vieja.join("a/portada.jpg").exists(),
            "lo que no es de la biblioteca se queda"
        );
        assert!(
            !vieja.join("a/x").exists() && !vieja.join("b").exists(),
            "sin carpetas vacías"
        );
        assert_eq!(carpeta(&db), Some(nueva));
    }

    #[test]
    fn si_un_archivo_no_llega_todo_vuelve_a_su_sitio() {
        let t = Temporal::nueva("deshacer");
        let (vieja, nueva) = (t.path().join("vieja"), t.path().join("nueva"));
        let db = biblioteca(&vieja);
        fijar(&db, &vieja).unwrap();
        // Un archivo donde debería ir una carpeta: la tercera canción no cabe.
        std::fs::create_dir_all(&nueva).unwrap();
        std::fs::write(nueva.join("b"), "estorbo").unwrap();
        assert_eq!(
            mover(&db, &vieja, &nueva, |_, _| {}),
            Err(NsError::StorageFailure)
        );
        for r in ["a/x/uno.mp3", "a/dos.mp3", "b/tres.mp3"] {
            assert!(vieja.join(r).is_file(), "{r} volvió");
        }
        assert!(!nueva.join("a/dos.mp3").exists());
        assert_eq!(carpeta(&db), Some(vieja));
    }

    #[test]
    fn no_se_mueve_dentro_de_si_misma_y_revisar_cuenta_lo_que_ya_esta() {
        let t = Temporal::nueva("revisar");
        let vieja = t.path().join("vieja");
        let db = biblioteca(&vieja);
        assert_eq!(
            mover(&db, &vieja, &vieja.join("dentro"), |_, _| {}),
            Err(NsError::InvalidInput)
        );
        let r = revisar(&db, Some(&vieja), &vieja).unwrap();
        assert_eq!((r.encontradas, r.total, r.misma), (3, 3, true));
        let otra = revisar(&db, Some(&vieja), t.path()).unwrap();
        assert_eq!((otra.encontradas, otra.misma), (0, false));
    }
}
