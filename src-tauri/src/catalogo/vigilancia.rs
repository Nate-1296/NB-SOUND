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

/// Cada cuánto se mira si ya hay carpeta de música, mientras no la hay.
const ESPERA_CARPETA: Duration = Duration::from_secs(5);

/// Cada cuánto se mira si lo que espera ya está quieto.
const SONDEO: Duration = Duration::from_millis(500);

fn es_audio(r: &Path) -> bool {
    r.extension()
        .and_then(|e| e.to_str())
        .is_some_and(|e| EXTENSIONES.contains(&e.to_lowercase().as_str()))
}

fn relativa(musica: &Path, r: &Path) -> String {
    r.strip_prefix(musica)
        .unwrap_or(r)
        .to_string_lossy()
        .replace('\\', "/")
}

/// Lo que ya está atendido: las rutas de la biblioteca (relativas a la música) y
/// las que esperan en la cola (absolutas). Mandar otra vez algo de la cola no lo
/// importaría dos veces, pero dejaría una importación vacía que nunca termina.
struct Atendidas {
    biblioteca: HashSet<String>,
    cola: HashSet<String>,
}

impl Atendidas {
    fn leer(db: &BaseDeDatos) -> NsResult<Self> {
        let conn = db.conexion()?;
        let columna = |sql: &str| -> NsResult<HashSet<String>> {
            let mut s = conn.prepare(sql).map_err(|_| NsError::StorageFailure)?;
            let filas = s
                .query_map([], |f| f.get::<_, String>(0))
                .map_err(|_| NsError::StorageFailure)?
                .collect::<rusqlite::Result<HashSet<_>>>()
                .map_err(|_| NsError::StorageFailure)?;
            Ok(filas)
        };
        Ok(Self {
            biblioteca: columna("SELECT ruta FROM pistas")?,
            cola: columna("SELECT ruta FROM pendientes_importacion")?,
        })
    }

    fn contiene(&self, musica: &Path, r: &Path) -> bool {
        self.biblioteca.contains(&relativa(musica, r))
            || self.cola.contains(r.to_string_lossy().as_ref())
    }
}

/// Lo que hay en la carpeta y no está ni en la biblioteca ni en la cola.
///
/// # Errors
///
/// [`NsError::StorageFailure`] si la consulta falla.
pub fn nuevos(db: &BaseDeDatos, musica: &Path) -> NsResult<Vec<PathBuf>> {
    let ya = Atendidas::leer(db)?;
    Ok(expandir(&[musica.to_path_buf()])
        .into_iter()
        .filter(|r| !ya.contiene(musica, r))
        .collect())
}

/// Vigila la carpeta de música hasta que se cierre la aplicación.
///
/// Si aún no hay ninguna, espera a que la fije la primera importación: vigilar
/// por su cuenta la carpeta del sistema importaría sin preguntar toda la música
/// que el usuario ya tuviera en ella.
pub fn vigilar(db: BaseDeDatos, importador: Importador) {
    let lanzado = std::thread::Builder::new()
        .name("vigilancia".into())
        .spawn(move || {
            let musica = loop {
                let fijada = db
                    .conexion()
                    .and_then(|c| crate::reproductor::carpeta_musica(&c));
                if let Ok(Some(m)) = fijada {
                    break m;
                }
                std::thread::sleep(ESPERA_CARPETA);
            };
            bucle(&db, &musica, QUIETO, |n| {
                importador.importar(n);
                true
            });
        });
    if lanzado.is_err() {
        tracing::error!("no se pudo lanzar la vigilancia de la carpeta de música");
    }
}

