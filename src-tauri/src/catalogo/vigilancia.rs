//! La carpeta de música vigilada (F4.2.2): copiar un álbum en ella lo añade sin
//! abrir nada (ADR-007).
//!
//! Se escuchan los cambios del sistema de archivos con `notify` y, al arrancar,
//! se recorre la carpeta una vez para recoger lo que llegó con la aplicación
//! cerrada. Un archivo se manda a importar cuando lleva un rato sin cambiar de
//! tamaño (una copia larga no se importa a medias) y si no está ya en la
//! biblioteca: los que coloca la propia importación ya lo están cuando se miran.

use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::mpsc;
use std::time::{Duration, Instant};

use notify::{RecursiveMode, Watcher};

use super::canalizacion::EXTENSIONES;
use super::importacion::{expandir, Importador};
use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};

/// Lo que tiene que estar quieto un archivo antes de importarlo.
const QUIETO: Duration = Duration::from_secs(3);

fn es_audio(r: &Path) -> bool {
    r.extension()
        .and_then(|e| e.to_str())
        .is_some_and(|e| EXTENSIONES.contains(&e.to_lowercase().as_str()))
}

/// Las rutas (relativas a la música) que ya están en la biblioteca.
fn conocidas(db: &BaseDeDatos) -> NsResult<HashSet<String>> {
    let conn = db.conexion()?;
    let mut s = conn
        .prepare("SELECT ruta FROM pistas")
        .map_err(|_| NsError::StorageFailure)?;
    let filas = s
        .query_map([], |f| f.get::<_, String>(0))
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<HashSet<_>>>()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(filas)
}

fn relativa(musica: &Path, r: &Path) -> String {
    r.strip_prefix(musica)
        .unwrap_or(r)
        .to_string_lossy()
        .replace('\\', "/")
}

/// Lo que hay en la carpeta y no está en la biblioteca.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn nuevos(db: &BaseDeDatos, musica: &Path) -> NsResult<Vec<PathBuf>> {
    let ya = conocidas(db)?;
    Ok(expandir(&[musica.to_path_buf()])
        .into_iter()
        .filter(|r| !ya.contains(&relativa(musica, r)))
        .collect())
}

/// Vigila `musica` hasta que se cierre la aplicación.
pub fn vigilar(db: BaseDeDatos, musica: PathBuf, importador: Importador) {
    let lanzado = std::thread::Builder::new()
        .name("vigilancia".into())
        .spawn(move || {
            if !musica.is_dir() {
                return;
            }
            match nuevos(&db, &musica) {
                Ok(n) if !n.is_empty() => {
                    tracing::info!(
                        archivos = n.len(),
                        "archivos nuevos en la carpeta de música"
                    );
                    importador.importar(n);
                }
                _ => {}
            }
            let (tx, rx) = mpsc::channel();
            let Ok(mut w) = notify::recommended_watcher(move |e: notify::Result<notify::Event>| {
                if let Ok(e) = e {
                    let _ = tx.send(e.paths);
                }
            }) else {
                tracing::error!("no se pudo vigilar la carpeta de música");
                return;
            };
            if w.watch(&musica, RecursiveMode::Recursive).is_err() {
                tracing::error!("no se pudo vigilar la carpeta de música");
                return;
            }
            // Ruta, tamaño visto y desde cuándo no cambia.
            let mut esperando: HashMap<PathBuf, (u64, Instant)> = HashMap::new();
            loop {
                match rx.recv_timeout(Duration::from_secs(1)) {
                    Ok(rutas) => {
                        for r in rutas {
                            if r.is_dir() {
                                for a in expandir(&[r]) {
                                    esperando.entry(a).or_insert((u64::MAX, Instant::now()));
                                }
                            } else if es_audio(&r) {
                                esperando.insert(r, (u64::MAX, Instant::now()));
                            }
                        }
                    }
                    Err(mpsc::RecvTimeoutError::Disconnected) => return,
                    Err(mpsc::RecvTimeoutError::Timeout) => {}
                }
                let mut listos = Vec::new();
                esperando.retain(|r, (tamano, desde)| {
                    let Ok(m) = std::fs::metadata(r) else {
                        return false;
                    };
                    if m.len() != *tamano {
                        *tamano = m.len();
                        *desde = Instant::now();
                        return true;
                    }
                    if desde.elapsed() < QUIETO {
                        return true;
                    }
                    listos.push(r.clone());
                    false
                });
                if listos.is_empty() {
                    continue;
                }
                let ya = conocidas(&db).unwrap_or_default();
                let nuevos: Vec<PathBuf> = listos
                    .into_iter()
                    .filter(|r| !ya.contains(&relativa(&musica, r)))
                    .collect();
                if !nuevos.is_empty() {
                    importador.importar(nuevos);
                }
            }
        });
    if lanzado.is_err() {
        tracing::error!("no se pudo lanzar la vigilancia de la carpeta de música");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lo_nuevo_es_lo_que_no_esta_en_la_biblioteca() {
        let d = std::env::temp_dir().join(format!("ns-vigilancia-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(d.join("a/b")).unwrap();
        for f in ["a/b/01_x.mp3", "a/b/02_y.mp3", "a/portada.jpg"] {
            std::fs::write(d.join(f), b"").unwrap();
        }
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute(
                "INSERT INTO pistas (titulo, ruta) VALUES ('x', 'a/b/01_x.mp3')",
                [],
            )
            .unwrap();
        let n = nuevos(&db, &d).unwrap();
        assert_eq!(n, [d.join("a/b/02_y.mp3")]);
    }
}
