//! El servicio de importación (F4.1.13 y F4.2.1 a F4.2.3): una cola de archivos
//! que se procesan de uno en uno en su propio hilo, con su progreso y su resumen.
//!
//! Cada archivo se apunta en `pendientes_importacion` antes de empezar y se borra
//! al terminarlo. Si la aplicación se cierra a medias, al volver se sigue por donde
//! iba (`core/import_recovery_service.py` de la V1, sin manifiestos).

use std::path::{Path, PathBuf};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, Mutex, PoisonError};

use rusqlite::params;
use serde::Serialize;
use ts_rs::TS;

use super::canalizacion::{self, Entorno, Resultado, EXTENSIONES};
use super::duplicados::Gestor;
use crate::db::{self, BaseDeDatos};
use crate::error::{NsError, NsResult};
use crate::net::{Red, Servicio};
use crate::paths::Rutas;

/// Lo que ve la interfaz mientras se importa y al acabar.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct ProgresoImportacion {
    pub activa: bool,
    pub total: u32,
    pub hechos: u32,
    pub importadas: u32,
    pub sin_verificar: u32,
    pub por_revisar: u32,
    /// El nombre del archivo en curso (sin carpeta).
    pub actual: Option<String>,
}

enum Mensaje {
    Rutas(Vec<PathBuf>),
}

/// El servicio. Clonable: el hilo y quien manda comparten el progreso.
#[derive(Clone)]
pub struct Importador {
    tx: Sender<Mensaje>,
    progreso: Arc<Mutex<ProgresoImportacion>>,
    recursos: Arc<Recursos>,
}

/// Todo lo que el hilo necesita para montar un [`Entorno`].
pub struct Recursos {
    pub db: BaseDeDatos,
    pub rutas: Rutas,
    pub red: Arc<Red>,
    pub fpcalc: PathBuf,
}

/// Los archivos de audio de una lista de rutas: los archivos tal cual y las
/// carpetas recorridas enteras, en orden estable.
pub fn expandir(rutas: &[PathBuf]) -> Vec<PathBuf> {
    let mut salida = Vec::new();
    let mut pila: Vec<PathBuf> = rutas.iter().rev().cloned().collect();
    while let Some(r) = pila.pop() {
        if r.is_dir() {
            let mut hijos: Vec<PathBuf> = std::fs::read_dir(&r)
                .map(|d| d.filter_map(Result::ok).map(|e| e.path()).collect())
                .unwrap_or_default();
            hijos.sort();
            pila.extend(hijos.into_iter().rev());
        } else if r
            .extension()
            .and_then(|e| e.to_str())
            .is_some_and(|e| EXTENSIONES.contains(&e.to_lowercase().as_str()))
        {
            salida.push(r);
        }
    }
    salida
}

fn preferencia(db: &BaseDeDatos, clave: &str) -> Option<serde_json::Value> {
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
        .and_then(|v| serde_json::from_str(&v).ok())
}

/// La carpeta de la música; si no hay ninguna, la del sistema, y se apunta.
fn carpeta_musica(db: &BaseDeDatos) -> NsResult<PathBuf> {
    if let Some(m) = preferencia(db, "carpeta_musica").and_then(|v| v.as_str().map(PathBuf::from)) {
        return Ok(m);
    }
    let m = crate::paths::musica_por_defecto().ok_or(NsError::StorageFailure)?;
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    tx.execute(
        "INSERT INTO preferencias (clave, valor) VALUES ('carpeta_musica', ?1) ON CONFLICT (clave) DO NOTHING",
        [serde_json::Value::from(m.to_string_lossy().into_owned()).to_string()],
    )
    .map_err(|_| NsError::StorageFailure)?;
    tx.commit().map_err(|_| NsError::StorageFailure)?;
    Ok(m)
}

fn clave(servicio: Servicio, anfitrion: &str) -> Option<String> {
    crate::secrets::leer(&crate::secrets::cuenta(servicio, anfitrion))
        .ok()
        .flatten()
}