/// El cuerpo del hilo, separado del [`Importador`] para poder probarlo: `mandar`
/// recibe cada tanda de archivos nuevos y devuelve `false` para terminar.
fn bucle(
    db: &BaseDeDatos,
    musica: &Path,
    quieto: Duration,
    mut mandar: impl FnMut(Vec<PathBuf>) -> bool,
) {
    if !musica.is_dir() {
        return;
    }
    // Lo que llegó con la aplicación cerrada.
    if let Ok(n) = nuevos(db, musica) {
        if !n.is_empty() {
            tracing::info!(
                archivos = n.len(),
                "archivos nuevos en la carpeta de música"
            );
            if !mandar(n) {
                return;
            }
        }
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
    if w.watch(musica, RecursiveMode::Recursive).is_err() {
        tracing::error!("no se pudo vigilar la carpeta de música");
        return;
    }
    // Ruta, tamaño visto y desde cuándo no cambia.
    let mut esperando: HashMap<PathBuf, (u64, Instant)> = HashMap::new();
    loop {
        match rx.recv_timeout(SONDEO) {
            Ok(rutas) => {
                for r in rutas {
                    if r.is_dir() {
                        // Una carpeta que llega entera (un álbum movido de otro
                        // sitio del mismo disco) puede no avisar de cada archivo.
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
            if desde.elapsed() < quieto {
                return true;
            }
            listos.push(r.clone());
            false
        });
        if listos.is_empty() {
            continue;
        }
        // Si la base no responde, lo recoge el recorrido del próximo arranque:
        // importar a ciegas podría repetir lo que ya está.
        let Ok(ya) = Atendidas::leer(db) else {
            continue;
        };
        let mut nuevos: Vec<PathBuf> = listos
            .into_iter()
            .filter(|r| !ya.contiene(musica, r))
            .collect();
        nuevos.sort();
        if !nuevos.is_empty() && !mandar(nuevos) {
            return;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lo_nuevo_es_lo_que_no_esta_ni_en_la_biblioteca_ni_en_la_cola() {
        let d = std::env::temp_dir().join(format!("ns-vigilancia-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(d.join("a/b")).unwrap();
        for f in [
            "a/b/01_x.mp3",
            "a/b/02_y.mp3",
            "a/b/03_z.mp3",
            "a/portada.jpg",
        ] {
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
        let conn = db.conexion().unwrap();
        conn.execute(
            "INSERT INTO importaciones (id, origen) VALUES (1, 'manual')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO pendientes_importacion (ruta, importacion_id, orden) VALUES (?1, 1, 1)",
            [d.join("a/b/03_z.mp3").to_string_lossy()],
        )
        .unwrap();
        let n = nuevos(&db, &d).unwrap();
        assert_eq!(n, [d.join("a/b/02_y.mp3")]);
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn copiar_un_album_en_la_carpeta_lo_manda_a_importar_cuando_termina_de_copiarse() {
        let d = std::env::temp_dir().join(format!("ns-vigilancia-album-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        std::fs::write(d.join("de_antes.mp3"), b"x").unwrap();
        let db = BaseDeDatos::en_memoria().unwrap();
        let (tx, rx) = mpsc::channel();
        let (dd, musica) = (db.clone(), d.clone());
        let hilo = std::thread::spawn(move || {
            bucle(&dd, &musica, Duration::from_millis(300), |n| {
                tx.send(n).is_ok()
            });
        });
        let espera = Duration::from_secs(15);
        assert_eq!(rx.recv_timeout(espera).unwrap(), [d.join("de_antes.mp3")]);

        // Uno de los archivos se escribe en dos tiempos, como una copia larga.
        let album = d.join("Artista/Álbum");
        std::fs::create_dir_all(&album).unwrap();
        std::fs::write(album.join("01.mp3"), b"uno").unwrap();
        std::fs::write(album.join("02.flac"), b"a").unwrap();
        std::fs::write(album.join("portada.jpg"), b"jpg").unwrap();
        std::thread::sleep(Duration::from_millis(100));
        std::fs::write(album.join("02.flac"), b"dos, ya completo").unwrap();
        let mut recibidos = Vec::new();
        while recibidos.len() < 2 {
            recibidos.extend(rx.recv_timeout(espera).unwrap());
        }
        recibidos.sort();
        assert_eq!(recibidos, [album.join("01.mp3"), album.join("02.flac")]);

        drop(rx);
        // Un último cambio para que el hilo vea que nadie escucha y termine.
        std::fs::write(album.join("03.mp3"), b"tres").unwrap();
        hilo.join().unwrap();
        let _ = std::fs::remove_dir_all(&d);
    }
}