fn nueva_importacion(db: &BaseDeDatos, origen: &str, rutas: &[PathBuf]) -> NsResult<i64> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    tx.execute(
        "INSERT INTO importaciones (origen, descubiertos) VALUES (?1, ?2)",
        params![origen, rutas.len() as i64],
    )
    .map_err(|_| NsError::StorageFailure)?;
    let id = tx.last_insert_rowid();
    // El orden continúa el de lo que ya hubiera pendiente.
    let base: i64 = tx
        .query_row(
            "SELECT coalesce(max(orden), 0) FROM pendientes_importacion",
            [],
            |f| f.get(0),
        )
        .map_err(|_| NsError::StorageFailure)?;
    for (i, r) in rutas.iter().enumerate() {
        tx.execute(
            "INSERT INTO pendientes_importacion (ruta, importacion_id, orden) VALUES (?1, ?2, ?3)
             ON CONFLICT (ruta) DO NOTHING",
            params![r.to_string_lossy(), id, base + 1 + i as i64],
        )
        .map_err(|_| NsError::StorageFailure)?;
    }
    tx.commit().map_err(|_| NsError::StorageFailure)?;
    Ok(id)
}

/// Lo que queda, en orden: lo de esta sesión y lo que dejó una anterior.
fn pendientes(db: &BaseDeDatos) -> NsResult<Vec<(PathBuf, i64)>> {
    let conn = db.conexion()?;
    let mut s = conn
        .prepare("SELECT ruta, importacion_id FROM pendientes_importacion ORDER BY orden")
        .map_err(|_| NsError::StorageFailure)?;
    let filas = s
        .query_map([], |f| {
            Ok((PathBuf::from(f.get::<_, String>(0)?), f.get(1)?))
        })
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(filas)
}

fn terminar_archivo(
    db: &BaseDeDatos,
    ruta: &Path,
    importacion: i64,
    r: Option<&Resultado>,
) -> NsResult<()> {
    let mut conn = db.conexion()?;
    let tx = db::transaccion_de_escritura(&mut conn)?;
    tx.execute(
        "DELETE FROM pendientes_importacion WHERE ruta = ?1",
        [ruta.to_string_lossy()],
    )
    .map_err(|_| NsError::StorageFailure)?;
    let columna = match r {
        Some(Resultado::Importada { .. }) => Some("aceptados"),
        Some(Resultado::PorRevisar { .. }) => Some("por_revisar"),
        Some(Resultado::Omitido) => None,
        None => Some("errores"),
    };
    if let Some(c) = columna {
        tx.execute(
            &format!("UPDATE importaciones SET {c} = {c} + 1 WHERE id = ?1"),
            [importacion],
        )
        .map_err(|_| NsError::StorageFailure)?;
    }
    // La importación termina cuando no le queda nada pendiente.
    tx.execute(
        "UPDATE importaciones SET estado = 'terminada', terminada_en = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
         WHERE id = ?1 AND NOT EXISTS (SELECT 1 FROM pendientes_importacion WHERE importacion_id = ?1)",
        [importacion],
    )
    .map_err(|_| NsError::StorageFailure)?;
    tx.commit().map_err(|_| NsError::StorageFailure)
}

impl Importador {
    /// Arranca el hilo y retoma lo que hubiera quedado a medias.
    pub fn arrancar(r: Recursos, avisar: impl Fn(&ProgresoImportacion) + Send + 'static) -> Self {
        let (tx, rx) = mpsc::channel();
        let progreso = Arc::new(Mutex::new(ProgresoImportacion::default()));
        let p = Arc::clone(&progreso);
        let recursos = Arc::new(r);
        let hilo = Arc::clone(&recursos);
        let lanzado = std::thread::Builder::new()
            .name("importador".into())
            .spawn(move || bucle(&hilo, &rx, &p, &avisar));
        if lanzado.is_err() {
            tracing::error!("no se pudo lanzar el importador");
        }
        Self {
            tx,
            progreso,
            recursos,
        }
    }

    /// Ejecuta algo con el entorno de la canalización: lo que hace Por revisar al
    /// importar un archivo a mano.
    ///
    /// # Errors
    ///
    /// Los de `f`, y [`NsError::StorageFailure`] si no hay carpeta de música.
    pub fn con_entorno<T>(&self, f: impl FnOnce(&Entorno<'_>) -> NsResult<T>) -> NsResult<T> {
        let r = &self.recursos;
        let e = Entorno {
            db: &r.db,
            rutas: &r.rutas,
            red: &r.red,
            musica: carpeta_musica(&r.db)?,
            clave_acoustid: None,
            clave_theaudiodb: clave(Servicio::TheAudioDb, "www.theaudiodb.com"),
            fpcalc: r.fpcalc.clone(),
            organizar: preferencia(&r.db, "organizar_archivos")
                .and_then(|v| v.as_bool())
                .unwrap_or(true),
            importacion: None,
            ia: super::ia::configurada(&r.db, &r.red),
        };
        f(&e)
    }

    /// Añade archivos o carpetas a la cola.
    pub fn importar(&self, rutas: Vec<PathBuf>) {
        let _ = self.tx.send(Mensaje::Rutas(rutas));
    }

    pub fn progreso(&self) -> ProgresoImportacion {
        self.progreso
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .clone()
    }
}

fn bucle(
    r: &Recursos,
    rx: &Receiver<Mensaje>,
    p: &Arc<Mutex<ProgresoImportacion>>,
    avisar: &dyn Fn(&ProgresoImportacion),
) {
    let publicar = |cambio: &dyn Fn(&mut ProgresoImportacion)| {
        let copia = {
            let mut g = p.lock().unwrap_or_else(PoisonError::into_inner);
            cambio(&mut g);
            g.clone()
        };
        avisar(&copia);
    };
    let mut primera = true;
    loop {
        if !primera {
            match rx.recv() {
                Ok(Mensaje::Rutas(rutas)) => {
                    let archivos = expandir(&rutas);
                    if !archivos.is_empty() {
                        if let Err(error) = nueva_importacion(&r.db, "manual", &archivos) {
                            tracing::error!(
                                codigo = error.code(),
                                "no se pudo apuntar una importación"
                            );
                        }
                    }
                }
                Err(_) => return,
            }
        }
        primera = false;
        // Lo que llegue mientras tanto se suma a esta misma tanda.
        while let Ok(Mensaje::Rutas(rutas)) = rx.try_recv() {
            let archivos = expandir(&rutas);
            if !archivos.is_empty() {
                let _ = nueva_importacion(&r.db, "manual", &archivos);
            }
        }
        let cola = pendientes(&r.db).unwrap_or_default();
        if cola.is_empty() {
            continue;
        }
        let Ok(musica) = carpeta_musica(&r.db) else {
            tracing::error!("no hay carpeta de música donde importar");
            continue;
        };
        publicar(&|g| {
            *g = ProgresoImportacion {
                activa: true,
                total: cola.len() as u32,
                ..ProgresoImportacion::default()
            };
        });
        let mut gestor = Gestor::desde_biblioteca(&r.db).unwrap_or_default();
        let organizar = preferencia(&r.db, "organizar_archivos")
            .and_then(|v| v.as_bool())
            .unwrap_or(true);
        // Una vez por tanda: leer el llavero por archivo no aporta nada.
        let config_ia = super::ia::configurada(&r.db, &r.red);
        let (clave_acoustid, clave_theaudiodb) = (
            clave(Servicio::AcoustId, "api.acoustid.org"),
            clave(Servicio::TheAudioDb, "www.theaudiodb.com"),
        );
        for (ruta, importacion) in cola {
            let nombre = ruta.file_name().map(|n| n.to_string_lossy().into_owned());
            publicar(&|g| g.actual.clone_from(&nombre));
            let e = Entorno {
                db: &r.db,
                rutas: &r.rutas,
                red: &r.red,
                musica: musica.clone(),
                clave_acoustid: clave_acoustid.clone(),
                clave_theaudiodb: clave_theaudiodb.clone(),
                fpcalc: r.fpcalc.clone(),
                organizar,
                importacion: Some(importacion),
                ia: config_ia.clone(),
            };
            let resultado = if ruta.is_file() {
                canalizacion::procesar(&e, &mut gestor, &ruta).ok()
            } else {
                // Se movió o se borró mientras esperaba: no hay nada que hacer.
                Some(Resultado::Omitido)
            };
            if resultado.is_none() {
                tracing::error!("un archivo no se pudo procesar");
            }
            let _ = terminar_archivo(&r.db, &ruta, importacion, resultado.as_ref());
            publicar(&|g| {
                g.hechos += 1;
                match resultado {
                    Some(Resultado::Importada {
                        verificada: true, ..
                    }) => g.importadas += 1,
                    Some(Resultado::Importada {
                        verificada: false, ..
                    }) => {
                        g.importadas += 1;
                        g.sin_verificar += 1;
                    }
                    Some(Resultado::PorRevisar { .. }) => g.por_revisar += 1,
                    _ => {}
                }
            });
        }
        publicar(&|g| {
            g.activa = false;
            g.actual = None;
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::audio::pruebas::wav;
    use crate::catalogo::etiquetas::{self, Escritura};
    use crate::net::PoliticaDeRed;

    #[test]
    fn expandir_recorre_carpetas_y_deja_lo_que_no_es_audio() {
        let d = std::env::temp_dir().join(format!("ns-expandir-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(d.join("b/c")).unwrap();
        for f in ["a.mp3", "b/2.FLAC", "b/c/3.m4a", "b/notas.txt", "b/1.wav"] {
            std::fs::write(d.join(f), b"").unwrap();
        }
        let e = expandir(std::slice::from_ref(&d));
        let rel: Vec<String> = e
            .iter()
            .map(|p| {
                p.strip_prefix(&d)
                    .unwrap()
                    .to_string_lossy()
                    .replace('\\', "/")
            })
            .collect();
        assert_eq!(rel, ["a.mp3", "b/1.wav", "b/2.FLAC", "b/c/3.m4a"]);
    }

    #[test]
    fn una_importacion_cortada_sigue_al_arrancar() {
        let d = std::env::temp_dir().join(format!("ns-importador-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        let rutas = Rutas::bajo(&d).unwrap();
        let musica = d.join("musica");
        std::fs::create_dir_all(&musica).unwrap();
        let db = BaseDeDatos::abrir(&rutas.base_de_datos()).unwrap();
        db.conexion()
            .unwrap()
            .execute(
                "INSERT INTO preferencias (clave, valor) VALUES ('carpeta_musica', ?1)",
                [serde_json::Value::from(musica.to_string_lossy().into_owned()).to_string()],
            )
            .unwrap();
        let mut archivos = Vec::new();
        for (i, t) in ["Uno", "Dos"].iter().enumerate() {
            let a = d.join(format!("{i}.wav"));
            let _ = wav(&a, 44_100, 44_100 * 20, |k, _| {
                ((k * (i + 2)) % 89) as f32 / 300.0
            });
            etiquetas::escribir(
                &a,
                &Escritura {
                    titulo: Some((*t).into()),
                    artista: Some("Alguien".into()),
                    ..Escritura::default()
                },
            )
            .unwrap();
            archivos.push(a);
        }
        // Lo que dejó a medias una sesión anterior.
        nueva_importacion(&db, "manual", &archivos).unwrap();
        let (tx, rx) = mpsc::channel();
        let _imp = Importador::arrancar(
            Recursos {
                db: db.clone(),
                rutas,
                red: Arc::new(Red::new(PoliticaDeRed::default())),
                fpcalc: PathBuf::from("fpcalc"),
            },
            move |p| {
                if !p.activa && p.hechos > 0 {
                    let _ = tx.send(p.clone());
                }
            },
        );
        let fin = rx.recv_timeout(std::time::Duration::from_secs(30)).unwrap();
        assert_eq!((fin.total, fin.importadas, fin.sin_verificar), (2, 2, 2));
        let (pistas, pendientes, estado): (i64, i64, String) = db
            .conexion()
            .unwrap()
            .query_row(
                "SELECT (SELECT count(*) FROM pistas), (SELECT count(*) FROM pendientes_importacion),
                        (SELECT estado FROM importaciones)",
                [],
                |f| Ok((f.get(0)?, f.get(1)?, f.get(2)?)),
            )
            .unwrap();
        assert_eq!((pistas, pendientes, estado.as_str()), (2, 0, "terminada"));
    }
}
